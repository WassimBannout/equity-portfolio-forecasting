"""Detached, dated RPC fixtures for dashboard interactions (no network)."""

import copy
from datetime import UTC, datetime
from typing import Any

from portfolio_forecasting.dashboard_data import READ_FUNCTIONS

WATERMARK = "2026-09-14T12:00:00+00:00"
NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


def run_summary(run: dict[str, Any]) -> dict[str, Any]:
    identity = run["identity"]
    return {
        "run_id": run["run_id"],
        "target": identity["forecast_target"],
        "observation_cutoff": identity["observation_cutoff"],
        "executed_at": run["executed_at"],
        "published_at": run["published_at"],
        "universe": identity["universe"],
        "scientific_revision": identity["scientific_revision"],
        "mode": identity["mode"],
    }


def matched(run: dict[str, Any], *, actual: float = 121.0, ticker: str = "AMD") -> None:
    item = next(item for item in run["assets"] if item["ticker"] == ticker)
    item["outcome"] = {
        "state": "matched",
        "actual_price": actual,
        "target": run["identity"]["forecast_target"],
        "observed_at": WATERMARK,
        "source_sha256": "c" * 64,
        "basis_policy": "all_overlap_unchanged_v1",
        "reason": "exact_target_and_unchanged_overlap",
    }


class MemoryReads:
    def __init__(self, runs: list[dict[str, Any]]) -> None:
        self.runs = runs
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.watermark = WATERMARK

    def query(self, name: str, args: dict[str, Any]) -> Any:
        assert name in READ_FUNCTIONS, f"dashboard attempted mutation: {name}"
        self.calls.append((name, copy.deepcopy(args)))
        if name == "pf_run":
            return copy.deepcopy(
                next(run for run in self.runs if run["run_id"] == args["p_run_id"])
            )
        rows = [run_summary(run) for run in self.runs]
        if name == "pf_history":
            rows = [
                {**header, "asset": item}
                for run, header in zip(self.runs, rows, strict=True)
                for item in run["assets"]
                if item["ticker"] == args["p_ticker"]
            ]

        def order(row: dict[str, Any]) -> tuple[str, str, str]:
            return row["target"], row["published_at"], row["run_id"]

        rows.sort(key=order, reverse=True)
        cursor = args.get("p_cursor")
        if cursor is not None:
            rows = [row for row in rows if order(row) < order(cursor)]
        limit = args["p_limit"]
        next_cursor = (
            {key: rows[limit - 1][key] for key in ("target", "published_at", "run_id")}
            if len(rows) > limit
            else None
        )
        return copy.deepcopy(
            {
                "items": rows[:limit],
                "as_of": args.get("p_as_of") or self.watermark,
                "next_cursor": next_cursor,
                "requested_start": args.get("p_start"),
                "requested_end": args.get("p_end"),
            }
        )
