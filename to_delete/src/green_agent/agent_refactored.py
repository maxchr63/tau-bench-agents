"""Green agent implementation - manages assessment and evaluation.

REFACTORED VERSION using AgentBeats SDK patterns and tools.
"""

import agentbeats as ab
import uvicorn
import tomllib
import dotenv
import json
import time
import logging
import httpx
from pathlib import Path
from datetime import datetime

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, SendMessageSuccessResponse, Message
from a2a.utils import new_agent_text_message, get_text_parts

from tau_bench.envs import get_env
from tau_bench.types import SolveResult, RESPOND_ACTION_NAME, Action
from src.my_util import parse_tags

# Import our new tools
from src.green_agent import tools as green_tools

dotenv.load_dotenv()

# Configuration
TAU_TASK_ID = 5  # Change this to test different tasks

# Set up logging
log_file = Path(__file__).parent.parent.parent / "green_agent.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("green_agent")


def load_agent_card_toml(agent_name):
    """Load agent card from TOML file."""
    current_dir = __file__.rsplit("/", 1)[0]
    with open(f"{current_dir}/{agent_name}.toml", "rb") as f:
        return tomllib.load(f)


async def evaluate_agent_with_tau_bench(
    white_agent_url: str,
    env,
    task_index: int,
    event_queue: EventQueue = None,
    max_num_steps: int = 30,
    battle_id: str = None,
    backend_url: str = None
) -> SolveResult:
    """
    Evaluate white agent using tau-bench environment.

    This is a refactored version using AgentBeats SDK utilities.
    """
    # Set up battle context if provided
    if battle_id and backend_url:
        battle_context = ab.BattleContext(
            battle_id=battle_id,
            backend_url=backend_url,
            agent_name="tau_green_agent"
        )
        ab.set_battle_context(battle_context)
        ab.record_battle_event(
            battle_context,
            f"Starting tau-bench evaluation on task {task_index}",
            {"white_agent_url": white_agent_url, "max_steps": max_num_steps}
        )

    total_cost = 0.0
    env_reset_res = env.reset(task_index=task_index)
    obs = env_reset_res.observation
    info = env_reset_res.info.model_dump()
    reward = 0.0

    # Create initial task description with tools
    task_description = f"""
{env.wiki}
Here's a list of tools you can use (you can use at most one tool at a time):
{json.dumps(env.tools_info, indent=2)}
Please response in the JSON format. Please wrap the JSON part with <json>...</json> tags.
The JSON should contain:
- "name": the tool call function name, or "{RESPOND_ACTION_NAME}" if you want to respond directly.
- "kwargs": the arguments for the tool call, or {{"content": "your message here"}} if you want to respond directly.

Next, I'll provide you with the user message and tool call results.
User message: {obs}
    """

    next_green_message = task_description
    context_id = None

    # Evaluation loop
    for step_num in range(max_num_steps):
        # Log progress using AgentBeats SDK
        if battle_id and backend_url:
            await green_tools.log_battle_progress(
                f"Evaluation step {step_num + 1}/{max_num_steps}...",
                battle_id=battle_id,
                backend_url=backend_url,
                step=step_num + 1,
                total_steps=max_num_steps
            )

        if event_queue:
            await event_queue.enqueue_event(
                new_agent_text_message(f"Evaluation step {step_num + 1}/{max_num_steps}...")
            )

        logger.info(f"Step {step_num + 1}/{max_num_steps}: Sending message to white agent (ctx_id={context_id})")
        logger.info(f"Green agent message (task):\n{next_green_message[:500]}...")

        # Send message using our tools (which use AgentBeats SDK under the hood)
        try:
            result = await green_tools.send_message_to_white_agent(
                white_agent_url,
                next_green_message,
                context_id=context_id,
                timeout=120.0
            )

            if not result["success"]:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"White agent returned error: {error_msg}")

                if event_queue:
                    await event_queue.enqueue_event(
                        new_agent_text_message(f"White agent error at step {step_num + 1}: {error_msg}")
                    )

                return SolveResult(
                    reward=0.0,
                    info={**info, "error": error_msg, "steps_completed": step_num + 1},
                    messages=[],
                    total_cost=total_cost,
                )

            white_agent_response = result["response"]
            res_root = white_agent_response.root

            if not isinstance(res_root, SendMessageSuccessResponse):
                logger.error(f"White agent returned error response: {res_root}")
                return SolveResult(
                    reward=0.0,
                    info={**info, "error": f"White agent error: {res_root}", "steps_completed": step_num + 1},
                    messages=[],
                    total_cost=total_cost,
                )

            res_result = res_root.result
            if not isinstance(res_result, Message):
                logger.error(f"Unexpected result type: {type(res_result)}")
                return SolveResult(
                    reward=0.0,
                    info={**info, "error": "Unexpected response format", "steps_completed": step_num + 1},
                    messages=[],
                    total_cost=total_cost,
                )

        except Exception as e:
            error_msg = "Communication error with white agent"
            error_detail = f"Exception: {type(e).__name__}: {str(e)}"
            logger.error(f"{error_msg}. {error_detail}", exc_info=True)

            if event_queue:
                await event_queue.enqueue_event(
                    new_agent_text_message(f"Error at step {step_num + 1}: {error_msg}")
                )

            return SolveResult(
                reward=0.0,
                info={**info, "error": error_msg, "error_detail": error_detail, "steps_completed": step_num + 1},
                messages=[],
                total_cost=total_cost,
            )

        # Update context ID
        if context_id is None:
            context_id = res_result.context_id
        else:
            assert context_id == res_result.context_id, "Context ID should remain the same"

        # Parse white agent response
        text_parts = get_text_parts(res_result.parts)
        assert len(text_parts) == 1, "Expecting exactly one text part from the white agent"

        white_text = text_parts[0]
        logger.info(f"White agent response received ({len(white_text)} chars)")
        logger.info(f"White agent response (raw):\n{white_text}")

        # Log to AgentBeats if available
        if battle_id and backend_url:
            await green_tools.log_battle_progress(
                f"⚪ **White Agent Response (Step {step_num + 1})**\n```\n{white_text[:500]}{'...' if len(white_text) > 500 else ''}\n```",
                battle_id=battle_id,
                backend_url=backend_url
            )

        # Parse the action from response
        white_tags = parse_tags(white_text)
        if "json" not in white_tags:
            error_msg = "White agent returned improperly formatted response (missing <json> tags)"
            error_detail = f"Response preview: {white_text[:300]}"
            logger.error(f"{error_msg}. {error_detail}")

            if event_queue:
                await event_queue.enqueue_event(
                    new_agent_text_message(f"Error at step {step_num + 1}: White agent response missing <json> tags")
                )

            return SolveResult(
                reward=0.0,
                info={**info, "error": error_msg, "error_detail": error_detail, "steps_completed": step_num + 1},
                messages=[],
                total_cost=total_cost,
            )

        action_json = white_tags["json"]
        try:
            action_dict = json.loads(action_json)
            action = Action(**action_dict)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            error_msg = "White agent returned invalid JSON format"
            error_detail = f"JSON parse error: {str(e)}. Content: {action_json[:300]}"
            logger.error(f"{error_msg}. {error_detail}")

            if event_queue:
                await event_queue.enqueue_event(
                    new_agent_text_message(f"Error at step {step_num + 1}: Invalid JSON in white agent response")
                )

            return SolveResult(
                reward=0.0,
                info={**info, "error": error_msg, "error_detail": error_detail, "steps_completed": step_num + 1},
                messages=[],
                total_cost=total_cost,
            )

        # Execute action in tau-bench environment
        env_response = env.step(action)
        reward = env_response.reward
        info = {**info, **env_response.info.model_dump()}

        # Prepare next message
        if action.name != RESPOND_ACTION_NAME:
            next_green_message = f"""
Tool call result:
{env_response.observation}
            """
        else:
            next_green_message = f"""
User message:
{env_response.observation}
            """

        if env_response.done:
            break

    return SolveResult(
        reward=reward,
        info=info,
        messages=[],
        total_cost=total_cost,
    )


class TauGreenAgentExecutor(AgentExecutor):
    """
    Green agent executor for tau-bench evaluations.

    REFACTORED VERSION using AgentBeats SDK patterns.
    """

    def __init__(self):
        pass

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("=== Green agent received task ===")
        user_input = context.get_user_input()
        logger.info(f"Received user_input: {user_input[:500]}")

        # Parse input - try JSON first (AgentBeats format)
        try:
            battle_info = json.loads(user_input)
            msg_type = battle_info.get("type")

            if msg_type == "battle_info":
                # Just a notification, acknowledge and return
                logger.info("Received battle_info notification, acknowledging")
                await event_queue.enqueue_event(
                    new_agent_text_message("Battle info received, ready for battle start")
                )
                return

            elif msg_type == "battle_start":
                # AgentBeats battle start format
                logger.info("Received battle_start message")
                opponent_infos = battle_info.get("opponent_infos", [])
                if opponent_infos:
                    white_agent_url = opponent_infos[0].get("agent_url")
                else:
                    raise ValueError("No opponent_infos in battle_start message")

                # Use configuration from battle or defaults
                env_config = {
                    "env": "retail",
                    "user_strategy": "llm",
                    "user_model": "gpt-4o-mini",
                    "user_provider": "openai",
                    "task_split": "test",
                    "task_ids": [TAU_TASK_ID],
                }
            else:
                raise json.JSONDecodeError(f"Unknown message type: {msg_type}", user_input, 0)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Fall back to XML tag parsing (direct launch format)
            logger.info(f"JSON parse failed ({e}), trying XML tag parsing")
            tags = parse_tags(user_input)
            white_agent_url = tags["white_agent_url"]
            env_config_str = tags["env_config"]
            env_config = json.loads(env_config_str)
            battle_info = {}  # No battle info in this case

        logger.info(f"Using white_agent_url: {white_agent_url}")
        logger.info(f"Using env_config: {env_config}")

        # Set up tau-bench environment
        logger.info("Setting up tau-bench environment...")
        await event_queue.enqueue_event(
            new_agent_text_message("Setting up tau-bench environment...")
        )

        assert len(env_config["task_ids"]) == 1, "Only single task supported"
        task_index = env_config["task_ids"][0]

        env = get_env(
            env_name=env_config["env"],
            user_strategy=env_config["user_strategy"],
            user_model=env_config["user_model"],
            task_split=env_config["task_split"],
            user_provider=env_config.get("user_provider", None),
            task_index=task_index,
        )

        metrics = {}

        logger.info(f"Starting evaluation of white agent at {white_agent_url}")
        await event_queue.enqueue_event(
            new_agent_text_message(f"Starting evaluation of white agent at {white_agent_url}...")
        )

        timestamp_started = time.time()

        # Get battle info for progress updates
        battle_id = battle_info.get("battle_id")
        backend_url = battle_info.get("backend_url") or battle_info.get("green_battle_context", {}).get("backend_url")

        # Run evaluation using our refactored function
        res = await evaluate_agent_with_tau_bench(
            white_agent_url,
            env,
            task_index,
            event_queue,
            max_num_steps=30,
            battle_id=battle_id,
            backend_url=backend_url
        )

        metrics["time_used"] = time.time() - timestamp_started
        result_bool = metrics["success"] = res.reward == 1
        result_emoji = "✅" if result_bool else "❌"

        logger.info(f"=== Evaluation complete! Success: {result_bool}, Time: {metrics['time_used']:.2f}s ===")

        # Generate user-friendly failure explanation
        failure_reason = ""
        if not result_bool and res.info:
            logger.info("Generating failure reason...")
            task_info = res.info.get("task", {})
            reward_info = res.info.get("reward_info")

            failure_parts = []

            # Add task instruction first for context
            instruction = task_info.get("instruction", "")
            if instruction:
                failure_parts.append(f"**Task**: {instruction}")

            # Check if error occurred
            if "error" in res.info:
                error_msg = res.info.get("error", "Unknown error")
                error_detail = res.info.get("error_detail", "")
                steps_completed = res.info.get("steps_completed", 0)
                failure_parts.append(f"**Error**: {error_msg}")
                if error_detail:
                    failure_parts.append(f"**Details**: {error_detail}")
                failure_parts.append(f"**Steps Completed**: {steps_completed}/30")
            elif reward_info:
                # Check for missing outputs
                actual_outputs = reward_info.get("info", {}).get("outputs", {})
                expected_outputs = task_info.get("outputs", [])

                if expected_outputs and actual_outputs:
                    missing_outputs = [out for out, provided in actual_outputs.items() if not provided]
                    if missing_outputs:
                        failure_parts.append(f"**Missing Required Outputs**: {', '.join(f'`{o}`' for o in missing_outputs)}")

                # Check reward breakdown
                reward_breakdown = reward_info.get("info", {})
                if "r_outputs" in reward_breakdown:
                    output_score = reward_breakdown["r_outputs"]
                    num_expected = len(expected_outputs) if expected_outputs else 1
                    failure_parts.append(f"**Output Score**: {output_score}/{num_expected} - Agent did not provide the required information")

            if failure_parts:
                failure_reason = "\n\n".join(failure_parts)
            else:
                failure_reason = "Agent failed to complete the task successfully. Check logs for details."

        # Report results using AgentBeats SDK
        if battle_id and backend_url:
            logger.info("Reporting battle results to AgentBeats...")

            if result_bool:
                message = "✅ **Tau-bench evaluation PASSED!**\n\nWhite agent successfully completed the task."
            else:
                message = f"❌ **Tau-bench evaluation FAILED**\n\n{failure_reason}"

            await green_tools.report_battle_result(
                success=result_bool,
                message=message,
                metrics={
                    **metrics,
                    "reward": res.reward,
                    "info": res.info
                },
                battle_id=battle_id,
                backend_url=backend_url
            )

        logger.info("Sending final result to event queue...")
        await event_queue.enqueue_event(
            new_agent_text_message(
                f"Finished. White agent success: {result_emoji}\nMetrics: {metrics}\n"
            )
        )
        logger.info("Battle execution complete!")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError

    async def reset(self, context: RequestContext) -> None:
        """Reset the agent state. Called by AgentBeats before each battle."""
        # No state to reset for this stateless evaluation agent
        pass


def start_green_agent(agent_name="tau_green_agent", host="localhost", port=9003):
    """
    Start the green agent server.

    REFACTORED VERSION using AgentBeats SDK patterns.
    """
    print("Starting green agent (refactored version)...")
    agent_card_dict = load_agent_card_toml(agent_name)
    url = f"http://{host}:{port}"
    agent_card_dict["url"] = url

    request_handler = DefaultRequestHandler(
        agent_executor=TauGreenAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=AgentCard(**agent_card_dict),
        http_handler=request_handler,
    )

    uvicorn.run(app.build(), host=host, port=port)
