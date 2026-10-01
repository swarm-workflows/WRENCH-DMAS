import sys
import json
import os
import time
import logging
import re
from pathlib import Path
from HeuristicBidding import compute_bid
import google.auth
from google.auth.transport.requests import Request
from anthropic import AnthropicVertex
from google.oauth2 import service_account

# -----------------------------
# Model setup
# -----------------------------
CLAUDE_LOCATION   = os.getenv("CLAUDE_LOCATION")
CLAUDE_PROJECT_ID = os.getenv("CLAUDE_PROJECT_ID")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL")
TEMP = 0
MAX_TOKENS = 5000
TIMEOUT = 30.0 # seconds
MAX_RETRIES = 0 # no retries

# -----------------------------
# Logging setup
# -----------------------------
def safe_name(value):
    value = str(value or "unknown")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def setup_logger(data):
    job_description = data.get("job_description", {})
    system_description = data.get("hpc_system_description", {})

    workload_name = (
        os.getenv("LLM_WORKLOAD_NAME")
        or data.get("workload_name")
        or job_description.get("workload_name")
        or job_description.get("workflow_name")
        or "unknown_workload"
    )

    system_name = system_description.get("name", "unknown_system")

    log_file = os.getenv("LLM_LOG_FILE")
    if not log_file:
        log_dir = os.getenv("LLM_LOG_DIR", "logs")
        log_file = os.path.join(
            log_dir,
            f"{safe_name(workload_name)}.log"
        )

    Path(os.path.dirname(log_file)).mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("llm_claude_bidder")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_file, mode="a")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(file_handler)

    logger.info("Logging to %s", log_file)
    logger.info("Workload=%s System=%s", workload_name, system_name)

    return logger


# #################################
# # Logs - provide a log_path here
# log_path = os.environ.get(
#     "LLM_LOG_FILE",
#     "results/llm_logs/business_large_long_rho0.9.log"
# )
# os.makedirs(os.path.dirname(log_path), exist_ok=True)
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s %(levelname)s: %(message)s",
#     handlers=[
#         logging.FileHandler(log_path)
#     ]
# )
# logger = logging.getLogger(__name__)
#################################


# -----------------------------
# Feasibility check function to short-circuit obviously infeasible jobs before calling the LLM to save time and cost on LLM calls
# -----------------------------
def is_feasible_system(job_description, system_description):
    nodes_req = job_description.get("num_nodes")
    req_gpu = job_description.get("needs_gpu")
    req_mem = job_description.get("requested_memory_gb")
    req_storage = job_description.get("requested_storage_gb")

    sys_nodes = system_description.get("num_nodes")
    sys_has_gpu = system_description.get("has_gpu")
    sys_mem_per_node = system_description.get("memory_amount_in_gb")
    sys_total_storage = system_description.get("storage_amount_in_gb", float("inf"))

    if nodes_req is not None and sys_nodes is not None and nodes_req > sys_nodes:
        return False, "nodes"
    if req_gpu and not sys_has_gpu:
        return False, "gpu"
    if req_mem is not None and sys_mem_per_node is not None and sys_nodes is not None:
        if req_mem > (sys_mem_per_node * sys_nodes):
            return False, "memory"
    if req_storage is not None and req_storage > sys_total_storage:
        return False, "storage"

    return True, ""

def main():
    
    llm_response = ""
    job_description = None
    system_description = None
    system_status = None
    logger=None

    try:
        input_data = sys.stdin.read()
        data = json.loads(input_data)

        logger = setup_logger(data)
        logger.info(f"="*80)
        job_description = data["job_description"]
        system_description = data["hpc_system_description"]
        system_status = data["hpc_system_status"]
        runtime_prompt = data.get("prompt")

        start_time = time.perf_counter()

        job_id = job_description.get("job_id", "unknown")
        system_name = system_description.get("name", "unknown")
        print(f"Processing job {job_id} on machine {system_name}", file=sys.stderr, flush=True)

        feasible, infeasible_reason = is_feasible_system(job_description, system_description)
        if not feasible:
            elapsed_time = time.perf_counter() - start_time
            result = {
                "bid": 0.0,
                "bid_generation_time_seconds": round(elapsed_time, 6)
            }
            logger.info("Feasibility check failed (%s); returning zero bid", infeasible_reason)
            logger.info("Result: %s", json.dumps(result))
            print(json.dumps(result))
            return

        # Step1: Prompt instructions
        if not isinstance(runtime_prompt, str) or not runtime_prompt.strip():
            raise ValueError("No prompt provided. Set 'bidder_prompt_file' in the experiment config.")

        prompt = (
            runtime_prompt
            .replace("{job_description}", json.dumps(job_description, indent=2))
            .replace("{system_description}", json.dumps(system_description, indent=2))
            .replace("{system_status}", json.dumps(system_status, indent=2))
        )

        # To save log space, only log Job id, system status, system name instead of full prompt
        logger.info("Prompt for job %s submitted on system %s with status %s", job_description.get("job_id", "unknown"), system_description.get("name", "unknown"), system_status)
        # Uncomment the following line to log the full prompt, but be aware it can be very long 
        # logger.info("Prompt:\n%s", prompt)

        # Step2: Format prompt
        message = [{"role": "user", "content": prompt}]

        # Measure (isolated) OAuth token acquisition/refresh explicitly
        oauth_t0 = time.perf_counter()
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        oauth_elapsed = time.perf_counter() - oauth_t0

        logger.info("OAuth refresh time_seconds=%.6f", oauth_elapsed)
        
        # Step3: Setup Anthropic client on Vertex AI for all requests made by this client instance
        client = AnthropicVertex(
            region=CLAUDE_LOCATION,
            project_id=CLAUDE_PROJECT_ID,
            timeout=TIMEOUT,
            max_retries=MAX_RETRIES,
        )

        # Step4: Get completion (LLM inference timing)
        llm_t0 = time.perf_counter()
        response = client.messages.create(
            model=CLAUDE_MODEL,
            messages=message,
            max_tokens=MAX_TOKENS,
            temperature=TEMP,
        )
        llm_elapsed = time.perf_counter() - llm_t0
        logger.info("LLM inference call time_seconds=%.6f", llm_elapsed)

        for content_block in response.content:
            llm_response = content_block.text

        logger.info("Response:\n%s", llm_response)

    except Exception as e:
        if logger:
            logger.error("Claude bidder request failed; will fall back to heuristic: %s", e)
            # logger.exception("Claude bidder request failed; will fall back to heuristic")
        else:
            print(f"Claude bidder failed before logger setup: {e}", file=sys.stderr)

    elapsed_time = time.perf_counter() - start_time

    if job_description is None or system_description is None or system_status is None:
        result = {
            "bid": 0.0,
            "bid_generation_time_seconds": round(elapsed_time, 6)
        }
        if logger:
            logger.error("Input unavailable after exception; returning zero bid")
        print(json.dumps(result))
        return

    # Step5: Response Parsing
    bid_score_pattern = r'"bid_score":\s*([0-9]*\.?[0-9]+)'
    match = re.search(bid_score_pattern, llm_response)

    # Compute heuristic bid for logging and fallback
    heuristic_bid = compute_bid(job_description, system_description, system_status)

    if logger:
        logger.info(
            "Job %s: Heuristic bid=%.4f, LLM bid=%s",
            job_description.get("job_id", "unknown"),
            heuristic_bid,
            match.group(1) if match else "parsing_failed"
        )
    
    # Step6: Fallback to the Heuristic bid if parsing fails
    bid = float(match.group(1)) if match else heuristic_bid

    # Log which bid is being used (LLM vs Heuristic)
    if logger:
        logger.info(
            "Job %s: Using %s bid",
            job_description.get("job_id", "unknown"),
            "LLM" if match else "Heuristic"
        )

    result = {
        "bid": bid,
        "bid_generation_time_seconds": round(elapsed_time, 6)
    }

    if logger:
        logger.info(json.dumps(result))

    print(json.dumps(result))

if __name__ == "__main__":
    main()
