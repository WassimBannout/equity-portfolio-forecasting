"""Bounded operational checks and the daily batch; scientific contracts stay in M4."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from portfolio_forecasting.config import RunRequest
from portfolio_forecasting.dashboard_data import (
    Query,
    Reader,
    published_run,
    read_page,
)
from portfolio_forecasting.market_data import utc_now
from portfolio_forecasting.pipeline import SkippedForecast
from portfolio_forecasting.publishing import publish_request
from portfolio_forecasting.sessions import exchange_calendar, plan_sessions
from portfolio_forecasting.snapshots import canonical_bytes, software_metadata
from portfolio_forecasting.store_contract import Release, StoreError, identity_for
from portfolio_forecasting.supabase_store import StoreCredentials, SupabaseStore


def expected_session(now: datetime) -> date:
    """Allow the 09:00 UTC job one hour, including across DST and holidays."""
    if now.utcoffset() is None:
        raise ValueError("an aware freshness clock is required")
    now = now.astimezone(UTC)
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    calendar = exchange_calendar(today - timedelta(days=40), today + timedelta(days=32))
    due = datetime.combine(today, time(10), UTC)
    end = today if now >= due else today - timedelta(days=1)
    return calendar.date_to_session(end.isoformat(), direction="previous").date()  # type: ignore[no-any-return]


def freshness_status(read: Query, now: datetime) -> dict[str, Any]:
    expected = expected_session(now)
    request = RunRequest()
    result: dict[str, Any] = {
        "checked_at": now.astimezone(UTC).isoformat(),
        "expected_target": expected.isoformat(),
        "status": "missing",
        "last_success": None,
    }
    arguments: dict[str, Any] = {"p_limit": 100, "p_cursor": None, "p_as_of": None}
    for _ in range(10):
        page = read_page(read("pf_runs", arguments), arguments)
        for header in page.summaries:
            if (
                header.mode != "live"
                or header.universe != tuple(sorted(request.tickers))
                or header.revision != request.scientific_revision
            ):
                continue
            run = published_run(read("pf_run", {"p_run_id": header.run_id}), header)
            if header.published_at > now or header.executed_at > now:
                raise StoreError("future publication timestamp")
            # A retrospective record or unrelated configuration cannot clear an alert.
            identity = run.document["identity"]
            settings = request.resolve(clock=lambda: now).to_metadata()
            if any(
                identity[key] != settings[key]
                for key in ("forecast", "allocation", "data")
            ):
                continue
            result["last_success"] = {
                "run_id": header.run_id,
                "target": header.target.isoformat(),
                "cutoff": header.cutoff.isoformat(),
                "published_at": header.published_at.isoformat(),
            }
            result["status"] = "fresh" if header.target >= expected else "stale"
            return result
        if page.next_cursor is None:
            return result
        arguments.update(p_cursor=page.next_cursor, p_as_of=page.as_of)
    result["status"] = "unknown_scan_limit"
    return result


def readiness(store: SupabaseStore, root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "release.json").read_bytes())
    if not re.fullmatch(r"[0-9a-f]{40}", manifest["revision"]):
        raise StoreError("invalid release revision")
    release = Release.capture(root / "uv.lock")
    if manifest["lock_sha256"] != release.lock_sha256:
        raise StoreError("release lock mismatch")
    if manifest["source_sha256"] != software_metadata()["source_sha256"]:
        raise StoreError("installed source mismatch")
    read = Reader(store).query
    args = {"p_limit": 1, "p_cursor": None, "p_as_of": None}
    page = read_page(read("pf_runs", args), args)
    last = None
    if page.summaries:
        header = page.summaries[0]
        published_run(read("pf_run", {"p_run_id": header.run_id}), header)
        last = header.run_id
    return {**manifest, "status": "ready", "latest_run": last}


def batch(store: SupabaseStore, root: Path, snapshots: Path) -> dict[str, Any]:
    request = RunRequest()
    resolved = request.resolve(clock=utc_now)
    plan = plan_sessions(resolved)
    if plan is None:
        return {"status": "no_op", "reason": "closed_session"}
    release = Release.capture(root / "uv.lock")
    store.preflight(writer=True)
    bound = store.lookup(identity=identity_for(resolved, plan, release))
    repeated = bound is not None and bound["state"] == "published"
    result = publish_request(
        request,
        store,
        release,
        snapshot_directory=snapshots,
    )
    if isinstance(result, SkippedForecast):
        return {"status": "no_op", "reason": "closed_session"}
    # Use today's durably bound input to mature exact earlier targets. M4 decides
    # price-basis compatibility; missed observations never become new live forecasts.
    snapshot = store.bound_snapshot(result["snapshot_sha256"], snapshots)
    cutoff = date.fromisoformat(result["identity"]["observation_cutoff"])
    oldest = cutoff - timedelta(days=14)
    cursor = None
    watermark = None
    observed = 0
    completion = {
        "status": "no_op" if repeated else "success",
        "reason": "already_published" if repeated else "published",
        "run_id": result["run_id"],
    }
    for _ in range(5):
        page = store.runs(limit=50, cursor=cursor, as_of=watermark)
        for row in page["items"]:
            target = date.fromisoformat(row["target"])
            if target < oldest:
                return {
                    **completion,
                    "observed_runs": observed,
                }
            if target <= cutoff:
                store.observe(row["run_id"], snapshot)
                observed += 1
        if page["next_cursor"] is None:
            return {
                **completion,
                "observed_runs": observed,
            }
        cursor, watermark = page["next_cursor"], page["as_of"]
    raise StoreError("outcome recovery scan limit; use the manual observe procedure")


def write_status(path: Path, result: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(canonical_bytes(result) + b"\n")
    temporary.replace(path)


def render_status() -> None:
    """Optional deployed status footer, independent of the selected historic run."""
    location = os.environ.get("PF_STATUS_FILE")
    if not location:
        return
    import streamlit as st

    st.subheader("Daily publication status")
    try:
        value = json.loads(Path(location).read_bytes())
        checked = datetime.fromisoformat(value["checked_at"])
        age = (datetime.now(UTC) - checked).total_seconds()
        state = value["status"] if 0 <= age <= 1800 else "monitor overdue"
        st.write(f"Status: {state} · Last check: {checked.isoformat()}")
        st.caption(
            f"Expected live target: {value.get('expected_target', 'unavailable')}"
        )
        last = value.get("last_success")
        if last:
            st.caption(
                f"Last successful live publication: {last['published_at']} · "
                f"Target: {last['target']} · Cutoff: {last['cutoff']} · "
                f"Run: {last['run_id']}"
            )
        if state != "fresh":
            st.warning(
                "Daily publication needs operator attention. "
                "Historical results remain available."
            )
    except (OSError, ValueError, KeyError, TypeError):
        st.warning("Daily publication monitor unavailable; freshness is unknown.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ready", "freshness", "batch"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--snapshots", type=Path, default=Path("/var/lib/pf-batch/inputs")
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    now = datetime.now(UTC)
    try:
        store = SupabaseStore(StoreCredentials.from_environment())
        if args.command == "ready":
            with urlopen("http://127.0.0.1:8501/_stcore/health", timeout=5) as response:
                if response.status != 200 or response.read(16).strip() != b"ok":
                    raise StoreError("web health failed")
            result = readiness(store, args.root)
        elif args.command == "batch":
            revision = json.loads((args.root / "release.json").read_bytes())["revision"]
            print(
                canonical_bytes(
                    {"event": "batch_start", "revision": revision, "started_at": now}
                ).decode(),
                flush=True,
            )
            result = batch(store, args.root, args.snapshots)
            result["revision"] = revision
        else:
            result = freshness_status(Reader(store).query, now)
        code = 0 if result["status"] in ("ready", "fresh", "success", "no_op") else 1
    except (ValueError, OSError, KeyError, TypeError):
        # Never serialize exceptions, tokens, transport bodies or full result payloads.
        result = {"status": "unavailable", "checked_at": now.isoformat()}
        code = 1
    if args.output:
        if result["status"] == "unavailable":
            try:
                previous = json.loads(args.output.read_bytes())
                result.update(
                    last_success=previous.get("last_success"),
                    expected_target=previous.get("expected_target"),
                )
            except (OSError, ValueError, AttributeError):
                pass
        write_status(args.output, result)
    print(canonical_bytes(result).decode())
    return code


if __name__ == "__main__":
    sys.exit(main())
