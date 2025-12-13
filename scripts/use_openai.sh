#!/bin/bash
# Switch back to using OpenAI as the LLM provider
# Usage: source ./scripts/use_openai.sh

echo "🔄 Switching to OpenAI..."

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env file if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "📄 Loading .env file..."
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# Set provider to OpenAI
# Preferred env var (used by Python code): USE_PROVIDER
# Legacy env var (older scripts): LLM_PROVIDER
export USE_PROVIDER="openai"
export LLM_PROVIDER="openai"
unset OPENROUTER_API_KEY
unset OPENROUTER_MODEL

echo "✅ OpenAI configured!"
echo ""
echo "Now run your agent with: ./scripts/start_mcp.sh"
