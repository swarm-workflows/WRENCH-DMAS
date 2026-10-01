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
import xml.etree.ElementTree as ET

def _parse_radical_upper(radical: str) -> int:
    # "1-5312" -> 5312
    if "-" in radical:
        return int(radical.split("-", 1)[1].strip())
    return int(radical.strip())

def parse_site_configs_from_platform_xml(xml_path: str) -> dict:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    site_configs = {}

    for cluster in root.findall(".//cluster"):
        machine = cluster.attrib["id"]
        node_limit = _parse_radical_upper(cluster.attrib["radical"])

        props = {p.attrib["id"]: p.attrib.get("value", "") for p in cluster.findall("./prop")}
        site = props["site"]

        site_configs.setdefault(site, {"machines": {}})
        site_configs[site]["machines"][machine] = {
            "type": props["type"],
            "has_gpu": props["has_gpu"].strip().lower() == "true",
            "node_limit": node_limit,
            "memory_limit": float(props["memory_amount_in_gb"]),
            "storage_limit": float(props["storage_amount_in_gb"]),
        }

    return site_configs

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

_SCENARIO_SHORT_FRAC: Dict[str, float] = {
    "small_short": 1.00,
    "large_long":   0.00,
    "mixed_80_20":       0.80,
    "mixed_20_80":       0.20,
}

def _build_short_flags(n_jobs: int, scenario: str, rng: random.Random) -> list:
    """Return per-job is_short flags with exact counts derived from scenario."""
    short_frac = _SCENARIO_SHORT_FRAC.get(scenario, 0.80)
    short_count = int(round(short_frac * n_jobs))
    flags = [True] * short_count + [False] * (n_jobs - short_count)
    rng.shuffle(flags)
    return flags

def _sample_uniform_int(rng: random.Random, lo: int, hi: int) -> int:
    lo = max(1, int(lo))
    hi = max(lo, int(hi))
    return rng.randint(lo, hi)

def _sample_lognormal_int(rng: random.Random, lo: int, hi: int, mu: float, sigma: float) -> int:
    lo = max(1, int(lo))
    hi = max(lo, int(hi))
    # stats.lognorm(s=sigma, scale=np.exp(mu))
    sample = int(round(rng.lognormvariate(mu, sigma)))
    # sample = stats.lognorm(s=sigma, scale=np.exp(mu)).rvs(random_state=rng)
    return max(lo, min(hi, sample))

def _format_scale_tag(value: float) -> str:
    return f"{float(value):g}".replace(".", "p")

def _business_day_times_by_site(n_jobs: int, sites: list, seed: int = 42) -> np.ndarray:
    """
    business day: for each site, draw local-time submissions ~ Normal(noon, 4h),
    then map into a shared timeline with offsets (EST=0, CST=+1, PST=+3).
    Output is per-job times in SECONDS (aligned with input job order).
    """
    rng = np.random.default_rng(seed)
    hour = 3600.0
    tz = {'OLCF': 0.0, 'ALCF': 1.0 * hour, 'NERSC': 3.0 * hour}  # offsets in seconds

    sites_arr = np.array(sites, dtype=object)
    if len(sites_arr) != n_jobs:
        raise ValueError(f"Expected {n_jobs} sites, got {len(sites_arr)}")

    submission_times = np.empty(n_jobs, dtype=float)

    for site in np.unique(sites_arr):
        mask = (sites_arr == site)
        cnt = int(np.sum(mask))
        if cnt == 0:
            continue
        offset = tz.get(str(site), 0.0)
        
        # local sampling (same business-day shape for every site)
        local_t = rng.normal(loc=12.0 * hour, scale=4.0 * hour, size=cnt)
        local_t = np.clip(local_t, 0.0, 24.0 * hour)

        # separate rule: force both local-day edges when possible
        if cnt >= 2:
            edge_idx = rng.choice(cnt, size=2, replace=False)
            local_t[edge_idx[0]] = 0.0
            local_t[edge_idx[1]] = 24.0 * hour
        elif cnt == 1:
            # only one sample exists, so choose one edge deterministically
            local_t[0] = 0.0  # or 24.0 * hour if you prefer upper edge

        # shift to shared timeline
        submission_times[mask] = local_t + offset

    # debug for each offset
    print("\n=== Debug: Submission Times by Site (business Day) ===", file=os.sys.stderr)
    
    # print min, max, mean for each site
    for site in np.unique(sites_arr):
        mask = (sites_arr == site)
        times = submission_times[mask]
        if len(times) > 0:
            print(f"Site: {site:10s} | count={len(times):4d} | min={times.min():.3f}s | mean={times.mean():.3f}s | max={times.max():.3f}s", file=os.sys.stderr)

    return submission_times

# ----------------------------
# Bursty arrival profiles
# ----------------------------
# Module-level defaults for bursty patterns.  Edit these to tune shape without
# touching the sampler.  peak_params kwarg can override component entries by
# name at call time.
BURSTY_PROFILES: Dict[str, dict] = {
    "bursty_low_stress": {
        # Two-hump day: exponential burst at open-of-day and a spike-free peak at 12 h.
        "components": [
            {
                "name": "peak1",
                "kind": "exponential_burst",
                "weight": 0.45,
                "mean_h": 0.5,   # mean arrival ~30 min after day-open
                "max_h": 4.0,
            },
            {
                "name": "peak2",
                "kind": "log_uniform_center_spike",
                "weight": 0.45,
                "center_h": 12.0,
                "spike_fraction": 0.18,
                "spike_sigma_s": 300.0,  # 5-min jitter replaces point mass
                "left_fraction": 0.38,
                "dmin_s": 120.0,
                "left_max_h": 1.5,
                "right_max_h": 3.2,
            },
            {
                "name": "background",
                "kind": "uniform",
                "weight": 0.10,
            },
        ],
    },
    "bursty_high_stress": {
        # More intense opening burst (mean 15 min) and second peak earlier at 4 h.
        "components": [
            {
                "name": "peak1",
                "kind": "exponential_burst",
                "weight": 0.45,
                "mean_h": 0.25,  # mean arrival ~15 min after day-open (sharper burst)
                "max_h": 2.0,
            },
            {
                "name": "peak2",
                "kind": "log_uniform_center_spike",
                "weight": 0.45,
                "center_h": 4.0,
                "spike_fraction": 0.18,
                "spike_sigma_s": 300.0,  # 5-min jitter replaces point mass
                "left_fraction": 0.38,
                "dmin_s": 120.0,
                "left_max_h": 1.5,
                "right_max_h": 3.2,
            },
            {
                "name": "background",
                "kind": "uniform",
                "weight": 0.10,
            },
        ],
    },
}


def _sample_split_normal_component(
    rng: np.random.Generator,
    count: int,
    center_h: float,
    sigma_rise_h: float,
    sigma_fall_h: float,
    hour: float,
) -> np.ndarray:
    if count <= 0:
        return np.empty(0, dtype=float)

    center = center_h * hour
    sigma_rise = sigma_rise_h * hour
    sigma_fall = sigma_fall_h * hour
    u = rng.normal(0.0, 1.0, size=count)
    return center + np.where(u < 0.0, sigma_rise, sigma_fall) * u


def _sample_log_uniform_center_spike_component(
    rng: np.random.Generator,
    count: int,
    center_h: float,
    spike_fraction: float,
    spike_sigma_s: float,
    left_fraction: float,
    dmin_s: float,
    left_max_h: float,
    right_max_h: float,
    hour: float,
) -> np.ndarray:
    if count <= 0:
        return np.empty(0, dtype=float)

    center = center_h * hour
    spike_fraction = float(np.clip(spike_fraction, 0.0, 1.0))
    spike_sigma_s = max(float(spike_sigma_s), 1.0)
    left_fraction = float(np.clip(left_fraction, 0.0, 1.0))
    dmin_s = max(float(dmin_s), 1.0)

    left_max_s = max(dmin_s, left_max_h * hour)
    right_max_s = max(dmin_s, right_max_h * hour)

    n_spike = int(round(count * spike_fraction))
    n_tail = max(0, count - n_spike)
    n_left = int(round(n_tail * left_fraction))
    n_right = max(0, n_tail - n_left)

    left_d = (
        np.exp(rng.uniform(np.log(dmin_s), np.log(left_max_s), size=n_left))
        if n_left > 0
        else np.empty(0, dtype=float)
    )
    right_d = (
        np.exp(rng.uniform(np.log(dmin_s), np.log(right_max_s), size=n_right))
        if n_right > 0
        else np.empty(0, dtype=float)
    )

    # Tight Gaussian around center instead of a point mass — avoids identical timestamps.
    spike_samples = (
        rng.normal(center, spike_sigma_s, size=n_spike)
        if n_spike > 0
        else np.empty(0, dtype=float)
    )

    samples = np.concatenate([spike_samples, center - left_d, center + right_d])
    rng.shuffle(samples)
    return samples


def _sample_uniform_component(
    rng: np.random.Generator,
    count: int,
    hour: float,
) -> np.ndarray:
    if count <= 0:
        return np.empty(0, dtype=float)
    return rng.uniform(0.0, 27.0 * hour, size=count)


def _sample_exponential_burst_component(
    rng: np.random.Generator,
    count: int,
    mean_h: float,
    max_h: float,
    hour: float,
) -> np.ndarray:
    """Exponential inter-arrival burst starting at t=0. All samples are strictly > 0."""
    if count <= 0:
        return np.empty(0, dtype=float)
    samples = rng.exponential(scale=mean_h * hour, size=count)
    return np.clip(samples, 0.0, max_h * hour)


def _sample_bursty_component(
    rng: np.random.Generator,
    component: Dict[str, float],
    count: int,
    hour: float,
) -> np.ndarray:
    kind = component["kind"]

    if kind == "split_normal":
        return _sample_split_normal_component(
            rng=rng,
            count=count,
            center_h=float(component["center_h"]),
            sigma_rise_h=float(component["sigma_rise_h"]),
            sigma_fall_h=float(component["sigma_fall_h"]),
            hour=hour,
        )

    if kind == "exponential_burst":
        return _sample_exponential_burst_component(
            rng=rng,
            count=count,
            mean_h=float(component["mean_h"]),
            max_h=float(component["max_h"]),
            hour=hour,
        )

    if kind == "log_uniform_center_spike":
        return _sample_log_uniform_center_spike_component(
            rng=rng,
            count=count,
            center_h=float(component["center_h"]),
            spike_fraction=float(component["spike_fraction"]),
            spike_sigma_s=float(component.get("spike_sigma_s", 300.0)),
            left_fraction=float(component["left_fraction"]),
            dmin_s=float(component["dmin_s"]),
            left_max_h=float(component["left_max_h"]),
            right_max_h=float(component["right_max_h"]),
            hour=hour,
        )

    if kind == "uniform":
        return _sample_uniform_component(rng=rng, count=count, hour=hour)

    raise ValueError(f"Unknown bursty component kind: {kind!r}")


def _allocate_component_counts(count: int, components: list) -> np.ndarray:
    weights = np.array([float(component["weight"]) for component in components], dtype=float)
    total = float(weights.sum())
    if total <= 0.0:
        raise ValueError("Bursty component weights must sum to > 0")

    weights = weights / total
    raw = count * weights
    counts = np.floor(raw).astype(int)
    remainder = int(count - counts.sum())

    if remainder > 0:
        order = np.argsort(-(raw - counts))
        for idx in order[:remainder]:
            counts[idx] += 1

    return counts


def _component_debug_stats(local_times: np.ndarray, components: list, hour: float) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    for component in components:
        name = str(component.get("name", component["kind"]))
        kind = component["kind"]

        if kind == "uniform":
            continue

        if kind == "exponential_burst":
            max_s = float(component["max_h"]) * hour
            stats[f"{name}_0to1h"] = int(np.sum((local_times >= 0.0) & (local_times <= 1.0 * hour)))
            stats[f"{name}_0tomax"] = int(np.sum((local_times >= 0.0) & (local_times <= max_s)))
            continue

        center = float(component["center_h"]) * hour

        if kind == "split_normal" and center <= 0.0:
            stats[f"{name}_0to2h"] = int(np.sum((local_times >= 0.0) & (local_times <= 2.0 * hour)))
            continue

        if kind == "log_uniform_center_spike":
            stats[f"{name}_core15m"] = int(np.sum(np.abs(local_times - center) <= 15.0 * 60.0))
            stats[f"{name}_pm2h"] = int(np.sum(np.abs(local_times - center) <= 2.0 * hour))
            continue

        stats[f"{name}_pm2h"] = int(np.sum(np.abs(local_times - center) <= 2.0 * hour))

    return stats


def _bursty_day_times_by_site(
    n_jobs: int,
    sites: list,
    stress: str = "low_stress",
    seed: int = 42,
    peak_params: Optional[Dict] = None,
    sync_sites: bool = True,
) -> np.ndarray:
    """
    Bursty arrivals: sample named profile components per site in local time, then
    shift by timezone offset. Components are configured declaratively in
    BURSTY_PROFILES, which makes it easier to experiment with peak shapes without
    rewriting the sampler.

    Args:
        stress:      "low_stress" or "high_stress" — selects profile from BURSTY_PROFILES.
        peak_params: optional per-component overrides merged shallowly by name,
                     e.g. {"peak2": {"spike_fraction": 0.25, "right_max_h": 4.0}}.
        sync_sites:  if True, all timezone offsets are zeroed so every site bursts
                     at the same global time — maximum simultaneous contention.
    """
    profile_key = f"bursty_{stress}"
    if profile_key not in BURSTY_PROFILES:
        raise ValueError(
            f"Unknown stress level {stress!r}. Valid choices: 'low_stress', 'high_stress'."
        )

    # Load profile defaults then apply any caller overrides (shallow per-component merge).
    base = BURSTY_PROFILES[profile_key]
    components = [dict(component) for component in base["components"]]
    if peak_params:
        components_by_name = {str(component["name"]): component for component in components}
        for name, overrides in peak_params.items():
            if name not in components_by_name:
                raise ValueError(
                    f"Unknown bursty component override {name!r}. "
                    f"Valid choices: {sorted(components_by_name)}."
                )
            if not isinstance(overrides, dict):
                raise ValueError(f"Override for bursty component {name!r} must be a JSON object")
            components_by_name[name].update(overrides)

    rng = np.random.default_rng(seed)
    hour = 3600.0
    # Timezone offsets shift each site's local burst onto the shared global clock.
    # Set sync_sites=True to zero all offsets and make every site burst simultaneously.
    if sync_sites:
        tz: Dict[str, float] = {}  # all sites get offset 0.0
    else:
        tz = {'OLCF': 0.0, 'ALCF': 1.0 * hour, 'NERSC': 3.0 * hour}

    sites_arr = np.array(sites, dtype=object)
    if len(sites_arr) != n_jobs:
        raise ValueError(f"Expected {n_jobs} sites, got {len(sites_arr)}")

    submission_times = np.empty(n_jobs, dtype=float)

    for site in np.unique(sites_arr):
        mask = (sites_arr == site)
        cnt = int(np.sum(mask))
        if cnt == 0:
            continue

        offset = tz.get(str(site), 0.0)

        counts = _allocate_component_counts(cnt, components)
        samples = [
            _sample_bursty_component(rng=rng, component=component, count=int(component_count), hour=hour)
            for component, component_count in zip(components, counts)
        ]

        local_t = np.concatenate(samples) if samples else np.empty(0, dtype=float)
        local_t = np.clip(local_t, 0.0, 27.0 * hour)
        rng.shuffle(local_t)
        submission_times[mask] = local_t + offset

    # Per-site debug stats.
    print(f"\n=== Debug: Submission Times by Site (Bursty {stress}) ===", file=os.sys.stderr)
    for site in np.unique(sites_arr):
        mask = (sites_arr == site)
        times = submission_times[mask]
        if len(times) > 0:
            local = times - tz.get(str(site), 0.0)
            stats = _component_debug_stats(local, components, hour)
            stat_text = " | ".join(f"{key}={value:4d}" for key, value in stats.items())
            print(
                f"Site: {site:10s} | count={len(times):4d} | "
                f"{stat_text} | "
                f"min={times.min():.1f}s | max={times.max():.1f}s",
                file=os.sys.stderr,
            )

    return submission_times

# ----------------------------
# Per-job-type size bands
# ----------------------------

# Global node bands across all job types
GLOBAL_NODE_BANDS: Dict[str, Tuple[int, int]] = {
    "small_nodes": (1, 256),
    "large_nodes": (257, 10624),
}

# Global node sampling config
# For log-normal: mode = exp(mu - sigma^2) -> mu = log(mode) + sigma^2
# desired_mode=1000 chosen so that:
#   - mean of clipped lognormal(257, 10624) ~ 2,549 nodes (~25% of Aurora)
#   - smaller systems (Perlmutter-Ph1, Andes) still receive ~15-21% of large jobs
#   - sigma=0.8 gives reasonable spread without too many jobs hitting the cap
NODE_SAMPLING = {
    "sigma": 0.6,
    "desired_mode": 600,
}

# Memory-per-node sampling config (GB per node).
# Drawn as log-uniform over [min_gb, max_gb].
# max_gb = 984 matches Aurora's memory_limit so no job is forced onto Frontier by memory alone.
MEMORY_PER_NODE_SAMPLING = {
    "min_gb": 32.0,
    "max_gb": 512.0,
}

# New: control the joint nodes x walltime structure
_JOINT_CFG = {"rho": 0.65, "p_outlier": 0.05, "tail_gate": 0.80, "outlier_lo": 0.90}
NODE_WALLTIME_DEPENDENCE = {
    "large_long":  _JOINT_CFG,
    "mixed_20_80_long": _JOINT_CFG,
    "mixed_80_20_long": _JOINT_CFG,
}

def _sample_nodes(
    rng: random.Random,
    size_class: str,
    node_bands: Optional[Dict[str, Tuple[int, int]]] = None,
    desired_mode: Optional[float] = None,
) -> int:
    bands = node_bands or GLOBAL_NODE_BANDS
    lo, hi = bands[size_class]

    # Requirement:
    # - small_nodes: uniformly sampled integers
    # - large_nodes: lognormal with peak near desired_mode
    if size_class == "small_nodes":
        return _sample_uniform_int(rng, lo, hi)

    sigma = float(NODE_SAMPLING.get("sigma", 0.8))
    mode = float(desired_mode if desired_mode is not None else NODE_SAMPLING.get("desired_mode", 600))
    mu = float(np.log(mode) + sigma ** 2)
    return _sample_lognormal_int(rng, lo, hi, mu, sigma)

def _normalized_log_position(value: int, lo: int, hi: int) -> float:
    value = max(lo, min(hi, int(value)))
    denom = np.log(hi) - np.log(lo)
    if denom <= 0:
        return 0.0
    x = (np.log(value) - np.log(lo)) / denom
    return float(np.clip(x, 0.0, 1.0))


def _sample_walltime_independent(
    wlo: float,
    whi: float,
) -> float:
    wall_h = float(np.exp(np.random.uniform(np.log(wlo), np.log(whi))))
    return max(wlo, min(whi, wall_h))


def _sample_walltime_joint_large_long(
    job_nodes: int,
    node_lo: int,
    node_hi: int,
    wlo: float,
    whi: float,
    rho: float,
    p_outlier: float,
    tail_gate: float,
    outlier_lo: float,
) -> float:
    """
    Keeps node marginal unchanged.
    Generates mostly anti-correlated nodes x walltime:
      - high nodes -> shorter walltime
      - low nodes -> longer walltime
    plus rare high-node high-walltime outliers.
    """
    x = _normalized_log_position(job_nodes, node_lo, node_hi)

    # Base anti-correlated walltime percentile
    u_rand = float(np.random.uniform(0.0, 1.0))
    u_wall = (1.0 - rho) * u_rand + rho * (1.0 - x)

    # Rare 10x10 tail outlier
    if x >= tail_gate and np.random.uniform(0.0, 1.0) < p_outlier:
        u_wall = max(u_wall, float(np.random.uniform(outlier_lo, 1.0)))

    u_wall = float(np.clip(u_wall, 0.0, 1.0))

    log_wall = np.log(wlo) + u_wall * (np.log(whi) - np.log(wlo))
    wall_h = float(np.exp(log_wall))
    return max(wlo, min(whi, wall_h))


def _sample_walltime_for_job(
    scenario: str,
    is_short: bool,
    job_nodes: int,
    node_bands: Dict[str, Tuple[int, int]],
    wlo: float,
    whi: float,
) -> float:
    # homogeneous_short: leave independent
    if scenario == "homogeneous_short":
        return _sample_walltime_independent(wlo, whi)

    # short jobs in mixed scenarios: keep independent
    if is_short:
        return _sample_walltime_independent(wlo, whi)

    # large_long: use L-shaped joint distribution
    if scenario == "large_long":
        cfg = NODE_WALLTIME_DEPENDENCE["large_long"]
        node_lo, node_hi = node_bands["large_nodes"]
        return _sample_walltime_joint_large_long(
            job_nodes=job_nodes,
            node_lo=node_lo,
            node_hi=node_hi,
            wlo=wlo,
            whi=whi,
            rho=cfg["rho"],
            p_outlier=cfg["p_outlier"],
            tail_gate=cfg["tail_gate"],
            outlier_lo=cfg["outlier_lo"],
        )

    # mixed scenarios: apply only to long jobs
    if scenario == "mixed_20_80":
        cfg = NODE_WALLTIME_DEPENDENCE["mixed_20_80_long"]
        node_lo, node_hi = node_bands["large_nodes"]
        return _sample_walltime_joint_large_long(
            job_nodes=job_nodes,
            node_lo=node_lo,
            node_hi=node_hi,
            wlo=wlo,
            whi=whi,
            rho=cfg["rho"],
            p_outlier=cfg["p_outlier"],
            tail_gate=cfg["tail_gate"],
            outlier_lo=cfg["outlier_lo"],
        )

    if scenario == "mixed_80_20":
        cfg = NODE_WALLTIME_DEPENDENCE["mixed_80_20_long"]
        node_lo, node_hi = node_bands["large_nodes"]
        return _sample_walltime_joint_large_long(
            job_nodes=job_nodes,
            node_lo=node_lo,
            node_hi=node_hi,
            wlo=wlo,
            whi=whi,
            rho=cfg["rho"],
            p_outlier=cfg["p_outlier"],
            tail_gate=cfg["tail_gate"],
            outlier_lo=cfg["outlier_lo"],
        )

    return _sample_walltime_independent(wlo, whi)



# "short_wall": (0.5, 4),"long_wall": (4, 24)
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

# ----------------------------
# Main generator
# ----------------------------

def generate_synthetic_jobs_v9(
    n_jobs: int = 100,
    seed: int = 42,
    arrival_pattern: str = "business",
    scenario: str = "mixed_80_20",
    # jobs_per_site: Optional[Dict[str, int]] = None,
    jobtype_proportions: Optional[Dict[str, float]] = None,
    # sfactor: float = 1.0,
    peak_params: Optional[Dict] = None,
    sync_sites: bool = True,
) -> pd.DataFrame:

    # Apply scale divisors to capacities if provided.
    # Example: sfactor=8 -> node_limit = node_limit / 8
    # sfactor = max(float(sfactor), 1e-9)

    if seed > 0:
        random.seed(seed)
        np.random.seed(seed)

    
    # if sfactor != 1.0:
    #     site_configs = parse_site_configs_from_platform_xml(f"platforms/AmSC_scaled_down_{int(sfactor)}.xml")
    # else:
    site_configs = parse_site_configs_from_platform_xml("platforms/AmSC.xml")

    
    # prettier print of platform config
    print("=== Original Platform Config ===")
    for site_name, site_cfg in site_configs.items():
        print(f"Site: {site_name}")
        for machine_name, machine_cfg in site_cfg["machines"].items():
            print(
                f"  Machine: {machine_name:22s} | "
                f"type={machine_cfg['type']:10s} | "
                f"GPU={'Yes' if machine_cfg['has_gpu'] else 'No ':3s} | "
                f"nodes={machine_cfg['node_limit']:5d} | "
                f"mem/node={machine_cfg['memory_limit']:6.1f} GB | "
                f"storage={machine_cfg['storage_limit']:.2e} GB"
            )
    
    # Adapt global/common node sampling to scaled platform limits
    max_scaled_nodes = max(
        machine_cfg["node_limit"]
        for site_cfg in site_configs.values()
        for machine_cfg in site_cfg["machines"].values()
    )
    # scale down small node bands proportionally, but keep at least 1 node
    # small_lo, small_hi = GLOBAL_NODE_BANDS["small_nodes"]
    small_lo = max(1, int(GLOBAL_NODE_BANDS["small_nodes"][0] ))
    small_hi = max(small_lo, int(GLOBAL_NODE_BANDS["small_nodes"][1] ))
    
    # scale down large_lo and large_hi proportionally, but keep at least 1 node
    large_lo = min(GLOBAL_NODE_BANDS["large_nodes"][0], small_hi + 1)
    large_hi = max(large_lo, int(max_scaled_nodes))
    scaled_node_bands = {
        "small_nodes": (small_lo, small_hi),
        "large_nodes": (large_lo, large_hi),
    }
    # edge case: if small_hi == small_lo, keep small_hi+1 and accordingly adjust large_lo to maintain the gap
    if small_hi == small_lo:
        small_hi = small_lo + 1
        large_lo = max(large_lo, small_hi + 1)
        scaled_node_bands["small_nodes"] = (small_lo, small_hi)
        scaled_node_bands["large_nodes"] = (large_lo, large_hi)

    
    # sanity check: ensure scaled bands fit within platform limits
    if large_hi < large_lo:
        raise ValueError(
            f"Invalid scaled node bands: "
            f"large_hi ({large_hi}) < large_lo ({large_lo}). "
            f"Check platform limits and scaling logic."
        )
    
    base_mode = float(NODE_SAMPLING.get("desired_mode", 600))
    scaled_desired_mode = max(float(large_lo), min(float(large_hi), base_mode ))

    print("\n=== Node Sampling (Effective) ===")
    print(f"small_nodes band: {scaled_node_bands['small_nodes']}")
    print(f"large_nodes band: {scaled_node_bands['large_nodes']}")
    print(
        f"large_nodes lognormal sigma={NODE_SAMPLING.get('sigma', 0.8)}, "
        f"base_mode={base_mode}, scaled_mode={scaled_desired_mode:.2f}"
    )
    
    job_types = ['HPC', 'AI', 'HYBRID', 'STORAGE']

    if jobtype_proportions is None:
        jobtype_proportions = {"HPC": 0.3, "AI": 0.3, "HYBRID": 0.25, "STORAGE": 0.15}
    jobtype_proportions = _normalize_probs(jobtype_proportions)
    proportions = [jobtype_proportions[jt] for jt in job_types]
   
    # Generate job types
    types = random.choices(job_types, weights=proportions, k=n_jobs)

    # Scenario mixing: exact per-scenario short/long counts
    rng = random.Random(seed + 123)
    short_flags = _build_short_flags(n_jobs=n_jobs, scenario=scenario, rng=rng)

    # Arrays
    job_ids = np.arange(1, n_jobs + 1)
    walltimes_min = np.zeros(n_jobs, dtype=int)
    nodes = np.zeros(n_jobs, dtype=int)
    memories = np.zeros(n_jobs, dtype=float)
    requested_gpus = np.zeros(n_jobs, dtype=bool)
    requested_storages = np.zeros(n_jobs, dtype=float)
    origin_sites = np.empty(n_jobs, dtype=object)
    origin_systems = np.empty(n_jobs, dtype=object)

    # Build a flat system lookup from parsed platform config for capacity-aware placement
    all_systems_info: Dict[str, dict] = {}
    for _site_name, _site_cfg in site_configs.items():
        for _machine_name, _machine_cfg in _site_cfg["machines"].items():
            all_systems_info[_machine_name] = {"site": _site_name, "caps": _machine_cfg}

    # System selection weight maps (same as before; capacity filtering applied at placement time)
    _GPU_SYSTEM_WEIGHTS: Dict[str, float] = {
        "Frontier": 1.0, "Aurora": 1.0, "Perlmutter-Phase-1": 0.8,
    }
    _NON_GPU_SYSTEM_WEIGHTS: Dict[str, float] = {
        "Perlmutter-Phase-2": 1.7, "Andes": 1.5, "Crux": 1.0,
        "Frontier": 1.0, "Aurora": 1.0, "Perlmutter-Phase-1": 1.0,
    }
    _MAX_PLACEMENT_RETRIES = 20

    # Generate per job
    for i in range(n_jobs):
        jt = types[i]
        bands = JOB_TYPE_BANDS[jt]

        is_short = short_flags[i]
        
        # GPU policy - determine first
        if jt == "AI":
            job_gpu = True
        elif jt == "STORAGE":
            job_gpu = False
        else:
            job_gpu = (rng.random() < (0.5 if jt == "HYBRID" else 0.3))  # hybrid more likely GPU than HPC


        # --- Job-first attribute sampling, then capacity-aware system selection ---
        size_class = "small_nodes" if is_short else "large_nodes"
        weights_map = _GPU_SYSTEM_WEIGHTS if job_gpu else _NON_GPU_SYSTEM_WEIGHTS

        # Walltime does not constrain system selection; sample it upfront
        wlo, whi = bands["short_wall"] if is_short else bands["long_wall"]

        # Sample nodes and storage, then pick a system that can host both.
        # Retry if no system in the weighted pool fits the sampled combination.
        slo, shi = bands["small_storage"] if is_short else bands["large_storage"]
        system = site = None
        
        for _attempt in range(_MAX_PLACEMENT_RETRIES):
            job_nodes = _sample_nodes(
                rng,
                size_class,
                node_bands=scaled_node_bands,
                desired_mode=scaled_desired_mode
            )

            # New: correlated walltime sampling
            wall_h = _sample_walltime_for_job(
                scenario=scenario,
                is_short=is_short,
                job_nodes=job_nodes,
                node_bands=scaled_node_bands,
                wlo=wlo,
                whi=whi,
            )
            job_wall_min = int(round(wall_h * 60))
            storage = float(np.exp(np.random.uniform(np.log(slo), np.log(shi))))
            # log-uniform memory-per-node in [min_gb, max_gb]
            mem_per_node_req = float(np.exp(np.random.uniform(
                np.log(float(MEMORY_PER_NODE_SAMPLING["min_gb"])),
                np.log(float(MEMORY_PER_NODE_SAMPLING["max_gb"])),
            )))
            # pick candidates from the weighted pool that satisfy node, memory, and storage constraints
            
            candidates: list = []
            candidate_weights: list = []
            for _sys_name, _w in weights_map.items():
                _sys_info = all_systems_info.get(_sys_name)
                if _sys_info is None:
                    continue
                _caps = _sys_info["caps"]

                if job_nodes > _caps["node_limit"]:
                    continue
                if storage > _caps["storage_limit"]:
                    continue
                # system memory is per node memory 
                if mem_per_node_req > _caps["memory_limit"]:
                    continue
                candidates.append(_sys_name)
                candidate_weights.append(_w)

            if candidates:
                system = random.choices(candidates, weights=candidate_weights, k=1)[0]
                site = all_systems_info[system]["site"]
                break

        if system is None:
            raise ValueError(
                f"Could not place job {i + 1} after {_MAX_PLACEMENT_RETRIES} retries: "
                f"job_type={jt}, size_class={size_class}, job_nodes={job_nodes}, "
                f"storage={storage:.0f} GB, mem_per_node_req={mem_per_node_req:.2f} GB, "
                f"job_gpu={job_gpu}. "
                f"No system in the pool satisfies these requirements."
            )

        caps = all_systems_info[system]["caps"]
        job_total_memory = job_nodes * mem_per_node_req

        # Assign
        nodes[i] = job_nodes
        walltimes_min[i] = job_wall_min
        requested_gpus[i] = bool(job_gpu)
        requested_storages[i] = round(storage, 2)
        memories[i] = job_total_memory
        origin_sites[i] = site
        origin_systems[i] = system

    # Users/groups
    user_ids = np.random.randint(1, max(2, n_jobs // 2 + 1), size=n_jobs)
    group_ids = np.random.randint(1, max(2, n_jobs // 4 + 1), size=n_jobs)

    # Submission times
    if arrival_pattern == "business":
        submission_times = _business_day_times_by_site(n_jobs, origin_sites, seed=seed)
    elif arrival_pattern in ("bursty_low_stress", "bursty_high_stress"):
        stress = arrival_pattern.replace("bursty_", "")
        submission_times = _bursty_day_times_by_site(
            n_jobs, origin_sites, stress=stress, seed=seed,
            peak_params=peak_params, sync_sites=sync_sites,
        )
    else:
        raise ValueError(
            f"Unknown arrival_pattern {arrival_pattern!r}. "
            "Valid choices: 'business', 'bursty_low_stress', 'bursty_high_stress'."
        )

    print("\n=== Submission Time Sampling ===")
    print(
        f"unit=seconds, min={submission_times.min():.3f}, "
        f"max={submission_times.max():.3f}, mean={submission_times.mean():.3f}"
    )

    
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
        'SubmissionTime': np.round(submission_times, 3),  # seconds
        'Walltime': walltimes_min*60,                        # seconds
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

    # Ensure jobs are ordered by submission time and IDs follow that order.
    df = df.sort_values(by="SubmissionTime", kind="mergesort").reset_index(drop=True)
    df["JobID"] = np.arange(1, len(df) + 1)

    return df

# ----------------------------
# CLI
# ----------------------------

def main():
    parser = argparse.ArgumentParser(description='Generate synthetic jobs for simulation')

    parser.add_argument('--n_jobs', type=int, default=None,
                        help=(
                            'Number of jobs to generate. Defaults are calibrated per scenario '
                            'to achieve rho~1.5 over the 27h global submission window: '
                            'small_short=3000, mixed_80_20=200, mixed_20_80=20, large_long=15. '
                            # 'These are fixed across all sfactor levels — do NOT divide by sfactor.'
                        ))
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument(
        '--arrival_pattern', '--day',
        dest='arrival_pattern',
        type=str, default='bursty_high_stress',
        choices=['business', 'bursty_low_stress', 'bursty_high_stress'],
        help="Arrival time pattern (default: business). --day is a deprecated alias.",
    )
    parser.add_argument('--scenario', type=str, default='small_short',
                        choices=['small_short', 'large_long', 'mixed_80_20', 'mixed_20_80'])
    parser.add_argument('--jobtype_proportions', type=str, default='',
                        help='JSON string, e.g. \'{"HPC":0.3,"AI":0.3,"HYBRID":0.25,"STORAGE":0.15}\'')
    # parser.add_argument("--sfactor", type=float, required=False, default=1.0,
                        # help="Radical scale divisor (default: 1.0)")
    parser.add_argument('--peak-params', type=str, default='',
                        help='JSON string to override named bursty components, '
                             'e.g. \'{"peak2": {"spike_fraction": 0.25, "right_max_h": 4.0}}\'')
    parser.add_argument('--stagger-sites', dest='sync_sites', action='store_false', default=True,
                        help='Apply per-site timezone offsets to stagger bursts across sites. '
                             'Default: all sites burst simultaneously (sync_sites=True).')
    parser.add_argument('--rho', type=float, default=1.5, choices=[0.9, 1.5], help='Target stress level rho (default: 1.5)')
    args = parser.parse_args()

    jobtype_proportions = _parse_json_arg(args.jobtype_proportions) if args.jobtype_proportions else None
    peak_params = _parse_json_arg(args.peak_params) if args.peak_params else None

    
    # Scenario-aware default n_jobs
    # rho=0.9
    _SCENARIO_DEFAULT_NJOBS_09: Dict[str, int] = {
    "small_short": 2880,
    "mixed_80_20":         251,
    "mixed_20_80":         67,
    "large_long":     54,
    }
    # rho=1.5
    _SCENARIO_DEFAULT_NJOBS_15: Dict[str, int] = {
        "small_short": 4800,
        "mixed_80_20":        415,
        "mixed_20_80":         112,
        "large_long":     91,
    }
    
    if args.n_jobs is None:
        table = _SCENARIO_DEFAULT_NJOBS_09 if args.rho == 0.9 else _SCENARIO_DEFAULT_NJOBS_15
        args.n_jobs = table[args.scenario]
        print(f"Using n_jobs={args.n_jobs} for scenario='{args.scenario}', rho={args.rho} (analytically derived)")

    print(f"Generating {args.n_jobs} jobs, arrival_pattern={args.arrival_pattern}, sync_sites={args.sync_sites}")

    df = generate_synthetic_jobs_v9(
        n_jobs=args.n_jobs,
        seed=args.seed,
        arrival_pattern=args.arrival_pattern,
        scenario=args.scenario,
        jobtype_proportions=jobtype_proportions,
        # sfactor=args.sfactor,
        peak_params=peak_params,
        sync_sites=args.sync_sites,
    )

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "data")
    os.makedirs(output_dir, exist_ok=True)
    # r_tag = _format_scale_tag(args.sfactor)

    out = os.path.join(output_dir, f"{args.arrival_pattern}_{args.scenario}_{len(df)}_rho{args.rho}.json")
    with open(out, "w") as f:
        json.dump(df.to_dict("records"), f, indent=2)

    print(f"Generated {len(df)} jobs.")
    print(f"Saved: {out}")

if __name__ == "__main__":
    main()
