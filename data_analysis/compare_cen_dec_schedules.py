#!/usr/bin/env python3

import argparse
from pathlib import Path
from typing import List, Tuple
import json
import pandas as pd

"""
Compare Centralized vs Decentralized Schedules
How to run: python data_analysis/compare_cen_dec_schedules.py --batch

Desc: This script compares centralized and decentralized scheduling results for the same workload.
Jobs are matched by JobID and analyzed to determine whether both schedulers produced the same
allocation decision and approximately the same start time.

Generated artifacts:
- results/comparison/differences/allocation_diff_<workload>.csv
- results/comparison/matches/allocation_match_<workload>.csv

Important note: The Bids column in the decentralized CSV is reordered to match the centralized bid-slot ordering
for comparison purposes. The centralized bid order is: andes, aurora, crux, frontier, P1, P2
The decentralized bid order is: andes, aurora, crux, P1, frontier, P2
Only the order of frontier and P1 is different, so we will sort the bids in the same order as centralized for comparison.
"""

def normalize_system(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip()


def normalize_start_time(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"JobId", "ScheduledOn", "StartTime"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing required columns: {sorted(missing)}")
    return df


def derive_match_output_path(diff_path: Path) -> Path:
    path_str = str(diff_path)
    if "/differences/" in path_str:
        path_str = path_str.replace("/differences/", "/matches/", 1)
    filename = Path(path_str).name
    if filename.startswith("allocation_diff_"):
        filename = filename.replace("allocation_diff_", "allocation_match_", 1)
    else:
        filename = f"allocation_match_{filename}"
    return Path(path_str).with_name(filename)

def load_workload_jobs(workload_json_path: Path) -> pd.DataFrame:
    with workload_json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list):
        raise ValueError(f"{workload_json_path} must contain a JSON list of jobs")

    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if "JobID" not in item:
            continue
        rows.append(
            {
                "JobId": int(item["JobID"]),
                "Job_json": json.dumps(item, separators=(",", ":"), sort_keys=True),
            }
        )

    return pd.DataFrame(rows)
def parse_bids(value: object) -> List[float]:
    if pd.isna(value):
        return []
    text = str(value).strip().strip('"')
    if not text:
        return []

    bids: List[float] = []
    for token in text.split(":"):
        token = token.strip()
        if not token:
            continue
        try:
            bids.append(float(token))
        except ValueError:
            return []
    return bids

def compare_allocations(
    decentralized_csv: Path,
    centralized_csv: Path,
    start_time_tolerance: float = 1.0,
    workload_json: Path = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    dec = load_csv(decentralized_csv).copy()
    cen = load_csv(centralized_csv).copy()

    dec = dec.rename(
        columns={
            "ScheduledOn": "ScheduledOn_decentralized",
            "StartTime": "StartTime_decentralized",
            "Bids": "Bids_decentralized",
            # "FinalStatus": "FinalStatus_decentralized",
        }
    )
    cen = cen.rename(
        columns={
            "ScheduledOn": "ScheduledOn_centralized",
            "StartTime": "StartTime_centralized",
            "Bids": "Bids_centralized",
            # "FinalStatus": "FinalStatus_centralized",
        }
    )

    keep_dec = [
        c
        for c in [
            "JobId",
            "ScheduledOn_decentralized",
            "StartTime_decentralized",
            "Bids_decentralized",
            # "FinalStatus_decentralized",
        ]
        if c in dec.columns
    ]
    keep_cen = [
        c
        for c in [
            "JobId",
            "ScheduledOn_centralized",
            "StartTime_centralized",
            "Bids_centralized",
            # "FinalStatus_centralized",
        ]
        if c in cen.columns
    ]

    merged = pd.merge(dec[keep_dec], cen[keep_cen], on="JobId", how="outer", indicator=True)

    # --> changing the order of bids to keep same as centralized for comparison
    CENTRALIZED_ORDER = ["Andes", "Aurora", "Crux", "Frontier", "P1", "P2"]
    DECENTRALIZED_ORDER = ["Andes", "Aurora", "Crux", "P1", "Frontier", "P2"]

    # index mapping: dec -> cen
    DEC_TO_CEN = [0, 1, 2, 4, 3, 5]
    def reorder_dec_to_cen(bids):
        return [bids[i] for i in DEC_TO_CEN]
    

    merged["Bids_decentralized"] = merged["Bids_decentralized"].apply(
        lambda x: ":".join(map(str, reorder_dec_to_cen(parse_bids(x)))) if pd.notna(x) else x
    )
    

    dec_sys = normalize_system(
        merged.get("ScheduledOn_decentralized", pd.Series(index=merged.index, dtype="string"))
    )
    cen_sys = normalize_system(
        merged.get("ScheduledOn_centralized", pd.Series(index=merged.index, dtype="string"))
    )
    dec_start = normalize_start_time(
        merged.get("StartTime_decentralized", pd.Series(index=merged.index, dtype="float64"))
    )
    cen_start = normalize_start_time(
        merged.get("StartTime_centralized", pd.Series(index=merged.index, dtype="float64"))
    )

    merged["ScheduledOn_decentralized"] = dec_sys
    merged["ScheduledOn_centralized"] = cen_sys
    merged["StartTime_decentralized"] = dec_start
    merged["StartTime_centralized"] = cen_start

    start_missing_both = dec_start.isna() & cen_start.isna()
    start_present_both = dec_start.notna() & cen_start.notna()
    start_equal_present = (dec_start - cen_start).abs() <= float(start_time_tolerance)
    start_equal = start_missing_both | (start_present_both & start_equal_present)

    site_mismatch = dec_sys != cen_sys
    start_time_mismatch = ~start_equal

    merged["site_mismatch"] = site_mismatch
    merged["start_time_mismatch"] = start_time_mismatch
    merged["different_allocation"] = site_mismatch | start_time_mismatch
    merged["same_allocation"] = (
        (merged["_merge"] == "both") & (~site_mismatch) & (~start_time_mismatch)
    )
    merged["start_time_abs_diff"] = (dec_start - cen_start).abs()

    merged["difference_reason"] = "same"
    merged.loc[merged["_merge"] == "left_only", "difference_reason"] = "missing_in_centralized"
    merged.loc[merged["_merge"] == "right_only", "difference_reason"] = "missing_in_decentralized"
    merged.loc[
        (merged["_merge"] == "both") & site_mismatch & start_time_mismatch,
        "difference_reason",
    ] = "site_and_start_time_mismatch"
    merged.loc[
        (merged["_merge"] == "both") & site_mismatch & ~start_time_mismatch,
        "difference_reason",
    ] = "site_mismatch"
    merged.loc[
        (merged["_merge"] == "both") & ~site_mismatch & start_time_mismatch,
        "difference_reason",
    ] = "start_time_mismatch"
    merged.loc[
        (merged["_merge"] == "both") & ~site_mismatch & ~start_time_mismatch,
        "difference_reason",
    ] = "site_and_start_time_match"

    print(f"Decentralized CSV: {decentralized_csv}")
    print(f"Centralized CSV:   {centralized_csv}")
    print(f"Site matches: {(~site_mismatch).sum()} / {len(merged)}")
    print(
        "Site+start matches "
        f"(tolerance={start_time_tolerance}s): {((~site_mismatch) & (~start_time_mismatch)).sum()} / {len(merged)}"
    )

    # create a column is_same_bid_order
    # each bids column is a string of comma-separated bids, we compare them as lists of strings
    # def parse_bids(bids_str: str) -> List[str]:
    #     if pd.isna(bids_str):
    #         return []
    #     return [b.strip() for b in str(bids_str).split(",") if b.strip()]


    
    merged["is_same_bid_order"] = merged.apply(
        lambda row: parse_bids(row["Bids_decentralized"]) == parse_bids(row["Bids_centralized"]),
        axis=1,
    )

    # max of all bids is top bid
    merged["top_bid_decentralized"] = merged["Bids_decentralized"].apply(
        lambda bids_str: max(parse_bids(bids_str), default=None)
    )
    merged["top_bid_centralized"] = merged["Bids_centralized"].apply(
        lambda bids_str: max(parse_bids(bids_str), default=None)
    )

    # top bid match is a tie
    merged["top_bid_match"] = merged["top_bid_decentralized"] == merged["top_bid_centralized"]

    # how many bids are unique in both decentralized and centralized
    merged["num_unique_bids_in_both"] = merged.apply(
        lambda row: len(set(parse_bids(row["Bids_decentralized"])) & set(parse_bids(row["Bids_centralized"]))),
        axis=1,
    )

    # how many bids are different in both decentralized and centralized
    merged["num_different_bids_in_both"] = merged.apply(
        lambda row: len(set(parse_bids(row["Bids_decentralized"])) ^ set(parse_bids(row["Bids_centralized"]))),
        axis=1,
    )

    # print variance of bids in both decentralized and centralized
    # merged["variance_bids_decentralized"] = merged["Bids_decentralized"].apply(
    #     lambda bids_str: pd.Series(parse_bids(bids_str)).var() if parse_bids(bids_str) else None
    # )
    # merged["variance_bids_centralized"] = merged["Bids_centralized"].apply(
    #     lambda bids_str: pd.Series(parse_bids(bids_str)).var() if parse_bids(bids_str) else None
    # )

    # variance of top 2 bids in both decentralized and centralized
    merged["variance_top2_bids_decentralized"] = merged["Bids_decentralized"].apply(
        lambda bids_str: pd.Series(sorted(parse_bids(bids_str), reverse=True)[:2]).var() if parse_bids(bids_str) else None
    )
    merged["variance_top2_bids_centralized"] = merged["Bids_centralized"].apply(
        lambda bids_str: pd.Series(sorted(parse_bids(bids_str), reverse=True)[:2]).var() if parse_bids(bids_str) else None
    )

    if workload_json is not None:
        if not workload_json.exists():
            raise ValueError(f"Workload JSON not found: {workload_json}")
        jobs_df = load_workload_jobs(workload_json_path=workload_json)
        if not jobs_df.empty:
            # with a column named job_json containing the original job JSON data
            merged = pd.merge(merged, jobs_df, on="JobId", how="left")
            
    output_cols = [
        "JobId",
        "Job_json",
        "ScheduledOn_decentralized",
        "ScheduledOn_centralized",
        "StartTime_decentralized",
        "start_time_abs_diff",
        "StartTime_centralized",
        "Bids_decentralized",
        "Bids_centralized",
        "top_bid_decentralized",
        "top_bid_centralized",
        "top_bid_match",
        "num_unique_bids_in_both",
        "num_different_bids_in_both",
        "variance_top2_bids_decentralized",
        "variance_top2_bids_centralized",
        "is_same_bid_order",
        # "FinalStatus_decentralized",
        # "FinalStatus_centralized",
        "site_mismatch",
        "start_time_mismatch",
        "difference_reason",
    ]
    output_cols = [c for c in output_cols if c in merged.columns]

    diffs = merged[merged["different_allocation"]].copy().sort_values("JobId")
    matches = merged[merged["same_allocation"]].copy().sort_values("JobId")
    return diffs[output_cols], matches[output_cols]


def discover_csv_pairs(results_dir: Path, centralized_dir: Path) -> List[Tuple[Path, Path]]:
    pairs: List[Tuple[Path, Path]] = []
    for dec_csv in sorted(results_dir.glob("*.csv")):
        cen_csv = centralized_dir / dec_csv.name
        if cen_csv.exists():
            pairs.append((dec_csv, cen_csv))
    return pairs


def run_single_comparison(
    dec_path: Path,
    cen_path: Path,
    diff_out_path: Path,
    match_out_path: Path,
    start_time_tolerance: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    diffs, matches = compare_allocations(
        dec_path,
        cen_path,
        start_time_tolerance=start_time_tolerance,
    )
    diff_out_path.parent.mkdir(parents=True, exist_ok=True)
    match_out_path.parent.mkdir(parents=True, exist_ok=True)
    diffs.to_csv(diff_out_path, index=False)
    matches.to_csv(match_out_path, index=False)

    job_ids = diffs["JobId"].tolist() if "JobId" in diffs.columns else []
    match_job_ids = matches["JobId"].tolist() if "JobId" in matches.columns else []
    print(f"Mismatched allocations: {len(diffs)}")
    print(f"Job IDs: {job_ids}")
    print(f"Saved mismatches: {diff_out_path}")
    print(f"Matched allocations: {len(matches)}")
    print(f"Matched Job IDs: {match_job_ids}")
    print(f"Saved matches: {match_out_path}")
    return diffs, matches


def run_batch_comparison(
    results_dir: Path,
    centralized_dir: Path,
    output_dir: Path,
    start_time_tolerance: float,
) -> None:
    pairs = discover_csv_pairs(results_dir, centralized_dir)
    if not pairs:
        raise SystemExit(
            f"No matching CSV pairs found between {results_dir} and {centralized_dir}"
        )

    diff_output_dir = output_dir / "differences"
    match_output_dir = output_dir / "matches"

    summary_rows = []
    match_summary_rows = []
    all_diffs_parts = []
    all_matches_parts = []

    for dec_path, cen_path in pairs:
        workload_name = dec_path.stem
        # bursty_high_stress_large_long_54_rho0.9_EmbeddingBidding --> workload json data_generation/data/bursty_high_stress_large_long_54_rho0.9.json
        workload_name_prefix = "_".join(workload_name.split("_")[:-1])
        workload_json = Path("data_generation/data") / f"{workload_name_prefix}.json"
        # print(f"\nComparing workload: {workload_json}")
        diff_out_path = diff_output_dir / f"allocation_diff_{workload_name}.csv"
        match_out_path = match_output_dir / f"allocation_match_{workload_name}.csv"
        diffs, matches = compare_allocations(
            dec_path,
            cen_path,
            start_time_tolerance=start_time_tolerance,
            workload_json=workload_json,
        )

        diff_out_path.parent.mkdir(parents=True, exist_ok=True)
        match_out_path.parent.mkdir(parents=True, exist_ok=True)
        diffs.to_csv(diff_out_path, index=False)
        matches.to_csv(match_out_path, index=False)

        job_ids = diffs["JobId"].tolist() if "JobId" in diffs.columns else []
        match_job_ids = matches["JobId"].tolist() if "JobId" in matches.columns else []
        print(
            f"[{workload_name}] mismatches={len(diffs)} -> {diff_out_path} | "
            f"matches={len(matches)} -> {match_out_path}"
        )

        summary_rows.append(
            {
                "workload": workload_name,
                "decentralized_csv": str(dec_path),
                "centralized_csv": str(cen_path),
                "num_mismatched_jobs": len(diffs),
                "job_ids": ",".join(map(str, job_ids)),
                "output_csv": str(diff_out_path),
            }
        )
        match_summary_rows.append(
            {
                "workload": workload_name,
                "decentralized_csv": str(dec_path),
                "centralized_csv": str(cen_path),
                "num_matched_jobs": len(matches),
                "job_ids": ",".join(map(str, match_job_ids)),
                "output_csv": str(match_out_path),
            }
        )

        if not diffs.empty:
            with_workload = diffs.copy()
            with_workload.insert(0, "workload", workload_name)
            all_diffs_parts.append(with_workload)
        if not matches.empty:
            with_workload = matches.copy()
            with_workload.insert(0, "workload", workload_name)
            all_matches_parts.append(with_workload)

    summary_df = pd.DataFrame(summary_rows).sort_values("workload")
    summary_path = diff_output_dir / "allocation_diff_summary.csv"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(summary_path, index=False)

    match_summary_df = pd.DataFrame(match_summary_rows).sort_values("workload")
    match_summary_path = match_output_dir / "allocation_match_summary.csv"
    match_summary_path.parent.mkdir(parents=True, exist_ok=True)
    match_summary_df.to_csv(match_summary_path, index=False)

    if all_diffs_parts:
        all_diffs_df = pd.concat(all_diffs_parts, ignore_index=True)
    else:
        all_diffs_df = pd.DataFrame(
            columns=[
                "JobId",
                "Job_json",
                "ScheduledOn_decentralized",
                "ScheduledOn_centralized",
                "StartTime_decentralized",
                "start_time_abs_diff",
                "StartTime_centralized",
                "Bids_decentralized",
                "Bids_centralized",
                "top_bid_decentralized",
                "top_bid_centralized",
                "top_bid_match",
                "num_unique_bids_in_both",
                "num_different_bids_in_both",
                "variance_top2_bids_decentralized",
                "variance_top2_bids_centralized",
                "is_same_bid_order",
                # "FinalStatus_decentralized",
                # "FinalStatus_centralized",
                "site_mismatch",
                "start_time_mismatch",
                "difference_reason",
        ]
        )
    all_diffs_path = diff_output_dir / "allocation_diff_all_mismatches.csv"
    # all_diffs_df.to_csv(all_diffs_path, index=False)

    if all_matches_parts:
        all_matches_df = pd.concat(all_matches_parts, ignore_index=True)
    else:
        all_matches_df = pd.DataFrame(
            columns=[
                "JobId",
                "Job_json",
                "ScheduledOn_decentralized",
                "ScheduledOn_centralized",
                "StartTime_decentralized",
                "start_time_abs_diff",
                "StartTime_centralized",
                "Bids_decentralized",
                "Bids_centralized",
                "top_bid_decentralized",
                "top_bid_centralized",
                "top_bid_match",
                "num_unique_bids_in_both",
                "num_different_bids_in_both",
                "variance_top2_bids_decentralized",
                "variance_top2_bids_centralized",
                "is_same_bid_order",
                # "FinalStatus_decentralized",
                # "FinalStatus_centralized",
                "site_mismatch",
                "start_time_mismatch",
                "difference_reason",
        ]
        )
    all_matches_path = match_output_dir / "allocation_match_all_matches.csv"
    # all_matches_df.to_csv(all_matches_path, index=False)

    print("\nBatch comparison complete")
    print(f"Matched workload pairs: {len(pairs)}")
    print(f"Total mismatched jobs: {int(summary_df['num_mismatched_jobs'].sum())}")
    print(f"Total matched jobs: {int(match_summary_df['num_matched_jobs'].sum())}")
    print(f"Mismatch summary saved: {summary_path}")
    print(f"All mismatches saved: {all_diffs_path}")
    print(f"Match summary saved: {match_summary_path}")
    print(f"All matches saved: {all_matches_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare centralized vs decentralized job allocations (single pair or batch mode)."
    )
    parser.add_argument(
        "--decentralized-csv",
        required=False,
        help="Path to decentralized CSV in results/",
    )
    parser.add_argument(
        "--centralized-csv",
        required=False,
        help="Path to centralized CSV in results/centralized/",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Output CSV path. Default: results/comparison/allocation_diff_<workload>.csv",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch compare all matching CSVs in results/ and results/centralized/",
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Decentralized results directory for batch mode (default: results)",
    )
    parser.add_argument(
        "--centralized-dir",
        default="results/centralized",
        help="Centralized results directory for batch mode (default: results/centralized)",
    )
    parser.add_argument(
        "--output-dir",
        default="results/comparison",
        help="Base output directory. Files are saved under <output-dir>/differences and <output-dir>/matches",
    )
    parser.add_argument(
        "--start-time-tolerance",
        type=float,
        default=1.0,
        help="Absolute tolerance for start-time equality in seconds (default: 1.0)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.batch:
        results_dir = Path(args.results_dir)
        centralized_dir = Path(args.centralized_dir)
        output_dir = Path(args.output_dir)
       

        if not results_dir.exists():
            raise SystemExit(f"Results directory not found: {results_dir}")
        if not centralized_dir.exists():
            raise SystemExit(f"Centralized results directory not found: {centralized_dir}")

        run_batch_comparison(
            results_dir,
            centralized_dir,
            output_dir,
            start_time_tolerance=args.start_time_tolerance,
        )
        return

    if not args.decentralized_csv or not args.centralized_csv:
        raise SystemExit(
            "Single mode requires both --decentralized-csv and --centralized-csv. "
            "Or use --batch."
        )

    dec_path = Path(args.decentralized_csv)
    cen_path = Path(args.centralized_csv)

    if not dec_path.exists():
        raise SystemExit(f"Decentralized CSV not found: {dec_path}")
    if not cen_path.exists():
        raise SystemExit(f"Centralized CSV not found: {cen_path}")

    workload_name = dec_path.stem
    print(f"Comparing workload: {workload_name}")
    if args.output_csv:
        diff_out_path = Path(args.output_csv)
        match_out_path = derive_match_output_path(diff_out_path)
    else:
        base_output_dir = Path(args.output_dir)
        diff_out_path = base_output_dir / "differences" / f"allocation_diff_{workload_name}.csv"
        match_out_path = base_output_dir / "matches" / f"allocation_match_{workload_name}.csv"

    run_single_comparison(
        dec_path,
        cen_path,
        diff_out_path,
        match_out_path,
        start_time_tolerance=args.start_time_tolerance,
    )


if __name__ == "__main__":
    main()
