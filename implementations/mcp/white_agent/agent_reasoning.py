"""Reasoning-enhanced white agent variant - adds explicit reasoning steps.

This agent maintains conversation memory AND explicitly reasons through problems
before deciding on actions. Expected to perform BETTER than baseline due to
improved decision-making through structured reasoning.
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
logger = logging.getLogger("white_agent_reasoning")

# Same history limits as baseline
MAX_MESSAGES_IN_HISTORY = 60

dotenv.load_dotenv()


def prepare_white_agent_card(url):
    skill = AgentSkill(
        id="task_fulfillment",
        name="Task Fulfillment",
        description="Handles user requests with explicit reasoning",
        tags=["general"],
        examples=[],
    )
    card = AgentCard(
        name="tau_white_agent_reasoning",
        description="Retail customer service agent with explicit reasoning capabilities",
        url=url,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )
    return card


class ReasoningWhiteAgentExecutor(AgentExecutor):
    """Executor with explicit reasoning - thinks through problems before acting."""

    def __init__(self):
        self.ctx_id_to_messages = {}
        self.max_contexts = 20

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

        if context.context_id not in self.ctx_id_to_messages:
            # Security: Limit memory growth - clear oldest contexts if too many
            if len(self.ctx_id_to_messages) >= self.max_contexts:
                oldest_context = next(iter(self.ctx_id_to_messages))
                del self.ctx_id_to_messages[oldest_context]
                print(f"[Reasoning Agent] Cleared old context {oldest_context} to prevent memory leak (max={self.max_contexts})")

            # Initialize with ENHANCED system prompt that encourages explicit reasoning
            print(f"[Reasoning Agent] Creating NEW context: {context.context_id}")
            self.ctx_id_to_messages[context.context_id] = [
                {
                    "role": "system",
                    "content": """You are a helpful retail customer service agent with strong reasoning capabilities.

⚠️ CRITICAL FORMAT REQUIREMENT ⚠️
EVERY response MUST include BOTH <reasoning> AND <json> tags.
Missing <json> tags = automatic failure. No exceptions.

Before taking any action or responding to the user, you MUST:
1. Think through the problem step-by-step
2. Consider what information you have and what you need
3. Evaluate your options and their consequences
4. Decide on the best course of action

REQUIRED Format for EVERY response:
<reasoning>
[Your step-by-step reasoning process here. Be explicit about:
 - What the user is asking for
 - What information/context you have
 - What actions are available to you
 - Why you're choosing this particular action
 - Any potential issues or edge cases to consider]
</reasoning>

<json>
{"name": "function_name_or_respond", "kwargs": {"content": "your message or arguments"}}
</json>

The reasoning section helps you think clearly and make better decisions. The JSON section contains your final action.

IMPORTANT: For multi-step tasks (orders, reservations, etc.):
1. Gather ALL necessary information FIRST (user details, order/reservation details)
2. Verify you understand the complete task
3. Take ALL actions needed to fully complete the task
4. Don't stop until the database state matches what's expected
"""
                }
            ]
        else:
            print(f"[Reasoning Agent] Reusing existing context: {context.context_id} (currently {len(self.ctx_id_to_messages[context.context_id])} messages)")

        messages = self.ctx_id_to_messages[context.context_id]
        messages.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        # Smart trimming: Keep system message + last N messages (sliding window)
        if len(messages) > MAX_MESSAGES_IN_HISTORY + 1:  # +1 for system message
            system_msg = messages[0]
            recent_messages = messages[-(MAX_MESSAGES_IN_HISTORY):]
            messages = [system_msg] + recent_messages
            self.ctx_id_to_messages[context.context_id] = messages
            print(f"[Reasoning Agent] Trimmed history to {len(messages)} messages (kept system + last {MAX_MESSAGES_IN_HISTORY})")

        # Use the globally configured model from shared_config
        print(f"[Reasoning Agent] Using model: {TAU_USER_MODEL}, provider: {TAU_USER_PROVIDER}")

        # CRITICAL: GPT-5 models only support temperature=1, other models work with temperature=0
        temperature = 1.0 if "gpt-5" in TAU_USER_MODEL.lower() else 0.0
        print(f"[Reasoning Agent] Using temperature: {temperature}")

        # Add timeout protection to prevent hanging on LLM calls
        import asyncio
        try:
            logger.info(f"[API] >>> Sending LLM request: model={TAU_USER_MODEL}, messages={len(messages)}, temp={temperature}")
            print(f"[Reasoning Agent API] >>> Sending LLM request: model={TAU_USER_MODEL}, messages={len(messages)}, temp={temperature}", file=sys.stderr, flush=True)
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
            print(f"[Reasoning Agent API] <<< Received LLM response: {len(response.choices[0].message.content or '')} chars", file=sys.stderr, flush=True)
        except asyncio.TimeoutError:
            error_msg = "LLM completion timed out after 60 seconds"
            logger.error(f"[API] XXX {error_msg}")
            print(f"[Reasoning Agent ERROR] {error_msg}")
            # Return error response in expected format
            await event_queue.enqueue_event(
                new_agent_text_message(
                    '<json>{"name": "transfer_to_human_agents", "kwargs": {"content": "I apologize, but I\'m experiencing technical difficulties. Please contact human support."}}</json>',
                    context_id=context.context_id
                )
            )
            return

        next_message = response.choices[0].message.model_dump()  # type: ignore
        content = next_message["content"]

        # Log reasoning if present (for debugging/analysis)
        if "<reasoning>" in content and "</reasoning>" in content:
            import re
            reasoning_match = re.search(r'<reasoning>(.*?)</reasoning>', content, re.DOTALL)
            if reasoning_match:
                reasoning = reasoning_match.group(1).strip()
                print(f"[Reasoning Agent] REASONING:\n{reasoning}")
                logger.info(f"[REASONING] {reasoning}")

        messages.append(
            {
                "role": "assistant",
                "content": content,
            }
        )

        # Instrumentation: log enqueue progress and catch any issues explicitly
        logger.info("[EXEC] Enqueueing response event to event_queue")
        try:
            await event_queue.enqueue_event(
                new_agent_text_message(
                    content, context_id=context.context_id
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
        # Clear ALL conversation history to prevent any memory leakage
        self.ctx_id_to_messages = {}
        print("[SECURITY] Reasoning agent memory completely cleared (reset called)")


def start_white_agent(agent_name="reasoning_white_agent", host="localhost", port=9024):
    """Start reasoning white agent on port 9024 (different from baseline 9004 and stateless 9014)."""
    # FORCE logging configuration
    root_logger = logging.getLogger()

    # Remove all existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create new handlers
    file_handler = logging.FileHandler('white_agent_reasoning.log', mode='a')
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

    print("Starting reasoning-enhanced white agent (with explicit reasoning)...")
    logger.info("Starting reasoning-enhanced white agent (with explicit reasoning)...")
    url = f"http://{host}:{port}"
    card = prepare_white_agent_card(url)

    request_handler = DefaultRequestHandler(
        agent_executor=ReasoningWhiteAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=card,
        http_handler=request_handler,
    )

    uvicorn.run(app.build(), host=host, port=port)


if __name__ == "__main__":
    start_white_agent()
