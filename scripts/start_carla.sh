#!/usr/bin/env bash
# Keep in foreground so the caller owns the process lifetime. No public ports.
set -euo pipefail
FLYHARD_CARLA_ROOT="${FLYHARD_CARLA_ROOT:-/tmp/flyhard-carla}"
FLYHARD_RUNTIME_DIR=/tmp/flyhard-carla-runtime
if [ "$(id -u)" = 0 ]; then
  id ubuntu >/dev/null
  mkdir -p "$FLYHARD_CARLA_ROOT/CarlaUE4/Saved" "$FLYHARD_RUNTIME_DIR"
  chown ubuntu:ubuntu "$FLYHARD_CARLA_ROOT/CarlaUE4/Saved" "$FLYHARD_RUNTIME_DIR"
  chmod 700 "$FLYHARD_RUNTIME_DIR"
  cd "$FLYHARD_CARLA_ROOT"
  exec runuser -u ubuntu -- env DISPLAY= XDG_RUNTIME_DIR="$FLYHARD_RUNTIME_DIR" \
    ./CarlaUE4.sh -RenderOffScreen -nosound -quality-level=Low -carla-rpc-port=2000 -unattended
else
  mkdir -p "$FLYHARD_RUNTIME_DIR"
  chmod 700 "$FLYHARD_RUNTIME_DIR"
  cd "$FLYHARD_CARLA_ROOT"
  DISPLAY= XDG_RUNTIME_DIR="$FLYHARD_RUNTIME_DIR" exec ./CarlaUE4.sh \
    -RenderOffScreen -nosound -quality-level=Low -carla-rpc-port=2000 -unattended
fi
