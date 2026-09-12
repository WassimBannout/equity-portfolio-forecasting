"""Synthetic session fixtures: no Yahoo requests or database access."""

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from portfolio_forecasting.market_data import (
    AssetHistory,
    normalize_history,
)

NOW = datetime(2026, 9, 8, 9, tzinfo=UTC)


def metadata(ticker: str) -> dict[str, Any]:
    return {
        "symbol": ticker,
        "currency": "USD",
        "instrumentType": "EQUITY",
        "exchangeName": "NMS",
        "exchangeTimezoneName": "America/New_York",
        "dataGranularity": "1d",
    }


def synthetic_history(
    ticker: str, days: tuple[date, ...], *, offset: float = 0.0
) -> AssetHistory:
    frame = pd.DataFrame(
        {"Adj Close": [100.0 + offset + i * 0.2 for i in range(len(days))]},
        index=pd.DatetimeIndex(days).tz_localize("America/New_York"),
    )
    return replace(
        normalize_history(ticker, frame, metadata(ticker), NOW),
        provider="synthetic_fixture",
    )
