# Tau-Bench for Agent Beats

Example code for agentifying Tau-Bench using A2A and MCP standards.

## Start AgentBeats

[](https://github.com/paulburkhardt/Rede_Labs/blob/initial-setup/README.md#2-start-agentbeats)

Open a new terminal and execute the following commands:

```shell
# Navigate to AgentBeats directory (could be different)
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

## Project Structure

```
src/
├── green_agent/    # Assessment manager agent
├── white_agent/    # Target agent being tested
└── launcher.py     # Evaluation coordinator
```

## Installation

```bash
uv sync
```

## Usage

First, configure `.env` with 
`ANTHROPIC_API_KEY=` or  (currently setup for anthropic keys)
`OPENAI_API_KEY=...`, then

```bash
# Launch complete evaluation
uv run python main.py launch
```
