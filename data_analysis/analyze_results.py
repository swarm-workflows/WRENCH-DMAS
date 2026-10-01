#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import json
from pathlib import Path
import re
import matplotlib.patches
import colorsys
import math

################ SYSTEM CAPACITIES ################

BASE_SYSTEM_CAPACITIES = {
    'Frontier': {'nodes': 9472, 'storage_gb': 220_000_000},
    'Andes': {'nodes': 704, 'storage_gb': 35_000_000},
    'Aurora': {'nodes': 10624, 'storage_gb': 700_000_000},
    'Crux': {'nodes': 256, 'storage_gb': 35_000_000},
    'Perlmutter-Phase-1': {'nodes': 1536, 'storage_gb': 220_000_000},
    'Perlmutter-Phase-2': {'nodes': 3072, 'storage_gb': 700_000_000}
}
################ CSV sanity_checks ################
def run_sanity_checks(df, df_valid, system_capacities, bidding_method, max_decision_time_sec=32.0, workload_name=""):
    """
    Log lightweight sanity checks for simulation CSV files.
    These checks help catch invalid outputs early during batch analysis.
    They do not stop the script; they only report results to the validation csv file.
    """
    sanity_check_results = {}
    
    sanity_check_results['bidding_method'] = bidding_method
    sanity_check_results['workload'] = workload_name
    sanity_check_results['total_jobs'] = len(df)
    sanity_check_results['failed_jobs'] = len(df) - len(df_valid)
    
    # If bidding method is LLM-based, attempt to read the log file to calculate heuristic fallback rate
    if "LLM" in bidding_method:
        log_path = Path("logs") / "llm_bidding" / f"{workload_name}.log"
        if log_path.exists():
            with open(log_path, 'r') as f:
                log_content = f.read()
            heuristic_fallbacks = len(re.findall(r"Using Heuristic bid", log_content))
            sanity_check_results['#heuristic_fallback'] = heuristic_fallbacks
            total_jobs_logged = len(re.findall(r"Prompt for job", log_content))
            fallback_rate = heuristic_fallbacks / total_jobs_logged if total_jobs_logged > 0 else 0
            print(f"✓ LLM fallback to heuristic bid rate: {fallback_rate:.2%} ({heuristic_fallbacks}/{total_jobs_logged})")
            sanity_check_results['llm_heuristic_fallback_rate%'] = fallback_rate
        else:
            print(f"⚠ Log file not found for LLM fallback rate calculation: {log_path}")
            sanity_check_results['llm_heuristic_fallback_rate%'] = None

    else:
        # print(f"✓ Non-LLM bidding method; skipping heuristic fallback rate check")
        sanity_check_results['llm_heuristic_fallback_rate%'] = "N/A"

    # 2. Completed/successful job check
    if 'FinalStatus' in df.columns:
        completed_count = len(df[df['FinalStatus'] == 'COMPLETED'])
        non_completed_count = len(df) - completed_count
        sanity_check_results['non_completed_jobs'] = non_completed_count
        if non_completed_count > 0:
            print(f"⚠ {non_completed_count} jobs are not COMPLETED")
        else:
            print("✓ All jobs have FinalStatus == COMPLETED")
    else:
        print("⚠ FinalStatus column missing; using scheduled/end/execution-time filtering only")

    # 3. Required columns for core metrics and plots
    required_cols = [
        'JobId', 'ScheduledOn', 'StartTime', 'EndTime',
        'ExecutionTime', 'SubmissionTime', 'Nodes'
    ]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"⚠ Missing expected columns: {missing_cols}")
    else:
        print("✓ Required metric columns are present")

    # 4. Bid range check: skip PureLocal or any CSV without Bids
    if 'Bids' in df_valid.columns:
        def check_bids(bids_str):
            try:
                bids = [float(bid.strip()) for bid in str(bids_str).split(':')]
                return all(0.0 <= bid <= 1.0 for bid in bids)
            except Exception:
                return False

        bids_valid = df_valid['Bids'].apply(check_bids)
        invalid_bids_count = len(df_valid[~bids_valid])

        if invalid_bids_count > 0:
            print(f"⚠ {invalid_bids_count} jobs have bid values outside [0, 1] or unparsable bids")
            sanity_check_results['invalid_bids_count'] = invalid_bids_count
        else:
            print("✓ All bid values are within [0, 1]")
            sanity_check_results['invalid_bids_count'] = 0

    else:
        print(f"✓ No Bids column found; skipping bid check for {bidding_method}")
        sanity_check_results['invalid_bids_count'] = None

    # 5. Decision time sanity_check
    if 'DecisionTime' in df_valid.columns:
        slow_decisions = df_valid[df_valid['DecisionTime'] > max_decision_time_sec]
        if len(slow_decisions) > 0:
            print(f"⚠ {len(slow_decisions)} jobs have DecisionTime > {max_decision_time_sec}s")
            print(f"  Max DecisionTime: {df_valid['DecisionTime'].max():.4f}s")
            sanity_check_results['slow_decisions_count'] = len(slow_decisions)
        else:
            print(f"✓ All DecisionTime values are <= {max_decision_time_sec}s")
            sanity_check_results['slow_decisions_count'] = 0
    else:
        print("⚠ DecisionTime column missing; skipping decision-time check")
        sanity_check_results['slow_decisions_count'] = None

    # 6. Time ordering check
    time_cols = {'SubmissionTime', 'StartTime', 'EndTime'}
    if time_cols.issubset(df_valid.columns):
        bad_time_order = df_valid[
            (df_valid['StartTime'] < df_valid['SubmissionTime']) |
            (df_valid['EndTime'] < df_valid['StartTime'])
        ]

        if len(bad_time_order) > 0:
            print(f"⚠ {len(bad_time_order)} jobs have invalid time ordering")
            sanity_check_results['bad_time_order_count'] = len(bad_time_order)
        else:
            print("✓ Time ordering is valid: SubmissionTime <= StartTime <= EndTime")
            sanity_check_results['bad_time_order_count'] = 0
    else:
        print("⚠ Missing time columns; skipping time-ordering check")

    # 7. Positive execution time check
    if 'ExecutionTime' in df_valid.columns:
        bad_exec = df_valid[df_valid['ExecutionTime'] <= 0]
        if len(bad_exec) > 0:
            print(f"⚠ {len(bad_exec)} jobs have non-positive ExecutionTime")
            sanity_check_results['non_positive_execution_time'] = len(bad_exec)
        else:
            print("✓ All completed jobs have positive ExecutionTime")
            sanity_check_results['non_positive_execution_time'] = 0

    # 8. Per-job node capacity check
    if {'ScheduledOn', 'Nodes'}.issubset(df_valid.columns):
        bad_node_requests = []
        for _, row in df_valid.iterrows():
            system = row['ScheduledOn']
            requested_nodes = row['Nodes']
            capacity = system_capacities.get(system, {}).get('nodes')

            if capacity is not None and requested_nodes > capacity:
                bad_node_requests.append(row['JobId'])

        if bad_node_requests:
            print(f"⚠ {len(bad_node_requests)} jobs request more nodes than system capacity")
            sanity_check_results['bad_node_requests'] = len(bad_node_requests)
        else:
            print("✓ No single job exceeds scheduled system node capacity")
            sanity_check_results['bad_node_requests'] = 0
    else:
        print("⚠ Missing ScheduledOn or Nodes; skipping node-capacity check")

    # 9. Oversubscription check using NodeList if available
    if {'ScheduledOn', 'NodeList', 'StartTime', 'EndTime', 'JobId'}.issubset(df_valid.columns):
        total_conflict_pairs = 0

        for system in sorted(df_valid['ScheduledOn'].dropna().unique()):
            system_df = df_valid[df_valid['ScheduledOn'] == system].copy()
            jobs = []

            for _, row in system_df.iterrows():
                try:
                    intervals = GanttVisualization.parse_nodelist_intervals(row['NodeList'])
                    jobs.append({
                        'job_id': row['JobId'],
                        'start': float(row['StartTime']) / 3600.0,
                        'end': float(row['EndTime']) / 3600.0,
                        'intervals': intervals,
                    })
                except Exception:
                    print(f"⚠ Could not parse NodeList for JobId={row.get('JobId')}")
                    continue

            fig, ax = plt.subplots()
            viz = GanttVisualization(ax)
            conflict_pairs, conflicted_jobs = viz._validate_contention(jobs)
            plt.close(fig)

            total_conflict_pairs += conflict_pairs

            if conflict_pairs > 0:
                print(f"⚠ {system}: {conflict_pairs} oversubscription/contention pairs involving {len(conflicted_jobs)} jobs")
                sanity_check_results[f'{system}_conflict_pairs'] = conflict_pairs
                sanity_check_results[f'{system}_conflicted_jobs'] = len(conflicted_jobs)

        if total_conflict_pairs == 0:
            print("✓ No node oversubscription detected from NodeList")
    else:
        print("⚠ NodeList or timing columns missing; skipping exact oversubscription check")

    print("="*70 + "\n")
    return sanity_check_results
    
################ JOB DEFINITIONS ################
def load_job_definitions(workload_path):
    """Load job definitions from workload JSON file."""
    with open(workload_path, 'r') as f:
        jobs = json.load(f)
    jobs_df = pd.DataFrame(jobs)
    # Ensure JobID column exists and select relevant columns
    if 'JobID' in jobs_df.columns:
        return jobs_df[['JobID', 'Nodes', 'MemoryGB', 'RequestedGPU', 'RequestedStorageGB', 
                        'JobType', 'Walltime']].copy()
    return jobs_df

def filter_successful_jobs(df):
    """
    Keep only jobs that were successfully scheduled and executed.
    Removes failed or unscheduled jobs that would corrupt metrics.
    """
    filtered = df.copy()

    # Must have been scheduled
    if 'ScheduledOn' in filtered.columns:
        filtered = filtered[filtered['ScheduledOn'].notna()]

    # Must have valid execution time
    if 'ExecutionTime' in filtered.columns:
        filtered = filtered[filtered['ExecutionTime'] > 0]

    # Must have valid end time
    if 'EndTime' in filtered.columns:
        filtered = filtered[filtered['EndTime'] > 0]

    return filtered

def load_results(csv_path, jobs_df=None):
    """Load simulation results from CSV file and merge with job definitions."""
    df = pd.read_csv(csv_path)
    
    if jobs_df is not None:
        jobs_df = jobs_df.copy()
        if "JobID" in jobs_df.columns and "JobId" not in jobs_df.columns:
            jobs_df = jobs_df.rename(columns={"JobID": "JobId"})

        if "JobId" in df.columns and "JobId" in jobs_df.columns:
            df["JobId"] = df["JobId"].astype(str)
            jobs_df["JobId"] = jobs_df["JobId"].astype(str)
            df = pd.merge(df, jobs_df, on="JobId", how="left")
        else:
            print("Warning: 'JobID' column not found in one of the DataFrames. Skipping merge.")

    if 'Nodes' not in df.columns:
        raise ValueError(
            "Merge failed: 'Nodes' column missing after merging workload JSON."
        )

    # add column in df for turnaround time if not already present
    if 'TurnaroundTime' not in df.columns and 'SubmissionTime' in df.columns and 'EndTime' in df.columns:
        df['TurnaroundTime'] = df['EndTime'] - df['SubmissionTime']

    
    return df



################ METRICS CALCULATION ################
def calculate_makespan(df):
    makespan = df['EndTime'].max() - df['SubmissionTime'].min() 
    return makespan

def calculate_throughput(df):
    completed_jobs = len(df)
    makespan = calculate_makespan(df)  # in minutes
    throughput = completed_jobs / makespan if makespan > 0 else 0
    return throughput

def calculate_resource_utilization(df, system_capacities):
    """
    Calculate resource utilization over time for total system.
    Utilization can be defined as (Nodes Used) / (Total Nodes Available) at any given time for total system.
    """
    # Calculate total node-minutes used across all jobs
    total_node_time = (df['Nodes'] * df['ExecutionTime']).sum()
    
    # Calculate makespan (total time window)
    total_time = calculate_makespan(df)
    
    # Total nodes across all systems
    total_nodes = sum(caps['nodes'] for caps in system_capacities.values())
    
    # Total available node-minutes in the system
    total_available_node_time = total_nodes * total_time
    
    # Node utilization as a percentage
    node_utilization = (total_node_time / total_available_node_time) * 100

    # Calculate total storage-GB-minutes used across all jobs
    total_storage_gb_minutes = (df['RequestedStorageGB'] * df['ExecutionTime']).sum()
    
    # Total storage capacity in GB (2 storage systems per site)
    total_storage_capacity = sum(2 * caps['storage_gb'] for caps in system_capacities.values())

    # Total available storage-GB-minutes in the system
    total_available_storage_gb_minutes = total_storage_capacity * total_time
    
    # Storage utilization as a percentage
    storage_utilization = (total_storage_gb_minutes / total_available_storage_gb_minutes) * 100

    return node_utilization, storage_utilization


def _max_endtime_hours(df):
    """Compute xmax in hours from EndTime (or StartTime+ExecutionTime fallback)."""
    if df is None or len(df) == 0:
        return 0.0

    if 'EndTime' in df.columns:
        return float(df['EndTime'].max()) / 3600.0

    if 'StartTime' in df.columns and 'ExecutionTime' in df.columns:
        return float((df['StartTime'] + df['ExecutionTime']).max()) / 3600.0

    return 0.0


def _counterpart_csv_path(csv_path):
    """
    Return centralized/decentralized counterpart CSV path for the same filename.
    - results/foo.csv <-> results/centralized/foo.csv
    """
    if csv_path.parent.name == 'centralized':
        return csv_path.parent.parent / csv_path.name
    return csv_path.parent / 'centralized' / csv_path.name


def compute_shared_xmax_hours(csv_path, current_df):
    """
    Build a shared x-axis max (hours) between current mode and counterpart mode.
    Uses 5-hour ceiling so both figures show the same explicit max tick.
    """
    current_max_h = _max_endtime_hours(current_df)

    counterpart_max_h = 0.0
    counterpart_path = _counterpart_csv_path(Path(csv_path))
    if counterpart_path.exists():
        counterpart_df = pd.read_csv(counterpart_path)
        counterpart_df = filter_successful_jobs(counterpart_df)
        counterpart_max_h = _max_endtime_hours(counterpart_df)

    shared_max_h = max(current_max_h, counterpart_max_h)
    shared_max_h = max(5.0, float(math.ceil(shared_max_h / 5.0) * 5.0))

    return shared_max_h, counterpart_path if counterpart_path.exists() else None


def calculate_per_system_metrics(df, system_capacities):
    """
    Calculate performance metrics for each system/machine.
    
    Returns:
        pd.DataFrame: DataFrame with metrics per system including:
            - Total Jobs Submitted
            - Total Jobs Scheduled
            - Makespan
            - Throughput
            - Node Utilization (%)
            - Storage Utilization (%)
            - Mean Turnaround Time
            - Mean Execution Time
            - Mean Decision Time
    """
    
    if 'ScheduledOn' not in df.columns:
        print("Error: 'ScheduledOn' column not found")
        return None
    
    # Get all unique systems from both SubmittedOn and ScheduledOn
    systems = set()
    if 'SubmittedOn' in df.columns:
        systems.update(df['SubmittedOn'].unique())
    systems.update(df['ScheduledOn'].unique())
    
    metrics = []
    
    for system in sorted(systems):
        # Jobs submitted to this system

        jobs_submitted = 0
        if 'SubmittedTo' in df.columns:
            jobs_submitted = len(df[df['SubmittedTo'] == system])
        
        # Jobs scheduled/executed on this system
        system_df = df[df['ScheduledOn'] == system].copy()
        total_jobs_scheduled = len(system_df)
        
        # Makespan for this system
        if 'EndTime' in system_df.columns and 'SubmissionTime' in system_df.columns:
            system_makespan = system_df['EndTime'].max() - system_df['SubmissionTime'].min()
        else:
            system_makespan = 0
        
        # Throughput
        throughput = total_jobs_scheduled / system_makespan if system_makespan > 0 else 0
        
        # Node utilization
        if 'Nodes' in system_df.columns and 'ExecutionTime' in system_df.columns:
            total_node_minutes = (system_df['Nodes'] * system_df['ExecutionTime']).sum()
            system_capacity = system_capacities.get(system, {}).get('nodes', 1000)
            available_node_minutes = system_capacity * system_makespan
            node_utilization = (total_node_minutes / available_node_minutes * 100) if available_node_minutes > 0 else 0
        else:
            node_utilization = 0
        
        # Storage utilization
        if 'RequestedStorageGB' in system_df.columns and 'ExecutionTime' in system_df.columns:
            total_storage_gb_minutes = (system_df['RequestedStorageGB'] * system_df['ExecutionTime']).sum()
            storage_capacity = system_capacities.get(system, {}).get('storage_gb', 100_000_000)
            # Multiply by 2 for 2 storage systems per site
            available_storage_gb_minutes = (2 * storage_capacity) * system_makespan
            storage_utilization = (total_storage_gb_minutes / available_storage_gb_minutes * 100) if available_storage_gb_minutes > 0 else 0
        else:
            storage_utilization = 0
        
        # Time statistics
        mean_turnaround = system_df['TurnaroundTime'].mean() if 'TurnaroundTime' in system_df.columns else 0
        mean_execution = system_df['ExecutionTime'].mean() if 'ExecutionTime' in system_df.columns else 0
        mean_decision = system_df['DecisionTime'].mean() if 'DecisionTime' in system_df.columns else 0
        
        metrics.append({
            'System': system,
            'JobsSubmitted': jobs_submitted,
            'JobsScheduled': total_jobs_scheduled,
            'Makespan (min)': round(system_makespan, 2),
            'Throughput (jobs/min)': round(throughput, 4),
            'NodeUtilization (%)': round(node_utilization, 2),
            'StorageUtilization (%)': round(storage_utilization, 2),
            'MeanTurnaroundTime (min)': round(mean_turnaround, 2),
            'MeanExecutionTime (min)': round(mean_execution, 2),
            'MeanDecisionTime (sec)': round(mean_decision, 4)
        })
    
    metrics_df = pd.DataFrame(metrics)
    return metrics_df

def print_per_system_metrics(metrics_df):
    """Pretty print per-system metrics."""
    if metrics_df is None or len(metrics_df) == 0:
        print("No per-system metrics available")
        return
    
    print("\n" + "="*80)
    print("PER-SYSTEM METRICS")
    print("="*80)
    print(metrics_df.to_string(index=False))
    print("="*80 + "\n")

def print_summary_stats(df, makespan):
    print("\n" + "="*60)
    print("SIMULATION SUMMARY")
    print("="*60)
    
    print(f"\nMakespan: {makespan:.2f} seconds")
    print(f"Completed Jobs: {len(df)}")
    
    if 'ScheduledOn' in df.columns:
        print(f"\nJobs per System:")
        for system, count in df['ScheduledOn'].value_counts().items():
            print(f"  {system}: {count}")
    
    if 'TurnaroundTime' in df.columns:
        print(f"\nTurnaround Time Statistics:")
        print(f"  Mean: {df['TurnaroundTime'].mean():.2f} seconds")
        print(f"  Median: {df['TurnaroundTime'].median():.2f} seconds")
        print(f"  Min: {df['TurnaroundTime'].min():.2f} seconds")
        print(f"  Max: {df['TurnaroundTime'].max():.2f} seconds")
    
    if 'ExecutionTime' in df.columns:
        print(f"\nExecution Time Statistics:")
        print(f"  Mean: {df['ExecutionTime'].mean():.2f} seconds")
        print(f"  Median: {df['ExecutionTime'].median():.2f} seconds")
        print(f"  Min: {df['ExecutionTime'].min():.2f} seconds")
        print(f"  Max: {df['ExecutionTime'].max():.2f} seconds")
    
    if 'DecisionTime' in df.columns:
        print(f"\nDecision Time Statistics:")
        print(f"  Mean: {df['DecisionTime'].mean():.4f} seconds")
        print(f"  Median: {df['DecisionTime'].median():.4f} seconds")
    
    print("="*60 + "\n")

################## PLOTTING FUNCTIONS ##################
def plot_resource_utilization(df, system_capacities, output_path='resource_utilization.png'):
    if 'ScheduledOn' not in df.columns:
        print("Error: 'ScheduledOn' column not found in CSV")
        return 
    systems = df['ScheduledOn'].unique()
    
    fig, axes = plt.subplots(len(systems), 1, figsize=(14, 4 * len(systems)), sharex=True)
    if len(systems) == 1:
        axes = [axes]
    
    fig.suptitle('Resource Utilization Across Systems', fontsize=16, fontweight='bold')
    
    for idx, system in enumerate(systems):
        ax = axes[idx]
        system_df = df[df['ScheduledOn'] == system].copy()

        # Create timeline visualization
        for _, job in system_df.iterrows():
            start = job['StartTime']
            duration = job['ExecutionTime']  
            ax.barh(y=0, width=duration, left=start,
                   alpha=0.6, edgecolor='black', linewidth=0.5)
        ax.set_xlim(0, df['EndTime'].max() * 1.1)
        ax.set_yticks([])
        ax.set_ylabel(f'{system}', fontweight='bold')
        ax.set_title(f'{system} - {len(system_df)} jobs', fontweight='bold', fontsize=12)
        ax.grid(True, alpha=0.3, axis='x')
    
    axes[-1].set_xlabel('Execution Time (mins)', fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.97])  
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Resource utilization plot saved to {output_path}")
    plt.close()

def plot_utilization_percentage(df, system_capacities, output_path='utilization_percentage.png', x_max_hours=None):
    if 'ScheduledOn' not in df.columns:
        print("Error: 'ScheduledOn' column not found")
        return
 
    systems = df['ScheduledOn'].unique()
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    for system in systems:
        system_df = df[df['ScheduledOn'] == system].copy()
        if 'EndTime' not in system_df.columns and 'TurnaroundTime' in system_df.columns:
            system_df['EndTime'] = system_df['SubmissionTime'] + system_df['TurnaroundTime']
        
        if 'ExecutionTime' in system_df.columns:
            system_df['StartTime'] = system_df['EndTime'] - system_df['ExecutionTime']
        else:
            system_df['StartTime'] = system_df['SubmissionTime']
        
        # Create time bins (seconds); convert to hours only for plotting.
        if x_max_hours is not None:
            max_time = x_max_hours * 3600.0
        else:
            max_time = df['EndTime'].max() if 'EndTime' in df.columns else df['SubmissionTime'].max()
        time_bins = np.linspace(0, max_time, 100)
        time_bins_hours = time_bins / 3600.0
        utilization_pct = []
        nodes_used_abs = []
        
        capacity = system_capacities.get(system, {}).get('nodes', 1000)
        
        for t in time_bins:
            # Count nodes in use at time t
            active_jobs = system_df[(system_df['StartTime'] <= t) & (system_df['EndTime'] >= t)]
            # print("active_jobs at time", t, "for system", system, ":", len(active_jobs))
            
            nodes_used = active_jobs['Nodes'].sum()
            nodes_used_abs.append(nodes_used)
            util_pct = (nodes_used / capacity) * 100
            utilization_pct.append(util_pct)
        
        # Plot 1: Absolute nodes used
        ax1.plot(time_bins_hours, nodes_used_abs, label=f'{system} (cap: {capacity})', 
                linewidth=2, marker='o', markersize=3, alpha=0.7)
        
        # Plot 2: Percentage utilization
        ax2.plot(time_bins_hours, utilization_pct, label=system, linewidth=2, marker='o', 
               markersize=3, alpha=0.7)
    
    # Configure absolute nodes plot
    ax1.set_ylabel('Nodes Used (Absolute)', fontweight='bold', fontsize=12)
    ax1.set_title('Absolute Node Utilization Over Time', fontweight='bold', fontsize=14)
    ax1.legend(loc='best', fontsize=9)
    ax1.grid(True, alpha=0.3)
    
    # Configure percentage plot
    ax2.set_xlabel('Time (hours)', fontweight='bold', fontsize=12)
    ax2.set_ylabel('Utilization (%)', fontweight='bold', fontsize=12)
    ax2.set_title('Percentage Utilization (Relative to System Capacity)', fontweight='bold', fontsize=14)
    ax2.legend(loc='best', fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(0, 100)

    if x_max_hours is not None:
        ticks = np.arange(0, x_max_hours + 0.1, 5)
        ax1.set_xlim(0, x_max_hours)
        ax2.set_xlim(0, x_max_hours)
        ax2.set_xticks(ticks)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Utilization percentage plot saved to {output_path}")
    plt.close()


################# Gantt plot helpers #################
def generate_palette(size):
    if size <= 0:
        return []
    # Build a pastel-ish unique palette for each job.
    if size <= 12:
        return list(plt.cm.Set3(np.linspace(0, 1, size, endpoint=False)))

    base = plt.cm.hsv(np.linspace(0, 1, size, endpoint=False))
    base[:, :3] = (0.58 * base[:, :3]) + 0.42
    return list(base)

def bulksetattr(obj, **kwargs):
    for k, v in kwargs.items():
        getattr(obj, k)
        setattr(obj, k, v)

class Visualization:
    def __init__(self, ax):
        self._ax = ax
        self.palette = generate_palette(8)

class GanttVisualization(Visualization):
    """
    Minimal Evalys-style Gantt renderer adapted to local CSV schema.
    """

    def __init__(self, ax, *, title='System Gantt chart'):
        super().__init__(ax)
        self.title = title
        self.alpha = 0.65
        # Time overlap tolerance in hours (~0.036s) to avoid boundary-rounding false positives.
        self.time_epsilon_hours = 1e-5

    @staticmethod
    def parse_nodelist_intervals(node_list):
        intervals = []
        tokens = str(node_list).split(':')
        for token in tokens:
            token = token.strip()
            if '-' in token:
                start, end = token.split('-', maxsplit=1)
                intervals.append((int(start), int(end)))
            else:
                value = int(token)
                intervals.append((value, value))
        return intervals

    def _time_overlaps(self, job_a, job_b):
        eps = self.time_epsilon_hours
        return (job_a['start'] < (job_b['end'] - eps)) and (job_b['start'] < (job_a['end'] - eps))

    @staticmethod
    def _node_overlaps(intervals_a, intervals_b):
        for a_start, a_end in intervals_a:
            for b_start, b_end in intervals_b:
                if not (a_end < b_start or b_end < a_start):
                    return True
        return False

    def _validate_contention(self, jobs):
        """
        Detects node contention where two jobs overlap in time and in at least one node id.
        Returns:
            - number of conflicting job pairs
            - set of job ids involved in at least one contention
        """
        if not jobs:
            return 0, set()

        sorted_jobs = sorted(jobs, key=lambda j: j['start'])
        conflict_pairs = 0
        conflicted_jobs = set()

        for i in range(len(sorted_jobs)):
            a = sorted_jobs[i]
            for j in range(i + 1, len(sorted_jobs)):
                b = sorted_jobs[j]

                # Because jobs are sorted by start time, once b starts after a ends,
                # no later job can overlap a in time.
                if b['start'] >= a['end']:
                    break

                if self._time_overlaps(a, b) and self._node_overlaps(a['intervals'], b['intervals']):
                    conflict_pairs += 1
                    conflicted_jobs.add(a['job_id'])
                    conflicted_jobs.add(b['job_id'])

        return conflict_pairs, conflicted_jobs

    def _assign_job_colors(self, jobs):
        if not jobs:
            return {}

        # Enforce one unique color per job and spread neighboring jobs far apart
        # in color space for better visual distinction.
        color_by_job = {}
        golden_ratio = 0.6180339887498949

        for idx, job in enumerate(jobs):
            hue = (idx * golden_ratio) % 1.0
            sat = 0.45 + 0.20 * (idx % 3) / 2.0
            val = 0.82 + 0.10 * (idx % 2)
            r, g, b = colorsys.hsv_to_rgb(hue, sat, min(val, 1.0))
            color_by_job[job['job_id']] = (r, g, b, 1.0)

        return color_by_job

    def draw_system(self, system_df, system_name, system_capacity, show_job_ids=True):
        jobs = []
        min_node = None
        max_node = None

        for _, row in system_df.iterrows():
            intervals = self.parse_nodelist_intervals(row['NodeList'])
            start_hr = float(row['StartTime']) / 3600.0
            if 'EndTime' in row and pd.notna(row['EndTime']):
                end_hr = float(row['EndTime']) / 3600.0
                duration_hr = max(end_hr - start_hr, 0.0)
            else:
                duration_hr = float(row['ExecutionTime']) / 3600.0
                end_hr = start_hr + duration_hr

            for interval_start, interval_end in intervals:
                if min_node is None or interval_start < min_node:
                    min_node = interval_start
                if max_node is None or interval_end > max_node:
                    max_node = interval_end

            jobs.append({
                'job_id': row['JobId'],
                'start': start_hr,
                'end': end_hr,
                'duration': duration_hr,
                'intervals': intervals,
            })

        contention_pairs, conflicted_job_ids = self._validate_contention(jobs)
        color_by_job = self._assign_job_colors(jobs)

        for job in jobs:
            for interval_start, interval_end in job['intervals']:
                is_conflicted = job['job_id'] in conflicted_job_ids
                rect = matplotlib.patches.Rectangle(
                    (job['start'], interval_start),
                    job['duration'],
                    interval_end - interval_start + 1,
                    alpha=self.alpha,
                    facecolor=color_by_job[job['job_id']],
                    edgecolor='crimson' if is_conflicted else 'black',
                    linewidth=0.9 if is_conflicted else 0.4,
                )
                self._ax.add_patch(rect)
                # Add job id label in each allocated interval rectangle.
                if show_job_ids:
                    cx = job['start'] + (job['duration'] / 2.0)
                    cy = interval_start + ((interval_end - interval_start + 1) / 2.0)
                    self._ax.text(
                        cx,
                        cy,
                        str(job['job_id']),
                        ha='center',
                        va='center',
                        fontsize=5,
                        color='black',
                        alpha=0.85,
                    )

        self._ax.set_title(f'{system_name} - {len(jobs)} jobs', fontweight='bold', fontsize=12)
        self._ax.set_ylabel(f'{system_name}\nNode IDs\n(cap={system_capacity})', fontweight='bold', fontsize=10)
        self._ax.grid(True, alpha=0.25, axis='x')
        # Show the coordinate origin marker for quick orientation.
        self._ax.scatter([0], [0], color='black', s=18, marker='+', zorder=5)

        if min_node is not None and max_node is not None:
            y_top = max(max_node + 10, system_capacity + 2)
            self._ax.set_ylim(0, y_top)

            # Capacity guide and explicit warning when allocations exceed capacity.
            self._ax.axhline(system_capacity, color='dimgray', linestyle='--', linewidth=0.8, alpha=0.8)
            # self._ax.text(
            #     0.01,
            #     0.92,
            #     f'capacity={system_capacity}',
            #     transform=self._ax.transAxes,
            #     ha='left',
            #     va='top',
            #     fontsize=8,
            #     color='dimgray',
            #     bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.75),
            # )
            if max_node > system_capacity:
                self._ax.text(
                    0.99,
                    0.92,
                    f'VIOLATION: max node {max_node} > cap {system_capacity}',
                    transform=self._ax.transAxes,
                    ha='right',
                    va='top',
                    fontsize=8,
                    color='crimson',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8),
                )

        if contention_pairs > 0:
            self._ax.text(
                0.01,
                0.84,
                f'CONTENTIONS: {contention_pairs} pairs, {len(conflicted_job_ids)} jobs',
                transform=self._ax.transAxes,
                ha='left',
                va='top',
                fontsize=8,
                color='crimson',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.85),
            )
            print(f"⚠ Contention detected on {system_name}: {contention_pairs} conflicting pairs across {len(conflicted_job_ids)} jobs")
        else:
            self._ax.text(
                0.01,
                0.84,
                'No node contention detected',
                transform=self._ax.transAxes,
                ha='left',
                va='top',
                fontsize=8,
                color='darkgreen',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.85),
            )


def build_scenario_label(workload_name, method_name, run_mode):
    # Expected pattern in workload_name: <arrival...>_<type_a>_<type_b>_<n_jobs>_rho<rho>
    match = re.match(r'^(.*)_([0-9]+)_rho[0-9.]+$', workload_name)
    if not match:
        return f'{workload_name}|{method_name}|{run_mode}'

    prefix, n_jobs = match.group(1), match.group(2)
    parts = prefix.split('_')

    if len(parts) >= 3:
        workload_type = '-'.join(parts[-2:])
        arrival = '_'.join(parts[:-2])
    elif len(parts) == 2:
        workload_type = parts[-1]
        arrival = parts[0]
    else:
        workload_type = prefix
        arrival = 'unknown'

    return f'{arrival}|{workload_type}|{n_jobs}|{method_name}|{run_mode}'


def plot_system_gantt(df, system_capacities, output_path='system_gantt.png', note_text='', scenario_label='', show_job_ids=True, x_max_hours=None):
    required_cols = {'ScheduledOn', 'NodeList', 'StartTime', 'ExecutionTime', 'JobId'}
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        print(f"Error: missing columns required for Gantt plot: {missing}")
        return

    gantt_df = df.copy()
    if 'FinalStatus' in gantt_df.columns:
        gantt_df = gantt_df[gantt_df['FinalStatus'] == 'COMPLETED']

    systems = sorted(gantt_df['ScheduledOn'].dropna().unique())
    if len(systems) == 0:
        print('Warning: no systems available for Gantt plot')
        return

    fig, axes = plt.subplots(len(systems), 1, figsize=(16, 3.8 * len(systems)), sharex=True)
    if len(systems) == 1:
        axes = [axes]

    global_start = 0.0
    if x_max_hours is not None:
        global_end = x_max_hours
    elif 'EndTime' in gantt_df.columns:
        global_end = (gantt_df['EndTime'] / 3600.0).max()
    else:
        global_end = ((gantt_df['StartTime'] + gantt_df['ExecutionTime']) / 3600.0).max()

    title = 'System-wise Node Allocation Gantt'
    if scenario_label:
        title = f'{title}\n{scenario_label}'
    fig.suptitle(title, fontsize=15, fontweight='bold')

    for idx, system in enumerate(systems):
        ax = axes[idx]
        system_df = gantt_df[gantt_df['ScheduledOn'] == system].copy()
        system_df = system_df.sort_values('StartTime')
        system_capacity = system_capacities.get(system, {}).get('nodes', 0)

        viz = GanttVisualization(ax, title=f'{system} Gantt')
        bulksetattr(viz, palette=generate_palette(max(8, len(system_df))))
        viz.draw_system(system_df, system, system_capacity, show_job_ids=show_job_ids)
        ax.set_xlim(global_start, global_end)

    if x_max_hours is not None:
        ticks = np.arange(0, x_max_hours + 0.1, 5)
        axes[-1].set_xticks(ticks)

    axes[-1].set_xlabel('Start Time (hours)', fontweight='bold', fontsize=11)

    if note_text:
        fig.text(
            0.01,
            0.01,
            note_text,
            ha='left',
            va='bottom',
            fontsize=9,
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.85),
        )

    plt.tight_layout(rect=[0, 0.02, 1, 0.97])
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ System Gantt plot saved to {output_path}")
    plt.close()



################
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze SWARM-DMAS simulation results')
    parser.add_argument('--csv_file','-c', default='../build/results/busy_homogeneous_short_700_PureLocal.csv', help='Path to CSV results file (default: ../build/results/busy_homogeneous_short_700_PureLocal.csv)')
    parser.add_argument('--output-dir', '-o', default='./plots/individual', help='Output root for plots (default: ./plots/individual)')
    parser.add_argument('--metrics-dir', '-m', default='./results', help='Output directory for metrics (default: ./results)')
    parser.add_argument('--gantt-note', default='', help='Custom note text box for Gantt figure (optional)')
    parser.add_argument('--hide-jobids', action='store_true', help='Hide job-id text labels from Gantt rectangles')
    parser.add_argument('--skip-gantt', action='store_true', help='Skip standalone per-mode Gantt chart generation')
    
    args = parser.parse_args()
    
    csv_path = Path(args.csv_file)
    csv_stem_parts = csv_path.stem.split('_')
    bidding_method = csv_stem_parts[-1]
    workload_name = '_'.join(csv_stem_parts[:-1])

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    utilization_output_dir = output_dir / 'utilization'
    
    # if results/centralized directory then put gantt into plots/individual/centralized/gantt/ otherwise plots/individual/decentarlized/gantt
    if 'centralized' in str(csv_path):
        gantt_output_dir = output_dir / 'gantt_centralized'
        run_mode = 'centralized'
    else:
        gantt_output_dir = output_dir / 'gantt_decentralized'
        run_mode = 'decentralized'
    utilization_output_dir.mkdir(exist_ok=True, parents=True)
    if not args.skip_gantt:
        gantt_output_dir.mkdir(exist_ok=True, parents=True)
    metrics_dir = Path(args.metrics_dir)
    metrics_dir.mkdir(exist_ok=True, parents=True)
    
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        print(f"Please run the simulation first to generate {csv_path.name}")
        return
    

    workload_fname = '_'.join(csv_path.stem.split('_')[:-1])  
    workload_path = Path(f'data_generation/data/{workload_fname}.json')
    print(f"Looking for workload file: {workload_fname} at {workload_path}")
    jobs_df = None
    
    if workload_path.exists():
        print(f"Loading job definitions from: {workload_path}")
        jobs_df = load_job_definitions(workload_path)
        print(f"Loaded {len(jobs_df)} job definitions")
    else:
        print(f"Warning: Workload file not found: {workload_path}")
    df = load_results(csv_path, jobs_df)
    total_jobs = len(df)
    df_valid = filter_successful_jobs(df)
    completed_jobs = len(df_valid)

    print(f"\nJobs Submitted: {total_jobs}")
    print(f"Jobs Completed: {completed_jobs}")
    print(f"Jobs Failed/Unscheduled: {total_jobs - completed_jobs}")
    
    system_capacities = BASE_SYSTEM_CAPACITIES
    results = run_sanity_checks(
        df=df,
        df_valid=df_valid,
        system_capacities=system_capacities,
        bidding_method=bidding_method,
        max_decision_time_sec=32.0,
        workload_name=workload_name,
    )

    # logs results under results/validation_logs.csv
    validation_logs_path = Path('results/validation_logs.csv')
    validation_logs_path.parent.mkdir(exist_ok=True, parents=True)
    if validation_logs_path.exists():
        validation_logs_df = pd.read_csv(validation_logs_path)
    else:
        validation_logs_df = pd.DataFrame()
    validation_logs_df = pd.concat([validation_logs_df, pd.DataFrame([results])], ignore_index=True)
    validation_logs_df.to_csv(validation_logs_path, index=False)
    print(f"✓ Validation logs updated: {validation_logs_path}")
    
    scenario_label = build_scenario_label(workload_name, bidding_method, run_mode)
    shared_xmax_hours, counterpart_csv = compute_shared_xmax_hours(csv_path, df_valid)
    if counterpart_csv is not None:
        print(f"Using shared x-axis scale: 0..{shared_xmax_hours:.1f}h (paired with {counterpart_csv})")
    else:
        print(f"Using x-axis scale from current CSV only: 0..{shared_xmax_hours:.1f}h")

    # Calculate makespan
    makespan = calculate_makespan(df_valid)
    
    # Print summary statistics
    print_summary_stats(df_valid, makespan)

    # Calculate, print and save per-system metrics
    per_system_metrics = calculate_per_system_metrics(df_valid, system_capacities)

    metrics_dir = metrics_dir / "metrics"
    metrics_dir.mkdir(exist_ok=True, parents=True)
    if per_system_metrics is not None:
        metrics_filename = (f"per_system_metrics_{workload_name}_{bidding_method}.csv")
        metrics_csv_path = metrics_dir / metrics_filename
        per_system_metrics.to_csv(metrics_csv_path, index=False)
        print(f"✓ Per-system metrics saved to {metrics_csv_path}")
    
    # Generate plots
    print("\nGenerating plots...")
    plot_utilization_percentage(
        df_valid,
        system_capacities,
        utilization_output_dir / f'utilisation_percentage_{workload_name}_{bidding_method}.png',
        x_max_hours=shared_xmax_hours,
    )
    if args.skip_gantt:
        print("Skipping standalone Gantt plot generation")
    else:
        plot_system_gantt(
            df_valid,
            system_capacities,
            gantt_output_dir / f'gantt_{workload_name}_{bidding_method}.png',
            note_text=args.gantt_note,
            scenario_label=scenario_label,
            show_job_ids=(not args.hide_jobids),
            x_max_hours=shared_xmax_hours,
        )

    thrhput = calculate_throughput(df_valid)
    print(f"\nThroughput: {thrhput:.2f} jobs/time unit")
    
    node_utili, storage_utili = calculate_resource_utilization(df, system_capacities)
    print(f"\nOverall Node Utilization: {node_utili}%")
    print(f"Overall Storage Utilization: {storage_utili}%")

    print("\n✓ Analysis complete!")

if __name__ == "__main__":
    main()
