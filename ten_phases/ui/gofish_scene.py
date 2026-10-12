"""The Go Fish table: same handheld look as 10 Phases.

  top screen     opponents with their cards and books, plus speech bubbles
  bottom screen  activity log, the pond, the board of all 12 books, your hand
"""

from __future__ import annotations

import math
import random

import pygame

from ..cards import COLORS, number
from ..gofish.ai import GoFishAI
from ..gofish.engine import VALUES, FishPlayer, GoFishGame, RuleError
from ..names import pick_ai_names
from ..settings import SPEED_DELAYS
from . import sfx, theme
from .card_art import card_with_shadow
from .admin import AdminPanel
from .table_skins import TableSkins
from .game_scene import DIFF_COLORS, FlyingCard
from .menus import Scene, _wrap, backdrop, status_bar
from .widgets import Button

HUMAN = 0
SPLIT_Y = 222
OPP_Y, OPP_H = 14, 194
LOG_BOX = pygame.Rect(20, 238, 250, 282)
POND = pygame.Rect(290, 238, 372, 282)
BOARD = pygame.Rect(682, 238, 578, 282)
MY_BOX = pygame.Rect(20, 532, 1240, 232)
HAND_AREA = pygame.Rect(36, 590, 990, 170)
HAND_W, HAND_H = 88, 132
HAND_Y = 622
CHIPS_PER_BOOK = 5


def plural(v: int) -> str:
    return f"{v}s"


class Bubble:
    def __init__(self, player: int, text: str, ttl: float = 1.8, color=None):
        self.player, self.text, self.ttl, self.color = player, text, ttl, color


class GoFishScene(Scene):
    """Local by default; pass `host` + `session` to host a network game, or `client` to join one."""

    def __init__(self, app, host=None, session=None, client=None):
        super().__init__(app)
        s = app.settings
        self.host, self.session, self.client = host, session, client
        if session is not None:
            self.game, self.ais = session.game, session.ais
        elif client is not None:
            self.game, self.ais = client.game, {}
        else:
            diffs = s.opponent_difficulties()
            names = pick_ai_names(len(diffs), taken=["YOU", s.player_name])
            players = [FishPlayer("YOU", is_human=True)]
            players += [FishPlayer(n, difficulty=d) for n, d in zip(names, diffs)]
            self.game = GoFishGame(players)
            self.ais = {i + 1: GoFishAI(d) for i, d in enumerate(diffs)}
        self.skins = TableSkins(self)
        self.admin = AdminPanel(self)
        self.hint_ai = GoFishAI("Expert", random.Random(0))
        self.delay = SPEED_DELAYS[s.ai_speed]

        self.selected_value: int | None = None
        self.anims: list[FlyingCard] = []
        self.bubbles: list[Bubble] = []
        self.log: list[tuple[str, tuple]] = []
        self.flash: tuple[str, float] | None = None
        self.splash: tuple[str, str, float, float] | None = ("GO FISH!", "MAKE BOOKS OF ALL FOUR COLORS", 1.8, 1.8)
        self.overlay: str | None = None
        self._pending_overlay = False
        self.ai_timer = 1.0
        self.card_rects: dict[int, pygame.Rect] = {}
        self.new_ids: set[int] = set()
        self.asked: dict[int, list[str]] = {}     # public memory for the hover card
        self._banked: int | None = None
        self.btn_hint = Button((1046, 560, 200, 52), "HINT", self.do_hint, size=20)
        self.btn_menu = Button((1046, 624, 200, 46), "MENU", lambda: self._set_overlay("pause"), size=18)
        self.overlay_buttons: list[Button] = []
        self._consume_events()
        sfx.play("phase")

    # ================================================================== helpers

    @property
    def me(self) -> FishPlayer:
        return self.game.players[HUMAN]

    @property
    def networked(self) -> bool:
        return self.host is not None or self.client is not None

    @property
    def busy(self) -> bool:
        return (bool(self.anims) or self.splash is not None or self.overlay is not None
                or getattr(self.game, "pending", False))

    @property
    def flow_blocked(self) -> bool:
        """Computers wait during animations; in network games the pause menu doesn't stop play."""
        if self.admin.blocking:
            return True
        if self.anims or self.splash is not None:
            return True
        return self.overlay is not None and not (self.overlay == "pause" and self.networked)

    def role(self, i: int):
        p = self.game.players[i]
        return (p.difficulty.upper(), DIFF_COLORS[p.difficulty]) if p.difficulty else ("PLAYER", theme.CARD_WHITE)

    @property
    def my_turn(self) -> bool:
        return self.game.current == HUMAN and not self.game.game_over and not self.busy

    def name(self, i: int) -> str:
        return "YOU" if i == HUMAN else self.game.players[i].name

    def say(self, msg: str, color=theme.TEXT):
        self.log.append((msg, color))
        del self.log[:-6]

    def error(self, msg: str):
        self.flash = (msg, 2.6)
        sfx.play("error")

    def bubble(self, i: int, text: str, ttl: float = 1.8, color=None):
        self.bubbles = [b for b in self.bubbles if b.player != i]
        self.bubbles.append(Bubble(i, text, ttl, color))

    def opponents(self) -> list[int]:
        return list(range(1, len(self.game.players)))

    def panel_rect(self, i: int) -> pygame.Rect:
        if i == HUMAN:
            return MY_BOX
        opps = self.opponents()
        n, gap = len(opps), 16
        w = min(300, (1240 - (n - 1) * gap) // n)
        x0 = (theme.WIDTH - (n * w + (n - 1) * gap)) // 2
        return pygame.Rect(x0 + opps.index(i) * (w + gap), OPP_Y, w, OPP_H)

    def anchor(self, i: int) -> pygame.Rect:
        if i == HUMAN:
            return pygame.Rect(HAND_AREA.centerx - HAND_W // 2, HAND_Y, HAND_W, HAND_H)
        r = self.panel_rect(i)
        return pygame.Rect(r.right - 70, r.y + 10, 40, 60)

    def pond_rect(self) -> pygame.Rect:
        return pygame.Rect(POND.centerx - 40, POND.centery - 50, 80, 120)

    def book_slot(self, value: int) -> pygame.Rect:
        k = value - 1
        col, row = k % 6, k // 6
        return pygame.Rect(BOARD.x + 18 + col * 92, BOARD.y + 62 + row * 106, 84, 98)

    def sorted_hand(self):
        return sorted(self.me.hand, key=lambda c: (c.value, COLORS.index(c.color)))

    def hand_layout(self) -> dict[int, pygame.Rect]:
        cards = self.sorted_hand()
        n = len(cards)
        if not n:
            return {}
        step = min(HAND_W + 8, (HAND_AREA.w - HAND_W) / max(1, n - 1))
        x0 = HAND_AREA.x + (HAND_AREA.w - (HAND_W + step * (n - 1))) / 2
        out = {}
        for k, c in enumerate(cards):
            lift = 24 if c.value == self.selected_value else 0
            out[c.id] = pygame.Rect(int(x0 + k * step), HAND_Y - lift, HAND_W, HAND_H)
        return out

    # ================================================================== events -> animation

    def _consume_events(self, origin: dict | None = None):
        origin = origin or {}
        g = self.game
        hand = self.hand_layout()
        stagger = 0.0
        for ev in g.pop_events():
            k = ev.kind
            if k == "ask":
                who = self.name(ev.target).title() if ev.target != HUMAN else "you"
                ask = f"GOT ANY {plural(ev.value)}?" if ev.target == HUMAN else \
                    f"GOT ANY {plural(ev.value)}, {self.name(ev.target)}?"
                self.bubble(ev.player, ask)
                self.say(f"{self.name(ev.player).title()} asked {who} for {plural(ev.value)}", theme.TEXT_DIM)
                sfx.play("click")
            elif k == "give":
                self.bubble(ev.target, f"HERE: {len(ev.cards)} x {ev.value}", color=theme.SUCCESS)
                self.say(f"{self.name(ev.target).title()} handed over {len(ev.cards)} x {ev.value}", theme.SUCCESS)
                src = "you" if ev.target == HUMAN else self.name(ev.target).title()
                self.asked.setdefault(ev.player, []).append(f"Got {plural(ev.value)} from {src}")
                for c in ev.cards:
                    start = origin.get(c.id, self.anchor(ev.target))
                    end = hand.get(c.id, self.anchor(ev.player))
                    self.anims.append(FlyingCard(c, start, end, 0.36, stagger, hide_id=c.id,
                                                 face=self.skins.face(ev.target)))
                    stagger += 0.06
                    if ev.player == HUMAN:
                        self.new_ids.add(c.id)
                sfx.play("draw")
            elif k == "gofish":
                self.bubble(ev.target, "GO FISH!", color=theme.INFO)
                self.say(f"{self.name(ev.target).title()}: Go fish!", theme.INFO)
                src = "you" if ev.target == HUMAN else self.name(ev.target).title()
                self.asked.setdefault(ev.player, []).append(f"Asked {src} for {plural(ev.value)}: go fish")
                sfx.play("fish")
            elif k == "draw":
                c = ev.cards[0]
                show = ev.player == HUMAN or ev.lucky
                end = hand.get(c.id, self.anchor(ev.player)) if ev.player == HUMAN else self.anchor(ev.player)
                sk = self.skins.seat(ev.player)
                self.anims.append(FlyingCard(c if show else None, self.pond_rect(), end, 0.4, stagger,
                                             hide_id=c.id if ev.player == HUMAN else None, face=sk[0], back=sk[1]))
                stagger += 0.08
                if ev.player == HUMAN:
                    self.new_ids.add(c.id)
                if ev.lucky:
                    self.bubble(ev.player, f"LUCKY! A {ev.value}!", color=theme.ACCENT)
                    self.say(f"{self.name(ev.player).title()} fished the {ev.value} they wanted!", theme.ACCENT)
                    sfx.play("coin")
                elif ev.player == HUMAN:
                    self.say(f"You fished a {c.label()}", theme.TEXT_DIM)
            elif k == "book":
                for n, c in enumerate(ev.cards):
                    start = origin.get(c.id, hand.get(c.id, self.anchor(ev.player)))
                    self.anims.append(FlyingCard(c, start, self.book_slot(ev.value), 0.42, stagger + 0.05 * n,
                                                 face=self.skins.face(ev.player)))
                stagger += 0.25
                who = "You" if ev.player == HUMAN else self.name(ev.player).title()
                self.say(f"{who} made a book of {plural(ev.value)}!", theme.SUCCESS)
                self.bubble(ev.player, f"BOOK OF {plural(ev.value)}!", color=theme.SUCCESS)
                sfx.play("lay")
                if ev.player == HUMAN:
                    self.splash = (f"BOOK OF {plural(ev.value)}!", "ALL FOUR COLORS", 1.1, 1.1)
            elif k == "turn":
                if ev.player == HUMAN:
                    sfx.play("turn")
                    self.selected_value = self.selected_value if self.selected_value in self.me.values() else None
                else:
                    self.new_ids.clear()
            elif k == "game_over":
                self._pending_overlay = True

    # ================================================================== actions

    def ask(self, target: int):
        if not self.my_turn:
            return
        if self.selected_value is None:
            self.error("Pick a card from your hand first, then click who to ask.")
            return
        origin = dict(self.card_rects)
        try:
            self.game.ask(HUMAN, target, self.selected_value)
        except RuleError as e:
            self.error(str(e))
            return
        self.new_ids.clear()
        self._consume_events(origin)
        if self.selected_value not in self.me.values():
            self.selected_value = None
        self.ai_timer = self.delay + 0.6

    def do_hint(self):
        if not self.my_turn:
            return
        target, value = self.hint_ai.choose_ask(self.game, HUMAN)
        self.selected_value = value
        self.flash = (f"Hint: ask {self.name(target).title()} for {plural(value)}.", 2.6)
        sfx.play("turn")

    def run_ai(self):
        g = self.game
        i = g.current
        target, value = self.ais[i].choose_ask(g, i)
        g.ask(i, target, value)
        self._consume_events()
        self.ai_timer = self.delay * 1.4 + 0.5

    # ================================================================== network

    def _pump_network(self):
        if self.host is not None:
            self.host.pump()
            while self.session.notices:
                self.say(self.session.notices.pop(0), theme.DANGER)
                sfx.play("skip")
        if self.client is not None:
            for msg in self.client.poll():
                t = msg["t"]
                if t == "error":
                    self.error(msg.get("msg", "That move wasn't allowed."))
                elif t == "notice":
                    self.say(msg.get("msg", ""), theme.DANGER)
                    sfx.play("skip")
                elif t == "to_lobby":
                    self.client.game = None
                    from .multiplayer import GuestLobbyScene
                    self.app.go(GuestLobbyScene(self.app, self.client))
                    return
            if self.client.status in ("closed", "failed") and self.overlay != "disconnected":
                self._set_overlay("disconnected")

    def leave_network(self):
        if self.host is not None:
            self.host.close()
        if self.client is not None:
            self.client.leave()

    def to_lobby(self):
        from .multiplayer import HostLobbyScene
        self.host.back_to_lobby()
        self.app.go(HostLobbyScene(self.app, self.host))

    # ================================================================== overlays

    def _set_overlay(self, kind: str | None):
        self.overlay = kind
        self._pending_overlay = False
        cx = theme.WIDTH // 2
        primary = dict(color="ACCENT", text_color="OUTLINE")
        if kind == "game":
            won = HUMAN in self.game.winners()
            sfx.play("game_win" if won else "game_lose")
            if self._banked is None:
                self._banked = len(self.me.books) * CHIPS_PER_BOOK
                self.app.settings.chip_bank += self._banked
                self.app.settings.save()
            if self.host is not None:
                again = Button((cx - 290, 650, 270, 58), "BACK TO LOBBY", self.to_lobby, size=20, **primary)
            elif self.client is not None:
                again = Button((cx - 290, 650, 270, 58), "WAIT FOR HOST", lambda: None, size=18)
                again.enabled = False
            else:
                again = Button((cx - 290, 650, 270, 58), "PLAY AGAIN", lambda: self.app.go(GoFishScene(self.app)),
                               size=22, **primary)
            self.overlay_buttons = [again, Button((cx + 20, 650, 270, 58), "MAIN MENU", self.to_menu, size=22)]
        elif kind == "disconnected":
            sfx.play("error")
            self.overlay_buttons = [Button((cx - 140, 470, 280, 58), "MAIN MENU", self.to_menu, size=22, **primary)]
        elif kind == "pause":
            resume = lambda: self._set_overlay(None)  # noqa: E731
            if self.host is not None:
                options = [("RESUME", resume), ("END GAME", self.to_menu)]
            elif self.client is not None:
                options = [("RESUME", resume), ("CUSTOMIZE", self.customize), ("LEAVE GAME", self.to_menu)]
            else:
                options = [("RESUME", resume), ("CUSTOMIZE", self.customize),
                           ("RESTART", lambda: self.app.go(GoFishScene(self.app))), ("MAIN MENU", self.to_menu)]
            self.overlay_buttons = [Button((cx - 140, 300 + k * 68, 280, 56), label, fn, size=22 if k == 0 else 20,
                                           **(primary if k == 0 else {})) for k, (label, fn) in enumerate(options)]
        else:
            self.overlay_buttons = []

    def customize(self):
        from .customize import CustomizeScene
        self.app.go(CustomizeScene(self.app, back=lambda: self.app.go(self)))

    def to_menu(self):
        self.leave_network()
        from .menus import MenuScene
        self.app.go(MenuScene(self.app))

    # ================================================================== input

    def handle(self, event):
        if self.admin.handle(event):
            return
        if self.overlay:
            for b in self.overlay_buttons:
                if b.handle(event):
                    return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.overlay == "pause":
                self._set_overlay(None)
            return
        if self.splash and event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
            self.splash = None
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._set_overlay("pause")
            return
        for b in (self.btn_hint, self.btn_menu):
            if b.handle(event):
                return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        for cid, rect in reversed(list(self.card_rects.items())):
            if rect.collidepoint(event.pos):
                card = next((c for c in self.me.hand if c.id == cid), None)
                if card is None:   # a stale click on a card that just left the hand
                    return
                if self.selected_value == card.value:
                    self.selected_value = None
                    sfx.play("deselect")
                else:
                    self.selected_value = card.value
                    sfx.play("select")
                return
        for i in self.opponents():
            if self.panel_rect(i).collidepoint(event.pos):
                self.ask(i)
                return

    # ================================================================== update

    def update(self, dt: float):
        super().update(dt)
        self.admin.update(dt)
        self._pump_network()
        if self.game.events:
            self._consume_events()
        for a in self.anims:
            a.t += dt
        self.anims = [a for a in self.anims if not a.done]
        for b in self.bubbles:
            b.ttl -= dt
        self.bubbles = [b for b in self.bubbles if b.ttl > 0]
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None
        if self.splash:
            t, s, left, total = self.splash
            self.splash = (t, s, left - dt, total) if left > dt else None
        if self._pending_overlay and not self.anims and not self.splash:
            self._set_overlay("game")
            return
        g = self.game
        if self.flow_blocked or g.game_over or g.current not in self.ais:
            return
        self.ai_timer -= dt
        if self.ai_timer <= 0:
            self.run_ai()

    # ================================================================== drawing

    def draw(self, surf):
        backdrop(surf, self.clock, SPLIT_Y)
        hidden = {a.hide_id for a in self.anims if a.hide_id is not None}
        for i in self.opponents():
            self._draw_opponent(surf, i)
        self._draw_log(surf)
        self._draw_pond(surf)
        self._draw_board(surf)
        self._draw_my_box(surf, hidden)
        for a in self.anims:
            a.draw(surf)
        self._draw_bubbles(surf)
        if not self.overlay and not self.splash:
            mouse = pygame.mouse.get_pos()
            for i in self.opponents():
                if self.panel_rect(i).collidepoint(mouse):
                    self._draw_info(surf, i)
                    break
        status_bar(surf, self.flash[0] if self.flash else self._status())
        if self.splash:
            self._draw_splash(surf)
        if self.overlay:
            self._draw_overlay(surf)
        self.admin.draw(surf)

    def _status(self) -> str:
        g = self.game
        if g.game_over:
            return "All 12 books are made!"
        if g.current != HUMAN:
            return "Wait until it is your turn."
        if self.selected_value is None:
            return "Pick a card, then click a player to ask them for that number."
        return f"Now click a player to ask for {plural(self.selected_value)}."

    def _chip(self, surf, label, pos, color, fg="OUTLINE", size=11):
        img = theme.pixel_surface(label, size, fg, None)
        r = pygame.Rect(pos[0], pos[1], img.get_width() + 12, img.get_height() + 4)
        theme.rounded(surf, theme.OUTLINE, r.move(0, 2), r.h // 2)
        theme.rounded(surf, color, r, r.h // 2)
        surf.blit(img, img.get_rect(center=r.center))
        return r

    def _book_badge(self, surf, center, value: int, size: int = 30, seat: int | None = None):
        """A little fan of the four colours of one number, in the skin of whoever made the book."""
        face = self.skins.face(seat)
        for k, c in enumerate(COLORS):
            img, _ = card_with_shadow(number(c, value), size, int(size * 1.5), face=face)
            surf.blit(img, img.get_rect(center=(center[0] - 9 + k * 6, center[1] - 3 + k * 2)))

    def _draw_opponent(self, surf, i: int):
        g = self.game
        p = g.players[i]
        r = self.panel_rect(i)
        active = g.current == i and not g.game_over
        can_ask = self.my_turn and self.selected_value is not None and p.hand
        hover = can_ask and r.collidepoint(pygame.mouse.get_pos())
        edge = theme.ACCENT if active else (theme.SUCCESS if can_ask else theme.PANEL_EDGE)
        theme.panel(surf, r, theme.PANEL_HOVER if hover else theme.PANEL, edge, edge_w=3 if active or hover else 2)
        bob = math.sin(self.clock * 6) * 2 if active else 0
        theme.face(surf, (r.x + 30, int(r.y + 30 + bob)), 22, i)
        theme.ptext(surf, p.name, (r.x + 60, r.y + 8), 20)
        label, color = self.role(i)
        self._chip(surf, label, (r.x + 60, r.y + 34), color)
        cnt = theme.ptext(surf, str(len(p.hand)), (r.right - 12, r.y + 8), 18, anchor="topright")
        back, _ = card_with_shadow(None, 18, 27, back=self.skins.back(i))
        for k in range(min(3, len(p.hand))):
            surf.blit(back, (cnt.x - 26 - k * 7, r.y + 6 + k))
        inner = pygame.Rect(r.x + 8, r.y + 60, r.w - 16, r.h - 66)
        theme.rounded(surf, theme.INNER, inner, 8)
        theme.ptext(surf, f"BOOKS {len(p.books)}", (inner.x + 10, inner.y + 6), 16, theme.ACCENT)
        if hover:
            theme.ptext(surf, f"ASK FOR {plural(self.selected_value)}!", (inner.right - 10, inner.y + 6), 14,
                        theme.SUCCESS, anchor="topright")
        per_row = max(1, (inner.w - 20) // 42)
        for k, v in enumerate(p.books):
            cx = inner.x + 28 + (k % per_row) * 42
            cy = inner.y + 60 + (k // per_row) * 52
            self._book_badge(surf, (cx, cy), v, 24, i)
        if not p.books:
            theme.ptext(surf, "NO BOOKS YET", inner.move(0, 12).center, 14, theme.TEXT_FAINT, anchor="center")

    def _draw_log(self, surf):
        theme.panel(surf, LOG_BOX)
        theme.ptext(surf, "GO FISH", (LOG_BOX.x + 14, LOG_BOX.y + 10), 18, theme.ACCENT)
        lines = []
        for msg, color in self.log[-6:]:
            for chunk in _wrap(msg, 13, LOG_BOX.w - 28):
                lines.append((chunk, color))
        y = LOG_BOX.y + 40
        for chunk, color in lines[-12:]:
            theme.text(surf, chunk, (LOG_BOX.x + 14, y), 13, color, bold=False)
            y += 19

    def _draw_pond(self, surf):
        water = POND.inflate(-10, -40)
        pygame.draw.ellipse(surf, theme.OUTLINE, water.move(0, 6))
        pygame.draw.ellipse(surf, (40, 150, 230), water)
        pygame.draw.ellipse(surf, (90, 190, 250), water.inflate(-30, -30), 4)
        for k in range(3):
            y = water.y + 40 + k * 60 + math.sin(self.clock * 2 + k) * 4
            pygame.draw.arc(surf, (160, 220, 255), (water.x + 60 + k * 50, y, 60, 18), 0.2, 2.9, 3)
        n = len(self.game.pond)
        rng = random.Random(3)
        for k in range(min(n, 9)):
            img, _ = card_with_shadow(None, 56, 84)
            img = pygame.transform.rotate(img, rng.randint(-35, 35))
            pos = (POND.centerx + rng.randint(-110, 110), POND.centery + rng.randint(-50, 40))
            surf.blit(img, img.get_rect(center=pos))
        theme.ptext(surf, f"POND {n}", (POND.centerx, POND.bottom - 16), 18, anchor="center")
        if not n:
            theme.ptext(surf, "EMPTY!", POND.center, 22, theme.TEXT_DIM, anchor="center")

    def _draw_board(self, surf):
        g = self.game
        theme.panel(surf, BOARD)
        theme.ptext(surf, "BOOKS", (BOARD.x + 16, BOARD.y + 12), 22, theme.ACCENT)
        theme.ptext(surf, f"YOU {len(self.me.books)}   -   {g.books_made()}/12 MADE", (BOARD.right - 16, BOARD.y + 16),
                    16, theme.TEXT_DIM, anchor="topright")
        owner = {v: i for i, p in enumerate(g.players) for v in p.books}
        animating = {a.end.topleft for a in self.anims}
        for v in VALUES:
            slot = self.book_slot(v)
            mine = owner.get(v) == HUMAN
            theme.rounded(surf, theme.PANEL_HOVER if mine else theme.INNER, slot, 8)
            if v in owner and slot.topleft not in animating:
                self._book_badge(surf, (slot.centerx, slot.centery - 6), v, 34, owner[v])
                who = owner[v]
                theme.face(surf, (slot.right - 14, slot.bottom - 14), 11, who)
                if mine:
                    theme.rounded(surf, theme.ACCENT, slot, 8, 3)
            else:
                theme.rounded(surf, theme.PANEL_LIGHT, slot, 8, 2)
                theme.ptext(surf, str(v), slot.center, 30, theme.PANEL_LIGHT, None, anchor="center")
                have = self.me.count(v)
                if have:
                    theme.ptext(surf, f"YOU {have}/4", (slot.centerx, slot.bottom - 12), 12, theme.TEXT, anchor="center")

    def _draw_my_box(self, surf, hidden):
        g = self.game
        active = g.current == HUMAN and not g.game_over
        theme.panel(surf, MY_BOX, edge=theme.ACCENT if active else theme.PANEL_EDGE, edge_w=3 if active else 2)
        bob = math.sin(self.clock * 6) * 2 if active else 0
        theme.face(surf, (MY_BOX.x + 34, int(MY_BOX.y + 30 + bob)), 24, HUMAN)
        theme.ptext(surf, "YOU", (MY_BOX.x + 68, MY_BOX.y + 10), 22)
        x = MY_BOX.x + 140
        theme.mini_card_icon(surf, (x, MY_BOX.y + 15))
        theme.ptext(surf, str(len(self.me.hand)), (x + 20, MY_BOX.y + 12), 18)
        theme.ptext(surf, f"BOOKS {len(self.me.books)}", (x + 70, MY_BOX.y + 12), 18, theme.ACCENT)
        if active:
            self._chip(surf, "YOUR TURN!", (x + 200, MY_BOX.y + 12), theme.ACCENT, size=14)
        layout = self.hand_layout()
        mouse = pygame.mouse.get_pos()
        hover = next((cid for cid, r in reversed(list(layout.items())) if r.collidepoint(mouse)), None)
        self.card_rects = {}
        for c in self.sorted_hand():
            rect = layout[c.id].copy()
            if c.id == hover and c.value != self.selected_value:
                rect.y -= 10
            self.card_rects[c.id] = rect
            if c.id in hidden:
                continue
            img, _ = card_with_shadow(c, rect.w, rect.h, lift=12 if c.value == self.selected_value else 0)
            surf.blit(img, rect)
            if c.value == self.selected_value:
                theme.rounded(surf, theme.ACCENT, rect.inflate(6, 6), 14, 4)
            elif c.id in self.new_ids:
                theme.rounded(surf, theme.INFO, rect.inflate(6, 6), 14, 3)
        if not self.me.hand:
            theme.ptext(surf, "NO CARDS - YOU'LL FISH ONE ON YOUR TURN", HAND_AREA.center, 18, theme.TEXT_DIM,
                        anchor="center")
        self.btn_hint.visible = self.app.settings.hints
        self.btn_hint.enabled = self.my_turn
        for b in (self.btn_hint, self.btn_menu):
            b.draw(surf)

    def _draw_bubbles(self, surf):
        for b in self.bubbles:
            img = theme.pixel_surface(b.text, 16, b.color or theme.OUTLINE, None)
            box = pygame.Rect(0, 0, img.get_width() + 24, img.get_height() + 14)
            if b.player == HUMAN:
                box.midbottom = (MY_BOX.x + 300, MY_BOX.y - 6)
                tail = (box.x + 30, box.bottom + 10)
            else:
                r = self.panel_rect(b.player)
                box.midtop = (r.centerx, r.bottom + 12)
                tail = (r.centerx, r.bottom + 2)
            box.clamp_ip(pygame.Rect(8, 0, theme.WIDTH - 16, theme.HEIGHT))
            alpha = min(1.0, b.ttl / 0.25)
            layer = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
            tip = [(tail[0] - 8, box.top if b.player != HUMAN else box.bottom - 2),
                   (tail[0] + 8, box.top if b.player != HUMAN else box.bottom - 2), tail]
            pygame.draw.polygon(layer, theme.OUTLINE, [(x, y + 3) for x, y in tip])
            theme.rounded(layer, theme.OUTLINE, box.move(0, 3), 12)
            theme.rounded(layer, theme.CARD_WHITE, box, 12)
            pygame.draw.polygon(layer, theme.CARD_WHITE, tip)
            layer.blit(img, img.get_rect(center=box.center))
            layer.set_alpha(int(255 * alpha))
            surf.blit(layer, (0, 0))

    def _draw_info(self, surf, i: int):
        """Hover card: books, cards in hand, and what they've asked for (everyone heard it)."""
        p = self.game.players[i]
        box = self.panel_rect(i)
        notes = self.asked.get(i, [])[-5:] if self.app.settings.hints else []
        w = 520
        h = 170 + (28 + 20 * len(notes) if notes else 34)
        x = max(10, min(theme.WIDTH - w - 10, box.centerx - w // 2))
        rect = pygame.Rect(x, box.bottom + 8, w, h)
        theme.panel(surf, rect, edge=theme.ACCENT, edge_w=3)
        theme.face(surf, (rect.x + 38, rect.y + 38), 24, i)
        theme.ptext(surf, p.name, (rect.x + 72, rect.y + 12), 24)
        self._chip(surf, self.role(i)[0], (rect.x + 72, rect.y + 44), self.role(i)[1], size=12)
        theme.ptext(surf, f"{len(p.books)} BOOKS", (rect.right - 18, rect.y + 12), 26, theme.ACCENT, anchor="topright")
        theme.ptext(surf, f"{len(p.hand)} CARD{'S' if len(p.hand) != 1 else ''} IN HAND", (rect.right - 18, rect.y + 46), 14, theme.TEXT_DIM,
                    anchor="topright")
        y = rect.y + 80
        if p.books:
            for k, v in enumerate(p.books):
                self._book_badge(surf, (rect.x + 40 + k * 42, y + 36), v, 28, i)
        else:
            theme.ptext(surf, "No books yet", (rect.x + 20, y + 30), 16, theme.TEXT_FAINT)
        y += 84
        if notes:
            theme.ptext(surf, "WHAT THEY'VE ASKED FOR", (rect.x + 18, y), 14, theme.ACCENT)
            for n, line in enumerate(reversed(notes)):
                theme.text(surf, line, (rect.x + 24, y + 22 + n * 20), 14, theme.TEXT if n == 0 else theme.TEXT_DIM,
                           bold=False)
        elif not self.app.settings.hints:
            theme.ptext(surf, "Turn on Hints to see what they've asked for", (rect.x + 18, y + 4), 13, theme.TEXT_FAINT)

    def _draw_splash(self, surf):
        title, sub, t, total = self.splash
        k = min(1.0, (total - t) / 0.25, t / 0.3)
        band = pygame.Rect(0, 300, theme.WIDTH, 170)
        shade = pygame.Surface(band.size, pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, int(200 * k)))
        surf.blit(shade, band)
        theme.logo(surf, title, (theme.WIDTH // 2 + int((1 - k) * -300), band.y + 70), 70, angle=6)
        theme.ptext(surf, sub, (theme.WIDTH // 2, band.bottom - 26), 20, anchor="center")

    def _draw_overlay(self, surf):
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, 190))
        surf.blit(shade, (0, 0))
        cx = theme.WIDTH // 2
        g = self.game
        if self.overlay == "pause":
            theme.panel(surf, (cx - 200, 200, 400, 120 + 68 * len(self.overlay_buttons)))
            theme.logo(surf, "PAUSED", (cx, 250), 40, angle=4)
            if self.networked:
                theme.ptext(surf, "The game keeps going while you're here.", (cx, 290), 12, theme.TEXT_DIM,
                            anchor="center")
        elif self.overlay == "disconnected":
            theme.panel(surf, (cx - 330, 250, 660, 300))
            theme.logo(surf, "DISCONNECTED", (cx, 320), 44, angle=4)
            reason = (self.client.error if self.client else None) or "The connection was lost."
            theme.ptext(surf, reason, (cx, 400), 16, anchor="center")
        else:
            panel = pygame.Rect(cx - 400, 90, 800, 640)
            theme.panel(surf, panel)
            winners = g.winners()
            if len(winners) > 1:
                title = "IT'S A TIE!" if HUMAN not in winners else "YOU TIED FOR FIRST!"
            else:
                title = "YOU WIN!" if winners[0] == HUMAN else f"{g.players[winners[0]].name} WINS!"
            theme.logo(surf, title, (cx, 150), 52, angle=4)
            bank = f"+{self._banked or 0} CHIPS BANKED!   BANK: {self.app.settings.chip_bank:,}"
            r_ = theme.ptext(surf, bank, (cx + 12, 206), 18, theme.ACCENT, anchor="center")
            theme.chip(surf, (r_.x - 16, r_.centery + 2), 10, theme.ACCENT)
            for k, i in enumerate(g.standings()):
                p = g.players[i]
                row = pygame.Rect(panel.x + 30, 240 + k * 64, panel.w - 60, 56)
                theme.rounded(surf, theme.PANEL_HOVER if i == HUMAN else theme.INNER, row, 10)
                theme.face(surf, (row.x + 34, row.centery), 20, i)
                theme.ptext(surf, self.name(i), (row.x + 66, row.centery), 20, anchor="midleft")
                theme.ptext(surf, f"{len(p.books)}", (row.x + 230, row.centery), 26, theme.ACCENT, anchor="center")
                for n, v in enumerate(p.books):
                    self._book_badge(surf, (row.x + 290 + n * 36, row.centery + 2), v, 22, i)
        for b in self.overlay_buttons:
            b.draw(surf)
