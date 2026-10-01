import sys
import json
import time

# Reuse the compute_bid function from HeuristicBidding
from EmbeddingBidding import compute_bid


def main():
    try:
        input_data = sys.stdin.read()
        data = json.loads(input_data)

        job_description = data["job_description"]
        systems = data["systems"]
        current_simulated_time = data.get("current_simulated_time", 0)

        start_time = time.perf_counter()

        # Compute a bid for every system; winner selection is done in C++
        bids = {
            s["system_name"]: compute_bid(job_description, s["description"], s["status"], current_simulated_time)
            for s in systems
        }

        elapsed_time = time.perf_counter() - start_time

        print(json.dumps({"bids": bids, "decision_time_seconds": round(elapsed_time, 6)}))
    except Exception as e:
        print(json.dumps({"error": str(e), "bids": {}}))


if __name__ == "__main__":
    main()
