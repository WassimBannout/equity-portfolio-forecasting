"""Close-lagged research accounting; no brokerage or executable-price claim."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from portfolio_forecasting.allocation import CONSTRAINT_TOL, numeric_array
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.sessions import exchange_calendar


@dataclass(frozen=True, slots=True)
class Signal:
    cutoff: date
    target: date
    weights: tuple[float, ...]


def paper_path(
    sessions: tuple[date, ...],
    prices: object,
    signals: tuple[Signal, ...],
    *,
    transaction_cost_bps: float = 10.0,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    values = numeric_array(prices, ndim=2, name="paper prices")
    if (
        len(sessions) < 2
        or values.shape[0] != len(sessions)
        or values.shape[1] < 1
        or np.any(values <= 0)
    ):
        raise ForecastError("evaluation", "paper path needs positive aligned prices")
    calendar = exchange_calendar(sessions[0], sessions[-1])
    if (
        tuple(
            day.date() for day in calendar.sessions_in_range(sessions[0], sessions[-1])
        )
        != sessions
    ):
        raise ForecastError(
            "evaluation", "paper prices must contain consecutive exchange sessions"
        )
    if any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or v < 0
        for v in (transaction_cost_bps, slippage_bps)
    ):
        raise ForecastError(
            "evaluation", "cost and slippage must be finite nonnegative bps"
        )
    cost_rate = (transaction_cost_bps + slippage_bps) / 10000
    if cost_rate >= 0.5:
        raise ForecastError(
            "evaluation", "cost rate is outside supported research range"
        )
    if (
        not signals
        or len({signal.target for signal in signals}) != len(signals)
        or tuple(signal.target for signal in signals)
        != tuple(sorted(signal.target for signal in signals))
    ):
        raise ForecastError("evaluation", "signals must have unique ordered targets")
    by_target = {}
    for signal in signals:
        if signal.target not in sessions[:-1] or signal.cutoff >= signal.target:
            raise ForecastError(
                "evaluation", "signal target must precede a holding interval"
            )
        full_calendar = exchange_calendar(signal.cutoff, signal.target)
        if (
            not full_calendar.is_session(signal.cutoff)
            or full_calendar.next_session(signal.cutoff).date() != signal.target
        ):
            raise ForecastError(
                "evaluation", "signal cutoff must be the previous exchange session"
            )
        w = numeric_array(signal.weights, ndim=1, name="signal weights")
        if (
            w.shape != (values.shape[1],)
            or abs(float(w.sum()) - 1) > CONSTRAINT_TOL
            or np.any(w < -CONSTRAINT_TOL)
        ):
            raise ForecastError("evaluation", "invalid full-investment signal weights")
        by_target[signal.target] = w
    if signals[0].target != sessions[0]:
        raise ForecastError(
            "evaluation", "paper path must begin at the first signal's execution close"
        )
    weights = np.full(values.shape[1], 1.0 / values.shape[1])
    gross_wealth = net_wealth = 1.0
    peak = 1.0
    max_drawdown = 0.0
    history: list[dict[str, Any]] = []
    for i, day in enumerate(sessions[:-1]):
        # Pre-trade weights were drifted by the previous holding interval.
        pretrade = weights.copy()
        target = by_target.get(day)
        turnover = 0.0 if target is None else float(np.abs(target - pretrade).sum())
        if target is not None:
            weights = target.copy()
        gross = float(weights @ (values[i + 1] / values[i] - 1))
        cost_fraction = cost_rate * turnover
        net = (1 - cost_fraction) * (1 + gross) - 1
        if (
            not all(math.isfinite(value) for value in (gross, net))
            or gross <= -1
            or net <= -1
        ):
            raise ForecastError(
                "evaluation", "invalid holding return or cost arithmetic"
            )
        gross_wealth *= 1 + gross
        net_wealth *= 1 + net
        peak = max(peak, net_wealth)
        max_drawdown = min(max_drawdown, net_wealth / peak - 1)
        history.append(
            {
                "execution_close": day,
                "holding_end": sessions[i + 1],
                "pretrade_weights": tuple(float(v) for v in pretrade),
                "held_weights": tuple(float(v) for v in weights),
                "turnover_l1": turnover,
                "one_way_turnover": turnover / 2,
                "cost_fraction": cost_fraction,
                "gross_return": gross,
                "net_return": net,
                "gross_wealth": gross_wealth,
                "net_wealth": net_wealth,
                "concentration_hhi": float(weights @ weights),
            }
        )
        weights = weights * (values[i + 1] / values[i]) / (1 + gross)
    returns = np.asarray([row["net_return"] for row in history], dtype=float)
    volatility = (
        float(np.std(returns, ddof=1) * math.sqrt(252)) if len(returns) > 1 else None
    )
    sharpe = (
        float(np.mean(returns) * 252 / volatility)
        if volatility is not None and volatility > 0
        else None
    )
    return {
        "kind": "adjusted-close research accounting",
        "gross_cumulative_return": gross_wealth - 1,
        "net_cumulative_return": net_wealth - 1,
        "annualized_net_volatility": volatility,
        "maximum_net_drawdown": max_drawdown,
        "zero_rate_sharpe": sharpe,
        "annualization_sessions": 252,
        "holding_intervals": len(history),
        "turnover_l1": sum(float(row["turnover_l1"]) for row in history),
        "mean_concentration_hhi": sum(
            float(row["concentration_hhi"]) for row in history
        )
        / len(history),
        "cost_bps": transaction_cost_bps,
        "slippage_bps": slippage_bps,
        "initial_holdings": "equal weight; first rebalance charged",
        "terminal_liquidation": False,
        "cost_convention": (
            "L1 dollars traded per pre-cost wealth; costs deducted "
            "proportionally before holding return"
        ),
        "path": history,
    }
