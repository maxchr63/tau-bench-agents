#!/bin/bash
# Complete restart script for AgentBeats + Tau-Bench agents

echo "========================================"
echo "RESTARTING AGENTBEATS + TAU-BENCH AGENTS"
echo "========================================"

# Kill everything
echo ""
echo "1. Killing all processes..."
pkill -f "agentbeats|green_launcher|white_launcher|start_green_agent"
sleep 3

# Start AgentBeats in background
echo ""
echo "2. Starting AgentBeats backend..."
cd /Users/max/Documents/Uni/Berkeley/agentic_ai/agentbeats
nohup agentbeats deploy > /tmp/agentbeats.log 2>&1 &
AGENTBEATS_PID=$!
echo "   AgentBeats PID: $AGENTBEATS_PID"

# Wait for backend to be ready
echo ""
echo "3. Waiting for AgentBeats backend to start (15 seconds)..."
sleep 15

# Check if backend is responding
echo ""
echo "4. Checking backend health..."
if curl -s http://localhost:9000/health > /dev/null 2>&1; then
    echo "   ✅ Backend is running!"
else
    echo "   ⚠️  Backend not responding yet, but continuing..."
fi

# Start agents
echo ""
echo "5. Starting tau-bench agents..."
cd /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents
bash scripts/start_mcp.sh

echo ""
echo "========================================"
echo "STARTUP COMPLETE!"
echo "========================================"
echo ""
echo "Services:"
echo "  • AgentBeats Backend: http://localhost:9000"
echo "  • AgentBeats Frontend: http://localhost:5173"
echo "  • Green Agent: http://localhost:9006"
echo "  • White Agent: http://localhost:9004"
echo ""
echo "To stop everything:"
echo "  pkill -f 'agentbeats|green_launcher|white_launcher'"
echo ""
echo "========================================"
