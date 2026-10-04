# Magic 2015 on 64-bit

<img src="https://github.com/user-attachments/assets/b723098b-d015-430f-a0fd-9db558a3576b" alt="screenshot" width="800">

Runs **Magic 2015 – Duels of the Planeswalkers** (v1.4.4959, `com.stainlessgames.D15`) on phones
whose CPUs cannot run 32-bit code at all. The game ships only `armeabi-v7a`/`x86` native code, so it cannot be installed there
(`INSTALL_FAILED_NO_MATCHING_ABIS`); raising its `targetSdkVersion` is not enough.

The build produces **one APK** (`dist/Magic2015-64-bit.apk`, ~1.6 GB). It is
[ZettaBridge](https://github.com/ZailoxTT/ZettaBridge), which translates the game's 32-bit ARM
code to 64-bit at run time, with the game and its OBB bundled inside and a set of fixes so this
particular game works.

> **[Latest release: v1.1.1](https://github.com/eesuhn/magic-2015-x64/releases/latest)**
>
> Releases are **source only**. The APK contains the copyrighted game, so it is not distributed:
> build it yourself as described below, for personal use.

## What is fixed

ZettaBridge runs the game's 32-bit code, and the port fixes what broke on top of that:
- NativeActivity and EGL support in ZettaBridge;
- missing OpenSL audio and a bad EGL config;
- the doubled install size;
- locked expansions;
- the repack's promo dialog;
- back navigation;
- Bluetooth for ad-hoc multiplayer.

It also opens multiplayer without first beating the Innistrad boss. New installs start with every
card unlocked and a ready-made deck.

See [CHANGELOG.md](CHANGELOG.md) for each change.

## Requirements

- macOS on Apple Silicon (the scripts use the macOS NDK and Homebrew).
- Android SDK at `~/.android-sdk` (or `ANDROID_HOME`) with build-tools 36.0.0, platform
  `android-35` and NDK `29.0.14206865`. Java 17+ is also needed.
- Homebrew packages: `cmake`, `ninja`, `boost`, `git-lfs`.
- The game files, stored in **Git LFS** (`.gitattributes` tracks `input/**`; git holds only
  pointers). After cloning, `git lfs pull` fetches them:
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
port/build.sh            # → dist/Magic2015-64-bit.apk  (SKIP_GUEST=1 to reuse the guest build)
```

A full build takes a few minutes. Gradle downloads its plugins on the first run. On a network that
inspects TLS, Java rejects the proxy's certificates; `port/java-truststore.sh` builds a trust
store from the macOS System keychain, and `build.sh` uses it automatically.

## Install

```
adb install -r dist/Magic2015-64-bit.apk
```

The app appears as **Magic 2015**. Updating over an earlier build keeps your progress; the
install needs about 1.6 GB free while it runs.

On first launch the app asks for **Nearby devices**, which ad-hoc (Bluetooth) multiplayer needs.
Allow it on every phone taking part, and install the same build on each of them. A new install
starts with:
- a profile named "Planewalker";
- every card at its copy limit;
- two decks, "Started" and "Dragonfire".

An existing save is never replaced.

## Decks

`decks/` holds decks built from the game's own card data (`build/cards/`). Each has a `.txt` list
and a `.md` write-up. The `m15-deck-builder` skill for Claude Code (`.claude/skills/`) builds and
checks decks against the game's rules, and puts them in the game:

```
python3 .claude/skills/m15-deck-builder/scripts/deck_check.py decks/rakdos-dragonfire.txt --max-cards 60
python3 .claude/skills/m15-deck-builder/scripts/install_deck.py decks/rakdos-dragonfire.txt --name Dragonfire --adb
```

`install_deck.py` edits an existing save. `--adb` needs `adb root`, so the emulator or a rooted
phone. To give every new install a deck, add it to `STARTING_DECKS` in `port/tools.py` and
rebuild. In-game deck names hold at most 15 characters.

## Layout

```
zettabridge/         ZettaBridge itself (from upstream d6066b9) with the fixes in CHANGELOG.md
  third_party/dynarmic, sysroot   (ignored) fetched by port/setup.sh
  build/             (ignored) native build
port/
  setup.sh           fetches Dynarmic and the sysroot
  build.sh           builds dist/Magic2015-64-bit.apk
  tools.py           game APK patches (libDuels, classes.dex, starting profile), save
                     editing (GameProfile) and APK packaging/alignment
  sles/sles_stub.c   silent OpenSL ES for the 32-bit guest
  overrides/         Java classes that replace the game's own (Bluetooth multiplayer)
  java-truststore.sh optional, for TLS-inspecting networks
build/cards/         card catalog decrypted from the OBB, with its extractor
decks/               decks: a .txt list and a .md write-up each
.claude/skills/m15-deck-builder/   deck-building skill: card_pool, deck_check, install_deck
input/   (Git LFS)   the game APK and OBB
keys/    (ignored)   signing key
build/, dist/ (ignored, except build/cards/) intermediates and the final APK
```
