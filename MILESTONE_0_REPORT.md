# Milestone 0 completion report

Date: 12 September 2026. Scope explicitly confirmed by the user: **design
documents, coverage review, and minimal repository scaffold**. The supplied
Milestones 1–6 retain their original numbering. Work stops at M0.

## Delivered

| File | What was implemented |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Independent system design, default settings, time/data/forecast/risk/evaluation contracts, publication, UI, reproduction and operation |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Confirmed M0 scope plus dependencies, deliverables, acceptance evidence and tests for M1–M6 |
| [DECISIONS.md](DECISIONS.md) | Eleven engineering decisions with reasons, consequences, deferred choices and evidence gates |
| [SPECIFICATION_COVERAGE.md](SPECIFICATION_COVERAGE.md) | All product/behavior areas, 14 MUST FIX, 7 SHOULD IMPROVE, 5 OPTIONAL and 8 DO NOT CHANGE recommendations, and all 12 independent acceptance scenarios |
| [README.md](README.md) | Honest project status, document navigation and next authorised boundary |
| [.editorconfig](.editorconfig) | UTF-8/LF, final newline, whitespace and indentation defaults |
| [.gitignore](.gitignore) | Local credentials, environments, caches, generated private datasets and build outputs; future lockfiles remain trackable |
| [MILESTONE_0_REPORT.md](MILESTONE_0_REPORT.md) | This delivery, verification and limitation record |

The three required design documents were created first. The architecture was then
compared with the supplied specifications and the coverage review was created
before the housekeeping scaffold. Only the supplied handoff documents were
consulted; no original implementation, remote project, or production service was
accessed.

## Important decisions

Retain one Python package with batch and read-only Streamlit workloads, Supabase
storage, independent Prophet fits, SciPy mean-variance allocation, and eventual
daily/manual Actions execution on a modest VPS deployment.

Correct the explicitly identified defects: valid session targets, separate UTC
execution/cutoff/target dates, direct forecast expectations and observed-only risk,
full-universe validation, stable retry identity, atomic complete publication,
exact-date outcomes, chronological evaluation, and safe first-run UI states.

Initial policy choices are recorded before implementation: live publication
before the target session opens; at least 252 realised returns for risk plus a
separate two-calendar-year gate when annual seasonality is enabled; positive risk
aversion; and a locked uv environment with one Actions quality gate. The latter
reduces tool/account maintenance in an empty repository. These choices preserve
the required product; empirically selected settings and exact dependency versions
are not claimed as established.

## Commands and results

The command sandbox could not start: `bwrap: loopback: Failed RTM_NEWADDR:
Operation not permitted`. Initial file discovery and Git status each exited 1
without executing. Required shell commands were rerun through approved escalation.
A later patch-update attempt hit the same sandbox failure and its edits were
completed through approved Python file operations.

Inspection commands completed successfully unless qualified below:

| Command | Result |
| --- | --- |
| `pwd && rg --files --hidden` with Markdown/configuration filters and generated-directory exclusions | Located the seven specification files in the new repository |
| Ancestor `AGENTS.md` checks, `ls -la`, and `find specifications -maxdepth 2 -type f -print` | No applicable instruction file found; repository initially contained only Git metadata and specifications |
| `git status --short --branch` | Initial branch main, no commits, only untracked specifications |
| `cat specifications/PROJECT_SPEC.md specifications/REBUILD_PLAN.md specifications/SYSTEM_ARCHITECTURE.md` | Read product, milestone and architecture requirements |
| `cat specifications/BEHAVIOR_SPEC.md specifications/ML_SPEC.md specifications/IMPROVEMENTS.md specifications/ANALYSIS_COMPLETE.md` | Read contracts, ML methodology, recommendations and handoff provenance |
| `cat specifications/REBUILD_PLAN.md`, `cat specifications/BEHAVIOR_SPEC.md`, `cat specifications/ML_SPEC.md specifications/SYSTEM_ARCHITECTURE.md`, `cat specifications/IMPROVEMENTS.md` | Focused reads to recover text truncated in combined tool output |
| `sed -n '145,285p' specifications/ML_SPEC.md` | Confirmed full evaluation and paper-timing requirements |
| `rg -n '^#{1,4} ' specifications/IMPROVEMENTS.md` | Inventoried all recommendation headings |
| `command -v python3 python uv poetry pytest ruff mypy` | Python and uv found; Poetry/pytest/Ruff/mypy not found as commands |
| `python3 --version` | Python 3.14.2 on this workstation; not selected or verified as the project's future runtime |
| `git diff --check` during initial inspection | Passed; repository has no tracked implementation changes |

Python file-operation scripts recorded SHA-256 hashes for all seven supplied
specifications in a temporary baseline, updated confirmed scope/terminology, and
created the documented files. No dependencies were installed. No original source
was fetched, and no database, market provider, deployment or messaging action ran.

Final verification:

| Command | Result |
| --- | --- |
| `python3 /tmp/portfolio_forecasting_m0_checks.py` | PASS, exit 0: 8 intended files, 7 unchanged specification hashes/membership, text hygiene, 62 local links across 13 Markdown documents, all 34 IDs and 12 scenarios |
| `git diff --check` | PASS, exit 0; new untracked files also checked by the Python integrity check |
| `git status --short --branch` | Exit 0: exactly the eight new M0 files plus the original untracked specifications; no commits |
| `git check-ignore --no-index --stdin` with credential/generated/lock/source probes | PASS, exit 0: all 14 secret/generated probes ignored; all 7 example/lock/version/manifest/fixture/document probes remained trackable |

The temporary check and baseline were kept in `/tmp`, outside the repository;
they are milestone audit tooling, not application tests or shipped infrastructure.
The Python check validates UTF-8/LF/final-newline and whitespace hygiene,
local Markdown targets, recommendation ID coverage, scenario count, explicit M0
file scope, and unchanged specification hashes. It examines newly created,
untracked files too; `git diff --check` alone cannot validate their contents.
Recommendation semantics and full behavior coverage were manually compared with
the specifications; checking identifier presence alone would not establish them.

There is no application behavior in this milestone. Unit, type, native-model,
database, UI, package-install and CI checks are therefore not applicable yet.
They are planned, not reported as passed. No placeholder tests were added.

## Unresolved items and stopping point

There are no unresolved product implementation defects in M0 because application
implementation has not begun. The sandbox initialization problem remains an
environment limitation; approved execution allowed the milestone work to finish.

Future gates include a tested Python/tool/package lock, actual provider semantics
and fixtures, model-selection evidence and numerical tolerances, corporate-action
outcome reconciliation, physical database contracts/permissions, and actual
host/domain/credentials/data-publication arrangements. Deployment completion also
requires prospective session runs and a matured outcome. These are explicitly
assigned to later milestones, not silently deferred M0 deliverables.

No application package, dependency manifest/lock, tests, CI/schedule/release
workflows, migrations, downloads, or deployed service was added. No commit was
created. **Milestone 1 has not started.**
