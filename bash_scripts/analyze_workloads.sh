#!/bin/bash
set -euo pipefail

WORKLOAD_DIR="data_generation/data"
WORKLOAD_VISUALIZER="data_analysis/visualize_workload.py"
PLOTS_DIR="plots/workload"

mkdir -p "$PLOTS_DIR"

RHO_VALUES=("0.9" "1.5")

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

DAYS=("business" "bursty_low_stress" "bursty_high_stress")
TYPES=("small_short" "large_long" "mixed_80_20" "mixed_20_80")

total=0
completed=0
failed=0
missing=0
 
for rho in "${RHO_VALUES[@]}"; do
    for day in "${DAYS[@]}"; do
        for type in "${TYPES[@]}"; do
            total=$((total + 1))

            if [ "$rho" = "0.9" ]; then
                num_jobs="${SCENARIO_NJOBS_RHO09[$type]}"
            elif [ "$rho" = "1.5" ]; then
                num_jobs="${SCENARIO_NJOBS_RHO15[$type]}"
            else
                echo "Unknown rho: $rho"
                exit 1
            fi

            workload_name="${day}_${type}_${num_jobs}_rho${rho}"
            workload_file="$WORKLOAD_DIR/${workload_name}.json"
            output_file="$PLOTS_DIR/${workload_name}.png"

            if [[ -f "$workload_file" ]]; then
                echo "Generating plot: $output_file"

                if python "$WORKLOAD_VISUALIZER" \
                    --input "$workload_file" \
                    --output "$output_file"; then
                    completed=$((completed + 1))
                else
                    failed=$((failed + 1))
                    echo "Failed workload: $workload_file" >&2
                fi
            else
                echo "Skipping missing workload: $workload_file"
                missing=$((missing + 1))
            fi
        done
    done
done

echo "Workload visualization run complete."
echo "Total scenarios: $total"
echo "Completed: $completed"
echo "Failed: $failed"
echo "Missing inputs: $missing"

if [[ $failed -gt 0 ]]; then
    exit 1
fi
