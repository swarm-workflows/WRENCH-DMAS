#!/usr/bin/env python3

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from analyze_results import (
    BASE_SYSTEM_CAPACITIES,
    GanttVisualization,
    bulksetattr,
    filter_successful_jobs,
    generate_palette,
    load_job_definitions,
    load_results,
)


REQUIRED_GANTT_COLUMNS = {"ScheduledOn", "NodeList", "StartTime", "ExecutionTime", "JobId"}


def parse_result_name(csv_path):
    stem = csv_path.stem
    if "_" not in stem:
        raise ValueError(f"Cannot parse workload/method from filename: {csv_path.name}")

    workload_name, method_name = stem.rsplit("_", maxsplit=1)
    return workload_name, method_name


def workload_path_for(workload_name, data_dir):
    return data_dir / f"{workload_name}.json"


def load_valid_results(csv_path, data_dir):
    workload_name, _ = parse_result_name(csv_path)
    workload_path = workload_path_for(workload_name, data_dir)

    jobs_df = None
    if workload_path.exists():
        jobs_df = load_job_definitions(workload_path)
    else:
        print(f"Warning: workload file not found: {workload_path}")

    df = load_results(csv_path, jobs_df)
    df = filter_successful_jobs(df)
    if "FinalStatus" in df.columns:
        df = df[df["FinalStatus"] == "COMPLETED"]
    return df


def validate_gantt_columns(df, csv_path):
    missing = sorted(REQUIRED_GANTT_COLUMNS - set(df.columns))
    if missing:
        print(f"Skipping {csv_path}: missing Gantt columns {missing}")
        return False
    return True


def max_endtime_hours(df):
    if df.empty:
        return 0.0
    if "EndTime" in df.columns:
        return float(df["EndTime"].max()) / 3600.0
    return float((df["StartTime"] + df["ExecutionTime"]).max()) / 3600.0


def shared_xmax_hours(*frames):
    max_hours = max((max_endtime_hours(df) for df in frames), default=0.0)
    return max(5.0, float(math.ceil(max_hours / 5.0) * 5.0))


def gantt_systems(*frames):
    systems = set()
    for df in frames:
        if "ScheduledOn" in df.columns:
            systems.update(df["ScheduledOn"].dropna().unique())
    return sorted(systems)


def draw_empty_axis(ax, system, mode_name, x_max_hours):
    ax.set_title(f"{mode_name} - 0 jobs", fontweight="bold", fontsize=12)
    ax.set_ylabel(f"{system}\nNode IDs", fontweight="bold", fontsize=10)
    ax.set_xlim(0.0, x_max_hours)
    ax.set_ylim(0.0, 1.0)
    ax.grid(True, alpha=0.25, axis="x")
    ax.text(
        0.5,
        0.5,
        "No completed jobs",
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=9,
        color="dimgray",
    )


def draw_mode_system(ax, df, system, mode_name, system_capacities, show_job_ids, x_max_hours):
    system_df = df[df["ScheduledOn"] == system].copy()
    system_df = system_df.sort_values("StartTime")

    if system_df.empty:
        draw_empty_axis(ax, system, mode_name, x_max_hours)
        return

    system_capacity = system_capacities.get(system, {}).get("nodes", 0)
    viz = GanttVisualization(ax, title=f"{system} {mode_name} Gantt")
    bulksetattr(viz, palette=generate_palette(max(8, len(system_df))))
    viz.draw_system(system_df, system, system_capacity, show_job_ids=show_job_ids)
    ax.set_title(f"{mode_name} - {len(system_df)} jobs", fontweight="bold", fontsize=12)
    ax.set_xlim(0.0, x_max_hours)


def plot_comparison_gantt(
    decentralized_df,
    centralized_df,
    output_path,
    workload_name,
    method_name,
    system_capacities,
    show_job_ids=True,
):
    systems = gantt_systems(decentralized_df, centralized_df)
    if not systems:
        print(f"Skipping {workload_name}_{method_name}: no systems with completed jobs")
        return False

    x_max_hours = shared_xmax_hours(decentralized_df, centralized_df)
    fig_height = max(4.8, 3.8 * len(systems))
    fig, axes = plt.subplots(
        len(systems),
        2,
        figsize=(24, fig_height),
        sharex=True,
        squeeze=False,
    )

    fig.suptitle(
        f"Centralized vs Decentralized System Gantt\n{workload_name} | {method_name}",
        fontsize=16,
        fontweight="bold",
    )

    for row_idx, system in enumerate(systems):
        left_ax = axes[row_idx][0]
        right_ax = axes[row_idx][1]

        draw_mode_system(
            left_ax,
            decentralized_df,
            system,
            "Decentralized",
            system_capacities,
            show_job_ids,
            x_max_hours,
        )
        draw_mode_system(
            right_ax,
            centralized_df,
            system,
            "Centralized",
            system_capacities,
            show_job_ids,
            x_max_hours,
        )

        y_min = min(left_ax.get_ylim()[0], right_ax.get_ylim()[0])
        y_max = max(left_ax.get_ylim()[1], right_ax.get_ylim()[1])
        left_ax.set_ylim(y_min, y_max)
        right_ax.set_ylim(y_min, y_max)

    ticks = np.arange(0, x_max_hours + 0.1, 5)
    for ax in axes[-1]:
        ax.set_xticks(ticks)
        ax.set_xlabel("Start Time (hours)", fontweight="bold", fontsize=11)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout(rect=[0, 0.02, 1, 0.96])
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved comparison Gantt plot to {output_path}")
    return True


def iter_result_pairs(results_dir):
    centralized_dir = results_dir / "centralized"
    for decentralized_csv in sorted(results_dir.glob("*.csv")):
        if decentralized_csv.name == "aggregated_metrics.csv":
            continue

        centralized_csv = centralized_dir / decentralized_csv.name
        if not centralized_csv.exists():
            print(f"Skipping missing centralized pair: {centralized_csv}")
            continue

        yield decentralized_csv, centralized_csv


def main():
    parser = argparse.ArgumentParser(
        description="Generate side-by-side centralized/decentralized Gantt comparisons."
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Directory containing decentralized CSVs and a centralized/ subdirectory.",
    )
    parser.add_argument(
        "--output-dir",
        default="plots/comparison/gantt",
        help="Directory where comparison Gantt PNGs will be written.",
    )
    parser.add_argument(
        "--data-dir",
        default="data_generation/data",
        help="Directory containing workload JSON files.",
    )
    parser.add_argument(
        "--hide-jobids",
        action="store_true",
        help="Hide job-id labels inside Gantt rectangles.",
    )

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    data_dir = Path(args.data_dir)

    if not results_dir.is_absolute():
        results_dir = project_root / results_dir
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    if not data_dir.is_absolute():
        data_dir = project_root / data_dir

    if not results_dir.exists():
        print(f"Error: results directory not found: {results_dir}")
        return 1

    count = 0
    for decentralized_csv, centralized_csv in iter_result_pairs(results_dir):
        workload_name, method_name = parse_result_name(decentralized_csv)
        print(f"Generating Gantt comparison for {workload_name} | {method_name}")

        try:
            decentralized_df = load_valid_results(decentralized_csv, data_dir)
            centralized_df = load_valid_results(centralized_csv, data_dir)
        except Exception as exc:
            print(f"Skipping {decentralized_csv.name}: {exc}")
            continue

        if not validate_gantt_columns(decentralized_df, decentralized_csv):
            continue
        if not validate_gantt_columns(centralized_df, centralized_csv):
            continue

        output_path = output_dir / f"gantt_comparison_{workload_name}_{method_name}.png"
        if plot_comparison_gantt(
            decentralized_df,
            centralized_df,
            output_path,
            workload_name,
            method_name,
            BASE_SYSTEM_CAPACITIES,
            show_job_ids=(not args.hide_jobids),
        ):
            count += 1

    print(f"Generated {count} comparison Gantt plot(s) under {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
