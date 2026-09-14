"""Strict scientific documents and stable identity inputs for M4 publication."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np

from portfolio_forecasting.allocation import (
    CONSTRAINT_TOL,
    GAP_REL_TOL,
    estimate_risk,
    numeric_array,
    solve_allocation,
)
from portfolio_forecasting.config import ResolvedRunRequest
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.market_data import aware_utc
from portfolio_forecasting.portfolio import PortfolioReport
from portfolio_forecasting.sessions import SessionPlan
from portfolio_forecasting.snapshots import (
    canonical_bytes,
    digest,
    read_snapshot,
    software_metadata,
)


class StoreError(ValueError):
    """Sanitized storage failure; never includes response bodies or credentials."""


class StoreConflict(StoreError):
    """A logical request is already bound to different immutable content."""


def object_value(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise StoreError(f"invalid {label} object")
    return value


def number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StoreError(f"missing or invalid {label}")
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise StoreError(f"invalid {label}") from error
    if not math.isfinite(result) or (positive and result <= 0):
        raise StoreError(f"invalid {label}")
    return result


def iso_date(value: object) -> date:
    if not isinstance(value, str):
        raise StoreError("missing session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise StoreError("invalid session date") from error
    if parsed.isoformat() != value:
        raise StoreError("session date must use YYYY-MM-DD")
    return parsed


def iso_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise StoreError("missing timestamp")
    try:
        return aware_utc(datetime.fromisoformat(value))
    except (ValueError, ForecastError) as error:
        raise StoreError("timestamp must be valid and timezone-aware") from error


def hash_value(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise StoreError("invalid SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class Release:
    lock_sha256: str
    software_json: str

    @classmethod
    def capture(cls, lock: Path) -> Release:
        return cls(
            digest(lock.read_bytes()), canonical_bytes(software_metadata()).decode()
        )

    def __post_init__(self) -> None:
        hash_value(self.lock_sha256)
        software = object_value(json.loads(self.software_json), "software")
        hash_value(software["source_sha256"])
        if not software.get("packages") or not software.get("python"):
            raise StoreError("missing runtime provenance")


def identity_for(
    resolved: ResolvedRunRequest, plan: SessionPlan, release: Release
) -> dict[str, Any]:
    request = resolved.request
    software = json.loads(release.software_json)
    # The database hashes canonical JSONB. Wall-clock attempts and weekend end
    # aliases do not create new logical runs. Canonical universe order is explicit.
    return {
        "schema_version": 1,
        "mode": request.mode,
        "observation_cutoff": plan.observation_cutoff.isoformat(),
        "forecast_target": plan.forecast_target.isoformat(),
        "universe": sorted(request.tickers),
        "history_start": request.history_start.isoformat(),
        "scientific_revision": request.scientific_revision,
        "forecast": asdict(request.forecast),
        "allocation": asdict(request.allocation),
        "data": asdict(request.data),
        "software_revision": software["source_sha256"],
        "lock_sha256": release.lock_sha256,
        "python_version": software["python"],
    }


def publication_payload(report: PortfolioReport, release: Release) -> dict[str, Any]:
    data = report.forecast.data
    captured = read_snapshot(report.forecast.snapshot_path)
    if captured != data or report.forecast.replay:
        raise StoreError(
            "publication requires its exact bound inputs and explicit mode"
        )
    if report.completed_at < report.forecast.completed_at:
        raise StoreError("completion timestamps are not chronological")
    risk = estimate_risk(data)
    tickers = risk.tickers
    indexed = {item.ticker: item for item in report.forecast.forecasts}
    if len(indexed) != len(report.forecast.forecasts) or set(indexed) != set(tickers):
        raise StoreError("incomplete or duplicate forecast membership")
    result = report.allocation
    if result.tickers != tickers:
        raise StoreError("allocation ticker order differs from observed risk")
    weights = numeric_array(result.weights, ndim=1, name="publication weights")
    settings = data.resolved.request.allocation
    if (
        weights.shape != (len(tickers),)
        or abs(float(weights.sum()) - 1) > CONSTRAINT_TOL
    ):
        raise StoreError("incomplete allocation or invalid full-investment budget")
    if np.any(weights < settings.lower_bound - CONSTRAINT_TOL) or np.any(
        weights > settings.upper_bound + CONSTRAINT_TOL
    ):
        raise StoreError("allocation violates declared bounds")
    direct = []
    for asset in data.assets:
        item = indexed[asset.ticker]
        if (
            item.observation_cutoff != data.plan.observation_cutoff
            or item.forecast_target != data.plan.forecast_target
            or item.observed_price != asset.observations[-1].price
        ):
            raise StoreError("forecast dates or observed basis differ from input")
        predicted = number(item.predicted_price, "forecast price", positive=True)
        expected = number(item.predicted_return, "forecast return")
        if not math.isclose(
            expected, predicted / item.observed_price - 1, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise StoreError("forecast price and return disagree")
        direct.append(expected)
    mu = numeric_array(result.expected_returns, ndim=1, name="publication expectations")
    matrix = numeric_array(result.covariance, ndim=2, name="publication covariance")
    if (
        mu.shape != (len(tickers),)
        or matrix.shape != (len(tickers), len(tickers))
        or not np.allclose(mu, direct, rtol=1e-12, atol=1e-12)
        or not np.allclose(matrix, risk.covariance, rtol=1e-12, atol=1e-12)
    ):
        raise StoreError(
            "published expectations/risk differ from the declared direct policy"
        )
    optimum = solve_allocation(tickers, mu, matrix, settings)
    check = json.loads(optimum.diagnostics_json)
    utility = float(
        mu @ weights - settings.risk_aversion / 2 * weights @ matrix @ weights
    )
    if utility < check["utility"] - GAP_REL_TOL * check["objective_scale"]:
        raise StoreError("allocation fails independent publication objective check")
    diagnostics = object_value(
        json.loads(result.diagnostics_json), "solver diagnostics"
    )
    if diagnostics.get("status") != 0 or not diagnostics.get("method"):
        raise StoreError("missing successful solver diagnostics")
    # Elapsed seconds belong to the attempt, not the immutable scientific payload.
    diagnostics = {key: value for key, value in diagnostics.items() if key != "seconds"}
    order = sorted(range(len(tickers)), key=lambda index: tickers[index])
    assets = []
    for index in order:
        ticker = tickers[index]
        item = indexed[ticker]
        model = object_value(json.loads(item.model_metadata_json), "model provenance")
        if not model.get("constructor") or not model.get("fit"):
            raise StoreError("missing effective model settings")
        assets.append(
            {
                "ticker": ticker,
                "observed_price": item.observed_price,
                "predicted_price": item.predicted_price,
                "predicted_return": item.predicted_return,
                "weight": float(weights[index]),
                "model": model,
                "recent_history": json.loads(
                    canonical_bytes(data.recent_history(ticker))
                ),
            }
        )
    payload = {
        "schema_version": 1,
        "assets": assets,
        "expected_returns": [float(mu[i]) for i in order],
        "covariance": [[float(matrix[i, j]) for j in order] for i in order],
        "risk_observations": risk.observation_count,
        "risk_estimator": "observed_sample_ddof1",
        "expectation_estimator": "direct_forecast_return",
        "solver": diagnostics,
        "software": json.loads(release.software_json),
        "lock_sha256": release.lock_sha256,
    }
    # Reject nonfinite nested diagnostics/provenance before any HTTP request.
    return object_value(json.loads(canonical_bytes(payload)), "publication")


def validate_published_run(value: object) -> dict[str, Any]:
    """Fail closed when API limits, malformed data, or mixed rows lose completeness."""
    try:
        canonical_bytes(value)
        run = object_value(value, "published run")
        UUID(run["run_id"])
        hash_value(run["request_key"])
        hash_value(run["snapshot_sha256"])
        hash_value(run["result_sha256"])
        if run["state"] != "published":
            raise StoreError("run is not published")
        identity = object_value(run["identity"], "run identity")
        cutoff, target = (
            iso_date(identity["observation_cutoff"]),
            iso_date(identity["forecast_target"]),
        )
        if cutoff >= target:
            raise StoreError("invalid run horizon")
        if iso_time(run["published_at"]) < iso_time(run["executed_at"]):
            raise StoreError("publication precedes execution")
        universe = identity["universe"]
        if (
            not isinstance(universe, list)
            or not universe
            or universe != sorted(set(universe))
        ):
            raise StoreError("invalid canonical universe")
        provenance = object_value(run["input_provenance"], "input provenance")
        hash_value(provenance["data_sha256"])
        if provenance["price_basis"] != "adjusted_close":
            raise StoreError("unsupported published price basis")
        object_value(provenance["provider_options"], "provider options")
        if [item["ticker"] for item in provenance["assets"]] != universe:
            raise StoreError("input provenance membership is incomplete")
        for item in provenance["assets"]:
            if not item["provider"] or not item["metadata"]:
                raise StoreError("missing input provider metadata")
            iso_time(item["retrieved_at"])
        if not (
            iso_time(run["executed_at"])
            <= iso_time(run["completed_at"])
            <= iso_time(run["published_at"])
        ):
            raise StoreError("publication timestamps are not chronological")
        if iso_time(run["target_open"]) >= iso_time(run["target_close"]):
            raise StoreError("invalid target session timestamps")
        assets = run["assets"]
        if (
            not isinstance(assets, list)
            or [row["ticker"] for row in assets] != universe
        ):
            raise StoreError("published run membership is incomplete or mixed")
        weights = []
        bounds = identity["allocation"]
        for asset in assets:
            observed = number(asset["observed_price"], "observed price", positive=True)
            predicted = number(
                asset["predicted_price"], "forecast price", positive=True
            )
            expected = number(asset["predicted_return"], "forecast return")
            weight = number(asset["weight"], "weight")
            if (
                not math.isclose(
                    expected, predicted / observed - 1, rel_tol=1e-10, abs_tol=1e-12
                )
                or not bounds["lower_bound"] - CONSTRAINT_TOL
                <= weight
                <= bounds["upper_bound"] + CONSTRAINT_TOL
            ):
                raise StoreError("invalid scientific output in published run")
            weights.append(weight)
            history = asset["recent_history"]
            if not isinstance(history, list) or not history:
                raise StoreError("missing dated history")
            dates = [iso_date(row["session"]) for row in history]
            if dates != sorted(set(dates)) or dates[-1] != cutoff:
                raise StoreError("invalid dated recent history")
            for row in history:
                number(row["price"], "history price", positive=True)
            if history[-1]["price"] != observed:
                raise StoreError("recent history does not end at the observed price")
            outcome = asset["outcome"]
            if outcome is not None:
                if iso_date(outcome["target"]) != target:
                    raise StoreError("outcome does not match the exact target")
                if outcome["state"] == "matched":
                    number(outcome["actual_price"], "actual price", positive=True)
                elif (
                    outcome["state"] not in ("pending", "incompatible")
                    or outcome["actual_price"] is not None
                ):
                    raise StoreError("invalid unresolved outcome")
        if abs(sum(weights) - 1) > CONSTRAINT_TOL:
            raise StoreError("published run allocation budget is incomplete")
        science = object_value(run["scientific_payload"], "scientific payload")
        published_assets = [
            {key: item for key, item in asset.items() if key != "outcome"}
            for asset in assets
        ]
        if published_assets != sorted(
            science["assets"], key=lambda item: item["ticker"]
        ):
            raise StoreError("asset rows differ from the immutable scientific payload")
        if (
            science["software"]["source_sha256"] != identity["software_revision"]
            or science["lock_sha256"] != identity["lock_sha256"]
        ):
            raise StoreError("published release provenance is inconsistent")
        return run
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, StoreError):
            raise
        raise StoreError("malformed complete-run response") from error
