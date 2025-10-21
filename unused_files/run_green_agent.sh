#!/bin/bash
# Script to run the green agent directly (without launcher API)

cd "$(dirname "$0")"

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "========================================"
echo "Starting Green Agent (Tau-Bench Evaluator)"
echo "========================================"
echo "Agent Port: 9003"
echo "========================================"
echo ""

uv run python main.py green
