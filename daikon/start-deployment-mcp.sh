#!/usr/bin/env bash
set -euo pipefail

root="${ENGINEER_ROOT:-$HOME/cbio-engineer}"
integration="$root/data/cbio-deployment"
state="$root/deployment-mcp-state"
socket=/var/run/docker.sock
image=cbio-deployment-mcp:1ee6d20

docker image inspect "$image" >/dev/null
test -S "$socket"

# Match Engineer's UID so the socket and staged local inputs stay private.
docker run -d --name hermes-cbio-deployment-mcp --restart unless-stopped \
  --init --network host --cpus 1 --memory 512m --memory-swap 512m \
  --log-opt max-size=10m --log-opt max-file=3 \
  --user 10000:10000 --group-add "$(stat -c %g "$socket")" \
  --mount "type=bind,src=$socket,dst=$socket" \
  --mount "type=bind,src=$root/deployment-mcp-runtime,dst=/runtime,readonly" \
  --mount "type=bind,src=$integration,dst=/ipc" \
  --mount "type=bind,src=$state,dst=$state" \
  --mount "type=bind,src=$root/work/checkouts,dst=$root/work/checkouts,readonly" \
  --mount "type=bind,src=$root/work/test-data,dst=$root/work/test-data,readonly" \
  -e "CBIO_MCP_HOME=$state" -e CBIO_RUNTIME=docker \
  --entrypoint bun "$image" /runtime/deployment-mcp-relay.mjs server /ipc/mcp.sock
