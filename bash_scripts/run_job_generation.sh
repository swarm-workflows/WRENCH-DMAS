#!/bin/bash
# run_job_generation.sh
# Generates synthetic workloads for all combinations of arrival_pattern, scenario, and sfactor.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
GENERATOR="$REPO_ROOT/data_generation/job_generation.py"

ARRIVAL_PATTERNS=("busy" "bursty_low_stress" "bursty_high_stress")
SCENARIOS=("homogeneous_short" "only_large_long" "mixed_80_20" "mixed_20_80")
SFACTORS=(32 16 8 4 2 1)

total=$(( ${#ARRIVAL_PATTERNS[@]} * ${#SCENARIOS[@]} * ${#SFACTORS[@]} ))
done_count=0

echo "=== Job Generation ==="
echo "Combinations to generate: $total"
echo ""

for arrival in "${ARRIVAL_PATTERNS[@]}"; do
    for scenario in "${SCENARIOS[@]}"; do
        for sfactor in "${SFACTORS[@]}"; do
            done_count=$(( done_count + 1 ))
            echo "[$done_count/$total] arrival=${arrival}  scenario=${scenario}  sfactor=${sfactor}"
            if [[ "$arrival" == "busy" ]]; then
                python "$GENERATOR" \
                    --arrival_pattern "$arrival" \
                    --scenario "$scenario" \
                    --sfactor "$sfactor"
            else
                python "$GENERATOR" \
                    --arrival_pattern "$arrival" \
                    --scenario "$scenario" \
                    --sfactor "$sfactor" \
                    --sync-sites
            fi
            echo ""
        done
    done
done

echo "Done. All $total workload files written to data_generation/data/"