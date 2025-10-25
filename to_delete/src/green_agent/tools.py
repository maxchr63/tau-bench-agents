# -*- coding: utf-8 -*-
"""
Tau-Bench Green Agent Tools

This module exposes tau-bench evaluation tools using the AgentBeats SDK.
These tools can be used directly by agents or exposed through MCP servers.
"""

import json
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

import agentbeats as ab
from tau_bench.envs import get_env
from tau_bench.types import SolveResult, RESPOND_ACTION_NAME, Action

# Set up logging
logger = logging.getLogger("green_agent.tools")


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
            AgentCard, Message, Part, TextPart, Role,
            SendMessageRequest, MessageSendParams
        )
        from uuid import uuid4
        import httpx

        # Create client using AgentBeats pattern
        httpx_client = httpx.AsyncClient(timeout=timeout)
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=white_agent_url)

        card: AgentCard | None = await resolver.get_agent_card(
            relative_card_path="/.well-known/agent.json"
        )

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
        response = await client.send_message(request=req)

        return {
            "success": True,
            "response": response,
            "context_id": context_id,
            "message_id": request_id
        }

    except Exception as e:
        logger.error(f"Error communicating with white agent: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


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
                agent_name="tau_green_agent"
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
                agent_name="tau_green_agent"
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
    user_model: str = "gpt-4o-mini",
    user_provider: str = "openai",
    task_split: str = "test",
    task_id: int = 5
) -> Dict[str, Any]:
    """
    Set up a tau-bench evaluation environment.

    Args:
        env_name: Environment name (e.g., "retail", "airline")
        user_strategy: User simulation strategy
        user_model: Model to use for user simulation
        user_provider: Provider for user model
        task_split: Task split to use
        task_id: Specific task ID to evaluate

    Returns:
        Dict containing environment info and tool schemas
    """
    try:
        logger.info(f"Setting up tau-bench environment: {env_name}, task {task_id}")

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
            user_model="gpt-4o-mini",
            task_split="test",
            user_provider="openai",
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
            user_model="gpt-4o-mini",
            task_split="test",
            user_provider="openai",
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
            "user_model": "gpt-4o-mini",
            "user_provider": "openai",
            "task_split": "test",
            "task_ids": [task_id],
        }

    env = get_env(
        env_name=env_config["env"],
        user_strategy=env_config["user_strategy"],
        user_model=env_config["user_model"],
        task_split=env_config["task_split"],
        user_provider=env_config.get("user_provider"),
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

@ab.tool
def parse_xml_tags(text: str, tag: str) -> str:
    """
    Parse XML-style tags from text.

    Args:
        text: Text to parse
        tag: Tag name to extract (e.g., "json", "xml")

    Returns:
        Content within the specified tags, or error message
    """
    from src.my_util import parse_tags

    try:
        tags = parse_tags(text)
        if tag in tags:
            return tags[tag]
        else:
            return f"Tag '{tag}' not found. Available tags: {list(tags.keys())}"
    except Exception as e:
        return f"Error parsing tags: {str(e)}"


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
