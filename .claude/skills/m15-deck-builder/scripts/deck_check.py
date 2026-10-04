#!/usr/bin/env python3
"""Validate a decklist against the game's rules and report its mana curve and colour odds.

Usage: deck_check.py DECKLIST [--max-cards 60] [--markdown]
  DECKLIST     text file, one "<count> <card name or ID>" per line; blank lines and lines
               starting with # are ignored. Basic lands go in by name ("10 Mountain").
  --max-cards  the user's cap; the game's own limits (rules.deck_size) always apply too
  --markdown   also print the decklist, curve, mana base, odds and card origin tables

Exits 1 when the deck breaks a rule (unknown card, not collectible, over the copy limit, wrong
size). Odds are on the play: by turn T you have seen 6 + T cards.
"""
import argparse
import math
import re
import sys
from collections import Counter, defaultdict

from catalog import COLOURS, Catalog, is_basic, land_colours, pips, type_line

COLOUR_NAMES = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}


def p_at_least(k, successes, draws, deck):
    if k <= 0:
        return 1.0
    draws = min(draws, deck)
    if deck <= 0 or k > min(successes, draws):
        return 0.0
    return 1 - sum(math.comb(successes, i) * math.comb(deck - successes, draws - i)
                   for i in range(k)) / math.comb(deck, draws)


def parse(path):
    entries = []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"(\d+)\s*x?\s+(.+)", line)
        if not m:
            sys.exit(f"{path}:{n}: expected '<count> <card>', got {line!r}")
        entries.append((int(m.group(1)), m.group(2).strip()))
    return entries


def cell(s):
    return (s or "").replace("|", "\\|").replace("\n", " · ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("decklist")
    ap.add_argument("--max-cards", type=int, default=None)
    ap.add_argument("--markdown", action="store_true")
    a = ap.parse_args()
    cat = Catalog()
    rules = cat.doc["rules"]["deck_size"]
    lo, hi = rules["min"], rules["max"]
    if a.max_cards is not None:
        hi = min(hi, a.max_cards)

    errors, notes = [], []
    deck = Counter()
    for qty, ref in parse(a.decklist):
        cid = cat.resolve(ref)
        if cid is None:
            errors.append(f"unknown card: {ref}")
            continue
        deck[cid] += qty
    for cid, qty in deck.items():
        c = cat.cards[cid]
        if is_basic(c):
            continue
        if not c["collectible"]:
            errors.append(f"{c['name']}: not collectible (only in AI decks)")
        elif qty > c["max_copies"]:
            errors.append(f"{c['name']}: {qty} copies, the limit for rarity {c['rarity']} is "
                          f"{c['max_copies']}")
        if "LEGENDARY" in c["supertypes"] and qty > 1:
            notes.append(f"{c['name']} is legendary: only one can be on the battlefield")
    total = sum(deck.values())
    if not lo <= total <= hi:
        errors.append(f"deck has {total} cards, needs {lo}–{hi}")

    lands = {cid: q for cid, q in deck.items() if "LAND" in cat.cards[cid]["types"]}
    spells = {cid: q for cid, q in deck.items() if cid not in lands}
    n_lands = sum(lands.values())
    sources = Counter()
    tapped = 0
    for cid, q in lands.items():
        for col in land_colours(cat.cards[cid]):
            sources[col] += q
        if "enters the battlefield tapped" in (cat.cards[cid]["rules_text"] or ""):
            tapped += q

    pip_total, curve = Counter(), Counter()
    needs = defaultdict(list)  # (colour, pips, turn) -> card names
    mv_sum = mv_n = 0
    for cid, q in spells.items():
        c = cat.cards[cid]
        p, _, has_x = pips(c["mana_cost"])
        curve["X" if has_x else min(c["cmc"], 7)] += q
        if not has_x:
            mv_sum += c["cmc"] * q
            mv_n += q
        turn = max(c["cmc"], 1)
        for col in COLOURS:
            if p[col]:
                pip_total[col] += p[col] * q
                needs[(col, p[col], turn)].append(c["name"])
    used = [col for col in COLOURS if pip_total[col]]
    for col in used:
        if not sources[col]:
            errors.append(f"no land produces {COLOUR_NAMES[col]} mana")

    print(f"cards {total} (lands {n_lands}, spells {sum(spells.values())}); limit {lo}–{hi}")
    print(f"average mana value {mv_sum / mv_n:.2f} (X spells excluded)" if mv_n else "")
    print("curve", {k: curve[k] for k in [1, 2, 3, 4, 5, 6, 7, "X"] if curve[k]},
          "| 0-cost:", curve[0])
    print("coloured pips", {col: pip_total[col] for col in used},
          "| land sources", {col: sources[col] for col in used}, f"| enters tapped {tapped}")
    odds = []
    for (col, k, turn), names in sorted(needs.items(), key=lambda x: (x[0][2], x[0][0], x[0][1])):
        pr = p_at_least(k, sources[col], 6 + turn, total) if total else 0
        odds.append((col, k, turn, pr, names))
    for t in range(2, 6):
        print(f"P(>= {t} lands by turn {t}) = {p_at_least(t, n_lands, 6 + t, total):.0%}")
    worst = {}
    for col, k, turn, pr, names in odds:
        if col not in worst or pr < worst[col][3]:
            worst[col] = (col, k, turn, pr, names)
    for col, k, turn, pr, names in worst.values():
        print(f"hardest {COLOUR_NAMES[col]} requirement: {k}× by turn {turn} = {pr:.0%} "
              f"({', '.join(sorted(set(names))[:3])})")
    for n in notes:
        print("note:", n)
    for e in errors:
        print("ERROR:", e)

    if a.markdown:
        print_markdown(cat, deck, lands, spells, curve, pip_total, sources, used, odds, total)
    sys.exit(1 if errors else 0)


def print_markdown(cat, deck, lands, spells, curve, pip_total, sources, used, odds, total):
    def group(ids):
        return sorted(ids, key=lambda i: (cat.cards[i]["cmc"], cat.cards[i]["name"]))

    creatures = [i for i in spells if "CREATURE" in cat.cards[i]["types"]]
    others = [i for i in spells if i not in creatures]
    print()
    for title, ids in (("Creatures", creatures), ("Other spells", others)):
        if not ids:
            continue
        print(f"### {title} ({sum(deck[i] for i in ids)})\n")
        print("| Qty | Max | Card | Cost | Type | Text |\n|---|---|---|---|---|---|")
        for i in group(ids):
            c = cat.cards[i]
            print(f"| {deck[i]} | {c['max_copies']} | {c['name']} | `{c['mana_cost'] or '—'}` | "
                  f"{type_line(c)} | {cell(c['rules_text'])} |")
        print()
    print(f"### Lands ({sum(lands.values())})\n")
    print("| Qty | Max | Card | Produces | Text |\n|---|---|---|---|---|")
    for i in sorted(lands, key=lambda i: (is_basic(cat.cards[i]), cat.cards[i]["name"])):
        c = cat.cards[i]
        mx = "∞" if is_basic(c) else c["max_copies"]
        prod = "".join(f"{{{x}}}" for x in COLOURS if x in land_colours(c))
        text = "Basic land" if is_basic(c) else cell(c["rules_text"])
        print(f"| {lands[i]} | {mx} | {c['name']} | {prod} | {text} |")
    keys = [k for k in [0, 1, 2, 3, 4, 5, 6, 7, "X"] if curve[k]]
    print("\n### Mana curve\n")
    print("| Mana value | " + " | ".join("7+" if k == 7 else str(k) for k in keys) + " |")
    print("|---|" + "---|" * len(keys))
    print("| Spells | " + " | ".join(str(curve[k]) for k in keys) + " |")
    print("\n### Mana base\n")
    print("| Colour | Pips in spells | Land sources |\n|---|---|---|")
    for col in used:
        print(f"| {COLOUR_NAMES[col].title()} | {pip_total[col]} | {sources[col]} |")
    print("\n### Odds of having the colours on curve (on the play)\n")
    print("| Need | By turn | Chance | Cards |\n|---|---|---|---|")
    for col, k, turn, pr, names in odds:
        print(f"| {k}× {COLOUR_NAMES[col]} | {turn} | {pr:.0%} | {', '.join(sorted(set(names)))} |")
    print("\n### Where the cards come from\n")
    print("| Card | Rarity | Card pools |\n|---|---|---|")
    for i in sorted(deck, key=lambda i: cat.cards[i]["name"]):
        c = cat.cards[i]
        if not is_basic(c):
            print(f"| {c['name']} | {c['rarity']} | {', '.join(cat.pools_of(i))} |")


if __name__ == "__main__":
    main()
