# Milestone 6 report

Completed local implementation and verification on **15 September 2026
(Asia/Beirut)**. **Milestone 6 is the final planned milestone.** Production
commissioning and prospective operational acceptance remain outstanding.

The user explicitly confirmed that a project VPS/domain, Supabase project,
deployment credentials and intended market-data display authorisation are not yet
provisioned/configured. This report separates actual local tests, static
configuration validation and unperformed live checks. **No deployment, public
HTTPS URL, hosted scheduler success or prospective forecast is claimed.**

## Reconstructed baseline and scope

The repository started at committed Milestone 5 revision
`fb051d24184f55300489d337f257b2695bc1edfc`. Read the architecture, decisions,
implementation plan, coverage matrix, M5 report, relevant supplied specifications,
existing scientific/publication/dashboard contracts, tests, workflows and packaging/
recovery files before implementing the operational layer. `specifications/` was
already untracked and remains unchanged. HEAD remains unchanged; no commit was
requested or made in the project repository.

Milestones 0–5 remain the established baseline. No scientific default, model,
allocation method, publication schema, credential role, numerical contract or
existing dashboard data contract was redesigned. No runtime dependency was added:
`uv.lock` remains byte-identical, with 78 package identities and SHA-256
`15b91a943d5641f75d21c47d90928ade69d7a0cd7dda8c97821804308482ebde`.

## 1. Locally implemented and verified

| Requirement | Implementation and actual local evidence |
| --- | --- |
| F07/F08/F12: exact tested release | Release calls the same-revision reusable full Quality workflow, explicitly checks out/archives `github.sha`, and checks archive commit identity. A new release directory receives a fresh locked, runtime-only, non-editable environment with a Git/source/lock manifest. A real temporary Git revision was archived, installed and verified locally. |
| F08: readiness and recovery | Verify HTTP health, installed package fingerprint, lock hash, actual reader role and a complete published result. Real non-root Streamlit plus disposable PostgreSQL/PostgREST passed readiness. A corrupted source fingerprint failed readiness and restored/rechecked the prior working release. Deterministic checks cover initial failure, ordinary rollback and interrupted pointer switching. |
| F09: constrained inputs | Tested rejection of wrong archive revision, path traversal, absolute paths, symlinks, excessive size and injected SSH host syntax. Gateway uses argument lists and a fixed command allowlist. Actual process-group timeout and cross-process lock exclusion are exercised. |
| F01/F04/F13: daily behavior | Wrap existing M2/M4 contracts without replacing them. Closed sessions and identical published forecasts have explicit no-op outcomes; late jobs fail before provider/database access. Existing provider/DB transient retry and database deadline/idempotency tests remain green. |
| F13/S05: missing-run detection | XNYS-aware due-session calculation, 10:00 UTC threshold after the 09:00 request, weekend/holiday/year/DST tests, bounded scanning, and missing/stale/unknown/unavailable states. A retrospective or unrelated configuration cannot clear live freshness. Candidate live results require complete-read validation. |
| F05/F13/S05: last-success visibility | Optional deployed status footer shows expected target, last successful live publication/cutoff/run ID and check time. Tests cover a stopped monitor, malformed file, outage handling and secret-safe CLI failure output. The independent read-only timer can detect absent Actions results without scheduling additional forecasts. |
| F06/F13/S05: recovery of outcomes | Associate exact earlier targets using the successful batch's durable input, within a 14-day/250-run bound. Real database checks verify matched outcomes and repeat-safe recovery; M4 retains incompatible-price-basis rules. No backdated live forecast is created. |
| F12: previous milestones | All prior offline and real database/UI tests pass, including native Prophet fits, twelve-asset coherent reads, Chrome interactions, permissions, transactional failures/concurrency and actual disposable backup/restore. |

The clean-release integration test copies the current task files into a temporary
Git repository, creates a **local test commit**, archives that exact commit and
runs the production install/activation code. Its serving process uses a fresh
installed runtime and the existing disposable-PostgREST dashboard fixture entrypoint.
Only the systemd restart boundary is replaced with an actual local process restart
and health/installed-reader checks. It verifies non-root UID, matching revision,
healthy service after recovery, and cleanup. This is neither a project commit nor
hosted CI/systemd/HTTPS operating evidence.

## 2. Configuration validated statically

| Configuration | Verification and boundary |
| --- | --- |
| Actions quality/release/daily workflows | Pinned actionlint **1.7.7** passes. Deterministic checks enforce immutable action references, `contents: read`, same-revision gate, main restriction, deployment-use guard and shared concurrency group with cancellation disabled. Actual GitHub environment/branch protections and workflow execution are not configured here. |
| SSH deployment | Root-owned restricted authorised key, forced bounded gateway, non-root deployment user, strict supplied known_hosts, no forwarding/TTY/user startup scripts, temporary mode-restricted key files and fixed sudo commands are reviewed in the artifacts. No real deployment SSH connection or host-key mismatch drill was possible. |
| systemd supervision/identities | Dashboard, batch, freshness service and timer pass **systemd-analyze 255.4** validation in a temporary root with inert executable placeholders. This checks unit structure/dependencies without installing/starting a host service. Actual `pf-web`, `pf-batch`, `pf-deploy` identities, service hardening and permissions remain host checks. |
| Privileged commands | `visudo -cf deploy/sudoers` passes. Only dashboard restart/failure reset and batch/freshness starts are granted. The reset permits recovery even after a failed candidate hits the service start limit. |
| HTTPS reverse proxy | Ubuntu Caddy **2.6.2-6ubuntu0.24.04.3** binary validates the Caddyfile with a placeholder domain, including automatic HTTPS and HTTP redirect configuration. No public certificate, DNS, firewall or externally reachable endpoint was exercised. |
| Bootstrap and shell entrypoints | `bash -n` validates provisioning/SSH scripts; `sh -n` validates readiness. Clean-host bootstrap verifies the pinned uv binary digest, installs root-owned interpreter/helpers and non-root services, restricts SSH and installs proxy/unit configuration. It was **not executed against this workstation or a VPS**. |
| Credentials and data-use gate | Separate root-only reader/writer environment files, a restricted writer JWT, production secret/variable names and an explicit intended-use approval gate are documented. No real credentials/signing material or rights confirmation were supplied. |

The service requires three bounded readiness probes. The batch has a 1,400-second
execution timeout, kill grace and a systemd upper bound; it never automatically
restarts a failed scientific job. Existing socket retries remain bounded. A shared
host file lock excludes batch/release work in addition to Actions concurrency and
SQL uniqueness. The read-only freshness timer runs every 15 minutes; records older
than 30 minutes become visibly overdue on the next UI access.

## 3. Live checks outstanding

These are **not passed**, because the user-confirmed external prerequisites and
prospective observation period are unavailable:

- Clean production VPS provisioning, actual non-root deployment/runtime identities,
  SSH key restriction/host-key rejection, credential-file protection and rotation.
- Actual protected-main/production Actions settings, release/manual/daily execution,
  notifications, queue/overlap behavior and controlled remote failures/recovery.
- Real domain/DNS/firewall, public certificate/redirect, HTTPS health/revision checks,
  read-only browser flow and confirmation that port 8501 is not externally exposed.
- Hosted Supabase migrations/gateway, actual restricted reader/writer token handling,
  project backup configuration and restore/recovery-time measurement.
- Confirmed intended market-data retention/public display rights. Release is gated
  until the operator supplies that confirmation; no legal conclusion is inferred.
- Multiple actual prospective eligible-session publications and at least one later
  exact-target comparable matured outcome. Historical/synthetic records cannot
  satisfy this requirement.

The [operations runbook](docs/OPERATIONS.md) supplies the host procedure, exact
external variable/secret names, first-release checks, manual rerun/rollback/resume,
missed-session policy, bounded outcome catch-up, retention and backup/restore
instructions. These values can be supplied later without changing the architecture.
There is no Kubernetes, Airflow, new cloud service, token issuer, custom API or
additional forecast scheduler.

## Decisions and practical limitations

[ADR-016](DECISIONS.md#adr-016--milestone-6-release-and-scheduler-controls) records
the implementation choices. The current deployed release runs the batch; Actions
is the remote trigger. Git archive metadata validates the supplied identity but is
not an independent signature proving CI success: trust in the reviewed production
workflow and restricted key must be enforced by the hosting repository settings.
Root-owned helpers/unit changes require administrative review separately from code
release. Application rollback does not roll back database state.

An empty database may pass service readiness with `latest_run: null`; it remains
missing for operational freshness. A failed first deployment has no predecessor.
A database/provider outage can leave an older successful run visible, and an outcome
recovery error can follow successful publication. These are labelled failures, not
claims that no write happened. Recovery must inspect the bound run before retrying.
An elapsed live target stays missing; later research is explicitly retrospective.

The monitor checks the latest expected result and exposes journal/Actions/UI signals.
It is not an external pager, cannot detect total VPS failure from that same host,
and its UI footer updates on page access. History/outcome scans are deliberately
bounded, and older catch-up remains manual. No automatic data or release deletion
is introduced. JWT provisioning/rotation, hosted backups and provider reliability
remain operator responsibilities. Existing scientific evidence does not establish
forecast accuracy, investability or profitable trading.

## Files and components

**29 task files: 10 modified baseline files and 19 additions.**

- `.github/workflows/quality.yml`, new `release.yml` and `daily.yml`: shared complete
  release gate, exact revision, serialisation, schedule/manual operations and signals.
- `deploy/`: gateway, clean-host bootstrap, dashboard/batch/freshness units, timer,
  readiness entrypoint, Caddyfile and narrow sudoers policy.
- `src/portfolio_forecasting/operations.py`, `streamlit_app.py`: operational wrapper,
  exact-outcome catch-up, readiness/freshness CLI and optional last-success footer.
- `tests/test_operations.py`, `tests/test_deployment.py`,
  `integration/test_operations.py`: 35 new offline and 3 new real-integration cases.
- `scripts/remote.sh`, `scripts/deployment_checks.py`, `scripts/package_smoke.py`,
  `Makefile`, `pyproject.toml`: SSH invocation, static validators, expanded package
  check, gate targets and strict typing coverage. Dependency declarations unchanged.
- `docs/OPERATIONS.md`, `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
  `IMPLEMENTATION_PLAN.md`, `SPECIFICATION_COVERAGE.md`, this report: actual scope,
  evidence, commissioning requirements and final-milestone status.

## Commands and exact results

Commands ran in `/home/wassim/code/portfolio-forecasting` except the explicit
Ubuntu package download, which ran in `/tmp`. In the commands below:

```sh
PINNED_UV=/home/wassim/.cache/uv/archive-v0/7S7aC_6BQ3jtOceC_r9uG/uv-0.12.13.data/scripts/uv
CADDY_BIN=/tmp/pf-m6-tools/caddy/usr/bin/caddy
```

| Final command | Actual result |
| --- | --- |
| `make check UV="$PINNED_UV"` | **Exit 0**; 78 locked packages; Ruff passes; **84 files already formatted**; mypy **58 source files**, no issues; **378 passed in 157.19s** |
| `M5_RECORD_DEMO=1 M5_BROWSER_PYTHON=/tmp/portfolio-m5-browser/bin/python M6_UV="$PINNED_UV" make database-smoke UV="$PINNED_UV"` | **Exit 0; 32 passed in 95.94s**; all 29 prior integration cases plus 3 M6 cases; real Chrome and disposable backup/restore included |
| `make package-smoke UV="$PINNED_UV"` | **Exit 0**; fresh sdist/wheel, hash-locked runtime-only install, native Prophet and SciPy checks, publication imports, installed Streamlit render and operational imports/calendar; all six PASS messages |
| `make deployment-smoke UV="$PINNED_UV" CADDY="$CADDY_BIN"` | **Exit 0; 35 passed in 6.73s** on the final rerun; shell syntax, isolated systemd units, Caddy HTTPS config and pinned actionlint all pass |
| `visudo -cf deploy/sudoers` | **Exit 0; `deploy/sudoers: parsed OK`** |
| `go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 -color=false` | **Exit 0**, no diagnostics; included in deployment gate |
| `apt-get download caddy=2.6.2-6ubuntu0.24.04.3` in `/tmp`; `dpkg-deb --extract /tmp/caddy_2.6.2-6ubuntu0.24.04.3_amd64.deb /tmp/pf-m6-tools/caddy` | Package downloaded/extracted for validation only; no workstation service installed or started |
| `.venv/bin/python artifacts/milestone6/verification/final_audit.py` | **Exit 0**; 29 task files; 92 baseline files and all tested input hashes preserved; **167 local links resolve**; credential-pattern/whitespace checks pass |
| `.venv/bin/ruff check .`; `.venv/bin/ruff format --check .`; `git diff --check` after documentation | **Exit 0**; lint passes; **85 files already formatted**; no whitespace errors |
| Filtered `ps -eo comm=,args=` cleanup audit | **PASS**; no disposable PostgreSQL/PostgREST/Streamlit processes remain |
| SHA-256 baseline audit | **92 of 102 baseline files byte-identical**; only 10 intended baseline files differ; all 7 specifications and both migrations unchanged; project HEAD unchanged |

The **410 unique passing tests** comprise **372 prior cases plus 38 M6 cases**.
The separate 35-case deployment target repeats its offline subset and is not added
to that total. Packaging and browser checks supplement the count.

Chrome **151.0.7922.137** verified the existing exact session-axis label, forecast
hover/run/revision, slider range `[122.91, 136.09]` to `[122.92, 136.09]`, and native
zoom to `[126.25790369217083, 132.81946952846977]`; `browser_errors: []`, `result: PASS`.
The regenerated evidence stays in ignored `artifacts/milestone5/demo/`; historical
committed M5 example files/reports were not overwritten.

Logs and input fingerprints are retained in ignored
`artifacts/milestone6/verification/`: `check.log`, `database.log`, `package.log`,
`deployment.log`, `deployment-final.log`, `baseline.json` and `tested-inputs.json`.
The first deployment-gate pass was **35 passed in 9.17s**. The final diff review
then moved public URL validation before transfer and required health body `ok`;
the affected deployment/workflow gate was rerun and passed as recorded above.
Python implementation, package inputs and scientific/integration tests did not
change after their final full gates.

Development failures were corrected before these final results: sandbox startup
failure, Ruff/import/type errors, the calendar range ending before a weekend or
holiday query, and a closed-session fixture using the real clock. The direct
`systemd-analyze verify deploy/...` attempt correctly reported missing production
executables; the final isolated-root validator makes that static boundary explicit.
Caddy formatting was corrected. Earlier partial passes are not substituted for
final evidence. The sandbox failed with `bwrap: loopback: Failed RTM_NEWADDR:
Operation not permitted`; commands used approved escalation. Existing native
migration/AppTest warnings did not fail the gates.

## Final diff audit and stopping boundary

The final audit passed for intended file scope, unchanged baseline/tested-input
hashes, all 167 local Markdown links, credential-pattern exposure and whitespace.
No disposable test processes remain. All **24 prior package files, 17 test files, 5 integration files, 2 SQL
migrations, 7 specifications, the dependency lock and previous milestone reports**
remain byte-identical. The only existing UI source change is the entrypoint's
optional operational footer; existing dashboard modules remain unchanged.

**Local Milestone 6 scope is complete. Full live operational acceptance is not.**
The project stops at Milestone 6 with the external commissioning checklist above;
no additional milestone or redesign is started.
