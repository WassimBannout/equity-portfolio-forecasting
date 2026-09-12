import json
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.forecasting import forecast_prices
from portfolio_forecasting.market_data import PreparedData


class FakeProphet:
    instances: list["FakeProphet"] = []
    value: Any = 125.0
    fail = False

    def __init__(self, **options: Any):
        self.options = options
        self.fit_options: dict[str, Any] = {}
        self.changepoints: list[pd.Timestamp] = []
        self.seasonalities: dict[str, Any] = {}
        self.stan_backend = self
        self.instances.append(self)

    def set_options(self, **options: Any) -> None:
        assert options == {"newton_fallback": False}

    def fit(self, history: pd.DataFrame, **options: Any) -> None:
        if self.fail:
            raise RuntimeError("fixture fit failure")
        self.history = history.copy(deep=True)
        self.fit_options = options
        history.iloc[0, 1] = -999  # Must not mutate captured inputs.

    def predict(self, future: pd.DataFrame) -> pd.DataFrame:
        self.future = future.copy(deep=True)
        return future.assign(yhat=self.value)


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch) -> type[FakeProphet]:
    FakeProphet.instances = []
    FakeProphet.value = 125.0
    FakeProphet.fail = False
    monkeypatch.setattr("portfolio_forecasting.forecasting.Prophet", FakeProphet)
    return FakeProphet


def test_independent_refits_complete_universe_and_no_future_prices(
    prepared: PreparedData, fake_model: type[FakeProphet]
) -> None:
    predictions = forecast_prices(prepared)
    assert (
        tuple(pred.ticker for pred in predictions) == prepared.resolved.request.tickers
    )
    assert len(fake_model.instances) == 2
    for model, asset, prediction in zip(
        fake_model.instances, prepared.assets, predictions, strict=True
    ):
        assert model.history["ds"].max().date() == prepared.plan.observation_cutoff
        assert model.history["ds"].min().date() == prepared.plan.sessions[0]
        assert len(model.history) == len(prepared.plan.sessions)
        assert model.history["y"].tolist() == [row.price for row in asset.observations]
        assert model.future["ds"].tolist() == [
            pd.Timestamp(prepared.plan.forecast_target)
        ]
        assert prediction.predicted_return == 125.0 / asset.observations[-1].price - 1.0
        assert model.fit_options["seed"] == 42
        assert json.loads(prediction.model_metadata_json)["newton_fallback"] is False
    assert prepared.assets[0].observations[0].price == 100.0
    forecast_prices(prepared)
    assert len(fake_model.instances) == 4


@pytest.mark.parametrize("value", [0.0, -1.0, np.nan, np.inf, -np.inf, 1e309])
def test_invalid_prediction_aborts_complete_run(
    prepared: PreparedData, fake_model: type[FakeProphet], value: float
) -> None:
    fake_model.value = value
    with pytest.raises(ForecastError, match="AMD.*finite"):
        forecast_prices(prepared)
    assert len(fake_model.instances) == 1


def test_fit_failure_has_ticker_and_stage(
    prepared: PreparedData, fake_model: type[FakeProphet]
) -> None:
    fake_model.fail = True
    with pytest.raises(ForecastError, match="forecast.*AMD.*Prophet"):
        forecast_prices(prepared)


def test_real_offline_prophet_fit_repeatability(prepared: PreparedData) -> None:
    first = forecast_prices(prepared)
    second = forecast_prices(prepared)
    assert all(
        np.isfinite(item.predicted_price) and item.predicted_price > 0 for item in first
    )
    # Numerical reproducibility on a fixed native environment, not accuracy.
    assert [item.predicted_price for item in first] == pytest.approx(
        [item.predicted_price for item in second], rel=1e-8, abs=1e-8
    )
    for item in first:
        assert item.forecast_target == prepared.plan.forecast_target
        assert item.predicted_return == item.predicted_price / item.observed_price - 1.0
        meta = json.loads(item.model_metadata_json)
        assert meta["training_rows"] == len(prepared.plan.sessions)
        assert meta["effective_seasonalities"]["weekly"]["fourier_order"] == 3


def test_forged_return_panel_rejected(prepared: PreparedData) -> None:
    with pytest.raises(ForecastError, match="return panel"):
        forecast_prices(replace(prepared, returns=((0.99, 0.99),)))
