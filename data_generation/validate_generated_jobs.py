import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# silent warnings
import warnings
warnings.filterwarnings("ignore")

def validate_jobs(jobs_df):
    for idx, row in jobs_df.iterrows():
        site = row['HPCSite']
        system = row['HPCSystem']
        site_configs = {
            'OLCF': ['Frontier', 'Andes'],
            'ALCF': ['Aurora', 'Crux'],
            'NERSC': ['Perlmutter-Phase-1', 'Perlmutter-Phase-2']
        }

        if system not in site_configs[site]:
            raise ValueError(f"Inconsistent HPCSite and HPCSystem for JobID {row['JobID']}: {site} - {system}")
        

    # check for resource limits
    site_resource_limits = {
        'OLCF': {
            'Frontier': {'node_limit': 9472, 'memory_limit': 12000, 'storage_limit': 700000000},
            'Andes': {'node_limit': 704, 'memory_limit': 256, 'storage_limit': 700000000}
        },
        'ALCF': {
            'Aurora': {'node_limit': 10624, 'memory_limit': 984, 'storage_limit': 220000000},
            'Crux': {'node_limit': 256, 'memory_limit': 512, 'storage_limit': 220000000}
        },
        'NERSC': {
            'Perlmutter-Phase-1': {'node_limit': 1536, 'memory_limit': 672, 'storage_limit': 35000000},
            'Perlmutter-Phase-2': {'node_limit': 3072, 'memory_limit': 512, 'storage_limit': 36000000}
        }
    }
    for idx, row in jobs_df.iterrows():
        site = row['HPCSite']
        system = row['HPCSystem']
        nodes = row['Nodes']
        memory = row['MemoryGB']
        storage = row['RequestedStorageGB']

        limits = site_resource_limits[site][system]
        if nodes > limits['node_limit']:
            raise ValueError(f"Node request exceeds limit for JobID {row['JobID']}: {nodes} > {limits['node_limit']}")
        if memory > limits['memory_limit'] * nodes:
            raise ValueError(f"Memory request exceeds limit for JobID {row['JobID']}: {memory} > {limits['memory_limit']}*{nodes}")
        if storage > limits['storage_limit']:
            raise ValueError(f"Storage request exceeds limit for JobID {row['JobID']}: {storage} > {limits['storage_limit']}")
    
 
    # check for has_gpu requirement
    for idx, row in jobs_df.iterrows():
        system = row['HPCSystem']
        requested_gpu = row['RequestedGPU']
        site = row['HPCSite']
        site_configs = {
            'OLCF': {
                'Frontier': {'has_gpu' : True},
                'Andes': {'has_gpu' : False}
            },
            'ALCF': {
                'Aurora': {'has_gpu' : True},
                'Crux': {'has_gpu' : False}
            },
            'NERSC': {
                'Perlmutter-Phase-1': {'has_gpu' : True},
                'Perlmutter-Phase-2': {'has_gpu' : False}
            }
        }
        
    # check if walltime, nodes, memory are positive
    for idx, row in jobs_df.iterrows():
        if row['Walltime'] <= 0:
            raise ValueError(f"Non-positive walltime for JobID {row['JobID']}: {row['Walltime']}")
        if row['Nodes'] <= 0:
            raise ValueError(f"Non-positive nodes for JobID {row['JobID']}: {row['Nodes']}")
        if row['MemoryGB'] <= 0:
            raise ValueError(f"Non-positive memory for JobID {row['JobID']}: {row['MemoryGB']}")
    
    # print all checks passed
    print("All job validations passed.")

# Visuale check
def visualize_job_distributions(jobs_df):
    # Visualize subplots of job characteristics

    fig, axs = plt.subplots(3, 2, figsize=(12, 10))
    sns.histplot(jobs_df['SubmissionTime'], bins=20, kde=True, ax=axs[0, 0], color='skyblue')
    axs[0, 0].set_title('Submission Time Distribution')
    sns.histplot(jobs_df['Walltime'], bins=20, kde=True, ax=axs[0, 1], color='salmon')
    axs[0, 1].set_title('Walltime Distribution')
    sns.histplot(jobs_df['Nodes'], bins=20, kde=True, ax=axs[1, 0], color='lightgreen')
    axs[1, 0].set_title('CPUs Distribution')
    sns.histplot(jobs_df['MemoryGB'], bins=20, kde=True, ax=axs[1, 1], color='plum')
    axs[1, 1].set_title('Memory Distribution (GB)') 
    # plot requested storage on log scale
    # sns.histplot(jobs_df['RequestedStorageGB'], bins=20, kde=True, ax=axs[0, 2], color='orange')
    # axs[2, 0].set_title('Storage Distribution (GB)')
    sns.countplot(data=jobs_df, x='HPCSite', order=jobs_df['HPCSite'].value_counts().index, ax=axs[2, 0], palette='pastel')
    axs[2, 0].set_title('HPC Site Distribution')
    # job type by hpc site
    sns.countplot(data=jobs_df, x='JobType', order=jobs_df['JobType'].value_counts().index, ax=axs[2, 1], palette='muted')
    axs[2, 1].set_title('Job Type by HPC Site')
    plt.tight_layout()
    plt.savefig('job_distributions.png')
    plt.show()


import matplotlib.pyplot as plt
import seaborn as sns

def visualize_submission_times_by_timezone(jobs_df):
    """Visualize job submission times across different timezones."""
    import matplotlib.pyplot as plt
    import seaborn as sns
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # 1. Timeline view of all submissions
    ax1 = axes[0, 0]
    for site in ['OLCF', 'ALCF', 'NERSC']:
        site_jobs = jobs_df[jobs_df['HPCSite'] == site]
        ax1.hist(site_jobs['SubmissionTime'], bins=30, alpha=0.5, label=f'{site}')
    ax1.axvline(x=12, color='red', linestyle='--', alpha=0.3, label='OLCF noon (EST)')
    ax1.axvline(x=13, color='green', linestyle='--', alpha=0.3, label='ALCF noon (CST)')
    ax1.axvline(x=15, color='blue', linestyle='--', alpha=0.3, label='NERSC noon (PST)')
    ax1.set_xlabel('Time (hours from start)')
    ax1.set_ylabel('Number of Jobs')
    ax1.set_title('Job Submissions Across 27-Hour Period')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. Density plot
    ax2 = axes[0, 1]
    for site in ['OLCF', 'ALCF', 'NERSC']:
        site_jobs = jobs_df[jobs_df['HPCSite'] == site]
        site_jobs['SubmissionTime'].plot(kind='density', ax=ax2, label=site, linewidth=2)
    ax2.set_xlabel('Time (hours from start)')
    ax2.set_ylabel('Density')
    ax2.set_title('Submission Time Density by Site')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. Box plot by site
    ax3 = axes[1, 0]
    sites_data = [jobs_df[jobs_df['HPCSite'] == site]['SubmissionTime'].values 
                  for site in ['OLCF', 'ALCF', 'NERSC']]
    bp = ax3.boxplot(sites_data, labels=['OLCF (EST)', 'ALCF (CST)', 'NERSC (PST)'])
    ax3.set_ylabel('Submission Time (hours)')
    ax3.set_title('Submission Time Distribution by Site')
    ax3.grid(True, alpha=0.3, axis='y')
    
    # 4. Cumulative distribution
    ax4 = axes[1, 1]
    for site, color in zip(['OLCF', 'ALCF', 'NERSC'], ['red', 'green', 'blue']):
        site_jobs = jobs_df[jobs_df['HPCSite'] == site].sort_values('SubmissionTime')
        ax4.plot(site_jobs['SubmissionTime'], 
                np.arange(1, len(site_jobs)+1) / len(site_jobs),
                label=site, linewidth=2, color=color)
    ax4.set_xlabel('Time (hours from start)')
    ax4.set_ylabel('Cumulative Proportion')
    ax4.set_title('Cumulative Job Arrivals by Site')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    # plt.savefig('./data/submission_times_by_timezone.png', dpi=300, bbox_inches='tight')
    # print("Saved submission time visualization to ./data/submission_times_by_timezone.png")
    plt.show()
    # plt.close()
    
    # Print statistics
    print("\nSubmission Time Statistics by Site:")
    for site in ['OLCF', 'ALCF', 'NERSC']:
        site_jobs = jobs_df[jobs_df['HPCSite'] == site]
        print(f"\n{site}:")
        print(f"  Count: {len(site_jobs)}")
        print(f"  Mean: {site_jobs['SubmissionTime'].mean():.2f}h")
        print(f"  Std: {site_jobs['SubmissionTime'].std():.2f}h")
        print(f"  Min: {site_jobs['SubmissionTime'].min():.2f}h")
        print(f"  Max: {site_jobs['SubmissionTime'].max():.2f}h")
        print(f"  Median: {site_jobs['SubmissionTime'].median():.2f}h")


##################### 
# deprecated function
#####################
def visualize_submission_times(jobs_df, save_path=None):
    """Visualize submission time distributions across timezones"""
    
    # Get the actual time range from the data
    min_time = jobs_df['SubmissionTime'].min()
    max_time = jobs_df['SubmissionTime'].max()
    time_span = max_time - min_time
    
    print(f"Actual time range: {min_time:.2f}h to {max_time:.2f}h (span: {time_span:.2f}h)")
    
    # Create figure with multiple subplots
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(f'Job Submission Time Distributions Over {time_span:.1f}-Hour Period', fontsize=16)
    
    # Define timezone mappings for sites
    site_timezones = {
        'OLCF': {'name': 'EST', 'offset': 0},
        'ALCF': {'name': 'CST', 'offset': -1}, 
        'NERSC': {'name': 'PST', 'offset': -3}
    }
    
    # Calculate appropriate number of bins based on time span
    n_bins = max(20, int(time_span))  # At least 20 bins, or 1 bin per hour
    
    # Plot 1: Overall submission distribution (EST time)
    ax1 = axes[0, 0]
    ax1.hist(jobs_df['SubmissionTime'], bins=n_bins, alpha=0.7, edgecolor='black', color='steelblue')
    ax1.set_xlabel('EST Time (hours)')
    ax1.set_ylabel('Number of Jobs')
    ax1.set_title('All Jobs - EST Timeline')
    ax1.grid(True, alpha=0.3)
    
    # FIXED: Use actual time range instead of hardcoded 24 hours
    # Create time labels based on actual range
    tick_interval = max(2, int(time_span / 10))  # Show ~10 ticks
    hours = np.arange(0, max_time + tick_interval, tick_interval)
    time_labels = [f"{h:02.0f}:00" for h in hours]
    ax1.set_xticks(hours)
    ax1.set_xticklabels(time_labels, rotation=45)
    ax1.set_xlim(min_time, max_time)
    
    # Plot 2: Distribution by site (EST time)
    ax2 = axes[0, 1]
    colors = ['red', 'green', 'blue']
    for i, site in enumerate(['OLCF', 'ALCF', 'NERSC']):
        site_jobs = jobs_df[jobs_df['HPCSite'] == site]
        if len(site_jobs) > 0:
            ax2.hist(site_jobs['SubmissionTime'], bins=n_bins//2, alpha=0.6, 
                    label=f"{site} ({len(site_jobs)} jobs)", color=colors[i])
    
    ax2.set_xlabel('EST Time (hours)')
    ax2.set_ylabel('Number of Jobs')
    ax2.set_title('Jobs by Site - EST Timeline')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(hours)
    ax2.set_xticklabels(time_labels, rotation=45)
    ax2.set_xlim(min_time, max_time)
    
    # Plot 3: Local time distributions (FIXED: Handle 27-hour period)
    ax3 = axes[1, 0]
    for i, (site, tz_info) in enumerate(site_timezones.items()):
        site_jobs = jobs_df[jobs_df['HPCSite'] == site]
        if len(site_jobs) > 0:
            # Convert EST times to local times - DON'T use modulo for 27-hour period
            local_times = site_jobs['SubmissionTime'] + tz_info['offset']
            ax3.hist(local_times, bins=n_bins//2, alpha=0.6, 
                    label=f"{site} ({tz_info['name']})", color=colors[i])
    
    ax3.set_xlabel('Local Time (hours)')
    ax3.set_ylabel('Number of Jobs')
    ax3.set_title('Jobs by Site - Local Timezone')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # FIXED: Local time axis should also extend beyond 24h
    local_hours = np.arange(-3, max_time + 3, tick_interval)  # Account for timezone offsets
    local_time_labels = [f"{h:02.0f}:00" for h in local_hours if h >= 0]
    ax3.set_xticks([h for h in local_hours if h >= 0])
    ax3.set_xticklabels(local_time_labels, rotation=45)
    
    # Plot 4: System-level distribution
    ax4 = axes[1, 1]
    systems = jobs_df['HPCSystem'].unique()
    system_colors = plt.cm.Set3(np.linspace(0, 1, len(systems)))
    
    for i, system in enumerate(systems):
        system_jobs = jobs_df[jobs_df['HPCSystem'] == system]
        if len(system_jobs) > 0:
            ax4.hist(system_jobs['SubmissionTime'], bins=n_bins//3, alpha=0.6,
                    label=f"{system} ({len(system_jobs)})", color=system_colors[i])
    
    ax4.set_xlabel('EST Time (hours)')
    ax4.set_ylabel('Number of Jobs')
    ax4.set_title('Jobs by System - EST Timeline')
    ax4.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax4.grid(True, alpha=0.3)
    ax4.set_xticks(hours)
    ax4.set_xticklabels(time_labels, rotation=45)
    ax4.set_xlim(min_time, max_time)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
    
    plt.show()
    
    # FIXED: Print statistics for actual time range
    print("\n=== SUBMISSION TIME STATISTICS ===")
    print(f"Total jobs: {len(jobs_df)}")
    print(f"Time span: {min_time:.2f}h to {max_time:.2f}h ({time_span:.2f}h total)")
    
    print("\nJobs by site:")
    for site in ['OLCF', 'ALCF', 'NERSC']:
        site_jobs = len(jobs_df[jobs_df['HPCSite'] == site])
        percentage = 100 * site_jobs / len(jobs_df)
        print(f"  {site}: {site_jobs} jobs ({percentage:.1f}%)")
    
    print(f"\nPeak submission hours (EST) over {time_span:.0f}-hour period:")
    # FIXED: Check peaks over actual time range, not just 24 hours
    for hour in range(int(min_time), int(max_time) + 1):
        hour_jobs = len(jobs_df[(jobs_df['SubmissionTime'] >= hour) & 
                               (jobs_df['SubmissionTime'] < hour + 1)])
        if hour_jobs > len(jobs_df) * 0.05:  # Show hours with >5% of jobs
            print(f"  {hour:02d}:00-{hour+1:02d}:00: {hour_jobs} jobs ({100*hour_jobs/len(jobs_df):.1f}%)")


    """Visualize job submission times across different timezones."""
    import matplotlib.pyplot as plt
    import seaborn as sns
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # 1. Timeline view of all submissions
    ax1 = axes[0, 0]
    for site in ['OLCF', 'ALCF', 'NERSC']:
        site_jobs = jobs_df[jobs_df['HPCSite'] == site]
        ax1.hist(site_jobs['SubmissionTime'], bins=30, alpha=0.5, label=f'{site}')
    ax1.axvline(x=12, color='red', linestyle='--', alpha=0.3, label='OLCF noon (EST)')
    ax1.axvline(x=13, color='green', linestyle='--', alpha=0.3, label='ALCF noon (CST)')
    ax1.axvline(x=15, color='blue', linestyle='--', alpha=0.3, label='NERSC noon (PST)')
    ax1.set_xlabel('Time (hours from start)')
    ax1.set_ylabel('Number of Jobs')
    ax1.set_title('Job Submissions Across 27-Hour Period')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. Density plot
    ax2 = axes[0, 1]
    for site in ['OLCF', 'ALCF', 'NERSC']:
        site_jobs = jobs_df[jobs_df['HPCSite'] == site]
        site_jobs['SubmissionTime'].plot(kind='density', ax=ax2, label=site, linewidth=2)
    ax2.set_xlabel('Time (hours from start)')
    ax2.set_ylabel('Density')
    ax2.set_title('Submission Time Density by Site')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. Box plot by site
    ax3 = axes[1, 0]
    sites_data = [jobs_df[jobs_df['HPCSite'] == site]['SubmissionTime'].values 
                  for site in ['OLCF', 'ALCF', 'NERSC']]
    bp = ax3.boxplot(sites_data, labels=['OLCF (EST)', 'ALCF (CST)', 'NERSC (PST)'])
    ax3.set_ylabel('Submission Time (hours)')
    ax3.set_title('Submission Time Distribution by Site')
    ax3.grid(True, alpha=0.3, axis='y')
    
    # 4. Cumulative distribution
    ax4 = axes[1, 1]
    for site, color in zip(['OLCF', 'ALCF', 'NERSC'], ['red', 'green', 'blue']):
        site_jobs = jobs_df[jobs_df['HPCSite'] == site].sort_values('SubmissionTime')
        ax4.plot(site_jobs['SubmissionTime'], 
                np.arange(1, len(site_jobs)+1) / len(site_jobs),
                label=site, linewidth=2, color=color)
    ax4.set_xlabel('Time (hours from start)')
    ax4.set_ylabel('Cumulative Proportion')
    ax4.set_title('Cumulative Job Arrivals by Site')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('./data/submission_times_by_timezone.png', dpi=300, bbox_inches='tight')
    print("Saved submission time visualization to ./data/submission_times_by_timezone.png")
    plt.close()
    
    # Print statistics
    print("\nSubmission Time Statistics by Site:")
    for site in ['OLCF', 'ALCF', 'NERSC']:
        site_jobs = jobs_df[jobs_df['HPCSite'] == site]
        print(f"\n{site}:")
        print(f"  Count: {len(site_jobs)}")
        print(f"  Mean: {site_jobs['SubmissionTime'].mean():.2f}h")
        print(f"  Std: {site_jobs['SubmissionTime'].std():.2f}h")
        print(f"  Min: {site_jobs['SubmissionTime'].min():.2f}h")
        print(f"  Max: {site_jobs['SubmissionTime'].max():.2f}h")
        print(f"  Median: {site_jobs['SubmissionTime'].median():.2f}h")
