#!/usr/bin/env bash
# Keep in foreground so the caller owns the process lifetime. No public ports.
set -euo pipefail
FLYHARD_CARLA_ROOT="${FLYHARD_CARLA_ROOT:-/tmp/flyhard-carla}"
FLYHARD_RUNTIME_DIR=/tmp/flyhard-carla-runtime
FLYHARD_CARLA_QUALITY="${FLYHARD_CARLA_QUALITY:-Epic}"
case "$FLYHARD_CARLA_QUALITY" in Low|Epic) ;; *) exit 2 ;; esac
if [ "$(id -u)" = 0 ]; then
  id ubuntu >/dev/null
  mkdir -p "$FLYHARD_CARLA_ROOT/CarlaUE4/Saved" "$FLYHARD_RUNTIME_DIR"
  if [ "${FLYHARD_RUNTIME_LAYOUT:-packaged}" = network-volume ]; then
    # Runpod's network filesystem manages ownership itself and rejects chown.
    # Check the permissions CARLA actually needs instead of changing ownership.
    runuser -u ubuntu -- test -w "$FLYHARD_CARLA_ROOT/CarlaUE4/Saved"
    runuser -u ubuntu -- test -x "$FLYHARD_CARLA_ROOT"
  else
    chown ubuntu:ubuntu "$FLYHARD_CARLA_ROOT/CarlaUE4/Saved"
  fi
  chown ubuntu:ubuntu "$FLYHARD_RUNTIME_DIR"
  chmod 700 "$FLYHARD_RUNTIME_DIR"
  cd "$FLYHARD_CARLA_ROOT"
  exec runuser -u ubuntu -- env DISPLAY= XDG_RUNTIME_DIR="$FLYHARD_RUNTIME_DIR" \
    ./CarlaUE4.sh -RenderOffScreen -nosound -quality-level="$FLYHARD_CARLA_QUALITY" -carla-rpc-port=2000 -unattended
else
  mkdir -p "$FLYHARD_RUNTIME_DIR"
  chmod 700 "$FLYHARD_RUNTIME_DIR"
  cd "$FLYHARD_CARLA_ROOT"
  DISPLAY= XDG_RUNTIME_DIR="$FLYHARD_RUNTIME_DIR" exec ./CarlaUE4.sh \
    -RenderOffScreen -nosound -quality-level="$FLYHARD_CARLA_QUALITY" -carla-rpc-port=2000 -unattended
fi
