#!/bin/bash
# Test script to verify OpenRouter configuration is working

set -euo pipefail

# Move to repo root (script is in ./scripts/)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==============================================="
echo "TESTING OPENROUTER CONFIGURATION"
echo "==============================================="

echo ""
echo "1. Testing shared_config.py directly..."
uv run python implementations/mcp/shared_config.py

echo ""
echo "==============================================="
echo "2. Killing old agents..."
pkill -f "green_launcher_mcp|white_launcher|start_green_agent"
sleep 2

echo ""
echo "3. Starting agents..."
nohup bash scripts/start_mcp.sh > /tmp/agent_startup_test.log 2>&1 &
sleep 8

echo ""
echo "4. Checking if agents are running..."
ps aux | grep python | grep -E "launcher|start_green_agent" | grep -v grep | wc -l

echo ""
echo "5. Checking for configuration messages in logs..."
echo "   From startup script:"
grep -E "Using OpenRouter|CONFIGURING" /tmp/agent_startup_test.log | head -5

echo ""
echo "   From green agent log (last 20 lines):"
tail -20 implementations/mcp/green_agent.log 2>/dev/null

echo ""
echo "==============================================="
echo "CONFIGURATION TEST COMPLETE!"
echo "==============================================="
echo ""
echo "If you see 'provider = openai' in the green_agent.log,"
echo "the configuration is working (OpenRouter uses OpenAI-compatible API)."
echo ""
echo "To verify it's actually using OpenRouter, run a test and check"
echo "the OpenRouter dashboard for API calls."
echo "==============================================="
