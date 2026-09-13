"""Twelve-asset offline M3 composition with the preserved deterministic M2 fixture."""

import argparse
import json
import logging
from pathlib import Path

from milestone2_smoke import INSTANT, SyntheticSource

from portfolio_forecasting import RunRequest
from portfolio_forecasting.portfolio import PortfolioReport, compute_portfolio
from portfolio_forecasting.snapshots import canonical_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/milestone3/smoke")
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("cmdstanpy").disabled = True
    result = compute_portfolio(
        RunRequest(mode="retrospective"),
        snapshot_directory=args.output / "inputs",
        source=SyntheticSource(),
        clock=lambda: INSTANT,
    )
    assert isinstance(result, PortfolioReport)
    assert len(result.allocation.weights) == 12
    assert abs(sum(result.allocation.weights) - 1) <= 1e-9
    assert all(
        0.05 - 1e-9 <= weight <= 0.45 + 1e-9 for weight in result.allocation.weights
    )
    metadata = result.to_metadata()
    metadata["demonstration"] = "deterministic synthetic prices; no accuracy claim"
    path = args.output / "portfolio.json"
    path.write_bytes(canonical_bytes(metadata) + b"\n")
    print(json.dumps({"status": "PASS", "assets": 12, "report": str(path)}))


if __name__ == "__main__":
    main()
