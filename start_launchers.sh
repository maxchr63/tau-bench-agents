# filepath: /Users/max/Documents/Uni/Berkeley/agentic_ai/tau-bench-agents/start_launchers.sh
#!/bin/bash

# Start both launchers in the background
cd "$(dirname "$0")"

echo "Starting Green Agent Launcher on port 9110..."
uv run python src/green_launcher.py &
GREEN_PID=$!
echo "Green launcher started with PID: $GREEN_PID"

sleep 2

echo "Starting White Agent Launcher on port 9210..."
uv run python src/white_launcher.py &
WHITE_PID=$!
echo "White launcher started with PID: $WHITE_PID"

echo ""
echo "Both launchers are running!"
echo "Green launcher: http://localhost:9110"
echo "White launcher: http://localhost:9210"
echo ""

# Wait a bit to ensure servers are ready
sleep 3

echo "Launching Green Agent via launcher API..."
curl -X POST http://localhost:9110/launch
echo ""

echo "Launching White Agent via launcher API..."
curl -X POST http://localhost:9210/launch
echo ""

echo "To stop them, run: kill $GREEN_PID $WHITE_PID"
echo "Or use: pkill -f 'python src/.*_launcher.py'"