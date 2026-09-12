#!/bin/bash
# Resume the official pinned asset archive and retain it for future builders.
set -euo pipefail
build_root=/workspace/flyhard-build
content_id=20250912_2171890
content_sha256=997d8cb2dde7f3757d789b898ddd0e33bbb5a0f3097ee2b0936971c585d007b5
archive=$build_root/content/$content_id.tar.gz
destination=$build_root/carla/Unreal/CarlaUE4/Content/Carla
mkdir -p "$build_root/logs" "$(dirname "$archive")" "$destination"
exec 9>"$build_root/content/.prepare.lock"
flock -n 9 || { echo 'Content preparation is already running'; exit 1; }
exec > >(tee -a "$build_root/logs/content-prepare.log") 2>&1
trap 'code=$?; printf "{\"exit_code\":%s,\"finished_epoch\":%s}\n" "$code" "$(date +%s)" > "$build_root/content-result.json"' EXIT
if [ "$(cat "$destination/.version" 2>/dev/null || true)" = "$content_id" ] \
  && [ -f "$build_root/content/extracted.sha256" ]; then
  (cd "$destination" && sha256sum -c "$build_root/content/extracted.sha256")
  echo 'Pinned CARLA content already extracted'
  exit 0
fi
archive_valid=0
if [ -f "$archive" ] \
  && [ "$(stat -c %s "$archive" 2>/dev/null || true)" = 21567002106 ] \
  && gzip -t "$archive" 2>/dev/null; then
  if [ -f "$build_root/content/archive.sha256" ]; then
    (cd "$build_root/content" && sha256sum -c archive.sha256 >/dev/null 2>&1) && archive_valid=1
  else
    (cd "$build_root/content" && printf '%s  %s\n' "$content_sha256" "$(basename "$archive")" \
      | sha256sum -c - >/dev/null 2>&1) && archive_valid=1
  fi
fi
if [ "$archive_valid" = 0 ]; then
  # A complete but damaged file must not be handed to aria2 as a valid cache.
  # Preserve an in-progress transfer so aria2 can resume it safely.
  if [ ! -f "$archive.aria2" ]; then
    rm -f "$archive"
  fi
  "${FLYHARD_ARIA2:-aria2c}" --continue=true --max-connection-per-server=16 --split=16 \
    --min-split-size=16M --file-allocation=none --auto-file-renaming=false \
    --max-tries=0 --retry-wait=5 --connect-timeout=15 --timeout=60 \
    --summary-interval=60 --dir="$(dirname "$archive")" --out="$(basename "$archive")" \
    "https://carla-assets.s3.us-east-005.backblazeb2.com/$content_id.tar.gz"
else
  echo 'Reusing verified content archive without network access'
fi
test ! -f "$archive.aria2"
test "$(stat -c %s "$archive")" = 21567002106
gzip -t "$archive"
(cd "$build_root/content" && printf '%s  %s\n' "$content_sha256" "$(basename "$archive")" > archive.sha256.partial \
  && sha256sum -c archive.sha256.partial && mv archive.sha256.partial archive.sha256)
printf 'extracting\n' > "$build_root/content-stage.txt"
tar --no-same-owner -xzf "$archive" -C "$destination"
test -f "$destination/Maps/Town03.umap"
(cd "$destination" && sha256sum Maps/Town03.umap) > "$build_root/content/extracted.sha256.partial"
mv "$build_root/content/extracted.sha256.partial" "$build_root/content/extracted.sha256"
printf '%s\n' "$content_id" > "$destination/.version"
printf 'extracted\n' > "$build_root/content-stage.txt"
