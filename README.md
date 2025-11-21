# Tau-Bench Agents - MCP Implementation Guide

An MCP-ready implementation of τ-bench integration for AgentBeats, featuring modular architecture and modern SDK utilities.

---

## 📋 Quick Commands

**Installation:**

```bash
cd tau-bench-agents
uv sync
echo "OPENROUTER_API_KEY=your_key_here" >> .env
```

**Run White Agent (agent being tested):**

```bash
uv run python main.py white
# Runs on http://localhost:9004
```

**Run Green Agent (evaluator):**

```bash
uv run python main.py green
# Runs on http://localhost:9006
```

**Test Green Agent Evaluation:**

```bash
uv run python scripts/test_mcp_tools.py
# Tests tau-bench integration and tools
```

**Run on AgentBeats (complete):**

```bash
./scripts/start_mcp.sh
# Then register agents in AgentBeats UI at http://localhost:5173
```

**Reproduce Tau-Bench Results:**

```bash
# Configure task in implementations/mcp/green_agent/tau_green_agent_mcp.toml
# Set mode="manual", domain="retail", task_id=5, k=1
# Run battle in AgentBeats UI
```

---

## 🚀 Quick Start

```bash
# Install dependencies
uv sync

# Configure API keys (see Installation section)
# Start agents
./scripts/start_mcp.sh

# Test tools
uv run python scripts/test_mcp_tools.py
```

---

## Table of Contents

- [Installation](#installation)
- [Architecture Overview](#architecture-overview)
- [Configuration](#configuration)
- [Running Locally](#running-locally)
- [Pass@k Evaluation](#passk-evaluation)
- [Testing on AgentBeats](#testing-on-agentbeats)
- [Reproducing Tau-Bench Results](#reproducing-tau-bench-results)
- [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

- Python 3.11 or higher
- uv (recommended) or pip
- AgentBeats repository at `../agentbeats`

### Setup Steps

```bash
# 1. Navigate to project
cd /path/to/tau-bench-agents

# 2. Install with uv (recommended)
uv sync

# OR install with pip
python -m venv .venv
source .venv/bin/activate
pip install -e ../agentbeats
pip install a2a-sdk[http-server] anthropic dotenv tau-bench typer uvicorn

# 3. Configure API keys
touch .env
echo "ANTHROPIC_API_KEY=your_key_here" >> .env
echo "OPENAI_API_KEY=your_key_here" >> .env
# OR use OpenRouter (recommended for avoiding rate limits)
echo "OPENROUTER_API_KEY=your_key_here" >> .env

# 4. Verify installation
uv run python scripts/test_mcp_tools.py
```

### Additional hard reset before restart

```bash
# Clean up any running processes
pkill -f 'python main.py'
pkill -f 'python.*launcher'

# Navigate to tau-bench-agents
cd /path/to/tau-bench-agents

# Start MCP agents
./scripts/start_mcp.sh
```

### Provider Configuration

**Switching LLM Provider:**

Edit `implementations/mcp/shared_config.py` and change this line:

```python
USE_PROVIDER = "openrouter"  # Change to "openai" or "openrouter"
```

**Provider Options:**
- `"openrouter"` - Use OpenRouter (recommended, no rate limits)
  - Requires: `OPENROUTER_API_KEY` in `.env`
  - Model: `anthropic/claude-haiku-4.5`
  
- `"openai"` - Use OpenAI directly
  - Requires: `OPENAI_API_KEY` in `.env`
  - Model: `gpt-4o-mini`

After changing provider, restart the agents:
```bash
./scripts/start_mcp.sh
```

**Full configuration example:**

```python
# In implementations/mcp/shared_config.py
USE_PROVIDER = "openrouter"  # or "anthropic" or "openai"

# Models (automatically set based on provider)
TAU_USER_MODEL = "anthropic/claude-haiku-4.5"  # For tau-bench user simulation
TAU_USER_PROVIDER = "openrouter"
```

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
│   Port 9111      │        │   Port 9210      │
└──────────────────┘        └──────────────────┘
        ↓                              ↓
┌──────────────────┐        ┌──────────────────┐
│   Green Agent    │        │   White Agent    │
│   (A2A Server)   │───────→│   (A2A Server)   │
│   Port 9006      │        │   Port 9004      │
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

## Running Locally

You can run the agents locally in two ways:

### Option 1: With AgentBeats Web UI (Recommended)

This is the standard way to run agents with the AgentBeats interface.

**Step 1: Start AgentBeats**

```bash
# Navigate to AgentBeats directory
cd /path/to/agentbeats

# Create and activate virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install AgentBeats
pip install -e .

# Install frontend
agentbeats install_frontend --webapp_version webapp-v2

# Launch AgentBeats
agentbeats deploy
```

Access the UI at [http://localhost:5173](http://localhost:5173)

**Step 2: Start Tau-Bench Agents**

```bash
# In a new terminal, navigate to tau-bench-agents
cd /path/to/tau-bench-agents

# Start MCP agents
./scripts/start_mcp.sh
```

**Step 3: Register Agents in UI**

Register the agents in AgentBeats UI (see [Testing on AgentBeats](#testing-on-agentbeats))

### Option 2: Terminal Only (For Development)

Run evaluations directly from the command line without the web UI.

```bash
# Start agents via main.py
uv run python main.py green   # Green agent on port 9006
uv run python main.py white   # White agent on port 9004
```

---

## Configuration

### Pass@k Configuration

Edit `implementations/mcp/green_agent/tau_green_agent_mcp.toml`

```toml
[pass_k_config]
mode = "manual"           # "manual" or "random"
k = 2                     # Number of attempts (use 2 for stability)
domain = "retail"         # "retail" or "airline"
task_id = 1              # Task ID to evaluate
num_battles = 5          # Number of battles to run
```

**Important**: For stable evaluation, use `k=2`. Higher values (k=3, k=4) may experience reliability issues due to resource exhaustion.

---

## Pass@k Evaluation

### What is Pass@k?

Pass@k evaluation runs multiple independent attempts of the same task to measure consistency:

- **pass@k**: All k attempts must succeed consecutively
- **pass@(k/2)**: Any window of k/2 consecutive successes
- **success_rate**: Overall percentage of successful attempts

### Configuration Options

#### Mode: manual vs random

```toml
# Manual mode: Specify exact domain and task_id
mode = "manual"
domain = "retail"
task_id = 1

# Automatic random task selection mode: Run all tasks in domain
mode = "random"
domain = "retail"
```

#### Number of Attempts (k)

```toml
k = 2  # Recommended for stable evaluation
```

### How we do pass^k evaluation:

1. **Context Isolation**: Each attempt gets a unique context ID (`attempt_1_xxxxx`, `attempt_2_xxxxx`, etc.)
2. **White Agent Reset**: Between attempts, the white agent is optionally reset for fresh state
3. **Independent Evaluation**: Each attempt runs completely independently
4. **Aggregated Results**: Final metrics show pass@k, pass@(k/2), and detailed failure analysis

### Preventing Context Leakage Between Attempts

To ensure fair evaluation and prevent the white agent from "cheating" by reusing information from previous attempts:

**Unique Context IDs**: Each pass@k attempt generates a fresh context ID (e.g., `attempt_1_a3f2b9c4`, `attempt_2_d7e1f8a2`). The white agent's A2A server treats each context as an independent conversation thread, preventing conversation history from leaking between attempts.

**Optional Agent Reset**: The configuration supports `reset_between_attempts` (disabled by default) which restarts the white agent process entirely between attempts. This clears any in-memory state, caches, or context that might persist across evaluations.

**Environment Reset**: Before each attempt, the tau-bench environment is reset with `env.reset(task_index=task_id)`, generating fresh task instances, user messages, and database states to ensure each attempt is independent.

This multi-layered approach ensures that each pass@k attempt is a genuine independent evaluation, measuring the agent's consistent performance rather than its ability to remember previous interactions.

### Example Output

```
=== Pass@2 Evaluation Results ===
✅ pass@2: True (2/2 consecutive successes)
✅ pass@1: True
📊 Success rate: 100.0%

Attempt Details:
- Attempt 1/2: ✅ (reward=1.0, steps=8, time=15.2s)
- Attempt 2/2: ✅ (reward=1.0, steps=7, time=12.8s)
```

---

## Testing on AgentBeats

### Step 1: Start MCP Agents

```bash
./scripts/start_mcp.sh
```

This script will:

- Clean up old processes on ports 9006, 9004, 9111, 9210
- Start MCP green launcher on port 9111
- Start white launcher on port 9210
- Launch both agents automatically

**Manual Cleanup (if needed):**

If the script doesn't automatically clean up old processes:

```bash
# Kill launcher processes
pkill -f 'python.*launcher'

# Kill processes on specific ports
for port in 9006 9004 9111 9210; do
  lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null
done
```

### Step 2: Verify Status

```bash
# Check launcher health
curl http://localhost:9111/health  # MCP green launcher
curl http://localhost:9210/health  # White launcher

# Check agent cards
curl http://localhost:9006/.well-known/agent-card.json
curl http://localhost:9004/.well-known/agent-card.json

# Or use the status script
./scripts/check_status.sh
```

### Step 3: Register in AgentBeats UI

Open AgentBeats UI (typically http://localhost:5173):

**White Agent (Target):**

- Agent URL: `http://localhost:9004`
- Launcher URL: `http://localhost:9210`
- Is Green?: ❌ No
- Alias: `tau_white_agent`

**MCP Green Agent (Evaluator):**

- Agent URL: `http://localhost:9006`
- Launcher URL: `http://localhost:9111`
- Is Green?: ✅ Yes
- Alias: `tau_green_agent_mcp`

### Step 4: Create Battle

In AgentBeats UI:

1. Click "Create Battle"
2. Select `tau_green_agent_mcp` (green agent/evaluator)
3. Select `tau_white_agent` (white agent/target)
4. Click "Start Battle"!

---

**Workarounds Implemented**:

1. Fresh httpx client for each message (keepalive disabled)
2. Agent card cache clearing between attempts
3. 2-second delay between attempts
4. All imports moved to function top (no import deadlocks)
5. Reduced connection pool limits

**Future Work**: This likely requires fixes in the A2A SDK itself or deeper async event loop debugging.

### HTTP Connection Limits

**Configuration**: httpx client settings optimized for stability:

```python
limits = httpx.Limits(
    max_keepalive_connections=0,   # Disabled for stability
    max_connections=5,              # Low limit to prevent exhaustion
    keepalive_expiry=1.0
)
```

---

## Reproducing Tau-Bench Results

This section explains how to reproduce results from the original tau-bench benchmark paper.

### Understanding Tau-Bench Metrics

The original tau-bench evaluates agents on:

- **Retail domain**: 50 customer service tasks
- **Airline domain**: 50 travel booking tasks
- **Metrics**: Success rate (reward = 1.0 means task completed correctly)

### Running Standard Tau-Bench Evaluation

**Single Task Evaluation:**

```bash
# Configure in tau_green_agent_mcp.toml
[pass_k_config]
mode = "manual"
domain = "retail"    # or "airline"
task_id = 5         # Task index (0-49)
k = 1               # Single attempt

# Start agents and run battle in AgentBeats UI
./scripts/start_mcp.sh
```

**Full Domain Evaluation:**

To evaluate across all 50 tasks in a domain:

```bash
# Option 1: Run 50 manual evaluations
# Change task_id from 0 to 49 in tau_green_agent_mcp.toml
# Run a battle for each task

# Option 2: Use random mode with high num_battles
[pass_k_config]
mode = "random"
num_battles = 50
k = 1
```

### Pass@k Evaluation (Extended Metric)

Our implementation adds pass@k evaluation beyond the original benchmark:

```toml
[pass_k_config]
mode = "manual"
domain = "retail"
task_id = 5
k = 4               # Run same task 4 times
```

**Metrics produced:**

- `pass@k`: All k attempts succeed
- `pass@(k/2)`: Any consecutive k/2 attempts succeed
- `success_rate`: Percentage of successful attempts

### Comparing to Original Benchmark

The original tau-bench paper reports:

- GPT-4: ~70-80% success rate on retail/airline
- GPT-3.5: ~40-50% success rate

To compare your agent:

1. Run evaluation on same tasks
2. Use single attempt (k=1) for fair comparison
3. Calculate success rate: `(successful_tasks / total_tasks) × 100%`
4. Compare against published baselines

### Test Cases for Verification

**Quick Sanity Check (3 tasks):**

```bash
# Edit tau_green_agent_mcp.toml
mode = "manual"
k = 1

# Test on: retail task 1, retail task 10, airline task 1
# Expected: Reasonable agent should get ~2/3 correct
```

**Standard Test Suite (10 tasks):**

```bash
mode = "random"
num_battles = 10
k = 1

# Run battle in AgentBeats
# Check success rate in results
```

### Example Results Interpretation

```
Results: 4/5 tests passed
✓ PASS     Tool Registration
✓ PASS     List Tau-Bench Tools
✓ PASS     Setup Environment        # ← This validates tau-bench integration
✓ PASS     Parse XML Tags
✗ FAIL     Format Evaluation Result
```

If "Setup Environment" passes, tau-bench is properly configured.

---

## Troubleshooting

### Connection Refused

**Symptom**: Cannot connect to agent/launcher

**Solutions**:

```bash
# Restart everything
./scripts/start_mcp.sh

# Check if services are running
curl http://localhost:9111/health
curl http://localhost:9210/health
```

### Evaluation Hangs

**Symptoms**:

- Green agent log stops updating
- White agent completes requests but no progress
- Stuck at "Sending to white agent"

**Solutions**:

```bash
# 1. Reduce k value in tau_green_agent_mcp.toml
k = 2  # Down from 3 or 4

# 2. Restart agents
./scripts/start_mcp.sh

# 3. Check logs for errors
tail -f implementations/mcp/green_agent.log
```

### Module Not Found

**Symptom**: `ModuleNotFoundError: agentbeats`

**Solutions**:

```bash
# Use uv run
uv run python scripts/test_mcp_tools.py

# Or activate environment
source .venv/bin/activate
python test_mcp_tools.py
```

### Ports Already in Use

**Solution**:

```bash
# The start_mcp.sh script handles this automatically
./scripts/start_mcp.sh

# Manual cleanup if needed:
pkill -f 'python.*launcher'

for port in 9006 9004 9111 9210; do
  lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null
done
```

### Complete System Restart

If you need to restart everything (AgentBeats + agents):

```bash
./restart_all.sh
```

This will restart the entire stack including AgentBeats backend and frontend.

---

## Testing

### Run Test Suite

```bash
uv run python scripts/test_mcp_tools.py
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

### Check System Status

```bash
./scripts/check_status.sh
```

This will verify that all launchers and agents are running properly.

### View Logs

```bash
# Green agent logs
tail -f implementations/mcp/green_agent.log

# White agent logs
tail -f white_agent.log

# Launcher logs (if running in foreground)
# Check terminal output
```

---

## File Structure

```
tau-bench-agents/
├── implementations/
│   ├── mcp/                              # MCP implementation (main)
│   │   ├── shared_config.py              # LLM provider configuration
│   │   ├── green_agent/
│   │   │   ├── agent.py                  # Green agent server
│   │   │   ├── tools.py                  # Evaluation tools
│   │   │   └── tau_green_agent_mcp.toml  # Pass@k configuration
│   │   └── white_agent/
│   │       ├── agent.py                  # White agent server
│   │       └── tau_white_agent.toml      # White agent config
│   └── a2a/                              # A2A implementation (alternative)
│       ├── green_agent/
│       └── white_agent/
├── launchers/
│   ├── green_launcher_mcp.py             # Green launcher (port 9111)
│   └── white_launcher.py                 # White launcher (port 9210)
├── scripts/
│   ├── start_mcp.sh                      # Start MCP agents
│   ├── start_a2a.sh                      # Start A2A agents
│   ├── check_status.sh                   # Verify system status
│   └── use_openrouter.sh                 # Switch to OpenRouter
├── main.py                               # CLI entry point
├── test_mcp_tools.py                     # Test suite
├── restart_all.sh                        # Complete system restart
└── README.md                             # This file
```

Explicit client closure in finally blocks

---

## Quick Reference

### Start Commands

```bash
# Start MCP agents
./scripts/start_mcp.sh

# Start A2A agents (alternative)
./scripts/start_a2a.sh

# Check status
./scripts/check_status.sh

# Verify launchers
curl http://localhost:9111/health  # MCP green
curl http://localhost:9210/health  # White
```

### Configuration Files

```bash
# Provider configuration
implementations/mcp/shared_config.py

# Pass@k settings
implementations/mcp/green_agent/tau_green_agent_mcp.toml
```

### Log Files

```bash
# Green agent
implementations/mcp/green_agent.log

# White agent
white_agent.log
```

### Recommended Settings

```toml
[pass_k_config]
mode = "manual"
k = 2                    # Use 2 for stability
domain = "retail"
task_id = 1
```

### Agent URLs for AgentBeats

| Component                    | Port | URL                   |
| ---------------------------- | ---- | --------------------- |
| **MCP Green Agent**    | 9006 | http://localhost:9006 |
| **MCP Green Launcher** | 9111 | http://localhost:9111 |
| **White Agent**        | 9004 | http://localhost:9004 |
| **White Launcher**     | 9210 | http://localhost:9210 |

---

**Ready to start?** Run `./scripts/start_mcp.sh` and create a battle in AgentBeats!

For issues or questions, check the logs or refer to the troubleshooting section above.

## **Main Files:**

- `/implementations/mcp/green_agent/` - Green agent (evaluator)
- `/implementations/mcp/white_agent/` - White agent (target)
- `/test_mcp_tools.py` - Test suite
- `/scripts/start_mcp.sh` - Complete startup script
