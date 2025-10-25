# Tau-Bench Agents - MCP Implementation Guide

An MCP-ready implementation of τ-bench integration for AgentBeats, featuring modular architecture and modern SDK utilities.

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
cd ~/tau-bench-agents
uv sync

# 2. Test the MCP tools
uv run python test_refactored_tools.py

# 3. Start MCP agents
./scripts/start_mcp.sh

# 4. Verify agents are running
./check_status.sh
```

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Installation](#installation)
- [Agent Components](#agent-components)
- [Available Tools](#available-tools)
- [Testing on AgentBeats](#testing-on-agentbeats)
- [Refactored vs Original](#refactored-vs-original)
- [Migration Guide](#migration-guide)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────┐
│            AgentBeats Backend                    │
│          (Orchestrates battles)                  │
└─────────────────────────────────────────────────┘
                      ↓ ↓
        ┌─────────────┴─┴─────────────┐
        ↓                              ↓
┌──────────────────┐        ┌──────────────────┐
│  Launcher Server │        │  Launcher Server │
│   (FastAPI)      │        │   (FastAPI)      │
│   Port 9110/9111 │        │   Port 9210      │
└──────────────────┘        └──────────────────┘
        ↓                              ↓
┌──────────────────┐        ┌──────────────────┐
│   Green Agent    │        │   White Agent    │
│   (A2A Server)   │───────→│   (A2A Server)   │
│   Port 9003/9005 │        │   Port 9004      │
└──────────────────┘        └──────────────────┘
```

### Port Mapping

| Component                    | Port | URL                   | Purpose                |
| ---------------------------- | ---- | --------------------- | ---------------------- |
| **MCP Green Launcher** | 9111 | http://localhost:9111 | FastAPI control server |
| **MCP Green Agent**    | 9006 | http://localhost:9006 | A2A agent server       |
| **White Launcher**     | 9210 | http://localhost:9210 | FastAPI control server |
| **White Agent**        | 9004 | http://localhost:9004 | A2A agent server       |

---

## Installation

### Prerequisites

- Python 3.11 or higher
- uv (recommended) or pip
- AgentBeats repository at `../agentbeats`

### Setup Steps

```bash
# 1. Navigate to project
cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents

# 2. Install with uv (recommended)
uv sync

# OR install with pip
python -m venv .venv
source .venv/bin/activate
pip install -e ../agentbeats
pip install a2a-sdk[http-server] anthropic dotenv tau-bench typer uvicorn

# 3. Verify installation
uv run python test_refactored_tools.py
```

### Configuration

Create a `.env` file with required API keys:

```bash
ANTHROPIC_API_KEY=your_key_here
```

---

## Agent Components

### File Structure

```
tau-bench-agents/
├── main.py                      # Entry point (uses MCP implementations)
├── .env                         # API keys
├── pyproject.toml              # Dependencies
├── implementations/
│   ├── mcp/                    # ✅ MCP-ready implementation
│   │   ├── green_agent/
│   │   │   ├── agent.py       # MCP green agent
│   │   │   ├── tools.py       # 9 MCP-ready tools
│   │   │   └── tau_green_agent_mcp.toml
│   │   └── white_agent/
│   │       ├── agent.py       # White agent
│   │       └── tau_white_agent.toml
│   └── a2a/                    # A2A-only implementation
│       ├── green_agent/
│       └── white_agent/
├── launchers/
│   ├── green_launcher_mcp.py   # MCP green launcher (port 9111)
│   ├── green_launcher_a2a.py   # A2A green launcher (port 9110)
│   └── white_launcher.py       # White launcher (port 9210)
├── scripts/
│   ├── start_mcp.sh           # Start MCP agents
│   ├── start_a2a.sh           # Start A2A agents
│   └── start_side_by_side.sh  # Start both for comparison
└── test_refactored_tools.py   # MCP tools test suite
```

---

### Launchers

**Launchers** are FastAPI servers that control agent lifecycle:

- **Endpoints**: `/launch`, `/terminate`, `/reset`, `/status`, `/health`
- **Purpose**: AgentBeats backend calls these to manage agents
- **Port**: Separate from the actual agent ports

### Agents

**Agents** are A2A protocol servers:

- **Protocol**: Agent-to-Agent (A2A) communication
- **Green Agent**: Evaluates other agents using τ-bench
- **White Agent**: Target agent being evaluated

---

## Available Tools

### 9 Evaluation & Orchestration Tools

All tools use the `@ab.tool` decorator for MCP compatibility.

#### Communication Tools

1. **`send_message_to_white_agent(white_agent_url, message, context_id)`**

   - Send A2A messages to white agent
   - Uses AgentBeats SDK for robust communication
2. **`parse_xml_tags(text, tag_name)`**

   - Parse structured XML-style responses
   - Extract JSON tool calls from agent responses

#### Battle Tracking Tools

3. **`log_battle_progress(message, battle_id, backend_url)`**

   - Log evaluation progress to AgentBeats
   - Uses `ab.record_battle_event()`
4. **`report_battle_result(success, result_summary, battle_id, backend_url)`**

   - Report final evaluation results
   - Structured result reporting

#### Environment Tools

5. **`setup_tau_bench_environment(env_name, task_id)`**

   - Initialize τ-bench evaluation environment
   - Returns environment info and available tools
6. **`get_tau_bench_tools_as_json(task_id)`**

   - Export tool schemas as JSON
   - For providing to agents being evaluated
7. **`list_tau_bench_tools(task_id)`**

   - List all 16 available τ-bench retail tools
   - Returns tool names and descriptions

#### Evaluation Tools

8. **`evaluate_white_agent(white_agent_url, task_id, max_num_steps)`**

   - Run complete τ-bench evaluation
   - Multi-step conversation with white agent
9. **`format_evaluation_result(success, reward, info)`**

   - Format results as markdown
   - Structured output for reporting

### 16 Tau-Bench Retail Tools

The underlying τ-bench environment provides 16 tools:

1. `calculate` - Mathematical expressions
2. `cancel_pending_order` - Cancel orders
3. `exchange_delivered_order_items` - Exchange items
4. `find_user_id_by_email` - Find user by email
5. `find_user_id_by_name_zip` - Find user by name/zip
6. `get_order_details` - Get order information
7. `get_product_details` - Get product details
8. `get_user_details` - Get user profile
9. `list_all_product_types` - List products
10. `modify_pending_order_address` - Change address
11. `modify_pending_order_items` - Modify items
12. `modify_pending_order_payment` - Change payment
13. `modify_user_address` - Update address
14. `return_delivered_order_items` - Process returns
15. `think` - Internal reasoning
16. `transfer_to_human_agents` - Escalate to human

---

## Testing on AgentBeats

### Step 1: Start MCP Agents

```bash
cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents
./scripts/start_mcp.sh
```

This will:

- Clean up old processes on ports 9003, 9004, 9006, 9110, 9111, 9210
- Start MCP green launcher on port 9111
- Start white launcher on port 9210
- Launch both agents automatically

### Step 2: Verify Status

```bash
# Check launcher health
curl http://localhost:9111/health  # MCP green launcher
curl http://localhost:9210/health  # White launcher

# Or use the status script
./scripts/check_status.sh
```

Expected output:

```
✅ Green launcher is running (PID: XXXXX)
✅ White launcher is running (PID: XXXXX)
```

### Step 3: Register in AgentBeats UI

Open AgentBeats UI (typically http://localhost:5173):

**White Agent (Target):**

- Agent URL: `http://localhost:9004`
- Launcher URL: `http://localhost:9210`
- Is Green?: ❌ No
- Alias: `general_white_agent`

**MCP Green Agent (Evaluator):**

- Agent URL: `http://localhost:9006`
- Launcher URL: `http://localhost:9111`
- Is Green?: ✅ Yes
- Alias: `tau_green_agent_mcp`

### Step 4: Agents Are Auto-Launched

The `start_mcp.sh` script automatically launches the agents, so they should already be running. You can verify:

```bash
curl http://localhost:9006/.well-known/agent.json  # Green agent card
curl http://localhost:9004/.well-known/agent.json  # White agent card
```

### Step 5: Create Battle

In AgentBeats UI:

1. Click "Create Battle"
2. Select `tau_green_agent_mcp` (green agent/evaluator)
3. Select `general_white_agent` (white agent/target)
4. Configure tau-bench parameters if needed
5. Click "Start Battle"!

The agents will automatically reset and be ready for evaluation.

---

## MCP Implementation Details

### Key Features

| Feature                     | MCP Implementation                                           |
| --------------------------- | ------------------------------------------------------------ |
| **Architecture**      | Modular, self-contained                                      |
| **Dependencies**      | No external src/ imports                                     |
| **A2A Communication** | AgentBeats SDK `ab.send_message_to_agent()`                |
| **Battle Tracking**   | `ab.record_battle_event()` & `ab.record_battle_result()` |
| **Tool Exposure**     | `@ab.tool` decorators                                      |
| **MCP Ready**         | ✅ Yes                                                       |
| **Parse Tags**        | Local `_parse_tags_helper()` function                      |
| **Log Files**         | `implementations/mcp/green_agent.log`                      |

### Code Example

**MCP Implementation (Clean & Modern):**

```python
import agentbeats as ab
from . import tools as green_tools  # Local imports

# SDK-based communication
response = await green_tools.send_message_to_white_agent(url, message)

# Structured battle tracking
await green_tools.log_battle_progress("Step complete", battle_id, backend_url)

# Parse XML tags locally
json_content = green_tools.parse_xml_tags(response_text, "json")
```

### Launcher Features

Both launchers (green and white) include:

✅ **Auto-cleanup**: Kills old processes on startup
✅ **Backend notification**: Notifies AgentBeats when agents are ready
✅ **Proper reset**: Terminates and relaunches agents
✅ **Health checks**: `/health`, `/status` endpoints
✅ **Error handling**: Detailed error messages on failure

---

## Starting Different Implementations

### MCP Implementation (Recommended)

```bash
./scripts/start_mcp.sh
```

- Green Agent: http://localhost:9006 (Launcher: 9111)
- White Agent: http://localhost:9004 (Launcher: 9210)
- Features: MCP-ready, AgentBeats SDK, modular architecture

### A2A Implementation

```bash
./scripts/start_a2a.sh
```

- Green Agent: http://localhost:9003 (Launcher: 9110)
- White Agent: http://localhost:9004 (Launcher: 9210)
- Features: Traditional A2A, compatible with original workflows

### Side-by-Side Comparison

```bash
./scripts/start_side_by_side.sh
```

Run both implementations simultaneously for testing and comparison.

---

## Troubleshooting

### Connection Refused

**Symptom**: Cannot connect to agent/launcher

**Solutions**:

```bash
# Check if services are running
curl http://localhost:9110/status

# Check all ports
lsof -ti:9003,9004,9005,9110,9111,9210

# Restart launchers
pkill -f 'python src/.*_launcher.*\.py'
./start_launchers_side_by_side.sh
```

### ModuleNotFoundError: agentbeats

**Symptom**: Python cannot find agentbeats module

**Solutions**:

```bash
# Option 1: Use uv run
uv run python test_refactored_tools.py

# Option 2: Activate environment
source .venv/bin/activate
python test_refactored_tools.py

# Option 3: Verify installation
uv run python -c "import agentbeats; print('OK')"
```

### Agent Card Not Found

**Symptom**: 404 on `/.well-known/agent.json`

**Solutions**:

```bash
# Wait for agent to initialize
sleep 5
curl http://localhost:9005/.well-known/agent.json

# Check launcher status
curl http://localhost:9111/status

# Check logs
tail -f green_agent.log
```

### Battle Fails to Start

**Checks**:

1. ✅ Both agents are running
2. ✅ Launcher endpoints are accessible
3. ✅ Agent cards are accessible
4. ✅ No port conflicts

```bash
# Full health check
curl http://localhost:9111/health  # Refactored green launcher
curl http://localhost:9210/health  # White launcher
curl http://localhost:9005/.well-known/agent.json  # Green agent
curl http://localhost:9004/.well-known/agent.json  # White agent
```

### Ports Already in Use

**Solution**:

```bash
# The start_mcp.sh script automatically handles this!
# It kills processes on these ports: 9003, 9004, 9006, 9110, 9111, 9210

# If you need to manually clean up:
for port in 9003 9004 9006 9110 9111 9210; do
  lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null
done

# Then restart
./scripts/start_mcp.sh
```

### Battle Stuck on "Waiting for agents to be ready"

**Cause**: Launchers not notifying backend after reset

**Solution**: This is now fixed! Both launchers include backend notification:

```python
# In launchers/green_launcher_mcp.py and launchers/white_launcher.py
if backend_url and agent_id:
    async with httpx.AsyncClient() as client:
        await client.put(
            f"{backend_url}/agents/{agent_id}",
            json={"ready": True}
        )
```

If you still see this issue, restart the agents:

```bash
./scripts/start_mcp.sh
```

---

## Testing

### Run Test Suite

```bash
uv run python test_refactored_tools.py
```

**Expected Output**:

```
✓ PASS     Tool Registration
✓ PASS     List Tau-Bench Tools
✓ PASS     Setup Environment
✓ PASS     Parse XML Tags
✓ PASS     Format Evaluation Result

Results: 5/5 tests passed
🎉 All tests passed!
```

### Manual Testing

```bash
# Test individual tools
uv run python -c "
import asyncio
from implementations.mcp.green_agent import tools as green_tools

async def test():
    # List tools
    result = green_tools.list_tau_bench_tools(task_id=5)
    print(f'Available tools: {result}')
  
    # Setup environment
    env = await green_tools.setup_tau_bench_environment('retail', 5)
    print(f'Environment ready: {env[\"success\"]}')

asyncio.run(test())
"
```

---

## Next Steps

### Immediate Actions

1. ✅ **Install**: Run `uv sync`
2. ✅ **Test**: Run `python test_refactored_tools.py`
3. ✅ **Verify**: Run `./check_status.sh`

### Short-term Goals

4. **Compare**: Test both versions side-by-side
5. **Validate**: Verify results match expected behavior
6. **Migrate**: Replace original when confident

### Future Enhancements

7. **Wrap Individual Tools**: Create `@ab.tool` wrappers for all 16 τ-bench tools
8. **MCP Server**: Expose tools via MCP for Claude Desktop
9. **Multi-Environment**: Support airline, banking scenarios
10. **Batch Evaluation**: Evaluate multiple tasks in parallel

---

## Resources

- **Test Suite**: `test_refactored_tools.py`
- **MCP Example**: `mcp_server_example.py`
- **Original Documentation**: Check individual .md files for detailed info
- **AgentBeats Examples**: `../agentbeats/scenarios/`

---

## Summary

### What You Get

✅ **MCP-ready implementation** - Fully independent and modular
✅ **9 evaluation tools** with `@ab.tool` decorator
✅ **Better SDK utilities** - No custom utilities needed
✅ **Clean architecture** - Self-contained, no external dependencies
✅ **Auto-cleanup** - Scripts handle port conflicts automatically
✅ **Proper reset handling** - Backend notification on agent ready
✅ **Professional logging** - Structured events and error handling

### Quick Commands

```bash
# Start MCP agents
./scripts/start_mcp.sh

# Test tools
uv run python test_refactored_tools.py

# Check status
./check_status.sh

# View logs
tail -f implementations/mcp/green_agent.log
```

### File Locations

- **MCP Implementation**: `implementations/mcp/`
- **Launchers**: `launchers/green_launcher_mcp.py`, `launchers/white_launcher.py`
- **Start Scripts**: `scripts/start_mcp.sh`
- **Tests**: `test_refactored_tools.py`
- **MCP Example**: `mcp_server_example.py`

---

**Ready to start?** Run `./scripts/start_mcp.sh` and create a battle in AgentBeats! 🚀
