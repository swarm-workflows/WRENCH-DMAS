import math
import sys
import json
import time
import random
import hashlib

RESOURCE_COMPATIBILITY_TABLE = {

    # ================= HPC JOB =================
    ("HPC", True,  "HPC", True):   (1.00, 1.00),
    ("HPC", True,  "AI", True):    (0.90, 0.95),
    ("HPC", True,  "HYB", True):   (0.90, 0.95),
    ("HPC", True,  "HYB", False):  (0.00, 0.00),
    ("HPC", True,  "STO", False):  (0.00, 0.00),

    ("HPC", False, "HPC", True):   (0.80, 0.90),
    ("HPC", False, "AI", True):    (0.80, 0.90),
    ("HPC", False, "HYB", True):   (0.80, 0.90),
    ("HPC", False, "HYB", False):  (0.90, 0.95),
    ("HPC", False, "STO", False):  (0.70, 0.80),

    # ================= AI JOB =================
    ("AI", True,   "HPC", True):   (0.90, 0.95),
    ("AI", True,   "AI", True):    (1.00, 1.00),
    ("AI", True,   "HYB", True):   (0.90, 0.95),
    ("AI", True,   "HYB", False):  (0.00, 0.00),
    ("AI", True,   "STO", False):  (0.00, 0.00),

    ("AI", False,  "HPC", True):   (0.80, 0.90),
    ("AI", False,  "AI", True):    (0.80, 0.90),
    ("AI", False,  "HYB", True):   (0.80, 0.90),
    ("AI", False,  "HYB", False):  (0.90, 0.95),
    ("AI", False,  "STO", False):  (0.70, 0.80),

    # ================= HYB JOB =================
    ("HYB", True,  "HPC", True):   (0.90, 0.95),
    ("HYB", True,  "AI", True):    (0.90, 0.95),
    ("HYB", True,  "HYB", True):   (1.00, 1.00),
    ("HYB", True,  "HYB", False):  (0.00, 0.00),
    ("HYB", True,  "STO", False):  (0.00, 0.00),

    ("HYB", False, "HPC", True):   (0.80, 0.90),  # 10-20% penalty
    ("HYB", False, "AI", True):    (0.80, 0.90),  # 10-20% penalty
    ("HYB", False, "HYB", True):   (0.80, 0.90),  # 10-20% penalty
    ("HYB", False, "HYB", False):  (1.00, 1.00),  # No penalty for non-GPU HYB job on non-GPU HYB system
    ("HYB", False, "STO", False):  (0.75, 0.85),  # 15-25% penalty

    # ================= STO JOB =================
    ("STO", False, "HPC", True):   (0.70, 0.80),
    ("STO", False, "AI", True):    (0.70, 0.80),
    ("STO", False, "HYB", True):   (0.70, 0.80),
    ("STO", False, "HYB", False):  (0.90, 0.95),
    ("STO", False, "STO", False):  (1.00, 1.00),
}
TYPE_ALIASES = {
    "HPC": "HPC",
    "AI": "AI",
    "HYB": "HYB",
    "HYBRID": "HYB",
    "STO": "STO",
    "STORAGE": "STO",
}
def fnum(x, default=0.0):
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)

def normalize_type_label(value):
    if value is None:
        return ""
    label = str(value).strip().upper()
    return TYPE_ALIASES.get(label, label)
    
def scaled_walltime(walltime_seconds, node_speed, has_gpu=False):
    BASE_SPEED = 1.5e12
    scaling_factor = fnum(node_speed, BASE_SPEED) / BASE_SPEED

    if has_gpu:
        scaling_factor = min(7.5, scaling_factor / 10.0)

    scaling_factor = max(1e-9, scaling_factor)
    return fnum(walltime_seconds, 0.0) / scaling_factor


def compute_bid(job_description, system_description, system_status, current_simulated_time=0.0):

    # Job details
    nodes_req = job_description.get("num_nodes")
    req_gpu = job_description.get("needs_gpu")
    req_mem = job_description.get("requested_memory_gb")
    req_storage = job_description.get("requested_storage_gb")
    req_walltime = job_description.get("walltime") 
    job_type = normalize_type_label(job_description.get("job_type"))
    job_site = job_description.get("hpc_site") 
    job_submission_time = job_description.get("submission_time") # in seconds

    # System configuration
    sys_nodes = system_description.get("num_nodes")
    sys_has_gpu = system_description.get("has_gpu")
    sys_name = system_description.get("name")
    sys_type = normalize_type_label(system_description.get("type"))
    sys_site = system_description.get("site") 
    sys_speed = fnum(system_description.get("node_speed"), 1.5e12)
    sys_total_storage = system_description.get("storage_amount_in_gb", float('inf'))
    
    # System status
    sys_avail_nodes = system_status.get("current_num_available_nodes") 
    # Get a estimated start time
    current_job_start_time_estimate = system_status.get("current_job_start_time_estimate") # in seconds


    # --- 1. Feasibility ---
    # Note: Adding a check for storage capacity if the system defines it
    sys_total_storage = system_description.get("storage_amount_in_gb", float('inf'))
    
    if (nodes_req > sys_nodes):
        return 0.0
    if (req_gpu and not sys_has_gpu):
        return 0.0
    if (req_mem > system_description["memory_amount_in_gb"] * system_description["num_nodes"]): 
        return 0.0
    if (req_storage > sys_total_storage):
        return 0.0
        
    # --- 2. Utilization Score (Preference for availability) ---
    used_nodes = sys_nodes - sys_avail_nodes
    node_util = used_nodes / max(1.0, float(sys_nodes))
    score_util = 1.0 - node_util 
    
    # --- 3. Node Fit Bonus (Preference for jobs that fit well within available resources) ---
    # Node-fit bonus based on job fraction and headroom
    total_nodes = max(1.0, float(sys_nodes))
    required_nodes = max(0.0, float(nodes_req))
    effective_available = max(0.0, float(sys_avail_nodes))
    # how much of the system do i need?
    job_fraction = required_nodes / total_nodes
    
    node_fit_bonus = 0.0
    if job_fraction < 0.2: # <20% of system needed
        node_fit_bonus += 0.12
    elif job_fraction < 0.3: # <30% of system needed
        node_fit_bonus += 0.08
    else:
        node_fit_bonus += 0.04 # even large jobs get a small bonus for fitting at all

    # how much headroom do i have?
    if sys_avail_nodes >= required_nodes * 2.0:
        node_fit_bonus += 0.10
    
    
    # --- 4. Resource Compatibility (Type Matching) ---
    # Goal: Prefer systems that are a good match for the job type and requirements.
    lookup_key = (job_type, req_gpu, sys_type, sys_has_gpu)
    
    if lookup_key in RESOURCE_COMPATIBILITY_TABLE:
        min_score, max_score = RESOURCE_COMPATIBILITY_TABLE[lookup_key]
        # Create deterministic seed from job_id and system_type
        job_id_str = str(job_description.get("job_id"))
        seed_string = f"{job_id_str}_{sys_type}_{job_type}_{req_gpu}_{sys_has_gpu}"
        seed_value = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
        random.seed(seed_value)
        score_resource = random.uniform(min_score, max_score)

    else:
        # Fallback for unexpected combinations
        score_resource = 0.5    # Neutral compatibility, if new job types appear

    
    # --- 5. Time Cost Calculation ---
    # A. Queue Wait Time
    r_j = job_submission_time  # in seconds
    current_job_start_time_estimate = fnum(system_status.get("current_job_start_time_estimate"), job_submission_time)
    wait_time = max(0.0, current_job_start_time_estimate - r_j)
    
    # B. Execution Time (adjusted for hardware speed)
    pred_exec_time = scaled_walltime(walltime_seconds=req_walltime, node_speed=sys_speed, has_gpu=sys_has_gpu)
    
    total_time_cost = wait_time + pred_exec_time
    
    slowdown = max(0.0, total_time_cost) / max(pred_exec_time , 1.0) # both in seconds
    alpha = 0.5
    norm_slowdown = math.exp(-alpha * slowdown) # lower slowdown => higher score
    
    # C. Speed penalty based on system speed relative to a baseline
    BASE_SPEED = 1.5e12
    MAX_SPEED_RATIO = 7.5

    speed_ratio = sys_speed / BASE_SPEED
    if sys_has_gpu:
        speed_ratio = min(MAX_SPEED_RATIO, speed_ratio / 10.0)

    speed_penalty = MAX_SPEED_RATIO - speed_ratio
    speed_penalty_score = 1.0 - (speed_penalty / MAX_SPEED_RATIO)

    # A+B, C combined into a single time score (equally weighted)
    time_score = 0.5 * norm_slowdown + 0.5 * speed_penalty_score
    
    # --- 6. Weighted Aggregation ---
    # Define importance of each factor
    w_util = 0.3      
    w_resource = 0.1  
    w_speed = 0.4    
    w_node_fit = 0.2    
    
    # --- 7. AI data-transfer penalty on final score (10-20%) ---
    ai_data_xfer_penalty = 0.0
    if job_type == "AI" and job_site and sys_site and (job_site != sys_site):
        seed_string = f"{job_description.get('job_id')}_{sys_name}_ai_xfer"
        seed_value = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed_value)
        ai_data_xfer_penalty = rng.uniform(0.10, 0.20)
    
    # Normalization
    final_score = (
        (score_util * w_util) + 
        (score_resource * w_resource) +     
        ((time_score - ai_data_xfer_penalty) * w_speed) + 
        (node_fit_bonus * w_node_fit)
    ) / (w_util + w_resource + w_speed + w_node_fit)

    return round(final_score, 4)

def main():
    try:
        input_data = sys.stdin.read()
        data = json.loads(input_data)
        
        job_description = data["job_description"]
        system_description = data["hpc_system_description"]
        system_status = data["hpc_system_status"]
        
        # Start timing
        start_time = time.perf_counter()

        # Do not modify before here
        # Add logic to generate a bid based on the job and system descriptions and system status here
        bid = compute_bid(job_description, system_description, system_status)

        # End timing
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        # Do not modify after here
        result = {
            "bid": bid,
            "bid_generation_time_seconds": round(elapsed_time, 6)
        }

        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()