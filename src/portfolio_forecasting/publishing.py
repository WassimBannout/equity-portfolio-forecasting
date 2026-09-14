"""Bind the first input before fitting; resume it and publish one coherent run."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from portfolio_forecasting.allocation import allocate_forecasts
from portfolio_forecasting.config import RunRequest
from portfolio_forecasting.forecasting import forecast_prices
from portfolio_forecasting.market_data import (
    MarketDataSource,
    YFinanceSource,
    aware_utc,
    prepare_data,
    utc_now,
)
from portfolio_forecasting.pipeline import ForecastReport, SkippedForecast
from portfolio_forecasting.portfolio import PortfolioReport
from portfolio_forecasting.sessions import check_deadline, plan_sessions
from portfolio_forecasting.snapshots import read_snapshot, write_snapshot
from portfolio_forecasting.store_contract import (
    Release,
    StoreConflict,
    StoreError,
    identity_for,
    publication_payload,
)
from portfolio_forecasting.supabase_store import SupabaseStore

LOGGER = logging.getLogger(__name__)


def publish_request(
    request: RunRequest,
    store: SupabaseStore,
    release: Release,
    *,
    snapshot_directory: Path,
    source: MarketDataSource | None = None,
    clock: Callable[[], datetime] = utc_now,
    input_snapshot: Path | None = None,
) -> dict[str, Any] | SkippedForecast:
    started = aware_utc(clock())
    attempt_id = str(uuid4())
    resolved = request.resolve(clock=lambda: started)
    plan = plan_sessions(resolved)
    if plan is None:
        return SkippedForecast(attempt_id, resolved)
    identity = identity_for(resolved, plan, release)
    store.preflight(writer=True)
    bound = store.lookup(identity=identity)
    if bound is None:
        if input_snapshot is None:
            provider = source if source is not None else YFinanceSource(clock=clock)
            assets = tuple(
                provider.fetch(ticker, resolved, run_id=attempt_id)
                for ticker in request.tickers
            )
            data = prepare_data(resolved, plan, assets)
            snapshot = write_snapshot(data, snapshot_directory)
        else:
            data = read_snapshot(input_snapshot)
            if identity_for(data.resolved, data.plan, release) != identity:
                raise StoreError(
                    "provided input snapshot does not match the explicit request"
                )
            snapshot = input_snapshot
        try:
            bound = store.stage(identity, snapshot, attempt_id, started)
        except StoreConflict:
            # A concurrent first capture won the binding. Discard this candidate
            # input and use the durable winner; never overwrite its observations.
            bound = store.lookup(identity=identity)
            if bound is None:
                raise
    return _finish(
        bound, store, release, snapshot_directory, attempt_id, started, clock
    )


def resume_publication(
    run_id: str,
    store: SupabaseStore,
    release: Release,
    *,
    snapshot_directory: Path,
    clock: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    store.preflight(writer=True)
    bound = store.lookup(run_id=run_id)
    if bound is None:
        raise StoreError("no bound request exists for this run")
    return _finish(
        bound,
        store,
        release,
        snapshot_directory,
        str(uuid4()),
        aware_utc(clock()),
        clock,
    )


def _finish(
    bound: dict[str, Any],
    store: SupabaseStore,
    release: Release,
    directory: Path,
    attempt_id: str,
    started: datetime,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    run_id = bound["run_id"]
    store.attempt(run_id, attempt_id, started)
    if bound["state"] == "published":
        run = store.get_run(run_id)
        LOGGER.info(
            "run=%s attempt=%s stage=publication status=already_published",
            run_id,
            attempt_id,
        )
        return run
    stage = "data"
    try:
        snapshot = store.bound_snapshot(bound["snapshot_sha256"], directory)
        data = read_snapshot(snapshot)
        if identity_for(data.resolved, data.plan, release) != bound["identity"]:
            raise StoreError(
                "resume requires the bound scientific configuration and release"
            )
        if data.resolved.request.mode == "live":
            check_deadline(data.plan, clock())
        stage = "forecast"
        mark = time.perf_counter()
        forecasts = forecast_prices(data, run_id=run_id)
        forecast_seconds = time.perf_counter() - mark
        forecast_completed = aware_utc(clock())
        stage = "allocation"
        mark = time.perf_counter()
        allocation = allocate_forecasts(data, forecasts, run_id=run_id)
        allocation_seconds = time.perf_counter() - mark
        completed = aware_utc(clock())
        if completed < started or completed < forecast_completed:
            raise StoreError("computation timestamps are not chronological")
        report = PortfolioReport(
            ForecastReport(
                run_id,
                data,
                forecasts,
                snapshot,
                forecast_completed,
                (("forecast", forecast_seconds),),
            ),
            allocation,
            completed,
            allocation_seconds,
        )
        stage = "publication"
        payload = publication_payload(report, release)
        if data.resolved.request.mode == "live":
            check_deadline(data.plan, clock())
        run = store.publish(
            run_id,
            payload,
            attempt_id,
            aware_utc(clock()),
            {
                "forecast_seconds": forecast_seconds,
                "allocation_seconds": allocation_seconds,
            },
        )
        LOGGER.info(
            "run=%s attempt=%s stage=publication status=published", run_id, attempt_id
        )
        return run
    except (ValueError, OSError):
        LOGGER.error(
            "run=%s attempt=%s stage=%s status=failed", run_id, attempt_id, stage
        )
        try:
            store.fail(run_id, attempt_id, stage)
        except StoreError:
            LOGGER.error(
                "run=%s attempt=%s stage=failure_record status=unavailable",
                run_id,
                attempt_id,
            )
        raise
