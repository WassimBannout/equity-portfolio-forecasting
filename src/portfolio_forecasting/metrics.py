"""Forecast diagnostics on explicit, identical cutoff/target observation pairs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from portfolio_forecasting.errors import ForecastError


@dataclass(frozen=True, slots=True)
class ForecastPair:
    ticker: str
    cutoff: date
    target: date
    observed: float
    predicted: float
    actual: float

    def __post_init__(self) -> None:
        if self.cutoff >= self.target or not self.ticker:
            raise ForecastError("evaluation", "invalid forecast pair identity/dates")
        if any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or v <= 0
            for v in (self.observed, self.predicted, self.actual)
        ):
            raise ForecastError(
                "evaluation", "forecast pair prices must be finite and positive"
            )


def forecast_metrics(
    pairs: tuple[ForecastPair, ...], *, zero_tolerance: float = 1e-12
) -> dict[str, Any]:
    if not pairs or not math.isfinite(zero_tolerance) or zero_tolerance < 0:
        raise ForecastError(
            "evaluation", "nonempty pairs and a finite zero tolerance required"
        )
    identities = [(pair.ticker, pair.target) for pair in pairs]
    if len(set(identities)) != len(identities):
        raise ForecastError("evaluation", "duplicate forecast outcome pair")
    per_asset = {}
    for ticker in sorted({pair.ticker for pair in pairs}):
        group = [pair for pair in pairs if pair.ticker == ticker]
        count = len(group)
        errors = [pair.actual - pair.predicted for pair in group]
        baseline = [abs(pair.actual - pair.observed) for pair in group]
        predicted_returns = [pair.predicted / pair.observed - 1 for pair in group]
        actual_returns = [pair.actual / pair.observed - 1 for pair in group]
        mae = sum(abs(value) for value in errors) / count
        base_mae = sum(baseline) / count

        def direction(value: float) -> int:
            return 0 if abs(value) <= zero_tolerance else (1 if value > 0 else -1)

        ratio = mae / base_mae if base_mae > 0 else (1.0 if mae == 0 else None)
        per_asset[ticker] = {
            "count": count,
            "price_mae": mae,
            "price_rmse": math.sqrt(sum(value * value for value in errors) / count),
            "return_mae": sum(
                abs(p - a)
                for p, a in zip(predicted_returns, actual_returns, strict=True)
            )
            / count,
            "directional_accuracy": sum(
                direction(p) == direction(a)
                for p, a in zip(predicted_returns, actual_returns, strict=True)
            )
            / count,
            "actual_zero_count": sum(direction(a) == 0 for a in actual_returns),
            "prediction_zero_count": sum(direction(p) == 0 for p in predicted_returns),
            "last_price_mae": base_mae,
            "relative_price_mae": ratio,
        }
    ratios = [row["relative_price_mae"] for row in per_asset.values()]
    return {
        "pairs": len(pairs),
        "origins": len({pair.target for pair in pairs}),
        "per_asset": per_asset,
        "macro_relative_price_mae": sum(value for value in ratios if value is not None)
        / len(ratios)
        if all(value is not None for value in ratios)
        else None,
        "zero_direction_tolerance": zero_tolerance,
        "tie_policy": (
            "three signs; zero is correct only when both actual and predicted are zero"
        ),
        "zero_baseline_policy": (
            "both perfect -> ratio 1; nonzero error against perfect baseline "
            "-> undefined"
        ),
    }
