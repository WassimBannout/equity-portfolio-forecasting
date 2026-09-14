# Milestone 5 report

Completed 15 September 2026 (Asia/Beirut). **Milestone 5 only** is implemented,
verified and documented. Milestones 0–4 were treated as the established baseline
at HEAD `f8955a6e1b7700aaea4ee6144b538063c0ca5a96`. Changes remain uncommitted;
no commit was requested. **Milestone 6 has not started.**

Before implementation, read the architecture, decisions, implementation plan,
coverage matrix, M4 report, relevant supplied product/behavior/ML/architecture/
correction/rebuild documents and the established implementation. No persistence
or scientific blocker required a baseline redesign. The preexisting untracked
`specifications/` directory is preserved unchanged.

## Functionality and requirements satisfied

| Assigned requirement / acceptance | Implemented functionality and evidence |
| --- | --- |
| F05; first-run and failure safety | Separate no-published-runs, pending-outcome, incompatible-outcome, bad-record and service-unavailable states. A first complete run renders allocations, forecasts, stored metrics and a forecast chart. Invalid history does not remove valid portfolio views. Missing credentials are unavailable, not an empty database. |
| F11; coherent selected runs | Target-date selector plus exact published-run/revision selector, using the established target/publication/UUID order. Fetch one complete M4 aggregate; cross-check the selected summary, identity, membership, immutable payload, finite weights/budget/bounds and provenance before rendering any pie. |
| F11; historical retrieval | Independent 25-record run and ticker-history keyset pages. Forward/backward browsing retains deliberate revisions, including a date split across pages. Publication watermark is carried across requests; a refreshed first-page watermark resets navigation. No unbounded scan or implicit API row-limit truncation. |
| Behavior 10; S07 | Streamlit date/run and alphabetical ticker controls, Plotly allocation doughnut, numeric weight column, forecast-price/percentage-return table, selected-run observed/predicted/return metrics, interactive actual/forecast comparison, vertical-range control and per-prediction error table. |
| F06; exact outcomes and supported aggregates | Use only the stored exact-target comparable actual. Pending/incompatible values remain unavailable. Signed error is actual minus predicted, absolute error is its magnitude, percentage error divides by predicted. Page-scoped matched MAE/RMSE, last-price MAE and relative MAE use identical original-basis pairs and explicit counts. |
| S07; time and scientific meaning | Show target, observation cutoff, UTC run/completion/publication times, adjusted USD convention, Prophet version, configuration and source revisions, recorded settings and input/lock hashes. Older selection retains its own stored actual. Dated history preserves original observation dates and values. |
| S04; allocation interpretation | Display the recorded floor, effective ceiling, risk aversion, total allocation and fully invested policy, including all-negative forecasts. Explain that a floor does not ensure diversification. |
| F05/F12; chart validation | Check finite positive chart inputs, overflow and degenerate ranges. Bounds expand to cents to match slider precision. Equal handles withhold the chart with guidance. Date-only ticks use recorded targets, with padded day bounds for a single session; no invented intraday or weekday observations. |
| D03/D04/D06/D08; read-only boundary | Retain Streamlit, Plotly as the only dashboard plotting library and existing Supabase RPCs. Reader preflight rejects writer/admin roles, and a read-operation allowlist excludes mutation. UI rerun spies forbid model/provider/solver/write work. No custom frontend, separate application API or new production service. |
| F07/F12/S06; verification | Independent locked additions, full unchanged baseline regression, new offline AppTest/contracts/cache cases, native twelve-fit batch-to-database-to-Streamlit path, actual Chrome interactions and a fresh installed-wheel dashboard render. |

All assigned Milestone 5 acceptance scenarios in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) are satisfied. The
[coverage matrix](SPECIFICATION_COVERAGE.md) records the M5 portions without
claiming M6 hosted or prospective operating evidence.

## UI and data-contract decisions

The date control explicitly means **forecast target date**, not execution date.
The adjacent selector chooses an exact complete run and scientific revision.
Run summaries and history each have 25 records per page; different attempts are
never combined into a portfolio. A full 12-asset aggregate renders even when the
native test PostgREST server is configured with a three-row ordinary response cap.

The historical panel browses all available predictions for the selected ticker,
independently of the selected run. It queries inclusive target bounds
0001-01-01 through 9999-12-31 and presents one bounded page at a time. Captions
identify actual page dates, counts and additional older history. Aggregate metrics
cover **matched predictions on the current page only**. Deliberate revisions
count separately; no independent-session or complete-history aggregate is implied.

The baseline for each matched forecast is its own stored cutoff observation.
A zero baseline MAE yields **Undefined**, including when both methods are perfect.
This explicit display-denominator policy does not change the M3 research metrics.
No pending value, invalid price, missing weight or absent metric becomes zero.
Forecasts remain visible when actual outcomes are unavailable. The source outcome
must retain M4's exact-target and unchanged-overlap adjusted-price provenance.

The Streamlit data cache has a 300-second TTL, at most 128 entries and no persistent
disk cache. Credentials, function and arguments participate in cache keys. A cache
miss first verifies an anonymous/authenticated database role. Expiry requires a
subsequent interaction; there is no background refresh promise. The publication
watermark is not a cross-page MVCC/outcome snapshot. Run and history reads can
have different cache ages within the disclosed interval, and no cross-query
scientific rows are joined.

For live records, freshness compares the target with the latest already-opened
XNYS session at render time. Retrospective results are explicitly labelled as
research. This supplies the M5 visible freshness context without adding M6
scheduling, missed-run monitoring or operational alerts.

Dependency additions are **Streamlit 1.63.0** and **Plotly 7.0.0**. The lock expands
from **55 to 78 packages**, with no removed packages. All prior direct scientific
and quality pins remain unchanged. Streamlit's `websockets<17` constraint requires
the sole changed existing transitive version: **17.1 → 16.1.1**. Full scientific,
database and installed-package regression passes verify this resolution. Altair,
PyDeck, Starlette and Uvicorn are framework dependencies; the application uses
Plotly alone and introduces no separately operated API.

Decisions are recorded in [ADR-015](DECISIONS.md#adr-015--milestone-5-read-only-presentation).
The [UI guide](docs/DASHBOARD.md) documents usage, states, cache semantics, metric
scope, permissions and demonstration reproduction.

## Files and components changed

| Files | Purpose |
| --- | --- |
| `streamlit_app.py` | Repository Streamlit entrypoint |
| `src/portfolio_forecasting/dashboard.py` | Bounded cached reads, run/ticker navigation, validated presentation, charts, metrics and state messages |
| `src/portfolio_forecasting/dashboard_data.py` | Reader role/operation boundary, complete-run/page/asset contracts, formatting, error arithmetic, chart bounds and freshness |
| `tests/dashboard_fixtures.py`, `tests/test_dashboard.py` | Deterministic RPC fixtures and 44 offline M5 cases, including Streamlit interactions |
| `integration/test_dashboard.py`, `integration/dashboard_app.py` | Two real-database M5 tests and a disposable native-PostgREST demo entrypoint |
| `scripts/milestone5_browser.py` | Optional explicit Chrome hover, session-axis, slider and native drag-zoom check |
| `pyproject.toml`, `uv.lock` | Actual UI dependencies; include the entrypoint in strict typing; narrow untyped Plotly import boundary |
| `scripts/package_smoke.py` | Preserve all prior installed-package checks and add a real installed Streamlit unavailable-state render |
| `docs/DASHBOARD.md`, `docs/examples/milestone5/` | State/data-contract guide, representative screenshots, rendered tables/metrics and browser evidence |
| `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `IMPLEMENTATION_PLAN.md`, `SPECIFICATION_COVERAGE.md`, this report | Current status, decisions, coverage and exact verification evidence |

The final task consists of 23 changed/new files, including two PNG screenshots.
All **48** baseline files captured before implementation are byte-identical:
**21 source modules, 15 test files, 3 integration files, 2 SQL migrations and
7 specifications**. No existing scientific/persistence module, migration, prior
test, workflow, service configuration or M0–M4 report changed.

## Commands and exact final results

Commands ran from `/home/wassim/code/portfolio-forecasting`.
`PINNED_UV` below means the exact executable
`/home/wassim/.cache/uv/archive-v0/7S7aC_6BQ3jtOceC_r9uG/uv-0.12.13.data/scripts/uv`.
Verification logs and hash manifests are retained in ignored
`artifacts/milestone5/verification/`; optional browser outputs are in
`artifacts/milestone5/demo/`, with selected evidence copied into the repository.

| Final command / operation | Exact result |
| --- | --- |
| `PINNED_UV add 'streamlit==1.63.0' 'plotly==7.0.0'` | Exit 0; 78 packages resolved, 23 added package identities, one existing transitive version changed; existing direct pins retained |
| `make check UV=PINNED_UV` after the final session-axis correction | **Exit 0**; `Resolved 78 packages in 0.70ms`; `All checks passed!`; `76 files already formatted`; `Success: no issues found in 52 source files`; **`343 passed in 168.17s (0:02:48)`** |
| `M5_RECORD_DEMO=1 M5_BROWSER_PYTHON=/tmp/portfolio-m5-browser/bin/python make database-smoke UV=PINNED_UV` after the final correction | **Exit 0; `29 passed in 78.24s (0:01:18)`**; all 27 existing database cases plus 2 M5 cases, with real Chrome checks and fresh screenshots enabled |
| `make package-smoke UV=PINNED_UV` after the final correction | **Exit 0**; sdist/wheel, fresh hash-locked runtime-only environment, all five PASS messages below |
| `PINNED_UV venv /tmp/portfolio-m5-browser`; `PINNED_UV pip install --python /tmp/portfolio-m5-browser/bin/python 'playwright==1.58.0'` | Exit 0; optional temporary driver installed with four packages; no project dependency or browser download added |
| Chrome test in the final database gate | **PASS**; target-axis label exactly `2026-09-08`; actual hover includes price/run/revision; slider range `[122.91, 136.09]` → `[122.92, 136.09]`; native drag zoom narrows the range; `browser_errors: []`; Chrome **151.0.7922.137** |
| Python SHA-256 baseline and dependency audit | PASS; all 48 baseline files unchanged; only existing transitive `websockets` changes version; no removed lock packages; HEAD unchanged |
| `.venv/bin/ruff check .`; `.venv/bin/ruff format --check .`; `git diff --check` after report completion | Exit 0; `All checks passed!`; `77 files already formatted`; no whitespace errors |
| `.venv/bin/python artifacts/milestone5/verification/final_audit.py` | PASS; 23 task files; 48 baseline files unchanged; 11 tested-input hashes unchanged; 148 local links resolve across 18 Markdown documents; demonstration source/lock match the final implementation |
| Process search for disposable database and integration Streamlit commands | No matching processes; `rg` exit 1 means no matches; fixture/browser cleanup completed |

Installed-package output:

```text
PASS: sdist/wheel, locked runtime-only install, isolated request resolution
PASS: installed wheel real offline Prophet backend fit/predict
PASS: installed wheel SciPy known optimum and research reporting import
PASS: installed wheel Supabase publication contracts and CLI imports
PASS: installed wheel Streamlit dashboard and safe unconfigured render
```

The final total is **372 passing tests**: **326 unchanged M1–M4 cases**, plus
**44 M5 offline cases and 2 M5 real-database cases**. The browser interactions and
isolated package smoke checks supplement that count. No old test was removed,
weakened or skipped to obtain a pass. No implementation changed after these final
gates; subsequent work only completed documentation and refreshed copied evidence.

Initial development failures were resolved rather than reported as passing:
Ruff/type diagnostics; a test timer targeting the wrong installed Streamlit
attribute; the browser helper reading SVG with an HTML-only accessor; slider
endpoint quantization; and an outdated Plotly modebar selector. The browser now
tests native mouse-drag zoom. The final visual audit also identified single-target
subsecond axis labels, which were corrected with explicit session ticks and a
regression assertion before rerunning all gates. Earlier **343/29/package** passes
and the **2 passed in 13.87s** browser run precede that final correction and are not
substituted for the final evidence above.

The environment's sandbox helper failed before execution with
`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`; necessary commands
used approved escalation. Native database startup can emit existing migration
escape-sequence warnings, and AppTest can emit Streamlit's bare-mode context
warning. These did not fail the gates; no unrelated baseline fix was introduced.

## Tests and representative demonstration

Offline tests cover no runs/missing credentials, first published run, one ticker
without outcomes, exact error/price/percentage arithmetic, numeric allocations,
missing/nonfinite/invalid weights, truncated/mixed run responses, malformed dated
history, incompatible/wrong-target outcomes, unavailable history, deterministic
revision/date selection, both paginators across 27 runs, old-run metrics with
all-history labels, page watermark/coverage/order/ticker checks, cache reuse/expiry
and credential isolation, expiry resetting navigation, constant/extreme/collapsed
chart ranges, date-only single-session ticks, missing provenance, reader-role
denial, and forbidden model/provider/solver/write work on UI reruns.

The fresh native database path uses a controlled twelve-asset dated fixture,
**twelve actual Prophet fits**, allocation, durable publication, anonymous complete
reads and Streamlit rendering. It observes the first pending render, adds a later
comparable exact-target snapshot, then verifies the rendered actual/error metrics
and original historical dates. Reader reruns create no new batch attempt. The
existing database suite also retains atomicity, role denials, concurrency/retries,
revision/basis validation, twelve-asset CLI computation, deadline, and actual
backup/restore checks.

The [recorded demonstration](docs/examples/milestone5/README.md) includes two
screenshots, browser interaction results and exact rendered values from the new
app. The final demonstration's source and lock hashes are verified against the
final implementation. Its short-history/two-return risk settings and disabled
yearly seasonality are explicit synthetic retrospective fixture settings; the
production defaults remain unchanged. No live market or investment result is
claimed from this demonstration.

## Known limitations and deferred work

- Hosted Supabase gateway/Auth provisioning, deployment, scheduling, HTTPS,
  monitoring, operational freshness alerts, public data-use arrangements and
  prospective runs/matured outcomes remain **Milestone 6**. Only disposable
  PostgreSQL/PostgREST and loopback Streamlit/Chrome were used here.
- History diagnostics summarize one visible page, and distinct revisions count
  separately. There is no full-history aggregate, as-of research mode or statistical
  independence claim. Wider historical browsing uses the existing page controls.
- Publication watermark and cache TTL do not freeze outcome vintages across
  queries. On an uncached outage, the UI reports unavailable; no hidden stale-data
  fallback is labelled as fresh. Cache expiry is not a background refresh.
- Original-basis outcome compatibility remains the conservative M4 policy.
  Incompatible corporate-action or provider revisions stay unavailable; the
  dashboard never resizes prices or manufactures a comparison.
- The verified browser environment is Linux x86-64 with the recorded Chrome
  version. The optional browser script expects that local binary and a temporary
  Playwright installation; ordinary offline tests do not require either.
- General accuracy, diversification or investability is not established by UI
  correctness. The existing M3 baseline-relative research evidence remains the
  measured scientific assessment.

**Milestone 5 is the stopping boundary. Do not proceed to Milestone 6.**
