"""Manual forecast report; publication commands belong to Milestone 4."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from portfolio_forecasting.config import RunRequest
from portfolio_forecasting.pipeline import (
    ForecastReport,
    SkippedForecast,
    compute_forecast,
    replay_forecast,
)
from portfolio_forecasting.snapshots import canonical_bytes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Produce a forecast-only JSON report with local input provenance."
    )
    parser.add_argument("--tickers", nargs="+")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--retrospective", action="store_true")
    parser.add_argument("--snapshots", type=Path, default=Path("artifacts/inputs"))
    parser.add_argument(
        "--replay",
        type=Path,
        help="Verified local snapshot; never downloads market data",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    result: ForecastReport | SkippedForecast
    try:
        if args.replay:
            if (
                args.tickers
                or args.end
                or args.retrospective
                or args.start != date(2024, 1, 1)
            ):
                parser.error(
                    "--replay uses its captured request; "
                    "do not combine with request options"
                )
            result = replay_forecast(args.replay)
        else:
            defaults = RunRequest()
            request = RunRequest(
                tickers=args.tickers if args.tickers is not None else defaults.tickers,
                history_start=args.start,
                history_end=args.end,
                mode="retrospective" if args.retrospective else "live",
            )
            result = compute_forecast(request, snapshot_directory=args.snapshots)
        print(canonical_bytes(result.to_metadata()).decode())
        return 0
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
