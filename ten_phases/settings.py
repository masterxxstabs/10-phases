"""User settings, persisted as JSON in the home directory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SETTINGS_PATH = Path.home() / ".ten_phases_settings.json"

DIFFICULTY_CHOICES = ("Easy", "Medium", "Hard", "Expert", "Mixed")
SPEED_CHOICES = ("Slow", "Normal", "Fast")
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
    # Look
    table_color: str = DEFAULT_TABLE
    accent: str = "Yellow"
    card_back: str = "Red"
    card_palette: str = "Classic"
    text_style: str = "Pixel"
    sparkles: bool = True

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
            known = {f.name for f in fields(cls)}
            s = cls(**{k: v for k, v in data.items() if k in known})
        except (OSError, ValueError, TypeError):
            return cls()
        if s.difficulty not in DIFFICULTY_CHOICES:
            s.difficulty = "Medium"
        if s.ai_speed not in SPEED_CHOICES:
            s.ai_speed = "Normal"
        if s.sfx not in SFX_CHOICES:
            s.sfx = "Medium"
        if s.text_style not in TEXT_STYLES:
            s.text_style = "Pixel"
        if not (isinstance(s.table_color, str) and len(s.table_color) == 7 and s.table_color.startswith("#")):
            s.table_color = DEFAULT_TABLE
        if s.game not in ("10 PHASES", "GO FISH", "BLACKJACK"):
            s.game = "10 PHASES"
        s.opponents = max(1, min(5, int(s.opponents)))
        s.chip_bank = max(0, int(s.chip_bank)) if isinstance(s.chip_bank, (int, float)) else 0
        return s

    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS_PATH
        try:
            path.write_text(json.dumps(asdict(self), indent=2))
        except OSError:
            pass
