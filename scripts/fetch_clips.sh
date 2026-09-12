#!/usr/bin/env bash
# Pull the clip library, the finished edits and their receipts off a pod.
#
# Raw takes come down alongside the edits so the cut can be changed later without
# re-running CARLA: plan_film.py and assemble_film.py work entirely from what this
# copies. Uses rsync so a repeated run only transfers what changed.
set -euo pipefail
CONFIG=${1:?usage: fetch_clips.sh <ssh-config> <host> [destination]}
HOST=${2:?usage: fetch_clips.sh <ssh-config> <host> [destination]}
DEST=${3:-$HOME/Desktop/claude-latest-videos}
REMOTE=/workspace/flyhard

mkdir -p "$DEST"
rsync -az --info=progress2 --no-owner --no-group \
  -e "ssh -F $CONFIG" \
  --include='*/' \
  --include='*.mp4' --include='*.json' --include='*.txt' \
  --exclude='*' \
  "$HOST:$REMOTE/runs/clips/" "$DEST/clips/"

for edit in film film-sponsored; do
  if ssh -F "$CONFIG" "$HOST" "test -d $REMOTE/runs/$edit"; then
    rsync -az --no-owner --no-group -e "ssh -F $CONFIG" \
      "$HOST:$REMOTE/runs/$edit/" "$DEST/$edit/"
  fi
done

rsync -az --no-owner --no-group -e "ssh -F $CONFIG" \
  --include='*/' --include='metrics.json' --include='site.json' --include='config.json' \
  --exclude='*' \
  "$HOST:$REMOTE/runs/" "$DEST/benchmarks/" || true

find "$DEST" -name '.DS_Store' -delete 2>/dev/null || true
echo
echo "Downloaded to $DEST"
du -sh "$DEST"/* 2>/dev/null || true
