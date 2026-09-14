"""Streamlit exploration of coherent published runs; no batch actions."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from portfolio_forecasting.dashboard_data import (
    CACHE_SECONDS,
    PAGE_SIZE,
    BadRecord,
    Page,
    Query,
    Reader,
    Run,
    Unavailable,
    aggregate_errors,
    chart_range,
    environment_credentials,
    error_rows,
    freshness,
    percent,
    price,
    published_run,
    read_page,
    timestamp,
)
from portfolio_forecasting.supabase_store import StoreCredentials, SupabaseStore


@st.cache_data(ttl=CACHE_SECONDS, max_entries=128, show_spinner=False)
def cached_query(
    credentials: StoreCredentials, function: str, arguments_json: str
) -> Any:
    # Credentials participate in the cache key; no disk cache or credential output.
    return Reader(SupabaseStore(credentials)).query(
        function, json.loads(arguments_json)
    )


def read_query(function: str, arguments: dict[str, Any]) -> Any:
    return cached_query(
        environment_credentials(), function, json.dumps(arguments, sort_keys=True)
    )


def _failure(error: ValueError, section: str) -> None:
    if isinstance(error, BadRecord):
        st.error(
            f"Bad record — {section} contains invalid or incomplete data. "
            "Ask the operator to check the published record."
        )
    else:
        st.error(
            f"Service unavailable — {section} could not be read. "
            "Try again after the cache interval; the operator can check the "
            "database connection and reader credentials."
        )


def _navigation(page: Page, key: str, noun: str) -> None:
    stack = st.session_state[key]
    newer, older = st.columns(2)
    if newer.button(f"Newer {noun}", disabled=len(stack) == 1, key=f"{key}-newer"):
        st.session_state[key] = stack[:-1]
        st.rerun()
    if older.button(
        f"Older {noun}", disabled=page.next_cursor is None, key=f"{key}-older"
    ):
        st.session_state[key] = [*stack, page.next_cursor]
        st.rerun()


def _plot(figure: Any, key: str) -> None:
    figure.update_layout(
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h"),
        height=380,
    )
    st.plotly_chart(
        figure,
        key=key,
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
    )


def _overview(run: Run, now: datetime) -> None:
    header, record = run.header, run.document
    st.subheader("Portfolio overview")
    st.caption(
        f"Forecast target: {header.target} · Observation cutoff: {header.cutoff} · "
        "Daily adjusted close · USD"
    )
    st.write(f"Run timestamp: {timestamp(header.executed_at)}")
    st.caption(
        f"Published: {timestamp(header.published_at)} · "
        f"Completed: {timestamp(datetime.fromisoformat(record['completed_at']))}"
    )
    st.info(freshness(header, now))
    prophet_version = record["scientific_payload"]["software"]["packages"]["prophet"]
    st.write(
        f"Model: Prophet {prophet_version} · Configuration revision: {header.revision}"
    )
    st.caption(f"Run ID: {header.run_id}")
    with st.expander("Recorded configuration and provenance"):
        st.json(
            {
                "model_and_configuration": record["identity"],
                "software": record["scientific_payload"]["software"],
                "input_provenance": record["input_provenance"],
                "snapshot_sha256": record["snapshot_sha256"],
                "result_sha256": record["result_sha256"],
                "effective_model_settings": {
                    item["ticker"]: item["model"] for item in record["assets"]
                },
            }
        )
    st.caption(f"Model/code revision: {record['identity']['software_revision']}")
    chart, table = st.columns([1, 1.6])
    with chart:
        # All weights and membership were checked before the pie can normalize them.
        figure = go.Figure(
            go.Pie(
                labels=[item.ticker for item in run.assets],
                values=[item.weight for item in run.assets],
                hole=0.6,
                sort=False,
                textinfo="label+percent",
                hovertemplate="%{label}: %{value:.2%}<extra></extra>",
            )
        )
        _plot(figure, "allocation")
    with table:
        st.dataframe(
            [
                {
                    "Ticker": item.ticker,
                    "Forecast price (USD)": price(item.predicted),
                    "Forecast return": percent(item.predicted_return),
                    "Allocation": percent(item.weight),
                }
                for item in run.assets
            ],
            hide_index=True,
            width="stretch",
        )
        settings = record["identity"]["allocation"]
        cap = min(
            settings["upper_bound"], 1 - (len(run.assets) - 1) * settings["lower_bound"]
        )
        st.caption(
            f"Total allocation: {percent(sum(item.weight for item in run.assets))}. "
            f"Per-asset floor: {percent(settings['lower_bound'])}; effective ceiling: "
            f"{percent(cap)}; risk aversion: {settings['risk_aversion']:g}. "
            "Fully invested, including when every forecast return is negative. "
            "A weight floor does not guarantee diversification."
        )


def _detail(run: Run, ticker: str) -> None:
    item = next(asset for asset in run.assets if asset.ticker == ticker)
    st.subheader(f"{ticker} · selected run")
    actual, prediction, change = st.columns(3)
    actual.metric(f"Stored actual · {run.header.cutoff}", price(item.observed))
    prediction.metric(f"Forecast · {run.header.target}", price(item.predicted))
    change.metric("Forecast return", percent(item.predicted_return))
    st.caption(
        "The actual above is the observation stored with this run, not a live quote."
    )
    if item.outcome_state == "matched":
        st.success(f"Exact-target outcome · {run.header.target}: {price(item.actual)}")
    elif item.outcome_state == "incompatible":
        st.warning(
            "Outcome unavailable — later observations have an "
            "incompatible price basis. "
            "The issued forecast is preserved; no error is calculated for this outcome."
        )
    else:
        st.info(
            f"Outcome pending — no comparable actual is stored for {ticker} on "
            f"{run.header.target}. The forecast and allocation remain available."
        )
    with st.expander("Dated observations stored with this run"):
        st.caption(
            f"{len(item.history)} observations · {item.history[0][0]} through "
            f"{item.history[-1][0]} · original recorded session dates"
        )
        st.dataframe(
            [
                {"Session": day.isoformat(), "Adjusted close (USD)": price(value)}
                for day, value in item.history
            ],
            hide_index=True,
            width="stretch",
        )


def _history(read: Query, ticker: str, watermark: str, page_size: int) -> None:
    st.subheader(f"{ticker} · historical forecast comparison")
    st.caption(
        "All available history for this ticker is browsable, independently of the "
        "selected run. An older run selection does not create an as-of research view. "
        "Each page contains at most 25 published predictions."
    )
    key = "history-pages"
    scope = (ticker, watermark)
    if st.session_state.get("history-scope") != scope:
        st.session_state["history-scope"] = scope
        st.session_state[key] = [None]
    arguments = {
        "p_ticker": ticker,
        "p_start": "0001-01-01",
        "p_end": "9999-12-31",
        "p_limit": page_size,
        "p_cursor": st.session_state[key][-1],
        "p_as_of": watermark,
    }
    try:
        page = read_page(read("pf_history", arguments), arguments)
    except (BadRecord, Unavailable) as error:
        _failure(error, "ticker history")
        return
    try:
        rows = error_rows(page.history)
        aggregate = aggregate_errors(page.history)
    except (ValueError, OverflowError):
        _failure(BadRecord("Invalid metrics"), "ticker history")
        return
    _navigation(page, key, "history")
    if not page.history:
        st.info("No published prediction history for this ticker in this page.")
        return
    targets = [entry.header.target for entry in page.history]
    pending = sum(entry.asset.outcome_state == "pending" for entry in page.history)
    incompatible = sum(
        entry.asset.outcome_state == "incompatible" for entry in page.history
    )
    st.caption(
        f"History coverage on page {len(st.session_state[key])}: "
        f"{min(targets)} through "
        f"{max(targets)} · {len(page.history)} predictions · "
        f"{aggregate['count']} matched · "
        f"{pending} pending · {incompatible} incompatible. "
        + (
            "Older predictions are available."
            if page.next_cursor
            else "Reached the oldest available prediction."
        )
    )
    st.caption(
        "Publication list watermark: "
        + timestamp(datetime.fromisoformat(page.as_of))
        + ". Outcome evidence may have been recorded later; "
        "reads can be cached for 300 seconds."
    )
    if aggregate["count"]:
        st.caption(
            "Metrics cover matched predictions on this page only. "
            "Each published revision "
            "counts separately; these are not independent sessions "
            "or investment returns. "
            "Last-price baseline uses each prediction's own stored cutoff price."
        )
        mae, rmse, baseline, ratio = st.columns(4)
        mae.metric("Price MAE", price(aggregate["mae"]))
        rmse.metric("Price RMSE", price(aggregate["rmse"]))
        baseline.metric("Last-price MAE", price(aggregate["baseline_mae"]))
        value = aggregate["ratio"]
        ratio.metric(
            "MAE / last-price MAE", "Undefined" if value is None else f"{value:.3f}×"
        )
        if value is None:
            st.caption("Relative MAE is undefined because the baseline MAE is zero.")
    else:
        st.info(
            "Evaluation pending/unavailable — no comparable "
            "exact-target pairs on this page."
        )
    entries = sorted(page.history, key=lambda entry: entry.header.order)
    values = [entry.asset.predicted for entry in entries] + [
        entry.asset.actual for entry in entries if entry.asset.actual is not None
    ]
    try:
        bounds = chart_range(values)
        selected = st.slider(
            "Vertical price range (USD)",
            min_value=bounds[0],
            max_value=bounds[1],
            value=bounds,
            key=f"range-{ticker}-{len(st.session_state[key])}-{bounds}",
        )
        if selected[0] >= selected[1]:
            st.warning(
                "Choose a lower price below the upper price to display the chart."
            )
        else:
            figure = go.Figure()
            # Retain pending predictions and actual nulls as gaps.
            custom = [
                [entry.header.run_id, entry.header.revision, entry.asset.outcome_state]
                for entry in entries
            ]
            for name, y, color in (
                ("Forecast", [entry.asset.predicted for entry in entries], "#3869b0"),
                (
                    "Exact-target actual",
                    [entry.asset.actual for entry in entries],
                    "#19816a",
                ),
            ):
                figure.add_trace(
                    go.Scatter(
                        x=[entry.header.target.isoformat() for entry in entries],
                        y=y,
                        name=name,
                        mode="lines+markers",
                        connectgaps=False,
                        line=dict(color=color),
                        customdata=custom,
                        hovertemplate=(
                            "%{x}<br>$%{y:.2f}<br>Revision %{customdata[1]}"
                            "<br>%{customdata[2]}<br>Run "
                            "%{customdata[0]}<extra>%{fullData.name}</extra>"
                        ),
                    )
                )
            days = sorted({entry.header.target for entry in entries})
            left = date.fromordinal(max(1, days[0].toordinal() - 1))
            right = date.fromordinal(
                min(date.max.toordinal(), days[-1].toordinal() + 1)
            )
            figure.update_layout(
                xaxis=dict(
                    title="Forecast target session",
                    type="date",
                    range=[left.isoformat(), right.isoformat()],
                    tickmode="array",
                    tickvals=[day.isoformat() for day in days],
                    tickformat="%Y-%m-%d",
                ),
                yaxis=dict(title="Adjusted close (USD)", range=list(selected)),
                hovermode="closest",
            )
            _plot(figure, "history-chart")
            st.caption(
                "Hover for dates and revisions; drag to zoom, double-click to reset. "
                "Lines connect stored predictions, not intervening observations. "
                "Each outcome retains its original run's comparable "
                "adjusted-price basis."
            )
    except (BadRecord, ValueError):
        st.error("Bad record — chart values exceed a safe finite plotting range.")
    st.caption(
        "Signed error = actual − predicted; percentage error = 100 × "
        "(actual − predicted) / predicted. The denominator "
        "is the prediction; this is not MAPE."
    )
    st.dataframe(rows, hide_index=True, width="stretch")


def main(
    *,
    read: Query | None = None,
    now: datetime | None = None,
    page_size: int = PAGE_SIZE,
) -> None:
    st.set_page_config(page_title="Portfolio forecasts", page_icon="📈", layout="wide")
    st.title("Portfolio forecasts")
    st.caption("Published forecasts and allocations · read-only research demonstration")
    st.caption(
        "Reads are cached for up to 300 seconds. After expiry, the next interaction "
        "fetches data; there is no automatic background refresh."
    )
    read = read or read_query
    now = now or datetime.now(UTC)
    arguments: dict[str, Any] = {
        "p_limit": page_size,
        "p_cursor": None,
        "p_as_of": None,
    }
    try:
        first = read_page(read("pf_runs", arguments), arguments)
        if st.session_state.get("run-watermark") != first.as_of:
            st.session_state["run-watermark"] = first.as_of
            st.session_state["run-pages"] = [None]
        arguments.update(
            p_cursor=st.session_state["run-pages"][-1], p_as_of=first.as_of
        )
        page = (
            first
            if arguments["p_cursor"] is None
            else read_page(read("pf_runs", arguments), arguments)
        )
    except (BadRecord, Unavailable) as error:
        _failure(error, "published runs")
        return
    if not first.summaries:
        st.info(
            "No published runs yet. A completed batch must publish "
            "a portfolio before results appear here."
        )
        return
    st.caption(
        f"Latest published target: {first.summaries[0].target} · "
        f"Published: {timestamp(first.summaries[0].published_at)} · "
        f"Run page {len(st.session_state['run-pages'])} ({len(page.summaries)} runs). "
        "Dates group runs by forecast target; older pages "
        "can include more revisions of the same date."
    )
    _navigation(page, "run-pages", "runs")
    if not page.summaries:
        st.info("No runs on this page. Use Newer runs to return.")
        return
    dates = sorted({item.target.isoformat() for item in page.summaries}, reverse=True)
    target = st.selectbox("Forecast target date", dates)
    choices = {
        item.run_id: item
        for item in page.summaries
        if item.target.isoformat() == target
    }
    selected_id = st.selectbox(
        "Published run / revision",
        list(choices),
        format_func=lambda key: (
            f"Revision {choices[key].revision} · {choices[key].mode} · "
            f"{timestamp(choices[key].published_at)} · {key}"
        ),
    )
    assert selected_id is not None
    try:
        run = published_run(
            read("pf_run", {"p_run_id": selected_id}), choices[selected_id]
        )
    except (BadRecord, Unavailable) as error:
        _failure(error, "selected run")
        return
    _overview(run, now)
    ticker = st.selectbox("Ticker", sorted(run.header.universe))
    assert ticker is not None
    _detail(run, ticker)
    _history(read, ticker, first.as_of, page_size)
