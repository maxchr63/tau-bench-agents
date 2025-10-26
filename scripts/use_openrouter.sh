#!/bin/bash
# Switch to using OpenRouter as the LLM provider
# Usage: source ./scripts/use_openrouter.sh

echo "🔄 Switching to OpenRouter..."

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env file if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "📄 Loading .env file..."
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# Check if OPENROUTER_API_KEY is set
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "⚠️  OPENROUTER_API_KEY not set!"
    echo ""
    echo "Please add your OpenRouter API key to .env file:"
    echo "  OPENROUTER_API_KEY=your-key-here"
    echo ""
    echo "Get your key from: https://openrouter.ai/keys"
    return 1 2>/dev/null || exit 1
fi

# Set provider to OpenRouter
export LLM_PROVIDER="openrouter"

# Optional: Set specific model (default is openai/gpt-4o-mini)
# Uncomment and modify to use a different model:
# export OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"
# export OPENROUTER_MODEL="google/gemini-pro-1.5"
# export OPENROUTER_MODEL="meta-llama/llama-3.1-8b-instruct"

echo "✅ OpenRouter configured!"
echo "   Model: ${OPENROUTER_MODEL:-openai/gpt-4o-mini}"
echo ""
echo "Now run your agent with: ./scripts/start_mcp.sh"
