import sys
import json
import time
import math
import random
import hashlib
import numpy as np

JOB_TYPES = ["HPC", "AI", "HYBRID", "STORAGE"]
SITES = ["NERSC", "ALCF", "OLCF"]


def one_hot(value, vocab):
    v = np.zeros(len(vocab) + 1, dtype=np.float32)  # +1 for OTHER
    if value in vocab:
        v[vocab.index(value)] = 1.0
    else:
        v[-1] = 1.0
    return v

def l2_normalize(x, eps=1e-12):
    x = np.asarray(x, dtype=np.float32)
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    n = float(np.linalg.norm(x))
    if not math.isfinite(n) or n < eps:
        return np.zeros_like(x, dtype=np.float32)
    return x / n

def fnum(x, default=0.0):
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)

def finite_or_inf(x):
    try:
        v = float(x)
    except Exception:
        return float("inf")
    if not math.isfinite(v):
        return float("inf")
    return v


def embed_job(job):
    nodes = fnum(job.get("num_nodes"), 0.0)
    wall = fnum(job.get("walltime"), 0.0)
    mem = fnum(job.get("requested_memory_gb"), 0.0)
    mem_per_node = mem / max(1.0, nodes)
    storage = fnum(job.get("requested_storage_gb"), 0.0)
    gpu = 1.0 if bool(job.get("needs_gpu", False)) else 0.0

    job_type = (job.get("job_type") or "OTHER")

    NODES_MAX = 8600.0
    WALL_MAX = 60.0 * 60.0   # 1 day in seconds
    MEM_MAX = 512       #1e6
    STORAGE_MAX = 500.0 * 1000

    def log01(x, cap):
        x = max(0.0, float(x))
        x = min(x, cap)
        return math.log1p(x) / math.log1p(cap)

    x_num = np.array([
        log01(nodes, NODES_MAX),
        log01(wall, WALL_MAX),
        log01(mem_per_node, MEM_MAX),
        log01(storage, STORAGE_MAX),
        gpu,
    ], dtype=np.float32)

    x_type = one_hot(job_type, JOB_TYPES)
    # x_site = one_hot(job_site, SITES)

    w_num  = 1.0
    w_type = 0.7
    # w_site = 0.5

    x = np.concatenate([w_num * x_num, w_type * x_type], axis=0)
    return l2_normalize(x)


def embed_system(sysdesc, job_site_hint=None):
    sys_nodes = fnum(sysdesc.get("num_nodes"), 1.0)
    sys_has_gpu = 1.0 if bool(sysdesc.get("has_gpu", False)) else 0.0
    sys_type = (sysdesc.get("type") or "OTHER")
    # sys_site = sysdesc.get("site") or (job_site_hint or "OTHER")
    sys_speed = fnum(sysdesc.get("node_speed"), 1.0)
    sys_mem_per_node = fnum(sysdesc.get("memory_amount_in_gb"), 0.0)

    sys_storage_cap = finite_or_inf(sysdesc.get("storage_amount_in_gb", float("inf")))
    if sys_storage_cap == float("inf"):
        sys_storage_cap = 1e9 

    NODES_MAX = 10624.0         # Aurora has the most nodes
    SPEED_MAX = 312e12          # Aurora speed in FLOPS
    MEM_MAX = 9472*12000        # Total memory in GB for Frontier
    MEM_PER_NODE_MAX = 12000.0 
    STORAGE_MAX = 700e6         # 700 PB for Summit

    def log01(x, cap):
        x = max(0.0, float(x))
        x = min(x, cap)
        return math.log1p(x) / math.log1p(cap)

    x_num = np.array([
        log01(sys_nodes, NODES_MAX),
        log01(sys_speed, SPEED_MAX),
        log01(sys_mem_per_node, MEM_PER_NODE_MAX),
        log01(sys_storage_cap, STORAGE_MAX),
        sys_has_gpu,
    ], dtype=np.float32)

    x_type = one_hot(sys_type, JOB_TYPES)
    # x_site = one_hot(sys_site, SITES)

    w_num  = 1.0
    w_type = 0.7
    # w_site = 0.5

    x = np.concatenate([w_num * x_num, w_type * x_type], axis=0)
    return l2_normalize(x)  


def scaled_walltime(walltime_seconds, node_speed, has_gpu=False):
    BASE_SPEED = 1.5e12
    scaling_factor = fnum(node_speed, BASE_SPEED) / BASE_SPEED

    if has_gpu:
        scaling_factor = min(7.5, scaling_factor / 10.0)

    scaling_factor = max(1e-9, scaling_factor)
    return fnum(walltime_seconds, 0.0) / scaling_factor


# Function that computes bid based on embeddings
def compute_bid(job, sysdesc, status, current_simulated_time=0.0):

    # Feasibility 
    nodes_req    = fnum(job.get("num_nodes"), 0.0)
    req_gpu      = bool(job.get("needs_gpu", False))
    req_mem      = fnum(job.get("requested_memory_gb"), 0.0)
    req_storage  = fnum(job.get("requested_storage_gb"), 0.0)
    req_walltime = fnum(job.get("walltime"), 0.0)
    job_submission_time = fnum(job.get("submission_time"), 0.0)

    sys_nodes    = fnum(sysdesc.get("num_nodes"), 0.0)
    sys_has_gpu  = bool(sysdesc.get("has_gpu", False))
    sys_speed = fnum(sysdesc.get("node_speed"), 1.0)
    sys_mem_per_node = fnum(sysdesc.get("memory_amount_in_gb"), 0.0)
    sys_total_mem = sys_mem_per_node * sys_nodes
    sys_total_storage = finite_or_inf(sysdesc.get("storage_amount_in_gb", float("inf")))

    if nodes_req > sys_nodes:
        return 0.0
    if req_gpu and not sys_has_gpu:
        return 0.0
    if req_mem > sys_total_mem:
        return 0.0
    if req_storage > sys_total_storage:
        return 0.0
    if req_walltime <= 0:
        return 0.0
    
    job_type = job.get("job_type") or "OTHER"
    job_site = job.get("hpc_site") or ""
    sys_site = sysdesc.get("site") or ""

    SMALL_NODE_THRESHOLD = 256
    SHORT_WALLTIME_THRESHOLD = 4 * 60 * 60

    small_short = (
        nodes_req <= SMALL_NODE_THRESHOLD
        and req_walltime <= SHORT_WALLTIME_THRESHOLD
    )

    # Embeddings for job and site
    e_job = embed_job(job)
    e_sys = embed_system(sysdesc, job_site_hint=job.get("hpc_site"))

    # Relative node availability 
    # Availability / headroom
    sys_avail_nodes = fnum(status.get("current_num_available_nodes"), 0.0)

    # headroom = sys_avail_nodes / max(1.0, nodes_req)
    # headroom_feat = headroom / (1.0 + headroom)

    avail_frac = sys_avail_nodes / max(1.0, sys_nodes)
    relative_headroom = sys_avail_nodes / max(1.0, nodes_req)
    relative_headroom_feat = math.log1p(relative_headroom) / math.log1p(max(2.0, sys_nodes))
    headroom_feat = 0.75 * avail_frac + 0.25 * relative_headroom_feat
    headroom_feat = max(0.0, min(1.0, headroom_feat))

    # Queue penalty
    queued_jobs = fnum(status.get("queue_length"), 0.0)
    running_nodes = max(0.0, min(sys_nodes, sys_nodes - sys_avail_nodes))
    queue_jobs_per_node = queued_jobs / max(1.0, sys_nodes)
    running_node_load = running_nodes / max(1.0, sys_nodes)
    queue_pressure = queue_jobs_per_node + 0.25 * running_node_load
    queue_feat = math.exp(-4.0 * queue_pressure)
    
    # Estimated slowdown using system status
    est_start_time = fnum(status.get("current_job_start_time_estimate"), job_submission_time)
    now = max(current_simulated_time, job_submission_time)
    wait_time = max(0.0, est_start_time - now)
    
    sys_speed = fnum(sysdesc.get("node_speed"), 1.0)
    pred_exec_time = scaled_walltime(walltime_seconds=req_walltime, node_speed=sys_speed, has_gpu=sys_has_gpu)
    slowdown = (wait_time + pred_exec_time) / max(1.0, pred_exec_time)
    alpha = 0.5
    slowdown_feat = math.exp(-alpha * slowdown)

    # Apply AI cross-site data transfer penalty to the time component
    ai_data_xfer_penalty = 0.0
    if job_type == "AI" and job_site and sys_site and (job_site != sys_site):
        seed_string = f"{job.get('job_id')}_{sysdesc.get('name')}_ai_xfer"
        seed_value = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed_value)
        ai_data_xfer_penalty = rng.uniform(0.10, 0.20)
        slowdown_feat = max(0.0, slowdown_feat - ai_data_xfer_penalty)

    BASE_SPEED = 1.5e12
    MAX_SPEED_RATIO = 7.5
    speed_ratio = sys_speed / BASE_SPEED
    if sys_has_gpu:
        speed_ratio = min(MAX_SPEED_RATIO, speed_ratio / 10.0)
    speed_feat = max(0.0, min(1.0, speed_ratio / MAX_SPEED_RATIO))

    completion_time = wait_time + pred_exec_time
    completion_feat = math.exp(-completion_time / max(1.0, req_walltime))

    # dynamic_bid = 0.3 * headroom_feat + 0.7 * slowdown_feat
    # dynamic_bid = (0.25 * headroom_feat + 0.55 * slowdown_feat + 0.20 * queue_feat)
    dynamic_bid = 0.15 * headroom_feat + 0.20 * slowdown_feat + 0.20 * queue_feat + 0.25 * speed_feat + 0.20 * completion_feat

    raw = float(np.dot(e_job, e_sys)) 
    static_bid = max(0.0, raw)
    bid = 0.2 * static_bid + 0.8 * dynamic_bid

    if not math.isfinite(bid):
        bid = 0.0

    return round(float(bid), 6)


def main():
    input_data = sys.stdin.read()
    data = json.loads(input_data)

    job_description = data["job_description"]
    system_description = data["hpc_system_description"]
    system_status = data["hpc_system_status"]
        
    # Start timing
    start_time = time.perf_counter()
    current_simulated_time = fnum(data.get("current_simulated_time"), fnum(job_description.get("submission_time"), 0.0))

    # Compute bids
    try:
        bid = compute_bid(job_description, system_description, system_status, current_simulated_time=current_simulated_time)
    except Exception as e:
        print(json.dumps({"error": str(e)}))

    # End timing
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time

    # Do not modify after here
    result = {
        "bid": bid,
        "bid_generation_time_seconds": round(elapsed_time, 6)
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
