#!/bin/bash
# Script to run the white agent directly (without launcher API)

cd "$(dirname "$0")"

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "========================================"
echo "Starting White Agent (Retail Service)"
echo "========================================"
echo "Agent Port: 9004"
echo "========================================"
echo ""

uv run python main.py white
