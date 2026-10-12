"""Chiptune sound effects, synthesised at start-up (no audio files needed).

Use `play("name")` from anywhere. If audio isn't available, every call is a no-op.
"""

from __future__ import annotations

import math
import random
from array import array

import pygame

RATE = 22050
VOLUME_LEVELS = {"Off": 0.0, "Low": 0.25, "Medium": 0.55, "High": 0.9}

_sounds: dict[str, pygame.mixer.Sound] = {}
_volume = VOLUME_LEVELS["Medium"]
_enabled = False


# --------------------------------------------------------------------------- synthesis


def _note(name: str) -> float:
    """'C5' -> frequency in Hz."""
    names = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4, "F#": -3, "G": -2, "G#": -1, "A": 0,
             "A#": 1, "B": 2}
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((names[pitch] + (octave - 4) * 12) / 12)


def tone(freq: float, dur: float, wave: str = "square", vol: float = 0.5, slide_to: float | None = None,
         attack: float = 0.004, decay: float = 6.0, duty: float = 0.5, vibrato: float = 0.0) -> list[float]:
    n = int(RATE * dur)
    out = []
    phase = 0.0
    for i in range(n):
        t = i / RATE
        f = freq if slide_to is None else freq + (slide_to - freq) * (i / n)
        if vibrato:
            f *= 1 + 0.03 * math.sin(2 * math.pi * vibrato * t)
        phase = (phase + f / RATE) % 1.0
        if wave == "square":
            s = 1.0 if phase < duty else -1.0
        elif wave == "triangle":
            s = 4 * abs(phase - 0.5) - 1
        else:
            s = math.sin(2 * math.pi * phase)
        env = min(1.0, t / attack) * math.exp(-decay * t)
        out.append(s * env * vol)
    return out


def noise(dur: float, vol: float = 0.4, decay: float = 30.0, smooth: float = 0.0, seed: int = 1) -> list[float]:
    rng = random.Random(seed)
    n = int(RATE * dur)
    out, prev = [], 0.0
    for i in range(n):
        s = rng.uniform(-1, 1)
        prev = prev * smooth + s * (1 - smooth)
        out.append(prev * vol * math.exp(-decay * i / RATE))
    return out


def silence(dur: float) -> list[float]:
    return [0.0] * int(RATE * dur)


def seq(*parts: list[float]) -> list[float]:
    out: list[float] = []
    for p in parts:
        out += p
    return out


def mix(*parts: list[float]) -> list[float]:
    out = [0.0] * max(len(p) for p in parts)
    for p in parts:
        for i, s in enumerate(p):
            out[i] += s
    return out


def arpeggio(notes: str, step: float, wave: str = "square", vol: float = 0.35, hold: float = 0.0,
             duty: float = 0.5) -> list[float]:
    names = notes.split()
    parts = []
    for k, nm in enumerate(names):
        last = k == len(names) - 1
        d = step + (hold if last else 0)
        parts.append(tone(_note(nm), d, wave, vol, decay=3 if last else 8, duty=duty))
    return seq(*parts)


def _soften(samples: list[float], amount: float = 0.35) -> list[float]:
    """One-pole low-pass so the square waves aren't harsh."""
    out, prev = [], 0.0
    for s in samples:
        prev = prev * amount + s * (1 - amount)
        out.append(prev)
    return out


def recipes() -> dict[str, list[float]]:
    return {
        "click": tone(880, 0.05, vol=0.3, decay=40, duty=0.25),
        "select": tone(1320, 0.04, vol=0.22, decay=50, duty=0.25),
        "deselect": tone(990, 0.04, vol=0.18, decay=50, duty=0.25),
        "draw": mix(noise(0.09, 0.25, decay=35, smooth=0.3), tone(520, 0.09, "triangle", 0.35, slide_to=980, decay=18)),
        "discard": mix(noise(0.07, 0.4, decay=50, smooth=0.55, seed=3),
                       tone(170, 0.11, "triangle", 0.55, slide_to=110, decay=25)),
        "hit": seq(tone(660, 0.045, vol=0.28, decay=25), tone(990, 0.08, vol=0.28, decay=22)),
        "lay": arpeggio("C5 E5 G5 C6", 0.065, vol=0.3, hold=0.18),
        "skip": tone(950, 0.3, vol=0.3, slide_to=260, decay=5, vibrato=18, duty=0.3),
        "turn": seq(tone(_note("E5"), 0.09, "triangle", 0.5, decay=12),
                    tone(_note("A5"), 0.2, "triangle", 0.5, decay=8)),
        "error": mix(tone(150, 0.2, vol=0.25, decay=8), tone(156, 0.2, vol=0.2, decay=8)),
        "shuffle": seq(*[seq(noise(0.025, 0.3, decay=80, smooth=0.4, seed=k), silence(0.03)) for k in range(7)]),
        "phase": mix(noise(0.35, 0.12, decay=6, smooth=0.85, seed=9),
                     seq(silence(0.08), arpeggio("G5 D6 G6", 0.07, "triangle", 0.4, hold=0.25))),
        "fish": mix(noise(0.32, 0.22, decay=9, smooth=0.75, seed=5),
                    seq(silence(0.04), tone(700, 0.08, "sine", 0.35, slide_to=1100, decay=20),
                        tone(500, 0.08, "sine", 0.3, slide_to=900, decay=20),
                        tone(380, 0.14, "sine", 0.25, slide_to=700, decay=14))),
        "coin": seq(tone(_note("B5"), 0.06, vol=0.28, decay=4, duty=0.5), tone(_note("E6"), 0.3, vol=0.28, decay=7)),
        "round_win": seq(arpeggio("C5 E5 G5 C6", 0.08, vol=0.3), silence(0.04),
                         arpeggio("G5 C6", 0.12, vol=0.3, hold=0.3)),
        "round_end": arpeggio("G4 C5 E5", 0.11, "triangle", 0.45, hold=0.25),
        "game_win": seq(arpeggio("C5 C5 C5 C5", 0.09, vol=0.28), arpeggio("G#4 A#4 C5", 0.14, vol=0.28),
                        silence(0.06), arpeggio("A#4 C5", 0.12, vol=0.3, hold=0.6)),
        "game_lose": arpeggio("G4 F#4 F4 E4", 0.18, "triangle", 0.45, hold=0.4),
    }


# --------------------------------------------------------------------------- playback


def init(volume: str = "Medium") -> None:
    """Build every sound. Safe to call when there's no audio device."""
    global _enabled
    set_volume(volume)
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(RATE, -16, 1, 512)
        freq, size, channels = pygame.mixer.get_init()
    except pygame.error:
        _enabled = False
        return
    for name, samples in recipes().items():
        samples = _soften(samples)
        if freq != RATE:
            ratio = RATE / freq
            samples = [samples[min(len(samples) - 1, int(i * ratio))] for i in range(int(len(samples) / ratio))]
        data = array("h", (int(max(-1.0, min(1.0, s)) * 32000) for s in samples for _ in range(channels)))
        if size == 8 or size == -8:
            continue  # 8-bit output isn't worth supporting
        try:
            _sounds[name] = pygame.mixer.Sound(buffer=data.tobytes())
        except pygame.error:
            continue
    _enabled = bool(_sounds)


def set_volume(level: str) -> None:
    global _volume
    _volume = VOLUME_LEVELS.get(level, VOLUME_LEVELS["Medium"])


def play(name: str) -> None:
    if not _enabled or _volume <= 0:
        return
    snd = _sounds.get(name)
    if snd is not None:
        try:
            snd.set_volume(_volume)
            snd.play()
        except pygame.error:
            pass  # audio device went away; carry on silently
