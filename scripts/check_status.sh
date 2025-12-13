#!/bin/bash

# Quick test script to verify everything is working

echo "🧪 Testing Tau-Bench Agent Setup"
echo "=================================="

# Check if launchers are running
echo ""
echo "Checking if launchers are running..."
GREEN_RUNNING=$(lsof -i :9111 -t 2>/dev/null)
WHITE_RUNNING=$(lsof -i :9210 -t 2>/dev/null)

if [ -z "$GREEN_RUNNING" ]; then
    echo "❌ Green launcher is NOT running on port 9111"
    echo "   Start it: uv run python launchers/green_launcher_mcp.py"
else
    echo "✅ Green launcher is running (PID: $GREEN_RUNNING)"
fi

if [ -z "$WHITE_RUNNING" ]; then
    echo "❌ White launcher is NOT running on port 9210"
    echo "   Start it: uv run python launchers/white_launcher.py"
else
    echo "✅ White launcher is running (PID: $WHITE_RUNNING)"
fi

# Test endpoints if running
if [ -n "$GREEN_RUNNING" ]; then
    echo ""
    echo "Testing Green Launcher endpoints..."
    HEALTH=$(curl -s http://localhost:9111/health 2>/dev/null)
    if [ -n "$HEALTH" ]; then
        echo "  ✅ Health endpoint: $HEALTH"
    else
        echo "  ❌ Health endpoint failed"
    fi
    
    STATUS=$(curl -s http://localhost:9111/status 2>/dev/null)
    if [ -n "$STATUS" ]; then
        echo "  ✅ Status endpoint: $STATUS"
    else
        echo "  ❌ Status endpoint failed"
    fi
fi

if [ -n "$WHITE_RUNNING" ]; then
    echo ""
    echo "Testing White Launcher endpoints..."
    HEALTH=$(curl -s http://localhost:9210/health 2>/dev/null)
    if [ -n "$HEALTH" ]; then
        echo "  ✅ Health endpoint: $HEALTH"
    else
        echo "  ❌ Health endpoint failed"
    fi
    
    STATUS=$(curl -s http://localhost:9210/status 2>/dev/null)
    if [ -n "$STATUS" ]; then
        echo "  ✅ Status endpoint: $STATUS"
    else
        echo "  ❌ Status endpoint failed"
    fi
fi

# Check if agents are running
echo ""
echo "Checking if agents are running..."
GREEN_AGENT=$(lsof -i :9006 -t 2>/dev/null)
WHITE_BASELINE=$(lsof -i :9004 -t 2>/dev/null)
WHITE_STATELESS=$(lsof -i :9014 -t 2>/dev/null)
WHITE_REASONING=$(lsof -i :9024 -t 2>/dev/null)

if [ -z "$GREEN_AGENT" ]; then
    echo "ℹ️  Green agent is NOT running on port 9006 (launch it first)"
else
    echo "✅ Green agent is running (PID: $GREEN_AGENT)"
fi

# Check all white agent variants
WHITE_FOUND=false
if [ -n "$WHITE_BASELINE" ]; then
    echo "✅ White agent BASELINE variant is running (PID: $WHITE_BASELINE, Port: 9004)"
    WHITE_FOUND=true
fi

if [ -n "$WHITE_STATELESS" ]; then
    echo "✅ White agent STATELESS variant is running (PID: $WHITE_STATELESS, Port: 9014)"
    WHITE_FOUND=true
fi

if [ -n "$WHITE_REASONING" ]; then
    echo "✅ White agent REASONING variant is running (PID: $WHITE_REASONING, Port: 9024)"
    WHITE_FOUND=true
fi

if [ "$WHITE_FOUND" = false ]; then
    echo "ℹ️  No white agent variants are running"
    echo "   Launch with: ./scripts/start_mcp.sh"
    echo "   Or: AGENT_VARIANT=stateless ./scripts/start_mcp.sh"
    echo "   Or: AGENT_VARIANT=reasoning ./scripts/start_mcp.sh"
fi

echo ""
echo "=================================="
echo "Next steps:"
if [ -z "$GREEN_RUNNING" ] || [ -z "$WHITE_RUNNING" ]; then
    echo "1. Start the launchers (see commands above)"
    echo "2. Run this script again to verify"
else
    echo "1. Register agents in AgentBeats UI:"
    echo "   - Green: http://localhost:9006 (Launcher: http://localhost:9111)"
    echo "   - White (baseline): http://localhost:9004 (Launcher: http://localhost:9210)"
    echo "   - White (stateless): http://localhost:9014 (Launcher: http://localhost:9210)"
    echo "   - White (reasoning): http://localhost:9024 (Launcher: http://localhost:9210)"
    echo "2. Launch agents via UI or API"
    echo "3. Create and run your evaluation!"
    echo ""
    echo "Available white agent variants:"
    echo "  • baseline   - Conversation memory (port 9004)"
    echo "  • stateless  - No memory (port 9014)"
    echo "  • reasoning  - Memory + reasoning (port 9024)"
fi
