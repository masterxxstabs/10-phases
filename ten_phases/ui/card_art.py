"""Procedurally drawn cards in a bright, flat, classic shedding-game style:
white border, solid colour face, a tilted white oval in the middle with a big
number, and small numbers in the corners."""

from __future__ import annotations

import colorsys
import math
import random

import pygame

from ..cards import COLORS, Card, Color
from ..skins import BACK_STYLES, FACE_STYLES, gen_spec, parse_gen
from . import skin_gen, theme

OVAL_TILT = 32  # degrees, the oval leans to the right

_cache: dict[tuple, pygame.Surface] = {}


def clear_cache() -> None:
    _cache.clear()


def _rounded_mask(size, radius) -> pygame.Surface:
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    return mask


def _clip_rounded(surf: pygame.Surface, radius: int) -> pygame.Surface:
    surf.blit(_rounded_mask(surf.get_size(), radius), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return surf


def _oval(size, fill=None, quadrants=None) -> pygame.Surface:
    """A tilted oval, either solid or split into four coloured quarters."""
    w, h = size
    ow, oh = int(w * 0.86), int(h * 0.66)
    oval = pygame.Surface((ow, oh), pygame.SRCALPHA)
    if quadrants:
        cx, cy = ow / 2, oh / 2
        # Split along the diagonals so the quarters look right once rotated.
        polys = [[(cx, cy), (0, 0), (ow, 0)], [(cx, cy), (ow, 0), (ow, oh)],
                 [(cx, cy), (ow, oh), (0, oh)], [(cx, cy), (0, oh), (0, 0)]]
        for color, poly in zip(quadrants, polys):
            pygame.draw.polygon(oval, color, poly)
        mask = pygame.Surface((ow, oh), pygame.SRCALPHA)
        pygame.draw.ellipse(mask, (255, 255, 255, 255), mask.get_rect())
        oval.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    else:
        pygame.draw.ellipse(oval, fill, oval.get_rect())
    return pygame.transform.rotozoom(oval, -OVAL_TILT, 1)


def _number(surf, label: str, center, size: int, color, shadow=(0, 0, 0), offset=None, outline=None):
    f = theme.font(size, True, heavy=True)
    offset = offset if offset is not None else max(1, size // 14)
    if outline:
        o = f.render(label, True, outline)
        r = o.get_rect(center=center)
        step = max(1, size // 20)
        for dx in (-step, 0, step):
            for dy in (-step, 0, step):
                if dx or dy:
                    surf.blit(o, r.move(dx, dy))
    sh = f.render(label, True, shadow)
    img = f.render(label, True, color)
    r = img.get_rect(center=center)
    surf.blit(sh, r.move(offset, offset))
    surf.blit(img, r)


def _skip_symbol(surf, center, radius, color):
    w = max(3, radius // 3)
    pygame.draw.circle(surf, color, center, radius, w)
    a = math.radians(45)
    dx, dy = math.cos(a) * (radius - w / 2), math.sin(a) * (radius - w / 2)
    pygame.draw.line(surf, color, (center[0] - dx, center[1] - dy), (center[0] + dx, center[1] + dy), w + 1)


def _face(card) -> str:
    """What's printed on a card: blackjack cards show A/J/Q/K, everything else its number."""
    return getattr(card, "rank_label", None) or str(card.value)


GOLD = (244, 196, 64)
GOLD_DARK = (150, 104, 20)
WHITE_A = (255, 255, 255, 255)

# How each card-front skin is put together. Anything left out uses the default:
#   shape  - the centre shape (None = just the number)
#   bg     - the background behind it, drawn in the card's colour
#   num    - number style: color (card colour, black edge), white, glow (neon), rgb (glitch)
#   frame  - the border: white, gold, rainbow, holo, or an RGB colour
#   ring   - a band around the shape: an RGB colour or "rainbow"
#   edge   - draw a black outline round the shape
#   hollow - outline the shape instead of filling it (neon)
FACES = {
    "classic": {"shape": "oval"},
    "bubble": {"shape": "circle"},
    "minimal": {"shape": None, "bg": "stripe", "num": "white"},
    "diamond": {"shape": "diamond"},
    "ring": {"shape": "ring", "num": "white"},
    "square": {"shape": "square"},
    "split": {"shape": "oval", "bg": "split"},
    "pinstripe": {"shape": "oval", "bg": "pinstripe"},
    "dots": {"shape": "circle", "bg": "dots"},
    "heart": {"shape": "heart"},
    "star": {"shape": "star"},
    "comic": {"shape": "burst", "bg": "rays", "edge": True},
    "neon": {"shape": "oval", "bg": "dark", "num": "glow", "frame": (16, 16, 24), "hollow": True},
    "glitch": {"shape": "square", "bg": "glitch", "num": "rgb", "frame": (24, 24, 32)},
    "cosmic": {"shape": "planet", "bg": "space", "num": "white", "frame": (30, 24, 70)},
    "gold": {"shape": "oval", "ring": GOLD, "frame": "gold"},
    "rainbow": {"shape": "oval", "ring": "rainbow", "frame": "rainbow"},
    "holo": {"shape": "oval", "bg": "holo", "frame": "holo", "ring": (235, 240, 255)},
}


FACES["koi"] = {"shape": None, "bg": "koi", "frame": (30, 46, 86), "num": "glow"}


def _spec(face: str) -> dict:
    spec = FACES.get(face)
    gen = parse_gen(face) if spec is None and face in FACE_STYLES else None
    if gen:
        spec = FACES[face] = _generated_face(gen[1], gen[0])
    return spec or FACES["classic"]


def _generated_face(n: int, series: str = "g") -> dict:
    g = gen_spec("face", n, series)
    base, pat, accent = skin_gen.palette(g)
    frame = {"white": "white", "black": (28, 28, 32), "palette": accent if g["dark"] else base}.get(g["frame"], g["frame"])
    return {"shape": g["shape"], "bg": "gen", "gen": g, "num": g["num"], "frame": frame,
            "ring": accent if g["ring"] else None}


def _hue(h: float, light: float = 0.6, sat: float = 0.9) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, light, sat)
    return int(r * 255), int(g * 255), int(b * 255)


def _rainbow(size, light: float = 0.58, diagonal: bool = False, sat: float = 0.9) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    if diagonal:
        for k in range(-h, w + 1, 2):
            pygame.draw.line(surf, _hue((k + h) / (w + h) * 0.85, light, sat), (k, 0), (k + h, h), 3)
    else:
        for y in range(h):
            pygame.draw.line(surf, _hue(y / max(1, h) * 0.85, light, sat), (0, y), (w, y))
    return surf


def _vgrad(surf, top, bottom, rect=None) -> None:
    rect = pygame.Rect(rect or surf.get_rect())
    for y in range(rect.h):
        k = y / max(1, rect.h - 1)
        col = tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3))
        pygame.draw.line(surf, col, (rect.x, rect.y + y), (rect.right, rect.y + y))


def _star_points(cx, cy, outer, inner, points, turn=-math.pi / 2, jitter=None):
    pts = []
    for k in range(points * 2):
        r = outer if k % 2 == 0 else inner
        if jitter:
            r *= jitter[k % len(jitter)]
        a = turn + k * math.pi / points
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def _shape_mask(size, shape: str, scale: float = 1.0) -> pygame.Surface:
    """A white silhouette of a centre shape, as big as the card's inside."""
    iw, ih = size
    w, h = max(2, int(iw * scale)), max(2, int(ih * scale))
    m = pygame.Surface((iw, ih), pygame.SRCALPHA)
    cx, cy = iw / 2, ih / 2
    if shape == "oval":
        o = _oval((w, h), fill=WHITE_A)
        m.blit(o, o.get_rect(center=(cx, cy)))
    elif shape in ("circle", "planet", "ring"):
        d = int(min(w, h) * (0.86 if shape != "planet" else 0.8))
        r = pygame.Rect(0, 0, d, d)
        r.center = (cx, cy)
        pygame.draw.ellipse(m, WHITE_A, r, max(3, d // 9) if shape == "ring" else 0)
    elif shape == "diamond":
        rx, ry = w * 0.48, h * 0.36
        pygame.draw.polygon(m, WHITE_A, [(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy)])
    elif shape == "square":
        side = int(w * 0.7)
        sq = pygame.Surface((side, side), pygame.SRCALPHA)
        pygame.draw.rect(sq, WHITE_A, sq.get_rect(), border_radius=max(2, side // 7))
        sq = pygame.transform.rotozoom(sq, -16, 1)
        m.blit(sq, sq.get_rect(center=(cx, cy)))
    elif shape == "heart":
        r = w * 0.235
        for dx in (-1, 1):
            pygame.draw.circle(m, WHITE_A, (cx + dx * r * 0.92, cy - r * 0.5), r)
        pygame.draw.polygon(m, WHITE_A, [(cx - r * 1.86, cy - r * 0.2), (cx + r * 1.86, cy - r * 0.2),
                                         (cx, cy + r * 2.25)])
    elif shape == "star":
        pygame.draw.polygon(m, WHITE_A, _star_points(cx, cy + h * 0.02, w * 0.56, w * 0.27, 5))
    elif shape == "burst":
        pygame.draw.polygon(m, WHITE_A, _star_points(cx, cy, w * 0.55, w * 0.4, 11, 0.2,
                                                     (1.0, 0.92, 1.08, 1.0, 0.95, 1.04)))
    return m


def _paint(mask: pygame.Surface, fill) -> pygame.Surface:
    """Colour a silhouette: an RGB colour, "rainbow", or four quadrant colours."""
    w, h = mask.get_size()
    if fill == "rainbow":
        out = _rainbow((w, h))
    else:
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        if isinstance(fill, list):
            cx, cy = w // 2, h // 2
            polys = [[(cx, cy), (0, 0), (w, 0)], [(cx, cy), (w, 0), (w, h)], [(cx, cy), (w, h), (0, h)],
                     [(cx, cy), (0, h), (0, 0)]]
            for color, poly in zip(fill, polys):
                pygame.draw.polygon(out, color, poly)
        else:
            out.fill(fill)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


def _background(inner: pygame.Surface, bg: str, color, spec: dict | None = None) -> None:
    iw, ih = inner.get_size()
    if bg == "koi":
        skin_gen.koi_face_bg(inner, color)
        return
    if bg == "gen":
        g = spec["gen"]
        inner.fill(color)
        tint = {"light": theme.lighten(color, 42), "dark": theme.darken(color, 42), "white": (255, 255, 255)}[g["tint"]]
        if g["tint"] == "white":
            layer = pygame.Surface((iw, ih), pygame.SRCALPHA)
            skin_gen.pattern(layer, g["pattern"], tint, g["scale"], g["seed"])
            layer.set_alpha(70)
            inner.blit(layer, (0, 0))
        else:
            skin_gen.pattern(inner, g["pattern"], tint, g["scale"], g["seed"])
        if g.get("foil"):
            skin_gen.foil(inner, g["hue"], g["foil"])
        return
    c = (iw // 2, ih // 2)
    rng = random.Random(3)
    light, dark = theme.lighten(color, 38), theme.darken(color, 45)
    if bg == "dark":
        inner.fill((10, 10, 18))
    elif bg == "space":
        _vgrad(inner, (10, 8, 36), (44, 18, 84))
        for _ in range(int(iw * ih / 90)):
            inner.set_at((rng.randrange(iw), rng.randrange(ih)), rng.choice([(255, 255, 255), (190, 200, 255)]))
        for _ in range(4):
            theme.star(inner, (rng.randrange(iw), rng.randrange(ih)), max(2, iw // 22), (255, 255, 255))
    else:
        inner.fill(color)
    if bg == "stripe":
        pygame.draw.polygon(inner, theme.lighten(color, 30), [(0, ih * 0.62), (iw, ih * 0.3), (iw, ih * 0.45),
                                                            (0, ih * 0.77)])
    elif bg == "split":
        pygame.draw.polygon(inner, dark, [(iw, ih * 0.25), (iw, ih), (0, ih), (0, ih * 0.75)])
        pygame.draw.polygon(inner, light, [(0, 0), (iw, 0), (iw, ih * 0.1), (0, ih * 0.6)])
    elif bg == "pinstripe":
        step = max(5, iw // 6)
        for k in range(-ih, iw + ih, step):
            pygame.draw.line(inner, light, (k, ih), (k + ih, 0), max(1, iw // 40))
    elif bg == "dots":
        step = max(6, iw // 4)
        for row, y in enumerate(range(0, ih + step, step)):
            for x in range(-step, iw + step, step):
                pygame.draw.circle(inner, light, (x + (step // 2 if row % 2 else 0), y), max(2, step // 4))
    elif bg == "rays":
        for k in range(16):
            if k % 2:
                a1, a2 = k * math.pi / 8, (k + 1) * math.pi / 8
                far = iw + ih
                pygame.draw.polygon(inner, light, [c, (c[0] + math.cos(a1) * far, c[1] + math.sin(a1) * far),
                                                   (c[0] + math.cos(a2) * far, c[1] + math.sin(a2) * far)])
    elif bg == "glitch":
        for y in range(0, ih, 3):
            pygame.draw.line(inner, theme.darken(color, 22), (0, y), (iw, y))
        for _ in range(6):
            y, hgt = rng.randrange(ih), rng.randint(2, max(3, ih // 14))
            band = inner.subsurface((0, y, iw, min(hgt, ih - y))).copy()
            inner.blit(band, (rng.choice([-1, 1]) * rng.randint(3, max(4, iw // 8)), y))
        for col in ((0, 255, 255, 70), (255, 0, 200, 70)):
            bar = pygame.Surface((iw, max(2, ih // 40)), pygame.SRCALPHA)
            bar.fill(col)
            inner.blit(bar, (0, rng.randrange(ih)))
    elif bg == "holo":
        sheen = _rainbow((iw, ih), 0.75, diagonal=True, sat=1.0)
        sheen.set_alpha(95)
        inner.blit(sheen, (0, 0))
        for k in range(3):
            band = pygame.Surface((iw, ih), pygame.SRCALPHA)
            x = iw * (0.1 + 0.4 * k)
            pygame.draw.polygon(band, (255, 255, 255, 60), [(x, 0), (x + iw * 0.14, 0), (x - iw * 0.4, ih),
                                                             (x - iw * 0.54, ih)])
            inner.blit(band, (0, 0))


def _frame(surf: pygame.Surface, frame, radius: int, border: int) -> None:
    rect = surf.get_rect()
    if frame == "rainbow" or frame == "holo":
        art = _rainbow(surf.get_size(), 0.6 if frame == "rainbow" else 0.8, diagonal=frame == "holo")
        surf.blit(_clip_rounded(art, radius), (0, 0))
        if frame == "holo":
            pygame.draw.rect(surf, (200, 205, 230), rect, max(1, border // 2), border_radius=radius)
        return
    color = GOLD if frame == "gold" else theme.CARD_WHITE if frame in (None, "white") else frame
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if frame == "gold":
        pygame.draw.rect(surf, GOLD_DARK, rect, max(1, border // 2), border_radius=radius)


def _number_styled(inner, label, center, size, color, style):
    off = max(2, size // 12)
    if style == "glow":
        _number(inner, label, center, size, color, shadow=(0, 0, 0), offset=off, outline=theme.lighten(color, 90))
    elif style == "white":
        _number(inner, label, center, size, theme.CARD_WHITE, shadow=(0, 0, 0), offset=off, outline=theme.CARD_BLACK)
    elif style == "rgb":
        f = theme.font(size, True, heavy=True)
        for dx, col in ((-off, (0, 230, 255)), (off, (255, 40, 200))):
            img = f.render(label, True, col)
            inner.blit(img, img.get_rect(center=(center[0] + dx, center[1])))
        _number(inner, label, center, size, theme.CARD_WHITE, shadow=(0, 0, 0), offset=0, outline=theme.CARD_BLACK)
    else:
        _number(inner, label, center, size, color, shadow=(0, 0, 0), offset=off, outline=theme.CARD_BLACK)


def _centre(inner, spec: dict, fill, hollow_bg=(10, 10, 18)) -> None:
    """Draw the centre shape, with its ring/outline/hollow extras."""
    size = inner.get_size()
    shape = spec.get("shape", "oval")
    if shape is None:
        return
    icenter = (size[0] // 2, size[1] // 2)
    if spec.get("ring"):
        inner.blit(_paint(_shape_mask(size, shape, 1.1), spec["ring"]), (0, 0))
    if spec.get("edge"):
        inner.blit(_paint(_shape_mask(size, shape, 1.1), theme.CARD_BLACK), (0, 0))
    if shape == "oval" and isinstance(fill, list):
        o = _oval(size, quadrants=fill)   # the classic wild: quarters split before the tilt
        inner.blit(o, o.get_rect(center=icenter))
    else:
        inner.blit(_paint(_shape_mask(size, shape), fill), (0, 0))
    if spec.get("hollow"):
        inner.blit(_paint(_shape_mask(size, shape, 0.86), hollow_bg), (0, 0))
    if shape == "planet" and not isinstance(fill, list):
        iw, ih = size
        ring = pygame.Surface(size, pygame.SRCALPHA)
        r = pygame.Rect(0, 0, int(iw * 1.02), int(ih * 0.2))
        r.center = icenter
        pygame.draw.ellipse(ring, (255, 236, 170), r, max(2, iw // 22))
        # Hide the part of the ring that passes behind the planet.
        d = int(min(iw, ih) * 0.8)
        pygame.draw.rect(ring, (0, 0, 0, 0), (icenter[0] - d // 2, icenter[1] - d // 2, d, d // 2))
        ring = pygame.transform.rotozoom(ring, 18, 1)
        inner.blit(ring, ring.get_rect(center=icenter))


def _draw_face(inner: pygame.Surface, card, face: str, small: int, big: int) -> None:
    spec = _spec(face)
    iw, ih = inner.get_size()
    icenter = (iw // 2, ih // 2)
    corners = (((small * 0.62, small * 0.62), False), ((iw - small * 0.62, ih - small * 0.62), True))
    dark_bg = spec.get("bg") in ("dark", "space")
    if card.is_wild or card.is_skip:
        bg = spec.get("bg") if dark_bg else None
        if bg:
            _background(inner, bg, theme.CARD_BLACK)
        else:
            inner.fill(theme.CARD_BLACK)
        shape = spec.get("shape") or "oval"
        shape = {"ring": "circle", "planet": "circle", "burst": "burst"}.get(shape, shape)
        wspec = dict(spec, shape=shape)
        if card.is_wild:
            quads = [theme.CARD_COLORS[c] for c in (Color.RED, Color.BLUE, Color.YELLOW, Color.GREEN)]
            if spec.get("hollow"):
                _centre(inner, wspec, theme.CARD_COLORS[Color.YELLOW])
            else:
                _centre(inner, dict(wspec, hollow=False), quads)
            _number(inner, "W", icenter, int(big * 0.82), theme.CARD_WHITE, outline=theme.CARD_BLACK)
            for pos, flip in corners:
                _corner(inner, "W", pos, small, theme.CARD_WHITE, flip)
        else:
            _centre(inner, dict(wspec, hollow=False), theme.CARD_WHITE)
            r = int(iw * 0.22)
            _skip_symbol(inner, (icenter[0] + 2, icenter[1] + 2), r, (0, 0, 0))
            _skip_symbol(inner, icenter, r, theme.CARD_BLACK)
            for pos, flip in corners:
                _corner_skip(inner, pos, int(small * 0.45), flip)
            label_size = max(7, int(ih * 0.08))
            _number(inner, "SKIP", (icenter[0], ih - label_size * 1.6), label_size, theme.CARD_WHITE, offset=1)
        return
    color = theme.CARD_COLORS[card.color]
    _background(inner, spec.get("bg", "solid"), color, spec)
    if spec.get("hollow"):
        _centre(inner, spec, color)
    else:
        _centre(inner, spec, color if spec.get("shape") == "planet" else theme.CARD_WHITE)
    label = _face(card)
    size = big if len(label) < 2 else int(big * (0.78 if iw >= 52 else 0.62))
    _number_styled(inner, label, icenter, size, color, spec.get("num", "color"))
    if label in ("6", "9"):
        # Underline 6 and 9 so they read correctly upside down.
        ul_w = int(size * 0.32)
        line = theme.CARD_WHITE if dark_bg else theme.CARD_BLACK
        pygame.draw.line(inner, line, (icenter[0] - ul_w // 2, icenter[1] + size * 0.42),
                         (icenter[0] + ul_w // 2, icenter[1] + size * 0.42), max(2, size // 14))
    for pos, flip in corners:
        _corner(inner, label, pos, small, theme.CARD_WHITE, flip)


def _draw_back(inner: pygame.Surface, style: str) -> None:
    """Card back patterns. The base colour is the Customize card-back colour."""
    iw, ih = inner.get_size()
    c = (iw // 2, ih // 2)
    base = theme.CARD_BACK
    dark = theme.darken(base, 70)
    light = theme.lighten(base, 45)
    yellow = theme.CARD_COLORS[Color.YELLOW]
    rng = random.Random(7)
    lw = max(2, iw // 30)

    def logo(color=yellow, edge=theme.CARD_BLACK, word=theme.CARD_WHITE, at=None):
        x, y = at or c
        _number(inner, "10", (x, y - ih * 0.07), int(ih * 0.3), color, outline=edge)
        _number(inner, "PHASES", (x, y + ih * 0.15), max(8, int(ih * 0.1)), word, outline=edge, offset=1)

    def medallion(fill=theme.CARD_BLACK, edge=theme.CARD_WHITE, r=0.38):
        pygame.draw.circle(inner, fill, c, int(iw * r))
        pygame.draw.circle(inner, edge, c, int(iw * r), lw)

    if style == "koi":
        skin_gen.koi_back(inner, logo)
    elif parse_gen(style) and style in BACK_STYLES:
        series, n = parse_gen(style)
        skin_gen.gen_back(inner, gen_spec("back", n, series), logo, _oval)
    elif style == "stars":
        inner.fill((18, 26, 70))
        for _ in range(int(iw * ih / 180)):
            x, y = rng.randrange(iw), rng.randrange(ih)
            theme.star(inner, (x, y), rng.choice([1.5, 2, 3, 4]), rng.choice([(255, 255, 255), (170, 210, 255), yellow]))
        medallion(base, r=0.36)
        logo()
    elif style == "checker":
        cell = max(4, iw // 6)
        for y in range(0, ih, cell):
            for x in range(0, iw, cell):
                pygame.draw.rect(inner, base if (x // cell + y // cell) % 2 else dark, (x, y, cell, cell))
        medallion()
        logo()
    elif style == "stripes":
        inner.fill(theme.CARD_BLACK)
        step = max(6, iw // 5)
        for k in range(-ih, iw + ih, step):
            pygame.draw.polygon(inner, base, [(k, 0), (k + step // 2, 0), (k + step // 2 - ih, ih), (k - ih, ih)])
        oval = _oval((iw, ih), fill=theme.CARD_BLACK)
        inner.blit(oval, oval.get_rect(center=c))
        logo()
    elif style == "dots":
        inner.fill(base)
        for _ in range(int(iw * ih / 260)):
            r = rng.choice([2, 3, 4, 6, 8]) * max(1, iw // 60)
            pygame.draw.circle(inner, light, (rng.randrange(iw), rng.randrange(ih)), r, max(1, r // 3))
        medallion()
        logo()
    elif style == "waves":
        inner.fill(dark)
        band = max(6, ih // 9)
        for row, y0 in enumerate(range(-band, ih + band, band)):
            pts = [(x, y0 + math.sin(x / max(1, iw) * math.pi * 3 + row) * band * 0.45) for x in range(0, iw + 4, 3)]
            col = (base, light, theme.lighten(base, 20))[row % 3]
            pygame.draw.polygon(inner, col, pts + [(iw, y0 + band), (0, y0 + band)])
        oval = _oval((iw, ih), fill=theme.CARD_BLACK)
        inner.blit(oval, oval.get_rect(center=c))
        logo()
    elif style == "plaid":
        inner.fill(base)
        for k, (step, width, col) in enumerate(((iw // 2, iw // 6, (0, 0, 0, 70)), (iw // 4, max(1, iw // 30),
                                                                                   (255, 255, 255, 90)))):
            layer = pygame.Surface((iw, ih), pygame.SRCALPHA)
            for x in range(step // 3, iw, max(4, step)):
                pygame.draw.rect(layer, col, (x, 0, width, ih))
            for y in range(step // 3, ih, max(4, step)):
                pygame.draw.rect(layer, col, (0, y, iw, width))
            inner.blit(layer, (0, 0))
        medallion()
        logo()
    elif style == "zigzag":
        inner.fill(base)
        band = max(6, ih // 8)
        tooth = max(4, iw // 6)
        for row, y0 in enumerate(range(0, ih + band, band)):
            pts = [(x, y0 + (band // 2 if (x // tooth) % 2 else 0)) for x in range(-tooth, iw + 2 * tooth, tooth)]
            col = (dark, theme.CARD_WHITE, light)[row % 3]
            pygame.draw.lines(inner, col, False, pts, max(2, band // 4))
        medallion()
        logo()
    elif style == "honeycomb":
        inner.fill((236, 162, 22))
        r = max(5, iw // 7)
        hh = r * math.sqrt(3)
        for row in range(-1, int(ih / hh) + 2):
            for col in range(-1, int(iw / (r * 1.5)) + 2):
                x = col * r * 1.5
                y = row * hh + (hh / 2 if col % 2 else 0)
                pts = [(x + math.cos(a) * r, y + math.sin(a) * r) for a in (k * math.pi / 3 for k in range(6))]
                pygame.draw.polygon(inner, (255, 200, 60), pts)
                pygame.draw.polygon(inner, (176, 102, 6), pts, max(1, iw // 40))
        hexr = iw * 0.42
        pts = [(c[0] + math.cos(a) * hexr, c[1] + math.sin(a) * hexr) for a in (k * math.pi / 3 for k in range(6))]
        pygame.draw.polygon(inner, theme.CARD_BLACK, pts)
        pygame.draw.polygon(inner, (255, 214, 90), pts, lw)
        logo((255, 214, 60))
    elif style == "sunset":
        horizon = int(ih * 0.62)
        _vgrad(inner, (255, 96, 120), (255, 190, 80), (0, 0, iw, horizon))
        _vgrad(inner, (40, 30, 110), (14, 10, 50), (0, horizon, iw, ih - horizon))
        sun = pygame.Surface((iw, ih), pygame.SRCALPHA)
        sr = int(iw * 0.34)
        _vgrad(sun, (255, 240, 120), (255, 80, 140), (c[0] - sr, horizon - sr * 2, sr * 2, sr * 2))
        mask = pygame.Surface((iw, ih), pygame.SRCALPHA)
        pygame.draw.circle(mask, WHITE_A, (c[0], horizon - sr // 3), sr)
        for k in range(4):
            y = horizon - sr // 3 + k * max(3, sr // 5) - sr // 6
            pygame.draw.rect(mask, (0, 0, 0, 0), (0, y, iw, max(1, k + 1)))
        sun.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        inner.blit(sun, (0, 0))
        for k in range(5):
            y = horizon + 3 + k * max(3, (ih - horizon) // 6)
            half = int(iw * (0.3 - k * 0.04))
            pygame.draw.line(inner, (255, 140, 120), (c[0] - half, y), (c[0] + half, y), max(1, iw // 50))
        logo(theme.CARD_WHITE, (90, 20, 80), (255, 230, 150), at=(c[0], int(ih * 0.3)))
    elif style == "circuit":
        inner.fill((8, 40, 28))
        green = (60, 230, 140)
        for _ in range(int(iw * ih / 500) + 6):
            x, y = rng.randrange(iw), rng.randrange(ih)
            pts = [(x, y)]
            for _ in range(rng.randint(2, 4)):
                if rng.random() < 0.5:
                    x += rng.choice([-1, 1]) * rng.randint(iw // 8, iw // 3)
                else:
                    y += rng.choice([-1, 1]) * rng.randint(ih // 10, ih // 4)
                pts.append((x, y))
            pygame.draw.lines(inner, (30, 140, 90), False, pts, max(1, iw // 40))
            pygame.draw.circle(inner, green, pts[-1], max(2, iw // 28))
        chip = pygame.Rect(0, 0, int(iw * 0.78), int(ih * 0.5))
        chip.center = c
        for k in range(5):
            for side in (-1, 1):
                px = chip.x + chip.w * (k + 1) / 6
                pygame.draw.line(inner, green, (px, c[1] + side * chip.h // 2), (px, c[1] + side * (chip.h // 2 + 6)), 2)
        pygame.draw.rect(inner, (10, 16, 14), chip, border_radius=max(2, iw // 16))
        pygame.draw.rect(inner, green, chip, lw, border_radius=max(2, iw // 16))
        logo(green, (4, 30, 18), (180, 255, 210))
    elif style == "lava":
        inner.fill((34, 8, 6))
        glow = pygame.Surface((iw, ih), pygame.SRCALPHA)
        for _ in range(14):
            x, y, r = rng.randrange(iw), rng.randrange(ih), rng.randint(iw // 8, iw // 3)
            pygame.draw.circle(glow, (255, 90, 20, 70), (x, y), r)
            pygame.draw.circle(glow, (255, 170, 40, 120), (x, y), r // 2)
            pygame.draw.circle(glow, (255, 240, 120, 160), (x, y), max(1, r // 5))
        inner.blit(glow, (0, 0))
        for _ in range(8):
            x, y = rng.randrange(iw), rng.randrange(ih)
            pts = [(x, y)]
            for _ in range(4):
                x += rng.randint(-iw // 6, iw // 6)
                y += rng.randint(-ih // 8, ih // 8)
                pts.append((x, y))
            pygame.draw.lines(inner, (255, 120, 30), False, pts, max(1, iw // 50))
        medallion((24, 6, 4), (255, 120, 30))
        logo((255, 200, 60), (60, 10, 0), (255, 160, 80))
    elif style == "aurora":
        _vgrad(inner, (6, 12, 40), (8, 46, 66))
        for _ in range(int(iw * ih / 200)):
            inner.set_at((rng.randrange(iw), rng.randrange(ih)), (230, 240, 255))
        lights = pygame.Surface((iw, ih), pygame.SRCALPHA)
        for band, col in enumerate(((80, 255, 170), (90, 200, 255), (200, 120, 255))):
            for x in range(0, iw, 2):
                y = ih * (0.2 + 0.18 * band) + math.sin(x / max(1, iw) * math.pi * 2 + band * 1.7) * ih * 0.08
                length = int(ih * 0.22)
                for k in range(0, length, 2):
                    a = int(110 * (1 - k / length))
                    lights.set_at((x, min(ih - 1, max(0, int(y) + k))), col + (a,))
        inner.blit(lights, (0, 0))
        inner.blit(lights, (1, 0))
        logo((150, 255, 210), (6, 20, 50), (220, 240, 255))
    elif style == "galaxy":
        for y in range(ih):
            k = y / max(1, ih - 1)
            col = (int(40 + 80 * k), int(10 + 20 * math.sin(k * 3)), int(110 - 50 * k))
            pygame.draw.line(inner, col, (0, y), (iw, y))
        for _ in range(int(iw * ih / 120)):
            x, y = rng.randrange(iw), rng.randrange(ih)
            inner.set_at((x, y), rng.choice([(255, 255, 255), (200, 180, 255), (255, 220, 150)]))
        for k in range(3):
            pygame.draw.ellipse(inner, (150, 110, 255), (c[0] - iw * 0.45 + k * 4, c[1] - ih * 0.1 + k * 3,
                                                          iw * 0.9 - k * 8, ih * 0.2 - k * 6), 1)
        logo((255, 230, 120), (40, 10, 80), (230, 220, 255))
    elif style == "gold":
        inner.fill(theme.CARD_BLACK)
        m = max(4, iw // 12)
        pygame.draw.rect(inner, GOLD, (m, m, iw - 2 * m, ih - 2 * m), max(2, iw // 28), border_radius=max(3, iw // 10))
        pygame.draw.rect(inner, GOLD_DARK, (m * 2, m * 2, iw - 4 * m, ih - 4 * m), 1, border_radius=max(3, iw // 12))
        logo(GOLD, theme.CARD_BLACK, GOLD)
    elif style == "holo":
        inner.blit(_rainbow((iw, ih), 0.72, diagonal=True, sat=1.0), (0, 0))
        shine = pygame.Surface((iw, ih), pygame.SRCALPHA)
        for k in range(4):
            x = iw * (-0.2 + 0.42 * k)
            pygame.draw.polygon(shine, (255, 255, 255, 70), [(x, 0), (x + iw * 0.12, 0), (x + iw * 0.12 + ih * 0.6, ih),
                                                              (x + ih * 0.6, ih)])
        inner.blit(shine, (0, 0))
        oval = _oval((iw, ih), fill=(236, 240, 255))
        inner.blit(oval, oval.get_rect(center=c))
        logo((120, 80, 255), theme.CARD_WHITE, (80, 60, 160))
    elif style == "neon":
        inner.fill((8, 8, 16))
        for k, col in enumerate((theme.lighten(base, 60), base, dark)):
            pygame.draw.rect(inner, col, (3 + k * 2, 3 + k * 2, iw - 6 - k * 4, ih - 6 - k * 4), 1,
                             border_radius=max(3, iw // 10))
        _number(inner, "10", (c[0], c[1] - ih * 0.07), int(ih * 0.3), (8, 8, 16), outline=theme.lighten(base, 80))
        _number(inner, "PHASES", (c[0], c[1] + ih * 0.15), max(8, int(ih * 0.1)), theme.lighten(base, 90), offset=1)
    else:  # classic
        inner.fill(theme.CARD_BLACK)
        oval = _oval((iw, ih), fill=base)
        inner.blit(oval, oval.get_rect(center=c))
        logo()


def render_card(card: Card | None, w: int, h: int, face: str | None = None, back: str | None = None) -> pygame.Surface:
    """Render a card face (or the back, if card is None) in the equipped skin, or the one given."""
    face = face or theme.FACE_STYLE
    back = back or theme.BACK_STYLE
    key = ("back", back) if card is None else (card.kind, card.color, card.value, _face(card), face)
    key += (w, h)
    cached = _cache.get(key)
    if cached:
        return cached
    if len(_cache) > 4000:
        _cache.clear()

    radius = max(4, int(w * 0.12))
    border = max(2, int(w * 0.065))
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    _frame(surf, None if card is None else _spec(face).get("frame"), radius, border)

    iw, ih = w - border * 2, h - border * 2
    inner = pygame.Surface((iw, ih), pygame.SRCALPHA)
    if card is None:
        _draw_back(inner, back)
    else:
        _draw_face(inner, card, face, max(9, int(ih * 0.15)), int(ih * 0.42))

    _clip_rounded(inner, max(3, radius - border // 2))
    surf.blit(inner, (border, border))
    _cache[key] = surf
    return surf


def _corner(surf, label, pos, size, color, flip):
    f = theme.font(size, True, heavy=True)
    tmp = pygame.Surface((f.size(label)[0] + 4, f.get_height() + 4), pygame.SRCALPHA)
    tmp.blit(f.render(label, True, (0, 0, 0)), (2, 2))
    tmp.blit(f.render(label, True, color), (1, 1))
    if flip:
        tmp = pygame.transform.rotate(tmp, 180)
    surf.blit(tmp, tmp.get_rect(center=(int(pos[0]) + (0 if flip else 2), int(pos[1]))))


def _corner_skip(surf, pos, radius, flip):
    _skip_symbol(surf, (int(pos[0]) + 1, int(pos[1]) + 1), radius, (0, 0, 0))
    _skip_symbol(surf, (int(pos[0]), int(pos[1])), radius, theme.CARD_WHITE)


def card_with_shadow(card: Card | None, w: int, h: int, lift: int = 0, face: str | None = None,
                     back: str | None = None) -> tuple[pygame.Surface, int]:
    """The card plus a flat offset shadow below it. Returns (surface, shadow_offset)."""
    face, back = face or theme.FACE_STYLE, back or theme.BACK_STYLE
    if card is None:
        face = "-"   # the front doesn't matter for a face-down card
    else:
        back = "-"
    key = ("shadow", None if card is None else (card.kind, card.color, card.value, _face(card)), w, h, lift,
           face, back)
    cached = _cache.get(key)
    off = 4 + lift // 3
    if cached:
        return cached, off
    img = render_card(card, w, h, None if card is None else face, back if card is None else None)
    surf = pygame.Surface((w + off, h + off), pygame.SRCALPHA)
    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 80), sh.get_rect(), border_radius=max(4, int(w * 0.12)))
    surf.blit(sh, (off, off))
    surf.blit(img, (0, 0))
    _cache[key] = surf
    return surf, off


def preview_sheet(path: str) -> None:
    """Debug helper: write every card design to an image."""
    from ..cards import number, skip, wild
    cards = [number(c, v) for c in COLORS for v in (1, 6, 9, 12)] + [wild(), skip(), None]
    w, h = 100, 150
    sheet = pygame.Surface((len(cards) * (w + 10) + 10, h + 20))
    sheet.fill(theme.BG)
    for i, c in enumerate(cards):
        sheet.blit(render_card(c, w, h), (10 + i * (w + 10), 10))
    pygame.image.save(sheet, path)


def app_icon(size: int = 256) -> pygame.Surface:
    """The app/window icon: a tilted card back on a rounded blue tile."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    radius = size // 5
    pygame.draw.rect(surf, (14, 52, 132), surf.get_rect().move(0, size // 40), border_radius=radius)
    pygame.draw.rect(surf, (30, 112, 226), surf.get_rect().inflate(0, -size // 40).move(0, -size // 80),
                     border_radius=radius)
    for k, (dx, angle) in enumerate(((-0.13, 14), (0.06, -8))):
        card = render_card(None, int(size * 0.5), int(size * 0.75))
        if k == 0:
            card = card.copy()
            card.fill((255, 255, 255, 140), special_flags=pygame.BLEND_RGBA_MULT)
        card = pygame.transform.rotozoom(card, angle, 1)
        surf.blit(card, card.get_rect(center=(size // 2 + int(dx * size), size // 2)))
    return surf
