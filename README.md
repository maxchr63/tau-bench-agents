# Tau-Bench for Agent Beats

Example code for agentifying Tau-Bench using A2A and MCP standards.


## 0. Installation

```bash
uv sync
```

### 0. Add API keys

First, configure `.env` with
`ANTHROPIC_API_KEY=` or  
`OPENAI_API_KEY=...`,  (currently setup for open ai api keys)
The model and provider used can be changed by changing the task, completion and env confing in the respective agent.py files
(only uncommenting needed)

## 1.  Start AgentBeats

Open a new terminal and execute the following commands:

```shell
# Navigate to AgentBeats directory best into the cloned repo (could be different)
cd ~/Projects/agentbeats

# Create and activate virtual environment with Python 3.11
python3.11 -m venv venv
source venv/bin/activate

# Install AgentBeats
pip install -e .

# Create a .env file
touch .env
echo "OPENROUTER_API_KEY=your-openrouter-api-key" >> .env
echo "OPENAI_API_KEY=your-openai-api-key" >> .env

# Install frontend dependencies
agentbeats install_frontend --webapp_version webapp-v2

# Launch AgentBeats
agentbeats deploy
```

Now, you can access the AgentBeats UI at** **[http://localhost:5173](http://localhost:5173/)



## 2.  and restart Agents:
This is the way you need to launch the agents, if you want to launch them for agentbeats web-appp

```shell
pkill -f 'python main.py'
pkill -f 'python.*launcher'
cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents
./start_launchers.sh
```


I you just want to tun a battle in the terminal, lauching the main in combiation with the terminal launcher is the way to go

```bash
uv run python main.py launch

```

## 3. Change Configeration parameters:


can be done in `tau-bench-agents/src/green_agent/agent.py`

task id sets the current task thats evaluated from tau-bench and the ratil that it is supposed to be a retail task

```bash
env_config = {
        "env": "retail",
        "user_strategy": "llm",
        "user_model": "gpt-5",  # Changed to GPT-5
        "user_provider": "openai",
        "task_split": "test",
        "task_ids": [1],
        }
```

##  3. Design Philosophy

### Green Agent: Deterministic Orchestrator

Our green agent uses **direct Python orchestration** rather than an LLM-driven tool-calling approach:

```python
# We manually control the evaluation loop
async def execute(self, context: RequestContext, event_queue: EventQueue):
    env = get_env(...)  # Load tau-bench environment
    
    # Explicit evaluation loop
    for step in range(max_num_steps):
        # 1. Send message to white agent
        response = await my_a2a.send_message(white_agent_url, message)
        
        # 2. Parse response
        action = parse_white_agent_response(response)
        
        # 3. Execute in environment
        result = env.step(action)
        
        # 4. Check completion
        if result.done:
            break
    
    # Report final results
    await report_battle_results(battle_id, result.reward)
```

**Why this approach?**

-  **Predictable**: Same evaluation process every time
-  **Transparent**: Easy to understand what's happening
-  **Efficient**: No LLM overhead for orchestration
-  **Suitable**: Tau-bench evaluation is a well-defined procedure

**Alternative approach (not used here):**
Use the AgentBeats SDK (`@ab.tool`) to make the orchestration LLM-driven, giving the green agent's LLM tools to decide when/how to evaluate. This is more flexible but adds complexity and potential unpredictability.

### White Agent: LLM-Driven Tool User

Our white agent IS LLM-driven because it needs to:
- Understand the task description and policy
- Choose appropriate tools to call from the available set
- Respond to the user naturally
- Handle multi-turn conversations

**Tool Calling Approach: Text-Based (Not Native Function Calling)**

The white agent receives tool descriptions as **text** in the initial prompt:

```python
# Tools provided as JSON text
task_description = f"""
{policy_document}

Available tools:
{json.dumps(tool_schemas, indent=2)}

Format: <json>{{"name": "tool_name", "kwargs": {{}}}}</json>

User message: {message}
"""
```


## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Tau-Bench Environment (External Package)                    │
│                                                             │
│  ┌────────────────┐  ┌──────────────────┐  ┌─────────────┐  │
│  │ tools_info     │  │ wiki (policy)    │  │ Database    │  │
│  │ (JSON schemas) │  │ (text document)  │  │ (users,     │  │
│  └────────────────┘  └──────────────────┘  │  orders)    │  │
│           │                    │           └─────────────┘  │
│           └────────────────────┼─────────────────┐          │
│                                │                 │          │
│                    ┌───────────▼───────────┐     │          │
│                    │ step(action)          │     │          │
│                    │ - Executes tool       │◄────┘          │
│                    │ - Returns observation │                │
│                    │ - Calculates reward   │                │
│                    └───────────────────────┘                │
└──────────────────────────────▲─────────────────────────────-┘
                               │
                               │ env.step(action)
                               │
┌──────────────────────────────┴───────────────────────────-──┐
│ Green Agent (Our Code)                                      │
│                                                             │
│  1. Get tools_info + wiki from env                          │
│  2. Format as text prompt                                   │
│  3. Send to white agent ─────────────────-───┐              │
│                                              │              │
│  4. Receive JSON response ◄──────────────────┼───────────┐  │
│  5. Parse: action = {"name": "...", ...}     │           │  │
│  6. Execute: env.step(action)                │           │  │
│  7. Get result: observation, reward, done    │           │  │
│  8. Send result back to white agent ─────────┼─────┐     │  │
│                                              │     │     │  │
└──────────────────────────────────────────────┼─────┼─────┼──┘
                                               │     │     │
                                               ▼     │     ▼
┌────────────────────────────────────────────────────────────-──┐
│ White Agent (Our Code)                       │     │          │
│                                              │     │          │
│  Receives text:                              │     │          │
│  ┌─────────────────────────────────────--┐   │     │          │
│  │ Policy: "authenticate users first..." │   │     │          │
│  │ Tools: [{name: "find_user_id_..."}]   │   │     │          │
│  │ User message: "I want to exchange..." │   │     │          │
│  └─────────────────────────────────────--┘   │     │          │
│                │                             │     │          │
│                ▼                             │     │          │
│  ┌─────────────────────────┐                 │     │          │
│  │ LLM (GPT-4o / Claude)   │                 │     │          │
│  │ - Reads policy          │                 │     │          │
│  │ - Sees tools available  │                 │     │          │
│  │ - Decides which to call │                 │     │          │
│  └─────────────────────────┘                 │     │          │
│                │                             │     │          │
│                ▼                             │     │          │
│  Generates JSON: {"name": "respond", ...}────┘     │          │
│                                                    │          │
│  Next turn receives: "Tool result: user_id_123" ◄──┘          │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────┐
│                        AgentBeats System                        │
│                                                                 │
│  ┌─────────────────┐              ┌──────────────────┐          │
│  │  Frontend (UI)  │◄────────────►│  Backend (API)   │          │
│  │  Port: 5173     │              │  Port: 9000      │          │
│  └─────────────────┘              └──────────────────┘          │
│         │                                   │                   │
│         │                x                  │                   │
│         └───────────────┬───────────────────┘                   │
│                         │                                       │
└─────────────────────────┼───────────────────────────────────────┘
                          │
                          │ Registers agents & creates battles
                          │
        ┌─────────────────┴──────────────────┐
        │                                    │
        ▼                                    ▼
┌──────────────────┐              ┌──────────────────┐
│ Green Launcher   │              │ White Launcher   │
│ Port: 9110       │              │ Port: 9210       │
│                  │              │                  │
│ ┌──────────────┐ │              │ ┌──────────────┐ │
│ │ /health      │ │              │ │ /health      │ │
│ │ /status      │ │              │ │ /status      │ │
│ │ /launch  ◄───┼─┼──────────────┼─┼─ POST        │ │
│ │ /terminate   │ │              │ │ /terminate   │ │
│ └──────────────┘ │              │ └──────────────┘ │
└────────┬─────────┘              └────────┬─────────┘
         │                                  │
         │ Spawns subprocess                │ Spawns subprocess
         │ "uv run python main.py green"    │ "uv run python main.py white"
         │                                  │
         ▼                                  ▼
┌──────────────────┐              ┌──────────────────┐
│ Green Agent      │              │ White Agent      │
│ Port: 9001       │              │ Port: 9002       │
│                  │              │                  │
│ ┌──────────────┐ │              │ ┌──────────────┐ │
│ │ agent-card   │ │              │ │ agent-card   │ │
│ │ /message     │ │              │ │ /message     │ │
│ └──────────────┘ │              │ └──────────────┘ │
│                  │              │                  │
│ Tau-Bench        │  Evaluates   │ Retail Service   │
│ Evaluator        │─────────────►│ Agent            │
│                  │              │                  │
└──────────────────┘              └──────────────────┘
```

## 4. 📋 URLs Reference Card

| What                     | URL                   |
| ------------------------ | --------------------- |
| **White Agent**    | http://localhost:9004 |
| **White Launcher** | http://localhost:9210 |
| **Green Agent**    | http://localhost:9003 |
| **Green Launcher** | http://localhost:9110 |
| **AgentBeats UI**  | http://localhost:5173 |
| **AgentBeats API** | http://localhost:9000 |
| **AgentBeats MCP** | http://localhost:9001 |


## 5. Future Improvements

Based on AgentBeats' upgrade recommendations, here are planned enhancements:

### 1. **MCP-Based Tool Delivery (Approach III)** 🎯 **Priority Upgrade**

**Current State**: Tools are delivered as JSON text in prompts (Approach II)

**Planned Enhancement**: Implement tau-bench tools as an MCP (Model Context Protocol) server

```python
# Future implementation
class TauBenchMCPServer:
    def __init__(self, env):
        self.env = env
        self.app = FastAPI()
        
        @self.app.get("/tools")
        async def list_tools():
            return self.env.tools_info
        
        @self.app.post("/execute")
        async def execute_tool(tool_call: ToolCall):
            action = Action(name=tool_call.name, kwargs=tool_call.kwargs)
            result = self.env.step(action)
            return result

# Green agent would:
# 1. Launch MCP server: mcp_server = TauBenchMCPServer(env)
# 2. Tell white agent: "Connect to MCP at http://localhost:9500"
# 3. White agent uses native MCP client to discover and call tools
```

**Benefits**:
-  Standards-based (MCP is industry standard)
-  White agents can use native tool-calling SDKs
-  Dynamic tool discovery
-  Better separation of concerns
-  More realistic evaluation environment

**Trade-offs**:
- Higher complexity in setup
- Requires white agents to support MCP protocol
- More moving parts (additional server process)

### 2. **Multiple/Parallel Task Evaluation**

**Current State**: Evaluates single task (task_id=1)

**Planned Enhancement**: Support batch evaluation of multiple tasks

**Option A - External Parallelism** (Simpler):
```python
# Run multiple battles in parallel
async def evaluate_multiple_tasks():
    tasks = [1, 2, 3, 4, 5]
    results = await asyncio.gather(*[
        run_battle(white_agent_url, task_id=task)
        for task in tasks
    ])
    return aggregate_results(results)
```

**Option B - Internal Parallelism** (More Efficient):
```python
# Single green agent manages multiple environments
class ParallelGreenAgent:
    async def execute(self):
        envs = [get_env(task_index=i) for i in range(5)]
        # Run all tasks in single session if white agent supports isolation
        results = await evaluate_parallel(white_agent_url, envs)
```

### 3. **Task-Based Responses for Long Operations**

**Current Issue**: Long evaluations risk timeouts with message-only responses

**Planned Enhancement**: Use A2A task-based responses
```python
# Create task for long-running evaluation
task_id = await create_task()

# Send periodic updates
await send_task_update(task_id, "Step 5/30 completed...")

# Final result
await send_task_result(task_id, final_result)
```

### 4. **Support All Tau-Bench Configurations**

**Current State**: Hardcoded to retail environment, specific model configs

**Planned Enhancement**: 
- CLI options for all tau-bench parameters
- Support for airline, retail, banking domains
- Configurable task splits (train/test/dev)
- User simulation strategies (rule-based, LLM-based)

```bash
# Future CLI
uv run python main.py launch \
    --env retail \
    --task-split test \
    --task-ids 1,2,3,4,5 \
    --user-model claude-sonnet-4 \
    --white-agent-url http://localhost:9004
```

### 5. **Multiple White Agent SDKs**

Test white agents built with different frameworks:
- ✅ Current: Custom LLM wrapper
- 🔄 Planned: Google ADK agents
- 🔄 Planned: OpenAI Assistants API
- 🔄 Planned: LangChain agents
- 🔄 Planned: Anthropic Claude agents

### 6. **Streaming & Push Notifications**

- Real-time progress updates during evaluation
- Streaming tool call results
- Live leaderboard updates

---

## Implementation Priority

For a production-ready tau-bench integration:

1. **Phase 1** (Current Demo): Basic text-based tool calling with single task
2. **Phase 2** (Next):  MCP-based tool delivery
3. **Phase 3**: Multiple task support + task-based responses
4. **Phase 4**: Full tau-bench config support + multiple SDKs
5. **Phase 5**: Streaming + advanced features