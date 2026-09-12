import copy
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from yfinance import _http
from yfinance.scrapers.history import PriceHistory

from portfolio_forecasting import AllocationSettings, ForecastSettings, RunRequest
from portfolio_forecasting.__main__ import main
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.forecasting import forecast_prices
from portfolio_forecasting.market_data import PreparedData, YFinanceSource, prepare_data
from portfolio_forecasting.pipeline import replay_forecast
from portfolio_forecasting.sessions import plan_sessions
from portfolio_forecasting.snapshots import (
    canonical_bytes,
    read_snapshot,
    write_content,
    write_snapshot,
)
from tests.market_fixtures import NOW, metadata, synthetic_history
from tests.test_forecasting import FakeProphet
from tests.test_market_data import Client


class Response:
    text = "synthetic fixture"

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return copy.deepcopy(self.payload)


class Transport:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def get(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        return Response(self.payload)

    cache_get = get


def yahoo_fixture() -> dict[str, Any]:
    timestamps = [
        int(day.timestamp())
        for day in pd.date_range("2026-09-02 09:30", periods=3, tz="America/New_York")
    ]
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {
                        **metadata("AMD"),
                        "priceHint": 2,
                        "validRanges": ["1mo"],
                        "gmtoffset": -14400,
                        "timezone": "EDT",
                    },
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [200.0, 204.0, 202.0],
                                "high": [201.0, 205.0, 203.0],
                                "low": [199.0, 203.0, 201.0],
                                "close": [200.0, 204.0, 202.0],
                                "volume": [100, 101, 102],
                            }
                        ],
                        "adjclose": [{"adjclose": [100.0, 102.0, 101.0]}],
                    },
                }
            ],
        }
    }


def test_actual_yfinance_parser_with_offline_transport() -> None:
    payload = yahoo_fixture()
    before = copy.deepcopy(payload)
    transport = Transport(payload)
    provider = YFinanceSource(
        factory=lambda ticker: PriceHistory(transport, ticker, "America/New_York"),
        clock=lambda: NOW,
    )
    history = provider.fetch(
        "AMD", RunRequest().resolve(clock=lambda: NOW), run_id="parser-fixture"
    )
    assert [item.price for item in history.observations] == [100.0, 102.0, 101.0]
    assert [item.session for item in history.observations] == [
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    ]
    assert payload == before
    assert len(transport.calls) == 1  # No lazy intraday metadata request.
    assert transport.calls[0]["params"]["interval"] == "1d"
    assert transport.calls[0]["timeout"] == 30.0


def test_actual_yfinance_parser_preserves_missing_adjusted_close() -> None:
    payload = yahoo_fixture()
    payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][1] = None
    transport = Transport(payload)
    provider = YFinanceSource(
        factory=lambda ticker: PriceHistory(transport, ticker, "America/New_York"),
        clock=lambda: NOW,
    )
    with pytest.raises(ForecastError, match="finite"):
        provider.fetch(
            "AMD", RunRequest().resolve(clock=lambda: NOW), run_id="missing-fixture"
        )
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "status,retries", [(429, 3), (500, 3), (503, 3), (400, 1), (401, 1), (404, 1)]
)
def test_http_failure_classification(status: int, retries: int) -> None:
    response = _http.requests.Response()
    response.status_code = status
    error = _http.HTTPError("fixture", response=response)
    client = Client([error] * 4)
    delays: list[float] = []
    provider = YFinanceSource(factory=lambda ticker: client, sleeper=delays.append)
    with pytest.raises(ForecastError):
        provider.fetch("AMD", RunRequest().resolve(clock=lambda: NOW), run_id="http")
    assert len(client.calls) == retries
    assert len(delays) == retries - 1


def test_one_attempt_and_backoff_cap() -> None:
    client = Client([TimeoutError()] * 4)
    delays: list[float] = []
    provider = YFinanceSource(factory=lambda ticker: client, sleeper=delays.append)
    request = RunRequest()
    capped = replace(request, data=replace(request.data, retry_backoff_seconds=1e100))
    with pytest.raises(ForecastError):
        provider.fetch("AMD", capped.resolve(clock=lambda: NOW), run_id="cap")
    assert delays == [30.0, 30.0]
    single = replace(request, data=replace(request.data, download_attempts=1))
    with pytest.raises(ForecastError):
        provider.fetch("AMD", single.resolve(clock=lambda: NOW), run_id="single")
    assert len(client.calls) == 4


@pytest.mark.parametrize("count", [252, 253])
def test_live_risk_price_gate(count: int) -> None:
    request = RunRequest(
        tickers=("AMD",), forecast=ForecastSettings(yearly_seasonality=False)
    )
    plan = plan_sessions(request.resolve(clock=lambda: NOW))
    assert plan is not None
    request = replace(request, history_start=plan.sessions[-count])
    resolved = request.resolve(clock=lambda: NOW)
    plan = plan_sessions(resolved)
    assert plan is not None
    assets = (synthetic_history("AMD", plan.sessions),)
    if count == 252:
        with pytest.raises(ForecastError, match="requires 253 prices"):
            prepare_data(resolved, plan, assets)
    else:
        assert len(prepare_data(resolved, plan, assets).returns) == 252


@pytest.mark.parametrize(
    "start,valid", [(date(2023, 2, 28), True), (date(2023, 3, 1), False)]
)
def test_annual_history_gate_at_leap_boundary(start: date, valid: bool) -> None:
    request = RunRequest(
        tickers=("AMD",),
        history_start=start,
        history_end=date(2024, 3, 1),
        mode="retrospective",
        allocation=AllocationSettings(risk_window=2),
        forecast=ForecastSettings(minimum_yearly_history_years=1),
    )
    resolved = request.resolve(clock=lambda: NOW)
    plan = plan_sessions(resolved)
    assert plan is not None
    assets = (synthetic_history("AMD", plan.sessions),)
    if valid:
        assert prepare_data(resolved, plan, assets).assets
    else:
        with pytest.raises(ForecastError, match="yearly seasonality"):
            prepare_data(resolved, plan, assets)


def test_holidays_can_be_disabled_without_disabling_calendar(
    prepared: PreparedData,
) -> None:
    request = replace(
        prepared.resolved.request,
        forecast=replace(prepared.resolved.request.forecast, holiday_effects=False),
    )
    resolved = request.resolve(clock=lambda: NOW)
    plan = plan_sessions(resolved)
    assert plan is not None and not plan.holidays
    assert plan.forecast_target == date(2026, 9, 8)
    assert prepare_data(resolved, plan, prepared.assets)


@pytest.mark.parametrize("value", [True, "125", None])
def test_nonnumeric_predictions_rejected(
    prepared: PreparedData, monkeypatch: pytest.MonkeyPatch, value: Any
) -> None:
    FakeProphet.instances = []
    FakeProphet.fail = False
    FakeProphet.value = value
    monkeypatch.setattr("portfolio_forecasting.forecasting.Prophet", FakeProphet)
    with pytest.raises(ForecastError):
        forecast_prices(prepared)


@pytest.mark.parametrize("kind", ["empty", "wrong_date", "missing_yhat", "multiple"])
def test_model_output_shape_and_target(
    prepared: PreparedData, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    class BadModel(FakeProphet):
        def predict(self, future: pd.DataFrame) -> pd.DataFrame:
            if kind == "empty":
                return pd.DataFrame()
            if kind == "missing_yhat":
                return future
            if kind == "multiple":
                return pd.concat([future, future]).assign(yhat=125.0)
            return future.assign(
                ds=pd.Timestamp(prepared.plan.forecast_target + timedelta(days=1)),
                yhat=125.0,
            )

    BadModel.fail = False
    monkeypatch.setattr("portfolio_forecasting.forecasting.Prophet", BadModel)
    with pytest.raises(ForecastError, match="unexpected target"):
        forecast_prices(prepared)


def test_source_version_change_blocks_replay(
    prepared: PreparedData, tmp_path: Path
) -> None:
    path = write_snapshot(prepared, tmp_path)
    payload = json.loads(path.read_bytes())
    payload["software"]["source_sha256"] = "different"
    changed = write_content(canonical_bytes(payload), tmp_path)
    assert read_snapshot(changed) == prepared
    with pytest.raises(ForecastError, match="captured source"):
        replay_forecast(changed, clock=lambda: NOW)


def test_cli_invalid_request_has_nonzero_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["portfolio_forecasting", "--tickers", "AMD", "AMD"]
    )
    assert main() == 1
    output = capsys.readouterr()
    assert output.out == "" and "unique" in output.err


def test_replay_cli_emits_complete_json(
    prepared: PreparedData,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_snapshot(prepared, tmp_path)
    monkeypatch.setattr("sys.argv", ["portfolio_forecasting", "--replay", str(path)])
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "complete" and output["replay"]
    assert len(output["assets"]) == 2
