# Milestone 2 report

Scope: market data and Prophet forecasting, exactly the M2 stage in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and
the authoritative rebuild plan (`specifications/REBUILD_PLAN.md`).
Implementation began from committed M1 revision `528472c`. The seven supplied
specifications were present but untracked at the start; none was altered.

Status: **Milestone 2 complete and verified.** Final verification passed on
13 September 2026 (Asia/Beirut).
Milestone 3 has not started. No M2 commit or external publication was created.

## Functionality implemented

- Real XNYS session planning with separate UTC execution, requested exclusive end,
  observed cutoff, target date, cutoff close and target open/close. Closed live days
  return a no-op before retrieval. Live execution at/after open fails, with another
  deadline check after fitting. Retrospective requests remain explicitly labelled.
- A yfinance adapter with explicit daily adjusted-close semantics, metadata checks,
  request timeout, bounded transient retries, and named failures. No required asset
  can silently disappear from a successful run.
- Immutable dated observations and a complete consecutive common panel. Invalid,
  missing, duplicate, unordered, gapped, stale, out-of-range, zero/nonpositive or
  nonfinite values are rejected. The first training price is retained; comparable
  observed-only simple returns are calculated after alignment. Separate risk and
  yearly-seasonality history gates remain intact.
- Dated recent actual history with inclusive calendar-day boundaries; no invented
  dates or predicted values in observed data.
- Independent real Prophet refits with explicit constructor/fitting settings,
  recorded effective seasonalities/changepoints, deterministic seed, known future
  regular holiday occurrences and ±1 calendar-day windows. Targets are actual
  sessions. Nonpositive/nonfinite predictions and nonfinite returns fail.
- Canonical local input snapshots, data/source/package provenance and SHA-256
  integrity, atomic creation without overwriting previous captures, revised-data
  preservation, verified offline loading and explicitly labelled model replay.
- A callable forecast-only coordinator and `python -m portfolio_forecasting` manual
  JSON report with complete/failure/no-op behavior, shared attempt identifiers,
  per-ticker diagnostics and stage durations. No database credentials are needed.
- Expanded locked dependencies, deterministic fixtures, actual offline yfinance
  parser tests, real Prophet tests, and a native fit from a freshly installed wheel.

## Requirements satisfied

The [coverage matrix](SPECIFICATION_COVERAGE.md) records only the delivered portions.

| Requirement | M2 evidence | Qualification |
| --- | --- | --- |
| F01 | Session/deadline/DST/holiday/year/early-close tests; real future-holiday feature test | Publication recheck and operational scheduling remain M4/M6 |
| F03 | Complete membership, price/date/history/freshness gates, aligned-return examples | Covariance and optimiser validation remain M3 |
| F07 | Locked native environment; data/source/settings/version metadata; frozen-input replay | Full release and operational provenance remain later |
| F12 | Full original suite plus offline adapter/parser/calendar/model/snapshot/CLI tests; fresh-wheel native check | Database/UI/evaluation/operational integration remain later |
| F14 | Explicit adjustment/security/currency/request policy; dated snapshots; revision preservation | Point-in-time availability, outcome adjustment reconciliation, durable storage and public-use gate remain later |
| S05 | Shared attempt UUID, ticker, retry attempts, prices/cutoff/target/hash, stage durations and failures | Solver/publication/retention/recovery diagnostics remain later |
| S06 | Only used scientific/provider dependencies; existing quality gate retained | Other dependencies arrive with their milestones |
| D01/D06/D08 | Prophet, independent full refits, exchange calendar and simple returns retained | No alternative model, inference service or infrastructure was added |

Behavior sections 1–5 and the M2 portion of section 7 now have executable evidence.
The twelve-asset valid-data, required-download failure, one-price, Friday/Monday
holiday, stale/malformed/revised-input scenarios are exercised. Later product
scenarios are not marked complete.

## Methodological and engineering decisions

No settled architecture contradiction required a redesign. M1's request/settings
and credential implementations and original tests remain byte-for-byte unchanged.
The detailed choices are recorded in [DECISIONS.md](DECISIONS.md) and
[the data/forecast assumptions](docs/MARKET_DATA_AND_FORECASTING.md).

The adjusted-close policy uses explicit `Adj Close` selection with automatic OHLC
adjustment disabled. This preserves the settled price basis. Selected cached chart
metadata validates the ticker, USD equity type, supported NYSE/Nasdaq listing,
New York timezone and daily granularity without requesting lazy intraday metadata.
Malformed/empty data fail immediately. Transient timeouts, connection errors,
rate limits, 429/5xx and the pinned provider's temporary-outage exception receive
at most three application attempts, with exponential sleeps capped at 30 seconds.

The complete requested session range is mandatory, including its first expected
session. This conservative policy refuses silent intersection/truncation and keeps
all observed returns on comparable one-session intervals. The annual gate checks
actual calendar span independently of the configured return window, including a
February 29 anniversary case.

Prophet retains the existing components and ±1 calendar-day holiday windows.
Regular holiday generation includes the target's following day to preserve a future
holiday's pre-event effect. Future exceptional closure features are excluded because
the library provides no announcement-time evidence. Retrospective calendars remain
ex-post schedules, not proof of what was known at an earlier forecast origin.

The fixed fitting policy is LBFGS MAP, seed 42, at most 10,000 iterations, recorded
stopping tolerances, and no implicit Newton fallback. Disabling unused uncertainty
simulations avoids producing optional intervals; all required point outputs remain.
No component comparison, parameter tuning, baseline study or allocation experiment
was performed. Those decisions require M3's chronological evaluation.

Snapshots contain actual normalized model inputs and context, not a raw-wire data
archive. Atomic hard-link creation and hash verification prevent application-level
overwrite and detect tampering. Revised inputs have different hashes and files.
Replay validates source/Python/scientific versions and the saved calendar before
refitting; ordinary input loading can support future research under a different
implementation without calling it an identical replay. Run UUIDs identify attempts;
durable retry/publication identity remains M4.

## Files/components added or changed

| Component | Files and purpose |
| --- | --- |
| Session and data boundary | `sessions.py`, `market_data.py`, `errors.py`: calendar/features, explicit provider calls, immutable records, preparation and failure context |
| Forecasting and provenance | `forecasting.py`, `snapshots.py`: real Prophet refits/settings, captured input files, verification and data loading |
| Manual computation | `pipeline.py`, `__main__.py`: forecast-only coordination, replay and JSON CLI |
| Toolchain | `pyproject.toml`, `uv.lock`: pinned scientific/provider dependencies and pandas typing stubs |
| Verification | New test fixtures and five M2 test modules; `scripts/package_smoke.py` extends existing installed-wheel verification |
| Controlled example | `scripts/milestone2_smoke.py` and `docs/examples/milestone2/`: twelve-asset synthetic forecasts, immutable inputs and reproducibility evidence |
| Documentation | README, architecture, plan, decisions, coverage, configuration navigation, M2 assumptions and this report |

Source paths in this table are under `src/portfolio_forecasting/`. No SQL, Supabase
client, allocation solver, evaluation pipeline, dashboard, Docker, workflow platform,
scheduler, deployment or optional model candidate was introduced. The existing
Actions quality workflow automatically runs the expanded checks; it was not replaced.

## Commands executed and exact results

The default workstation uv remains 0.9.26. Commands requiring the project pin used
this already cached uv 0.12.13 executable without changing global tool installations:

```text
/home/wassim/.cache/uv/archive-v0/7S7aC_6BQ3jtOceC_r9uG/uv-0.12.13.data/scripts/uv
```

In the command table, `UV_PIN` denotes that exact path for readability; it is not a
new runtime dependency. Ordinary documented commands work with uv 0.12.13 on PATH.

| Command/check | Exact observed result |
| --- | --- |
| Initial sandboxed repository read | Exit 1 before execution: `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` |
| Initial apply_patch attempt | Failed before file access with the same sandbox-helper error; no file changed |
| Approved repository/instruction/specification reads | Completed; M1 commit `528472c`, no applicable AGENTS.md, existing untracked specifications |
| Official PyPI metadata reads for candidate dependencies | Exit 0; verified Python compatibility metadata and selected exact versions |
| `UV_PIN sync` after dependency update | Exit 0; 54 lock entries resolved; scientific/provider dependencies installed without changing M1 pins |
| Initial `make check UV=UV_PIN` | Exit 2 from make at lint: 7 findings; all corrected |
| Initial direct mypy and pytest run | Mypy: 6 typing findings; pytest exit 2: two helper-import collection errors; corrected |
| Next direct mypy and pytest run | Mypy: 1 test-helper typing finding; pytest exit 0: 199 passed in 23.84s; typing corrected |
| Subsequent `make check UV=UV_PIN` | Exit 2 at lint for one newly added overlong replay error string; corrected |
| Expanded `make check UV=UV_PIN` | Exit 0: lock/lint/format/strict typing passed; 223 tests passed in 14.69s |
| `python scripts/milestone2_smoke.py`, first controlled run | Exit 0: 12 assets, 672 prices each, 2026-09-04 cutoff, 2026-09-08 target; original and replay agreed at relative/absolute tolerance 1e-8 |
| `make package-smoke UV=UV_PIN`, first M2 package verification | Exit 0: sdist, wheel, hash-verified fresh runtime-only install, M1 import/request assertions and real offline Prophet fit/predict passed |
| `pytest tests/test_market_data.py -q`, outage-retry regression | Exit 0: 48 passed in 2.18s |
| Source/specification SHA-256 baseline comparison | No changes to the seven authoritative documents, M1 config/publication modules, or two original test files |

Final verification evidence is recorded below.

The runtime additions are yfinance 1.7.0, exchange-calendars 4.13.2, pandas 3.0.5,
NumPy 2.5.3 and Prophet 1.4.0, with cmdstanpy 1.3.0 and other transitives in uv.lock.
Pandas-stubs 3.0.5.260730 is development-only. Python 3.12.14, uv/uv_build 0.12.13,
tzdata 2026.4, pytest 9.1.1, Ruff 0.16.7 and mypy 2.3.1 remain unchanged.

## Tests performed

- Actual exchange sessions: ordinary Friday/Monday, Labor Day and Good Friday,
  year boundary, weekends/holidays, spring/fall DST, timezone conversion, early
  close, empty range, retrospective weekend, exact-opening and post-fit deadlines.
- Future holiday occurrences and their negative windows, including a January 1
  event affecting December 31 through real Prophet feature generation; conservative
  exceptional-closure handling and explicitly disabled holiday features.
- Explicit provider options and real installed yfinance parsing through a synthetic
  transport, with no extra intraday metadata read; retained missing adjusted values.
- Empty/partial/one-price data, missing/ambiguous columns, invalid indices,
  duplicates, unordered values, missing/nonfinite/nonpositive prices, wrong security
  metadata, stale/gapped/common-gap/extra/future/truncated observations, unchanged
  provider inputs, full ticker sets and deterministic ticker ordering.
- Timeout/connection/rate-limit/HTTP status/temporary-outage retry classification,
  exhaustion, permanent failure, configured single attempt and 30-second backoff cap.
- First-price preservation, independently calculated simple returns, overflow,
  252-versus-253-price live gate, separate annual-history gate and leap boundary,
  inclusive dated recent observations, and retrieval-time availability.
- Independent fits and repeated fresh instances, exact training/target frames,
  no future prices, recorded seeds/effective settings, fit failures, output shape,
  nonnumeric/nonfinite/nonpositive forecasts and forecast-return arithmetic.
- Real offline Prophet fitting and same-input repeatability; complete twelve-asset
  controlled run plus replay, and a native model fit in a fresh installed wheel.
- Snapshot roundtrip, original/revised preservation, tamper detection, malformed
  rehashed inputs, mismatched implementation replay, no database credentials,
  failure/closed-day behavior, correlated diagnostics, and successful/error CLI exits.

The ordinary pytest suite forbids Python socket connections and the provider's
HTTP session requests. Every provider fixture and model test is offline. No optional
live provider request or external service was used as acceptance evidence.

## Limitations and intentionally deferred work

- No live Yahoo request was performed. The actual parser and adapter are tested
  offline; endpoint availability, rate-limit behavior in production and public
  data-use rights remain unverified. Display/use arrangements are a later gate.
- Validation begins at yfinance's returned frame; upstream parsing can already sort
  and deduplicate raw chart timestamps. Local snapshots preserve normalized inputs,
  not full raw HTTP responses or defects hidden before the application boundary.
- Present-day adjusted prices and retrospective calendar closures do not establish
  point-in-time historical availability. Known-future regular features are retained;
  unknown-future exceptional features are conservatively omitted. No accuracy,
  profitability, model-selection or executable trading claim follows from these tests.
- Application retry limits do not bound every upstream authentication HTTP request.
  Complete job timeouts, overlap/missed-session policy, monitoring and deployment
  evidence remain M6. Publication must recheck the target deadline in M4/M6.
- The tested native environment is Linux x86-64. Other platforms and bitwise equality
  across native environments are not claimed. Prophet's missing optional Plotly
  message is informational; that unused plotting dependency was not installed.
- Snapshot file permissions and checksums are integrity mechanisms, not a security
  boundary against a file owner. Durable private storage, backup/recovery, stable
  publication identity and corporate-action outcome reconciliation remain M4.
- Allocation, covariance estimation, baselines/chronological evaluation, Supabase,
  dashboard, scheduling and deployment remain Milestones 3–6. No later work began.
- Hosted GitHub Actions execution was not performed. Local commands exercise the
  existing workflow's quality/package gates; they are not a hosted CI result.

Work stops at Milestone 2.

## Final verification evidence

| Final command/check | Exact result |
| --- | --- |
| `make check UV=UV_PIN` | Exit 0; 54 lock entries consistent, lint passed, 39 files already formatted, strict mypy passed for 22 source files, **224 tests passed in 16.62s** |
| `make package-smoke UV=UV_PIN` | Exit 0; sdist/wheel build, fresh runtime dependency install with hashes, isolated M1 assertions, and real installed-wheel Prophet fit/predict passed |
| `.venv/bin/python scripts/milestone2_smoke.py --output docs/examples/milestone2` | Exit 0; all 12 assets, 672 prices each, 2026-09-04 cutoff, 2026-09-08 target; 12 original fits and 12 replay fits agreed with `rtol=1e-8, atol=1e-8` |
| `.venv/bin/python /tmp/portfolio_m2_final_audit.py` | Exit 0; specification/foundation hashes, controlled artifact/source/lock/fixture hashes, forecast arithmetic, local links, whitespace, scope and Git diff checks passed |

The final suite includes all **118 original M1 cases plus 106 M2 cases**. M1's two
implementation modules and two original test modules match their initial hashes.
All seven supplied specification documents also match their initial hashes.

The full final command logs remain in `/tmp/portfolio-m2-final-quality.log`,
`/tmp/portfolio-m2-final-package.log`, and `/tmp/portfolio-m2-final-smoke.log` for
this workspace session. They are verification records, not runtime dependencies.
The repository retains the synthetic forecast and its complete input snapshot:

- [Forecast report](docs/examples/milestone2/forecast.json).
- [Immutable synthetic input snapshot](docs/examples/milestone2/inputs/f9f465e54358dc8bb99b26911358229e1c23de9c2cb06eb7ec646af3b92b41b1.json).

Snapshot SHA-256: `f9f465e54358dc8bb99b26911358229e1c23de9c2cb06eb7ec646af3b92b41b1`.

Observed-data SHA-256: `598800ef028583a0d0bcd6c2a81e1afe99c2092cca9aaaccbdc80f959710a373`.

Source-manifest SHA-256: `7d7b590ad3b0ae9109da61285eaa1485c89454ec115557cbfe656e6faaf357fd`.

Lock SHA-256: `237582a4b9d38793497a69c3547d6b5d68131ffff6465da3170ec8bb350273d5`.

These are synthetic execution/reproducibility artifacts. They establish no live
provider availability or forecast accuracy. Milestone 3 remains unstarted.
