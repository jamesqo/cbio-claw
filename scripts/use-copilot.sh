#!/usr/bin/env bash
# Switch the Hermes agent back to GitHub Copilot.
# Usage: use-copilot.sh [model]
#   model: Copilot model to use (default: claude-sonnet-4.6)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$REPO_ROOT/hermes-data/config.yaml"

RED='\033[0;31m'; GREEN='\033[0;32m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[use-copilot]${RESET} $*"; }
error() { echo -e "${RED}[use-copilot]${RESET} $*" >&2; exit 1; }

MODEL="${1:-claude-sonnet-4.6}"
[[ -f "$CONFIG" ]] || error "Config not found: $CONFIG"

# ── Backup ─────────────────────────────────────────────────────────────────────

TS="$(date -u +%Y%m%dT%H%M%SZ)"
cp "$CONFIG" "${CONFIG}.bak-$TS"
info "Backed up config → ${CONFIG}.bak-$TS"

# ── Patch config.yaml ──────────────────────────────────────────────────────────

python3 - "$CONFIG" "$MODEL" <<'PYEOF'
import re, sys

config_path, model = sys.argv[1], sys.argv[2]
with open(config_path) as f:
    content = f.read()

content = re.sub(
    r'^(model:\n  default: ).*$',
    lambda m: m.group(1) + model,
    content, count=1, flags=re.MULTILINE
)
content = re.sub(r'^(  provider: ).*$', r'\g<1>copilot',                        content, count=1, flags=re.MULTILINE)
content = re.sub(r'^(  base_url: ).*$', r'\g<1>https://api.githubcopilot.com',  content, count=1, flags=re.MULTILINE)
content = re.sub(r'^(  api_mode: ).*$', r'\g<1>chat_completions',               content, count=1, flags=re.MULTILINE)

with open(config_path, 'w') as f:
    f.write(content)

print(f"  model.default  → {model}")
print(f"  model.provider → copilot")
print(f"  model.base_url → https://api.githubcopilot.com")
print(f"  model.api_mode → chat_completions")
PYEOF

info "Updated $CONFIG"

echo ""
info "Agent is now configured to use Copilot model: $MODEL"
echo ""
echo "  Run  make restart  to apply the new config."
echo ""
