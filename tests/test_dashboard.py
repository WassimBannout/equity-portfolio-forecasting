import copy
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from streamlit.testing.v1 import AppTest

from portfolio_forecasting import dashboard
from portfolio_forecasting.dashboard_data import (
    BadRecord,
    Reader,
    Unavailable,
    aggregate_errors,
    chart_range,
    error_rows,
    freshness,
    published_run,
    read_page,
    summary,
)
from portfolio_forecasting.portfolio import PortfolioReport
from portfolio_forecasting.store_contract import Release
from portfolio_forecasting.supabase_store import SupabaseStore
from tests.dashboard_fixtures import NOW, MemoryReads, matched, run_summary
from tests.test_persistence import credentials, reader_record
from tests.test_persistence import release as release
from tests.test_persistence import report as report

APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


@pytest.fixture
def ui_run(report: PortfolioReport, release: Release) -> dict[str, Any]:
    run = reader_record(report, release)
    run["run_id"] = str(UUID(int=1))
    for item in run["assets"]:
        item["observed_price"] = 100.0
        item["predicted_price"] = 110.0
        item["predicted_return"] = 0.1
        item["recent_history"][-1]["price"] = 100.0
    run["scientific_payload"]["assets"] = [
        {k: copy.deepcopy(v) for k, v in item.items() if k != "outcome"}
        for item in run["assets"]
    ]
    return run


def launch(monkeypatch: pytest.MonkeyPatch, reader: MemoryReads) -> AppTest:
    monkeypatch.setattr(dashboard, "read_query", reader.query)
    app = AppTest.from_file(APP, default_timeout=15).run()
    assert not app.exception
    return app


def text_of(app: AppTest) -> str:
    return "\n".join(
        str(item.value)
        for kind in (app.caption, app.info, app.warning, app.error, app.markdown)
        for item in kind
    )


def test_empty_database_is_distinct_from_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = launch(monkeypatch, MemoryReads([]))
    assert "No published runs yet" in text_of(app)
    assert not app.error and not app.get("plotly_chart")


def test_unconfigured_real_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_ACCESS_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert "Service unavailable" in text_of(app)
    assert "No published runs" not in text_of(app)


def test_first_run_pending_renders_allocation_forecasts_and_real_dates(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any]
) -> None:
    reader = MemoryReads([ui_run])
    app = launch(monkeypatch, reader)
    assert not app.error
    assert app.selectbox[2].options == ["AMD", "MSFT"]
    assert len(app.get("plotly_chart")) == 2
    axis = json.loads(app.get("plotly_chart")[-1].proto.spec)["layout"]["xaxis"]
    assert axis["tickvals"] == ["2026-09-08"]
    assert axis["range"] == ["2026-09-07", "2026-09-09"]
    assert axis["tickformat"] == "%Y-%m-%d"
    assert [metric.value for metric in app.metric] == ["$100.00", "$110.00", "10.00%"]
    assert "Outcome pending" in text_of(app)
    table = app.dataframe[0].value
    assert list(table.columns) == [
        "Ticker",
        "Forecast price (USD)",
        "Forecast return",
        "Allocation",
    ]
    assert all(value.endswith("%") for value in table["Allocation"])
    dates = app.dataframe[1].value["Session"].tolist()
    assert dates == [item["session"] for item in ui_run["assets"][0]["recent_history"]]
    assert dates[-1] == "2026-09-04" and "2026-09-07" not in dates
    assert "Configuration revision: 1" in text_of(app)
    assert "Model/code revision:" in text_of(app)
    assert "Observation cutoff: 2026-09-04" in text_of(app)
    assert "Forecast target: 2026-09-08" in text_of(app)


def test_known_errors_and_asset_without_outcomes(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any]
) -> None:
    matched(ui_run)
    app = launch(monkeypatch, MemoryReads([ui_run]))
    assert not app.error
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Price MAE"] == "$11.00"
    assert metrics["Price RMSE"] == "$11.00"
    assert metrics["Last-price MAE"] == "$21.00"
    assert metrics["MAE / last-price MAE"] == "0.524×"
    row = app.dataframe[-1].value.iloc[0]
    assert row["Error / predicted"] == "10.00%"
    assert row["Signed error (actual − predicted)"] == "$11.00"
    assert "this is not MAPE" in text_of(app)
    app.selectbox[2].select("MSFT").run()
    assert not app.exception and not app.error
    assert len(app.metric) == 3 and "Outcome pending" in text_of(app)
    assert len(app.get("plotly_chart")) == 2


def test_history_failure_does_not_remove_valid_selected_run(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any]
) -> None:
    reader = MemoryReads([ui_run])

    def read(name: str, args: dict[str, Any]) -> Any:
        if name == "pf_history":
            raise Unavailable("secret-should-not-be-rendered")
        return reader.query(name, args)

    monkeypatch.setattr(dashboard, "read_query", read)
    app = AppTest.from_file(APP).run()
    assert not app.exception and len(app.metric) == 3
    assert len(app.get("plotly_chart")) == 1
    assert "Service unavailable — ticker history" in text_of(app)
    assert "secret-should-not-be-rendered" not in text_of(app)


@pytest.mark.parametrize(
    "bad", [None, True, float("nan"), float("inf"), "0.5", -0.1, 0.2]
)
def test_bad_full_weights_never_render_normalized_pie(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any], bad: Any
) -> None:
    ui_run["assets"][0]["weight"] = bad
    app = launch(monkeypatch, MemoryReads([ui_run]))
    assert "Bad record — selected run" in text_of(app)
    assert not app.get("plotly_chart") and not app.metric


def test_truncated_and_mixed_run_rejected(ui_run: dict[str, Any]) -> None:
    selected = summary(run_summary(ui_run))
    broken = copy.deepcopy(ui_run)
    broken["assets"].pop()
    with pytest.raises(BadRecord):
        published_run(broken, selected)
    broken = copy.deepcopy(ui_run)
    broken["run_id"] = str(UUID(int=9))
    with pytest.raises(BadRecord):
        published_run(broken, selected)


@pytest.mark.parametrize(
    "bad",
    [None, [], "[]", [{"price": 1}], [{"session": "2026-09-04", "price": "oops"}]],
)
def test_bad_history_is_visible_without_breaking_overview(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any], bad: Any
) -> None:
    reader = MemoryReads([ui_run])

    def read(name: str, args: dict[str, Any]) -> Any:
        value = reader.query(name, args)
        if name == "pf_history":
            value["items"][0]["asset"]["recent_history"] = bad
        return value

    monkeypatch.setattr(dashboard, "read_query", read)
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert "Bad record — ticker history" in text_of(app)
    assert len(app.get("plotly_chart")) == 1 and len(app.metric) == 3


def test_revisions_old_date_and_both_paginators(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any]
) -> None:
    runs = []
    for index in range(27):
        run = copy.deepcopy(ui_run)
        run["run_id"] = str(UUID(int=index + 1))
        run["identity"]["scientific_revision"] = str(index + 1)
        if index == 26:
            run["identity"]["forecast_target"] = "2026-09-09"
        matched(run)
        runs.append(run)
    reader = MemoryReads(runs)
    app = launch(monkeypatch, reader)
    assert app.selectbox[0].value == "2026-09-09"
    assert app.selectbox[1].value == str(UUID(int=27))
    app.selectbox[0].select("2026-09-08").run()
    assert app.selectbox[1].value == str(UUID(int=26))
    assert app.metric[0].value == "$100.00"
    assert "All available history for this ticker" in text_of(app)
    assert "2026-09-08 through 2026-09-09" in text_of(app)
    app.button(key="run-pages-older").click().run()
    assert app.selectbox[1].value == str(UUID(int=2))
    app.selectbox[1].select(str(UUID(int=1))).run()
    assert "Configuration revision: 1" in text_of(app)
    app.button(key="history-pages-older").click().run()
    assert "History coverage on page 2" in text_of(app)
    assert "2 predictions · 2 matched" in text_of(app)
    assert app.button(key="history-pages-older").disabled
    app.button(key="history-pages-newer").click().run()
    app.button(key="run-pages-newer").click().run()
    assert not app.exception and not app.error
    assert all(args["p_limit"] == 25 for name, args in reader.calls if name != "pf_run")
    assert all(
        args["p_as_of"] == reader.watermark
        for name, args in reader.calls
        if name == "pf_history"
    )


def test_incompatible_and_wrong_target_are_distinct(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any]
) -> None:
    matched(ui_run)
    outcome = ui_run["assets"][0]["outcome"]
    outcome.update(
        state="incompatible", actual_price=None, reason="adjusted_history_changed"
    )
    app = launch(monkeypatch, MemoryReads([ui_run]))
    assert "Outcome unavailable" in text_of(app) and not app.error
    assert "Unavailable" in app.dataframe[-1].value.iloc[0]["Actual"]
    outcome["target"] = "2026-09-09"
    app.run()
    assert "Bad record — selected run" in text_of(app)


def test_constant_chart_and_collapsed_slider(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any]
) -> None:
    matched(ui_run, actual=110)
    app = launch(monkeypatch, MemoryReads([ui_run]))
    low, high = app.slider[0].value
    assert low < 110 < high
    app.slider[0].set_value((low, low)).run()
    assert not app.exception
    assert "Choose a lower price below" in text_of(app)
    assert len(app.get("plotly_chart")) == 1
    assert len(app.dataframe[-1].value) == 1


@pytest.mark.parametrize(
    "values", [[], [0], [-1], [float("nan")], [float("inf")], [1.7976931348623157e308]]
)
def test_chart_rejects_invalid_or_overflowing_ranges(values: list[float]) -> None:
    with pytest.raises(BadRecord):
        chart_range(values)


def test_zero_baseline_and_signed_arithmetic(ui_run: dict[str, Any]) -> None:
    matched(ui_run, actual=100)
    reader = MemoryReads([ui_run])
    args = dict(p_limit=25, p_ticker="AMD", p_start="0001-01-01", p_end="9999-12-31")
    page = read_page(reader.query("pf_history", args), args)
    aggregate = aggregate_errors(page.history)
    assert aggregate == dict(count=1, mae=10, rmse=10, baseline_mae=0, ratio=None)
    assert error_rows(page.history)[0]["Signed error (actual − predicted)"] == "$-10.00"
    assert error_rows(page.history)[0]["Error / predicted"] == "-9.09%"


@pytest.mark.parametrize(
    "fault", ["cursor", "watermark", "duplicate", "coverage", "ticker", "nonfinite"]
)
def test_bad_page_contract(ui_run: dict[str, Any], fault: str) -> None:
    args = dict(
        p_limit=25,
        p_ticker="AMD",
        p_start="0001-01-01",
        p_end="9999-12-31",
        p_as_of="2026-09-14T12:00:00+00:00",
    )
    page = MemoryReads([ui_run]).query("pf_history", args)
    if fault == "cursor":
        page["next_cursor"] = {"run_id": "bad"}
    if fault == "watermark":
        page["as_of"] = "2026-09-14T13:00:00+00:00"
    if fault == "duplicate":
        page["items"] *= 2
    if fault == "coverage":
        page["requested_start"] = "2026-01-01"
    if fault == "ticker":
        page["items"][0]["asset"]["ticker"] = "MSFT"
    if fault == "nonfinite":
        page["items"][0]["asset"]["predicted_price"] = float("inf")
    with pytest.raises(BadRecord):
        read_page(page, args)


@pytest.mark.parametrize("role", ["portfolio_writer", "service_role", "administrator"])
def test_writer_roles_cannot_enter_dashboard(role: str) -> None:
    calls = []

    def transport(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> bytes:
        calls.append(url)
        return json.dumps(dict(role=role, schema_version=1)).encode()

    reader = Reader(SupabaseStore(credentials(), transport=transport))
    with pytest.raises(Unavailable):
        reader.query("pf_runs", {})
    assert len(calls) == 1 and calls[0].endswith("/pf_access")
    with pytest.raises(Unavailable):
        reader.query("pf_publish", {})
    assert len(calls) == 1


def test_reads_and_reruns_never_run_models_provider_or_writes(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any]
) -> None:
    def denied(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("UI must never invoke computation or mutation")

    for name in ("publish", "stage", "observe", "attempt", "fail"):
        monkeypatch.setattr(SupabaseStore, name, denied)
    monkeypatch.setattr("prophet.Prophet.fit", denied)
    monkeypatch.setattr(
        "portfolio_forecasting.market_data.YFinanceSource.fetch", denied
    )
    monkeypatch.setattr("portfolio_forecasting.allocation.solve_allocation", denied)
    reader = MemoryReads([ui_run])
    app = launch(monkeypatch, reader)
    app.selectbox[2].select("MSFT").run()
    app.slider[0].set_value(app.slider[0].value).run()
    assert not app.exception


def test_reader_distinguishes_malformed_wire_data_from_outage() -> None:
    count = 0

    def transport(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> bytes:
        nonlocal count
        count += 1
        return (
            b'{"role":"anon","schema_version":1}'
            if url.endswith("pf_access")
            else b"bad-json"
        )

    with pytest.raises(BadRecord):
        Reader(SupabaseStore(credentials(), transport=transport)).query("pf_runs", {})
    assert count == 2


def test_cache_reuses_bounded_reads_and_expires_without_background_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.runtime.caching import cache_utils

    clock = [0.0]
    monkeypatch.setattr(cache_utils, "TTLCACHE_TIMER", lambda: clock[0])
    calls = []

    def query(self: Reader, function: str, args: dict[str, Any]) -> Any:
        calls.append((function, args))
        return {"items": []}

    monkeypatch.setattr(Reader, "query", query)
    dashboard.cached_query.clear()
    for instant in (0, 1, 299):
        clock[0] = instant
        assert dashboard.cached_query(credentials(), "pf_runs", '{"p_limit":25}') == {
            "items": []
        }
    assert len(calls) == 1
    clock[0] = 301
    assert len(calls) == 1
    dashboard.cached_query(credentials(), "pf_runs", '{"p_limit":25}')
    assert len(calls) == 2
    dashboard.cached_query(
        replace(credentials(), access_token="another-reader"),
        "pf_runs",
        '{"p_limit":25}',
    )
    assert len(calls) == 3
    dashboard.cached_query.clear()


def test_freshness_uses_opened_sessions_and_retrospective_label(
    ui_run: dict[str, Any],
) -> None:
    header = summary(run_summary(ui_run))
    assert "Retrospective" in freshness(header, NOW)
    header = replace(header, mode="live", target=date(2026, 9, 8))
    assert "Older result" in freshness(header, datetime(2026, 9, 14, 14, tzinfo=UTC))
    assert "2026-09-08" in freshness(header, datetime(2026, 9, 8, 14, tzinfo=UTC))


def test_chart_bounds_expand_to_slider_cent_precision() -> None:
    low, high = chart_range([109.618273, 109.718273])
    assert low < 109.618273 < high
    assert round(low, 2) == low and round(high, 2) == high


def test_bad_recent_dates_and_missing_revision_are_rejected(
    ui_run: dict[str, Any],
) -> None:
    selected = summary(run_summary(ui_run))
    broken = copy.deepcopy(ui_run)
    broken["assets"][0]["recent_history"][-1]["session"] = "2026-09-03"
    with pytest.raises(BadRecord):
        published_run(broken, selected)
    broken = copy.deepcopy(ui_run)
    del broken["identity"]["software_revision"]
    with pytest.raises(BadRecord):
        published_run(broken, selected)


def test_expired_root_watermark_restarts_pagination(
    monkeypatch: pytest.MonkeyPatch, ui_run: dict[str, Any]
) -> None:
    runs = []
    for index in range(26):
        run = copy.deepcopy(ui_run)
        run["run_id"] = str(UUID(int=index + 1))
        runs.append(run)
    reader = MemoryReads(runs)
    app = launch(monkeypatch, reader)
    app.button(key="run-pages-older").click().run()
    app.button(key="history-pages-older").click().run()
    assert "History coverage on page 2" in text_of(app)
    reader.watermark = "2026-09-14T13:00:00+00:00"
    app.run()
    assert not app.exception and not app.error
    assert "Run page 1" in text_of(app)
    assert "History coverage on page 1" in text_of(app)
