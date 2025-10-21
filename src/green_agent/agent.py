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
            logger.error(f"Error communicating with white agent: {e}")
            if event_queue:
                await event_queue.enqueue_event(
                    new_agent_text_message(f"Error at step {step_num + 1}: {str(e)}")
                )
            return SolveResult(
                reward=0.0,
                info={**info, "error": str(e), "steps_completed": step_num + 1},
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
        action_json = white_tags["json"]
        action_dict = json.loads(action_json)
        action = Action(**action_dict)

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
                    "user_model": "gpt-5",  # Changed to GPT-5
                    "user_provider": "openai",
                    "task_split": "test",
                    "task_ids": [1],
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
        
        if battle_id and backend_url:
            logger.info(f"Reporting battle results to AgentBeats: {backend_url}")
            try:
                from datetime import datetime
                async with httpx.AsyncClient() as client:
                    # Use correct AgentBeats API endpoint format
                    report_url = f"{backend_url}/battles/{battle_id}"
                    report_data = {
                        "is_result": True,
                        "message": f"Tau-bench evaluation completed. White agent {'succeeded' if result_bool else 'failed'}.",
                        "winner": "green" if result_bool else "red",  # Green wins if white agent passes evaluation
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
                logger.error(f"Error reporting battle results: {e}")
        
        await event_queue.enqueue_event(
            new_agent_text_message(
                f"Finished. White agent success: {result_emoji}\nMetrics: {metrics}\n"
            )
        )  # alternative, impl as a task-generating agent

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
