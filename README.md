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


## 3. Architecture Overview

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