import sys
import json
import os
import time
import logging
import re

#################################
# Claude OpenAI imports 
from anthropic import AnthropicVertex
from google.oauth2 import service_account
#################################
# Model Setup
CLAUDE_LOCATION   = os.getenv("CLAUDE_LOCATION")
CLAUDE_PROJECT_ID = os.getenv("CLAUDE_PROJECT_ID")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL")
TEMP = 0
MAX_TOKENS = 5000
#################################
# Logs
logging.basicConfig(level=logging.INFO)
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

        # Step2: Format prompt
        message = [{"role": "user", "content": prompt}]

        # Step3: Setup Openai client
        client = AnthropicVertex(region=CLAUDE_LOCATION, project_id=CLAUDE_PROJECT_ID)

        # Step4: Get completion
        response = client.messages.create(
            model=CLAUDE_MODEL,
            messages=message,
            max_tokens=MAX_TOKENS,
            temperature=TEMP,
        )
        for content_block in response.content:
            response = content_block.text
        # Log response for debugging
        logger.debug(f"Response: {response}")

    except Exception as e:
        print(json.dump({"error" : str(e)}))

    # End timing
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time

    # Step5: Response Parsing
    bid_score_pattern = r'"bid_score":\s*([0-9]*\.?[0-9]+)'
    match = re.search(bid_score_pattern, response)

    # Step6: Heuristic bid if parsing fails
    heuristic_bid = 0.5  # Change later with the heuristic logic as needed!  

    bid = float(match.group(1)) if match else heuristic_bid

    # Do not modify after here
    result = {
      "bid": bid,
      "bid_generation_time_seconds": round(elapsed_time, 6)
    }
    logger.info(json.dumps(result))
    print(json.dumps(result))

if __name__ == "__main__":
    main()
