#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

RESULTS_DIR="$PROJECT_ROOT/results"
AGGREGATED_FILE="$RESULTS_DIR/aggregated_metrics.csv"
PLOT_AGGREGATED_FILE="$RESULTS_DIR/aggregated_metrics_for_plots.csv"

BIDDING_SCRIPT="$PROJECT_ROOT/data_analysis/biddingComparison.Rscript"
MODE_SCRIPT="$PROJECT_ROOT/data_analysis/compareToCentralized.Rscript"

PLOTS_DIR="$PROJECT_ROOT/plots/comparison"
mkdir -p "$PLOTS_DIR"

GANTT_SCRIPT="$PROJECT_ROOT/data_analysis/compare_gantt.py"
GANTT_DIR="$PLOTS_DIR/gantt"
mkdir -p "$GANTT_DIR"

CENTRALIZED_DIR="$RESULTS_DIR/centralized"

if [ ! -f "$AGGREGATED_FILE" ]; then
    echo "Error: $AGGREGATED_FILE not found"
    exit 1
fi

echo "Processing aggregated metrics: $AGGREGATED_FILE"

# Create a plotting-safe version of aggregated_metrics.csv.

FILTER_STATS="$RESULTS_DIR/.plot_filter_stats.txt"

python - "$AGGREGATED_FILE" "$PLOT_AGGREGATED_FILE" "$FILTER_STATS" <<'PY'
import sys
import pandas as pd

src, dst, stats_path = sys.argv[1], sys.argv[2], sys.argv[3]

df = pd.read_csv(src)

if "total_jobs" not in df.columns:
    raise SystemExit("Error: aggregated_metrics.csv is missing required column: total_jobs")

df["total_jobs"] = pd.to_numeric(df["total_jobs"], errors="coerce").fillna(0)

plot_df = df[df["total_jobs"] > 0].copy()

plot_df.to_csv(dst, index=False)

with open(stats_path, "w") as f:
    f.write(f"{len(df)} {len(plot_df)}\n")
PY

read TOTAL_ROWS PLOT_ROWS < "$FILTER_STATS"
rm -f "$FILTER_STATS"

echo "Using $PLOT_ROWS of $TOTAL_ROWS aggregate rows for plotting."
echo "Plot-safe aggregate file: $PLOT_AGGREGATED_FILE"

if [ "$PLOT_ROWS" -eq 0 ]; then
    echo "Error: no non-empty result rows found for plotting."
    exit 1
fi

echo "Generating bidding method comparisons..."
Rscript "$BIDDING_SCRIPT" "$PLOT_AGGREGATED_FILE" "$PLOTS_DIR"

CENTRALIZED_ROWS=$(python - "$PLOT_AGGREGATED_FILE" <<'PY'
import sys
import pandas as pd

df = pd.read_csv(sys.argv[1])

if "mode" not in df.columns:
    print(0)
else:
    print((df["mode"] == "centralized").sum())
PY
)

if [ -d "$CENTRALIZED_DIR" ] && [ "$CENTRALIZED_ROWS" -gt 0 ]; then
    echo "Generating centralized vs decentralized comparisons..."
    Rscript "$MODE_SCRIPT" "$PLOT_AGGREGATED_FILE" "$PLOTS_DIR"
else
    echo "Skipping centralized comparison."
    echo "Reason: no usable centralized rows found in $PLOT_AGGREGATED_FILE"
fi

echo "Generating centralized vs decentralized Gantt comparisons..."
python "$GANTT_SCRIPT" \
    --results-dir "$RESULTS_DIR" \
    --output-dir "$GANTT_DIR"

echo "All comparison plots saved under $PLOTS_DIR"