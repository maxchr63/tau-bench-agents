# QUICK START - Register Your Agents in AgentBeats

## TL;DR - What You Need To Do

1. **Start launchers** (in 2 separate terminal windows)
2. **Open AgentBeats UI** and register agents with the URLs below
3. **Launch agents** via UI or API
4. **Create battle** and run!

---

## Step-by-Step Instructions

### 1️⃣ Start the Launchers

**IMPORTANT**: Keep these terminal windows open! Don't close them.

#### Terminal Window 1 - Green Launcher

```bash
cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents
uv run python src/green_launcher.py
```

You'll see: `INFO: Uvicorn running on http://0.0.0.0:9110`

#### Terminal Window 2 - White Launcher

```bash
cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents
uv run python src/white_launcher.py
```

You'll see: `INFO: Uvicorn running on http://0.0.0.0:9210`

### 2️⃣ Verify Everything Is Working

In a **third terminal window**:

```bash
cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents
./check_status.sh
```

You should see:

```
✅ Green launcher is running
✅ White launcher is running
```

### 3️⃣ Register Agents in AgentBeats UI

Open your browser to **http://localhost:5173** (or wherever AgentBeats UI is running)

#### Register White Agent (the agent being tested)

- **Agent URL**: `http://localhost:9004`
- **Launcher URL**: `http://localhost:9210`
- **Is Green?**: ❌ **UNCHECKED**
- **Alias**: `tau_white_agent` (or any name)

#### Register Green Agent (the evaluator)

- **Agent URL**: `http://localhost:9003`
- **Launcher URL**: `http://localhost:9110`
- **Is Green?**: ✅ **CHECKED**
- **Alias**: `tau_green_agent` (or any name)
- **Participant Requirements**: May need to specify it needs a white agent (UI might auto-detect this)

### 4️⃣ Launch the Agents

**Option A**: If AgentBeats UI has a "Launch" button, click it for each agent

**Option B**: Use curl commands:

```bash
# Launch white agent
curl -X POST http://localhost:9210/launch

# Launch green agent  
curl -X POST http://localhost:9110/launch
```

Wait a few seconds, then verify agents are running:

```bash
curl http://localhost:9003/.well-known/agent-card.json
curl http://localhost:9004/.well-known/agent-card.json
```

### 5️⃣ Create and Run Your Battle!

In AgentBeats UI:

1. Click "Create Battle" (or similar)
2. Select `tau_green_agent` as the evaluator
3. Select `tau_white_agent` as the target
4. Configure tau-bench parameters if needed
5. Click "Start"!

---

 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AgentBeats System                        │
│                                                                 │
│  ┌─────────────────┐              ┌──────────────────┐         │
│  │  Frontend (UI)  │◄────────────►│  Backend (API)   │         │
│  │  Port: 5173     │              │  Port: 9000      │         │
│  └─────────────────┘              └──────────────────┘         │
│         │                                   │                   │
│         │                x                   │                   │
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

## Data Flow During Registration

1. **User registers white agent in UI**:
   ```
   UI Form:
   - Agent URL: http://localhost:9002
   - Launcher URL: http://localhost:9210
   - Is Green?: NO
   ```

2. **AgentBeats backend validates**:
   - ✅ Checks `http://localhost:9210/status` → expects `"server up, with agent running"` OR `"stopped"`
   - ✅ Checks `http://localhost:9002/.well-known/agent-card.json` → gets agent card

3. **If validation passes** → 🟢 Green dot in UI

4. **If validation fails** → 🔴 Red dot in UI

## Data Flow During Battle Launch

1. **User clicks "Start Battle"** in UI

2. **Backend calls launchers**:
   ```bash
   POST http://localhost:9210/launch  # Launch white agent
   POST http://localhost:9110/launch  # Launch green agent
   ```

3. **Launchers spawn agent processes**:
   ```bash
   Green launcher → spawns: uv run python main.py green
   White launcher → spawns: uv run python main.py white
   ```

4. **Agents start on ports 9001 and 9002**

5. **Green agent evaluates white agent**:
   - Green agent sends tau-bench test tasks to white agent
   - White agent responds
   - Green agent scores the responses

6. **Results sent back to AgentBeats**

## Main Files

```
tau-bench-agents/
├── main.py                      # Entry point: handles "green", "white", "launch" commands
├── .env                         # API keys (ANTHROPIC_API_KEY)
│
├── src/
│   ├── green_launcher.py       # FastAPI server on port 9110 

│   ├── white_launcher.py       # FastAPI server on port 9210 
│   ├── terminal_launcher.py    # CLI evaluation launcher
│   │
│   ├── green_agent/
│   │   ├── agent.py           # Green agent implementation
│   │   └── tau_green_agent.toml   # Agent card (A2A standard)
│   │
│   └── white_agent/
│       ├── agent.py           # White agent implementation  
│       └── tau_white_agent.toml   # Agent card (A2A standard)
│
├── QUICKSTART.md              # Start here! ⭐
├── check_status.sh            # Quick health check script
```


## 🔴 Troubleshooting Red Dots in Agentbeatrs

If you see red dots in the UI after registration:

### Check #1: Are launchers running?

```bash
./check_status.sh
```

If not running, start them (see Step 1)

### Check #2: Test the endpoints manually

```bash
# Should return healthy status
curl http://localhost:9110/health
curl http://localhost:9210/health

# Should return stopped or running status
curl http://localhost:9110/status
curl http://localhost:9210/status
```

### Check #3: Check AgentBeats backend

- Make sure AgentBeats backend is running on port 9000
- Check backend logs for errors
- Try re-registering the agents

### Check #4: Network/CORS issues

- Make sure you're using `http://localhost` not `http://127.0.0.1`
- Make sure no firewalls are blocking the ports

---

## 📋 URLs Reference Card

| What                     | URL                   |
| ------------------------ | --------------------- |
| **White Agent**    | http://localhost:9004 |
| **White Launcher** | http://localhost:9210 |
| **Green Agent**    | http://localhost:9003 |
| **Green Launcher** | http://localhost:9110 |
| **AgentBeats UI**  | http://localhost:5173 |
| **AgentBeats API** | http://localhost:9000 |
| **AgentBeats MCP** | http://localhost:9001 |

---

## 🐛 What Was Wrong and Fixed

1. **Port conflict with AgentBeats MCP**:

   - Green agent was on port 9001, conflicting with AgentBeats MCP server ❌
   - Moved to port 9003 (green) and 9004 (white) ✅
2. **Critical bug in green_launcher.py**:

   - Line 63 was launching "white" agent instead of "green" ❌
   - Now correctly launches "green" agent ✅
3. **Wrong status response**:

   - Launchers returned `"status": "running"` ❌
   - AgentBeats expects `"status": "server up, with agent running"` ✅
   - Both launchers now return the correct format ✅

---

## 💡 Pro Tips

- Keep the launcher terminal windows open and visible so you can see logs
- Use `./check_status.sh` to quickly verify everything is running
- If something breaks, kill everything and restart:
  ```bash
  pkill -f 'python.*launcher'
  pkill -f 'python main.py'
  # Then start launchers again
  ```

---

## ✅ You're Ready!

Everything is fixed and ready to go. Just follow the 5 steps above and you should see **green dots** 🟢 in the AgentBeats UI!

**Need help?** Run `./check_status.sh` to see what's running and what's not.
