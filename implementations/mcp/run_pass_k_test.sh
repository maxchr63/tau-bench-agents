#!/bin/bash
# Start agents for pass@k testing

set -e

echo "=================================================="
echo "🚀 Tau-Bench Pass@k Evaluation - Quick Start"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "scenario_pass_k.toml" ]; then
    echo -e "${RED}Error: scenario_pass_k.toml not found${NC}"
    echo "Please run this script from tau-bench-agents/implementations/mcp/"
    exit 1
fi

echo -e "${YELLOW}Step 1: Checking AgentBeats backend...${NC}"
if ! curl -s http://localhost:9000/health > /dev/null 2>&1; then
    echo -e "${RED}❌ AgentBeats backend not running on port 9000${NC}"
    echo ""
    echo "Please start AgentBeats backend first:"
    echo "  cd agentbeats"
    echo "  uv run python -m src.backend.main"
    echo ""
    exit 1
else
    echo -e "${GREEN}✅ AgentBeats backend is running${NC}"
fi

echo ""
echo -e "${YELLOW}Step 2: Current pass@k configuration:${NC}"
echo ""
cat green_agent/tau_green_agent_mcp.toml | grep -A 5 "\[pass_k_config\]"
echo ""

read -p "Do you want to change the configuration? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Edit green_agent/tau_green_agent_mcp.toml to change:${NC}"
    echo "  - mode: 'manual' or 'random'"
    echo "  - k: number of attempts per task"
    echo "  - domain: 'retail' or 'airline' (for manual mode)"
    echo "  - task_id: which task to test (for manual mode)"
    echo "  - num_battles: how many random tasks (for random mode)"
    echo ""
    read -p "Press Enter when ready to continue..."
fi

echo ""
echo -e "${YELLOW}Step 3: Killing any existing agents on ports 9006, 9111, 9210, 9211...${NC}"
lsof -ti:9006 | xargs kill -9 2>/dev/null || true
lsof -ti:9111 | xargs kill -9 2>/dev/null || true
lsof -ti:9210 | xargs kill -9 2>/dev/null || true
lsof -ti:9211 | xargs kill -9 2>/dev/null || true
sleep 1
echo -e "${GREEN}✅ Ports cleared${NC}"

echo ""
echo -e "${YELLOW}Step 4: Starting agents...${NC}"
echo ""

# Start launchers using existing script
cd ../../
./scripts/start_mcp.sh &

echo ""
echo -e "${GREEN}✅ Agents started${NC}"
echo ""

echo -e "${YELLOW}Step 5: Waiting for agents to register...${NC}"
sleep 5

# Check if agents are registered
GREEN_REGISTERED=$(curl -s http://localhost:9000/agents | grep -c "tau_green_agent_mcp" || echo "0")
WHITE_REGISTERED=$(curl -s http://localhost:9000/agents | grep -c "tau_white_agent" || echo "0")

if [ "$GREEN_REGISTERED" -eq "0" ]; then
    echo -e "${RED}❌ Green agent not registered${NC}"
    echo "Check launcher output above for errors"
    exit 1
fi

if [ "$WHITE_REGISTERED" -eq "0" ]; then
    echo -e "${RED}❌ White agent not registered${NC}"
    echo "Check launcher output above for errors"
    exit 1
fi

echo -e "${GREEN}✅ Both agents registered with AgentBeats${NC}"
echo ""

echo "=================================================="
echo "🎉 Setup Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Open AgentBeats UI:"
echo "   http://localhost:3000"
echo ""
echo "2. Create a battle:"
echo "   - Green Agent: Tau Green Agent (MCP)"
echo "   - White Agent: Tau White Agent (MCP)"
echo "   - Click 'Start Battle'"
echo ""
echo "3. Watch the pass@k evaluation live in the battle view!"
echo ""
echo "To stop the agents:"
echo "  pkill -f 'python.*launcher'"
echo ""
