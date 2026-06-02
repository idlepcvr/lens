#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

PORT=8765

if systemctl --user is-active --quiet lens.service; then
    echo "lens is already running — restarting..."
    systemctl --user restart lens.service
else
    echo "Starting lens..."
    systemctl --user start lens.service
fi

# Give uvicorn a moment to bind the port
sleep 1

# Best-effort LAN IP (for opening the dashboard from your phone on the same network)
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo
if systemctl --user is-active --quiet lens.service; then
    echo "✅ LENS is up. Open the dashboard:"
    echo
    echo "   →  http://localhost:${PORT}"
    [ -n "$LAN_IP" ] && echo "   →  http://${LAN_IP}:${PORT}   (from another device on this LAN)"
    echo
    echo "   health: http://localhost:${PORT}/health"
else
    echo "❌ LENS failed to start. Recent log:"
    tail -n 20 /home/mini/lens/lens.log
    exit 1
fi
