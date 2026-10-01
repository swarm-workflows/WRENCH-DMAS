#!/bin/bash
set -euo pipefail

EXEC_FILE=./build/swarm_dmas
WRENCH_ARGS="--wrench-commport-pool-size=80000"     # --cfg=precision/work-amount:1e-12

# Number of concurrent runs
MAX_JOBS=8
SLEEP_BETWEEN_RUNS=60   # seconds

declare -A SCENARIO_NJOBS_RHO_15=(
    ["mixed_80_20"]=415
    ["mixed_20_80"]=112
    ["large_long"]=91
    ["small_short"]=4800
)
declare -A SCENARIO_NJOBS_RHO_09=(
    ["mixed_80_20"]=251
    ["mixed_20_80"]=67
    ["large_long"]=54
    ["small_short"]=2880
)

DAYS=("business" "bursty_low_stress" "bursty_high_stress")           #  "bursty_low_stress" "bursty_high_stress"
TYPES=("mixed_20_80" "large_long" "small_short" "mixed_80_20")       #    "mixed_80_20"  "mixed_20_80" "large_long" "small_short"
RHO_VALUES=(1.5 0.9)            #   1.5 0.9


# Build workload list with per-scenario job counts
WORKLOADS=()

for rho in "${RHO_VALUES[@]}"; do
    if [[ "$rho" == "1.5" ]]; then
            declare -n SCENARIO_NJOBS=SCENARIO_NJOBS_RHO_15
        else
            declare -n SCENARIO_NJOBS=SCENARIO_NJOBS_RHO_09
        fi

    for day in "${DAYS[@]}"; do
        for type in "${TYPES[@]}"; do
            num="${SCENARIO_NJOBS[$type]}"
            WORKLOADS+=("${rho}|data_generation/data/${day}_${type}_${num}_rho${rho}.json")
        done
    done
done

# Directories & templates
DEC_TEMPLATE=experiments/test_decentralized.json
CENT_TEMPLATE=experiments/test_centralized.json
RESULT_DIR=results
RESULT_DIR_CENTRALIZED=results/centralized

mkdir -p "$RESULT_DIR"
mkdir -p "$RESULT_DIR_CENTRALIZED"

# Bidding strategies to evaluate
PYTHON_BIDDERS=(
    "python_scripts/HeuristicBidding.py"
    # "python_scripts/EmbeddingBidding.py"
    # "python_scripts/llm_claude_bidder.py"
)

BASELINE_POLICIES=(
    # "RandomBidding"
    "PureLocal"
)

python_bidder_label() {
    local bidder="$1"
    local bidder_name

    bidder_name=$(basename "$bidder" .py)
    case "$bidder_name" in
        llm_claude_bidder)
            echo "LLMBidding"
            ;;
        *)
            echo "$bidder_name"
            ;;
    esac
}


run_decentralized_python() {
    local workload="$1"
    local platform_file="$2"
    local bidder="$3"
    local workload_name="$4"
    local bidder_name output_file temp_json

    bidder_name=$(python_bidder_label "$bidder")
    output_file="$RESULT_DIR/${workload_name}_${bidder_name}.csv"
    temp_json=$(mktemp /tmp/swarm_dec_py_XXXXXX.json)

    jq \
        --arg workload "$workload" \
        --arg bidder "$bidder" \
        --arg platform "$platform_file" \
        '
        .workload = $workload |
        .platform = $platform |
        .decentralized_policy = "PythonBidding" |
        .decentralized_bidder = $bidder
        ' "$DEC_TEMPLATE" > "$temp_json"

    echo "Running DECENTRALIZED - $bidder_name on $workload_name"
    LLM_WORKLOAD_NAME="$workload_name" \
    LLM_LOG_DIR="logs/llm_bidding" \
    "$EXEC_FILE" "$temp_json" $WRENCH_ARGS > "$output_file"
    rm -f "$temp_json"
}


run_decentralized_baseline() {
    local workload="$1"
    local platform_file="$2"
    local policy="$3"
    local workload_name="$4"
    local output_file temp_json

    output_file="$RESULT_DIR/${workload_name}_${policy}.csv"
    temp_json=$(mktemp /tmp/swarm_dec_base_XXXXXX.json)

    jq \
        --arg workload "$workload" \
        --arg policy "$policy" \
        --arg platform "$platform_file" \
        '
        .workload = $workload |
        .platform = $platform |
        .decentralized_policy = $policy |
        del(.decentralized_bidder)
        ' "$DEC_TEMPLATE" > "$temp_json"

    echo "Running DECENTRALIZED - $policy on $workload_name"
    "$EXEC_FILE" "$temp_json" $WRENCH_ARGS > "$output_file"
    rm -f "$temp_json"
}


run_centralized() {
    local workload="$1"
    local platform_file="$2"
    local bidder="$3"
    local workload_name="$4"
    local bidder_name output_file temp_json

    bidder_name=$(python_bidder_label "$bidder")
    output_file="$RESULT_DIR_CENTRALIZED/${workload_name}_${bidder_name}.csv"
    temp_json=$(mktemp /tmp/swarm_cent_XXXXXX.json)

    jq \
        --arg workload "$workload" \
        --arg platform "$platform_file" \
        --arg bidder "$bidder" \
        '
        .workload = $workload |
        .platform = $platform |
        .centralized_submission = true |
        .centralized_policy = $bidder |
        del(.centralized_bidder)
        ' "$CENT_TEMPLATE" > "$temp_json"

    echo "Running CENTRALIZED - $bidder_name on $workload_name"
    "$EXEC_FILE" "$temp_json" $WRENCH_ARGS > "$output_file"
    rm -f "$temp_json"
}


throttle_jobs() {
    while [ "$(jobs -rp | wc -l)" -ge "$MAX_JOBS" ]; do
        wait -n || true
    done
}


# ==============
# Main loop
# ==============
platform_file="platforms/AmSC.xml"

for entry in "${WORKLOADS[@]}"; do
    rho="${entry%%|*}"
    workload="${entry#*|}"
    workload_name=$(basename "${workload}" .json)

    # Verify workload file exists before launching
    if [[ ! -f "$workload" ]]; then
        echo "WARNING: Workload file not found, skipping: $workload"
        continue
    fi

    echo "==============================================="
    echo "Workload: $workload_name"
    echo "Using platform: $platform_file"
    echo "==============================================="

    # for bidder in "${PYTHON_BIDDERS[@]}"; do
    #     throttle_jobs
    #     run_decentralized_python "$workload" "$platform_file" "$bidder" "$workload_name" &

    #     # wait -n || true

    #     # echo "Sleeping ${SLEEP_BETWEEN_RUNS}s before next run..."
    #     # sleep "$SLEEP_BETWEEN_RUNS"
    # done

    # for policy in "${BASELINE_POLICIES[@]}"; do
    #     throttle_jobs
    #     run_decentralized_baseline "$workload" "$platform_file" "$policy" "$workload_name" &
    # done

    for bidder in "${PYTHON_BIDDERS[@]}"; do
        throttle_jobs
        run_centralized "$workload" "$platform_file" "$bidder" "$workload_name" &
    done

    # throttle_jobs
    # # run_centralized "$workload" "$platform_file" "HeuristicBidding" "$workload_name" &
    # run_centralized "$workload" "$platform_file" "EmbeddingBidding" "$workload_name" &
done

wait || true
echo "All experiments completed."
