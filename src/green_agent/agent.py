"""Green agent implementation - manages assessment and evaluation."""

import uvicorn
import tomllib
import dotenv
import json
import time
import logging
import httpx
from pathlib import Path
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, SendMessageSuccessResponse, Message
from a2a.utils import new_agent_text_message, get_text_parts
from src.my_util import parse_tags, my_a2a

# set max num_steps to solve stuff  max_num_steps = 5
# change env_config = if I want to change the model

# TODO: Change to [2], [3], [4], [5], [6], [7], [8], etc. to test different tasks
TAU_TASK_ID = 5 # task ID seems 4 causes a false json return at the moment

# from tau_bench.agents.tool_calling_agent import ToolCallingAgent
from tau_bench.envs import get_env
from tau_bench.types import SolveResult, RESPOND_ACTION_NAME, Action

dotenv.load_dotenv()

# Set up logging to file
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
    current_dir = __file__.rsplit("/", 1)[0]
    with open(f"{current_dir}/{agent_name}.toml", "rb") as f:
        return tomllib.load(f)


async def send_battle_update(battle_id: str, backend_url: str, message: str, step: int = None, total_steps: int = None):
    """Send progress update to AgentBeats backend."""
    try:
        from datetime import datetime
        async with httpx.AsyncClient() as client:
            update_data = {
                "is_result": False,
                "message": message,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "reported_by": "tau_green_agent",
            }
            if step is not None and total_steps is not None:
                update_data["detail"] = {"step": step, "total_steps": total_steps}
            
            response = await client.post(
                f"{backend_url}/battles/{battle_id}",
                json=update_data,
                timeout=5.0
            )
            if response.status_code != 204:
                logger.debug(f"Battle update failed: {response.status_code}")
    except Exception as e:
        logger.debug(f"Error sending battle update: {e}")


async def ask_agent_to_solve(white_agent_url, env, task_index, event_queue=None, max_num_steps=30, battle_id=None, backend_url=None):
    total_cost = 0.0
    env_reset_res = env.reset(task_index=task_index)
    obs = env_reset_res.observation
    info = env_reset_res.info.model_dump()
    reward = 0.0

    # messages = [
    #     {"role": "system", "content": env.wiki},
    #     {"role": "user", "content": obs},
    # ]

    # Here, instead of calling white agent like calling an LLM, we need to present
    #   the assessment scenario to the white agent as if it is a independent task
    # Specifically, here we provide the tool information for the agent to reply with
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
    for step_num in range(max_num_steps):
        # Send progress update to AgentBeats backend
        if battle_id and backend_url:
            await send_battle_update(
                battle_id,
                backend_url,
                f"Evaluation step {step_num + 1}/{max_num_steps}...",
                step=step_num + 1,
                total_steps=max_num_steps
            )
        
        # Also send to event queue if available (though it may be closed)
        if event_queue:
            await event_queue.enqueue_event(
                new_agent_text_message(f"Evaluation step {step_num + 1}/{max_num_steps}...")
            )
        
        # # --> messages (message history)
        # res = completion(
        #     messages=messages,
        #     model=self.model,
        #     custom_llm_provider=self.provider,
        #     tools=self.tools_info,
        #     temperature=self.temperature,
        # )
        # next_message = res.choices[0].message.model_dump()
        # total_cost += res._hidden_params["response_cost"] or 0
        # action = message_to_action(next_message)
        # # --> action (to be executed in the environment)
        logger.info(f"Step {step_num + 1}/{max_num_steps}: Sending message to white agent (ctx_id={context_id})")
        logger.info(f"Green agent message (task):\n{next_green_message}")
        
        # Send task message to AgentBeats UI
        if battle_id and backend_url:
            await send_battle_update(
                battle_id,
                backend_url,
                f"🟢 **Green Agent -> White Agent (Step {step_num + 1})**\n```\n{next_green_message[:500]}{'...' if len(next_green_message) > 500 else ''}\n```"
            )
        
        try:
            white_agent_response = await my_a2a.send_message(
                white_agent_url, next_green_message, context_id=context_id
            )
            res_root = white_agent_response.root
            
            if not isinstance(res_root, SendMessageSuccessResponse):
                logger.error(f"White agent returned error response: {res_root}")
                # Send update about the error
                if event_queue:
                    await event_queue.enqueue_event(
                        new_agent_text_message(f"White agent error at step {step_num + 1}: {res_root}")
                    )
                # Return incomplete result
                return SolveResult(
                    reward=0.0,  # Failed evaluation
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
            error_msg = f"Communication error with white agent"
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
        if context_id is None:
            context_id = res_result.context_id
        else:
            assert context_id == res_result.context_id, (
                "Context ID should remain the same in a conversation"
            )

        text_parts = get_text_parts(res_result.parts)
        assert len(text_parts) == 1, (
            "Expecting exactly one text part from the white agent"
        )
        white_text = text_parts[0]
        logger.info(f"White agent response received ({len(white_text)} chars)")
        logger.info(f"White agent response (raw):\n{white_text}")
        
        # Send white agent response to AgentBeats UI
        if battle_id and backend_url:
            await send_battle_update(
                battle_id,
                backend_url,
                f"⚪ **White Agent -> Green Agent (Step {step_num + 1})**\n```\n{white_text[:500]}{'...' if len(white_text) > 500 else ''}\n```"
            )
        
        # parse the action out
        white_tags = parse_tags(white_text)
        if "json" not in white_tags:
            error_msg = f"White agent returned improperly formatted response (missing <json> tags)"
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

        env_response = env.step(action)
        reward = env_response.reward
        info = {**info, **env_response.info.model_dump()}

        # instead of maintain history, just prepare the next message with the latest observation
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
        messages=[],  # incompatible, thus removed
        total_cost=total_cost,
    )


class TauGreenAgentExecutor(AgentExecutor):
    def __init__(self):
        pass

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("=== Green agent received task ===")
        user_input = context.get_user_input()
        logger.info(f"Received user_input: {user_input[:500]}")  # First 500 chars
        
        # Try to parse as JSON first (AgentBeats format)
        try:
            battle_info = json.loads(user_input)
            msg_type = battle_info.get("type")
            
            if msg_type == "battle_info":
                # This is just a notification message, acknowledge and return
                logger.info("Received battle_info notification, acknowledging")
                await event_queue.enqueue_event(
                    new_agent_text_message("Battle info received, ready for battle start")
                )
                return  # Wait for the actual battle_start message
                
            elif msg_type == "battle_start":
                # AgentBeats battle start format
                logger.info("Received battle_start message")
                opponent_infos = battle_info.get("opponent_infos", [])
                if opponent_infos:
                    white_agent_url = opponent_infos[0].get("agent_url")
                else:
                    raise ValueError("No opponent_infos in battle_start message")
                
                # Extract config from task_config or use defaults
                task_config_str = battle_info.get("green_battle_context", {}).get("task_config", "")
                # Parse task config or use defaults
                # TODO: use if we want to use claude-haiku
                # env_config = {
                #     "env": "retail",
                #     "user_strategy": "llm",
                #     "user_model": "claude-haiku-4-5-20251001",
                #     "user_provider": "anthropic",
                #     "task_split": "test",
                #     "task_ids": [1],
                # }

                # if we want to use gpt-5
                env_config = {
                    "env": "retail",
                    "user_strategy": "llm",
                    "user_model": "gpt-4o-mini",  # Changed to GPT-4o-mini, can also use gpt-5 instead
                    "user_provider": "openai",
                    "task_split": "test",
                    "task_ids": [TAU_TASK_ID], # TODO: Change to [2], [3], [4], [5], [6], [7], [8], etc. to test different tasks
                }
            else:
                # JSON but unknown type, try XML parsing
                raise json.JSONDecodeError(f"Unknown message type: {msg_type}", user_input, 0)
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Fall back to XML tag parsing (direct launch format)
            logger.info(f"JSON parse failed or unknown format ({e}), trying XML tag parsing")
            tags = parse_tags(user_input)
            white_agent_url = tags["white_agent_url"]
            env_config_str = tags["env_config"]
            env_config = json.loads(env_config_str)
        
        logger.info(f"Using white_agent_url: {white_agent_url}")
        logger.info(f"Using env_config: {env_config}")

        # set up the environment
        # migrate from https://github.com/sierra-research/tau-bench/blob/4754e6b406507dbcbce8e8b3855dcf80aaec18ac/tau_bench/run.py#L20
        logger.info("Setting up tau-bench environment...")
        await event_queue.enqueue_event(
            new_agent_text_message("Setting up tau-bench environment...")
        )
        
        assert len(env_config["task_ids"]) == 1, (
            "Only single task supported for demo purpose"
        )
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
        # TODO: replace
        # agent = ToolCallingAgent(
        #     tools_info=env.tools_info,
        #     wiki=env.wiki,
        #     model="openai/gpt-4o",
        #     provider="openai",
        # )
        # res = agent.solve(
        #     env=env,
        #     task_index=task_index,
        # )
        
        # Get battle info for progress updates
        battle_id = battle_info.get("battle_id")
        backend_url = battle_info.get("backend_url") or battle_info.get("green_battle_context", {}).get("backend_url")
        
        # Pass event_queue and battle info to evaluation function for progress updates
        res = await ask_agent_to_solve(
            white_agent_url, 
            env, 
            task_index, 
            event_queue,
            battle_id=battle_id,
            backend_url=backend_url
        )

        metrics["time_used"] = time.time() - timestamp_started
        result_bool = metrics["success"] = res.reward == 1
        result_emoji = "✅" if result_bool else "❌"

        logger.info(f"=== Evaluation complete! Success: {result_bool}, Time: {metrics['time_used']:.2f}s ===")
        
        # Generate user-friendly failure explanation
        failure_reason = ""
        try:
            if not result_bool and res.info:
                logger.info("Generating failure reason...")
                task_info = res.info.get("task", {})
                reward_info = res.info.get("reward_info")
                
                logger.info(f"DEBUG - task_info keys: {list(task_info.keys()) if task_info else 'None'}")
                logger.info(f"DEBUG - reward_info keys: {list(reward_info.keys()) if reward_info else 'None'}")
                
                # Extract what was expected vs what happened
                expected_outputs = task_info.get("outputs", [])
                instruction = task_info.get("instruction", "")
                
                logger.info(f"DEBUG - expected_outputs: {expected_outputs}")
                logger.info(f"DEBUG - instruction: {instruction[:100] if instruction else 'None'}")
                
                failure_parts = []
                
                # Add the task instruction FIRST for context
                if instruction:
                    failure_parts.append(f"**Task**: {instruction}")
                
                # Check if error occurred (reward_info will be None for errors)
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
                    logger.info(f"DEBUG - actual_outputs: {actual_outputs}")
                    
                    if expected_outputs and actual_outputs:
                        missing_outputs = [out for out, provided in actual_outputs.items() if not provided]
                        if missing_outputs:
                            failure_parts.append(f"**Missing Required Outputs**: {', '.join(f'`{o}`' for o in missing_outputs)}")
                    
                    # Check reward breakdown
                    reward_breakdown = reward_info.get("info", {})
                    if "r_outputs" in reward_breakdown:
                        output_score = reward_breakdown["r_outputs"]
                        num_expected = len(expected_outputs) if expected_outputs else 1
                        failure_parts.append(f"**Output Score**: {output_score}/{num_expected} - Agent did not provide the required information to the user")
                
                if failure_parts:
                    failure_reason = "\n\n".join(failure_parts)
                else:
                    failure_reason = "Agent failed to complete the task successfully. Check logs for details."
                
                logger.info(f"DEBUG - Generated failure_reason length: {len(failure_reason)}")
        except Exception as e:
            logger.error(f"Error generating failure reason: {e}", exc_info=True)
            failure_reason = f"Agent failed to complete the task. Error details: {str(e)}"
        
        # ALWAYS report results to AgentBeats, even if there was an error above
        if battle_id and backend_url:
            logger.info(f"Reporting battle results to AgentBeats: {backend_url}")
            try:
                from datetime import datetime
                async with httpx.AsyncClient() as client:
                    # Use correct AgentBeats API endpoint format
                    report_url = f"{backend_url}/battles/{battle_id}"
                    
                    # Create user-friendly message
                    if result_bool:
                        message = "✅ **Tau-bench evaluation PASSED!**\n\nWhite agent successfully completed the task."
                    else:
                        message = f"❌ **Tau-bench evaluation FAILED**\n\n{failure_reason}"
                    
                    report_data = {
                        "is_result": True,
                        "message": message,
                        "winner": "white" if result_bool else "green",  # White wins if it passes evaluation, green wins if white fails
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "reported_by": "tau_green_agent",
                        "detail": {
                            "metrics": metrics,
                            "reward": res.reward,
                            "info": res.info,
                        }
                    }
                    response = await client.post(report_url, json=report_data, timeout=10.0)
                    if response.status_code == 204:
                        logger.info("Successfully reported battle results to AgentBeats")
                    else:
                        logger.warning(f"Failed to report battle results: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error reporting battle results to AgentBeats backend: {e}", exc_info=True)
        
        logger.info("Sending final result to event queue...")
        await event_queue.enqueue_event(
            new_agent_text_message(
                f"Finished. White agent success: {result_emoji}\nMetrics: {metrics}\n"
            )
        )  # alternative, impl as a task-generating agent
        logger.info("Battle execution complete!")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError

    async def reset(self, context: RequestContext) -> None:
        """Reset the agent state. Called by AgentBeats before each battle."""
        # No state to reset for this stateless evaluation agent
        pass


def start_green_agent(agent_name="tau_green_agent", host="localhost", port=9003):
    print("Starting green agent...")
    agent_card_dict = load_agent_card_toml(agent_name)
    url = f"http://{host}:{port}"
    agent_card_dict["url"] = url  # complete all required card fields

    request_handler = DefaultRequestHandler(
        agent_executor=TauGreenAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=AgentCard(**agent_card_dict),
        http_handler=request_handler,
    )

    uvicorn.run(app.build(), host=host, port=port)
