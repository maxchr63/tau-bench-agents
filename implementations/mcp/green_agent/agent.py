"""Green agent implementation - manages assessment and evaluation.

VERSION using AgentBeats SDK patterns and tools.
"""

# CRITICAL: Import shared config FIRST to configure LiteLLM before anything else!
import sys
from pathlib import Path
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from implementations.mcp.shared_config import USE_PROVIDER, TAU_USER_MODEL, TAU_USER_PROVIDER
print(f"[GREEN AGENT STARTUP] Loaded config: Provider={USE_PROVIDER}, Model={TAU_USER_MODEL}")

import agentbeats as ab
import uvicorn
import tomllib
import dotenv
import json
import logging

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, SendMessageSuccessResponse, Message
from a2a.utils import new_agent_text_message, get_text_parts

from tau_bench.types import SolveResult, RESPOND_ACTION_NAME, Action

# Import our new tools (local to this implementation)
from . import tools as green_tools

dotenv.load_dotenv()

# Configuration
TAU_TASK_ID = 5  # Change this to test different tasks

# Set up logging
log_file = Path(__file__).parent.parent / "green_agent.log"
# Ensure directory exists
log_file.parent.mkdir(parents=True, exist_ok=True)
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

    This is a mcp-ready version using AgentBeats SDK utilities.
    """
    # Set up battle context if provided
    if battle_id and backend_url:
        battle_context = ab.BattleContext(
            battle_id=battle_id,
            backend_url=backend_url,
            agent_name="tau_green_agent_mcp"
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
        white_tags = green_tools.parse_xml_tags(white_text, "json")
        if not white_tags:
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

        action_json = white_tags
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
    
    VERSION using AgentBeats SDK patterns with pass@k support.
    """

    def __init__(self, agent_card_path: str = "tau_green_agent_mcp"):
        """Initialize executor and load pass@k config from TOML."""
        import tomllib

        current_dir = Path(__file__).parent
        toml_path = current_dir / f"{agent_card_path}.toml"

        with open(toml_path, "rb") as f:
            config = tomllib.load(f)

        self.pass_k_config = config.get("pass_k_config", {
            "mode": "manual",
            "k": 4,
            "domain": "retail",
            "task_id": 5,
            "num_battles": 5
        })
        
        # Track active battles to prevent duplicate processing
        self.active_battles = set()  # Set of battle_ids currently being processed

        logger.info(f"Loaded pass@k config: {self.pass_k_config}")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("=== Green agent received task ===")
        user_input = context.get_user_input()
        logger.info(f"Received user_input: {user_input[:500]}")

        # Parse input - try JSON first (AgentBeats format)
        try:
            battle_info = json.loads(user_input)
            msg_type = battle_info.get("type")
            battle_id = battle_info.get("battle_id")

            if msg_type == "battle_info":
                # Just a notification, acknowledge and return
                # Don't add to active set yet - wait for battle_start
                logger.info("Received battle_info notification, acknowledging")
                await event_queue.enqueue_event(
                    new_agent_text_message("Battle info received, ready for battle start")
                )
                return

            elif msg_type == "battle_start":
                # Check for duplicate battle_start request
                if battle_id and battle_id in self.active_battles:
                    logger.info(f"⚠️  Duplicate battle_start for {battle_id} - already processing, returning acknowledgment")
                    await event_queue.enqueue_event(
                        new_agent_text_message(f"Battle {battle_id} already in progress")
                    )
                    return
                
                # Mark battle as active NOW (when we're actually starting work)
                if battle_id:
                    self.active_battles.add(battle_id)
                    logger.info(f"✅ Added battle {battle_id} to active set, starting evaluation")
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
                    "user_model": green_tools.TAU_USER_MODEL,
                    "user_provider": green_tools.TAU_USER_PROVIDER,
                    "task_split": "test",
                    "task_ids": [TAU_TASK_ID],
                }
            else:
                raise json.JSONDecodeError(f"Unknown message type: {msg_type}", user_input, 0)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Fall back to XML tag parsing (direct launch format)
            logger.info(f"JSON parse failed ({e}), trying XML tag parsing")
            white_agent_url = green_tools.parse_xml_tags(user_input, "white_agent_url")
            env_config_str = green_tools.parse_xml_tags(user_input, "env_config")
            env_config = json.loads(env_config_str)
            battle_info = {}  # No battle info in this case

        logger.info(f"Using white_agent_url: {white_agent_url}")

        # Get battle info for progress updates
        battle_id = battle_info.get("battle_id")
        backend_url = battle_info.get("backend_url") or battle_info.get("green_battle_context", {}).get("backend_url")

        # Determine evaluation mode and task selection
        mode = self.pass_k_config.get("mode", "manual")
        k = self.pass_k_config.get("k", 4)

        logger.info(f"Pass@k evaluation mode: {mode}, k={k}")
        await event_queue.enqueue_event(
            new_agent_text_message(f"🎯 Pass@k evaluation mode: {mode} (k={k})")
        )

        if mode == "manual":
            # Manual mode: Use config from TOML
            domain = self.pass_k_config.get("domain", "retail")
            task_id = self.pass_k_config.get("task_id", 5)
            tasks_to_evaluate = [(domain, task_id)]

            logger.info(f"Manual mode: Evaluating domain={domain}, task_id={task_id}")
            await event_queue.enqueue_event(
                new_agent_text_message(f"📋 Manual mode: {domain} task {task_id}")
            )

        elif mode == "random":
            # Random mode: Generate random task selections
            import random

            num_battles = self.pass_k_config.get("num_battles", 5)
            domains = ["retail", "airline"]
            task_range = list(range(10))  # Assuming 10 tasks per domain

            tasks_to_evaluate = [
                (random.choice(domains), random.choice(task_range))
                for _ in range(num_battles)
            ]

            logger.info(f"Random mode: Generated {num_battles} random tasks")
            await event_queue.enqueue_event(
                new_agent_text_message(
                    f"🎲 Random mode: {num_battles} random tasks\n" +
                    "\n".join([f"  - {d} task {t}" for d, t in tasks_to_evaluate])
                )
            )

        else:
            raise ValueError(f"Unknown evaluation mode: {mode}")

        # Run pass@k evaluation on selected tasks
        all_results = []

        for idx, (domain, task_id) in enumerate(tasks_to_evaluate):
            logger.info(f"\n{'='*60}")
            logger.info(f"Evaluating {idx + 1}/{len(tasks_to_evaluate)}: {domain} task {task_id}")
            logger.info(f"{'='*60}\n")

            await event_queue.enqueue_event(
                new_agent_text_message(
                    f"\n--- Task {idx + 1}/{len(tasks_to_evaluate)}: {domain} task {task_id} ---"
                )
            )

            # Run pass@k evaluation using our tool
            results = await green_tools.evaluate_agent_with_pass_k(
                white_agent_url=white_agent_url,
                domain=domain,
                task_id=task_id,
                k=k,
                max_num_steps=30,
                battle_id=battle_id,
                backend_url=backend_url
            )

            all_results.append(results)

        # Generate aggregate summary across all evaluated tasks
        logger.info("\n" + "="*60)
        logger.info("PASS@K EVALUATION SUMMARY")
        logger.info("="*60)

        total_tasks = len(all_results)
        overall_pass_k = sum(r["pass_k"] for r in all_results) / total_tasks if total_tasks > 0 else 0
        overall_pass_k_half = sum(r["pass_k_half"] for r in all_results) / total_tasks if total_tasks > 0 else 0
        overall_success_rate = sum(r["success_rate"] for r in all_results) / total_tasks if total_tasks > 0 else 0

        logger.info(f"Tasks evaluated: {total_tasks}")
        logger.info(f"Overall pass^{k}: {overall_pass_k:.1%}")
        logger.info(f"Overall pass^{k//2}: {overall_pass_k_half:.1%}")
        logger.info(f"Overall success rate: {overall_success_rate:.1%}")

        # Send final summary to event queue
        summary_lines = [
            "\n" + "="*60,
            "🏁 PASS@K EVALUATION COMPLETE",
            "="*60,
            f"\n**Tasks Evaluated**: {total_tasks}",
            f"**Mode**: {mode}",
            f"**Attempts per task (k)**: {k}",
            "",
            "## Overall Results",
            f"- **pass^{k}**: {overall_pass_k:.1%} ({sum(r['pass_k'] for r in all_results)}/{total_tasks} tasks)",
            f"- **pass^{k//2}**: {overall_pass_k_half:.1%} ({sum(r['pass_k_half'] for r in all_results)}/{total_tasks} tasks)",
            f"- **Success Rate**: {overall_success_rate:.1%}",
            "",
            "## Per-Task Summary"
        ]

        for idx, result in enumerate(all_results):
            pass_k_emoji = "✅" if result["pass_k"] else "❌"
            summary_lines.append(
                f"{idx + 1}. {result['domain']} task {result['task_id']}: "
                f"{pass_k_emoji} pass^{k}={result['pass_k']}, "
                f"success_rate={result['success_rate']:.0%}"
            )

        await event_queue.enqueue_event(
            new_agent_text_message("\n".join(summary_lines))
        )

        # Mark battle as complete in AgentBeats
        # Determine winner: white agent wins if pass@k > 0, otherwise tau-bench (green) wins
        winner = "white_agent" if overall_pass_k > 0 else "tau_green_agent_mcp"
        
        # Only record result if we have battle context
        if battle_id and backend_url:
            battle_context = ab.BattleContext(
                battle_id=battle_id,
                backend_url=backend_url,
                agent_name="tau_green_agent_mcp"
            )
            
            ab.record_battle_result(
                battle_context,
                message=f"✅ Pass@k evaluation complete: {overall_pass_k:.1%} pass^{k}, {overall_success_rate:.1%} success rate",
                winner=winner,
                detail={
                    "overall_pass_k": overall_pass_k,
                    "overall_pass_k_half": overall_pass_k_half,
                    "overall_success_rate": overall_success_rate,
                    "total_tasks": total_tasks,
                    "k": k,
                    "mode": mode,
                    "results": all_results,
                    "winner_rationale": f"White agent achieved {overall_pass_k:.1%} pass^{k} success rate" if overall_pass_k > 0 else "White agent failed all pass@k evaluations"
                }
            )
            logger.info(f"Battle result recorded to AgentBeats. Winner: {winner}")
            
            # Clean up: Remove battle from active set
            if battle_id in self.active_battles:
                self.active_battles.remove(battle_id)
                logger.info(f"✅ Removed battle {battle_id} from active set")
        else:
            logger.info(f"No battle context - skipping AgentBeats result recording. Winner would be: {winner}")
            
            # Still clean up if we have a battle_id
            if battle_id and battle_id in self.active_battles:
                self.active_battles.remove(battle_id)
                logger.info(f"✅ Removed battle {battle_id} from active set")

        logger.info(f"Pass@k evaluation complete! Winner: {winner}")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError

    async def reset(self, context: RequestContext) -> None:
        """Reset the agent state. Called by AgentBeats before each battle."""
        # No state to reset for this stateless evaluation agent
        pass


def start_green_agent(agent_name="tau_green_agent_mcp", host="localhost", port=9003):
    """
    Start the green agent server.

    VERSION using AgentBeats SDK patterns.
    """
    print("Starting green agent (mcp ready version)...")
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
