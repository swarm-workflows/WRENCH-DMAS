import sys
import json
import time
import logging
import os
import re
import openai
from HeuristicBidding import compute_bid


#################################
SAMBASTUDIO_URL     = os.getenv('SAMBASTUDIO_URL')
SAMBASTUDIO_API_KEY = os.getenv('SAMBASTUDIO_API_KEY')
SAMBASTUDIO_MODEL   = os.getenv('SAMBASTUDIO_MODEL')
MAX_TOKENS = 100000


os.makedirs("/workspaces/SWARM-DMAS-wrench/logs", exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("/workspaces/SWARM-DMAS-wrench/logs/gptoss_bidder.log"),
        logging.StreamHandler()  # Keep stderr output too
    ]
)
logger = logging.getLogger(__name__)
#################################

def process_request(input_data):
    response = ""
    failure = None  # why the LLM bid could not be obtained, if so
    try:
        data = json.loads(input_data)

        job_description = data["job_description"]
        system_description = data["hpc_system_description"]
        system_status = data["hpc_system_status"]
        runtime_prompt = data.get("prompt")

        # Start timing
        start_time = time.perf_counter()

        # Do not modify before here
        # Step1: Prompt instructions
        if not isinstance(runtime_prompt, str) or not runtime_prompt.strip():
            raise ValueError("No prompt provided. Set 'bidder_prompt_file' in the experiment config.")

        prompt_text = (
            runtime_prompt
            .replace("{job_description}", json.dumps(job_description, indent=2))
            .replace("{system_description}", json.dumps(system_description, indent=2))
            .replace("{system_status}", json.dumps(system_status, indent=2))
        )
        # Log prompt for debugging
        logger.info(f"Prompt:\n{prompt_text}")
        print(f"GPTOSS_PROMPT:\n{prompt_text}", file=sys.stderr, flush=True)
        
        
        client = openai.OpenAI(
                api_key=SAMBASTUDIO_API_KEY,
                base_url=SAMBASTUDIO_URL,
        )


        # Step3: Get completion
        prompt = [
            {"role":"assistant","content":"You are a helpful assistant"},
            {"role":"user","content":prompt_text}]
        response = client.chat.completions.create(model=SAMBASTUDIO_MODEL,
                                                    messages=prompt, 
                                                    temperature=0, 
                                                    top_p=0.1)

        response = response.choices[0].message.content
        print(f"LLM Response: {response}", file=sys.stderr)

    except Exception as e:
        failure = str(e)
        logger.info(json.dumps({"error": str(e)}))

    # Log response for debugging
    logger.info(f"Response:\n{response}")
    print(f"GPTOSS_RESPONSE:\n{response}", file=sys.stderr, flush=True)

    # End timing
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time

    # Step4: Response Parsing
    bid_score_pattern = r'"bid_score":\s*([0-9]*\.?[0-9]+)'
    match = re.search(bid_score_pattern, response)

    # Step5: Heuristic bid if parsing fails
    heuristic_bid = compute_bid(job_description, system_description, system_status)

    bid = round(float(match.group(1)), 3) if match else heuristic_bid
    logger.debug(f"Final bid score: {bid} (using {'LLM' if match else 'heuristic'})")
    logger.debug(f"bid_generation_time_seconds: {round(elapsed_time, 6)}")
    # Do not modify after here
    result = {
        "bid": bid,
        "bid_generation_time_seconds": round(elapsed_time, 6),
        # Tell the simulator whether the LLM or the heuristic fallback produced this bid, so that fallbacks are counted
        "bid_source": "llm" if match else "heuristic_fallback"
    }
    if not match:
        result["fallback_reason"] = failure or "no bid_score in the LLM answer"

    print(json.dumps(result), flush=True)


def main():
    # Process one JSON request per line, so that the simulator can keep this script running as a persistent worker.
    # EOF from the parent ends the worker. A single request without a trailing newline also works.
    for input_data in sys.stdin:
        if input_data.strip():
            process_request(input_data)

if __name__ == "__main__":
    main()
