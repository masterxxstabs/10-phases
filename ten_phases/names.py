"""Names for computer players. Each game picks a random handful."""

from __future__ import annotations

import random

# Short (7 letters or fewer) so they fit the player boxes in the pixel font.
AI_NAMES = (
    "ZACH", "RACHEL", "RYAN", "MAYA", "OTTO", "LUNA", "FINN", "IVY", "REX", "JUNO", "KAI", "NOVA",
    "ABBY", "BEAU", "CLEO", "DANTE", "EDDIE", "FAYE", "GUS", "HAZEL", "IGGY", "JADE", "KOJI", "LOLA",
    "MILO", "NINA", "OSCAR", "PIPER", "QUINN", "ROSA", "SAGE", "THEO", "UMA", "VIC", "WREN", "XAVI",
    "YUKI", "ZOE", "ARLO", "BIBI", "COCO", "DEXTER", "ELLA", "FELIX", "GIGI", "HUGO", "ISLA", "JAX",
    "KIKI", "LEO", "MOLLY", "NED", "OLIVE", "PABLO", "RUBY", "SAMMY", "TESS", "VERA", "WALLY", "ZIGGY",
    "BUSTER", "CHIP", "DOTTIE", "PEARL", "ROCCO", "SUNNY", "TOBY", "PENNY", "MOE", "LULU",
)


def pick_ai_names(count: int, taken=(), rng: random.Random | None = None) -> list[str]:
    """`count` different random names, avoiding any already `taken` (case-insensitive)."""
    rng = rng or random.Random()
    used = {str(t).upper() for t in taken}
    pool = [n for n in AI_NAMES if n not in used]
    rng.shuffle(pool)
    return pool[:count]
