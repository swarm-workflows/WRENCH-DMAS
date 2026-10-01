#!/usr/bin/env python3

from __future__ import annotations

import argparse
from itertools import permutations
from pathlib import Path
from typing import Dict, List
import pandas as pd

"""
How to run: python confirm_cen_dec_bid_order.py

Columns:
eligible_rows = number of rows that were actually used to infer the bid order.
validation = How confident are we that the inferred slot order is correct? 
           perfect = if all eligible rows match the inferred order
           partial_X/Y = if X out of Y eligible rows match the inferred order
           unsolved = if no eligible rows to validate against

A row is eligible if:
-It has exactly 6 bids.
-All 6 bids are different (no ties).
"""
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


def infer_bid_order(csv_path: Path, bid_len: int = 6) -> dict:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return {
            "bid_order": "unresolved",
            "validation": "missing_or_empty",
            "validation_match": 0,
            "validation_total": 0,
            "eligible_rows": 0,
        }

    df = pd.read_csv(csv_path, usecols=lambda c: c in {"ScheduledOn", "Bids"})
    if "ScheduledOn" not in df.columns or "Bids" not in df.columns:
        return {
            "bid_order": "unresolved",
            "validation": "missing_columns",
            "validation_match": 0,
            "validation_total": 0,
            "eligible_rows": 0,
        }

    # unique systems --> ['Aurora', 'Crux', 'Frontier', 'Perlmutter-Phase-1', 'Perlmutter-Phase-2']
    systems = sorted(df["ScheduledOn"].dropna().astype(str).str.strip().unique().tolist())
    # print(f"Found {len(systems)} unique systems in {csv_path}: {systems}")
    parsed = df["Bids"].apply(parse_bids)
   
    # Use only rows with full-length unique bid vectors for robust mapping votes.
    eligible = df[(parsed.apply(len) == bid_len)].copy()
    # print(f"Found {(eligible)} eligible rows with full-length bids in {csv_path}")
    eligible["_bids"] = parsed[parsed.apply(len) == bid_len]
    
    eligible = eligible[eligible["_bids"].apply(lambda x: len(set(x)) == bid_len)]
    
    if eligible.empty or not systems:
        return {
            "bid_order": "unresolved",
            "validation": "insufficient_unique_rows",
            "validation_match": 0,
            "validation_total": 0,
            "eligible_rows": int(len(eligible)),
        }

    # ---> add here
    slot_votes: Dict[int, Dict[str, int]] = {i: {} for i in range(bid_len)}

    for _, row in eligible.iterrows():
        bids = row["_bids"]
        winner = str(row["ScheduledOn"]).strip()

        max_idx = int(max(range(len(bids)), key=lambda i: bids[i]))

        slot_votes[max_idx][winner] = slot_votes[max_idx].get(winner, 0) + 1

    inferred_slots = []
    for i in range(bid_len):
        if slot_votes[i]:
            best_system = max(slot_votes[i], key=slot_votes[i].get)
            inferred_slots.append(best_system)
        else:
            inferred_slots.append("?")

    bid_order = ":".join(inferred_slots)

    validation_match = 0
    validation_total = 0

    for _, row in eligible.iterrows():
        bids = row["_bids"]
        winner = str(row["ScheduledOn"]).strip()
        max_idx = int(max(range(len(bids)), key=lambda i: bids[i]))

        if inferred_slots[max_idx] != "?":
            validation_total += 1
            if inferred_slots[max_idx] == winner:
                validation_match += 1

    if validation_total == 0:
        validation = "unresolved"
    elif validation_match == validation_total:
        validation = "perfect"
    else:
        validation = f"partial_{validation_match}/{validation_total}"

    # ----> tailor to the following code

    return {
        "bid_order": bid_order,
        "validation": validation,
        "validation_match": int(validation_match),
        "validation_total": int(validation_total),
        "eligible_rows": int(len(eligible)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Infer and validate Bids slot order for decentralized vs centralized CSV pairs, "
            "then export a summary CSV."
        )
    )
    parser.add_argument("--results-dir", default="results", help="Path to decentralized results directory")
    parser.add_argument(
        "--centralized-dir",
        default="results/centralized",
        help="Path to centralized results directory",
    )
    parser.add_argument(
        "--output-csv",
        default="results/bid_order_confirmation.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--details-csv",
        default="results/bid_order_confirmation_details.csv",
        help="Detailed output CSV path with validation diagnostics",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    centralized_dir = Path(args.centralized_dir)
    output_csv = Path(args.output_csv)
    details_csv = Path(args.details_csv)

    if not results_dir.exists():
        raise SystemExit(f"Results directory not found: {results_dir}")
    if not centralized_dir.exists():
        raise SystemExit(f"Centralized directory not found: {centralized_dir}")

    rows = []
    for dec_path in sorted(results_dir.glob("*.csv")):
        cen_path = centralized_dir / dec_path.name
        if not cen_path.exists():
            continue

        dec_info = infer_bid_order(dec_path)
        cen_info = infer_bid_order(cen_path)

        rows.append(
            {
                "input_csv_file": dec_path.name,
                "dec_bid_order": dec_info["bid_order"],
                "cen_bid_order": cen_info["bid_order"],
                "dec_validation": dec_info["validation"],
                "cen_validation": cen_info["validation"],
                "dec_eligible_rows": dec_info["eligible_rows"],
                "cen_eligible_rows": cen_info["eligible_rows"],
            }
        )

    if not rows:
        raise SystemExit("No decentralized/centralized CSV pairs found.")

    out_df = pd.DataFrame(rows).sort_values("input_csv_file")
    compact_df = out_df[["input_csv_file", "dec_bid_order", "cen_bid_order"]].copy()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    compact_df.to_csv(output_csv, index=False)
    details_csv.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(details_csv, index=False)

    print(f"Wrote {len(compact_df)} rows to {output_csv}")
    print(f"Wrote detailed diagnostics to {details_csv}")


if __name__ == "__main__":
    main()
