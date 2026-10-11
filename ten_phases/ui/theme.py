"""Colours, fonts and drawing helpers.

The look is a bright handheld-era card table: a blue sparkly background, blue
boxes with light outlines, chunky pixel-style lettering and a black status bar.
"""

from __future__ import annotations

import math
import random

import pygame

from ..cards import Color

WIDTH, HEIGHT = 1280, 800

# Table
BG = (30, 112, 226)
BG_DARK = (14, 52, 132)
SPARKLE = (88, 164, 250)
SPARKLE_BRIGHT = (170, 214, 255)
SCREEN_GAP = (12, 26, 60)

# Boxes
PANEL = (22, 88, 196)
PANEL_LIGHT = (40, 116, 222)
PANEL_HOVER = (52, 132, 236)
PANEL_EDGE = (150, 206, 255)
PANEL_SHADOW = (10, 44, 120)
INNER = (16, 70, 170)

TEXT = (255, 255, 255)
TEXT_DIM = (186, 218, 255)
TEXT_FAINT = (120, 166, 226)
OUTLINE = (8, 26, 70)
ACCENT = (255, 214, 40)        # yellow
ACCENT_DARK = (206, 150, 0)
ORANGE = (255, 164, 28)
SUCCESS = (90, 220, 110)
DANGER = (244, 70, 70)
INFO = (120, 220, 255)
STATUS_BAR = (0, 0, 0)

CARD_COLORS = {
    Color.RED: (232, 46, 52),
    Color.BLUE: (20, 108, 210),
    Color.GREEN: (52, 170, 76),
    Color.YELLOW: (252, 196, 18),
}
CARD_BLACK = (28, 28, 32)
CARD_WHITE = (255, 255, 255)

AVATAR_COLORS = [(255, 112, 90), (255, 214, 40), (110, 220, 130), (120, 220, 255), (210, 150, 255), (255, 160, 60)]
CHIP_COLORS = [(226, 40, 48), (40, 120, 230), (250, 200, 30)]

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


# --------------------------------------------------------------------------- pixel text

_pixel_cache: dict[tuple, pygame.Surface] = {}


def _pixel_font(base: int) -> pygame.font.Font:
    key = ("pixel", base)
    f = _font_cache.get(key)
    if f is None:
        path = pygame.font.match_font("pressstart2p,silkscreen,pixeloperator,freesansbold,dejavusans", bold=True)
        f = pygame.font.Font(path, base) if path else pygame.font.Font(None, int(base * 1.4))
        _font_cache[key] = f
    return f


def pixel_surface(msg: str, size: int = 18, color=TEXT, outline=OUTLINE) -> pygame.Surface:
    """Chunky, unsmoothed text with a 1-pixel outline, scaled up 2x like a handheld screen."""
    key = (msg, size, color, outline)
    img = _pixel_cache.get(key)
    if img is not None:
        return img
    if len(_pixel_cache) > 3000:
        _pixel_cache.clear()
    base = max(6, size // 2)
    f = _pixel_font(base)
    body = f.render(msg, False, color)
    w, h = body.get_size()
    small = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    if outline is not None:
        edge = f.render(msg, False, outline)
        for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2), (0, 0), (2, 2), (0, 2), (2, 0)):
            small.blit(edge, (dx, dy))
    small.blit(body, (1, 1))
    img = pygame.transform.scale(small, (small.get_width() * 2, small.get_height() * 2))
    _pixel_cache[key] = img
    return img


def ptext(surf, msg: str, pos, size: int = 18, color=TEXT, outline=OUTLINE, anchor: str = "topleft") -> pygame.Rect:
    img = pixel_surface(msg, size, color, outline)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def pixel_width(msg: str, size: int = 18) -> int:
    return pixel_surface(msg, size).get_width()


# --------------------------------------------------------------------------- smooth text


def text(surf: pygame.Surface, msg: str, pos, size: int = 18, color=TEXT, bold: bool = True,
         heavy: bool = False, anchor: str = "topleft") -> pygame.Rect:
    img = font(size, bold, heavy).render(msg, True, color)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def outlined(msg: str, size: int, color, outline=OUTLINE, width: int = 3, heavy: bool = True) -> pygame.Surface:
    f = font(size, True, heavy)
    body = f.render(msg, True, color)
    edge = f.render(msg, True, outline)
    w, h = body.get_size()
    out = pygame.Surface((w + width * 2 + 4, h + width * 2 + 4), pygame.SRCALPHA)
    for a in range(0, 360, 30):
        dx = round(math.cos(math.radians(a)) * width)
        dy = round(math.sin(math.radians(a)) * width)
        out.blit(edge, (width + dx, width + dy + 3))
    for a in range(0, 360, 30):
        dx = round(math.cos(math.radians(a)) * width)
        dy = round(math.sin(math.radians(a)) * width)
        out.blit(edge, (width + dx, width + dy))
    out.blit(body, (width, width))
    return out


def shadow_text(surf, msg, pos, size, color, shadow=OUTLINE, offset=3, heavy=True, anchor="center"):
    img = outlined(msg, size, color, shadow, max(2, offset - 1), heavy)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


_logo_cache: dict[tuple, pygame.Surface] = {}


def logo(surf, msg: str, center, size: int = 64, angle: float = 8, color=ACCENT, edge=OUTLINE) -> pygame.Rect:
    """A tilted, thick-outlined wordmark like a handheld game logo."""
    key = (msg, size, angle, color, edge)
    img = _logo_cache.get(key)
    if img is None:
        inner = outlined(msg, size, color, TEXT, max(2, size // 22))
        pad = max(4, size // 9)
        outer = pygame.Surface((inner.get_width() + pad * 2, inner.get_height() + pad * 2), pygame.SRCALPHA)
        mask = pygame.mask.from_surface(inner).to_surface(setcolor=(*edge, 255), unsetcolor=(0, 0, 0, 0))
        for a in range(0, 360, 20):
            dx = round(math.cos(math.radians(a)) * pad)
            dy = round(math.sin(math.radians(a)) * pad)
            outer.blit(mask, (pad + dx, pad + dy + pad // 2))
        outer.blit(inner, (pad, pad))
        img = pygame.transform.rotozoom(outer, angle, 1)
        _logo_cache[key] = img
    rect = img.get_rect(center=center)
    surf.blit(img, rect)
    return rect


# --------------------------------------------------------------------------- shapes


def rounded(surf, color, rect, radius: int = 12, width: int = 0):
    pygame.draw.rect(surf, color, rect, width, border_radius=radius)


def alpha_rect(surf, rgba, rect, radius: int = 12):
    tmp = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    pygame.draw.rect(tmp, rgba, tmp.get_rect(), border_radius=radius)
    surf.blit(tmp, (rect[0], rect[1]))


def panel(surf, rect, fill=PANEL, edge=PANEL_EDGE, radius: int = 10, shadow: bool = True, edge_w: int = 2):
    """A handheld-style box: solid fill, light outline, hard drop shadow."""
    rect = pygame.Rect(rect)
    if shadow:
        rounded(surf, PANEL_SHADOW, rect.move(-4, 5), radius)
    rounded(surf, fill, rect, radius)
    rounded(surf, edge, rect, radius, edge_w)


def lighten(color, amount: int = 24):
    return tuple(min(255, c + amount) for c in color[:3])


def darken(color, amount: int = 24):
    return tuple(max(0, c - amount) for c in color[:3])


def star(surf, center, r: float, color, thin: float = 0.28):
    """A four-pointed sparkle."""
    cx, cy = center
    t = r * thin
    pts = [(cx, cy - r), (cx + t, cy - t), (cx + r, cy), (cx + t, cy + t),
           (cx, cy + r), (cx - t, cy + t), (cx - r, cy), (cx - t, cy - t)]
    pygame.draw.polygon(surf, color, pts)


_bg_cache: dict[tuple, pygame.Surface] = {}


def background(split_y: int | None = None) -> pygame.Surface:
    """Blue sparkle backdrop. With split_y, a dark gap divides it into two 'screens'."""
    key = (split_y,)
    bg = _bg_cache.get(key)
    if bg is None:
        bg = pygame.Surface((WIDTH, HEIGHT))
        bg.fill(BG)
        rng = random.Random(10)
        for _ in range(70):
            x, y = rng.randrange(WIDTH), rng.randrange(HEIGHT)
            r = rng.choice([6, 8, 10, 14, 18, 26, 34])
            star(bg, (x, y), r, SPARKLE if r > 10 else SPARKLE_BRIGHT, 0.22)
        for _ in range(140):
            x, y = rng.randrange(WIDTH), rng.randrange(HEIGHT)
            pygame.draw.rect(bg, SPARKLE, (x, y, 3, 3))
        if split_y is not None:
            pygame.draw.rect(bg, SCREEN_GAP, (0, split_y - 5, WIDTH, 10))
            pygame.draw.line(bg, PANEL_EDGE, (0, split_y - 6), (WIDTH, split_y - 6), 2)
            pygame.draw.line(bg, PANEL_EDGE, (0, split_y + 5), (WIDTH, split_y + 5), 2)
        _bg_cache[key] = bg
    return bg


TWINKLES = [(random.Random(i).randrange(WIDTH), random.Random(i + 99).randrange(HEIGHT), i * 0.7) for i in range(14)]


def twinkle(surf, t: float):
    for x, y, phase in TWINKLES:
        k = (math.sin(t * 2.2 + phase) + 1) / 2
        if k > 0.35:
            star(surf, (x, y), 4 + 10 * k, SPARKLE_BRIGHT, 0.2)


def face(surf, center, r: int, idx: int, ring=None):
    """Round avatar: a light ring with a little black robot face."""
    ring = ring or AVATAR_COLORS[idx % len(AVATAR_COLORS)]
    cx, cy = center
    pygame.draw.circle(surf, OUTLINE, (cx, cy + 2), r + 2)
    pygame.draw.circle(surf, ring, center, r)
    pygame.draw.circle(surf, CARD_WHITE, center, int(r * 0.8))
    hw = int(r * 0.52)
    head = pygame.Rect(0, 0, hw * 2, int(hw * 1.7))
    head.center = (cx, cy + 1)
    rounded(surf, CARD_BLACK, head, max(3, r // 4))
    ey = head.y + head.h * 0.38
    ew = max(2, r // 6)
    style = idx % 3
    for sx in (-1, 1):
        ex = cx + sx * hw * 0.42
        if style == 1:
            pygame.draw.line(surf, CARD_WHITE, (ex - ew, ey), (ex + ew, ey), max(2, ew // 1))
        else:
            pygame.draw.rect(surf, CARD_WHITE, (ex - ew / 2, ey - ew / 2, ew, ew * (1.6 if style == 2 else 1)))
    my = head.y + head.h * 0.72
    if idx == 0:
        # The player gets a big grin.
        pygame.draw.rect(surf, CARD_WHITE, (cx - hw * 0.6, my - ew * 0.6, hw * 1.2, ew * 1.4), border_radius=2)
        for k in range(1, 4):
            x = cx - hw * 0.6 + k * hw * 0.3
            pygame.draw.line(surf, CARD_BLACK, (x, my - ew * 0.6), (x, my + ew * 0.8), 1)
    else:
        pygame.draw.line(surf, CARD_WHITE, (cx - hw * 0.4, my), (cx + hw * 0.4, my), max(2, ew // 2 + 1))


def chip(surf, center, r: int, color):
    cx, cy = center
    pygame.draw.ellipse(surf, darken(color, 70), (cx - r, cy - r * 0.5 + 3, r * 2, r))
    pygame.draw.ellipse(surf, color, (cx - r, cy - r * 0.5, r * 2, r))
    pygame.draw.ellipse(surf, CARD_WHITE, (cx - r * 0.6, cy - r * 0.3, r * 1.2, r * 0.6), 2)


def chip_stack(surf, base, r: int, color, count: int):
    for k in range(min(count, 8)):
        chip(surf, (base[0], base[1] - k * 5), r, color)


def mini_card_icon(surf, pos, color=CARD_WHITE):
    x, y = pos
    pygame.draw.rect(surf, OUTLINE, (x - 1, y - 1, 14, 18), border_radius=3)
    pygame.draw.rect(surf, color, (x, y, 12, 16), border_radius=2)
    pygame.draw.rect(surf, (226, 40, 48), (x + 3, y + 3, 6, 10), border_radius=2)
