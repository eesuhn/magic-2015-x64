#!/bin/bash
# Recreates vendor/ZettaBridge: upstream at a pinned commit, plus this project's changes
# (port/zettabridge.patch), the Dynarmic submodule with ZettaBridge's own Dynarmic patches, and
# the arm32 guest sysroot taken from ZettaBridge's v0.1.0 release APK.
#
#   port/setup.sh          create vendor/ZettaBridge (refuses to touch an existing one)
#   port/setup.sh --force  delete and recreate it
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
ZB=$ROOT/vendor/ZettaBridge
REPO=https://github.com/ZailoxTT/ZettaBridge.git
BASE=d6066b9                       # upstream main, 2026-10-01
SYSROOT_APK_URL=https://github.com/ZailoxTT/ZettaBridge/releases/download/v0.1.0/ZettaBridge-0.1.0.apk
SYSROOT_APK_SHA256=75b95cc6b1aa567d8168dd02034af5d9bb7c8191fbe08144dfdda6ee79c65c41

if [ -e "$ZB" ]; then
    [ "${1:-}" = --force ] || { echo "$ZB exists; use --force to recreate it" >&2; exit 1; }
    rm -rf "$ZB"
fi
mkdir -p "$ROOT/vendor"

echo "== ZettaBridge $BASE + port/zettabridge.patch"
git clone -q "$REPO" "$ZB"
git -C "$ZB" checkout -q "$BASE"
git -C "$ZB" apply --whitespace=nowarn "$HERE/zettabridge.patch"

echo "== Dynarmic submodule + ZettaBridge's Dynarmic patches"
git -C "$ZB" submodule update -q --init
git -C "$ZB/third_party/dynarmic" apply ../patches/dynarmic-0001-thumb32-armv8.patch \
    ../patches/dynarmic-0002-asimd-narrowing.patch

echo "== arm32 guest sysroot (from the v0.1.0 release APK)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/zb.apk" "$SYSROOT_APK_URL"
echo "$SYSROOT_APK_SHA256  $tmp/zb.apk" | shasum -a 256 -c - >/dev/null
unzip -q "$tmp/zb.apk" 'assets/zb/sysroot/*' -d "$tmp/x"
mkdir -p "$ZB/sysroot"
cp -R "$tmp/x/assets/zb/sysroot/system" "$ZB/sysroot/"

echo "vendor/ZettaBridge ready"
