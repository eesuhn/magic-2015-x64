# Changelog

## Unreleased

### 32-bit build

- `port/build-x32.sh` builds `dist/Magic2015-32-bit.apk`: the game itself with the port's game
  fixes, for devices that run 32-bit code. It runs natively, without ZettaBridge. The fixes are the
  `libDuels.so` patches, the Bluetooth override, the promo removal and the starting profile. The
  package stays `com.stainlessgames.D15` and the OBB stays outside the APK. The manifest adds the
  location permission Bluetooth discovery needs and raises `minSdkVersion` to 21. The 64-bit
  build is unchanged.

## v1.1.1 (2026-10-05)

Ad-hoc multiplayer now gets past joining. Source only. Update both phones: a v1.1.0 phone cannot
join or host a match with a v1.1.1 phone.

### Multiplayer

- Joining an ad-hoc match never completed: the host stayed on "Waiting" and the joiner gave up
  after about 20 seconds. The game registers each player under its own Bluetooth address and
  matches every message by its sender's address, but since Android 6 apps read their own address
  as `02:00:00:00:00:00`, so no message ever matched. `port/overrides/` replaces the game's
  `BluetoothConnection`: each phone uses a stable ID of its own, and the phones swap IDs when
  they connect. The same class now reads messages whole (RFCOMM splits them at about 1 KB) and
  clears the host's session between attempts. Both phones need this build. Tested between two
  emulators, up to a running duel.

## v1.1.0 (2026-10-05)

Multiplayer works, and new installs start with every card and a ready-made deck. Source only, like
v1.0.0. Installing over a v1.0.0 build keeps your save, which this release does not change: the
starting profile below applies only to new installs.

### Multiplayer

- Ad-hoc (Bluetooth) multiplayer was blocked: the app targets Android 15 but declared no
  Bluetooth permissions, and the game predates runtime permissions. The app now declares them and
  asks for "Nearby devices" once, before the game starts.
- Multiplayer no longer waits for the Innistrad boss (the campaign's first plane): a 2-byte patch
  in `libDuels.so` makes that check pass. The same check gated the expansion content in the deck
  builder and collection, which is now available from the start. Multiplayer still needs the
  tutorial, which gives the starter deck.

### Profile

- New installs start with the player named "Planewalker" and the equipped deck named "Started"
  instead of the repack's "user" and "Колода". Existing saves are not changed.
- New installs start with every card at its copy limit, including the 34 cards that came only
  from booster packs, and with the Dragonfire deck (`decks/rakdos-dragonfire.txt`).

### Cards and decks

- `build/cards/` holds the card list decrypted from the OBB (`extract_cards.py`). The canonical
  catalog includes the game's own deck rules: deck size, copy limits by rarity, card pools.
- `decks/` holds decks built from that catalog: a `.txt` list and a `.md` write-up each, starting
  with Rakdos Dragonfire.
- The `m15-deck-builder` Claude Code skill (`.claude/skills/`) builds and checks decks against
  those rules. Its `install_deck.py` writes a list into a save as a real in-game deck: into the
  emulator's live save with `--adb`, or into a save file. `STARTING_DECKS` in `port/tools.py`
  adds a deck to every build's starting profile.

## v1.0.0 (2026-10-04)

First release. Source only: the APK contains the copyrighted game, so build it yourself (see
[README.md](README.md#build)).

### Runtime

- The 32-bit-only game runs on 64-bit-only CPUs through
  [ZettaBridge](https://github.com/ZailoxTT/ZettaBridge), which translates ARM32 to ARM64 with
  Dynarmic.
- ZettaBridge fixes in `zettabridge/`: NativeActivity start, looper idents, the 5th argument of
  `AInputQueue_attachLooper`, EGL handle maps, AAssetDir, `sched_*` syscalls and stalls in the
  report writer.

### Audio

- 32-bit guests have no `libOpenSLES.so`, so a silent stub (`port/sles/`) stands in. Only the
  intro videos use OpenSL; music and effects play normally.

### Graphics

- When the GPU lacks RGB565, the game used a pointer as an EGL config. Fixed with a 1-byte patch
  in `libDuels.so`.

### Install size

- The 1.5 GB OBB is no longer copied, which doubled the install size. It is served from inside
  the APK through a file window, and a sparse placeholder satisfies the game's size check.

### Expansions

- The repack restored its unlock snapshot into the wrong data folder, so purchases stayed
  locked. It is now applied to the game's own data on first launch: purchases are merged and
  existing progress is kept.

### Promo

- The source APK (an androeed.ru repack) showed the site's dialog and toast. Both are disabled
  in `classes.dex`.

### Navigation

- The back gesture was ignored. Back events are now paced so the game sees them.
- The system bars blocked gestures. Fullscreen now leaves the back gesture working.
- The app showed two Recents entries. It now runs as a single task.
