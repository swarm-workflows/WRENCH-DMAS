"""
Compute median(mean_wait / mean_turnaround) per strategy.

Metric: for each scenario CSV, compute mean waiting time and mean turnaround
time across completed jobs, take their ratio, then report the median of that
ratio across all scenarios for each strategy.

Used in the RQ2 paragraph:
  "wait drops from 61% (Pure Local) to 2% (Embedding), 5% (Heuristic), 7% (LLM)"
"""

import csv
import glob
import os
import statistics

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")

STRATEGIES = {
    "PureLocal":        "Pure Local",
    "HeuristicBidding": "Heuristic",
    "EmbeddingBidding": "Embedding",
    "LLMBidding":       "LLM",
}

ORDER = ["Pure Local", "Heuristic", "Embedding", "LLM"]

scenario_ratios = {label: [] for label in STRATEGIES.values()}

for csv_file in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.csv"))):
    if "aggregated_metrics" in csv_file:
        continue
    bname = os.path.basename(csv_file)
    strat = None
    for key, label in STRATEGIES.items():
        if key in bname:
            strat = label
            break
    if strat is None:
        continue

    waits, tas = [], []
    with open(csv_file) as f:
        for row in csv.DictReader(f):
            if row["FinalStatus"] != "COMPLETED":
                continue
            sub   = float(row["SubmissionTime"])
            start = float(row["StartTime"])
            end   = float(row["EndTime"])
            waits.append(start - sub)
            tas.append(end - sub)

    if waits:
        scenario_ratios[strat].append(statistics.mean(waits) / statistics.mean(tas))

print(f"{'Strategy':<16} {'Scenarios':>9} {'Median wait%':>13} {'Mean wait%':>11}")
print("-" * 52)
for label in ORDER:
    vals = scenario_ratios[label]
    if not vals:
        print(f"{label:<16} {'(no data)':>9}")
        continue
    med  = statistics.median(vals)
    mean = statistics.mean(vals)
    print(f"{label:<16} {len(vals):>9}     {med*100:>6.1f}%     {mean*100:>6.1f}%")
