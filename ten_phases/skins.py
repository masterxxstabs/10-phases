"""Every card skin in the game, with its rarity.

Free skins belong to everybody from the start and never come out of packs.
Everything else is found in card packs (see shop.py). Skins travel with you in
multiplayer: the other players see your fronts on the cards you lay down and
your back on the cards in your hand.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

FREE, COMMON, RARE, EPIC, LEGENDARY = "FREE", "COMMON", "RARE", "EPIC", "LEGENDARY"
RARITIES = (COMMON, RARE, EPIC, LEGENDARY)
RARITY_COLORS = {
    FREE: (170, 200, 235),
    COMMON: (205, 215, 230),
    RARE: (80, 170, 255),
    EPIC: (196, 96, 255),
    LEGENDARY: (255, 200, 40),
}
# Chips back when a pack gives you a skin you already have.
DUPLICATE_CHIPS = {COMMON: 10, RARE: 25, EPIC: 60, LEGENDARY: 150}


@dataclass(frozen=True)
class Skin:
    id: str          # "face:neon" / "back:gold"
    kind: str        # face (card fronts) or back
    style: str       # the card_art style name
    name: str
    rarity: str
    blurb: str

    @property
    def free(self) -> bool:
        return self.rarity == FREE

    @property
    def color(self) -> tuple[int, int, int]:
        return RARITY_COLORS[self.rarity]


def _f(style, name, rarity, blurb):
    return Skin(f"face:{style}", "face", style, name, rarity, blurb)


def _b(style, name, rarity, blurb):
    return Skin(f"back:{style}", "back", style, name, rarity, blurb)


SKINS = (
    # Card fronts
    _f("classic", "CLASSIC", FREE, "The original tilted oval"),
    _f("bubble", "BUBBLE", FREE, "Round and bouncy"),
    _f("minimal", "MINIMAL", FREE, "Big numbers, clean stripe"),
    _f("diamond", "DIAMOND", COMMON, "Sharp diamond centers"),
    _f("ring", "HALO", COMMON, "A bright ring around the number"),
    _f("square", "BLOCK", COMMON, "A chunky tilted square"),
    _f("split", "TWO TONE", COMMON, "Light and dark halves"),
    _f("pinstripe", "PINSTRIPE", COMMON, "Sporty diagonal stripes"),
    _f("dots", "POLKA", RARE, "Polka dots everywhere"),
    _f("heart", "SWEETHEART", RARE, "Every number gets a heart"),
    _f("star", "SUPERSTAR", RARE, "A big star in the middle"),
    _f("comic", "KA-POW", RARE, "Comic book burst"),
    _f("neon", "NEON", EPIC, "Glowing outlines on black"),
    _f("glitch", "GLITCH", EPIC, "Scanlines and broken pixels"),
    _f("cosmic", "COSMIC", EPIC, "Your color, lost in space"),
    _f("gold", "GOLD", LEGENDARY, "Gold frames and trim"),
    _f("rainbow", "RAINBOW", LEGENDARY, "Rainbow frame, shining center"),
    _f("holo", "HOLO FOIL", LEGENDARY, "Shimmering holographic foil"),
    # Card backs
    _b("classic", "CLASSIC", FREE, "The original oval logo"),
    _b("checker", "CHECKER", FREE, "Checkerboard in your back color"),
    _b("stripes", "RACING STRIPES", FREE, "Fast diagonal stripes"),
    _b("dots", "BUBBLES", COMMON, "Bubbles floating up"),
    _b("waves", "WAVES", COMMON, "Rolling ocean waves"),
    _b("plaid", "PLAID", COMMON, "Cozy picnic plaid"),
    _b("zigzag", "ZIGZAG", COMMON, "Jagged zigzag bands"),
    _b("stars", "STARRY NIGHT", RARE, "A sky full of sparkles"),
    _b("honeycomb", "HONEYCOMB", RARE, "Sweet hexagon grid"),
    _b("sunset", "SUNSET", RARE, "Retro sun over the sea"),
    _b("circuit", "CIRCUIT", RARE, "Glowing circuit board"),
    _b("neon", "NEON GLOW", EPIC, "Glowing frame, dark card"),
    _b("lava", "LAVA", EPIC, "Hot molten rock"),
    _b("aurora", "AURORA", EPIC, "Northern lights"),
    _b("galaxy", "GALAXY", LEGENDARY, "Purple space swirl"),
    _b("gold", "GOLD EDITION", LEGENDARY, "Black and gold, very fancy"),
    _b("holo", "HOLOGRAM", LEGENDARY, "Shifting holographic foil"),
)
# The koi pond set: line-drawn koi over seigaiha waves.
SKINS += (
    _f("koi", "KOI POND", LEGENDARY, "Koi circling your number"),
    _b("koi", "KOI POND", LEGENDARY, "Koi swimming over the waves"),
)

# ---------------------------------------------------------------------------- generated skins
#
# Beyond the hand-made skins, the game invents a big collection of its own. Each
# one is rebuilt from its number every time (same number, same skin), so there's
# nothing to store and every copy of the game agrees on what "g042" looks like.

GENERATED = 96          # of each kind
FOIL_SERIES = 32        # plus this many all-foil skins of each kind
PATTERNS = ("dots", "stripes", "checker", "waves", "zigzag", "scales", "hex", "triangles", "diamonds", "rings",
            "crosses", "confetti", "stars", "chevrons", "grid", "bubbles", "plaid", "sunburst")
FOILS = ("rainbow", "gold", "silver", "prism", "aurora")
SHAPES = ("oval", "circle", "diamond", "square", "ring", "heart", "star", "burst")
_ADJ = ("ARCTIC", "ATOMIC", "BLAZING", "BRIGHT", "CANDY", "COSMIC", "CRYSTAL", "CYBER", "DUSTY", "ELECTRIC", "EMBER",
        "FIZZY", "FROSTED", "FUNKY", "GHOST", "GLOWING", "GROOVY", "HYPER", "JUNGLE", "LUCKY", "LUNAR", "MAGIC",
        "MIDNIGHT", "MINTY", "MISTY", "MYSTIC", "NOVA", "OCEAN", "PASTEL", "PIXEL", "PLASMA", "POLAR", "RETRO",
        "ROYAL", "RUSTY", "SHADOW", "SOLAR", "SPICY", "STORMY", "SUGAR", "SUNNY", "TURBO", "VELVET", "VIVID",
        "WILD", "ZESTY")
_NOUN = ("BLOOM", "BREEZE", "CANYON", "COMET", "CORAL", "CRUSH", "DREAM", "DRIFT", "ECHO", "FLARE", "FROST", "GALE",
         "GROVE", "HAZE", "JAM", "LAGOON", "MAZE", "MIRAGE", "ORBIT", "PARADE", "PEAK", "PULSE", "QUARTZ", "RIPPLE",
         "RUSH", "SIGNAL", "SPARK", "SPLASH", "STORM", "SWIRL", "TIDE", "VAULT", "VIBE", "WAVE", "ZONE")
_GEN_RARITY = {COMMON: 56, RARE: 28, EPIC: 11, LEGENDARY: 5}


_FOIL_RARITY = {RARE: 50, EPIC: 35, LEGENDARY: 15}


def parse_gen(style) -> tuple[str, int] | None:
    """("g", 12) for style "g012" (generated), ("f", 3) for "f003" (foil series), else None."""
    if isinstance(style, str) and len(style) == 4 and style[0] in "gf" and style[1:].isdigit():
        return style[0], int(style[1:])
    return None


def gen_spec(kind: str, n: int, series: str = "g") -> dict:
    """The recipe for generated skin number n (pure numbers; card_art turns it into pixels)."""
    rng = random.Random(f"gen-{kind}-{n}" if series == "g" else f"foil-{kind}-{n}")
    table = _GEN_RARITY if series == "g" else _FOIL_RARITY
    rarity = rng.choices(list(table), weights=list(table.values()))[0]
    spec = {
        "rarity": rarity,
        "pattern": PATTERNS[(n * 7 + rng.randrange(len(PATTERNS))) % len(PATTERNS)],
        "scale": rng.choice((0.7, 0.85, 1.0, 1.2, 1.5)),
        "hue": rng.random(),
        "scheme": rng.choice(("mono", "complement", "analog", "triad")),
        "dark": rng.random() < 0.45,
        "seed": rng.randrange(1_000_000),
    }
    if kind == "face":
        spec.update(shape=rng.choice(SHAPES), tint=rng.choice(("light", "dark", "white")),
                    frame=rng.choice(("white", "white", "black", "palette")), num=rng.choice(("color", "color", "white")),
                    ring=rng.random() < 0.35)
    else:
        spec.update(medallion=rng.choice(("circle", "oval", "hex", "diamond", "banner")))
    if rarity in (EPIC, LEGENDARY):
        spec["frame"] = rng.choice(("gold", "rainbow", "holo")) if rarity == LEGENDARY else rng.choice(("palette", "black"))
    # Foil finishes: every legendary, most epics, some rares.
    if series == "f" or rng.random() < {COMMON: 0.0, RARE: 0.3, EPIC: 0.7, LEGENDARY: 1.0}[rarity]:
        spec["foil"] = FOILS[n % len(FOILS)] if series == "f" else rng.choice(FOILS)
    return spec


def _gen_name(kind: str, n: int, attempt: int = 0) -> str:
    rng = random.Random(f"gen-name-{kind}-{n}-{attempt}")
    return f"{rng.choice(_ADJ)} {rng.choice(_NOUN)}"


def _gen_name_for(kind: str, n: int, series: str, spec: dict, attempt: int = 0) -> str:
    if series == "g":
        return _gen_name(kind, n, attempt)
    return f"{spec['foil'].upper()} {_gen_name(kind, n, 50 + attempt).split()[1]}"


def _generated() -> tuple[Skin, ...]:
    out, used = [], set()
    for series, count in (("g", GENERATED), ("f", FOIL_SERIES)):
        for kind in ("face", "back"):
            for n in range(count):
                spec = gen_spec(kind, n, series)
                name, k = _gen_name_for(kind, n, series, spec), 1
                while (kind, name) in used:
                    name, k = _gen_name_for(kind, n, series, spec, k), k + 1
                used.add((kind, name))
                style = f"{series}{n:03d}"
                blurb = f"{spec['pattern'].title()} pattern, {spec['scheme']} colors"
                if spec.get("foil"):
                    blurb = f"{spec['foil'].title()} foil, {spec['pattern']} pattern"
                out.append(Skin(f"{kind}:{style}", kind, style, name, spec["rarity"], blurb))
    return tuple(out)


SKINS += _generated()
BY_ID = {s.id: s for s in SKINS}
FACE_STYLES = {s.style for s in SKINS if s.kind == "face"}
BACK_STYLES = {s.style for s in SKINS if s.kind == "back"}
FREE_IDS = [s.id for s in SKINS if s.free]
IN_PACKS = [s for s in SKINS if not s.free]


def by_rarity(rarity: str) -> list[Skin]:
    return [s for s in SKINS if s.rarity == rarity]


def safe_face(style) -> str:
    """A front style we can draw (anything unknown, e.g. from a newer version, shows as classic)."""
    return style if style in FACE_STYLES else "classic"


def safe_back(style) -> str:
    return style if style in BACK_STYLES else "classic"


def random_skin(seed) -> tuple[str, str]:
    """A (face, back) pair for a computer player, the same every time for the same seed (its name)."""
    rng = random.Random(f"skin:{seed}")
    faces = [s.style for s in SKINS if s.kind == "face"]
    backs = [s.style for s in SKINS if s.kind == "back"]
    return rng.choice(faces), rng.choice(backs)


def clean_skin(value) -> tuple[str, str]:
    """A (face, back) pair from the network, with anything unknown swapped for classic."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return safe_face(value[0]), safe_back(value[1])
    return "classic", "classic"


def player_skin(player) -> tuple[str, str]:
    """The skins a player shows: their own if we know them, otherwise a random pick (computers)."""
    skin = getattr(player, "skin", None)
    if skin:
        return clean_skin(skin)
    return random_skin(player.name)
