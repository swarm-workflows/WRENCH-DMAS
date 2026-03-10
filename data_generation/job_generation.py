import argparse
import json
import os
import random
from typing import Dict, Tuple, Optional

import numpy as np
import pandas as pd

# ----------------------------
# Helpers
# ----------------------------

def _normalize_probs(d: Dict[str, float]) -> Dict[str, float]:
    s = sum(float(v) for v in d.values())
    if s <= 0:
        raise ValueError("jobtype_proportions must sum to > 0")
    return {k: float(v) / s for k, v in d.items()}

def _parse_json_arg(s: str) -> Dict:
    try:
        return json.loads(s)
    except Exception as e:
        raise ValueError(f"Invalid JSON arg: {s}. Error: {e}")

def _scenario_short_frac(scenario: str) -> float:
    if scenario == "homogeneous_short":
        return 0.95
    if scenario == "only_large_long":
        return 0.05
    if scenario == "mixed_80_20":
        return 0.80
    if scenario == "mixed_20_80":
        return 0.20
    return 0.80

def _sample_log_uniform_int(rng: random.Random, lo: int, hi: int) -> int:
    lo = max(1, int(lo))
    hi = max(lo, int(hi))
    return int(round(np.exp(rng.uniform(np.log(lo), np.log(hi)))))

def _busy_day_times_by_site(n_jobs: int, sites: list, seed: int = 42) -> np.ndarray:
    """
    Busy day: for each site, draw local-time submissions ~ Normal(noon, 4h),
    then map into a shared timeline with offsets (EST=0, CST=+1, PST=+3).
    Output is sorted times in HOURS.
    """
    rng = np.random.default_rng(seed)
    tz = {'OLCF': 0, 'ALCF': 1, 'NERSC': 3}  # offsets in hours

    sites_arr = np.array(sites, dtype=object)
    all_times = []

    for site, offset in tz.items():
        cnt = int(np.sum(sites_arr == site))
        if cnt == 0:
            continue
        peak = 12.0 + offset
        t = rng.normal(loc=peak, scale=4.0, size=cnt)
        t = np.clip(t, offset, offset + 24.0)
        all_times.extend(t.tolist())

    submission_times = np.array(sorted(all_times), dtype=float)
    if len(submission_times) != n_jobs:
        # fallback safety
        submission_times = np.sort(rng.uniform(0, 24.0, size=n_jobs))
    return submission_times

def _idle_day_times(n_jobs: int, seed: int = 42) -> np.ndarray:
    """
    Idle/sparse: long gaps + small bursts (heavy-tailed inter-arrival).
    Returns sorted times in HOURS within [0,24].
    """
    rng = np.random.default_rng(seed)
    day_minutes = 24 * 60

    times = []
    t = 0.0
    while len(times) < n_jobs and t < day_minutes:
        if rng.random() < 0.7:
            gap = rng.lognormal(mean=4.0, sigma=0.8)  # long gaps (minutes)
        else:
            gap = rng.exponential(scale=8.0)          # short gaps (minutes)
        t += gap
        if t <= day_minutes:
            times.append(t)

    while len(times) < n_jobs:
        times.append(rng.uniform(0, day_minutes))

    times = np.array(sorted(times[:n_jobs]), dtype=float) / 60.0
    return times

# ----------------------------
# Per-job-type size bands
# ----------------------------

JOB_TYPE_BANDS = {
    "HPC": {
        "small_nodes": (1, 64),
        "large_nodes": (256, 2048),
        "short_wall": (0.25, 4),   # hours
        "long_wall": (12, 72),     # hours
        "small_storage": (50, 10_000),      # GB - small HPC jobs
        "large_storage": (5_000, 50_000)     
    },
    "AI": {
        "small_nodes": (1, 16),
        "large_nodes": (256, 1024),  # up to 1024 can be allowed if you want
        "short_wall": (1, 12),
        "long_wall": (12, 120),
        "small_storage": (500, 50_000),     # GB - small AI jobs (datasets, models)
        "large_storage": (10_000, 200_000)  # GB - large AI jobs (large models, training data)

    },
    "HYBRID": {
        "small_nodes": (1, 32),
        "large_nodes": (256, 1024),
        "short_wall": (1, 12),
        "long_wall": (12, 120),
        "small_storage": (100, 20_000),     # GB - small hybrid jobs
        "large_storage": (5_000, 100_000)   # GB - large hybrid jobs
    },
    "STORAGE": {
        "small_nodes": (1, 16),
        "large_nodes": (256, 1024),
        "short_wall": (0.25, 6),
        "long_wall": (6, 24),
        "small_storage": (10_000, 100_000),  # GB - small storage jobs (still substantial)
        "large_storage": (50_000, 500_000)   # GB - large storage jobs (massive I/O)
    },
}

# ----------------------------
# Main generator
# ----------------------------

def generate_synthetic_jobs_v3(
    n_jobs: int = 100,
    seed: int = 42,
    day: str = "busy",  # busy|idle
    scenario: str = "mixed_80_20",
    jobs_per_site: Optional[Dict[str, int]] = None,
    jobtype_proportions: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:

    if seed > 0:
        random.seed(seed)
        np.random.seed(seed)

    # Sites + machines (your configs)
    site_configs = {
        'OLCF': {'machines': {
            'Frontier': {'type': 'HPC', 'has_gpu': True,  'node_limit': 9472,  'memory_limit': 12000, 'storage_limit': 700000000},
            'Andes':    {'type': 'STORAGE', 'has_gpu': False,'node_limit': 704,   'memory_limit': 256,   'storage_limit': 700000000}
        }},
        'ALCF': {'machines': {
            'Aurora': {'type': 'AI', 'has_gpu': True,      'node_limit': 10624, 'memory_limit': 984,   'storage_limit': 220000000},
            'Crux':   {'type': 'STORAGE','has_gpu': False, 'node_limit': 256,   'memory_limit': 512,   'storage_limit': 220000000}
        }},
        'NERSC': {'machines': {
            'Perlmutter-Phase-1': {'type': 'HYBRID', 'has_gpu': True,  'node_limit': 1536, 'memory_limit': 672, 'storage_limit': 35000000},
            'Perlmutter-Phase-2': {'type': 'HYBRID', 'has_gpu': False, 'node_limit': 3072, 'memory_limit': 512, 'storage_limit': 36000000}
        }},
    }

    job_types = ['HPC', 'AI', 'HYBRID', 'STORAGE']

    if jobtype_proportions is None:
        jobtype_proportions = {"HPC": 0.3, "AI": 0.3, "HYBRID": 0.25, "STORAGE": 0.15}
    jobtype_proportions = _normalize_probs(jobtype_proportions)
    proportions = [jobtype_proportions[jt] for jt in job_types]

    # jobs_per_site defaults
    if jobs_per_site is None:
        base = n_jobs // 3
        remainder = n_jobs % 3
        jobs_per_site = {
            "OLCF": base + (1 if remainder > 0 else 0),
            "ALCF": base + (1 if remainder > 1 else 0),
            "NERSC": base
        }
    else:
        # If custom jobs_per_site provided, override n_jobs to match it
        n_jobs = sum(jobs_per_site.values())
        print(f"Note: Using custom jobs_per_site with total {n_jobs} jobs")
    # verify the sum matches n_jobs
    if sum(jobs_per_site.values()) != n_jobs:
        raise ValueError(f"jobs_per_site must sum to n_jobs. Got {sum(jobs_per_site.values())} vs {n_jobs}")
   

    # Build origin sites list
    origin_sites = []
    
    for site, cnt in jobs_per_site.items():
        if site not in site_configs:
            raise ValueError(f"Unknown site in jobs_per_site: {site}")
        origin_sites.extend([site] * int(cnt))
    random.shuffle(origin_sites)

    # Pick origin system within each site
    origin_systems = []
    for site in origin_sites:
        origin_systems.append(random.choice(list(site_configs[site]["machines"].keys())))

    # Submission times
    if day == "busy":
        submission_times = _busy_day_times_by_site(n_jobs, origin_sites, seed=seed)  # hours
    elif day == "idle":
        submission_times = _idle_day_times(n_jobs, seed=seed)  # hours
    else:
        raise ValueError("day must be 'busy' or 'idle'")

    # Scenario mixing
    short_frac = _scenario_short_frac(scenario)

    # Generate job types
    types = random.choices(job_types, weights=proportions, k=n_jobs)

    # Arrays
    job_ids = np.arange(1, n_jobs + 1)
    walltimes_min = np.zeros(n_jobs, dtype=int)
    nodes = np.zeros(n_jobs, dtype=int)
    memories = np.zeros(n_jobs, dtype=float)
    requested_gpus = np.zeros(n_jobs, dtype=bool)
    requested_storages = np.zeros(n_jobs, dtype=float)

    # Generate per job
    rng = random.Random(seed + 123)
    for i in range(n_jobs):
        jt = types[i]
        bands = JOB_TYPE_BANDS[jt]

        is_short = (rng.random() < short_frac)

        # GPU policy - determine first
        if jt == "AI":
            job_gpu = True
        elif jt == "STORAGE":
            job_gpu = False
        else:
            job_gpu = (rng.random() < (0.5 if jt == "HYBRID" else 0.3))  # hybrid more likely GPU than HPC

        # Filter systems based on job type and GPU requirement
        if jt == 'AI':
            # AI jobs ALWAYS need GPU
            available_systems = ['Frontier', 'Aurora', 'Perlmutter-Phase-1']
        elif jt == 'STORAGE':
            # STORAGE jobs NEVER need GPU - can go anywhere but no GPU systems
            available_systems = ['Frontier', 'Andes', 'Aurora', 'Crux', 'Perlmutter-Phase-1', 'Perlmutter-Phase-2']
        elif jt in ['HPC', 'HYBRID']:
            if job_gpu:
                # HPC/HYBRID with GPU requirement
                available_systems = ['Frontier', 'Aurora', 'Perlmutter-Phase-1']
            else:
                # HPC/HYBRID without GPU requirement
                available_systems = ['Frontier', 'Aurora', 'Perlmutter-Phase-1','Andes', 'Crux', 'Perlmutter-Phase-2']
        else:
            available_systems = list(site_configs[origin_sites[i]]["machines"].keys())
        
        # Select system from filtered list
        # system = rng.choice(available_systems)
        if job_gpu:
            # GPU jobs: uniform across GPU systems
            system = random.choice(available_systems)
        else:
            # Non-GPU jobs: prefer CPU systems with weights based on system size
            # Define per-system weights (higher = more jobs)
            system_weights = {
                'Perlmutter-Phase-2': 3.0,  # Largest CPU system (3072 nodes)
                'Andes': 1.5,               # Medium CPU system (704 nodes)
                'Crux': 1,                # Smallest CPU system (256 nodes)
            }
            weights = [system_weights.get(sys, 1.0) for sys in available_systems]
            system = random.choices(available_systems, weights=weights, k=1)[0]
        
        # Find the site for the selected system
        for site_name, site_config in site_configs.items():
            if system in site_config["machines"]:
                site = site_name
                break

        # Get system capabilities
        caps = site_configs[site]["machines"][system]
        node_cap = int(caps["node_limit"])
        storage_cap = float(caps["storage_limit"])
        mem_per_node_cap = float(caps["memory_limit"])

        # Nodes (log-uniform)
        lo, hi = bands["small_nodes"] if is_short else bands["large_nodes"]
        job_nodes = _sample_log_uniform_int(rng, lo, hi)
        job_nodes = min(job_nodes, node_cap)

        # Walltime (log-uniform), store in minutes
        wlo, whi = bands["short_wall"] if is_short else bands["long_wall"]
        wall_h = float(np.exp(np.random.uniform(np.log(wlo), np.log(whi))))
        wall_h = max(wlo, min(whi, wall_h))
        job_wall_min = int(round(wall_h * 60))

        # Storage (log-uniform) - use small/large bands based on is_short
        slo, shi = bands["small_storage"] if is_short else bands["large_storage"]
        storage = float(np.exp(np.random.uniform(np.log(slo), np.log(shi))))
        storage = min(storage, storage_cap)

        total_mem = job_nodes * mem_per_node_cap

        # Assign
        nodes[i] = job_nodes
        walltimes_min[i] = job_wall_min
        requested_gpus[i] = bool(job_gpu)
        requested_storages[i] = round(storage, 2)
        memories[i] = total_mem
        origin_sites[i] = site  # Update with actual assigned site
        origin_systems[i] = system  # Update with actual assigned system

    # Users/groups
    user_ids = np.random.randint(1, max(2, n_jobs // 2 + 1), size=n_jobs)
    group_ids = np.random.randint(1, max(2, n_jobs // 4 + 1), size=n_jobs)

    # DEBUG: Analyze system distribution
    print("\n=== System Distribution Analysis ===")
    system_counts = pd.Series(origin_systems).value_counts()
    print("\nSystem counts:")
    for system, count in system_counts.items():
        pct = (count / n_jobs) * 100
        print(f"  {system:25s}: {count:4d} ({pct:5.1f}%)")
    
    # Break down by job type
    print("\n=== Distribution by Job Type ===")
    for jt in job_types:
        jt_mask = [types[i] == jt for i in range(n_jobs)]
        jt_systems = [origin_systems[i] for i in range(n_jobs) if jt_mask[i]]
        jt_gpus = [requested_gpus[i] for i in range(n_jobs) if jt_mask[i]]
        
        print(f"\n{jt} jobs: {len(jt_systems)} total")
        if len(jt_systems) > 0:
            sys_counts = pd.Series(jt_systems).value_counts()
            for sys, cnt in sys_counts.items():
                # Count GPU jobs for this system
                gpu_for_sys = sum(1 for i in range(n_jobs) if types[i] == jt and origin_systems[i] == sys and requested_gpus[i])
                pct = (cnt / len(jt_systems)) * 100
                print(f"  {sys:25s}: {cnt:4d} ({pct:5.1f}%), GPU: {gpu_for_sys}/{cnt}")
            
            gpu_count = sum(jt_gpus)
            print(f"  Total GPU jobs: {gpu_count}/{len(jt_systems)} ({100*gpu_count/len(jt_systems):.1f}%)")
    
    df = pd.DataFrame({
        'JobID': job_ids,
        'SubmissionTime': np.round(submission_times, 3),  # hours
        'Walltime': walltimes_min,                        # minutes
        'Nodes': nodes,
        'MemoryGB': memories,
        'RequestedGPU': requested_gpus,
        'RequestedStorageGB': requested_storages,
        'JobType': types,
        'UserID': user_ids,
        'GroupID': group_ids,
        'HPCSite': np.array(origin_sites, dtype=object),
        'HPCSystem': np.array(origin_systems, dtype=object),
    })

    return df

# ----------------------------
# CLI
# ----------------------------

def main():
    parser = argparse.ArgumentParser(description='Generate synthetic jobs for simulation')

    parser.add_argument('--n_jobs', type=int, default=100)
    parser.add_argument('--seed', type=int, default=42)

    parser.add_argument('--day', type=str, default='busy', choices=['busy', 'idle'])
    parser.add_argument('--scenario', type=str, default='mixed_80_20',
                        choices=['homogeneous_short', 'only_large_long', 'mixed_80_20', 'mixed_20_80'])

    parser.add_argument('--jobs_per_site', type=str, default='',
                        help='JSON string, e.g. \'{"OLCF":34,"ALCF":33,"NERSC":33}\'')

    parser.add_argument('--jobtype_proportions', type=str, default='',
                        help='JSON string, e.g. \'{"HPC":0.3,"AI":0.3,"HYBRID":0.25,"STORAGE":0.15}\'')

    args = parser.parse_args()

    jobs_per_site = _parse_json_arg(args.jobs_per_site) if args.jobs_per_site else None
    jobtype_proportions = _parse_json_arg(args.jobtype_proportions) if args.jobtype_proportions else None

    df = generate_synthetic_jobs_v3(
        n_jobs=args.n_jobs,
        seed=args.seed,
        day=args.day,
        scenario=args.scenario,
        jobs_per_site=jobs_per_site,
        jobtype_proportions=jobtype_proportions,
    )

    os.makedirs("./data", exist_ok=True)
    out = f"./data/{args.day}_{args.scenario}_{len(df)}.json"
    with open(out, "w") as f:
        json.dump(df.to_dict("records"), f, indent=2)

    print(f"Generated {len(df)} jobs.")
    print(f"Saved: {out}")

if __name__ == "__main__":
    main()
