import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from portfolio_forecasting import AllocationSettings, RunRequest
from portfolio_forecasting.allocation import (
    allocate_forecasts,
    estimate_risk,
    solve_allocation,
)
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.forecasting import AssetForecast
from portfolio_forecasting.market_data import PreparedData


def forecasts(
    data: PreparedData, returns: tuple[float, ...] = (0.02, -0.01)
) -> tuple[AssetForecast, ...]:
    return tuple(
        AssetForecast(
            asset.ticker,
            data.plan.observation_cutoff,
            data.plan.forecast_target,
            asset.observations[-1].price,
            asset.observations[-1].price * (1 + change),
            change,
            "{}",
        )
        for asset, change in zip(data.assets, returns, strict=True)
    )


def test_hand_calculated_covariance_and_mean(prepared: PreparedData) -> None:
    risk = estimate_risk(prepared)
    a, b = prepared.returns[-2:]
    expected = [[(a[i] - b[i]) * (a[j] - b[j]) / 2 for j in range(2)] for i in range(2)]
    np.testing.assert_allclose(risk.sample_covariance, expected, rtol=1e-12, atol=1e-20)
    np.testing.assert_allclose(
        risk.historical_mean, [(a[i] + b[i]) / 2 for i in range(2)]
    )
    assert risk.observation_count == 2
    shrunk = estimate_risk(prepared, shrinkage=0.25)
    assert shrunk.covariance[0][1] == pytest.approx(risk.covariance[0][1] * 0.75)
    assert shrunk.covariance[0][0] == risk.covariance[0][0]


def test_forecasts_change_mu_but_not_risk(prepared: PreparedData) -> None:
    first = allocate_forecasts(prepared, forecasts(prepared))
    second = allocate_forecasts(prepared, forecasts(prepared, (-0.02, 0.04)))
    assert first.expected_returns == (0.02, -0.01)
    assert first.covariance == second.covariance
    assert first.weights != second.weights
    historical = allocate_forecasts(prepared, forecasts(prepared), alpha=0)
    assert historical.expected_returns == estimate_risk(prepared).historical_mean
    blended = allocate_forecasts(prepared, forecasts(prepared), alpha=0.25)
    assert blended.expected_returns == pytest.approx(
        np.asarray(historical.expected_returns) * 0.75 + np.array([0.02, -0.01]) * 0.25
    )


def test_known_two_asset_optimum_and_half_factor() -> None:
    # With covariance I, lambda=2, and mu=(.2, 0), w1=.55 exactly.
    result = solve_allocation(
        ("A", "B"),
        (0.2, 0),
        ((1, 0), (0, 1)),
        AllocationSettings(risk_aversion=2, lower_bound=0),
    )
    assert result.weights == pytest.approx((0.55, 0.45), abs=1e-8)
    diagnostics = json.loads(result.diagnostics_json)
    assert diagnostics["variance"] == pytest.approx(0.505)
    assert diagnostics["utility"] == pytest.approx(-0.395)
    assert diagnostics["concavity_gap"] <= diagnostics["gap_tolerance"]
    assert diagnostics["covariance_rank"] == 2


@pytest.mark.parametrize("n", [1, 12, 20])
def test_single_default_and_forced_allocations(n: int) -> None:
    tickers = tuple(f"T{i}" for i in range(n))
    result = solve_allocation(
        tickers, tuple(-0.01 * i for i in range(n)), np.eye(n) * 1e-4
    )
    assert sum(result.weights) == pytest.approx(1, abs=1e-9)
    assert min(result.weights) >= 0.05 - 1e-9
    if n == 1:
        assert result.weights == (1.0,)
    if n == 12:
        assert max(result.weights) <= 0.45 + 1e-9
    if n == 20:
        assert result.weights == pytest.approx((0.05,) * 20)


def test_infeasibility_before_solver(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("solver called")

    monkeypatch.setattr("portfolio_forecasting.allocation.minimize", unexpected)
    with pytest.raises(ValueError, match="infeasible"):
        solve_allocation(tuple(str(i) for i in range(21)), np.zeros(21), np.eye(21))
    with pytest.raises(ValueError, match="infeasible"):
        solve_allocation(
            ("A", "B"), (0, 0), np.eye(2), AllocationSettings(upper_bound=0.4)
        )


def test_permutation_invariance_and_scaling() -> None:
    mu = np.array([0.001, 0.002, -0.001])
    covariance = np.array([[0.02, 0.001, 0], [0.001, 0.03, 0.002], [0, 0.002, 0.01]])
    settings = AllocationSettings(lower_bound=0)
    first = solve_allocation(("A", "B", "C"), mu, covariance, settings)
    permutation = [2, 0, 1]
    second = solve_allocation(
        ("C", "A", "B"),
        mu[permutation],
        covariance[np.ix_(permutation, permutation)],
        settings,
    )
    assert np.array(second.weights)[[1, 2, 0]] == pytest.approx(first.weights, abs=1e-7)
    scaled = solve_allocation(("A", "B", "C"), mu * 1e-8, covariance * 1e-8, settings)
    assert scaled.weights == pytest.approx(first.weights, abs=1e-7)


@pytest.mark.parametrize("covariance", [np.zeros((2, 2)), np.ones((2, 2)) * 0.01])
def test_singular_psd_is_valid_not_exact_weights(covariance: Any) -> None:
    result = solve_allocation(("A", "B"), (0.01, 0.01), covariance)
    diagnostics = json.loads(result.diagnostics_json)
    assert diagnostics["covariance_condition"] is None
    assert diagnostics["concavity_gap"] <= diagnostics["gap_tolerance"]
    assert sum(result.weights) == pytest.approx(1)


@pytest.mark.parametrize(
    "mu,covariance",
    [
        ((float("nan"), 0), np.eye(2)),
        ((float("inf"), 0), np.eye(2)),
        ((True, False), np.eye(2)),
        (("1", "2"), np.eye(2)),
        ((0, 0), [[1, 0.1], [0.2, 1]]),
        ((0, 0), [[1, 2], [2, 1]]),
        ((0, 0), [[1, 0], [0, float("nan")]]),
        ((0,), np.eye(2)),
        ((0, 0), [[1, 0]]),
    ],
)
def test_invalid_numerical_inputs(mu: object, covariance: object) -> None:
    with pytest.raises(ForecastError):
        solve_allocation(("A", "B"), mu, covariance)


@pytest.mark.parametrize(
    "kind", ["failed", "nan", "budget", "bound", "poor", "count", "raised"]
)
def test_untrusted_solver_result_independently_checked(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    weights = {
        "nan": [float("nan"), 0.5],
        "budget": [0.3, 0.3],
        "bound": [-0.1, 1.1],
        "poor": [0.5, 0.5],
        "count": [1.0],
    }.get(kind, [0.5, 0.5])

    def solver(*args: object, **kwargs: object) -> SimpleNamespace:
        if kind == "raised":
            raise RuntimeError("fixture")
        return SimpleNamespace(
            success=kind != "failed",
            x=np.asarray(weights),
            status=8 if kind == "failed" else 0,
            message="fixture",
            nit=1,
        )

    monkeypatch.setattr("portfolio_forecasting.allocation.minimize", solver)
    with pytest.raises(ForecastError):
        solve_allocation(("A", "B"), (0.02, 0), np.eye(2) * 1e-4)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "date", "basis", "return"])
def test_forecast_contract_checks(prepared: PreparedData, kind: str) -> None:
    values = forecasts(prepared)
    if kind == "missing":
        values = values[:1]
    elif kind == "duplicate":
        values = (values[0], values[0])
    elif kind == "date":
        values = (
            replace(values[0], forecast_target=prepared.plan.observation_cutoff),
            values[1],
        )
    elif kind == "basis":
        values = (replace(values[0], observed_price=1.0), values[1])
    elif kind == "return":
        values = (replace(values[0], predicted_return=0.9), values[1])
    with pytest.raises(ForecastError):
        allocate_forecasts(prepared, values)


def test_risk_window_defaults_remain_252() -> None:
    assert RunRequest().allocation.risk_window == 252


def test_mixed_booleans_and_scalar_labels_rejected() -> None:
    with pytest.raises(ForecastError):
        solve_allocation(("A", "B"), (True, 0.1), ((1.0, 0.0), (0.0, 1.0)))
    with pytest.raises(ForecastError):
        solve_allocation("AB", (0.1, 0.1), ((1.0, 0.0), (0.0, 1.0)))


def test_overflowing_risk_scale_fails_cleanly() -> None:
    with pytest.raises(ForecastError, match="nonfinite"):
        solve_allocation(("A",), (0.1,), ((1e308,),))
