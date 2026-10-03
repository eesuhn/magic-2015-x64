# Magic 2015 on 64-bit-only Android 16

Runs **Magic 2015 – Duels of the Planeswalkers** (v1.4.4959, `com.stainlessgames.D15`) on phones
whose CPUs cannot run 32-bit code at all, such as the OnePlus 15 or Pixel 7 and later on
Android 16. The game ships only `armeabi-v7a`/`x86` native code, so it cannot be installed there
(`INSTALL_FAILED_NO_MATCHING_ABIS`); raising its `targetSdkVersion` is not enough.

The build produces **one APK** (`dist/Magic2015-Android16.apk`, ~1.6 GB). It is
[ZettaBridge](https://github.com/ZailoxTT/ZettaBridge), which translates the game's 32-bit ARM
code to 64-bit at run time, with the game and its OBB bundled inside and a set of fixes so this
particular game works. Install it like any APK; the first launch sets the game up in a few
seconds.

## What is fixed

| Area | Problem | Fix |
| --- | --- | --- |
| Runtime | 32-bit-only game on a 64-bit-only CPU | ZettaBridge (Dynarmic ARM32 → ARM64 translation) |
| ZettaBridge | NativeActivity start, looper idents, `AInputQueue_attachLooper` 5th argument, EGL handle maps, AAssetDir, `sched_*` syscalls, report writer stalls | `zettabridge/` |
| Audio | No `libOpenSLES.so` for 32-bit guests | Silent stub (`port/sles/`); only the intro videos use it, music and effects play |
| Graphics | Game uses a pointer as an EGL config when the GPU lacks RGB565 | 1-byte patch in `libDuels.so` |
| Size | A 1.5 GB OBB copy doubled the install size | OBB served from inside the APK through a file window; a sparse placeholder satisfies the game's size check |
| Expansions | The repack's unlock snapshot was restored into the wrong data folder | Applied to the game's own data on first launch (purchases merged, progress kept) |
| Promo | The source APK (an androeed.ru repack) shows the site's dialog and toast | Disabled in `classes.dex` |
| Navigation | Back gesture ignored; bars blocked gestures; two Recents entries | Back events paced, gesture-friendly fullscreen, single task |

**Not fixable:** Google sign-in, Google+ and Facebook login. The APK is a repack signed with a
different key, and Google+ no longer exists. The intro videos are silent.

## Requirements

- macOS on Apple Silicon (the scripts use the macOS NDK and Homebrew).
- Android SDK at `~/.android-sdk` (or `ANDROID_HOME`) with build-tools 36.0.0, platform
  `android-35` and NDK `29.0.14206865`. Java 17+ is also needed.
- Homebrew packages: `cmake`, `ninja`, `boost`.
- The game files, which are **not** in this repository:
  - `input/magic-2015.apk`: the androeed.ru build of v1.4.4959. The patches check its exact
    bytes and refuse anything else.
  - `input/com.stainlessgames.D15/main.4959.com.stainlessgames.D15.obb`
- A signing key, `keys/magic-2015-mod.keystore` (alias `mod`), with its password in
  `keys/magic-2015-mod.keystore.pass`. Use the **same key for every update**, or Android will
  refuse the update and you would have to uninstall, losing your progress. To create one:

  ```
  keytool -genkeypair -keystore keys/magic-2015-mod.keystore -alias mod -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Local Mod"
  ```

## Build

```
port/setup.sh            # once: fetch Dynarmic (pinned, patched) and the arm32 sysroot into zettabridge/
port/java-truststore.sh  # only behind TLS inspection (e.g. Cloudflare Gateway), see below
port/build.sh            # → dist/Magic2015-Android16.apk  (SKIP_GUEST=1 to reuse the guest build)
```

A full build takes a few minutes. Gradle downloads its plugins on the first run. On a network that
inspects TLS, Java rejects the proxy's certificates; `port/java-truststore.sh` builds a trust
store from the macOS System keychain, and `build.sh` uses it automatically.

## Install

```
adb install -r dist/Magic2015-Android16.apk
```

The app appears as **Magic 2015**. Updating over an earlier build keeps your progress; the
install needs about 1.6 GB free while it runs.

## Layout

```
zettabridge/         ZettaBridge itself (from upstream d6066b9) with all the fixes above
  third_party/dynarmic, sysroot   (ignored) fetched by port/setup.sh
  build/             (ignored) native build
port/
  setup.sh           fetches Dynarmic and the sysroot
  build.sh           builds dist/Magic2015-Android16.apk
  tools.py           game APK patches (libDuels, classes.dex) and APK packaging/alignment
  sles/sles_stub.c   silent OpenSL ES for the 32-bit guest
  java-truststore.sh optional, for TLS-inspecting networks
input/   (ignored)   the game APK and OBB
keys/    (ignored)   signing key
build/, dist/ (ignored) intermediates and the final APK
tools/   (ignored)   AXML-Editor, used for the first manifest experiment
```

## Licences

ZettaBridge is the project owner's own code. Dynarmic and its bundled libraries keep their own
licences (fetched with them). Magic 2015 belongs to Wizards of the Coast and Stainless Games; no
game files are included here, and builds are for personal use only.
