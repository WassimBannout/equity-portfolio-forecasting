import json
from dataclasses import replace
from pathlib import Path

import pytest

from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.evaluation import (
    AllocationVariant,
    Experiment,
    evaluate_snapshot,
    origin_data,
    select_candidates,
)
from portfolio_forecasting.forecasting import AssetForecast
from portfolio_forecasting.market_data import PreparedData, prepare_data
from portfolio_forecasting.research_models import (
    ModelVariant,
    predict_variant,
    variant_data,
)
from portfolio_forecasting.research_report import export_report
from portfolio_forecasting.snapshots import read_snapshot, write_snapshot
from tests.test_allocation import forecasts


def experiment(data: PreparedData) -> Experiment:
    days = data.plan.sessions
    return Experiment(
        training_start=days[0],
        training_end=days[9],
        validation_start=days[10],
        validation_end=days[22],
        test_start=days[23],
        test_end=days[-1],
        models=(
            ModelVariant("reference", yearly=False),
            ModelVariant("simple", yearly=False, holidays=False),
        ),
        allocations=(
            AllocationVariant("direct"),
            AllocationVariant("blend", alpha=0.25),
        ),
        origin_stride_sessions=3,
        risk_window=2,
        minimum_validation_origins=2,
    )


def test_periods_and_candidate_config_rejected(prepared: PreparedData) -> None:
    config = experiment(prepared)
    with pytest.raises(ForecastError):
        replace(config, test_start=config.validation_end)
    with pytest.raises(ForecastError):
        replace(config, models=(ModelVariant("wrong"),))
    with pytest.raises(ForecastError):
        replace(config, origin_stride_sessions=0)
    with pytest.raises(ForecastError):
        ModelVariant("bad", window_prices=2)
    with pytest.raises(ForecastError):
        AllocationVariant("bad", alpha=2)


def test_origin_and_rolling_windows_contain_only_past(prepared: PreparedData) -> None:
    config = experiment(prepared)
    target = prepared.plan.sessions[20]
    data = origin_data(prepared, target, config)
    assert all(
        row.session < target for asset in data.assets for row in asset.observations
    )
    assert data.plan.forecast_target == target
    rolled = variant_data(data, ModelVariant("rolling", yearly=False, window_prices=5))
    assert len(rolled.plan.sessions) == 5
    assert rolled.assets[0].observations[-1] == data.assets[0].observations[-1]
    assert len(rolled.returns) == 4


def test_real_prior_variant_fit(prepared: PreparedData) -> None:
    result = predict_variant(
        prepared, ModelVariant("prior", yearly=False, changepoint_prior_scale=0.01)
    )
    assert len(result) == 2 and all(item.predicted_price > 0 for item in result)
    assert (
        json.loads(result[0].model_metadata_json)["constructor"][
            "changepoint_prior_scale"
        ]
        == 0.01
    )


def test_future_mutation_cannot_change_validation_or_selection(
    prepared: PreparedData, tmp_path: Path
) -> None:
    config = experiment(prepared)
    calls = []

    def predictor(data: PreparedData, model: ModelVariant) -> tuple[AssetForecast, ...]:
        assert (
            max(row.session for asset in data.assets for row in asset.observations)
            < data.plan.forecast_target
        )
        calls.append(data.plan.forecast_target)
        return forecasts(
            data, (0.001, 0.001) if model.name == "reference" else (0.0015, 0.0015)
        )

    original = write_snapshot(prepared, tmp_path / "inputs")
    first = evaluate_snapshot(
        original,
        config,
        output_directory=tmp_path / "first",
        predictor=predictor,
        progress=lambda value: None,
    )
    changed_assets = tuple(
        replace(
            asset,
            observations=tuple(
                replace(row, price=row.price * 1.01)
                if row.session >= config.test_start
                else row
                for row in asset.observations
            ),
        )
        for asset in prepared.assets
    )
    changed = prepare_data(prepared.resolved, prepared.plan, changed_assets)
    second = evaluate_snapshot(
        write_snapshot(changed, tmp_path / "inputs"),
        config,
        output_directory=tmp_path / "second",
        predictor=predictor,
        progress=lambda value: None,
    )
    a, b = json.loads(first.read_bytes()), json.loads(second.read_bytes())
    assert a["validation"]["forecast_metrics"] == b["validation"]["forecast_metrics"]
    for key in ("model", "allocation", "model_scores", "allocation_net_scores"):
        assert a["selection"][key] == b["selection"][key]
    assert a["final_test"]["forecast_metrics"] != b["final_test"]["forecast_metrics"]
    selection = tmp_path / "first" / "selection" / f"{a['selection_sha256']}.json"
    assert (
        selection.exists()
        and json.loads(selection.read_bytes())["test_inspected"] is False
    )
    assert read_snapshot(original) == prepared
    report = export_report(first, tmp_path / "report")
    assert report.is_file()
    assert (report.parent / "forecast_metrics.csv").read_text().startswith("phase,")
    assert (
        (report.parent / "final_test_research.png").read_bytes().startswith(b"\x89PNG")
    )
    assert (
        json.loads((report.parent / "summary.json").read_bytes())["selection"]
        == a["selection"]
    )


def test_selection_file_exists_before_final_prediction(
    prepared: PreparedData, tmp_path: Path
) -> None:
    config = experiment(prepared)

    def predictor(data: PreparedData, model: ModelVariant) -> tuple[AssetForecast, ...]:
        if data.plan.forecast_target >= config.test_start:
            assert len(list((tmp_path / "study" / "selection").glob("*.json"))) == 1
        return forecasts(data, (0.001, 0.001))

    evaluate_snapshot(
        write_snapshot(prepared, tmp_path / "input"),
        config,
        output_directory=tmp_path / "study",
        predictor=predictor,
        progress=lambda value: None,
    )


def test_candidate_failure_has_common_exclusion(
    prepared: PreparedData, tmp_path: Path
) -> None:
    config = experiment(prepared)
    failed_target = config.validation_start

    def predictor(data: PreparedData, model: ModelVariant) -> tuple[AssetForecast, ...]:
        if data.plan.forecast_target == failed_target and model.name == "simple":
            raise ForecastError("forecast", "fixture failure")
        return forecasts(data, (0.001, 0.001))

    path = evaluate_snapshot(
        write_snapshot(prepared, tmp_path / "input"),
        config,
        output_directory=tmp_path / "study",
        predictor=predictor,
        progress=lambda value: None,
    )
    result = json.loads(path.read_bytes())["validation"]
    assert len(result["excluded_origins"]) == 1
    assert len({value["pairs"] for value in result["forecast_metrics"].values()}) == 1
    assert result["accepted_origins"] == result["attempted_origins"] - 1


def test_selection_rules_and_ties(prepared: PreparedData) -> None:
    config = experiment(prepared)
    metrics = {
        "reference": {"macro_relative_price_mae": 2.0},
        "simple": {"macro_relative_price_mae": 1.99},
    }
    paper = {
        f"{model}/{name}": {"net_cumulative_return": 0.02}
        for model in ("reference", "simple")
        for name in ("direct", "blend")
    }
    validation = {"accepted_origins": 3, "forecast_metrics": metrics, "paper": paper}
    assert select_candidates(validation, config)["model"] == "reference"
    metrics["simple"]["macro_relative_price_mae"] = 1.0
    paper["simple/blend"]["net_cumulative_return"] = 0.03
    selection = select_candidates(validation, config)
    assert selection["model"] == "simple" and selection["allocation"] == "blend"


@pytest.mark.parametrize("cost", [float("nan"), float("inf"), -1.0, True])
def test_invalid_research_costs_rejected(prepared: PreparedData, cost: float) -> None:
    with pytest.raises(ForecastError):
        replace(experiment(prepared), transaction_cost_bps=cost)


def test_declared_training_boundary_enforced(
    prepared: PreparedData, tmp_path: Path
) -> None:
    config = replace(experiment(prepared), training_end=prepared.plan.sessions[8])
    with pytest.raises(ForecastError, match="training_end"):
        evaluate_snapshot(
            write_snapshot(prepared, tmp_path / "inputs"),
            config,
            output_directory=tmp_path / "study",
            progress=lambda value: None,
        )
