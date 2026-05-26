#!/usr/bin/env bash
# =============================================================================
# Mission Control — Stop Script
# Gracefully shuts down the dashboard server.
# =============================================================================

set -e

MISSION_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="${MISSION_DIR}/server.pid"

if [ ! -f "$PIDFILE" ]; then
    # Try to find by port
    PID="$(lsof -ti:51763 2>/dev/null || true)"
    if [ -z "$PID" ]; then
        echo "! Mission Control is not running."
        exit 0
    fi
else
    PID="$(cat "$PIDFILE")"
fi

echo "▼ Stopping Mission Control (PID $PID)..."
kill "$PID" 2>/dev/null || true

# Wait for graceful shutdown
for i in 1 2 3; do
    if ! kill -0 "$PID" 2>/dev/null; then
        break
    fi
    sleep 1
done

# Force kill if still running
if kill -0 "$PID" 2>/dev/null; then
    echo "! Force killing..."
    kill -9 "$PID" 2>/dev/null || true
fi

rm -f "$PIDFILE"
echo "✓ Mission Control stopped."
