"""Observed risk, explicit expectations, and independently checked SLSQP weights."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from portfolio_forecasting.config import AllocationSettings
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.forecasting import AssetForecast
from portfolio_forecasting.market_data import PreparedData, prepare_data
from portfolio_forecasting.snapshots import canonical_bytes

Array = NDArray[np.float64]
CONSTRAINT_TOL = 1e-9
MATRIX_REL_TOL = 1e-10
GAP_REL_TOL = 1e-6
SLSQP_FTOL = 1e-12
SLSQP_MAXITER = 1000
DEFAULT_SETTINGS = AllocationSettings()


def numeric_array(value: object, *, ndim: int, name: str) -> Array:
    try:
        objects = np.asarray(value, dtype=object)
        if any(isinstance(item, (bool, np.bool_)) for item in objects.flat):
            raise ValueError("boolean is not a numerical observation")
        original = np.asarray(value)
        if original.dtype.kind not in "fiu" or original.ndim != ndim:
            raise ValueError("not a real numeric array of the required dimension")
        result = np.array(original, dtype=np.float64, copy=True)
        if not np.isfinite(result).all():
            raise ValueError("nonfinite array")
        return result
    except (TypeError, ValueError, OverflowError) as error:
        raise ForecastError(
            "allocation", f"{name} must be a finite numeric {ndim}D array"
        ) from error


def fraction(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ForecastError("allocation", f"{name} must be a finite fraction in [0, 1]")
    return float(value)


@dataclass(frozen=True, slots=True)
class RiskEstimate:
    tickers: tuple[str, ...]
    historical_mean: tuple[float, ...]
    sample_covariance: tuple[tuple[float, ...], ...]
    covariance: tuple[tuple[float, ...], ...]
    observation_count: int
    shrinkage: float


@dataclass(frozen=True, slots=True)
class AllocationResult:
    tickers: tuple[str, ...]
    weights: tuple[float, ...]
    expected_returns: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    diagnostics_json: str


def rows(array: Array) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(value) for value in row) for row in array)


def estimate_risk(data: PreparedData, *, shrinkage: float = 0.0) -> RiskEstimate:
    checked = prepare_data(data.resolved, data.plan, data.assets)
    if checked.returns != data.returns:
        raise ForecastError(
            "allocation", "returns differ from validated observed prices"
        )
    strength = fraction(shrinkage, "shrinkage")
    window = data.resolved.request.allocation.risk_window
    sample = numeric_array(data.returns[-window:], ndim=2, name="observed returns")
    if len(sample) != window or sample.shape[1] != len(data.assets):
        raise ForecastError("allocation", "incomplete risk window or ticker columns")
    with np.errstate(over="ignore", invalid="ignore"):
        covariance = np.atleast_2d(np.cov(sample, rowvar=False, ddof=1))
        regularized = (1 - strength) * covariance + strength * np.diag(
            np.diag(covariance)
        )
    if not np.isfinite(regularized).all():
        raise ForecastError("allocation", "observed covariance is nonfinite")
    return RiskEstimate(
        tuple(data.resolved.request.tickers),
        tuple(float(v) for v in sample.mean(axis=0)),
        rows(covariance),
        rows(regularized),
        window,
        strength,
    )


def equal_weights(
    tickers: Sequence[str], settings: AllocationSettings
) -> tuple[float, ...]:
    settings.validate_universe_size(len(tickers))
    return (1.0 / len(tickers),) * len(tickers)


def _linear_maximum(gradient: Array, lower: float, upper: float) -> Array:
    # Exact linear oracle on a box-constrained simplex, independent of SLSQP.
    vertex = np.full(len(gradient), lower, dtype=np.float64)
    remaining = 1.0 - len(gradient) * lower
    for index in np.argsort(-gradient, kind="stable"):
        change = min(upper - lower, max(0.0, remaining))
        vertex[index] += change
        remaining -= change
    return vertex


def solve_allocation(
    tickers: Sequence[str],
    expectations: object,
    covariance: object,
    settings: AllocationSettings = DEFAULT_SETTINGS,
) -> AllocationResult:
    if isinstance(tickers, (str, bytes)):
        raise ForecastError("allocation", "ticker labels must be a sequence of names")
    labels = tuple(tickers)
    if (
        not labels
        or any(not isinstance(label, str) or not label for label in labels)
        or len(set(labels)) != len(labels)
    ):
        raise ForecastError("allocation", "ticker labels must be nonempty and unique")
    settings.validate_universe_size(len(labels))
    mu = numeric_array(expectations, ndim=1, name="expected returns")
    matrix = numeric_array(covariance, ndim=2, name="covariance")
    if mu.shape != (len(labels),) or matrix.shape != (len(labels), len(labels)):
        raise ForecastError("allocation", "ticker/vector/covariance shape mismatch")
    magnitude = max(float(np.max(np.abs(matrix))), 1e-12)
    with np.errstate(over="ignore", invalid="ignore"):
        symmetry_error = float(np.max(np.abs(matrix - matrix.T)))
    if symmetry_error > MATRIX_REL_TOL * magnitude:
        raise ForecastError("allocation", "covariance must be symmetric")
    # Only accepted roundoff asymmetry is symmetrized; no eigenvalue clipping.
    matrix = 0.5 * matrix + 0.5 * matrix.T
    try:
        eigenvalues = np.linalg.eigvalsh(matrix)
    except np.linalg.LinAlgError as error:
        raise ForecastError(
            "allocation", "covariance eigendecomposition failed"
        ) from error
    if not np.isfinite(eigenvalues).all():
        raise ForecastError("allocation", "covariance eigenvalues are nonfinite")
    psd_tolerance = MATRIX_REL_TOL * max(float(np.max(np.abs(eigenvalues))), 1e-12)
    if eigenvalues[0] < -psd_tolerance:
        raise ForecastError("allocation", "covariance is indefinite")
    rank = int(np.count_nonzero(eigenvalues > psd_tolerance))
    condition = float(eigenvalues[-1] / eigenvalues[0]) if rank == len(labels) else None
    scale = max(float(np.max(np.abs(mu))), settings.risk_aversion * magnitude, 1e-12)
    if not math.isfinite(scale):
        raise ForecastError("allocation", "risk-adjusted objective scale is nonfinite")
    initial = np.asarray(equal_weights(labels, settings))

    def negative_utility(weights: Array) -> float:
        return float(
            (-mu @ weights + settings.risk_aversion / 2 * weights @ matrix @ weights)
            / scale
        )

    def derivative(weights: Array) -> Array:
        return np.asarray((-mu + settings.risk_aversion * matrix @ weights) / scale)

    started = time.perf_counter()
    # A singleton feasible set needs no iterative solver. This is not a fallback.
    fixed = (
        len(labels) == 1
        or len(labels) * settings.lower_bound == 1
        or len(labels) * settings.upper_bound == 1
    )
    if fixed:
        weights, status, message, iterations = (
            initial,
            0,
            "unique feasible allocation",
            0,
        )
    else:
        try:
            result = minimize(
                negative_utility,
                initial,
                jac=derivative,
                method="SLSQP",
                bounds=[(settings.lower_bound, settings.upper_bound)] * len(labels),
                constraints={
                    "type": "eq",
                    "fun": lambda w: float(np.sum(w) - 1),
                    "jac": lambda w: np.ones(len(w)),
                },
                options={"ftol": SLSQP_FTOL, "maxiter": SLSQP_MAXITER, "disp": False},
            )
            if not result.success:
                raise ForecastError(
                    "allocation",
                    f"SLSQP failed (status {result.status}): {result.message}",
                )
            weights = numeric_array(result.x, ndim=1, name="solver weights")
            status, message, iterations = (
                int(result.status),
                str(result.message),
                int(result.nit),
            )
        except ForecastError:
            raise
        except Exception as error:
            raise ForecastError(
                "allocation", f"SLSQP execution failed: {type(error).__name__}"
            ) from error
    if weights.shape != initial.shape:
        raise ForecastError("allocation", "solver returned incorrect weight count")
    budget_error = abs(float(weights.sum()) - 1)
    bound_error = max(
        0.0,
        float(np.max(settings.lower_bound - weights)),
        float(np.max(weights - settings.upper_bound)),
    )
    if budget_error > CONSTRAINT_TOL or bound_error > CONSTRAINT_TOL:
        raise ForecastError("allocation", "solver weights violate budget or bounds")
    utility = -negative_utility(weights) * scale
    initial_utility = -negative_utility(initial) * scale
    gradient = mu - settings.risk_aversion * matrix @ weights
    gap = max(
        0.0,
        float(
            gradient
            @ (
                _linear_maximum(gradient, settings.lower_bound, settings.upper_bound)
                - weights
            )
        ),
    )
    if not all(math.isfinite(v) for v in (utility, initial_utility, gap)):
        raise ForecastError("allocation", "nonfinite objective diagnostics")
    if utility < initial_utility - GAP_REL_TOL * scale or gap > GAP_REL_TOL * scale:
        raise ForecastError(
            "allocation", "solver solution fails independent objective/gap check"
        )
    diagnostics: dict[str, Any] = {
        "method": "fixed_feasible" if fixed else "SLSQP",
        "status": status,
        "message": message,
        "iterations": iterations,
        "seconds": time.perf_counter() - started,
        "utility": utility,
        "initial_utility": initial_utility,
        "expected_return": float(mu @ weights),
        "variance": float(weights @ matrix @ weights),
        "budget_residual": budget_error,
        "bound_residual": bound_error,
        "concavity_gap": gap,
        "gap_tolerance": GAP_REL_TOL * scale,
        "objective_scale": scale,
        "covariance_min_eigenvalue": float(eigenvalues[0]),
        "covariance_rank": rank,
        "covariance_condition": condition,
        "covariance_symmetry_residual": symmetry_error,
        "psd_tolerance": psd_tolerance,
        "constraint_tolerance": CONSTRAINT_TOL,
        "slsqp_ftol": SLSQP_FTOL,
        "slsqp_maxiter": SLSQP_MAXITER,
        "risk_aversion": settings.risk_aversion,
        "lower_bound": settings.lower_bound,
        "upper_bound": settings.upper_bound,
        "effective_max_weight": min(
            settings.upper_bound, 1 - (len(labels) - 1) * settings.lower_bound
        ),
        "concentration_hhi": float(weights @ weights),
    }
    return AllocationResult(
        labels,
        tuple(float(v) for v in weights),
        tuple(float(v) for v in mu),
        rows(matrix),
        canonical_bytes(diagnostics).decode(),
    )


def allocate_forecasts(
    data: PreparedData,
    forecasts: tuple[AssetForecast, ...],
    *,
    alpha: float = 1.0,
    shrinkage: float = 0.0,
    settings: AllocationSettings | None = None,
    run_id: str = "manual",
) -> AllocationResult:
    blend = fraction(alpha, "alpha")
    risk = estimate_risk(data, shrinkage=shrinkage)
    if len(forecasts) != len(risk.tickers) or {
        item.ticker for item in forecasts
    } != set(risk.tickers):
        raise ForecastError(
            "allocation", "forecasts must match the complete ticker set"
        )
    indexed = {item.ticker: item for item in forecasts}
    direct = []
    for ticker, asset in zip(risk.tickers, data.assets, strict=True):
        item = indexed[ticker]
        if (
            item.observation_cutoff != data.plan.observation_cutoff
            or item.forecast_target != data.plan.forecast_target
            or item.observed_price != asset.observations[-1].price
        ):
            raise ForecastError(
                "allocation",
                "forecast dates or price basis do not match observations",
                ticker=ticker,
            )
        values = numeric_array(
            (item.predicted_price, item.predicted_return), ndim=1, name="forecast"
        )
        if values[0] <= 0 or not math.isclose(
            item.predicted_return,
            item.predicted_price / item.observed_price - 1,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ForecastError(
                "allocation", "invalid price/return forecast", ticker=ticker
            )
        direct.append(item.predicted_return)
    mu = (1 - blend) * np.asarray(risk.historical_mean) + blend * np.asarray(direct)
    result = solve_allocation(
        risk.tickers, mu, risk.covariance, settings or data.resolved.request.allocation
    )
    logging.getLogger(__name__).info(
        "run=%s stage=allocation diagnostics=%s", run_id, result.diagnostics_json
    )
    return result


def allocation_sensitivity(
    result: AllocationResult, settings: AllocationSettings, *, step: float = 1e-4
) -> dict[str, float]:
    """One-basis-point expectation shocks, one asset at a time; no outcomes used."""
    if isinstance(step, bool) or not math.isfinite(step) or step <= 0:
        raise ForecastError(
            "allocation", "sensitivity step must be finite and positive"
        )
    distances = []
    original = np.asarray(result.weights)
    for index in range(len(result.tickers)):
        expectations = np.asarray(result.expected_returns).copy()
        expectations[index] += step
        shocked = solve_allocation(
            result.tickers, expectations, result.covariance, settings
        )
        distances.append(float(np.abs(np.asarray(shocked.weights) - original).sum()))
    return {"expectation_step": step, "maximum_weight_l1_change": max(distances)}
