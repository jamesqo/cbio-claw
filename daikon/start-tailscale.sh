#!/usr/bin/env bash
set -euo pipefail
state="$HOME/.local/state/tailscale"
mkdir -p "$state"
chmod 700 "$state"
exec 9>"$state/daemon.lock"
flock -n 9 || exit 0
exec >"$state/daemon.log" 2>&1
exec "$HOME/.local/opt/tailscale/tailscaled" \
  --tun=userspace-networking \
  --state="$state/tailscaled.state" \
  --socket="$state/tailscaled.sock" \
  --socks5-server=127.0.0.1:1055
