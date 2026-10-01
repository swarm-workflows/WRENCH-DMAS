#!/usr/bin/env python3
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
import matplotlib.pyplot as plt

ARRIVAL_PATTERNS = [
    ("business", "Business day"),
    ("bursty_low_stress", "Bursty low stress"),
    ("bursty_high_stress", "Bursty high stress"),
]

SITE_COLORS = {
    "ALCF": "#4E79A7",
    "NERSC": "#F28E2B",
    "OLCF": "#59A14F",
}

REQUIRED_COLUMNS = {"SubmissionTime", "HPCSite"}
PANEL_SIZE_INCHES = 3.0
LEGEND_HEIGHT_INCHES = 0.55

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot business-day, bursty low-stress, and bursty high-stress "
            "workload arrivals in side-by-side panels."
        )
    )
    parser.add_argument(
        "--data-dir",
        default="data_generation/data",
        help="Directory containing workload JSON files.",
    )
    parser.add_argument(
        "--rho",
        default=1.5,
        help="Rho value to plot, e.g. 0.9 or 1.5. A leading 'rho' is accepted.",
    )
    parser.add_argument(
        "--workload-type",
        default="small_short",
        choices=["small_short", "large_long", "mixed_80_20", "mixed_20_80"],
        help="Workload composition to compare across arrival patterns.",
    )
    parser.add_argument(
        "--num-jobs",
        type=int,
        default=None,
        help=(
            "Optional job count in the filename. If omitted, the script "
            "auto-detects the one matching file per arrival pattern."
        ),
    )
    parser.add_argument(
        "--bin-width-hours",
        type=float,
        default=0.5,
        help="Histogram bin width in hours.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output image path. Default: "
            "plots/workload/arrival_patterns_<workload-type>_rho<rho>.png"
        ),
    )
    return parser.parse_args()


def normalize_rho(value: str) -> str:
    value = str(value).strip()
    return value[3:] if value.startswith("rho") else value


def find_workload_file(
    data_dir: Path,
    arrival_pattern: str,
    workload_type: str,
    rho: str,
    num_jobs: int | None,
) -> Path:
    if num_jobs is None:
        matches = sorted(data_dir.glob(f"{arrival_pattern}_{workload_type}_*_rho{rho}.json"))
    else:
        matches = [data_dir / f"{arrival_pattern}_{workload_type}_{num_jobs}_rho{rho}.json"]
        matches = [path for path in matches if path.exists()]

    if not matches:
        raise FileNotFoundError(
            "No workload file found for "
            f"arrival_pattern={arrival_pattern}, workload_type={workload_type}, "
            f"rho={rho}, num_jobs={num_jobs or 'auto'}"
        )

    if len(matches) > 1:
        raise ValueError(
            "Multiple matching workload files found; pass --num-jobs to disambiguate:\n"
            + "\n".join(str(path) for path in matches)
        )

    return matches[0]


def load_jobs(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        jobs = json.load(handle)

    if not isinstance(jobs, list):
        raise ValueError(f"Expected a JSON array in {path}")

    missing = {
        column
        for column in REQUIRED_COLUMNS
        if any(column not in job for job in jobs)
    }
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

    return jobs


def make_edges(max_hours: float, bin_width_hours: float) -> list[float]:
    if bin_width_hours <= 0:
        raise ValueError("--bin-width-hours must be > 0")

    right_edge = max(bin_width_hours, math.ceil(max_hours / bin_width_hours) * bin_width_hours)
    count = int(round(right_edge / bin_width_hours))
    return [i * bin_width_hours for i in range(count + 1)]


def histogram_by_site(jobs: list[dict], edges: list[float]) -> dict[str, list[int]]:
    site_counts: dict[str, list[int]] = defaultdict(lambda: [0] * (len(edges) - 1))
    bin_width = edges[1] - edges[0]

    for job in jobs:
        site = str(job["HPCSite"])
        hour = float(job["SubmissionTime"]) / 3600.0
        idx = int(math.floor((hour - edges[0]) / bin_width))
        idx = max(0, min(idx, len(edges) - 2))
        site_counts[site][idx] += 1

    return dict(site_counts)


def format_workload_type(value: str) -> str:
    return {
        "small_short": "small/short",
        "large_long": "large/long",
        "mixed_80_20": "mixed 80/20",
        "mixed_20_80": "mixed 20/80",
    }.get(value, value.replace("_", " "))


def get_job_count_label(datasets: list[dict]) -> str:
    counts = sorted({len(dataset["jobs"]) for dataset in datasets})
    if len(counts) == 1:
        return f"{counts[0]} jobs"
    return "job counts: " + ", ".join(str(count) for count in counts)


def plot_arrivals(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    rho = normalize_rho(args.rho)

    datasets = []
    for arrival_pattern, arrival_label in ARRIVAL_PATTERNS:
        path = find_workload_file(
            data_dir=data_dir,
            arrival_pattern=arrival_pattern,
            workload_type=args.workload_type,
            rho=rho,
            num_jobs=args.num_jobs,
        )
        jobs = load_jobs(path)
        datasets.append(
            {
                "arrival_pattern": arrival_pattern,
                "arrival_label": arrival_label,
                "path": path,
                "jobs": jobs,
            }
        )

    all_sites = sorted(
        {
            str(job["HPCSite"])
            for dataset in datasets
            for job in dataset["jobs"]
        }
    )

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(3 * PANEL_SIZE_INCHES, PANEL_SIZE_INCHES + LEGEND_HEIGHT_INCHES),
    )

    for ax, dataset in zip(axes, datasets):
        max_hours = max(float(job["SubmissionTime"]) / 3600.0 for job in dataset["jobs"])
        edges = make_edges(max_hours=max_hours, bin_width_hours=args.bin_width_hours)
        centers = [(edges[i] + edges[i + 1]) / 2.0 for i in range(len(edges) - 1)]
        width = args.bin_width_hours * 0.92

        site_counts = histogram_by_site(dataset["jobs"], edges)
        bottom = [0] * (len(edges) - 1)

        for site in all_sites:
            counts = site_counts.get(site, [0] * (len(edges) - 1))
            ax.bar(
                centers,
                counts,
                width=width,
                bottom=bottom,
                color=SITE_COLORS.get(site),
                edgecolor="white",
                linewidth=0.35,
                label=site,
            )
            bottom = [a + b for a, b in zip(bottom, counts)]

        ax.set_title(dataset["arrival_label"])
        ax.set_xlabel("Submission time (hours)")
        if hasattr(ax, "set_box_aspect"):
            ax.set_box_aspect(1)
        ax.grid(axis="y", color="#d9d9d9", linewidth=0.8)
        ax.set_axisbelow(True)

    axes[0].set_ylabel("Job arrivals per bin")

    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=max(1, len(labels)),
        frameon=True,
    )

    fig.tight_layout(rect=(0, 0.11, 1, 0.98))

    output = (
        Path(args.output)
        if args.output
        else Path("plots/workload") / f"arrival_patterns_{args.workload_type}_rho{rho}.png"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight")
    print(f"Saved: {output}")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    plot_arrivals(args)


if __name__ == "__main__":
    main()
