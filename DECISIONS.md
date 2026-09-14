# Engineering decisions

Established Milestone 0 decisions, 12 September 2026. Milestone 1–5 implementation
and measured research/database evidence is recorded below; later design choices are not
claims of implemented behavior. Sources are the
supplied [specification package](specifications/PROJECT_SPEC.md) and its classified
[recommendations](specifications/IMPROVEMENTS.md). Implementation status is in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## ADR-001 — Preserve supplied milestone numbering

Decision: Milestone 0 means preparatory design, coverage review, README, and basic
repository housekeeping. The source plan defines only Milestones 1–6. The user
explicitly confirmed this scope after clarification; the separate foundation
milestone remains future work. No application modules,
dependency installs/lock, CI, data downloads, migrations, or deployment in M0.

Consequence: this milestone produces a reviewable engineering starting point,
not a runnable forecasting application. Do not renumber the source milestones.

## ADR-002 — One package, batch and dashboard, one durable service

Decision: retain Python, independent Prophet refits, SciPy mean-variance allocation,
Supabase, Streamlit, the daily/manual Actions job, and a modest supervised VPS.
The computation interface is independent of database publication. Define typed
records at actual boundaries and add modules when needed.

Reason: this directly covers the single-operator, twelve-asset daily workload
(D01–D08). Extra API services, queues, distributed training, a frontend rewrite,
brokerage, and multi-user features have no requirement. No current evidence
justifies adding concurrency or model serialization.

## ADR-003 — Resolve time explicitly and enforce a pre-open live deadline

Decision: capture execution time in UTC per invocation; retain separate requested
date bounds, observed session cutoff, next exchange-session target, and publication
time. Use a real exchange schedule, including closures and early closes. A normal
live run must target that market day's upcoming session and publish before its
opening. Historical execution is explicitly retrospective. Closed-market requests
are no-ops; elapsed/stale live requests fail visibly.

Reason: F01/F13 require meaningful targets and delayed-job handling. A pre-open
deadline is a deliberately stricter policy than merely checking that the target
close has not passed: it gives the intended morning product a consistent issue
window and prevents incomparable intraday releases. Recheck after computation so
a slow fit cannot publish past the deadline. A future intraday mode would require
its own timing/evaluation contract; it is not implemented by relaxing this guard.

## ADR-004 — Explicit adjusted prices, full universe, no silent filling

Decision: start with explicitly adjusted daily close for the configured USD
US-listed securities, as required by F14. Validate identity/currency and session
compatibility, positive finite dated observations, full membership, and contiguous
common sessions before return computation. Keep the initial price. Reject missing
required data after bounded transient retries; never impute a closure or hide a
ticker exclusion. Save immutable input snapshots with retrieval/settings hashes.

Reason: F03/F14 correct changed-universe recommendations, mixed return intervals,
and unrepeatable data revisions. Strict rejection trades availability for an
explainable fixed-universe result. A future exclusion or gap policy must be
explicitly configured and evaluated. Price adjustment and source access do not
establish permission for public redistribution; resolve the actual intended use
before deployment, as the supplied specification requires.

## ADR-005 — Separate risk-history and seasonal-history gates

Decision: require 252 realised returns (at least 253 consecutive session prices)
for normal risk estimation. Initially require two calendar years of price history
when yearly seasonality is enabled. Preserve weekly/yearly on, daily off and
holiday effects as the initial reference configuration; record all effective
Prophet settings. Shorter evaluation settings must be explicit and cannot silently
alter live production requirements.

Reason: the source plan asks for separate configurable history gates without
fixing an annual-seasonality threshold. Two annual cycles are a conservative
initial engineering choice, not a claim of statistically sufficient predictive
signal. Validation experiments in M3 can justify a simpler component configuration
or different documented threshold (S01). Always keep known future holiday events
through the forecast horizon when that component is enabled.

## ADR-006 — Correct expectations and risk; retain the optimisation family

Decision: `mu` initially equals direct fractional forecast returns; covariance is
sample covariance of observed single-session returns only. Retain
`mu.T @ w - (lambda / 2) * w.T @ covariance @ w`, lambda 5, full investment, and
5%/100% bounds. Require finite positive lambda for the initial supported policy;
zero or negative lambda is rejected rather than introducing a separate risk-neutral
expected-return-only allocation mode. Use SLSQP with explicit numerical criteria and independent
output checks; singular valid covariance can have nonunique solutions.

Reason: F02 explicitly requires correcting synthetic risk contamination and
accidental forecast dilution. F03 requires feasibility and numerical validation.
Direct expectations preserve the forecast-to-allocation feature but may be noisy.
Compare blends, observed-only historical expectations, equal weights, and optional
shrinkage on earlier validation data (S02–S04); no alternative is presumed better.
Keep the 5% default and explain its 45% effective cap for twelve assets.

## ADR-007 — Scientific request identity and atomic complete publication

Decision: use a stable request key and one shared run ID, with separately recorded
attempt time and explicit scientific revision. Bind the first captured immutable
dataset to the logical request; retries reuse that identity/input. Different
scientific payloads cannot silently overwrite a published run. Use Supabase
uniqueness constraints and a transactional publication operation; expose only
complete published runs. Retain missing/failed states without displacing prior
success, and reject absent outputs instead of defaulting them to zero.

Reason: F04/F10 require retry safety and coherent portfolios. An atomic database
operation handles the small result without a queue. Storage policies must enforce
reader/writer separation and be tested against a real disposable database in M4.
The exact SQL is deferred until that milestone; no recovered schema is assumed.

## ADR-008 — Match exact target outcomes and evaluate chronologically

Decision: join actual observations by ticker and exact target session, with
comparable price convention and recorded revision provenance. Missing/incompatible
outcomes stay unresolved. Preserve the specified signed error and prediction-based
percentage denominator with honest labels. Use frozen chronological evaluation,
earlier-only model selection, a separate final test, identical baseline pairs,
and explicit counts/exclusions. State fixed-universe and revised-data limitations.

Reason: F06 forbids substituting the next available run for the correct horizon.
Low dollar price error is not allocation value. A paper return must begin at an
execution time after the signal exists; include drifted holdings and costs before
claiming executable performance. Outcomes across corporate actions need a tested
basis-reconciliation policy in M4; don't invent that evidence in M0.

## ADR-009 — Keep the dashboard simple and honest about available information

Decision: retain Streamlit and one plotting library. Select a complete run;
independently paginate ticker history. Preserve the useful date/asset controls,
allocation doughnut, price/return metrics, interactive chart/range control, and
individual error table; add numeric weights, cutoff/target, adjusted-price label,
freshness, and all-history scope. Use a 300-second cache with explicit semantics.
Handle empty, first-run, pending, bad-data, and unavailable states independently.

Reason: F05/F11/S07 concern correct data and understandable UI, not a framework
limitation. A normalised pie must not conceal missing assets. Browser reruns never
fit models or retrieve market data. No as-of research mode is required initially.

## ADR-010 — Locked Python environment and one CI provider

Decision: in M1, use `uv`, one tested Python minor, a committed independent lock,
pytest, Ruff lint/format checks, mypy, and package build/install checks. The foundation now verifies Python
3.12.14, uv/uv_build 0.12.13, tzdata 2026.4, pytest 9.1.1, Ruff 0.16.7, and
mypy 2.3.1 on Linux x86-64. Dependencies arrive with the code that
uses them. Do not install notebooks or multiple plotting/formatting tools by habit.

Use GitHub Actions for the one quality gate as well as the future schedule/release.
This exercises the specification's optional CI consolidation (O02). The repository
is empty, so there is no working CircleCI configuration to migrate. One provider
reduces account administration and makes the exact-tested-revision release
dependency straightforward. `uv` provides the simple locked workflow permitted
by S06; there is no existing Poetry environment to preserve or migrate.

Reason: F07/F08/F12 require reproducible installation and a non-modifying gate.
These are maintainability choices, not claimed forecasting improvements. Foundation
lock/tool and sdist-to-wheel installation checks now pass. Native Prophet
compatibility is now verified by M2 offline fits and installed-wheel checks.
Development fixture tests are offline; a successful live-provider check is never
a prerequisite for ordinary unit CI. Database/model/UI integration tests are added
when those contracts exist.

## ADR-011 — Simple supervised deployment and explicit recovery

Decision: a locked virtual environment on a modest VPS, non-root systemd dashboard
service, HTTPS reverse proxy, restricted deployment identity, checked SSH host
key, immutable action pins, and release of an exact passing revision. Retain a
previous working release for automatic recovery after a failed readiness check.
Schedule daily at 09:00 UTC with manual rerun, overlap control, bounded timeouts/
retries, no-op states, and session-aware freshness reporting. Record shared run
IDs, durations, data counts, solver residuals, and publication outcome.

Reason: F08/F09/F13 and S05 need a reproducible operating procedure, not Kubernetes.
Docker (O01) remains deferred unless native dependency/host portability problems
justify it. Database retention and backup/restore drills belong in M4/M6. Real
host/domain credentials and prospective observation time are external inputs;
this design makes no deployment or uptime claim.

## Deferred choices and evidence required

| Choice | Resolve in | Evidence required |
| --- | --- | --- |
| Exact Python/uv/package versions and lock | M1 foundation verified; extend with each feature | Pinned metadata, locked install/build/import; M2 native Prophet installation/fit verified |
| Provider options, metadata, calendar compatibility | M2 implemented | Pinned API inspection, real offline yfinance parser fixtures, session/holiday checks |
| Empirical model settings, blend, shrinkage, constraint sensitivity | M3 resolved for this study | ADR-013 and frozen chronological comparison; broader evidence remains limited |
| Numerical tolerances, conditioning thresholds | M3 implemented | ADR-013; known cases, scaling, independent optimality gap and sensitivity evidence |
| Corporate-action outcome basis and executable paper prices | M3/M4 | Documented data conventions and deterministic adjustment/timing examples |
| Exact schema, policies, snapshot retention | M4 | Real provision/insert/read/permission/idempotency/restore checks |
| Actual host, domain, service credentials, provider display rights | M6 | Operator's new authorised services and resolved intended data use |
| Public operational success | M6 | Healthy exact release, recovery drills, prospective runs and matured outcome |

Optional dedicated QP solver (O03), intervals/fitted models (O04), and additional
models/parallel fitting (O05) remain deferred unless evidence demonstrates their
specific value. No optional feature is a prerequisite for the required product.

## Milestone 1 implementation notes

These implement the existing decisions; no overall architecture choice was reopened.

- Frozen standard-library dataclasses provide the small typed validation boundary.
  They reject invalid values at construction, detach ticker lists, and keep secret
  settings separate. No settings framework or application service was necessary.
- The pinned tzdata runtime dependency supplies New York rules directly through
  ZoneInfo.from_file. This avoids depending on an independently updated host
  timezone database while implementing ADR-003's exchange-local default date.
- Full-universe enforcement and at most three download attempts are validated
  policy settings only; provider calls, retries, actual history checks, and
  session eligibility still belong to M2/M6.
- The independently generated lock includes the runtime and development graph.
  uv_build is pinned to the uv tool version; a fresh runtime-only smoke check
  uses hash-verified exported requirements and a wheel built from the sdist.
  No scientific libraries are installed before there is code to use them.
- CI uses verified immutable official checkout/setup-uv revisions, read-only
  repository permission, no persisted Git credentials and no application secrets.
  This establishes the quality workflow, not a deployment or scheduler.
- The supplied handoff exists under specifications/, not to_keep/. Git's local
  info/exclude was hiding it. Narrow .gitignore exceptions now make the unchanged
  handoff trackable so fresh checkouts can retain the existing design links.
  No Git metadata or original handoff content was changed.

Tool behavior was checked against the
[uv build backend documentation](https://docs.astral.sh/uv/concepts/build-backend/)
and [uv Actions integration](https://docs.astral.sh/uv/guides/integration/github/).
Interpreter support was checked against the
[Python support table](https://devguide.python.org/versions/); actual foundation
compatibility is supported by the local tests and package installation, not by
a claim that future scientific libraries were already exercised.

## Milestone 2 implementation notes

These implement ADR-002–005 and ADR-010; no settled architecture was redesigned.

- The tested additions are yfinance 1.7.0, exchange-calendars 4.13.2, pandas 3.0.5,
  NumPy 2.5.3, Prophet 1.4.0, and development-only pandas-stubs 3.0.5.260730.
  The existing Python, uv, tzdata, pytest, Ruff, and mypy pins remain unchanged.
  Prophet uses the wheel's bundled CmdStan model through cmdstanpy 1.3.0.
- `auto_adjust=False` plus explicit `Adj Close` selection preserves adjusted-close
  semantics. Daily interval, inclusive/exclusive bounds, no repair/back-adjustment,
  retained missing rows, no rounding/prepost, timeout, and raised errors are explicit.
  Cached chart metadata validates symbol, USD equity type, NYQ/NMS/NGM/NCM listing,
  New York timezone and daily granularity. The pinned calendar aliases NASDAQ/XNAS
  to XNYS. Other listing codes fail until deliberately supported.
- The installed yfinance still supports per-call `raise_errors=True` but deprecates
  it. A warning filter matches only that known deprecation inside the call; global
  yfinance exception settings are not changed. Application retries cover timeouts,
  connection errors, rate limiting, HTTP 429/5xx, and its explicit temporary-outage
  error, up to the configured maximum of three attempts. Each exponential delay is
  capped at 30 seconds. Malformed/empty inputs and permanent errors fail immediately.
  Authentication/network retries within yfinance are not counted as application
  attempts. A process-wide wall-clock deadline remains an operational M6 concern.
- Session planning returns a closed-market no-op before retrieval, rejects live
  requests at or after opening, and checks the same deadline after fitting.
  Histories must cover the complete requested consecutive session range; there is
  no silent intersection, repair, truncation, filling, or reduced universe.
- Regular XNYS holiday names retain stable normalized labels and ±1 calendar-day
  windows. Event generation includes target + 1 so a following holiday's negative
  window can affect the target. Future exceptional closures are conservatively
  omitted from model features without announcement-time evidence. The calendar
  remains an ex-post schedule for retrospective requests, explicitly disclosed.
- Prophet retains linear growth, additive yearly/weekly/holiday components, daily
  off, 25 requested changepoints over 80% of history, and 0.05/10/10 prior scales.
  Fitting explicitly uses LBFGS MAP, seed 42, at most 10,000 iterations, recorded
  tolerances, and no hidden Newton fallback. Unused uncertainty draws are disabled
  (`uncertainty_samples=0`); this changes no point-forecast requirement. There is
  no model selection or accuracy claim. Resolved changepoints/seasonalities and
  holiday events are recorded with every asset forecast.
- Content-addressed local JSON stores the actual normalized dated model inputs.
  Atomic hard-link creation prevents overwriting an existing snapshot; reads verify
  its SHA-256 and revalidate the calendar/data. Data hashes distinguish revised
  prices while whole-snapshot hashes also capture retrieval/software context.
  Offline replay requires matching implementation and scientific versions and is
  labelled as replay even when the captured request was live. Publication identity
  and durable storage remain ADR-007's M4 work.
- Narrow untyped-library import boundaries retain strict checking of project code.
  Tests prohibit network access and include the actual yfinance parser and real
  Prophet fits. The existing packaging check now verifies a real native fit from
  an installed wheel without development dependencies.

Sources consulted were the [yfinance history reference](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html),
[Prophet holiday documentation](https://facebook.github.io/prophet/docs/seasonality,_holiday_effects,_and_regressors.html),
[exchange-calendars source and aliases](https://github.com/gerrymanoim/exchange_calendars),
official PyPI package metadata, and the installed versions' source. The installed
source inspection and offline tests resolve behavior that current online documents
alone cannot establish. Full limitations are in
[the M2 assumptions](docs/MARKET_DATA_AND_FORECASTING.md).

## ADR-013 — Milestone 3 numerical and research evidence

Decision: retain the established architecture, Prophet, direct expectations,
observed-only 252-return sample covariance, SLSQP, lambda 5 and 5%/100% default
bounds. Add the independently checked allocation and callable composition.
No contradiction in M0–M2 required redesign or source changes.

SLSQP uses analytic derivatives, positive objective scaling, `ftol=1e-12` and
`maxiter=1000`. Budget/bound tolerance is `1e-9`; symmetry/PSD tolerance is
`1e-10` relative to a magnitude floored at `1e-12`. Valid singular PSD matrices
remain supported; no eigenvalue clipping or solver fallback is introduced.
A separate exact linear oracle bounds the concave objective's suboptimality by
`1e-6 * objective_scale`; output is neither clipped nor normalized. Known optima,
scale/permutation checks, fake solver failures and degenerate cases justify these
choices. Conditions and sensitivity are reported instead of rejecting matrices
by an unvalidated condition-number cutoff. SciPy 1.18.1 is the sole new resolved
package; Matplotlib 3.11.2 was already installed through Prophet and is now a
direct declared dependency because M3 writes standalone figures.

Before running the study, [the declaration](experiments/milestone3.json) fixed
2024-01-01–2026-02-27 training, March–June 2026 validation and July 1–September 3
2026 final reporting. Five Prophet variants and seven allocation profiles were
bounded in advance. Origins occur every five sessions to limit native refit cost;
all intervening holding sessions are included. We retained the actual dated M2
Yahoo snapshot and its retrieval/software provenance locally. Current-universe,
revised adjusted-close and ex-post calendar limitations remain explicit.

Each origin constructs past-only model/risk inputs and calculates all forecasts
and weights before retrieving target outcomes. The immutable validation/selection
artifacts precede final-test fitting. Model selection requires over 5% lower
validation macro relative MAE; allocation selection requires over 0.001 higher
net cumulative research return, with declaration-order ties. Final outcomes
cannot reselect candidates. The reference/direct policy remains the callable
product default; research selection does not silently rewrite stable settings.

Measured decision evidence from [the full comparison](docs/examples/milestone3/MODEL_SELECTION.md):

- All 17 validation and 9 final-test origins succeeded for all 12 assets; no
  candidate exclusion or solver failure occurred. Validation reference price MAE
  was 3.997361 times last price; every tested Prophet alternative was worse.
  Retain the reference Prophet and report the weak result. No new model is added.
- Alpha 0.25 improved validation net research return from 4.3687% to 8.9629%, but
  the predeclared 20% cap won at 11.8076%. Lambda 1/10 returned 3.8825%/4.5562%;
  removing the floor returned -5.9035%. The selected policy keeps alpha 1,
  sample covariance, lambda 5 and the 5% floor with cap 20%.
- Diagonal shrinkage improved mean covariance condition from 26.3004 to 18.0490,
  while worst +1 bp expectation-shock L1 weight movement was 0.04544 versus
  0.04501. Validation net return was 4.5401%, a small improvement over direct
  that did not win. Do not add a more elaborate estimator or new solver.
- The locked cap policy's final-test net research return was 5.7162%, compared
  with direct -0.0881%, equal weights 7.7733%, and historical-only/direct -2.2475%.
  Final-test Prophet MAE remained 2.599968 times last price. These results show
  no convincing forecasting or allocation advantage over the simple baselines.
  The final split/candidates were not changed after inspecting this result.

Accounting uses target-close execution and subsequent close returns, with
pre-trade drifted holdings, L1 turnover and 10+5 bps costs. Costs are charged on
the first rebalance from equal weights; there is no terminal liquidation charge.
The declared zero risk-free rate is used only for a descriptive Sharpe statistic.
This is adjusted-close research, not executable trading evidence. Short samples,
fixed current universe, unavailable point-in-time vintages and selection noise
prevent general claims or automatic production-policy promotion. Paper timing
is implemented; durable corporate-action outcome comparability stays in M4.

Primary references: [SciPy SLSQP](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html),
[NumPy covariance](https://numpy.org/doc/stable/reference/generated/numpy.cov.html),
and [Prophet cutoff diagnostics](https://facebook.github.io/prophet/docs/diagnostics.html).
Pinned source behavior and local deterministic tests resolve numerical details.

## ADR-014 — Milestone 4 durable publication

Status: accepted and implemented 14 September 2026; implements ADR-007/008 without
changing the established scientific or Supabase architecture.

- Keep all durable data in Supabase PostgreSQL. Exact content-addressed snapshot
  text is private in `pf_private.snapshots`, avoiding a separate object-store
  publication transaction. Size is bounded at 16 MiB; no fitted model storage.
- Use two checksummed SQL migrations and a psql administrator runner. The runtime
  uses standard-library HTTP to narrowly granted database functions; no SDK or new
  Python dependency is needed. Application roles cannot perform direct writes.
- Use a dedicated `portfolio_writer` JWT role and public/ordinary authenticated
  readers, with explicit schema/function ACLs and published-only RLS. The server
  receives a scoped access token and publishable API key, never a signing key or
  service-role key. Hosted issuer/gateway provisioning remains external.
- Hash a versioned logical request, canonicalizing JSON numeric scales and ticker
  order. Include current source/lock/Python and effective settings; exclude attempt
  clocks. Bind the first snapshot before fitting. Changed input needs an explicit
  revision; retries load the original input and published results remain immutable.
- Commit the complete portfolio and publication marker in one locked transaction.
  Keep durations and failures in separate attempts. Recheck the pre-open deadline
  before the final state transition; report success only after complete read-back.
- Retain immutable exact-target outcome vintages. Use conservative unchanged full
  overlap (`1e-8 + 1e-10 * abs(original_price)`) with equal provider/metadata/basis;
  do not infer split factors or rescale issued predictions. Incompatible outcomes
  withhold an actual value and preserve the source evidence.
- Return a selected run as one JSON aggregate; use bounded keyset pages for
  summaries/ticker history. No reader merges independently latest asset rows.
- Verify real PostgreSQL 16.15 and PostgREST 16.3 in disposable native processes,
  including twelve real Prophet fits, role denial, concurrent/lost-response
  retries, exact targets, and pg_dump/pg_restore. These are Supabase components,
  not a claim that a hosted Supabase gateway/Auth service was exercised.

The restore drill exposed reliance on implicit public-schema usage; explicit
usage grants now survive clean restoration. [The persistence guide](docs/PERSISTENCE_AND_PUBLICATION.md)
and [M4 report](MILESTONE_4_REPORT.md) contain commands, limitations and evidence.
No alternate database, production API, queue, Docker or M5 UI was introduced.

## ADR-015 — Milestone 5 read-only presentation

Status: accepted and implemented 14 September 2026. Implements ADR-009 and the
assigned M5 scope without changing M1–M4 scientific or persistence components.

- Keep Streamlit and use Plotly alone for dashboard charts. The verified additions
  are Streamlit 1.63.0 and Plotly 7.0.0. The 78-package lock retains all previous
  direct scientific/tool pins. Streamlit requires `websockets<17`, so the existing
  transitive package resolves from 17.1 to 16.1.1; full prior tests verify compatibility.
  Altair and PyDeck are Streamlit dependencies but are not used by this dashboard.
- Use the M4 `pf_access`, `pf_runs`, `pf_run` and `pf_history` functions; accept only
  `anon`/`authenticated` roles and expose no mutation. The existing writer-capable
  store remains unchanged behind a dashboard read allowlist.
- Label date selection as forecast target date. Keep distinct revisions and the
  existing target/publication/UUID ordering. Fetch one complete selected aggregate
  and validate it before any allocation chart; never normalize an incomplete run.
- Browse run summaries and ticker history independently in 25-record keyset pages.
  State page coverage and the all-history browsing scope. Aggregate errors cover
  matched predictions on the displayed page only. Each revision counts separately;
  no unloaded history or independent-session count is implied.
- Keep exact-target errors and a last-price baseline on the same original-basis
  predictions. A zero baseline MAE produces an undefined ratio, including two
  perfect methods, instead of manufacturing a display ratio. This is an explicit
  UI denominator policy; the M3 research metric implementation is unchanged.
- Retain null outcomes and dated observations. Distinguish no runs, pending,
  incompatible, bad-record and unavailable states. Reject invalid scientific
  display values, range overflow and incomplete weights. Expand chart bounds to
  cents to match the USD slider, including constant/single-point series.
- Cache at most 128 queries for 300 seconds with connection credentials in the
  key and no disk persistence. Refresh occurs on the next access after expiry.
  Keep the M4 publication watermark and disclose that outcomes are not a frozen
  cross-page information snapshot. Show timestamps, retrospective/live freshness,
  Prophet/configuration/source revisions, price basis and history coverage.
- Verify offline Streamlit interactions, installed-wheel rendering, a twelve-fit
  synthetic batch through fresh PostgreSQL/PostgREST to Streamlit, and real Chrome
  tooltip/range/zoom interaction. Native test services remain disposable; no new
  production service, custom frontend, deployment or scheduling is introduced.

Primary implementation references were the installed pinned libraries and
[Streamlit cache semantics](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data),
[AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest),
[Plotly rendering](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart),
and [Plotly hover formatting](https://plotly.com/python/hover-text-and-formatting/).
Behavior is established by the local interaction/browser checks, not just by
current documentation. [M5 report](MILESTONE_5_REPORT.md) records exact results.
