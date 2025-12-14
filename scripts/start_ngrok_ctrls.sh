#!/usr/bin/env bash
set -euo pipefail

# Start TWO ngrok HTTP tunnels (green + white controllers) and run the controllers
# with CLOUDRUN_HOST/HTTPS_ENABLED set to the ngrok public hostnames.
#
# Defaults:
# - green controller on :8010
# - white controller on :8011
#
# Requirements:
# - ngrok installed + authenticated (ngrok config add-authtoken ...)
# - uv installed + deps synced (uv sync)

GREEN_PORT="${GREEN_PORT:-8010}"
WHITE_PORT="${WHITE_PORT:-8011}"

# ngrok local inspection API ports (must be different for 2 ngrok processes)
GREEN_NGROK_WEB_PORT="${GREEN_NGROK_WEB_PORT:-4040}"
WHITE_NGROK_WEB_PORT="${WHITE_NGROK_WEB_PORT:-4041}"

ROLE_GREEN="${ROLE_GREEN:-green}"
ROLE_WHITE="${ROLE_WHITE:-white}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${REPO_ROOT}/.ab/ngrok"
mkdir -p "$LOG_DIR"
GREEN_NGROK_LOG="${GREEN_NGROK_LOG:-${LOG_DIR}/ngrok_green_${GREEN_PORT}.log}"
WHITE_NGROK_LOG="${WHITE_NGROK_LOG:-${LOG_DIR}/ngrok_white_${WHITE_PORT}.log}"

if ! command -v ngrok >/dev/null 2>&1; then
  echo "❌ ngrok not found. Install from https://ngrok.com/download and then run:"
  echo "   ngrok config add-authtoken <your_token>"
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "❌ uv not found. Install uv and run: uv sync"
  exit 1
fi

_cleanup() {
  set +e
  if [[ -n "${GREEN_CTRL_PID:-}" ]]; then kill "$GREEN_CTRL_PID" 2>/dev/null; fi
  if [[ -n "${WHITE_CTRL_PID:-}" ]]; then kill "$WHITE_CTRL_PID" 2>/dev/null; fi
  if [[ -n "${GREEN_NGROK_PID:-}" ]]; then kill "$GREEN_NGROK_PID" 2>/dev/null; fi
  if [[ -n "${WHITE_NGROK_PID:-}" ]]; then kill "$WHITE_NGROK_PID" 2>/dev/null; fi
}
trap _cleanup EXIT INT TERM

_get_ngrok_host() {
  local web_port="$1"
  WEB_PORT="$web_port" NGROK_LOG_PATH="${NGROK_LOG_PATH:-}" uv run python - <<'PY'
import json
import time
import urllib.request
from urllib.parse import urlparse
import os

web_port = int(os.environ["WEB_PORT"])
url = f"http://127.0.0.1:{web_port}/api/tunnels"

last_err = None
for _ in range(120):
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            data = json.loads(r.read().decode("utf-8"))
        tunnels = data.get("tunnels") or []
        # Prefer HTTPS; fallback to any public_url.
        for t in tunnels:
            pu = (t or {}).get("public_url") or ""
            if pu.startswith("https://"):
                print(urlparse(pu).netloc)
                raise SystemExit(0)
        for t in tunnels:
            pu = (t or {}).get("public_url") or ""
            if pu:
                print(urlparse(pu).netloc)
                raise SystemExit(0)
    except Exception as e:
        last_err = e
        time.sleep(0.25)

log_path = os.environ.get("NGROK_LOG_PATH") or ""
hint = f" (see {log_path})" if log_path else ""
raise SystemExit(f"ngrok tunnel not ready on web_port={web_port}: {last_err}{hint}")
PY
}

echo "🟢 Starting ngrok tunnel for green controller on localhost:$GREEN_PORT ..."
echo "   log: $GREEN_NGROK_LOG"
ngrok http "$GREEN_PORT" --web-addr "127.0.0.1:${GREEN_NGROK_WEB_PORT}" >"$GREEN_NGROK_LOG" 2>&1 &
GREEN_NGROK_PID=$!

echo "⚪ Starting ngrok tunnel for white controller on localhost:$WHITE_PORT ..."
echo "   log: $WHITE_NGROK_LOG"
ngrok http "$WHITE_PORT" --web-addr "127.0.0.1:${WHITE_NGROK_WEB_PORT}" >"$WHITE_NGROK_LOG" 2>&1 &
WHITE_NGROK_PID=$!

NGROK_LOG_PATH="$GREEN_NGROK_LOG" GREEN_HOST="$(_get_ngrok_host "$GREEN_NGROK_WEB_PORT")"
NGROK_LOG_PATH="$WHITE_NGROK_LOG" WHITE_HOST="$(_get_ngrok_host "$WHITE_NGROK_WEB_PORT")"

echo ""
echo "=========================================================================="
echo "  NGROK TUNNELS READY"
echo "=========================================================================="
echo "Green: https://$GREEN_HOST"
echo "White: https://$WHITE_HOST"
echo ""

echo "🟢 Starting GREEN controller (PORT=$GREEN_PORT, ROLE=$ROLE_GREEN) ..."
PORT="$GREEN_PORT" HTTPS_ENABLED=true CLOUDRUN_HOST="$GREEN_HOST" ROLE="$ROLE_GREEN" \
  uv run python scripts/run_ctrl_normalized.py &
GREEN_CTRL_PID=$!

echo "⚪ Starting WHITE controller (PORT=$WHITE_PORT, ROLE=$ROLE_WHITE) ..."
PORT="$WHITE_PORT" HTTPS_ENABLED=true CLOUDRUN_HOST="$WHITE_HOST" ROLE="$ROLE_WHITE" \
  uv run python scripts/run_ctrl_normalized.py &
WHITE_CTRL_PID=$!

echo ""
echo "=========================================================================="
echo "  CONTROLLERS RUNNING"
echo "=========================================================================="
echo "Green controller public: https://$GREEN_HOST"
echo "White controller public: https://$WHITE_HOST"
echo ""
echo "Verify (once up):"
echo "  curl https://$GREEN_HOST/status"
echo "  curl https://$WHITE_HOST/status"
echo ""
echo "Stop: Ctrl-C"
echo ""

wait "$GREEN_CTRL_PID" "$WHITE_CTRL_PID"
