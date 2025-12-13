"""Green agent implementation - manages assessment and evaluation."""

# Fast imports first - get the server up quickly
import asyncio
import sys
import os
from pathlib import Path
import uvicorn
import tomllib
import json
import logging
import time
import re
from urllib.parse import urlparse, urlunparse
import uuid

# Setup path before any local imports
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Fast A2A imports (these are lightweight)
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCard, MessageSendConfiguration, MessageSendParams, Part, TextPart

# LAZY IMPORTS: Heavy modules (litellm, tau-bench) are imported only when needed
# This allows the A2A server to start immediately and respond to health checks
green_tools = None  # Lazy loaded on first request
_config_loaded = False
USE_PROVIDER = os.environ.get("USE_PROVIDER", "openrouter")
TAU_USER_MODEL = os.environ.get("TAU_USER_MODEL", "openrouter/anthropic/claude-haiku-4.5")
TAU_USER_PROVIDER = os.environ.get("TAU_USER_PROVIDER", "openrouter")

def _lazy_load_tools():
    """Lazy load heavy dependencies on first use."""
    global green_tools, _config_loaded, USE_PROVIDER, TAU_USER_MODEL, TAU_USER_PROVIDER
    if green_tools is None:
        print("[GREEN AGENT] Lazy loading tools and config (first request)...")
        import dotenv
        dotenv.load_dotenv()
        # Now load the heavy modules
        from implementations.mcp.shared_config import USE_PROVIDER as _UP, TAU_USER_MODEL as _TM, TAU_USER_PROVIDER as _TP
        USE_PROVIDER, TAU_USER_MODEL, TAU_USER_PROVIDER = _UP, _TM, _TP
        from . import tools as _tools
        green_tools = _tools
        _config_loaded = True
        print(f"[GREEN AGENT] Tools loaded. Provider={USE_PROVIDER}, Model={TAU_USER_MODEL}")
    return green_tools

# Configuration
# Evaluation defaults live in `tau_green_agent_mcp.toml` (pass@k config).

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


def _normalize_agent_url(url: str) -> str:
    """Normalize externally-provided agent URLs.

    - Trims whitespace
    - Removes trailing slash
    - Collapses repeated slashes in the *path* (e.g. `/to_agent/...`, not the `https://` part)
    """
    url = (url or "").strip()
    if not url:
        return url

    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        norm_path = re.sub(r"/{2,}", "/", parsed.path or "")
        url = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                norm_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    return url.rstrip("/")


def _bool_from_env(name: str) -> bool | None:
    v = os.environ.get(name)
    if v is None:
        return None
    v = v.strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return None


def _default_blocking_behavior(public_url: str | None) -> bool:
    """Pick a sane default for A2A blocking mode.

    Prefer blocking by default so clients that don't implement task polling
    still receive a final result in the `message/send` response.

    If you *want* non-blocking behavior (return a Task immediately), set:
      A2A_DEFAULT_BLOCKING=false
    """

    override = _bool_from_env("A2A_DEFAULT_BLOCKING")
    if override is not None:
        return override
    return True


class TauRequestHandler(DefaultRequestHandler):
    """Request handler with configurable blocking default.

    Some clients (like Earthshaker) do not set `configuration.blocking`.
    We default to blocking so those clients receive a final result in the
    `message/send` response. You can force non-blocking via:

      A2A_DEFAULT_BLOCKING=false
    """

    def __init__(self, *args, default_blocking: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self._default_blocking = default_blocking

    async def on_message_send(  # type: ignore[override]
        self,
        params: MessageSendParams,
        context=None,
    ):
        if self._default_blocking:
            return await super().on_message_send(params, context)

        # If caller didn't specify blocking, default to non-blocking.
        if params.configuration is None or params.configuration.blocking is None:
            cfg = params.configuration or MessageSendConfiguration()
            cfg = cfg.model_copy(update={"blocking": False})
            params = params.model_copy(update={"configuration": cfg})

        return await super().on_message_send(params, context)


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

        # NOTE: Requests routed through trycloudflare.com often hit a ~100s
        # "time to first byte" limit (HTTP 524) if we don't return quickly.
        #
        # AgentBeats/Earthshaker should send `configuration.blocking=false` for
        # long-running assessments. In that mode, the server can return quickly
        # with a Task after our first TaskStatusUpdateEvent, and continue
        # evaluation in the background while updating task state.
        a2a_task_id = context.task_id or uuid.uuid4().hex
        a2a_context_id = context.context_id or uuid.uuid4().hex
        updater = TaskUpdater(event_queue=event_queue, task_id=a2a_task_id, context_id=a2a_context_id)

        blocking = None
        try:
            blocking = context.configuration.blocking if context.configuration else None
        except Exception:
            blocking = None
        logger.info(
            f"[A2A] request configuration blocking={blocking!r} task_id={a2a_task_id} context_id={a2a_context_id}"
        )

        # Detect if we are running behind a Cloudflare quick tunnel.
        # (The controller sets AGENT_URL to the externally reachable URL.)
        agent_url_env = (os.environ.get("AGENT_URL") or os.environ.get("CLOUDRUN_HOST") or "").lower()
        is_cloudflare = "trycloudflare.com" in agent_url_env
        cloudflare_blocking = is_cloudflare and (blocking is not False)

        await updater.start_work(
            message=updater.new_agent_message(
                parts=[Part(root=TextPart(text="Starting tau-bench evaluation..."))]
            )
        )
        
        # Lazy load heavy dependencies on first request
        tools = _lazy_load_tools()
        
        user_input = context.get_user_input()
        logger.info(f"Received user_input: {user_input[:500]}")

        # Parse input - look for XML tags first as in reference implementation
        # Or try to parse JSON if it looks like JSON
        white_agent_url = None
        env_config = None
        
        try:
            # Try parsing XML tags (agentify-example style)
            white_agent_url = tools.parse_xml_tags(user_input, "white_agent_url")
            env_config_str = tools.parse_xml_tags(user_input, "env_config")
            
            if white_agent_url:
                # AgentBeats often provides ONLY <white_agent_url> without an <env_config>.
                # Accept that and fall back to defaults / TOML config.
                logger.info("Parsed input using XML tags")
                white_agent_url = _normalize_agent_url(white_agent_url)
                if env_config_str:
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
                    # Note: battle_start payloads typically don't include tau-bench task config.
                    # Use the TOML defaults unless the caller explicitly provides an env_config.
                elif "white_agent_url" in input_json:
                    # Simple JSON format
                    logger.info("Parsed input as simple JSON")
                    white_agent_url = input_json["white_agent_url"]
                    env_config = input_json.get("env_config")

        except Exception as e:
            logger.error(f"Error parsing input: {e}")
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=f"Error parsing input: {e}"))]
                )
            )
            return

        if not white_agent_url:
            logger.error("Could not determine white_agent_url")
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[
                        Part(
                            root=TextPart(
                                text="Error: Could not determine white_agent_url from input."
                            )
                        )
                    ]
                )
            )
            return

        white_agent_url = _normalize_agent_url(white_agent_url)

        logger.info(f"Using white_agent_url: {white_agent_url}")

        # Evaluation defaults from TOML
        mode = (self.pass_k_config.get("mode", "manual") or "manual").strip().lower()
        k = int(self.pass_k_config.get("k", 4))
        max_num_steps = int(self.pass_k_config.get("max_num_steps", 30))
        reset_between_attempts = bool(self.pass_k_config.get("reset_between_attempts", False))

        # Cloudflare-safe defaults:
        # If the client is making a blocking call (the common case for Earthshaker),
        # we keep evaluation bounded so the HTTP request can complete before
        # Cloudflare's ~100s timeout.
        if cloudflare_blocking and not (isinstance(env_config, dict) and env_config):
            k = int(os.environ.get("CLOUDFLARE_K", "1"))
            max_num_steps = int(os.environ.get("CLOUDFLARE_MAX_NUM_STEPS", "12"))
            reset_between_attempts = False
            logger.info(
                f"[CLOUDFLARE] Blocking request detected; using fast defaults k={k}, max_num_steps={max_num_steps}"
            )

        # If the caller provided an explicit env_config (agentify-example style),
        # prefer it for task selection to keep the interface simple.
        tasks_to_evaluate: list[tuple[str, int]]
        if isinstance(env_config, dict) and env_config:
            logger.info("Using env_config override from request payload")

            domain = (
                (env_config.get("env") or env_config.get("domain") or self.pass_k_config.get("domain") or "retail")
                .strip()
                .lower()
            )

            task_ids = env_config.get("task_ids")
            if task_ids is None:
                task_ids = env_config.get("task_id")

            if isinstance(task_ids, int):
                task_ids = [task_ids]
            if not task_ids:
                task_ids = [int(self.pass_k_config.get("task_id", 5))]

            tasks_to_evaluate = [(domain, int(t)) for t in task_ids]

            # Optional overrides:
            # - env_config *defaults* to k=1 unless explicitly provided
            # - max_num_steps/reset_between_attempts fall back to TOML defaults
            if env_config.get("k") is not None:
                k = int(env_config["k"])
            else:
                k = 1

            if env_config.get("max_num_steps") is not None:
                max_num_steps = int(env_config["max_num_steps"])

            if env_config.get("reset_between_attempts") is not None:
                reset_between_attempts = bool(env_config["reset_between_attempts"])

            logger.info(
                f"Override: domain={domain}, task_ids={[t for _, t in tasks_to_evaluate]}, k={k}, max_steps={max_num_steps}"
            )
        else:
            logger.info(f"Pass@k evaluation mode: {mode}, k={k}")

            if mode == "manual":
                domain = str(self.pass_k_config.get("domain", "retail")).strip().lower()
                tau_task_id = int(self.pass_k_config.get("task_id", 5))
                tasks_to_evaluate = [(domain, tau_task_id)]
                logger.info(f"Manual mode: Evaluating domain={domain}, task_id={tau_task_id}")

            elif mode == "random":
                import random

                num_battles = int(self.pass_k_config.get("num_battles", 5))
                domains = ["retail", "airline"]
                task_range = list(range(10))  # keep small for stability

                tasks_to_evaluate = [
                    (random.choice(domains), int(random.choice(task_range)))
                    for _ in range(num_battles)
                ]
                logger.info(f"Random mode: Generated {num_battles} random tasks")

            else:
                raise ValueError(f"Unknown evaluation mode: {mode}")

        # Run pass@k evaluation on selected tasks
        all_results = []

        try:
            for idx, (domain, tau_task_id) in enumerate(tasks_to_evaluate):
                logger.info(f"\n{'='*60}")
                logger.info(
                    f"Evaluating {idx + 1}/{len(tasks_to_evaluate)}: {domain} task {tau_task_id}"
                )
                logger.info(f"{'='*60}\n")

                # IMPORTANT: do not pass the A2A event_queue into the evaluator.
                # Message events would be treated as terminal and cause premature queue shutdown.
                eval_coro = tools.evaluate_agent_with_pass_k(
                    white_agent_url=white_agent_url,
                    domain=domain,
                    task_id=tau_task_id,
                    k=k,
                    max_num_steps=max_num_steps,
                    reset_between_attempts=reset_between_attempts,
                    event_queue=None,
                )

                if cloudflare_blocking:
                    import asyncio

                    timeout_s = float(os.environ.get("CLOUDFLARE_BLOCKING_TIMEOUT_S", "90"))
                    results = await asyncio.wait_for(eval_coro, timeout=timeout_s)
                else:
                    results = await eval_coro

                all_results.append(results)
        except asyncio.TimeoutError:
            msg = (
                "Evaluation timed out (Cloudflare blocking request). "
                "Reduce k/max steps or run with A2A_DEFAULT_BLOCKING=false and poll tasks."
            )
            logger.error(msg, exc_info=True)
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=msg))]
                )
            )
            return
        except Exception as e:
            logger.error(f"Evaluation failed: {e}", exc_info=True)
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[
                        Part(
                            root=TextPart(
                                text=f"Evaluation failed: {type(e).__name__}: {e}"
                            )
                        )
                    ]
                )
            )
            return

        # Generate aggregate summary across all evaluated tasks
        logger.info("\n" + "="*60)
        logger.info("PASS@K EVALUATION SUMMARY")
        logger.info("="*60)

        total_tasks = len(all_results)
        k_half = max(1, k // 2)
        overall_pass_k = sum(r["pass_k"] for r in all_results) / total_tasks if total_tasks > 0 else 0
        overall_pass_k_half = sum(r["pass_k_half"] for r in all_results) / total_tasks if total_tasks > 0 else 0
        overall_success_rate = sum(r["success_rate"] for r in all_results) / total_tasks if total_tasks > 0 else 0

        logger.info(f"Tasks evaluated: {total_tasks}")
        logger.info(f"Overall pass^{k}: {overall_pass_k:.1%}")
        logger.info(f"Overall pass^{k_half}: {overall_pass_k_half:.1%}")
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
            f"- **pass^{k_half}**: {overall_pass_k_half:.1%} ({sum(r['pass_k_half'] for r in all_results)}/{total_tasks} tasks)",
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

        await updater.complete(
            message=updater.new_agent_message(
                parts=[Part(root=TextPart(text="\n".join(summary_lines)))]
            )
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


def start_green_agent(agent_name="tau_green_agent_mcp", host="localhost", port=9006, public_url=None):
    """
    Start the green agent server.
    
    Args:
        agent_name: Name of the agent
        host: Host to bind to
        port: Port to bind to
        public_url: Public URL for the agent card (from CLOUDRUN_HOST).
                    If None, uses localhost.
    """
    print("Starting green agent (mcp ready version)...")
    
    agent_card_dict = load_agent_card_toml(agent_name)
    
    # URL for agent card: use public_url if provided, otherwise localhost
    if public_url:
        url = public_url
    else:
        url_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
        url = f"http://{url_host}:{port}"
    
    agent_card_dict["url"] = url
    print(f"Green agent URL: {url}")

    default_blocking = _default_blocking_behavior(url)
    if not default_blocking:
        logger.info("[A2A] Defaulting to NON-BLOCKING message/send (Cloudflare-safe)")

    request_handler = TauRequestHandler(
        agent_executor=TauGreenAgentExecutor(),
        task_store=InMemoryTaskStore(),
        default_blocking=default_blocking,
    )

    app = A2AStarletteApplication(
        agent_card=AgentCard(**agent_card_dict),
        http_handler=request_handler,
    )

    starlette_app = app.build()
    try:
        from starlette.responses import JSONResponse
        from starlette.requests import Request

        async def health(_: Request):
            return JSONResponse({"status": "ok", "agent": "green"})

        starlette_app.add_route("/health", health, methods=["GET"])
    except Exception:
        pass

    uvicorn.run(starlette_app, host=host, port=port)
