# Milestone 2: market data and forecasting

This milestone produces forecasts and local provenance. It has no portfolio
optimiser, database operations, dashboard, scheduler, deployment, or evaluation
experiment. Milestone 1 request/default/credential behavior is unchanged.

## Run and reproduce

Use the pinned Python/uv and locked installation described in [README](../README.md).
The complete offline quality gate includes real Prophet execution:

```sh
make check
make package-smoke
uv run --locked python scripts/milestone2_smoke.py
```

The synthetic example generates all twelve assets with 672 actual XNYS session
labels from 2024-01-02 through 2026-09-04, a 2026-09-08 target, and a fixed aware
execution clock. Values are deterministic synthetic prices, explicitly labelled
as such. It saves `artifacts/milestone2/forecast.json` and a content-addressed input
snapshot, then refits the same inputs and checks agreement at `rtol=1e-8, atol=1e-8`.
[Recorded output](examples/milestone2/forecast.json) and its sibling `inputs/`
snapshot preserve this controlled run. Run UUIDs and elapsed durations vary.

A deliberate live-provider invocation is separate from offline CI:

```sh
uv run --locked python -m portfolio_forecasting
```

This emits JSON to stdout and diagnostics to stderr. A closed exchange day emits
`status=skipped` and downloads nothing. A live run at or after that session's open
fails with exit 1. Complete reports and explicit skips use exit 0. No credentials
or `.env` loader are needed. The optional live-provider path was not exercised
for milestone acceptance.

Explicit retrospective requests download data as available at the real retrieval
time, label the result `mode=retrospective`, and retain the requested exclusive end:

```sh
uv run --locked python -m portfolio_forecasting --retrospective --end 2026-09-08
```

Replay an existing snapshot without provider access:

```sh
uv run --locked python -m portfolio_forecasting --replay path/to/SHA256.json
```

The filename must match its bytes' SHA-256. Replay requires the captured Python,
source and scientific dependency versions, verifies the current calendar matches
its saved sessions/events, and sets `replay=true`. Captured live mode describes
the original request; replay is never evidence of a newly issued live forecast.
A verified `read_snapshot(path)` can separately recover inputs for later evaluation
without requiring identical model source. M3 evaluation itself is not implemented.

The callable entry point is `portfolio_forecasting.pipeline.compute_forecast`.
It takes an existing `RunRequest`, an explicit `snapshot_directory: Path`, and
optional source/clock injection, returning `ForecastReport | SkippedForecast`.
It writes the requested local input snapshot; it never writes to a database.
`forecast_prices(prepared_data)` is the lower-level in-memory forecasting boundary.
Use `canonical_bytes(report.to_metadata())` for strict finite JSON serialization.

## Time and observations

The execution timestamp is aware UTC. Live requests use the New York execution
date, require that date to be an exchange session, and target its upcoming close
before its opening. The observation cutoff is the previous completed XNYS session.
Both opening and closing timestamps come from the real schedule, including DST
and early closes. Completion rechecks the opening deadline. Publication will need
its own additional check in M4/M6. Retrospective requests select the last session
strictly before their exclusive end and then the next actual session as target.

Every asset must contain exactly the exchange sessions in the requested interval.
A common gap fails even if every asset has that gap. A shorter history, absent
first session, stale final session, extra/future date, duplicate or unordered row,
non-session label, missing/nonfinite/zero/negative price, wrong metadata, or failed
required ticker aborts the run. There is no intersection that silently discards
sessions, no sorting to hide disorder, no imputation, and no reduced universe.

Returned provider indices must be timezone-aware daily labels that map to New York
midnight. Equivalent UTC representations are accepted; arbitrary naive, intraday,
string, or missing labels fail. Validated observations are frozen date/float records
copied from provider frames. Changing a source frame cannot change captured inputs.

Training retains the first price. Return rows are computed only after complete
alignment, dated by `plan.sessions[1:]`, and use `current / previous - 1` in request
ticker order. No predicted value enters observations or this return panel. Live
risk-history settings require 252 returns/253 prices. The separate yearly gate
uses actual first/last observations and calendar-year subtraction with February 28
for a February 29 anniversary. Recent history includes actual observations from
`cutoff - recent_history_days` through cutoff, both endpoints inclusive; its dates
are never inferred from a sequence length.

## Provider contract and its limits

The adapter uses yfinance 1.7.0 with `interval=1d`, inclusive start/exclusive end,
`period=None`, `auto_adjust=False`, `back_adjust=False`, `repair=False`,
`keepna=True`, `rounding=False`, `prepost=False`, `actions=False`, and the configured
request timeout (default 30 seconds). It explicitly selects `Adj Close`. Other OHLC
columns are not model inputs. Metadata read from the chart response must identify
the requested symbol, USD, EQUITY, daily granularity, New York timezone, and one of
NYQ/NMS/NGM/NCM. Those NYSE/Nasdaq listing codes share the pinned library's XNYS
calendar mapping. Unsupported listings or absent metadata fail visibly.

The retained per-call `raise_errors=True` option is deprecated upstream; the adapter
filters only that exact known deprecation within its call. It does not change global
yfinance configuration. Metadata access selects only needed keys and avoids the
lazy `tradingPeriods` value, which would trigger an extra intraday request.

Transient timeouts, connection errors, rate limits, HTTP 429/5xx, and the pinned
library's explicit temporary-outage exception are retried up to the configured
maximum of three application attempts. Delay is `min(backoff * 2**(attempt-1), 30)`;
default failed attempts sleep 1 then 2 seconds. Permanent provider failures and
empty/malformed returned data are not retried. The failing ticker is retained in
the error and correlated diagnostics. There is no partial-success report.

These are application attempts, not a promise of at most three HTTP requests:
yfinance can perform its own cookie/authentication requests and retries. Request
timeouts are not a total process deadline; full operational time budgets are M6.
The pinned upstream parser can normalize, sort and deduplicate raw chart timestamps
before returning a frame. Validation covers the returned data; the snapshot is the
actual normalized model input, not a raw-wire archive or detection of defects
already hidden by upstream parsing. Strict deterministic fixtures exercise the
adapter and real parser without network access.

## Prophet and chronological correctness

Each ticker gets a new Prophet instance and a full fit using only observations
through the shared cutoff. Prediction receives exactly one date: the recorded next
session. Prices must remain finite and positive, and fractional forecast returns
are computed without rounding as `predicted / observed - 1`.

The reference constructor uses linear growth, additive components, yearly/weekly
on and daily off (unless the existing request explicitly disables a component),
25 requested changepoints in the first 80% of history, and prior scales 0.05 for
changepoints and 10 for seasonality/holidays. Scaling is explicitly `absmax`.
MAP fitting uses LBFGS, seed 42, 10,000 maximum iterations and recorded tolerances;
Newton fallback is disabled so failure is visible. No uncertainty intervals are
requested (`uncertainty_samples=0`); point forecasts are the required output.
The report records effective seasonalities, resolved changepoints, training bounds,
all supplied holiday events, constructor options and fitting settings.

Regular XNYS holidays retain stable names and one-calendar-day windows before and
after each event. Events are generated from first observation minus one through
target plus one, including future occurrences. Thus a January 1 holiday can affect
a December 31 target through its negative window. Known calendar features are not
future prices. No future target observation is supplied to fitting or preprocessing.
Future exceptional closure features are conservatively excluded because the
calendar does not provide announcement timestamps. Historical exceptional closures
are included under a stable exceptional-closure label.

Retrospective calendars and provider-adjusted histories are ex-post information;
this milestone does not establish their historical point-in-time availability.
Future chronological evaluation must disclose those limits and fixed-universe
selection bias. It must not treat these smoke runs as validation/model selection.

## Provenance and remaining boundaries

Canonical JSON snapshots capture all dated normalized prices, provider identity,
selected metadata, UTC retrieval timestamps, attempt counts, resolved request and
provider policy, complete calendar plan/holiday features, source hashes, and installed
package versions. An observation-content hash identifies changed prices/metadata;
a whole-snapshot hash also identifies changes to retrieval or environment context.
Synthetic fixtures are labelled with their own provider name; the recorded yfinance
options describe the configured adapter policy, not an executed Yahoo request.

Snapshots publish atomically without replacement and are made read-only. A later
revised download creates a new file, preserving the original. Hash verification
rejects tampering; ordinary file permissions are not protection against an owner
who deliberately changes files. Invalid or interrupted computations never emit a
successful report, but an already captured input snapshot can remain for diagnosis.
Reports include shared attempt UUIDs, dated outputs/history and stage durations.
Stable durable publication identity and revision handling remain M4 work.

The native backend and package installation were tested on Linux x86-64 with the
locked Python 3.12.14 environment. Other platforms are not validated. Prophet emits
an informational message about missing optional Plotly on import; interactive model
plots are unused and that optional dependency was not added. CPU/native changes can
change floating-point results; the declared tolerance is not a bitwise guarantee.

No live Yahoo availability, public data-use entitlement, out-of-sample accuracy,
allocation benefit, or investment performance is claimed. Provider-adjustment
revision reconciliation for actual forecast outcomes, database durability,
optimisation/evaluation, UI, scheduling and deployment remain their later milestones.

Primary API references: [yfinance history](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html),
[Prophet holiday features](https://facebook.github.io/prophet/docs/seasonality,_holiday_effects,_and_regressors.html),
and [exchange-calendars](https://github.com/gerrymanoim/exchange_calendars).
