# Implementation plan

Status: Milestones 0–2 implemented and verified.
Milestones 3–6 have not started. The established plan remains dated 12 September 2026.

The supplied [rebuild plan](specifications/REBUILD_PLAN.md) starts at Milestone 1;
it does not define Milestone 0. The user explicitly confirmed Milestone 0 as
"Design documents, coverage review, and minimal repository scaffold." Preserve
that boundary and the supplied numbering;
do not silently implement its foundation milestone under another name.

The authoritative requirements remain in [specifications/](specifications/).
[ARCHITECTURE.md](ARCHITECTURE.md) describes the intended system and
[DECISIONS.md](DECISIONS.md) records choices and their reasons. Significant changes
must be explained before implementation. Update the coverage matrix and decisions
when evidence changes a choice.

## Milestone 0 — Independent design and repository preparation

Deliver:

- Architecture, this implementation plan, and a decision record before application
  implementation.
- A requirement-by-requirement architecture comparison, with ownership, future
  milestone, and observable verification for every required feature/correction.
- A README stating the actual repository status, navigation, and next authorised
  boundary, plus basic ignore/editor settings.
- A milestone report with changes, exact verification commands/results, decisions,
  and unresolved items. Preserve the supplied specifications unchanged.

Acceptance: the required documents exist; all local Markdown links resolve; all
MUST FIX, SHOULD IMPROVE, OPTIONAL, and DO NOT CHANGE recommendations have an
explicit disposition; all behavior sections and independent acceptance scenarios
have a future verification path; no product/runtime code or automation is added;
specification hashes are unchanged; whitespace checks pass.

Tests: documentation integrity and scope checks only. There is no application
behavior yet to unit-test. Do not add vacuous tests, unused package modules, a
nominal CI badge, or invented execution evidence. Executable configuration and
packaging tests start with Milestone 1.

Stop after completing and reporting these checks. Later milestones require a new
user instruction, even if their work is otherwise straightforward.

## Milestone 1 — Reproducible foundation and validated contracts

Implementation: package/settings, fixed-clock resolution, locked toolchain, offline
configuration tests, quality workflow and isolated packaging smoke check are in
place. Evidence is recorded in [MILESTONE_1_REPORT.md](MILESTONE_1_REPORT.md).

Depends on Milestone 0 and authorisation to continue. This is exactly the
foundation stage in the supplied plan, not work included in Milestone 0.

Implement project metadata, a tested Python/tool version, independent committed
dependency lock, minimal importable package, and non-modifying local/Actions quality
commands. Implement typed request/settings validation and a fixed-clock resolution
boundary; publication settings are required only for the publishing path. Capture
time/price vocabulary and resolved scientific settings. Document installation and
explicit environment injection with nonsecret examples.

Checks: fresh locked installation and package build/install/import; lint, format
check, type check, and deterministic tests for empty/duplicate assets, invalid
dates, fractional bound feasibility including 1/12/20/21 assets, nonfinite or
unsupported numerical settings, separate history gates, missing publication
credentials, and fixed-clock behavior across midnight/time zones. No live market
or database dependency in foundation CI. Freeze exact versions only after checking
compatibility, not by copying any historical dependency file.

Exit evidence: documented repeatable setup/check commands, committed lock,
successful package smoke check, request contract examples, and test results.

## Milestone 2 — Validated data and session-targeted forecasts

Implementation: session planning, the explicit yfinance adapter, validated immutable
price/return panels, local snapshots/replay, independent Prophet refits, and a
manual forecast-only report are in place. See [MILESTONE_2_REPORT.md](MILESTONE_2_REPORT.md)
and [usage and assumptions](docs/MARKET_DATA_AND_FORECASTING.md) for verification
and limitations. No later milestone is implemented.

Depends on Milestone 1. Implement explicit yfinance request semantics, required
universe validation and bounded retries, exchange-session targeting/freshness,
consecutive aligned price/return panels, dated recent history, immutable local
input snapshots and provenance, and independent real Prophet refits. A callable
computation/manual forecast report does not require database credentials.

Checks: deterministic provider-adapter fixtures for empty/one-price/partial/stale/
malformed/revised data; zero/nonfinite values, duplicates, missing sessions,
input preservation, first-price/return handling, return arithmetic, and complete
ticker membership. Test Friday/Monday-holiday, year boundary, daylight saving,
late invocation, target/cutoff, annual-history gate, future holiday windows, and
finite-positive predictions. Run a small real offline Prophet fit/predict test.
Keep live provider smoke checks optional and explicitly labelled.

Exit evidence: controlled forecast/provenance artifacts and an assumptions report;
successful model execution is not evidence of forecast accuracy.

## Milestone 3 — Allocation and chronological evaluation

Depends on Milestone 2. Implement direct forecast expectations, observed-only
252-return sample covariance, SLSQP allocation, independent validation, diagnostics,
last-price/equal-weight/historical-only baselines, and offline rolling-origin
evaluation with frozen inputs and predeclared train/validation/final-test periods.
Resolve modest component/window/blend/stability experiments with evidence. Record
execution timing and costs before any paper-performance claim.

Checks: hand-computed return/covariance examples; known small optimal or degenerate
problems; single-asset and infeasible bounds; permutation invariance; solver
failure, nonfinite and singular/indefinite covariance behavior; finite weights,
budget/bound residuals, objective quality, and unchanged covariance when forecasts
change. Assert no target/future information enters fitting or model selection.
Verify metrics, tie policies, sample/exclusion counts, drifted turnover, transaction
cost arithmetic, and signal/holding interval timing.

Exit evidence: reproducible comparison tables/figures, experiment settings and
data hashes, numerical tolerances, and model-selection report including weak or
negative results. Do not change the final test after viewing its performance.

## Milestone 4 — Durable coherent publication

Depends on Milestones 1–3 and a new Supabase/disposable test environment. Implement
versioned independent SQL migrations, restricted reader/writer policies, run/asset/
observation/snapshot contracts, stable identities and explicit revisions,
transactional publication, outcome association, paginated reads, and the manual
compute/publish command with honest exit status. Store snapshots privately and
retain enough provenance to reproduce each computation.

Checks: real fresh-database provisioning and insert/read round trip; permissions;
missing fields/numeric/date serialization; retry/concurrency/idempotency; changed
payload and explicit revision; interrupted publication; previous-success
preservation; exact target-date matching across skipped jobs; incompatible adjusted
price revisions/corporate actions; complete selected runs across API page
boundaries; rejected credentials/API errors and read-back completeness. Mock-only
tests do not meet this gate.

Exit evidence: runnable migration instructions, integration results, result
examples, identity/publication contract, and recovery/backup guide. Credentials
are externally supplied and never versioned.

## Milestone 5 — Read-only historical dashboard

Depends on Milestones 3–4. Implement Streamlit run/date and alphabetical ticker
selection, doughnut and numeric allocations, forecast table, observed/predicted
metrics, interactive dated historical comparison with vertical-range control,
per-prediction and supported aggregate error metrics, explicit history scope,
freshness, and robust empty/pending/invalid/unavailable states. Use one charting
library and bounded cached reads. No model fitting or market retrieval on UI runs.

Checks: empty database, first run/no outcomes, one asset missing outcomes,
multi-run/revision selection, old-run metrics with all-history labels, malformed
history, database failure, known forecast/actual arithmetic, price/percent
formatting, degenerate chart range, pagination, and full-weight validation. Use
Streamlit interaction tests and one fixture-to-real-storage-to-rendered-dashboard
integration path; record an interactive chart smoke check.

Exit evidence: UI state guide, representative screenshots or recorded new-app
demonstration, and passing interaction/end-to-end checks.

## Milestone 6 — Deployment, schedule, and operational evidence

Depends on Milestones 1–5, a new authorised host/domain/Supabase project, workflow
secrets, and resolved intended market-data publication rights. Implement the exact
tested release gate, pinned workflows, non-root VPS/systemd service, HTTPS proxy,
secret injection, verified SSH identity, serialised release, readiness and rollback.
Add 09:00 UTC/manual batch execution tied to a known release, eligibility/no-op
handling, deadlines, bounded retries/timeouts, freshness/failure signals, and
documented manual rerun, retention, backup/restore, and missed-session policies.

Checks: full quality/package/model/database/UI gate; clean-host provisioning;
public read-only flow; revision/readiness verification; controlled provider/DB
failure, repeated/manual/non-session/late jobs and recovery; missing-result
visibility; rollback drill and backup/restore drill. Record multiple actual
prospective session runs and at least one matured outcome. A historical backfill
cannot stand in for evidence of live operation.

Exit evidence: live HTTPS URL, reproducible release/provisioning artifacts,
operations runbook, actual session-run records, recovery evidence, and an honest
project presentation. Missing external access or observation time is reported,
not replaced with a fabricated deployment claim.

## Common milestone gate

For each authorised milestone: implement only its scope, add meaningful behavior
tests, run its relevant non-modifying checks, explain consequential choices,
update architecture/decisions/coverage where needed, and record exact commands,
results, limitations, and unresolved problems. Stop and report before the next
milestone. A planned check is never recorded as a passed check.
