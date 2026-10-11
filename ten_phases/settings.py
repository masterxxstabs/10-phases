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


@dataclass
class Settings:
    difficulty: str = "Medium"
    opponents: int = 3
    ai_speed: str = "Normal"
    hints: bool = True
    sort_by: str = "number"
    sfx: str = "Medium"

    def opponent_difficulties(self) -> list[str]:
        if self.difficulty != "Mixed":
            return [self.difficulty] * self.opponents
        ladder = ["Easy", "Medium", "Hard", "Expert"]
        return [ladder[i % len(ladder)] for i in range(self.opponents)]

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "Settings":
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
        s.opponents = max(1, min(5, int(s.opponents)))
        return s

    def save(self, path: Path = SETTINGS_PATH) -> None:
        try:
            path.write_text(json.dumps(asdict(self), indent=2))
        except OSError:
            pass
