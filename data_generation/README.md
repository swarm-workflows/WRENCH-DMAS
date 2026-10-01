# Synthetic HPC Job Generator v4

Generate heterogeneous workloads (HPC, AI, HYBRID, STORAGE) for multi-site HPC simulation with realistic job characteristics, GPU-aware system routing, and timezone-based submission patterns.

## Basic Usage

```bash
# Busy day, Full platform, default scenario mixed_80_20
python data_generation/job_generation.py --arrival_pattern busy

# Busy day (default timezones), scaled platform
python data_generation/job_generation.py --sfactor 32 --arrival_pattern busy --scenario homogeneous_short

# Bursty low stress
python data_generation/job_generation.py --sfactor 32 --arrival_pattern bursty_low_stress --scenario homogeneous_short

# Bursty high stress (same mixture, earlier 2nd peak)
python data_generation/job_generation.py --sfactor 32 --arrival_pattern bursty_high_stress --scenario homogeneous_short

# Force all sites to burst at same global time
python data_generation/job_generation.py --sfactor 32 --arrival_pattern bursty_high_stress --scenario homogeneous_short --sync-sites

# Custom job-type proportions
python data_generation/job_generation.py --arrival_pattern busy --jobtype_proportions '{"HPC":0.3,"AI":0.3,"HYBRID":0.25,"STORAGE":0.15}'
