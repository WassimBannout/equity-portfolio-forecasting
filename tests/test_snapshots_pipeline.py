import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from portfolio_forecasting import RunRequest
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.market_data import AssetHistory, PreparedData
from portfolio_forecasting.pipeline import (
    ForecastReport,
    SkippedForecast,
    compute_forecast,
    replay_forecast,
)
from portfolio_forecasting.snapshots import (
    canonical_bytes,
    read_snapshot,
    write_content,
    write_snapshot,
)
from tests.market_fixtures import NOW


class Source:
    def __init__(self, data: PreparedData):
        self.data = data
        self.calls: list[str] = []

    def fetch(self, ticker: str, resolved: object, *, run_id: str) -> AssetHistory:
        self.calls.append(ticker)
        assert run_id
        return next(asset for asset in self.data.assets if asset.ticker == ticker)


def test_snapshot_roundtrip_revisions_and_tamper(
    prepared: PreparedData, tmp_path: Path
) -> None:
    original = write_snapshot(prepared, tmp_path)
    content = original.read_bytes()
    assert write_snapshot(prepared, tmp_path) == original
    assert read_snapshot(original) == prepared
    asset = prepared.assets[0]
    revised_asset = replace(
        asset,
        observations=(
            replace(asset.observations[0], price=99.0),
            *asset.observations[1:],
        ),
    )
    from portfolio_forecasting.market_data import prepare_data

    revision = prepare_data(
        prepared.resolved, prepared.plan, (revised_asset, prepared.assets[1])
    )
    revised = write_snapshot(revision, tmp_path)
    assert revised != original and original.read_bytes() == content
    assert (
        json.loads(content)["data_sha256"]
        != json.loads(revised.read_bytes())["data_sha256"]
    )
    original.chmod(0o644)
    original.write_bytes(content + b" ")
    with pytest.raises(ForecastError, match="hash mismatch"):
        read_snapshot(original)
    with pytest.raises(ForecastError, match="existing snapshot"):
        write_snapshot(prepared, tmp_path)


def test_snapshot_rejects_validly_hashed_but_invalid_data(
    prepared: PreparedData, tmp_path: Path
) -> None:
    original = write_snapshot(prepared, tmp_path)
    payload = json.loads(original.read_bytes())
    payload["assets"][0]["observations"][-1]["session"] = (
        prepared.plan.forecast_target.isoformat()
    )
    bad = write_content(canonical_bytes(payload), tmp_path)
    with pytest.raises(ForecastError, match="every requested session"):
        read_snapshot(bad)


def test_compute_and_offline_replay_without_credentials(
    prepared: PreparedData, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    source = Source(prepared)
    result = compute_forecast(
        prepared.resolved.request,
        snapshot_directory=tmp_path,
        source=source,
        clock=lambda: NOW,
    )
    assert isinstance(result, ForecastReport)
    assert source.calls == ["AMD", "MSFT"]
    assert result.data == prepared
    metadata = json.loads(canonical_bytes(result.to_metadata()))
    assert metadata["kind"] == "forecast_only"
    assert "weights" not in metadata
    assert metadata["assets"][0]["recent_history"][-1]["session"] == "2026-09-04"
    assert metadata["snapshot_sha256"] == result.snapshot_path.stem
    assert metadata["stage_seconds"].keys() == {"data", "snapshot", "forecast"}
    replay = replay_forecast(result.snapshot_path, clock=lambda: NOW)
    assert replay.replay and replay.forecasts == result.forecasts


def test_closed_day_and_late_start_do_not_download(
    prepared: PreparedData, tmp_path: Path
) -> None:
    source = Source(prepared)
    result = compute_forecast(
        RunRequest(),
        snapshot_directory=tmp_path,
        source=source,
        clock=lambda: NOW - timedelta(days=1),
    )
    assert isinstance(result, SkippedForecast)
    assert result.to_metadata()["reason"] == "exchange_closed"
    with pytest.raises(ForecastError, match="deadline"):
        compute_forecast(
            RunRequest(),
            snapshot_directory=tmp_path,
            source=source,
            clock=lambda: NOW.replace(hour=14),
        )
    assert source.calls == [] and list(tmp_path.iterdir()) == []


def test_crossing_deadline_aborts_before_success(
    prepared: PreparedData, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portfolio_forecasting.market_data import prepare_data
    from portfolio_forecasting.sessions import plan_sessions
    from tests.market_fixtures import synthetic_history

    request = RunRequest()
    resolved = request.resolve(clock=lambda: NOW)
    plan = plan_sessions(resolved)
    assert plan is not None
    full = prepare_data(
        resolved,
        plan,
        tuple(synthetic_history(ticker, plan.sessions) for ticker in request.tickers),
    )
    ticks = iter([NOW, plan.target_open])
    monkeypatch.setattr(
        "portfolio_forecasting.pipeline.forecast_prices", lambda data, **kwargs: ()
    )
    with pytest.raises(ForecastError, match="deadline"):
        compute_forecast(
            request,
            snapshot_directory=tmp_path,
            source=Source(full),
            clock=lambda: next(ticks),
        )
    assert len(list(tmp_path.glob("*.json"))) == 1  # Inputs remain for diagnosis.


def test_failure_does_not_return_partial_report(
    prepared: PreparedData, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class FailingSource(Source):
        def fetch(self, ticker: str, resolved: object, *, run_id: str) -> AssetHistory:
            if ticker == "MSFT":
                raise ForecastError("download", "fixture failure", ticker=ticker)
            return super().fetch(ticker, resolved, run_id=run_id)

    with pytest.raises(ForecastError, match="MSFT"):
        compute_forecast(
            prepared.resolved.request,
            snapshot_directory=tmp_path,
            source=FailingSource(prepared),
            clock=lambda: NOW,
        )
    assert "run=" in caplog.text and "status=failed" in caplog.text
    assert list(tmp_path.iterdir()) == []
