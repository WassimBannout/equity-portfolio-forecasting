"""Configuration and clock contracts; all fixtures are offline and deterministic."""

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest

from portfolio_forecasting import (
    AllocationSettings,
    DataSettings,
    ForecastSettings,
    ResolvedRunRequest,
    RunRequest,
)

NOW = datetime(2026, 9, 12, 9, tzinfo=UTC)


def test_reference_request_and_json_metadata() -> None:
    request = RunRequest()
    result = request.resolve(clock=lambda: NOW)
    metadata = result.to_metadata()
    assert request.tickers == (
        "AMD",
        "MSFT",
        "AAPL",
        "TSLA",
        "AMZN",
        "NVDA",
        "META",
        "GOOG",
        "TSM",
        "JPM",
        "NFLX",
        "PLTR",
    )
    assert metadata["history_start"] == "2024-01-01"
    assert metadata["history_end"] == "2026-09-12"
    assert metadata["requested_history_end"] is None
    assert metadata["executed_at"] == "2026-09-12T09:00:00+00:00"
    assert metadata["exchange_timezone"] == "America/New_York"
    assert request.allocation == AllocationSettings(
        risk_window=252,
        risk_aversion=5,
        lower_bound=0.05,
        upper_bound=1,
    )
    assert request.allocation.required_price_observations == 253
    assert request.forecast.yearly_seasonality
    assert request.forecast.weekly_seasonality
    assert request.forecast.holiday_effects
    assert not request.forecast.daily_seasonality
    assert request.forecast.minimum_yearly_history_years == 2
    assert request.data.price_basis == "adjusted_close"
    assert request.data.currency == "USD"
    assert request.data.calendar == "XNYS"
    assert request.data.require_full_universe
    assert request.data.download_attempts == 3
    assert request.data.recent_history_days == 30
    assert json.loads(json.dumps(metadata, allow_nan=False)) == metadata
    assert "observation_cutoff" not in metadata
    assert "forecast_target" not in metadata


def test_tickers_preserve_order_and_detach_from_mutable_input() -> None:
    supplied = [" msft ", "aapl", "BRK-B"]
    request = RunRequest(tickers=supplied)
    supplied.append("TSLA")
    assert request.tickers == ("MSFT", "AAPL", "BRK-B")
    for record, attribute, value in (
        (request, "mode", "retrospective"),
        (request.allocation, "risk_window", 2),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(record, attribute, value)


@pytest.mark.parametrize(
    "tickers", [[], "AMD", {"AMD"}, [""], ["  "], [None], ["A A"], ["AMD", " amd "]]
)
def test_rejects_invalid_or_duplicate_universe(tickers: Any) -> None:
    with pytest.raises(ValueError, match="ticker"):
        RunRequest(tickers=tickers)


@pytest.mark.parametrize("count", [1, 12, 20])
def test_default_bounds_are_feasible_for_supported_asset_counts(count: int) -> None:
    request = RunRequest(tickers=tuple(f"T{i}" for i in range(count)))
    assert len(request.tickers) == count


def test_twenty_one_assets_fail_before_any_solver() -> None:
    with pytest.raises(ValueError, match="infeasible lower_bound: 21"):
        RunRequest(tickers=tuple(f"T{i}" for i in range(21)))


def test_upper_bound_feasibility_and_forced_single_asset() -> None:
    with pytest.raises(ValueError, match="infeasible upper_bound"):
        RunRequest(tickers=("AMD",), allocation=AllocationSettings(upper_bound=0.9))
    single = RunRequest(
        tickers=("AMD",), allocation=AllocationSettings(lower_bound=1, upper_bound=1)
    )
    assert single.allocation.lower_bound == single.allocation.upper_bound == 1
    with pytest.raises(ValueError, match="infeasible upper_bound"):
        RunRequest(allocation=AllocationSettings(upper_bound=0.08))


@pytest.mark.parametrize(
    "field,value",
    [
        ("risk_aversion", 0),
        ("risk_aversion", -1),
        ("risk_aversion", True),
        ("risk_aversion", "5"),
        ("risk_aversion", float("nan")),
        ("risk_aversion", float("inf")),
        ("risk_aversion", -float("inf")),
        ("risk_aversion", 10**400),
        ("lower_bound", 10**400),
        ("upper_bound", 10**400),
        ("lower_bound", -0.01),
        ("lower_bound", 1.01),
        ("lower_bound", float("nan")),
        ("lower_bound", True),
        ("upper_bound", float("inf")),
        ("upper_bound", -0.01),
        ("upper_bound", 1.01),
        ("upper_bound", "1"),
        ("risk_window", 1),
        ("risk_window", 252.0),
        ("risk_window", True),
    ],
)
def test_allocation_rejects_invalid_numerical_choices(field: str, value: Any) -> None:
    with pytest.raises(ValueError, match=field):
        AllocationSettings(**{field: value})


def test_reversed_bounds() -> None:
    with pytest.raises(ValueError, match="lower_bound must not exceed"):
        AllocationSettings(lower_bound=0.5, upper_bound=0.4)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"history_start": "2024-01-01"},
        {"history_start": NOW},
        {"history_end": "2026-09-12"},
        {"history_end": NOW},
        {"history_end": date(2024, 1, 1)},
        {"history_end": date(2023, 12, 31)},
        {"mode": "backtest"},
        {"scientific_revision": ""},
        {"scientific_revision": "secret\nvalue"},
        {"scientific_revision": "x" * 65},
        {"forecast": {}},
        {"allocation": {}},
        {"data": {}},
    ],
)
def test_request_rejects_invalid_dates_modes_revisions_and_nested_settings(
    kwargs: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        RunRequest(**kwargs)


def test_shorter_research_history_requires_explicit_retrospective_mode() -> None:
    short_risk = AllocationSettings(risk_window=20)
    with pytest.raises(ValueError, match="live requests require"):
        RunRequest(allocation=short_risk)
    retrospective = RunRequest(mode="retrospective", allocation=short_risk)
    assert retrospective.allocation.required_price_observations == 21
    assert (
        retrospective.resolve(clock=lambda: NOW).to_metadata()["mode"]
        == "retrospective"
    )


def test_annual_gate_is_independent_of_return_window() -> None:
    short_annual = ForecastSettings(minimum_yearly_history_years=1)
    with pytest.raises(ValueError, match="2 calendar years"):
        RunRequest(forecast=short_annual)
    research = RunRequest(mode="retrospective", forecast=short_annual)
    assert research.allocation.risk_window == 252
    assert research.forecast.minimum_yearly_history_years == 1
    no_yearly = RunRequest(
        forecast=ForecastSettings(
            yearly_seasonality=False, minimum_yearly_history_years=1
        )
    )
    assert no_yearly.allocation.risk_window == 252


@pytest.mark.parametrize(
    "kwargs",
    [
        {"yearly_seasonality": "false"},
        {"weekly_seasonality": 1},
        {"daily_seasonality": True},
        {"holiday_effects": None},
        {"minimum_yearly_history_years": 0},
        {"minimum_yearly_history_years": 1.5},
    ],
)
def test_invalid_forecast_settings(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ForecastSettings(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"price_basis": "raw_close"},
        {"currency": "EUR"},
        {"calendar": "weekdays"},
        {"require_full_universe": False},
        {"require_full_universe": 1},
        {"download_attempts": 0},
        {"download_attempts": 4},
        {"download_attempts": True},
        {"request_timeout_seconds": 0},
        {"request_timeout_seconds": float("inf")},
        {"retry_backoff_seconds": float("nan")},
        {"retry_backoff_seconds": -1},
        {"recent_history_days": 0},
        {"recent_history_days": 30.0},
    ],
)
def test_invalid_data_policies(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        DataSettings(**kwargs)


def test_same_request_resolves_again_across_exchange_midnight() -> None:
    request = RunRequest()
    times = iter(
        (datetime(2026, 9, 12, 3, 59, tzinfo=UTC), datetime(2026, 9, 12, 4, tzinfo=UTC))
    )
    calls = 0

    def clock() -> datetime:
        nonlocal calls
        calls += 1
        return next(times)

    assert request.resolve(clock=clock).history_end == date(2026, 9, 11)
    assert request.resolve(clock=clock).history_end == date(2026, 9, 12)
    assert calls == 2
    assert request.history_end is None


@pytest.mark.parametrize(
    "execution",
    [
        datetime(2026, 3, 8, 6, 59, tzinfo=UTC),
        datetime(2026, 3, 8, 7, tzinfo=UTC),
        datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
        datetime(2026, 11, 1, 6, 30, tzinfo=UTC),
    ],
)
def test_daylight_saving_changes_keep_market_date_meaning(execution: datetime) -> None:
    resolved = RunRequest().resolve(clock=lambda: execution)
    assert resolved.history_end == execution.date()


def test_clock_normalizes_to_utc_without_using_machine_local_date() -> None:
    execution = datetime(2026, 1, 1, 3, 30, tzinfo=timezone(timedelta(hours=3)))
    resolved = RunRequest().resolve(clock=lambda: execution)
    assert resolved.executed_at == datetime(2026, 1, 1, 0, 30, tzinfo=UTC)
    assert resolved.executed_at.tzinfo is UTC
    assert resolved.history_end == date(2025, 12, 31)
    assert resolved == RunRequest().resolve(clock=lambda: execution)


@pytest.mark.parametrize("execution", [datetime(2026, 9, 12), date(2026, 9, 12), None])
def test_invalid_clock(execution: Any) -> None:
    with pytest.raises(ValueError, match="timezone-aware datetime"):
        RunRequest().resolve(clock=lambda: execution)


def test_explicit_historical_end_is_retrospective_and_exclusive() -> None:
    end = date(2026, 9, 1)
    request = RunRequest(history_end=end)
    with pytest.raises(ValueError, match="retrospective mode"):
        request.resolve(clock=lambda: NOW)
    result = RunRequest(mode="retrospective", history_end=end).resolve(
        clock=lambda: NOW
    )
    assert result.history_end == end
    assert result.to_metadata()["requested_history_end"] == "2026-09-01"
    assert result.executed_at == NOW


@pytest.mark.parametrize("mode", ["live", "retrospective"])
def test_future_history_end_rejected(mode: Any) -> None:
    with pytest.raises(ValueError, match="must not be after"):
        RunRequest(mode=mode, history_end=date(2026, 9, 13)).resolve(clock=lambda: NOW)


def test_resolved_empty_range_rejected() -> None:
    with pytest.raises(ValueError, match="resolved exclusive history_end"):
        RunRequest(history_start=date(2026, 9, 12)).resolve(clock=lambda: NOW)


def test_resolved_record_cannot_bypass_clock_validation() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ResolvedRunRequest(request=RunRequest(), executed_at=datetime(2026, 9, 12))


def test_metadata_is_detached_and_does_not_load_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    result = RunRequest().resolve(clock=lambda: NOW)
    metadata = result.to_metadata()
    nested = metadata["data"]
    assert isinstance(nested, dict)
    nested["currency"] = "EUR"
    tickers = metadata["tickers"]
    assert isinstance(tickers, list)
    tickers.clear()
    assert result.request.data.currency == "USD"
    assert len(result.request.tickers) == 12
    monkeypatch.setenv("SUPABASE_KEY", "dummy-private-test-value")
    assert "dummy-private-test-value" not in json.dumps(result.to_metadata())
    assert "SUPABASE" not in json.dumps(result.to_metadata())
