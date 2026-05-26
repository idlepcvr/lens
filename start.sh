#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if systemctl --user is-active --quiet lens.service; then
    echo "lens is already running — restarting..."
    systemctl --user restart lens.service
else
    echo "Starting lens..."
    systemctl --user start lens.service
fi

systemctl --user status lens.service --no-pager
