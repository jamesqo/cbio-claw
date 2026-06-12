#!/usr/bin/env bash
# Install and start oMLX — https://github.com/jundot/omlx
#
# Optional env vars:
#   PORT=<n>   Port for oMLX to listen on (default: 8000)
#
set -euo pipefail

PORT="${PORT:-8000}"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'

info()  { echo -e "${GREEN}[oMLX]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[oMLX]${RESET} $*"; }
error() { echo -e "${RED}[oMLX]${RESET} $*" >&2; exit 1; }

# ── Pre-flight checks ──────────────────────────────────────────────────────────

[[ "$(uname -s)" == "Darwin" ]] || error "oMLX requires macOS."

ARCH="$(uname -m)"
[[ "$ARCH" == "arm64" ]] || error "oMLX requires Apple Silicon (arm64). Detected: $ARCH"

OS_VER="$(sw_vers -productVersion)"
MAJOR="$(echo "$OS_VER" | cut -d. -f1)"
(( MAJOR >= 15 )) || error "oMLX requires macOS 15+. You have $OS_VER."

command -v brew >/dev/null 2>&1 || error "Homebrew is required. Install it from https://brew.sh"

# ── Install hf CLI ─────────────────────────────────────────────────────────────

if command -v hf >/dev/null 2>&1; then
    info "hf CLI already installed ($(hf --version 2>/dev/null || echo 'version unknown'))."
else
    info "Installing hf CLI…"
    pip install -q "huggingface_hub[cli]" || error "Failed to install hf CLI. Make sure pip is available."
    info "hf CLI installed."
fi

# ── Check port availability ────────────────────────────────────────────────────

check_port() {
    # Returns non-zero if port is in use by a process other than omlx itself
    lsof -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | grep -v "omlx\|Python.*omlx" | grep -q .
}

if check_port; then
    OWNER="$(lsof -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | grep -v "omlx\|Python.*omlx" | awk 'NR==2{print $1}' || echo 'unknown')"
    error "Port $PORT is already in use by: $OWNER
  Stop that process or run with a different port:
    PORT=8001 make setup-omlx
    PORT=8001 make use-omlx MODEL=<model-id>"
fi

# ── Install ────────────────────────────────────────────────────────────────────

if command -v omlx >/dev/null 2>&1; then
    info "oMLX is already installed ($(omlx --version 2>/dev/null || echo 'version unknown'))."
else
    info "Adding oMLX tap…"
    brew tap jundot/omlx https://github.com/jundot/omlx
    # Homebrew requires explicit trust for third-party taps
    brew trust jundot/omlx

    info "Installing oMLX…"
    brew install omlx
fi

# ── Write launchd plist ────────────────────────────────────────────────────────
#
# The default brew-managed plist binds to 127.0.0.1. Docker containers reach
# the host via host.docker.internal (→ host LAN IP), so oMLX must bind on
# 0.0.0.0. We own the plist directly instead of patching brew's copy.

OMLX_BIN="/opt/homebrew/opt/omlx/bin/omlx"
PLIST="$HOME/Library/LaunchAgents/homebrew.mxcl.omlx.plist"
LOG_DIR="/opt/homebrew/var/log"
mkdir -p "$LOG_DIR"

write_plist() {
    cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>Label</key>
    <string>homebrew.mxcl.omlx</string>
    <key>ProgramArguments</key>
    <array>
        <string>$OMLX_BIN</string>
        <string>serve</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>$PORT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/omlx.log</string>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/omlx.log</string>
</dict>
</plist>
PLIST
}

# ── Start / restart service ────────────────────────────────────────────────────
# launchctl load/unload are deprecated on macOS 13+; use bootstrap/bootout.

UID_="$(id -u)"
DOMAIN="gui/$UID_"
LABEL="homebrew.mxcl.omlx"

service_running() {
    launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
}

if service_running; then
    warn "oMLX already running — rewriting plist and restarting…"
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
fi

write_plist
launchctl bootstrap "$DOMAIN" "$PLIST"
info "oMLX started (bound to 0.0.0.0:$PORT)."

# ── Done ───────────────────────────────────────────────────────────────────────

echo ""
info "oMLX is ready at http://127.0.0.1:$PORT/v1"
echo ""
echo "  Next steps:"
echo "    1. Pull a model, e.g.:"
echo "         omlx pull mlx-community/Qwen3-8B-4bit"
echo ""
echo "    2. Verify it appears in the model list:"
echo "         curl http://127.0.0.1:$PORT/v1/models"
echo ""
echo "    3. Switch the agent to use it (replace <model-id> with the name from step 2):"
echo "         make use-omlx MODEL=<model-id> PORT=$PORT"
echo "         make restart"
echo ""
