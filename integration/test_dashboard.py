"""The controlled batch fixture -> real storage -> rendered Streamlit path."""

import json
import os
import socket
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from integration.conftest import ROOT, Database
from integration.test_database import future_snapshot
from portfolio_forecasting import dashboard
from portfolio_forecasting.config import DEFAULT_TICKERS
from portfolio_forecasting.dashboard_data import Reader, Unavailable
from portfolio_forecasting.market_data import PreparedData, prepare_data, utc_now
from portfolio_forecasting.publishing import publish_request
from portfolio_forecasting.sessions import plan_sessions
from portfolio_forecasting.snapshots import write_snapshot
from portfolio_forecasting.store_contract import Release
from tests.market_fixtures import synthetic_history


def test_batch_fixture_real_storage_and_rendered_dashboard(
    database: Database,
    frozen_data: PreparedData,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = replace(
        frozen_data.resolved.request,
        tickers=DEFAULT_TICKERS,
        scientific_revision="m5-" + str(uuid4()),
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
    snapshot = write_snapshot(data, tmp_path / "inputs")
    run = publish_request(
        request,
        database.client(),
        Release.capture(ROOT / "uv.lock"),
        snapshot_directory=tmp_path / "work",
        input_snapshot=snapshot,
    )
    assert isinstance(run, dict)
    assert len(run["assets"]) == 12
    calls = []
    reader = Reader(database.client("anon"))

    def read(name: str, arguments: dict[str, Any]) -> Any:
        calls.append(name)
        return reader.query(name, arguments)

    monkeypatch.setattr(dashboard, "read_query", read)
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    assert not app.exception and not app.error
    app.selectbox[1].select(run["run_id"]).run()
    assert len(app.dataframe[0].value) == 12
    assert app.selectbox[2].options == sorted(DEFAULT_TICKERS)
    assert any("Outcome pending" in item.value for item in app.info)
    assert len(app.get("plotly_chart")) == 2
    # Native PostgREST is configured to return at most three ordinary rows.
    # Its one complete JSON run still renders all twelve allocations.
    evidence: dict[str, Any] = {
        "run_id": run["run_id"],
        "target": plan.forecast_target.isoformat(),
        "cutoff": plan.observation_cutoff.isoformat(),
        "assets": len(run["assets"]),
        "source_sha256": run["identity"]["software_revision"],
        "lock_sha256": run["identity"]["lock_sha256"],
        "first_render": {"charts": len(app.get("plotly_chart")), "pending": True},
    }
    future = future_snapshot(data, tmp_path / "outcome")
    observed = database.client().observe(run["run_id"], future)
    assert observed["matched"] == 12
    app.run()
    assert not app.exception and not app.error
    assert any("Exact-target outcome" in item.value for item in app.success)
    assert len(app.metric) == 7
    chart = json.loads(app.get("plotly_chart")[-1].proto.spec)
    assert chart["data"][0]["x"] == [plan.forecast_target.isoformat()]
    assert chart["data"][1]["y"][0] > 0
    evidence["matched_render"] = {
        "metrics": {item.label: item.value for item in app.metric},
        "forecast_table": app.dataframe[0].value.to_dict(orient="records"),
        "error_table": app.dataframe[-1].value.to_dict(orient="records"),
        "history_dates": app.dataframe[1].value["Session"].tolist(),
    }
    assert set(calls) == {"pf_run", "pf_runs", "pf_history"}
    assert (
        database.sql(
            f"SELECT count(*) FROM pf_private.attempts WHERE run_id='{run['run_id']}';"
        ).strip()
        == "1"
    )
    if os.environ.get("M5_RECORD_DEMO") == "1":
        directory = ROOT / "artifacts/milestone5/demo"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "rendered.json").write_text(json.dumps(evidence, indent=2) + "\n")
        _browser_demo(database, directory)


def test_real_dashboard_rejects_writer_credentials(database: Database) -> None:
    with pytest.raises(Unavailable):
        Reader(database.client()).query("pf_runs", {"p_limit": 25})


def _browser_demo(database: Database, directory: Path) -> None:
    python = os.environ["M5_BROWSER_PYTHON"]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = {
        **os.environ,
        "SUPABASE_URL": database.url,
        "SUPABASE_KEY": "disposable-api-key",
        "SUPABASE_ACCESS_TOKEN": database.token("anon"),
    }
    with (directory / "streamlit.log").open("w") as log:
        process = subprocess.Popen(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "streamlit",
                "run",
                "integration/dashboard_app.py",
                "--server.address=127.0.0.1",
                f"--server.port={port}",
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
            ],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    with urlopen(
                        f"http://127.0.0.1:{port}/_stcore/health", timeout=1
                    ) as response:
                        assert response.status == 200
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise AssertionError("local demo failed to start") from None
                    time.sleep(0.1)
            subprocess.run(
                [
                    python,
                    "scripts/milestone5_browser.py",
                    "--url",
                    f"http://127.0.0.1:{port}",
                    "--output",
                    str(directory),
                ],
                cwd=ROOT,
                check=True,
                timeout=90,
            )
        finally:
            process.terminate()
            process.wait(timeout=15)
