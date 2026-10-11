"""Colours, fonts and small drawing helpers for the flat UI."""

from __future__ import annotations

import pygame

from ..cards import Color

WIDTH, HEIGHT = 1280, 800

# Flat palette
BG = (24, 32, 52)
BG_DARK = (17, 23, 38)
PANEL = (34, 45, 72)
PANEL_LIGHT = (46, 60, 94)
PANEL_HOVER = (56, 72, 112)
TEXT = (240, 244, 252)
TEXT_DIM = (150, 162, 190)
TEXT_FAINT = (98, 110, 140)
ACCENT = (255, 201, 60)       # yellow highlight
ACCENT_DARK = (214, 160, 20)
SUCCESS = (64, 196, 120)
DANGER = (238, 82, 83)
INFO = (72, 160, 255)
SHADOW = (0, 0, 0, 70)

# Card colours, bright and saturated like a classic shedding card game
CARD_COLORS = {
    Color.RED: (232, 46, 52),
    Color.BLUE: (20, 108, 210),
    Color.GREEN: (52, 170, 76),
    Color.YELLOW: (252, 196, 18),
}
CARD_BLACK = (28, 28, 32)
CARD_WHITE = (255, 255, 255)

AVATAR_COLORS = [(239, 108, 87), (90, 170, 250), (110, 205, 130), (250, 200, 80), (190, 130, 240), (80, 210, 210)]

_font_cache: dict[tuple, pygame.font.Font] = {}

_HEAVY = "arialblack,arial black,impact,montserratblack,montserrat,segoeuiblack,dejavusans,freesans"
_UI = "segoeui,inter,helvetica,arial,dejavusans,freesans"


def font(size: int, bold: bool = True, heavy: bool = False) -> pygame.font.Font:
    key = (size, bold, heavy)
    f = _font_cache.get(key)
    if f is None:
        names = _HEAVY if heavy else _UI
        path = pygame.font.match_font(names, bold=bold)
        f = pygame.font.Font(path, size) if path else pygame.font.Font(None, int(size * 1.3))
        if not path:
            f.set_bold(bold)
        _font_cache[key] = f
    return f


def text(surf: pygame.Surface, msg: str, pos, size: int = 18, color=TEXT, bold: bool = True,
         heavy: bool = False, anchor: str = "topleft") -> pygame.Rect:
    img = font(size, bold, heavy).render(msg, True, color)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def shadow_text(surf, msg, pos, size, color, shadow=(0, 0, 0), offset=3, heavy=True, anchor="center"):
    f = font(size, True, heavy)
    sh = f.render(msg, True, shadow)
    img = f.render(msg, True, color)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(sh, rect.move(offset, offset))
    surf.blit(img, rect)
    return rect


def rounded(surf, color, rect, radius: int = 12, width: int = 0):
    pygame.draw.rect(surf, color, rect, width, border_radius=radius)


def alpha_rect(surf, rgba, rect, radius: int = 12):
    tmp = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    pygame.draw.rect(tmp, rgba, tmp.get_rect(), border_radius=radius)
    surf.blit(tmp, (rect[0], rect[1]))


def lighten(color, amount: int = 24):
    return tuple(min(255, c + amount) for c in color[:3])


def darken(color, amount: int = 24):
    return tuple(max(0, c - amount) for c in color[:3])
