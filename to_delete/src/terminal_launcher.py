"""Launcher module - initiates and coordinates the evaluation process."""

import multiprocessing
import json
from src.green_agent.agent import start_green_agent
from src.white_agent.agent import start_white_agent
from src.my_util import my_a2a


async def launch_evaluation():
    # start green agent
    print("Launching green agent...")
    green_address = ("localhost", 9003)
    green_url = f"http://{green_address[0]}:{green_address[1]}"
    p_green = multiprocessing.Process(
        target=start_green_agent, args=("tau_green_agent", *green_address)
    )
    p_green.start()
    assert await my_a2a.wait_agent_ready(green_url), "Green agent not ready in time"
    print("Green agent is ready.")

    # start white agent
    print("Launching white agent...")
    white_address = ("localhost", 9004)
    white_url = f"http://{white_address[0]}:{white_address[1]}"
    p_white = multiprocessing.Process(
        target=start_white_agent, args=("general_white_agent", *white_address)
    )
    p_white.start()
    assert await my_a2a.wait_agent_ready(white_url), "White agent not ready in time"
    print("White agent is ready.")

    # send the task description
    print("Sending task description to green agent...")

    # TODO: modify task_config as needed and change back to anthropic model
    # task_config = {
    #     "env": "retail",
    #     "user_strategy": "llm",
    #     # "user_model": "claude-3-7-sonnet-20250219",  # Changed to Claude 3.5 Sonnet
    #     "user_model": "claude-haiku-4-5-20251001",  # ← Faster, cheaper
    #     "user_provider": "anthropic",
    #     "task_split": "test",
    #     "task_ids": [1],
    # }

    # changed to gpt-5
    task_config = {
        "env": "retail",
        "user_strategy": "llm",
        "user_model": "gpt-5",  # Changed to GPT-5
        "user_provider": "openai",
        "task_split": "test",
        "task_ids": [1],
    }


    task_text = f"""
Your task is to instantiate tau-bench to test the agent located at:
<white_agent_url>
http://{white_address[0]}:{white_address[1]}/
</white_agent_url>
You should use the following env configuration:
<env_config>
{json.dumps(task_config, indent=2)}
</env_config>
    """
    print("Task description:")
    print(task_text)
    print("Sending...")
    response = await my_a2a.send_message(green_url, task_text)
    print("Response from green agent:")
    print(response)

    print("Evaluation complete. Terminating agents...")
    p_green.terminate()
    p_green.join()
    p_white.terminate()
    p_white.join()
    print("Agents terminated.")
