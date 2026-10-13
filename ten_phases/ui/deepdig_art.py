"""Deep Dig art, all drawn in code: the ground, ore, hazards, the drill pod, the surface town and the dark."""

from __future__ import annotations

import math
import random

import pygame

from ..deepdig.engine import (AIR, BEDROCK, CONCRETE, CORE, DIRT, GAS, H, LAVA, ORE0, ORES, ROCK, is_ore)
from . import theme

TILE = 40
BANDS = 8          # the ground changes colour as you go down
_cache: dict = {}

# Dirt colours from the topsoil down to the deep crust.
DIRT_COLORS = [(150, 98, 56), (138, 84, 50), (126, 72, 52), (112, 62, 58), (100, 54, 66), (86, 46, 72),
               (72, 40, 76), (60, 34, 70)]


def band(row: int) -> int:
    return max(0, min(BANDS - 1, int(row / H * BANDS)))


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _dirt(b: int, variant: int) -> pygame.Surface:
    key = ("dirt", b, variant)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TILE, TILE))
    base = DIRT_COLORS[b]
    s.fill(base)
    rng = random.Random(b * 31 + variant)
    for _ in range(14):
        c = _shade(base, rng.choice((0.78, 0.86, 1.12, 1.2)))
        x, y = rng.randrange(TILE), rng.randrange(TILE)
        pygame.draw.circle(s, c, (x, y), rng.choice((1, 2, 2, 3)))
    for _ in range(3):
        x, y = rng.randrange(4, TILE - 4), rng.randrange(4, TILE - 4)
        pygame.draw.circle(s, _shade(base, 0.6), (x, y), 2)
        pygame.draw.circle(s, _shade(base, 1.35), (x - 1, y - 1), 1)
    pygame.draw.line(s, _shade(base, 1.15), (0, 0), (TILE - 1, 0))
    pygame.draw.line(s, _shade(base, 0.75), (0, TILE - 1), (TILE - 1, TILE - 1))
    _cache[key] = s
    return s


def _gem(s, color, cx, cy, r, rng):
    """A faceted lump of ore."""
    pts = []
    n = rng.choice((5, 6, 7))
    for k in range(n):
        a = k / n * 2 * math.pi + rng.uniform(-0.3, 0.3)
        rr = r * rng.uniform(0.75, 1.1)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    pygame.draw.polygon(s, _shade(color, 0.45), [(x + 1, y + 2) for x, y in pts])
    pygame.draw.polygon(s, color, pts)
    pygame.draw.polygon(s, _shade(color, 1.35), [(cx, cy), pts[0], pts[1]])
    pygame.draw.polygon(s, _shade(color, 0.7), pts, 1)
    pygame.draw.circle(s, (255, 255, 255), (int(cx - r * 0.35), int(cy - r * 0.35)), max(1, r // 4))


def tile_surface(t: int, row: int, col: int) -> pygame.Surface | None:
    b = band(row)
    variant = (col * 7 + row * 13) % 4
    if t == AIR:
        return None
    if t == DIRT:
        if row == 0:
            return _topsoil(variant)
        return _dirt(b, variant)
    key = ("t", t, b, variant)
    if key in _cache:
        return _cache[key]
    rng = random.Random(t * 97 + b * 13 + variant)
    if t == ROCK:
        s = _dirt(b, variant).copy()
        grey = _shade((128, 128, 138), 1 - b * 0.05)
        pts = [(4, 14), (12, 4), (28, 3), (37, 12), (37, 30), (26, 37), (10, 36), (3, 26)]
        pygame.draw.polygon(s, _shade(grey, 0.55), [(x + 1, y + 2) for x, y in pts])
        pygame.draw.polygon(s, grey, pts)
        pygame.draw.polygon(s, _shade(grey, 1.25), [(12, 4), (28, 3), (37, 12), (20, 14)])
        pygame.draw.line(s, _shade(grey, 0.6), (14, 18), (26, 28), 2)
        pygame.draw.line(s, _shade(grey, 0.6), (26, 28), (30, 22), 2)
    elif t == GAS:
        s = _dirt(b, (variant + 1) % 4).copy()
        for _ in range(4):   # a faint hint: tiny bubbles
            pygame.draw.circle(s, (150, 200, 120), (rng.randrange(6, 34), rng.randrange(6, 34)), 2, 1)
    elif t == LAVA:
        s = pygame.Surface((TILE, TILE))
        s.fill((200, 50, 20))
        for _ in range(10):
            c = rng.choice([(255, 140, 30), (255, 200, 60), (170, 30, 10)])
            pygame.draw.circle(s, c, (rng.randrange(TILE), rng.randrange(TILE)), rng.randint(2, 7))
    elif t == BEDROCK:
        s = pygame.Surface((TILE, TILE))
        s.fill((44, 30, 48))
        for _ in range(8):
            pygame.draw.circle(s, (64, 46, 70), (rng.randrange(TILE), rng.randrange(TILE)), rng.randint(2, 5))
        pygame.draw.rect(s, (30, 20, 34), s.get_rect(), 1)
    elif t == CONCRETE:
        s = pygame.Surface((TILE, TILE))
        s.fill((150, 150, 160))
        pygame.draw.rect(s, (110, 110, 120), s.get_rect(), 2)
        pygame.draw.line(s, (120, 120, 130), (0, TILE // 2), (TILE, TILE // 2), 1)
    elif t == CORE:
        s = pygame.Surface((TILE, TILE))
        s.fill((60, 20, 60))
        for k in range(6, 0, -1):
            pygame.draw.circle(s, (255, 60 + k * 25, 120 + k * 20), (TILE // 2, TILE // 2), 3 + k * 3)
        pygame.draw.circle(s, (255, 255, 255), (TILE // 2 - 4, TILE // 2 - 4), 3)
    elif is_ore(t):
        s = _dirt(b, variant).copy()
        ore = ORES[t - ORE0]
        for k in range(rng.choice((2, 3, 3))):
            _gem(s, ore.color, rng.randrange(10, 30), rng.randrange(10, 30), rng.randint(5, 8), rng)
    else:
        s = _dirt(b, variant)
    _cache[key] = s
    return s


def _topsoil(variant: int) -> pygame.Surface:
    key = ("top", variant)
    if key in _cache:
        return _cache[key]
    s = _dirt(0, variant).copy()
    pygame.draw.rect(s, (70, 170, 70), (0, 0, TILE, 9))
    rng = random.Random(variant)
    for x in range(0, TILE, 4):
        pygame.draw.line(s, (90, 200, 80), (x, 9), (x + rng.randint(-2, 2), 2 + rng.randint(0, 3)), 2)
    _cache[key] = s
    return s


def tunnel_color(row: int):
    """The colour behind dug-out tiles."""
    b = DIRT_COLORS[band(row)]
    return _shade(b, 0.32)


# --------------------------------------------------------------------------- the pod


def pod(facing: int, drilling: str | None, spin: float, flame: bool, clock: float, hurt: float = 0.0,
        size: int = 36) -> pygame.Surface:
    """The drill pod. drilling is None, "down", "left" or "right"."""
    S = size * 2
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S // 2
    body = theme.ACCENT if hurt <= 0 else (255, 90, 80)
    dark = _shade(body, 0.6)
    # Thruster flames.
    if flame:
        for k, sx in enumerate((-10, 10)):
            fl = 10 + 6 * abs(math.sin(clock * 30 + k))
            pygame.draw.polygon(s, (255, 140, 30), [(c + sx - 5, c + 14), (c + sx + 5, c + 14), (c + sx, c + 14 + fl)])
            pygame.draw.polygon(s, (255, 230, 120), [(c + sx - 2, c + 14), (c + sx + 2, c + 14),
                                                     (c + sx, c + 14 + fl * 0.6)])
    # Tracks.
    tr = pygame.Rect(c - 17, c + 6, 34, 9)
    pygame.draw.rect(s, (40, 40, 48), tr, border_radius=4)
    for k in range(5):
        x = tr.x + 4 + ((k * 7 + int(clock * 30)) % 30)
        pygame.draw.line(s, (90, 90, 100), (x, tr.y + 1), (x, tr.bottom - 2), 2)
    # Body.
    bd = pygame.Rect(c - 16, c - 12, 32, 20)
    pygame.draw.rect(s, theme.OUTLINE, bd.move(0, 2), border_radius=6)
    pygame.draw.rect(s, body, bd, border_radius=6)
    pygame.draw.rect(s, dark, (bd.x, bd.bottom - 6, bd.w, 6), border_bottom_left_radius=6,
                     border_bottom_right_radius=6)
    # Cockpit.
    cx = c + 5 * facing
    pygame.draw.circle(s, theme.OUTLINE, (cx, c - 11), 9)
    pygame.draw.circle(s, (120, 210, 255), (cx, c - 12), 8)
    pygame.draw.circle(s, (230, 250, 255), (cx - 3, c - 15), 3)
    # The drill bit.
    d = drilling or "down"
    phase = spin * 6
    if d == "down":
        tip = [(c - 9, c + 12), (c + 9, c + 12), (c, c + 26)]
    elif d == "right":
        tip = [(c + 15, c - 7), (c + 15, c + 9), (c + 30, c + 1)]
    else:
        tip = [(c - 15, c - 7), (c - 15, c + 9), (c - 30, c + 1)]
    if drilling or d == "down":
        pygame.draw.polygon(s, theme.OUTLINE, [(x, y + 1) for x, y in tip])
        pygame.draw.polygon(s, (190, 196, 206), tip)
        for k in range(3):   # the spinning thread
            f = ((k / 3 + phase) % 1.0)
            a, b = tip[0], tip[1]
            p = tip[2]
            x1 = a[0] + (p[0] - a[0]) * f
            y1 = a[1] + (p[1] - a[1]) * f
            x2 = b[0] + (p[0] - b[0]) * f
            y2 = b[1] + (p[1] - b[1]) * f
            pygame.draw.line(s, (110, 116, 130), (x1, y1), (x2, y2), 2)
    return s


# --------------------------------------------------------------------------- the surface


def sky(width: int, height: int) -> pygame.Surface:
    key = ("sky", width, height)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((width, height))
    top, bottom = (90, 160, 240), (190, 225, 255)
    for y in range(0, height, 2):
        k = y / max(1, height)
        pygame.draw.rect(s, [int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)], (0, y, width, 2))
    sun = max(70, height - 290)                        # the bottom of the sky is what's usually in view
    pygame.draw.circle(s, (255, 240, 170), (width - 160, sun), 46)
    pygame.draw.circle(s, (255, 250, 210), (width - 160, sun), 36)
    rng = random.Random(3)
    for _ in range(6):
        x, y = rng.randrange(width), rng.randrange(max(40, height - 330), max(41, height - 120))
        for k in range(4):
            pygame.draw.circle(s, (250, 252, 255), (x + k * 22, y + (k % 2) * 6), 20 + (k % 2) * 6)
    # Hills on the horizon.
    for k, col in enumerate(((120, 180, 120), (96, 160, 96))):
        pts = [(0, height)]
        for x in range(0, width + 40, 40):
            pts.append((x, height - 60 - k * 18 - 30 * math.sin(x / 140 + k * 2)))
        pts.append((width, height))
        pygame.draw.polygon(s, col, pts)
    _cache[key] = s
    return s


BUILDING_STYLE = {
    "FUEL": ((230, 70, 60), "FUEL"),
    "SELL": ((70, 160, 90), "ORE BUYER"),
    "SHOP": ((70, 120, 230), "UPGRADES"),
    "REPAIR": ((240, 170, 40), "REPAIRS"),
}


def building(name: str, width: int) -> pygame.Surface:
    key = ("bld", name, width)
    if key in _cache:
        return _cache[key]
    color, label = BUILDING_STYLE[name]
    h = 150
    s = pygame.Surface((width, h + 40), pygame.SRCALPHA)
    wall = pygame.Rect(6, 40, width - 12, h - 2)
    pygame.draw.rect(s, theme.OUTLINE, wall.move(0, 4), border_radius=6)
    pygame.draw.rect(s, (236, 230, 214), wall, border_radius=6)
    pygame.draw.polygon(s, theme.OUTLINE, [(0, 46), (width // 2, 4), (width, 46)])
    pygame.draw.polygon(s, color, [(4, 44), (width // 2, 8), (width - 4, 44)])
    door = pygame.Rect(width // 2 - 30, h - 34, 60, 72)
    pygame.draw.rect(s, (60, 60, 70), door, border_radius=4)
    pygame.draw.rect(s, (90, 90, 100), door.inflate(-8, -8), 2, border_radius=3)
    for wx in (wall.x + 14, wall.right - 44):
        win = pygame.Rect(wx, wall.y + 20, 30, 26)
        pygame.draw.rect(s, (130, 200, 255), win, border_radius=3)
        pygame.draw.rect(s, theme.OUTLINE, win, 2, border_radius=3)
    sign = theme.pixel_surface(label, 20, (255, 255, 255))
    sr = sign.get_rect(center=(width // 2, 66))
    pygame.draw.rect(s, color, sr.inflate(16, 8), border_radius=6)
    pygame.draw.rect(s, theme.OUTLINE, sr.inflate(16, 8), 2, border_radius=6)
    s.blit(sign, sr)
    _cache[key] = s
    return s


# --------------------------------------------------------------------------- light underground


def light_hole(radius: int) -> pygame.Surface:
    """Alpha 0 in the middle rising to 255 at the edge: punched out of the darkness around the pod."""
    key = ("hole", radius)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    s.fill((0, 0, 0, 255))
    for r in range(radius, 0, -3):
        a = int(255 * (r / radius) ** 1.6)
        pygame.draw.circle(s, (0, 0, 0, a), (radius, radius), r)
    _cache[key] = s
    return s
