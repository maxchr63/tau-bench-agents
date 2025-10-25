#!/bin/bash
# Restructure tau-bench-agents into a2a and mcp implementations

echo "🔧 Restructuring tau-bench-agents..."
echo ""

# Move original (a2a) implementation
echo "📦 Moving A2A implementation (original)..."
cp -r src/green_agent implementations/a2a/ 2>/dev/null || echo "  ⚠️  green_agent already exists"
cp -r src/white_agent implementations/a2a/ 2>/dev/null || echo "  ⚠️  white_agent already exists"
cp -r src/my_util implementations/a2a/ 2>/dev/null || echo "  ⚠️  my_util already exists"

# Remove refactored files from a2a
rm -f implementations/a2a/green_agent/agent_refactored.py
rm -f implementations/a2a/green_agent/tools.py
rm -f implementations/a2a/green_agent/tau_green_agent_refactored.toml

echo "  ✓ A2A implementation ready"
echo ""

# Move refactored (mcp) implementation
echo "📦 Moving MCP implementation (refactored)..."
mkdir -p implementations/mcp/green_agent
mkdir -p implementations/mcp/white_agent

cp src/green_agent/agent_refactored.py implementations/mcp/green_agent/agent.py
cp src/green_agent/tools.py implementations/mcp/green_agent/
cp src/green_agent/tau_green_agent_refactored.toml implementations/mcp/green_agent/tau_green_agent.toml
cp src/green_agent/__init__.py implementations/mcp/green_agent/ 2>/dev/null || echo "from .agent import start_green_agent" > implementations/mcp/green_agent/__init__.py

# White agent is same for both
cp -r src/white_agent/* implementations/mcp/white_agent/

echo "  ✓ MCP implementation ready"
echo ""

# Move launchers
echo "📦 Moving launchers..."
cp src/green_launcher.py launchers/green_launcher_a2a.py
cp src/green_launcher_refactored.py launchers/green_launcher_mcp.py
cp src/white_launcher.py launchers/

echo "  ✓ Launchers ready"
echo ""

# Move scripts
echo "📦 Moving scripts..."
cp start_launchers.sh scripts/start_a2a.sh 2>/dev/null || echo "  ⚠️  start_launchers.sh not found"
cp start_refactored_only.sh scripts/start_mcp.sh 2>/dev/null || echo "  ⚠️  start_refactored_only.sh not found"
cp start_launchers_side_by_side.sh scripts/start_side_by_side.sh 2>/dev/null || echo "  ⚠️  start_side_by_side.sh not found"

echo "  ✓ Scripts ready"
echo ""

echo "✅ Restructure complete!"
echo ""
echo "New structure:"
echo "  implementations/a2a/     - Original implementation"
echo "  implementations/mcp/     - Refactored with @ab.tool"
echo "  launchers/               - Launcher servers"
echo "  scripts/                 - Start scripts"
echo ""
echo "Old src/ directory preserved (you can delete it later)"

