"""Manual Supabase publication, exact outcome association, and bounded inspection."""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

from portfolio_forecasting.config import (
    AllocationSettings,
    DataSettings,
    ForecastSettings,
    RunRequest,
)
from portfolio_forecasting.pipeline import SkippedForecast
from portfolio_forecasting.publishing import publish_request, resume_publication
from portfolio_forecasting.snapshots import canonical_bytes, read_snapshot
from portfolio_forecasting.store_contract import Release, StoreError, object_value
from portfolio_forecasting.supabase_store import StoreCredentials, SupabaseStore


def request_from_file(path: Path) -> RunRequest:
    value = object_value(json.loads(path.read_bytes()), "request")
    options: dict[str, Any] = dict(value)
    for name in ("history_start", "history_end"):
        if options.get(name) is not None:
            options[name] = date.fromisoformat(options[name])
    for name, cls in (
        ("forecast", ForecastSettings),
        ("allocation", AllocationSettings),
        ("data", DataSettings),
    ):
        if name in options:
            options[name] = cls(**object_value(options[name], name))
    return RunRequest(**options)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument("--snapshots", type=Path, default=Path("artifacts/inputs"))
    parser.add_argument(
        "--api-prefix",
        choices=("/rest/v1", ""),
        default="/rest/v1",
        help="Empty only for disposable native PostgREST verification",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    compute = commands.add_parser(
        "compute", help="Compute and publish; defaults to an eligible live request"
    )
    compute.add_argument("--request", type=Path)
    compute.add_argument(
        "--snapshot", type=Path, help="Existing retrospective input snapshot"
    )
    commands.add_parser("resume", help="Reuse one already-bound run").add_argument(
        "run_id"
    )
    commands.add_parser("read", help="Read one complete published run").add_argument(
        "run_id"
    )
    observe = commands.add_parser(
        "observe", help="Associate only exact comparable target observations"
    )
    observe.add_argument("run_id")
    observe.add_argument("--snapshot", type=Path, required=True)
    runs = commands.add_parser("runs", help="Read one bounded run-summary page")
    history = commands.add_parser(
        "history", help="Read bounded, inclusive ticker history"
    )
    history.add_argument("ticker")
    history.add_argument("--start", type=date.fromisoformat, required=True)
    history.add_argument("--end", type=date.fromisoformat, required=True)
    for page in (runs, history):
        page.add_argument("--limit", type=int, default=50)
        page.add_argument(
            "--cursor", type=Path, help="Previous returned page JSON, including as_of"
        )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        store = SupabaseStore(
            StoreCredentials.from_environment(), api_prefix=args.api_prefix
        )
        result: Any
        if args.command == "compute":
            if args.snapshot:
                data = read_snapshot(args.snapshot)
                if data.resolved.request.mode != "retrospective":
                    raise StoreError(
                        "manual captured-input publication requires retrospective mode"
                    )
                request = data.resolved.request
                if args.request and request_from_file(args.request) != request:
                    raise StoreError("request file conflicts with captured inputs")
            else:
                request = (
                    request_from_file(args.request) if args.request else RunRequest()
                )
            result = publish_request(
                request,
                store,
                Release.capture(args.lock),
                snapshot_directory=args.snapshots,
                input_snapshot=args.snapshot,
            )
        elif args.command == "resume":
            result = resume_publication(
                args.run_id,
                store,
                Release.capture(args.lock),
                snapshot_directory=args.snapshots,
            )
        elif args.command == "observe":
            store.preflight(writer=True)
            result = store.observe(args.run_id, args.snapshot)
        else:
            store.preflight()
            if args.command == "read":
                result = store.get_run(args.run_id)
            else:
                previous = (
                    object_value(json.loads(args.cursor.read_bytes()), "page")
                    if args.cursor
                    else {}
                )
                options = {
                    "limit": args.limit,
                    "cursor": previous.get("next_cursor"),
                    "as_of": previous.get("as_of"),
                }
                if args.cursor and previous.get("next_cursor") is None:
                    raise StoreError("the supplied page has no continuation")
                result = (
                    store.runs(**options)
                    if args.command == "runs"
                    else store.history(args.ticker, args.start, args.end, **options)
                )
        print(
            canonical_bytes(
                result.to_metadata() if isinstance(result, SkippedForecast) else result
            ).decode()
        )
        return 0
    except (ValueError, TypeError, OSError) as error:
        # Credential values and server response bodies are never interpolated.
        message = (
            str(error)
            if isinstance(error, (StoreError, ValueError))
            else "invalid command input or local file operation"
        )
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
