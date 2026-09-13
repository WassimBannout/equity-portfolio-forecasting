import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from portfolio_forecasting import RunRequest
from portfolio_forecasting.allocation import (
    allocation_sensitivity,
    solve_allocation,
)
from portfolio_forecasting.config import AllocationSettings
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.market_data import PreparedData
from portfolio_forecasting.pipeline import ForecastReport, SkippedForecast
from portfolio_forecasting.portfolio import PortfolioReport, compute_portfolio
from portfolio_forecasting.snapshots import canonical_bytes
from tests.test_allocation import forecasts


def test_forecast_allocation_composition_and_metadata(
    prepared: PreparedData, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = prepared.resolved.executed_at
    report = ForecastReport(
        "fixture-run",
        prepared,
        forecasts(prepared, (0.01, 0.02)),
        tmp_path / "input.json",
        now,
        (("forecast", 0.1),),
    )
    monkeypatch.setattr(
        "portfolio_forecasting.portfolio.compute_forecast",
        lambda *args, **kwargs: report,
    )
    result = compute_portfolio(
        prepared.resolved.request, snapshot_directory=tmp_path, clock=lambda: now
    )
    assert isinstance(result, PortfolioReport)
    assert result.forecast is report
    assert result.allocation.tickers == prepared.resolved.request.tickers
    assert sum(result.allocation.weights) == pytest.approx(1, abs=1e-9)
    metadata = json.loads(canonical_bytes(result.to_metadata()))
    assert metadata["run_id"] == "fixture-run"
    assert metadata["kind"] == "forecast_and_allocation"
    assert metadata["stage_seconds"]["allocation"] >= 0
    assert metadata["scipy_version"] == "1.18.1"


def test_closed_session_skips_before_allocation(tmp_path: Path) -> None:
    result = compute_portfolio(
        RunRequest(),
        snapshot_directory=tmp_path,
        clock=lambda: datetime(2026, 9, 13, 9, tzinfo=UTC),
    )
    assert isinstance(result, SkippedForecast)
    assert not list(tmp_path.iterdir())


def test_allocation_failure_propagates(
    prepared: PreparedData,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = prepared.resolved.executed_at
    report = ForecastReport("fixture-run", prepared, (), tmp_path / "in.json", now, ())
    monkeypatch.setattr(
        "portfolio_forecasting.portfolio.compute_forecast",
        lambda *args, **kwargs: report,
    )
    with pytest.raises(ForecastError, match="complete ticker"):
        compute_portfolio(
            prepared.resolved.request, snapshot_directory=tmp_path, clock=lambda: now
        )
    assert "run=fixture-run" in caplog.text and "status=failed" in caplog.text


def test_late_allocation_rechecks_live_deadline(
    prepared: PreparedData,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = ForecastReport(
        "fixture-run",
        prepared,
        forecasts(prepared, (0.01, 0.02)),
        tmp_path / "in.json",
        prepared.resolved.executed_at,
        (),
    )
    monkeypatch.setattr(
        "portfolio_forecasting.portfolio.compute_forecast",
        lambda *args, **kwargs: report,
    )
    with pytest.raises(ForecastError, match="open"):
        compute_portfolio(
            RunRequest(),
            snapshot_directory=tmp_path,
            clock=lambda: prepared.plan.target_open,
        )


def test_hand_computed_one_bp_weight_sensitivity() -> None:
    settings = AllocationSettings(risk_aversion=2, lower_bound=0)
    result = solve_allocation(
        ("A", "B"), (0.2, 0.0), ((1.0, 0.0), (0.0, 1.0)), settings
    )
    sensitivity = allocation_sensitivity(result, settings)
    assert sensitivity["maximum_weight_l1_change"] == pytest.approx(0.00005, abs=1e-9)
