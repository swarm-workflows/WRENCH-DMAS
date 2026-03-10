import math
import sys
import json
import time
import random
import hashlib

RESOURCE_COMPATIBILITY_TABLE = {
    # HPC + GPU
    ("HPC", True, "Frontier"): (1.00, 1.00),
    ("HPC", True, "Aurora"): (0.90, 0.95),
    ("HPC", True, "Perlmutter-Phase-1"): (0.90, 0.95),
    
    # HPC + CPU
    ("HPC", False, "Frontier"): (0.80, 0.90),
    ("HPC", False, "Aurora"): (0.80, 0.90),
    ("HPC", False, "Perlmutter-Phase-1"): (0.80, 0.90),
    ("HPC", False, "Andes"): (0.70, 0.80),
    ("HPC", False, "Crux"): (0.70, 0.80),
    ("HPC", False, "Perlmutter-Phase-2"): (0.90, 0.95),
    
    # AI + GPU
    ("AI", True, "Frontier"): (0.90, 0.95),
    ("AI", True, "Aurora"): (1.00, 1.00),
    ("AI", True, "Perlmutter-Phase-1"): (0.90, 0.95),
    
    # HYBRID + GPU
    ("HYBRID", True, "Frontier"): (0.90, 0.95),
    ("HYBRID", True, "Aurora"): (0.90, 0.95),
    ("HYBRID", True, "Perlmutter-Phase-1"): (1.00, 1.00),
    
    # HYBRID + CPU
    ("HYBRID", False, "Frontier"): (0.80, 0.90),
    ("HYBRID", False, "Aurora"): (0.80, 0.90),
    ("HYBRID", False, "Perlmutter-Phase-1"): (0.80, 0.90),
    ("HYBRID", False, "Andes"): (0.75, 0.85),
    ("HYBRID", False, "Crux"): (0.75, 0.85),
    ("HYBRID", False, "Perlmutter-Phase-2"): (1.00, 1.00),
    
    # STORAGE + CPU (storage jobs don't require GPU)
    ("STORAGE", False, "Frontier"): (0.70, 0.80),
    ("STORAGE", False, "Aurora"): (0.70, 0.80),
    ("STORAGE", False, "Perlmutter-Phase-1"): (0.70, 0.80),
    ("STORAGE", False, "Andes"): (1.00, 1.00),
    ("STORAGE", False, "Crux"): (1.00, 1.00),
    ("STORAGE", False, "Perlmutter-Phase-2"): (0.90, 0.95),
}

def compute_bid(job_description, system_description, system_status, current_simulated_time=0):
    """Compute a heuristic bid score for a job on a given system_description.
    
    Args:
        job (dict): JobDescription "job_id", "user_id","group_id", "job_type",
            "submission_time", "walltime", "num_nodes", "needs_gpu", "requested_memory_gb", "requested_storage_gb",
            "hpc_site", "hpc_system"
        hpc_system (dict): HPC System description: "name", "type", "num_nodes",
            "memory_amount_in_gb", "storage_amount_in_gb", "has_gpu", "network_interconnect"
        system_status (dict): HPC System status: "current_num_available_nodes", "current_job_start_time_estimate", "queue_length"
        current_time (int): Current time in the scheduling system for wait time calculations.
    Returns:
        float 0.0 to 1.0.
    """
    # Job details
    nodes_req = job_description.get("num_nodes")
    req_gpu = job_description.get("needs_gpu")
    req_mem = job_description.get("requested_memory_gb")
    req_storage = job_description.get("requested_storage_gb")
    req_walltime = job_description.get("walltime") 
    job_type = job_description.get("job_type")
    job_site = job_description.get("hpc_site") 

    # System configuration
    sys_nodes = system_description.get("num_nodes")
    sys_has_gpu = system_description.get("has_gpu")
    sys_name = system_description.get("name")
    sys_type = system_description.get("type")
    sys_site = system_description.get("site") 
    # Performance Index for each machine: 
    # Usually, the standard CPU partition is the baseline in our case is the Perlmutter (Phase 2, CPU nodes, 4.9Tf) as a Baseline 1.0
    # E.g., Aurora (312Tf) gets a score of 63.6 (it is 63x faster than the CPU node). 
    # Andes gets 0.36 (it is slower).)
    sys_speed = system_description.get("node_speed") # in TFLOPS
    base_sys_speed = 1.5e12
    sys_perf = round(sys_speed / base_sys_speed, 2)
    # system_description["network_gbps"] by default is 200 Gbps for each one described in AmSC.xml
    sys_network_gbps = 200 
    
    # System status
    sys_avail_nodes = system_status.get("current_num_available_nodes")
    # Get a estimated start time
    est_start_time = system_status.get("current_job_start_time_estimate")

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
    # Goal: Prefer systems that aren't hammered, but don't kill busy systems if they are fast.
    used_nodes = sys_nodes - sys_avail_nodes
    node_util = used_nodes / max(1.0, float(sys_nodes))
    score_util = 1.0 - node_util 
    
    # --- 3. Resource Compatibility (Type Matching) ---
    lookup_key = (job_type, req_gpu, sys_name)
    
    if lookup_key in RESOURCE_COMPATIBILITY_TABLE:
        min_score, max_score = RESOURCE_COMPATIBILITY_TABLE[lookup_key]
        # print(f"{min_score}, {max_score}", file=sys.stderr)
        # Create deterministic seed from job_id and system_name
        job_id_str = str(job_description.get("job_id"))
        seed_string = f"{job_id_str}_{sys_name}_{job_type}_{req_gpu}"
        seed_value = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
        random.seed(seed_value)
        score_resource = random.uniform(min_score, max_score)
        print(f"{sys_name}: score_resource: {score_resource:.5f}", file=sys.stderr)
    else:
        # Fallback for unexpected combinations
        score_resource = 0.5    # Neutral compatibility, if new job types appear
    
    # --- 4. Time Cost Calculation ---
    # A. Queue Wait Time
    wait_time = max(0, est_start_time - current_simulated_time) 
    
    # B. Execution Time (adjusted for hardware speed)
    pred_exec_time = req_walltime / sys_perf
    
    # C. Data Transfer Time
    if job_site and sys_site and (job_site != sys_site):
        # Convert Gbps to GB
        sys_bw_gb_per_unit = (sys_network_gbps / 8.0) 
        transfer_time = (req_storage / sys_bw_gb_per_unit) + 5.0 # 5 time units overhead
    else:
        transfer_time = 0.0

    total_time_cost = wait_time + pred_exec_time + transfer_time
    
    # Protect against divide by zero
    total_time_cost = max(1.0, total_time_cost)
    # Speed Score (Sigmoid)
    slowdown = total_time_cost / req_walltime
    alpha = 1.0
    score_speed = math.exp(-alpha * slowdown) 

    # --- 6. Weighted Aggregation ---
    # Define importance of each factor
    w_util = 0.6      # Change to Low weight: Don't worry too much if system is busy ~ 0.1
    w_resource = 0.1  # Change to Medium: Prefer correct hardware types ~ 0.3
    w_speed = 0.3    # Change to High: User cares most about "When is my job done?" ~ 0.6

    # Normalization
    final_score = (
        (score_util * w_util) + 
        (score_resource * w_resource) + 
        (score_speed * w_speed)
    ) / (w_util + w_resource + w_speed)
    
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
