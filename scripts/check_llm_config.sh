#!/bin/bash
# Check LLM provider configuration
# Usage: ./scripts/check_llm_config.sh

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env file if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

echo "🔍 Current LLM Configuration"
echo "=============================="
echo ""

# Check LLM_PROVIDER
if [ -z "$LLM_PROVIDER" ]; then
    echo "Provider: OpenAI (default)"
else
    echo "Provider: $LLM_PROVIDER"
fi

echo ""

# Check API keys
if [ "$LLM_PROVIDER" = "openrouter" ]; then
    echo "OpenRouter Configuration:"
    if [ -z "$OPENROUTER_API_KEY" ]; then
        echo "  ❌ API Key: NOT SET"
        echo ""
        echo "  To set your key:"
        echo "    export OPENROUTER_API_KEY='sk-or-v1-your-key'"
        echo "    source ./scripts/use_openrouter.sh"
    else
        KEY_PREFIX="${OPENROUTER_API_KEY:0:10}"
        echo "  ✅ API Key: ${KEY_PREFIX}..."
    fi
    
    echo "  Model: ${OPENROUTER_MODEL:-openai/gpt-4o-mini (default)}"
else
    echo "OpenAI Configuration:"
    if [ -z "$OPENAI_API_KEY" ]; then
        echo "  ⚠️  API Key: NOT SET in environment"
        echo "     (May be set in .env file)"
    else
        KEY_PREFIX="${OPENAI_API_KEY:0:7}"
        echo "  ✅ API Key: ${KEY_PREFIX}..."
    fi
fi

echo ""
echo "=============================="
echo ""
echo "To switch providers:"
echo "  OpenRouter: source ./scripts/use_openrouter.sh"
echo "  OpenAI:     source ./scripts/use_openai.sh"
echo ""
