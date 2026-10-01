#!/usr/bin/env python3
"""Plot normalized objective metrics from aggregated_metrics.csv.

This script compares `HeuristicBidding` and `EmbeddingBidding` to
`PureLocal` by objective, where normalized values are:

	normalized = method_metric / purelocal_metric

Layout: 3 rows (day: busy, bursty_low_stress, bursty_high_stress) 
        × 4 columns (workload_type: homogeneous_short, mixed_20_80, mixed_80_20, only_large_long)
        One figure per num_jobs scenario (r32, r16, r8 mapping).

Lower is better for the selected objectives.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


OBJECTIVE_COLUMNS = [
	"makespan_seconds",
	"waiting_mean",
	"execution_mean",
	"turnaround_mean",
]

OBJECTIVE_LABELS = {
	"makespan_seconds": "makespan",
	"waiting_mean": "waiting mean",
	"execution_mean": "execution mean",
	"turnaround_mean": "turnaround mean",
}

DEFAULT_METHODS = ["HeuristicBidding", "EmbeddingBidding"]


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Create normalized objective bar plots (3 rows × 4 columns grid) from aggregated_metrics.csv "
			"using PureLocal as baseline (1.0). Rows = day, Columns = workload_type. "
			"One figure per num_jobs scenario."
		)
	)
	parser.add_argument(
		"--input",
		"-i",
		required=True,
		help="Path to aggregated_metrics.csv",
	)
	parser.add_argument(
		"--output-dir",
		"-o",
		default="plots",
		help="Output directory (default: plots).",
	)
	parser.add_argument(
		"--num-jobs",
		default="1000,2000,4000",
		help="Comma-separated num_jobs values to include (default: 1000,2000,4000).",
	)
	parser.add_argument(
		"--methods",
		default=",".join(DEFAULT_METHODS),
		help=(
			"Comma-separated strategies to compare against PureLocal "
			"(default: HeuristicBidding,EmbeddingBidding)."
		),
	)
	return parser.parse_args()


def _parse_csv_list(raw: str) -> list[str]:
	return [x.strip() for x in raw.split(",") if x.strip()]


def _parse_int_list(raw: str) -> list[int]:
	vals: list[int] = []
	for token in raw.split(","):
		token = token.strip()
		if not token:
			continue
		vals.append(int(token))
	return vals


def validate_columns(df: pd.DataFrame) -> None:
	required = {
		"day",
		"workload_type",
		"num_jobs",
		"strategy",
		*OBJECTIVE_COLUMNS,
	}
	missing = [c for c in required if c not in df.columns]
	if missing:
		raise ValueError(f"Missing required columns in aggregated CSV: {missing}")


def filter_by_num_jobs(
	df: pd.DataFrame,
	num_jobs: int,
	methods: list[str],
) -> pd.DataFrame:
	allowed_strategies = ["PureLocal", *methods]
	out = df[
		(df["num_jobs"].astype(int) == num_jobs)
		& (df["strategy"].astype(str).isin(allowed_strategies))
	].copy()
	return out


def build_normalized_for_num_jobs(
	scope_df: pd.DataFrame,
	methods: list[str],
) -> tuple[pd.DataFrame, list[str]]:
	"""Build normalized metrics for all (day, workload_type) combinations in scope_df."""
	rows: list[dict[str, object]] = []
	warnings: list[str] = []

	# Group by (day, workload_type) combination
	for (day, wtype), group in scope_df.groupby(["day", "workload_type"]):
		pure = group[group["strategy"] == "PureLocal"]
		if pure.empty:
			warnings.append(f"Missing PureLocal baseline for day={day}, workload_type={wtype}.")
			continue
		pure_row = pure.iloc[0]

		for method in methods:
			method_row = group[group["strategy"] == method]
			if method_row.empty:
				continue  # Skip silently if method not available for this combo
			mrow = method_row.iloc[0]

			for objective in OBJECTIVE_COLUMNS:
				baseline = float(pure_row[objective])
				value = float(mrow[objective])
				if baseline == 0.0:
					continue
				rows.append(
					{
						"day": day,
						"workload_type": wtype,
						"strategy": method,
						"objective": objective,
						"normalized": value / baseline,
					}
				)

	return pd.DataFrame(rows), warnings


def _scenario_label_title(num_jobs: int) -> str:
	mapping = {1000: "r32", 2000: "r16", 4000: "r8"}
	return f"{mapping.get(num_jobs, f'n{num_jobs}')} (jobs={num_jobs})"


def plot_grid_for_num_jobs(
	norm_df: pd.DataFrame,
	output_path: Path,
	methods: list[str],
	num_jobs_val: int,
) -> None:
	"""Plot a 3×4 grid: rows=day, cols=workload_type."""
	days = ["busy", "bursty_low_stress", "bursty_high_stress"]
	workload_types = ["homogeneous_short", "mixed_20_80", "mixed_80_20", "only_large_long"]

	x = np.arange(len(OBJECTIVE_COLUMNS))
	width = 0.35
	colors = {
		"HeuristicBidding": "#1f77b4",
		"EmbeddingBidding": "#ff7f0e",
	}

	fig, axes = plt.subplots(3, 4, figsize=(16, 12))

	# Iterate and plot each cell
	for row_idx, day in enumerate(days):
		for col_idx, wtype in enumerate(workload_types):
			ax = axes[row_idx, col_idx]
			sub = norm_df[(norm_df["day"] == day) & (norm_df["workload_type"] == wtype)]

			# If no data for this cell, leave it empty and continue
			if sub.empty:
				ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes, fontsize=10)
				ax.set_xticks([])
				ax.set_yticks([])
				if col_idx == 0:
					ax.set_ylabel(day.replace("_", " "), fontsize=10, labelpad=10)
				if row_idx == 0:
					ax.set_title(wtype.replace("_", " "), fontsize=10, loc="center")
				continue

			for idx, method in enumerate(methods):
				vals = []
				for obj in OBJECTIVE_COLUMNS:
					row_data = sub[(sub["strategy"] == method) & (sub["objective"] == obj)]
					vals.append(float(row_data.iloc[0]["normalized"]) if not row_data.empty else np.nan)

				offset = (idx - (len(methods) - 1) / 2.0) * width
				bars = ax.bar(
					x + offset,
					vals,
					width,
					label=method,
					color=colors.get(method, None),
					alpha=0.9,
				)
				for b in bars:
					h = b.get_height()
					if np.isnan(h):
						continue
					ax.text(
						b.get_x() + b.get_width() / 2.0,
						h,
						f"{h:.2f}",
						ha="center",
						va="bottom",
						fontsize=7,
					)

			ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="PureLocal baseline")
			ax.set_xticks(x)
			ax.set_xticklabels([OBJECTIVE_LABELS[c] for c in OBJECTIVE_COLUMNS], rotation=45, ha="right", fontsize=8)
			ax.set_ylim(0, None)
			ax.grid(axis="y", alpha=0.25)

			# Add column and row headers
			if row_idx == 0:
				ax.set_title(wtype.replace("_", " "), fontsize=10, loc="center")
			if col_idx == 0:
				ax.set_ylabel(day.replace("_", " "), fontsize=10, labelpad=10)

	# Add common legend at the bottom center
	handles, labels = axes[0, 0].get_legend_handles_labels()
	# Filter out the baseline line from legend
	legend_handles = [h for h, l in zip(handles, labels) if "baseline" not in l.lower()]
	legend_labels = [l for l in labels if "baseline" not in l.lower()]
	if legend_handles:
		fig.legend(legend_handles, legend_labels, loc="lower center", ncol=len(methods), frameon=True, bbox_to_anchor=(0.5, -0.02))

	fig.suptitle(
		f"Normalized Objectives vs PureLocal - {_scenario_label_title(num_jobs_val)}",
		fontsize=14,
		y=0.995,
	)
	# Add common y-axis label
	fig.text(0.02, 0.5, "Normalized value (PureLocal = 1.0)", va="center", rotation="vertical", fontsize=11)

	fig.tight_layout(rect=(0.05, 0.05, 1, 0.99))
	output_path.parent.mkdir(parents=True, exist_ok=True)
	fig.savefig(output_path, dpi=300, bbox_inches="tight")
	print(f"Saved plot to: {output_path}")
	plt.close(fig)


def main() -> None:
	args = parse_args()
	input_path = Path(args.input)
	output_dir = Path(args.output_dir)

	if not input_path.exists():
		raise FileNotFoundError(f"Input CSV not found: {input_path}")

	methods = _parse_csv_list(args.methods)
	if not methods:
		raise ValueError("At least one method must be provided via --methods.")

	jobs = _parse_int_list(args.num_jobs)
	if not jobs:
		raise ValueError("At least one num_jobs value must be provided via --num-jobs.")

	df = pd.read_csv(input_path)
	validate_columns(df)

	# Process each num_jobs value separately
	all_warnings: list[str] = []
	for num_jobs_val in jobs:
		scoped = filter_by_num_jobs(df=df, num_jobs=num_jobs_val, methods=methods)
		if scoped.empty:
			print(f"Warning: No rows found for num_jobs={num_jobs_val}; skipping.")
			continue

		norm_df, warnings = build_normalized_for_num_jobs(scoped, methods=methods)
		all_warnings.extend(warnings)

		if norm_df.empty:
			print(f"Warning: Normalization produced no rows for num_jobs={num_jobs_val}.")
			continue

		# Generate output filename
		scenario_tag = _scenario_label_title(num_jobs_val).replace(" ", "_").replace("(", "").replace(")", "")
		output_path = output_dir / f"normalized_objectives_grid_{scenario_tag}.png"
		plot_grid_for_num_jobs(
			norm_df=norm_df,
			output_path=output_path,
			methods=methods,
			num_jobs_val=num_jobs_val,
		)

	if all_warnings:
		print("\nWarnings:")
		for w in all_warnings:
			print(f"- {w}")


if __name__ == "__main__":
	main()
