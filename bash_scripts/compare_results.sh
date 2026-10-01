#!/bin/bash
set -eu

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

RESULTS_DIR="$PROJECT_ROOT/results"
AGGREGATED_FILE="$RESULTS_DIR/aggregated_metrics.csv"

BIDDING_SCRIPT="$PROJECT_ROOT/data_analysis/biddingComparison.Rscript"
MODE_SCRIPT="$PROJECT_ROOT/data_analysis/compareToCentralized.Rscript"

PLOTS_DIR="$PROJECT_ROOT/plots/comparison"
mkdir -p "$PLOTS_DIR"

GANTT_SCRIPT="$PROJECT_ROOT/data_analysis/compare_gantt.py"
GANTT_DIR="$PLOTS_DIR/gantt"
mkdir -p "$GANTT_DIR"

if [ ! -f "$AGGREGATED_FILE" ]; then
    echo "Error: $AGGREGATED_FILE not found"
    exit 1
fi

echo "Processing aggregated metrics: $AGGREGATED_FILE"

echo "Generating bidding method comparisons..."
Rscript "$BIDDING_SCRIPT" "$AGGREGATED_FILE" "$PLOTS_DIR"

CENTRALIZED_DIR="$RESULTS_DIR/centralized"

if [ -d "$CENTRALIZED_DIR" ] && [ -n "$(ls -A "$CENTRALIZED_DIR" 2>/dev/null)" ]; then
    echo "Generating centralized vs decentralized comparisons..."
    Rscript "$MODE_SCRIPT" "$AGGREGATED_FILE" "$PLOTS_DIR"
else
    echo "Skipping centralized comparison (no results found in $CENTRALIZED_DIR)"
fi

echo "Generating centralized vs decentralized Gantt comparisons..."
python "$GANTT_SCRIPT" \
    --results-dir "$RESULTS_DIR" \
    --output-dir "$GANTT_DIR"

echo "All comparison plots saved under $PLOTS_DIR"
