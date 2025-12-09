#!/bin/bash
# Helper script to launch different white agent variants

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

cd "$PROJECT_ROOT"

if [ $# -eq 0 ]; then
    echo "Usage: $0 {baseline|stateless|reasoning}"
    echo ""
    echo "Variants:"
    echo "  baseline   - Standard agent with conversation memory (port 9004)"
    echo "  stateless  - No conversation memory (port 9014) - expected WORSE performance"
    echo "  reasoning  - Explicit reasoning steps (port 9024) - expected BETTER performance"
    exit 1
fi

VARIANT=$1

case $VARIANT in
    baseline)
        echo "================================"
        echo "Launching BASELINE white agent"
        echo "Port: 9004"
        echo "Features: Conversation memory"
        echo "================================"
        uv run python main.py white
        ;;
    stateless)
        echo "===================================="
        echo "Launching STATELESS white agent"
        echo "Port: 9014"
        echo "Features: NO conversation memory"
        echo "Expected: WORSE performance"
        echo "===================================="
        uv run python main.py white-stateless
        ;;
    reasoning)
        echo "=========================================="
        echo "Launching REASONING-ENHANCED white agent"
        echo "Port: 9024"
        echo "Features: Conversation memory + reasoning"
        echo "Expected: BETTER performance"
        echo "=========================================="
        uv run python main.py white-reasoning
        ;;
    *)
        echo "Error: Unknown variant '$VARIANT'"
        echo "Valid variants: baseline, stateless, reasoning"
        exit 1
        ;;
esac
