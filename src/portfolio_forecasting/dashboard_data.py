"""Read-only presentation contracts for the published M4 database functions."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from portfolio_forecasting.config import (
    AllocationSettings,
    DataSettings,
    ForecastSettings,
)
from portfolio_forecasting.sessions import exchange_calendar
from portfolio_forecasting.store_contract import (
    StoreError,
    hash_value,
    iso_date,
    iso_time,
    number,
    object_value,
    validate_published_run,
)
from portfolio_forecasting.supabase_store import StoreCredentials, SupabaseStore

PAGE_SIZE = 25
CACHE_SECONDS = 300
READ_FUNCTIONS = frozenset({"pf_runs", "pf_run", "pf_history"})
Query = Callable[[str, dict[str, Any]], Any]


class BadRecord(ValueError):
    """A response cannot be presented as valid scientific data."""


class Unavailable(ValueError):
    """The read service or its reader credentials are unavailable."""


class Reader:
    """Only named public reads; reject writer/admin roles before fetching data."""

    def __init__(self, store: SupabaseStore) -> None:
        self._store = store

    def query(self, function: str, arguments: dict[str, Any]) -> Any:
        if function not in READ_FUNCTIONS:
            raise Unavailable("Unsupported dashboard operation")
        try:
            access = object_value(self._store.rpc("pf_access", {}), "reader access")
            if (
                access.get("role") not in ("anon", "authenticated")
                or access.get("schema_version") != 1
            ):
                raise Unavailable("A restricted reader credential is required")
            return self._store.rpc(function, arguments)
        except StoreError as error:
            if str(error) in (
                "malformed storage JSON response",
                "nonfinite storage JSON value",
            ):
                raise BadRecord("Invalid storage response") from None
            raise Unavailable("Published results could not be retrieved") from None


def environment_credentials() -> StoreCredentials:
    try:
        return StoreCredentials.from_environment()
    except ValueError:
        raise Unavailable("Configure a valid read-only database connection") from None


def _symbol(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*", value
    ):
        raise BadRecord("Invalid ticker")
    return value


def _revision(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value
    ):
        raise BadRecord("Missing configuration revision")
    return value


@dataclass(frozen=True)
class Summary:
    run_id: str
    target: date
    cutoff: date
    executed_at: datetime
    published_at: datetime
    universe: tuple[str, ...]
    revision: str
    mode: str

    @property
    def order(self) -> tuple[date, datetime, str]:
        return self.target, self.published_at, self.run_id

    @property
    def cursor(self) -> dict[str, str]:
        return {
            "target": self.target.isoformat(),
            "published_at": self.published_at.isoformat(),
            "run_id": self.run_id,
        }


def summary(value: object) -> Summary:
    row = object_value(value, "run summary")
    universe = row["universe"]
    if not isinstance(universe, list) or not universe:
        raise BadRecord("Missing universe")
    symbols = tuple(_symbol(item) for item in universe)
    result = Summary(
        str(UUID(row["run_id"])),
        iso_date(row["target"]),
        iso_date(row["observation_cutoff"]),
        iso_time(row["executed_at"]),
        iso_time(row["published_at"]),
        symbols,
        _revision(row["scientific_revision"]),
        row["mode"],
    )
    if (
        symbols != tuple(sorted(set(symbols)))
        or result.cutoff >= result.target
        or result.executed_at > result.published_at
        or result.mode not in ("live", "retrospective")
    ):
        raise BadRecord("Invalid run summary")
    return result


@dataclass(frozen=True)
class Asset:
    ticker: str
    observed: float
    predicted: float
    predicted_return: float
    weight: float
    history: tuple[tuple[date, float], ...]
    outcome_state: str
    actual: float | None
    outcome_observed_at: datetime | None


def asset_record(value: object, header: Summary) -> Asset:
    row = object_value(value, "asset")
    ticker = _symbol(row["ticker"])
    observed = number(row["observed_price"], "observed price", positive=True)
    predicted = number(row["predicted_price"], "prediction", positive=True)
    forecast_return = number(row["predicted_return"], "forecast return")
    weight = number(row["weight"], "allocation")
    number(forecast_return * 100, "display forecast percentage")
    if (
        ticker not in header.universe
        or not 0 <= weight <= 1
        or not math.isclose(
            forecast_return, predicted / observed - 1, rel_tol=1e-10, abs_tol=1e-12
        )
    ):
        raise BadRecord("Invalid asset output")
    if not isinstance(row["recent_history"], list) or not row["recent_history"]:
        raise BadRecord("Missing dated observations")
    history = tuple(
        (iso_date(item["session"]), number(item["price"], "history", positive=True))
        for item in row["recent_history"]
    )
    dates = [item[0] for item in history]
    if dates != sorted(set(dates)) or history[-1] != (header.cutoff, observed):
        raise BadRecord("Invalid dated observations")
    model = object_value(row["model"], "model settings")
    if not object_value(model["constructor"], "constructor") or not object_value(
        model["fit"], "fit"
    ):
        raise BadRecord("Missing model settings")
    outcome = row["outcome"]
    state, actual, observed_at = "pending", None, None
    if outcome is not None:
        outcome = object_value(outcome, "outcome")
        state = outcome["state"]
        if iso_date(outcome["target"]) != header.target:
            raise BadRecord("Outcome does not match forecast target")
        observed_at = iso_time(outcome["observed_at"])
        hash_value(outcome["source_sha256"])
        if (
            outcome["basis_policy"] != "all_overlap_unchanged_v1"
            or not isinstance(outcome["reason"], str)
            or not outcome["reason"]
        ):
            raise BadRecord("Missing outcome basis provenance")
        if state == "matched":
            actual = number(outcome["actual_price"], "actual", positive=True)
        elif (
            state not in ("pending", "incompatible")
            or outcome["actual_price"] is not None
        ):
            raise BadRecord("Invalid unresolved outcome")
    return Asset(
        ticker,
        observed,
        predicted,
        forecast_return,
        weight,
        history,
        state,
        actual,
        observed_at,
    )


@dataclass(frozen=True)
class Run:
    header: Summary
    assets: tuple[Asset, ...]
    document: dict[str, Any]


def published_run(value: object, selected: Summary) -> Run:
    try:
        row = validate_published_run(value)
        identity = row["identity"]
        header = summary(
            {
                **row,
                "target": identity["forecast_target"],
                "observation_cutoff": identity["observation_cutoff"],
                "universe": identity["universe"],
                "scientific_revision": identity["scientific_revision"],
                "mode": identity["mode"],
            }
        )
        if header != selected:
            raise BadRecord("Selected run and complete response disagree")
        allocation = AllocationSettings(**identity["allocation"])
        allocation.validate_universe_size(len(header.universe))
        data = DataSettings(**identity["data"])
        ForecastSettings(**identity["forecast"])
        hash_value(identity["software_revision"])
        hash_value(identity["lock_sha256"])
        software = row["scientific_payload"]["software"]
        if not software["packages"]["prophet"] or not software["python"]:
            raise BadRecord("Missing model version")
        assets = tuple(asset_record(item, header) for item in row["assets"])
        for asset in assets:
            if asset.history[0][0] < header.cutoff - timedelta(
                days=data.recent_history_days
            ):
                raise BadRecord("Recent observations exceed recorded window")
            if asset.actual is not None and (
                asset.outcome_observed_at is None
                or asset.outcome_observed_at < iso_time(row["target_close"])
            ):
                raise BadRecord("Outcome was retrieved before target close")
        for item in row["input_provenance"]["assets"]:
            if dict(item["metadata"])["currency"] != "USD":
                raise BadRecord("Unsupported price currency")
        return Run(header, assets, row)
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError):
        raise BadRecord("Invalid or incomplete published run") from None


@dataclass(frozen=True)
class HistoryEntry:
    header: Summary
    asset: Asset


@dataclass(frozen=True)
class Page:
    summaries: tuple[Summary, ...]
    history: tuple[HistoryEntry, ...]
    as_of: str
    next_cursor: dict[str, Any] | None


def _cursor_order(value: object) -> tuple[date, datetime, str]:
    row = object_value(value, "cursor")
    return (
        iso_date(row["target"]),
        iso_time(row["published_at"]),
        str(UUID(row["run_id"])),
    )


def read_page(value: object, arguments: dict[str, Any]) -> Page:
    try:
        row = object_value(value, "page")
        watermark = iso_time(row["as_of"])
        requested_watermark = arguments.get("p_as_of")
        if requested_watermark is not None and watermark != iso_time(
            requested_watermark
        ):
            raise BadRecord("Page watermark changed")
        limit = arguments["p_limit"]
        items = row["items"]
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or not isinstance(items, list)
            or len(items) > limit
        ):
            raise BadRecord("Invalid page size")
        headers = tuple(summary(item) for item in items)
        orders = [item.order for item in headers]
        if (
            orders != sorted(set(orders), reverse=True)
            or len({item.run_id for item in headers}) != len(headers)
            or any(item.published_at > watermark for item in headers)
        ):
            raise BadRecord("Invalid page ordering or membership")
        cursor = arguments.get("p_cursor")
        if cursor is not None and any(item >= _cursor_order(cursor) for item in orders):
            raise BadRecord("Page does not progress")
        next_cursor = row["next_cursor"]
        if next_cursor is not None and (
            len(items) != limit or _cursor_order(next_cursor) != orders[-1]
        ):
            raise BadRecord("Invalid next page cursor")
        history: tuple[HistoryEntry, ...] = ()
        if "p_ticker" in arguments:
            start, end = iso_date(arguments["p_start"]), iso_date(arguments["p_end"])
            if (
                start > end
                or row["requested_start"] != start.isoformat()
                or row["requested_end"] != end.isoformat()
            ):
                raise BadRecord("History coverage differs from request")
            history = tuple(
                HistoryEntry(header, asset_record(item["asset"], header))
                for header, item in zip(headers, items, strict=True)
            )
            if any(
                item.asset.ticker != arguments["p_ticker"]
                or not start <= item.header.target <= end
                for item in history
            ):
                raise BadRecord("History membership or dates disagree")
        return Page(headers, history, row["as_of"], next_cursor)
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError):
        raise BadRecord("Invalid historical page") from None


def price(value: float | None) -> str:
    return "Unavailable" if value is None else f"${number(value, 'price'):,.2f}"


def percent(value: float) -> str:
    number(number(value, "fraction") * 100, "display percentage")
    return f"{number(value, 'fraction'):.2%}"


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def error_rows(entries: tuple[HistoryEntry, ...]) -> list[dict[str, Any]]:
    rows = []
    for entry in entries:
        item = entry.asset
        error = None if item.actual is None else item.actual - item.predicted
        percentage = None if error is None else error / item.predicted
        for value in (error, percentage):
            if value is not None:
                number(value, "error")
        rows.append(
            {
                "Target session": entry.header.target.isoformat(),
                "Observation cutoff": entry.header.cutoff.isoformat(),
                "Run timestamp (UTC)": timestamp(entry.header.executed_at),
                "Run ID": entry.header.run_id,
                "Revision": entry.header.revision,
                "Mode": entry.header.mode,
                "Predicted": price(item.predicted),
                "Actual": price(item.actual),
                "Outcome": item.outcome_state,
                "Signed error (actual − predicted)": price(error),
                "Absolute error": price(None if error is None else abs(error)),
                "Error / predicted": "Unavailable"
                if percentage is None
                else percent(percentage),
            }
        )
    return rows


def aggregate_errors(
    entries: tuple[HistoryEntry, ...],
) -> dict[str, float | int | None]:
    pairs = [entry.asset for entry in entries if entry.asset.actual is not None]
    if not pairs:
        return {
            "count": 0,
            "mae": None,
            "rmse": None,
            "baseline_mae": None,
            "ratio": None,
        }
    errors = [
        abs(item.actual - item.predicted) for item in pairs if item.actual is not None
    ]
    baseline = [
        abs(item.actual - item.observed) for item in pairs if item.actual is not None
    ]
    count = len(errors)
    mae = math.fsum(item / count for item in errors)
    base = math.fsum(item / count for item in baseline)
    result = {
        "count": count,
        "mae": mae,
        "rmse": math.hypot(*(item / math.sqrt(count) for item in errors)),
        "baseline_mae": base,
        "ratio": mae / base if base > 0 else None,
    }
    for value in result.values():
        if value is not None:
            number(value, "aggregate error")
    return result


def chart_range(values: list[float]) -> tuple[float, float]:
    if not values:
        raise BadRecord("No chart values")
    try:
        values = [number(item, "chart price", positive=True) for item in values]
        low, high = min(values), max(values)
        padding = max((high - low) * 0.2, high * 0.05, 0.01)
        lower, upper = max(0.0, low - padding), high + padding
        if not math.isfinite(upper) or lower >= upper:
            raise BadRecord("Unsupported chart range")
        # Match the USD slider's cent precision, expanding rather than truncating.
        return math.floor(lower * 100) / 100, math.ceil(upper * 100) / 100
    except (ValueError, OverflowError):
        raise BadRecord("Invalid chart values or range") from None


def freshness(header: Summary, now: datetime) -> str:
    if header.mode == "retrospective":
        return "Retrospective research run — not a live forecast."
    try:
        calendar = exchange_calendar(
            now.date() - timedelta(days=32), now.date() + timedelta(days=32)
        )
        import pandas as pd

        sessions = calendar.sessions[calendar.opens <= pd.Timestamp(now)]
        expected = sessions[-1].date()
        if header.target < expected:
            return f"Older result: latest session already opened is {expected}."
        return (
            f"Live run for {header.target}; "
            f"latest session already opened is {expected}."
        )
    except (ValueError, IndexError, OverflowError):
        return "Freshness unavailable; inspect the recorded cutoff and target."
