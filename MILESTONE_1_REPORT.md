# Milestone 1 report

Scope: the foundation milestone in the supplied
[REBUILD_PLAN.md](specifications/REBUILD_PLAN.md), implemented against the
established Milestone 0 design. The handoff is stored under specifications/, not
to_keep/, in this repository. Milestone 2 has not started.

Status: **Milestone 1 complete.** Primary and clean-checkout verification pass.
Milestone 2 has not started.

## Functionality implemented

- Importable typed Python package with immutable RunRequest, ResolvedRunRequest,
  ForecastSettings, AllocationSettings, DataSettings and PublicationSettings.
- Reference twelve-asset configuration and 2024-01-01 start; normalized ordered,
  duplicate-free tickers; strict date, mode, revision, numerical and nested-setting
  validation; early budget/bound feasibility checks.
- One aware clock read per resolution, UTC execution time, exchange-local exclusive
  end date using locked New York rules, explicit retrospective mode for historical
  requests, and detached JSON-compatible nonsecret metadata.
- Separate configured risk-history and annual-seasonality gates. Default risk
  requires 252 returns/253 prices; shorter live gates cannot be silently selected.
- Explicit adjusted-close/USD/XNYS and full-universe policy plus bounded retry
  settings. This defines policy only; no ingestion, session targeting or retry
  execution is implemented.
- Publication URL/key environment validation on explicit request, secret-safe
  representations/errors, no implicit environment-file loading, no credentials
  needed for ordinary configuration/installation/testing.
- Pinned interpreter/tool/build versions, an independently generated dependency
  lock, local quality commands, deterministic tests, isolated sdist/wheel install
  verification, and one minimal GitHub Actions quality workflow.
- Updated setup/contract documentation, requirement status and engineering record.

## Requirements satisfied

| Requirement | M1 evidence | Qualification |
| --- | --- | --- |
| F01 | Fixed-clock UTC/exchange-date resolution; midnight/DST/year-boundary tests | Market-session targets and live deadlines remain M2/M6 |
| F03 | Request/numerical/universe/feasibility validation and configurable separate history policies | Actual observations and optimiser validation remain M2/M3 |
| F07 | Python/uv/build pins, independent hashed lock, fresh environment checks and serializable resolved settings | Native scientific compatibility and full run/data provenance remain later |
| F12 | 118 deterministic offline tests, lint/format/type gate and real package install smoke | Model/database/UI/full-path tests remain their milestones |
| F14 | Explicit price/currency/calendar vocabulary and validated conventions | Provider metadata, snapshots/revisions and public display gate remain later |
| S06 | Only tzdata at runtime; separate quality tools and non-modifying aggregate check | Dependency additions remain incremental |
| O02 | One Actions quality gate using the same local commands | Hosted execution and required-check enforcement need repository hosting configuration |
| D08 | Simple Python contracts and conventional established tooling | All other retained technology guardrails remain unchanged |

The coverage document marks only these M1 portions as implemented. It does not
mark multi-milestone corrections complete in their entirety.

## Added or changed components

| Files | Purpose |
| --- | --- |
| pyproject.toml, uv.lock, .python-version | Package/build metadata, exact requirements and resolved artifact hashes, interpreter/tool pins |
| src/portfolio_forecasting/__init__.py, config.py, publication.py, py.typed | Public typed foundation and validation boundaries |
| tests/test_config.py, tests/test_publication_settings.py | Configuration, timing, immutability, numerical and credential contract tests |
| Makefile, scripts/package_smoke.py | Non-modifying quality tasks, explicit formatter, isolated packaging verification |
| .github/workflows/quality.yml | Main/PR/manual quality workflow, read-only permissions, immutable official actions |
| docs/CONFIGURATION.md, .env.example | Actual interface/default contracts and explicit secret injection |
| README.md, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, DECISIONS.md, SPECIFICATION_COVERAGE.md | Setup instructions, implementation evidence and accurate milestone status |
| .editorconfig, .gitignore | Makefile tabs and narrow exceptions retaining the authoritative handoff |
| MILESTONE_1_REPORT.md | This milestone evidence and limitation record |

Git's local info/exclude initially hid specifications/. Narrow project ignore
exceptions now make those seven existing documents trackable. Their contents
remain byte-for-byte unchanged; Git metadata was not edited. MILESTONE_0_REPORT.md
remains the historical M0 record.

## Engineering decisions

The architecture was not redesigned. Frozen standard-library records are enough
for this boundary; no settings framework, service abstraction or application CLI
was necessary. Fields with numerical semantics reject booleans, numeric strings,
NaN/infinity and unsupported values rather than coercing them silently. Feasibility
uses decimal representations of fractional settings; future solver tolerances do
not excuse an invalid request.

The timezone database is the sole runtime dependency. Reading it explicitly
avoids host timezone-data drift while preserving the established New York
date policy. No exchange-calendar logic is claimed by timezone conversion.

The verified Linux x86-64 environment uses Python 3.12.14, uv and uv_build 0.12.13,
tzdata 2026.4, pytest 9.1.1, Ruff 0.16.7 and mypy 2.3.1. uv.lock includes transitive
dependencies and artifact hashes from the public PyPI registry. Future scientific
libraries are intentionally not installed until used in M2/M3.

The existing workstation's uv 0.9.26 and default Python were preserved. The pinned
uv was installed at /tmp/portfolio-forecasting-m1-bin/uv and Python 3.12.14 was
installed with --no-bin. Documented ordinary commands use uv 0.12.13 on PATH.

The Actions workflow uses verified immutable official checkout/setup-uv revisions,
contents: read, no persisted Git credentials, no secrets, and a ten-minute timeout.
It runs the same checks and checks for tracked source changes afterward. No batch
schedule or release automation was added.

## Commands executed and results

Inspection used pwd, rg, ancestor AGENTS.md checks, ls, git status/log/ls-files/
check-ignore, and the authoritative Milestone 1 definition plus the M0 documents.
No additional applicable AGENTS.md was found. Only supplied handoff material and
official Python/uv/package/action sources were consulted, never the original
implementation.

Initial sandboxed discovery/status exited 1 before execution with
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted. Necessary commands
subsequently ran through approved escalation. This is an environment limitation,
not a test failure.

Tool selection/install:

| Command | Result |
| --- | --- |
| uv --version; python3 --version; uv python list --only-installed | Existing uv 0.9.26, default Python 3.14.2; also found system 3.12.3 |
| Python urllib reads of official PyPI JSON for uv/uv_build/pytest/Ruff/mypy/tzdata | Verified selected package versions and Python compatibility metadata |
| UV_TOOL_DIR=/tmp/portfolio-forecasting-m1-tools UV_TOOL_BIN_DIR=/tmp/portfolio-forecasting-m1-bin uv tool install uv==0.12.13 | Exit 0; isolated pinned tool installed without replacing the existing uv |
| /tmp/portfolio-forecasting-m1-bin/uv python list 3.12 | Identified downloadable CPython 3.12.14 |
| /tmp/portfolio-forecasting-m1-bin/uv python install 3.12.14 --no-bin | Exit 0; interpreter installed without changing default executable links |
| git ls-remote https://github.com/actions/checkout.git refs/tags/v7.0.1 | Exit 0; verified 3d3c42e5aac5ba805825da76410c181273ba90b1 |
| git ls-remote https://github.com/astral-sh/setup-uv.git refs/tags/v9.0.0 | Exit 0; verified c771a70e6277c0a99b617c7a806ffedaca235ff9 |

Implementation verification (uv below means the isolated pinned executable above):

| Command | Result |
| --- | --- |
| uv lock | Exit 0; independently resolved 15 lock entries |
| uv sync --locked | Exit 0; created .venv with Python 3.12.14 and 14 installed distributions including the project; platform-specific lock entries need not install on Linux |
| make format UV=/tmp/portfolio-forecasting-m1-bin/uv | Exit 0; applied the explicitly separate formatting step |
| make lint UV=/tmp/portfolio-forecasting-m1-bin/uv, initial run | Exit 2 from make: three lint findings in test/helper code; all corrected |
| make typecheck UV=/tmp/portfolio-forecasting-m1-bin/uv, initial run | Exit 0; strict checking passed for six Python files |
| make test UV=/tmp/portfolio-forecasting-m1-bin/uv, initial run | Exit 0; 115 tests passed |
| make check UV=/tmp/portfolio-forecasting-m1-bin/uv, after fixes/regressions | Exit 0; lock consistency, lint, format and strict typing passed; 118 tests passed |
| make package-smoke UV=/tmp/portfolio-forecasting-m1-bin/uv | Exit 0; built sdist then wheel, exported locked runtime hashes, installed in a fresh venv and passed isolated import/request resolution without pytest/mypy |
| Python SHA-256 comparison against the initial specification baseline | Exit 0; all seven supplied files unchanged |
| python3 /tmp/portfolio_forecasting_m1_verify.py | Exit 0; 76 local links, 34 requirement IDs, unchanged specification hashes, version/scope checks, identical fresh dependency set, full quality gate with 118 passing tests, package smoke, executable documentation examples, source immutability and ignore checks all passed |

make check expands to uv lock --check, uv run --locked ruff check .,
uv run --locked ruff format --check ., uv run --locked mypy, and
uv run --locked pytest. The formatter applies fixes only when explicitly requested.

The packaging helper executes uv build, uv export --locked --no-dev
--no-emit-project, uv venv, uv pip sync --require-hashes, uv pip install --no-deps
for the built wheel, and an isolated Python -I import/metadata/request assertion.
Its temporary directory is cleaned after execution.

## Tests performed

118 collected cases cover reference configuration/units, normalized immutable
universes and nested settings, empty/duplicate/malformed symbols, 1/12/20/21-asset
bounds and infeasible ceilings, invalid/reversed bounds, nonfinite/oversized
numerical values, booleans/numeric strings, risk/annual history independence,
explicit shorter retrospective policies, component/data-policy validation,
invalid dates/revisions/modes/nested settings, one clock reading per invocation,
re-resolution across exchange midnight, DST and year boundaries, UTC normalization,
future/historical end restrictions, detached JSON metadata, credential absence,
mapping precedence, URL/port validation, key redaction, and absence of implicit
dotenv loading. All use deterministic local fixtures.

The real package test verifies both build formats, the py.typed marker, installed
distribution metadata, import from the fresh environment rather than the source
tree, absence of development dependencies, and request resolution using the
runtime timezone data.

## Known limitations and deferred work

- No M2+ behavior exists: no market download, actual history sufficiency check,
  exchange-session selection, forecast, covariance/solver, outcome evaluation,
  database schema/write/read, dashboard, schedule or deployment.
- No Prophet/native scientific compatibility, model quality or investment
  performance is claimed. Those require their assigned milestones and evidence.
- Publication settings validation checks input shape only; it does not establish
  endpoint availability or permissions. Actual roles/credentials are M4/M6.
- The verified environment is Linux x86-64. Other OS/architecture combinations and
  future native dependencies need their own checks.
- The quality workflow is implemented and its commands run locally. No hosted
  GitHub Actions execution or branch-protection configuration was performed.
- The shell sandbox cannot initialize in this session; approved commands allowed
  work to proceed. Temporary tool/audit locations are not runtime dependencies.

No overall design contradiction or blocker required reopening an M0 decision.
All M1 implementation failures identified during verification were fixed. The
final clean candidate checkout passed independently of the existing .venv and
left all candidate source files unchanged. The temporary audit script/baseline
remain in /tmp and are not application dependencies.

No commit or external publication was created. The new source files, lockfile,
and unchanged handoff are ready for version control. **Work stops at Milestone 1.**
