"""Card pack wrappers and the light effects used when ripping them open."""

from __future__ import annotations

import math
import random

import pygame

from ..cards import COLORS, number, wild
from . import theme
from .card_art import _clip_rounded, render_card

_cache: dict[tuple, pygame.Surface] = {}

PACK_W, PACK_H = 300, 440
TEAR_Y = 66            # where the tear line runs, in pack pixels
CRIMP = 10             # depth of the crimped edges


def _teeth(w: int, y: int, depth: int, down: bool) -> list[tuple[int, int]]:
    step = 12
    pts = []
    for k, x in enumerate(range(0, w + step, step)):
        pts.append((min(x, w), y + (depth if (k % 2) == down else 0)))
    return pts


def pack_surface(pack, w: int = PACK_W, h: int = PACK_H) -> pygame.Surface:
    """The foil wrapper for a pack tier, drawn at full size and scaled for small views."""
    key = ("pack", pack.id, w, h, theme.ACCENT)
    if key in _cache:
        return _cache[key]
    if (w, h) != (PACK_W, PACK_H):
        img = pygame.transform.smoothscale(pack_surface(pack), (w, h))
        _cache[key] = img
        return img
    light, dark = pack.colors
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    # Foil body with a vertical gradient and a holographic diagonal shimmer.
    body = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        k = y / (h - 1)
        wave = 0.5 + 0.5 * math.sin(k * math.pi * 2.2)
        col = tuple(int(dark[i] + (light[i] - dark[i]) * (0.25 + 0.75 * wave)) for i in range(3))
        pygame.draw.line(body, col, (0, y), (w, y))
    shimmer = pygame.Surface((w, h), pygame.SRCALPHA)
    for x in range(-h, w, 26):
        pygame.draw.polygon(shimmer, (255, 255, 255, 26), [(x, h), (x + 12, h), (x + 12 + h, 0), (x + h, 0)])
    body.blit(shimmer, (0, 0))
    rng = random.Random(pack.id)
    for _ in range(36 if pack.id == "legendary" else 18):
        theme.star(body, (rng.randrange(w), rng.randrange(h)), rng.choice([2, 3, 4, 6]), (255, 255, 255, 150))
    # Crimped top and bottom seals.
    for y0, down in ((0, True), (h - 34, False)):
        seal = pygame.Rect(0, y0, w, 34)
        pygame.draw.rect(body, theme.darken(dark, 20), seal)
        for x in range(4, w, 7):
            pygame.draw.line(body, theme.lighten(dark, 30), (x, seal.y + 6), (x, seal.bottom - 6), 2)
    # Card fan artwork.
    art = pygame.Surface((w, h), pygame.SRCALPHA)
    for k, (card, angle, dx) in enumerate(((number(COLORS[0], 7), 16, -58), (number(COLORS[1], 10), -16, 58),
                                           (wild(), 0, 0))):
        img = pygame.transform.rotozoom(render_card(card, 108, 162, face="classic"), angle, 1)
        art.blit(img, img.get_rect(center=(w // 2 + dx, 210 + abs(dx) // 5)))
    glow = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(glow, (255, 255, 255, 50), (20, 120, w - 40, 190))
    body.blit(glow, (0, 0))
    body.blit(art, (0, 0))
    # Logo and tier name.
    logo = theme.pixel_surface("10 PHASES", 30, theme.ACCENT, theme.OUTLINE)
    body.blit(logo, logo.get_rect(center=(w // 2, 96)))
    banner = pygame.Rect(18, 310, w - 36, 64)
    pygame.draw.rect(body, theme.darken(dark, 30), banner.move(0, 4), border_radius=12)
    pygame.draw.rect(body, (255, 255, 255), banner, border_radius=12)
    pygame.draw.rect(body, dark, banner.inflate(-8, -8), border_radius=9)
    name = theme.pixel_surface(pack.name, 26, (255, 255, 255), theme.OUTLINE)
    body.blit(name, name.get_rect(center=(banner.centerx, banner.centery - 8)))
    sub = theme.pixel_surface("3 CARD SKINS", 14, light, theme.OUTLINE)
    body.blit(sub, sub.get_rect(center=(banner.centerx, banner.centery + 16)))
    # Cut the crimped outline.
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    outline = _teeth(w, 0, CRIMP, True) + list(reversed(_teeth(w, h - CRIMP, CRIMP, False)))
    pygame.draw.polygon(mask, (255, 255, 255, 255), outline)
    body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(body, (0, 0))
    # Dashed tear line with a little notch.
    for x in range(14, w - 14, 14):
        pygame.draw.line(surf, (255, 255, 255, 170), (x, TEAR_Y), (x + 7, TEAR_Y), 2)
    pygame.draw.polygon(surf, (0, 0, 0, 0), [(0, TEAR_Y - 6), (9, TEAR_Y), (0, TEAR_Y + 6)])
    _cache[key] = surf
    return surf


def tear_edge(w: int = PACK_W) -> list[tuple[int, int]]:
    """The jagged line the wrapper rips along."""
    rng = random.Random(5)
    return [(x, TEAR_Y + rng.randint(-5, 5)) for x in range(0, w + 1, 10)]


def split_pack(pack) -> tuple[pygame.Surface, pygame.Surface]:
    """(strip, body): the wrapper cut along the tear line."""
    key = ("split", pack.id, theme.ACCENT)
    if key in _cache:
        return _cache[key][0], _cache[key][1]
    full = pack_surface(pack)
    w, h = full.get_size()
    edge = tear_edge(w)
    top = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(top, (255, 255, 255, 255), [(0, 0), (w, 0)] + list(reversed(edge)))
    bottom = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(bottom, (255, 255, 255, 255), edge + [(w, h), (0, h)])
    strip, body = full.copy(), full.copy()
    strip.blit(top, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    body.blit(bottom, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    # A pale paper edge along the rip.
    for (x1, y1), (x2, y2) in zip(edge, edge[1:]):
        pygame.draw.line(body, (255, 255, 255, 230), (x1, y1 + 1), (x2, y2 + 1), 2)
        pygame.draw.line(strip, (255, 255, 255, 230), (x1, y1 - 1), (x2, y2 - 1), 2)
    strip = strip.subsurface((0, 0, w, TEAR_Y + 8)).copy()
    _cache[key] = (strip, body)
    return strip, body


def silhouette(img: pygame.Surface, color) -> pygame.Surface:
    """A solid-colour copy of an image's shape (for sheen bands and glows)."""
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    out.fill(color)
    out.blit(img, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


def sheen(img: pygame.Surface, t: float, width: float = 0.22, alpha: int = 120) -> pygame.Surface:
    """`img` with a bright diagonal band sweeping across it; t runs 0..1 across the image."""
    w, h = img.get_size()
    band = pygame.Surface((w, h), pygame.SRCALPHA)
    x = -w * 0.6 + (w * 2.2) * t
    bw = w * width
    pygame.draw.polygon(band, (255, 255, 255, alpha), [(x, 0), (x + bw, 0), (x + bw - h * 0.5, h), (x - h * 0.5, h)])
    pygame.draw.polygon(band, (255, 255, 255, alpha // 2),
                        [(x + bw * 1.3, 0), (x + bw * 1.6, 0), (x + bw * 1.6 - h * 0.5, h), (x + bw * 1.3 - h * 0.5, h)])
    # Keep the band inside the image's shape.
    mask = silhouette(img, (255, 255, 255, 255))
    band.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    out = img.copy()
    out.blit(band, (0, 0))
    return out


def glow(radius: int, color) -> pygame.Surface:
    """A soft round light, meant for additive blending (BLEND_RGB_ADD)."""
    key = ("glow", radius, tuple(color))
    if key in _cache:
        return _cache[key]
    surf = pygame.Surface((radius * 2, radius * 2))
    for k in range(24, 0, -1):
        f = (1 - k / 24) ** 2
        pygame.draw.circle(surf, tuple(int(c * f) for c in color), (radius, radius), int(radius * k / 24))
    _cache[key] = surf
    return surf


def card_glow(w: int, h: int, color, spread: int = 34) -> pygame.Surface:
    """A soft glow in the shape of a card, for additive blending."""
    key = ("cglow", w, h, tuple(color), spread)
    if key in _cache:
        return _cache[key]
    surf = pygame.Surface((w + spread * 2, h + spread * 2))
    for k in range(spread, 0, -2):
        f = (1 - k / spread) ** 1.6 * 0.9
        r = pygame.Rect(spread - k, spread - k, w + 2 * k, h + 2 * k)
        pygame.draw.rect(surf, tuple(int(c * f) for c in color), r, border_radius=18 + k)
    _cache[key] = surf
    return surf


def rays(target: pygame.Surface, center, color, strength: float, angle: float, count: int = 14,
         rainbow: bool = False) -> None:
    """Rotating light beams, added onto `target`."""
    if strength <= 0.01:
        return
    w, h = target.get_size()
    layer = _cache.get(("rays-layer", w, h))
    if layer is None:
        layer = _cache[("rays-layer", w, h)] = pygame.Surface((w, h))
    layer.fill((0, 0, 0))
    far = w + h
    cx, cy = center
    for k in range(count):
        a = angle + k * 2 * math.pi / count
        spread = math.pi / count * 0.55
        col = color
        if rainbow:
            import colorsys
            r, g, b = colorsys.hls_to_rgb((k / count + angle * 0.05) % 1, 0.6, 1.0)
            col = (r * 255, g * 255, b * 255)
        col = tuple(int(max(0, min(255, c * strength * 0.55))) for c in col)
        pygame.draw.polygon(layer, col, [(cx, cy), (cx + math.cos(a - spread) * far, cy + math.sin(a - spread) * far),
                                         (cx + math.cos(a + spread) * far, cy + math.sin(a + spread) * far)])
    target.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def mystery_back(pack, w: int, h: int) -> pygame.Surface:
    """The face-down side of a card inside a pack."""
    key = ("mystery", pack.id, w, h)
    if key in _cache:
        return _cache[key]
    light, dark = pack.colors
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    radius = max(6, w // 9)
    pygame.draw.rect(surf, (255, 255, 255), surf.get_rect(), border_radius=radius)
    inner = pygame.Surface((w - 16, h - 16), pygame.SRCALPHA)
    iw, ih = inner.get_size()
    for y in range(ih):
        k = y / max(1, ih - 1)
        pygame.draw.line(inner, tuple(int(dark[i] + (light[i] - dark[i]) * (1 - k) * 0.6) for i in range(3)),
                         (0, y), (iw, y))
    for x in range(-ih, iw, 20):
        pygame.draw.line(inner, theme.lighten(dark, 25), (x, ih), (x + ih, 0), 6)
    pygame.draw.circle(inner, theme.darken(dark, 30), (iw // 2, ih // 2), int(iw * 0.36))
    pygame.draw.circle(inner, (255, 255, 255), (iw // 2, ih // 2), int(iw * 0.36), 4)
    q = theme.pixel_surface("?", int(iw * 0.42), light, theme.OUTLINE)
    inner.blit(q, q.get_rect(center=(iw // 2, ih // 2 + 2)))
    _clip_rounded(inner, radius - 4)
    surf.blit(inner, (8, 8))
    _cache[key] = surf
    return surf
