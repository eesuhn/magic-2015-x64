# Changelog

## Unreleased

### Multiplayer

- Ad-hoc (Bluetooth) multiplayer was blocked: the app targets Android 15 but declared no
  Bluetooth permissions, and the game predates runtime permissions. The app now declares them and
  asks for "Nearby devices" once, before the game starts.

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
