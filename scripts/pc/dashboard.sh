#!/usr/bin/env bash
# Opens petri's live dashboard from the PC: an ssh tunnel to alfred's 127.0.0.1:8780 and the browser.
# Start the culture on alfred first: ssh alfred 'cd ~/Projects/petri && docker compose --profile live up -d'
set -euo pipefail
PORT=${PORT:-8780}
if ! ss -ltn "sport = :$PORT" | grep -q LISTEN; then
    ssh -f -N -o ExitOnForwardFailure=yes -L "$PORT:127.0.0.1:8780" alfred
fi
xdg-open "http://localhost:$PORT" >/dev/null 2>&1 &
echo "dashboard: http://localhost:$PORT (tunnel: pkill -f 'L $PORT:127.0.0.1:8780' to close it)"
