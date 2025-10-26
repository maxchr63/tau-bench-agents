"""White agent implementation - the target agent being tested."""

# CRITICAL: Import shared config FIRST to configure LiteLLM globally
import sys
sys.path.insert(0, '/Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents')
from implementations.mcp.shared_config import TAU_USER_MODEL, TAU_USER_PROVIDER

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

# Safety: limit message history to prevent context overflow while maintaining coherence
MAX_MESSAGES_IN_HISTORY = 20  # Keep last 20 messages (10 exchanges) + system prompt


dotenv.load_dotenv()


def prepare_white_agent_card(url):
    skill = AgentSkill(
        id="task_fulfillment",
        name="Task Fulfillment",
        description="Handles user requests and completes tasks",
        tags=["general"],
        examples=[],
    )
    card = AgentCard(
        name="tau_white_agent",
        description="Retail customer service agent being tested by tau-bench",
        url=url,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )
    return card


class GeneralWhiteAgentExecutor(AgentExecutor):
    def __init__(self):
        self.ctx_id_to_messages = {}
        self.max_contexts = 10  # Prevent unbounded memory growth (allow up to 10 concurrent contexts)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # parse the task
        user_input = context.get_user_input()
        
        ## Use in case white agent fails again

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
                print(f"[White Agent] Cleared old context {oldest_context} to prevent memory leak (max={self.max_contexts})")

            # Initialize with system prompt to enforce JSON format
            self.ctx_id_to_messages[context.context_id] = [
                {
                    "role": "system",
                    "content": "You are a retail customer service agent. You MUST always respond with your answer wrapped in <json>...</json> tags. Never respond with plain text outside these tags. Follow the JSON format exactly as specified in the user's instructions."
                }
            ]
        messages = self.ctx_id_to_messages[context.context_id]
        messages.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        # Smart trimming: Keep system message + last N messages (sliding window)
        # This maintains recent context while preventing unbounded growth
        if len(messages) > MAX_MESSAGES_IN_HISTORY + 1:  # +1 for system message
            # Keep system message (index 0) and the most recent MAX_MESSAGES_IN_HISTORY messages
            system_msg = messages[0]
            recent_messages = messages[-(MAX_MESSAGES_IN_HISTORY):]
            messages = [system_msg] + recent_messages
            self.ctx_id_to_messages[context.context_id] = messages
            print(f"[White Agent] Trimmed history to {len(messages)} messages (kept system + last {MAX_MESSAGES_IN_HISTORY})")
        
        # Use the globally configured model from shared_config
        print(f"[White Agent] Using model: {TAU_USER_MODEL}, provider: {TAU_USER_PROVIDER}")
        
        # CRITICAL: GPT-5 models only support temperature=1, other models work with temperature=0
        # With litellm.drop_params=True, unsupported params will be dropped automatically
        temperature = 1.0 if "gpt-5" in TAU_USER_MODEL.lower() else 0.0
        print(f"[White Agent] Using temperature: {temperature}")
        
        # Add timeout protection to prevent hanging on LLM calls
        import asyncio
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    completion,
                    model=TAU_USER_MODEL,
                    messages=messages,
                    temperature=temperature,
                ),
                timeout=60.0  # 60 second timeout for LLM completion
            )
        except asyncio.TimeoutError:
            error_msg = "LLM completion timed out after 60 seconds"
            print(f"[White Agent ERROR] {error_msg}")
            # Return error response in expected format
            await event_queue.enqueue_event(
                new_agent_text_message(
                    '<json>{"name": "transfer_to_human_agents", "kwargs": {"content": "I apologize, but I\'m experiencing technical difficulties. Please contact human support."}}</json>',
                    context_id=context.context_id
                )
            )
            return

        next_message = response.choices[0].message.model_dump()  # type: ignore
        messages.append(
            {
                "role": "assistant",
                "content": next_message["content"],
            }
        )
        await event_queue.enqueue_event(
            new_agent_text_message(
                next_message["content"], context_id=context.context_id
            )
        )

    async def cancel(self, context, event_queue) -> None:
        raise NotImplementedError

    async def reset(self, context: RequestContext) -> None:
        """Reset the agent state. Called by AgentBeats before each battle."""
        # Clear ALL conversation history to prevent any memory leakage
        self.ctx_id_to_messages = {}
        print("[SECURITY] White agent memory completely cleared (reset called)")


def start_white_agent(agent_name="general_white_agent", host="localhost", port=9004):
    print("Starting white agent...")
    url = f"http://{host}:{port}"
    card = prepare_white_agent_card(url)

    request_handler = DefaultRequestHandler(
        agent_executor=GeneralWhiteAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=card,
        http_handler=request_handler,
    )

    uvicorn.run(app.build(), host=host, port=port)
