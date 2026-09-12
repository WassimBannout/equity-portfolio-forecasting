"""Independent, fresh Prophet price fits on validated completed sessions only."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import date
from numbers import Real
from typing import Any

import pandas as pd
from prophet import Prophet

from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.market_data import PreparedData, prepare_data
from portfolio_forecasting.snapshots import canonical_bytes

# An explicit fixed fitting policy; model selection is Milestone 3.
FIT_OPTIONS: dict[str, Any] = {
    "algorithm": "LBFGS",
    "iter": 10000,
    "seed": 42,
    "tol_obj": 1e-12,
    "tol_rel_obj": 1e4,
    "tol_grad": 1e-8,
    "tol_rel_grad": 1e7,
    "tol_param": 1e-8,
}


def model_options(data: PreparedData) -> dict[str, Any]:
    settings = data.resolved.request.forecast
    return {
        "growth": "linear",
        "changepoints": None,
        "n_changepoints": 25,
        "changepoint_range": 0.8,
        "yearly_seasonality": settings.yearly_seasonality,
        "weekly_seasonality": settings.weekly_seasonality,
        "daily_seasonality": settings.daily_seasonality,
        "seasonality_mode": "additive",
        "holidays_mode": "additive",
        "seasonality_prior_scale": 10.0,
        "holidays_prior_scale": 10.0,
        "changepoint_prior_scale": 0.05,
        "mcmc_samples": 0,
        "interval_width": 0.8,
        "uncertainty_samples": 0,
        "stan_backend": "CMDSTANPY",
        "scaling": "absmax",
    }


@dataclass(frozen=True, slots=True)
class AssetForecast:
    ticker: str
    observation_cutoff: date
    forecast_target: date
    observed_price: float
    predicted_price: float
    predicted_return: float
    model_metadata_json: str


def forecast_prices(
    data: PreparedData, *, run_id: str = "manual"
) -> tuple[AssetForecast, ...]:
    # Check the complete panel, including callers using the lower-level function.

    checked = prepare_data(data.resolved, data.plan, data.assets)
    if checked.returns != data.returns:
        raise ForecastError("forecast", "return panel does not match observed prices")
    options = model_options(data)
    holidays = pd.DataFrame(
        [
            {
                "ds": pd.Timestamp(event.day),
                "holiday": event.name,
                "lower_window": event.lower_window,
                "upper_window": event.upper_window,
            }
            for event in data.plan.holidays
        ],
        columns=["ds", "holiday", "lower_window", "upper_window"],
    )
    output = []
    for asset in data.assets:
        started = time.perf_counter()
        try:
            model = Prophet(
                **options,
                holidays=holidays.copy(deep=True) if not holidays.empty else None,
            )
            if model.stan_backend is None:
                raise ForecastError(
                    "forecast", "Prophet backend unavailable", ticker=asset.ticker
                )
            model.stan_backend.set_options(newton_fallback=False)
            history = pd.DataFrame(
                {
                    "ds": pd.to_datetime([row.session for row in asset.observations]),
                    "y": [row.price for row in asset.observations],
                }
            )
            # Future prices are never constructed or passed to fit.
            model.fit(history.copy(deep=True), **FIT_OPTIONS)
            future = pd.DataFrame({"ds": [pd.Timestamp(data.plan.forecast_target)]})
            prediction = model.predict(future)
            if (
                len(prediction) != 1
                or "ds" not in prediction
                or "yhat" not in prediction
                or prediction["ds"].iloc[0] != future["ds"].iloc[0]
            ):
                raise ForecastError(
                    "forecast",
                    "model returned an unexpected target or output shape",
                    ticker=asset.ticker,
                )
            raw_price = prediction["yhat"].iloc[0]
            if isinstance(raw_price, bool) or not isinstance(raw_price, Real):
                raise ForecastError(
                    "forecast", "prediction must be numeric", ticker=asset.ticker
                )
            price = float(raw_price)
            observed = asset.observations[-1].price
            change = price / observed - 1.0
            if not math.isfinite(price) or price <= 0 or not math.isfinite(change):
                raise ForecastError(
                    "forecast",
                    "prediction must be finite and positive with a finite return",
                    ticker=asset.ticker,
                )
            if model.changepoints is None:
                raise ForecastError(
                    "forecast", "missing fitted model metadata", ticker=asset.ticker
                )
            metadata = {
                "model": "Prophet",
                "constructor": options,
                "fit": FIT_OPTIONS,
                "newton_fallback": False,
                "effective_changepoints": [
                    value.isoformat() for value in model.changepoints
                ],
                "effective_seasonalities": model.seasonalities,
                "training_rows": len(history),
                "training_start": asset.observations[0].session,
                "training_end": asset.observations[-1].session,
                "holiday_events": data.plan.holidays,
            }
            output.append(
                AssetForecast(
                    asset.ticker,
                    data.plan.observation_cutoff,
                    data.plan.forecast_target,
                    observed,
                    price,
                    change,
                    canonical_bytes(metadata).decode(),
                )
            )
            logging.getLogger(__name__).info(
                "run=%s stage=fit ticker=%s prices=%d seconds=%.6f status=complete",
                run_id,
                asset.ticker,
                len(history),
                time.perf_counter() - started,
            )
        except ForecastError:
            raise
        except Exception as error:
            raise ForecastError(
                "forecast",
                f"Prophet fit/predict failed: {type(error).__name__}",
                ticker=asset.ticker,
            ) from error
    return tuple(output)
