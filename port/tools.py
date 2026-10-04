#!/usr/bin/env python3
"""Build helpers for the Magic 2015 single-APK port (called by build.sh).

  tools.py patch-libduels SRC DST
      Applies LIBDUELS_PATCHES: the EGL config fallback fix and the multiplayer unlock.

  tools.py game-apk ORIG_APK OUT_APK LIB_DIR
      The game APK as ZettaBridge runs it: the original (targetSdk 17, which the guest linker
      relies on), its v1 signature removed, with every lib/armeabi-v7a/*.so from LIB_DIR replacing
      or joining the original libraries, classes.dex patched (see patch_dex) and the starting
      profile renamed (see PROFILE_PATCHES).

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
# files/p1.profile, which BundledGame.seedUnlocks installs only when the game has none yet. The
# profile is RollingXOR'ed (plain[i] = c[i] ^ c[i-1], first byte as is); its names are wchar_t
# (UTF-32LE) in fixed 16-character slots. Each patch is (offset in the decoded profile, original
# name, new name, what it is).
PROFILE_SLOT = 64
PROFILE_PATCHES = [
    (0x1694, "user", "Planewalker", "player name"),
    (0x16D4, "\u041a\u043e\u043b\u043e\u0434\u0430", "Started", "equipped deck name"),  # "Koloda"
]


def patch_profile(data):
    plain = bytearray(data[:1]) + bytearray(data[i] ^ data[i - 1] for i in range(1, len(data)))
    for offset, old, new, what in PROFILE_PATCHES:
        if len(new) >= PROFILE_SLOT // 4:
            sys.exit("p1.profile: %s %r is longer than %d characters" % (what, new, PROFILE_SLOT // 4 - 1))
        at = bytes(plain[offset:offset + PROFILE_SLOT]).decode("utf-32-le").rstrip("\0")
        if at == new:
            continue
        if at != old:
            sys.exit("p1.profile: unexpected %s %r at 0x%x (not the v1.4.4959 androeed build?)" % (what, at, offset))
        plain[offset:offset + PROFILE_SLOT] = new.encode("utf-32-le").ljust(PROFILE_SLOT, b"\0")
        print("p1.profile: %s set to %r" % (what, new))
    out = bytearray(plain[:1])
    for i in range(1, len(plain)):
        out.append(plain[i] ^ out[i - 1])
    return bytes(out)


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


def game_apk(orig, out, lib_dir):
    libs = {"lib/armeabi-v7a/" + name: os.path.join(lib_dir, name)
            for name in sorted(os.listdir(lib_dir)) if name.endswith(".so")}
    with zipfile.ZipFile(orig) as zi, zipfile.ZipFile(out, "w") as zo:
        for info in zi.infolist():
            if SIGNATURE_FILE.match(info.filename) or info.filename in libs:
                continue
            if info.filename == "classes.dex":
                copy_entry(zi, zo, info, patch_dex(zi.read(info)))
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
