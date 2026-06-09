#!/bin/sh
# Docker entrypoint wrapper for Hermes Agent.
#
# Purpose: Grant the hermes user access to the host Docker socket
#          without hardcoding the Docker group GID or using
#          Docker Compose's group_add (which gets dropped by gosu).
#
# How it works:
#   1. Detect the Docker socket's group GID on the host
#   2. Create a matching group in /etc/group if needed
#   3. Add the hermes user to that group
#   4. Hand off to the real Hermes entrypoint
#
# This runs as root (container default), before gosu drops privileges.
set -e

DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)

if ! getent group "$DOCKER_GID" >/dev/null 2>&1; then
    groupadd -g "$DOCKER_GID" docker
fi

# Don't hardcode the group to 'docker' -- it's possible that DOCKER_GID
# may exist on the host but is owned by a different name, eg. 'staff'
DOCKER_GROUP=$(getent group "$DOCKER_GID" | cut -d: -f1)
usermod -aG "$DOCKER_GROUP" hermes

exec /opt/hermes/docker/entrypoint.sh "$@"
