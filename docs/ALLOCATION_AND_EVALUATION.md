# Allocation and chronological evaluation

Milestone 3 implements the callable allocation path and offline research. It adds
no durable publication, database operations, dashboard, trading, or deployment.
M1 configuration and all M2 ingestion/calendar/forecast interfaces are preserved.

## Compute without publication

```python
from pathlib import Path
from portfolio_forecasting import RunRequest
from portfolio_forecasting.portfolio import compute_portfolio
from portfolio_forecasting.snapshots import canonical_bytes

# An eligible live pre-open request explicitly retrieves the configured universe.
result = compute_portfolio(RunRequest(), snapshot_directory=Path("artifacts/inputs"))
print(canonical_bytes(result.to_metadata()).decode())
```

The result is a complete `PortfolioReport`, an explicit closed-session
`SkippedForecast`, or a raised `ForecastError`. A report retains forecast dates,
prices, provenance, the same attempt ID, weights, expectations, covariance,
completion time, stage durations, SciPy version, and numerical diagnostics.
The live opening deadline is checked again after allocation. Failures propagate;
there is no successful partial portfolio, automatic equal-weight fallback, or
publication side effect. The M2 forecast-only command remains unchanged.

For a deterministic twelve-asset run with real Prophet and SciPy and no network:

```sh
uv run --locked python scripts/milestone3_smoke.py
```

This reuses the M2 synthetic fixture. It is integration evidence, not market
performance evidence. The result is `artifacts/milestone3/smoke/portfolio.json`.

## Numerical contract

For each asset, the direct expectation is `predicted_price / observed_price - 1`.
Forecasts must match all requested assets, the observation cutoff, target, and
validated observed price. Reordering forecast records is harmless; duplicate,
missing, mismatched, nonfinite, or invalid forecasts fail.

Risk uses the latest **252 actual simple-return rows**, calculated from 253
consecutive observed price rows. Sample covariance uses `ddof=1`; no synthetic
forecast enters the panel. Shorter research windows must be explicitly requested
under the retained retrospective contract. Historical-only expectations use the
mean of exactly the same trailing observed return window.

Maximize `mu @ w - (lambda / 2) * w @ covariance @ w`, with unannualized
single-session returns and variances, common fractional bounds and `sum(w)=1`.
The half-factor cancels the factor of two in the variance derivative. The analytic
minimization gradient is `-mu + lambda * covariance @ w`. Scaling both objective
and gradient by one positive constant preserves the optimum. Variance is used
in this objective; volatility is its square root and is a separate report metric.

The supplied audit's old synthetic-row mean diluted the forecast to a coefficient
of `1/252` (about 0.397%) and also contaminated covariance. The corrected direct
expectation gives it coefficient 1. The separately declared research blend is
`(1-alpha) * observed_mean + alpha * forecast_return`; alpha 0.25 is evaluated,
never inferred from a row count. See the authoritative analysis (`specifications/ML_SPEC.md`).

| Check/setting | Implemented policy |
| --- | --- |
| Input arrays | Real, finite, correct dimensions; booleans/complex values rejected |
| Covariance symmetry/PSD tolerance | `1e-10 * max(matrix/eigenvalue magnitude, 1e-12)` |
| Accepted asymmetry | Only roundoff within tolerance is symmetrized; no eigenvalue clipping |
| Singular positive-semidefinite matrix | Allowed; rank and undefined condition number recorded; optimum can be nonunique |
| Indefinite matrix | Rejected outside the declared PSD tolerance |
| SLSQP | Analytic gradient; `ftol=1e-12`, `maxiter=1000`; no solver retry/fallback |
| Objective scale | `max(max(abs(mu)), lambda * max(max(abs(covariance)), 1e-12), 1e-12)` |
| Budget/bound tolerance | `1e-9` absolute fractional residual |
| Independent optimality check | Concavity gap from an exact box/simplex linear oracle must be at most `1e-6 * scale`; utility must not degrade from equal weights beyond that tolerance |
| Degenerate feasible set | A mathematically unique allocation is returned directly and independently validated |
| Output handling | No clipping, rounding, or normalization of returned solver weights |

The scale is required to be finite. Negative eigenvalues beyond roundoff,
nonfinite data/diagnostics, failed solver status, violated constraints, or a poor
objective all fail explicitly. Condition numbers and expectation sensitivity
are diagnostics, not arbitrary rejection thresholds for otherwise valid PSD risk.

The default twelve-asset 5% floor commits 60% of wealth and implies a 45% maximum
single weight, despite the configured 100% upper bound. Twenty assets force 5%
each; twenty-one are infeasible. A positive floor does not establish sector
or factor diversification. `concentration_hhi = sum(weight**2)` measures weight
concentration only. Equal weights are a feasible starting point and a named
research baseline, never a disguised solver-failure recovery.

## Frozen study and leakage controls

The predeclared [experiment](../experiments/milestone3.json) fixes:

- Training: 2024-01-01 through the 2026-02-27 observation cutoff.
- Validation: 2026-03-02 through 2026-06-30.
- Final test: 2026-07-01 through 2026-09-03.
- One origin every five exchange sessions; the final phase close ends the last
  holding interval and is not a new signal. All held sessions remain in accounting.
- Five Prophet variants: unchanged reference, no holidays, weekly only, weekly
  only with 253 price rows, and a 0.01 changepoint prior. Default prior is 0.05.
- Seven allocation configurations: direct, alpha 0.25, diagonal shrinkage 0.25,
  risk aversion 1 or 10, zero floor, and 20% cap. Other settings retain lambda 5,
  5% floor, 100% cap, observed sample covariance, and direct expectations.

The captured M2 snapshot has 12 assets and 672 valid sessions, 2024-01-02 through
2026-09-04. It preserves actual retrieved Yahoo adjusted-close observations,
metadata and retrieval times. It is retrospective and revised; point-in-time
availability is not established. No retrieval occurs during evaluation.

At each origin, a new validated panel contains observations strictly before the
exact next-session target. Model windows/components are applied to this past-only
panel. The risk panel retains 252 observed returns regardless of model choice.
Known future calendar features remain when the holiday component is enabled;
turning that component off is an explicit candidate. Every forecast and weight
exists before the evaluator reads its target outcome. Later final-test observations
can enter later expanding fits only after they become past observations.

Selection uses validation only: a different Prophet needs strictly over 5%
lower macro relative price MAE; a different allocation needs over 0.001 higher
cumulative net research return. Ties keep declaration order. The validation and
selection JSON files are content-addressed and saved **before** final-test fitting
or scoring. Final evaluation uses the selected and unchanged reference variants
plus comparable baselines. A future-price mutation test verifies that final data
cannot change validation metrics or selection. No final-test reselection occurs.

A failed candidate excludes its entire origin across all candidates and baselines;
the reason and attempted/accepted counts are retained. Holdings carry through
later failed rebalance dates, and the first accepted target starts the shared
comparison. The measured study had zero exclusions. Three accepted validation
origins are the mechanical minimum; this is not a statistical power claim.

## Metrics and paper accounting

Price MAE/RMSE, return MAE and directional accuracy are reported per asset.
Return errors use the observed cutoff price as denominator. Cross-asset summaries
average per-asset model price-MAE / last-price-MAE ratios, not dollar errors.
If both forecasts are perfect, the ratio is 1; a nonzero error against a perfect
baseline has an undefined ratio. Direction is negative, zero, or positive with
absolute tolerance `1e-12`; a zero prediction is correct only for a zero actual
return. Zero counts and all matched sample counts are retained.

This research assumes execution at a signal's **target close** and earns only
subsequent close-to-close returns. The unavailable previous-close-to-target-close
return is never counted as investment performance. At each execution, L1 turnover
is measured against the holdings drifted by prior realized returns. Costs are
10 bps plus 5 bps slippage per dollar traded, applied to pre-cost wealth and
deducted proportionally before the next holding return. The first rebalance from
preexisting equal weights is charged; terminal liquidation is excluded. One-way
turnover is half L1. Daily holdings drift even between five-session rebalance dates.

Reports include gross/net cumulative return, sample annualized net volatility
(`sqrt(252)`), maximum net drawdown from a peak initially equal to 1, turnover,
HHI, and Sharpe with an explicitly zero risk-free rate. Annualization over a short
sample is descriptive and unstable. Adjusted closes, costs, fractional holdings
and this execution lag define hypothetical research accounting; they do not prove
that the prices or allocations were executable.

For stability, sample covariance is compared with the declared estimator
`0.75 * sample + 0.25 * diagonal(sample)`. Historical-only baselines use the same
estimator/constraints as their paired policy. One asset at a time receives a
+1 bp expectation shock, with no changed outcomes/covariance; the maximum L1
weight change is recorded for reference/direct and reference/diagonal policies.

## Reproduce the evidence

With the locally retained input snapshot:

```sh
uv run --locked python scripts/milestone3_research.py \
  --snapshot artifacts/milestone3/inputs/de59a36d380db0db6d78b1c4d0771d7bea18dc5bc6a3934d869b994375c6d1d0.json \
  --output artifacts/milestone3/research-replay \
  --report artifacts/milestone3/research-replay/report
```

Full inputs, origin forecasts, weights, paths and diagnostics remain in ignored
local `artifacts/`. The small derived [tables, figures and selection report](examples/milestone3/MODEL_SELECTION.md)
are retained under `docs/examples/milestone3/`. A fresh provider download can be
revised and is not a replacement for the frozen input. Exact replay therefore
requires preserving that local snapshot. Runtime durations/retrieval context
are provenance and need not be byte-identical; numerical replay uses `1e-8`
relative/absolute tolerances. Full declaration/result hashes bind settings,
source files, installed versions, frozen inputs, validation and selection.

The standalone CSV/PNG/JSON exporter is `research_report.export_report`. Matplotlib
uses its headless Agg backend; no interactive charting service is required.
Prophet may emit its existing optional-Plotly notice; Plotly is not needed and has
not been installed.

The [selection report](examples/milestone3/MODEL_SELECTION.md) contains the measured
negative baseline comparison. The selected cap is a research finding; unchanged
Prophet/default direct allocation remain supported. This short, fixed-universe
study does not justify promoting a new production policy, adding a new model,
or claiming alpha. No optional model/solver or experiment platform was introduced.

Primary technical references: [SciPy SLSQP](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html),
[NumPy sample covariance](https://numpy.org/doc/stable/reference/generated/numpy.cov.html),
and [Prophet cutoff diagnostics](https://facebook.github.io/prophet/docs/diagnostics.html).
The installed pinned versions and deterministic arithmetic tests establish actual
implementation behavior.
