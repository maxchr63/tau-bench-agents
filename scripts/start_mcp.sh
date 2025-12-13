#!/bin/bash
cd "$(dirname "$0")/.."

# Load .env file if it exists
if [ -f ".env" ]; then
    echo "📄 Loading .env file..."
    export $(grep -v '^#' .env | xargs)
fi

# Detect white agent variant from environment variable
export AGENT_VARIANT=${AGENT_VARIANT:-baseline}

# Set variant-specific ports and info
case $AGENT_VARIANT in
    baseline)
        WHITE_PORT=9004
        VARIANT_NAME="BASELINE"
        VARIANT_DESC="Conversation memory, no explicit reasoning"
        ;;
    stateless)
        WHITE_PORT=9014
        VARIANT_NAME="STATELESS"
        VARIANT_DESC="NO conversation memory - testing memory importance"
        ;;
    reasoning)
        WHITE_PORT=9024
        VARIANT_NAME="REASONING-ENHANCED"
        VARIANT_DESC="Conversation memory + explicit reasoning steps"
        ;;
    *)
        echo "❌ Unknown AGENT_VARIANT: $AGENT_VARIANT"
        echo "Valid options: baseline, stateless, reasoning"
        exit 1
        ;;
esac

# Show LLM provider configuration (match implementations/mcp/shared_config.py)
PROVIDER="${USE_PROVIDER:-${LLM_PROVIDER:-openrouter}}"
if [ "$PROVIDER" = "openrouter" ]; then
    echo "Using OpenRouter (model: ${TAU_USER_MODEL:-${OPENROUTER_MODEL:-anthropic/claude-haiku-4.5}})"
else
    echo "Using OpenAI (model: ${TAU_USER_MODEL:-${OPENAI_MODEL:-gpt-4o-mini}})"
fi
echo "🎯 White Agent Variant: $VARIANT_NAME"
echo "   Features: $VARIANT_DESC"
echo ""

echo "🔄 Cleaning up old processes..."
pkill -f 'python.*launcher' 2>/dev/null
for port in 9003 9004 9006 9110 9111 9210 9014 9024; do
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

echo "🚀 Launching White Agent ($VARIANT_NAME variant)..."
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
echo "WHITE AGENT ($VARIANT_NAME):"
echo "  URL: http://localhost:$WHITE_PORT"
echo "  Name: ${AGENT_VARIANT}_white_agent"
echo "  Features: $VARIANT_DESC"
echo ""
echo "--------------------------------------------------------------------------"
echo ""
echo "USE THESE URLs IN AGENTBEATS UI:"
echo "  Green Agent: http://localhost:9006"
echo "  White Agent: http://localhost:$WHITE_PORT"
echo ""
echo "To test other variants:"
echo "  AGENT_VARIANT=baseline ./scripts/start_mcp.sh  (port 9004)"
echo "  AGENT_VARIANT=stateless ./scripts/start_mcp.sh (port 9014)"
echo "  AGENT_VARIANT=reasoning ./scripts/start_mcp.sh (port 9024)"
echo ""
echo "=========================================================================="
echo ""
echo "To STOP:"
echo "  kill $GREEN_PID $WHITE_PID"
echo ""
echo "=========================================================================="
