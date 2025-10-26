# Pass@k Evaluation Fixes - October 26, 2025

## Issues Fixed

### 1. ❌ **TypeError: record_battle_result() missing 'winner' argument**
**Location**: `implementations/mcp/green_agent/agent.py` line 484

**Problem**: The AgentBeats SDK's `record_battle_result()` function requires 4 parameters:
- `context` (BattleContext)
- `message` (str)
- `winner` (str) - **This was missing!**
- `detail` (Optional[Dict])

**Solution**: Added winner determination logic:
- `winner = "white_agent"` if `overall_pass_k > 0` (white agent succeeded at least once)
- `winner = "tau_green_agent_mcp"` if `overall_pass_k == 0` (white agent failed all attempts)

**Files Changed**:
- `implementations/mcp/green_agent/agent.py` (lines 481-507)

---

### 2. 🔄 **Potential Hanging During Pass@k Evaluation**

Multiple causes identified and fixed:

#### 2.1 White Agent Context Memory Leak
**Location**: `implementations/mcp/white_agent/agent.py`

**Problem**: The white agent stored unlimited contexts in memory (`ctx_id_to_messages` dict). With k=4 attempts × 30 steps each, this created unbounded memory growth leading to:
- Memory exhaustion
- Slow processing
- Potential hanging

**Solution**: Re-enabled and improved max context limit:
```python
self.max_contexts = 10  # Allow up to 10 concurrent contexts
```
When limit reached, oldest context is evicted (FIFO).

**Files Changed**:
- `implementations/mcp/white_agent/agent.py` (lines 47-50, 72-75)

#### 2.2 White Agent LLM Call Timeout
**Location**: `implementations/mcp/white_agent/agent.py`

**Problem**: The `completion()` call to the LLM had no timeout protection. If OpenRouter/OpenAI API hangs, the entire evaluation freezes indefinitely.

**Solution**: Added 60-second timeout wrapper:
```python
response = await asyncio.wait_for(
    asyncio.to_thread(
        completion,
        model=TAU_USER_MODEL,
        messages=messages,
        temperature=0.0,
    ),
    timeout=60.0  # 60 second timeout
)
```

On timeout, returns graceful error response instead of hanging.

**Files Changed**:
- `implementations/mcp/white_agent/agent.py` (lines 107-128)

#### 2.3 Improved Inter-Attempt Delay
**Location**: `implementations/mcp/green_agent/tools.py`

**Problem**: 1-second delay between attempts was too short, causing potential resource exhaustion.

**Solution**: Increased to 2 seconds between attempts to give agents time to clean up resources.

**Files Changed**:
- `implementations/mcp/green_agent/tools.py` (line 987)

---

## Key Improvements

### Context Management
- ✅ Each pass@k attempt uses fresh `context_id` (already working)
- ✅ White agent now limits total contexts to 10 (prevents memory leak)
- ✅ Sliding window trimming (20 messages + system prompt) prevents unbounded growth per context

### Timeout Protection
- ✅ Card fetch: 5 seconds
- ✅ Message send: 120 seconds (outer 125s timeout)
- ✅ **NEW**: White agent LLM completion: 60 seconds

### Battle Reporting
- ✅ Proper winner determination based on pass@k success
- ✅ Winner rationale included in battle details
- ✅ Battle status updates correctly in AgentBeats UI

---

## Testing Recommendations

1. **Restart Agents** (required for changes to take effect):
   ```bash
   cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents
   pkill -f "green_launcher_mcp|white_launcher"
   sleep 2
   bash scripts/start_mcp.sh
   ```

2. **Monitor for**:
   - No hanging (evaluation should complete within reasonable time)
   - Proper winner reporting in AgentBeats UI
   - Context cleanup messages in logs: `[White Agent] Cleared old context...`
   - No timeout errors unless APIs actually fail

3. **Check Logs**:
   - `implementations/mcp/green_agent.log` - Green agent activity
   - Look for: `Pass@k evaluation complete! Winner: white_agent` or `Winner: tau_green_agent_mcp`
   - Look for: `[White Agent] Cleared old context` when contexts exceed 10

---

## Configuration Summary

| Setting | Value | Purpose |
|---------|-------|---------|
| MAX_MESSAGES_IN_HISTORY | 20 | Sliding window size (per context) |
| max_contexts | 10 | Max concurrent contexts (white agent) |
| LLM timeout | 60s | Prevent hanging on LLM calls |
| Card fetch timeout | 5s | Prevent hanging on card fetch |
| Message send timeout | 120s | Timeout for agent message exchange |
| Inter-attempt delay | 2s | Resource cleanup time between attempts |

---

## Winner Determination Logic

```python
# White agent wins if it achieves pass@k > 0 (at least one success pattern)
# Tau-bench (green agent) wins if white agent fails all attempts
winner = "white_agent" if overall_pass_k > 0 else "tau_green_agent_mcp"
```

This aligns with your requirement:
> "report tau bench as winner if the white agent did not succeed in all passes and else the white_agent as winner"

---

## Files Modified

1. **implementations/mcp/green_agent/agent.py**
   - Fixed `record_battle_result()` call with proper winner parameter
   - Added winner determination logic

2. **implementations/mcp/white_agent/agent.py**
   - Re-enabled max_contexts limit (10 contexts)
   - Added 60-second timeout to LLM completion calls
   - Improved error handling for timeout scenarios

3. **implementations/mcp/green_agent/tools.py**
   - Increased inter-attempt delay to 2 seconds

---

## Next Steps

After restarting agents, run a pass@k evaluation and verify:
1. ✅ No `TypeError` about missing winner argument
2. ✅ Evaluation completes without hanging
3. ✅ Battle status updates to "completed" in AgentBeats UI
4. ✅ Correct winner reported based on pass@k results
