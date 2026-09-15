# Milestone 4 report

Completed 14 September 2026 (Asia/Beirut). **Milestone 4 only** is implemented,
verified and documented. HEAD remains `e8f49b3` (`feat: complete milestone 3
allocation and evaluation`). Changes are uncommitted; no commit was requested.
Milestone 5 has not started.

Before implementation, read the architecture, decision record, implementation
plan, coverage matrix, M3 report, relevant authoritative specifications and the
M1–M3 implementation. After the usage-limit interruption, inspected `git status`,
the complete tracked diff, new components, the plan/coverage and the final SQL edit.
The report did not yet exist. The earlier 299/23-test passes were not treated as
final evidence for the subsequently modified migration. Fresh final checks below
supersede them. No established architecture or scientific default was redesigned.

## Functionality and acceptance

| M4 requirement / acceptance criterion | Implemented behavior and evidence |
| --- | --- |
| F04; coherent logical run | One versioned request identity includes mode, cutoff/target, canonical universe, settings, source/lock/Python and scientific revision. The first durable snapshot binding precedes fitting. Unique request/UUID and run/ticker keys prevent independent mixed portfolios. |
| F04; retry, revision and atomic publication | Run lock plus one transaction inserts every asset and publishes together. Identical semantic payloads are idempotent; conflicting payload/input bindings fail. Concurrent capture/publish, lost success reply, interrupted fit/resume, late invalid row rollback, deliberate revisions and preservation of prior success pass against the real database. |
| F10; independent provisioning | Two versioned SQL files and a checksummed transactional psql runner provision a fresh database. Reapplication is safe; changed applied migration contents fail. Required numeric/date/unique/FK constraints, indexes and whole-portfolio checks are exercised. |
| F10; privilege separation | Public/ordinary authenticated readers see published data; `portfolio_writer` has only the required named RPC grants. Readers cannot write or inspect snapshots/stages/attempts. The role cannot bypass RLS or administer the database; service-role credentials are not supported. Real role/JWT and direct SQL denial checks pass. |
| F07/F14; dates and provenance | Persist execution/completion/publication timestamps, cutoff/target/open/close, effective settings and Prophet fitting metadata, universe, source/lock/Python/packages, explicit adjusted USD basis, provider/options/retrieval metadata, original dated snapshots and exact recent histories. |
| F03/F04/F10; invalid results | Application rechecks observed risk, direct returns, bounds/budget and objective; SQL rejects missing/nonfinite/invalid scientific values, missing model/software provenance, incomplete portfolios and undated/inconsistent history. No missing result becomes zero. |
| F06/F14; exact outcome association | Join each ticker to its recorded target, including across skipped jobs. Retain immutable source vintages and explicit pending/incompatible states. Same provider/metadata/basis plus unchanged full overlap is required; uniform and nonuniform adjusted-history revisions withhold actual values. |
| F11; complete and bounded reads | One complete JSON aggregate per selected published run; validated membership, arithmetic, history and scientific payload. Bounded keyset summary/history pages preserve distinct revisions and state date coverage. Real twelve-asset response passes with PostgREST row limit 3. |
| F01/F13; publication failure/deadline | Established session planner remains authoritative. Live deadline checks occur before fit/submission and inside SQL before publication. Expired staging/resume is rejected. Transport retries and timeouts are bounded. Failed read-back returns failure even if the transaction committed; the next retry retrieves the durable result. |
| S05/F12; operation and verification | Manual compute/publish/resume/observe/read/history commands, correlated attempt diagnostics, recovery/retention instructions, actual pg_dump/pg_restore drill, full earlier regression, native Prophet integration and installed-package checks. |

All M4 acceptance criteria in [the plan](IMPLEMENTATION_PLAN.md) and
the authoritative rebuild scope (`specifications/REBUILD_PLAN.md`) are met using the
allowed disposable database environment. [Coverage](SPECIFICATION_COVERAGE.md)
keeps M5 presentation/cache/metrics and M6 hosted operations explicitly pending.
The [persistence guide](docs/PERSISTENCE_AND_PUBLICATION.md) provides runnable
provisioning, credentials, CLI, identity, pagination and recovery contracts.

## Database and methodological decisions

Supabase remains the sole production persistence layer. The batch calls its
PostgREST database functions through standard-library HTTP; there is no new Python
dependency, additional production database, API service, queue, Docker image or
tracking platform. Native PostgreSQL/PostgREST processes are disposable test tools.

`pf_private` holds `snapshots`, `runs`, `asset_results`, `attempts`, `outcomes` and
the migration ledger. Exact content-addressed snapshot text is stored privately
inside PostgreSQL, avoiding a second storage transaction. Run state and all asset
rows become visible atomically. Published rows, snapshots and outcome vintages are
immutable. Published ordering, ticker/run lookups, attempt chronology and latest
outcome queries have explicit indexes. Numeric domains reject nonfinite prices,
returns and weights; full membership, price-return arithmetic, budget/bounds,
cutoff/target consistency and required model settings are durable checks.

Logical identity excludes attempt clocks and equivalent exclusive-end aliases.
Recursive JSON numeric normalization makes `5` and `5.0` identical. The full SHA-256
is retained; UUID uses its first 128 bits. A snapshot race keeps the first committed
binding. Intentional input replacement requires a new scientific revision. Native
execution timing is stored on attempts, not hashed into scientific results.
Retries of already published runs return stored results without another fit.
An interrupted or already-published-read attempt can remain `registered`; it is
not a second publication and does not overwrite the original success record.

The unchanged full-overlap basis policy uses tolerance
`1e-8 + 1e-10 * abs(original_price)`. It detects both uniform corporate-action
rescaling and nonuniform historical corrections, preserves evidence, and does not
infer an adjustment factor or modify an issued prediction. Latest evidence is
retrieval timestamp then source hash; older vintages remain stored. Missing or
incompatible actuals are null and have an explicit reason. Metrics/rendering
remain M5 work.

Reader RPC functions use fixed empty search paths and restricted grants; private
schema ACLs plus RLS hide unpublished rows. `portfolio_writer` is a dedicated
non-login role with neither direct table writes nor RLS bypass. Runtime processes
receive a project publishable/anon API key and, only for writing, a trusted scoped
JWT. Signing and administrator credentials remain outside runtime processes.
The client checks the actual database role, hides credentials from representations,
refuses redirects and excludes server response bodies from failures.

The adapter allows three attempts for transient transport/429/500/502/503/504
failures, 15-second socket timeouts and 1/2-second backoff. Permanent API rejection,
conflicts and expired deadlines fail promptly. Request/response size is capped at
16 MiB. The database rechecks the live target opening immediately before publishing;
network delivery after commit is outside that transaction-time guarantee.

These choices implement ADR-007/008 and are recorded in
[ADR-014](DECISIONS.md#adr-014--milestone-4-durable-publication).

## Final migration edit reviewed after resumption

The previously verified `0001_publication.sql` had SHA-256
`48aaae0d59244815759eaa71ba5e1d05102009be4b490d14e4e21d9f16d53c30`.
Reconstructing that exact version by reversing the final edit reproduced its hash,
so the post-check difference was independently identified:

- Require nonempty JSON objects for model `constructor` and `fit`, instead of
  accepting keys whose values are null or empty.
- Require a nonempty solver method and package provenance object.
- Require reported Python version to match the bound identity.

The edit is intentional enforcement of missing-scientific-output/provenance
requirements. Four new real-database cases remove constructor, fit, packages or
Python provenance and assert an unpublished run with **zero** inserted asset rows.
The complete real-database suite was rerun from fresh provisioning, including
valid native fits, retries, permissions and restoration. No SQL or source edit
followed the final passing tests. These are unreleased migrations used only in
disposable environments; no previously applied hosted migration was changed.

Final migration hashes:

| File | SHA-256 |
| --- | --- |
| `0001_publication.sql` | `cbb2778536fd2b4ce43dc6d453daec1c7cddc90047f1d72aa7857e98d903eb28` |
| `0002_outcomes_and_reads.sql` | `ed3d80f579f074e5ca41d6e56ec43226b1bac58177950af5df54fd74c1bed687` |

## Files and components

| Added / changed files | Purpose |
| --- | --- |
| `src/portfolio_forecasting/store_contract.py` | Stable identity, release provenance, strict scientific payload and complete read validation |
| `src/portfolio_forecasting/supabase_store.py` | Restricted credentials, bounded RPC transport, publication and reader/outcome contracts |
| `src/portfolio_forecasting/publishing.py` | Durable binding before fit, reuse/resume, established forecasting/allocation composition and publication checks |
| `src/portfolio_forecasting/publish.py` | Manual compute/publish, resume, observe, read, paginated summaries/history |
| `supabase/migrations/0001_publication.sql` | Core records, constraints/indexes, access roles/policies, stage/attempt/publish functions |
| `supabase/migrations/0002_outcomes_and_reads.sql` | Exact outcome vintages and complete/bounded reader functions |
| `scripts/migrate.py` | Explicit administrator connection, checksummed transactional provisioning |
| `tests/test_persistence.py` | 18 deterministic M4 contract/transport tests |
| `integration/__init__.py`, `integration/conftest.py`, `integration/test_database.py` | Explicit fresh PostgreSQL/PostgREST fixtures and 27 real-database tests |
| `.env.example`, `Makefile`, `.github/workflows/quality.yml`, `pyproject.toml` | Scoped token name, explicit database gate, existing CI integration and typing of integration code; no dependency change |
| `scripts/package_smoke.py` | Retains M1–M3 checks and adds installed M4 imports |
| `docs/PERSISTENCE_AND_PUBLICATION.md`, `docs/examples/milestone4/run-summary.json` | Operator/data contracts and portable controlled result example |
| `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `IMPLEMENTATION_PLAN.md`, `SPECIFICATION_COVERAGE.md`, this report | Accurate status, decisions, coverage and completion evidence |
| `MILESTONE_3_REPORT.md` | Formatting only: the existing quality gate rejected one committed Python list-comprehension example; Ruff reformatted that code block without semantic changes |

All 17 prior application source files, all 14 prior test/fixture files, all seven
supplied specifications and `uv.lock` remain byte-for-byte unchanged. Existing
scientific/model/configuration tests and package smoke behavior remain intact.
The preexisting untracked `specifications/` directory is preserved. HEAD is still
`e8f49b3`; no commit or external deployment/publication was performed.

## Commands and exact final results

Commands ran from `/home/wassim/code/portfolio-forecasting`. `PINNED_UV` below is
exactly `/home/wassim/.cache/uv/archive-v0/7S7aC_6BQ3jtOceC_r9uG/uv-0.12.13.data/scripts/uv`.
The default host uv is older; the project remains pinned to uv 0.12.13, Python
3.12.14 and the unchanged 55-package lock. Logs are retained locally in ignored
`artifacts/milestone4/verification/`; PostgreSQL/PostgREST logs are under
`artifacts/milestone4/integration/`. They are local evidence, not committed secrets.

| Final command / operation | Exact result |
| --- | --- |
| `git status --short`; `git diff --stat`; `git diff -- ...`; `rg`/`cat`/`sed` on project/specification/new implementation files | Reconstructed 11 modified tracked files plus the M4 additions and preexisting untracked specifications; report absent at resumption; final SQL change identified and reviewed |
| Python reverse-diff SHA-256 audit of `0001_publication.sql` | Reconstructed prior hash `48aaae0d…53c30`; only the intended model/solver/software provenance checks differ; final hash `cbb27785…3eb28` |
| `make check UV=PINNED_UV` after resumption/final migration | **Exit 0**; `Resolved 55 packages in 0.79ms`; `All checks passed!`; `65 files already formatted`; `Success: no issues found in 44 source files`; **`299 passed in 105.80s (0:01:45)`** |
| `make database-smoke UV=PINNED_UV` after resumption/final migration | **Exit 0; `27 passed in 40.53s`**; fresh private database, both final migrations, real JWT/RPC/SQL assertions, full twelve-asset native computation and backup/restore |
| `make package-smoke UV=PINNED_UV` after resumption/final migration | **Exit 0**; sdist then wheel built, fresh hash-locked runtime-only environment, all four PASS messages below |
| `/usr/lib/postgresql/16/bin/postgres --version` | `postgres (PostgreSQL) 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)` |
| `artifacts/milestone4/tools/postgrest --version` | `PostgREST 16.3` |
| Python SHA-256 comparison with the initial `/tmp/portfolio-m4-baseline.json`; `git show HEAD:uv.lock` comparison; `git rev-parse --short HEAD` | PASS: 17 prior source + 14 prior test/fixture + 7 specification files unchanged; lock byte-identical; HEAD `e8f49b3` |
| `.venv/bin/ruff check .`; `.venv/bin/ruff format --check .` after report/documentation completion | Exit 0; `All checks passed!`; `66 files already formatted` |
| `git diff --check`; Python final scope/whitespace/link/hash audit | Exit 0; 25 expected changed/new authored text files; 120 local links resolve across 15 authored Markdown documents; source/migration hashes unchanged after final tests; no M5 code or task-owned database processes |
| Task-owned `pg_ctl -D <private temporary development directory>/data -m fast -w stop` | Exit 0; `server stopped`; disposable integration fixtures also stop their own processes; system PostgreSQL was untouched |

Installed-package messages:

```text
PASS: sdist/wheel, locked runtime-only install, isolated request resolution
PASS: installed wheel real offline Prophet backend fit/predict
PASS: installed wheel SciPy known optimum and research reporting import
PASS: installed wheel Supabase publication contracts and CLI imports
```

The final audit script and initial/final hash manifests are retained in
`artifacts/milestone4/verification/`. The report was added after the full suite;
only documentation/result examples changed afterward, and the final non-modifying
lint/format/link/whitespace checks include them. No implementation or migration
changed after the fresh passing database suite.

The existing optional-Plotly notice comes from unchanged Prophet behavior; real
fits and installed package checks pass without introducing a dashboard dependency.

The database gate executes `initdb`, `pg_ctl`, explicit Supabase-equivalent role
bootstrap, `python scripts/migrate.py`, and native PostgREST with real JWT role
switching. It tests migration reapplication and rejects changed applied content.
The CLI subprocess runs real `compute --snapshot`, `resume`, and reader `read` with
loopback test credentials; denied credentials return nonzero. Restoration uses
`pg_dump --format=custom --schema=pf_private --schema=public --file <temporary dump>`,
then `pg_restore --exit-on-error --clean --if-exists --dbname=pf_restore <dump>` into
a separate disposable database, followed by an anonymous complete read and a
private snapshot denial. No production database is a destination.

Earlier incremental verification is retained as development history, **not** final
migration evidence: 15 database tests passed initially; a combined run found a
fixture aliasing failure (1 failed, 7 passed); later combined runs reached 39 passes
and exposed restore failures for existing `public` schema and missing explicit
schema usage. The restore command/ACLs were corrected. Ruff/mypy import/format/type
diagnostics were fixed. The committed M3 report code-block formatting also blocked
the complete quality gate and was corrected as documented above. Pre-interruption
passes were 299 tests in 108.63s, 23 database tests in 38.15s and package checks;
a later 27-test database run completed in 33.29s, but all final checks were rerun
after resumption as shown in the table.

Initial sandboxed shell/patch attempts failed before execution with
`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`; required workspace
commands used approved escalation. PostgreSQL server/client binaries already
existed. The pinned official PostgREST archive was downloaded and verified as
SHA-256 `4eb414eb948c8800863cc8c9896a17b611b2dccf9ff581f4d57f42ec9ccee40d`.
No dependency installation changed `uv.lock`.

## Tests performed and live-service evidence

The final total is **326 passing tests: 281 unchanged M1–M3 cases, 18 M4 unit cases,
and 27 real-database cases**. Normal pytest remains offline; the database gate is
explicit and fails, rather than silently skips, if its prerequisites are absent.

Unit tests cover canonical identity inputs, timestamp/ticker order independence,
release/revision changes, complete scientific membership and dates, invalid
weights/covariance/basis, mixed/truncated reads, target mismatch, nonfinite nested
JSON, bounded identical-body retry, permanent API rejections, timeout exhaustion,
malformed JSON, redirect refusal, role preflight and credential representations.

Real tests cover fresh/repeated/checksummed migrations, reader/writer/RLS denials,
private stages/snapshots, positive publication and semantic repeat, conflicting
payload/revision behavior, five invalid numeric forms with whole-transaction
rollback, preservation of previous success, four concurrent publishers, lost
commit replies, competing first snapshots, interrupted fitting and real Prophet
resume, missing outcomes/exact targets across gaps, uniform/nonuniform revisions,
keyset pagination and API row limits, invalid JWTs/reader CLI, equivalent JSON
numbers, missing completion/direct incomplete publication, expired live
stage/resume, real dump/restore, failed read-back after commit, and four missing
model/software provenance cases. The complete twelve-asset CLI test actually fits
Prophet and allocates; it does not substitute model mocks for that acceptance path.

**Live-service scope:** a fresh local PostgreSQL **16.15** cluster plus actual
PostgREST **16.3**, Supabase-equivalent roles and signed test JWTs. The cluster has
no PostgreSQL TCP listener; its private Unix socket and test PostgREST loopback
listener are temporary. The existing system database is not used. No hosted
Supabase project, API-key gateway, Auth issuer, managed backups or live market
provider was exercised in M4. No hosted credentials were supplied. The plan permits
this real disposable database gate; mock-only tests were not used as its substitute.

The [portable synthetic example](docs/examples/milestone4/run-summary.json)
contains twelve assets, cutoff 2026-09-04, target 2026-09-08, explicit retrospective
mode and all key date/config/input-provenance fields. The full validated reader
response remains in ignored `artifacts/milestone4/verification/complete-run.json`.
Its scientific source hash is
`b560631cf31e6613667e206e1ba62e85dcb283a10298f501125ce13a4b003996`.
Synthetic short-history settings (`risk_window=2`, annual seasonality disabled)
are explicit test configuration; production defaults remain unchanged. These
results establish engineering correctness, not forecast accuracy or investability.

## Limitations and intentionally deferred work

- Hosted Supabase gateway behavior, trusted restricted-token issuance/rotation,
  project settings and public data-use entitlement need operator/M6 verification.
  A project publishable key alone cannot write. No signing key or privileged
  production credential is shipped or printed.
- Snapshots and payloads are bounded at 16 MiB; the chosen dozen-asset workload fits.
  Full input snapshots and outcome vintages require retention alongside the exact
  source/lock release. There is no automatic deletion, retention scheduler or
  hosted backup/PITR configuration. The demonstrated restore is a local drill.
- HTTP timeouts bound socket operations; there is no global scheduler wall-clock
  guarantee. Deadline acceptance is checked at the database state transition,
  not when a delayed success response eventually reaches the client.
- Full-overlap adjusted-basis matching is conservative: valid corporate-action
  transformations can remain incompatible until a defensible original-basis
  observation exists. No price rescaling or point-in-time availability is inferred.
- Each page is coherent at its database snapshot; an `as_of` watermark and keyset
  do not provide a long-lived MVCC snapshot across concurrent commits/outcome
  updates. Refreshing starts a new visible cohort. Histories remain explicitly
  bounded by requested target dates.
- Test UUIDs, temporary JWTs and real service timestamps isolate executions;
  financial input dates/values and invariant assertions are controlled fixtures.
  Linux x86-64 with the stated PostgreSQL/PostgREST versions is the verified platform.
- M5 dashboard/cache/formatting/error metrics and M6 scheduling, monitoring,
  deployment, public service operation and prospective matured-outcome evidence
  remain unimplemented. No architecture redesign, alternate model, optional
  infrastructure or unrelated feature was introduced.

Milestone 4 is the stopping boundary.
