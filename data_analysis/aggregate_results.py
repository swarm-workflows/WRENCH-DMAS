import pandas as pd
from pathlib import Path
from pandas.errors import EmptyDataError

RHO_VALUES = [1.5, 0.9]
SCENARIO_NJOBS_BY_RHO = {
    1.5: {
        "mixed_80_20": 415,
        "mixed_20_80": 112,
        "large_long": 91,
        "small_short": 4800,
    },
    0.9: {
        "mixed_80_20": 251,
        "mixed_20_80": 67,
        "large_long": 54,
        "small_short": 2880,
    },
}

RESULTS_DIR = Path("results")
CENTRALIZED_DIR = RESULTS_DIR / "centralized"
OUTPUT_FILE = RESULTS_DIR / "aggregated_metrics.csv"

DAYS = ["bursty_low_stress", "bursty_high_stress", "business"]      # "business", 
TYPES = ["small_short", "large_long", "mixed_80_20", "mixed_20_80"]     # , "large_long", "mixed_80_20", "mixed_20_80"

PYTHON_BIDDERS = ["HeuristicBidding", "EmbeddingBidding", "LLMBidding"]     #    "EmbeddingBidding", 
BASELINE_POLICIES = ["PureLocal"]           # "RandomBidding",  
ALL_STRATEGIES = PYTHON_BIDDERS + BASELINE_POLICIES


def _to_numeric(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def filter_valid_jobs(df):
    filtered = df.copy()
    if "FinalStatus" in filtered.columns:
        status = filtered["FinalStatus"].astype("string").str.lower()
        success_mask = (
            status.str.contains("success", na=False)
            | status.str.contains("completed", na=False)
            | status.str.contains("finished", na=False)
        )
        failure_mask = (
            status.str.contains("fail", na=False)
            | status.str.contains("reject", na=False)
            | status.str.contains("unscheduled", na=False)
        )
        if success_mask.any():
            filtered = filtered[success_mask]
        else:
            filtered = filtered[~failure_mask]
    if "ScheduledOn" in filtered.columns:
        filtered = filtered[
            filtered["ScheduledOn"].notna()
            & (filtered["ScheduledOn"].astype(str).str.strip() != "")
        ]
    if "ExecutionTime" in filtered.columns:
        filtered = filtered[filtered["ExecutionTime"] > 0]
    if "EndTime" in filtered.columns:
        filtered = filtered[filtered["EndTime"].notna()]
        filtered = filtered[filtered["EndTime"] > 0]

    return filtered


def mean_std(series):
    s = series.dropna()
    if s.empty:
        return None, None
    return float(s.mean()), float(s.std(ddof=1)) if len(s) > 1 else 0.0

def empty_metrics():
    return {
        "total_jobs": 0,
        "completed_jobs": 0,
        "failed_jobs": 0,
        "completion_ratio": None,
        "makespan_seconds": None,
        "throughput_jobs_per_second": None,
        "turnaround_mean": None,
        "turnaround_std": None,
        "waiting_mean": None,
        "waiting_std": None,
        "execution_mean": None,
        "execution_std": None,
        "decision_mean": None,
        "decision_std": None,
    }


def calculate_metrics(csv_path):
    try:
        raw_df = pd.read_csv(csv_path)
    except EmptyDataError:
        print(f"Warning: empty CSV file: {csv_path}")
        return empty_metrics()

    if raw_df.empty:
        print(f"Warning: CSV has headers but no rows: {csv_path}")
        return empty_metrics()
 
    time_cols = [
        "SubmissionTime",
        "SchedulingTime",
        "StartTime",
        "EndTime",
        "DecisionTime",
        "WaitingTime",
        "ExecutionTime",
    ]

    raw_df = _to_numeric(raw_df, time_cols)

    total_jobs = len(raw_df)

    df = filter_valid_jobs(raw_df)

    completed_jobs = len(df)
    failed_jobs = total_jobs - completed_jobs
    completion_ratio = completed_jobs / total_jobs if total_jobs > 0 else None

    if "TurnaroundTime" not in df.columns and {"EndTime","SubmissionTime"}.issubset(df.columns):
        df["TurnaroundTime"] = df["EndTime"] - df["SubmissionTime"]

    # Makespan
    makespan_seconds = None
    throughput_jobs_per_second = None

    if not df.empty and {"EndTime","SubmissionTime"}.issubset(df.columns):

        min_submit = df["SubmissionTime"].min()
        max_end = df["EndTime"].max()

        if pd.notna(min_submit) and pd.notna(max_end):

            makespan_seconds = max_end - min_submit
            if makespan_seconds > 0:
                throughput_jobs_per_second = completed_jobs / makespan_seconds

    turnaround_mean, turnaround_std = mean_std(df["TurnaroundTime"]) if "TurnaroundTime" in df else (None,None)
    waiting_mean, waiting_std = mean_std(df["WaitingTime"]) if "WaitingTime" in df else (None,None)
    execution_mean, execution_std = mean_std(df["ExecutionTime"]) if "ExecutionTime" in df else (None,None)
    decision_mean, decision_std = mean_std(df["DecisionTime"]) if "DecisionTime" in df else (None,None)

    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "completion_ratio": completion_ratio,
        "makespan_seconds": makespan_seconds,
        "throughput_jobs_per_second": throughput_jobs_per_second,
        "turnaround_mean": turnaround_mean,
        "turnaround_std": turnaround_std,
        "waiting_mean": waiting_mean,
        "waiting_std": waiting_std,
        "execution_mean": execution_mean,
        "execution_std": execution_std,
        "decision_mean": decision_mean,
        "decision_std": decision_std,
    }


def main():
    rows = []

    for rho in RHO_VALUES:
        scenario_njobs = SCENARIO_NJOBS_BY_RHO[rho]
        for day in DAYS:
            for workload_type in TYPES:
                num_jobs = scenario_njobs[workload_type]
                workload_name = f"{day}_{workload_type}_{num_jobs}_rho{rho}"

                for mode, base_dir in [("decentralized", RESULTS_DIR), ("centralized", CENTRALIZED_DIR)]:       # 
                    for strategy in ALL_STRATEGIES:
                        csv_path = base_dir / f"{workload_name}_{strategy}.csv"
                        if not csv_path.exists():
                            print(f"Skipping missing file: {csv_path}")
                            continue
                        print(f"Processing {mode} - {csv_path.name}")
                        metrics = calculate_metrics(csv_path)
                        row = {
                                "mode": mode,
                                "day": day,
                                "workload_type": workload_type,
                                "num_jobs": num_jobs,
                                "rho": rho,
                                "strategy": strategy,
                                **metrics,
                            }
                        rows.append(row)

    if not rows:
        print("No matching CSV files found.")
        return

    df_summary = pd.DataFrame(rows)

    column_order = [
        "mode","day","workload_type","num_jobs","rho","strategy",
        "total_jobs","completed_jobs","failed_jobs","completion_ratio",
        "makespan_seconds","throughput_jobs_per_second",
        "turnaround_mean","turnaround_std",
        "waiting_mean","waiting_std",
        "execution_mean","execution_std",
        "decision_mean","decision_std"
    ]

    df_summary = df_summary[column_order]
    df_summary.sort_values(
        by=["mode","day","workload_type", "rho", "num_jobs","strategy"],
        inplace=True
    )

    # Compute percent change vs PureLocal for key metrics
    for metric in ["makespan_seconds", "waiting_mean", "execution_mean", "turnaround_mean"]:
        pct_col = f"{metric}_pct_vs_purelocal"

        purelocal = df_summary[df_summary["strategy"] == "PureLocal"]
        # Merge to align each row with its PureLocal baseline
        merged = df_summary.merge(
            purelocal[["mode", "day", "workload_type", "num_jobs", "rho", metric]],
            on=["mode", "day", "workload_type", "num_jobs", "rho"],
            suffixes=("", "_purelocal"),
            how="left"
        )

        # Compute percent change
        merged[pct_col] = (
            (merged[metric] - merged[f"{metric}_purelocal"])
            / merged[f"{metric}_purelocal"]
            * 100
        ).round(2)

        def format_pct_change(val):
            if pd.isna(val):
                return None
            arrow = "↑" if val > 0 else "↓" if val < 0 else ""
            return f"{val}% {arrow}"

        merged[pct_col] = merged[pct_col].apply(format_pct_change)
        df_summary[pct_col] = merged[pct_col]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df_summary.to_csv(OUTPUT_FILE, index=False)

    print("\nAggregated Metrics Table:\n")
    print(df_summary.to_string(index=False))

    print(f"\nSaved aggregated metrics to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
