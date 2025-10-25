"""White agent implementation - the target agent being tested."""

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
        # TODO: modify task_config as needed and change back to anthropic model
        # response = completion(
        #     #model="claude-3-7-sonnet-20250219",  # ← Use Claude
        #     model="claude-haiku-4-5-20251001",  
        #     messages=messages,
        #     temperature=0.0,
        # )

        # Using OpenAI GPT-4o-mini (fast and cost-effective)
        response = completion(
            model="gpt-4o-mini",  # Valid OpenAI model
            messages=messages,
            temperature=0.0,
        )

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
        # Clear conversation history for this context
        if context.context_id in self.ctx_id_to_messages:
            self.ctx_id_to_messages[context.context_id] = []


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
