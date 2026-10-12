"""User settings, persisted as JSON in the home directory."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

SETTINGS_PATH = Path.home() / ".ten_phases_settings.json"

DIFFICULTY_CHOICES = ("Easy", "Medium", "Hard", "Expert", "Mixed")
SPEED_CHOICES = ("Slow", "Normal", "Fast")
MAX_BLANKS = 60
SPEED_DELAYS = {"Slow": 1.1, "Normal": 0.65, "Fast": 0.25}
SFX_CHOICES = ("Off", "Low", "Medium", "High")
TEXT_STYLES = ("Pixel", "Smooth")
DEFAULT_TABLE = "#1e70e2"


@dataclass
class Settings:
    difficulty: str = "Medium"
    opponents: int = 3
    ai_speed: str = "Normal"
    hints: bool = True
    sort_by: str = "number"
    sfx: str = "Medium"
    player_name: str = "PLAYER"
    auto_update: bool = True
    chip_bank: int = 0   # chips kept from finished games
    game: str = "10 PHASES"   # which game the main menu shows
    owned_items: list = field(default_factory=lambda: ["face:classic", "back:classic"])  # shop purchases
    face_style: str = "classic"
    back_style: str = "classic"
    # Look
    table_color: str = DEFAULT_TABLE
    accent: str = "Yellow"
    card_back: str = "Red"
    card_palette: str = "Classic"
    text_style: str = "Pixel"
    sparkles: bool = True
    # Cards Against Humanity house options
    cah_packs: list = field(default_factory=lambda: [0])   # pack ids in the deck (0 = the base set)
    cah_blanks: int = 5                                      # blank cards shuffled into the deck
    cah_images: bool = True                                  # blank cards can carry a picture
    cah_points: int = 7                                      # points to win

    def reset_look(self) -> None:
        defaults = Settings()
        for name in ("table_color", "accent", "card_back", "card_palette", "text_style", "sparkles"):
            setattr(self, name, getattr(defaults, name))

    def opponent_difficulties(self) -> list[str]:
        if self.difficulty != "Mixed":
            return [self.difficulty] * self.opponents
        ladder = ["Easy", "Medium", "Hard", "Expert"]
        return [ladder[i % len(ladder)] for i in range(self.opponents)]

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or SETTINGS_PATH
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                return cls()
            known = {f.name for f in fields(cls)}
            s = cls(**{k: v for k, v in data.items() if k in known})
        except (OSError, ValueError, TypeError):
            return cls()
        # Anything of the wrong type (a hand-edited or damaged file) goes back to its default.
        defaults = cls()
        for f in fields(cls):
            want = type(getattr(defaults, f.name))
            value = getattr(s, f.name)
            if want is int and isinstance(value, float) and math.isfinite(value) and abs(value) < 1e12:
                setattr(s, f.name, int(value))
            elif not isinstance(value, want) or (want is int and isinstance(value, bool)):
                setattr(s, f.name, getattr(defaults, f.name))
        if s.difficulty not in DIFFICULTY_CHOICES:
            s.difficulty = "Medium"
        if s.ai_speed not in SPEED_CHOICES:
            s.ai_speed = "Normal"
        if s.sfx not in SFX_CHOICES:
            s.sfx = "Medium"
        if s.text_style not in TEXT_STYLES:
            s.text_style = "Pixel"
        try:
            if len(s.table_color) != 7 or not s.table_color.startswith("#"):
                raise ValueError
            int(s.table_color[1:], 16)
        except ValueError:
            s.table_color = DEFAULT_TABLE
        s.player_name = s.player_name[:24]
        from .skins import BY_ID, FREE_IDS
        if not isinstance(s.owned_items, list):
            s.owned_items = []
        s.owned_items = sorted({i for i in s.owned_items if isinstance(i, str) and i in BY_ID} | set(FREE_IDS))
        for attr, kind in (("face_style", "face"), ("back_style", "back")):
            if f"{kind}:{getattr(s, attr)}" not in s.owned_items:
                setattr(s, attr, "classic")
        if s.game not in ("10 PHASES", "GO FISH", "BLACKJACK", "POKER", "CAH", "SLOTS"):
            s.game = "10 PHASES"
        s.opponents = max(1, min(5, s.opponents))
        s.chip_bank = max(0, s.chip_bank)
        s.cah_packs = sorted({p for p in s.cah_packs if isinstance(p, int) and not isinstance(p, bool) and p >= 0}) \
            or [0]
        s.cah_blanks = max(0, min(MAX_BLANKS, s.cah_blanks))
        s.cah_points = max(3, min(20, s.cah_points))
        return s

    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS_PATH
        # Write a temp file and swap it in, so a crash mid-save can't wipe the Chip Bank.
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(asdict(self), indent=2))
            os.replace(tmp, path)
        except OSError:
            pass
