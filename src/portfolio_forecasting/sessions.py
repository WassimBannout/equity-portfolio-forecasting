"""XNYS sessions and known calendar features; no generic weekday targeting."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import exchange_calendars as xcals
import pandas as pd

from portfolio_forecasting.config import ResolvedRunRequest
from portfolio_forecasting.errors import ForecastError


@dataclass(frozen=True, slots=True)
class HolidayEvent:
    day: date
    name: str
    lower_window: int = -1
    upper_window: int = 1


@dataclass(frozen=True, slots=True)
class SessionPlan:
    observation_cutoff: date
    forecast_target: date
    cutoff_close: datetime
    target_open: datetime
    target_close: datetime
    sessions: tuple[date, ...]
    holidays: tuple[HolidayEvent, ...]


def exchange_calendar(start: date, end: date) -> Any:
    try:
        # Explicit bounds avoid the library's moving default history window.
        return xcals.get_calendar("XNYS", start=start.isoformat(), end=end.isoformat())
    except (ValueError, OverflowError) as error:
        raise ForecastError("calendar", "unsupported calendar range") from error


def holiday_events(
    calendar: Any, start: date, cutoff: date, target: date
) -> tuple[HolidayEvent, ...]:
    # Include events whose +/-1 calendar-day window intersects training OR target.
    left, right = start - timedelta(days=1), target + timedelta(days=1)
    regular = calendar.regular_holidays.holidays(left, right, return_name=True)
    events = {
        (day.date(), re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_"))
        for day, name in regular.items()
    }
    # Exceptional closures have no announcement timestamps in this library.
    # Conservatively exclude future exceptional events from model features.
    events.update(
        (day.date(), "exceptional_closure")
        for day in calendar.adhoc_holidays
        if left <= day.date() <= min(cutoff, right)
    )
    return tuple(HolidayEvent(day, name) for day, name in sorted(events))


def plan_sessions(resolved: ResolvedRunRequest) -> SessionPlan | None:
    request = resolved.request
    try:
        calendar = exchange_calendar(
            request.history_start - timedelta(days=32),
            resolved.history_end + timedelta(days=32),
        )
        end = pd.Timestamp(resolved.history_end)
        if request.mode == "live" and not calendar.is_session(end):
            return None
        cutoff = calendar.date_to_session(
            end - pd.Timedelta(days=1), direction="previous"
        )
        target = calendar.next_session(cutoff)
        sessions = tuple(
            day.date()
            for day in calendar.sessions_in_range(request.history_start, cutoff)
        )
        if not sessions:
            raise ForecastError(
                "calendar", "requested range contains no completed sessions"
            )
        plan = SessionPlan(
            observation_cutoff=cutoff.date(),
            forecast_target=target.date(),
            cutoff_close=calendar.session_close(cutoff).to_pydatetime().astimezone(UTC),
            target_open=calendar.session_open(target).to_pydatetime().astimezone(UTC),
            target_close=calendar.session_close(target).to_pydatetime().astimezone(UTC),
            sessions=sessions,
            holidays=holiday_events(calendar, sessions[0], cutoff.date(), target.date())
            if request.forecast.holiday_effects
            else (),
        )
        if plan.cutoff_close >= resolved.executed_at:
            raise ForecastError("calendar", "observation session has not completed")
        if request.mode == "live":
            if plan.forecast_target != resolved.history_end:
                raise ForecastError(
                    "calendar", "live target must be today's eligible session"
                )
            check_deadline(plan, resolved.executed_at)
        return plan
    except ForecastError:
        raise
    except (ValueError, OverflowError) as error:
        raise ForecastError(
            "calendar", "cannot resolve requested exchange sessions"
        ) from error


def check_deadline(plan: SessionPlan, now: datetime) -> None:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ForecastError("calendar", "deadline clock must be timezone-aware")
    if now >= plan.target_open:
        raise ForecastError(
            "calendar", "live forecast deadline elapsed at target session open"
        )
