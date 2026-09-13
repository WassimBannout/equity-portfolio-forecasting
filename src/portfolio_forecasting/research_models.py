"""Bounded Prophet research variants over the unchanged M2 data/forecast contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

import pandas as pd
from prophet import Prophet

from portfolio_forecasting.config import ForecastSettings
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.forecasting import (
    FIT_OPTIONS,
    AssetForecast,
    forecast_prices,
    model_options,
)
from portfolio_forecasting.market_data import PreparedData, prepare_data
from portfolio_forecasting.sessions import plan_sessions
from portfolio_forecasting.snapshots import canonical_bytes


@dataclass(frozen=True, slots=True)
class ModelVariant:
    name: str
    yearly: bool = True
    weekly: bool = True
    holidays: bool = True
    window_prices: int | None = None
    changepoint_prior_scale: float = 0.05

    def __post_init__(self) -> None:
        if not self.name or any(
            type(value) is not bool
            for value in (self.yearly, self.weekly, self.holidays)
        ):
            raise ForecastError("evaluation", "invalid model variant")
        if self.window_prices is not None and (
            type(self.window_prices) is not int or self.window_prices < 3
        ):
            raise ForecastError("evaluation", "rolling price window must be at least 3")
        if (
            isinstance(self.changepoint_prior_scale, bool)
            or not math.isfinite(self.changepoint_prior_scale)
            or self.changepoint_prior_scale <= 0
        ):
            raise ForecastError(
                "evaluation", "changepoint prior must be finite and positive"
            )


def variant_data(data: PreparedData, variant: ModelVariant) -> PreparedData:
    start = data.plan.sessions[0]
    if variant.window_prices is not None:
        if variant.window_prices > len(data.plan.sessions):
            raise ForecastError(
                "evaluation", "rolling window exceeds available training prices"
            )
        start = data.plan.sessions[-variant.window_prices]
    request = replace(
        data.resolved.request,
        history_start=start,
        forecast=ForecastSettings(
            yearly_seasonality=variant.yearly,
            weekly_seasonality=variant.weekly,
            holiday_effects=variant.holidays,
        ),
    )
    resolved = request.resolve(clock=lambda: data.resolved.executed_at)
    plan = plan_sessions(resolved)
    if plan is None:
        raise ForecastError("evaluation", "research origin has no target session")
    assets = tuple(
        replace(
            asset,
            observations=tuple(
                row for row in asset.observations if row.session >= start
            ),
        )
        for asset in data.assets
    )
    return prepare_data(resolved, plan, assets)


def predict_variant(
    data: PreparedData, variant: ModelVariant
) -> tuple[AssetForecast, ...]:
    training = variant_data(data, variant)
    if variant.changepoint_prior_scale == 0.05:
        return forecast_prices(training, run_id=f"research:{variant.name}")
    # Only the prior experiment needs another constructor setting. M2's public
    # default behavior and implementation are not modified or monkeypatched.
    options = model_options(training)
    options["changepoint_prior_scale"] = variant.changepoint_prior_scale
    events = pd.DataFrame(
        [
            {
                "ds": pd.Timestamp(event.day),
                "holiday": event.name,
                "lower_window": event.lower_window,
                "upper_window": event.upper_window,
            }
            for event in training.plan.holidays
        ]
    )
    forecasts = []
    for asset in training.assets:
        try:
            model = Prophet(
                **options, holidays=events.copy(deep=True) if not events.empty else None
            )
            if model.stan_backend is None:
                raise RuntimeError("missing Prophet backend")
            model.stan_backend.set_options(newton_fallback=False)
            history = pd.DataFrame(
                {
                    "ds": pd.to_datetime([row.session for row in asset.observations]),
                    "y": [row.price for row in asset.observations],
                }
            )
            model.fit(history, **FIT_OPTIONS)
            target = pd.DataFrame({"ds": [pd.Timestamp(training.plan.forecast_target)]})
            predicted = float(model.predict(target)["yhat"].iloc[0])
            observed = asset.observations[-1].price
            change = predicted / observed - 1
            if (
                not math.isfinite(predicted)
                or predicted <= 0
                or not math.isfinite(change)
            ):
                raise ValueError("invalid Prophet point forecast")
            metadata: dict[str, Any] = {
                "variant": variant,
                "constructor": options,
                "fit": FIT_OPTIONS,
                "newton_fallback": False,
                "training_start": asset.observations[0].session,
                "training_end": asset.observations[-1].session,
                "training_rows": len(history),
                "holiday_events": training.plan.holidays,
                "effective_seasonalities": model.seasonalities,
                "effective_changepoints": [
                    day.isoformat() for day in model.changepoints
                ]
                if model.changepoints is not None
                else [],
            }
            forecasts.append(
                AssetForecast(
                    asset.ticker,
                    training.plan.observation_cutoff,
                    training.plan.forecast_target,
                    observed,
                    predicted,
                    change,
                    canonical_bytes(metadata).decode(),
                )
            )
        except Exception as error:
            raise ForecastError(
                "forecast",
                f"research Prophet fit failed: {type(error).__name__}",
                ticker=asset.ticker,
            ) from error
    return tuple(forecasts)
