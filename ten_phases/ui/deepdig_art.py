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


DRILL_METALS = [   # the drill bit's look by DRILL level: steel, then better and better alloys
    (186, 192, 204), (196, 204, 214), (214, 170, 110), (230, 196, 90), (150, 220, 240), (200, 160, 255),
    (255, 120, 120), (240, 250, 255)]


def pod(facing: int, drilling: str | None, spin: float, flame: bool, clock: float, hurt: float = 0.0,
        size: int = 36, drill_level: int = 0) -> pygame.Surface:
    """The drill pod, seen from the side and facing left (-1) or right (1). drilling is None, "down",
    "left" or "right". Drawn at double size and smoothed down, so the edges come out clean."""
    Z = 2                                   # supersampling
    S = size * 2 * Z
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S // 2
    f = 1 if facing >= 0 else -1

    def P(x, y):                            # pod coordinates (pixels at final size, +x is "forward") to canvas
        return (c + x * Z * f, c + y * Z)

    def poly(color, pts, width=0):
        pygame.draw.polygon(s, color, [P(x, y) for x, y in pts], width * Z if width else 0)

    def rect(color, x, y, w, h, radius=0, width=0):
        a, b = P(x, y), P(x + w, y + h)
        r = pygame.Rect(min(a[0], b[0]), min(a[1], b[1]), abs(b[0] - a[0]), abs(b[1] - a[1]))
        pygame.draw.rect(s, color, r, width * Z if width else 0, border_radius=radius * Z)
        return r

    def circle(color, x, y, r, width=0):
        pygame.draw.circle(s, color, P(x, y), r * Z, width * Z if width else 0)

    ink = theme.OUTLINE
    body = theme.ACCENT if hurt <= 0 else (255, 96, 84)
    light, mid, shadow = _shade(body, 1.18), body, _shade(body, 0.68)
    steel, steel_dark = (150, 156, 170), (84, 88, 100)

    # Thruster flames (under the tracks), drawn first so the pod sits on top.
    if flame:
        for k, sx in enumerate((-9, 9)):
            fl = 9 + 6 * abs(math.sin(clock * 31 + k * 1.7))
            poly((255, 120, 30), [(sx - 4.5, 15), (sx + 4.5, 15), (sx, 15 + fl)])
            poly((255, 220, 110), [(sx - 2.5, 15), (sx + 2.5, 15), (sx, 15 + fl * 0.62)])
            circle((255, 250, 220), sx, 16, 1.5)
    # Thruster nozzles.
    for sx in (-9, 9):
        poly(ink, [(sx - 4, 12), (sx + 4, 12), (sx + 3.5, 16.5), (sx - 3.5, 16.5)])
        poly(steel_dark, [(sx - 3, 12), (sx + 3, 12), (sx + 2.5, 15.5), (sx - 2.5, 15.5)])

    # Drill: the bit on its collar. Spins and points where it digs; tucked under the pod otherwise.
    d = drilling or "down"
    metal = DRILL_METALS[max(0, min(len(DRILL_METALS) - 1, drill_level))]
    if d == "down":
        base_a, base_b, tip = (-6.5, 15), (6.5, 15), (0, 29 if drilling else 25)
        rect(ink, -7.5, 11.5, 15, 5, 2)
        rect(steel_dark, -6.5, 12, 13, 3.5, 1)
    else:   # sideways: always out the front (the pod turns to face the wall it digs)
        base_a, base_b, tip = (17, -6), (17, 7), (32, 0.5)
        rect(ink, 13.5, -7.5, 5, 16, 2)
        rect(steel_dark, 14, -6.5, 3.5, 14, 1)
    poly(ink, [(base_a[0] - 0.8, base_a[1] - 0.8), (base_b[0] + 0.8, base_b[1] + 0.8), tip])
    poly(_shade(metal, 0.62), [base_a, base_b, tip])
    mid_pt = ((base_a[0] + base_b[0]) / 2, (base_a[1] + base_b[1]) / 2)
    poly(metal, [base_a, mid_pt, tip])                       # the lit half
    phase = (spin * 5) % 1.0
    for k in range(4):                                         # the spiral thread, turning
        t = (k / 4 + phase) % 1.0
        a = (base_a[0] + (tip[0] - base_a[0]) * t, base_a[1] + (tip[1] - base_a[1]) * t)
        b = (base_b[0] + (tip[0] - base_b[0]) * (t + 0.12), base_b[1] + (tip[1] - base_b[1]) * (t + 0.12))
        pygame.draw.line(s, _shade(metal, 0.45), P(*a), P(*b), 2 * Z)
    circle((255, 255, 255), *((base_a[0] * 0.6 + tip[0] * 0.4), (base_a[1] * 0.6 + tip[1] * 0.4)), 1)

    # Tracks: a tread loop around two wheels, the links rolling with the clock.
    rect(ink, -18, 4.5, 36, 12, 6)
    rect((44, 44, 54), -17, 5.5, 34, 10, 5)
    roll = (clock * 24) % 4
    for k in range(7):
        x = -15 + ((k * 4 + roll) % 28)
        rect((86, 86, 98), x, 5.5, 1.6, 1.6)                   # links along the top run one way...
        rect((86, 86, 98), -x - 1.6, 13.9, 1.6, 1.6)           # ...and back along the bottom
    for wx in (-11.5, 0, 11.5):
        r = 3.6 if wx else 2.6
        circle(ink, wx, 10.5, r + 0.8)
        circle((128, 130, 142), wx, 10.5, r)
        circle((70, 72, 84), wx, 10.5, r * 0.45)
        a = clock * 9 + wx
        for k in range(3):                                      # spokes
            ang = a + k * 2.094
            pygame.draw.line(s, (70, 72, 84), P(wx, 10.5),
                             P(wx + math.cos(ang) * r * 0.9, 10.5 + math.sin(ang) * r * 0.9), Z)

    # Body: an armoured hull, lit from above, with a hazard stripe and rivets.
    hull = [(-17, 5), (-17, -6), (-13, -10), (12, -10), (17, -5), (17, 5)]
    poly(ink, [(x + (0.9 if x > 0 else -0.9), y + (0.9 if y > 0 else -0.9)) for x, y in hull])
    poly(mid, hull)
    poly(light, [(-17, -6), (-13, -10), (12, -10), (17, -5), (17, -3.5), (-17, -3.5)])
    poly(shadow, [(-17, 1), (17, 1), (17, 5), (-17, 5)])
    for k in range(9):                                         # hazard stripes along the bottom
        x = -16 + k * 4
        poly(_shade(body, 0.42), [(x, 5), (x + 2, 5), (x + 3.5, 1.5), (x + 1.5, 1.5)])
    pygame.draw.line(s, _shade(body, 0.55), P(-4, -3.5), P(-4, 1), Z)       # a panel seam
    for x in (-14.5, -7, 6, 14.5):
        circle(_shade(body, 0.6), x, -1.2, 0.9)
        circle(_shade(body, 1.35), x - 0.3, -1.5, 0.4)
    # The engine block on the back, with vents, an exhaust stack and an antenna with a beacon.
    rect(ink, -15, -15, 12, 6.5, 2)
    rect(steel, -14.2, -14.2, 10.4, 5, 2)
    for k in range(3):
        pygame.draw.line(s, steel_dark, P(-12.5 + k * 3, -13.2), P(-12.5 + k * 3, -10.6), Z)
    rect(ink, -16.5, -19, 3.5, 6, 1)
    rect(steel_dark, -16, -18.5, 2.5, 5)
    pygame.draw.line(s, ink, P(-6, -15), P(-7.5, -24), Z)
    if int(clock * 2.5) % 2 == 0:
        circle((255, 80, 70), -7.5, -24, 2.4)
        circle((255, 200, 190), -7.9, -24.4, 0.8)
    else:
        circle((120, 40, 40), -7.5, -24, 1.6)
    # The cab: a glass bubble at the front, with the pilot inside.
    cab = [(0, -9), (0, -16), (3, -20), (11, -20), (15.5, -14), (15.5, -9)]
    poly(ink, [(x + (0.9 if x > 7 else -0.9), y - (0.9 if y < -12 else 0)) for x, y in cab])
    poly((96, 176, 230), cab)
    poly((150, 214, 250), [(0, -16), (3, -20), (11, -20), (12.4, -18), (1.5, -12)])
    circle((40, 44, 60), 7.4, -13.2, 3.1)                      # the pilot's helmet...
    rect((255, 210, 90), 8.2, -14.4, 2.4, 1.6, 1)               # ...and visor
    pygame.draw.line(s, (240, 252, 255), P(3.5, -18), P(1.8, -15.2), Z)    # a glint
    pygame.draw.line(s, (240, 252, 255), P(5.5, -18.6), P(4.6, -17.4), Z)
    rect(ink, -0.6, -10, 16.4, 1.2)                              # the cab's sill
    # The headlamp, with a soft glow.
    if d == "down":                                             # (a sideways drill sits in front of it)
        glow = pygame.Surface((10 * Z, 10 * Z), pygame.SRCALPHA)
        for r, a in ((5, 50), (3.5, 90)):
            pygame.draw.circle(glow, (255, 248, 200, a), (5 * Z, 5 * Z), int(r * Z))
        gx, gy = P(18.5, -4.5)
        s.blit(glow, (gx - 5 * Z, gy - 5 * Z))
    rect(ink, 15.5, -6.5, 3.5, 4, 1)
    rect((255, 246, 200), 16.2, -5.8, 2.2, 2.6, 1)
    return pygame.transform.smoothscale(s, (size * 2, size * 2))


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
