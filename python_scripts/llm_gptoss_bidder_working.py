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

def main():
    response = ""
    try:
        input_data = sys.stdin.read()
        data = json.loads(input_data)

        job_description = data["job_description"]
        system_description = data["hpc_system_description"]
        system_status = data["hpc_system_status"]

        # Start timing
        start_time = time.perf_counter()

        # Do not modify before here
        # Step1: Prompt instructions
        prompt = f"""
                You are an HPC_RESOURCE agent, managing a massive supercomputer cluster in a decentralized resource allocation system. 
                IMPORTANT:
                - The fields hpc_site and hpc_system in JOB_REQUEST indicate only where the job was SUBMITTED (origin), NOT where it must run.
                - You MUST NOT reward or penalize this system just because its site/system matches or differs from the job’s origin.


                JOB_REQUEST (MASSIVE SCALE):
                {
                    job_description
                }

                SYSTEM CAPABILITIES:
                {
                    system_description,
                }

                SYSTEM STATUS:
                {
                    system_status
                }

                TASK:
                1. Evaluate the incoming job request above.
                2. Compute your resource-job suitability score [0-1] based on system capabilites and status.
                3. Share your reasoning and score in JSON block:
                        {{
                            "bid_score": <value>
                            "reasoning": "<justification>"

                        }}
                """
        # Log prompt for debugging
        logger.debug(f"Prompt: {prompt}")
        
        
        client = openai.OpenAI(
                api_key=SAMBASTUDIO_API_KEY,
                base_url=SAMBASTUDIO_URL,
        )


        # Step3: Get completion
        prompt = [
            {"role":"assistant","content":"You are a helpful assistant"},
            {"role":"user","content":prompt}]
        response = client.chat.completions.create(model=SAMBASTUDIO_MODEL,
                                                    messages=prompt, 
                                                    temperature=0, 
                                                    top_p=0.1)

        response = response.choices[0].message.content
        print(f"LLM Response: {response}", file=sys.stderr)

    except Exception as e:
        logger.info(json.dumps({"error": str(e)}))

    # Log response for debugging
    logger.debug(f"Response: {response}")

    # End timing
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time

    # Step4: Response Parsing
    bid_score_pattern = r'"bid_score":\s*([0-9]*\.?[0-9]+)'
    match = re.search(bid_score_pattern, response)

    # Step5: Heuristic bid if parsing fails
    heuristic_bid = compute_bid(job_description, system_description, system_status)

    bid = float(match.group(1)) if match else heuristic_bid
    logger.debug(f"Final bid score: {bid} (using {'LLM' if match else 'heuristic'})")
    logger.debug(f"bid_generation_time_seconds: {round(elapsed_time, 6)}")
    # Do not modify after here
    result = {
        "bid": bid,
        "bid_generation_time_seconds": round(elapsed_time, 6)
    }

    print(json.dumps(result))

if __name__ == "__main__":
    main()
