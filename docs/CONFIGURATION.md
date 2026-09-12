# Configuration and information contracts

The M1 configuration contracts below remain unchanged. M2 now executes their
calendar, data-validation, retry, and forecasting policies; see
[market data and forecasting](MARKET_DATA_AND_FORECASTING.md). References below to
M2 identify the consuming layer rather than additional request fields.

Milestone 1 implements request/settings validation only. The established
[architecture](../ARCHITECTURE.md) and [decisions](../DECISIONS.md) remain the
design baseline. Actual data sufficiency, market-session targeting, forecasts,
risk estimation, allocation and storage are later-milestone work.

## Public boundary

Import `RunRequest`, `ResolvedRunRequest`, `ForecastSettings`,
`AllocationSettings`, `DataSettings`, and `PublicationSettings` from
`portfolio_forecasting`. These are frozen dataclasses. Nested settings are also
frozen; ticker input is copied to a tuple so caller mutations cannot change a
validated request. No configuration framework, global settings singleton, or
import-time clock/credential lookup is used.

Construct nonsecret settings in Python. Dates must be `datetime.date`, not
strings or datetimes; this avoids implicit parsing or timezone truncation.
Unknown constructor keywords raise `TypeError`; invalid supported values raise
field-specific `ValueError`. Numerical strings and booleans are not accepted as
numeric settings. NaN, infinity, and values too large to represent as finite
floating-point inputs are rejected where a positive real number is required.

| Request field | Default and contract |
| --- | --- |
| tickers | AMD, MSFT, AAPL, TSLA, AMZN, NVDA, META, GOOG, TSM, JPM, NFLX, PLTR, in that order |
| ticker syntax | Ordered nonempty string sequence; trim/uppercase; unique after normalization; letters/digits with optional dot/hyphen-separated components |
| history_start | 2024-01-01, inclusive |
| history_end | Omitted initially; exclusive bound resolved per invocation |
| mode | live or retrospective; live is the default |
| scientific_revision | "1"; explicit 1–64 character alphanumeric/dot/underscore/hyphen label |
| forecast | Validated ForecastSettings |
| allocation | Validated AllocationSettings |
| data | Validated DataSettings |

Ticker syntax validation does not establish that a security exists, is USD
denominated, or follows the chosen exchange schedule. Provider metadata validation
belongs to M2. No universes are silently reduced.

## Time resolution

`request.resolve(clock=...)` calls the injected clock exactly once. Without a
clock argument it captures `datetime.now(UTC)` at invocation, not at import or
request construction. The clock must return an aware datetime; non-UTC inputs
are converted to UTC. The default end is the execution timestamp's date in
`America/New_York`, independent of the machine-local timezone.

New York rules are loaded explicitly from the locked `tzdata` package using
`ZoneInfo.from_file`, avoiding variation from host timezone-database updates.
The standard API supports loading timezone files directly.
[Python zoneinfo documentation](https://docs.python.org/3.12/library/zoneinfo.html).

The resolved start must precede the exclusive end. End dates after the
exchange-local execution date are rejected. A live request's explicit end must
equal that local date; a past explicit end requires retrospective mode.

```python
from datetime import UTC, date, datetime

from portfolio_forecasting import AllocationSettings, ForecastSettings, RunRequest

research = RunRequest(
    mode="retrospective",
    history_end=date(2025, 9, 1),
    scientific_revision="research-1",
    allocation=AllocationSettings(risk_window=60),
    forecast=ForecastSettings(yearly_seasonality=False),
)
resolved = research.resolve(
    clock=lambda: datetime(2026, 9, 12, 9, tzinfo=UTC),
)
assert resolved.history_end == date(2025, 9, 1)
assert resolved.to_metadata()["mode"] == "retrospective"
```

This validation does not decide whether the run date is a market holiday or
whether publication is still before the session opening. M2/M6 add calendar and
deadline enforcement. An execution timestamp, requested end, observed cutoff,
and forecast target are different concepts; M1 deliberately does not fabricate
the latter two.

## Scientific policy settings

| Record / field | Default | Validation / meaning |
| --- | --- | --- |
| Forecast: yearly_seasonality | true | Strict boolean; enabled live requests require at least two calendar years |
| Forecast: weekly_seasonality | true | Strict boolean |
| Forecast: daily_seasonality | false | true is unsupported for daily close forecasts |
| Forecast: holiday_effects | true | Strict boolean; actual holiday features and coverage are M2 |
| Forecast: minimum_yearly_history_years | 2 | Integer at least 1; live yearly mode requires at least 2 |
| Allocation: risk_aversion | 5.0 | Finite positive number; zero/negative is unsupported |
| Allocation: lower_bound / upper_bound | 0.05 / 1.0 | Finite fractions with 0 <= lower <= upper <= 1 |
| Allocation: risk_window | 252 | Integer at least 2; live requests require at least 252 |
| Data: price_basis / currency / calendar | adjusted_close / USD / XNYS | Only these conventions are currently supported |
| Data: require_full_universe | true | Cannot be disabled |
| Data: download_attempts | 3 | Integer from 1 through 3; actual retry execution is M2 |
| Data: request_timeout_seconds | 30.0 | Finite positive per-attempt timeout |
| Data: retry_backoff_seconds | 1.0 | Finite positive base backoff; exponential delays before later attempts |
| Data: recent_history_days | 30 | Positive integer; future dated context is inclusive of cutoff minus this many calendar days |

The declared default retry policy is at most three transient-failure attempts,
with 1-second and 2-second delays and a 30-second per-attempt timeout. Invalid
payloads fail without retries. Exhaustion will yield a failed, unpublished run
with missing tickers reported, preserving the previous successful result.
M1 defines/validates this policy; no network or retry loop is implemented.

Bounds are checked before any solver: `N * lower <= 1 <= N * upper`. Decimal
representations of configured bounds are used for this configuration feasibility
check, so a numerical solver tolerance cannot silently excuse an infeasible
request. For twenty assets at 5%, the floor consumes the entire budget; twenty-one
are rejected. One asset needs a ceiling of 1. The twelve-asset floor implies a
45% effective maximum allocation.

The risk window is also the minimum required count of complete realised return
vectors; `required_price_observations` is one greater. The default is therefore
252 returns and 253 prices. The annual-history requirement is independent:
having 253 prices does not establish two calendar years of data. Shorter research
windows/annual spans require an explicit retrospective request. These settings
are validated now; checking actual observations and seasonal span happens in M2.

Future expected returns use direct fractional forecast returns; sample covariance
uses observed returns only. Neither estimator nor the half-factor Markowitz
objective is implemented in this milestone. Adjusted research prices are not
asserted to be raw executable trade prices.

## Nonsecret request metadata and future results

`resolved.to_metadata()` returns a detached JSON-compatible dictionary containing
the effective settings, normalized ordered tickers, inclusive start, resolved
exclusive end, original optional end, UTC execution timestamp, and exchange
timezone. Changing that dictionary cannot mutate the validated request. No
rounding is applied to scientific settings and no credentials are included.

This dictionary is a request record, not a forecast result or retry identity.
The later logical result owns the shared run ID, mode/revision, actual cutoff and
target, complete ticker-matched observed/predicted prices, forecast returns,
weights, dated history, software/data provenance and publication status, as
specified in the architecture. Snapshot binding, stable run identity, atomic
publication and exact target-date outcomes are not implemented prematurely.

## Explicit secret injection

No credentials are necessary for installation, tests, import, or request
resolution. When a future publication/read operation needs a connection,
`PublicationSettings.from_environment()` explicitly reads `SUPABASE_URL`
and `SUPABASE_KEY`. Passing a mapping uses only that mapping; it never falls back
to hidden process values.

Both settings are required and nonempty. The URL must be a base HTTPS URL without
embedded credentials, query, fragment or API path. HTTP is allowed only for
localhost/127.0.0.1/::1 disposable local services. Invalid ports and whitespace
are rejected. Keys cannot contain whitespace. Validation checks shape only; it
does not connect to Supabase or prove authorization. Keys are excluded from the
record's repr, and validation messages do not echo secret values.

[.env.example](../.env.example) contains blank names only. A local .env file alone
does nothing. Set the process environment explicitly, for example:

```sh
export SUPABASE_URL='https://your-project.supabase.co'
export SUPABASE_KEY='replace-with-the-appropriate-workload-credential'
```

Use the appropriate GitHub secret environment for a future batch job and protected
systemd environment injection for the future dashboard. Provision separate
restricted writer and read-only reader credentials in M4/M6; administrative
credentials never belong in browser output. Do not log/serialize the publication
settings as scientific metadata. There is no application-level .env loader or
automatic Streamlit secret lookup.

## Development checks

`make check` runs lock validation, Ruff lint, Ruff formatting checks, strict mypy
over package/tests/helper, and deterministic pytest cases. `make format` is the
separate modifying command. `make package-smoke` builds sdist -> wheel and checks
a fresh runtime-only environment using hash-verified requirements exported from
the same lock. Temporary packaging artifacts are cleaned when the command exits.

Run `uv lock` only when intentionally changing dependencies, then review and retain
the new lock together with the manifest. Normal installs use `uv sync --locked`;
a stale lock must fail instead of choosing a new environment. The interpreter,
uv version, build backend and runtime/development requirements are independently
pinned; future native numerical reproducibility still needs declared tolerances.
