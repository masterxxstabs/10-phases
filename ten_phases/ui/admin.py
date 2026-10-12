"""The owner's admin panel: see every hand, give anyone a card, kick guests.

Open it at any card table with F12 (or Ctrl+Shift+D). It asks for the admin
password once per run; the password itself is never stored, only a salted hash
(ten_phases/admin_key.py, set with tools/set_admin_password.py).

Changing the game only works where your copy runs the real game: solo games, and
multiplayer games you host. Guests' copies are only mirrors of the host's game.
"""

from __future__ import annotations

import hashlib
import hmac

import pygame

from .. import admin_key
from ..cards import COLORS, number, skip, wild
from . import sfx, theme
from .card_art import card_with_shadow
from .widgets import Button, TextInput

_unlocked = False          # stays unlocked until the game is closed (or LOCK is pressed)
_failures = 0
MAX_TRIES = 3
LOCKOUT = 30.0             # seconds to wait after too many wrong passwords


def check_password(password: str) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(admin_key.SALT), admin_key.ITERATIONS)
    return hmac.compare_digest(digest.hex(), admin_key.HASH)


def is_unlocked() -> bool:
    return _unlocked


def lock() -> None:
    global _unlocked
    _unlocked = False


class PasswordInput(TextInput):
    """A text box that shows dots instead of what you type."""

    def draw(self, surf):
        real = self.value
        self.value = "*" * len(real)
        try:
            super().draw(surf)
        finally:
            self.value = real


# --------------------------------------------------------------------------- per-game details


def _kind(scene) -> str:
    return {"GameScene": "phases", "GoFishScene": "fish", "BlackjackScene": "blackjack",
            "PokerScene": "poker"}.get(type(scene).__name__, "phases")


VALUES = {"phases": (1, 12), "fish": (1, 12), "blackjack": (1, 13), "poker": (2, 14)}


def player_cards(scene, i: int) -> list:
    p = scene.game.players[i]
    kind = _kind(scene)
    if kind == "blackjack":
        return [c for h in p.hands for c in h.cards]
    if kind == "poker":
        return list(p.hole)
    return list(p.hand)


def make_card(kind: str, color, value: int, special: str | None = None):
    if special == "wild":
        return wild()
    if special == "skip":
        return skip()
    if kind == "blackjack":
        from ..blackjack.engine import bj_card
        return bj_card(color, value)
    if kind == "poker":
        from ..poker.engine import poker_card
        return poker_card(color, value)
    return number(color, value)


def give_card(scene, i: int, card, slot: int = 0) -> str:
    """Put a card in player i's hand. Returns a message for the status bar (raises ValueError if it can't)."""
    g = scene.game
    p = g.players[i]
    kind = _kind(scene)
    if kind == "blackjack":
        if not p.hands:
            raise ValueError("They have no hand yet - wait for the deal.")
        turn = getattr(g, "turn", None)
        h = turn[1] if turn and turn[0] == i and turn[1] < len(p.hands) else 0
        p.hands[h].cards.append(card)
        return f"Gave {p.name} the {card.label()} (hand {h + 1})."
    if kind == "poker":
        if not p.hole:
            raise ValueError("They have no cards this hand.")
        slot = min(slot, len(p.hole) - 1)
        in_play = [c for q in g.players for c in q.hole] + list(g.board)
        if any((c.color, c.value) == (card.color, card.value) for c in in_play):
            raise ValueError(f"The {card.label()} is already in play - there's only one of each card.")
        g.deck = [c for c in g.deck if (c.color, c.value) != (card.color, card.value)]
        old = p.hole[slot]
        p.hole[slot] = card
        return f"Swapped {p.name}'s {old.label()} for the {card.label()}."
    p.hand.append(card)
    if kind == "fish" and hasattr(g, "_collect_books"):
        g._collect_books(i)   # four of a kind becomes a book right away, as in play
    return f"Gave {p.name} the {card.label()}."


# --------------------------------------------------------------------------- the panel

PANEL = pygame.Rect(40, 40, 1200, 700)


class AdminPanel:
    def __init__(self, scene):
        self.scene = scene
        self.open = False
        self.flash = ""
        self.lockout = 0.0
        self.password = PasswordInput((PANEL.centerx - 200, 330, 400, 56), max_len=40, placeholder="PASSWORD",
                                      allowed=lambda ch: ch.isprintable() and ch != " ", upper=False,
                                      on_enter=self._try_unlock)
        self.btn_unlock = Button((PANEL.centerx - 200, 404, 190, 54), "UNLOCK", self._try_unlock, "ACCENT",
                                 "OUTLINE", 20)
        self.btn_cancel = Button((PANEL.centerx + 10, 404, 190, 54), "CANCEL", self.close, size=20)
        self.btn_close = Button((PANEL.right - 150, PANEL.y + 16, 130, 44), "CLOSE", self.close, size=16)
        self.btn_lock = Button((PANEL.right - 290, PANEL.y + 16, 130, 44), "LOCK", self._lock, size=16)
        self.btn_chips = Button((PANEL.x + 20, PANEL.bottom - 64, 210, 46), "+100 CHIP BANK", self._chips, size=15)
        self.target: int | None = None
        self.color_k = 0
        self.value = 7
        self.special: str | None = None     # wild / skip for 10 Phases
        self.slot = 0                       # which hole card to swap in poker
        self.row_buttons: list[tuple[Button, Button | None]] = []
        self.picker: list[Button] = []

    # ---------------------------------------------------------------- state

    @property
    def blocking(self) -> bool:
        """Pause solo games while the panel is up (network games keep going for everyone else)."""
        s = self.scene
        return self.open and s.host is None and s.client is None

    @property
    def can_edit(self) -> bool:
        return self.scene.client is None

    def toggle(self):
        if self.open:
            self.close()
        else:
            self.open = True
            self.password.value = ""
            self.password.focused = not _unlocked
            self.flash = ""
            sfx.play("select")

    def close(self):
        self.open = False
        self.password.focused = False
        self.password.value = ""

    def _try_unlock(self):
        global _unlocked, _failures
        if self.lockout > 0:
            self.flash = f"Too many wrong tries. Wait {int(self.lockout) + 1}s."
            sfx.play("error")
            return
        if check_password(self.password.value):
            _unlocked, _failures = True, 0
            self.password.value = ""
            self.password.focused = False
            self.flash = "Unlocked. Admin tools stay open until you close the game or press LOCK."
            sfx.play("coin")
            return
        _failures += 1
        self.password.value = ""
        sfx.play("error")
        if _failures >= MAX_TRIES:
            _failures = 0
            self.lockout = LOCKOUT
            self.flash = f"Wrong password. Locked for {int(LOCKOUT)} seconds."
        else:
            self.flash = f"Wrong password ({MAX_TRIES - _failures} tries left)."

    def _lock(self):
        lock()
        self.close()
        sfx.play("deselect")

    def _chips(self):
        st = self.scene.app.settings
        st.chip_bank += 100
        st.save()
        self.flash = f"Chip Bank is now {st.chip_bank:,}."
        sfx.play("coin")

    def _changed(self):
        session = getattr(self.scene, "session", None)
        if session is not None:
            session.flush(force=True)   # guests get the new hands straight away

    def _give(self):
        if self.target is None:
            self.flash = "Pick a player with GIVE first."
            sfx.play("error")
            return
        kind = _kind(self.scene)
        card = make_card(kind, COLORS[self.color_k], self.value, self.special)
        try:
            self.flash = give_card(self.scene, self.target, card, self.slot)
        except ValueError as e:
            self.flash = str(e)
            sfx.play("error")
            return
        self._changed()
        sfx.play("draw")

    def _kick(self, i: int):
        s = self.scene
        session = getattr(s, "session", None)
        conn = next((c for c, seat in session.seat_of.items() if seat == i), None) if session else None
        if conn is None:
            self.flash = "Only guests in a game you host can be kicked."
            sfx.play("error")
            return
        name = s.game.players[i].name
        s.host.kick(conn, "The host removed you from the game.")
        self.flash = f"Kicked {name}. A computer took their seat."
        sfx.play("skip")

    # ---------------------------------------------------------------- input

    def handle(self, event) -> bool:
        """True if the panel used the event (the table should ignore it)."""
        if event.type == pygame.KEYDOWN:
            hotkey = event.key == pygame.K_F12 or (event.key == pygame.K_d and event.mod & pygame.KMOD_CTRL
                                                   and event.mod & pygame.KMOD_SHIFT)
            if hotkey:
                self.toggle()
                return True
            if self.open and event.key == pygame.K_ESCAPE and not self.password.focused:
                self.close()
                return True
        if not self.open:
            return False
        if not _unlocked:
            for w in (self.password, self.btn_unlock, self.btn_cancel):
                if w.handle(event):
                    return True
            return True
        self._layout()
        for b in [self.btn_close, self.btn_lock, self.btn_chips] + self.picker:
            if b.handle(event):
                return True
        for give, kick in self.row_buttons:
            if give.handle(event) or (kick is not None and kick.handle(event)):
                return True
        return True   # the panel covers the table: nothing gets through

    def update(self, dt: float):
        self.lockout = max(0.0, self.lockout - dt)

    # ---------------------------------------------------------------- layout

    def _rows(self) -> list[int]:
        return list(range(len(self.scene.game.players)))

    def _row_rect(self, k: int) -> pygame.Rect:
        return pygame.Rect(PANEL.x + 20, PANEL.y + 76 + k * 72, PANEL.w - 40, 64)

    def _layout(self):
        """(Re)build the buttons for the current table."""
        s = self.scene
        g = s.game
        self.row_buttons = []
        for k, i in enumerate(self._rows()):
            r = self._row_rect(k)
            give = Button((r.right - 250, r.y + 10, 116, 44), "GIVE", lambda i=i: self._pick_target(i), size=15)
            give.enabled = self.can_edit
            if self.target == i:
                give.color, give.text_color = "ACCENT", "OUTLINE"
            kick = None
            p = g.players[i]
            if s.host is not None and i != 0 and p.is_human:
                kick = Button((r.right - 126, r.y + 10, 116, 44), "KICK", lambda i=i: self._kick(i), "DANGER",
                              "TEXT", 15)
            self.row_buttons.append((give, kick))
        kind = _kind(s)
        y = PANEL.bottom - 128
        x = PANEL.x + 250
        self.picker = []
        for n, col in enumerate(COLORS):
            b = Button((x + n * 64, y, 56, 48), "", lambda n=n: self._set_color(n), size=12)
            b.color = theme.CARD_COLORS[col]
            self.picker.append(b)
        x += 4 * 64 + 10
        lo, hi = VALUES[kind]
        self.picker.append(Button((x, y, 48, 48), "-", lambda: self._set_value(-1, lo, hi), size=22))
        self.picker.append(Button((x + 132, y, 48, 48), "+", lambda: self._set_value(1, lo, hi), size=22))
        x += 196
        if kind == "phases":
            for n, sp in enumerate(("wild", "skip")):
                b = Button((x + n * 90, y, 82, 48), sp.upper(), lambda sp=sp: self._set_special(sp), size=14)
                if self.special == sp:
                    b.color, b.text_color = "ACCENT", "OUTLINE"
                self.picker.append(b)
            x += 190
        if kind == "poker":
            for n in range(2):
                b = Button((x + n * 96, y, 88, 48), f"CARD {n + 1}", lambda n=n: self._set_slot(n), size=13)
                if self.slot == n:
                    b.color, b.text_color = "ACCENT", "OUTLINE"
                self.picker.append(b)
            x += 202
        label = "SWAP IN" if kind == "poker" else "GIVE CARD"
        give = Button((PANEL.right - 230, y, 210, 48), label, self._give, "SUCCESS", "OUTLINE", 18)
        give.enabled = self.can_edit and self.target is not None
        self.picker.append(give)
        if not (lo <= self.value <= hi):
            self.value = max(lo, min(hi, self.value))

    def _pick_target(self, i: int):
        self.target = i
        self.flash = f"Pick a card below, then GIVE CARD to {self.scene.game.players[i].name}."
        sfx.play("select")

    def _set_color(self, n: int):
        self.color_k, self.special = n, None
        sfx.play("select")

    def _set_value(self, step: int, lo: int, hi: int):
        self.special = None
        self.value = lo + (self.value - lo + step) % (hi - lo + 1)
        sfx.play("select")

    def _set_special(self, sp: str):
        self.special = None if self.special == sp else sp
        sfx.play("select")

    def _set_slot(self, n: int):
        self.slot = n
        sfx.play("select")

    # ---------------------------------------------------------------- drawing

    def draw(self, surf):
        if not self.open:
            return
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, 200))
        surf.blit(shade, (0, 0))
        if not _unlocked:
            box = pygame.Rect(PANEL.centerx - 260, 200, 520, 300)
            theme.panel(surf, box, edge=theme.DANGER, edge_w=3)
            theme.logo(surf, "ADMIN", (box.centerx, box.y + 60), 44, angle=4, color="DANGER")
            theme.ptext(surf, "Enter the admin password", (box.centerx, box.y + 108), 16, theme.TEXT_DIM,
                        anchor="center")
            self.password.draw(surf)
            self.btn_unlock.enabled = self.lockout <= 0
            self.btn_unlock.draw(surf)
            self.btn_cancel.draw(surf)
            if self.flash:
                theme.ptext(surf, self.flash, (box.centerx, box.bottom - 20), 14, theme.DANGER, anchor="center")
            return
        self._layout()
        s = self.scene
        g = s.game
        theme.panel(surf, PANEL, edge=theme.DANGER, edge_w=3)
        theme.ptext(surf, "ADMIN PANEL", (PANEL.x + 24, PANEL.y + 20), 28, theme.DANGER)
        where = "SOLO GAME" if s.host is None and s.client is None else "HOSTING" if s.host else "GUEST (VIEW ONLY)"
        theme.ptext(surf, where, (PANEL.x + 250, PANEL.y + 28), 16, theme.TEXT_DIM)
        self.btn_close.draw(surf)
        self.btn_lock.draw(surf)
        for k, i in enumerate(self._rows()):
            self._draw_row(surf, k, i)
        if _kind(s) == "blackjack" and getattr(g, "dealer", None):
            r = self._row_rect(len(self._rows()))
            if r.bottom < PANEL.bottom - 140:
                theme.rounded(surf, theme.INNER, r, 10)
                theme.ptext(surf, "DEALER", (r.x + 16, r.y + 20), 18, theme.ACCENT)
                for n, c in enumerate(g.dealer):
                    img, _ = card_with_shadow(c, 34, 51)
                    surf.blit(img, (r.x + 220 + n * 38, r.y + 6))
        self._draw_picker(surf)
        self.btn_chips.draw(surf)
        if self.flash:
            theme.ptext(surf, self.flash, (PANEL.centerx, PANEL.bottom - 18), 15, theme.ACCENT, anchor="center")
        elif not self.can_edit:
            theme.ptext(surf, "You're a guest: you can look, but only the host's game can be changed.",
                        (PANEL.centerx, PANEL.bottom - 18), 15, theme.TEXT_DIM, anchor="center")

    def _draw_row(self, surf, k: int, i: int):
        s = self.scene
        p = s.game.players[i]
        r = self._row_rect(k)
        theme.rounded(surf, theme.PANEL_HOVER if self.target == i else theme.INNER, r, 10)
        theme.face(surf, (r.x + 30, r.centery), 20, i)
        theme.ptext(surf, p.name if i or p.name == "YOU" else f"{p.name} (YOU)", (r.x + 58, r.y + 8), 18)
        role = "YOU" if i == 0 else "GUEST" if p.is_human else (p.difficulty or "COMPUTER").upper()
        cards = player_cards(s, i)
        theme.ptext(surf, f"{role}  -  {len(cards)} CARD{'S' if len(cards) != 1 else ''}", (r.x + 58, r.y + 36),
                    12, theme.TEXT_DIM)
        area = pygame.Rect(r.x + 220, r.y + 6, r.w - 220 - 270, 52)
        step = min(38, (area.w - 34) / max(1, len(cards) - 1)) if len(cards) > 1 else 0
        for n, c in enumerate(cards):
            known = c.color is not None or c.kind.value != "number"
            if getattr(c, "id", 0) < 0 or not known:
                img, _ = card_with_shadow(None, 34, 51)    # a guest's mirror doesn't know other hands
            else:
                img, _ = card_with_shadow(c, 34, 51)
            surf.blit(img, (area.x + n * step, area.y))
        give, kick = self.row_buttons[k]
        give.draw(surf)
        if kick:
            kick.draw(surf)

    def _draw_picker(self, surf):
        kind = _kind(self.scene)
        y = PANEL.bottom - 128
        theme.ptext(surf, "CARD TO GIVE", (PANEL.x + 24, y + 4), 16, theme.ACCENT)
        target = self.scene.game.players[self.target].name if self.target is not None else "nobody yet"
        theme.ptext(surf, f"TO: {target}", (PANEL.x + 24, y + 28), 13, theme.TEXT_DIM)
        for n, b in enumerate(self.picker[:4]):
            b.draw(surf)
            if n == self.color_k and self.special is None:
                pygame.draw.rect(surf, theme.CARD_WHITE, b.rect.inflate(6, 6), 3, border_radius=12)
        for b in self.picker[4:]:
            b.draw(surf)
        vx = self.picker[4].rect.right + 6
        box = pygame.Rect(vx, y, 72, 48)
        theme.rounded(surf, theme.INNER, box, 8)
        label = make_card(kind, COLORS[self.color_k], self.value, self.special)
        text = self.special.upper() if self.special else getattr(label, "rank_label", None) or str(self.value)
        theme.ptext(surf, text, box.center, 22 if not self.special else 14, theme.ACCENT, anchor="center")
        img, _ = card_with_shadow(label, 46, 69)
        surf.blit(img, (PANEL.right - 290, y - 12))
