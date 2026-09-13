from datetime import date

import numpy as np
import pytest

from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.metrics import ForecastPair, forecast_metrics
from portfolio_forecasting.paper import Signal, paper_path


def test_known_errors_denominators_and_direction_ties() -> None:
    pairs = (
        ForecastPair("A", date(2026, 9, 1), date(2026, 9, 2), 100, 110, 105),
        ForecastPair("A", date(2026, 9, 2), date(2026, 9, 3), 100, 100, 100),
    )
    result = forecast_metrics(pairs)
    a = result["per_asset"]["A"]
    assert a["price_mae"] == 2.5
    assert a["price_rmse"] == pytest.approx(12.5**0.5)
    assert a["return_mae"] == pytest.approx(0.025)
    assert a["directional_accuracy"] == 1.0
    assert a["relative_price_mae"] == 1.0
    assert a["actual_zero_count"] == a["prediction_zero_count"] == 1
    wrong = forecast_metrics(
        (ForecastPair("A", date(2026, 9, 1), date(2026, 9, 2), 100, 110, 100),)
    )
    assert wrong["macro_relative_price_mae"] is None
    assert wrong["per_asset"]["A"]["directional_accuracy"] == 0


def test_empty_duplicate_invalid_pairs() -> None:
    with pytest.raises(ForecastError):
        forecast_metrics(())
    pair = ForecastPair("A", date(2026, 9, 1), date(2026, 9, 2), 100, 100, 100)
    with pytest.raises(ForecastError):
        forecast_metrics((pair, pair))
    with pytest.raises(ForecastError):
        ForecastPair("A", date(2026, 9, 2), date(2026, 9, 1), 100, 100, 100)
    with pytest.raises(ForecastError):
        ForecastPair("A", date(2026, 9, 1), date(2026, 9, 2), 0, 100, 100)


DAYS = (date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3))


def test_drifted_turnover_costs_and_lag_hand_calculated() -> None:
    prices = ((100, 100), (110, 100), (121, 100))
    signals = (
        Signal(date(2026, 8, 31), DAYS[0], (0.5, 0.5)),
        Signal(DAYS[0], DAYS[1], (0.5, 0.5)),
    )
    result = paper_path(DAYS, prices, signals, transaction_cost_bps=10, slippage_bps=0)
    first, second = result["path"]
    assert first["execution_close"] == DAYS[0] and first["holding_end"] == DAYS[1]
    assert first["gross_return"] == pytest.approx(0.05)
    assert first["turnover_l1"] == 0
    assert second["pretrade_weights"] == pytest.approx((11 / 21, 10 / 21))
    assert second["turnover_l1"] == pytest.approx(1 / 21)
    assert second["cost_fraction"] == pytest.approx(0.001 / 21)
    assert second["net_return"] == pytest.approx((1 - 0.001 / 21) * 1.05 - 1)
    assert result["gross_cumulative_return"] == pytest.approx(1.05**2 - 1)
    assert result["net_cumulative_return"] == pytest.approx(
        1.05**2 * (1 - 0.001 / 21) - 1
    )


def test_initial_rebalance_and_terminal_convention() -> None:
    result = paper_path(
        DAYS,
        ((100, 100), (100, 100), (100, 100)),
        (Signal(date(2026, 8, 31), DAYS[0], (1.0, 0.0)),),
        transaction_cost_bps=10,
        slippage_bps=5,
    )
    assert result["turnover_l1"] == 1
    assert result["net_cumulative_return"] == pytest.approx(-0.0015)
    assert result["maximum_net_drawdown"] == pytest.approx(-0.0015)
    assert result["terminal_liquidation"] is False


def test_holding_drift_without_rebalancing() -> None:
    result = paper_path(
        DAYS,
        ((100, 100), (110, 100), (121, 100)),
        (Signal(date(2026, 8, 31), DAYS[0], (0.5, 0.5)),),
        transaction_cost_bps=0,
        slippage_bps=0,
    )
    assert result["gross_cumulative_return"] == pytest.approx(0.105)
    assert result["path"][1]["held_weights"] == pytest.approx((11 / 21, 10 / 21))


def test_no_previous_close_profit_and_invalid_signal_dates() -> None:
    # The 100 -> 200 move BEFORE target is never included in this path.
    result = paper_path(
        DAYS,
        ((200, 100), (200, 100), (200, 100)),
        (Signal(date(2026, 8, 31), DAYS[0], (1.0, 0.0)),),
        transaction_cost_bps=0,
        slippage_bps=0,
    )
    assert result["gross_cumulative_return"] == 0
    for signals in (
        (Signal(DAYS[0], DAYS[0], (0.5, 0.5)),),
        (Signal(DAYS[1], DAYS[2], (0.5, 0.5)),),
        (Signal(date(2026, 8, 28), DAYS[0], (0.5, 0.5)),),
    ):
        with pytest.raises(ForecastError):
            paper_path(DAYS, np.ones((3, 2)), signals)
    with pytest.raises(ForecastError):
        paper_path(
            (DAYS[0], DAYS[2]),
            np.ones((2, 2)),
            (Signal(date(2026, 8, 31), DAYS[0], (0.5, 0.5)),),
        )
