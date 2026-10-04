#!/usr/bin/env python3
"""Build helpers for the Magic 2015 single-APK port (called by build.sh).

  tools.py patch-libduels SRC DST
      Applies LIBDUELS_PATCHES: the EGL config fallback fix and the multiplayer unlock.

  tools.py game-apk ORIG_APK OUT_APK LIB_DIR [OVERRIDES_DEX]
      The game APK as ZettaBridge runs it: the original (targetSdk 17, which the guest linker
      relies on), its v1 signature removed, with every lib/armeabi-v7a/*.so from LIB_DIR replacing
      or joining the original libraries, OVERRIDES_DEX (port/overrides/, built by build.sh) as
      classes.dex in front of the game's own dex, classes.dex patched (see patch_dex) and the starting
      profile renamed, fully unlocked and given STARTING_DECKS (see patch_profile).

  tools.py inject APK OUT_APK ARCNAME=FILE ...
      Copies APK and adds each FILE uncompressed at ARCNAME, streamed (the OBB is 1.5 GB). Does
      the alignment itself: uncompressed data on 4 bytes, .so files and *.obb on 16 KiB pages
      (the OBB is memory-mapped through a ZettaBridge file window), each recorded in the
      0xD935 alignment extra field. apksigner then runs with --alignment-preserved.

  tools.py check-align APK
      Fails unless every uncompressed .so and .obb entry starts on a 16 KiB boundary.
"""
import hashlib
import io
import struct
import os
import zlib
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Thumb code in libDuels.so, whose file offsets equal its addresses. Each patch is (file offset,
# original bytes, replacement, what it does).
LIBDUELS_PATCHES = [
    # __android_init_display: `mov r7, r6` (r7 = the config array itself) becomes `ldr r7, [r6]`
    # (r7 = its first config), so a GPU without an RGB565 config (the Android emulator) still gets
    # a valid config. Devices with one are unaffected.
    (0x736490, "3746", "3768", "EGL config fallback"),
    # CPlayerCallBack::lua_HasPlayerBeatenInnistradBoss: the campaign's first plane gates
    # multiplayer (main menu, phud) and the expansion content in the deck builder and collection.
    # The `blt` that answers false when its boss match is not completed becomes a nop, so any
    # loaded profile counts as having beaten it. With no profile it still answers false.
    (0x42BC84, "13db", "00bf", "multiplayer unlocked (Innistrad boss check)"),
]
SIGNATURE_FILE = re.compile(r"META-INF/(MANIFEST\.MF|[^/]*\.(SF|RSA|DSA|EC))$")


def patch_libduels(src, dst):
    data = bytearray(open(src, "rb").read())
    for offset, old_hex, new_hex, what in LIBDUELS_PATCHES:
        old, new = bytes.fromhex(old_hex), bytes.fromhex(new_hex)
        at = bytes(data[offset:offset + len(old)])
        if at == new:
            print("libDuels.so: %s: already patched" % what)
        elif at == old:
            data[offset:offset + len(new)] = new
            print("libDuels.so: %s patched at 0x%x" % (what, offset))
        else:
            sys.exit("libDuels.so: unexpected bytes %s at 0x%x (not v1.4.4959?)" % (at.hex(), offset))
    open(dst, "wb").write(data)


# The APK is an androeed.ru repack, and the repackers call two promo routines first thing in
# DuelsLoader.onCreate. Each patch is (file offset, original bytes, replacement, what it does).
DEX_PATCHES = [
    # L億;.三(Context): a first-launch dialog with the site's promo image (assets/config.bin), then
    # a "Downloaded from www.androeed.ru" toast on every later launch, and finally
    # `SPOOF_SIGNATURE = true`, which the repack's package-info shims rely on. Keep only that:
    # its first three code units (const/4 + const-string) become goto/16 +0xa4, nop, landing on
    # `const/4 v0, 1; sput-boolean SPOOF_SIGNATURE; return-void`.
    (0x33EAA4, "12021a019539", "2900a4000000", "androeed.ru promo #1 (L億;.三) skipped"),
    # DuelsLoader.onCreate+0x2ca: invoke-static {v0} MobileLinkQualityInfo.iLLLLiiIIiIILLii, a
    # chain of trampolines in fake android.support.v4.net classes ending in
    # NetworkTemplate.iIIiiLLiLIIiIILI: the same promo dialog/toast with encoded strings, and
    # nothing else. The call becomes three nops.
    (0x2E61B8, "711060070000", "000000000000", "androeed.ru promo #2 (onCreate call) removed"),
]


def patch_dex(data):
    data = bytearray(data)
    changed = False
    for offset, old, new, what in DEX_PATCHES:
        old, new = bytes.fromhex(old), bytes.fromhex(new)
        at = bytes(data[offset:offset + len(old)])
        if at == new:
            continue
        if at != old:
            sys.exit("classes.dex: unexpected bytes %s at 0x%x (not the v1.4.4959 androeed build?)"
                     % (at.hex(), offset))
        data[offset:offset + len(new)] = new
        changed = True
        print("classes.dex: " + what)
    if changed:
        # Header: magic[8], checksum = adler32 of [12:], signature = SHA-1 of [32:]
        data[12:32] = hashlib.sha1(bytes(data[32:])).digest()
        struct.pack_into("<I", data, 8, zlib.adler32(bytes(data[12:])) & 0xFFFFFFFF)
    return bytes(data)


# The repack's unlock snapshot, assets/opera-fan (a zip), carries the starting profile,
# files/p1.profile, which BundledGame.seedUnlocks installs only when the game has none yet.
# patch_profile renames it (PROFILE_PATCHES), gives it every card at its copy limit and adds
# STARTING_DECKS. Layout, from libDuels.so (BZ::Player::PD_*, CSaveGameManager, UserOptions):
# - The whole file is WrappingXOR'ed (see wx_back). After the u32 size come the player block
#   (0x1464 bytes), the save block (0x2c78: player name at 0x1694, decks at 0x16d4) and a tail.
# - Names are wchar_t (UTF-32LE) in 16-character slots; the game keeps at most 15 characters.
# - Decks: 32 slots of 0x120 bytes: name, 100 u16 (uid << 3 | count), basic lands as 5 x 4 bytes
#   (count per land type, then art variant), icon byte (0xff = empty slot).
# - Profile settings 0x18-0x1a are 0x400-byte chunks in the player block, each followed by its used
#   length. Their used parts, joined and padded to 0xbb8 bytes, are WrappingXOR'ed again:
#   [u32 used][u32 len][entry]..., the second entry being the UserOptions profile block, whose
#   collection at +0x4f holds a nibble per card uid: copies (0-7), bit 3 a flag. Editing the
#   chunks as one run corrupts their lengths, and the game then discards the whole profile.
# Each name patch is (offset in the decoded file, original name, new name, what it is).
PROFILE_PATCHES = [
    (0x1694, "user", "Planewalker", "player name"),
    (0x16D4, "\u041a\u043e\u043b\u043e\u0434\u0430", "Started", "equipped deck name"),  # "Koloda"
]
# (deck name, list in decks/): added to the first free deck slot.
STARTING_DECKS = [("Dragonfire", "rakdos-dragonfire.txt")]
CARD_CATALOG = os.path.join(ROOT, "build", "cards", "cards.canonical.json")
PROFILE_NAME_SLOT = 0x40
PROFILE_CHUNKS = [(0x85C, 0xC5C), (0xC60, 0x1060), (0x1064, 0x1464)]  # (data, u32 used length)
PROFILE_INNER_LEN = 0xBB8
PROFILE_DECKS = 0x16D4
BASIC_LANDS = {"Plains": 0, "Island": 1, "Swamp": 2, "Mountain": 3, "Forest": 4}


def wx_back(buf):
    """Obfuscation::WrappingXOR_Backwards."""
    out = bytearray(buf)
    for i in range(len(buf) - 1, 0, -1):
        out[i] = buf[i] ^ buf[i - 1]
    out[0] = buf[0] ^ out[-1]
    return out


def wx_fwd(buf):
    """Obfuscation::WrappingXOR_Forward."""
    out = bytearray(buf)
    out[0] = buf[0] ^ buf[-1]
    for i in range(1, len(buf)):
        out[i] = buf[i] ^ out[i - 1]
    return out


def profile_name(plain, offset):
    return bytes(plain[offset:offset + PROFILE_NAME_SLOT]).decode("utf-32-le").rstrip("\0")


def put_profile_name(plain, offset, name):
    if len(name) > 15:
        sys.exit("p1.profile: %r is longer than 15 characters" % name)
    plain[offset:offset + PROFILE_NAME_SLOT] = name.encode("utf-32-le").ljust(PROFILE_NAME_SLOT, b"\0")


def load_cards(keys=False):
    """uid -> card from the extracted catalog (build/cards/extract_cards.py); with keys, uid -> ID."""
    import json
    catalog = json.load(open(CARD_CATALOG, encoding="utf-8"))
    return {e["uid"]: e["card"] if keys else catalog["cards"][e["card"]]
            for pool in catalog["card_pools"].values() for e in pool["cards"]}


def card_key(name):
    """Name as .claude/skills/m15-deck-builder/scripts/catalog.py compares it."""
    return re.sub(r"\s+", " ", name.replace("’", "'").strip().lower())


def read_deck_list(path):
    """A deck list as deck_check.py reads it (`<count> <card name or ID>`, # comments), as
    ([(uid, count)], [count per basic land type])."""
    cards_by_uid, ids = load_cards(), load_cards(keys=True)
    uid_of = {card_key(card["name"]): uid for uid, card in cards_by_uid.items()}
    uid_of.update({card_id: uid for uid, card_id in ids.items()})
    basics = {card_key(name): land for name, land in BASIC_LANDS.items()}
    cards, lands = [], [0] * 5
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"(\d+)\s*x?\s+(.+)", line)
        if not m:
            sys.exit("%s: expected '<count> <card>', got %r" % (path, line))
        count, ref = int(m.group(1)), m.group(2).strip()
        if card_key(ref) in basics:
            lands[basics[card_key(ref)]] += count
        elif ref in uid_of or card_key(ref) in uid_of:
            cards.append((uid_of.get(ref, uid_of.get(card_key(ref))), count))
        else:
            sys.exit("%s: %r is not a card the player can own" % (path, ref))
    if len(cards) > 100 or any(n > 7 for _, n in cards) or any(n > 255 for n in lands):
        sys.exit("%s: does not fit a deck slot" % path)
    return cards, lands


class GameProfile:
    """A decoded p1.profile (layout above). Edit, then encode()."""

    def __init__(self, data):
        self.outer = wx_back(data)
        self.lengths = [struct.unpack_from("<I", self.outer, at)[0] for _, at in PROFILE_CHUNKS]
        if any(n > 0x400 for n in self.lengths) or sum(self.lengths) > PROFILE_INNER_LEN:
            sys.exit("p1.profile: unexpected chunk lengths %s" % self.lengths)
        cipher = b"".join(bytes(self.outer[d:d + n]) for (d, _), n in zip(PROFILE_CHUNKS, self.lengths))
        self.inner = wx_back(cipher.ljust(PROFILE_INNER_LEN, b"\0"))
        first = struct.unpack_from("<I", self.inner, 4)[0]
        block = 8 + ((first + 3) & ~3) + 4
        if (struct.unpack_from("<I", self.inner, 0)[0] != sum(self.lengths)
                or struct.unpack_from("<I", self.inner, block - 4)[0] != 0x470):
            sys.exit("p1.profile: unexpected profile block layout")
        self.collection = block + 0x4F
        self.inner_changed = False

    def encode(self):
        if self.inner_changed:
            cipher = wx_fwd(self.inner)
            pos = 0
            for (d, _), n in zip(PROFILE_CHUNKS, self.lengths):
                self.outer[d:d + n] = cipher[pos:pos + n]
                pos += n
        return bytes(wx_fwd(self.outer))

    def owned(self, uid):
        """Copies of card uid in the collection."""
        return (self.inner[self.collection + uid // 2] >> (0 if uid % 2 == 0 else 4)) & 7

    def set_owned(self, uid, copies):
        at, shift = self.collection + uid // 2, 0 if uid % 2 == 0 else 4
        flag = (self.inner[at] >> shift) & 8
        self.inner[at] = (self.inner[at] & ~(0xF << shift) & 0xFF) | ((flag | copies) << shift)
        self.inner_changed = True

    def unlock_all(self, cards):
        """Raises every card to its copy limit; returns how many were raised."""
        raised = 0
        for uid, card in cards.items():
            if self.owned(uid) < card["max_copies"]:
                self.set_owned(uid, card["max_copies"])
                raised += 1
        return raised

    def decks(self):
        """{name: slot offset} of the used deck slots."""
        slots = (PROFILE_DECKS + i * 0x120 for i in range(32))
        return {profile_name(self.outer, at): at for at in slots if self.outer[at + 0x11C] != 0xFF}

    def put_deck(self, name, cards, lands, replace=False):
        """Writes a deck into its own slot (with replace) or the first free one."""
        at = self.decks().get(name)
        if at is not None and not replace:
            sys.exit("p1.profile: a deck named %r already exists" % name)
        if at is None:
            at = next((PROFILE_DECKS + i * 0x120 for i in range(32)
                       if self.outer[PROFILE_DECKS + i * 0x120 + 0x11C] == 0xFF), None)
            if at is None:
                sys.exit("p1.profile: no free deck slot for %r" % name)
        slot = bytearray(0x120)
        put_profile_name(slot, 0, name)
        struct.pack_into("<100H", slot, 0x40, *([uid << 3 | n for uid, n in cards] + [0] * (100 - len(cards))))
        for land, n in enumerate(lands):
            slot[0x108 + land * 4] = n
        slot[0x11C] = 0  # icon, as the repack's deck
        self.outer[at:at + 0x120] = slot


def patch_profile(data):
    profile = GameProfile(data)
    for offset, old, new, what in PROFILE_PATCHES:
        at = profile_name(profile.outer, offset)
        if at == new:
            continue
        if at != old:
            sys.exit("p1.profile: unexpected %s %r at 0x%x (not the v1.4.4959 androeed build?)" % (what, at, offset))
        put_profile_name(profile.outer, offset, new)
        print("p1.profile: %s set to %r" % (what, new))
    raised = profile.unlock_all(load_cards())
    if raised:
        print("p1.profile: %d cards raised to their copy limit" % raised)
    for name, list_file in STARTING_DECKS:
        if name not in profile.decks():
            profile.put_deck(name, *read_deck_list(os.path.join(ROOT, "decks", list_file)))
            print("p1.profile: deck %r added from decks/%s" % (name, list_file))
    return profile.encode()


def patch_unlock_snapshot(data):
    """assets/opera-fan with its files/p1.profile patched; every other entry is copied as is."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zi, zipfile.ZipFile(out, "w") as zo:
        for info in zi.infolist():
            body = zi.read(info)
            if info.filename == "files/p1.profile":
                body = patch_profile(body)
            zo.writestr(info, body)
    return out.getvalue()


PAGE = 16384
ALIGNMENT_EXTRA_ID = 0xD935  # Android's zip alignment extra field (apksig, zipalign -p)


def alignment_for(name):
    return PAGE if name.endswith(".so") or name.endswith(".obb") else 4


def align(zo, info):
    """Pads info.extra so an uncompressed entry's data lands on its alignment."""
    if info.compress_type != zipfile.ZIP_STORED:
        info.extra = b""
        return
    alignment = alignment_for(info.filename)
    data_start = zo.fp.tell() + 30 + len(info.filename.encode("utf-8"))
    if alignment == 4:
        info.extra = b"\0" * ((-data_start) % 4)
        return
    # id(2) + size(2) + alignment(2), then zero padding up to the boundary
    pad = (-(data_start + 6)) % alignment
    info.extra = struct.pack("<HHH", ALIGNMENT_EXTRA_ID, 2 + pad, alignment) + b"\0" * pad


def copy_entry(zi, zo, info, data=None):
    out = zipfile.ZipInfo(info.filename, info.date_time)
    out.compress_type = info.compress_type
    out.external_attr = info.external_attr
    align(zo, out)
    if data is None:
        with zi.open(info) as src, zo.open(out, "w") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    else:
        zo.writestr(out, data)


def game_apk(orig, out, lib_dir, overrides_dex=None):
    libs = {"lib/armeabi-v7a/" + name: os.path.join(lib_dir, name)
            for name in sorted(os.listdir(lib_dir)) if name.endswith(".so")}
    with zipfile.ZipFile(orig) as zi, zipfile.ZipFile(out, "w") as zo:
        if overrides_dex:
            # ART searches an APK's dex files in order and takes the first definition of a class,
            # so the port's replacement classes (port/overrides/) go first and the game's own dex
            # becomes classes2.dex.
            info = zipfile.ZipInfo("classes.dex", (2015, 4, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zo.writestr(info, open(overrides_dex, "rb").read())
        for info in zi.infolist():
            if SIGNATURE_FILE.match(info.filename) or info.filename in libs:
                continue
            if info.filename == "classes.dex":
                dex = patch_dex(zi.read(info))
                if overrides_dex:
                    if "classes2.dex" in zi.namelist():
                        sys.exit("game APK already has classes2.dex; cannot place the overrides in front")
                    renamed = zipfile.ZipInfo("classes2.dex", info.date_time)
                    renamed.compress_type = info.compress_type
                    renamed.external_attr = info.external_attr
                    info = renamed
                copy_entry(zi, zo, info, dex)
                continue
            if info.filename == "assets/opera-fan":
                copy_entry(zi, zo, info, patch_unlock_snapshot(zi.read(info)))
                continue
            copy_entry(zi, zo, info)
        for arcname, path in libs.items():
            info = zipfile.ZipInfo(arcname, (2015, 4, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zo.writestr(info, open(path, "rb").read())
    print("game APK: %s (%d libraries replaced or added)" % (out, len(libs)))


def inject(apk, out, pairs):
    adds = dict(pair.split("=", 1) for pair in pairs)
    with zipfile.ZipFile(apk) as zi, zipfile.ZipFile(out, "w", allowZip64=False) as zo:
        for info in zi.infolist():
            if info.filename not in adds and not SIGNATURE_FILE.match(info.filename):
                copy_entry(zi, zo, info)
        for arcname, path in adds.items():
            info = zipfile.ZipInfo(arcname, (2015, 4, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED  # AssetManager.openFd needs uncompressed
            info.external_attr = 0o644 << 16
            info.file_size = os.path.getsize(path)
            align(zo, info)
            with open(path, "rb") as src, zo.open(info, "w") as dst:
                shutil.copyfileobj(src, dst, 4 << 20)
            print("injected %s (%d bytes)" % (arcname, info.file_size))


def check_align(apk):
    bad = []
    with open(apk, "rb") as f, zipfile.ZipFile(f) as z:
        for info in z.infolist():
            if info.compress_type != zipfile.ZIP_STORED or alignment_for(info.filename) != PAGE:
                continue
            f.seek(info.header_offset)
            header = f.read(30)
            name_len, extra_len = struct.unpack("<HH", header[26:30])
            start = info.header_offset + 30 + name_len + extra_len
            if start % PAGE:
                bad.append("%s at %d" % (info.filename, start))
    if bad:
        sys.exit("not 16 KiB aligned: " + ", ".join(bad))
    print("alignment ok")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "patch-libduels":
        patch_libduels(*args)
    elif cmd == "game-apk":
        game_apk(*args)
    elif cmd == "inject":
        inject(args[0], args[1], args[2:])
    elif cmd == "check-align":
        check_align(*args)
    else:
        sys.exit(__doc__)
