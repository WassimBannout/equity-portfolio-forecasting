from datetime import UTC, date, datetime, timedelta, timezone
from functools import partial

import pandas as pd
import pytest

from portfolio_forecasting import RunRequest
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.sessions import (
    exchange_calendar,
    holiday_events,
    plan_sessions,
)


@pytest.mark.parametrize(
    "end,cutoff,target",
    [
        ("2026-09-14", "2026-09-11", "2026-09-14"),
        ("2026-09-08", "2026-09-04", "2026-09-08"),
        ("2026-01-02", "2025-12-31", "2026-01-02"),
        ("2026-04-06", "2026-04-02", "2026-04-06"),
    ],
)
def test_next_real_session(end: str, cutoff: str, target: str) -> None:
    resolved = RunRequest().resolve(
        clock=lambda: datetime.fromisoformat(end + "T09:00:00+00:00")
    )
    plan = plan_sessions(resolved)
    assert plan is not None
    assert plan.observation_cutoff == date.fromisoformat(cutoff)
    assert plan.forecast_target == date.fromisoformat(target)
    assert (
        plan.cutoff_close < resolved.executed_at < plan.target_open < plan.target_close
    )


@pytest.mark.parametrize(
    "day", ["2026-09-05", "2026-09-06", "2026-09-07", "2026-01-01", "2026-04-03"]
)
def test_closed_live_day_is_noop(day: str) -> None:
    resolved = RunRequest().resolve(
        clock=lambda: datetime.fromisoformat(day + "T09:00:00+00:00")
    )
    assert plan_sessions(resolved) is None


@pytest.mark.parametrize(
    "day,hour",
    [("2026-03-06", 14), ("2026-03-09", 13), ("2026-10-30", 13), ("2026-11-02", 14)],
)
def test_dst_open_deadline(day: str, hour: int) -> None:
    instant = datetime.fromisoformat(day).replace(hour=hour, minute=30, tzinfo=UTC)
    before = RunRequest().resolve(clock=lambda: instant - timedelta(microseconds=1))
    plan = plan_sessions(before)
    assert plan is not None and plan.target_open == instant
    for late in (instant, instant + timedelta(hours=9)):
        with pytest.raises(ForecastError, match="deadline"):
            plan_sessions(
                RunRequest().resolve(clock=partial(lambda value: value, late))
            )


def test_execution_timezone_and_early_close() -> None:
    instant = datetime(2026, 11, 27, 12, tzinfo=timezone(timedelta(hours=3)))
    plan = plan_sessions(RunRequest().resolve(clock=lambda: instant))
    assert plan is not None
    assert plan.forecast_target == date(2026, 11, 27)
    assert plan.target_close == datetime(2026, 11, 27, 18, tzinfo=UTC)


def test_retrospective_weekend_uses_next_session_without_claiming_live() -> None:
    request = RunRequest(history_end=date(2026, 9, 5), mode="retrospective")
    plan = plan_sessions(
        request.resolve(clock=lambda: datetime(2026, 9, 12, 9, tzinfo=UTC))
    )
    assert plan is not None
    assert plan.observation_cutoff == date(2026, 9, 4)
    assert plan.forecast_target == date(2026, 9, 8)


def test_empty_session_range_rejected() -> None:
    request = RunRequest(
        history_start=date(2026, 9, 5),
        history_end=date(2026, 9, 7),
        mode="retrospective",
    )
    with pytest.raises(ForecastError, match="calendar"):
        plan_sessions(
            request.resolve(clock=lambda: datetime(2026, 9, 8, 9, tzinfo=UTC))
        )


def test_future_holiday_window_survives_cutoff_and_year_boundary() -> None:
    calendar = exchange_calendar(date(2024, 1, 1), date(2027, 1, 5))
    events = holiday_events(
        calendar, date(2024, 1, 2), date(2026, 12, 30), date(2026, 12, 31)
    )
    future = next(event for event in events if event.day == date(2027, 1, 1))
    assert future.name == "new_year_s_day"
    assert future.lower_window == -1 and future.upper_window == 1
    assert future.day + timedelta(days=future.lower_window) == date(2026, 12, 31)
    assert len({(event.day, event.name) for event in events}) == len(events)
    assert list(events) == sorted(events, key=lambda event: (event.day, event.name))
    # Unknown-future exceptional closure features are excluded conservatively.
    earlier = holiday_events(
        calendar, date(2024, 1, 2), date(2025, 1, 7), date(2025, 1, 8)
    )
    assert not any(event.day == date(2025, 1, 9) for event in earlier)


def test_future_event_generates_real_prophet_target_feature() -> None:
    from prophet import Prophet

    calendar = exchange_calendar(date(2024, 1, 1), date(2027, 1, 5))
    events = holiday_events(
        calendar, date(2024, 1, 2), date(2026, 12, 30), date(2026, 12, 31)
    )
    holidays = pd.DataFrame(
        [
            {
                "ds": pd.Timestamp(event.day),
                "holiday": event.name,
                "lower_window": event.lower_window,
                "upper_window": event.upper_window,
            }
            for event in events
        ]
    )
    model = Prophet(holidays=holidays)
    features, _, _ = model.make_holiday_features(
        pd.Series(pd.to_datetime(["2026-12-31"])), holidays
    )
    columns = [
        column
        for column in features
        if str(column).startswith("new_year_s_day_delim_-")
    ]
    assert columns and features[columns].iloc[0].sum() == 1
