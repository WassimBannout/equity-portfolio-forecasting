# Portfolio forecasting

**Milestone 2 is implemented:** validated daily market data, exchange-session
cutoff/target dates, independent Prophet forecasts, dated recent observations,
immutable local input snapshots, and offline replay. The Milestone 1 request and
credential contracts remain unchanged. Allocation, database operations, dashboard,
scheduling, and deployment remain future milestones.

The planned product remains the configured twelve-equity Prophet forecasting,
mean-variance allocation, Supabase publication, and read-only Streamlit demonstrator
defined in the [authoritative handoff](specifications/PROJECT_SPEC.md).
Recommendations are weights; the application does not execute trades.

## Install and verify

The tested baseline is Linux x86-64, Python **3.12.14**, and uv **0.12.13**.
Python/uv versions are pinned in [.python-version](.python-version) and
[pyproject.toml](pyproject.toml); [uv.lock](uv.lock) records resolved dependencies
and artifact hashes. Milestone 2 adds the tested market-data, calendar, and Prophet
dependencies.

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
use no network, market provider, database, or credentials. Runtime dependencies now
include yfinance, exchange-calendars, pandas, NumPy,
Prophet, and timezone data. Pytest, Ruff, mypy, and pandas stubs are development
tools. The native Prophet backend has been verified on Linux x86-64; other
operating systems remain untested.

`make check` verifies lock consistency, lint, formatting, strict typing, and tests.
It does not apply source fixes. `make format` is the separate modifying command.
The packaging check builds an sdist and then its wheel, installs hash-verified
locked runtime dependencies into a fresh temporary environment, and verifies an
isolated import, request resolution, and a real offline Prophet fit without
development dependencies.

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
default exclusive history end is that time's date in New York. Milestone 2 then
resolves exchange sessions and validates actual observations
against the expected cutoff; a date-only request does not prove data freshness.

See [configuration and contracts](docs/CONFIGURATION.md) for defaults, validation,
explicit retrospective requests, metadata semantics, and secret injection.
Creating and resolving a request does not read database credentials.
[.env.example](.env.example) is a blank template, not an automatically loaded file.

## Forecast-only computation

Run the controlled twelve-asset synthetic example without network or credentials:

```sh
uv run --locked python scripts/milestone2_smoke.py
```

On an eligible session before its opening, this explicitly requests live Yahoo data
and emits a forecast-only JSON report with local input snapshots:

```sh
uv run --locked python -m portfolio_forecasting
```

See [Milestone 2 usage and assumptions](docs/MARKET_DATA_AND_FORECASTING.md) for
retrospective requests, replay, failure behavior, provenance, and limitations.
The [recorded synthetic example](docs/examples/milestone2/forecast.json) contains
controlled execution evidence, not an accuracy or live-provider result.

## Project records

- [Architecture](ARCHITECTURE.md): established system design and implemented boundary.
- [Implementation plan](IMPLEMENTATION_PLAN.md): milestone scope and acceptance gates.
- [Decisions](DECISIONS.md): settled choices and implementation evidence.
- [Specification coverage](SPECIFICATION_COVERAGE.md): implemented versus future requirements.
- [Milestone 2 report](MILESTONE_2_REPORT.md): implementation and verification evidence.
- [Milestone 1 report](MILESTONE_1_REPORT.md): changes, commands, results, and limitations.
- [Milestone 0 report](MILESTONE_0_REPORT.md): retained historical design record.

The user's `to_keep/REBUILD_PLAN.md` handoff is present here as
[specifications/REBUILD_PLAN.md](specifications/REBUILD_PLAN.md), the same source
used for Milestone 0. All seven supplied documents remain unchanged and are
trackable alongside the implementation. The original implementation was not consulted.

**Stop at Milestone 2. Do not start Milestone 3 until instructed.**
