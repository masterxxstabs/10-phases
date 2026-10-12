"""The card shop: spend Chip Bank chips on card skins. Purely cosmetic, and only on your screen."""

from __future__ import annotations

from dataclasses import dataclass


class ShopError(Exception):
    """A purchase that can't happen; the message is shown to the player."""


@dataclass(frozen=True)
class Item:
    id: str          # "face:neon" / "back:gold"
    kind: str        # face (card fronts) or back
    style: str       # the card_art style name
    name: str
    price: int
    blurb: str


ITEMS = (
    Item("face:classic", "face", "classic", "CLASSIC", 0, "The original tilted oval"),
    Item("face:bubble", "face", "bubble", "BUBBLE", 60, "Round and bouncy"),
    Item("face:diamond", "face", "diamond", "DIAMOND", 90, "Sharp diamond centers"),
    Item("face:minimal", "face", "minimal", "MINIMAL", 120, "Big numbers, clean stripe"),
    Item("face:neon", "face", "neon", "NEON", 250, "Glowing outlines on black"),
    Item("face:gold", "face", "gold", "GOLD", 400, "Gold frames and trim"),
    Item("back:classic", "back", "classic", "CLASSIC", 0, "The original oval logo"),
    Item("back:checker", "back", "checker", "CHECKER", 50, "Checkerboard in your back color"),
    Item("back:stripes", "back", "stripes", "RACING STRIPES", 75, "Fast diagonal stripes"),
    Item("back:stars", "back", "stars", "STARRY NIGHT", 150, "A sky full of sparkles"),
    Item("back:neon", "back", "neon", "NEON GLOW", 200, "Glowing frame, dark card"),
    Item("back:galaxy", "back", "galaxy", "GALAXY", 300, "Purple space swirl"),
    Item("back:gold", "back", "gold", "GOLD EDITION", 500, "Black and gold, very fancy"),
)
BY_ID = {i.id: i for i in ITEMS}
FREE = [i.id for i in ITEMS if i.price == 0]


def owns(settings, item_id: str) -> bool:
    return item_id in settings.owned_items or BY_ID[item_id].price == 0


def equipped(settings, item: Item) -> bool:
    return (settings.face_style if item.kind == "face" else settings.back_style) == item.style


def buy(settings, item_id: str) -> Item:
    item = BY_ID[item_id]
    if owns(settings, item_id):
        raise ShopError("You already own that.")
    if settings.chip_bank < item.price:
        raise ShopError(f"You need {item.price - settings.chip_bank} more chips. Play a game or try the slots!")
    settings.chip_bank -= item.price
    settings.owned_items = sorted(set(settings.owned_items) | {item_id})
    return item


def equip(settings, item_id: str) -> Item:
    item = BY_ID[item_id]
    if not owns(settings, item_id):
        raise ShopError("Buy it first.")
    if item.kind == "face":
        settings.face_style = item.style
    else:
        settings.back_style = item.style
    return item
