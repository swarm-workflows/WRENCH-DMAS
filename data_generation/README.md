# Synthetic HPC Job Generator v3

Advanced workload generator for multi-site HPC simulation with realistic job characteristics, GPU-aware system routing, and timezone-based submission patterns.

## Quick Start

```bash
# Generate 100 jobs with default settings (busy day, 80% short jobs, identical #jobs across sites, job type proportion {"HPC":0.3,"AI":0.3,"HYBRID":0.25,"STORAGE":0.15})
python job_generation.py

# Generate 1000 jobs with custom scenario
python job_generation.py --n_jobs 1000 --scenario only_large_long --day idle

# Custom site distribution
python job_generation.py --n_jobs 300 --jobs_per_site '{"OLCF":150,"ALCF":100,"NERSC":50}'

# Custom job type proportions
python job_generation.py --jobtype_proportions '{"HPC":0.4,"AI":0.4,"HYBRID":0.15,"STORAGE":0.05}'
