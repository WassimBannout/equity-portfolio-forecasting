"""Explicit yfinance adapter and immutable, consecutive observed price panels."""

from __future__ import annotations

import logging
import math
import time
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from numbers import Real
from typing import Any, Protocol

import pandas as pd
import yfinance as yf
from yfinance import _http
from yfinance.exceptions import YFDataException, YFRateLimitError

from portfolio_forecasting.config import EXCHANGE_TIMEZONE, ResolvedRunRequest
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.sessions import SessionPlan, plan_sessions

LOGGER = logging.getLogger(__name__)
METADATA_FIELDS = (
    "symbol",
    "currency",
    "instrumentType",
    "exchangeName",
    "exchangeTimezoneName",
    "dataGranularity",
)
# exchange_calendars maps NASDAQ/XNAS to its XNYS session calendar.
SUPPORTED_EXCHANGES = frozenset({"NYQ", "NMS", "NGM", "NCM"})


def utc_now() -> datetime:
    return datetime.now(UTC)


def aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ForecastError("data", "retrieval clock must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Observation:
    session: date
    price: float

    def __post_init__(self) -> None:
        if type(self.session) is not date:
            raise ForecastError("data", "observation session must be a date")
        if isinstance(self.price, bool) or not isinstance(self.price, Real):
            raise ForecastError("data", "price must be a finite positive number")
        try:
            value = float(self.price)
        except OverflowError as error:
            raise ForecastError("data", "price must be finite") from error
        if not math.isfinite(value) or value <= 0:
            raise ForecastError("data", "price must be finite and positive")
        object.__setattr__(self, "price", value)


@dataclass(frozen=True, slots=True)
class AssetHistory:
    ticker: str
    observations: tuple[Observation, ...]
    metadata: tuple[tuple[str, str], ...]
    retrieved_at: datetime
    attempts: int = 1
    provider: str = "yfinance"

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(
            self, "metadata", tuple(tuple(item) for item in self.metadata)
        )
        object.__setattr__(self, "retrieved_at", aware_utc(self.retrieved_at))
        if type(self.attempts) is not int or not 1 <= self.attempts <= 3:
            raise ForecastError(
                "data", "invalid download attempt count", ticker=self.ticker
            )


@dataclass(frozen=True, slots=True)
class PreparedData:
    resolved: ResolvedRunRequest
    plan: SessionPlan
    assets: tuple[AssetHistory, ...]
    # Rows have dates plan.sessions[1:], columns retain request ticker order.
    returns: tuple[tuple[float, ...], ...]

    def recent_history(self, ticker: str) -> tuple[Observation, ...]:
        start = self.plan.observation_cutoff - timedelta(
            days=self.resolved.request.data.recent_history_days
        )
        asset = next(asset for asset in self.assets if asset.ticker == ticker)
        return tuple(item for item in asset.observations if item.session >= start)


class MarketDataSource(Protocol):
    def fetch(
        self, ticker: str, resolved: ResolvedRunRequest, *, run_id: str
    ) -> AssetHistory: ...


class HistoryClient(Protocol):
    def history(self, **kwargs: Any) -> pd.DataFrame: ...
    def get_history_metadata(self) -> Mapping[str, Any]: ...


def history_options(resolved: ResolvedRunRequest) -> dict[str, Any]:
    return {
        "start": resolved.request.history_start.isoformat(),
        "end": resolved.history_end.isoformat(),
        "period": None,
        "interval": "1d",
        "prepost": False,
        "actions": False,
        "auto_adjust": False,
        "back_adjust": False,
        "repair": False,
        "keepna": True,
        "rounding": False,
        "timeout": resolved.request.data.request_timeout_seconds,
        "raise_errors": True,
    }


def validate_metadata(
    ticker: str, metadata: Mapping[str, object]
) -> tuple[tuple[str, str], ...]:
    expected = {
        "symbol": ticker,
        "currency": "USD",
        "instrumentType": "EQUITY",
        "exchangeTimezoneName": EXCHANGE_TIMEZONE,
        "dataGranularity": "1d",
    }
    for name, value in expected.items():
        if metadata.get(name) != value:
            raise ForecastError(
                "data", f"missing or incompatible {name}", ticker=ticker
            )
    exchange = metadata.get("exchangeName")
    if not isinstance(exchange, str) or exchange not in SUPPORTED_EXCHANGES:
        raise ForecastError(
            "data", "unsupported listing exchange for XNYS sessions", ticker=ticker
        )
    return tuple((name, str(metadata[name])) for name in METADATA_FIELDS)


def normalize_history(
    ticker: str,
    frame: pd.DataFrame,
    metadata: Mapping[str, object],
    retrieved_at: datetime,
    *,
    attempts: int = 1,
) -> AssetHistory:
    checked_metadata = validate_metadata(ticker, metadata)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ForecastError("data", "empty price response", ticker=ticker)
    if not frame.columns.is_unique or "Adj Close" not in frame.columns:
        raise ForecastError(
            "data", "missing or ambiguous Adj Close field", ticker=ticker
        )
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.hasnans:
        raise ForecastError("data", "expected dated daily observations", ticker=ticker)
    if frame.index.tz is None:
        raise ForecastError(
            "data", "provider dates must carry an exchange timezone", ticker=ticker
        )
    local = frame.index.tz_convert(EXCHANGE_TIMEZONE)
    if not (local == local.normalize()).all():
        raise ForecastError(
            "data",
            "daily observations must be exchange-local midnight labels",
            ticker=ticker,
        )
    dates = tuple(day.date() for day in local)
    if len(set(dates)) != len(dates):
        raise ForecastError("data", "duplicate observation sessions", ticker=ticker)
    if dates != tuple(sorted(dates)):
        raise ForecastError(
            "data", "observations are not in chronological order", ticker=ticker
        )
    try:
        observations = tuple(
            Observation(day, value)
            for day, value in zip(dates, frame["Adj Close"].tolist(), strict=True)
        )
    except ForecastError as error:
        raise ForecastError("data", str(error), ticker=ticker) from error
    return AssetHistory(ticker, observations, checked_metadata, retrieved_at, attempts)


def _transient(error: Exception) -> bool:
    if type(error) is YFDataException and "YAHOO! FINANCE IS CURRENTLY DOWN" in str(
        error
    ):
        return True
    if isinstance(
        error,
        (
            TimeoutError,
            ConnectionError,
            YFRateLimitError,
            _http.requests.exceptions.Timeout,
            _http.requests.exceptions.ConnectionError,
        ),
    ):
        return True
    if isinstance(error, _http.HTTPError):
        status = getattr(getattr(error, "response", None), "status_code", None)
        return isinstance(status, int) and (status == 429 or 500 <= status <= 599)
    return False


class YFinanceSource:
    def __init__(
        self,
        *,
        factory: Callable[[str], HistoryClient] = yf.Ticker,
        clock: Callable[[], datetime] = utc_now,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self._factory, self._clock, self._sleep = factory, clock, sleeper

    def fetch(
        self, ticker: str, resolved: ResolvedRunRequest, *, run_id: str
    ) -> AssetHistory:
        settings = resolved.request.data
        for attempt in range(1, settings.download_attempts + 1):
            try:
                client = self._factory(ticker)
                # Per-call errors avoid changing yfinance's process-global config.
                # Only this pinned, understood deprecation is filtered.
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="^'raise_errors' deprecated",
                        category=DeprecationWarning,
                    )
                    frame = client.history(**history_options(resolved))
                source_metadata = client.get_history_metadata()
                # Do not materialize lazy tradingPeriods (an extra intraday fetch).
                metadata = {name: source_metadata.get(name) for name in METADATA_FIELDS}
            except Exception as error:
                retry = _transient(error) and attempt < settings.download_attempts
                LOGGER.warning(
                    "run=%s stage=download ticker=%s attempt=%d error=%s retry=%s",
                    run_id,
                    ticker,
                    attempt,
                    type(error).__name__,
                    retry,
                )
                if not retry:
                    raise ForecastError(
                        "download",
                        f"provider failed after {attempt} attempt(s): "
                        f"{type(error).__name__}",
                        ticker=ticker,
                    ) from error
                self._sleep(
                    min(settings.retry_backoff_seconds * 2 ** (attempt - 1), 30.0)
                )
                continue
            # Malformed/empty data are permanent validation failures, never retried.
            return normalize_history(
                ticker, frame, metadata, self._clock(), attempts=attempt
            )
        raise AssertionError("validated attempt count must be positive")


def prepare_data(
    resolved: ResolvedRunRequest, plan: SessionPlan, histories: tuple[AssetHistory, ...]
) -> PreparedData:
    if plan_sessions(resolved) != plan:
        raise ForecastError("data", "session plan differs from the resolved request")
    tickers = tuple(asset.ticker for asset in histories)
    expected_tickers = tuple(resolved.request.tickers)
    if len(set(tickers)) != len(tickers) or set(tickers) != set(expected_tickers):
        raise ForecastError(
            "data", "histories must match the complete requested universe"
        )
    assets_by_ticker = {asset.ticker: asset for asset in histories}
    assets = tuple(assets_by_ticker[ticker] for ticker in expected_tickers)
    required = resolved.request.allocation.required_price_observations
    if (
        not plan.sessions
        or plan.sessions[-1] != plan.observation_cutoff
        or plan.forecast_target <= plan.observation_cutoff
    ):
        raise ForecastError("data", "invalid cutoff/target session plan")
    for asset in assets:
        validate_metadata(asset.ticker, dict(asset.metadata))
        if asset.retrieved_at < plan.cutoff_close:
            raise ForecastError(
                "data",
                "retrieval precedes observation availability",
                ticker=asset.ticker,
            )
        dates = tuple(item.session for item in asset.observations)
        if not dates:
            raise ForecastError("data", "empty observed history", ticker=asset.ticker)
        if dates[-1] < plan.observation_cutoff:
            raise ForecastError(
                "data",
                f"stale history; expected cutoff {plan.observation_cutoff}",
                ticker=asset.ticker,
            )
        if dates != plan.sessions:
            raise ForecastError(
                "data",
                "history must contain every requested session exactly once in order; "
                "gaps, extra/future dates and truncation are rejected",
                ticker=asset.ticker,
            )
        if len(dates) < required:
            raise ForecastError(
                "data",
                f"requires {required} prices for {required - 1} returns; "
                f"received {len(dates)}",
                ticker=asset.ticker,
            )
        forecast = resolved.request.forecast
        if forecast.yearly_seasonality:
            cutoff = plan.observation_cutoff
            if forecast.minimum_yearly_history_years >= cutoff.year:
                raise ForecastError(
                    "data",
                    "yearly history gate exceeds available dates",
                    ticker=asset.ticker,
                )
            try:
                boundary = cutoff.replace(
                    year=cutoff.year - forecast.minimum_yearly_history_years
                )
            except ValueError:
                boundary = cutoff.replace(
                    year=cutoff.year - forecast.minimum_yearly_history_years, day=28
                )
            if dates[0] > boundary:
                raise ForecastError(
                    "data",
                    "yearly seasonality requires "
                    f"{forecast.minimum_yearly_history_years} calendar years "
                    "of observed history",
                    ticker=asset.ticker,
                )
    returns = tuple(
        tuple(
            asset.observations[i].price / asset.observations[i - 1].price - 1.0
            for asset in assets
        )
        for i in range(1, len(plan.sessions))
    )
    if any(not math.isfinite(value) for row in returns for value in row):
        raise ForecastError("data", "observed simple returns must be finite")
    return PreparedData(resolved, plan, assets, returns)
