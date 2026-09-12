# Engineering decisions

Established Milestone 0 decisions, 12 September 2026. Milestone 1 implementation
evidence is recorded below; later design choices are not claims of implemented
or empirically validated forecasting behavior. Sources are the
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
compatibility will be tested when its dependency is introduced in M2.
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
| Exact Python/uv/package versions and lock | M1 foundation verified; extend with each feature | Pinned metadata, locked install/build/import; native scientific backend checks remain M2 |
| Provider options, metadata, calendar compatibility | M2 | Official library semantics and deterministic adapter/session fixtures |
| Empirical model settings, blend, shrinkage, constraint sensitivity | M3 | Frozen chronological validation; final test remains untouched during selection |
| Numerical tolerances, conditioning thresholds | M3 | Small known problems, scaling/residual and degenerate-data tests |
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
