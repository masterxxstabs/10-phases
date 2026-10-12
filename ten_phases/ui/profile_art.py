"""Drawing profiles: profile pictures, hover-card backgrounds, name colours and level badges.

Everything is drawn in code. Pictures are drawn 4x big and smoothed down, then cached.
"""

from __future__ import annotations

import colorsys
import math
import random

import pygame

from ..profile import COLOR_BY_NAME, ai_profile, my_profile, player_profile
from . import theme

SS = 4   # supersampling for the pictures
_cache: dict = {}

INK = (30, 30, 40)
WHITE = (250, 250, 250)


# --------------------------------------------------------------------------- whose profile


def seat_profile(scene, i) -> dict:
    """The profile for a seat at a table: seat 0 is always you (your current settings)."""
    if i == 0:
        return my_profile(scene.app.settings)
    players = scene.game.players
    if isinstance(i, int) and 0 <= i < len(players):
        return player_profile(players[i])
    return ai_profile(i)


# --------------------------------------------------------------------------- name colours


def name_rgb(prof: dict, clock: float = 0.0) -> tuple[int, int, int]:
    name = prof.get("c", "WHITE")
    if name == "RAINBOW":
        r, g, b = colorsys.hsv_to_rgb((clock * 0.25) % 1.0, 0.55, 1.0)
        return int(r * 255), int(g * 255), int(b * 255)
    return COLOR_BY_NAME.get(name, ((255, 255, 255), 0))[0]


def swatch_rgb(name: str, clock: float = 0.0) -> tuple[int, int, int]:
    return name_rgb({"c": name}, clock)


# --------------------------------------------------------------------------- level badge


def level_badge(surf, center, level: int, size: int = 14):
    """A little gold badge with the level number."""
    text = str(level)
    img = theme.pixel_surface(text, max(8, size - 2), INK, None)
    w = max(size * 2, img.get_width() + 10)
    r = pygame.Rect(0, 0, w, size + 6)
    r.center = center
    pygame.draw.rect(surf, theme.OUTLINE, r.move(0, 2), border_radius=r.h // 2)
    pygame.draw.rect(surf, (255, 206, 60), r, border_radius=r.h // 2)
    pygame.draw.rect(surf, (255, 240, 170), r.inflate(-4, -r.h + 4).move(0, -r.h // 4), border_radius=2)
    pygame.draw.rect(surf, theme.OUTLINE, r, 2, border_radius=r.h // 2)
    surf.blit(img, img.get_rect(center=(r.centerx, r.centery + 1)))
    return r


# --------------------------------------------------------------------------- pictures


def avatar(surf, center, r: int, prof: dict | None, idx: int = 0, level: bool = False):
    """Draw a player's profile picture (the robot is the table's own face, coloured by seat)."""
    style = (prof or {}).get("a", "robot")
    if style == "robot" or r < 6:
        theme.face(surf, center, r, idx)
    else:
        img = avatar_surface(style, r)
        cx, cy = center
        pygame.draw.circle(surf, theme.OUTLINE, (cx, cy + 2), r + 2)
        surf.blit(img, img.get_rect(center=center))
    if level and prof:
        level_badge(surf, (center[0] + int(r * 0.7), center[1] + int(r * 0.85)), prof.get("l", 1),
                    max(10, r // 2))


def avatar_surface(style: str, r: int) -> pygame.Surface:
    key = ("avatar", style, r)
    if key in _cache:
        return _cache[key]
    R = r * SS
    big = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
    draw = _AVATARS.get(style, _smiley)
    pic = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
    draw(pic, R, R, R)
    mask = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (R, R), R)
    pic.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    big.blit(pic, (0, 0))
    pygame.draw.circle(big, WHITE, (R, R), R, max(2, R // 12))
    img = pygame.transform.smoothscale(big, (r * 2, r * 2))
    _cache[key] = img
    return img


def _bg(s, R, color, color2=None):
    if color2 is None:
        s.fill(color)
        return
    for y in range(0, 2 * R, 4):
        k = y / (2 * R)
        c = [int(color[i] + (color2[i] - color[i]) * k) for i in range(3)]
        pygame.draw.rect(s, c, (0, y, 2 * R, 4))


def _e(s, color, cx, cy, w, h, width=0):
    pygame.draw.ellipse(s, color, (int(cx - w / 2), int(cy - h / 2), int(w), int(h)), width)


def _c(s, color, cx, cy, rad, width=0):
    pygame.draw.circle(s, color, (int(cx), int(cy)), max(1, int(rad)), width)


def _poly(s, color, pts, width=0):
    pygame.draw.polygon(s, color, [(int(x), int(y)) for x, y in pts], width)


def _eyes(s, cx, cy, u, gap=0.32, size=0.1, color=INK, shine=True):
    for sx in (-1, 1):
        _c(s, color, cx + sx * u * gap, cy, u * size)
        if shine:
            _c(s, WHITE, cx + sx * u * gap + u * size * 0.35, cy - u * size * 0.35, u * size * 0.35)


def _smile(s, cx, cy, u, w=0.5, color=INK, width=0.06):
    rect = pygame.Rect(0, 0, int(u * w), int(u * w * 0.7))
    rect.center = (int(cx), int(cy - u * w * 0.2))
    pygame.draw.arc(s, color, rect, math.pi * 1.1, math.pi * 1.9, max(2, int(u * width)))


def _stars(s, R, n, seed, color=(255, 255, 255)):
    rng = random.Random(seed)
    for _ in range(n):
        x, y = rng.randrange(2 * R), rng.randrange(2 * R)
        _c(s, color, x, y, rng.choice((R * 0.015, R * 0.025, R * 0.035)))


def _smiley(s, cx, cy, u):
    _bg(s, u, (255, 214, 60), (255, 170, 30))
    _eyes(s, cx, cy - u * 0.15, u, 0.3, 0.11)
    _smile(s, cx, cy + u * 0.25, u, 0.9)
    _c(s, (255, 130, 110), cx - u * 0.55, cy + u * 0.15, u * 0.12)
    _c(s, (255, 130, 110), cx + u * 0.55, cy + u * 0.15, u * 0.12)


def _cat(s, cx, cy, u):
    _bg(s, u, (190, 160, 255), (140, 110, 230))
    fur, inner = (255, 160, 60), (255, 200, 170)
    for sx in (-1, 1):
        _poly(s, fur, [(cx + sx * u * 0.75, cy - u * 0.15), (cx + sx * u * 0.6, cy - u * 0.95),
                       (cx + sx * u * 0.15, cy - u * 0.5)])
        _poly(s, inner, [(cx + sx * u * 0.62, cy - u * 0.3), (cx + sx * u * 0.56, cy - u * 0.75),
                         (cx + sx * u * 0.3, cy - u * 0.5)])
    _e(s, fur, cx, cy + u * 0.1, u * 1.5, u * 1.25)
    _e(s, (255, 235, 210), cx, cy + u * 0.4, u * 0.8, u * 0.55)
    _eyes(s, cx, cy, u, 0.32, 0.12)
    _poly(s, (240, 90, 120), [(cx - u * 0.08, cy + u * 0.22), (cx + u * 0.08, cy + u * 0.22), (cx, cy + u * 0.32)])
    for sy in (0.28, 0.38):
        for sx in (-1, 1):
            pygame.draw.line(s, INK, (cx + sx * u * 0.2, cy + u * sy), (cx + sx * u * 0.75, cy + u * (sy - 0.06)),
                             max(1, int(u * 0.025)))


def _dog(s, cx, cy, u):
    _bg(s, u, (130, 200, 255), (80, 150, 230))
    fur, ear = (200, 140, 80), (120, 70, 40)
    _e(s, fur, cx, cy + u * 0.05, u * 1.3, u * 1.3)
    for sx in (-1, 1):
        _e(s, ear, cx + sx * u * 0.62, cy + u * 0.05, u * 0.42, u * 0.95)
    _e(s, (245, 225, 200), cx, cy + u * 0.38, u * 0.8, u * 0.6)
    _eyes(s, cx, cy - u * 0.05, u, 0.28, 0.11)
    _e(s, INK, cx, cy + u * 0.25, u * 0.3, u * 0.2)
    _e(s, (240, 90, 110), cx, cy + u * 0.55, u * 0.2, u * 0.22)


def _frog(s, cx, cy, u):
    _bg(s, u, (255, 245, 160), (230, 220, 110))
    g = (80, 190, 80)
    _e(s, g, cx, cy + u * 0.25, u * 1.7, u * 1.2)
    for sx in (-1, 1):
        _c(s, g, cx + sx * u * 0.42, cy - u * 0.3, u * 0.33)
        _c(s, WHITE, cx + sx * u * 0.42, cy - u * 0.3, u * 0.22)
        _c(s, INK, cx + sx * u * 0.42, cy - u * 0.28, u * 0.11)
        _c(s, (255, 140, 140), cx + sx * u * 0.55, cy + u * 0.35, u * 0.12)
    _smile(s, cx, cy + u * 0.45, u, 1.0, (40, 110, 40))


def _fox(s, cx, cy, u):
    _bg(s, u, (60, 190, 180), (30, 140, 140))
    o, w = (245, 120, 40), (255, 245, 235)
    for sx in (-1, 1):
        _poly(s, o, [(cx + sx * u * 0.2, cy - u * 0.4), (cx + sx * u * 0.7, cy - u * 0.95), (cx + sx * u * 0.8, cy - u * 0.1)])
        _poly(s, INK, [(cx + sx * u * 0.55, cy - u * 0.6), (cx + sx * u * 0.7, cy - u * 0.95), (cx + sx * u * 0.75, cy - u * 0.5)])
    _poly(s, o, [(cx - u * 0.85, cy - u * 0.25), (cx + u * 0.85, cy - u * 0.25), (cx, cy + u * 0.75)])
    _e(s, o, cx, cy - u * 0.2, u * 1.6, u * 0.8)
    _poly(s, w, [(cx - u * 0.85, cy - u * 0.05), (cx - u * 0.1, cy + u * 0.2), (cx, cy + u * 0.75)])
    _poly(s, w, [(cx + u * 0.85, cy - u * 0.05), (cx + u * 0.1, cy + u * 0.2), (cx, cy + u * 0.75)])
    _eyes(s, cx, cy - u * 0.12, u, 0.3, 0.1)
    _c(s, INK, cx, cy + u * 0.62, u * 0.1)


def _panda(s, cx, cy, u):
    _bg(s, u, (120, 210, 120), (70, 170, 80))
    for sx in (-1, 1):
        _c(s, INK, cx + sx * u * 0.55, cy - u * 0.55, u * 0.28)
    _e(s, WHITE, cx, cy + u * 0.1, u * 1.45, u * 1.3)
    for sx in (-1, 1):
        _e(s, INK, cx + sx * u * 0.32, cy - u * 0.02, u * 0.36, u * 0.46)
        _c(s, WHITE, cx + sx * u * 0.3, cy - u * 0.05, u * 0.08)
    _e(s, INK, cx, cy + u * 0.3, u * 0.24, u * 0.16)
    _smile(s, cx, cy + u * 0.48, u, 0.4)


def _bear(s, cx, cy, u):
    _bg(s, u, (255, 200, 120), (240, 160, 80))
    b = (150, 95, 55)
    for sx in (-1, 1):
        _c(s, b, cx + sx * u * 0.55, cy - u * 0.55, u * 0.3)
        _c(s, (210, 160, 120), cx + sx * u * 0.55, cy - u * 0.55, u * 0.15)
    _e(s, b, cx, cy + u * 0.1, u * 1.45, u * 1.3)
    _e(s, (225, 185, 140), cx, cy + u * 0.38, u * 0.7, u * 0.5)
    _eyes(s, cx, cy - u * 0.05, u, 0.3, 0.1)
    _e(s, INK, cx, cy + u * 0.25, u * 0.26, u * 0.17)


def _bunny(s, cx, cy, u):
    _bg(s, u, (255, 180, 210), (240, 130, 180))
    for sx in (-1, 1):
        _e(s, WHITE, cx + sx * u * 0.3, cy - u * 0.65, u * 0.36, u * 1.1)
        _e(s, (255, 170, 200), cx + sx * u * 0.3, cy - u * 0.62, u * 0.17, u * 0.8)
    _e(s, WHITE, cx, cy + u * 0.3, u * 1.3, u * 1.1)
    _eyes(s, cx, cy + u * 0.2, u, 0.3, 0.1)
    _poly(s, (240, 100, 140), [(cx - u * 0.07, cy + u * 0.38), (cx + u * 0.07, cy + u * 0.38), (cx, cy + u * 0.46)])
    for sx in (-1, 1):
        _c(s, (255, 170, 190), cx + sx * u * 0.48, cy + u * 0.45, u * 0.1)


def _owl(s, cx, cy, u):
    _bg(s, u, (40, 60, 130), (20, 30, 80))
    _stars(s, int(u), 14, "owl")
    b = (150, 100, 60)
    for sx in (-1, 1):
        _poly(s, b, [(cx + sx * u * 0.3, cy - u * 0.5), (cx + sx * u * 0.75, cy - u * 0.9), (cx + sx * u * 0.75, cy - u * 0.3)])
    _e(s, b, cx, cy + u * 0.2, u * 1.5, u * 1.5)
    _e(s, (210, 175, 130), cx, cy + u * 0.55, u * 0.8, u * 0.7)
    for sx in (-1, 1):
        _c(s, WHITE, cx + sx * u * 0.33, cy - u * 0.05, u * 0.3)
        _c(s, (255, 190, 40), cx + sx * u * 0.33, cy - u * 0.05, u * 0.18)
        _c(s, INK, cx + sx * u * 0.33, cy - u * 0.05, u * 0.1)
    _poly(s, (255, 160, 40), [(cx - u * 0.1, cy + u * 0.18), (cx + u * 0.1, cy + u * 0.18), (cx, cy + u * 0.38)])


def _penguin(s, cx, cy, u):
    _bg(s, u, (180, 230, 255), (120, 190, 240))
    _e(s, INK, cx, cy + u * 0.25, u * 1.5, u * 1.7)
    _e(s, WHITE, cx - u * 0.22, cy + u * 0.15, u * 0.6, u * 0.75)
    _e(s, WHITE, cx + u * 0.22, cy + u * 0.15, u * 0.6, u * 0.75)
    _e(s, WHITE, cx, cy + u * 0.55, u * 0.9, u * 0.8)
    _eyes(s, cx, cy, u, 0.24, 0.09)
    _poly(s, (255, 160, 40), [(cx - u * 0.15, cy + u * 0.22), (cx + u * 0.15, cy + u * 0.22), (cx, cy + u * 0.4)])


def _pizza(s, cx, cy, u):
    _bg(s, u, (230, 70, 60), (190, 40, 40))
    _poly(s, (230, 160, 70), [(cx - u * 0.8, cy - u * 0.5), (cx + u * 0.8, cy - u * 0.5), (cx, cy + u * 0.9)])
    _poly(s, (255, 215, 90), [(cx - u * 0.68, cy - u * 0.38), (cx + u * 0.68, cy - u * 0.38), (cx, cy + u * 0.75)])
    _e(s, (200, 120, 50), cx, cy - u * 0.5, u * 1.7, u * 0.3)
    for px, py in ((-0.3, -0.15), (0.25, -0.1), (0, 0.25), (-0.05, -0.25), (0.1, 0.5)):
        _c(s, (200, 50, 50), cx + u * px, cy + u * py, u * 0.11)


def _ghost(s, cx, cy, u):
    _bg(s, u, (90, 50, 140), (50, 20, 90))
    _stars(s, int(u), 10, "ghost", (200, 180, 255))
    _c(s, WHITE, cx, cy - u * 0.1, u * 0.6)
    pygame.draw.rect(s, WHITE, (cx - u * 0.6, cy - u * 0.1, u * 1.2, u * 0.65))
    for k in range(4):
        _c(s, WHITE, cx - u * 0.45 + k * u * 0.3, cy + u * 0.55, u * 0.15)
    _e(s, INK, cx - u * 0.22, cy - u * 0.15, u * 0.16, u * 0.26)
    _e(s, INK, cx + u * 0.22, cy - u * 0.15, u * 0.16, u * 0.26)
    _e(s, INK, cx, cy + u * 0.15, u * 0.18, u * 0.2)


def _alien(s, cx, cy, u):
    _bg(s, u, (20, 20, 50), (40, 10, 70))
    _stars(s, int(u), 22, "alien")
    g = (120, 230, 100)
    for sx in (-1, 1):
        pygame.draw.line(s, g, (cx + sx * u * 0.2, cy - u * 0.5), (cx + sx * u * 0.45, cy - u * 0.9), max(2, int(u * 0.06)))
        _c(s, (255, 230, 80), cx + sx * u * 0.45, cy - u * 0.9, u * 0.1)
    _poly(s, g, [(cx - u * 0.7, cy - u * 0.3), (cx + u * 0.7, cy - u * 0.3), (cx + u * 0.25, cy + u * 0.75),
                 (cx - u * 0.25, cy + u * 0.75)])
    _e(s, g, cx, cy - u * 0.3, u * 1.4, u * 0.9)
    for sx in (-1, 1):
        _poly(s, INK, [(cx + sx * u * 0.08, cy - u * 0.1), (cx + sx * u * 0.55, cy - u * 0.35),
                       (cx + sx * u * 0.45, cy + u * 0.1)])
    pygame.draw.line(s, (40, 110, 40), (cx - u * 0.12, cy + u * 0.45), (cx + u * 0.12, cy + u * 0.45), max(2, int(u * 0.04)))


def _cool(s, cx, cy, u):
    _bg(s, u, (90, 220, 255), (40, 150, 240))
    _c(s, (255, 214, 60), cx, cy + u * 0.05, u * 0.8)
    for sx in (-1, 1):
        rect = pygame.Rect(0, 0, int(u * 0.55), int(u * 0.35))
        rect.center = (int(cx + sx * u * 0.3), int(cy - u * 0.1))
        pygame.draw.rect(s, INK, rect, border_radius=int(u * 0.12))
        pygame.draw.line(s, (120, 120, 140), (rect.x + u * 0.08, rect.y + u * 0.08), (rect.x + u * 0.2, rect.y + u * 0.08),
                         max(2, int(u * 0.04)))
    pygame.draw.line(s, INK, (cx - u * 0.75, cy - u * 0.15), (cx + u * 0.75, cy - u * 0.15), max(2, int(u * 0.06)))
    rect = pygame.Rect(0, 0, int(u * 0.6), int(u * 0.3))
    rect.center = (int(cx + u * 0.08), int(cy + u * 0.35))
    pygame.draw.arc(s, INK, rect, math.pi * 1.1, math.pi * 1.8, max(2, int(u * 0.06)))


def _ninja(s, cx, cy, u):
    _bg(s, u, (230, 60, 60), (170, 30, 40))
    _c(s, (30, 30, 40), cx, cy + u * 0.1, u * 0.85)
    pygame.draw.rect(s, (240, 200, 160), (cx - u * 0.65, cy - u * 0.15, u * 1.3, u * 0.35), border_radius=int(u * 0.12))
    _eyes(s, cx, cy + u * 0.02, u, 0.28, 0.09)
    pygame.draw.rect(s, (230, 40, 40), (cx - u * 0.8, cy - u * 0.42, u * 1.6, u * 0.16))
    _poly(s, (230, 40, 40), [(cx + u * 0.7, cy - u * 0.4), (cx + u * 1.05, cy - u * 0.55), (cx + u * 1.0, cy - u * 0.3)])


def _pirate(s, cx, cy, u):
    _bg(s, u, (60, 140, 200), (30, 90, 160))
    _c(s, (240, 195, 150), cx, cy + u * 0.15, u * 0.75)
    _e(s, (220, 40, 40), cx, cy - u * 0.4, u * 1.5, u * 0.7)
    pygame.draw.rect(s, (220, 40, 40), (cx - u * 0.75, cy - u * 0.4, u * 1.5, u * 0.25))
    for k in range(4):
        _c(s, WHITE, cx - u * 0.45 + k * u * 0.3, cy - u * 0.45, u * 0.06)
    _c(s, INK, cx - u * 0.28, cy + u * 0.05, u * 0.1)
    _e(s, INK, cx + u * 0.28, cy + u * 0.05, u * 0.3, u * 0.24)
    pygame.draw.line(s, INK, (cx - u * 0.6, cy - u * 0.2), (cx + u * 0.6, cy + u * 0.25), max(2, int(u * 0.04)))
    _smile(s, cx, cy + u * 0.45, u, 0.5)


def _skull(s, cx, cy, u):
    _bg(s, u, (60, 60, 70), (25, 25, 30))
    _c(s, (240, 240, 230), cx, cy - u * 0.12, u * 0.7)
    pygame.draw.rect(s, (240, 240, 230), (cx - u * 0.4, cy + u * 0.2, u * 0.8, u * 0.45), border_radius=int(u * 0.1))
    for sx in (-1, 1):
        _e(s, INK, cx + sx * u * 0.28, cy - u * 0.12, u * 0.32, u * 0.34)
    _poly(s, INK, [(cx - u * 0.08, cy + u * 0.18), (cx + u * 0.08, cy + u * 0.18), (cx, cy + u * 0.05)])
    for k in range(4):
        pygame.draw.line(s, INK, (cx - u * 0.24 + k * u * 0.16, cy + u * 0.4), (cx - u * 0.24 + k * u * 0.16, cy + u * 0.62),
                         max(2, int(u * 0.04)))


def _devil(s, cx, cy, u):
    _bg(s, u, (120, 20, 30), (60, 0, 10))
    red = (230, 50, 50)
    for sx in (-1, 1):
        _poly(s, (250, 230, 200), [(cx + sx * u * 0.3, cy - u * 0.55), (cx + sx * u * 0.7, cy - u * 0.95),
                                   (cx + sx * u * 0.55, cy - u * 0.4)])
    _c(s, red, cx, cy + u * 0.1, u * 0.75)
    for sx in (-1, 1):
        pygame.draw.line(s, INK, (cx + sx * u * 0.12, cy - u * 0.12), (cx + sx * u * 0.48, cy - u * 0.22), max(2, int(u * 0.06)))
    _eyes(s, cx, cy + u * 0.02, u, 0.28, 0.08, (255, 230, 80), False)
    rect = pygame.Rect(0, 0, int(u * 0.7), int(u * 0.4))
    rect.center = (int(cx), int(cy + u * 0.32))
    pygame.draw.arc(s, INK, rect, math.pi * 1.15, math.pi * 1.85, max(2, int(u * 0.06)))


def _wizard(s, cx, cy, u):
    _bg(s, u, (40, 40, 110), (20, 20, 60))
    _stars(s, int(u), 14, "wizard", (255, 240, 160))
    _c(s, (240, 200, 160), cx, cy + u * 0.15, u * 0.5)
    _poly(s, WHITE, [(cx - u * 0.5, cy + u * 0.25), (cx + u * 0.5, cy + u * 0.25), (cx, cy + u * 1.0)])
    _eyes(s, cx, cy + u * 0.08, u, 0.2, 0.07)
    _poly(s, (130, 70, 220), [(cx - u * 0.75, cy - u * 0.1), (cx + u * 0.75, cy - u * 0.1), (cx + u * 0.1, cy - u * 1.0)])
    _e(s, (130, 70, 220), cx, cy - u * 0.1, u * 1.6, u * 0.3)
    _star(s, (255, 220, 60), cx, cy - u * 0.45, u * 0.16)


def _astronaut(s, cx, cy, u):
    _bg(s, u, (15, 15, 40), (30, 20, 60))
    _stars(s, int(u), 24, "astro")
    _c(s, (235, 235, 245), cx, cy + u * 0.05, u * 0.82)
    _e(s, (40, 60, 110), cx, cy + u * 0.05, u * 1.15, u * 0.85)
    _e(s, (255, 160, 70), cx + u * 0.15, cy + u * 0.1, u * 0.7, u * 0.45)
    _e(s, (140, 200, 255), cx - u * 0.25, cy - u * 0.12, u * 0.25, u * 0.15)


def _koi(s, cx, cy, u):
    _bg(s, u, (40, 120, 190), (20, 70, 140))
    _c(s, (60, 170, 90), cx - u * 0.55, cy + u * 0.55, u * 0.3)
    body = (250, 245, 240)
    _e(s, body, cx - u * 0.1, cy, u * 1.2, u * 0.6)
    _poly(s, body, [(cx + u * 0.45, cy), (cx + u * 0.85, cy - u * 0.35), (cx + u * 0.85, cy + u * 0.35)])
    for px, py, rr in ((-0.35, -0.1, 0.18), (0.05, 0.08, 0.15), (0.3, -0.05, 0.1)):
        _c(s, (240, 80, 40), cx + u * px, cy + u * py, u * rr)
    _c(s, INK, cx - u * 0.55, cy - u * 0.05, u * 0.05)


def _unicorn(s, cx, cy, u):
    _bg(s, u, (255, 220, 250), (210, 190, 255))
    mane = [(255, 100, 120), (255, 180, 60), (255, 240, 90), (110, 220, 130), (110, 170, 255), (180, 120, 255)]
    for k, col in enumerate(mane):
        _c(s, col, cx + u * 0.45 - k * u * 0.05, cy - u * 0.5 + k * u * 0.22, u * 0.25)
    _e(s, WHITE, cx - u * 0.1, cy + u * 0.1, u * 1.1, u * 1.2)
    _e(s, (255, 200, 220), cx - u * 0.25, cy + u * 0.55, u * 0.6, u * 0.35)
    _poly(s, (255, 210, 60), [(cx - u * 0.25, cy - u * 0.45), (cx + u * 0.05, cy - u * 0.45), (cx - u * 0.2, cy - u * 1.0)])
    _eyes(s, cx - u * 0.05, cy, u, 0.22, 0.08)


def _dragon(s, cx, cy, u):
    _bg(s, u, (255, 150, 50), (230, 80, 30))
    g = (60, 170, 90)
    for sx in (-1, 1):
        _poly(s, (250, 240, 200), [(cx + sx * u * 0.3, cy - u * 0.45), (cx + sx * u * 0.6, cy - u * 1.0),
                                   (cx + sx * u * 0.55, cy - u * 0.35)])
    _e(s, g, cx, cy, u * 1.3, u * 1.2)
    _e(s, (90, 200, 120), cx, cy + u * 0.4, u * 1.0, u * 0.6)
    for sx in (-1, 1):
        _e(s, (255, 230, 60), cx + sx * u * 0.32, cy - u * 0.15, u * 0.3, u * 0.22)
        _e(s, INK, cx + sx * u * 0.32, cy - u * 0.15, u * 0.08, u * 0.2)
        _c(s, (30, 90, 50), cx + sx * u * 0.18, cy + u * 0.38, u * 0.06)


def _king(s, cx, cy, u):
    _bg(s, u, (120, 50, 190), (70, 20, 130))
    _c(s, (240, 200, 160), cx, cy + u * 0.25, u * 0.6)
    _eyes(s, cx, cy + u * 0.2, u, 0.22, 0.08)
    _smile(s, cx, cy + u * 0.52, u, 0.45)
    gold = (255, 200, 40)
    _poly(s, gold, [(cx - u * 0.6, cy - u * 0.15), (cx - u * 0.65, cy - u * 0.75), (cx - u * 0.32, cy - u * 0.4),
                    (cx, cy - u * 0.85), (cx + u * 0.32, cy - u * 0.4), (cx + u * 0.65, cy - u * 0.75),
                    (cx + u * 0.6, cy - u * 0.15)])
    for k, col in enumerate(((230, 40, 60), (60, 140, 255), (40, 200, 120))):
        _c(s, col, cx - u * 0.3 + k * u * 0.3, cy - u * 0.28, u * 0.08)


def _star(s, color, cx, cy, rad):
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = rad if k % 2 == 0 else rad * 0.45
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    _poly(s, color, pts)


def _superstar(s, cx, cy, u):
    _bg(s, u, (30, 50, 150), (60, 20, 120))
    _stars(s, int(u), 20, "star")
    _star(s, (180, 120, 0), cx, cy + u * 0.06, u * 0.95)
    _star(s, (255, 214, 50), cx, cy, u * 0.9)
    _eyes(s, cx, cy, u, 0.2, 0.08)
    _smile(s, cx, cy + u * 0.25, u, 0.35)


def _trophy(s, cx, cy, u):
    _bg(s, u, (40, 170, 90), (20, 110, 60))
    gold, dark = (255, 205, 50), (200, 140, 20)
    for sx in (-1, 1):
        _c(s, gold, cx + sx * u * 0.5, cy - u * 0.3, u * 0.25, max(2, int(u * 0.08)))
    _poly(s, gold, [(cx - u * 0.55, cy - u * 0.65), (cx + u * 0.55, cy - u * 0.65), (cx + u * 0.4, cy - u * 0.05),
                    (cx, cy + u * 0.2), (cx - u * 0.4, cy - u * 0.05)])
    pygame.draw.rect(s, gold, (cx - u * 0.1, cy + u * 0.15, u * 0.2, u * 0.35))
    pygame.draw.rect(s, dark, (cx - u * 0.4, cy + u * 0.48, u * 0.8, u * 0.25), border_radius=int(u * 0.05))
    _star(s, WHITE, cx, cy - u * 0.35, u * 0.18)


_AVATARS = {
    "smiley": _smiley, "cat": _cat, "dog": _dog, "frog": _frog, "fox": _fox, "panda": _panda, "bear": _bear,
    "bunny": _bunny, "owl": _owl, "penguin": _penguin, "pizza": _pizza, "ghost": _ghost, "alien": _alien,
    "cool": _cool, "ninja": _ninja, "pirate": _pirate, "skull": _skull, "devil": _devil, "wizard": _wizard,
    "astronaut": _astronaut, "koi": _koi, "unicorn": _unicorn, "dragon": _dragon, "king": _king,
    "star": _superstar, "trophy": _trophy,
}


# --------------------------------------------------------------------------- hover-card backgrounds


def panel(surf, rect, style: str | None, clock: float = 0.0, edge=None, edge_w: int = 3):
    """A panel with a player's background (the table's own panel for "classic")."""
    rect = pygame.Rect(rect)
    edge = edge or theme.ACCENT
    if not style or style == "classic":
        theme.panel(surf, rect, edge=edge, edge_w=edge_w)
        return
    pygame.draw.rect(surf, theme.OUTLINE, rect.move(0, 4), border_radius=14)
    surf.blit(banner_surface(style, rect.w, rect.h), rect.topleft)
    _animate(surf, rect, style, clock)
    pygame.draw.rect(surf, edge, rect, edge_w, border_radius=14)


def banner_surface(style: str, w: int, h: int) -> pygame.Surface:
    key = ("banner", style, w, h)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    (_BANNERS.get(style) or _midnight)(s, w, h)
    # Darken a little so text on top stays easy to read.
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 60))
    s.blit(shade, (0, 0))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=14)
    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    if len(_cache) > 400:
        _cache.clear()
    _cache[key] = s
    return s


def _grad(s, w, h, top, bottom, horizontal=False):
    n = w if horizontal else h
    for k in range(0, n, 2):
        t = k / max(1, n - 1)
        c = [int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)]
        if horizontal:
            pygame.draw.rect(s, c, (k, 0, 2, h))
        else:
            pygame.draw.rect(s, c, (0, k, w, 2))


def _sprinkle(s, w, h, n, seed, colors, big=3):
    rng = random.Random(seed)
    for _ in range(n):
        pygame.draw.circle(s, rng.choice(colors), (rng.randrange(w), rng.randrange(h)), rng.randint(1, big))


def _midnight(s, w, h):
    _grad(s, w, h, (30, 40, 100), (8, 10, 30))
    _sprinkle(s, w, h, w * h // 1800, "midnight", [(255, 255, 255), (200, 210, 255)], 2)


def _forest(s, w, h):
    _grad(s, w, h, (60, 140, 90), (15, 60, 35))
    rng = random.Random("forest")
    for _ in range(w // 18):
        x, th = rng.randrange(-20, w), rng.randint(h // 4, h // 2)
        pygame.draw.polygon(s, (20, 70 + rng.randint(0, 30), 40), [(x, h), (x + 22, h - th), (x + 44, h)])


def _sunset(s, w, h):
    _grad(s, w, h, (255, 150, 70), (110, 40, 120))
    pygame.draw.circle(s, (255, 220, 120), (int(w * 0.8), int(h * 0.75)), min(w, h) // 4)
    for k in range(4):
        pygame.draw.rect(s, (110, 40, 120), (0, int(h * 0.75) + k * 8, w, 3))


def _stripes(s, w, h):
    s.fill((255, 150, 190))
    for x in range(-h, w + h, 40):
        pygame.draw.polygon(s, (255, 235, 245), [(x, 0), (x + 18, 0), (x + 18 + h, h), (x + h, h)])


def _polka(s, w, h):
    s.fill((40, 170, 170))
    for y in range(0, h + 30, 30):
        for x in range(0 if (y // 30) % 2 else 15, w + 30, 30):
            pygame.draw.circle(s, (110, 220, 210), (x, y), 7)


def _checker(s, w, h):
    s.fill((50, 90, 200))
    for y in range(0, h, 24):
        for x in range(0, w, 24):
            if (x // 24 + y // 24) % 2:
                pygame.draw.rect(s, (80, 130, 240), (x, y, 24, 24))


def _camo(s, w, h):
    s.fill((95, 115, 60))
    rng = random.Random("camo")
    for _ in range(w * h // 900):
        c = rng.choice([(60, 80, 40), (140, 130, 80), (40, 50, 30)])
        x, y = rng.randrange(w), rng.randrange(h)
        for _ in range(3):
            pygame.draw.ellipse(s, c, (x + rng.randint(-14, 14), y + rng.randint(-8, 8), rng.randint(20, 40),
                                       rng.randint(12, 24)))


def _waves(s, w, h):
    _grad(s, w, h, (40, 150, 230), (20, 70, 160))
    for k in range(0, h + 20, 22):
        pts = [(x, k + math.sin(x / 26 + k) * 6) for x in range(0, w + 8, 8)]
        pygame.draw.lines(s, (110, 200, 255), False, pts, 3)


def _heart(s, color, cx, cy, r):
    pygame.draw.circle(s, color, (int(cx - r / 2), int(cy)), int(r / 2) + 1)
    pygame.draw.circle(s, color, (int(cx + r / 2), int(cy)), int(r / 2) + 1)
    pygame.draw.polygon(s, color, [(cx - r, cy + 2), (cx + r, cy + 2), (cx, cy + r * 1.3)])


def _hearts(s, w, h):
    _grad(s, w, h, (255, 120, 170), (200, 50, 110))
    rng = random.Random("hearts")
    for _ in range(w * h // 1500):
        _heart(s, rng.choice([(255, 180, 210), (255, 90, 140)]), rng.randrange(w), rng.randrange(h), rng.randint(5, 11))


def _starry(s, w, h):
    _grad(s, w, h, (20, 20, 70), (60, 30, 110))
    rng = random.Random("stars")
    for _ in range(w * h // 1200):
        _star(s, rng.choice([(255, 240, 160), (255, 255, 255)]), rng.randrange(w), rng.randrange(h), rng.randint(2, 6))


def _ocean(s, w, h):
    _grad(s, w, h, (20, 110, 170), (5, 25, 70))
    rng = random.Random("ocean")
    for _ in range(w * h // 1400):
        pygame.draw.circle(s, (120, 200, 255), (rng.randrange(w), rng.randrange(h)), rng.randint(2, 7), 1)


def _lava(s, w, h):
    _grad(s, w, h, (90, 10, 10), (40, 0, 0))
    rng = random.Random("lava")
    for _ in range(w * h // 1300):
        c = rng.choice([(255, 120, 20), (230, 60, 20), (255, 190, 60)])
        pygame.draw.ellipse(s, c, (rng.randrange(w), rng.randrange(h), rng.randint(8, 30), rng.randint(6, 16)))


def _neon(s, w, h):
    s.fill((15, 5, 30))
    for x in range(0, w, 28):
        pygame.draw.line(s, (200, 40, 220), (x, 0), (x, h), 1)
    for y in range(0, h, 28):
        pygame.draw.line(s, (40, 200, 240), (0, y), (w, y), 1)


def _matrix(s, w, h):
    s.fill((5, 15, 5))
    rng = random.Random("matrix")
    f = theme.font(12, True)
    for x in range(4, w, 14):
        for y in range(rng.randint(-60, 0), h, 15):
            if rng.random() < 0.55:
                g = rng.randint(90, 230)
                s.blit(f.render(rng.choice("01ABCDEF<>$#*+"), True, (40, g, 60)), (x, y))


def _koi_pond(s, w, h):
    _grad(s, w, h, (40, 120, 170), (20, 60, 110))
    rng = random.Random("koi")
    for _ in range(max(3, w * h // 9000)):
        pygame.draw.circle(s, (50, 150, 80), (rng.randrange(w), rng.randrange(h)), rng.randint(10, 18))
    for _ in range(max(3, w * h // 7000)):
        x, y = rng.randrange(w), rng.randrange(h)
        pygame.draw.ellipse(s, (250, 245, 240), (x, y, 34, 16))
        pygame.draw.polygon(s, (250, 245, 240), [(x + 30, y + 8), (x + 44, y), (x + 44, y + 16)])
        pygame.draw.circle(s, (240, 90, 40), (x + 12, y + 7), 5)


def _galaxy(s, w, h):
    s.fill((10, 5, 30))
    rng = random.Random("galaxy")
    for _ in range(14):
        c = rng.choice([(90, 30, 140), (30, 60, 150), (150, 40, 120)])
        blob = pygame.Surface((160, 100), pygame.SRCALPHA)
        pygame.draw.ellipse(blob, (*c, 90), blob.get_rect())
        s.blit(blob, (rng.randrange(-60, w), rng.randrange(-40, h)))
    _sprinkle(s, w, h, w * h // 700, "galaxy-stars", [(255, 255, 255), (220, 200, 255)], 2)


def _aurora(s, w, h):
    _grad(s, w, h, (10, 20, 50), (5, 10, 25))
    for k, c in enumerate([(60, 230, 150), (120, 90, 230), (40, 180, 220)]):
        band = pygame.Surface((w, h), pygame.SRCALPHA)
        pts = [(x, h * (0.3 + 0.15 * k) + math.sin(x / 40 + k * 2) * 18) for x in range(0, w + 10, 10)]
        for y_off in range(0, 26, 2):
            pygame.draw.lines(band, (*c, 55), False, [(x, y + y_off) for x, y in pts], 3)
        s.blit(band, (0, 0))


def _rainbow(s, w, h):
    cols = [(230, 70, 70), (240, 150, 50), (230, 210, 60), (80, 190, 90), (60, 140, 230), (140, 90, 220)]
    bh = h / len(cols)
    for k, c in enumerate(cols):
        pygame.draw.rect(s, c, (0, int(k * bh), w, int(bh) + 1))


def _gold(s, w, h):
    _grad(s, w, h, (250, 210, 90), (170, 110, 20))
    for x in range(-h, w, 18):
        pygame.draw.line(s, (255, 230, 140), (x, 0), (x + h, h), 1)


def _royal(s, w, h):
    _grad(s, w, h, (110, 30, 150), (50, 10, 80))
    for y in range(12, h, 30):
        for x in range(12 if (y // 30) % 2 else 27, w, 30):
            _star(s, (230, 180, 60), x, y, 5)
    pygame.draw.rect(s, (230, 180, 60), (6, 6, w - 12, h - 12), 2, border_radius=10)


def _diamond(s, w, h):
    _grad(s, w, h, (190, 240, 255), (90, 160, 220))
    rng = random.Random("diamond")
    for _ in range(w * h // 1600):
        x, y, r = rng.randrange(w), rng.randrange(h), rng.randint(8, 18)
        c = rng.choice([(220, 250, 255), (150, 210, 245), (120, 190, 235)])
        pygame.draw.polygon(s, c, [(x, y - r), (x + r * 0.7, y), (x, y + r), (x - r * 0.7, y)])


_BANNERS = {
    "midnight": _midnight, "forest": _forest, "sunset": _sunset, "stripes": _stripes, "polka": _polka,
    "checker": _checker, "camo": _camo, "waves": _waves, "hearts": _hearts, "stars": _starry, "ocean": _ocean,
    "lava": _lava, "neon": _neon, "matrix": _matrix, "koi": _koi_pond, "galaxy": _galaxy, "aurora": _aurora,
    "rainbow": _rainbow, "gold": _gold, "royal": _royal, "diamond": _diamond,
}


def _animate(surf, rect, style, clock):
    """Moving touches for the fancy backgrounds: a shine across gold, sparkles on diamond."""
    if style == "gold":
        x = rect.x + int(((clock * 0.5) % 1.6 - 0.3) * rect.w)
        shine = pygame.Surface((60, rect.h), pygame.SRCALPHA)
        for k in range(60):
            a = int(90 * (1 - abs(k - 30) / 30))
            pygame.draw.line(shine, (255, 255, 230, a), (k, 0), (k, rect.h))
        clip = surf.get_clip()
        surf.set_clip(rect.inflate(-6, -6))
        surf.blit(pygame.transform.rotate(shine, -15), (x, rect.y - 10))
        surf.set_clip(clip)
    elif style in ("diamond", "galaxy", "stars"):
        rng = random.Random(style)
        for k in range(8):
            px, py = rect.x + rng.randrange(8, max(9, rect.w - 8)), rect.y + rng.randrange(8, max(9, rect.h - 8))
            tw = math.sin(clock * 3 + k * 1.7)
            if tw > 0.5:
                rr = int(2 + 4 * (tw - 0.5))
                pygame.draw.line(surf, (255, 255, 255), (px - rr, py), (px + rr, py), 2)
                pygame.draw.line(surf, (255, 255, 255), (px, py - rr), (px, py + rr), 2)
