"""
Compute mean turnaround time by (strategy × arrival pattern) and
(strategy × workload type), then report the percentage gaps cited in
the RQ3 paragraph:

  Arrival pattern ranking and gaps (Embedding vs Heuristic, LLM vs Embedding)
  Workload type ranking and gaps   (Embedding vs Heuristic, LLM vs Heuristic)

Methodology: per-scenario mean turnaround (hours) across completed jobs,
then averaged across scenarios sharing the same (strategy, dimension) cell.
Percentage gap: (worse - better) / better * 100  (positive = worse is slower).
"""

import csv
import glob
import os
import statistics
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")

STRATEGY_MAP = {
    "HeuristicBidding": "Heuristic",
    "EmbeddingBidding": "Embedding",
    "LLMBidding":       "LLM",
}

WORKLOAD_MAP = {
    "small_short": "Small/Short",
    "large_long":  "Large/Long",
    "mixed":       "Mixed",
}

ARRIVAL_MAP = {
    "business":   "Business",
    "bursty_low": "Bursty Low",
    "bursty_high":"Bursty High",
}

# Accumulate per-scenario means into cells
# cell key: (strategy, dimension_value)
cells_arr  = defaultdict(list)   # keyed by (strategy, arrival)
cells_wtype = defaultdict(list)  # keyed by (strategy, workload_type)

for csv_file in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.csv"))):
    if "aggregated_metrics" in csv_file:
        continue
    bname = os.path.basename(csv_file).replace(".csv", "")

    strat = next((v for k, v in STRATEGY_MAP.items() if k in bname), None)
    wtype = next((v for k, v in WORKLOAD_MAP.items() if k in bname), None)
    arr   = next((v for k, v in ARRIVAL_MAP.items()  if k in bname), None)
    if strat is None or wtype is None or arr is None:
        continue

    tas = []
    with open(csv_file) as f:
        for row in csv.DictReader(f):
            if row["FinalStatus"] != "COMPLETED":
                continue
            sub = float(row["SubmissionTime"])
            end = float(row["EndTime"])
            tas.append((end - sub) / 3600)

    if tas:
        mean_ta = statistics.mean(tas)
        cells_arr [(strat, arr)].append(mean_ta)
        cells_wtype[(strat, wtype)].append(mean_ta)

def mean_of(cells, strat, dim):
    vals = cells.get((strat, dim), [])
    return statistics.mean(vals) if vals else float("nan")

def gap(a, b):
    """Percentage by which b exceeds a: (b-a)/a*100. Positive = b is slower."""
    return (b - a) / a * 100

STRATS = ["Heuristic", "Embedding", "LLM"]
ARRIVALS = ["Business", "Bursty Low", "Bursty High"]
WTYPES   = ["Small/Short", "Mixed", "Large/Long"]

# ── By arrival pattern ────────────────────────────────────────────────────────
print("=== Mean turnaround by arrival pattern (hours) ===")
print(f"{'':15}", end="")
for s in STRATS:
    print(f"  {s:>10}", end="")
print()
for arr in ARRIVALS:
    print(f"{arr:15}", end="")
    for s in STRATS:
        print(f"  {mean_of(cells_arr, s, arr):>10.3f}", end="")
    print()

print()
print("=== Gaps by arrival pattern ===")
print(f"{'':15}  {'Emb vs Heu':>12}  {'LLM vs Emb':>12}  {'LLM vs Heu':>12}")
for arr in ARRIVALS:
    h = mean_of(cells_arr, "Heuristic", arr)
    e = mean_of(cells_arr, "Embedding", arr)
    l = mean_of(cells_arr, "LLM",       arr)
    print(f"{arr:15}  {gap(h,e):>+11.1f}%  {gap(e,l):>+11.1f}%  {gap(h,l):>+11.1f}%")

# ── By workload type ──────────────────────────────────────────────────────────
print()
print("=== Mean turnaround by workload type (hours) ===")
print(f"{'':15}", end="")
for s in STRATS:
    print(f"  {s:>10}", end="")
print()
for wt in WTYPES:
    print(f"{wt:15}", end="")
    for s in STRATS:
        print(f"  {mean_of(cells_wtype, s, wt):>10.3f}", end="")
    print()

print()
print("=== Gaps by workload type ===")
print(f"{'':15}  {'Emb vs Heu':>12}  {'LLM vs Emb':>12}  {'LLM vs Heu':>12}")
for wt in WTYPES:
    h = mean_of(cells_wtype, "Heuristic", wt)
    e = mean_of(cells_wtype, "Embedding", wt)
    l = mean_of(cells_wtype, "LLM",       wt)
    print(f"{wt:15}  {gap(h,e):>+11.1f}%  {gap(e,l):>+11.1f}%  {gap(h,l):>+11.1f}%")
