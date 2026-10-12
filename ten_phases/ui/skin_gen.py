"""Pixels for the generated skins, and the hand-drawn koi pond set.

skins.gen_spec(kind, n) gives a recipe (pattern, colours, shape...); this module
draws it. Patterns are drawn tiled over whatever surface they're given.
"""

from __future__ import annotations

import colorsys
import math
import random

import pygame


def hls(h: float, light: float, sat: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, light)), max(0.0, min(1.0, sat)))
    return int(r * 255), int(g * 255), int(b * 255)


def palette(spec: dict) -> tuple[tuple, tuple, tuple]:
    """(base, pattern, accent) colours for a generated card back."""
    h = spec["hue"]
    second = {"mono": h, "complement": h + 0.5, "analog": h + 0.09, "triad": h + 1 / 3}[spec["scheme"]]
    if spec["dark"]:
        return hls(h, 0.16, 0.6), hls(second, 0.42, 0.75), hls(second + 0.04, 0.68, 0.95)
    return hls(h, 0.52, 0.72), hls(second, 0.74, 0.8), hls(second + 0.04, 0.3, 0.8)


# --------------------------------------------------------------------------- patterns


def pattern(surf: pygame.Surface, name: str, color, scale: float = 1.0, seed: int = 0, width_hint=None) -> None:
    """Tile a pattern in `color` over the whole surface (the background is left alone)."""
    w, h = surf.get_size()
    unit = max(5, int((width_hint or w) / 6 * scale))
    lw = max(1, unit // 6)
    rng = random.Random(seed)
    if name == "dots":
        for row, y in enumerate(range(0, h + unit, unit)):
            for x in range(-unit, w + unit, unit):
                pygame.draw.circle(surf, color, (x + (unit // 2 if row % 2 else 0), y), max(2, unit // 4))
    elif name == "stripes":
        for k in range(-h, w + h, unit):
            pygame.draw.polygon(surf, color, [(k, 0), (k + unit // 2, 0), (k + unit // 2 - h, h), (k - h, h)])
    elif name == "checker":
        for y in range(0, h, unit):
            for x in range(0, w, unit):
                if (x // unit + y // unit) % 2:
                    pygame.draw.rect(surf, color, (x, y, unit, unit))
    elif name == "waves":
        for row, y0 in enumerate(range(0, h + unit, unit)):
            pts = [(x, y0 + math.sin(x / unit * math.pi) * unit * 0.3) for x in range(0, w + 3, 3)]
            if len(pts) > 1:
                pygame.draw.lines(surf, color, False, pts, max(2, lw + 1))
    elif name == "zigzag":
        for y0 in range(0, h + unit, unit):
            pts = [(x, y0 + (unit // 2 if (x // max(1, unit // 2)) % 2 else 0)) for x in range(-unit, w + unit,
                                                                                      max(1, unit // 2))]
            pygame.draw.lines(surf, color, False, pts, max(2, lw + 1))
    elif name == "scales":
        seigaiha(surf, None, color, max(6, unit * 0.7), lw)
    elif name == "hex":
        r = unit * 0.55
        hh = r * math.sqrt(3)
        for row in range(-1, int(h / hh) + 2):
            for col in range(-1, int(w / (r * 1.5)) + 2):
                x, y = col * r * 1.5, row * hh + (hh / 2 if col % 2 else 0)
                pts = [(x + math.cos(a) * r, y + math.sin(a) * r) for a in (k * math.pi / 3 for k in range(6))]
                pygame.draw.polygon(surf, color, pts, lw)
    elif name == "triangles":
        for row, y in enumerate(range(0, h + unit, unit)):
            for x in range(-unit, w + unit, unit):
                ox = unit // 2 if row % 2 else 0
                pygame.draw.polygon(surf, color, [(x + ox, y + unit), (x + ox + unit // 2, y), (x + ox + unit, y + unit)],
                                    0 if (x // unit) % 2 else lw)
    elif name == "diamonds":
        for row, y in enumerate(range(0, h + unit, unit)):
            for x in range(-unit, w + unit, unit):
                cx = x + (unit // 2 if row % 2 else 0)
                q = unit // 3
                pygame.draw.polygon(surf, color, [(cx, y - q), (cx + q, y), (cx, y + q), (cx - q, y)])
    elif name == "rings":
        for row, y in enumerate(range(0, h + unit, unit)):
            for x in range(-unit, w + unit, unit):
                pygame.draw.circle(surf, color, (x + (unit // 2 if row % 2 else 0), y), max(3, unit // 3), lw)
    elif name == "crosses":
        for row, y in enumerate(range(0, h + unit, unit)):
            for x in range(-unit, w + unit, unit):
                cx, q = x + (unit // 2 if row % 2 else 0), max(2, unit // 4)
                pygame.draw.line(surf, color, (cx - q, y), (cx + q, y), lw + 1)
                pygame.draw.line(surf, color, (cx, y - q), (cx, y + q), lw + 1)
    elif name == "confetti":
        for _ in range(int(w * h / (unit * unit) * 2.5)):
            x, y, a = rng.randrange(w), rng.randrange(h), rng.uniform(0, math.pi)
            q = unit * 0.3
            pygame.draw.line(surf, color, (x, y), (x + math.cos(a) * q, y + math.sin(a) * q), lw + 1)
    elif name == "stars":
        for _ in range(int(w * h / (unit * unit) * 1.5)):
            x, y, r = rng.randrange(w), rng.randrange(h), rng.uniform(unit * 0.12, unit * 0.32)
            t = r * 0.3
            pygame.draw.polygon(surf, color, [(x, y - r), (x + t, y - t), (x + r, y), (x + t, y + t), (x, y + r),
                                              (x - t, y + t), (x - r, y), (x - t, y - t)])
    elif name == "chevrons":
        for y0 in range(-unit, h + unit, unit):
            pygame.draw.lines(surf, color, False, [(0, y0), (w / 2, y0 + unit * 0.6), (w, y0)], max(2, lw + 1))
    elif name == "grid":
        for x in range(0, w, unit):
            pygame.draw.line(surf, color, (x, 0), (x, h), lw)
        for y in range(0, h, unit):
            pygame.draw.line(surf, color, (0, y), (w, y), lw)
    elif name == "bubbles":
        for _ in range(int(w * h / (unit * unit) * 1.2)):
            r = rng.randint(max(2, unit // 6), max(3, unit // 2))
            pygame.draw.circle(surf, color, (rng.randrange(w), rng.randrange(h)), r, max(1, r // 3))
    elif name == "plaid":
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        for x in range(unit // 3, w, unit * 2):
            pygame.draw.rect(layer, (*color, 110), (x, 0, unit // 2, h))
        for y in range(unit // 3, h, unit * 2):
            pygame.draw.rect(layer, (*color, 110), (0, y, w, unit // 2))
        surf.blit(layer, (0, 0))
    elif name == "sunburst":
        cx, cy, far = w / 2, h / 2, w + h
        for k in range(0, 24, 2):
            a1, a2 = k * math.pi / 12, (k + 1) * math.pi / 12
            pygame.draw.polygon(surf, color, [(cx, cy), (cx + math.cos(a1) * far, cy + math.sin(a1) * far),
                                              (cx + math.cos(a2) * far, cy + math.sin(a2) * far)])


def seigaiha(surf: pygame.Surface, fill, line, r: float, lw: int = 1) -> None:
    """Overlapping wave scales, drawn top row first so each row tucks under the next."""
    w, h = surf.get_size()
    r = max(4.0, r)
    rows = int(h / (r * 0.5)) + 3
    for row in range(-1, rows):
        y = row * r * 0.5
        off = r if row % 2 else 0
        x = -2 * r + off
        while x < w + 2 * r:
            if fill is not None:
                pygame.draw.circle(surf, fill, (int(x), int(y)), int(r))
            for k in (1.0, 0.75, 0.5, 0.25):
                pygame.draw.circle(surf, line, (int(x), int(y)), max(1, int(r * k)), lw, draw_top_left=True,
                                   draw_top_right=True)
            x += 2 * r


# --------------------------------------------------------------------------- koi

KOI_LINE = (206, 220, 240)
KOI_INK = (18, 30, 60)


def koi(surf: pygame.Surface, center, length: float, angle: float, bend: float, rng: random.Random,
        line=KOI_LINE, ink=KOI_INK) -> None:
    """A line-drawn koi seen from above, its head at `center` facing `angle`: a slim pale body with
    dark patches, and long striped fins that trail behind it."""
    cx, cy = center
    n = 26
    spine = [(cx, cy, angle)]
    for k in range(1, n + 1):
        t = k / n
        a = angle + bend * t * 1.6
        px, py, _ = spine[-1]
        step = length * 0.62 / n
        spine.append((px - math.cos(a) * step, py - math.sin(a) * step, a))

    def width(t):
        return length * (0.075 * math.sin(math.pi * min(1.0, 0.22 + t * 0.78)) + 0.018)

    lw = max(1, int(length / 90))
    fins = pygame.Surface(surf.get_size(), pygame.SRCALPHA)   # fins are sheer, so they go on their own layer

    def fin(root, direction, size, spread, curl):
        """A flowing fin: a petal with ribs, drawn ink-filled with a pale outline."""
        pts_l, pts_r = [], []
        for k in range(11):
            s = k / 10
            a = direction + curl * s
            r = size * s
            off = math.sin(math.pi * min(1.0, s * 1.15)) * size * spread
            x = root[0] + math.cos(a) * r
            y = root[1] + math.sin(a) * r
            pts_l.append((x + math.cos(a + math.pi / 2) * off, y + math.sin(a + math.pi / 2) * off))
            pts_r.append((x - math.cos(a + math.pi / 2) * off, y - math.sin(a + math.pi / 2) * off))
        poly = pts_l + list(reversed(pts_r))
        pygame.draw.polygon(fins, (*line, 70), poly)
        pygame.draw.polygon(fins, (*line, 255), poly, lw)
        for k in (0.2, 0.4, 0.6, 0.8):
            rib = [(pl[0] + (pr[0] - pl[0]) * k, pl[1] + (pr[1] - pl[1]) * k) for pl, pr in zip(pts_l, pts_r)]
            pygame.draw.lines(fins, (*line, 200), False, rib, max(1, lw - 1))

    # Tail: two long lobes splaying out from the end of the body.
    tx, ty, ta = spine[-1]
    back = ta + math.pi
    for side in (-1, 0, 1):
        fin((tx, ty), back + side * 0.45, length * (0.5 if side else 0.4), 0.3, side * 0.45 + bend * 0.7)
    # Pectoral and pelvic fins.
    for frac, size in ((0.2, 0.32), (0.58, 0.2)):
        fx, fy, fa = spine[int(n * frac)]
        for side in (-1, 1):
            root = (fx + math.cos(fa + side * math.pi / 2) * width(frac) * 0.7,
                    fy + math.sin(fa + side * math.pi / 2) * width(frac) * 0.7)
            fin(root, fa + math.pi + side * 1.05, length * size, 0.42, side * 0.4)
    surf.blit(fins, (0, 0))
    # Body: outline pass then pale fill.
    for k, (x, y, _) in enumerate(spine):
        pygame.draw.circle(surf, ink, (x, y), width(k / n) + lw + 1)
    for k, (x, y, _) in enumerate(spine):
        pygame.draw.circle(surf, line, (x, y), width(k / n))
    # Dark patches along the back and spots on the head.
    for _ in range(rng.randint(3, 5)):
        k = rng.randint(4, n - 4)
        x, y, a = spine[k]
        r = width(k / n) * rng.uniform(0.5, 0.85)
        off = rng.uniform(-0.35, 0.35) * width(k / n)
        patch = pygame.Rect(0, 0, int(r * 2.6), int(r * 1.5))
        patch.center = (int(x + math.cos(a + math.pi / 2) * off), int(y + math.sin(a + math.pi / 2) * off))
        pygame.draw.ellipse(surf, ink, patch)
    for _ in range(rng.randint(2, 4)):
        k = rng.randint(1, 3)
        x, y, _ = spine[k]
        pygame.draw.circle(surf, ink, (x + rng.uniform(-1, 1) * width(0.1) * 0.4,
                                       y + rng.uniform(-1, 1) * width(0.1) * 0.4), max(1, length / 90))
    # Whiskers.
    for side in (-1, 1):
        pts = [(cx + math.cos(angle) * width(0) * 0.5, cy + math.sin(angle) * width(0) * 0.5)]
        for k in range(1, 5):
            a = angle + side * (0.6 + k * 0.3)
            pts.append((pts[-1][0] + math.cos(a) * length * 0.035, pts[-1][1] + math.sin(a) * length * 0.035))
        pygame.draw.lines(surf, line, False, pts, max(1, lw - 1))


def koi_sprite(length: float, bend: float, seed: int, line=KOI_LINE, ink=KOI_INK) -> pygame.Surface:
    """One koi, heading right, cropped tight so it's easy to place: blit it centred where it should swim."""
    size = int(length * 2.4)
    canvas = pygame.Surface((size, size), pygame.SRCALPHA)
    koi(canvas, (size * 0.72, size / 2), length, 0.0, bend, random.Random(seed), line, ink)
    return canvas.subsurface(canvas.get_bounding_rect()).copy()


def place_koi(surf: pygame.Surface, center, length: float, heading_deg: float, bend: float, seed: int,
              line=KOI_LINE, ink=KOI_INK) -> None:
    img = pygame.transform.rotozoom(koi_sprite(length, bend, seed, line, ink), heading_deg, 1)
    surf.blit(img, img.get_rect(center=(int(center[0]), int(center[1]))))


def koi_back(inner: pygame.Surface, logo) -> None:
    iw, ih = inner.get_size()
    inner.fill((22, 36, 70))
    seigaiha(inner, (22, 36, 70), (44, 66, 116), max(5, iw / 9), max(1, iw // 70))
    for (fx, fy, heading, bend, size, seed) in ((0.5, 0.15, 170, 0.5, 0.55, 1), (0.5, 0.85, -10, 0.5, 0.55, 2),
                                                (0.13, 0.5, 100, -0.4, 0.4, 3), (0.87, 0.5, -80, -0.4, 0.4, 4)):
        place_koi(inner, (iw * fx, ih * fy), iw * size, heading, bend, seed)
    r = int(iw * 0.3)
    pygame.draw.circle(inner, (16, 26, 54), (iw // 2, ih // 2), r)
    pygame.draw.circle(inner, KOI_LINE, (iw // 2, ih // 2), r, max(2, iw // 34))
    logo(KOI_LINE, (10, 18, 40), (230, 238, 250))


def koi_face_bg(inner: pygame.Surface, color) -> None:
    """The koi front: deep water tinted with the card's colour, waves, and two koi circling the number."""
    iw, ih = inner.get_size()
    deep = tuple(int(c * 0.3 + 12) for c in color)
    wave = tuple(int(c * 0.5 + 24) for c in color)
    inner.fill(deep)
    seigaiha(inner, deep, wave, max(4, iw / 8), max(1, iw // 70))
    light = tuple(min(255, int(c * 0.3 + 180)) for c in color)
    ink = tuple(int(c * 0.22 + 8) for c in color)
    place_koi(inner, (iw * 0.56, ih * 0.16), iw * 0.5, 172, 0.5, 5, light, ink)
    place_koi(inner, (iw * 0.44, ih * 0.84), iw * 0.5, -8, 0.5, 6, light, ink)


# --------------------------------------------------------------------------- generated backs


def gen_back(inner: pygame.Surface, spec: dict, logo, oval) -> None:
    iw, ih = inner.get_size()
    base, pat, accent = palette(spec)
    inner.fill(base)
    pattern(inner, spec["pattern"], pat, spec["scale"], spec["seed"])
    if spec.get("foil"):
        foil(inner, spec["hue"], spec["foil"])
    c = (iw // 2, ih // 2)
    edge = max(2, iw // 30)
    dark = tuple(int(v * 0.35) for v in base)
    med = spec["medallion"]
    if med == "circle":
        pygame.draw.circle(inner, dark, c, int(iw * 0.37))
        pygame.draw.circle(inner, accent, c, int(iw * 0.37), edge)
    elif med == "oval":
        o = oval((iw, ih), fill=dark)
        inner.blit(o, o.get_rect(center=c))
    elif med == "hex":
        r = iw * 0.42
        pts = [(c[0] + math.cos(a) * r, c[1] + math.sin(a) * r) for a in (k * math.pi / 3 for k in range(6))]
        pygame.draw.polygon(inner, dark, pts)
        pygame.draw.polygon(inner, accent, pts, edge)
    elif med == "diamond":
        rx, ry = iw * 0.46, ih * 0.3
        pts = [(c[0], c[1] - ry), (c[0] + rx, c[1]), (c[0], c[1] + ry), (c[0] - rx, c[1])]
        pygame.draw.polygon(inner, dark, pts)
        pygame.draw.polygon(inner, accent, pts, edge)
    else:   # banner
        band = pygame.Rect(0, int(ih * 0.3), iw, int(ih * 0.4))
        pygame.draw.rect(inner, dark, band)
        pygame.draw.line(inner, accent, band.topleft, band.topright, edge)
        pygame.draw.line(inner, accent, band.bottomleft, band.bottomright, edge)
    light = tuple(min(255, int(v * 0.5 + 128)) for v in accent)
    logo(light, (10, 10, 20), (255, 255, 255))


def foil(inner: pygame.Surface, hue: float, kind="rainbow") -> None:
    """A shiny foil finish over the whole card (rarer generated skins)."""
    if kind is True:
        kind = "rainbow"
    iw, ih = inner.get_size()
    layer = pygame.Surface((iw, ih), pygame.SRCALPHA)
    if kind == "prism":
        # Little triangles of every colour, like a prism sticker.
        rng = random.Random(int(hue * 1000))
        step = max(6, iw // 7)
        for y in range(0, ih + step, step):
            for x in range(0, iw + step, step):
                for flip in (0, 1):
                    pts = [(x, y), (x + step, y), (x + step, y + step)] if flip else [(x, y), (x, y + step),
                                                                                       (x + step, y + step)]
                    col = hls(hue + rng.random() * 0.6, 0.7, 1.0)
                    pygame.draw.polygon(layer, (*col, rng.randint(25, 80)), pts)
    elif kind == "aurora":
        for y in range(ih):
            k = y / max(1, ih - 1)
            col = hls(0.33 + 0.4 * math.sin(k * math.pi * 1.5 + hue * 6), 0.65, 1.0)
            pygame.draw.line(layer, (*col, 55), (0, y), (iw, y))
    else:
        for k in range(-ih, iw, 3):
            t = (k + ih) / (iw + ih)
            if kind == "gold":
                col = hls(0.12 + 0.03 * math.sin(t * 12), 0.55 + 0.2 * math.sin(t * 9), 0.9)
            elif kind == "silver":
                v = int(170 + 70 * math.sin(t * 11))
                col = (v, v, min(255, v + 20))
            else:
                col = hls(hue + t, 0.7, 1.0)
            pygame.draw.line(layer, (*col, 70 if kind != "rainbow" else 60), (k, ih), (k + ih, 0), 3)
    inner.blit(layer, (0, 0))
    # A couple of bright glints so it reads as shiny even standing still.
    glint = pygame.Surface((iw, ih), pygame.SRCALPHA)
    for x0, wd in ((0.15, 0.08), (0.55, 0.16)):
        x = iw * x0
        pygame.draw.polygon(glint, (255, 255, 255, 55), [(x, 0), (x + iw * wd, 0), (x + iw * wd - ih * 0.5, ih),
                                                          (x - ih * 0.5, ih)])
    inner.blit(glint, (0, 0))
