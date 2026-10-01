# capacity_analysis.py
import argparse
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# System configurations
SYSTEM_CONFIGS = {
    'OLCF': {
        'Frontier': {'nodes': 9472, 'has_gpu': True},
        'Andes': {'nodes': 704, 'has_gpu': False}
    },
    'ALCF': {
        'Aurora': {'nodes': 10624, 'has_gpu': True},
        'Crux': {'nodes': 256, 'has_gpu': False}
    },
    'NERSC': {
        'Perlmutter-Phase-1': {'nodes': 1536, 'has_gpu': True},
        'Perlmutter-Phase-2': {'nodes': 3072, 'has_gpu': False}
    }
}

def convert_to_df(workload_file):
    with open(workload_file) as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    return df


def plot_max_node_demand_over_time(df, save_path='max_node_demand_over_time.png', title='workload', sfactor=1.0):
    """
    Plot the maximum number of requested nodes over time for each job type.
    Shows concurrent node demand as jobs execute.

    Args:
        sfactor: scale divisor matching job_generation --sfactor. Divides all system node
                 counts so capacity lines align with a scaled-down workload.
    """
    sfactor = max(float(sfactor), 1e-9)
    # Calculate total capacity across all systems (scaled to match the workload).
    total_capacity = sum(
        config['nodes']
        for site in SYSTEM_CONFIGS.values()
        for config in site.values()
    ) / sfactor

    # SubmissionTime and Walltime are stored in seconds by job_generation; convert to hours.
    df = df.copy()
    df['SubmissionTime'] = df['SubmissionTime'] / 3600.0
    df['Walltime'] = df['Walltime'] / 3600.0
    df['EndTime'] = df['SubmissionTime'] + df['Walltime']
    
    # Create time grid from first submission to last job completion
    min_time = df['SubmissionTime'].min()
    max_time = df['EndTime'].max()
    time_resolution = 0.5  # hours
    time_grid = np.arange(min_time, max_time + time_resolution, time_resolution)
    
    # Get unique job types
    job_types = df['JobType'].unique()
    
    # Calculate node demand at each time point for each job type
    demand_by_type = {jt: [] for jt in job_types}
    total_demand = []
    
    for t in time_grid:
        # Find jobs active at time t (submitted but not finished)
        active_jobs = df[(df['SubmissionTime'] <= t) & (df['EndTime'] > t)]
        
        # Total demand
        total_demand.append(active_jobs['Nodes'].sum())
        
        # Demand by job type
        for job_type in job_types:
            type_jobs = active_jobs[active_jobs['JobType'] == job_type]
            demand_by_type[job_type].append(type_jobs['Nodes'].sum())
    
    # Find overall peak
    peak_demand = max(total_demand)
    peak_idx = total_demand.index(peak_demand)
    peak_time = time_grid[peak_idx]
    
    # Print statistics
    print("\n" + "="*70)
    print("MAXIMUM NODE DEMAND OVER TIME BY JOB TYPE")
    print("="*70)
    sf_note = f"  (full-scale / {sfactor:g})" if sfactor != 1.0 else ""
    print(f"Total system capacity:        {total_capacity:,.0f} nodes{sf_note}")
    print(f"Peak concurrent node demand:  {peak_demand:,} nodes")
    print(f"Time at peak:                 {peak_time:.2f} hours")
    print(f"Peak as % of capacity:        {(peak_demand/total_capacity)*100:.1f}%")
    
    print(f"\nPeak demand by job type:")
    for job_type in job_types:
        type_peak = max(demand_by_type[job_type])
        type_peak_idx = demand_by_type[job_type].index(type_peak)
        type_peak_time = time_grid[type_peak_idx]
        print(f"  {job_type:8s}: {type_peak:,} nodes @ {type_peak_time:.2f}h")
    
    if peak_demand > total_capacity:
        excess = peak_demand - total_capacity
        print(f"\n⚠️  WARNING: Peak demand EXCEEDS capacity by {excess:,} nodes!")
    else:
        headroom = total_capacity - peak_demand
        print(f"\n✓  Peak demand is within capacity")
        print(f"   Available headroom: {headroom:,} nodes ({(headroom/total_capacity)*100:.1f}%)")
    print("="*70 + "\n")
    
    # Create plot
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    
    # Plot 1: Total demand + by job type (stacked or separate lines)
    ax1 = axes[0]
    
    # Plot each job type
    colors = {'HPC': 'blue', 'AI': 'green', 'HYBRID': 'orange', 'STORAGE': 'purple'}
    for job_type in job_types:
        color = colors.get(job_type, 'gray')
        ax1.plot(time_grid, demand_by_type[job_type], linewidth=2, 
                label=f'{job_type}', alpha=0.7, color=color)
    
    # Add total capacity line
    ax1.axhline(y=total_capacity, color='red', linestyle='--', linewidth=2, 
                label=f'Total Capacity ({total_capacity:,} nodes)')
    
    ax1.set_xlabel('Time (hours)', fontsize=12)
    ax1.set_ylabel('Concurrent Node Demand', fontsize=12)
    ax1.set_title(f'Maximum Requested Nodes Over Time by Job Type - {title}', fontsize=14, fontweight='bold')
    ax1.legend(fontsize=10, loc='best')
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Total demand (all job types combined)
    ax2 = axes[1]
    
    ax2.plot(time_grid, total_demand, linewidth=2, color='blue', label='Total Concurrent Demand')
    ax2.fill_between(time_grid, 0, total_demand, alpha=0.3, color='blue')
    
    # Add total capacity line
    ax2.axhline(y=total_capacity, color='red', linestyle='--', linewidth=2, 
                label=f'Total Capacity ({total_capacity:,} nodes)')
    
    # Mark peak
    ax2.scatter([peak_time], [peak_demand], color='red', s=300, zorder=5, 
                marker='*', edgecolors='black', linewidths=2,
                label=f'Peak: {peak_demand:,} nodes @ {peak_time:.1f}h')
    
    ax2.set_xlabel('Time (hours)', fontsize=12)
    ax2.set_ylabel('Total Concurrent Node Demand', fontsize=12)
    ax2.set_title(f'Total Maximum Requested Nodes Over Time - {title}', fontsize=14, fontweight='bold')
    ax2.legend(fontsize=10, loc='best')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved max node demand plot to {save_path}")
    plt.close()



def plot_max_node_demand_by_system(df, save_path='max_node_demand_by_system.png', title='workload', sfactor=1.0):
    """
    Plot the maximum number of requested nodes over time for each of the 6 systems.
    Shows concurrent node demand as jobs execute on each system.

    Args:
        sfactor: scale divisor matching job_generation --sfactor. Divides all system node
                 counts so capacity lines align with a scaled-down workload.
    """
    sfactor = max(float(sfactor), 1e-9)
    # SubmissionTime and Walltime are stored in seconds by job_generation; convert to hours.
    df = df.copy()
    df['SubmissionTime'] = df['SubmissionTime'] / 3600.0
    df['Walltime'] = df['Walltime'] / 3600.0
    df['EndTime'] = df['SubmissionTime'] + df['Walltime']
    
    # Create time grid from first submission to last job completion
    min_time = df['SubmissionTime'].min()
    max_time = df['EndTime'].max()
    time_resolution = 0.5  # hours
    time_grid = np.arange(min_time, max_time + time_resolution, time_resolution)
    
    # Get all systems
    systems = ['Frontier', 'Andes', 'Aurora', 'Crux', 'Perlmutter-Phase-1', 'Perlmutter-Phase-2']
    
    # Calculate node demand at each time point for each system
    demand_by_system = {sys: [] for sys in systems}
    total_demand = []
    
    for t in time_grid:
        # Find jobs active at time t (submitted but not finished)
        active_jobs = df[(df['SubmissionTime'] <= t) & (df['EndTime'] > t)]
        
        # Total demand
        total_demand.append(active_jobs['Nodes'].sum())
        
        # Demand by system (based on submission system)
        for system in systems:
            sys_jobs = active_jobs[active_jobs['HPCSystem'] == system]
            demand_by_system[system].append(sys_jobs['Nodes'].sum())
    
    # Find overall peak
    peak_demand = max(total_demand)
    peak_idx = total_demand.index(peak_demand)
    peak_time = time_grid[peak_idx]
    
    # Print statistics
    print("\n" + "="*70)
    print("MAXIMUM NODE DEMAND OVER TIME BY SYSTEM")
    print("="*70)
    
    sf_note = f"  (x1/{sfactor:g} scale)" if sfactor != 1.0 else ""
    print(f"\nSystem Capacities{sf_note}:")
    for site, systems_dict in SYSTEM_CONFIGS.items():
        for system, config in systems_dict.items():
            scaled = config['nodes'] / sfactor
            print(f"  {system:22s}: {scaled:,.0f} nodes  (raw: {config['nodes']:,})")

    total_capacity = sum(config['nodes'] for site in SYSTEM_CONFIGS.values()
                        for config in site.values()) / sfactor
    print(f"  {'TOTAL':22s}: {total_capacity:,.0f} nodes")
    
    print(f"\nPeak concurrent demand by system:")
    for system in systems:
        sys_peak = max(demand_by_system[system])
        sys_peak_idx = demand_by_system[system].index(sys_peak)
        sys_peak_time = time_grid[sys_peak_idx]
        
        # Get system capacity (scaled).
        sys_capacity = None
        for site in SYSTEM_CONFIGS.values():
            if system in site:
                sys_capacity = site[system]['nodes'] / sfactor
                break

        utilization = (sys_peak / sys_capacity * 100) if sys_capacity else 0
        print(f"  {system:22s}: {sys_peak:,} nodes @ {sys_peak_time:.2f}h ({utilization:.1f}% of capacity)")
    
    print(f"\nOverall peak demand: {peak_demand:,} nodes @ {peak_time:.2f}h")
    print("="*70 + "\n")
    
    # Create plot with 3 subplots
    fig, axes = plt.subplots(3, 1, figsize=(16, 14))
    
    # Plot 1: Individual system demands with their capacity lines
    ax1 = axes[0]
    
    colors = {
        'Frontier': 'darkred', 
        'Andes': 'lightcoral',
        'Aurora': 'darkgreen', 
        'Crux': 'lightgreen',
        'Perlmutter-Phase-1': 'darkblue', 
        'Perlmutter-Phase-2': 'lightblue'
    }
    
    for system in systems:
        color = colors.get(system, 'gray')
        
        # Get system capacity (scaled).
        sys_capacity = None
        for site in SYSTEM_CONFIGS.values():
            if system in site:
                sys_capacity = site[system]['nodes'] / sfactor
                break

        # Plot demand
        ax1.plot(time_grid, demand_by_system[system], linewidth=2,
                label=f'{system}', alpha=0.8, color=color)

        # Plot capacity line
        if sys_capacity:
            ax1.axhline(y=sys_capacity, color=color, linestyle='--', alpha=0.3, linewidth=1)
    
    ax1.set_xlabel('Time (hours)', fontsize=12)
    ax1.set_ylabel('Concurrent Node Demand', fontsize=12)
    ax1.set_title(f'Maximum Requested Nodes Over Time by System (with Individual Capacities) - {title}', 
                  fontsize=14, fontweight='bold')
    ax1.legend(fontsize=9, loc='upper right', ncol=2)
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Systems grouped by site
    ax2 = axes[1]
    
    # Calculate demand by site
    site_demand = {'OLCF': [], 'ALCF': [], 'NERSC': []}
    site_capacities = {}
    
    for site, systems_dict in SYSTEM_CONFIGS.items():
        site_capacities[site] = sum(config['nodes'] for config in systems_dict.values()) / sfactor
    
    for t_idx, t in enumerate(time_grid):
        for site in ['OLCF', 'ALCF', 'NERSC']:
            site_systems = list(SYSTEM_CONFIGS[site].keys())
            site_total = sum(demand_by_system[sys][t_idx] for sys in site_systems)
            site_demand[site].append(site_total)
    
    site_colors = {'OLCF': 'red', 'ALCF': 'green', 'NERSC': 'blue'}
    
    for site in ['OLCF', 'ALCF', 'NERSC']:
        color = site_colors[site]
        ax2.plot(time_grid, site_demand[site], linewidth=2.5, 
                label=f'{site}', color=color, alpha=0.8)
        ax2.axhline(y=site_capacities[site], color=color, linestyle='--', 
                   alpha=0.4, linewidth=2)
    
    ax2.set_xlabel('Time (hours)', fontsize=12)
    ax2.set_ylabel('Concurrent Node Demand', fontsize=12)
    ax2.set_title(f'Maximum Requested Nodes Over Time by Site (with Site Capacities) - {title}', 
                  fontsize=14, fontweight='bold')
    ax2.legend(fontsize=10, loc='best')
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Total demand across all systems
    ax3 = axes[2]
    
    ax3.plot(time_grid, total_demand, linewidth=2.5, color='blue', label='Total Demand')
    ax3.fill_between(time_grid, 0, total_demand, alpha=0.3, color='blue')
    
    # Add total capacity line
    ax3.axhline(y=total_capacity, color='red', linestyle='--', linewidth=2, 
                label=f'Total Capacity ({total_capacity:,} nodes)')
    
    # Mark peak
    ax3.scatter([peak_time], [peak_demand], color='red', s=300, zorder=5, 
                marker='*', edgecolors='black', linewidths=2,
                label=f'Peak: {peak_demand:,} nodes @ {peak_time:.1f}h')
    
    ax3.set_xlabel('Time (hours)', fontsize=12)
    ax3.set_ylabel('Total Concurrent Node Demand', fontsize=12)
    ax3.set_title(f'Total Maximum Requested Nodes Over Time (All Systems) - {title}', 
                  fontsize=14, fontweight='bold')
    ax3.legend(fontsize=10, loc='best')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved system-level max node demand plot to {save_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze node capacity vs. demand for a workload JSON file."
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Path to workload JSON file.")
    parser.add_argument(
        "--sfactor", type=float, default=1.0,
        help="Scale divisor matching job_generation --sfactor (default: 1.0). "
             "Divides SYSTEM_CONFIGS node counts so capacity lines match a scaled-down workload.",
    )
    parser.add_argument("--output-dir", "-o", default="plots/",
                        help="Directory to save plots (default: plots/).")
    parser.add_argument("--title", default=None,
                        help="Plot title prefix. Defaults to the input file stem.")
    args = parser.parse_args()

    sfactor = max(float(args.sfactor), 1e-9)
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    title = args.title or input_path.stem
    df = convert_to_df(str(input_path))

    r_tag = f"{sfactor:g}".replace(".", "p")
    stem = input_path.stem

    plot_max_node_demand_over_time(
        df,
        save_path=str(output_dir / f"{stem}_job_type_demand_r{r_tag}.png"),
        title=title,
        sfactor=sfactor,
    )
    plot_max_node_demand_by_system(
        df,
        save_path=str(output_dir / f"{stem}_system_demand_r{r_tag}.png"),
        title=title,
        sfactor=sfactor,
    )


if __name__ == "__main__":
    main()