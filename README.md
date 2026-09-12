# Portfolio forecasting

**Milestone 1 is complete:** an installable Python foundation, validated immutable
requests, deterministic date resolution, explicit publication settings, a locked
environment, and an automated quality gate. No data ingestion, forecasting,
allocation solver, database operations, dashboard, or deployment is implemented yet.

The planned product remains the configured twelve-equity Prophet forecasting,
mean-variance allocation, Supabase publication, and read-only Streamlit demonstrator
defined in the [authoritative handoff](specifications/PROJECT_SPEC.md).
Recommendations are weights; the application does not execute trades.

## Install and verify

The tested baseline is Linux x86-64, Python **3.12.14**, and uv **0.12.13**.
Python/uv versions are pinned in [.python-version](.python-version) and
[pyproject.toml](pyproject.toml); [uv.lock](uv.lock) records resolved dependencies
and artifact hashes. Scientific/service dependencies arrive in their milestones.

Install the pinned uv using its [official installation method](https://docs.astral.sh/uv/getting-started/installation/):

```sh
curl -LsSf https://astral.sh/uv/0.12.13/install.sh | sh
```

Follow the installer's PATH instructions or open a new shell. From the checkout:

```sh
uv --version
uv python install
uv sync --locked
make check
make package-smoke
```

Initial setup needs access to Python/package downloads; the configuration tests
use no network, market provider, database, or credentials. The only runtime
dependency is the pinned timezone database; pytest, Ruff, and mypy are development
tools. Other operating systems/native forecasting dependencies are not yet tested.

`make check` verifies lock consistency, lint, formatting, strict typing, and tests.
It does not apply source fixes. `make format` is the separate modifying command.
The packaging check builds an sdist and then its wheel, installs hash-verified
locked runtime dependencies into a fresh temporary environment, and verifies an
isolated import and request resolution without development dependencies.

The [quality workflow](.github/workflows/quality.yml) runs the same checks on main
pushes, pull requests, and manual invocation. GitHub execution/branch protection
must be enabled in the hosting repository; a local pass is not evidence of a
hosted CI run. No scheduling or deployment workflow is included.

## Use the foundation

```python
from datetime import UTC, datetime

from portfolio_forecasting import RunRequest

request = RunRequest()
resolved = request.resolve(
    clock=lambda: datetime(2026, 9, 12, 9, tzinfo=UTC),
)
assert resolved.history_end.isoformat() == "2026-09-12"
metadata = resolved.to_metadata()
assert len(metadata["tickers"]) == 12
```

Omit `clock` to capture the current aware UTC time at each invocation. The
default exclusive history end is that time's date in New York. An observation
cutoff and forecast target cannot be inferred from a request alone; those require
validated market data and exchange sessions in Milestone 2.

See [configuration and contracts](docs/CONFIGURATION.md) for defaults, validation,
explicit retrospective requests, metadata semantics, and secret injection.
Creating and resolving a request does not read database credentials.
[.env.example](.env.example) is a blank template, not an automatically loaded file.

## Project records

- [Architecture](ARCHITECTURE.md): established system design and implemented boundary.
- [Implementation plan](IMPLEMENTATION_PLAN.md): milestone scope and acceptance gates.
- [Decisions](DECISIONS.md): settled choices and implementation evidence.
- [Specification coverage](SPECIFICATION_COVERAGE.md): implemented versus future requirements.
- [Milestone 1 report](MILESTONE_1_REPORT.md): changes, commands, results, and limitations.
- [Milestone 0 report](MILESTONE_0_REPORT.md): retained historical design record.

The user's `to_keep/REBUILD_PLAN.md` handoff is present here as
[specifications/REBUILD_PLAN.md](specifications/REBUILD_PLAN.md), the same source
used for Milestone 0. All seven supplied documents remain unchanged and are
trackable alongside the implementation. The original implementation was not consulted.

**Stop at Milestone 1. Do not start Milestone 2 until instructed.**
