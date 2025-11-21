# -*- coding: utf-8 -*-
"""
Tau-Bench Green Agent Tools

This module exposes tau-bench evaluation tools using the AgentBeats SDK.
These tools can be used directly by agents or exposed through MCP servers.
"""

import json
import logging
import sys
from typing import Dict, Any, Optional, TYPE_CHECKING

# ============================================================================
# GLOBAL LLM CONFIGURATION - CHANGE HERE TO SWITCH PROVIDERS
# ============================================================================
# CRITICAL: Import shared config FIRST to configure LiteLLM before any other imports
from implementations.mcp.shared_config import USE_PROVIDER, TAU_USER_MODEL, TAU_USER_PROVIDER

# NOW import tau-bench (after LiteLLM is configured)
import agentbeats as ab
from tau_bench.envs import get_env
from tau_bench.types import RESPOND_ACTION_NAME, Action

# Import AgentCard for type annotation
from a2a.types import AgentCard
import httpx  # Pre-import httpx to avoid per-call import overhead/hangs

if TYPE_CHECKING:
    import httpx

# Set up logging
logger = logging.getLogger("green_agent.tools")

# ============================================================================
# HTTP CLIENT CONFIGURATION
# ============================================================================

# Cache agent card to avoid repeated fetches
_cached_agent_card: Optional[AgentCard] = None
_card_cache_url: Optional[str] = None

def _get_httpx_client(timeout: float = 120.0) -> "httpx.AsyncClient":
    """
    Create a FRESH httpx client for each call.

    CRITICAL: Do NOT reuse clients! Stale connections cause hanging.
    Each evaluation attempt gets a fresh client to avoid connection state issues.
    """
    # ALWAYS create a fresh client - no global caching!
    # Reusing clients leads to stale/CLOSED connections that hang indefinitely
    limits = httpx.Limits(
        max_keepalive_connections=0,   # DISABLE keepalive completely - no connection reuse
        max_connections=5,              # Lower limit to prevent socket exhaustion
        keepalive_expiry=1.0            # Very short expiry
    )
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=5.0),  # Shorter connect timeout
        limits=limits,
        http2=False,  # Disable HTTP/2 to avoid protocol issues
        trust_env=False,  # Ignore env proxies/netrc to avoid surprises
        follow_redirects=False  # Don't follow redirects
    )
    logger.info(f"[DEBUG] Created FRESH httpx client (timeout={timeout}s, keepalive=DISABLED)")

    return client


# ============================================================================
# COMMUNICATION TOOLS - Using AgentBeats SDK
# ============================================================================

@ab.tool
async def send_message_to_white_agent(
    white_agent_url: str,
    message: str,
    context_id: Optional[str] = None,
    timeout: float = 120.0
) -> Dict[str, Any]:
    """
    Send a message to the white agent and get a response.

    Args:
        white_agent_url: URL of the white agent to communicate with
        message: The message to send
        context_id: Optional context ID to maintain conversation continuity
        timeout: Timeout in seconds (default: 120)

    Returns:
        Dict containing response, context_id, and metadata
    """
    try:
        from a2a.client import A2AClient, A2ACardResolver
        from a2a.types import (
            Message, Part, TextPart, Role,
            SendMessageRequest, MessageSendParams
        )
        from uuid import uuid4
        import asyncio

        # Use FRESH httpx client for each call to avoid stale connections
        httpx_client = _get_httpx_client(timeout)

        try:
            # Use cached agent card if available for same URL
            global _cached_agent_card, _card_cache_url
            if _cached_agent_card and _card_cache_url == white_agent_url:
                card = _cached_agent_card
            else:
                resolver = A2ACardResolver(httpx_client=httpx_client, base_url=white_agent_url)
                try:
                    card = await asyncio.wait_for(
                        resolver.get_agent_card(relative_card_path="/.well-known/agent-card.json"),
                        timeout=5.0
                    )
                    _cached_agent_card = card
                    _card_cache_url = white_agent_url
                except asyncio.TimeoutError:
                    raise TimeoutError("Agent card fetch timeout after 5s")

            if card is None:
                raise RuntimeError(f"Failed to resolve agent card from {white_agent_url}")

            client = A2AClient(httpx_client=httpx_client, agent_card=card)

            # Send message
            params = MessageSendParams(
                message=Message(
                    role=Role.user,
                    parts=[Part(TextPart(text=message))],
                    message_id=uuid4().hex,
                    task_id=None,
                    context_id=context_id,
                )
            )

            request_id = uuid4().hex
            req = SendMessageRequest(id=request_id, params=params)

            logger.info(f"[A2A] >>> Sending to white agent (len={len(message)}, ctx={context_id})")

            try:
                response = await asyncio.wait_for(client.send_message(request=req), timeout=timeout)
                logger.info("[A2A] <<< Received response")
            except asyncio.TimeoutError:
                raise TimeoutError(f"Message send timeout after {timeout}s")

            return {
                "success": True,
                "response": response,
                "context_id": context_id,
                "message_id": request_id
            }

        finally:
            await httpx_client.aclose()

    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__

        if "429" in error_msg or "rate" in error_msg.lower():
            logger.error(f"Rate limit error: {error_msg}")
        elif "timeout" in error_type.lower():
            logger.error(f"Timeout error: {error_msg}")
        elif "401" in error_msg or "unauthorized" in error_msg.lower():
            logger.error(f"Auth error: {error_msg}")
        else:
            logger.error(f"Error sending message: {error_type}: {error_msg}")

        return {
            "success": False,
            "error": error_msg,
            "error_type": error_type
        }


@ab.tool
async def reset_white_agent(white_agent_url: str, timeout: float = 30.0) -> Dict[str, Any]:
    """
    Reset the white agent's memory state by restarting it via the launcher.
    This ensures complete memory isolation between evaluation attempts.

    Args:
        white_agent_url: URL of the white agent (e.g., http://localhost:9004)
        timeout: Timeout in seconds

    Returns:
        Dict with success status and message
    """
    global _cached_agent_card, _card_cache_url

    try:
        import re
        import asyncio

        logger.info(f"[RESET] Resetting white agent at {white_agent_url}")

        # Extract host and port from URL
        match = re.match(r'https?://([^:]+):(\d+)', white_agent_url)
        if not match:
            return {"success": False, "error": "Invalid URL format"}

        host, port = match.groups()
        launcher_url = f"http://{host}:9210"

        httpx_client = _get_httpx_client(timeout)
        try:
            # Terminate the white agent
            await httpx_client.post(f"{launcher_url}/terminate", timeout=timeout)
            await asyncio.sleep(1.0)

            # Relaunch the white agent
            launch_response = await httpx_client.post(f"{launcher_url}/launch", timeout=timeout)

            if launch_response.status_code == 200:
                # Wait for agent to be ready
                start = asyncio.get_event_loop().time()
                probe_path = "/.well-known/agent-card.json"
                while (asyncio.get_event_loop().time() - start) < timeout:
                    try:
                        resp = await httpx_client.get(f"{white_agent_url}{probe_path}", timeout=5.0)
                        if resp.status_code == 200:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)

                # Clear agent card cache
                _cached_agent_card = None
                _card_cache_url = None

                return {"success": True, "message": "White agent restarted"}
            else:
                return {"success": False, "error": f"Launch returned {launch_response.status_code}"}

        except Exception as e:
            _cached_agent_card = None
            _card_cache_url = None
            return {"success": False, "error": str(e)}
        finally:
            await httpx_client.aclose()

    except Exception as e:
        logger.error(f"[RESET] Reset failed: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# BATTLE PROGRESS TRACKING - Using AgentBeats SDK
# ============================================================================

@ab.tool
async def log_battle_progress(
    message: str,
    battle_id: Optional[str] = None,
    backend_url: Optional[str] = None,
    step: Optional[int] = None,
    total_steps: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Log battle progress using AgentBeats logging utilities.

    Args:
        message: Progress message to log
        battle_id: Battle ID (uses context if not provided)
        backend_url: Backend URL (uses context if not provided)
        step: Current step number
        total_steps: Total number of steps
        metadata: Additional metadata to include

    Returns:
        Confirmation message
    """
    try:
        # Try to use existing battle context first
        battle_context = ab.get_battle_context()

        if not battle_context and (battle_id and backend_url):
            # Create new context if needed
            battle_context = ab.BattleContext(
                battle_id=battle_id,
                backend_url=backend_url,
                agent_name="tau_green_agent_mcp"
            )
            ab.set_battle_context(battle_context)

        if battle_context:
            detail = metadata or {}
            if step is not None and total_steps is not None:
                detail["step"] = step
                detail["total_steps"] = total_steps

            ab.record_battle_event(battle_context, message, detail)
            return f"Logged: {message}"
        else:
            # Fallback to regular logging
            logger.info(f"Battle progress: {message}")
            return f"Logged locally: {message}"

    except Exception as e:
        logger.error(f"Error logging battle progress: {e}")
        return f"Error logging: {str(e)}"


@ab.tool
async def report_battle_result(
    success: bool,
    message: str,
    metrics: Optional[Dict[str, Any]] = None,
    battle_id: Optional[str] = None,
    backend_url: Optional[str] = None
) -> str:
    """
    Report final battle result using AgentBeats logging utilities.

    Args:
        success: Whether the evaluation succeeded
        message: Result message
        metrics: Evaluation metrics
        battle_id: Battle ID (uses context if not provided)
        backend_url: Backend URL (uses context if not provided)

    Returns:
        Confirmation message
    """
    try:
        battle_context = ab.get_battle_context()

        if not battle_context and (battle_id and backend_url):
            battle_context = ab.BattleContext(
                battle_id=battle_id,
                backend_url=backend_url,
                agent_name="tau_green_agent_mcp"
            )
            ab.set_battle_context(battle_context)

        if battle_context:
            winner = "white" if success else "green"
            detail = {
                "metrics": metrics or {},
                "success": success
            }

            ab.record_battle_result(battle_context, message, detail)
            return f"Battle result reported: {winner} wins"
        else:
            logger.info(f"Battle result: {message}")
            return f"Logged locally: {message}"

    except Exception as e:
        logger.error(f"Error reporting battle result: {e}")
        return f"Error reporting: {str(e)}"


# ============================================================================
# TAU-BENCH ENVIRONMENT TOOLS
# ============================================================================

@ab.tool
async def setup_tau_bench_environment(
    env_name: str = "retail",
    user_strategy: str = "llm",
    user_model: str | None = None,
    user_provider: str | None = None,
    task_split: str = "test",
    task_id: int = 5
) -> Dict[str, Any]:
    """
    Set up a tau-bench evaluation environment.

    Args:
        env_name: Environment name (e.g., "retail", "airline")
        user_strategy: User simulation strategy
        user_model: Model to use for user simulation (defaults to TAU_USER_MODEL from config)
        user_provider: Provider for user model (defaults to TAU_USER_PROVIDER from config)
        task_split: Task split to use
        task_id: Specific task ID to evaluate

    Returns:
        Dict containing environment info and tool schemas
    """
    try:
        logger.info(f"Setting up tau-bench environment: {env_name}, task {task_id}")

        # Use configured values if not explicitly provided
        if user_model is None:
            user_model = TAU_USER_MODEL
        if user_provider is None:
            user_provider = TAU_USER_PROVIDER

        env = get_env(
            env_name=env_name,
            user_strategy=user_strategy,
            user_model=user_model,
            task_split=task_split,
            user_provider=user_provider,
            task_index=task_id,
        )

        return {
            "success": True,
            "env_name": env_name,
            "task_id": task_id,
            "tools_count": len(env.tools_info),
            "tools_info": env.tools_info,
            "wiki": env.wiki,
            "tools_available": [tool["function"]["name"] for tool in env.tools_info]
        }

    except Exception as e:
        logger.error(f"Error setting up tau-bench environment: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


@ab.tool
def get_tau_bench_tools_as_json(task_id: int = 5) -> str:
    """
    Get tau-bench tools as JSON string for easy sharing with agents.

    Args:
        task_id: Task ID to get tools for

    Returns:
        JSON string containing all tool schemas
    """
    try:
        env = get_env(
            env_name="retail",
            user_strategy="llm",
            user_model=TAU_USER_MODEL,
            task_split="test",
            user_provider=TAU_USER_PROVIDER,
            task_index=task_id,
        )

        return json.dumps(env.tools_info, indent=2)

    except Exception as e:
        logger.error(f"Error getting tau-bench tools: {e}")
        return json.dumps({"error": str(e)})


@ab.tool
def list_tau_bench_tools(task_id: int = 5) -> str:
    """
    List all available tau-bench tools for a given task.

    Args:
        task_id: Task ID to get tools for

    Returns:
        Formatted string listing all tools with descriptions
    """
    try:
        env = get_env(
            env_name="retail",
            user_strategy="llm",
            user_model=TAU_USER_MODEL,
            task_split="test",
            user_provider=TAU_USER_PROVIDER,
            task_index=task_id,
        )

        tool_list = []
        for tool in env.tools_info:
            func_info = tool.get("function", {})
            name = func_info.get("name", "unknown")
            desc = func_info.get("description", "No description")
            tool_list.append(f"- **{name}**: {desc}")

        return "\n".join([
            f"# Tau-Bench Tools for Task {task_id}",
            f"Total tools: {len(tool_list)}",
            "",
            *tool_list
        ])

    except Exception as e:
        logger.error(f"Error listing tau-bench tools: {e}")
        return f"Error: {str(e)}"


# ============================================================================
# EVALUATION ORCHESTRATION TOOLS
# ============================================================================

@ab.tool
async def evaluate_white_agent(
    white_agent_url: str,
    task_id: int = 5,
    max_num_steps: int = 30,
    env_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run a full tau-bench evaluation of a white agent.

    Args:
        white_agent_url: URL of the white agent to evaluate
        task_id: Tau-bench task ID to evaluate on
        max_num_steps: Maximum number of evaluation steps
        env_config: Optional custom environment configuration

    Returns:
        Dict containing evaluation results, metrics, and info
    """
    from a2a.types import SendMessageSuccessResponse, Message
    from a2a.utils import get_text_parts
    from src.my_util import parse_tags

    logger.info(f"Starting evaluation of {white_agent_url} on task {task_id}")

    # Set up environment
    if env_config is None:
        env_config = {
            "env": "retail",
            "user_strategy": "llm",
            "user_model": TAU_USER_MODEL,
            "user_provider": TAU_USER_PROVIDER,
            "task_split": "test",
            "task_ids": [task_id],
        }

    env = get_env(
        env_name=env_config["env"],
        user_strategy=env_config["user_strategy"],
        user_model=env_config["user_model"],
        task_split=env_config["task_split"],
        user_provider=env_config.get("user_provider", TAU_USER_PROVIDER),
        task_index=task_id,
    )

    # Reset environment
    total_cost = 0.0
    env_reset_res = env.reset(task_index=task_id)
    obs = env_reset_res.observation
    info = env_reset_res.info.model_dump()
    reward = 0.0

    # Create initial task description
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
        logger.info(f"Step {step_num + 1}/{max_num_steps}")

        # Log progress
        await log_battle_progress(
            f"Evaluation step {step_num + 1}/{max_num_steps}...",
            step=step_num + 1,
            total_steps=max_num_steps
        )

        # Send message to white agent
        result = await send_message_to_white_agent(
            white_agent_url,
            next_green_message,
            context_id=context_id,
            timeout=120.0
        )

        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"White agent error: {error_msg}")
            return {
                "success": False,
                "reward": 0.0,
                "info": {**info, "error": error_msg, "steps_completed": step_num + 1},
                "total_cost": total_cost
            }

        white_agent_response = result["response"]
        res_root = white_agent_response.root

        if not isinstance(res_root, SendMessageSuccessResponse):
            logger.error(f"Invalid response type: {type(res_root)}")
            return {
                "success": False,
                "reward": 0.0,
                "info": {**info, "error": "Invalid response format", "steps_completed": step_num + 1},
                "total_cost": total_cost
            }

        res_result = res_root.result
        if not isinstance(res_result, Message):
            logger.error(f"Unexpected result type: {type(res_result)}")
            return {
                "success": False,
                "reward": 0.0,
                "info": {**info, "error": "Unexpected response format", "steps_completed": step_num + 1},
                "total_cost": total_cost
            }

        # Update context ID
        if context_id is None:
            context_id = res_result.context_id

        # Parse response
        text_parts = get_text_parts(res_result.parts)
        if len(text_parts) != 1:
            return {
                "success": False,
                "reward": 0.0,
                "info": {**info, "error": "Expected exactly one text part", "steps_completed": step_num + 1},
                "total_cost": total_cost
            }

        white_text = text_parts[0]
        logger.info(f"White agent response: {white_text[:200]}...")

        # Parse action from response
        white_tags = parse_tags(white_text)
        if "json" not in white_tags:
            return {
                "success": False,
                "reward": 0.0,
                "info": {**info, "error": "Missing <json> tags in response", "steps_completed": step_num + 1},
                "total_cost": total_cost
            }

        action_json = white_tags["json"]
        try:
            action_dict = json.loads(action_json)
            action = Action(**action_dict)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            return {
                "success": False,
                "reward": 0.0,
                "info": {**info, "error": f"Invalid JSON: {str(e)}", "steps_completed": step_num + 1},
                "total_cost": total_cost
            }

        # Execute action in environment
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

    # Return final result
    return {
        "success": reward == 1.0,
        "reward": reward,
        "info": info,
        "total_cost": total_cost,
        "steps_completed": step_num + 1
    }


# ============================================================================
# UTILITY TOOLS
# ============================================================================

def _parse_tags_helper(str_with_tags: str) -> dict:
    """
    Internal helper to parse XML-style tags from text.
    Tags are in the format <tag_name>...</tag_name>
    
    Returns dict with tag names as keys and content as values.
    """
    import re
    tags = re.findall(r"<(.*?)>(.*?)</\1>", str_with_tags, re.DOTALL)
    return {tag: content.strip() for tag, content in tags}


@ab.tool
def parse_xml_tags(text: str, tag: str) -> str:
    """
    Parse XML-style tags from text.

    Args:
        text: Text to parse
        tag: Tag name to extract (e.g., "json", "xml")

    Returns:
        Content within the specified tags, or empty string if not found
    """
    try:
        tags = _parse_tags_helper(text)
        return tags.get(tag, "")
    except Exception as e:
        logger.error(f"Error parsing tags: {e}")
        return ""


@ab.tool
def format_evaluation_result(
    success: bool,
    reward: float,
    info: Dict[str, Any],
    metrics: Optional[Dict[str, Any]] = None
) -> str:
    """
    Format an evaluation result as a user-friendly markdown message.

    Args:
        success: Whether evaluation succeeded
        reward: Reward value (0.0 or 1.0)
        info: Evaluation info dict
        metrics: Optional metrics dict

    Returns:
        Formatted markdown string
    """
    result_emoji = "✅" if success else "❌"

    lines = [
        f"# Evaluation Result {result_emoji}",
        "",
        f"**Success**: {success}",
        f"**Reward**: {reward}",
        ""
    ]

    if metrics:
        lines.append("## Metrics")
        for key, value in metrics.items():
            lines.append(f"- **{key}**: {value}")
        lines.append("")

    # Add failure details if available
    if not success and info:
        lines.append("## Failure Details")

        if "error" in info:
            lines.append(f"**Error**: {info['error']}")
            if "error_detail" in info:
                lines.append(f"**Details**: {info['error_detail']}")

        task_info = info.get("task", {})
        if "instruction" in task_info:
            lines.append(f"**Task**: {task_info['instruction']}")

        if "steps_completed" in info:
            lines.append(f"**Steps Completed**: {info['steps_completed']}")

    return "\n".join(lines)


# ============================================================================
# PASS@K EVALUATION TOOLS
# ============================================================================

@ab.tool
async def evaluate_agent_with_pass_k(
    white_agent_url: str,
    domain: str,
    task_id: int,
    k: int = 4,
    max_num_steps: int = 30,
    reset_between_attempts: bool = True,
    battle_id: Optional[str] = None,
    backend_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluate white agent with k independent attempts on a task.

    This implements pass^k evaluation:
    - pass^k: All first k attempts must succeed consecutively
    - pass^(k/2): Any window of k/2 consecutive successes
    - success_rate: Overall percentage of successful attempts

    Args:
        white_agent_url: URL of the white agent to evaluate
        domain: Domain to test ("retail" or "airline")
        task_id: Task ID within the domain
        k: Number of attempts (must be even)
        max_num_steps: Maximum steps per attempt
        battle_id: Optional battle ID for AgentBeats logging
        backend_url: Optional backend URL for AgentBeats logging

    Returns:
        Dict with pass^k metrics, attempt details, and failure analysis
    """
    import time
    import asyncio
    from uuid import uuid4
    from a2a.types import SendMessageSuccessResponse, Message
    from a2a.utils import get_text_parts

    logger.info(f"=== Starting pass@k evaluation: domain={domain}, task={task_id}, k={k} ===")

    # Set up battle context for logging
    battle_context = None
    if battle_id and backend_url:
        battle_context = ab.BattleContext(
            battle_id=battle_id,
            backend_url=backend_url,
            agent_name="tau_green_agent_mcp"
        )
        ab.set_battle_context(battle_context)
        ab.record_battle_event(
            battle_context,
            f"Starting pass@{k} evaluation",
            {"domain": domain, "task_id": task_id, "k": k}
        )

    # Set up tau-bench environment
    env = get_env(
        env_name=domain,
        user_strategy="llm",
        user_model=TAU_USER_MODEL,
        task_split="test",
        user_provider=TAU_USER_PROVIDER,
        task_index=task_id
    )

    # Run k attempts
    attempts = []
    failure_reasons = []
    total_steps = 0

    for attempt_num in range(k):
        logger.info(f"--- Attempt {attempt_num + 1}/{k} ---")
        logger.info(f"[DEBUG] ========== ATTEMPT {attempt_num + 1}/{k} STARTING ==========")

        # Optionally reset white agent to prevent state pollution (safer to rely on new context_id)
        if reset_between_attempts:
            try:
                logger.info(f"[RESET] Resetting white agent before attempt {attempt_num + 1}")
                print(f"[RESET] Resetting white agent before attempt {attempt_num + 1}", file=sys.stderr, flush=True)
                reset_result = await reset_white_agent(white_agent_url, timeout=30.0)
                if reset_result["success"]:
                    logger.info("[RESET] White agent reset completed successfully")
                    print("[RESET] White agent reset completed successfully", file=sys.stderr, flush=True)
                else:
                    logger.warning(f"[RESET] Reset returned failure but continuing: {reset_result.get('error')}")
                    print(f"[RESET] Reset failed but continuing: {reset_result.get('error')}", file=sys.stderr, flush=True)
            except Exception as e:
                logger.warning(f"[RESET] Warning: Reset failed (continuing anyway): {e}")
                print(f"[RESET] Warning: Reset exception (continuing anyway): {e}", file=sys.stderr, flush=True)

        if battle_context:
            ab.record_battle_event(
                battle_context,
                f"🔄 Starting attempt {attempt_num + 1}/{k}...",
                {}
            )

        timestamp_started = time.time()

        # Reset environment for fresh attempt
        logger.info(f"[DEBUG] Calling env.reset() for attempt {attempt_num + 1}")
        env_reset_res = env.reset(task_index=task_id)
        logger.info(f"[DEBUG] env.reset() completed for attempt {attempt_num + 1}")
        obs = env_reset_res.observation
        info = env_reset_res.info.model_dump()
        reward = 0.0

        # Create task description
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
        # Create a NEW context for each attempt to ensure white agent starts fresh
        # This prevents conversation history from leaking between attempts
        context_id = f"attempt_{attempt_num + 1}_{uuid4().hex[:8]}"
        steps_in_attempt = 0
        attempt_error = None

        # Evaluation loop for this attempt
        for _ in range(max_num_steps):
            steps_in_attempt += 1
            total_steps += 1

            try:
                # Send message to white agent
                result = await send_message_to_white_agent(
                    white_agent_url,
                    next_green_message,
                    context_id=context_id,
                    timeout=120.0
                )

                if not result["success"]:
                    attempt_error = result.get("error", "Unknown error")
                    logger.error(f"White agent error: {attempt_error}")
                    break

                # Extract response
                white_agent_response = result["response"]
                res_root = white_agent_response.root

                if not isinstance(res_root, SendMessageSuccessResponse):
                    attempt_error = f"White agent returned error: {res_root}"
                    logger.error(attempt_error)
                    break

                res_result = res_root.result
                if not isinstance(res_result, Message):
                    attempt_error = f"Unexpected response type: {type(res_result)}"
                    logger.error(attempt_error)
                    break

                # Parse white agent response
                text_parts = get_text_parts(res_result.parts)
                if len(text_parts) != 1:
                    attempt_error = "Expected exactly one text part from white agent"
                    logger.error(attempt_error)
                    break

                white_text = text_parts[0]

                # Parse action from response
                white_tags = parse_xml_tags(white_text, "json")
                if not white_tags:
                    attempt_error = "Missing <json> tags in response"
                    logger.error(attempt_error)
                    break

                try:
                    action_dict = json.loads(white_tags)
                    action = Action(**action_dict)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                    attempt_error = f"Invalid JSON: {str(e)}"
                    logger.error(attempt_error)
                    break

                # Execute action in tau-bench environment with a safety timeout
                try:
                    ENV_STEP_TIMEOUT = 60.0
                    env_response = await asyncio.wait_for(
                        asyncio.to_thread(env.step, action),
                        timeout=ENV_STEP_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    attempt_error = f"Environment step timed out after {ENV_STEP_TIMEOUT}s for action '{action.name}'"
                    logger.error(attempt_error)
                    break

                reward = env_response.reward
                info = {**info, **env_response.info.model_dump()}

                # Prepare next message
                if action.name != RESPOND_ACTION_NAME:
                    observation_text = str(env_response.observation)
                    MAX_MESSAGE_SIZE = 10000
                    if len(observation_text) > MAX_MESSAGE_SIZE:
                        logger.info(f"Truncating tool result from {len(observation_text)} to {MAX_MESSAGE_SIZE} chars")
                        observation_text = observation_text[:MAX_MESSAGE_SIZE] + "\n...[TRUNCATED]"
                    next_green_message = f"Tool call result:\n{observation_text}"
                else:
                    next_green_message = f"User message:\n{env_response.observation}"

                if env_response.done:
                    break

            except Exception as e:
                attempt_error = f"Exception: {type(e).__name__}: {str(e)}"
                logger.error(attempt_error, exc_info=True)
                break

        logger.info(f"Attempt {attempt_num + 1} completed: {steps_in_attempt} steps, reward={reward}")
        
        # Record attempt result
        time_used = time.time() - timestamp_started
        success = (reward == 1 and attempt_error is None)

        # Extract detailed failure information from tau-bench
        failure_detail = None
        if not success:
            failure_detail = extract_failure_details(info, attempt_error)
            failure_reason = failure_detail["category"]
            failure_reasons.append(failure_reason)

        attempts.append({
            "attempt": attempt_num + 1,
            "success": success,
            "reward": reward,
            "steps": steps_in_attempt,
            "time": time_used,
            "error": attempt_error,
            "failure_detail": failure_detail,
            "tau_bench_info": info
        })

        # Log attempt result
        result_emoji = "✅" if success else "❌"
        logger.info(f"Attempt {attempt_num + 1}/{k}: {result_emoji} (reward={reward}, steps={steps_in_attempt}, time={time_used:.1f}s)")

        # Small delay between attempts to prevent resource exhaustion
        if attempt_num < k - 1:
            global _cached_agent_card, _card_cache_url
            _cached_agent_card = None
            _card_cache_url = None
            await asyncio.sleep(2.0)

        if battle_context:
            # Build detailed failure message for UI
            event_message = f"{result_emoji} Attempt {attempt_num + 1}/{k}: {'SUCCESS' if success else 'FAILED'}"

            event_detail = {
                "reward": reward,
                "steps": steps_in_attempt,
                "time": f"{time_used:.2f}s",
                "error": attempt_error
            }

            # Add comprehensive failure details to event
            if not success and failure_detail:
                # Core categorization
                event_detail["failure_category"] = failure_detail["category"]
                event_detail["fault_author"] = failure_detail.get("fault_author", "unknown")
                event_detail["fault_type"] = failure_detail.get("fault_type", "other")
                event_detail["description"] = failure_detail.get("description", "")

                # Scores
                if failure_detail.get("action_score") is not None:
                    event_detail["action_score"] = failure_detail["action_score"]
                if failure_detail.get("output_score") is not None:
                    event_detail["output_score"] = failure_detail["output_score"]

                # Database state analysis
                if failure_detail.get("database_state_match") is not None:
                    event_detail["database_state_match"] = failure_detail["database_state_match"]
                if failure_detail.get("ground_truth_actions"):
                    event_detail["expected_num_actions"] = len(failure_detail["ground_truth_actions"])

                # Output analysis
                if failure_detail.get("missing_outputs"):
                    event_detail["missing_outputs"] = failure_detail["missing_outputs"]
                if failure_detail.get("provided_outputs"):
                    event_detail["provided_outputs"] = failure_detail["provided_outputs"]

                # Task context
                if failure_detail.get("task_instruction"):
                    event_detail["task_instruction"] = failure_detail["task_instruction"]

                # Build rich human-readable message
                event_message += f"\n   🔍 **{failure_detail['category']}**"
                if failure_detail.get("description"):
                    event_message += f"\n   💬 {failure_detail['description']}"

                # Add fault attribution
                fault_author_emoji = {
                    "agent": "🤖",
                    "user": "👤",
                    "environment": "⚙️",
                    "unknown": "❓"
                }
                event_message += f"\n   {fault_author_emoji.get(failure_detail.get('fault_author', 'unknown'), '❓')} Fault: {failure_detail.get('fault_author', 'unknown')}"

                # Add fault type
                fault_type_labels = {
                    "called_wrong_tool": "Called Wrong Tool",
                    "used_wrong_tool_argument": "Wrong Tool Arguments",
                    "goal_partially_completed": "Goal Partially Completed",
                    "other": "Other"
                }
                event_message += f" | Type: {fault_type_labels.get(failure_detail.get('fault_type', 'other'), 'Other')}"

            ab.record_battle_event(
                battle_context,
                event_message,
                event_detail
            )

    # Calculate pass^k metrics
    success_flags = [a["success"] for a in attempts]

    # pass^k: All first k attempts must succeed
    pass_k = all(success_flags[0:k])

    # pass^(k/2): Any window of k/2 consecutive successes
    k_half = k // 2
    pass_k_half = any(
        all(success_flags[i:i+k_half])
        for i in range(len(success_flags) - k_half + 1)
    )

    # Overall success rate
    num_successes = sum(success_flags)
    success_rate = num_successes / k

    # Average steps (only for successful attempts)
    successful_attempts = [a for a in attempts if a["success"]]
    avg_steps = (
        sum(a["steps"] for a in successful_attempts) / len(successful_attempts)
        if successful_attempts else 0
    )

    # Failure breakdown
    failure_breakdown = {}
    for reason in failure_reasons:
        failure_breakdown[reason] = failure_breakdown.get(reason, 0) + 1

    # Compile results
    results = {
        "domain": domain,
        "task_id": task_id,
        "k": k,
        "pass_k": pass_k,
        "pass_k_half": pass_k_half,
        "success_rate": success_rate,
        "num_successes": num_successes,
        "num_failures": k - num_successes,
        "avg_steps_on_success": avg_steps,
        "total_steps": total_steps,
        "attempts": attempts,
        "failure_breakdown": failure_breakdown
    }

    # Log final summary
    logger.info("=== Pass@k Evaluation Complete ===")
    logger.info(f"pass^{k}: {pass_k} (all first {k} attempts succeeded)")
    logger.info(f"pass^{k_half}: {pass_k_half} (found {k_half} consecutive successes)")
    logger.info(f"Success rate: {success_rate:.1%} ({num_successes}/{k})")
    logger.info(f"Average steps on success: {avg_steps:.1f}")

    # Report detailed breakdown to AgentBeats with a safety timeout
    if battle_context:
        import asyncio as _asyncio
        try:
            await _asyncio.wait_for(report_pass_k_results(results, battle_context), timeout=20.0)
        except _asyncio.TimeoutError:
            logger.warning("[FINALIZE] Reporting results to AgentBeats timed out after 20s; returning results anyway.")

    return results


def extract_failure_details(info: Dict[str, Any], error: Optional[str]) -> Dict[str, Any]:
    """
    Extract comprehensive failure information from tau-bench info and error message.

    This function provides detailed failure analysis including:
    - Fault author attribution (user simulator, agent, environment)
    - Fault type classification (wrong_tool, wrong_argument, partial_completion, other)
    - Action-level analysis (expected vs actual database state)
    - Output-level analysis (missing required information)
    - Human-readable descriptions of what went wrong

    Args:
        info: Tau-bench info dict with task, reward_info, etc.
        error: Error message if any

    Returns:
        Dict with comprehensive failure details
    """
    failure_detail = {
        # Primary categorization
        "category": "unknown_failure",
        "fault_author": "unknown",  # "user", "agent", or "environment"
        "fault_type": "other",  # "called_wrong_tool", "used_wrong_tool_argument", "goal_partially_completed", "other"

        # Error information
        "error_message": error,
        "description": "",  # Human-readable description

        # Task context
        "task_instruction": None,
        "expected_actions": [],
        "expected_outputs": [],

        # Score breakdown
        "action_score": None,  # r_actions (0.0 or 1.0)
        "output_score": None,  # r_outputs (0.0 or 1.0)
        "constraint_score": None,  # r_constraints if available

        # Action analysis
        "ground_truth_actions": [],  # From task.actions
        "ground_truth_data_hash": None,  # Expected database state hash
        "actual_data_hash": None,  # Agent's database state hash
        "database_state_match": False,  # Whether hashes match

        # Output analysis
        "missing_outputs": [],
        "provided_outputs": [],
        "outputs_detail": {},  # Per-output found status

        # Steps information
        "steps_completed": None,
        "max_steps_reached": False
    }

    logger.info(f"[DEBUG extract_failure_details] Called with error={error}")
    logger.info(f"[DEBUG extract_failure_details] info has keys: {list(info.keys())}")

    # Extract task information
    task_info = info.get("task", {})
    if task_info:
        logger.info(f"[DEBUG extract_failure_details] Found task_info with keys: {list(task_info.keys())}")
        failure_detail["task_instruction"] = task_info.get("instruction", "")
        failure_detail["expected_outputs"] = task_info.get("outputs", [])
        failure_detail["ground_truth_actions"] = task_info.get("actions", [])
    else:
        logger.info("[DEBUG extract_failure_details] No task_info found")

    # Extract steps completed
    if "steps_completed" in info:
        failure_detail["steps_completed"] = info["steps_completed"]
        logger.info(f"[DEBUG extract_failure_details] Steps completed: {info['steps_completed']}")

    # ========================================================================
    # STEP 1: Check for explicit errors (environment/communication failures)
    # ========================================================================
    if error:
        logger.info(f"[DEBUG extract_failure_details] Processing explicit error: {error}")
        failure_detail["fault_author"] = "environment"  # Communication/system errors

        if "timeout" in error.lower():
            failure_detail["category"] = "timeout"
            failure_detail["description"] = f"Evaluation timed out after {failure_detail.get('steps_completed', '?')} steps"
        elif "llm provider not provided" in error.lower() or "bad request" in error.lower() or "api key" in error.lower() or "401" in error or "403" in error:
            failure_detail["category"] = "llm_configuration_error"
            failure_detail["fault_author"] = "environment"
            failure_detail["fault_type"] = "other"
            failure_detail["description"] = "LLM API configuration error (check model name, API key, or provider settings)"
        elif "missing" in error.lower() and "json" in error.lower() and "tags" in error.lower():
            # Only categorize as format_error if explicitly about missing JSON tags
            failure_detail["category"] = "format_error"
            failure_detail["fault_author"] = "agent"  # Agent produced bad format
            failure_detail["fault_type"] = "other"
            failure_detail["description"] = "Agent returned improperly formatted response (missing or invalid JSON tags)"
        elif "json" in error.lower() and ("parse" in error.lower() or "decode" in error.lower()):
            # JSON parsing errors
            failure_detail["category"] = "format_error"
            failure_detail["fault_author"] = "agent"
            failure_detail["fault_type"] = "other"
            failure_detail["description"] = "Agent returned invalid JSON that could not be parsed"
        elif "communication" in error.lower() or "connection" in error.lower():
            failure_detail["category"] = "communication_error"
            failure_detail["description"] = "Network or communication error with white agent"
        else:
            failure_detail["category"] = "white_agent_error"
            failure_detail["fault_author"] = "agent"
            failure_detail["description"] = f"Agent error: {error}"

        logger.info(f"[DEBUG extract_failure_details] Categorized as: {failure_detail['category']}")
        return failure_detail

    # ========================================================================
    # STEP 2: Analyze tau-bench reward information
    # ========================================================================
    reward_info = info.get("reward_info", {})
    logger.info(f"[DEBUG extract_failure_details] reward_info exists: {bool(reward_info)}")

    if not reward_info:
        logger.info("[DEBUG extract_failure_details] No reward_info found - cannot extract detailed failure info")
        if "steps_completed" in info:
            failure_detail["category"] = "task_incomplete"
            failure_detail["fault_author"] = "agent"
            failure_detail["fault_type"] = "goal_partially_completed"
            failure_detail["description"] = f"Task incomplete after {info['steps_completed']} steps"
        return failure_detail

    reward_detail = reward_info.get("info", {})
    logger.info(f"[DEBUG extract_failure_details] reward_detail keys: {list(reward_detail.keys())}")

    # Extract ground truth actions from reward_info
    gt_actions = reward_info.get("actions", [])
    if gt_actions:
        failure_detail["ground_truth_actions"] = gt_actions
        logger.info(f"[DEBUG extract_failure_details] Ground truth actions: {len(gt_actions)} actions")

    # ========================================================================
    # STEP 3: Analyze r_actions (Database State Correctness)
    # ========================================================================
    # r_actions checks if database modifications are correct
    # - Compares SHA256 hash of database state after agent's actions
    # - Against hash after replaying ground truth actions
    # - r_actions = 1.0 means database state is EXACTLY correct
    # - r_actions = 0.0 means database state is WRONG

    if "r_actions" in reward_detail:
        action_score = float(reward_detail["r_actions"])
        failure_detail["action_score"] = action_score
        logger.info(f"[DEBUG extract_failure_details] Found r_actions: {action_score}")

        # Extract data hashes if available
        if "gt_data_hash" in reward_detail:
            failure_detail["ground_truth_data_hash"] = reward_detail["gt_data_hash"]
            logger.info(f"[DEBUG extract_failure_details] Ground truth hash: {reward_detail['gt_data_hash'][:16]}...")

        failure_detail["database_state_match"] = (action_score == 1.0)

        if action_score == 0.0:
            # Agent's database modifications were incorrect
            failure_detail["fault_author"] = "agent"  # Agent is responsible
            failure_detail["category"] = "incorrect_database_state"

            # Now determine WHY the database state is wrong
            # This requires analyzing what actions the agent took

            # Check if we have action history from tau-bench trajectory
            # (This would be populated if we store the trajectory)
            num_gt_actions = len(failure_detail["ground_truth_actions"])

            if num_gt_actions == 0:
                # Task required NO actions (just respond)
                failure_detail["fault_type"] = "called_wrong_tool"
                failure_detail["description"] = (
                    "Agent called tools when it should have only responded. "
                    "This task requires no database modifications."
                )
            else:
                # Task required specific actions
                # Without trajectory, we can infer general issues
                failure_detail["fault_type"] = "other"  # Default, may be refined below
                failure_detail["description"] = (
                    f"Agent's database modifications do not match expected state. "
                    f"Expected {num_gt_actions} action(s) to achieve correct state. "
                    f"Database state hash mismatch."
                )

                # Try to be more specific based on context
                if "steps_completed" in info:
                    steps = info["steps_completed"]
                    if steps < num_gt_actions:
                        failure_detail["fault_type"] = "goal_partially_completed"
                        failure_detail["description"] = (
                            f"Agent completed only {steps} step(s) but {num_gt_actions} action(s) "
                            f"were needed to reach goal state. Task appears incomplete."
                        )
                    elif steps > num_gt_actions * 2:
                        failure_detail["fault_type"] = "called_wrong_tool"
                        failure_detail["description"] = (
                            f"Agent took {steps} step(s) vs {num_gt_actions} expected action(s). "
                            f"Likely called wrong tools or took unnecessary actions."
                        )
                    else:
                        # Similar step count, probably wrong arguments
                        failure_detail["fault_type"] = "used_wrong_tool_argument"
                        failure_detail["description"] = (
                            f"Agent took approximately correct number of steps ({steps}) "
                            f"but database state is wrong. Likely used wrong tool arguments "
                            f"(e.g., wrong IDs, wrong values, wrong parameters)."
                        )

            logger.info(f"[DEBUG extract_failure_details] Set category to {failure_detail['category']} (r_actions=0.0)")
            logger.info(f"[DEBUG extract_failure_details] Fault type: {failure_detail['fault_type']}")

    # ========================================================================
    # STEP 4: Analyze r_outputs (Required Information Output)
    # ========================================================================
    # r_outputs checks if agent communicated required information to user
    # - Looks for substring matches in agent's "respond" actions
    # - Case-insensitive, comma-stripped matching
    # - r_outputs = 1.0 means ALL required outputs were communicated
    # - r_outputs = 0.0 means at least ONE required output is missing

    if "r_outputs" in reward_detail:
        output_score = float(reward_detail["r_outputs"])
        failure_detail["output_score"] = output_score
        logger.info(f"[DEBUG extract_failure_details] Found r_outputs: {output_score}")

        # Get per-output details if available
        outputs_dict = reward_detail.get("outputs", {})
        if outputs_dict:
            failure_detail["outputs_detail"] = outputs_dict

            # Categorize provided vs missing
            provided = [k for k, v in outputs_dict.items() if v]
            missing = [k for k, v in outputs_dict.items() if not v]

            failure_detail["provided_outputs"] = provided
            failure_detail["missing_outputs"] = missing

            logger.info(f"[DEBUG extract_failure_details] Provided outputs: {provided}")
            logger.info(f"[DEBUG extract_failure_details] Missing outputs: {missing}")

        if output_score == 0.0:
            # Agent failed to communicate required information
            if failure_detail["category"] == "unknown_failure":
                # Only set if not already categorized by r_actions
                failure_detail["fault_author"] = "agent"
                failure_detail["category"] = "missing_required_outputs"
                failure_detail["fault_type"] = "goal_partially_completed"

                num_missing = len(failure_detail["missing_outputs"])
                num_expected = len(failure_detail["expected_outputs"])

                if num_missing == num_expected:
                    failure_detail["description"] = (
                        f"Agent did not communicate ANY of the required information to the user. "
                        f"Missing: {', '.join(failure_detail['missing_outputs'])}"
                    )
                else:
                    failure_detail["description"] = (
                        f"Agent communicated only {num_expected - num_missing}/{num_expected} "
                        f"required output(s). Missing: {', '.join(failure_detail['missing_outputs'])}"
                    )

                logger.info("[DEBUG extract_failure_details] Set category to missing_required_outputs")
        elif output_score < 1.0:
            # Partial output (unusual, but handle it)
            logger.info(f"[DEBUG extract_failure_details] Partial r_outputs: {output_score}")
            if failure_detail["category"] == "unknown_failure":
                failure_detail["fault_author"] = "agent"
                failure_detail["category"] = "incomplete_outputs"
                failure_detail["fault_type"] = "goal_partially_completed"
                failure_detail["description"] = (
                    f"Agent partially communicated required information (score: {output_score})"
                )

    # ========================================================================
    # STEP 5: Check for constraint violations (if tau-bench provides)
    # ========================================================================
    # Note: Current tau-bench doesn't calculate r_constraints in reward
    # But if it existed, it would check rule compliance (e.g., user ID confirmation)

    if "r_constraints" in reward_detail:
        constraint_score = float(reward_detail["r_constraints"])
        failure_detail["constraint_score"] = constraint_score
        logger.info(f"[DEBUG extract_failure_details] Found r_constraints: {constraint_score}")

        if constraint_score < 1.0:
            if failure_detail["category"] == "unknown_failure":
                failure_detail["fault_author"] = "agent"
                failure_detail["category"] = "constraint_violation"
                failure_detail["fault_type"] = "other"
                failure_detail["description"] = (
                    f"Agent violated task constraints or rules (score: {constraint_score}). "
                    f"For example: didn't confirm user ID, didn't get authorization, etc."
                )
                logger.info("[DEBUG extract_failure_details] Set category to constraint_violation")

    # ========================================================================
    # STEP 6: Finalize unknown failures
    # ========================================================================
    if failure_detail["category"] == "unknown_failure":
        failure_detail["fault_author"] = "environment"
        failure_detail["description"] = (
            "Failure occurred but root cause could not be determined. "
            "Reward was 0.0 but no specific failure indicators found."
        )
        logger.info("[DEBUG extract_failure_details] Kept as unknown_failure (fallback)")

    logger.info(f"[DEBUG extract_failure_details] Final category: {failure_detail['category']}")
    logger.info(f"[DEBUG extract_failure_details] Fault author: {failure_detail['fault_author']}")
    logger.info(f"[DEBUG extract_failure_details] Fault type: {failure_detail['fault_type']}")
    return failure_detail


def categorize_failure(info: Dict[str, Any], error: Optional[str]) -> str:
    """
    Categorize the failure reason (legacy function for backward compatibility).

    Args:
        info: Tau-bench info dict
        error: Error message if any

    Returns:
        Categorized failure reason string
    """
    details = extract_failure_details(info, error)
    return details["category"]


async def report_pass_k_results(
    results: Dict[str, Any],
    battle_context: ab.BattleContext
) -> None:
    """
    Report detailed pass@k results to AgentBeats UI.

    Args:
        results: Pass@k evaluation results
        battle_context: AgentBeats battle context
    """
    k = results["k"]
    k_half = k // 2

    # Create visual attempt history
    attempt_visual = "".join(
        "✅" if a["success"] else "❌"
        for a in results["attempts"]
    )

    # Build detailed message
    lines = [
        "# 📊 Pass@k Evaluation Results",
        "",
        f"**Domain**: {results['domain']} | **Task**: {results['task_id']}",
        "",
        f"## Attempts ({k} total)",
        f"{attempt_visual}",
        "",
        "## Metrics",
        f"- **pass^{k}**: {'✅ PASS' if results['pass_k'] else '❌ FAIL'} (all first {k} attempts must succeed)",
        f"- **pass^{k_half}**: {'✅ PASS' if results['pass_k_half'] else '❌ FAIL'} (any {k_half} consecutive successes)",
        f"- **Success Rate**: {results['success_rate']:.1%} ({results['num_successes']}/{k} successful)",
        f"- **Avg Steps on Success**: {results['avg_steps_on_success']:.1f}",
        f"- **Total Steps**: {results['total_steps']}",
        ""
    ]

    # Add failure breakdown if any failures
    if results["failure_breakdown"]:
        lines.append("## Failure Breakdown by Category")
        for reason, count in sorted(results["failure_breakdown"].items(), key=lambda x: -x[1]):
            lines.append(f"- **{reason}**: {count} occurrence(s)")
        lines.append("")

        # Add fault author breakdown
        fault_authors = {}
        fault_types = {}
        for attempt in results["attempts"]:
            if not attempt["success"] and attempt.get("failure_detail"):
                author = attempt["failure_detail"].get("fault_author", "unknown")
                fault_type = attempt["failure_detail"].get("fault_type", "other")
                fault_authors[author] = fault_authors.get(author, 0) + 1
                fault_types[fault_type] = fault_types.get(fault_type, 0) + 1

        if fault_authors:
            lines.append("## Fault Author Distribution")
            for author, count in sorted(fault_authors.items(), key=lambda x: -x[1]):
                author_emoji = {"agent": "🤖", "user": "👤", "environment": "⚙️", "unknown": "❓"}.get(author, "❓")
                lines.append(f"- {author_emoji} **{author.capitalize()}**: {count} occurrence(s)")
            lines.append("")

        if fault_types:
            lines.append("## Fault Type Distribution")
            fault_type_labels = {
                "called_wrong_tool": "Called Wrong Tool",
                "used_wrong_tool_argument": "Wrong Tool Arguments",
                "goal_partially_completed": "Goal Partially Completed",
                "other": "Other"
            }
            for fault_type, count in sorted(fault_types.items(), key=lambda x: -x[1]):
                label = fault_type_labels.get(fault_type, fault_type)
                lines.append(f"- **{label}**: {count} occurrence(s)")
            lines.append("")

    # Add per-attempt details with rich failure information
    lines.append("## Attempt Details")
    for attempt in results["attempts"]:
        emoji = "✅" if attempt["success"] else "❌"
        lines.append(
            f"{emoji} **Attempt {attempt['attempt']}**: "
            f"{'Success' if attempt['success'] else 'Failed'} "
            f"(steps={attempt['steps']}, time={attempt['time']:.1f}s)"
        )

        # Add comprehensive failure information
        if not attempt["success"]:
            failure_detail = attempt.get("failure_detail", {})

            if attempt["error"]:
                lines.append(f"   ↳ **Error**: {attempt['error']}")

            if failure_detail:
                # Category and description
                category = failure_detail.get("category", "unknown")
                description = failure_detail.get("description", "")
                lines.append(f"   ↳ **Category**: {category}")
                if description:
                    lines.append(f"   ↳ **Description**: {description}")

                # Fault attribution
                fault_author = failure_detail.get("fault_author", "unknown")
                fault_type = failure_detail.get("fault_type", "other")
                fault_author_emoji = {"agent": "🤖", "user": "👤", "environment": "⚙️", "unknown": "❓"}.get(fault_author, "❓")
                fault_type_label = {
                    "called_wrong_tool": "Called Wrong Tool",
                    "used_wrong_tool_argument": "Wrong Tool Arguments",
                    "goal_partially_completed": "Goal Partially Completed",
                    "other": "Other"
                }.get(fault_type, fault_type)
                lines.append(f"   ↳ {fault_author_emoji} **Fault**: {fault_author} | **Type**: {fault_type_label}")

                # Score breakdown
                action_score = failure_detail.get("action_score")
                output_score = failure_detail.get("output_score")
                if action_score is not None:
                    lines.append(f"   ↳ **Action Score (r_actions)**: {action_score} (database state {'✅ correct' if action_score == 1.0 else '❌ wrong'})")
                if output_score is not None:
                    lines.append(f"   ↳ **Output Score (r_outputs)**: {output_score}")

                # Output analysis
                missing = failure_detail.get("missing_outputs", [])
                provided = failure_detail.get("provided_outputs", [])
                expected = failure_detail.get("expected_outputs", [])

                if expected:
                    lines.append(f"   ↳ **Expected outputs**: {', '.join(expected) if expected else 'None'}")
                if provided:
                    lines.append(f"   ↳ **Provided outputs**: {', '.join(provided)}")
                if missing:
                    lines.append(f"   ↳ **Missing outputs**: {', '.join(missing)}")

                # Ground truth actions
                gt_actions = failure_detail.get("ground_truth_actions", [])
                if gt_actions:
                    lines.append(f"   ↳ **Expected # of actions**: {len(gt_actions)}")

                # Task instruction (first 150 chars)
                task_inst = failure_detail.get("task_instruction")
                if task_inst:
                    task_preview = task_inst[:150] + "..." if len(task_inst) > 150 else task_inst
                    lines.append(f"   ↳ **Task**: {task_preview}")

    message = "\n".join(lines)

    # Report to AgentBeats
    ab.record_battle_event(
        battle_context,
        message,
        results
    )
