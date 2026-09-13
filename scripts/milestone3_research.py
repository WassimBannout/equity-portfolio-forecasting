"""Evaluate the predeclared M3 study from a frozen local snapshot (no retrieval)."""

import argparse
import json
import logging
from pathlib import Path

from portfolio_forecasting.evaluation import Experiment, evaluate_snapshot
from portfolio_forecasting.research_report import export_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("experiments/milestone3.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/milestone3/research")
    )
    parser.add_argument("--report", type=Path, default=Path("docs/examples/milestone3"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("cmdstanpy").disabled = True
    result = evaluate_snapshot(
        args.snapshot,
        Experiment.from_mapping(json.loads(args.config.read_bytes())),
        output_directory=args.output,
        progress=lambda value: print(value, flush=True),
    )
    print(export_report(result, args.report), flush=True)


if __name__ == "__main__":
    main()
