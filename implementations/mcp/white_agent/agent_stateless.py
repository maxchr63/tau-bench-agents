"""Stateless white agent variant - NO conversation memory.

This agent processes each request independently without maintaining conversation history.
Expected to perform WORSE than baseline due to lack of context in multi-turn conversations.
"""

# CRITICAL: Import shared config FIRST to configure LiteLLM globally
import sys
sys.path.insert(0, '/Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents')
from implementations.mcp.shared_config import TAU_USER_MODEL, TAU_USER_PROVIDER

import logging
import uvicorn
import dotenv
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentSkill, AgentCard, AgentCapabilities
from a2a.utils import new_agent_text_message
from litellm import completion

# Set up logging
logger = logging.getLogger("white_agent_stateless")

dotenv.load_dotenv()


def prepare_white_agent_card(url):
    skill = AgentSkill(
        id="task_fulfillment",
        name="Task Fulfillment",
        description="Handles user requests and completes tasks (stateless mode)",
        tags=["general"],
        examples=[],
    )
    card = AgentCard(
        name="tau_white_agent_stateless",
        description="Retail customer service agent (STATELESS - no conversation memory)",
        url=url,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )
    return card


class StatelessWhiteAgentExecutor(AgentExecutor):
    """Stateless executor - each request processed independently with NO memory."""

    def __init__(self):
        # No message history storage - this is the key difference
        pass

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # parse the task
        user_input = context.get_user_input()

        # Check if this is a battle_info notification (should be ignored by white agent)
        try:
            import json
            battle_data = json.loads(user_input)
            if battle_data.get("type") == "battle_info":
                # This is just a notification, acknowledge and return
                await event_queue.enqueue_event(
                    new_agent_text_message("Battle info received, ready for battle", context_id=context.context_id)
                )
                return
        except (json.JSONDecodeError, KeyError, ValueError):
            # Not JSON or not battle_info, proceed normally
            pass

        # STATELESS: Create fresh messages for EVERY request - no history!
        print(f"[Stateless Agent] Processing request with NO conversation history (context: {context.context_id})")
        messages = [
            {
                "role": "system",
                "content": "You are a helpful retail customer service agent. When you need to take an action or respond to the user, you should format your response with the action/response wrapped in <json>...</json> tags as specified in the instructions. The JSON should contain 'name' (the function name or 'respond') and 'kwargs' (the arguments or message content)."
            },
            {
                "role": "user",
                "content": user_input,
            }
        ]

        # Use the globally configured model from shared_config
        print(f"[Stateless Agent] Using model: {TAU_USER_MODEL}, provider: {TAU_USER_PROVIDER}")

        # CRITICAL: GPT-5 models only support temperature=1, other models work with temperature=0
        temperature = 1.0 if "gpt-5" in TAU_USER_MODEL.lower() else 0.0
        print(f"[Stateless Agent] Using temperature: {temperature}")

        # Add timeout protection to prevent hanging on LLM calls
        import asyncio
        try:
            logger.info(f"[API] >>> Sending LLM request: model={TAU_USER_MODEL}, messages={len(messages)}, temp={temperature}")
            print(f"[Stateless Agent API] >>> Sending LLM request: model={TAU_USER_MODEL}, messages={len(messages)}, temp={temperature}", file=sys.stderr, flush=True)
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    completion,
                    model=TAU_USER_MODEL,
                    messages=messages,
                    temperature=temperature,
                ),
                timeout=60.0  # 60 second timeout for LLM completion
            )
            logger.info(f"[API] <<< Received LLM response: {len(response.choices[0].message.content or '')} chars")
            print(f"[Stateless Agent API] <<< Received LLM response: {len(response.choices[0].message.content or '')} chars", file=sys.stderr, flush=True)
        except asyncio.TimeoutError:
            error_msg = "LLM completion timed out after 60 seconds"
            logger.error(f"[API] XXX {error_msg}")
            print(f"[Stateless Agent ERROR] {error_msg}")
            # Return error response in expected format
            await event_queue.enqueue_event(
                new_agent_text_message(
                    '<json>{"name": "transfer_to_human_agents", "kwargs": {"content": "I apologize, but I\'m experiencing technical difficulties. Please contact human support."}}</json>',
                    context_id=context.context_id
                )
            )
            return

        next_message = response.choices[0].message.model_dump()  # type: ignore

        # NO history storage - just return the response
        logger.info("[EXEC] Enqueueing response event to event_queue")
        try:
            await event_queue.enqueue_event(
                new_agent_text_message(
                    next_message["content"], context_id=context.context_id
                )
            )
            logger.info("[EXEC] Enqueue completed; returning from executor")
            return
        except Exception as enqueue_err:
            logger.error(f"[EXEC] Failed to enqueue response: {type(enqueue_err).__name__}: {enqueue_err}", exc_info=True)
            # Best-effort fallback
            try:
                await event_queue.enqueue_event(
                    new_agent_text_message(
                        '<json>{"name": "respond", "kwargs": {"content": "Encountered an internal error delivering response, but here is my reply."}}</json>',
                        context_id=context.context_id
                    )
                )
            finally:
                return

    async def cancel(self, context, event_queue) -> None:
        raise NotImplementedError

    async def reset(self, context: RequestContext) -> None:
        """Reset the agent state. Called by AgentBeats before each battle."""
        # No state to clear in stateless mode
        print("[SECURITY] Stateless agent reset called (no-op - no memory to clear)")
        pass


def start_white_agent(agent_name="stateless_white_agent", host="localhost", port=9014):
    """Start stateless white agent on port 9014 (different from baseline 9004)."""
    # FORCE logging configuration for white agent
    root_logger = logging.getLogger()

    # Remove all existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create new handlers with force=True
    file_handler = logging.FileHandler('white_agent_stateless.log', mode='a')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    # Add handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    root_logger.setLevel(logging.INFO)

    # Also configure the logger specifically
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.INFO)
    # Prevent duplicate logging via root handlers
    logger.propagate = False

    print("Starting stateless white agent (NO conversation memory)...")
    logger.info("Starting stateless white agent (NO conversation memory)...")
    url = f"http://{host}:{port}"
    card = prepare_white_agent_card(url)

    request_handler = DefaultRequestHandler(
        agent_executor=StatelessWhiteAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=card,
        http_handler=request_handler,
    )

    uvicorn.run(app.build(), host=host, port=port)


if __name__ == "__main__":
    start_white_agent()
