#!/usr/bin/env bash
# Downloads the official package. A local container path avoids slow NFS unpacking.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data work
FLYHARD_CARLA_ROOT="${FLYHARD_CARLA_ROOT:-/tmp/flyhard-carla}"
FLYHARD_CARLA_ARCHIVE="data/CARLA_0.9.16.tar.gz"
if [ ! -f "$FLYHARD_CARLA_ARCHIVE" ]; then
  curl --fail --location --retry 2 --continue-at - --user-agent 'Mozilla/5.0 Flyhard/0.1' \
    'https://downloads.carlasim.com/Linux/CARLA_0.9.16.tar.gz' -o "$FLYHARD_CARLA_ARCHIVE.part"
  mv "$FLYHARD_CARLA_ARCHIVE.part" "$FLYHARD_CARLA_ARCHIVE"
fi
printf '%s  %s\n' '09e3ebb28df17962f0c997e66f4b914ad5ea6f1d6a6dbbf13c9f87eb38346d57' "$FLYHARD_CARLA_ARCHIVE" | sha256sum --check
mkdir -p "$FLYHARD_CARLA_ROOT"
tar --no-same-owner -xzf "$FLYHARD_CARLA_ARCHIVE" -C "$FLYHARD_CARLA_ROOT"
test -x "$FLYHARD_CARLA_ROOT/CarlaUE4.sh"
.venv/bin/pip install -c requirements/runpod-pilot.txt carla==0.9.16
