#!/bin/bash
# Watch the green agent log file in real-time

echo "Watching green_agent.log (press Ctrl+C to stop)..."
echo "==============================================="
tail -f green_agent.log
