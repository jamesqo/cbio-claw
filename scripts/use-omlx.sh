#!/usr/bin/env bash
# Switch the Hermes agent to use a local oMLX model.
# Usage: use-omlx.sh <model-id> [port]
#   model-id: HuggingFace repo ID (e.g. mlx-community/Qwen3-8B-4bit)
#   port:     oMLX port (default: 8000; match the PORT used with setup-omlx.sh)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$REPO_ROOT/hermes-data/config.yaml"
ENV_FILE="$REPO_ROOT/hermes-data/.env"
PLIST="$HOME/Library/LaunchAgents/homebrew.mxcl.omlx.plist"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[use-omlx]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[use-omlx]${RESET} $*"; }
error() { echo -e "${RED}[use-omlx]${RESET} $*" >&2; exit 1; }

HF_MODEL="${1:-}"   # HuggingFace repo ID:  mlx-community/Qwen3-8B-4bit
PORT="${2:-8000}"
[[ -n "$HF_MODEL" ]] || error "Usage: $0 <model-id> [port]  (e.g. mlx-community/Qwen3-8B-4bit 8001)"
[[ -f "$CONFIG" ]] || error "Config not found: $CONFIG"

# oMLX derives model IDs from HF cache dir names, replacing / with --
# e.g. mlx-community/Qwen3-8B-4bit → mlx-community--Qwen3-8B-4bit
OMLX_MODEL="${HF_MODEL//\//--}"

# ── Check oMLX is reachable ────────────────────────────────────────────────────

curl -s --max-time 5 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1 \
    || error "oMLX is not responding on port $PORT. Run: make setup-omlx PORT=$PORT"

# ── Download model if not in HF cache ─────────────────────────────────────────

HF_CACHE_DIR="$HOME/.cache/huggingface/hub/models--${HF_MODEL//\//--}"

if [[ -d "$HF_CACHE_DIR" ]]; then
    info "Model already in HF cache."
else
    info "Downloading '$HF_MODEL' from HuggingFace…"
    hf download "$HF_MODEL" || error "Download failed. Check the model name and try again."
fi

# ── Restart oMLX so it discovers the model from the HF cache ──────────────────

AVAILABLE="$(curl -s "http://127.0.0.1:$PORT/v1/models" | python3 -c "import json,sys; print(' '.join(m['id'] for m in json.load(sys.stdin)['data']))")"

if echo "$AVAILABLE" | tr ' ' '\n' | grep -qxF "$OMLX_MODEL"; then
    info "Model '$OMLX_MODEL' is already loaded."
else
    info "Restarting oMLX to pick up the downloaded model…"
    launchctl bootout "gui/$(id -u)/homebrew.mxcl.omlx" 2>/dev/null || true
    sleep 1
    launchctl bootstrap "gui/$(id -u)" "$PLIST" \
        || error "Failed to restart oMLX. Is $PLIST present? Run: make setup-omlx PORT=$PORT"
    until curl -s --max-time 2 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; do sleep 2; done
    info "oMLX is back up."

    AVAILABLE="$(curl -s "http://127.0.0.1:$PORT/v1/models" | python3 -c "import json,sys; print(' '.join(m['id'] for m in json.load(sys.stdin)['data']))")"
    echo "$AVAILABLE" | tr ' ' '\n' | grep -qxF "$OMLX_MODEL" \
        || error "Model '$OMLX_MODEL' still not found after restart. Available: $AVAILABLE"
    info "Model '$OMLX_MODEL' is ready."
fi

# ── Backup + patch config.yaml ────────────────────────────────────────────────

TS="$(date -u +%Y%m%dT%H%M%SZ)"
cp "$CONFIG" "${CONFIG}.bak-$TS"
info "Backed up config → ${CONFIG}.bak-$TS"

python3 - "$CONFIG" "$OMLX_MODEL" "$PORT" <<'PYEOF'
import re, sys

config_path, model, port = sys.argv[1], sys.argv[2], sys.argv[3]
with open(config_path) as f:
    content = f.read()

content = re.sub(
    r'^(model:\n  default: ).*$',
    lambda m: m.group(1) + model,
    content, count=1, flags=re.MULTILINE
)
content = re.sub(r'^(  provider: ).*$', r'\g<1>openai-api',       content, count=1, flags=re.MULTILINE)
content = re.sub(r'^(  base_url: ).*$', r'\g<1>http://host.docker.internal:' + port + r'/v1', content, count=1, flags=re.MULTILINE)
content = re.sub(r'^(  api_mode: ).*$', r'\g<1>chat_completions', content, count=1, flags=re.MULTILINE)
# MLX quantized models often report <64K context; override Hermes's minimum check.
# Override Hermes's 64K minimum context check — MLX quantized models often report
# smaller windows, but work fine within their actual limit.
if re.search(r'^  context_length:', content, flags=re.MULTILINE):
    content = re.sub(r'^(  context_length: ).*$', r'\g<1>65536', content, count=1, flags=re.MULTILINE)
else:
    content = re.sub(r'^(  api_mode: chat_completions)$', r'\1\n  context_length: 65536', content, count=1, flags=re.MULTILINE)

with open(config_path, 'w') as f:
    f.write(content)

print(f"  model.default  → {model}")
print(f"  model.provider → openai-api")
print(f"  model.base_url → http://host.docker.internal:{port}/v1")
print(f"  model.api_mode → chat_completions")
PYEOF

info "Updated $CONFIG"

# ── Ensure OPENAI_API_KEY is set ──────────────────────────────────────────────
# oMLX doesn't require auth; Hermes needs a non-empty key to make API calls.

if [[ -f "$ENV_FILE" ]]; then
    if grep -qE '^OPENAI_API_KEY=.+' "$ENV_FILE"; then
        warn "OPENAI_API_KEY already set in $ENV_FILE — leaving it unchanged."
    else
        sed -i.bak '/^OPENAI_API_KEY=/d' "$ENV_FILE"
        echo "OPENAI_API_KEY=local" >> "$ENV_FILE"
        info "Set OPENAI_API_KEY=local in $ENV_FILE (placeholder — oMLX doesn't require auth)."
    fi
else
    warn ".env not found at $ENV_FILE; skipping OPENAI_API_KEY update."
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
info "Agent is now configured to use oMLX model: $OMLX_MODEL"
echo ""
echo "  Run  make restart  to apply the new config."
echo ""
