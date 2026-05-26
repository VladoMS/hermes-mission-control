#!/usr/bin/env bash
# =============================================================================
# Mission Control — Launch Script
# Starts the dashboard server in background, verifies it's up, and prints the
# Tailscale access URL.
# =============================================================================

set -e

MISSION_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_PY="${MISSION_DIR}/server.py"
PIDFILE="${MISSION_DIR}/server.pid"
LOGFILE="${MISSION_DIR}/server.log"
PORT=51763

# --- Resolve Tailscale IP ---
TAILSCALE_IP="$(tailscale ip -4 2>/dev/null || true)"
if [ -z "$TAILSCALE_IP" ]; then
    echo "! WARNING: Tailscale IP not found. Dashboard will only be accessible locally."
    ACCESS_URL="http://localhost:${PORT}"
else
    ACCESS_URL="http://${TAILSCALE_IP}:${PORT}"
fi

# --- Check if already running ---
if [ -f "$PIDFILE" ]; then
    OLD_PID="$(cat "$PIDFILE")"
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "! Mission Control is already running (PID $OLD_PID)"
        echo "  → $ACCESS_URL"
        echo "  Use 'stop.sh' to shut it down."
        exit 0
    else
        echo "! Stale PID file found. Removing."
        rm -f "$PIDFILE"
    fi
fi

# --- Start server ---
echo "▶ Starting Mission Control..."
cd "$MISSION_DIR"

nohup python3 "$SERVER_PY" > "$LOGFILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PIDFILE"

# --- Wait for startup ---
sleep 2

# --- Verify reachability ---
if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
    echo "✓ Mission Control is running (PID $SERVER_PID)"
    echo "  → ${ACCESS_URL}"
else
    echo "! Server started (PID $SERVER_PID) but not yet reachable."
    echo "  Check logs: ${LOGFILE}"
fi

echo ""
echo "  Stop:  ${MISSION_DIR}/stop.sh"
echo "  Logs:  ${LOGFILE}"
echo "  PID:   ${SERVER_PID}"
