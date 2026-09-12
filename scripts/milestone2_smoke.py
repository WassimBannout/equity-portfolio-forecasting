"""Controlled twelve-asset synthetic demonstration; never retrieves market data."""

import argparse
import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path

from portfolio_forecasting import RunRequest
from portfolio_forecasting.config import ResolvedRunRequest
from portfolio_forecasting.market_data import AssetHistory, Observation
from portfolio_forecasting.pipeline import (
    ForecastReport,
    compute_forecast,
    replay_forecast,
)
from portfolio_forecasting.sessions import plan_sessions
from portfolio_forecasting.snapshots import canonical_bytes, digest

INSTANT = datetime(2026, 9, 8, 9, tzinfo=UTC)


class SyntheticSource:
    def fetch(
        self, ticker: str, resolved: ResolvedRunRequest, *, run_id: str
    ) -> AssetHistory:
        plan = plan_sessions(resolved)
        assert plan is not None
        index = tuple(resolved.request.tickers).index(ticker)
        observations = tuple(
            Observation(
                day, 100.0 + 10 * index + 0.04 * i + 2.0 * math.sin(i / 21.0 + index)
            )
            for i, day in enumerate(plan.sessions)
        )
        return AssetHistory(
            ticker,
            observations,
            (
                ("symbol", ticker),
                ("currency", "USD"),
                ("instrumentType", "EQUITY"),
                ("exchangeName", "NMS"),
                ("exchangeTimezoneName", "America/New_York"),
                ("dataGranularity", "1d"),
            ),
            INSTANT,
            provider="synthetic_fixture_v1",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/milestone2"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    request = RunRequest(mode="retrospective")
    result = compute_forecast(
        request,
        snapshot_directory=args.output / "inputs",
        source=SyntheticSource(),
        clock=lambda: INSTANT,
    )
    assert isinstance(result, ForecastReport)
    replay = replay_forecast(result.snapshot_path, clock=lambda: INSTANT)
    assert len(result.forecasts) == 12
    assert all(
        math.isclose(a.predicted_price, b.predicted_price, rel_tol=1e-8, abs_tol=1e-8)
        for a, b in zip(result.forecasts, replay.forecasts, strict=True)
    )
    report = result.to_metadata()
    report["demonstration"] = (
        "Synthetic deterministic prices; no market-data or accuracy claim"
    )
    report["fixture_sha256"] = digest(Path(__file__).read_bytes())
    report["lock_sha256"] = digest(Path("uv.lock").read_bytes())
    content = canonical_bytes(report)
    destination = args.output / "forecast.json"
    destination.write_bytes(content + b"\n")
    print(
        json.dumps(
            {
                "status": "PASS",
                "assets": len(result.forecasts),
                "prices_per_asset": len(result.data.plan.sessions),
                "cutoff": str(result.data.plan.observation_cutoff),
                "target": str(result.data.plan.forecast_target),
                "snapshot": str(result.snapshot_path),
                "report": str(destination),
                "replay_tolerance": "rel=1e-8, abs=1e-8",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
