#!/bin/bash
# Builds dist/Magic2015-32-bit.apk: the game itself, patched, for devices that run 32-bit ARM code
# (armeabi-v7a). No ZettaBridge, so it runs natively; the 64-bit-only build is port/build.sh.
#
#   port/build-x32.sh
#
# It carries the port's game fixes: the libDuels.so patches, the Bluetooth override, the promo
# removal and the starting profile (port/tools.py native-apk). The package stays
# com.stainlessgames.D15, so the game reads its OBB from
# Android/obb/com.stainlessgames.D15/main.4959.com.stainlessgames.D15.obb, which is not bundled.
#
# Inputs: input/magic-2015.apk and keys/magic-2015-mod.keystore with its password in
# keys/magic-2015-mod.keystore.pass (or KEYSTORE_PASS). Intermediates go to build/x32/.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
OUT=$ROOT/build/x32
SDK=${ANDROID_HOME:-$HOME/.android-sdk}
BT=$SDK/build-tools/36.0.0
ANDROID_JAR=$SDK/platforms/android-35/android.jar
GAME_APK=$ROOT/input/magic-2015.apk
KEYSTORE=$ROOT/keys/magic-2015-mod.keystore
KEYSTORE_PASS_FILE=$KEYSTORE.pass
FINAL=$ROOT/dist/Magic2015-32-bit.apk

for f in "$GAME_APK" "$KEYSTORE" "$ANDROID_JAR" "$BT/apksigner" "$BT/d8" "$BT/zipalign"; do
    [ -e "$f" ] || { echo "missing $f" >&2; exit 1; }
done
if [ -z "${KEYSTORE_PASS:-}" ]; then
    [ -f "$KEYSTORE_PASS_FILE" ] || { echo "set KEYSTORE_PASS or create $KEYSTORE_PASS_FILE" >&2; exit 1; }
    KEYSTORE_PASS=$(cat "$KEYSTORE_PASS_FILE")
fi
rm -rf "$OUT" && mkdir -p "$OUT/lib" "$OUT/overrides/classes" "$(dirname "$FINAL")"

echo "== 1/4 libDuels.so"
unzip -p "$GAME_APK" lib/armeabi-v7a/libDuels.so > "$OUT/libDuels.orig.so"
python3 "$HERE/tools.py" patch-libduels "$OUT/libDuels.orig.so" "$OUT/lib/libDuels.so"

echo "== 2/4 Java overrides"
# Android's own OpenSL ES serves the game here, so unlike build.sh there is no silent stub.
javac -source 8 -target 8 -Xlint:-options -bootclasspath "$ANDROID_JAR" \
    -d "$OUT/overrides/classes" $(find "$HERE/overrides" -name '*.java')
"$BT/d8" --release --min-api 21 --lib "$ANDROID_JAR" \
    --output "$OUT/overrides" $(find "$OUT/overrides/classes" -name '*.class')

echo "== 3/4 game APK"
python3 "$HERE/tools.py" native-apk "$GAME_APK" "$OUT/unsigned.apk" "$OUT/lib" "$OUT/overrides/classes.dex"
"$BT/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"

echo "== 4/4 sign"
KEYSTORE_PASS=$KEYSTORE_PASS "$BT/apksigner" sign --ks "$KEYSTORE" --ks-pass env:KEYSTORE_PASS \
    --ks-key-alias mod --key-pass env:KEYSTORE_PASS --v4-signing-enabled false \
    --out "$FINAL" "$OUT/aligned.apk"
rm -f "$OUT/unsigned.apk" "$OUT/aligned.apk"
"$BT/apksigner" verify "$FINAL"
"$BT/zipalign" -c -p 4 "$FINAL" >/dev/null || { echo "zipalign check failed" >&2; exit 1; }
ls -la "$FINAL"
