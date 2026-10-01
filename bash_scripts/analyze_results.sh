#!/bin/bash
set -eu
 
RHO_VALUES=("1.5" "0.9" )      # 

declare -A SCENARIO_NJOBS_RHO09=(
    ["small_short"]=2880
    ["mixed_80_20"]=251
    ["mixed_20_80"]=67
    ["large_long"]=54
)
declare -A SCENARIO_NJOBS_RHO15=(
    ["small_short"]=4800
    ["mixed_80_20"]=415
    ["mixed_20_80"]=112
    ["large_long"]=91
)

PY_ANALYZER="data_analysis/analyze_results.py"
R_ANALYZER="data_analysis/output_analysis.Rscript"

RESULT_DIRS=("results/centralized")     # "results"

# Workload files
DAYS=("business" "bursty_low_stress" "bursty_high_stress")       
TYPES=("large_long" "mixed_20_80" "mixed_80_20" "small_short" )       # "mixed_80_20". "small_short" 
METHODS=(
    # "HeuristicBidding"
    "EmbeddingBidding"
    # "LLMBidding"
    # "RandomBidding"
    # "PureLocal"
)

PLOTS_DIR="plots/individual"
PLOTS_DIR_CENTRALIZED="plots/centralized"

mkdir -p "$PLOTS_DIR" "$PLOTS_DIR_CENTRALIZED"


for rho in "${RHO_VALUES[@]}"; do
    for day in "${DAYS[@]}"; do
        for type in "${TYPES[@]}"; do

            if [ "$rho" = "0.9" ]; then
                num="${SCENARIO_NJOBS_RHO09[$type]}"
            elif [ "$rho" = "1.5" ]; then
                num="${SCENARIO_NJOBS_RHO15[$type]}"
            else
                echo "Unknown rho: $rho"
                exit 1
            fi

            workload_name="${day}_${type}_${num}_rho${rho}"

            for dir in "${RESULT_DIRS[@]}"; do
                for method in "${METHODS[@]}"; do
                    csv_file="$dir/${workload_name}_${method}.csv"

                    if [ -f "$csv_file" ]; then
                        base_name=$(basename "$csv_file" .csv)
                        echo "Analyzing $csv_file"

                        if [ "$dir" = "${RESULT_DIRS[0]}" ]; then
                            python "$PY_ANALYZER" \
                                --csv_file "$csv_file" \
                                --output-dir "$PLOTS_DIR" \
                                --metrics-dir "$dir" \
                                --skip-gantt

                            Rscript "$R_ANALYZER" \
                                "$csv_file" \
                                "$PLOTS_DIR/${base_name}_summary.pdf"
                        else
                            python "$PY_ANALYZER" \
                                --csv_file "$csv_file" \
                                --output-dir "$PLOTS_DIR_CENTRALIZED" \
                                --metrics-dir "$dir" \
                                --skip-gantt

                            Rscript "$R_ANALYZER" \
                                "$csv_file" \
                                "$PLOTS_DIR_CENTRALIZED/${base_name}_summary.pdf"
                        fi
                    else
                        echo "Skipping missing file: $csv_file"
                    fi
                done
            done
        done
    done
done
