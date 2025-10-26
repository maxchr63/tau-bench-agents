# Pass@k Evaluation Guide

This document explains how to use the pass@k evaluation feature for tau-bench agents.

## Overview

Pass@k evaluation tests agent reliability by running k independent attempts on the same task. This implementation provides:

- **pass^k**: All first k attempts must succeed consecutively (strict metric)
- **pass^(k/2)**: Any window of k/2 consecutive successes (reliability indicator)
- **Success Rate**: Overall percentage of successful attempts

## Configuration

Configure pass@k evaluation in `green_agent/tau_green_agent_mcp.toml`:

```toml
[pass_k_config]
mode = "manual"           # "manual" or "random"
k = 4                     # Number of attempts per task (must be even)
domain = "retail"         # For manual mode: "retail" or "airline"
task_id = 5               # For manual mode: specific task to test (0-based index)
num_battles = 5           # For random mode: how many different random tasks to test
```

## Evaluation Modes

### Manual Mode

Tests a specific task repeatedly:

```toml
[pass_k_config]
mode = "manual"
k = 4
domain = "retail"
task_id = 5
```

This will:
1. Run 4 independent attempts on retail task 5
2. Each attempt uses a fresh conversation context (context_id=None)
3. Report detailed results for all 4 attempts

### Random Mode

Tests multiple random tasks:

```toml
[pass_k_config]
mode = "random"
k = 4
num_battles = 5
```

This will:
1. Randomly select 5 tasks (from retail or airline domains)
2. Run 4 attempts on each of the 5 tasks
3. Report aggregate statistics across all tasks

## Running an Evaluation

### 1. Start White Agent

```bash
cd tau-bench-agents
python -m implementations.mcp.white_agent.agent
# Should start on port 9210
```

### 2. Start Green Agent (MCP)

```bash
python -m implementations.mcp.green_agent.agent
# Should start on port 9111 (launcher) and 9006 (agent)
```

### 3. Create a Battle in AgentBeats

Via AgentBeats UI or API:

```bash
curl -X POST http://localhost:9000/battles \
  -H "Content-Type: application/json" \
  -d '{
    "green_agent_id": "tau_green_agent_mcp_id",
    "opponents": [
      {"name": "white_agent", "agent_id": "white_agent_id"}
    ]
  }'
```

### 4. Monitor Results

The evaluation will show:

**Live Progress** (in AgentBeats UI battle history):
```
🎯 Starting pass@4 evaluation
🔄 Starting attempt 1/4...
✅ Attempt 1/4: SUCCESS (reward=1.0, steps=12, time=34.2s)
🔄 Starting attempt 2/4...
❌ Attempt 2/4: FAILED (reward=0.0, steps=8, time=15.3s)
...
```

**Final Summary** (after all attempts):
```
📊 Pass@k Evaluation Results

Domain: retail | Task: 5

## Attempts (4 total)
✅❌✅✅

## Metrics
- pass^4: ❌ FAIL (all first 4 attempts must succeed)
- pass^2: ✅ PASS (any 2 consecutive successes)
- Success Rate: 75% (3/4 successful)
- Avg Steps on Success: 11.3
- Total Steps: 42

## Failure Breakdown
- missing_outputs: 1 occurrence(s)

## Attempt Details
✅ Attempt 1: Success (steps=12, time=34.2s)
❌ Attempt 2: Failed (steps=8, time=15.3s)
   ↳ Error: Missing <json> tags in response
✅ Attempt 3: Success (steps=10, time=28.7s)
✅ Attempt 4: Success (steps=12, time=31.5s)
```

## Understanding the Metrics

### pass^k (Strict Consecutive)

**Definition**: All of the first k attempts must succeed.

**Use case**: Measures if agent can reliably solve task from cold start.

**Example** (k=4):
- ✅✅✅✅ → pass^4 = True
- ❌✅✅✅ → pass^4 = False (first attempt failed)
- ✅❌✅✅ → pass^4 = False (second attempt failed)

### pass^(k/2) (Any Consecutive Window)

**Definition**: Agent must have k/2 consecutive successes anywhere in the k attempts.

**Use case**: Measures if agent can achieve consistency at some point.

**Example** (k=4, so k/2=2):
- ❌✅✅❌ → pass^2 = True (found ✅✅ at indices 1-2)
- ✅❌❌✅ → pass^2 = False (no 2 consecutive successes)
- ❌❌✅✅ → pass^2 = True (found ✅✅ at indices 2-3)

### Success Rate

**Definition**: Percentage of attempts that succeeded (regardless of order).

**Use case**: Overall measure of agent capability.

**Example** (k=4):
- ✅❌✅✅ → 75% (3 out of 4)
- ✅✅❌❌ → 50% (2 out of 4)

## Failure Categories

The system automatically categorizes failures:

- **format_error**: Invalid JSON or missing tags
- **missing_outputs**: Task completed but missing required information
- **incomplete_outputs**: Task partially completed
- **timeout**: Exceeded max steps
- **communication_error**: Connection issues with white agent
- **white_agent_error**: White agent returned an error
- **task_incomplete**: Task not finished
- **unknown_failure**: Other failure reasons

## Fresh Context Guarantee

Each attempt uses `context_id=None`, which ensures:

1. ✅ White agent creates a NEW conversation thread
2. ✅ No memory from previous attempts
3. ✅ Tau-bench environment resets (`env.reset()`)
4. ✅ True independence between attempts

### Security Note

The white agent implementation was updated to prevent memory leakage:
- Memory cleared on reset: `self.ctx_id_to_messages = {}`
- Bounded memory growth: Max 100 contexts kept
- Each context isolated: No cross-contamination

## Example Workflows

### Testing Agent Consistency

```toml
# Test if agent can consistently solve a known task
[pass_k_config]
mode = "manual"
k = 10
domain = "retail"
task_id = 5  # A task you know the agent should solve
```

Expected result: High pass^10 and pass^5 indicates good consistency.

### Comprehensive Evaluation

```toml
# Test agent across random tasks
[pass_k_config]
mode = "random"
k = 4
num_battles = 20  # Test 20 different tasks
```

Expected result: Overall success rate shows general capability across domains.

### Quick Reliability Check

```toml
# Fast check with k=4
[pass_k_config]
mode = "manual"
k = 4
domain = "retail"
task_id = 5
```

Expected result: In ~2 minutes, get pass^4, pass^2, and success rate.

## Troubleshooting

### No results showing in AgentBeats UI

**Check**:
1. Green agent has battle_id and backend_url
2. AgentBeats backend is running on port 9000
3. Battle was created successfully

### White agent returns same response every time

**Possible causes**:
1. Temperature set to 0.0 (deterministic)
2. White agent caching responses (check implementation)
3. Context ID not being refreshed

**Verify**: Check logs for "New conversation started with context_id: ..."

### Evaluation hangs or times out

**Possible causes**:
1. White agent not responding (check port 9210)
2. Tau-bench user simulation failing (OpenAI API issues)
3. Max steps too high

**Solution**: Check white agent logs and reduce max_num_steps.

## Performance Considerations

### API Costs

Each attempt makes LLM API calls:
- White agent: GPT-4o-mini (default)
- Tau-bench user: GPT-4o-mini (simulates user responses)

**Estimated costs** (k=4, 1 task):
- ~40-80 API calls total
- ~$0.01-0.02 per evaluation

### Execution Time

**Manual mode** (k=4, 1 task): ~2-5 minutes
**Random mode** (k=4, 20 tasks): ~40-100 minutes

Time varies based on:
- Task complexity
- White agent response time
- Number of steps per attempt

## Next Steps

1. **Implement Option 2**: Wrap pass@k in AgentBeats battle orchestration script for automated multi-task evaluation
2. **Add confidence intervals**: Statistical significance for pass@k metrics
3. **Export to CSV**: Save results for spreadsheet analysis
4. **Compare models**: Run same evaluation on different white agent models
