#!/usr/bin/env python3
"""Extract every card definition from the Magic 2015 OBB into cards.json and cards.csv.

Usage: extract_cards.py [OBB] [OUTDIR]
  OBB defaults to the Git LFS object for input/com.stainlessgames.D15/main.4959.*.obb,
  OUTDIR to the directory holding this script. Standard library only.

OBB layout (reverse-engineered from the x86 libDuels.so, which keeps its symbols):
  u32 version, u32 count, then count x {u32 name_len, name, u32 offset, u32 size}: a table of
  .ZED archives. Each ZED is a ZIP without local file headers, data at the central-directory
  offset directly, followed by an 8-byte trailer.
  - Central directory: Obfuscation::RollingXOR, plain[i] = c[i] ^ c[i-1].
  - Entry data (ZipIO::freadFromZippedBuffer): read in 0x2000-byte chunks. The first chunk starts
    with a 256-byte RSA-2048 PSS-R signature (Crypto++ PSSR, SHA-1, e=17; key embedded in the
    library, WrappingXOR'ed). The recovered message plus the rest of the chunk are RollingXOR'ed
    with seed 0x53; later chunks continue the chain from the previous ciphertext byte. The result
    is raw deflate (method 8) or stored (method 0). Entries under 256 bytes are stored as is.

Copy limits (CRuntimeCollection::_InterrogateData and ::AddCard): the collection holds only cards
listed in a card pool, at most 4 copies of a common, 3 of an uncommon, 2 of a rare and 1 of a
mythic (CCardSpec::GetRarity; C, T and L parse to the common slot). A deck can use only owned
copies, basic lands are unlimited, and CRuntimeDeckConfiguration::AddCard caps a deck at 100.
"""
import csv, hashlib, json, mmap, os, re, struct, sys, zlib
import xml.etree.ElementTree as ET
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_OBB = os.path.join(REPO, ".git/lfs/objects/96/87/"
                           "968707fd01a0e0fc97f22a2983560bf0adc233eed2ff7ad9a3cd0f625ce6d260")

# RSA public key from libDuels.so (x86 VA 0x11b9ab0, de-obfuscated).
RSA_N = int(
    "c4d0b8819cab92e7e87a4d2e1a7b5c911f1d7cf1818bc8b5cdc955374a019e67984a3a26fe200d8187ceadec5637eb"
    "c009ca1163cc5016e6fd59a4773d91aa361239aa16462c8a63fe086747bad97f7607619a4bfa325272934639922f1e"
    "c3e94bc57e2352c2c7754625542884fde95952702ab9ee39eb4bf9fb6d6605552c07190388abd8e49e04732a2aa1b0"
    "070a84e8b85a68485919b8b66d5cf5d12a31c0c65f11c5695a2b3bc01b9038513a6ceb47892f1e679d2f7d6f1a30fe"
    "c526c6be19d260e8568cc9b2074b759b473bb8de7cfab3cc540a7d69340496b65d45274c7a602fda2155af24d828e7"
    "56ebb8555d2f379a57dced0ee3bf6ff8543890a435", 16)
RSA_E = 17
CHUNK = 0x2000


def unchain(buf, seed):
    """RollingXOR_Backwards: plain[0] = c[0] ^ seed, plain[i] = c[i] ^ c[i-1]."""
    if not buf:
        return b""
    prev = bytes([seed]) + buf[:-1]
    n = len(buf)
    return (int.from_bytes(buf, "little") ^ int.from_bytes(prev, "little")).to_bytes(n, "little")


def mgf1(seed, n):
    out = b""
    c = 0
    while len(out) < n:
        out += hashlib.sha1(seed + c.to_bytes(4, "big")).digest()
        c += 1
    return out[:n]


def pssr_recover(sig):
    rep = pow(int.from_bytes(sig, "big"), RSA_E, RSA_N).to_bytes(256, "big")
    if rep[-1] != 0xBC:
        raise ValueError("bad PSS-R trailer")
    d = 20
    dbl = 256 - 1 - d
    h = rep[dbl:dbl + d]
    db = bytes(a ^ b for a, b in zip(rep[:dbl], mgf1(h, dbl)))
    db = bytes([db[0] & 0x7F]) + db[1:]
    return db[db.index(1) + 1:dbl - d]  # drop the salt (digest-sized)


def decrypt_entry(raw):
    if len(raw) < 256:
        return raw  # too short to hold a signature: stored as is (CRC-checked)
    first = raw[:CHUNK]
    out = unchain(pssr_recover(first[:256]) + first[256:], 0x53)
    if len(raw) > CHUNK:
        out += unchain(raw[CHUNK:], first[-1])
    return out


class Obb:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        _, n = struct.unpack_from("<II", self.m, 0)
        p = 8
        self.zeds = {}
        for _ in range(n):
            (ln,) = struct.unpack_from("<I", self.m, p)
            p += 4
            name = self.m[p:p + ln].decode()
            p += ln
            off, size = struct.unpack_from("<II", self.m, p)
            p += 8
            self.zeds[name] = (off, size)

    def entries(self, zed):
        off, size = self.zeds[zed]
        tail = min(size, 32 << 20)
        c = self.m[off + size - tail:off + size]
        p = unchain(c[1:], c[0])
        i = p.find(b"PK\x01\x02")
        while p[i:i + 4] == b"PK\x01\x02":
            (_, _, _, _, meth, _, _, crc, cs, us, nl, el, cl, _, _, _, lho) = struct.unpack_from(
                "<IHHHHHHIIIHHHHHII", p, i)
            name = p[i + 46:i + 46 + nl].decode("utf-8", "replace")
            yield dict(zed=zed, name=name, meth=meth, crc=crc, cs=cs, us=us, off=off + lho)
            i += 46 + nl + el + cl

    def read(self, e):
        d = decrypt_entry(bytes(self.m[e["off"]:e["off"] + e["cs"]]))
        x = zlib.decompressobj(-15).decompress(d) if e["meth"] == 8 else d
        if zlib.crc32(x) != e["crc"]:
            raise ValueError("CRC mismatch: " + e["name"])
        return x


# ---------------------------------------------------------------- card parsing

LANG = "en-US"
ABILITY_TAGS = ("STATIC_ABILITY", "TRIGGERED_ABILITY", "ACTIVATED_ABILITY", "SPELL_ABILITY",
                "MANA_ABILITY", "UTILITY_ABILITY")
COLOURS = "WUBRG"
MAX_COPIES = {"C": 4, "T": 4, "L": 4, "U": 3, "R": 2, "M": 1}


def en(el):
    if el is None:
        return ""
    for t in el.findall("LOCALISED_TEXT"):
        if t.get("LanguageCode") == LANG:
            return re.sub(r"\|([^|]*)\|", r"\1", (t.text or "").strip())  # |Heroic| = italics
    return ""


def cost_info(cost):
    syms = re.findall(r"\{([^}]*)\}", cost or "")
    cmc = 0
    cols = set()
    for s in syms:
        if s.isdigit():
            cmc += int(s)
        elif s.upper() in ("X", "Y", "Z"):
            pass
        else:
            parts = s.upper().split("/")
            cols.update(c for c in parts if c in COLOURS)
            cmc += 2 if parts[0] == "2" else 1
    return cmc, cols


def parse_card(el):
    g = lambda tag, attr: (el.find(tag).get(attr) if el.find(tag) is not None else None)
    cost = g("CASTING_COST", "cost") or ""
    cmc, cols = cost_info(cost)
    for c in el.findall("COLOUR"):
        cols.update(ch for ch in (c.get("value") or "").upper() if ch in COLOURS)
    abilities = []
    for a in el:
        if a.tag in ABILITY_TAGS:
            t = en(a)
            if t and a.get("commaspace") == "1" and abilities:
                abilities[-1] += ", " + t  # keyword lists: "Flying, lifelink"
            elif t:
                abilities.append(t)
    return {
        "id": g("FILENAME", "text"),
        "name": en(el.find("TITLE")),
        "mana_cost": cost,
        "cmc": cmc,
        "colors": "".join(c for c in COLOURS if c in cols),
        "supertypes": [x.get("metaname") for x in el.findall("SUPERTYPE")],
        "types": [x.get("metaname") for x in el.findall("TYPE")],
        "subtypes": [x.get("metaname") for x in el.findall("SUB_TYPE")],
        "power": g("POWER", "value"),
        "toughness": g("TOUGHNESS", "value"),
        "rules_text": "\n".join(abilities),
        "flavour_text": en(el.find("FLAVOURTEXT")),
        "rarity": g("RARITY", "metaname"),
        "expansion": g("EXPANSION", "value"),
        "multiverse_id": g("MULTIVERSEID", "value"),
        "art_id": g("ARTID", "value"),
        "artist": g("ARTIST", "name"),
        "is_token": el.find("TOKEN") is not None,
        "ai_base_score": g("AI_BASE_SCORE", "score"),
        "creates_tokens": sorted({x.get("type") for x in el.findall("TOKEN_REGISTRATION")}),
    }


def xml_root(data):
    return ET.fromstring(data.decode("utf-8-sig"))


# ---------------------------------------------------------------- canonical JSON

# MTG::CDataLoader::ParseRarity: RARITY metaname -> engine value. CRuntimeCollection::AddCard
# maps engine values 0..3 to 4/3/2/1 copies; anything else can't be added (0).
RARITIES = [("C", "Common", 0), ("T", "Token", 0), ("L", "Land", 0), ("U", "Uncommon", 1),
            ("R", "Rare", 2), ("M", "Mythic", 3), ("S", "Special", 4)]
ENGINE_COPIES = {0: 4, 1: 3, 2: 2, 3: 1}
COLOUR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
# Specs/*_Types.txt: which card types each subtype list belongs to.
SUBTYPE_SPECS = {"Artifact_Types.txt": ["ARTIFACT"], "Creature_Types.txt": ["CREATURE", "TRIBAL"],
                 "Enchantment_Types.txt": ["ENCHANTMENT"], "Land_Types.txt": ["LAND"],
                 "Planeswalker_Types.txt": ["PLANESWALKER"],
                 "Spell_Types.txt": ["INSTANT", "SORCERY"], "Plane_Types.txt": ["PLANE"],
                 "Scheme_Types.txt": ["SCHEME"]}


def spec_list(text):
    return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("//")]


def type_key(name):
    """Card XML metaname -> Specs spelling: "Assembly-Worker" -> ASSEMBLY_WORKER, "Urza's" -> URZAS."""
    return re.sub(r"[^A-Z0-9]+", "_", name.upper().replace("'", "").replace("’", "")).strip("_")


def as_int(v):
    return int(v) if v is not None and re.fullmatch(r"-?\d+", str(v)) else None


def deck_entry(root):
    return {
        "uid": as_int(root.get("uid")),
        "booster_id": as_int(root.get("booster_id")),
        "content_pack": as_int(root.get("content_pack")),
        "personality": root.get("personality") or None,
        "datapool": root.get("cheat_menu_filter_datapool") or None,
        "deck_type": root.get("cheat_menu_filter_deck_type") or None,
        "colours": [c for c, n in (("W", "white"), ("U", "blue"), ("B", "black"), ("R", "red"),
                                   ("G", "green")) if root.get("is_" + n) == "true"],
        "basic_lands": {x.get("name"): int(x.get("quantity")) for x in root.iter("BASICLAND")},
        "cards": [{"card": card, "difficulty": diff, "count": n}
                  for (card, diff), n in sorted(Counter_(deck_card(x.get("name"))
                                                         for x in root.iter("CARD")).items(),
                                                key=lambda kv: (kv[0][0], kv[0][1] or 0))],
    }


def deck_card(ref):
    """"NAME@3" -> (NAME, 3): the card is only in the deck at AI difficulty 3
    (CDeckSpec::CardValidForThisDifficulty); a plain name is in it at every difficulty."""
    card, _, diff = ref.partition("@")
    return card, as_int(diff)


def Counter_(it):
    out = {}
    for k in it:
        out[k] = out.get(k, 0) + 1
    return out


def write_canonical(path, rows, pools, decks, boosters, specs, store):
    card_types = spec_list(specs["Card_Types.txt"])
    supertypes = spec_list(specs["Supertypes.txt"])
    subtypes = {}
    for f, parents in SUBTYPE_SPECS.items():
        for st in spec_list(specs.get(f, "")):
            subtypes.setdefault(st, {"card_types": []})["card_types"] += parents
    store_items = {}
    if store is not None:
        for it in store.iter("ITEM"):
            uid = as_int((it.get("CONTENT_PACK_UID") or "").strip())
            if uid is not None:
                store_items[uid] = it.get("ITEMTYPE").strip()

    problems = []
    cards = {}
    for c in rows:
        for kind, vals, vocab in (("type", c["types"], card_types),
                                  ("supertype", c["supertypes"], supertypes),
                                  ("subtype", c["subtypes"], subtypes)):
            problems += [f"{c['id']}: unknown {kind} {v}" for v in vals if type_key(v) not in vocab]
        for st in c["subtypes"]:  # subtype must belong to one of the card's types
            parents = subtypes.get(type_key(st), {}).get("card_types", [])
            if parents and not set(parents) & {type_key(t) for t in c["types"]}:
                problems.append(f"{c['id']}: subtype {st} doesn't fit types {c['types']}")
        cards[c["id"]] = {
            "name": c["name"],
            "mana_cost": c["mana_cost"] or None,
            "cmc": c["cmc"],
            "colours": list(c["colors"]),
            "supertypes": [type_key(t) for t in c["supertypes"]],
            "types": [type_key(t) for t in c["types"]],
            "subtypes": [type_key(t) for t in c["subtypes"]],
            "power": c["power"],
            "toughness": c["toughness"],
            "rules_text": c["rules_text"] or None,
            "flavour_text": c["flavour_text"] or None,
            "rarity": c["rarity"],
            "collectible": bool(c["card_pools"]),
            "max_copies": c["max_copies"],
            "is_token": c["is_token"],
            "creates_tokens": c["creates_tokens"],
            "expansion": c["expansion"],
            "multiverse_id": as_int(c["multiverse_id"]),
            "art_id": as_int(c["art_id"]),
            "artist": c["artist"],
            "ai_base_score": as_int(c["ai_base_score"]),
            "content_pack": c["content_pack"],
        }
        problems += [f"{c['id']}: token {t} not defined" for t in c["creates_tokens"]
                     if t not in {r["id"] for r in rows}]

    def refs(owner, ids):
        return [f"{owner}: card {i} not defined" for i in ids if i not in cards]

    card_pools = {}
    for name, root in sorted(pools.items()):
        a = root["attrs"]
        uid = as_int(a.get("content_booster_uid"))
        card_pools[name] = {
            "id": as_int(a.get("id")),
            "plane_id": as_int(a.get("plane_id")),
            "content_id": as_int(a.get("content_id")),
            "content_booster_uid": uid,
            "store_item": store_items.get(uid),
            "cards": sorted(({"card": n, "uid": as_int(u)} for n, u in root["cards"]),
                            key=lambda x: (x["uid"] is None, x["uid"], x["card"])),
        }
        problems += refs("pool " + name, [n for n, _ in root["cards"]])
    deck_map = {k: deck_entry(v) for k, v in sorted(decks.items())}
    booster_map = {k: deck_entry(v) for k, v in sorted(boosters.items())}
    for owner, m in (("deck", deck_map), ("booster", booster_map)):
        for k, d in m.items():
            problems += refs(f"{owner} {k}", [x["card"] for x in d["cards"]])

    doc = {
        "schema": "magic2015-card-catalog/1",
        "generator": "build/cards/extract_cards.py",
        "rules": {
            "deck_size": {"min": 60, "max": 100},
            "copies_by_engine_rarity": {str(k): v for k, v in ENGINE_COPIES.items()},
            "basic_lands_limited": False,
            "collectible_cards": "cards listed in a card pool",
            "sources": {
                "deck_size.min": "game text: 'Decks must contain no less than 60 and no more "
                                 "than 100 cards in Duels of the Planeswalkers.'",
                "deck_size.max": "CRuntimeDeckConfiguration::AddCard refuses card 101",
                "copies": "CRuntimeCollection::AddCard, limit by CCardSpec::GetRarity",
                "collectible": "CRuntimeCollection::_InterrogateData iterates the card pools",
                "rarity": "MTG::CDataLoader::ParseRarity",
                "types": "Specs/*_Types.txt (Card_Types and Supertypes in engine enum order)",
            },
        },
        "enums": {
            "rarities": {code: {"label": label, "engine_value": v,
                                "max_copies": ENGINE_COPIES.get(v, 0)}
                         for code, label, v in RARITIES},
            "colours": COLOUR_NAMES,
            "card_types": {t: {"engine_value": i} for i, t in enumerate(card_types)},
            "supertypes": {t: {"engine_value": i} for i, t in enumerate(supertypes)},
            "subtypes": {k: {"card_types": sorted(set(v["card_types"]))}
                         for k, v in sorted(subtypes.items())},
        },
        "cards": cards,
        "card_pools": card_pools,
        "decks": deck_map,
        "booster_definitions": booster_map,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    for p in problems:
        print("canonical:", p)


def main():
    obb_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OBB
    out = sys.argv[2] if len(sys.argv) > 2 else HERE
    obb = Obb(obb_path)
    want = ("/Cards/", "/CardPools/", "/Decks/", "/BoosterDefinitions/", "/Specs/",
            "/Store/store_items.xml")

    cards, pools, decks, boosters, specs, store = {}, {}, {}, {}, {}, None
    conflicts = []
    for zed in sorted(obb.zeds):
        if not zed.startswith("DATA"):
            continue
        for e in obb.entries(zed):
            if e["us"] == 0 or not any(w in e["name"] for w in want):
                continue
            data = obb.read(e)
            rel = e["name"].split("/Data_All_Platforms/", 1)[-1]
            dst = os.path.join(out, "xml", zed[:-4], rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
            base = os.path.splitext(os.path.basename(rel))[0]
            if "/Specs/" in e["name"]:
                specs[os.path.basename(rel)] = data.decode("utf-8-sig")  # later packs override
                continue
            root = xml_root(data)
            if "/Store/" in e["name"]:
                store = root
            elif "/Cards/" in e["name"]:
                for el in ([root] if root.tag == "CARD_V2" else root.findall("CARD_V2")):
                    c = parse_card(el)
                    c["content_pack"] = zed[:-4]
                    prev = cards.get(c["id"])
                    if prev and {k: v for k, v in prev.items() if k != "content_pack"} != \
                            {k: v for k, v in c.items() if k != "content_pack"}:
                        conflicts.append(c["id"])
                    if not prev:
                        cards[c["id"]] = c
            elif "/CardPools/" in e["name"]:
                pools[base] = dict(attrs=root.attrib,
                                   cards=[(x.get("name"), x.get("id")) for x in root.findall("card")])
            elif "/Decks/" in e["name"]:
                decks[base] = root
            else:
                boosters[base] = root

    in_pools = defaultdict(list)
    for p, v in sorted(pools.items()):
        for n, _ in v["cards"]:
            in_pools[n].append(p)
    in_decks = defaultdict(set)
    for d, root in decks.items():
        for x in root.iter("CARD"):
            in_decks[deck_card(x.get("name"))[0]].add(d)
    in_boosters = defaultdict(set)
    for b, root in boosters.items():
        for x in root.iter():
            n = x.get("name") or x.get("card")
            if n in cards:
                in_boosters[n].add(b)

    rows = sorted(cards.values(), key=lambda c: (c["is_token"], c["name"].lower(), c["id"]))
    for c in rows:
        c["card_pools"] = in_pools.get(c["id"], [])
        # Collectible cards only; None means the card can't be in a player's collection.
        c["max_copies"] = MAX_COPIES.get(c["rarity"]) if c["card_pools"] else None
        c["decks"] = sorted(in_decks.get(c["id"], ()))
        c["booster_definitions"] = sorted(in_boosters.get(c["id"], ()))

    with open(os.path.join(out, "cards.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    cols = ["id", "name", "mana_cost", "cmc", "colors", "supertypes", "types", "subtypes", "power",
            "toughness", "rules_text", "flavour_text", "rarity", "expansion", "multiverse_id",
            "art_id", "artist", "is_token", "ai_base_score", "content_pack", "card_pools",
            "max_copies", "decks", "booster_definitions"]
    with open(os.path.join(out, "cards.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for c in rows:
            w.writerow([" ".join(c[k]) if k in ("supertypes", "types", "subtypes") else
                        "; ".join(c[k]) if isinstance(c[k], list) else c[k] for k in cols])

    write_canonical(os.path.join(out, "cards.canonical.json"), rows, pools, decks, boosters,
                    specs, store)

    n_tok = sum(c["is_token"] for c in rows)
    print(f"{len(rows)} cards ({len(rows) - n_tok} + {n_tok} tokens), {len(pools)} pools, "
          f"{len(decks)} decks, {len(boosters)} booster definitions -> {out}")
    if conflicts:
        print("differing duplicate definitions (first kept):", ", ".join(sorted(set(conflicts))))


if __name__ == "__main__":
    main()
