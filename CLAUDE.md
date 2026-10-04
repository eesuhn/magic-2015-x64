# CLAUDE.md

Guidance for Claude Code in this repository. Read README.md first for what the project is and
how it is built.

## The short version

The project builds one APK that runs Magic 2015 (32-bit ARM, NativeActivity, 2015) on
64-bit-only devices, which cannot run 32-bit code at all. It is ZettaBridge, an ARM32→ARM64 translator app, plus our fixes, with
the game and its OBB bundled inside. What is tracked is what we wrote: `zettabridge/` (the
translator, including all the Magic 2015 fixes), `port/` (game patches and build scripts) and
`build/cards/` (the card list extracted from the OBB, with its extractor), `decks/` (decks built
from it, each a `.txt` list plus a `.md` write-up) and `.claude/skills/m15-deck-builder/` (the
skill for building and checking those decks).
`input/` holds the game files (APK and OBB) in Git LFS: `.gitattributes` routes `input/**` to
LFS, so git stores only pointers, and `.gitignore` re-allows `input/*.apk` past its `*.apk` rule.
Everything else is generated, third-party or private, and git-ignored:

- `zettabridge/third_party/dynarmic/` and `zettabridge/sysroot/` come from `port/setup.sh`.
- The rest of `build/`, and `dist/`, come from `port/build.sh`; `zettabridge/build/` holds the native build.
- `keys/` holds the signing key.

## Commands

```
port/setup.sh [--force]        # fetch dynarmic (pinned + zettabridge/third_party/patches) and the sysroot
SKIP_GUEST=1 port/build.sh     # dist/Magic2015-64-bit.apk (drop SKIP_GUEST after guest/ changes)
build/cards/extract_cards.py   # decrypt the OBB's card data into build/cards/ (cards.canonical.json, cards.json, cards.csv, xml/)
port/java-truststore.sh        # once, when Gradle/sdkmanager fail with PKIX errors (TLS inspection)
git lfs install --local && git lfs pull   # fresh clone: input/ holds only pointers until this runs
```

`port/setup.sh`, `git lfs pull`, `port/java-truststore.sh` and `port/build.sh` need the sandbox
disabled: they write git hooks or the system temp folder, and Gradle binds a local socket.

### Changing ZettaBridge

Edit `zettabridge/` directly, rebuild and test, and commit it like any other code. Its own
`CLAUDE.md` and `AGENTS.md` describe the architecture and gotchas; they predate this project.
Changes to Dynarmic go into a new patch under `zettabridge/third_party/patches/` and the
`git apply` list in `port/setup.sh`, because the Dynarmic checkout is not tracked.

### Testing on the emulator

AVD `android16`: Android 16 arm64. Apple Silicon has no AArch32, so it is a faithful
64-bit-only test bed.

- Start it with `~/.android-sdk/emulator/emulator -avd android16 -no-snapshot-save -no-boot-anim`, run in the background.
- Stop it with `adb -e emu kill`.
- Commands that start the emulator or talk to adb need the sandbox disabled.
- Install with `adb -e install -r dist/Magic2015-64-bit.apk`. Space is tight: about 1.6 GB per install, and an update needs another 1.6 GB while it runs.
- The first launch asks for "Nearby devices" (Allow is at 1265,589), then shows the game's "Unknown issue with Google Play services" dialog. Tap OK. The intro video needs taps to skip.
- The user often drives the game UI. Ask them to navigate (for example to the Tutorial screen) rather than scripting long tap sequences. A badly timed tap during loading can trigger an ANR.
- The back gesture can't be faked with `input swipe`; SystemUI ignores it. Use stepwise `input motionevent DOWN/MOVE/UP` from the screen edge.
- Screen coordinates follow the current rotation: landscape is 2400x1080.
- `adb -e root` works on this Google APIs image. The app is a release build, so `run-as` does not.
  - Plugin data: `/data/data/com.zettabridge.magic2015/files/plugins/com.stainlessgames.D15/data/`
  - Runtime report: `/data/media/0/Android/data/com.zettabridge.magic2015/files/zb-runtime-report.txt`

## Facts that are easy to get wrong

- **The game derives paths from the host package.** Inside ZettaBridge, `getPackageName()` is
  `com.zettabridge.magic2015`.
  - The OBB the game opens is `Android/obb/com.zettabridge.magic2015/main.4959.com.zettabridge.magic2015.obb`.
  - The app's `versionCode` must stay 4959; `build.sh` checks this.
- **The OBB is never copied.** A sparse placeholder of the right size stands at that path for the
  game's Java size check. In the guest process, `ZBridge.addFileWindow` maps the path onto the
  OBB's bytes inside the installed APK (`core/src/file_windows.cpp`, wired into the
  read/seek/stat/mmap/dup syscalls). The OBB entry must stay 16 KiB-aligned: `tools.py` aligns
  it, and `apksigner` runs with `--alignment-preserved`. Do not run `zipalign` on the output.
- **The source APK is an androeed.ru repack.** `tools.py` patches checked byte offsets in its
  `classes.dex`:
  - promo #1, `L億;.三`: skip to setting `SPOOF_SIGNATURE`, which the repack's shims need;
  - promo #2: nop the call in `DuelsLoader.onCreate`;
  - it then recomputes the dex SHA-1 and Adler-32.

  The unlock is `assets/opera-fan`: `purchase.db` with every IAP marked purchased. The game
  restores it into the host's data folder, so `BundledGame.seedUnlocks` applies it to the plugin
  data folder instead, once per install.
- **The starting profile is `files/p1.profile` in `assets/opera-fan`.** `seedUnlocks` installs it
  only when the game has no profile yet. At build time, `patch_profile` in `tools.py`:
  - renames the player to "Planewalker" and the deck to "Started";
  - sets every card to its copy limit;
  - adds `STARTING_DECKS`.

  Its comment documents the format. The traps:
  - The whole file is WrappingXOR'ed.
  - The collection lives in a second, inner WrappingXOR buffer, made of three 0x400-byte chunks
    whose used lengths follow them. Editing the chunks as one run corrupts those lengths, and the
    game then silently discards the whole profile and starts a new one.
  - There is no checksum.
  - Deck and player names hold at most 15 characters.
  - Card uids come from `card_pools` in `cards.canonical.json`.

  The live save is `files/p1.profile` in the plugin data folder. Force-stop the game before
  editing it, keep a backup, and decode it again with a strict parser before pushing it.
  - Edit saves through `GameProfile` in `tools.py`. The deck-builder skill's
    `scripts/install_deck.py` uses it to put a `decks/*.txt` list into a save (`--adb` for the
    emulator).
- **Change game logic in `libDuels.so`, not the OBB.** The UI logic is compiled Lua 5.1 (`.lol`)
  inside the OBB, and every entry is RSA-signed, so it cannot be edited. Its string constants are
  readable, and the `Obb` class in `build/cards/extract_cards.py` decrypts any entry. The Lua calls
  into native `lua_*` bindings, which keep their symbols in `libDuels.so`.
  - Patches go in `LIBDUELS_PATCHES` in `port/tools.py`: each has an offset, the original bytes and
    the new bytes, which are checked.
  - The code is Thumb, and file offsets equal addresses. Disassemble with the NDK's
    `llvm-objdump -d --triple=thumbv7-linux-androideabi`.
- **Multiplayer gates.** The tutorial is required because it gives the starter deck. Beating the
  Innistrad boss was also required, but `lua_HasPlayerBeatenInnistradBoss` is patched to pass;
  it also gated the expansion content in the deck builder and collection.
- **Ad-hoc multiplayer is classic Bluetooth in Java** (`BluetoothConnection`,
  `BluetoothDeviceSelect`). The host manifest declares the Bluetooth permissions, and
  `BundleActivity` asks for "Nearby devices" once per install, before the game starts.
  - The native layer (`AndroidBluetooth_*` in `libDuels.so`) keys players by the address
    `GetLocalBluetoothMACAddress` returns and matches each bundle's sender against it. Apps read
    their own address as `02:00:00:00:00:00`, so `port/overrides/` replaces `BluetoothConnection`.
    Each device gets an ID derived from ANDROID_ID, and the first frame on each connection is a
    `ZBID` hello that swaps the IDs. Both phones need this build.
  - Frames are `[u32 big-endian length][bytes]`. A payload starting `FF FE FD FC` is the host's
    session descriptor (`mBznetstruct`).
  - The join flow: the host taps Create Match, then Make discoverable. The joiner taps Custom
    Match (the eye card), then picks the host in `BluetoothDeviceSelect`, a full-screen black
    list by the game's own design. Scanning takes about 15 seconds. The first connection asks
    both phones to pair.
  - Test it with two emulators: create a second AVD from the same image and start it with
    `-port 5556`. netsim links their Bluetooth.
- **Java overrides.** Classes under `port/overrides/` are compiled against `android.jar` and
  converted with `d8` by `build.sh`. `tools.py game-apk` makes them `classes.dex` and moves the
  game's own dex to `classes2.dex`. ART takes the first definition of a class, and the overrides
  load in the plugin's own class loader, so the game's package-private access still works.
  Keep every public signature of a replaced class identical.
- **Back handling.** The game handles Back only in `onKeyDown`/`onKeyUp`; its `onBackPressed` is empty.
  - Predictive back is off (`enableOnBackInvokedCallback=false`).
  - `GuestBackKeys` stretches a synthesized gesture Back to 100 ms, because the game samples the button once per frame.
  - System bars use `BEHAVIOR_DEFAULT`; sticky immersive disables the back gesture. They are re-hidden on the next frame.
- **Audio.** Only Bink video uses OpenSL, which gets the silent stub. Music is FMOD over Java `AudioTrack`.
- **Login cannot work.** The repack is re-signed and the game runs under the host package. Do not
  chase Google or Facebook sign-in.
- **This network inspects TLS (Cloudflare Gateway).** Java tools need `build/java-truststore.jks`. curl and git
  use the keychain and work.
- **The sandbox's `$TMPDIR` differs from an unsandboxed shell's.** Pass absolute paths when
  switching between them.

## Rules

- Never commit `keys/`, `build/` (except `build/cards/`), `dist/`, `zettabridge/build/`, Dynarmic, the sysroot,
  or any APK, OBB or keystore outside `input/`. Anything added under `input/` must go through
  LFS: check `git lfs status` shows it as `LFS`, not `Git`.
- Keep the signing key: updates signed with a different key need an uninstall, which loses the
  user's progress. The original key was lost. The current one (`CN=Local Mod`, SHA-256
  `43fc3935…25938d`) was made on 2026-10-05, so an install signed with the old key must be
  uninstalled once. Never print, read out or publish the key or its password.
- ZettaBridge is the user's own code. Builds contain the copyrighted game: personal use only; do
  not publish them. Dynarmic and its externals keep their own licences.
