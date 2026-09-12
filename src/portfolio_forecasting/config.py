"""Immutable request settings; no data retrieval, calendar prediction, or fitting."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib.resources import files
from typing import Literal
from zoneinfo import ZoneInfo

DEFAULT_TICKERS = (
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
EXCHANGE_TIMEZONE = "America/New_York"
RunMode = Literal["live", "retrospective"]


def _exchange_timezone() -> ZoneInfo:
    # Read the locked tzdata package, not the host's independently updated database.
    resource = files("tzdata.zoneinfo").joinpath(EXCHANGE_TIMEZONE)
    with resource.open("rb") as source:
        return ZoneInfo.from_file(source, key=EXCHANGE_TIMEZONE)


def _positive_number(value: object, name: str) -> None:
    valid = False
    if not isinstance(value, bool) and isinstance(value, (int, float)):
        try:
            valid = math.isfinite(value) and value > 0
        except OverflowError:
            pass
    if not valid:
        raise ValueError(f"{name} must be a finite positive number")


def _integer(value: object, name: str, minimum: int) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _date(value: object, name: str) -> None:
    if type(value) is not date:
        raise ValueError(f"{name} must be a date, not a datetime or string")


@dataclass(frozen=True, slots=True, kw_only=True)
class ForecastSettings:
    """Component choices and a history gate independent of the risk window."""

    yearly_seasonality: bool = True
    weekly_seasonality: bool = True
    daily_seasonality: bool = False
    holiday_effects: bool = True
    minimum_yearly_history_years: int = 2

    def __post_init__(self) -> None:
        for name in (
            "yearly_seasonality",
            "weekly_seasonality",
            "daily_seasonality",
            "holiday_effects",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if self.daily_seasonality:
            raise ValueError(
                "daily_seasonality is unsupported for daily close forecasts"
            )
        _integer(self.minimum_yearly_history_years, "minimum_yearly_history_years", 1)


@dataclass(frozen=True, slots=True, kw_only=True)
class AllocationSettings:
    """Fractional bounds and per-session mean-variance settings, without a solver."""

    risk_aversion: float = 5.0
    lower_bound: float = 0.05
    upper_bound: float = 1.0
    risk_window: int = 252

    def __post_init__(self) -> None:
        _positive_number(self.risk_aversion, "risk_aversion")
        _integer(self.risk_window, "risk_window", 2)
        for name in ("lower_bound", "upper_bound"):
            value = getattr(self, name)
            if type(value) not in (int, float):
                raise ValueError(f"{name} must be a finite fraction between 0 and 1")
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite fraction between 0 and 1")
        if self.lower_bound > self.upper_bound:
            raise ValueError("lower_bound must not exceed upper_bound")

    @property
    def required_price_observations(self) -> int:
        """A full return window needs one additional initial price."""
        return self.risk_window + 1

    def validate_universe_size(self, count: int) -> None:
        _integer(count, "asset count", 1)
        # Decimal interprets user-facing decimal bounds without hiding infeasibility
        # behind a solver tolerance (20 * 5% is feasible; 21 * 5% is not).
        if count * Decimal(str(self.lower_bound)) > 1:
            raise ValueError(
                f"infeasible lower_bound: {count} assets exceed full investment"
            )
        if count * Decimal(str(self.upper_bound)) < 1:
            raise ValueError(f"infeasible upper_bound: {count} assets cannot sum to 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class DataSettings:
    """Declared conventions and bounded retry policy; no provider is called."""

    price_basis: Literal["adjusted_close"] = "adjusted_close"
    currency: Literal["USD"] = "USD"
    calendar: Literal["XNYS"] = "XNYS"
    require_full_universe: bool = True
    download_attempts: int = 3
    request_timeout_seconds: float = 30.0
    retry_backoff_seconds: float = 1.0
    recent_history_days: int = 30

    def __post_init__(self) -> None:
        for name, expected in (
            ("price_basis", "adjusted_close"),
            ("currency", "USD"),
            ("calendar", "XNYS"),
        ):
            if getattr(self, name) != expected:
                raise ValueError(f"{name} currently supports only {expected}")
        if self.require_full_universe is not True:
            raise ValueError("require_full_universe must be True")
        _integer(self.download_attempts, "download_attempts", 1)
        if self.download_attempts > 3:
            raise ValueError("download_attempts must not exceed 3")
        _positive_number(self.request_timeout_seconds, "request_timeout_seconds")
        _positive_number(self.retry_backoff_seconds, "retry_backoff_seconds")
        _integer(self.recent_history_days, "recent_history_days", 1)


@dataclass(frozen=True, slots=True, kw_only=True)
class RunRequest:
    """Validate static choices immediately; resolve the clock at invocation time."""

    tickers: Sequence[str] = DEFAULT_TICKERS
    history_start: date = date(2024, 1, 1)
    history_end: date | None = None
    mode: RunMode = "live"
    scientific_revision: str = "1"
    forecast: ForecastSettings = field(default_factory=ForecastSettings)
    allocation: AllocationSettings = field(default_factory=AllocationSettings)
    data: DataSettings = field(default_factory=DataSettings)

    def __post_init__(self) -> None:
        if isinstance(self.tickers, (str, bytes)) or not isinstance(
            self.tickers, Sequence
        ):
            raise ValueError("tickers must be an ordered sequence of ticker strings")
        if not self.tickers:
            raise ValueError("tickers must not be empty")
        symbols = []
        for ticker in self.tickers:
            if not isinstance(ticker, str) or not re.fullmatch(
                r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*", ticker.strip().upper()
            ):
                raise ValueError("each ticker must be a nonempty equity symbol")
            symbols.append(ticker.strip().upper())
        if len(set(symbols)) != len(symbols):
            raise ValueError(
                "tickers must be unique after whitespace/case normalization"
            )
        object.__setattr__(self, "tickers", tuple(symbols))
        _date(self.history_start, "history_start")
        if self.history_end is not None:
            _date(self.history_end, "history_end")
            if self.history_start >= self.history_end:
                raise ValueError("history_start must precede the exclusive history_end")
        if self.mode not in ("live", "retrospective"):
            raise ValueError("mode must be live or retrospective")
        if not isinstance(self.scientific_revision, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", self.scientific_revision
        ):
            raise ValueError(
                "scientific_revision must be a 1–64 character revision label"
            )
        for name, expected_type in (
            ("forecast", ForecastSettings),
            ("allocation", AllocationSettings),
            ("data", DataSettings),
        ):
            if not isinstance(getattr(self, name), expected_type):
                raise ValueError(f"{name} must be a validated {expected_type.__name__}")
        self.allocation.validate_universe_size(len(self.tickers))
        if self.mode == "live":
            if self.allocation.risk_window < 252:
                raise ValueError("live requests require a risk_window of at least 252")
            if (
                self.forecast.yearly_seasonality
                and self.forecast.minimum_yearly_history_years < 2
            ):
                raise ValueError(
                    "live yearly seasonality requires at least 2 calendar years"
                )

    def resolve(
        self, *, clock: Callable[[], datetime] | None = None
    ) -> ResolvedRunRequest:
        """Capture one aware clock reading, without guessing market-session dates."""
        executed_at = datetime.now(UTC) if clock is None else clock()
        if not isinstance(executed_at, datetime) or executed_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return ResolvedRunRequest(request=self, executed_at=executed_at.astimezone(UTC))


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedRunRequest:
    """Execution-time request metadata; observed cutoff/target are established in M2."""

    request: RunRequest
    executed_at: datetime
    history_end: date = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.request, RunRequest):
            raise ValueError("request must be a validated RunRequest")
        if (
            not isinstance(self.executed_at, datetime)
            or self.executed_at.utcoffset() is None
        ):
            raise ValueError("executed_at must be a timezone-aware datetime")
        executed_at = self.executed_at.astimezone(UTC)
        object.__setattr__(self, "executed_at", executed_at)
        local_today = executed_at.astimezone(_exchange_timezone()).date()
        end = self.request.history_end or local_today
        if self.request.history_start >= end:
            raise ValueError(
                "history_start must precede the resolved exclusive history_end"
            )
        if end > local_today:
            raise ValueError(
                "history_end must not be after the exchange-local execution date"
            )
        if self.request.mode == "live" and end != local_today:
            raise ValueError("a past history_end requires retrospective mode")
        object.__setattr__(self, "history_end", end)

    def to_metadata(self) -> dict[str, object]:
        """Return detached JSON-compatible settings without publication credentials."""
        result = asdict(self.request)
        result["tickers"] = list(self.request.tickers)
        result["history_start"] = self.request.history_start.isoformat()
        result["requested_history_end"] = (
            self.request.history_end.isoformat() if self.request.history_end else None
        )
        result["history_end"] = self.history_end.isoformat()
        result["executed_at"] = self.executed_at.isoformat()
        result["exchange_timezone"] = EXCHANGE_TIMEZONE
        return result
