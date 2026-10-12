"""The card shop: spend Chip Bank chips on card packs, and equip the skins you own.

A pack holds three skins. Each slot rolls a rarity from the pack's odds, then a
random skin of that rarity (fronts and backs alike). Skins you already own pay
out chips instead. Free skins are never in packs: everybody has them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .skins import BY_ID, COMMON, DUPLICATE_CHIPS, EPIC, FREE_IDS, IN_PACKS, LEGENDARY, RARE, RARITIES, Skin

__all__ = ["BY_ID", "PACKS", "PACK_BY_ID", "Pull", "ShopError", "buy_pack", "equip", "equipped", "owns",
           "collection", "open_pack"]


class ShopError(Exception):
    """A purchase that can't happen; the message is shown to the player."""


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    price: int
    slots: tuple[dict[str, float], ...]   # one rarity table per card, in reveal order
    colors: tuple[tuple[int, int, int], tuple[int, int, int]]   # foil light, foil dark
    blurb: str


BASIC_ODDS = {COMMON: 70, RARE: 23, EPIC: 6, LEGENDARY: 1}
PACKS = (
    Pack("basic", "BASIC PACK", 75, (BASIC_ODDS, BASIC_ODDS, BASIC_ODDS),
         ((70, 170, 255), (16, 64, 170)), "3 cards. Anything can happen!"),
    Pack("premium", "PREMIUM PACK", 200,
         (BASIC_ODDS, BASIC_ODDS, {RARE: 70, EPIC: 24, LEGENDARY: 6}),
         ((210, 120, 255), (80, 20, 150)), "3 cards. Last card is Rare or better."),
    Pack("legendary", "LEGENDARY PACK", 500,
         ({COMMON: 40, RARE: 40, EPIC: 15, LEGENDARY: 5}, {RARE: 60, EPIC: 30, LEGENDARY: 10},
          {EPIC: 72, LEGENDARY: 28}),
         ((255, 214, 70), (150, 80, 0)), "3 cards. Last card is Epic or better."),
)
PACK_BY_ID = {p.id: p for p in PACKS}


@dataclass
class Pull:
    skin: Skin
    new: bool           # first copy
    refund: int = 0     # chips paid out for a duplicate


def owns(settings, item_id: str) -> bool:
    return item_id in FREE_IDS or item_id in settings.owned_items


def equipped(settings, item: Skin) -> bool:
    return (settings.face_style if item.kind == "face" else settings.back_style) == item.style


def equip(settings, item_id: str) -> Skin:
    item = BY_ID[item_id]
    if not owns(settings, item_id):
        raise ShopError("Find it in a card pack first.")
    if item.kind == "face":
        settings.face_style = item.style
    else:
        settings.back_style = item.style
    return item


def collection(settings) -> tuple[int, int]:
    """(skins owned, skins in the game), free ones included."""
    return sum(owns(settings, s.id) for s in BY_ID.values()), len(BY_ID)


def odds_percent(pack: Pack) -> dict[str, float]:
    """Chance that a pack holds at least one card of each rarity, in percent."""
    out = {}
    for r in RARITIES:
        miss = 1.0
        for slot in pack.slots:
            miss *= 1 - slot.get(r, 0) / sum(slot.values())
        out[r] = 100 * (1 - miss)
    return out


def open_pack(pack: Pack, owned: set[str], rng: random.Random | None = None) -> list[Pull]:
    """Roll a pack's contents. Doesn't touch settings; `owned` is what the player has right now."""
    rng = rng or random.Random()
    owned = set(owned)
    taken: set[str] = set()
    pulls = []
    for slot in pack.slots:
        rarity = rng.choices(list(slot), weights=list(slot.values()))[0]
        pool = [s for s in IN_PACKS if s.rarity == rarity]
        fresh = [s for s in pool if s.id not in taken] or pool
        skin = rng.choice(fresh)
        taken.add(skin.id)
        new = skin.id not in owned
        owned.add(skin.id)
        pulls.append(Pull(skin, new, 0 if new else DUPLICATE_CHIPS[rarity]))
    return pulls


def buy_pack(settings, pack_id: str, rng: random.Random | None = None) -> list[Pull]:
    """Pay for a pack and add what's inside to the collection straight away (the opening is just for show)."""
    pack = PACK_BY_ID[pack_id]
    if settings.chip_bank < pack.price:
        raise ShopError(f"You need {pack.price - settings.chip_bank} more chips. Play a game or try the slots!")
    pulls = open_pack(pack, set(settings.owned_items) | set(FREE_IDS), rng)
    settings.chip_bank -= pack.price
    settings.chip_bank += sum(p.refund for p in pulls)
    settings.owned_items = sorted(set(settings.owned_items) | {p.skin.id for p in pulls})
    return pulls
