import math
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest
from yfinance.exceptions import YFDataException, YFRateLimitError

from portfolio_forecasting import RunRequest
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.market_data import (
    Observation,
    PreparedData,
    YFinanceSource,
    history_options,
    normalize_history,
    prepare_data,
)
from tests.market_fixtures import NOW, metadata, synthetic_history


def frame(values: list[Any] | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Adj Close": [100.0, 102.0, 101.0] if values is None else values,
            "Close": [200.0, 204.0, 202.0],
        },
        index=pd.date_range("2026-09-02", periods=3, tz="America/New_York"),
    )


@pytest.mark.parametrize(
    "value", [0.0, -1.0, float("nan"), float("inf"), -float("inf"), True, "100", None]
)
def test_invalid_prices_fail_without_coercion(value: Any) -> None:
    with pytest.raises(ForecastError, match="price"):
        normalize_history("AMD", frame([100.0, value, 101.0]), metadata("AMD"), NOW)


@pytest.mark.parametrize(
    "mutation",
    [
        "empty",
        "missing_column",
        "duplicate_columns",
        "duplicate_dates",
        "reverse",
        "nat",
        "naive",
        "intraday",
        "string_index",
    ],
)
def test_malformed_frames(mutation: str) -> None:
    source = frame()
    if mutation == "empty":
        source = source.iloc[:0]
    elif mutation == "missing_column":
        source = source.drop(columns="Adj Close")
    elif mutation == "duplicate_columns":
        source.columns = ["Adj Close", "Adj Close"]
    elif mutation == "duplicate_dates":
        source.index = pd.DatetimeIndex(
            [source.index[0], source.index[0], source.index[2]]
        )
    elif mutation == "reverse":
        source = source.iloc[::-1]
    elif mutation == "nat":
        source.index = pd.DatetimeIndex([source.index[0], pd.NaT, source.index[2]])
    elif mutation == "naive":
        source.index = pd.DatetimeIndex(source.index).tz_localize(None)
    elif mutation == "intraday":
        source.index += pd.Timedelta(hours=1)
    elif mutation == "string_index":
        source.index = source.index.astype(str)
    before = source.copy(deep=True)
    with pytest.raises(ForecastError):
        normalize_history("AMD", source, metadata("AMD"), NOW)
    pd.testing.assert_frame_equal(source, before)


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "MSFT"),
        ("currency", "EUR"),
        ("instrumentType", "ETF"),
        ("exchangeName", "LSE"),
        ("exchangeTimezoneName", "UTC"),
        ("dataGranularity", "1h"),
        ("symbol", None),
    ],
)
def test_security_metadata_validation(field: str, value: Any) -> None:
    bad = metadata("AMD")
    bad[field] = value
    with pytest.raises(
        ForecastError, match=field if field != "exchangeName" else "exchange"
    ):
        normalize_history("AMD", frame(), bad, NOW)


def test_adjusted_prices_dates_and_inputs_preserved() -> None:
    source = frame()
    source.index = pd.DatetimeIndex(source.index).tz_convert("UTC")
    before = source.copy(deep=True)
    history = normalize_history("AMD", source, metadata("AMD"), NOW)
    assert [row.price for row in history.observations] == [100, 102, 101]
    assert [row.session for row in history.observations] == [
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    ]
    source.iloc[0, 0] = 900
    assert history.observations[0].price == 100
    assert before.iloc[0, 0] == 100


class Client:
    def __init__(self, results: list[object]):
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def history(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, pd.DataFrame)
        return result

    def get_history_metadata(self) -> dict[str, Any]:
        return metadata("AMD")


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError(),
        ConnectionError(),
        YFRateLimitError(),
        YFDataException("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***"),
    ],
)
def test_bounded_transient_retry_and_explicit_options(failure: Exception) -> None:
    client = Client([failure, failure, frame()])
    delays: list[float] = []
    provider = YFinanceSource(
        factory=lambda ticker: client, clock=lambda: NOW, sleeper=delays.append
    )
    resolved = RunRequest().resolve(clock=lambda: NOW)
    result = provider.fetch("AMD", resolved, run_id="fixture")
    assert result.attempts == 3 and delays == [1.0, 2.0]
    assert client.calls == [history_options(resolved)] * 3
    assert client.calls[0] == {
        "start": "2024-01-01",
        "end": "2026-09-08",
        "period": None,
        "interval": "1d",
        "prepost": False,
        "actions": False,
        "auto_adjust": False,
        "back_adjust": False,
        "repair": False,
        "keepna": True,
        "rounding": False,
        "timeout": 30.0,
        "raise_errors": True,
    }


def test_exhaustion_names_asset_and_stops_at_three() -> None:
    client = Client([TimeoutError()] * 4)
    provider = YFinanceSource(
        factory=lambda ticker: client, sleeper=lambda seconds: None
    )
    with pytest.raises(ForecastError, match=r"AMD.*3 attempt"):
        provider.fetch("AMD", RunRequest().resolve(clock=lambda: NOW), run_id="failure")
    assert len(client.calls) == 3


@pytest.mark.parametrize(
    "result",
    [ValueError("permanent"), pd.DataFrame(), frame([100.0, float("nan"), 101.0])],
)
def test_permanent_and_malformed_responses_not_retried(result: object) -> None:
    client = Client([result, frame()])
    provider = YFinanceSource(factory=lambda ticker: client, clock=lambda: NOW)
    with pytest.raises(ForecastError):
        provider.fetch("AMD", RunRequest().resolve(clock=lambda: NOW), run_id="bad")
    assert len(client.calls) == 1


def test_first_price_retained_returns_computed_after_alignment(
    prepared: PreparedData,
) -> None:
    assert len(prepared.returns) == len(prepared.plan.sessions) - 1
    assert prepared.assets[0].observations[0].price == 100
    assert prepared.returns[0] == pytest.approx(
        (100.2 / 100 - 1, 110.2 / 110 - 1), abs=1e-15
    )
    assert all(math.isfinite(value) for row in prepared.returns for value in row)
    reordered = prepare_data(
        prepared.resolved, prepared.plan, tuple(reversed(prepared.assets))
    )
    assert reordered == prepared
    assert (
        max(item.session for asset in prepared.assets for item in asset.observations)
        < prepared.plan.forecast_target
    )


@pytest.mark.parametrize(
    "kind",
    [
        "gap_one",
        "gap_both",
        "stale",
        "duplicate",
        "weekend",
        "future",
        "start_truncated",
        "extra_ticker",
        "missing_ticker",
        "duplicate_ticker",
    ],
)
def test_no_silent_intersection_filling_or_universe_changes(
    prepared: PreparedData, kind: str
) -> None:
    assets = list(prepared.assets)
    rows = assets[0].observations
    if kind.startswith("gap"):
        assets[0] = replace(assets[0], observations=rows[:3] + rows[4:])
        if kind == "gap_both":
            assets[1] = replace(
                assets[1],
                observations=assets[1].observations[:3] + assets[1].observations[4:],
            )
    elif kind == "stale":
        assets[0] = replace(assets[0], observations=rows[:-1])
    elif kind == "duplicate":
        assets[0] = replace(assets[0], observations=rows[:3] + rows[2:])
    elif kind == "weekend":
        assets[0] = replace(
            assets[0], observations=rows + (Observation(date(2026, 9, 5), 120.0),)
        )
    elif kind == "future":
        assets[0] = replace(
            assets[0],
            observations=rows + (Observation(prepared.plan.forecast_target, 120.0),),
        )
    elif kind == "start_truncated":
        assets[0] = replace(assets[0], observations=rows[1:])
    elif kind == "extra_ticker":
        assets.append(replace(assets[0], ticker="AAPL"))
    elif kind == "missing_ticker":
        assets.pop()
    elif kind == "duplicate_ticker":
        assets.append(assets[0])
    with pytest.raises(ForecastError):
        prepare_data(prepared.resolved, prepared.plan, tuple(assets))


def test_dated_recent_history_inclusive_boundary(prepared: PreparedData) -> None:
    request = replace(
        prepared.resolved.request,
        data=replace(prepared.resolved.request.data, recent_history_days=31),
    )
    resolved = request.resolve(clock=lambda: NOW)
    data = prepare_data(resolved, prepared.plan, prepared.assets)
    recent = data.recent_history("AMD")
    assert recent[0].session == data.plan.observation_cutoff - timedelta(days=31)
    assert recent[-1] == data.assets[0].observations[-1]


def test_one_price_and_short_risk_history_fail(prepared: PreparedData) -> None:
    from portfolio_forecasting.sessions import plan_sessions

    request = replace(prepared.resolved.request, history_start=date(2026, 9, 4))
    resolved = request.resolve(clock=lambda: NOW)
    plan = plan_sessions(resolved)
    assert plan is not None
    with pytest.raises(ForecastError, match="requires 3 prices"):
        prepare_data(
            resolved,
            plan,
            tuple(
                synthetic_history(ticker, plan.sessions) for ticker in request.tickers
            ),
        )


def test_annual_gate_separate_from_risk_gate(prepared: PreparedData) -> None:
    request = replace(
        prepared.resolved.request,
        forecast=replace(prepared.resolved.request.forecast, yearly_seasonality=True),
    )
    with pytest.raises(ForecastError, match="yearly seasonality"):
        prepare_data(request.resolve(clock=lambda: NOW), prepared.plan, prepared.assets)


def test_nonfinite_return_and_unavailable_retrieval_rejected(
    prepared: PreparedData,
) -> None:
    asset = prepared.assets[0]
    rows = (
        replace(asset.observations[0], price=1e-300),
        replace(asset.observations[1], price=1e300),
        *asset.observations[2:],
    )
    with pytest.raises(ForecastError, match="returns must be finite"):
        prepare_data(
            prepared.resolved,
            prepared.plan,
            (replace(asset, observations=rows), prepared.assets[1]),
        )
    with pytest.raises(ForecastError, match="retrieval"):
        prepare_data(
            prepared.resolved,
            prepared.plan,
            (
                replace(asset, retrieved_at=datetime(2026, 1, 1, tzinfo=UTC)),
                prepared.assets[1],
            ),
        )
