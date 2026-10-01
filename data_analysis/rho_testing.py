import argparse
import json
import os
import re
import random
from typing import Dict, Tuple, Optional

import numpy as np
import pandas as pd

from pathlib import Path


JOB_TYPE_BANDS = {
    "HPC": {
        "short_wall": (0.5, 4),   # hours
        "long_wall": (4, 24),     # hours
        "small_storage": (50, 10_000),      # GB - small HPC jobs
        "large_storage": (5_000, 50_000)     
    },
    "AI": {
        "short_wall": (0.5, 4),
        "long_wall": (4, 24),
        "small_storage": (500, 50_000),     # GB - small AI jobs (datasets, models)
        "large_storage": (10_000, 200_000)  # GB - large AI jobs (large models, training data)

    },
    "HYBRID": {
        "short_wall": (0.5, 4),
        "long_wall": (4, 24),
        "small_storage": (100, 20_000),     # GB - small hybrid jobs
        "large_storage": (5_000, 100_000)   # GB - large hybrid jobs
    },
    "STORAGE": {
        "short_wall": (0.5, 4),
        "long_wall": (4, 24),
        "small_storage": (10_000, 100_000),  # GB - small storage jobs (still substantial)
        "large_storage": (50_000, 500_000)   # GB - large storage jobs (massive I/O)
    },
}

# 4. System load = (n * avg_nodes * avg_walltime) / (avg_nodes * 27)
#    avg_nodes cancels: = (n * avg_walltime) / 27
BASE_SYSTEM_CAPACITIES = {
'Frontier': {'nodes': 9472, 'storage_gb': 220_000_000},
'Andes': {'nodes': 704, 'storage_gb': 35_000_000},
'Aurora': {'nodes': 10624, 'storage_gb': 700_000_000},
'Crux': {'nodes': 256, 'storage_gb': 35_000_000},
'Perlmutter-Phase-1': {'nodes': 1536, 'storage_gb': 220_000_000},
'Perlmutter-Phase-2': {'nodes': 3072, 'storage_gb': 700_000_000}}


# read a workload from a json file
def read_workload_from_json(json_file: str) -> pd.DataFrame:
    with open(json_file, "r") as f:
        data = json.load(f)
    return pd.DataFrame(data)


def scenario_from_input_file(input_file: str) -> str:
    stem = Path(input_file).stem
    return re.sub(r"_\d+_r\d+$", "", stem)


def format_walltime_seconds_hours(seconds: float) -> str:
    return f"{int(round(seconds))} ({seconds / 3600:.2f})"

def print_workload_stats(df: pd.DataFrame):
    n = len(df)
    df['num_jobs'] = n

    # for each unique job type, print min and max walltime and nodes
    for job_type in df["JobType"].unique():
        job_type_df = df[df["JobType"] == job_type]
        wt_min = job_type_df["Walltime"].min()
        wt_max = job_type_df["Walltime"].max()
        nd_min = job_type_df["Nodes"].min()
        nd_max = job_type_df["Nodes"].max()
        print(f"\n=== Job Type: {job_type} ===")
        print(f"  Walltime (seconds): Min: {wt_min:,.0f}  Max: {wt_max:,.0f} Hours: Min: {wt_min/3600:,.2f}  Max: {wt_max/3600:,.2f}")
        print(f"  Nodes: Min: {nd_min:,}  Max: {nd_max:,}")
        # comapre with the defined bands
        bands = JOB_TYPE_BANDS[job_type]
        print(f"  Defined Bands:")
        # print(f"    Short Walltime: {bands['short_wall'][0]} - {bands['short_wall'][1]} hours")
        print(f"    Long Walltime: {bands['long_wall'][0]} - {bands['long_wall'][1]} hours")
        # print(f"    Small Storage: {bands['small_storage'][0]:,} - {bands['small_storage'][1]:,} GB")
        # print(f"    Large Storage: {bands['large_storage'][0]:,} - {bands['large_storage'][1]:,} GB")

    # 1. Walltime stats
    wt_min = df["Walltime"].min()
    wt_max = df["Walltime"].max()
    wt_avg = df["Walltime"].mean()
    # save these values to the dataframe
    df['min_walltime_sec(hr)'] = wt_min
    df['max_walltime_sec(hr)'] = wt_max
    df['avg_walltime_sec(hr)'] = wt_avg
    print("=== Walltime (seconds) ===")
    print(f"  Min: {wt_min:,.0f}  min_hr: {wt_min/3600:,.2f} (Job {df.loc[df['Walltime'].idxmin(), 'JobID']})")
    print(f"  Max: {wt_max:,.0f}  max_hr: {wt_max/3600:,.2f} (Job {df.loc[df['Walltime'].idxmax(), 'JobID']})")
    print(f"  Avg: {wt_avg:,.2f}  avg_hr: {wt_avg/3600:,.2f}")

    # print Tmax for each system from data
    print("\n=== Tmax for each HPC System from data ===")
    for system in df["HPCSystem"].unique():
        system_df = df[df["HPCSystem"] == system]
        system_tmax = system_df["Walltime"].max() / 3600
        print(f"  {system}: Tmax = {system_tmax:.2f} hours")

    # 2. Nodes stats
    nd_min = df["Nodes"].min()
    nd_max = df["Nodes"].max()
    nd_avg = df["Nodes"].mean()
    print("\n=== Nodes ===")
    print(f"  Min: {nd_min:,}  (Job {df.loc[df['Nodes'].idxmin(), 'JobID']})")
    print(f"  Max: {nd_max:,}  (Job {df.loc[df['Nodes'].idxmax(), 'JobID']})")
    print(f"  Avg: {nd_avg:,.2f}")
    df['min_node'] = nd_min
    df['max_node'] = nd_max
    df['avg_nodes'] = nd_avg

    # 3. Average node-hours
    node_hours = (df["Nodes"] * (df["Walltime"] / 3600)).mean()
    print(f"\n=== Avg Node-Hours ===")
    print(f"  {node_hours:,.2f} node-hours calculated as nodes*walltime/3600 averaged across all jobs")
    df['avg_node_hours'] = node_hours

    # take unique of hpc systems and their node counts, and compute the average node count across them
    available_system_nodes = df['HPCSystem'].unique()
    print(f"\n=== HPC Systems in Workload ===")
    print(available_system_nodes)
    df['num_systems'] = len(available_system_nodes)

    total_nodes_of_the_available_system = sum(BASE_SYSTEM_CAPACITIES[system]['nodes'] for system in available_system_nodes)
    df['total_nodes_of_available_system'] = total_nodes_of_the_available_system
    print(f"total node capacity {total_nodes_of_the_available_system}")
    num = sum(df['Nodes'] * (df['Walltime']/3600)) # node-hours across all jobs
    df['total_node_hours'] = num
    den = (total_nodes_of_the_available_system * 27)
    system_load = num / den
    print(f"num = sum of nodes * walltime across all jobs in hours = {num:,.2f}")
    print(f"den = total_nodes_of_the_available_system * 27 = {den:,.2f}")
    df['empirical_system_load'] = system_load
    print(f"\n=== System Load ===")
    print(f"  (sum of nodes * (walltime/3600)) / (total_nodes_of_the_available_system * 27) = {system_load:,.2f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate job data for testing rho values.")
    parser.add_argument("--input_file", type=str, required=True, help="Path to the input JSON file containing the workload data.")
    args = parser.parse_args()

    df = pd.DataFrame(columns=["scenario", "empirical_system_load", "num_jobs", "num_systems", "min_node", "max_node", "avg_nodes", "min_walltime_sec(hr)", "max_walltime_sec(hr)", "avg_walltime_sec(hr)", "avg_node_hours", "total_node_hours"])
    df_final = read_workload_from_json(args.input_file)
    print(f"Loaded {len(df_final)} jobs from: {args.input_file}\n")
    print_workload_stats(df_final)
    scenario_name = scenario_from_input_file(args.input_file)
    df['scenario'] = scenario_name
    row_to_append = df_final.iloc[[0]].copy()
    row_to_append['scenario'] = scenario_name
    row_to_append['empirical_system_load'] = round(float(row_to_append['empirical_system_load'].iloc[0]), 1)
    row_to_append['min_walltime_sec(hr)'] = format_walltime_seconds_hours(float(row_to_append['min_walltime_sec(hr)'].iloc[0]))
    row_to_append['max_walltime_sec(hr)'] = format_walltime_seconds_hours(float(row_to_append['max_walltime_sec(hr)'].iloc[0]))
    row_to_append['avg_walltime_sec(hr)'] = format_walltime_seconds_hours(float(row_to_append['avg_walltime_sec(hr)'].iloc[0]))
    row_to_append = row_to_append.reindex(columns=df.columns)
    df = pd.concat([df, row_to_append], ignore_index=True)

    output_csv = "rho_testing_results.csv"
    write_mode = "a" if os.path.exists(output_csv) else "w"
    df.to_csv(output_csv, mode=write_mode, header=(write_mode == "w"), index=False)











