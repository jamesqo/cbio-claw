#!/usr/bin/env bash
set -euo pipefail
root="${ENGINEER_ROOT:-$HOME/cbio-engineer}"
image='nousresearch/hermes-agent:v2026.6.5@sha256:9ad3b04ec916ea2c2da22358fd43b024c788d74073210695af88bfc2e63869b4'
test -d "$root/data"
test -f "$root/runtime.env"
# The old listener must be stopped before executing this script.
docker run -d --name hermes-cbio-engineer --restart unless-stopped \
  --cpus 2 --memory 4g --memory-swap 4g \
  --log-opt max-size=10m --log-opt max-file=3 \
  --env-file "$root/runtime.env" \
  -e HERMES_HOME=/opt/data -e HERMES_UID=10000 -e HERMES_GID=10000 \
  -e CBIO_MAILING_REPLIES=off -e HERMES_HOME_CHANNEL_REMINDER=false \
  --mount "type=bind,src=$root/data,dst=/opt/data" \
  --mount "type=bind,src=$root/work,dst=/Users/jko/Code/cbio-engineer/work" \
  --mount "type=bind,src=$root/vault,dst=/opt/cbio-claw/vault,readonly" \
  --mount "type=bind,src=$root/data/runtime-patches/gateway-run.py,dst=/opt/hermes/gateway/run.py,readonly" \
  "$image" hermes -p engineering gateway run
