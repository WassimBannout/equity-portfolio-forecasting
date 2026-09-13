"""Frozen-input rolling-origin validation, locked selection, and held-out reporting."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Any

from portfolio_forecasting.allocation import (
    allocate_forecasts,
    allocation_sensitivity,
    equal_weights,
    estimate_risk,
    fraction,
    solve_allocation,
)
from portfolio_forecasting.config import AllocationSettings
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.forecasting import AssetForecast
from portfolio_forecasting.market_data import PreparedData, prepare_data
from portfolio_forecasting.metrics import ForecastPair, forecast_metrics
from portfolio_forecasting.paper import Signal, paper_path
from portfolio_forecasting.research_models import ModelVariant, predict_variant
from portfolio_forecasting.sessions import plan_sessions
from portfolio_forecasting.snapshots import (
    canonical_bytes,
    digest,
    read_snapshot,
    software_metadata,
    write_content,
)

Predictor = Callable[[PreparedData, ModelVariant], tuple[AssetForecast, ...]]


@dataclass(frozen=True, slots=True)
class AllocationVariant:
    name: str
    alpha: float = 1.0
    shrinkage: float = 0.0
    risk_aversion: float = 5.0
    lower_bound: float = 0.05
    upper_bound: float = 1.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ForecastError("evaluation", "allocation variant needs a name")
        fraction(self.alpha, "alpha")
        fraction(self.shrinkage, "shrinkage")
        self.settings()

    def settings(self, risk_window: int = 252) -> AllocationSettings:
        return AllocationSettings(
            risk_aversion=self.risk_aversion,
            lower_bound=self.lower_bound,
            upper_bound=self.upper_bound,
            risk_window=risk_window,
        )


@dataclass(frozen=True, slots=True)
class Experiment:
    training_start: date
    training_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date
    models: tuple[ModelVariant, ...]
    allocations: tuple[AllocationVariant, ...]
    origin_stride_sessions: int = 5
    risk_window: int = 252
    minimum_validation_origins: int = 3
    transaction_cost_bps: float = 10.0
    slippage_bps: float = 5.0
    zero_direction_tolerance: float = 1e-12

    def __post_init__(self) -> None:
        dates = (
            self.training_start,
            self.training_end,
            self.validation_start,
            self.validation_end,
            self.test_start,
            self.test_end,
        )
        if any(type(day) is not date for day in dates) or not (
            dates[0] < dates[1] < dates[2] <= dates[3] < dates[4] <= dates[5]
        ):
            raise ForecastError(
                "evaluation",
                "training/validation/test periods must be ordered and disjoint",
            )
        for value, minimum in (
            (self.origin_stride_sessions, 1),
            (self.risk_window, 2),
            (self.minimum_validation_origins, 1),
        ):
            if type(value) is not int or value < minimum:
                raise ForecastError(
                    "evaluation", "invalid stride, risk window, or minimum sample count"
                )
        for group in (self.models, self.allocations):
            if not group or len({item.name for item in group}) != len(group):
                raise ForecastError(
                    "evaluation", "candidate names must be unique and nonempty"
                )
        if self.models[0].name != "reference" or self.allocations[0].name != "direct":
            raise ForecastError(
                "evaluation", "reference model and direct allocation must be first"
            )
        for cost_value in (
            self.transaction_cost_bps,
            self.slippage_bps,
            self.zero_direction_tolerance,
        ):
            if (
                isinstance(cost_value, bool)
                or not isinstance(cost_value, (int, float))
                or not math.isfinite(cost_value)
                or cost_value < 0
            ):
                raise ForecastError(
                    "evaluation", "invalid cost or zero-direction setting"
                )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Experiment:
        return cls(
            **{
                name: date.fromisoformat(value[name])
                for name in (
                    "training_start",
                    "training_end",
                    "validation_start",
                    "validation_end",
                    "test_start",
                    "test_end",
                )
            },
            models=tuple(ModelVariant(**item) for item in value["models"]),
            allocations=tuple(
                AllocationVariant(**item) for item in value["allocations"]
            ),
            origin_stride_sessions=value["origin_stride_sessions"],
            risk_window=value["risk_window"],
            minimum_validation_origins=value["minimum_validation_origins"],
            transaction_cost_bps=value["transaction_cost_bps_per_dollar_traded"],
            slippage_bps=value["slippage_bps_per_dollar_traded"],
            zero_direction_tolerance=value["zero_direction_tolerance"],
        )


def origin_data(
    frozen: PreparedData, target: date, experiment: Experiment
) -> PreparedData:
    # No target price is included in the object handed to forecasting/allocation.
    request = replace(
        frozen.resolved.request,
        mode="retrospective",
        history_start=experiment.training_start,
        history_end=target,
        allocation=replace(
            frozen.resolved.request.allocation, risk_window=experiment.risk_window
        ),
    )
    resolved = request.resolve(clock=lambda: frozen.resolved.executed_at)
    plan = plan_sessions(resolved)
    if plan is None or plan.forecast_target != target:
        raise ForecastError(
            "evaluation", "evaluation target is not the next exchange session"
        )
    assets = tuple(
        replace(
            asset,
            observations=tuple(
                row
                for row in asset.observations
                if experiment.training_start <= row.session < target
            ),
        )
        for asset in frozen.assets
    )
    return prepare_data(resolved, plan, assets)


def _phase(
    frozen: PreparedData,
    experiment: Experiment,
    start: date,
    end: date,
    models: tuple[ModelVariant, ...],
    allocations: tuple[AllocationVariant, ...],
    predictor: Predictor,
    progress: Callable[[str], None],
) -> dict[str, Any]:
    dates = tuple(day for day in frozen.plan.sessions if start <= day <= end)
    if len(dates) < 2 or end > frozen.plan.observation_cutoff:
        raise ForecastError(
            "evaluation", "evaluation phase lacks complete dated outcomes"
        )
    # The last close is reserved for ending a holding interval, not a new trade.
    targets = dates[: -1 : experiment.origin_stride_sessions]
    pairs: dict[str, list[ForecastPair]] = {model.name: [] for model in models}
    pairs["last_price"] = []
    signals: dict[str, list[Signal]] = {}
    diagnostics: dict[str, list[dict[str, Any]]] = {}
    records: list[dict[str, Any]] = []
    exclusions = []
    timings = []
    for number, target in enumerate(targets, 1):
        progress(f"origin {number}/{len(targets)} target={target}")
        started = time.perf_counter()
        try:
            data = origin_data(frozen, target, experiment)
            risk = estimate_risk(data)
            forecasts = {model.name: predictor(data, model) for model in models}
            local_signals: dict[str, Signal] = {}
            local_diagnostics: dict[str, dict[str, Any]] = {}
            for model in models:
                for allocation in allocations:
                    name = f"{model.name}/{allocation.name}"
                    result = allocate_forecasts(
                        data,
                        forecasts[model.name],
                        alpha=allocation.alpha,
                        shrinkage=allocation.shrinkage,
                        settings=allocation.settings(experiment.risk_window),
                        run_id=f"research:{target}:{name}",
                    )
                    local_signals[name] = Signal(
                        data.plan.observation_cutoff, target, result.weights
                    )
                    local_diagnostics[name] = json.loads(result.diagnostics_json)
                    if model.name == "reference" and allocation.name in {
                        "direct",
                        "diagonal_025",
                    }:
                        local_diagnostics[name]["sensitivity"] = allocation_sensitivity(
                            result, allocation.settings(experiment.risk_window)
                        )
            for allocation in allocations:
                settings = allocation.settings(experiment.risk_window)
                # Comparable baseline for each constraint/risk configuration.
                baseline_risk = estimate_risk(data, shrinkage=allocation.shrinkage)
                result = solve_allocation(
                    risk.tickers,
                    risk.historical_mean,
                    baseline_risk.covariance,
                    settings,
                )
                name = f"historical_only/{allocation.name}"
                local_signals[name] = Signal(
                    data.plan.observation_cutoff, target, result.weights
                )
                local_diagnostics[name] = json.loads(result.diagnostics_json)
                local_signals[f"equal_weight/{allocation.name}"] = Signal(
                    data.plan.observation_cutoff,
                    target,
                    equal_weights(risk.tickers, settings),
                )
            # All forecasts AND weights now exist. Only now read this target outcome.
            actuals = {
                asset.ticker: next(
                    row.price for row in asset.observations if row.session == target
                )
                for asset in frozen.assets
            }
            local_pairs = {}
            for model in models:
                local_pairs[model.name] = [
                    ForecastPair(
                        item.ticker,
                        data.plan.observation_cutoff,
                        target,
                        item.observed_price,
                        item.predicted_price,
                        actuals[item.ticker],
                    )
                    for item in forecasts[model.name]
                ]
            local_pairs["last_price"] = [
                ForecastPair(
                    asset.ticker,
                    data.plan.observation_cutoff,
                    target,
                    asset.observations[-1].price,
                    asset.observations[-1].price,
                    actuals[asset.ticker],
                )
                for asset in data.assets
            ]
            for name, values in local_pairs.items():
                pairs[name].extend(values)
            for name, signal in local_signals.items():
                signals.setdefault(name, []).append(signal)
            for name, info in local_diagnostics.items():
                diagnostics.setdefault(name, []).append(info)
            records.append(
                {
                    "cutoff": data.plan.observation_cutoff,
                    "target": target,
                    "input_sha256": digest(canonical_bytes(data.assets)),
                    "risk": risk,
                    "forecasts": forecasts,
                    "signals": local_signals,
                }
            )
        except (ForecastError, ValueError, StopIteration) as error:
            exclusions.append(
                {
                    "target": target,
                    "reason": str(error),
                    "policy": "exclude entire origin for every candidate and baseline",
                }
            )
            progress(f"excluded target={target}: {error}")
        timings.append({"target": target, "seconds": time.perf_counter() - started})
    accepted = len(records)
    if not accepted:
        raise ForecastError("evaluation", "no complete comparable evaluation origins")
    first_target = records[0]["target"]
    holding_dates = tuple(day for day in dates if day >= first_target)
    asset_prices = [
        {
            row.session: row.price
            for row in asset.observations
            if holding_dates[0] <= row.session <= holding_dates[-1]
        }
        for asset in frozen.assets
    ]
    prices = tuple(tuple(asset[day] for asset in asset_prices) for day in holding_dates)
    paths = {
        name: paper_path(
            holding_dates,
            prices,
            tuple(values),
            transaction_cost_bps=experiment.transaction_cost_bps,
            slippage_bps=experiment.slippage_bps,
        )
        for name, values in signals.items()
    }
    return {
        "start": start,
        "end": end,
        "attempted_origins": len(targets),
        "accepted_origins": accepted,
        "excluded_origins": exclusions,
        "forecast_metrics": {
            name: forecast_metrics(
                tuple(values), zero_tolerance=experiment.zero_direction_tolerance
            )
            for name, values in pairs.items()
        },
        "paper": paths,
        "solver_diagnostics": diagnostics,
        "origins": records,
        "timings": timings,
        "failure_holding_policy": (
            "carry preceding weights until next successful signal; all "
            "policies share excluded origins"
        ),
    }


def select_candidates(
    validation: Mapping[str, Any], experiment: Experiment
) -> dict[str, Any]:
    if validation["accepted_origins"] < experiment.minimum_validation_origins:
        raise ForecastError("evaluation", "insufficient comparable validation origins")
    scores = {
        model.name: validation["forecast_metrics"][model.name][
            "macro_relative_price_mae"
        ]
        for model in experiment.models
    }
    finite = {
        name: score
        for name, score in scores.items()
        if score is not None and math.isfinite(score)
    }
    if "reference" not in finite:
        raise ForecastError("evaluation", "reference validation score is undefined")
    best = min(finite, key=lambda name: finite[name])
    chosen = best if finite[best] < 0.95 * finite["reference"] else "reference"
    net = {
        allocation.name: validation["paper"][f"{chosen}/{allocation.name}"][
            "net_cumulative_return"
        ]
        for allocation in experiment.allocations
    }
    best_allocation = max(net, key=lambda name: net[name])
    selected_allocation = (
        best_allocation if net[best_allocation] > net["direct"] + 0.001 else "direct"
    )
    return {
        "model": chosen,
        "allocation": selected_allocation,
        "model_scores": scores,
        "allocation_net_scores": net,
        "model_rule": (
            "at least 5% lower validation macro relative price MAE, otherwise reference"
        ),
        "allocation_rule": (
            "over 0.001 greater validation cumulative net research return, "
            "otherwise direct"
        ),
        "tie_policy": "candidate declaration order",
    }


def evaluate_snapshot(
    snapshot: Path,
    experiment: Experiment,
    *,
    output_directory: Path,
    predictor: Predictor = predict_variant,
    progress: Callable[[str], None] = print,
) -> Path:
    frozen = read_snapshot(snapshot)
    if (
        frozen.resolved.request.history_start > experiment.training_start
        or frozen.plan.observation_cutoff < experiment.test_end
    ):
        raise ForecastError(
            "evaluation", "frozen dataset does not cover declared training/test dates"
        )
    first_origin = origin_data(frozen, experiment.validation_start, experiment)
    if first_origin.plan.observation_cutoff != experiment.training_end:
        raise ForecastError(
            "evaluation", "training_end must be the first validation origin cutoff"
        )
    for allocation in experiment.allocations:
        allocation.settings(experiment.risk_window).validate_universe_size(
            len(frozen.assets)
        )
    declaration = {
        "schema_version": 1,
        "experiment": experiment,
        "snapshot_sha256": snapshot.stem,
        "software": {**software_metadata(), "scipy": version("scipy")},
        "providers": sorted({asset.provider for asset in frozen.assets}),
        "research_only": True,
        "price_basis": (
            "retrospective adjusted_close; point-in-time availability unproven"
        ),
    }
    declared = write_content(
        canonical_bytes(declaration), output_directory / "declarations"
    )
    progress(f"declaration={declared.stem}; final-test outcomes not yet evaluated")
    validation = _phase(
        frozen,
        experiment,
        experiment.validation_start,
        experiment.validation_end,
        experiment.models,
        experiment.allocations,
        predictor,
        progress,
    )
    selection = select_candidates(validation, experiment)
    validation_file = write_content(
        canonical_bytes(validation), output_directory / "validation"
    )
    selection.update(
        {
            "declaration_sha256": declared.stem,
            "validation_sha256": validation_file.stem,
            "test_inspected": False,
        }
    )
    selection_file = write_content(
        canonical_bytes(selection), output_directory / "selection"
    )
    # No later score is passed back into selection. Persist this decision FIRST.
    progress(
        f"selection frozen={selection_file.stem}; "
        f"model={selection['model']} allocation={selection['allocation']}"
    )
    models = tuple(
        model
        for model in experiment.models
        if model.name in {"reference", selection["model"]}
    )
    allocations = tuple(
        item
        for item in experiment.allocations
        if item.name in {"direct", selection["allocation"]}
    )
    test = _phase(
        frozen,
        experiment,
        experiment.test_start,
        experiment.test_end,
        models,
        allocations,
        predictor,
        progress,
    )
    result = {
        "schema_version": 1,
        "declaration": declaration,
        "declaration_sha256": declared.stem,
        "selection": selection,
        "selection_sha256": selection_file.stem,
        "validation": validation,
        "final_test": test,
        "limitations": [
            "current fixed universe",
            "revised adjusted history is not point-in-time data",
            "sampled origins, next-session forecasts",
            (
                "costed adjusted-close research accounting is not executable "
                "trading performance"
            ),
            "no selection after final-test inspection",
        ],
    }
    path = write_content(canonical_bytes(result), output_directory / "results")
    progress(f"complete result={path}")
    return path
