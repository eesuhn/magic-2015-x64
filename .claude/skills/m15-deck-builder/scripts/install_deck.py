#!/usr/bin/env python3
"""Put a decklist into a Magic 2015 save (p1.profile) as a real in-game deck.

Usage: install_deck.py DECKLIST --name NAME (--save IN [--out OUT] | --adb) [--replace] [--unlock]
  DECKLIST   the same file deck_check.py reads ("<count> <card name or ID>", # comments)
  --name     the deck's name in the game: at most 15 characters (the game cuts longer ones)
  --save     a p1.profile on disk; written back in place unless --out is given
  --adb      edit the live save on the device adb talks to (ANDROID_SERIAL picks one). Needs
             `adb root`, so the emulator or a rooted phone. Force-stops the game and keeps the
             old save next to it as p1.profile.before-<name>.
  --replace  overwrite an existing deck with the same name instead of failing
  --unlock   raise any card the save owns too few copies of to its copy limit; without it,
             missing copies are an error, since a deck can only use owned cards

The save format and the codec live in port/tools.py (GameProfile); the build uses the same code
for the starting profile's decks (STARTING_DECKS). A new install gets those; this script is for
saves that already exist.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "port"))
import tools  # noqa: E402

PACKAGE = "com.zettabridge.magic2015"
DEVICE_SAVE = f"/data/data/{PACKAGE}/files/plugins/com.stainlessgames.D15/data/files/p1.profile"


def adb(*args, capture=False):
    result = subprocess.run(["adb", *args], check=True, capture_output=capture)
    return result.stdout if capture else None


def install(data, decklist, name, replace, unlock):
    if len(name) > 15:
        sys.exit(f"--name {name!r} is longer than 15 characters")
    cards, lands = tools.read_deck_list(decklist)
    catalog = tools.load_cards()
    profile = tools.GameProfile(data)
    short = [(uid, n) for uid, n in cards if profile.owned(uid) < n]
    if short and not unlock:
        sys.exit("the save owns too few copies of: "
                 + ", ".join(f"{catalog[u]['name']} ({profile.owned(u)}/{n})" for u, n in short)
                 + "\nrerun with --unlock to raise them to their copy limit")
    for uid, _ in short:
        profile.set_owned(uid, catalog[uid]["max_copies"])
    profile.put_deck(name, cards, lands, replace=replace)
    out = profile.encode()

    # Read it back the way the game will: same chunk lengths, the deck where we put it.
    check = tools.GameProfile(out)
    if check.lengths != profile.lengths or name not in check.decks():
        sys.exit("internal error: the edited save does not read back; nothing was written")
    total = sum(n for _, n in cards) + sum(lands)
    print(f"deck {name!r}: {total} cards ({sum(lands)} basic lands)"
          + (f", unlocked {len(short)} card(s)" if short else ""))
    print("decks in the save:", ", ".join(check.decks()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("decklist")
    ap.add_argument("--name", required=True)
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--save")
    where.add_argument("--adb", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--unlock", action="store_true")
    args = ap.parse_args()

    if args.save:
        data = Path(args.save).read_bytes()
        out = install(data, args.decklist, args.name, args.replace, args.unlock)
        Path(args.out or args.save).write_bytes(out)
        print("wrote", args.out or args.save)
        return

    adb("root", capture=True)
    adb("shell", "am", "force-stop", PACKAGE)
    data = adb("exec-out", "cat", DEVICE_SAVE, capture=True)
    out = install(data, args.decklist, args.name, args.replace, args.unlock)
    owner = adb("shell", "stat", "-c", "%u:%g", DEVICE_SAVE, capture=True).decode().strip()
    backup = f"{DEVICE_SAVE}.before-{args.name.replace(' ', '_')}"
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(out)
    try:
        adb("push", f.name, "/data/local/tmp/p1.profile", capture=True)
    finally:
        os.unlink(f.name)
    adb("shell", f"cp -p {DEVICE_SAVE} {backup} && cp /data/local/tmp/p1.profile {DEVICE_SAVE} && "
                 f"rm /data/local/tmp/p1.profile && chown {owner} {DEVICE_SAVE} && chmod 600 {DEVICE_SAVE} && "
                 f"restorecon {DEVICE_SAVE} {backup}")
    if adb("exec-out", "cat", DEVICE_SAVE, capture=True) != out:
        sys.exit(f"the save on the device does not match what was pushed; the old one is {backup}")
    print(f"installed on the device; previous save kept as {backup}")


if __name__ == "__main__":
    main()
