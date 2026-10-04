---
name: m15-deck-builder
description: Build, tune or review Magic 2015 (Duels of the Planeswalkers 2015) decks from this repo's extracted card data, following the game's real deck rules (deck size, per-rarity copy limits, collectible cards only) and balancing the lands against the spells' mana costs, then write the deck to decks/<name>.md, and put a decks/*.txt list into the game itself (a starting deck in every build, or a deck in an existing save). Use this whenever the user asks for a deck, a "best deck", a decklist, a mana base or land count, card choices for a colour or archetype, whether a deck is legal in Magic 2015, or to add, install or update a deck in the game or app, even if they don't say "skill" or name the files.
---

# Magic 2015 deck builder

The card data comes from the game itself (`build/cards/cards.canonical.json`, produced by
`build/cards/extract_cards.py`). Work from that file, not from memory of real-world Magic: the
game's pool is about 380 collectible cards, its copy limits differ from tabletop Magic, and card
text can differ from the printed versions.

## Rules to respect

Read them from the `rules` section of the canonical JSON. They come from the game binary, and at
the time of writing they are:

- **Deck size:** 60 to 100 cards. If the user gives a cap ("at most 60"), apply it on top.
- **Copies:** limited by rarity, not the usual 4 of anything. Common 4, uncommon 3, rare 2,
  mythic 1. Each card's `max_copies` already holds its limit.
- **Collectible only:** a card with `collectible: false` exists only in AI decks. The player can
  never own it, so never put one in a deck, however strong it looks.
- **Basic lands** (Plains, Island, Swamp, Mountain, Forest) are unlimited.
- **Legendary cards** are legal in multiples, but only one can be on the battlefield. Usually run
  one copy.

The rarity caps shape the deck. Only commons come as full playsets, so the backbone of a
consistent deck is commons and uncommons. Rares and mythics are 1–2-copy upgrades on top.

## Workflow

1. **Survey the pool.** List what's available, filtered as needed:

   ```
   python3 .claude/skills/m15-deck-builder/scripts/card_pool.py --colours BR
   python3 .claude/skills/m15-deck-builder/scripts/card_pool.py --type CREATURE --max-cmc 3
   ```

   Each line shows colours, cost, type, rarity, max copies and rules text. Read the whole
   candidate list for the colours you're considering before choosing. The strongest options are
   easy to miss when skimming.

2. **Pick a plan.** Unless the user names one, aim for the strongest deck against the game's AI.
   What usually wins:
   - **Cheap, efficient removal in quantity.** The AI commits creatures to the board, so killing
     them one-for-one and then landing bigger threats works well.
   - **A smooth curve:** enough 1–3 mana plays to act early, and a handful of 5–6 mana finishers.
   - **Evasion and card advantage:** fliers, haste, enters-the-battlefield value.
   - **Two colours.** Three is possible with the tri-lands and guildgates, but each tapped land
     costs tempo.

3. **Draft the list** as a text file, `decks/<slug>.txt`, with one `<count> <card name>` per
   line. `#` starts a comment, and basic lands go in by name. This file is the deck's source of
   truth, so it can be re-checked later.

4. **Check it and iterate:**

   ```
   python3 .claude/skills/m15-deck-builder/scripts/deck_check.py decks/<slug>.txt --max-cards 60
   ```

   It exits non-zero and prints `ERROR:` lines for anything illegal (unknown or non-collectible
   card, over the copy limit, wrong size, a colour with no land source). It also reports:
   - the curve and average mana value;
   - coloured pips against land sources;
   - the chance of having enough lands and each colour on curve.

   Fix errors and tune until the numbers are healthy (see below).

5. **Write `decks/<slug>.md`.** Run the checker with `--markdown` to get the decklist, curve,
   mana base, odds and card-origin tables, then add the prose around them (structure below).
   `decks/rakdos-dragonfire.md` is a finished example of the expected depth and tone.

6. **Put it in the game**, if the user wants to play it. See the next section.

## Putting a deck into the game

The `.txt` list becomes a real deck in the save file, `p1.profile`. The format and codec are in
`port/tools.py` (`GameProfile`); never edit a save by hand. Both routes below read the list the
same way `deck_check.py` does, so check the deck first.

- **The in-game name holds at most 15 characters.** The game cuts longer names, so pick a short
  name ("Dragonfire" for Rakdos Dragonfire). The `.md` title can stay long.
- **A deck can only use cards the save owns.** New installs start with every card at its copy
  limit. An older save may lack the booster-pack cards.

**Starting deck for every new install.**
1. Add `("<Name>", "<slug>.txt")` to `STARTING_DECKS` in `port/tools.py`.
2. Rebuild with `SKIP_GUEST=1 port/build.sh`. The build log prints
   `p1.profile: deck '<Name>' added from decks/<slug>.txt`.

This only reaches installs that don't have a profile yet. Existing saves are never overwritten.

**Into an existing save** (the emulator, or a rooted phone):

```
python3 .claude/skills/m15-deck-builder/scripts/install_deck.py decks/<slug>.txt --name "<Name>" --adb
python3 .claude/skills/m15-deck-builder/scripts/install_deck.py decks/<slug>.txt --name "<Name>" --save p1.profile --out p1.new.profile
```

- `--adb` force-stops the game, edits the live save, and keeps the old one on the device as
  `p1.profile.before-<Name>`.
- `--replace` updates a deck that already has that name.
- `--unlock` raises any card the save owns too few copies of to its copy limit. Without it, the
  script stops and lists them.
- Commands that talk to adb need the sandbox disabled.
- A non-rooted phone can't be edited this way. It gets decks through a new install.

After installing, ask the user to open the deck in the game and confirm it before going further.
If a save is ever corrupted, the game silently replaces it with a new, empty profile. A blank
collection or a reset player name means the edit went wrong, so restore the backup.

## Balancing lands to the mana costs

- **Land count:** 24 lands for an average mana value around 3 or more with 6-drops. Use 22–23
  for a low curve that tops out at 4. Below 22 risks missing land drops: check the "lands by turn
  N" lines.
- **Colour split:** start from the share of coloured pips, then shift toward the colour that needs
  to be there early (1-drops, `{R}{R}` on turn 3) or twice (`{B}{B}` costs). Double pips need far
  more sources than single pips.
- **Targets on the play:** about 85–90% for a colour you want on turn 1–2, and about 75–80% for
  double pips on curve. If the hardest requirement falls well short, add sources, reduce that
  colour's double-pip cards, or move them later in the curve.
- **Dual lands** (guildgates, tri-lands) fix colours but enter tapped. 4–6 is usually the sweet
  spot in a two-colour deck.

## Deck file structure

```markdown
# <Deck Name>

<2–3 sentences: colours, size, land/spell split, how it wins.>

## Why this deck
<3–4 bullets on what makes it strong, tied to specific cards.>

## Decklist
<tables from --markdown: creatures, other spells, lands (with the Max column)>

## Mana curve
<table + a line on the average mana value and any deliberate gaps>

## Mana base
<pips vs sources table, how the split was chosen, and the odds table>

## How to play it
<early / mid / late game steps, then card-specific gotchas>

## Where the cards come from
<card pool table>

## Rules this deck follows
<deck size, copy limits, collectible-only. Say they come from the game data.>
```

Give the deck an evocative name that hints at its colours or plan, and use a kebab-case slug of
that name for both files. Keep the `.txt` and `.md` lists identical. If you change one, re-run
the checker and regenerate the tables.

## When the data is missing

If `build/cards/cards.canonical.json` doesn't exist, run `python3 build/cards/extract_cards.py`
from the repo root. It needs the OBB, which is a Git LFS object, so `git lfs pull` may be needed
first.
