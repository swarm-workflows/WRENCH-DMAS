import sys
import json
import time

def process_request(input_data):
    data = json.loads(input_data)

    job_description = data["job_description"]
    system_description = data["hpc_system_description"]
    system_status = data["hpc_system_status"]
    current_simulated_time = data["current_simulated_time"]

    # Start timing
    start_time = time.perf_counter()

    try:
        # Do not modify before here
        # Add logic to generate a bid based on the job and system descriptions and system status here
        bid = 0.0

    except Exception as e:
        print(json.dumps({"error": str(e)}), flush=True)
        return

    # End timing
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time

    # Do not modify after here
    result = {
        "bid": round(bid, 3),
        "bid_generation_time_seconds": round(elapsed_time, 6)
    }

    print(json.dumps(result), flush=True)


def main():
    # Process one JSON request per line, so that the simulator can keep this script running as a persistent worker.
    # EOF from the parent ends the worker. A single request without a trailing newline also works.
    for input_data in sys.stdin:
        if input_data.strip():
            process_request(input_data)

if __name__ == "__main__":
    main()
