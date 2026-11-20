#!/usr/bin/env bash
set -euo pipefail

source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root="${ENGINEER_ROOT:-$HOME/cbio-engineer}"
container=hermes-cbio-engineer
image=cbio-deployment-mcp:1ee6d20
profile=/opt/data/profiles/engineering
state="$root/deployment-mcp-state"
runtime="$root/deployment-mcp-runtime"

docker image inspect "$image" >/dev/null
mkdir -p "$state" "$runtime"
chmod 755 "$runtime"
relay_changed=false
if ! cmp -s "$source_dir/deployment-mcp-relay.mjs" "$runtime/deployment-mcp-relay.mjs"; then
  relay_changed=true
fi
install -m 644 "$source_dir/deployment-mcp-relay.mjs" "$runtime/"
docker run --rm --user 0 --mount "type=bind,src=$state,dst=/state" \
  --entrypoint install "$image" -d -m 700 -o 10000 -g 10000 /state

docker exec -u 10000:10000 "$container" mkdir -p /opt/data/cbio-deployment "$profile/skills"
docker exec -i -u 10000:10000 "$container" sh -c \
  'cat > /opt/data/cbio-deployment/deployment-mcp-relay.mjs' \
  < "$source_dir/deployment-mcp-relay.mjs"
tar -C "$source_dir/skills" -cf - cbio-e2e-triage cbio-daikon-deployment | \
  docker exec -i -u 10000:10000 "$container" tar -C "$profile/skills" -xf -

if ! docker container inspect hermes-cbio-deployment-mcp >/dev/null 2>&1; then
  bash "$source_dir/start-deployment-mcp.sh"
elif "$relay_changed"; then
  docker restart hermes-cbio-deployment-mcp
else
  docker start hermes-cbio-deployment-mcp
fi
for attempt in {1..10}; do
  if docker exec -u 10000:10000 "$container" sh -c \
      'test -S /opt/data/cbio-deployment/mcp.sock && test -S /opt/data/cbio-deployment/portal.sock'; then
    docker exec -i -u 10000:10000 "$container" /opt/hermes/.venv/bin/python - \
      < "$source_dir/configure-integrations.py"
    exit
  fi
  sleep 1
done
echo "cBioPortal deployment MCP did not open its Unix socket" >&2
exit 1
