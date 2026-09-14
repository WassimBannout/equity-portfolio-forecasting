# Milestone 5 recorded dashboard demonstration

Captured from the new Streamlit application on 14 September 2026 UTC
(15 September in Asia/Beirut) using a fresh
native PostgreSQL 16.15/PostgREST 16.3 fixture and Chrome 151.0.7922.137.
This is synthetic retrospective engineering evidence, not live market operation.

The controlled path prepares dated inputs for all twelve configured tickers,
fits twelve real Prophet models, allocates and publishes one complete run, and
renders it with anonymous reader access. A first render has no outcomes and still
shows both charts and the complete forecast/allocation table. A later synthetic
snapshot supplies comparable actuals for exactly 2026-09-08. No next-run join or
model fit is performed by the dashboard.

- [Portfolio overview screenshot](dashboard.png): one coherent twelve-asset run,
  numeric allocations, timestamps and revision.
- [Historical comparison screenshot](chart-range.png): matched target outcome,
  price/error metrics, actual session axis and adjusted vertical range.
- [Rendered values](rendered.json): AppTest evidence from both pending and matched
  stages, displayed metrics/tables, retained dates and source/lock revisions.
- [Browser results](browser.json): actual hover text, initial/changed/zoomed axis
  bounds, Chrome version and empty browser-error list.

The browser verified that the single-session axis labels only **2026-09-08**.
It changed the lower axis bound from **122.91** to **122.92** while the
upper bound remained **136.09**, then narrowed the range with a native Plotly
mouse drag. These observations supplement Streamlit's Python interaction tests.

The publication watermark is a pagination boundary, not an as-of outcome snapshot.
The fixture uses a two-return risk window and disables yearly seasonality for
its short synthetic training period; established production defaults are unchanged.
Screenshots retain recorded run IDs and retrospective labels. They contain no
connection credentials or privileged database data.

Reproduction commands are in [the dashboard guide](../../DASHBOARD.md).
Exact full-suite results and remaining M6 work are in
[the milestone report](../../../MILESTONE_5_REPORT.md).
