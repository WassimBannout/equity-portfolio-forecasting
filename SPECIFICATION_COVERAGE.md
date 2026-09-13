# Specification coverage review

Reviewed for Milestone 0 on 12 September 2026, after creating
[ARCHITECTURE.md](ARCHITECTURE.md),
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and
[DECISIONS.md](DECISIONS.md), and before adding the repository scaffold.

Result: every required feature and classified correction has a proposed owner
and acceptance check. No required feature is intentionally removed. **Design
coverage is not implementation completion:** the M1 foundation, M2 data/forecast path, and M3 allocation/evaluation are implemented;
application work in Milestones 4–6 remains pending. The user explicitly confirmed M0 as design documents,
coverage review, and minimal repository scaffold.

Only the supplied handoff was consulted. Its descriptions of defects are context;
its required corrections govern the proposed design.

## Milestone 1 implementation status

The original matrix below remains the design baseline. This status table records
only the M1 portions; no multi-milestone requirement is labelled fully complete
when its later behavior is still absent.

| Requirement | Implemented M1 portion and evidence | Remaining work |
| --- | --- | --- |
| F01 | UTC execution, one clock read per invocation, explicit exchange-local end, retrospective labeling; fixed-clock/midnight/DST tests | Actual session cutoff/target, holidays, freshness and pre-open deadline in M2/M6 |
| F03 | Immutable request validation, full-universe policy, strict finite settings, bound feasibility including 1/12/20/21 assets, separate configurable history gates; offline tests | Observed-data sufficiency/validity and solver validation in M2/M3 |
| F07 | Pinned interpreter/uv/build backend, independent uv.lock, frozen settings metadata, locked install and isolated package checks | Dataset/software run provenance and native scientific checks in M2/M4/M6 |
| F12 | Deterministic offline configuration/credential suite, strict typing, non-modifying lint/format gate, sdist/wheel/runtime-only check | Model/database/UI/full-path checks as their components arrive |
| F14 | Explicit adjusted-close/USD/XNYS settings and documented time/price/result vocabulary; unsupported conventions rejected | Provider metadata, actual snapshots/revisions and public data-use gate in M2/M4/M6 |
| S06 | Minimal runtime timezone dependency, separate developer tools, documented locked setup and non-modifying make check | Keep additions proportionate in subsequent milestones |
| O02 | Single GitHub Actions quality workflow using the local checks; immutable action revisions | Hosted execution/required-check settings depend on the repository service; release integration is M6 |
| D08 | Standard-library contracts, pytest/Ruff/mypy and the established Python tooling retained | Numerical/calendar libraries are introduced only when needed |

The authoritative M1 definition explicitly includes F14's convention contract;
its matrix milestone list is clarified below to include that M1 portion. D01–D07
remain architectural guardrails; no forecast, solver, dashboard, storage,
scheduler or hosting component has been substituted or prematurely implemented.
See [MILESTONE_1_REPORT.md](MILESTONE_1_REPORT.md) for commands and results and
[configuration contracts](docs/CONFIGURATION.md) for the shipped interfaces.

## Milestone 2 implementation status

M1's table above remains its historical boundary. M2 implements the following
portions; it does not complete requirements assigned across later milestones.
Evidence: [M2 report](MILESTONE_2_REPORT.md),
[contracts and assumptions](docs/MARKET_DATA_AND_FORECASTING.md), and the new offline
test modules. All original requirement IDs and future acceptance gates remain.

| Requirement | Implemented M2 portion and evidence | Remaining work |
| --- | --- | --- |
| F01 | XNYS cutoff/next-session target; closed-day no-op; before/after-fit opening deadline; weekend/holiday/year/DST/early-close tests; future holiday windows tested with real Prophet feature generation | Publication deadline recheck, scheduler/recovery evidence in M4/M6 |
| F03 | Strict complete-universe dated-price validation; gaps/duplicates/order/finiteness/freshness checks; 253-price risk gate and independent annual gate; observed-only return arithmetic | Covariance and solver validation in M3 |
| F07 | Expanded independent lock; tested native backend; request, source and package metadata; content/data hashes; immutable inputs and replay with declared numerical tolerance | Full released run/deployment provenance and operational evidence |
| F12 | Deterministic provider/parser, calendar, data, snapshot, CLI and pipeline tests; real offline Prophet refits; fresh installed-wheel native fit; original 118 M1 tests retained | Optimiser/evaluation/database/UI/full operational checks |
| F14 | Explicit adjusted-close and request semantics; selected security/currency/calendar metadata; timestamped dated snapshots; revised-input preservation and tamper detection | Point-in-time data availability, corporate-action outcome comparability, private durable storage and public-use gate |
| S05 | Shared attempt UUID in data/fitting/failure logs; ticker, attempts, counts, cutoff/target, snapshot and stage durations | Solver/publication diagnostics, monitoring and retention/backup/recovery |
| S06 | Used dependencies only; retained locked quality gate and strict project typing; optional plotting/model packages not added | Continue incremental dependency discipline |
| D01/D06/D08 | Fresh independent Prophet price fits; exchange calendar and simple observed returns; no alternate model or inference service | Preserve guardrails in later milestones |
| Behaviors 1–5 | Explicit times, callable forecast-only path, full ingestion/preparation/forecast outputs and inclusive dated recent history | Durable shared run identity belongs to M4 |
| Behavior 7 (M2 portion) | Complete forecast result or failure/no-op; local snapshots; manual JSON report and honest exit code; computation requires no database credentials | Allocation, publication and release coordination in M3/M4/M6 |

Independent scenarios now exercised include all twelve valid assets (real synthetic
Prophet demonstration), one failed required download, one usable price, Friday to
next session including a Monday holiday, revised inputs, and late/closed requests.
No test or artifact is presented as provider reliability, forecast accuracy, or
investment-performance evidence.

## Milestone 3 implementation status

M1/M2 tables remain historical records. M3 adds the portions below without changing
any original requirement ID, authoritative specification or later acceptance gate.
Evidence: [M3 report](MILESTONE_3_REPORT.md),
[contracts and tolerances](docs/ALLOCATION_AND_EVALUATION.md),
[experiment declaration](experiments/milestone3.json), and
[measured tables/figures](docs/examples/milestone3/MODEL_SELECTION.md).

| Requirement | Implemented M3 portion and evidence | Remaining work |
| --- | --- | --- |
| F02; Behavior 6 | Direct forecast returns and observed-only trailing 252-return sample covariance; hand arithmetic and forecast-risk independence tests | None for estimator correction |
| F03; Behavior 6 | Shape/finiteness/PSD checks, feasible fractional bounds, analytic-gradient SLSQP and independent residual/objective/gap validation; known/degenerate optima, 1/12/20/21 assets, singular/indefinite and injected failure tests | Publication and downstream payload checks retain later gates |
| F06; required ML evidence | Frozen dated real snapshot; predeclared disjoint periods; past-only origin panels; exact target pairs; locked selection before test; last-price/equal-weight/historical-only baselines; metrics, ties, common exclusions, lagged holding/cost arithmetic | Durable target/outcome association and corporate-action comparability in M4; dashboard metrics in M5 |
| S01 | Five bounded Prophet component/window/prior configurations evaluated on 17 common validation origins, then 9 held-out origins; Prophet retained despite worse-than-last-price error | Broader prospective/generalization evidence is not claimed |
| S02 | Explicit scaling/tolerances, analytic gradient, eigen/rank/condition/gap diagnostics; sample versus diagonal shrinkage and one-basis-point expectation sensitivity measured | Dedicated QP solver O03 remains deferred: no measured SLSQP blocker |
| S03 | Declared alpha 0.25 historical-mean blend compared with direct alpha 1; validation-only selection and recorded negative/comparative findings | No automatic live fallback or unvalidated default promotion |
| S04 | Lambda/floor/cap comparisons, effective 45% default cap, HHI, drifted turnover, gross/net returns, volatility/drawdown and zero-rate Sharpe | Dashboard explanation in M5; executable-price/prospective evidence remains absent |
| S05; Behavior 7 (M3 portion) | Complete callable forecast/allocation result; shared attempt logs, solver status/residuals/timing, post-allocation opening deadline, failure propagation | Durable publication/monitoring/recovery in M4/M6 |
| F07/F12/S06 | SciPy pin, explicitly used Matplotlib pin, expanded strict offline tests, full existing regression and installed-wheel native scientific checks; frozen data/config/source/version provenance | Later database/UI/deployment checks; local artifacts require retention |
| D01/D02/D06/D08 | Independent Prophet refits, mean-variance objective, SLSQP, simple observed returns/calendar, established Python tools retained | Preserve these guardrails through later milestones |

The real study accepted 17/17 validation and 9/9 final-test origins (12 assets;
204 and 108 pairs per model). The locked selection kept reference Prophet and
chose a research 20% cap. Final-test Prophet macro price-MAE ratio was 2.599968
against last price; selected net research return was 5.7162% versus equal weights
7.7733%. These are retrospective adjusted-close diagnostics, not investable alpha.
All prior source/tests and all seven authoritative documents remain unchanged.

## Product and behavior contracts

Sources: [PROJECT_SPEC.md](specifications/PROJECT_SPEC.md) and numbered sections
of [BEHAVIOR_SPEC.md](specifications/BEHAVIOR_SPEC.md). Owners below are proposed
responsibilities, not existing modules.

| Requirement | Architecture owner and design | Milestone | Acceptance evidence |
| --- | --- | --- | --- |
| Product scope/defaults | One configured twelve-asset demonstration, reference dates/risk/bounds/components, recommendations only | M1–M6 | Default-setting tests; scope review; no brokerage or individual account claims |
| Behavior 1: time/numbers/identity | UTC execution, separate session cutoff/target, shared run ID, unrounded fractional calculations | M1/M2/M4 | Fixed clock; session dates; finite numeric and serialization checks |
| Behavior 2: configuration/invocation | Validated request, runtime end resolution, callable computation without database writes, explicit publication credentials | M1/M2/M4 | Invalid inputs; injected clock; compute without DB credentials; publish failures return nonzero |
| Behavior 3: ingestion | Explicit yfinance adjusted daily data; full universe; bounded retries; immutable snapshots | M2 | Empty/partial/one-price/stale/malformed/revised provider fixtures |
| Behavior 4: alignment/context | Calendar-validated common prices before single-session returns; first price retained; dated 30-calendar-day context | M2 | Gaps, intersection/order/duplicates, 253-price risk minimum, inclusive context boundaries |
| Behavior 5: forecast/return | Independent Prophet refits and recorded settings; future holiday coverage; next-session target | M2 | Small real fit; Friday/holiday/year/DST cases; features and price-return arithmetic |
| Behavior 6: portfolio | Direct expectations, observed-only covariance, half-factor mean-variance objective, checked SLSQP solution | M3 | Known optima/numeric examples, risk independence, residuals, invalid/degenerate inputs |
| Behavior 7: orchestration/publication | Computation separate from publication, complete validation, explicit publication, correlated stages and honest exits | M2–M4/M6 | Fault injection, no partial success, stage diagnostics, read-back completeness |
| Behavior 8: storage | Run-owned assets/history, stable retries, explicit revisions, atomic publication, independent migrations | M4 | Real fresh DB, permissions, interrupted/concurrent writes, missing-value rejection |
| Behavior 9: retrieval/cache | Complete selected run, paginated summaries/history, deterministic revisions, 300-second cache | M4/M5 | More than one page, membership check, expiry semantics, no mixed portfolios |
| Behavior 10: presentation | Date/ticker selection, doughnut/numeric weights, forecast table, stored/predicted metrics, interactive range-controlled chart, error table | M5 | Empty/first/multiple/old-run UI, formatting, known errors, degenerate chart inputs |
| Behavior 10: history meaning | Selected run's actual-price metric, real session dates, explicit all-history ticker scope | M4/M5 | Exact target association across gaps; old-run detail and scope assertions |
| Behavior 11: automation/release | Daily 09:00 UTC/manual Actions, exact tested release, non-root HTTPS service, recovery | M6 | Eligibility/late/retry checks, clean-host deployment, revision/readiness and rollback |
| Required ML evidence | Frozen chronological evaluation, last-price and equal-weight/historical baselines, leakage control | M3 | Origin-cutoff assertions, held-out comparison, sample/exclusion counts and honest limitations |
| Reproduction/deployment | Independent lock, tested interpreter/native backend, migration/provisioning/runbooks, real operating evidence | M1–M6 | Fresh install; real model/database/UI integration; prospective runs and matured outcome |

## All MUST FIX corrections

Identifier authority: [IMPROVEMENTS.md](specifications/IMPROVEMENTS.md).

| ID | Design coverage | Milestone | Required check |
| --- | --- | --- | --- |
| F01 | Time/calendar contract, future holidays, pre-open live publication deadline | M1/M2/M6 | Weekday/weekend/holiday/year/DST, stale cutoff, late job and publication recheck |
| F02 | Separate forecast expectations and realised sample covariance | M3 | Changing forecasts changes expectations without changing covariance |
| F03 | Request, universe, history, feasibility, covariance and solution validation | M1–M3 | Nonfinite/empty/gapped/duplicate/infeasible cases; independent residual/objective checks |
| F04 | Stable request and bound snapshot, explicit revision, transactional complete publication | M4 | Retry/conflicting payload, concurrent/interrupted attempts, previous-success preservation |
| F05 | No-data/pending/invalid/unavailable UI states and guarded chart inputs | M5 | First run renders; absent pairs and bad history do not crash other views |
| F06 | Exact comparable target outcomes, chronological baselines, post-signal paper timing | M3–M5 | Gap matching, availability assertions, untouched test selection, metrics/timing arithmetic |
| F07 | Independent lock/tested toolchain, runtime dates, data/config/software hashes | M1/M2/M6 | Fresh locked install, fixed clock, frozen-input reproducibility within tolerances |
| F08 | Exact passing revision, provisioned service/HTTPS, serialised release/readiness/rollback | M6 | Clean-host and rollback drills; dependencies installed from lock |
| F09 | Restricted identities, verified SSH host, immutable action pins, minimal workflow permissions | M6 | Configuration review and non-root authorised deployment verification |
| F10 | Independent migrations/constraints, published-only reader and restricted writer, dated records | M4 | Real provision/insert/read and reader/writer denial tests |
| F11 | Paginated summaries/history and complete selected-run membership validation | M4/M5 | Page boundary cannot omit offered runs or conceal partial portfolios |
| F12 | Deterministic offline contract tests plus actual model/database/UI/full-path checks | M1–M6 | Non-modifying CI, declared tolerances, opt-in live provider checks |
| F13 | Eligibility, overlap/deadline/retry/timeout controls, last expected result and recovery | M4/M6 | Closed/late/repeated jobs, controlled provider/DB failure, freshness signal and rerun |
| F14 | Adjusted-price/currency/security semantics, immutable snapshots/revisions, deployment-use gate | M1/M2/M4/M6 | Provenance/revised-data fixtures; resolve intended public data use before deployment |

## SHOULD IMPROVE and optional work

| ID | Disposition | Milestone / evidence |
| --- | --- | --- |
| S01 | Compare bounded Prophet component/window/prior choices and last-price baseline | M3; chronological validation, retained final test |
| S02 | Explicit solver criteria/analytic gradient and conditioning diagnostics; test shrinkage when warranted | M3; known cases and measured sensitivity, retain simple reference |
| S03 | Evaluate explicit forecast/prior blend; record coefficient/policy/evidence | M3; no accidental row blend or final-test tuning |
| S04 | Explain floor/concentration; bound/risk sensitivity; timing/costs for paper results | M3/M5; comparable policies, drifted holdings and turnover/cost tests |
| S05 | Run-correlated stage/data/solver/publication diagnostics, retention/recovery | M2–M4/M6; failure logs and backup/restore drill |
| S06 | Only used dependencies, uv lock, one formatter/linter, non-modifying quality gate | M1 onward; fresh installation and unchanged source after checks |
| S07 | Numeric weights and explicit price/cutoff/target/freshness/history labels | M5; UI assertions and representative rendering |
| O01 | Defer Docker unless actual native packaging/host portability problems justify it | M6 if needed; start with virtual environment/systemd |
| O02 | Choose one Actions quality gate for this empty repository | M1; ADR-010 records reduced administration and release-gating rationale |
| O03 | Defer dedicated QP solver unless SLSQP limitations are demonstrated | M3 diagnostics establish need before dependency addition |
| O04 | Defer intervals and fitted-model storage; retain inputs/settings/point outputs | Add only for measured calibration or forensic requirements |
| O05 | Defer extra models/features and concurrent fitting | Add only for measured accuracy/latency need after core completion |

## DO NOT CHANGE constraints

| ID | Preserved design |
| --- | --- |
| D01 | Prophet supported as an independent candidate even when a baseline wins |
| D02 | Mean-variance objective, full investment, fractional long-only configurable bounds |
| D03 | Streamlit read-only dashboard; no separate custom frontend/API |
| D04 | Supabase as the durable workload boundary; no second database |
| D05 | Simple daily/manual Actions scheduler |
| D06 | Independent full refits and separate stored-result web workload |
| D07 | Modest VPS/supervised process, independently chosen host identifiers |
| D08 | Simple returns, exchange calendar, established scientific and engineering tools |

## Independent acceptance scenarios

All twelve scenarios in Behavior section 12 have an assigned verification path.

| Source scenario | Planned acceptance check | Milestone |
| --- | --- | --- |
| All twelve assets valid | Complete finite matching ticker sets and coherent visible portfolio | M2–M5 |
| One asset download fails | Bounded retries, named failure, no reduced-universe publication | M2/M4 |
| One usable price | Reject before fitting with explicit history requirement | M1/M2 |
| Friday last session | Target next actual session, including a Monday holiday | M2 |
| Repeated/interrupted publication | One complete retry-safe published run | M4 |
| Twenty-one assets at 5% floor | Explain infeasibility before solver invocation | M1/M3 |
| Only one stored run | Display allocations/forecasts; evaluation pending | M5 |
| Missing scheduled day | Match only recorded target; missing actual stays unresolved | M4/M5 |
| Old date selected | That run's observation metric plus explicit all-history scope | M5 |
| Temporary database outage | Understandable unavailable state; labelled prior cached data where available | M5/M6 |
| More than one API response | Every offered run fetches fully; history pagination/scope explicit | M4/M5 |
| Poor forecasts | Keep valid recommendations visible; report baseline-relative weakness | M3/M5 |

## Reconciliation and remaining gates

The architecture covers the corrected product requirements. Choices beyond fixed
defaults were documented before implementation: pre-open deadline (ADR-003),
two-cycle annual-history gate (ADR-005), positive risk-aversion policy (ADR-006),
and uv/Actions consolidation (ADR-010). These settle open design choices; no
product feature is removed. Calendar-day targets, forecast-augmented covariance,
partial universes, mixed-run portfolios, and mismatched outcomes are not reproduced.

Future gates remain: native scientific compatibility, numerical tolerances and empirical selection,
provider metadata/calendar fixtures, corporate-action outcome reconciliation,
physical SQL and permissions, authorised infrastructure and actual public data-use
arrangements, and prospective operating evidence. Each has an assigned milestone
in the plan and decision record. Only the explicitly verified M1 and M2 portions above are implemented; the rest remain design commitments.
