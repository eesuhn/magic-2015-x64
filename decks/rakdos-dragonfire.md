# Rakdos Dragonfire

A black-red (Rakdos) midrange deck for Magic 2015: 60 cards, 24 lands and 36 spells. It kills
almost every creature the opponent plays, builds a board of tokens with Young Pyromancer and Goblin
Rabblemaster, and finishes with flying demons and dragons. Every card is in the player
collection, no card goes over the game's own copy limit, and every cost and text below comes from
the game's data (`build/cards/cards.json`).

## Why this deck

- **17 removal spells, plus 3 creatures that remove.** Shock, Ulcerate, Auger Spree, Bolt of
  Keranos, Tribute to Hunger, Flesh to Dust and Banefire answer creatures at every mana cost.
  Shadowborn Demon destroys a creature when it enters, and Inferno Titan deals 3 damage every time
  it enters or attacks. Rune-Scarred Demon fetches whichever of these you need. The AI commits to
  the board, so trading one-for-one and then out-sizing it wins most games.
- **Removal builds the board too.** Each instant or sorcery makes a 1/1 Elemental with Young
  Pyromancer. Goblin Rabblemaster adds a hasty Goblin every turn.
- **Eight fliers at 5 mana or more close the game.** Stormbreath Dragon has haste and protection
  from white. Indulgent Tormentor draws a card or costs the opponent a creature or 3 life every
  turn. Bolt of Keranos and Banefire can go to the face for the last points.
- **Commons and uncommons do the heavy lifting.** Rares and mythics are capped at 2 and 1 copies,
  so the playsets are Shock, Bolt of Keranos and Phyrexian Rager (all common). The single-copy
  mythics are a bonus when drawn, and Rune-Scarred Demon can fetch them.

## Decklist

"Max" is the most copies the game lets you own (see the rules section).

### Creatures (19)

| Qty | Max | Card | Cost | Type | Text |
|---|---|---|---|---|---|
| 2 | 4 | Child of Night | `{1}{B}` | Creature — Vampire 2/1 | Lifelink |
| 3 | 3 | Young Pyromancer | `{1}{R}` | Creature — Human Shaman 2/1 | Whenever you cast an instant or sorcery spell, put a 1/1 red Elemental creature token onto the battlefield. |
| 2 | 2 | Goblin Rabblemaster | `{2}{R}` | Creature — Goblin Warrior 2/2 | Other Goblin creatures you control attack each turn if able. · At the beginning of combat on your turn, put a 1/1 red Goblin creature token with haste onto the battlefield. · Whenever Goblin Rabblemaster attacks, it gets +1/+0 until end of turn for each other attacking Goblin. |
| 4 | 4 | Phyrexian Rager | `{2}{B}` | Creature — Horror 2/2 | When Phyrexian Rager enters the battlefield, you draw a card and you lose 1 life. |
| 2 | 2 | Indulgent Tormentor | `{3}{B}{B}` | Creature — Demon 5/3 | Flying · At the beginning of your upkeep, draw a card unless target opponent sacrifices a creature or pays 3 life. |
| 1 | 1 | Shadowborn Demon | `{3}{B}{B}` | Creature — Demon 5/6 | Flying · When Shadowborn Demon enters the battlefield, destroy target non-Demon creature. · At the beginning of your upkeep, if there are fewer than six creature cards in your graveyard, sacrifice a creature. |
| 1 | 1 | Stormbreath Dragon | `{3}{R}{R}` | Creature — Dragon 4/4 | Flying, haste, protection from white · {5}{R}{R}: Monstrosity 3. · When Stormbreath Dragon becomes monstrous, it deals damage to each opponent equal to the number of cards in that player’s hand. |
| 1 | 1 | Inferno Titan | `{4}{R}{R}` | Creature — Giant 6/6 | {R}: Inferno Titan gets +1/+0 until end of turn. · Whenever Inferno Titan enters the battlefield or attacks, it deals 3 damage divided as you choose among one, two, or three target creatures and/or players. |
| 2 | 2 | Shivan Dragon | `{4}{R}{R}` | Creature — Dragon 5/5 | Flying · {R}: Shivan Dragon gets +1/+0 until end of turn. |
| 1 | 2 | Rune-Scarred Demon | `{5}{B}{B}` | Creature — Demon 6/6 | Flying · When Rune-Scarred Demon enters the battlefield, search your library for a card, put it into your hand, then shuffle your library. |

### Removal and burn (17)

| Qty | Max | Card | Cost | Type | Text |
|---|---|---|---|---|---|
| 4 | 4 | Shock | `{R}` | Instant | Shock deals 2 damage to target creature or player. |
| 3 | 3 | Ulcerate | `{B}` | Instant | Target creature gets -3/-3 until end of turn. You lose 3 life. |
| 2 | 4 | Auger Spree | `{1}{B}{R}` | Instant | Target creature gets +4/-4 until end of turn. |
| 4 | 4 | Bolt of Keranos | `{1}{R}{R}` | Sorcery | Bolt of Keranos deals 3 damage to target creature or player. Scry 1. |
| 2 | 3 | Tribute to Hunger | `{2}{B}` | Instant | Target opponent sacrifices a creature. You gain life equal to that creature’s toughness. |
| 1 | 4 | Flesh to Dust | `{3}{B}{B}` | Instant | Destroy target creature. It can’t be regenerated. |
| 1 | 2 | Banefire | `{X}{R}` | Sorcery | Banefire deals X damage to target creature or player. · If X is 5 or more, Banefire can’t be countered by spells or abilities and the damage can’t be prevented. |

### Lands (24)

| Qty | Max | Card | Text |
|---|---|---|---|
| 4 | 4 | Rakdos Guildgate | Rakdos Guildgate enters the battlefield tapped. · {T}: Add {B} or {R} to your mana pool. |
| 2 | 3 | Savage Lands | Savage Lands enters the battlefield tapped. · {T}: Add {B}, {R}, or {G} to your mana pool. |
| 10 | ∞ | Mountain | Basic land: {T}: add {R}. |
| 8 | ∞ | Swamp | Basic land: {T}: add {B}. |

## Mana curve

| Mana value | 1 | 2 | 3 | 4 | 5 | 6 | 7 | X |
|---|---|---|---|---|---|---|---|---|
| Spells | 7 | 5 | 14 | 0 | 5 | 3 | 1 | 1 |

Average mana value: **3.11** (Banefire not counted). There is no 4-drop on purpose: turn 4 is a
3-drop plus a 1-mana removal spell, or two removal spells.

## Mana base

Coloured mana symbols in the spells: **28 red, 23 black**. Red is needed early (Shock, Young
Pyromancer, Bolt of Keranos's `{R}{R}` on turn 3). Black's double costs come later (the demons and
Flesh to Dust at 5 to 7 mana). The basics lean red to match.

| Source | Red | Black |
|---|---|---|
| Rakdos Guildgate ×4 | 4 | 4 |
| Savage Lands ×2 | 2 | 2 |
| Mountain ×10 | 10 | — |
| Swamp ×8 | — | 8 |
| **Total (of 24 lands)** | **16** | **14** |

Odds of having the mana in time, on the play (hypergeometric, 60 cards):

| Need | By | Chance |
|---|---|---|
| Red source (Shock) | turn 1 (7 cards) | 90% |
| Black source (Ulcerate) | turn 1 (7 cards) | 86% |
| Two red sources (Bolt of Keranos) | turn 3 (9 cards) | 76% |
| Two black sources (Shadowborn Demon, Indulgent Tormentor) | turn 5 (11 cards) | 79% |
| Two red sources (Stormbreath Dragon) | turn 5 (11 cards) | 86% |
| Three lands | turn 3 (9 cards) | 79% |

Only the 6 dual lands enter tapped. Play them on turns where you don't need all your mana.

## How to play it

1. **Turns 1–3:** kill their early creatures with Shock or Ulcerate. Put down Young Pyromancer or
   Goblin Rabblemaster when the board is clear enough for them to survive. Phyrexian Rager keeps
   cards flowing, and Child of Night's lifelink pays back Ulcerate and Rager.
2. **Turns 4–5:** keep removing their best creature. Shadowborn Demon kills a creature and leaves a
   5/6 flier. Stormbreath Dragon attacks the turn it lands. Indulgent Tormentor taxes them
   every upkeep.
3. **Turn 6 on:** Inferno Titan, Shivan Dragon or Rune-Scarred Demon. Rune-Scarred Demon should
   fetch Inferno Titan when you're ahead and Flesh to Dust when you're behind. Use spare mana on
   Stormbreath's monstrosity (`{5}{R}{R}`) or a big Banefire (X ≥ 5 can't be prevented).

Things to watch:

- **Shadowborn Demon** makes you sacrifice a creature each upkeep while your graveyard has fewer
  than six creature cards. Feed it a Goblin or Elemental token. It can sacrifice itself if
  nothing else is around, and by then it has still killed a creature.
- **Goblin Rabblemaster** forces your other Goblins (its tokens) to attack each turn.
  Young Pyromancer's tokens are Elementals, so they can stay home and block.
- **Ulcerate** costs 3 life. Against fast decks, prefer Shock, Bolt of Keranos or Auger Spree.
- **Tribute to Hunger** is the answer to hexproof or protected creatures, because it doesn't target.

## Where the cards come from

| Card | Card pool | Rarity |
|---|---|---|
| Shock | Zendikar player pool | Common |
| Ulcerate | Shandalar player pool | Uncommon |
| Child of Night | Shandalar player pool | Common |
| Young Pyromancer | F15 Red booster | Uncommon |
| Goblin Rabblemaster | Ravnica player pool | Rare |
| Phyrexian Rager | DLC pool | Common |
| Bolt of Keranos | Theros player pool | Common |
| Auger Spree | Ravnica player pool | Common |
| Tribute to Hunger | Innistrad player pool | Uncommon |
| Indulgent Tormentor | Zendikar player pool | Rare |
| Shadowborn Demon | Shandalar player pool | Mythic |
| Stormbreath Dragon | Theros player pool | Mythic |
| Flesh to Dust | Ravnica player pool | Common |
| Inferno Titan | Ravnica player pool | Mythic |
| Shivan Dragon | Shandalar rewards | Rare |
| Rune-Scarred Demon | Shandalar player pool | Rare |
| Banefire | E15 player pool | Rare |
| Rakdos Guildgate | Ravnica supplemental land pool | Common |
| Savage Lands | E15 tri-land pool | Uncommon |

## Rules this deck follows (from the game binary)

All of these come from the x86 `libDuels.so`. The extractor's docstring
(`build/cards/extract_cards.py`) records the functions they come from.

- **Deck size:** the game allows 60 to 100 cards. The deck builder refuses a card once a deck has
  100 (`CRuntimeDeckConfiguration::AddCard`), and the game's text says "Decks must contain no
  less than 60 and no more than 100 cards". This deck uses the 60-card maximum asked for.
- **Copies per card:** you can only put in a deck the copies you own. The collection holds at most:

  | Rarity | Max copies |
  |---|---|
  | Common | 4 |
  | Uncommon | 3 |
  | Rare | 2 |
  | Mythic | 1 |

  The limit is set by the card's rarity (`CRuntimeCollection::AddCard`, `_InterrogateData`).
- **Basic lands** are added separately from the collection and have no limit.
- **Only card-pool cards are collectible.** The collection is built from the card pools. Cards that
  appear only in AI decks never enter it, so this deck uses none of them.
