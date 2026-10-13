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
        size: int = 36, drill_level: int = 0, top_drill: bool = False) -> pygame.Surface:
    """The drill pod, seen from the side and facing left (-1) or right (1). drilling is None, "down",
    "left", "right" or "up" (with the roof drill, which shows once you own it). Drawn at double size and smoothed down, so the edges come out clean."""
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
    d = drilling if drilling in ("left", "right") else "down"
    main = drilling in ("down", "left", "right")
    metal = DRILL_METALS[max(0, min(len(DRILL_METALS) - 1, drill_level))]
    if d == "down":
        base_a, base_b, tip = (-6.5, 15), (6.5, 15), (0, 29 if main else 25)
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
    if top_drill or drilling == "up":       # the roof drill, tucked away or digging up
        up = drilling == "up"
        rect(ink, -6.5, -14.5, 9, 5, 2)
        rect(steel_dark, -6, -14, 8, 3.5, 1)
        a, b, tip = (-6, -14), (2, -14), (-2, -29 if up else -21)
        poly(ink, [(a[0] - 0.8, a[1] + 0.6), (b[0] + 0.8, b[1] + 0.6), (tip[0], tip[1] - 1)])
        poly(_shade(metal, 0.62), [a, b, tip])
        poly(metal, [a, (-2, -14), tip])
        for k in range(3):
            t = (k / 3 + (spin * 5 if up else 0)) % 1.0
            p1 = (a[0] + (tip[0] - a[0]) * t, a[1] + (tip[1] - a[1]) * t)
            p2 = (b[0] + (tip[0] - b[0]) * min(1, t + 0.15), b[1] + (tip[1] - b[1]) * min(1, t + 0.15))
            pygame.draw.line(s, _shade(metal, 0.45), P(*p1), P(*p2), Z)
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
    "SHOP": ((70, 120, 230), "GARAGE"),
    "LAB": ((150, 90, 230), "TECH LAB"),
    "REPAIR": ((240, 150, 40), "REPAIRS"),
    "BOTS": ((40, 180, 170), "ROBOTICS"),
    "OIL": ((70, 70, 84), "OIL REFINERY"),
}
BOT_COLORS = [(60, 210, 200), (255, 120, 180), (170, 230, 70)]
BUILDING_TAGLINE = {
    "FUEL": "Fill up before you head down",
    "SELL": "Cash for anything you dig up",
    "SHOP": "Pod parts: drills, engines, hulls and more",
    "LAB": "Gadgets, gear and things that go boom",
    "REPAIR": "Dents out, good as new",
    "BOTS": "Little robots that dig while you dig",
    "OIL": "Your oil business: drill, pump, haul and sell",
}
GROUND = 196          # the height of a building picture; its bottom row sits on the ground


def _box(s, color, rect, radius=0, edge=2):
    """A filled box with the theme's dark outline (and a drop shadow under it)."""
    r = pygame.Rect(rect)
    pygame.draw.rect(s, theme.OUTLINE, r.move(0, edge + 1), border_radius=radius)
    pygame.draw.rect(s, theme.OUTLINE, r.inflate(edge * 2, edge * 2), border_radius=radius + edge)
    pygame.draw.rect(s, color, r, border_radius=radius)
    return r


def _sign(s, label, color, center, size=18):
    img = theme.pixel_surface(label, size, (255, 255, 255))
    r = img.get_rect(center=center)
    _box(s, color, r.inflate(18, 10), 6)
    pygame.draw.line(s, _shade(color, 1.3), (r.x - 6, r.y - 2), (r.right + 6, r.y - 2), 2)
    s.blit(img, r)
    return r.inflate(18, 10)


def _window(s, rect, lit):
    r = _box(s, (255, 226, 140) if lit else (126, 196, 244), rect, 3)
    pygame.draw.line(s, (255, 255, 255), (r.x + 4, r.bottom - 6), (r.x + r.w // 2, r.y + 4), 2)
    pygame.draw.line(s, theme.OUTLINE, (r.centerx, r.y), (r.centerx, r.bottom - 1), 2)


def building(name: str, width: int, lit: bool = False) -> pygame.Surface:
    """Each building in town has its own look. `lit` switches the blinking lights (two cached pictures)."""
    key = ("bld", name, width, lit)
    if key in _cache:
        return _cache[key]
    color, label = BUILDING_STYLE[name]
    s = pygame.Surface((width, GROUND), pygame.SRCALPHA)
    {"FUEL": _fuel_station, "SELL": _ore_buyer, "SHOP": _garage, "LAB": _lab, "REPAIR": _repairs,
     "BOTS": _robotics, "OIL": _refinery}[name](
        s, width, color, label, lit)
    _cache[key] = s
    return s


def _fuel_station(s, w, color, label, lit):
    # The kiosk at the back.
    kiosk = _box(s, (240, 236, 226), (w - 92, 92, 84, GROUND - 94), 4)
    pygame.draw.rect(s, color, (kiosk.x, kiosk.y + 8, kiosk.w, 10))
    _window(s, (kiosk.x + 10, kiosk.y + 30, 30, 28), lit)
    _box(s, (70, 70, 84), (kiosk.x + 48, kiosk.y + 30, 26, kiosk.bottom - kiosk.y - 32), 2)
    # The canopy on its pillars, with lights underneath.
    for x in (22, w - 120):
        _box(s, (210, 210, 220), (x, 60, 10, GROUND - 62))
    canopy = _box(s, color, (4, 40, w - 8, 24), 4)
    pygame.draw.rect(s, (255, 255, 255), (canopy.x, canopy.y + 14, canopy.w, 4))
    for x in range(canopy.x + 16, canopy.right - 8, 30):
        pygame.draw.rect(s, (255, 250, 200) if lit else (200, 200, 190), (x, canopy.bottom, 14, 3))
    # Two pumps with glowing displays and hoses.
    for x in (44, w - 150):
        pump = _box(s, (230, 60, 50), (x, GROUND - 52, 24, 50), 4)
        pygame.draw.rect(s, (30, 40, 30), (pump.x + 4, pump.y + 6, 16, 10))
        pygame.draw.rect(s, (90, 255, 120) if lit else (60, 200, 90), (pump.x + 6, pump.y + 8, 12, 6))
        pygame.draw.lines(s, theme.OUTLINE, False, [(pump.right, pump.y + 24), (pump.right + 8, pump.y + 30),
                                                    (pump.right + 6, pump.y + 42)], 3)
    # A tall price sign.
    _box(s, (90, 90, 100), (w - 18, 6, 6, 40))
    _sign(s, label, color, (w // 2 - 10, 20), 20)


def _ore_buyer(s, w, color, label, lit):
    wall = _box(s, (150, 160, 150), (8, 64, w - 16, GROUND - 66), 4)
    for x in range(wall.x + 6, wall.right - 4, 8):           # corrugated metal
        pygame.draw.line(s, (126, 136, 126), (x, wall.y + 2), (x, wall.bottom - 2), 2)
    pygame.draw.polygon(s, theme.OUTLINE, [(2, 68), (w // 2, 30), (w - 2, 68)])
    pygame.draw.polygon(s, color, [(8, 66), (w // 2, 36), (w - 8, 66)])
    pygame.draw.line(s, _shade(color, 1.3), (w // 2, 36), (w - 8, 66), 3)
    # The big sliding door, open, with crates of ore inside.
    door = _box(s, (52, 46, 44), (w // 2 - 46, GROUND - 82, 92, 80), 3)
    pygame.draw.rect(s, (200, 180, 120) if lit else (150, 130, 90), (door.x, door.y, door.w, 4))
    for k, ore in enumerate(ORES[:4]):
        crate = _box(s, (150, 104, 60), (door.x + 6 + k * 22, door.bottom - 22, 18, 20), 2)
        pygame.draw.circle(s, ore.color, (crate.centerx, crate.y + 4), 5)
    # A mine cart full of ore out front, on rails.
    pygame.draw.line(s, (90, 80, 70), (6, GROUND - 3), (62, GROUND - 3), 3)
    cart = _box(s, (110, 110, 124), (12, GROUND - 34, 44, 22), 3)
    for k, c in enumerate(((255, 206, 40), (190, 240, 255), (235, 40, 70), (40, 200, 110))):
        pygame.draw.circle(s, c, (cart.x + 8 + k * 9, cart.y - 1), 5)
    for x in (cart.x + 8, cart.right - 8):
        pygame.draw.circle(s, theme.OUTLINE, (x, cart.bottom + 4), 6)
        pygame.draw.circle(s, (160, 160, 170), (x, cart.bottom + 4), 3)
    # The sign, with a gem.
    r = _sign(s, label, color, (w // 2 + 10, 92), 18)
    _gem(s, (190, 240, 255), r.x - 16, r.centery, 9, random.Random(5))


def _garage(s, w, color, label, lit):
    wall = _box(s, (176, 84, 66), (8, 50, w - 16, GROUND - 52), 3)
    for row, y in enumerate(range(wall.y + 4, wall.bottom, 10)):   # bricks
        pygame.draw.line(s, (150, 70, 56), (wall.x, y), (wall.right - 1, y), 1)
        for x in range(wall.x + (0 if row % 2 else 10), wall.right, 20):
            pygame.draw.line(s, (150, 70, 56), (x, y), (x, y + 9), 1)
    _box(s, (90, 90, 100), (2, 42, w - 4, 12), 3)                  # the roof edge
    # The roll-up door, half open, with the light on inside.
    door = pygame.Rect(w // 2 - 56, GROUND - 92, 112, 90)
    _box(s, (40, 40, 48), door, 2)
    inside = pygame.Rect(door.x, door.y + 44, door.w, door.h - 44)
    pygame.draw.rect(s, (255, 230, 150) if lit else (210, 180, 110), inside)
    for y in range(door.y + 2, door.y + 44, 6):
        pygame.draw.line(s, (130, 140, 160), (door.x, y), (door.right - 1, y), 4)
    pygame.draw.circle(s, (40, 40, 48), (door.centerx - 20, door.bottom - 12), 10)   # a tyre inside
    pygame.draw.rect(s, (200, 60, 50), (door.centerx + 10, door.bottom - 24, 30, 22))   # a toolbox
    # Stacked tyres by the wall.
    for k in range(3):
        pygame.draw.ellipse(s, theme.OUTLINE, (w - 46, GROUND - 14 - k * 12, 34, 14))
        pygame.draw.ellipse(s, (60, 60, 70), (w - 44, GROUND - 13 - k * 12, 30, 11))
    # The sign with a cog.
    r = _sign(s, label, color, (w // 2 + 12, 76), 20)
    cx, cy = r.x - 18, r.centery
    for k in range(8):
        a = k * math.pi / 4
        pygame.draw.circle(s, (200, 200, 210), (int(cx + math.cos(a) * 11), int(cy + math.sin(a) * 11)), 4)
    pygame.draw.circle(s, (200, 200, 210), (cx, cy), 11)
    pygame.draw.circle(s, color, (cx, cy), 4)


def _lab(s, w, color, label, lit):
    base = _box(s, (230, 234, 244), (10, 96, w - 20, GROUND - 98), 6)
    pygame.draw.rect(s, color, (base.x, base.y + 10, base.w, 6))
    dome = pygame.Rect(w // 2 - 70, 40, 140, 112)
    pygame.draw.ellipse(s, theme.OUTLINE, dome.inflate(6, 6))
    pygame.draw.ellipse(s, (210, 220, 240), dome)
    pygame.draw.ellipse(s, (240, 246, 255), dome.inflate(-40, -30).move(-12, -18))
    pygame.draw.rect(s, (230, 234, 244), (dome.x - 4, dome.centery + 2, dome.w + 8, dome.h // 2))   # cut the dome
    for k in range(4):                                        # a ring of glowing windows
        _window(s, (base.x + 16 + k * ((base.w - 52) // 3), base.y + 26, 22, 20), lit and k % 2 == 0)
    _box(s, (60, 60, 80), (w // 2 - 16, GROUND - 52, 32, 50), 4)   # sliding door
    pygame.draw.line(s, (120, 200, 255), (w // 2, GROUND - 50), (w // 2, GROUND - 4), 2)
    # A satellite dish and an antenna with a beacon.
    pygame.draw.line(s, theme.OUTLINE, (w - 46, 70), (w - 40, 50), 3)
    pygame.draw.arc(s, theme.OUTLINE, (w - 64, 26, 36, 36), 0.6, 3.6, 5)
    pygame.draw.arc(s, (220, 224, 236), (w - 63, 27, 34, 34), 0.6, 3.6, 3)
    pygame.draw.line(s, theme.OUTLINE, (34, 96), (34, 50), 2)
    pygame.draw.circle(s, (255, 70, 70) if lit else (120, 40, 50), (34, 48), 5)
    _sign(s, label, color, (w // 2, 116), 18)


def _repairs(s, w, color, label, lit):
    wall = _box(s, (236, 200, 140), (8, 70, w - 16, GROUND - 72), 3)
    pygame.draw.rect(s, (60, 60, 70), (wall.x, wall.y + 12, wall.w, 8))
    for x in range(wall.x, wall.right, 16):                   # hazard stripe
        pygame.draw.polygon(s, color, [(x, wall.y + 12), (x + 8, wall.y + 12), (x + 4, wall.y + 20), (x - 4, wall.y + 20)])
    _box(s, (70, 70, 80), (w // 2 - 34, GROUND - 70, 68, 68), 2)
    pygame.draw.rect(s, (255, 220, 140) if lit else (200, 170, 110), (w // 2 - 30, GROUND - 30, 60, 28))
    # A crane arm with a hook.
    pygame.draw.line(s, theme.OUTLINE, (16, 70), (16, 24), 5)
    pygame.draw.line(s, theme.OUTLINE, (16, 26), (w - 30, 26), 5)
    pygame.draw.line(s, color, (16, 26), (w - 30, 26), 2)
    pygame.draw.line(s, theme.OUTLINE, (w - 34, 26), (w - 34, 52), 2)
    pygame.draw.arc(s, theme.OUTLINE, (w - 42, 48, 14, 14), 3.2, 6.2, 3)
    # An oil barrel.
    _box(s, (60, 110, 200), (w - 34, GROUND - 30, 20, 28), 3)
    _sign(s, label, color, (w // 2 - 6, 50), 18)
    # A wrench on the sign's end.
    pygame.draw.line(s, (200, 200, 210), (w // 2 - 70, 44), (w // 2 - 56, 58), 5)
    pygame.draw.circle(s, (200, 200, 210), (w // 2 - 72, 42), 6)


def _robotics(s, w, color, label, lit):
    wall = _box(s, (196, 206, 214), (8, 76, w - 16, GROUND - 78), 4)
    for x in range(wall.x + 20, wall.right - 10, 40):        # panels
        pygame.draw.line(s, (170, 180, 190), (x, wall.y + 2), (x, wall.bottom - 2), 2)
    # A saw-tooth factory roof with skylights.
    teeth = 4
    tw = (w - 16) / teeth
    for k in range(teeth):
        x = 8 + k * tw
        pygame.draw.polygon(s, theme.OUTLINE, [(x - 2, 78), (x + tw * 0.8, 44), (x + tw * 0.8, 78)])
        pygame.draw.polygon(s, color, [(x + 1, 76), (x + tw * 0.8 - 2, 48), (x + tw * 0.8 - 2, 76)])
        pygame.draw.line(s, (200, 240, 255) if lit else (150, 200, 220), (x + tw * 0.8 - 2, 50),
                         (x + tw * 0.8 - 2, 76), 3)
    # A chimney with a bit of steam.
    _box(s, (110, 110, 124), (w - 40, 24, 14, 30), 2)
    for k, r in enumerate((6, 8, 10)):
        pygame.draw.circle(s, (240, 244, 250), (w - 33 + k * 6, 16 - k * 8), r)
    # The bay door, with a conveyor coming out and a bot riding it.
    door = _box(s, (50, 56, 70), (w // 2 - 48, GROUND - 78, 96, 76), 3)
    pygame.draw.rect(s, (90, 255, 220) if lit else (60, 190, 170), (door.x, door.y, door.w, 4))
    belt = pygame.Rect(10, GROUND - 16, w - 20, 10)
    _box(s, (70, 70, 84), belt, 4)
    for x in range(belt.x + 6, belt.right - 4, 12):
        pygame.draw.circle(s, (130, 130, 144), (x, belt.centery), 3)
    bot_img = bot_sprite(BOT_COLORS[0], 1, 0, 0.0, 0.0, size=34)
    s.blit(bot_img, (w // 2 + 30, GROUND - 16 - 30))
    _sign(s, label, color, (w // 2, 100), 18)


def bot_sprite(color, dx: int, dy: int, spin: float, clock: float, size: int = 26, carry: int = 0,
               glow: bool = False) -> pygame.Surface:
    """A little dig bot: a round body on treads, one big eye, and a drill arm pointing where it's digging."""
    Z = 3
    S = 32 * Z
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    ink = theme.OUTLINE

    def P(x, y):
        return (int(x * Z), int(y * Z))

    def circ(c, x, y, r, w=0):
        pygame.draw.circle(s, c, P(x, y), int(r * Z), int(w * Z) if w else 0)

    def poly(c, pts):
        pygame.draw.polygon(s, c, [P(*p) for p in pts])

    if glow:
        for r, a in ((15, 40), (11, 60)):
            pygame.draw.circle(s, (*color, a), P(16, 16), r * Z)
    # The drill arm, under the body when it points down (so draw it first).
    ax, ay = (dx, dy) if (dx or dy) else (0, 1)
    px, py = -ay, ax                                   # across the arm
    base = (16 + ax * 7, 16 + ay * 7)
    tip = (16 + ax * 15, 16 + ay * 15)
    poly(ink, [(base[0] + px * 4.5, base[1] + py * 4.5), (base[0] - px * 4.5, base[1] - py * 4.5),
               (tip[0] + ax * 1.2, tip[1] + ay * 1.2)])
    poly((200, 206, 218), [(base[0] + px * 3.5, base[1] + py * 3.5), (base[0] - px * 3.5, base[1] - py * 3.5), tip])
    for k in range(2):
        f = (k / 2 + spin * 4) % 1.0
        a = (base[0] + px * 3.5 * (1 - f) + (tip[0] - base[0]) * f, base[1] + py * 3.5 * (1 - f) + (tip[1] - base[1]) * f)
        b = (base[0] - px * 3.5 * (1 - f) + (tip[0] - base[0]) * f, base[1] - py * 3.5 * (1 - f) + (tip[1] - base[1]) * f)
        pygame.draw.line(s, (110, 116, 130), P(*a), P(*b), Z)
    # Treads.
    pygame.draw.rect(s, ink, pygame.Rect(P(6, 20), (20 * Z, 8 * Z)), border_radius=4 * Z)
    pygame.draw.rect(s, (60, 60, 72), pygame.Rect(P(7, 21), (18 * Z, 6 * Z)), border_radius=3 * Z)
    for k in range(3):
        x = 9 + ((k * 6 + clock * 20) % 15)
        circ((120, 120, 134), x, 24, 1.2)
    # The body, its eye, and an antenna.
    circ(ink, 16, 15, 9.5)
    circ(color, 16, 15, 8.5)
    circ(_shade(color, 1.3), 13.5, 11.5, 3.5)
    eye_x = 16 + (dx or 0) * 2
    circ(ink, eye_x, 14, 4.2)
    circ((240, 250, 255), eye_x, 14, 3.4)
    circ((30, 40, 60), eye_x + (dx or 0) * 1.2, 14 + (dy or 0) * 1.2, 1.8)
    pygame.draw.line(s, ink, P(16, 6), P(18, 2), Z)
    blink = int(clock * 3 + color[0]) % 2 == 0
    circ((255, 230, 90) if blink else (150, 130, 60), 18, 2, 1.6)
    for k in range(min(carry, 5)):                      # little lights: how full it is
        circ((255, 220, 90), 11 + k * 2.5, 22.5 - 3, 0.8)
    return pygame.transform.smoothscale(s, (size, size))


def _refinery(s, w, color, label, lit):
    """Storage tanks, a cracking tower with a flare on top, and pipes everywhere."""
    for k, x in enumerate((10, 70)):                          # two fat storage tanks
        tank = _box(s, (214, 218, 226), (x, GROUND - 70, 54, 68), 10)
        pygame.draw.rect(s, (180, 186, 196), (tank.x, tank.y + 14, tank.w, 6))
        pygame.draw.ellipse(s, (236, 240, 246), (tank.x + 2, tank.y - 4, tank.w - 4, 14))
        pygame.draw.rect(s, (40, 40, 48), (tank.x + 8, tank.bottom - 30, 10, 26), border_radius=2)
    tower = _box(s, (150, 156, 170), (w - 70, 44, 34, GROUND - 46), 4)  # the cracking tower
    for y in range(tower.y + 14, tower.bottom - 6, 22):
        pygame.draw.rect(s, (110, 116, 130), (tower.x - 4, y, tower.w + 8, 5))
    pygame.draw.line(s, theme.OUTLINE, (w - 22, 44), (w - 22, 14), 6)  # the flare stack
    pygame.draw.line(s, (130, 136, 150), (w - 22, 44), (w - 22, 14), 3)
    flame = 10 if lit else 7
    pygame.draw.polygon(s, (255, 140, 30), [(w - 28, 14), (w - 16, 14), (w - 22, 14 - flame * 2)])
    pygame.draw.polygon(s, (255, 230, 120), [(w - 25, 14), (w - 19, 14), (w - 22, 14 - flame)])
    for y in (GROUND - 40, GROUND - 20):                      # pipework between it all
        pygame.draw.line(s, theme.OUTLINE, (60, y), (w - 70, y), 7)
        pygame.draw.line(s, (200, 120, 60), (60, y), (w - 70, y), 4)
    pygame.draw.circle(s, (255, 90, 70) if lit else (120, 40, 40), (w - 53, 40), 4)
    _sign(s, label, (60, 60, 72), (w // 2 - 6, GROUND - 100), 16)
    pygame.draw.circle(s, (30, 30, 36), (w // 2 - 80, GROUND - 100), 9)            # an oil drop on the sign
    pygame.draw.polygon(s, (30, 30, 36), [(w // 2 - 88, GROUND - 103), (w // 2 - 72, GROUND - 103),
                                          (w // 2 - 80, GROUND - 118)])
    pygame.draw.circle(s, (120, 120, 140), (w // 2 - 83, GROUND - 103), 2)


def oil_buyer(label: str, color, width: int, lit: bool) -> pygame.Surface:
    """A refinery that buys oil (the Oil Field's two buyers)."""
    key = ("buyer", label, width, lit)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((width, GROUND), pygame.SRCALPHA)
    _refinery(s, width, color, label, lit)
    _cache[key] = s
    return s


def mine_sign(lit: bool) -> pygame.Surface:
    """The signpost between town and the mine."""
    key = ("minesign", lit)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((150, 150), pygame.SRCALPHA)
    _box(s, (130, 90, 56), (68, 60, 12, 90))
    r = _sign(s, "MINE >", (180, 120, 60), (74, 40), 22)
    pygame.draw.circle(s, (255, 230, 120) if lit else (150, 130, 80), (r.right - 4, r.y + 2), 4)
    _cache[key] = s
    return s


def icon(name: str, size: int = 56) -> pygame.Surface:
    """A picture for each upgrade and item."""
    key = ("icon", name, size)
    if key in _cache:
        return _cache[key]
    Z = 2
    S = 64 * Z
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    ink = theme.OUTLINE

    def P(x, y):
        return (int(x * Z), int(y * Z))

    def poly(c, pts, w=0):
        pygame.draw.polygon(s, c, [P(*p) for p in pts], w * Z if w else 0)

    def circ(c, x, y, r, w=0):
        pygame.draw.circle(s, c, P(x, y), int(r * Z), int(w * Z) if w else 0)

    def box(c, x, y, w, h, r=2):
        pygame.draw.rect(s, ink, pygame.Rect(P(x - 2, y - 2), (int((w + 4) * Z), int((h + 4) * Z))), border_radius=int((r + 2) * Z))
        pygame.draw.rect(s, c, pygame.Rect(P(x, y), (int(w * Z), int(h * Z))), border_radius=int(r * Z))

    def line(c, a, b, w=3):
        pygame.draw.line(s, c, P(*a), P(*b), int(w * Z))

    steel, gold = (190, 196, 210), (255, 206, 40)
    if name in ("DRILL", "TOP DRILL"):
        up = name == "TOP DRILL"
        pts = [(18, 14), (46, 14), (32, 54)] if not up else [(18, 50), (46, 50), (32, 10)]
        poly(ink, [(x + (2 if x > 32 else -2 if x < 32 else 0), y) for x, y in pts])
        poly(steel, pts)
        poly((240, 244, 250), [pts[0], ((pts[0][0] + pts[1][0]) / 2, pts[0][1]), pts[2]])
        for k in range(3):
            t = 0.2 + k * 0.25
            a = (pts[0][0] + (pts[2][0] - pts[0][0]) * t, pts[0][1] + (pts[2][1] - pts[0][1]) * t)
            b = (pts[1][0] + (pts[2][0] - pts[1][0]) * (t + 0.1), pts[1][1] + (pts[2][1] - pts[1][1]) * (t + 0.1))
            line((110, 116, 130), a, b, 2)
        if up:
            poly((90, 220, 120), [(48, 30), (58, 30), (53, 20)])
            line((90, 220, 120), (53, 28), (53, 44), 3)
    elif name == "HULL":
        pts = [(32, 8), (52, 16), (50, 36), (32, 56), (14, 36), (12, 16)]
        poly(ink, [(x, y + 2) for x, y in pts])
        poly((90, 150, 230), pts)
        poly((140, 190, 255), [(32, 8), (52, 16), (50, 36), (32, 32)])
        line((255, 255, 255), (24, 30), (30, 38), 3)
        line((255, 255, 255), (30, 38), (42, 22), 3)
    elif name == "ENGINE":
        box((120, 124, 140), 12, 22, 34, 26, 4)
        for k in range(3):
            box(steel, 16 + k * 10, 12, 6, 10, 1)
        poly((255, 140, 30), [(48, 28), (60, 35), (48, 42)])
        poly((255, 230, 120), [(48, 31), (55, 35), (48, 39)])
        circ((70, 72, 84), 29, 35, 6)
    elif name in ("FUEL TANK", "FUEL CAN"):
        box((230, 60, 50) if name == "FUEL CAN" else (240, 170, 40), 14, 16, 34, 40, 5)
        box((90, 90, 100), 38, 8, 8, 8, 2)
        poly((255, 255, 255), [(31, 22), (24, 36), (38, 36)])            # a fuel drop
        circ((255, 255, 255), 31, 40, 7.5)
    elif name == "CARGO":
        box((176, 120, 70), 10, 18, 44, 36, 3)
        line((130, 86, 48), (10, 30), (54, 30), 2)
        line((130, 86, 48), (10, 42), (54, 42), 2)
        for k, c in enumerate((gold, (190, 240, 255), (235, 40, 70))):
            circ(ink, 20 + k * 12, 16, 6)
            circ(c, 20 + k * 12, 15, 5)
    elif name == "RADIATOR":
        box((150, 200, 230), 12, 14, 40, 38, 3)
        for x in range(18, 50, 7):
            line((90, 140, 180), (x, 16), (x, 50), 3)
        for k in range(3):
            line((120, 220, 255), (20 + k * 12, 6), (24 + k * 12, 10), 2)
    elif name == "SHOCKS":
        for k in range(5):
            y = 14 + k * 8
            line(ink, (20, y), (44, y + 4), 6)
            line(steel, (20, y), (44, y + 4), 3)
        box((90, 90, 100), 14, 8, 36, 6, 2)
        box((90, 90, 100), 14, 52, 36, 6, 2)
    elif name == "LAMP":
        for k in range(8):
            a = k * math.pi / 4
            line((255, 230, 120), (32 + math.cos(a) * 18, 28 + math.sin(a) * 18),
                 (32 + math.cos(a) * 26, 28 + math.sin(a) * 26), 3)
        circ(ink, 32, 28, 14)
        circ((255, 240, 160), 32, 28, 12)
        circ((255, 255, 230), 28, 24, 4)
        box((120, 124, 140), 25, 42, 14, 12, 2)
    elif name == "SCANNER":
        circ(ink, 32, 32, 26)
        circ((30, 70, 50), 32, 32, 24)
        for r in (8, 16):
            circ((60, 160, 100), 32, 32, r, 1)
        poly((90, 255, 150), [(32, 32), (54, 22), (56, 32)])
        circ(gold, 22, 40, 3)
        circ((235, 40, 70), 42, 20, 3)
    elif name == "ARMOR":
        for k, (x, y) in enumerate(((10, 12), (34, 12), (10, 36), (34, 36))):
            box((150, 156, 172) if k % 3 == 0 else (120, 126, 142), x, y, 20, 18, 3)
            circ((220, 224, 236), x + 4, y + 4, 2)
    elif name == "REFINERY":
        box((120, 80, 70), 10, 20, 30, 36, 3)
        box((255, 140, 30), 16, 36, 18, 12, 2)
        box((90, 90, 100), 30, 6, 8, 16, 1)
        circ(ink, 48, 40, 11)
        circ(gold, 48, 40, 9)
        line((200, 150, 20), (48, 34), (48, 46), 2)
    elif name == "RESCUE":
        circ(ink, 32, 32, 24)
        circ((255, 255, 255), 32, 32, 22)
        for k in range(4):
            a = k * math.pi / 2 + math.pi / 4
            poly((240, 70, 60), [(32 + math.cos(a - 0.4) * 22, 32 + math.sin(a - 0.4) * 22),
                                 (32 + math.cos(a + 0.4) * 22, 32 + math.sin(a + 0.4) * 22),
                                 (32 + math.cos(a + 0.4) * 11, 32 + math.sin(a + 0.4) * 11),
                                 (32 + math.cos(a - 0.4) * 11, 32 + math.sin(a - 0.4) * 11)])
        circ(ink, 32, 32, 11)
        circ((0, 0, 0, 0), 32, 32, 9)             # (punches the hole in the middle)
    elif name in ("DIG BOTS", "BOT LEVEL"):
        robot = bot_sprite(BOT_COLORS[0] if name == "DIG BOTS" else BOT_COLORS[1], 0, 1, 0.0, 0.0, size=56 * Z)
        s.blit(robot, P(4, 2))
        if name == "BOT LEVEL":
            poly((90, 220, 120), [(46, 22), (60, 22), (53, 8)])
            line((90, 220, 120), (53, 20), (53, 36), 4)
    elif name == "REPAIR KIT":
        box((240, 240, 244), 10, 18, 44, 34, 4)
        box((230, 60, 50), 28, 24, 8, 22, 1)
        box((230, 60, 50), 21, 31, 22, 8, 1)
        line(ink, (26, 18), (26, 12), 3)
        line(ink, (38, 18), (38, 12), 3)
        line(ink, (26, 12), (38, 12), 3)
    elif name == "DYNAMITE":
        for k in range(3):
            box((220, 60, 50), 14 + k * 12, 22, 10, 32, 2)
        box((60, 60, 70), 12, 34, 40, 6, 1)
        line((120, 90, 60), (32, 22), (40, 10), 2)
        circ((255, 220, 90), 41, 9, 4)
    elif name == "MEGA BLAST":
        circ(ink, 30, 36, 20)
        circ((70, 50, 110), 30, 36, 18)
        circ((150, 120, 200), 24, 30, 5)
        box((90, 90, 100), 38, 14, 8, 8, 1)
        line((120, 90, 60), (44, 14), (52, 6), 2)
        for k in range(5):
            a = k * 1.25
            line((255, 220, 90), (54, 6), (54 + math.cos(a) * 6, 6 + math.sin(a) * 6), 2)
    elif name == "TELEPORTER":
        for r, c in ((24, (40, 90, 160)), (18, (80, 170, 240)), (11, (160, 230, 255)), (5, (255, 255, 255))):
            pygame.draw.ellipse(s, c, pygame.Rect(P(32 - r, 32 - r * 0.55), (int(r * 2 * Z), int(r * 1.1 * Z))))
        poly((160, 230, 255), [(28, 30), (36, 30), (32, 6)])
    out = pygame.transform.smoothscale(s, (size, size))
    _cache[key] = out
    return out


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
