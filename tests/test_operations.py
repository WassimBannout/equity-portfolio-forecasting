import copy
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from portfolio_forecasting import operations
from portfolio_forecasting.config import RunRequest
from portfolio_forecasting.dashboard_data import BadRecord, Unavailable
from portfolio_forecasting.pipeline import SkippedForecast
from portfolio_forecasting.store_contract import StoreError
from portfolio_forecasting.supabase_store import StoreCredentials
from tests.dashboard_fixtures import MemoryReads
from tests.test_dashboard import ui_run as ui_run
from tests.test_persistence import release as release
from tests.test_persistence import report as report


@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        ("2026-09-08T09:59:59+00:00", "2026-09-04"),
        ("2026-09-08T10:00:00+00:00", "2026-09-08"),
        ("2026-09-07T12:00:00+00:00", "2026-09-04"),
        ("2026-09-12T12:00:00+00:00", "2026-09-11"),
        ("2026-03-09T10:00:00+00:00", "2026-03-09"),
        ("2026-11-02T09:00:00+00:00", "2026-10-30"),
        ("2027-01-01T10:00:00+00:00", "2026-12-31"),
        ("2026-09-08T00:30:00+00:00", "2026-09-04"),
    ],
)
def test_session_aware_due_time(stamp: str, expected: str) -> None:
    assert operations.expected_session(
        datetime.fromisoformat(stamp)
    ) == date.fromisoformat(expected)


def test_freshness_rejects_naive_clock() -> None:
    with pytest.raises(ValueError, match="aware"):
        operations.expected_session(datetime(2026, 9, 8))


def test_no_runs_and_research_cannot_satisfy_live_monitor(
    ui_run: dict[str, Any],
) -> None:
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    assert (
        operations.freshness_status(MemoryReads([]).query, now)["status"] == "missing"
    )
    assert (
        operations.freshness_status(MemoryReads([ui_run]).query, now)["status"]
        == "missing"
    )


@pytest.mark.parametrize(("day", "state"), [(8, "fresh"), (9, "stale")])
def test_live_monitor_and_complete_read(
    ui_run: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    day: int,
    state: str,
) -> None:
    # The M4 fixture is a small retrospective portfolio. Adapt only the monitor's
    # read boundary; database validity and live deadlines are tested with real SQL.
    from portfolio_forecasting.dashboard_data import Run, summary
    from tests.dashboard_fixtures import run_summary

    run = copy.deepcopy(ui_run)
    request = RunRequest()
    run["identity"].update(
        mode="live",
        universe=sorted(request.tickers),
        scientific_revision=request.scientific_revision,
    )
    now = datetime(2026, 9, day, 12, tzinfo=UTC)
    settings = request.resolve(clock=lambda: now).to_metadata()
    run["identity"].update(
        {key: settings[key] for key in ("forecast", "allocation", "data")}
    )
    run["executed_at"] = "2026-09-08T09:00:00+00:00"
    run["published_at"] = "2026-09-08T09:30:00+00:00"
    reads = MemoryReads([run])
    reads.watermark = now.isoformat()
    monkeypatch.setattr(
        operations, "published_run", lambda value, header: Run(header, (), value)
    )
    result = operations.freshness_status(reads.query, now)
    assert result["status"] == state
    assert result["last_success"]["cutoff"] == "2026-09-04"
    assert result["last_success"]["run_id"] == summary(run_summary(run)).run_id
    assert any(name == "pf_run" for name, _ in reads.calls)
    monkeypatch.setattr(
        operations,
        "published_run",
        lambda *args: (_ for _ in ()).throw(BadRecord("partial")),
    )
    with pytest.raises(BadRecord):
        operations.freshness_status(reads.query, now)


def test_unavailable_is_not_missing() -> None:
    def read(name: str, arguments: dict[str, Any]) -> Any:
        raise Unavailable("controlled DB outage")

    with pytest.raises(Unavailable):
        operations.freshness_status(read, datetime(2026, 9, 8, 12, tzinfo=UTC))


def test_scan_limit_reports_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    from portfolio_forecasting.dashboard_data import Page

    calls = []

    def read(name: str, arguments: dict[str, Any]) -> Any:
        calls.append(arguments.copy())
        return {}

    monkeypatch.setattr(
        operations,
        "read_page",
        lambda *args: Page((), (), "stamp", {"cursor": len(calls)}),
    )
    assert (
        operations.freshness_status(read, datetime(2026, 9, 8, 12, tzinfo=UTC))[
            "status"
        ]
        == "unknown_scan_limit"
    )
    assert len(calls) == 10 and calls[1]["p_as_of"] == "stamp"


def test_batch_closed_session_has_no_outcome_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    resolved = RunRequest().resolve(clock=lambda: datetime(2026, 9, 12, 9, tzinfo=UTC))
    monkeypatch.setattr(operations, "utc_now", lambda: resolved.executed_at)
    monkeypatch.setattr(
        operations,
        "publish_request",
        lambda *args, **kwargs: SkippedForecast("attempt", resolved),
    )
    (tmp_path / "uv.lock").write_text("fixture")
    assert operations.batch(None, tmp_path, tmp_path)["status"] == "no_op"  # type: ignore[arg-type]


def test_batch_failure_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from unittest.mock import Mock

    monkeypatch.setattr(
        operations, "utc_now", lambda: datetime(2026, 9, 8, 9, tzinfo=UTC)
    )
    store = Mock()
    store.lookup.return_value = None

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise StoreError("controlled provider failure")

    monkeypatch.setattr(operations, "publish_request", fail)
    (tmp_path / "uv.lock").write_text("fixture")
    with pytest.raises(StoreError, match="provider"):
        operations.batch(store, tmp_path, tmp_path)


def test_monitor_footer_detects_stopped_timer_and_keeps_last_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    status = tmp_path / "status.json"
    operations.write_status(
        status,
        {
            "checked_at": "2026-01-01T09:00:00+00:00",
            "status": "fresh",
            "expected_target": "2026-01-01",
            "last_success": {
                "published_at": "2025-12-31T09:30:00+00:00",
                "target": "2025-12-31",
                "cutoff": "2025-12-30",
                "run_id": "fixture",
            },
        },
    )
    monkeypatch.setenv("PF_STATUS_FILE", str(status))
    app = AppTest.from_string(
        "from portfolio_forecasting.operations import render_status\nrender_status()"
    ).run()
    assert not app.exception
    assert "monitor overdue" in app.markdown[0].value
    assert "2025-12-30" in app.caption[1].value
    status.write_text("broken")
    app.run()
    assert "unavailable" in app.warning[0].value


def test_cli_sanitizes_errors_and_writes_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = tmp_path / "status.json"
    monkeypatch.setattr(
        "sys.argv", ["operations", "freshness", "--output", str(status)]
    )
    monkeypatch.setattr(
        StoreCredentials,
        "from_environment",
        lambda: (_ for _ in ()).throw(ValueError("secret-marker")),
    )
    assert operations.main() == 1
    assert "secret-marker" not in capsys.readouterr().out
    assert json.loads(status.read_text())["status"] == "unavailable"


def test_repeated_batch_is_an_explicit_no_op(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from unittest.mock import Mock

    store = Mock()
    store.lookup.return_value = {"state": "published"}
    store.runs.return_value = {"items": [], "next_cursor": None}
    monkeypatch.setattr(
        operations, "utc_now", lambda: datetime(2026, 9, 8, 9, tzinfo=UTC)
    )
    monkeypatch.setattr(
        operations,
        "publish_request",
        lambda *args, **kwargs: {
            "run_id": "fixture",
            "snapshot_sha256": "a" * 64,
            "identity": {"observation_cutoff": "2026-09-04"},
        },
    )
    (tmp_path / "uv.lock").write_text("fixture")
    result = operations.batch(store, tmp_path, tmp_path)
    assert result["status"] == "no_op" and result["reason"] == "already_published"
    store.observe.assert_not_called()


def test_late_batch_fails_before_provider_or_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from portfolio_forecasting.errors import ForecastError

    monkeypatch.setattr(
        operations, "utc_now", lambda: datetime(2026, 9, 8, 14, tzinfo=UTC)
    )
    with pytest.raises(ForecastError, match="deadline"):
        operations.batch(None, tmp_path, tmp_path)  # type: ignore[arg-type]
