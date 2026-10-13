"""Deep Dig keeps one saved game next to the settings file, so you can stop and carry on later."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .. import settings
from .engine import DeepDig

SAVE_NAME = ".ten_phases_deepdig.json"


def save_path() -> Path:
    return Path(settings.SETTINGS_PATH).parent / SAVE_NAME


def save_game(game: DeepDig) -> None:
    path = save_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(game.to_dict()))
        os.replace(tmp, path)
    except OSError:
        pass


def load_game() -> DeepDig | None:
    try:
        data = json.loads(save_path().read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return DeepDig.from_dict(data)
    except (TypeError, ValueError):
        return None


def delete_save() -> None:
    try:
        save_path().unlink()
    except OSError:
        pass
