#!/bin/bash
# Builds dist/Magic2015-64-bit.apk: ZettaBridge with Magic 2015 and its OBB bundled, one install.
#
#   port/build.sh                full build
#   SKIP_GUEST=1 port/build.sh   reuse the arm32 guest build (tools/build_guest.sh is slow-ish)
#
# Inputs: input/magic-2015.apk, input/com.stainlessgames.D15/main.4959.*.obb,
# keys/magic-2015-mod.keystore with its password in keys/magic-2015-mod.keystore.pass (or
# KEYSTORE_PASS), and zettabridge/ with its fetched parts (port/setup.sh). Intermediates go to build/.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
ZB=$ROOT/zettabridge
OUT=$ROOT/build
SDK=${ANDROID_HOME:-$HOME/.android-sdk}
NDK=${NDK:-$SDK/ndk/29.0.14206865}
BT=$SDK/build-tools/36.0.0
LLVM=$NDK/toolchains/llvm/prebuilt/darwin-x86_64/bin
GAME_APK=$ROOT/input/magic-2015.apk
OBB=$ROOT/input/com.stainlessgames.D15/main.4959.com.stainlessgames.D15.obb
KEYSTORE=$ROOT/keys/magic-2015-mod.keystore
KEYSTORE_PASS_FILE=$KEYSTORE.pass
FINAL=$ROOT/dist/Magic2015-64-bit.apk
OBB_VERSION=4959

for f in "$GAME_APK" "$OBB" "$KEYSTORE" "$ZB/third_party/dynarmic/CMakeLists.txt" "$ZB/sysroot/system/bin/linker" "$LLVM/clang" "$BT/apksigner"; do
    [ -e "$f" ] || { echo "missing $f (port/setup.sh fetches dynarmic and the sysroot)" >&2; exit 1; }
done
command -v brew >/dev/null || { echo "Homebrew is needed for the Boost headers" >&2; exit 1; }
if [ -z "${KEYSTORE_PASS:-}" ]; then
    [ -f "$KEYSTORE_PASS_FILE" ] || { echo "set KEYSTORE_PASS or create $KEYSTORE_PASS_FILE" >&2; exit 1; }
    KEYSTORE_PASS=$(cat "$KEYSTORE_PASS_FILE")
fi
# The game names its OBB from the host app's versionCode, so the two must agree.
grep -qE "versionCode = $OBB_VERSION([^0-9]|$)" "$ZB/android/launcher/app/build.gradle.kts" || {
    echo "launcher versionCode must be $OBB_VERSION to match the OBB" >&2; exit 1; }
mkdir -p "$OUT/lib" "$(dirname "$FINAL")"
# Behind TLS inspection, Gradle needs the inspection CA (see port/java-truststore.sh).
if [ -f "$OUT/java-truststore.jks" ]; then
    export JAVA_TOOL_OPTIONS="-Djavax.net.ssl.trustStore=$OUT/java-truststore.jks -Djavax.net.ssl.trustStorePassword=changeit"
fi

echo "== 1/6 silent libOpenSLES.so (arm32)"
"$LLVM/armv7a-linux-androideabi21-clang" -shared -fPIC -O2 -Wall -Wextra -Werror \
    -nostdlib -ffreestanding -fno-builtin -fno-stack-protector -Wl,-soname,libOpenSLES.so \
    -Wl,-z,noexecstack -Wl,--no-undefined -o "$OUT/lib/libOpenSLES.so" "$HERE/sles/sles_stub.c" -lc \
    "$("$LLVM/armv7a-linux-androideabi21-clang" -print-libgcc-file-name)"

echo "== 2/6 game APK for the bundle"
unzip -p "$GAME_APK" lib/armeabi-v7a/libDuels.so > "$OUT/libDuels.orig.so"
python3 "$HERE/tools.py" patch-libduels "$OUT/libDuels.orig.so" "$OUT/lib/libDuels.so"
# Java classes that replace the game's own (port/overrides/), compiled against android.jar.
rm -rf "$OUT/overrides" && mkdir -p "$OUT/overrides/classes"
javac -source 8 -target 8 -Xlint:-options -bootclasspath "$SDK/platforms/android-35/android.jar" \
    -d "$OUT/overrides/classes" $(find "$HERE/overrides" -name '*.java')
"$BT/d8" --release --min-api 26 --lib "$SDK/platforms/android-35/android.jar" \
    --output "$OUT/overrides" $(find "$OUT/overrides/classes" -name '*.class')
python3 "$HERE/tools.py" game-apk "$GAME_APK" "$OUT/game.apk" "$OUT/lib" "$OUT/overrides/classes.dex"

echo "== 3/6 ZettaBridge native code"
cd "$ZB"
if [ "${SKIP_GUEST:-0}" != 1 ]; then
    NDK=$NDK NDK_HOST=darwin-x86_64 sh tools/build_guest.sh >/dev/null 2>&1 || {
        echo "guest build failed; rerun tools/build_guest.sh for details" >&2; exit 1; }
fi
if [ ! -f build/android-arm64/build.ninja ]; then
    mkdir -p build/boost-headers
    ln -sfn "$(brew --prefix)/include/boost" build/boost-headers/boost
    cmake -S . -B build/android-arm64 -G Ninja -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
        -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-29 -DCMAKE_BUILD_TYPE=Release \
        -DZB_BUILD_TESTS=OFF -DBoost_INCLUDE_DIR="$PWD/build/boost-headers" >/dev/null
fi
ninja -C build/android-arm64 zbridge zbproxy | tail -1
sh tools/make_launcher_bundle.sh | tail -1

echo "== 4/6 launcher (release)"
cd "$ZB/android/launcher"
[ -f local.properties ] || echo "sdk.dir=$SDK" > local.properties
rm -rf app/build/outputs/apk/release
if ! ANDROID_HOME=$SDK ./gradlew -q --no-daemon :app:assembleRelease > "$OUT/gradle.log" 2>&1; then
    grep -v 'Picked up JAVA_TOOL' "$OUT/gradle.log" >&2
    echo "launcher build failed (log: $OUT/gradle.log)" >&2
    exit 1
fi
# Unsigned unless ~/.zettabridge/signing.properties exists; either way it is re-signed below.
LAUNCHER=$(ls app/build/outputs/apk/release/app-release*.apk | head -1)

echo "== 5/6 bundle game + OBB"
python3 "$HERE/tools.py" inject "$LAUNCHER" "$OUT/bundled-aligned.apk" \
    "assets/bundle/game.apk=$OUT/game.apk" "assets/bundle/obb/main.$OBB_VERSION.obb=$OBB"

echo "== 6/6 sign"
KEYSTORE_PASS=$KEYSTORE_PASS "$BT/apksigner" sign --ks "$KEYSTORE" --ks-pass env:KEYSTORE_PASS \
    --ks-key-alias mod --key-pass env:KEYSTORE_PASS --alignment-preserved true \
    --v4-signing-enabled false --out "$FINAL" "$OUT/bundled-aligned.apk"
rm -f "$OUT/bundled-aligned.apk"
"$BT/apksigner" verify --min-sdk-version 26 "$FINAL"
python3 "$HERE/tools.py" check-align "$FINAL"
"$BT/zipalign" -c -P 16 4 "$FINAL" >/dev/null || { echo "zipalign check failed" >&2; exit 1; }
ls -la "$FINAL"
