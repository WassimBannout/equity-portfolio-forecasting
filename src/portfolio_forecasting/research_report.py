"""Portable CSV tables, scientific figures, and explicit research-only conclusions."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from portfolio_forecasting.snapshots import canonical_bytes


def _table(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export_report(result_path: Path, output: Path) -> Path:
    result = json.loads(result_path.read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    forecasts = []
    allocations = []
    solvers = []
    summary: dict[str, Any] = {
        "result_sha256": result_path.stem,
        "declaration_sha256": result["declaration_sha256"],
        "selection_sha256": result["selection_sha256"],
        "declaration": result["declaration"],
        "selection": result["selection"],
        "limitations": result["limitations"],
    }
    for phase in ("validation", "final_test"):
        block = result[phase]
        summary[phase] = {
            key: block[key]
            for key in (
                "start",
                "end",
                "attempted_origins",
                "accepted_origins",
                "excluded_origins",
                "forecast_metrics",
                "timings",
            )
        }
        summary[phase]["paper"] = {
            name: {key: value for key, value in path.items() if key != "path"}
            for name, path in block["paper"].items()
        }
        for model, metric in block["forecast_metrics"].items():
            for ticker, row in metric["per_asset"].items():
                forecasts.append(
                    {"phase": phase, "model": model, "ticker": ticker, **row}
                )
        for policy, row in summary[phase]["paper"].items():
            allocations.append({"phase": phase, "policy": policy, **row})
        for policy, values in block["solver_diagnostics"].items():
            sensitivity = [
                row["sensitivity"]["maximum_weight_l1_change"]
                for row in values
                if "sensitivity" in row
            ]
            conditions = [
                row["covariance_condition"]
                for row in values
                if row["covariance_condition"] is not None
            ]
            solvers.append(
                {
                    "phase": phase,
                    "policy": policy,
                    "solutions": len(values),
                    "max_budget_residual": max(
                        row["budget_residual"] for row in values
                    ),
                    "max_bound_residual": max(row["bound_residual"] for row in values),
                    "max_gap_tolerance_ratio": max(
                        row["concavity_gap"] / row["gap_tolerance"] for row in values
                    ),
                    "mean_condition": mean(conditions) if conditions else None,
                    "mean_hhi": mean(row["concentration_hhi"] for row in values),
                    "worst_1bp_weight_l1": max(sensitivity) if sensitivity else None,
                    "solver_seconds": sum(row["seconds"] for row in values),
                }
            )
    summary["solver_summary"] = solvers
    _table(output / "forecast_metrics.csv", forecasts)
    _table(output / "allocation_metrics.csv", allocations)
    _table(output / "solver_diagnostics.csv", solvers)
    (output / "summary.json").write_bytes(canonical_bytes(summary) + b"\n")
    selected = f"{result['selection']['model']}/{result['selection']['allocation']}"
    metrics = result["validation"]["forecast_metrics"]
    fig, axis = plt.subplots(figsize=(9, 4), layout="constrained")
    names = list(metrics)
    axis.bar(names, [metrics[name]["macro_relative_price_mae"] for name in names])
    axis.axhline(1, color="black", linestyle="--", linewidth=1)
    axis.set_ylabel("Macro price MAE / last-price MAE (lower is better)")
    axis.set_title("Validation only: Prophet components, window and trend prior")
    axis.tick_params(axis="x", labelrotation=20)
    fig.savefig(output / "validation_errors.png", dpi=160)
    plt.close(fig)
    fig, axis = plt.subplots(figsize=(9, 4), layout="constrained")
    policies = list(
        dict.fromkeys(
            (
                "reference/direct",
                selected,
                "equal_weight/direct",
                "historical_only/direct",
            )
        )
    )
    for policy in policies:
        path = result["final_test"]["paper"][policy]["path"]
        axis.plot(
            [row["holding_end"] for row in path],
            [row["net_wealth"] for row in path],
            label=policy,
        )
    axis.set_xticks([0, len(path) // 2, len(path) - 1])
    axis.set_ylabel("Net research wealth; initial wealth = 1")
    axis.set_title("Final test: target-close execution, subsequent close returns")
    axis.legend(fontsize=8)
    fig.savefig(output / "final_test_research.png", dpi=160)
    plt.close(fig)
    lines = [
        "# Milestone 3 model-selection evidence",
        "",
        "Retrospective adjusted-close research on a fixed twelve-asset universe. "
        "These are not executable trading returns or evidence of investment alpha.",
        "",
        f"Frozen input: `{result['declaration']['snapshot_sha256']}`.",
        f"Full local result: `{result_path.stem}`.",
        f"Selection locked before final testing: `{result['selection_sha256']}`.",
        "",
        f"Validation selected **{selected}**. The unchanged **reference/direct** "
        "remains a reported comparator and the callable product default.",
        "",
        "| Phase | Model | Origins | Price MAE / last-price MAE |",
        "| --- | --- | ---: | ---: |",
    ]
    for phase in ("validation", "final_test"):
        for model, metric in result[phase]["forecast_metrics"].items():
            ratio = metric["macro_relative_price_mae"]
            lines.append(f"| {phase} | {model} | {metric['origins']} | {ratio:.6f} |")
    lines += [
        "",
        "A ratio above 1 means worse price MAE than last price. "
        "Dollar errors are reported per asset in the CSV, never pooled.",
        "",
        "| Phase | Policy | Gross return | Net return | L1 turnover | Mean HHI |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for phase in ("validation", "final_test"):
        for policy in policies:
            row = result[phase]["paper"][policy]
            lines.append(
                f"| {phase} | {policy} | {row['gross_cumulative_return']:.4%} | "
                f"{row['net_cumulative_return']:.4%} | {row['turnover_l1']:.4f} | "
                f"{row['mean_concentration_hhi']:.4f} |"
            )
    lines += [
        "",
        "Costs: 10 bps transaction cost + 5 bps slippage per dollar traded. "
        "Initial holdings are equal weight, the first rebalance is charged, "
        "and terminal liquidation is excluded. Sharpe uses an explicit zero "
        "risk-free rate; volatility uses 252 sessions and sample variance.",
        "",
        "![Validation forecast comparison](validation_errors.png)",
        "",
        "![Final-test research accounting](final_test_research.png)",
        "",
        "[Per-asset errors](forecast_metrics.csv), "
        "[all allocation comparisons](allocation_metrics.csv), "
        "[numerical diagnostics and 1 bp sensitivity](solver_diagnostics.csv), "
        "[settings, counts, provenance and structured summary](summary.json).",
        "",
        "The experiment fixes candidate order, selection thresholds, split "
        "dates and costs before evaluation. Five-session origin spacing "
        "limits fitting cost; holdings drift across every intervening session. "
        "Earlier test observations may enter later test-origin fits, but "
        "test scores cannot change the locked selection. Any failed origin "
        "is excluded for all candidates and baselines; existing holdings carry.",
        "",
        "Provider history and the calendar are ex-post snapshots. Point-in-time "
        "price availability and executable adjusted closes are unproven. "
        "The short final test and fixed current universe limit generalization. "
        "No final-test-driven tuning or production-default promotion is made.",
        "",
    ]
    destination = output / "MODEL_SELECTION.md"
    destination.write_text("\n".join(lines))
    return destination
