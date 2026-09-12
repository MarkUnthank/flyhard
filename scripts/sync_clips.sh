#!/usr/bin/env bash
# Pull new takes down every few minutes. Two pods have now exited mid-run, and a take
# that only exists on a pod is a take that can be lost; one that is also on the desk is
# not. rsync only moves what changed, so repeating this is cheap.
set -u
CONFIG=${1:?usage: sync_clips.sh <ssh-config> <host> [seconds]}
HOST=${2:?usage: sync_clips.sh <ssh-config> <host> [seconds]}
EVERY=${3:-240}
cd "$(dirname "$0")/.."   # repository root
while true; do
  bash scripts/fetch_clips.sh "$CONFIG" "$HOST" > /dev/null 2>&1 \
    && echo "$(date +%H:%M:%S) synced $(find "$HOME/Desktop/claude-latest-videos/clips" \
         -name take.json 2>/dev/null | wc -l | tr -d ' ') takes" \
    || echo "$(date +%H:%M:%S) sync failed (pod unreachable?)"
  sleep "$EVERY"
done
