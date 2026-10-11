"""Render the app icon to packaging/build/icon.png (+ .ico on any OS, .icns on macOS).

Usage: python tools/make_icon.py
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

OUT = ROOT / "packaging" / "build"


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    from ten_phases.ui.card_art import app_icon

    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / "icon.png"
    pygame.image.save(app_icon(512), str(png))
    from PIL import Image

    img = Image.open(png)
    img.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    if sys.platform == "darwin":
        img.save(OUT / "icon.icns")
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
