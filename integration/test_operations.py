import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from integration.conftest import ROOT, Database
from integration.test_database import future_snapshot, staged
from portfolio_forecasting import operations
from portfolio_forecasting.dashboard_data import Unavailable
from portfolio_forecasting.market_data import PreparedData, utc_now
from portfolio_forecasting.snapshots import software_metadata
from portfolio_forecasting.store_contract import Release, StoreError


def manifest(root: Path) -> dict[str, Any]:
    (root / "uv.lock").write_bytes((ROOT / "uv.lock").read_bytes())
    value = {
        "revision": "a" * 40,
        "lock_sha256": Release.capture(root / "uv.lock").lock_sha256,
        "source_sha256": software_metadata()["source_sha256"],
    }
    (root / "release.json").write_text(json.dumps(value))
    return value


def test_real_reader_readiness_and_revision_rejection(
    database: Database, frozen_data: PreparedData, tmp_path: Path
) -> None:
    writer, run_id, attempt, payload, _ = staged(
        database, frozen_data, tmp_path / "stage"
    )
    writer.publish(run_id, payload, attempt, utc_now(), {})
    value = manifest(tmp_path)
    result = operations.readiness(database.client("anon"), tmp_path)
    assert result["status"] == "ready" and result["latest_run"] is not None
    with pytest.raises(Unavailable):
        operations.readiness(database.client(), tmp_path)
    for field in ("lock_sha256", "source_sha256", "revision"):
        (tmp_path / "release.json").write_text(json.dumps({**value, field: "invalid"}))
        with pytest.raises(StoreError):
            operations.readiness(database.client("anon"), tmp_path)


def test_batch_outcome_recovery_uses_bound_exact_inputs(
    database: Database,
    frozen_data: PreparedData,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import uuid4

    from integration.test_database import document
    from portfolio_forecasting.snapshots import read_snapshot
    from portfolio_forecasting.store_contract import identity_for

    writer, prior, attempt, payload, _ = staged(
        database, frozen_data, tmp_path / "prior"
    )
    writer.publish(prior, payload, attempt, utc_now(), {})
    later = read_snapshot(future_snapshot(frozen_data, tmp_path / "future"))
    data, snapshot, release, payload = document(later, tmp_path / "later")
    attempt = str(uuid4())
    bound = writer.stage(
        identity_for(data.resolved, data.plan, release), snapshot, attempt, utc_now()
    )
    run = writer.publish(bound["run_id"], payload, attempt, utc_now(), {})
    monkeypatch.setattr(operations, "publish_request", lambda *args, **kwargs: run)
    monkeypatch.setattr(
        operations, "utc_now", lambda: datetime(2026, 9, 8, 9, tzinfo=UTC)
    )
    result = operations.batch(writer, ROOT, tmp_path / "recovery")
    assert result["status"] == "success" and result["observed_runs"] >= 1
    assert all(
        asset["outcome"]["state"] == "matched"
        for asset in writer.get_run(prior)["assets"]
    )
    count = database.sql(
        f"SELECT count(*) FROM pf_private.outcomes WHERE run_id='{prior}'"
    ).strip()
    operations.batch(writer, ROOT, tmp_path / "recovery")
    assert (
        database.sql(
            f"SELECT count(*) FROM pf_private.outcomes WHERE run_id='{prior}'"
        ).strip()
        == count
    )


def test_clean_locked_release_web_readiness_and_rollback(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real locked install + non-root processes; only systemd is replaced locally."""
    import os
    import shutil
    import socket
    import subprocess
    import time
    from urllib.request import urlopen

    from tests.test_deployment import gateway

    repository = tmp_path / "repository"
    repository.mkdir()
    files = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    for name in files:
        source = ROOT / name
        if source.is_file():
            target = repository / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Local release fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Local verification snapshot",
        ],
        cwd=repository,
        check=True,
    )
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    archive = subprocess.check_output(
        ["git", "archive", "--format=tar", revision], cwd=repository
    )
    host = tmp_path / "host"
    (host / "releases").mkdir(parents=True)
    monkeypatch.setattr(gateway, "ROOT", host)
    monkeypatch.setattr(gateway, "UV", os.environ.get("M6_UV", "uv"))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = {
        **os.environ,
        "SUPABASE_URL": database.url,
        "SUPABASE_KEY": "disposable-api-key",
        "SUPABASE_ACCESS_TOKEN": database.token("anon"),
    }
    running: list[subprocess.Popen[bytes]] = []
    readiness_program = """
import os
from pathlib import Path
from portfolio_forecasting.operations import readiness
from portfolio_forecasting.supabase_store import StoreCredentials, SupabaseStore
assert os.geteuid() != 0
store = SupabaseStore(StoreCredentials.from_environment(), api_prefix="")
print(readiness(store, Path.cwd()))
"""

    def restart() -> None:
        for process in running:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        active = (host / "current").resolve()
        process = subprocess.Popen(
            [
                str(active / ".venv/bin/python"),
                "-m",
                "streamlit",
                "run",
                "integration/dashboard_app.py",
                "--server.address=127.0.0.1",
                f"--server.port={port}",
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
            ],
            cwd=active,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        running.append(process)
        until = time.monotonic() + 20
        while True:
            try:
                with urlopen(
                    f"http://127.0.0.1:{port}/_stcore/health", timeout=1
                ) as response:
                    assert response.read().strip() == b"ok"
                break
            except OSError:
                if time.monotonic() >= until:
                    raise RuntimeError("local web readiness deadline") from None
                time.sleep(0.1)
        result = subprocess.run(
            [str(active / ".venv/bin/python"), "-I", "-c", readiness_program],
            cwd=active,
            env=environment,
            capture_output=True,
            timeout=60,
        )
        if result.returncode:
            raise RuntimeError("local installed-release readiness failed")
        assert revision.encode() in result.stdout

    activate = gateway.activate
    monkeypatch.setattr(
        gateway, "activate", lambda root, candidate: activate(root, candidate, restart)
    )
    try:
        gateway.deploy(archive, revision)
        good = (host / "last-good").resolve()
        assert json.loads((good / "release.json").read_bytes())["revision"] == revision
        bad = host / "releases/bad-readiness"
        (bad / "integration").mkdir(parents=True)
        (bad / ".venv").symlink_to(good / ".venv")
        shutil.copy2(
            good / "integration/dashboard_app.py", bad / "integration/dashboard_app.py"
        )
        shutil.copy2(good / "uv.lock", bad / "uv.lock")
        manifest = json.loads((good / "release.json").read_bytes())
        (bad / "release.json").write_text(
            json.dumps({**manifest, "source_sha256": "f" * 64})
        )
        with pytest.raises(RuntimeError, match="readiness failed"):
            activate(host, bad, restart)
        assert (host / "current").resolve() == good
        assert running[-1].poll() is None
    finally:
        for process in running:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
