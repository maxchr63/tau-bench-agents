#!/bin/bash
cd "$(dirname "$0")/.."

echo "🔄 Cleaning up old processes..."
pkill -f 'python.*launcher' 2>/dev/null
for port in 9003 9004 9006 9110 9111 9210; do 
    lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null
done
sleep 2

echo ""
echo "=========================================================================="
echo "  MCP GREEN AGENT LAUNCHER"
echo "=========================================================================="
echo ""

echo "🔧 Starting MCP Green Launcher on port 9111..."
uv run python launchers/green_launcher_mcp.py &
GREEN_PID=$!
echo "   ✓ MCP green launcher started with PID: $GREEN_PID"
echo ""

sleep 2

echo "📦 Starting White Launcher on port 9210..."
uv run python launchers/white_launcher.py &
WHITE_PID=$!
echo "   ✓ White launcher started with PID: $WHITE_PID"
echo ""

echo "=========================================================================="
echo "  LAUNCHERS RUNNING!"
echo "=========================================================================="
echo ""
echo "  • Green launcher (MCP): http://localhost:9111"
echo "  • White launcher: http://localhost:9210"
echo ""

sleep 3

echo "=========================================================================="
echo "  LAUNCHING AGENTS"
echo "=========================================================================="
echo ""

echo "🚀 Launching MCP Green Agent..."
curl -s -X POST http://localhost:9111/launch && echo ""
echo ""

echo "🚀 Launching White Agent..."
curl -s -X POST http://localhost:9210/launch && echo ""
echo ""

echo "=========================================================================="
echo "  AGENTS READY FOR AGENTBEATS!"
echo "=========================================================================="
echo ""
echo "GREEN AGENT (MCP):"
echo "  URL: http://localhost:9006"
echo "  Name: tau_green_agent_mcp"
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
