"""M3 forecast-to-allocation composition; no durable publication."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from portfolio_forecasting.allocation import AllocationResult, allocate_forecasts
from portfolio_forecasting.config import RunRequest
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.market_data import MarketDataSource, aware_utc, utc_now
from portfolio_forecasting.pipeline import (
    ForecastReport,
    SkippedForecast,
    compute_forecast,
)
from portfolio_forecasting.sessions import check_deadline


@dataclass(frozen=True, slots=True)
class PortfolioReport:
    forecast: ForecastReport
    allocation: AllocationResult
    completed_at: datetime
    allocation_seconds: float

    def to_metadata(self) -> dict[str, object]:
        result = self.forecast.to_metadata()
        result["kind"] = "forecast_and_allocation"
        result["allocation"] = self.allocation
        result["completed_at"] = self.completed_at
        result["scipy_version"] = version("scipy")
        result["stage_seconds"] = {
            **dict(self.forecast.stage_seconds),
            "allocation": self.allocation_seconds,
        }
        return result


def compute_portfolio(
    request: RunRequest,
    *,
    snapshot_directory: Path,
    source: MarketDataSource | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> PortfolioReport | SkippedForecast:
    forecast = compute_forecast(
        request, snapshot_directory=snapshot_directory, source=source, clock=clock
    )
    if isinstance(forecast, SkippedForecast):
        return forecast
    started = time.perf_counter()
    try:
        result = allocate_forecasts(
            forecast.data, forecast.forecasts, run_id=forecast.run_id
        )
        completed = aware_utc(clock())
        if completed < forecast.completed_at:
            raise ForecastError("calendar", "allocation completion precedes forecast")
        if request.mode == "live":
            check_deadline(forecast.data.plan, completed)
    except ForecastError as error:
        logging.getLogger(__name__).error(
            "run=%s stage=%s status=failed detail=%s",
            forecast.run_id,
            error.stage,
            error,
        )
        raise
    return PortfolioReport(forecast, result, completed, time.perf_counter() - started)
