"""Finite forecast computation with local provenance and no database dependency."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from portfolio_forecasting.config import ResolvedRunRequest, RunRequest
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.forecasting import AssetForecast, forecast_prices
from portfolio_forecasting.market_data import (
    MarketDataSource,
    PreparedData,
    YFinanceSource,
    aware_utc,
    prepare_data,
    utc_now,
)
from portfolio_forecasting.sessions import check_deadline, plan_sessions
from portfolio_forecasting.snapshots import (
    canonical_bytes,
    digest,
    read_snapshot,
    software_metadata,
    write_snapshot,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SkippedForecast:
    run_id: str
    resolved: ResolvedRunRequest
    reason: str = "exchange_closed"

    def to_metadata(self) -> dict[str, object]:
        return {
            "status": "skipped",
            "run_id": self.run_id,
            "reason": self.reason,
            "request": self.resolved.to_metadata(),
        }


@dataclass(frozen=True, slots=True)
class ForecastReport:
    run_id: str
    data: PreparedData
    forecasts: tuple[AssetForecast, ...]
    snapshot_path: Path
    completed_at: datetime
    stage_seconds: tuple[tuple[str, float], ...]
    replay: bool = False

    def to_metadata(self) -> dict[str, object]:
        return {
            "status": "complete",
            "kind": "forecast_only",
            "run_id": self.run_id,
            "request": self.data.resolved.to_metadata(),
            "replay": self.replay,
            "completed_at": self.completed_at,
            "sessions": self.data.plan,
            "snapshot_sha256": self.snapshot_path.stem,
            "software": software_metadata(),
            "request_sha256": digest(canonical_bytes(self.data.resolved.to_metadata())),
            "stage_seconds": dict(self.stage_seconds),
            "assets": [
                {
                    "ticker": item.ticker,
                    "observed_price": item.observed_price,
                    "predicted_price": item.predicted_price,
                    "predicted_return": item.predicted_return,
                    "observation_cutoff": item.observation_cutoff,
                    "forecast_target": item.forecast_target,
                    "recent_history": self.data.recent_history(item.ticker),
                    "model": json.loads(item.model_metadata_json),
                }
                for item in self.forecasts
            ],
        }


def compute_forecast(
    request: RunRequest,
    *,
    snapshot_directory: Path,
    source: MarketDataSource | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> ForecastReport | SkippedForecast:
    run_id = str(uuid4())
    started = time.perf_counter()
    resolved = request.resolve(clock=clock)
    try:
        plan = plan_sessions(resolved)
        if plan is None:
            LOGGER.info(
                "run=%s stage=calendar status=skipped reason=exchange_closed", run_id
            )
            return SkippedForecast(run_id, resolved)
        provider = source if source is not None else YFinanceSource(clock=clock)
        histories = tuple(
            provider.fetch(ticker, resolved, run_id=run_id)
            for ticker in request.tickers
        )
        data = prepare_data(resolved, plan, histories)
        downloaded = time.perf_counter()
        snapshot = write_snapshot(data, snapshot_directory)
        snapshotted = time.perf_counter()
        LOGGER.info(
            "run=%s stage=data status=complete assets=%d prices=%d "
            "cutoff=%s target=%s snapshot=%s",
            run_id,
            len(data.assets),
            len(plan.sessions),
            plan.observation_cutoff,
            plan.forecast_target,
            snapshot.stem,
        )
        forecasts = forecast_prices(data, run_id=run_id)
        completed = aware_utc(clock())
        if completed < resolved.executed_at or any(
            asset.retrieved_at > completed for asset in histories
        ):
            raise ForecastError("calendar", "run timestamps are not chronological")
        if request.mode == "live":
            check_deadline(plan, completed)
        finished = time.perf_counter()
        LOGGER.info(
            "run=%s stage=forecast status=complete seconds=%.6f",
            run_id,
            finished - snapshotted,
        )
        return ForecastReport(
            run_id,
            data,
            forecasts,
            snapshot,
            completed,
            (
                ("data", downloaded - started),
                ("snapshot", snapshotted - downloaded),
                ("forecast", finished - snapshotted),
            ),
        )
    except ForecastError as error:
        LOGGER.error(
            "run=%s stage=%s ticker=%s status=failed detail=%s",
            run_id,
            error.stage,
            error.ticker,
            error,
        )
        raise
    except OSError as error:
        LOGGER.error(
            "run=%s stage=snapshot status=failed error=%s", run_id, type(error).__name__
        )
        raise ForecastError("snapshot", "local artifact operation failed") from error


def replay_forecast(
    snapshot: Path, *, clock: Callable[[], datetime] = utc_now
) -> ForecastReport:
    started = time.perf_counter()
    data = read_snapshot(snapshot, require_same_software=True)
    run_id = str(uuid4())
    forecasts = forecast_prices(data, run_id=run_id)
    # Replays are explicitly labelled and cannot be treated as fresh live outputs.
    return ForecastReport(
        run_id,
        data,
        forecasts,
        snapshot,
        aware_utc(clock()),
        (("replay", time.perf_counter() - started),),
        replay=True,
    )
