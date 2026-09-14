# Persistence and publication

Milestone 4 adds Supabase storage to the established M1–M3 scientific pipeline.
The application still runs as a Python batch. No dashboard, additional production
API, scheduler or deployment is included. See [the M4 report](../MILESTONE_4_REPORT.md)
for verification and [the SQL migrations](../supabase/migrations/) for the contract.

## Provisioning and privileges

Use a **new Supabase project** with PostgreSQL 16 or compatible supported SQL,
its Data API exposing `public`, and the standard `anon`, `authenticated`,
`authenticator`, and `service_role` roles. Apply migrations as the database
administrator from this checkout, using `psql` and an explicit libpq connection.
Credentials come from the operator's secret mechanism; nothing loads `.env`.

```sh
# Inject PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSFILE and PGSSLMODE=verify-full.
# Alternatively configure PGSERVICE with the appropriate verified TLS settings.
uv run --locked python scripts/migrate.py
```

The runner refuses an implicit default database connection. Each numbered SQL
file runs under a transaction/advisory lock, with a SHA-256 migration ledger.
Repeating the command skips identical applied versions; changing an applied file
fails. Future changes require a new migration. Migration errors return nonzero
without printing connection details. Inspect administrator database logs when
investigating a failure. Do not amend already applied migration contents.

| Role | Allowed access |
| --- | --- |
| Administrator | Provisioning, explicit recovery/backup, private audit inspection |
| `portfolio_writer` | Publication, bound snapshot retrieval, attempt records, outcome association and public reads through named RPC functions |
| `anon`, `authenticated` | Published runs/assets/outcomes and bounded reader functions; no writes, private snapshots, or attempts |
| `service_role` | No grants on these application functions/tables; not a supported runtime identity |

`portfolio_writer` is a dedicated non-login, non-superuser role without RLS bypass
or role/database creation. It has no direct table DML. `authenticator` can assume
it from a valid trusted JWT. Public schema usage and function grants are explicit;
public schema creation is revoked from ordinary application roles. Private tables
use RLS and explicit ACLs. Functions that cross the private boundary are
`SECURITY DEFINER` with an empty `search_path` and fully qualified object names.
A reader cannot expose a staged run through either the RPC or direct SQL policies.
The private migration ledger is administrator-only by ACL.

Configure each process independently:

- `SUPABASE_URL`: HTTPS project URL; local HTTP is only for loopback testing.
- `SUPABASE_KEY`: project publishable API key, or legacy anon key.
- `SUPABASE_ACCESS_TOKEN`: **writer process only**, a valid short-lived token
  issued by the project's trusted authentication/signing setup with the role claim
  `portfolio_writer`. Readers omit it or use an ordinary authenticated reader JWT.

The operator must provision and rotate that restricted credential using a trusted
issuer accepted by the project. A publishable key alone cannot write. Do not put
JWT signing keys or service-role keys into the application process. The client
sends the project API key in `apikey`, and an access JWT separately in
`Authorization: Bearer ...`; it does not use a new publishable key as a bearer JWT.
An old anon JWT key can serve as the reader bearer token. The preflight checks the
**actual PostgreSQL role**, not a locally decoded assertion. `sb_secret_` keys are
rejected and `service_role` lacks the application grants. Credentials are hidden
from representations and HTTP response bodies are excluded from error messages.
Redirects are refused so credentials cannot follow them to another host.

These choices follow the official [Supabase API-key contract](https://supabase.com/docs/guides/getting-started/api-keys),
[JWT role handling](https://supabase.com/docs/guides/auth/jwts), and
[database-function privilege guidance](https://supabase.com/docs/guides/database/functions).
The repository does not introduce user accounts or a token-issuing service.
Hosted gateway/token provisioning must be verified in the operator's project;
M4's disposable test verifies real JWT role selection and database permissions.

## Stored records and complete reads

| Private table | Purpose and durable invariants |
| --- | --- |
| `schema_migrations` | Version/checksum ledger, applied time |
| `snapshots` | Exact UTF-8 snapshot bytes as text, SHA-256 primary key/check, normalized data hash, capture time; immutable |
| `runs` | Stable request SHA-256/UUID, immutable first snapshot binding, mode/revision/settings/universe, cutoff/target/open/close, execution/completion/publication times, result JSON/hash, staged/published state |
| `asset_results` | One row per run/ticker, positive finite observed/predicted prices, finite fractional return/weight, model settings and exact dated recent history |
| `attempts` | Separate attempt UUID, start/end, registered/failed/published status, stage diagnostics |
| `outcomes` | Immutable run/ticker/source-snapshot vintage, exact target, matched/pending/incompatible state, comparable actual or null, reason and basis policy |

Unique request and run/ticker keys enforce coherence. Foreign keys connect every
result/outcome to its owner and source. A publication trigger checks exact full
membership, budget and configured bounds. Numeric domains reject NaN and either
infinity; required values have no zero defaults. Dates and aware timestamps have
strict input parsers and checks. Published headers/results and all snapshots and
outcome vintages are immutable. Indexes cover published target/time/ID ordering,
ticker/run lookup, attempt chronology and latest outcome provenance.

`pf_run(run_id)` returns **one complete JSON object**, so PostgREST's row limit
cannot cut an asset list into pages. It includes the immutable scientific payload,
all assets sorted canonically, exact dates/times, effective configuration, lock
and source revisions, covariance and solver evidence, snapshot/data hashes,
provider/options/retrieval metadata, dated recent histories and the latest outcome
vintage per asset. Full input snapshots and attempt internals stay private.
The client checks membership, price/return arithmetic, budget/bounds, dated
history, chronology, provenance and equality with the stored scientific payload.
An invalid/truncated read is an error, never a partial success.

`pf_runs` and `pf_history` return bounded pages (1–100 items, default 50), a
`next_cursor`, and `as_of`. Order is target descending, publication time descending,
then run UUID descending; deliberate revisions stay distinct. History requires a
ticker and inclusive target-date range. Reuse both cursor and watermark until
`next_cursor` is null. A new first page refreshes the cohort. Each RPC has a database
snapshot, but separate pages do not promise one long-lived MVCC snapshot across
concurrent commits or newly associated outcomes. This avoids unbounded retrieval
or a long database transaction. The response states requested date coverage.

## Identity, first binding, and publication

Identity schema 1 includes mode, observation cutoff, next-session target, sorted
universe, history start, scientific revision, all effective forecast/allocation/data
settings, package source hash, lock hash and Python version. It excludes the
attempt's wall clock and exclusive-end aliases that resolve to the same horizon.
PostgreSQL recursively normalizes equivalent JSON numbers before SHA-256 hashing;
`5` and `5.0` produce the same key. UUID uses the first 128 bits, with the full
request hash retained and independently unique. A hypothetical truncated-hash
collision fails, rather than replacing an existing request.

The batch looks up that identity and **durably stages its first validated snapshot
before fitting**. On a capture race the first committed binding wins. The other
process discards its candidate and reloads the winner. A different snapshot cannot
replace the binding. Retries/resumes use that exact frozen snapshot and matching
scientific release. Intentional changed data requires a new `scientific_revision`;
changed effective configuration/software also changes identity.

Each invocation has a separate attempt UUID. Failed stages leave the bound request
unpublished and record a sanitized stage when storage is available. A hard process
stop can leave an attempt `registered`; that is audit evidence, not published
success. A retry that finds an already published run records a new registered
attempt and returns the stored complete result without fitting again. It logs
`already_published`; it does not rewrite the original successful attempt.

The application independently revalidates M3 risk, expectations, feasibility and
objective before submitting the result. `pf_publish` locks its one run, validates
all members/provenance/numerics/histories, inserts all rows, and sets published
state in **one transaction**. A late invalid row rolls back earlier inserts.
Live deadlines are checked before fitting, before submission, at database entry,
and after inserts immediately before the published-state transition. The target
must remain unopened at the final database check. This is a transactional check,
not a guarantee about network delivery time after commit.

Identical semantic payload retries acknowledge the original result. Conflicting
payloads fail with 409; they cannot mutate a prior run. Durations are attempt
metadata and do not manufacture different scientific payloads. The CLI reports
success only after validated full read-back. Losing a success response or failing
read-back can therefore return an error after a successful commit: resume/read
that same identity to recover. Earlier successful runs remain available.

The HTTP adapter allows three attempts, each with a 15-second socket timeout and
1/2-second backoff, for transport errors or 429/500/502/503/504. Permanent rejection,
conflict, deadline and malformed JSON fail promptly. There is no outer unbounded
retry or automatic solver fallback. Requests/responses are limited to 16 MiB;
HTTP timeouts are socket-operation bounds, not an end-to-end scheduler deadline.

## Exact target observations and adjusted revisions

`observe` accepts a validated later snapshot and considers each forecast's own
**ticker and target session**. It does not join to the next stored run, so skipped
jobs do not shift outcomes. A target not present, a missing asset, or a capture
before target close remains pending. Numeric absence is null, never zero.

Basis policy `all_overlap_unchanged_v1` requires the same provider, selected
security/currency/calendar metadata and adjusted-close convention. Every originally
captured observation date must be present and have the same price within
`1e-8 + 1e-10 * abs(original_price)`. Missing overlap or a changed historical price
is incompatible, including uniform split/dividend rescaling and nonuniform
revisions. No inferred rescaling changes an issued forecast. This conservative
policy intentionally withholds metrics when a defensible comparable basis is
unavailable; it cannot prove point-in-time vintage accuracy.

Each source snapshot gets a separate immutable outcome vintage; retries of the
same evidence add nothing. Latest is retrieval time then source hash, not arrival
order. Revised incompatible evidence can supersede a previously matched display,
while all earlier evidence remains retained. Display metric calculations and UI
states belong to M5. Provider reliability and public display rights remain M6 gates.

## Manual operation

After restricted writer credentials are injected, an eligible pre-open live
request uses the unchanged validated yfinance, Prophet and allocation defaults:

```sh
uv run --locked python -m portfolio_forecasting.publish compute
```

For explicit research settings, provide a RunRequest-shaped JSON file; dates use
`YYYY-MM-DD`, and nested settings use the established configuration names:

```sh
uv run --locked python -m portfolio_forecasting.publish compute --request request.json
uv run --locked python -m portfolio_forecasting.publish compute --snapshot artifacts/inputs/HASH.json
uv run --locked python -m portfolio_forecasting.publish resume RUN_UUID
uv run --locked python -m portfolio_forecasting.publish observe RUN_UUID --snapshot artifacts/inputs/LATER_HASH.json
```

`--snapshot` accepts only a previously validated retrospective input. To revisit
changed data under the same configuration, create a request with a new scientific
revision and capture it through the established data path. Do not relabel an old
live forecast as newly issued. No command bypasses live eligibility or deadlines.
A closed live request returns an explicit skipped result; operational errors exit
1, success/no-op exits 0 (argument parsing errors exit 2).

Reader credentials suffice for:

```sh
uv run --locked python -m portfolio_forecasting.publish read RUN_UUID
uv run --locked python -m portfolio_forecasting.publish runs --limit 50 > page.json
uv run --locked python -m portfolio_forecasting.publish runs --limit 50 --cursor page.json
uv run --locked python -m portfolio_forecasting.publish history AMD --start 2026-01-01 --end 2026-09-30
```

Use global `--lock` for an explicit release lock file and `--snapshots` for private
local working copies. `--api-prefix ''` exists solely for disposable native
PostgREST tests; Supabase uses the default `/rest/v1`. The original forecast-only
CLI and callable M1–M3 computation still require no storage credentials.

## Recovery, retention and backup

For a transport failure, first inspect/read the same run. If published, reuse it.
If staged and still eligible, run `resume` with the bound release; never fetch
replacement prices under that identity. Expired live stages remain unpublished.
Use a separate labelled retrospective revision for later research, not a backdated
live forecast. Associate later target evidence to recover missing outcomes across
skipped jobs. An admin can inspect `attempts` for interrupted/failed work.

No automatic deletion is implemented. Retain private input and outcome snapshots,
run identities/results, attempts, migrations and their matching source/lock
releases. Losing the first binding destroys the retry/reproduction guarantee.
Private local copies are also sensitive datasets; generated artifacts are ignored
by Git. Immutable snapshots live inside Supabase PostgreSQL, avoiding object-store
credentials and a second distributed commit boundary.

Use administrator credentials and libpq environment for a custom-format backup:

```sh
pg_dump --format=custom --schema=pf_private --schema=public --file=portfolio.dump
```

This contains private data; protect it with access controls and the operator's
encrypted backup mechanism. On a dedicated project these schemas contain the
application contract. On a shared project the `public` schema can include other
objects: inventory the scope before restoring. Cluster roles are not part of a
database dump. Provision the expected roles on the **disposable restore target**
and explicitly set its connection environment before restoring:

```sh
pg_restore --exit-on-error --clean --if-exists --dbname=DISPOSABLE_RESTORE_DATABASE portfolio.dump
```

`--clean` replaces objects in the destination; this is a recovery drill command,
not a command to run against the serving database. Then verify complete reader
retrieval, the migration checksums, private snapshot hashes/counts and permission
denials. The integration test performs a real dump/restore into a separate fresh
database and rechecks complete reads plus private-snapshot denial. Hosted Supabase
managed backup/PITR configuration and a production recovery-time objective are
operator/M6 work, not claimed by this local drill.

## Reproduce the database acceptance gate

```sh
make check
make package-smoke
make database-smoke
```

The explicit database gate requires a non-root Linux x86-64 user, PostgreSQL 16
server/client binaries (default `/usr/lib/postgresql/16/bin`; server override
`M4_POSTGRES_BIN`) and local socket/loopback access. It downloads official PostgREST
16.3 once into ignored `artifacts/milestone4/tools/`, checking archive SHA-256
`4eb414eb948c8800863cc8c9896a17b611b2dccf9ff581f4d57f42ec9ccee40d`.
No Docker or hosted credential is needed. No existing database is contacted: a
temporary PostgreSQL cluster uses a private directory/socket and no TCP listener;
a temporary PostgREST process binds only loopback and is shut down afterwards.
Supabase-equivalent roles and real JWT validation exercise the actual SQL/RLS/RPC
path. PostgREST's row limit is deliberately 3 for the twelve-asset test.

These are real PostgreSQL/PostgREST integration checks, not a hosted Supabase
project or gateway/Auth-service test. Missing prerequisites fail the gate rather
than silently skipping it. The quality workflow includes the same explicit gate.
Controlled example output is retained under `artifacts/milestone4/verification/`;
[the portable example](examples/milestone4/run-summary.json) is a selected-field
summary of synthetic test data, not a market forecast or accuracy study.
