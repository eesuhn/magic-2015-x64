#!/bin/bash
# Fetches what zettabridge/ needs but does not track: the Dynarmic JIT (third-party, pinned,
# with ZettaBridge's own patches from zettabridge/third_party/patches) and the arm32 guest
# sysroot taken from ZettaBridge's v0.1.0 release APK.
#
#   port/setup.sh          fetch whatever is missing
#   port/setup.sh --force  delete both and fetch them again
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ZB=$(dirname "$HERE")/zettabridge
DYNARMIC=$ZB/third_party/dynarmic
DYNARMIC_REPO=https://github.com/Vita3K/dynarmic.git
DYNARMIC_REV=86458a0bd369d63ba4c2ef812cacbb6c9080c065
SYSROOT_APK_URL=https://github.com/ZailoxTT/ZettaBridge/releases/download/v0.1.0/ZettaBridge-0.1.0.apk
SYSROOT_APK_SHA256=75b95cc6b1aa567d8168dd02034af5d9bb7c8191fbe08144dfdda6ee79c65c41

if [ "${1:-}" = --force ]; then
    chmod -R u+w "$DYNARMIC" 2>/dev/null || true
    rm -rf "$DYNARMIC" "$ZB/sysroot"
fi

if [ ! -e "$DYNARMIC" ]; then
    echo "== Dynarmic ${DYNARMIC_REV:0:8} + ZettaBridge's Dynarmic patches"
    git clone -q "$DYNARMIC_REPO" "$DYNARMIC"
    git -C "$DYNARMIC" checkout -q "$DYNARMIC_REV"
    git -C "$DYNARMIC" apply ../patches/dynarmic-0001-thumb32-armv8.patch \
        ../patches/dynarmic-0002-asimd-narrowing.patch
fi

if [ ! -e "$ZB/sysroot/system" ]; then
    echo "== arm32 guest sysroot (from the v0.1.0 release APK)"
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    curl -fsSL -o "$tmp/zb.apk" "$SYSROOT_APK_URL"
    echo "$SYSROOT_APK_SHA256  $tmp/zb.apk" | shasum -a 256 -c - >/dev/null
    unzip -q "$tmp/zb.apk" 'assets/zb/sysroot/*' -d "$tmp/x"
    mkdir -p "$ZB/sysroot"
    cp -R "$tmp/x/assets/zb/sysroot/system" "$ZB/sysroot/"
fi

echo "zettabridge/ ready"
