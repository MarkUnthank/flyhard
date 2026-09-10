#!/bin/bash
# Run as builder on the private durable volume, never in a public image build.
set -eo pipefail
phase=${1:-setup}
case "$phase" in setup|project-files|compile) ;; *) echo 'Phase must be setup, project-files, or compile'; exit 2 ;; esac
build_root=/workspace/flyhard-build
engine_root=$build_root/UnrealEngine_4.26
mkdir -p "$build_root/logs"
rm -f "$build_root/engine-result.json"
exec > >(tee -a "$build_root/logs/engine-build.log") 2>&1
trap 'code=$?; printf "{\"exit_code\":%s,\"finished_epoch\":%s}\n" "$code" "$(date +%s)" > "$build_root/engine-result.json"' EXIT
date -u
test "$(id -u)" != 0
if [ "$phase" = setup ]; then
  sudo bash "$build_root/downloads/install_dependencies.sh"
fi
cd "$engine_root"
test "$(git rev-parse HEAD)" = e9d9e60c85f643e10eeb03f42f61554d18dcb30f
if ! git apply --reverse --check "$build_root/downloads/engine-lifecycle.patch" >/dev/null 2>&1; then
  git apply --check "$build_root/downloads/engine-lifecycle.patch"
  git apply "$build_root/downloads/engine-lifecycle.patch"
fi
toolchain=v17_clang-10.0.1-centos7.tar.gz
if [ "$phase" = setup ] && [ -f "$build_root/downloads/$toolchain" ] && [ ! -f "$build_root/downloads/$toolchain.aria2" ]; then
  gzip -t "$build_root/downloads/$toolchain"
  mkdir -p .git/ue4-sdks
  ln -sf "$build_root/downloads/$toolchain" ".git/ue4-sdks/$toolchain"
fi
mkdir -p "$HOME/.config/Unreal Engine/UnrealBuildTool"
cat > "$HOME/.config/Unreal Engine/UnrealBuildTool/BuildConfiguration.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<Configuration xmlns="https://www.unrealengine.com/BuildConfiguration">
  <ParallelExecutor><MaxProcessorCount>16</MaxProcessorCount></ParallelExecutor>
  <BuildConfiguration><MaxParallelActions>16</MaxParallelActions></BuildConfiguration>
  <SourceFileWorkingSet><Provider>None</Provider></SourceFileWorkingSet>
  <ProjectFileGenerator>
    <Format>Make</Format>
    <bGenerateIntelliSenseData>false</bGenerateIntelliSenseData>
  </ProjectFileGenerator>
</Configuration>
XML
if [ "$phase" = setup ]; then
printf 'dependencies\n' > "$build_root/engine-stage.txt"
# The pinned upstream scripts predate HTTPS-by-default. Retain identical
# dependency hashes and paths while using the CDN's encrypted endpoint.
python3 - <<'PY'
from pathlib import Path
for name in ['Engine/Build/Commit.gitdeps.xml', 'Engine/Build/BatchFiles/Linux/SetupToolchain.sh']:
    path = Path(name)
    path.write_text(path.read_text().replace('http://cdn.unrealengine.com/', 'https://cdn.unrealengine.com/'))
PY
# Setup.sh adds --prompt itself; combining it with --force makes this pinned
# GitDependencies version print usage and incorrectly return success.
# Use Ubuntu's maintained Mono and CA store for HTTPS dependency downloads.
# The bundled 2019 Mono fails TLS against the current CDN. Keep the bundled
# runtime for project generation and compilation by scoping this override.
UE_USE_SYSTEM_MONO=1 ./Setup.sh --threads=16 --exclude=Win32 --exclude=Win64 --exclude=Mac \
  --exclude=Android --exclude=IOS --exclude=TVOS --exclude=HoloLens --exclude=HTML5
fi
test -f .ue4dependencies
test -f Engine/Build/OneTimeSetupPerformed
if [ "$phase" != compile ]; then
printf 'project-files\n' > "$build_root/engine-stage.txt"
./GenerateProjectFiles.sh -Makefile -NoIntelliSense
fi
test -f Makefile
printf 'compiling\n' > "$build_root/engine-stage.txt"
# UnrealBuildTool schedules compilation internally; do not use make -j.
make UE4Editor ShaderCompileWorker UnrealPak CrashReportClient
test -x Engine/Binaries/Linux/UE4Editor
sha256sum Engine/Binaries/Linux/UE4Editor Engine/Binaries/Linux/ShaderCompileWorker \
  Engine/Binaries/Linux/UnrealPak > "$build_root/engine-binaries.sha256"
printf 'compiled\n' > "$build_root/engine-stage.txt"
date -u
