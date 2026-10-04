"""Shared helpers for the deck-builder scripts: load build/cards/cards.canonical.json and resolve
card names. Standard library only."""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CANONICAL = REPO / "build/cards/cards.canonical.json"
COLOURS = "WUBRG"
BASIC_COLOUR = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}


def load():
    if not CANONICAL.exists():
        sys.exit(f"{CANONICAL} is missing: run build/cards/extract_cards.py first")
    with open(CANONICAL, encoding="utf-8") as f:
        return json.load(f)


def norm(name):
    return re.sub(r"\s+", " ", name.replace("’", "'").strip().lower())


def is_basic(card):
    return "BASIC" in card["supertypes"] and "LAND" in card["types"]


class Catalog:
    def __init__(self):
        self.doc = load()
        self.cards = self.doc["cards"]
        self.by_name = {}
        for cid, c in self.cards.items():
            self.by_name.setdefault(norm(c["name"]), []).append(cid)

    def resolve(self, ref):
        """Card name or ID -> card ID. Prefers the collectible printing, then a non-token one."""
        if ref in self.cards:
            return ref
        ids = self.by_name.get(norm(ref), [])
        if not ids:
            return None
        return sorted(ids, key=lambda i: (not self.cards[i]["collectible"],
                                          self.cards[i]["is_token"], i))[0]

    def pools_of(self, cid):
        return [p for p, v in sorted(self.doc["card_pools"].items())
                if any(x["card"] == cid for x in v["cards"])]


def pips(cost):
    """Mana cost -> ({colour: count}, generic, has_x). Hybrid symbols count toward no colour."""
    out = {c: 0 for c in COLOURS}
    generic, has_x = 0, False
    for s in re.findall(r"\{([^}]*)\}", cost or ""):
        s = s.upper()
        if s.isdigit():
            generic += int(s)
        elif s in ("X", "Y", "Z"):
            has_x = True
        elif s in out:
            out[s] += 1
    return out, generic, has_x


def land_colours(card):
    """Colours a land can produce: basics by name, others from their '{T}: Add ...' text."""
    if card["name"] in BASIC_COLOUR:
        return {BASIC_COLOUR[card["name"]]}
    text = card["rules_text"] or ""
    found = set()
    for sentence in re.findall(r"Add ([^.]*)", text):
        found |= {c for c in re.findall(r"\{([WUBRG])\}", sentence)}
        if "any color" in sentence:
            found |= set(COLOURS)
    return found


def type_line(card):
    t = " ".join(x.title() for x in card["supertypes"] + card["types"])
    if card["subtypes"]:
        t += " — " + " ".join(x.replace("_", " ").title() for x in card["subtypes"])
    if card["power"] is not None:
        t += f" {card['power']}/{card['toughness']}"
    return t
