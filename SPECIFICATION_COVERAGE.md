# Specification coverage review

Reviewed for Milestone 0 on 12 September 2026, after creating
[ARCHITECTURE.md](ARCHITECTURE.md),
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and
[DECISIONS.md](DECISIONS.md), and before adding the repository scaffold.

Result: every required feature and classified correction has a proposed owner
and acceptance check. No required feature is intentionally removed. **Design
coverage is not implementation completion:** application work is assigned to
future Milestones 1–6. The user explicitly confirmed M0 as design documents,
coverage review, and minimal repository scaffold.

Only the supplied handoff was consulted. Its descriptions of defects are context;
its required corrections govern the proposed design.

## Product and behavior contracts

Sources: [PROJECT_SPEC.md](specifications/PROJECT_SPEC.md) and numbered sections
of [BEHAVIOR_SPEC.md](specifications/BEHAVIOR_SPEC.md). Owners below are proposed
responsibilities, not existing modules.

| Requirement | Architecture owner and design | Milestone | Acceptance evidence |
| --- | --- | --- | --- |
| Product scope/defaults | One configured twelve-asset demonstration, reference dates/risk/bounds/components, recommendations only | M1–M6 | Default-setting tests; scope review; no brokerage or individual account claims |
| Behavior 1: time/numbers/identity | UTC execution, separate session cutoff/target, shared run ID, unrounded fractional calculations | M1/M2/M4 | Fixed clock; session dates; finite numeric and serialization checks |
| Behavior 2: configuration/invocation | Validated request, runtime end resolution, callable computation without writes, explicit publication credentials | M1/M2/M4 | Invalid inputs; injected clock; compute without DB credentials; publish failures return nonzero |
| Behavior 3: ingestion | Explicit yfinance adjusted daily data; full universe; bounded retries; immutable snapshots | M2 | Empty/partial/one-price/stale/malformed/revised provider fixtures |
| Behavior 4: alignment/context | Calendar-validated common prices before single-session returns; first price retained; dated 30-calendar-day context | M2 | Gaps, intersection/order/duplicates, 253-price risk minimum, inclusive context boundaries |
| Behavior 5: forecast/return | Independent Prophet refits and recorded settings; future holiday coverage; next-session target | M2 | Small real fit; Friday/holiday/year/DST cases; features and price-return arithmetic |
| Behavior 6: portfolio | Direct expectations, observed-only covariance, half-factor mean-variance objective, checked SLSQP solution | M3 | Known optima/numeric examples, risk independence, residuals, invalid/degenerate inputs |
| Behavior 7: orchestration/publication | Pure computation, complete validation, explicit publication, correlated stages and honest exits | M2–M4/M6 | Fault injection, no partial success, stage diagnostics, read-back completeness |
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
| F14 | Adjusted-price/currency/security semantics, immutable snapshots/revisions, deployment-use gate | M2/M4/M6 | Provenance/revised-data fixtures; resolve intended public data use before deployment |

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

Future gates remain: tested versions, numerical tolerances and empirical selection,
provider metadata/calendar fixtures, corporate-action outcome reconciliation,
physical SQL and permissions, authorised infrastructure and actual public data-use
arrangements, and prospective operating evidence. Each has an assigned milestone
in the plan and decision record. None is claimed as solved by this design review.
