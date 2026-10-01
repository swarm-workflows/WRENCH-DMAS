#!/bin/bash
set -e
EXEC_FILE=./build/swarm_dmas
WRENCH_ARGS="--wrench-commport-pool-size=80000"


# Workload construction
WORKLOADS=()
DAYS=("busy" "bursty_low_stress" "bursty_high_stress")       # 
TYPES=("homogeneous_short" "only_large_long" "mixed_80_20" "mixed_20_80")     # 
NUM_JOBS=(1000)
R_VALUES=(32)

for day in "${DAYS[@]}"; do
    for i in "${!NUM_JOBS[@]}"; do
        num="${NUM_JOBS[$i]}"
        r="${R_VALUES[$i]}"
        for type in "${TYPES[@]}"; do
            WORKLOADS+=("data_generation/data/${day}_${type}_${num}_r${r}.json")
        done
    done
done


# Directories & templates
DEC_TEMPLATE=experiments/test_decentralized.json
CENT_TEMPLATE=experiments/test_centralized.json
RESULT_DIR=results/sfactor_${R_VALUES[0]}
RESULT_DIR_CENTRALIZED=results/sfactor_${R_VALUES[0]}/centralized

mkdir -p "$RESULT_DIR"
mkdir -p "$RESULT_DIR_CENTRALIZED"


# Policies
PYTHON_BIDDERS=(
    # "python_scripts/HeuristicBidding.py"
    "python_scripts/EmbeddingBidding.py"
)
BASELINE_POLICIES=(
    # "RandomBidding"
    # "PureLocal"
)

# --------------------------------------------------
# Main loop
# --------------------------------------------------
for workload in "${WORKLOADS[@]}"; do

    workload_name=$(basename "${workload}" .json)
    if [[ $workload =~ _r([0-9]+)\.json$ ]]; then
        r_value="${BASH_REMATCH[1]}"
    else
        echo "ERROR: Could not extract r value from $workload"
        exit 1
    fi

    platform_file="platforms/AmSC_scaled_down_${r_value}.xml"
    echo "==============================================="
    echo "Workload: $workload_name"
    echo "Using platform: $platform_file"
    echo "==============================================="

    # --------------------------------------------------
    # DECENTRALIZED - Python bidders
    # --------------------------------------------------

    for bidder in "${PYTHON_BIDDERS[@]}"; do

        bidder_name=$(basename "$bidder" .py)
        output_file="$RESULT_DIR/${workload_name}_${bidder_name}.csv"
        temp_json="temp_config.json"

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

        echo "Running DECENTRALIZED - $bidder_name"

        # $EXEC_FILE "$temp_json" > "$output_file"
        $EXEC_FILE "$temp_json" $WRENCH_ARGS > "$output_file"
        rm "$temp_json"
    done

    # --------------------------------------------------
    # DECENTRALIZED - Baselines
    # --------------------------------------------------

    for policy in "${BASELINE_POLICIES[@]}"; do

        output_file="$RESULT_DIR/${workload_name}_${policy}.csv"
        temp_json="temp_config.json"

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

        echo "Running DECENTRALIZED - $policy"

        # $EXEC_FILE "$temp_json" > "$output_file"
        $EXEC_FILE "$temp_json" $WRENCH_ARGS > "$output_file"
        rm "$temp_json"
    done

    # --------------------------------------------------
    # CENTRALIZED - Python bidders (one subprocess per system, parallel)
    # --------------------------------------------------
    for bidder in "${PYTHON_BIDDERS[@]}"; do
        bidder_name=$(basename "$bidder" .py)
        output_file="$RESULT_DIR_CENTRALIZED/${workload_name}_${bidder_name}.csv"
        temp_json="temp_config_centralized.json"

        jq \
        --arg workload "$workload" \
        --arg platform "$platform_file" \
        --arg bidder "$bidder" \
        '
        .workload = $workload |
        .platform = $platform |
        .centralized_policy = $bidder
        ' "$CENT_TEMPLATE" > "$temp_json"

        echo "Running CENTRALIZED - $bidder_name"

        $EXEC_FILE "$temp_json" $WRENCH_ARGS > "$output_file"
        rm "$temp_json"
    done

done

echo "All experiments completed."