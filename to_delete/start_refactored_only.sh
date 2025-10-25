#!/bin/bash
# Start ONLY the refactored agents for AgentBeats testing

cd "$(dirname "$0")"

echo "🔄 Cleaning up old processes..."
pkill -f 'python.*launcher' 2>/dev/null
for port in 9003 9004 9006 9110 9111 9210; do 
    lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null
done
sleep 2

echo ""
echo "=========================================================================="
echo "  REFACTORED AGENTS LAUNCHER"
echo "=========================================================================="
echo ""

# Start refactored green launcher
echo "🔧 Starting REFACTORED Green Agent Launcher on port 9111..."
uv run python src/green_launcher_refactored.py &
GREEN_PID=$!
echo "   ✓ Refactored green launcher started with PID: $GREEN_PID"
echo ""

sleep 2

# Start white launcher (same for both)
echo "📦 Starting White Agent Launcher on port 9210..."
uv run python src/white_launcher.py &
WHITE_PID=$!
echo "   ✓ White launcher started with PID: $WHITE_PID"
echo ""

echo "=========================================================================="
echo "  LAUNCHERS RUNNING!"
echo "=========================================================================="
echo ""
echo "  • Green launcher (refactored): http://localhost:9111"
echo "  • White launcher: http://localhost:9210"
echo ""

# Wait for servers to be ready
sleep 3

# Launch the agents
echo "=========================================================================="
echo "  LAUNCHING AGENTS"
echo "=========================================================================="
echo ""

echo "🚀 Launching REFACTORED Green Agent..."
curl -X POST http://localhost:9111/launch
echo ""
echo ""

echo "🚀 Launching White Agent..."
curl -X POST http://localhost:9210/launch
echo ""
echo ""

echo "=========================================================================="
echo "  AGENTS READY FOR AGENTBEATS!"
echo "=========================================================================="
echo ""
echo "GREEN AGENT (Refactored):"
echo "  URL: http://localhost:9006"
echo "  Name: tau_green_agent_refactored"
echo "  Features: AgentBeats SDK, @ab.tool decorators, MCP-ready"
echo ""
echo "WHITE AGENT:"
echo "  URL: http://localhost:9004"
echo "  Name: general_white_agent"
echo ""
echo "--------------------------------------------------------------------------"
echo ""
echo "USE THESE URLs IN AGENTBEATS UI:"
echo "  Green Agent: http://localhost:9006"
echo "  White Agent: http://localhost:9004"
echo ""
echo "=========================================================================="
echo ""
echo "To STOP:"
echo "  kill $GREEN_PID $WHITE_PID"
echo ""
echo "=========================================================================="
