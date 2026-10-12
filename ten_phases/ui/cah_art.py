"""Drawing Cards Against Humanity cards: white answers, black questions, blank cards and pictures."""

from __future__ import annotations

import base64
import io

import pygame

from . import theme

_cache: dict[tuple, pygame.Surface] = {}
_images: dict[str, pygame.Surface | None] = {}

INK = (16, 16, 20)
PAPER = (250, 250, 246)
BLANK_INK = (150, 150, 160)
IMAGE_MAX = 192          # pictures are shrunk to this many pixels on their long side before sending


def wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if font.size(trial)[0] <= width or not cur:
            cur = trial
            while font.size(cur)[0] > width and len(cur) > 1:   # one huge word: break it
                cut = len(cur) - 1
                while cut > 1 and font.size(cur[:cut])[0] > width:
                    cut -= 1
                lines.append(cur[:cut])
                cur = cur[cut:]
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_text(text: str, width: int, height: int, start: int, smallest: int = 9) -> tuple[pygame.font.Font, list[str]]:
    """The biggest font (from `start` down) at which the text fits the box."""
    size = start
    while True:
        font = theme.font(size, True)
        lines = wrap(text, font, width)
        words_fit = all(font.size(word)[0] <= width for word in text.split())
        if (words_fit and len(lines) * font.get_linesize() <= height) or size <= smallest:
            return font, lines
        size -= 1


def show_blanks(text: str) -> str:
    return text.replace("_", "_____")


def image_surface(data: str | None, key: str | None = None) -> pygame.Surface | None:
    """Decode a base64 picture (None if it isn't a picture pygame can read)."""
    if not data:
        return None
    key = key or str(hash(data))
    if key not in _images:
        try:
            _images[key] = pygame.image.load(io.BytesIO(base64.b64decode(data)), "pic.jpg").convert()
        except (pygame.error, ValueError, TypeError):
            _images[key] = None
    return _images[key]


def encode_image_file(path: str) -> str:
    """Load a picture from disk, shrink it, and return it as base64 JPEG. Raises ValueError if it can't."""
    try:
        img = pygame.image.load(path)
    except (pygame.error, FileNotFoundError, OSError) as e:
        raise ValueError("That file isn't a picture the game can open (try PNG or JPG).") from e
    w, h = img.get_size()
    scale = min(1.0, IMAGE_MAX / max(w, h))
    img = pygame.transform.smoothscale(img.convert_alpha() if img.get_alpha() else img.convert(),
                                       (max(1, int(w * scale)), max(1, int(h * scale))))
    flat = pygame.Surface(img.get_size())
    flat.fill((255, 255, 255))
    flat.blit(img, (0, 0))
    buf = io.BytesIO()
    pygame.image.save(flat, buf, "pic.jpg")
    return base64.b64encode(buf.getvalue()).decode()


def _footer(surf, color):
    w, h = surf.get_size()
    f = theme.font(max(7, w // 16), True)
    img = f.render("Cards Against Humanity", True, color)
    surf.blit(img, (max(6, w // 14), h - img.get_height() - max(4, h // 28)))


def white_card(text: str, w: int, h: int, blank: bool = False, image: str | None = None,
               image_key: str | None = None, selected: int | None = None, dim: bool = False) -> pygame.Surface:
    """A white answer card. `selected` draws an order badge (1, 2, 3) for multi-pick answers."""
    key = ("w", text, w, h, blank, image_key or bool(image), selected, dim)
    if key in _cache:
        return _cache[key]
    if len(_cache) > 1500:
        _cache.clear()
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    radius = max(6, w // 12)
    pygame.draw.rect(surf, PAPER, surf.get_rect(), border_radius=radius)
    pygame.draw.rect(surf, (200, 200, 205), surf.get_rect(), 2, border_radius=radius)
    pad = max(6, w // 12)
    area = pygame.Rect(pad, pad, w - 2 * pad, h - 2 * pad - max(10, h // 9))
    pic = image_surface(image, image_key)
    if pic is not None:
        box = pygame.Rect(area.x, area.y, area.w, int(area.h * (0.62 if text else 1.0)))
        pw, ph = pic.get_size()
        s = min(box.w / pw, box.h / ph)
        scaled = pygame.transform.smoothscale(pic, (max(1, int(pw * s)), max(1, int(ph * s))))
        surf.blit(scaled, scaled.get_rect(midtop=box.midtop))
        area = pygame.Rect(area.x, box.bottom + 4, area.w, area.bottom - box.bottom - 4)
    if blank and not text and pic is None:
        pygame.draw.rect(surf, BLANK_INK, area.inflate(-2, -2), 2, border_radius=6)
        font, lines = fit_text("BLANK CARD - write your own answer", area.w - 12, area.h - 12, max(10, w // 8))
        color = BLANK_INK
    else:
        font, lines = fit_text(text, area.w, max(10, area.h), max(10, w // 8))
        color = INK
    y = area.y + (2 if pic is None else 0)
    for line in lines:
        surf.blit(font.render(line, True, color), (area.x + (6 if blank and not text and pic is None else 0), y))
        y += font.get_linesize()
    _footer(surf, (150, 150, 155))
    if blank and (text or pic is not None):
        tag = theme.font(max(7, w // 15), True).render("BLANK", True, (120, 120, 130))
        surf.blit(tag, tag.get_rect(topright=(w - 4, 2)))
    if dim:
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(shade, (0, 0, 0, 110), shade.get_rect(), border_radius=radius)
        surf.blit(shade, (0, 0))
    if selected:
        r = max(12, w // 7)
        pygame.draw.circle(surf, theme.OUTLINE, (w - r - 2, r + 4), r)
        pygame.draw.circle(surf, theme.ACCENT, (w - r - 2, r + 2), r)
        theme.ptext(surf, str(selected), (w - r - 2, r + 2), max(12, r), theme.OUTLINE, None, anchor="center")
    _cache[key] = surf
    return surf


def black_card(text: str, pick: int, w: int, h: int) -> pygame.Surface:
    key = ("b", text, pick, w, h)
    if key in _cache:
        return _cache[key]
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    radius = max(6, w // 12)
    pygame.draw.rect(surf, INK, surf.get_rect(), border_radius=radius)
    pygame.draw.rect(surf, (70, 70, 80), surf.get_rect(), 2, border_radius=radius)
    pad = max(8, w // 12)
    font, lines = fit_text(show_blanks(text), w - 2 * pad, h - 2 * pad - max(16, h // 7), max(11, w // 9))
    y = pad
    for line in lines:
        surf.blit(font.render(line, True, (245, 245, 245)), (pad, y))
        y += font.get_linesize()
    _footer(surf, (150, 150, 160))
    if pick > 1:
        f = theme.font(max(9, w // 13), True)
        tag = f.render(f"PICK {pick}", True, INK)
        r = tag.get_rect(bottomright=(w - pad, h - max(4, h // 28)))
        pygame.draw.rect(surf, (245, 245, 245), r.inflate(10, 4), border_radius=8)
        surf.blit(tag, r)
    _cache[key] = surf
    return surf


def filled_sentence(black: str, answers: list[str]) -> list[tuple[str, bool]]:
    """The question with the answers dropped in: [(text, is_answer), ...] word by word."""
    parts = black.split("_")
    out: list[tuple[str, bool]] = []
    answers = [a.rstrip(".") if k < len(parts) - 1 else a for k, a in enumerate(answers)]
    if len(parts) == 1:   # no blanks: the answer goes after the question
        out += [(w, False) for w in black.split()]
        for a in answers:
            out += [(w, True) for w in a.split()]
        return out
    for k, part in enumerate(parts):
        out += [(w, False) for w in part.split()]
        if k < len(parts) - 1:
            a = answers[k] if k < len(answers) else "_____"
            out += [(w, True) for w in a.split()]
    return out


def draw_sentence(surf, words: list[tuple[str, bool]], rect: pygame.Rect, start: int = 24) -> None:
    """Draw a filled-in question, with the answers highlighted, fitted into rect."""
    size = start
    while size > 10:
        font = theme.font(size, True)
        x, y = 0, 0
        for word, _ in words:
            ww = font.size(word + " ")[0]
            if x + ww > rect.w and x:
                x, y = 0, y + font.get_linesize()
            x += ww
        if y + font.get_linesize() <= rect.h:
            break
        size -= 1
    font = theme.font(size, True)
    x, y = rect.x, rect.y
    for word, answer in words:
        img = font.render(word, True, theme.ACCENT if answer else (245, 245, 245))
        space = font.size(" ")[0]
        if x + img.get_width() > rect.right and x > rect.x:
            x, y = rect.x, y + font.get_linesize()
        surf.blit(img, (x, y))
        x += img.get_width() + space
