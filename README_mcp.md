# Tau-Bench Agents - MCP Implementation Guide

An MCP-ready implementation of τ-bench integration for AgentBeats, featuring modular architecture and modern SDK utilities.

---

## 🚀 Quick Start

```bash
# Install dependencies
uv sync

# Start agents
./scripts/start_mcp.sh

# Test
uv run python test_refactored_tools.py
```

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Installation](#installation)
- [Configuration](#configuration)
- [Pass@k Evaluation](#passk-evaluation)
- [Testing on AgentBeats](#testing-on-agentbeats)
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

| Component              | Port | URL                   | Purpose                |
| ---------------------- | ---- | --------------------- | ---------------------- |
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
cd /path/to/tau-bench-agents

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
# OpenRouter (recommended for avoiding rate limits)
OPENROUTER_API_KEY=your_key_here

# Or use Anthropic directly
ANTHROPIC_API_KEY=your_key_here
```

---

## Configuration

### Provider Configuration

Edit `implementations/mcp/shared_config.py` to select your LLM provider:

```python
# Choose your provider
USE_PROVIDER = "openrouter"  # or "anthropic"

# Models
TAU_USER_MODEL = "anthropic/claude-haiku-4.5"  # For tau-bench user simulation
TAU_USER_PROVIDER = "openrouter"
```

### Pass@k Configuration

Edit `implementations/mcp/green_agent/tau_green_agent_mcp.toml`:

```toml
[pass_k_config]
mode = "manual"           # "manual" or "automatic"
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

#### Mode: manual vs automatic

```toml
# Manual mode: Specify exact domain and task_id
mode = "manual"
domain = "retail"
task_id = 1

# Automatic mode: Run all tasks in domain
mode = "automatic"
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

This will:
- Clean up old processes on ports 9006, 9004, 9111, 9210
- Start MCP green launcher on port 9111
- Start white launcher on port 9210
- Launch both agents automatically

### Step 2: Verify Status

```bash
# Check launcher health
curl http://localhost:9111/health  # MCP green launcher
curl http://localhost:9210/health  # White launcher

# Check agent cards
curl http://localhost:9006/.well-known/agent-card.json
curl http://localhost:9004/.well-known/agent-card.json
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

### Import Deadlocks (Fixed ✅)

**Issue**: Imports inside async loops could cause deadlocks

**Fix**: All imports moved to function/file top:
```python
# ✅ Good - imports at top
from a2a.utils import get_text_parts

async def evaluate():
    # Use imported function
    text_parts = get_text_parts(parts)

# ❌ Bad - import inside loop
async def evaluate():
    for step in range(max_steps):
        from a2a.utils import get_text_parts  # Deadlock risk!
```

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
uv run python test_refactored_tools.py

# Or activate environment
source .venv/bin/activate
python test_refactored_tools.py
```

### Ports Already in Use

**Solution**:
```bash
# The start_mcp.sh script handles this automatically
./scripts/start_mcp.sh

# Or if you need to kill the agents manually :
for port in 9006 9004 9111 9210; do
  lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null
done
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
│   └── mcp/
│       ├── shared_config.py              # LLM provider configuration
│       ├── green_agent/
│       │   ├── agent.py                  # Green agent server
│       │   ├── tools.py                  # Evaluation tools (cleaned up)
│       │   └── tau_green_agent_mcp.toml  # Pass@k configuration
│       └── white_agent/
│           ├── agent.py                  # White agent server
│           └── tau_white_agent.toml      # White agent config
├── launchers/
│   ├── green_launcher_mcp.py             # Green launcher (port 9111)
│   └── white_launcher.py                 # White launcher (port 9210)
├── scripts/
│   └── start_mcp.sh                      # Start all services
└── README_MCP.md                         # This file
```

---

## Recent Changes

### Code Cleanup (Latest)

**What Changed**:
- ✅ Removed excessive debug logging
- ✅ Simplified error messages
- ✅ Fixed all Python linting warnings
- ✅ Cleaned up import statements
- ✅ Reduced verbosity while maintaining critical logs

**Performance Improvements**:
- httpx keepalive fully disabled (was partially disabled)
- Longer delay between attempts (2s, was 0.5s)
- Agent card cache cleared between attempts
- Connection limits reduced (max 5, was 10)

### Bug Fixes

**Import Deadlock Fix**:
- Moved all imports to function top
- Prevents Python's import lock from blocking async operations
- Fixes non-deterministic hangs

**Connection Stability**:
- Fresh httpx client for every message
- No connection reuse (keepalive=0)
- Explicit client closure in finally blocks

---

## Quick Reference

### Start Commands
```bash
# Start everything
./scripts/start_mcp.sh
# Check status
./check_status.sh

# ór
curl http://localhost:9111/health
curl http://localhost:9210/health
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

---

**Ready to start?** Run `./scripts/start_mcp.sh` and create a battle in AgentBeats! 🚀

For issues or questions, check the logs or refer to the troubleshooting section above.
