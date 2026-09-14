import copy
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from integration.conftest import ROOT, Database
from portfolio_forecasting.allocation import allocate_forecasts
from portfolio_forecasting.forecasting import FIT_OPTIONS, AssetForecast, model_options
from portfolio_forecasting.market_data import PreparedData, prepare_data, utc_now
from portfolio_forecasting.pipeline import ForecastReport
from portfolio_forecasting.portfolio import PortfolioReport
from portfolio_forecasting.publishing import publish_request, resume_publication
from portfolio_forecasting.sessions import plan_sessions
from portfolio_forecasting.snapshots import (
    canonical_bytes,
    read_snapshot,
    write_snapshot,
)
from portfolio_forecasting.store_contract import (
    Release,
    StoreConflict,
    StoreError,
    identity_for,
    publication_payload,
)
from portfolio_forecasting.supabase_store import SupabaseStore, http_transport
from tests.market_fixtures import synthetic_history


def require_bound(writer: SupabaseStore, run_id: str) -> dict[str, Any]:
    value = writer.lookup(run_id=run_id)
    assert value is not None
    return value


def document(
    data: PreparedData, directory: Path
) -> tuple[PreparedData, Path, Release, dict[str, Any]]:
    request = replace(data.resolved.request, scientific_revision=str(uuid4()))
    resolved = request.resolve()
    plan = plan_sessions(resolved)
    assert plan is not None
    data = prepare_data(resolved, plan, data.assets)
    path = write_snapshot(data, directory)
    release = Release.capture(ROOT / "uv.lock")
    forecasts = tuple(
        AssetForecast(
            asset.ticker,
            plan.observation_cutoff,
            plan.forecast_target,
            asset.observations[-1].price,
            asset.observations[-1].price * 1.001,
            0.001,
            canonical_bytes(
                {
                    "constructor": model_options(data),
                    "fit": FIT_OPTIONS,
                    "fixture": "deterministic publication contract",
                }
            ).decode(),
        )
        for asset in data.assets
    )
    allocation = allocate_forecasts(data, forecasts)
    now = utc_now()
    report = PortfolioReport(
        ForecastReport(str(uuid4()), data, forecasts, path, now, ()),
        allocation,
        now,
        0.0,
    )
    return data, path, release, publication_payload(report, release)


def staged(
    database: Database, data: PreparedData, directory: Path
) -> tuple[SupabaseStore, str, str, dict[str, Any], Path]:
    data, path, release, payload = document(data, directory)
    writer = database.client()
    writer.preflight(writer=True)
    attempt = str(uuid4())
    bound = writer.stage(
        identity_for(data.resolved, data.plan, release), path, attempt, utc_now()
    )
    return writer, bound["run_id"], attempt, payload, path


def test_fresh_migrations_are_repeatable_and_roles_restricted(
    database: Database,
) -> None:
    assert (
        database.sql("select count(*) from pf_private.schema_migrations").strip() == "2"
    )
    subprocess.run(
        [str(ROOT / ".venv/bin/python"), "scripts/migrate.py"],
        cwd=ROOT,
        env=database.environment,
        check=True,
    )
    assert (
        database.sql("select count(*) from pf_private.schema_migrations").strip() == "2"
    )
    assert (
        database.sql(
            "select rolsuper or rolbypassrls or rolcreaterole "
            "from pg_roles where rolname='portfolio_writer'"
        ).strip()
        == "f"
    )
    database.client("anon").preflight()
    with pytest.raises(StoreError):
        database.client("anon").preflight(writer=True)
    with pytest.raises(StoreError):
        database.client("service_role").preflight(writer=True)


def test_staged_runs_and_snapshots_are_private(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, _, _, path = staged(database, frozen_data, tmp_path)
    reader = database.client("anon")
    with pytest.raises(StoreError):
        reader.get_run(run_id)
    with pytest.raises(StoreError):
        reader.lookup(run_id=run_id)
    with pytest.raises(StoreError):
        reader.bound_snapshot(path.stem, tmp_path / "forbidden")
    assert require_bound(writer, run_id)["state"] == "staged"
    assert (
        database.sql(
            "SET ROLE anon; SELECT count(*) FROM pf_private.runs "
            f"WHERE run_id='{run_id}';"
        )
        .strip()
        .endswith("0")
    )
    assert "permission denied" in database.sql(
        "SET ROLE anon; SELECT content FROM pf_private.snapshots;", ok=False
    )
    assert "permission denied" in database.sql(
        "SET ROLE portfolio_writer; INSERT INTO pf_private.snapshots "
        "VALUES ('bad','bad','bad',now());",
        ok=False,
    )


def test_atomic_publication_idempotency_conflicts_and_complete_read(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, attempt, payload, _ = staged(database, frozen_data, tmp_path)
    first = writer.publish(run_id, payload, attempt, utc_now(), {})
    assert first == writer.publish(run_id, payload, attempt, utc_now(), {})
    assert database.client("anon").get_run(run_id) == first
    assert (
        database.sql(
            f"SELECT count(*) FROM pf_private.asset_results WHERE run_id='{run_id}'"
        ).strip()
        == "2"
    )
    changed = copy.deepcopy(payload)
    changed["risk_estimator"] = "changed"
    with pytest.raises(StoreConflict):
        writer.publish(run_id, changed, attempt, utc_now(), {})
    assert writer.get_run(run_id) == first
    with pytest.raises(StoreError):
        database.client("anon").publish(run_id, payload, attempt, utc_now(), {})
    assert "immutable" in database.sql(
        f"UPDATE pf_private.asset_results SET weight=0.5 WHERE run_id='{run_id}';",
        ok=False,
    )


@pytest.mark.parametrize("invalid", [None, "NaN", "Infinity", "0.5", True])
def test_invalid_scientific_values_roll_back_every_asset(
    database: Database, frozen_data: PreparedData, tmp_path: Path, invalid: object
) -> None:
    writer, run_id, attempt, payload, _ = staged(database, frozen_data, tmp_path)
    changed = copy.deepcopy(payload)
    changed["assets"][1]["weight"] = invalid
    with pytest.raises(StoreError):
        writer.publish(run_id, changed, attempt, utc_now(), {})
    assert require_bound(writer, run_id)["state"] == "staged"
    assert (
        database.sql(
            f"SELECT count(*) FROM pf_private.asset_results WHERE run_id='{run_id}'"
        ).strip()
        == "0"
    )
    writer.publish(run_id, payload, attempt, utc_now(), {})


def test_failed_new_run_preserves_previous_success(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, previous, attempt, payload, _ = staged(
        database, frozen_data, tmp_path / "old"
    )
    saved = writer.publish(previous, payload, attempt, utc_now(), {})
    writer, fresh, attempt, payload, _ = staged(database, frozen_data, tmp_path / "new")
    payload["assets"].pop()
    with pytest.raises(StoreError):
        writer.publish(fresh, payload, attempt, utc_now(), {})
    assert database.client("anon").get_run(previous) == saved
    assert fresh not in {
        row["run_id"] for row in database.client("anon").runs()["items"]
    }


def test_concurrent_publish_and_lost_success_reply(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, attempt, payload, _ = staged(
        database, frozen_data, tmp_path / "concurrent"
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: database.client().publish(
                    run_id, payload, attempt, utc_now(), {}
                ),
                range(4),
            )
        )
    assert all(result == results[0] for result in results)
    writer, run_id, attempt, payload, _ = staged(
        database, frozen_data, tmp_path / "lost"
    )
    lost = False

    def transport(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> bytes:
        nonlocal lost
        result = http_transport(url, body, headers, timeout)
        if url.endswith("pf_publish") and not lost:
            lost = True
            raise TimeoutError("simulated lost committed response")
        return result

    retrying = SupabaseStore(
        writer.credentials,
        transport=transport,
        api_prefix="",
        sleeper=lambda duration: None,
    )
    assert (
        retrying.publish(run_id, payload, attempt, utc_now(), {})["state"]
        == "published"
    )
    assert lost
    assert (
        database.sql(
            f"SELECT count(*) FROM pf_private.asset_results WHERE run_id='{run_id}'"
        ).strip()
        == "2"
    )


def test_first_binding_wins_and_changes_require_revision(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    data, path, release, _ = document(frozen_data, tmp_path / "a")
    changed_assets = tuple(
        replace(
            asset,
            observations=tuple(
                replace(row, price=row.price * 1.01) for row in asset.observations
            ),
        )
        for asset in data.assets
    )
    changed = prepare_data(data.resolved, data.plan, changed_assets)
    other = write_snapshot(changed, tmp_path / "b")
    identity = identity_for(data.resolved, data.plan, release)

    def bind(snapshot: Path) -> object:
        try:
            return database.client().stage(identity, snapshot, str(uuid4()), utc_now())
        except StoreConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(bind, (path, other)))
    assert results.count("conflict") == 1
    bound = database.client().lookup(identity=identity)
    assert bound is not None
    assert bound["snapshot_sha256"] in (path.stem, other.stem)
    assert database.client().bound_snapshot(
        bound["snapshot_sha256"], tmp_path / "read"
    ).read_bytes() in (path.read_bytes(), other.read_bytes())
    revised, revised_path, revised_release, _ = document(changed, tmp_path / "revision")
    distinct = database.client().stage(
        identity_for(revised.resolved, revised.plan, revised_release),
        revised_path,
        str(uuid4()),
        utc_now(),
    )
    assert distinct["run_id"] != bound["run_id"]


def test_interrupted_fit_resumes_bound_inputs_with_real_prophet(
    database: Database,
    frozen_data: PreparedData,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data, path, release, _ = document(frozen_data, tmp_path / "input")
    import portfolio_forecasting.publishing as publishing
    from portfolio_forecasting.forecasting import forecast_prices

    real = forecast_prices

    def broken(*args: object, **kwargs: object) -> None:
        raise ValueError("controlled fit interruption")

    monkeypatch.setattr(publishing, "forecast_prices", broken)
    with pytest.raises(ValueError, match="interruption"):
        publish_request(
            data.resolved.request,
            database.client(),
            release,
            snapshot_directory=tmp_path / "work",
            input_snapshot=path,
        )
    bound = database.client().lookup(
        identity=identity_for(data.resolved, data.plan, release)
    )
    assert bound is not None
    assert bound["state"] == "staged" and bound["snapshot_sha256"] == path.stem
    monkeypatch.setattr(publishing, "forecast_prices", real)
    complete = resume_publication(
        bound["run_id"],
        database.client(),
        release,
        snapshot_directory=tmp_path / "resume",
    )
    assert complete["state"] == "published"
    monkeypatch.setattr(publishing, "forecast_prices", broken)
    assert (
        resume_publication(
            bound["run_id"],
            database.client(),
            release,
            snapshot_directory=tmp_path / "again",
        )
        == complete
    )


def future_snapshot(
    data: PreparedData, directory: Path, *, missing: bool = False, split: bool = False
) -> Path:
    request = replace(
        data.resolved.request,
        history_start=date(2026, 9, 9) if missing else date(2026, 7, 1),
        history_end=date(2026, 9, 12),
    )
    resolved = request.resolve()
    plan = plan_sessions(resolved)
    assert plan is not None
    assets = tuple(
        replace(
            synthetic_history(ticker, plan.sessions, offset=index * 10),
            retrieved_at=utc_now(),
        )
        for index, ticker in enumerate(request.tickers)
    )
    if split:
        assets = tuple(
            replace(
                asset,
                observations=tuple(
                    replace(row, price=row.price / 2) for row in asset.observations
                ),
            )
            for asset in assets
        )
    return write_snapshot(prepare_data(resolved, plan, assets), directory)


def test_exact_target_across_gap_and_revised_basis_history(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, attempt, payload, _ = staged(
        database, frozen_data, tmp_path / "base"
    )
    original = writer.publish(run_id, payload, attempt, utc_now(), {})
    missing = future_snapshot(frozen_data, tmp_path / "missing", missing=True)
    assert writer.observe(run_id, missing)["pending"] == 2
    assert all(
        row["outcome"]["actual_price"] is None
        for row in writer.get_run(run_id)["assets"]
    )
    source = future_snapshot(frozen_data, tmp_path / "matured")
    assert writer.observe(run_id, source)["matched"] == 2
    assert writer.observe(run_id, source)["matched"] == 2
    complete = writer.get_run(run_id)
    expected = {
        asset.ticker: next(
            row.price for row in asset.observations if row.session == date(2026, 9, 8)
        )
        for asset in read_snapshot(source).assets
    }
    assert all(
        row["outcome"]["actual_price"] == expected[row["ticker"]]
        for row in complete["assets"]
    )
    assert all(row["outcome"]["target"] == "2026-09-08" for row in complete["assets"])
    revised = future_snapshot(frozen_data, tmp_path / "split", split=True)
    assert writer.observe(run_id, revised)["incompatible"] == 2
    latest = writer.get_run(run_id)
    assert all(
        row["outcome"]["reason"] == "adjusted_history_changed"
        and row["outcome"]["actual_price"] is None
        for row in latest["assets"]
    )
    assert latest["scientific_payload"] == original["scientific_payload"]
    assert (
        database.sql(
            f"SELECT count(*) FROM pf_private.outcomes WHERE run_id='{run_id}'"
        ).strip()
        == "6"
    )


def test_bounded_pages_and_complete_runs_exceed_api_row_limit(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    created = set()
    for index in range(5):
        writer, run_id, attempt, payload, _ = staged(
            database, frozen_data, tmp_path / str(index)
        )
        writer.publish(run_id, payload, attempt, utc_now(), {})
        created.add(run_id)
    reader = database.client("anon")
    seen: set[str] = set()
    cursor = None
    watermark = None
    for _ in range(100):
        page = reader.runs(limit=2, cursor=cursor, as_of=watermark)
        assert not seen.intersection(row["run_id"] for row in page["items"])
        seen.update(row["run_id"] for row in page["items"])
        cursor, watermark = page["next_cursor"], page["as_of"]
        if cursor is None:
            break
    else:
        raise AssertionError("pagination did not terminate")
    assert created <= seen
    history = reader.history("AMD", date(2026, 9, 8), date(2026, 9, 8), limit=2)
    assert len(history["items"]) == 2 and history["next_cursor"] is not None
    assert all(
        row["target"] == "2026-09-08" and row["asset"]["ticker"] == "AMD"
        for row in history["items"]
    )


def test_invalid_jwt_and_reader_cli_roundtrip(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, attempt, payload, _ = staged(database, frozen_data, tmp_path)
    writer.publish(run_id, payload, attempt, utc_now(), {})
    bad = SupabaseStore(
        replace(writer.credentials, access_token="invalid.token.signature"),
        api_prefix="",
    )
    with pytest.raises(StoreError, match="401"):
        bad.preflight()
    env = {
        **database.environment,
        "SUPABASE_URL": database.url,
        "SUPABASE_KEY": "disposable-api-key",
        "SUPABASE_ACCESS_TOKEN": database.token("anon"),
    }
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "portfolio_forecasting.publish",
            "--api-prefix",
            "",
            "read",
            run_id,
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run_id"] == run_id
    assert env["SUPABASE_ACCESS_TOKEN"] not in result.stdout + result.stderr


def test_equivalent_number_types_share_one_identity(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    data, path, release, _ = document(frozen_data, tmp_path)
    identity = identity_for(data.resolved, data.plan, release)
    first = database.client().stage(identity, path, str(uuid4()), utc_now())
    identity["allocation"]["risk_aversion"] = 5
    second = database.client().stage(identity, path, str(uuid4()), utc_now())
    assert (
        first["run_id"] == second["run_id"]
        and first["request_key"] == second["request_key"]
    )


def test_missing_completion_and_incomplete_direct_sql_publication_rejected(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, attempt, payload, _ = staged(database, frozen_data, tmp_path)
    with pytest.raises(StoreError):
        writer.rpc(
            "pf_publish",
            {
                "p_run_id": run_id,
                "p_attempt_id": attempt,
                "p_payload": payload,
                "p_completed_at": None,
            },
        )
    error = database.sql(
        "UPDATE pf_private.runs SET state='published',payload='{}',"
        "result_sha256=pf_private.hash_json('{}'),"
        f"completed_at=now(),published_at=now() WHERE run_id='{run_id}';",
        ok=False,
    )
    assert "complete feasible portfolio" in error
    assert require_bound(writer, run_id)["state"] == "staged"


def test_applied_migration_changes_fail(database: Database, tmp_path: Path) -> None:
    for path in (ROOT / "supabase/migrations").glob("*.sql"):
        (tmp_path / path.name).write_bytes(
            path.read_bytes() + b"\n-- changed applied content\n"
        )
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "scripts/migrate.py",
            "--migrations",
            str(tmp_path),
        ],
        cwd=ROOT,
        env=database.environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert (
        database.sql("SELECT count(*) FROM pf_private.schema_migrations").strip() == "2"
    )


def test_twelve_asset_real_compute_publish_cli_and_resume(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    from portfolio_forecasting.config import DEFAULT_TICKERS

    request = replace(
        frozen_data.resolved.request,
        tickers=DEFAULT_TICKERS,
        scientific_revision=str(uuid4()),
    )
    resolved = request.resolve()
    plan = plan_sessions(resolved)
    assert plan is not None
    data = prepare_data(
        resolved,
        plan,
        tuple(
            replace(
                synthetic_history(ticker, plan.sessions, offset=index * 10),
                retrieved_at=utc_now(),
            )
            for index, ticker in enumerate(request.tickers)
        ),
    )
    path = write_snapshot(data, tmp_path / "input")
    env = {
        **database.environment,
        "SUPABASE_URL": database.url,
        "SUPABASE_KEY": "disposable-api-key",
        "SUPABASE_ACCESS_TOKEN": database.token("portfolio_writer"),
    }
    command = [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "portfolio_forecasting.publish",
        "--api-prefix",
        "",
        "--snapshots",
        str(tmp_path / "work"),
    ]
    result = subprocess.run(
        command + ["compute", "--snapshot", str(path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    run = json.loads(result.stdout)
    assert len(run["assets"]) == 12  # Real PostgREST max-rows is deliberately only 3.
    assert abs(sum(row["weight"] for row in run["assets"]) - 1) <= 1e-9
    assert database.client("anon").get_run(run["run_id"]) == run
    evidence = ROOT / "artifacts/milestone4/verification"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "complete-run.json").write_text(json.dumps(run, indent=2) + "\n")
    repeated = subprocess.run(
        command + ["resume", run["run_id"]],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert json.loads(repeated.stdout) == run
    denied = subprocess.run(
        command + ["compute", "--snapshot", str(path)],
        cwd=ROOT,
        env={**env, "SUPABASE_ACCESS_TOKEN": database.token("anon")},
        text=True,
        capture_output=True,
    )
    assert denied.returncode == 1 and not denied.stdout


def test_nonuniform_revised_history_is_detected_before_metrics(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, attempt, payload, _ = staged(
        database, frozen_data, tmp_path / "base"
    )
    writer.publish(run_id, payload, attempt, utc_now(), {})
    source = future_snapshot(frozen_data, tmp_path / "new")
    data = read_snapshot(source)
    asset = data.assets[0]
    revised = replace(
        asset,
        observations=(
            replace(asset.observations[0], price=asset.observations[0].price * 1.01),
            *asset.observations[1:],
        ),
    )
    data = prepare_data(data.resolved, data.plan, (revised, *data.assets[1:]))
    summary = writer.observe(run_id, write_snapshot(data, tmp_path / "revised"))
    assert summary["incompatible"] == 1 and summary["matched"] == 1


def test_expired_live_request_is_rejected_by_database(
    database: Database, tmp_path: Path
) -> None:
    from datetime import UTC, datetime

    from portfolio_forecasting.config import (
        AllocationSettings,
        ForecastSettings,
        RunRequest,
    )

    request = RunRequest(
        tickers=("AMD",),
        history_start=date(2024, 1, 1),
        history_end=date(2026, 9, 8),
        mode="live",
        scientific_revision=str(uuid4()),
        allocation=AllocationSettings(),
        forecast=ForecastSettings(yearly_seasonality=False),
    )
    instant = datetime(2026, 9, 8, 9, tzinfo=UTC)
    resolved = request.resolve(clock=lambda: instant)
    plan = plan_sessions(resolved)
    assert plan is not None
    data = prepare_data(
        resolved,
        plan,
        (replace(synthetic_history("AMD", plan.sessions), retrieved_at=instant),),
    )
    path = write_snapshot(data, tmp_path)
    release = Release.capture(ROOT / "uv.lock")
    with pytest.raises(StoreError, match="410"):
        database.client().stage(
            identity_for(resolved, plan, release), path, str(uuid4()), instant
        )

    # Restore a valid historical staged binding, as if its process had stopped
    # before target opening; a late resume must still fail inside PostgreSQL.
    identity = json.dumps(identity_for(resolved, plan, release)).replace("'", "''")
    content = path.read_text().replace("'", "''")
    attempt = str(uuid4())
    database.sql(f"""
    SELECT pf_private.validate_snapshot('{identity}', '{content}');
    INSERT INTO pf_private.snapshots(snapshot_sha256,content,data_sha256)
    VALUES ('{path.stem}','{content}',('{content}'::jsonb)->>'data_sha256');
    INSERT INTO pf_private.runs(run_id,request_key,identity,snapshot_sha256,
      executed_at,cutoff,target,target_open,target_close)
    VALUES (substr(pf_private.hash_json('{identity}'),1,32)::uuid,
      pf_private.hash_json('{identity}'),'{identity}','{path.stem}',
      '{instant.isoformat()}','{plan.observation_cutoff}','{plan.forecast_target}',
      '{plan.target_open.isoformat()}','{plan.target_close.isoformat()}');
    """)
    writer = database.client()
    bound = writer.lookup(identity=json.loads(identity))
    assert bound is not None
    writer.attempt(bound["run_id"], attempt, utc_now())
    with pytest.raises(StoreError, match="410"):
        writer.publish(bound["run_id"], {}, attempt, utc_now(), {})
    assert require_bound(writer, bound["run_id"])["state"] == "staged"


def test_backup_restore_retains_complete_runs_and_permissions(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, attempt, payload, _ = staged(
        database, frozen_data, tmp_path / "input"
    )
    writer.publish(run_id, payload, attempt, utc_now(), {})
    backup = tmp_path / "portfolio.dump"
    subprocess.run(
        [
            "/usr/lib/postgresql/16/bin/pg_dump",
            "--format=custom",
            "--schema=pf_private",
            "--schema=public",
            "--file",
            str(backup),
        ],
        env=database.environment,
        check=True,
    )
    database.sql("CREATE DATABASE pf_restore")
    restored = {**database.environment, "PGDATABASE": "pf_restore"}
    subprocess.run(
        [
            "/usr/lib/postgresql/16/bin/pg_restore",
            "--exit-on-error",
            "--clean",
            "--if-exists",
            "--dbname=pf_restore",
            str(backup),
        ],
        env=restored,
        check=True,
    )
    check = subprocess.run(
        ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
        input=(
            "SET ROLE anon; SELECT jsonb_array_length("
            f"public.pf_run('{run_id}')->'assets');"
        ),
        env=restored,
        text=True,
        capture_output=True,
    )
    assert check.returncode == 0, check.stderr
    assert check.stdout.strip().endswith("2")
    denial = subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1"],
        input="SET ROLE anon; SELECT content FROM pf_private.snapshots;",
        env=restored,
        text=True,
        capture_output=True,
    )
    assert denial.returncode != 0 and "permission denied" in denial.stderr


def test_committed_run_with_failed_readback_is_not_reported_as_success(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, attempt, payload, _ = staged(database, frozen_data, tmp_path)
    original = writer._transport

    def truncate(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> bytes:
        raw = original(url, body, headers, timeout)
        if url.endswith("/rpc/pf_run"):
            result = json.loads(raw)
            result["assets"].pop()
            return json.dumps(result).encode()
        return raw

    interrupted = SupabaseStore(writer.credentials, transport=truncate, api_prefix="")
    with pytest.raises(StoreError, match="membership"):
        interrupted.publish(run_id, payload, attempt, utc_now(), {})
    assert require_bound(writer, run_id)["state"] == "published"
    assert len(writer.get_run(run_id)["assets"]) == 2
    assert writer.publish(run_id, payload, attempt, utc_now(), {})["run_id"] == run_id


@pytest.mark.parametrize("field", ["constructor", "fit", "packages", "python"])
def test_missing_model_or_software_provenance_rolls_back(
    database: Database, frozen_data: PreparedData, tmp_path: Path, field: str
) -> None:
    writer, run_id, attempt, payload, _ = staged(database, frozen_data, tmp_path)
    if field in ("constructor", "fit"):
        payload["assets"][-1]["model"][field] = None
    else:
        payload["software"][field] = None
    with pytest.raises(StoreError):
        writer.publish(run_id, payload, attempt, utc_now(), {})
    assert require_bound(writer, run_id)["state"] == "staged"
    assert (
        database.sql(
            f"SELECT count(*) FROM pf_private.asset_results WHERE run_id='{run_id}'"
        ).strip()
        == "0"
    )
