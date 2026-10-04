#!/usr/bin/env python3
"""List the cards available for deck building, one line per card.

Usage: card_pool.py [--colours BR] [--type CREATURE] [--max-cmc 3] [--all]
  --colours  only cards whose colours are a subset of these (colourless cards always included)
  --type     only cards with this card type (ARTIFACT, CREATURE, INSTANT, LAND, ...)
  --max-cmc  only cards at or below this mana value
  --all      include cards that can't be collected (AI-only decks); never use these in a deck

Line format: [colours] Name cost | type line | rarity, max copies | rules text
"""
import argparse

from catalog import Catalog, type_line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colours", default=None)
    ap.add_argument("--type", default=None)
    ap.add_argument("--max-cmc", type=int, default=None)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    cat = Catalog()
    rows = []
    for cid, c in cat.cards.items():
        if c["is_token"] or (not c["collectible"] and not a.all):
            continue
        if a.colours is not None and not set(c["colours"]) <= set(a.colours.upper()):
            continue
        if a.type and a.type.upper() not in c["types"]:
            continue
        if a.max_cmc is not None and c["cmc"] > a.max_cmc:
            continue
        rows.append((len(c["colours"]) or 9, "".join(c["colours"]), c["cmc"], c["name"], cid))
    for _, _, _, _, cid in sorted(rows):
        c = cat.cards[cid]
        text = (c["rules_text"] or "").replace("\n", " · ")
        limit = c["max_copies"] if c["collectible"] else "not collectible"
        print(f"[{''.join(c['colours']) or '-'}] {c['name']} {c['mana_cost'] or ''} | "
              f"{type_line(c)} | {c['rarity']} max {limit} | {text}")
    print(f"# {len(rows)} cards")


if __name__ == "__main__":
    main()
