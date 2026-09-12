from datetime import date

import pytest

from portfolio_forecasting import AllocationSettings, ForecastSettings, RunRequest
from portfolio_forecasting.market_data import PreparedData, prepare_data
from portfolio_forecasting.sessions import plan_sessions
from tests.market_fixtures import NOW, synthetic_history


@pytest.fixture
def prepared() -> PreparedData:
    request = RunRequest(
        tickers=("AMD", "MSFT"),
        history_start=date(2026, 7, 1),
        history_end=date(2026, 9, 8),
        mode="retrospective",
        allocation=AllocationSettings(risk_window=2),
        forecast=ForecastSettings(yearly_seasonality=False),
    )
    resolved = request.resolve(clock=lambda: NOW)
    plan = plan_sessions(resolved)
    assert plan is not None
    return prepare_data(
        resolved,
        plan,
        tuple(
            synthetic_history(ticker, plan.sessions, offset=i * 10.0)
            for i, ticker in enumerate(request.tickers)
        ),
    )


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("ordinary tests must not access the network")

    monkeypatch.setattr("socket.socket.connect", denied)
    monkeypatch.setattr("yfinance._http.requests.Session.request", denied)
