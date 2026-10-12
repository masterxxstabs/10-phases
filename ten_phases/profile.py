"""Your profile: a picture, a background for your hover card, a name colour, and your level.

Pictures and backgrounds are bought in the shop with Chip Bank chips (a few are free, and a
few unlock by reaching a level). Name colours are free, apart from two level rewards.
In multiplayer each player's profile travels with them, so everyone sees everyone's.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .levels import MAX_LEVEL, level_for


class ProfileError(Exception):
    """Something you can't buy or equip; the message is shown to the player."""


@dataclass(frozen=True)
class Cosmetic:
    kind: str          # "avatar" or "banner"
    style: str
    name: str
    price: int = 0     # chips; 0 = free (or a level reward, see `level`)
    level: int = 0     # unlocks free at this level
    blurb: str = ""

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.style}"

    @property
    def free(self) -> bool:
        return self.price == 0 and self.level == 0


def _a(style, name, price=0, level=0, blurb=""):
    return Cosmetic("avatar", style, name, price, level, blurb)


def _b(style, name, price=0, level=0, blurb=""):
    return Cosmetic("banner", style, name, price, level, blurb)


AVATARS = (
    _a("robot", "ROBOT", blurb="The classic."),
    _a("smiley", "SMILEY"),
    _a("cat", "CAT"),
    _a("dog", "DOG"),
    _a("frog", "FROG"),
    _a("fox", "FOX", 150),
    _a("panda", "PANDA", 150),
    _a("bear", "BEAR", 150),
    _a("bunny", "BUNNY", 150),
    _a("owl", "OWL", 200),
    _a("penguin", "PENGUIN", 200),
    _a("pizza", "PIZZA", 200),
    _a("ghost", "GHOST", 250),
    _a("alien", "ALIEN", 250),
    _a("cool", "COOL GUY", 300, blurb="Sunglasses indoors."),
    _a("ninja", "NINJA", 300),
    _a("pirate", "PIRATE", 300),
    _a("skull", "SKULL", 350),
    _a("devil", "LITTLE DEVIL", 400),
    _a("wizard", "WIZARD", 450),
    _a("astronaut", "ASTRONAUT", 500),
    _a("koi", "KOI", 500),
    _a("unicorn", "UNICORN", 700),
    _a("dragon", "DRAGON", 800),
    _a("king", "THE KING", 1200, blurb="Crown included."),
    _a("star", "SUPERSTAR", level=10, blurb="Reach level 10."),
    _a("trophy", "CHAMPION", level=25, blurb="Reach level 25."),
)

BANNERS = (
    _b("classic", "CLASSIC", blurb="The table's own colours."),
    _b("midnight", "MIDNIGHT"),
    _b("forest", "FOREST"),
    _b("sunset", "SUNSET"),
    _b("stripes", "CANDY STRIPES", 150),
    _b("polka", "POLKA DOTS", 150),
    _b("checker", "CHECKERS", 150),
    _b("camo", "CAMO", 200),
    _b("waves", "WAVES", 200),
    _b("hearts", "HEARTS", 250),
    _b("stars", "STARRY NIGHT", 250),
    _b("ocean", "DEEP OCEAN", 300),
    _b("lava", "LAVA", 350),
    _b("neon", "NEON GRID", 400),
    _b("matrix", "CODE RAIN", 450),
    _b("koi", "KOI POND", 500),
    _b("galaxy", "GALAXY", 600),
    _b("aurora", "AURORA", 600),
    _b("rainbow", "RAINBOW", 800),
    _b("gold", "GOLD FOIL", 1200, blurb="It shines."),
    _b("royal", "ROYAL", level=15, blurb="Reach level 15."),
    _b("diamond", "DIAMOND", level=40, blurb="Reach level 40."),
)

# Name colours: (name, rgb, level needed). "rainbow" is drawn cycling through the colours.
NAME_COLORS = (
    ("WHITE", (255, 255, 255), 0), ("YELLOW", (255, 214, 40), 0), ("ORANGE", (255, 150, 40), 0),
    ("RED", (255, 84, 84), 0), ("PINK", (255, 120, 200), 0), ("PURPLE", (190, 130, 255), 0),
    ("BLUE", (110, 170, 255), 0), ("CYAN", (80, 230, 240), 0), ("GREEN", (90, 220, 110), 0),
    ("LIME", (190, 255, 80), 0), ("GOLD", (255, 200, 60), 10), ("RAINBOW", (255, 255, 255), 20),
)
COLOR_BY_NAME = {name: (rgb, lvl) for name, rgb, lvl in NAME_COLORS}

ITEMS = AVATARS + BANNERS
BY_ID = {c.id: c for c in ITEMS}
AVATAR_STYLES = {c.style for c in AVATARS}
BANNER_STYLES = {c.style for c in BANNERS}
FOR_SALE = [c for c in ITEMS if c.price]


def level_of(settings) -> int:
    return level_for(getattr(settings, "xp", 0))


def owns(settings, item_id: str) -> bool:
    item = BY_ID.get(item_id)
    if item is None:
        return False
    if item.free:
        return True
    if item.level:
        return level_of(settings) >= item.level
    return item_id in settings.owned_items


def color_unlocked(settings, name: str) -> bool:
    return name in COLOR_BY_NAME and level_of(settings) >= COLOR_BY_NAME[name][1]


def buy(settings, item_id: str) -> Cosmetic:
    """Spend chips on a picture or background (and equip it)."""
    item = BY_ID.get(item_id)
    if item is None:
        raise ProfileError("That isn't in the shop.")
    if owns(settings, item_id):
        return equip(settings, item_id)
    if item.level:
        raise ProfileError(f"Reach level {item.level} to unlock {item.name}.")
    if settings.chip_bank < item.price:
        raise ProfileError(f"You need {item.price - settings.chip_bank} more chips.")
    settings.chip_bank -= item.price
    settings.owned_items = sorted(set(settings.owned_items) | {item_id})
    return equip(settings, item_id)


def equip(settings, item_id: str) -> Cosmetic:
    item = BY_ID.get(item_id)
    if item is None or not owns(settings, item_id):
        raise ProfileError("You don't have that yet.")
    if item.kind == "avatar":
        settings.avatar = item.style
    else:
        settings.banner = item.style
    return item


def set_color(settings, name: str) -> None:
    if not color_unlocked(settings, name):
        lvl = COLOR_BY_NAME.get(name, (None, MAX_LEVEL))[1]
        raise ProfileError(f"Reach level {lvl} to unlock {name.title()}.")
    settings.name_color = name


def equipped(settings, item: Cosmetic) -> bool:
    return (settings.avatar if item.kind == "avatar" else settings.banner) == item.style


# --------------------------------------------------------------------------- profiles on the table


def my_profile(settings) -> dict:
    """What we send to other players (and draw for ourselves)."""
    return clean_profile({"a": settings.avatar, "b": settings.banner, "c": settings.name_color,
                          "l": level_of(settings)})


def clean_profile(value) -> dict:
    """A profile from the network or a file, with anything unknown swapped for a default."""
    d = value if isinstance(value, dict) else {}
    level = d.get("l")
    if not isinstance(level, int) or isinstance(level, bool):
        level = 1
    def pick(key, allowed, default):
        value = d.get(key)
        return value if isinstance(value, str) and value in allowed else default
    return {"a": pick("a", AVATAR_STYLES, "robot"), "b": pick("b", BANNER_STYLES, "classic"),
            "c": pick("c", COLOR_BY_NAME, "WHITE"), "l": max(1, min(MAX_LEVEL, level))}


def ai_profile(seed) -> dict:
    """A computer's profile: the same every time for the same name."""
    rng = random.Random(f"profile:{seed}")
    return {"a": rng.choice([a.style for a in AVATARS if not a.level]),
            "b": rng.choice([b.style for b in BANNERS if not b.level]),
            "c": rng.choice([n for n, _, lvl in NAME_COLORS if not lvl]), "l": rng.randint(1, 30)}


def player_profile(player) -> dict:
    """The profile a player shows: their own if we know it, otherwise a computer's pick."""
    prof = getattr(player, "profile", None)
    if prof:
        return clean_profile(prof)
    return ai_profile(player.name)
