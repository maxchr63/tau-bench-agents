"""Green agent implementation - manages assessment and evaluation."""

# CRITICAL: Import shared config FIRST to configure LiteLLM before anything else!
import sys
from pathlib import Path
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from implementations.mcp.shared_config import USE_PROVIDER, TAU_USER_MODEL, TAU_USER_PROVIDER
print(f"[GREEN AGENT STARTUP] Loaded config: Provider={USE_PROVIDER}, Model={TAU_USER_MODEL}")

import uvicorn
import tomllib
import dotenv
import json
import logging
import time

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from a2a.utils import new_agent_text_message

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


class TauGreenAgentExecutor(AgentExecutor):
    """
    Green agent executor for tau-bench evaluations.
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
        
        logger.info(f"Loaded pass@k config: {self.pass_k_config}")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("=== Green agent received task ===")
        user_input = context.get_user_input()
        logger.info(f"Received user_input: {user_input[:500]}")

        # Parse input - look for XML tags first as in reference implementation
        # Or try to parse JSON if it looks like JSON
        white_agent_url = None
        env_config = None
        
        try:
            # Try parsing XML tags (agentify-example style)
            white_agent_url = green_tools.parse_xml_tags(user_input, "white_agent_url")
            env_config_str = green_tools.parse_xml_tags(user_input, "env_config")
            
            if white_agent_url and env_config_str:
                logger.info("Parsed input using XML tags")
                env_config = json.loads(env_config_str)
            else:
                # Try JSON parsing (AgentBeats style)
                input_json = json.loads(user_input)
                
                if "opponent_infos" in input_json:
                    # AgentBeats battle_start format
                    logger.info("Parsed input as AgentBeats battle_start JSON")
                    opponent_infos = input_json.get("opponent_infos", [])
                    if opponent_infos:
                        white_agent_url = opponent_infos[0].get("agent_url")
                    
                    # Default env config for battle mode
                    env_config = {
                        "env": "retail",
                        "user_strategy": "llm",
                        "user_model": green_tools.TAU_USER_MODEL,
                        "user_provider": green_tools.TAU_USER_PROVIDER,
                        "task_split": "test",
                        "task_ids": [TAU_TASK_ID],
                    }
                elif "white_agent_url" in input_json:
                    # Simple JSON format
                    logger.info("Parsed input as simple JSON")
                    white_agent_url = input_json["white_agent_url"]
                    env_config = input_json.get("env_config")

        except Exception as e:
            logger.error(f"Error parsing input: {e}")
            await event_queue.enqueue_event(
                new_agent_text_message(f"Error parsing input: {str(e)}")
            )
            return

        if not white_agent_url:
            logger.error("Could not determine white_agent_url")
            await event_queue.enqueue_event(
                new_agent_text_message("Error: Could not determine white_agent_url from input.")
            )
            return

        logger.info(f"Using white_agent_url: {white_agent_url}")

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
            # Allow optional control of white-agent restarts between attempts via TOML
            reset_between_attempts = bool(self.pass_k_config.get("reset_between_attempts", False))
            
            # Pass event_queue directly for real-time updates
            results = await green_tools.evaluate_agent_with_pass_k(
                white_agent_url=white_agent_url,
                domain=domain,
                task_id=task_id,
                k=k,
                max_num_steps=30,
                reset_between_attempts=reset_between_attempts,
                event_queue=event_queue
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

        # Determine winner: white agent wins if pass@k > 0
        winner = "white_agent" if overall_pass_k > 0 else "tau_green_agent_mcp"
        logger.info(f"Pass@k evaluation complete! Winner: {winner}")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError

    async def reset(self, context: RequestContext) -> None:
        """Reset the agent state."""
        # No state to reset for this stateless evaluation agent
        pass


def start_green_agent(agent_name="tau_green_agent_mcp", host="localhost", port=9006, **kwargs):
    """
    Start the green agent server.

    VERSION using AgentBeats SDK patterns.
    """
    import os
    print("Starting green agent (mcp ready version)...")
    if kwargs:
        print(f"Green agent received additional kwargs: {kwargs}")
    
    agent_card_dict = load_agent_card_toml(agent_name)
    
    # Determine the public URL for the agent card
    # Priority: AGENT_URL env var > construct from host/port (using localhost for 0.0.0.0)
    url = os.environ.get("AGENT_URL")
    if not url:
        # Use localhost for the URL even when binding to 0.0.0.0
        url_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
        url = f"http://{url_host}:{port}"
    agent_card_dict["url"] = url
    print(f"Green agent URL: {url}")

    request_handler = DefaultRequestHandler(
        agent_executor=TauGreenAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=AgentCard(**agent_card_dict),
        http_handler=request_handler,
    )

    uvicorn.run(app.build(), host=host, port=port)
