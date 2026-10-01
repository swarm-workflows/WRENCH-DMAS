# Experiment & Analysis Scripts

The scripts automate the full evaluation pipeline from simulation execution to final visualization.
This directory contains shell scripts used to:

1. Run SWARM-DMAS experiments for various workloads and bidding strategies.
2. Analyze workloads and results and generate plots.
3. Generate comparison plots from aggregated evaluation metrics.


### 1. Workload Analysis
From project directory, run:
```bash
bash bash_scripts/analyze_workloads.sh
```
This script:
- Iterates over multiple workloads, spanning various temporal settings and scenarios.
- Analyzes workloads from `data_generation/data` directory.
- Uses `data_analysis/workload_analysis.Rscript` to analyze the workloads.
- Saves the generated plots in `plots/workload`.


### 2. Run Experiments
From project directory, run:
```bash
bash bash_scripts/run_experiments.sh
```
This script:
- Iterates over workloads and bidding strategies.
- Runs swarm_dmas with appropriate JSON configurations, including both decentralized and centralized modes.
- Stores raw outputs from decentralized mode executions under `results/`.
- Stores raw outputs from centralized executions under `results/centralized`.


### 3. Analyze Individual Results
From project directory, run:
```bash
bash bash_scripts/analyze_results.sh
```
This script:
- Analyzes the generated .csv results files from `results/` and `results/centralized`.
- Uses python analyzer file `data_analysis/analyze_results_old.py` and Rscript analyzer file `data_analysis/output_analysis.Rscript` to generate individual metrics for workloads.
- Stores generated plots under `plots/individual` and `plots/centralized` directories for decentralized and centralized modes, respectively.


### 4. Compare Results
Before running this script, make sure to run `data_analysis/aggregate_results.py` to aggregate results across jobs for all experiment scenarios. Then from project directory, run:
```bash
bash bash_scripts/compare_results.sh
```
This script:
- Reads the aggregated metrics from `results/aggregated_metrics.csv`.
- Uses `data_analysis/biddingComparison.Rscript` to compare between multiple bidding strategies (heuristic, embedding, LLM, local, random) and generates plots with appropriate metrics.
- Uses script `data_analysis/compareToCentralized.Rscript` to compare centralized vs decentralized operation with the same bidding method and generates plots.
- Saves the generated plots under `plots/comparison`.
