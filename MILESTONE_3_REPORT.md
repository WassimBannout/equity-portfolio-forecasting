# Milestone 3 report

Completed 14 September 2026 (Asia/Beirut). **Milestone 3 only** is implemented and
verified. Milestones 0–2 remain stable; Milestone 4 has not started. No commit or
external publication was requested or performed.

The starting HEAD was `54f9f19`, following `528472c` and `c53f5ae`. Before coding,
reviewed `ARCHITECTURE.md`, `DECISIONS.md`, `IMPLEMENTATION_PLAN.md`,
`SPECIFICATION_COVERAGE.md`, `MILESTONE_2_REPORT.md`, and the seven authoritative
local documents under `specifications/`, focusing on Behavior 6–7, ML evaluation,
F02/F03/F06 and S01–S04. The preexisting untracked `specifications/` directory
was preserved; none of its content was edited. No completed architecture needed
redesign, and no M0–M2 source/test behavior was changed.

## Functionality and requirement coverage

- **F02 / Behavior 6:** direct fractional forecast expectations; historical mean
  and `ddof=1` sample covariance from exactly 252 actual trailing returns by default;
  synthetic forecasts never enter risk. Full ticker/date/price-basis validation.
- **F03 / Behavior 6:** input shape/finiteness/symmetry/PSD and fractional feasibility;
  analytic-gradient SLSQP; independent budget, bounds, objective and concavity-gap
  checks; explicit diagnostics and failure. Singular PSD matrices are supported.
  There is no solver retry, clipping, normalization or disguised fallback.
- **F06 / required ML evidence:** frozen-input rolling origins; predeclared
  training/validation/final-test periods; exact next-session target pairs;
  past-only fitting/risk; locked validation selection before final-test fitting;
  last-price, equal-weight and historical-only baselines on common observations.
- **S01–S04:** bounded Prophet components/window/prior, expectation blend,
  diagonal shrinkage, lambda/floor/cap experiments; condition and +1 bp expectation
  sensitivity diagnostics; price/return/direction metrics; drifted holdings,
  turnover/cost arithmetic and properly lagged hypothetical paper accounting.
- **F01/S05 / Behavior 7 M3 portion:** complete callable forecast/allocation
  composition, shared attempt logging, stage/solver durations, completion time,
  post-allocation live opening deadline and explicit failure propagation.
- **F07/F12/S06:** exact dependency additions, frozen input/source/settings hashes,
  deterministic offline tests, full previous regression, real native scientific
  execution, installed-wheel checks and reproducible CSV/PNG/JSON artifacts.
  D01/D02/D06/D08 are preserved: Prophet, mean-variance allocation, full refits,
  SLSQP, observed simple returns, exchange calendars and established tooling.

[Coverage](SPECIFICATION_COVERAGE.md) distinguishes completed M3 portions from
later persistence, outcome-association, dashboard and operational requirements.
[Detailed contracts](docs/ALLOCATION_AND_EVALUATION.md) give callable usage,
mathematics, tolerances, failure behavior and reproduction commands.

## Decisions and measured research

The original direct/sample-covariance/lambda-5/5%-floor product defaults remain.
[ADR-013](DECISIONS.md#adr-013--milestone-3-numerical-and-research-evidence) records
numerical choices and the evidence for retaining the simple implementation.
The half-factor objective uses variance, not volatility, in single-session units.
The old synthetic-row coefficient was `1/252`; the new direct expectation is
explicitly coefficient 1, with a separately evaluated alpha-0.25 blend.

SLSQP uses analytic derivatives and common positive objective scaling, `ftol=1e-12`
and `maxiter=1000`. Fractional constraint tolerance is `1e-9`; symmetry/PSD
roundoff tolerance is `1e-10` relative to the relevant magnitude floored at `1e-12`.
The independent concavity gap must be at most `1e-6 * objective_scale`, and utility
must not worsen from the equal-weight initial point beyond that tolerance. Valid
singular PSD matrices can have nonunique optima; condition number alone is not a
failure criterion. A unique feasible allocation needs no iterative solver.

SciPy **1.18.1** is the only newly resolved package. Matplotlib **3.11.2**, already
a Prophet dependency, is now declared directly because M3 generates standalone
figures. Python 3.12.14, uv 0.12.13 and every earlier package version are unchanged.
No alternative model/solver, Docker, tracker or additional service was added.

The experiment was declared before evaluating either period:

| Item | Fixed setting / observation |
| --- | --- |
| Dataset | Actual Yahoo adjusted-close observations through the unchanged M2 adapter; twelve default assets |
| Capture | 2026-09-13 20:11:16.474376 through 20:11:19.804481 UTC |
| Frozen dates | 672 consecutive XNYS sessions, 2024-01-02–2026-09-04 |
| Initial training | Request start 2024-01-01; cutoff 2026-02-27 |
| Validation | 2026-03-02–2026-06-30; 17/17 accepted origins; 204 pairs/model; 83 holding intervals |
| Final test | 2026-07-01–2026-09-03; 9/9 accepted origins; 108 pairs/model; 45 holding intervals |
| Spacing | Every five exchange sessions; every intervening holding return retained |
| Prophet candidates | Reference, no holidays, weekly only, weekly rolling 253 prices, rigid trend prior 0.01 |
| Allocation candidates | Direct, alpha 0.25, diagonal shrinkage 0.25, lambda 1, lambda 10, floor 0, cap 0.20 |
| Selection | Strictly over 5% lower validation macro relative price MAE; strictly over 0.001 higher validation net cumulative research return; declaration-order ties |
| Execution and costs | Target close; earn subsequent closes; drifted pre-trade holdings; 10+5 bps per L1 dollar traded; initial equal weights; first rebalance charged; no terminal liquidation |

Validation kept **reference Prophet** and selected **cap_020** for the research
allocation comparison. All Prophet alternatives had worse validation error.
Final-test outcomes were not used for reselection or changing the split/candidates.

| Result | Validation | Final test |
| --- | ---: | ---: |
| Reference price MAE / last-price MAE, macro | 3.997361 | 2.599968 |
| Reference/direct net research return | 4.3687% | -0.0881% |
| Reference/cap_020 net research return | 11.8076% | 5.7162% |
| Equal-weight/direct net research return | 12.7667% | 7.7733% |
| Historical-only/direct net research return | 35.3536% | -2.2475% |

The selected cap reduced concentration, but still trailed equal weights in the
final period. Alpha 0.25 achieved validation net 8.9629%; the cap beat it.
Diagonal shrinkage changed mean validation condition number from 26.3004 to
18.0490 and worst one-basis-point-shock L1 weight movement from 0.04544 to 0.04501;
its validation net return was 4.5401%. This does not establish a need for another
estimator or solver. These weak results are retained, not tuned away.

Across 750 recorded model/historical allocation solutions, maximum budget
residual was `7.682743330406083e-14`, maximum bound violation `0.0`, and the largest
independent gap/tolerance ratio `0.474504108404313` (all below 1). The validation
and final-origin workloads took respectively `199.98604844900365` and
`37.76726048100318` seconds on this host; these include forecasts, risk,
allocation and sensitivity, and are observations rather than runtime guarantees.
There were zero excluded origins and zero solver failures in the measured study.

[Selection evidence and figures](docs/examples/milestone3/MODEL_SELECTION.md)
link all per-asset errors, allocation metrics, solver summaries and structured
provenance. Forecast errors are not evidence of investable alpha. Results are
retrospective adjusted-close research with explicit costs and extra execution lag,
not executable trading performance. Product defaults are not silently promoted
from this short study.

## Frozen provenance

| Artifact | SHA-256 |
| --- | --- |
| Input snapshot | `de59a36d380db0db6d78b1c4d0771d7bea18dc5bc6a3934d869b994375c6d1d0` |
| Normalized dated data | `1fd090d904c21beeeecd469d52016ad8c32600d0746a6978d3a3a04b6b49a8bf` |
| Experiment declaration | `a0ac56bf91f9d2b5c0d7fb61e01785400de11e5cad0ac1ca3a7abbc7082f52bc` |
| Validation result | `bd890666406d200a1e9119ab8fe307ed305e05e78c5daa73d72f80a08b76f563` |
| Selection saved before test | `2c65b0fd7de0a09e9063eded04f50b5ec3466adfa3530b2b87c053a419becc23` |
| Complete research result | `25a4b77488561402cae47259b8368d30b9ce3078b47b72c15924e28a80d0391a` |
| Evaluator/package source | `0cb201cdfa9b28097aa6fce7a8eb8269c616880c5facf781f1c3aa04bdfcd0d3` |

Full snapshots/results and verification logs/scripts are retained locally in
ignored `artifacts/milestone3/`; portable derived artifacts are in
`docs/examples/milestone3/`. Exact numerical replay requires that retained input,
not a new Yahoo download. Native fits and allocation replay use relative and
absolute tolerance `1e-8`; timings and later capture context need not be identical.
A replay verified all twelve first-origin reference forecasts and both direct/cap
allocations, exact covariance, matching source/config/data hashes, and byte-identical
regeneration of all seven CSV/PNG/JSON/Markdown report artifacts. The final-test
figure was visually inspected for dates, labels and policy series.

## Files and components

| Files | Purpose |
| --- | --- |
| `src/portfolio_forecasting/allocation.py` | Observed risk, direct/blended expectations, SLSQP, independent checks, diagnostics and sensitivity |
| `src/portfolio_forecasting/portfolio.py` | Complete callable composition and final deadline/failure handling |
| `src/portfolio_forecasting/research_models.py` | Bounded Prophet components/window/prior over stable M2 interfaces |
| `src/portfolio_forecasting/evaluation.py` | Frozen chronological origins, comparable baselines, validation lock, final reporting |
| `src/portfolio_forecasting/metrics.py`, `paper.py` | Exact forecast diagnostics and costed lagged holdings |
| `src/portfolio_forecasting/research_report.py` | Standalone reproducible tables, figures and selection report |
| `experiments/milestone3.json` | Predeclared candidates, splits, timing, costs and selection rules |
| `scripts/milestone3_research.py`, `milestone3_smoke.py` | Offline research and deterministic twelve-asset integration commands |
| `scripts/package_smoke.py` | Preserved M1/M2 installed checks plus SciPy optimum/report import |
| `tests/test_allocation.py`, `test_evaluation.py`, `test_portfolio.py`, `test_research_metrics.py` | 57 new deterministic M3 test cases |
| `pyproject.toml`, `uv.lock` | SciPy pin and explicit existing Matplotlib dependency |
| `docs/ALLOCATION_AND_EVALUATION.md`, `docs/examples/milestone3/` | Contracts, assumptions and measured evidence |
| `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `IMPLEMENTATION_PLAN.md`, `SPECIFICATION_COVERAGE.md`, this report | Accurate completion boundary, decisions and coverage |

## Commands and exact results

Commands ran from the repository root. The environment's default uv was 0.9.26;
all lock/install/make commands used the already available pinned executable:
`/home/wassim/.cache/uv/archive-v0/7S7aC_6BQ3jtOceC_r9uG/uv-0.12.13.data/scripts/uv`.
In the table, `PINNED_UV` abbreviates exactly that path. Python/Ruff/mypy/pytest
commands use the resulting project `.venv`. Raw verification logs and the one-off
replay script are archived under `artifacts/milestone3/verification/`.

| Command / operation executed | Exact result |
| --- | --- |
| `pwd`; `git status --short`; `git log`; `rg --files`; `cat`/`sed`/`rg` on the named project/specification files | Reviewed starting state and M3 authority; HEAD `54f9f19`; preexisting `?? specifications/` retained |
| Initial sandboxed shell/apply-patch attempts | Environment failure before execution: `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`; subsequent required commands used approved escalation |
| Primary documentation/package metadata inspection | SciPy SLSQP and NumPy covariance documentation, Prophet cutoff guidance and installed/PyPI version constraints consulted; compatible Python/NumPy/SciPy pins retained |
| `PINNED_UV sync` after adding SciPy | 55 packages resolved; SciPy 1.18.1 installed; no previous dependency upgraded |
| `PINNED_UV sync` after declaring existing Matplotlib | `Resolved 55 packages in 588ms`; editable project rebuilt; no additional resolved package |
| Incremental `.venv/bin/ruff check --fix ...`, `.venv/bin/ruff format ...`, `.venv/bin/mypy` on new implementation/tests/scripts | Initial import, line-length and typing diagnostics corrected during implementation; final lint/type results below clean |
| `.venv/bin/pytest tests/test_allocation.py tests/test_evaluation.py tests/test_research_metrics.py -q` (initial implementation) | `45 passed in 75.18s` |
| Same targeted command after numerical/boundary regressions | `52 passed in 80.42s (0:01:20)` |
| `.venv/bin/pytest tests/test_portfolio.py tests/test_evaluation.py -q` | `17 passed in 77.83s (0:01:17)` |
| `.venv/bin/python scripts/milestone3_research.py --snapshot artifacts/milestone3/inputs/de59a36d380db0db6d78b1c4d0771d7bea18dc5bc6a3934d869b994375c6d1d0.json` | Exit 0; 17 validation + 9 final origins; selection frozen before final fitting; full result `25a4b774…0391a`; 7 report artifacts exported |
| `make check UV=PINNED_UV` | Exit 0; `Resolved 55 packages in 0.82ms`; `All checks passed!`; `53 files already formatted`; `Success: no issues found in 35 source files`; **`281 passed in 89.78s (0:01:29)`** |
| `make package-smoke UV=PINNED_UV` | Exit 0; sdist then wheel built; fresh hash-locked runtime-only install; all three PASS messages below |
| `.venv/bin/python scripts/milestone3_smoke.py` | Exit 0; `{"status": "PASS", "assets": 12, "report": "artifacts/milestone3/smoke/portfolio.json"}` |
| `.venv/bin/python scripts/milestone2_smoke.py --output artifacts/milestone3/m2-regression` | Exit 0; `status=PASS`, 12 assets, 672 prices each, cutoff 2026-09-04 / target 2026-09-08; native replay `rel=1e-8, abs=1e-8` |
| `.venv/bin/python /tmp/portfolio-m3-replay-check.py` | PASS: hashes/source/config, 12 real forecasts, direct/cap weights within `1e-8`, exact covariance, all 7 report files byte-identical |
| Python SHA-256 comparison with `/tmp/portfolio-m3-baseline.json`; lock comparison with `git show HEAD:uv.lock` | PASS: all 10 previous source files, all 10 previous test/fixture files, all 7 specifications and M2 smoke unchanged; only package smoke extended. All previous dependency versions unchanged; only new resolved package SciPy 1.18.1 |
| Python local Markdown link audit | PASS: 97 local links resolve across 13 authored documents; supplied specifications excluded from authored-link auditing and preserved unchanged |
| `git diff --check`; Python whitespace/newline scan of changed and untracked text files | PASS: Git exit 0; 29 changed/new text files clean |
| Final source-hash/HEAD audit | PASS: all 17 application source files match the frozen declaration; earlier source/tests/specifications unchanged; HEAD remains `54f9f19` |

Installed-wheel messages:

```text
PASS: sdist/wheel, locked runtime-only install, isolated request resolution
PASS: installed wheel real offline Prophet backend fit/predict
PASS: installed wheel SciPy known optimum and research reporting import
```

The successful real capture used the unchanged adapter and preparation boundary:

```python
request = RunRequest(mode="retrospective", history_end=date(2026, 9, 5))
resolved = request.resolve()
plan = plan_sessions(resolved)
provider = YFinanceSource()
assets = [provider.fetch(ticker, resolved, run_id="m3-frozen-capture")
          for ticker in request.tickers]
data = prepare_data(resolved, plan, tuple(assets))
path = write_snapshot(data, Path("artifacts/milestone3/inputs"))
```

It returned all twelve validated assets and 672 sessions; the snapshot hash is
listed above. This was an explicit research-data capture, separate from network-
prohibited deterministic tests. No live reliability or public-data-use claim follows.

The optional-Plotly import notice originates in unchanged Prophet behavior;
static reports and native fits passed without adding Plotly. Initial image-viewer
access encountered the same sandbox initialization failure; an approved read
allowed inspection of the generated figure.

## Tests performed and preservation

The final 281 tests include **all 224 previous cases and 57 new M3 cases**.
New checks cover hand-computed observed covariance, known two-asset optimum,
single/fixed/infeasible portfolios including 12/20/21 assets, scale/permutation
invariance, valid singular and invalid indefinite/asymmetric/nonfinite matrices,
solver status/exception/output/residual/objective failures, mixed booleans and
nonfinite scale, full forecast membership/dates/basis and covariance independence.

Research tests cover ordered disjoint periods, the declared first training cutoff,
rolling past-only inputs, a real Prophet prior fit, final-price mutation isolation,
a selection file existing before final prediction, common failure exclusions,
selection thresholds/ties, invalid costs, per-asset error/return/directional/zero
arithmetic, baseline ratio degeneracy, duplicate pairs, consecutive sessions,
execution lag, drifted turnover, first/subsequent costs and no terminal charge.
Integration tests verify complete allocation metadata, closed-session no-op,
correlated failure propagation, a late allocation deadline, and hand-computed
one-basis-point weight sensitivity. Report exports are exercised against fixtures.

All M1 validation/settings and M2 provider/parser/calendar/holiday/freshness/
nonfinite/gap/snapshot/replay/native-model tests still pass. Their files and the
seven authoritative specifications are byte-for-byte unchanged. All checks ran
offline except the separately labelled capture and package/setup access. No application source
or test changed after the final full-suite pass; remaining edits were documentation.

## Limitations and intentionally deferred work

- A fixed current twelve-equity universe and short held-out period limit inference.
  Prophet materially underperformed last price. Neither the cap nor the blend
  establishes alpha or justifies changing stable product defaults.
- Historical adjusted prices and calendar information are revised/ex-post;
  point-in-time vintages and raw executable prices were not supplied. Target-close
  lag and costs are explicit research conventions, not proof of realizable trades.
- Three validation origins are only a mechanical minimum; the actual study uses
  17. Five-session origin spacing reduces fit cost; it is not a daily-origin
  accuracy study. Annualized short-sample statistics and zero-rate Sharpe are
  descriptive. There is no confidence-interval or multi-universe robustness claim.
- Local frozen snapshots and full results must be retained for exact reproduction.
  A fresh clone without those ignored inputs cannot reproduce the real study from
  derived summaries alone. Durable private persistence, corporate-action outcome
  reconciliation and publication identity remain M4 work.
- No Supabase persistence, migrations, dashboard, scheduling, deployment,
  additional model candidates, dedicated QP solver, Docker, tracking platform or
  other infrastructure was started. M4–M6 require separate authorization.

Milestone 3 is the stopping boundary.
