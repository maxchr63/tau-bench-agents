#!/bin/bash
# Side-by-side launcher: Original vs Refactored Green Agent
# This allows you to test both versions on AgentBeats

cd "$(dirname "$0")"

echo "=========================================================================="
echo "  SIDE-BY-SIDE LAUNCHER: Original vs Refactored"
echo "=========================================================================="
echo ""

# ============================================================================
# ORIGINAL AGENTS
# ============================================================================

echo "📦 Starting ORIGINAL Green Agent Launcher on port 9110..."
uv run python src/green_launcher.py &
GREEN_PID=$!
echo "   ✓ Original green launcher started with PID: $GREEN_PID"
echo ""

sleep 2

echo "📦 Starting White Agent Launcher on port 9210..."
uv run python src/white_launcher.py &
WHITE_PID=$!
echo "   ✓ White launcher started with PID: $WHITE_PID"
echo ""

sleep 2

# ============================================================================
# REFACTORED GREEN AGENT
# ============================================================================

echo "🔧 Starting REFACTORED Green Agent Launcher on port 9111..."
uv run python src/green_launcher_refactored.py &
GREEN_REFACTORED_PID=$!
echo "   ✓ Refactored green launcher started with PID: $GREEN_REFACTORED_PID"
echo ""

# ============================================================================
# SUMMARY
# ============================================================================

echo "=========================================================================="
echo "  ALL LAUNCHERS RUNNING!"
echo "=========================================================================="
echo ""
echo "ORIGINAL AGENTS:"
echo "  • Green launcher: http://localhost:9110 (PID: $GREEN_PID)"
echo "  • White launcher: http://localhost:9210 (PID: $WHITE_PID)"
echo ""
echo "REFACTORED AGENTS:"
echo "  • Green launcher (refactored): http://localhost:9111 (PID: $GREEN_REFACTORED_PID)"
echo ""
echo "--------------------------------------------------------------------------"
echo ""

# Wait for servers to be ready
echo "⏳ Waiting for servers to be ready..."
sleep 3

# ============================================================================
# LAUNCH AGENTS
# ============================================================================

echo ""
echo "=========================================================================="
echo "  LAUNCHING AGENTS"
echo "=========================================================================="
echo ""

echo "🚀 Launching ORIGINAL Green Agent (port 9003)..."
curl -X POST http://localhost:9110/launch
echo ""
echo ""

echo "🚀 Launching White Agent (port 9004)..."
curl -X POST http://localhost:9210/launch
echo ""
echo ""

echo "🚀 Launching REFACTORED Green Agent (port 9006)..."
curl -X POST http://localhost:9111/launch
echo ""
echo ""

# ============================================================================
# AGENTBEATS INSTRUCTIONS
# ============================================================================

echo "=========================================================================="
echo "  READY FOR AGENTBEATS!"
echo "=========================================================================="
echo ""
echo "AGENT URLS FOR AGENTBEATS:"
echo ""
echo "ORIGINAL GREEN AGENT:"
echo "  URL: http://localhost:9003"
echo "  Name: tau_green_agent"
echo "  Type: Green (Evaluator)"
echo ""
echo "REFACTORED GREEN AGENT:"
echo "  URL: http://localhost:9006"
echo "  Name: tau_green_agent_refactored"
echo "  Type: Green (Evaluator)"
echo "  Features: AgentBeats SDK, @ab.tool decorators, MCP-ready"
echo ""
echo "WHITE AGENT (Same for both):"
echo "  URL: http://localhost:9004"
echo "  Name: general_white_agent"
echo "  Type: White (Target)"
echo ""
echo "--------------------------------------------------------------------------"
echo ""
echo "TO TEST ON AGENTBEATS:"
echo ""
echo "1. Go to AgentBeats UI"
echo "2. Create a new battle"
echo "3. Choose GREEN agent:"
echo "   - Original: http://localhost:9003"
echo "   - Refactored: http://localhost:9006"
echo "4. Choose WHITE agent: http://localhost:9004"
echo "5. Start battle and compare!"
echo ""
echo "--------------------------------------------------------------------------"
echo ""
echo "COMPARISON:"
echo ""
echo "Original Agent (9003):"
echo "  • Uses custom my_util/my_a2a.py"
echo "  • Manual battle progress tracking"
echo "  • No tool decorators"
echo ""
echo "Refactored Agent (9006):"
echo "  • Uses AgentBeats SDK utilities"
echo "  • Automatic battle tracking with ab.record_battle_event()"
echo "  • Has @ab.tool decorated functions"
echo "  • MCP-ready tools"
echo ""
echo "=========================================================================="
echo ""
echo "To STOP all agents:"
echo "  kill $GREEN_PID $WHITE_PID $GREEN_REFACTORED_PID"
echo ""
echo "Or use:"
echo "  pkill -f 'python src/.*_launcher.*\.py'"
echo ""
echo "=========================================================================="
