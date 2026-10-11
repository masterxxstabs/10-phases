"""The main table, laid out like a two-screen handheld:

  top screen     opponents, each in a box with their cards, chips, phase and groups
  bottom screen  pot, piles with turn arrows, your phase board, your hand,
                 and a black status bar
"""

from __future__ import annotations

import math
import random

import pygame

from ..ai import AIPlayer, plan_phase
from ..cards import Card
from ..game import Game, Player, RuleError
from ..phases import NUM_PHASES, PHASES, GroupType, describe_phase
from ..settings import SPEED_DELAYS
from . import sfx, theme
from .card_art import card_with_shadow
from .menus import Scene, _wrap, backdrop, status_bar
from .widgets import Button

HUMAN = 0
AI_NAMES = ["ZACH", "RACHEL", "RYAN", "MAYA", "OTTO"]
DIFF_COLORS = {"Easy": theme.SUCCESS, "Medium": theme.INFO, "Hard": theme.ORANGE, "Expert": theme.DANGER}

# Layout
SPLIT_Y = 222
OPP_Y, OPP_H = 14, 194
POT_BOX = pygame.Rect(20, 238, 250, 120)
LOG_BOX = pygame.Rect(20, 370, 250, 150)
DECK_RECT = pygame.Rect(352, 256, 104, 156)
DISCARD_RECT = pygame.Rect(490, 256, 104, 156)
BOARD = pygame.Rect(682, 238, 578, 282)
MY_BOX = pygame.Rect(20, 532, 1240, 232)
HAND_AREA = pygame.Rect(36, 590, 990, 170)
HAND_W, HAND_H = 88, 132
HAND_Y = 622

REQ_LABEL = {GroupType.SET: "SET OF {}", GroupType.RUN: "RUN OF {}", GroupType.COLOR: "{} OF ONE COLOR"}


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


class FlyingCard:
    def __init__(self, card: Card | None, start: pygame.Rect, end: pygame.Rect, duration: float = 0.32,
                 delay: float = 0.0, hide_id: int | None = None):
        self.card = card
        self.start = pygame.Rect(start)
        self.end = pygame.Rect(end)
        self.duration = duration
        self.t = -delay
        self.hide_id = hide_id

    @property
    def done(self) -> bool:
        return self.t >= self.duration

    def draw(self, surf):
        if self.t < 0:
            return
        k = ease_out(min(1.0, self.t / self.duration))
        x = self.start.x + (self.end.x - self.start.x) * k
        y = self.start.y + (self.end.y - self.start.y) * k - 40 * (4 * k * (1 - k))
        w = max(10, int(self.start.w + (self.end.w - self.start.w) * k))
        h = max(15, int(self.start.h + (self.end.h - self.start.h) * k))
        img, _ = card_with_shadow(self.card, self.end.w, self.end.h, lift=12)
        if img.get_width() != w + 8:
            img = pygame.transform.smoothscale(img, (w + 8, h + 8))
        surf.blit(img, (x, y))


class GameScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        s = app.settings
        diffs = s.opponent_difficulties()
        players = [Player("YOU", is_human=True)]
        players += [Player(AI_NAMES[i], difficulty=d) for i, d in enumerate(diffs)]
        self.game = Game(players)
        self.ais = {i + 1: AIPlayer(d) for i, d in enumerate(diffs)}
        self.hint_ai = AIPlayer("Expert", random.Random(0))
        self.delay = SPEED_DELAYS[s.ai_speed]

        self.selected: list[int] = []
        self.anims: list[FlyingCard] = []
        self.log: list[tuple[str, tuple]] = []
        self.flash: tuple[str, float] | None = None
        self.splash: tuple[str, str, float, float] | None = None
        self.choosing_skip: Card | None = None
        self.overlay: str | None = None
        self.ai_timer = 0.8
        self.card_rects: dict[int, pygame.Rect] = {}
        self.meld_rects: dict[int, pygame.Rect] = {}
        self.new_card_id: int | None = None
        self._last_click = (None, 0)
        self._pending_overlay: str | None = None

        bx = 1046
        self.btn_lay = Button((bx, 548, 200, 50), "LAY DOWN", self.do_lay_down, "ACCENT", "OUTLINE", 20)
        self.btn_discard = Button((bx, 608, 200, 46), "DISCARD", self.do_discard_button, size=18)
        self.btn_sort = Button((bx, 664, 96, 42), "SORT", self.toggle_sort, size=16)
        self.btn_hint = Button((bx + 104, 664, 96, 42), "HINT", self.do_hint, size=16)
        self.btn_menu = Button((POT_BOX.x + 150, POT_BOX.y + 12, 88, 32), "MENU", lambda: self._set_overlay("pause"),
                               size=14, radius=8)
        self.buttons = [self.btn_lay, self.btn_discard, self.btn_sort, self.btn_hint, self.btn_menu]
        self.overlay_buttons: list[Button] = []

        self._consume_events()
        self._round_splash()

    # ================================================================== helpers

    @property
    def human(self) -> Player:
        return self.game.players[HUMAN]

    @property
    def busy(self) -> bool:
        return bool(self.anims) or self.splash is not None or self.overlay is not None

    @property
    def my_turn(self) -> bool:
        g = self.game
        return g.current == HUMAN and not g.round_over and not self.busy

    def say(self, msg: str, color=theme.TEXT):
        self.log.append((msg, color))
        self.log = self.log[-6:]

    def error(self, msg: str):
        self.flash = (msg, 2.6)
        sfx.play("error")

    def tip(self, msg: str):
        self.flash = (msg, 2.6)
        sfx.play("turn")

    def name(self, i: int) -> str:
        return self.game.players[i].name.title()

    def sorted_hand(self) -> list[Card]:
        key = Card.color_sort_key if self.app.settings.sort_by == "color" else Card.sort_key
        return sorted(self.human.hand, key=key)

    def selected_cards(self) -> list[Card]:
        by_id = {c.id: c for c in self.human.hand}
        return [by_id[i] for i in self.selected if i in by_id]

    def shown_phase(self, i: int) -> int:
        """The phase this round is being played for. Once a round ends the engine has already
        moved finishers up, but the table should keep showing what they just completed."""
        p = self.game.players[i]
        return p.phase - 1 if self.game.round_over and p.completed_this_round else p.phase

    def shown_requirements(self, i: int):
        return PHASES[min(self.shown_phase(i), NUM_PHASES - 1)]

    def opponent_indices(self) -> list[int]:
        return list(range(1, len(self.game.players)))

    def panel_rect(self, i: int) -> pygame.Rect:
        if i == HUMAN:
            return MY_BOX
        opps = self.opponent_indices()
        n = len(opps)
        gap = 16
        w = min(300, (1240 - (n - 1) * gap) // n)
        total = n * w + (n - 1) * gap
        x0 = (theme.WIDTH - total) // 2
        k = opps.index(i)
        return pygame.Rect(x0 + k * (w + gap), OPP_Y, w, OPP_H)

    def player_anchor(self, i: int) -> pygame.Rect:
        """Where cards fly to/from for a player."""
        if i == HUMAN:
            return pygame.Rect(HAND_AREA.centerx - HAND_W // 2, HAND_Y, HAND_W, HAND_H)
        r = self.panel_rect(i)
        return pygame.Rect(r.right - 70, r.y + 10, 40, 60)

    def _round_splash(self):
        p = self.human
        self.splash = (f"PHASE {p.phase + 1}", f"ROUND {self.game.round}  -  {describe_phase(p.phase).upper()}",
                       2.2, 2.2)
        self.say(f"Round {self.game.round}: you need {describe_phase(p.phase)}", theme.ACCENT)
        sfx.play("phase")

    # ================================================================== layout

    def hand_layout(self) -> dict[int, pygame.Rect]:
        cards = self.sorted_hand()
        n = len(cards)
        if not n:
            return {}
        step = min(HAND_W + 8, (HAND_AREA.w - HAND_W) / max(1, n - 1))
        total = HAND_W + step * (n - 1)
        x0 = HAND_AREA.x + (HAND_AREA.w - total) / 2
        rects = {}
        for k, c in enumerate(cards):
            lift = 26 if c.id in self.selected else 0
            rects[c.id] = pygame.Rect(int(x0 + k * step), HAND_Y - lift, HAND_W, HAND_H)
        return rects

    def slot_rects(self, i: int) -> list[pygame.Rect]:
        """One slot per phase requirement: on your board, or inside an opponent's box."""
        reqs = self.shown_requirements(i)
        n = len(reqs)
        if i == HUMAN:
            area = pygame.Rect(BOARD.x + 14, BOARD.y + 74, BOARD.w - 28, BOARD.h - 86)
        else:
            r = self.panel_rect(i)
            area = pygame.Rect(r.x + 10, r.y + 104, r.w - 20, r.h - 112)
        gap = 6
        h = (area.h - gap * (n - 1)) // n
        return [pygame.Rect(area.x, area.y + k * (h + gap), area.w, h) for k in range(n)]

    def _slot_cards(self, slot: pygame.Rect, cards: list[Card], label_w: int):
        """Positions for cards laid out left-to-right inside a slot after its label."""
        ch = min(84, slot.h - 10)
        cw = int(ch * 2 / 3)
        x0 = slot.x + label_w
        avail = slot.right - 8 - x0
        n = len(cards)
        step = min(cw + 3, (avail - cw) / max(1, n - 1)) if n > 1 else 0
        y = slot.y + (slot.h - ch) // 2
        return [pygame.Rect(int(x0 + k * step), y, cw, ch) for k in range(n)], (cw, ch, step)

    def label_width(self, i: int) -> int:
        return 150 if i == HUMAN else 0

    def table_layout(self):
        """Returns (meld_rects, card_rects) for every group on the table."""
        g = self.game
        meld_rects, card_rects = {}, {}
        for i in range(len(g.players)):
            melds = [m for m in g.melds if m.owner == i]
            if not melds:
                continue
            slots = self.slot_rects(i)
            for m, slot in zip(melds, slots):
                rects, _ = self._slot_cards(slot, m.ordered(), self.label_width(i) or 6)
                for c, r in zip(m.ordered(), rects):
                    card_rects[c.id] = r
                meld_rects[m.id] = slot
        return meld_rects, card_rects

    # ================================================================== events -> animation

    def _consume_events(self, origin: dict[int, pygame.Rect] | None = None):
        origin = origin or {}
        g = self.game
        _, table_cards = self.table_layout()
        hand = self.hand_layout()
        stagger = 0.0
        played: set[str] = set()

        def sound(name: str):
            if name not in played:  # one of each per batch, so hits don't stack into noise
                played.add(name)
                sfx.play(name)

        for ev in g.pop_events():
            k = ev.kind
            if k == "draw":
                sound("draw")
                src = DECK_RECT if ev.source == "deck" else DISCARD_RECT
                if ev.player == HUMAN:
                    self.new_card_id = ev.card.id
                    end = hand.get(ev.card.id, self.player_anchor(HUMAN))
                    self.anims.append(FlyingCard(ev.card, src, end, hide_id=ev.card.id))
                    if ev.source == "discard":
                        self.say(f"You took the {ev.card.label()}", theme.TEXT_DIM)
                else:
                    face = ev.card if ev.source == "discard" else None
                    self.anims.append(FlyingCard(face, src, self.player_anchor(ev.player)))
                    where = f"took the {ev.card.label()}" if ev.source == "discard" else "drew a card"
                    self.say(f"{self.name(ev.player)} {where}", theme.TEXT_DIM)
            elif k == "discard":
                sound("discard")
                start = origin.get(ev.card.id, self.player_anchor(ev.player))
                self.anims.append(FlyingCard(ev.card, start, DISCARD_RECT, hide_id=ev.card.id))
                if ev.player != HUMAN:
                    self.say(f"{self.name(ev.player)} discarded {ev.card.label()}", theme.TEXT_DIM)
            elif k == "lay":
                sound("lay")
                for m in [m for m in g.melds if m.owner == ev.player]:
                    for c in m.cards:
                        start = origin.get(c.id, self.player_anchor(ev.player))
                        self.anims.append(FlyingCard(c, start, table_cards[c.id], 0.34, stagger, hide_id=c.id))
                        stagger += 0.04
                if ev.player == HUMAN:
                    n = self.shown_phase(ev.player) + 1
                    self.say(f"You completed phase {n}!", theme.SUCCESS)
                    self.splash = ("PHASE COMPLETE!", f"PHASE {n} DONE - NOW PLAY OUT YOUR HAND", 1.5, 1.5)
                else:
                    self.say(f"{self.name(ev.player)} completed phase {self.shown_phase(ev.player) + 1}!",
                             theme.SUCCESS)
            elif k == "hit":
                sound("hit")
                start = origin.get(ev.card.id, self.player_anchor(ev.player))
                self.anims.append(FlyingCard(ev.card, start, table_cards[ev.card.id], 0.3, stagger, hide_id=ev.card.id))
                stagger += 0.06
                if ev.player != HUMAN:
                    self.say(f"{self.name(ev.player)} played {ev.card.label()}", theme.TEXT_DIM)
            elif k == "skip":
                sound("skip")
                who = "You" if ev.player == HUMAN else self.name(ev.player)
                target = "you" if ev.target == HUMAN else self.name(ev.target)
                self.say(f"{who} skipped {target}!", theme.DANGER)
            elif k == "skipped":
                who = "You lose" if ev.player == HUMAN else f"{self.name(ev.player)} loses"
                self.say(f"{who} a turn", theme.DANGER)
            elif k == "reshuffle":
                sound("shuffle")
                self.say("Discards shuffled into the deck", theme.TEXT_DIM)
            elif k == "turn" and ev.player == HUMAN:
                self.new_card_id = None
                sound("turn")
            elif k in ("round_end", "game_over"):
                self._pending_overlay = "game" if g.game_over else "round"

    # ================================================================== human actions

    def _act(self, fn, *args):
        origin = dict(self.card_rects)
        try:
            fn(HUMAN, *args)
        except RuleError as e:
            self.error(str(e))
            return False
        self.selected = [i for i in self.selected if any(c.id == i for c in self.human.hand)]
        self._consume_events(origin)
        if self.game.current != HUMAN:
            self.ai_timer = self.delay
        return True

    def click_deck(self):
        if not self.my_turn:
            return
        if self.game.has_drawn:
            self.error("You've already drawn. Now discard a card.")
            return
        self._act(self.game.draw_from_deck)

    def click_discard_pile(self):
        if not self.my_turn:
            return
        if not self.game.has_drawn:
            self._act(self.game.draw_from_discard)
        else:
            self.do_discard_button()

    def do_discard_button(self):
        if not self.my_turn:
            return
        if not self.game.has_drawn:
            self.error("Draw a card first.")
            return
        cards = self.selected_cards()
        if len(cards) != 1:
            self.error("Select exactly one card to discard.")
            return
        self.discard(cards[0])

    def discard(self, card: Card):
        if card.is_skip and len(self.game.players) > 2:
            self.choosing_skip = card
            return
        self.selected = []
        self._act(self.game.discard, card, None)

    def do_lay_down(self):
        if not self.my_turn:
            return
        if self.human.laid_down:
            self.error("Already laid down. Click a group to add cards to it.")
            return
        cards = self.selected_cards()
        if not cards:
            self.error(f"Select the cards for: {describe_phase(self.human.phase)}")
            return
        if self._act(self.game.lay_down_auto, cards):
            self.selected = []

    def click_meld(self, meld_id: int):
        if not self.my_turn:
            return
        cards = self.selected_cards()
        if not cards:
            self.error("Select cards from your hand, then click a group.")
            return
        placed = 0
        for c in cards:
            if self.game.round_over:
                break
            if self.game.meld_by_id(meld_id).accepts(c) or len(cards) == 1:
                if self._act(self.game.hit, c, meld_id):
                    placed += 1
        if placed == 0 and len(cards) > 1:
            self.error("None of those cards fit that group.")

    def toggle_sort(self):
        s = self.app.settings
        s.sort_by = "color" if s.sort_by == "number" else "number"
        s.save()

    def do_hint(self):
        if not self.my_turn:
            return
        action = self.hint_ai.next_action(self.game, HUMAN)
        kind = action[0]
        if kind == "draw":
            self.tip("Hint: take the discard." if action[1] == "discard" else "Hint: draw from the deck.")
        elif kind == "lay":
            self.selected = [c.id for g in action[1] for c in g]
            self.tip("Hint: you have your phase! Press LAY DOWN.")
        elif kind == "hit":
            self.selected = [action[1].id]
            self.tip(f"Hint: play the {action[1].label()} on a group.")
        else:
            self.selected = [action[1].id]
            self.tip(f"Hint: discard the {action[1].label()}.")

    # ================================================================== AI

    def run_ai(self):
        g = self.game
        i = g.current
        action = self.ais[i].next_action(g, i)
        try:
            if action[0] == "draw":
                (g.draw_from_deck if action[1] == "deck" else g.draw_from_discard)(i)
            elif action[0] == "lay":
                g.lay_down(i, action[1])
            elif action[0] == "hit":
                g.hit(i, action[1], action[2])
            else:
                g.discard(i, action[1], action[2])
        except RuleError:
            # Should never happen; fall back to a safe move so the game can't stall.
            if not g.has_drawn:
                g.draw_from_deck(i)
            else:
                g.discard(i, g.player.hand[0], None)
        self._consume_events()
        self.ai_timer = self.delay * (0.6 if action[0] == "draw" else 1.0)

    # ================================================================== overlays

    def _set_overlay(self, kind: str | None):
        self.overlay = kind
        self._pending_overlay = None
        cx = theme.WIDTH // 2
        primary = dict(color="ACCENT", text_color="OUTLINE")
        g = self.game
        if kind == "game":
            sfx.play("game_win" if g.winner == HUMAN else "game_lose")
        elif kind == "round":
            sfx.play("round_win" if g.went_out == HUMAN else "round_end")
        if kind in ("round", "game") and g.went_out == HUMAN:
            sfx.play("coin")
        if kind == "round":
            self.overlay_buttons = [Button((cx - 140, 650, 280, 58), "NEXT ROUND", self.next_round, size=24,
                                           **primary)]
        elif kind == "game":
            self.overlay_buttons = [
                Button((cx - 290, 650, 270, 58), "PLAY AGAIN", self.restart, size=22, **primary),
                Button((cx + 20, 650, 270, 58), "MAIN MENU", self.to_menu, size=22),
            ]
        elif kind == "pause":
            self.overlay_buttons = [
                Button((cx - 140, 300, 280, 56), "RESUME", lambda: self._set_overlay(None), size=22, **primary),
                Button((cx - 140, 368, 280, 56), "CUSTOMIZE", self.customize, size=20),
                Button((cx - 140, 436, 280, 56), "RESTART", self.restart, size=20),
                Button((cx - 140, 504, 280, 56), "MAIN MENU", self.to_menu, size=20),
            ]
        else:
            self.overlay_buttons = []

    def next_round(self):
        self.game.next_round()
        self.selected = []
        self._set_overlay(None)
        self.log = []
        self._consume_events()
        self._round_splash()
        self.ai_timer = 0.5

    def customize(self):
        from .customize import CustomizeScene
        self.app.go(CustomizeScene(self.app, back=lambda: self.app.go(self)))

    def restart(self):
        self.app.go(GameScene(self.app))

    def to_menu(self):
        from .menus import MenuScene
        self.app.go(MenuScene(self.app))

    # ================================================================== input

    def handle(self, event):
        if self.overlay:
            for b in self.overlay_buttons:
                if b.handle(event):
                    return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.overlay == "pause":
                self._set_overlay(None)
            return

        if self.splash and event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
            self.splash = None  # any click skips the banner
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.choosing_skip:
                    self.choosing_skip = None
                else:
                    self._set_overlay("pause")
            elif event.key == pygame.K_SPACE:
                self.click_deck()
            elif event.key == pygame.K_s:
                self.toggle_sort()
            return

        for b in self.buttons:
            if b.handle(event):
                return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button not in (1, 3):
            return
        pos = event.pos

        if self.choosing_skip:
            for i in self.opponent_indices():
                if self.panel_rect(i).collidepoint(pos):
                    card, self.choosing_skip = self.choosing_skip, None
                    self.selected = []
                    self._act(self.game.discard, card, i)
                    return
            self.choosing_skip = None
            return

        for cid, rect in reversed(list(self.card_rects.items())):
            if rect.collidepoint(pos):
                self.click_card(cid, event.button)
                return
        if DECK_RECT.collidepoint(pos):
            self.click_deck()
        elif DISCARD_RECT.collidepoint(pos):
            self.click_discard_pile()
        else:
            for mid, rect in self.meld_rects.items():
                if rect.collidepoint(pos):
                    self.click_meld(mid)
                    return
            if event.button == 1 and not HAND_AREA.collidepoint(pos):
                self.selected = []

    def click_card(self, cid: int, button: int):
        now = pygame.time.get_ticks()
        double = self._last_click[0] == cid and now - self._last_click[1] < 350
        self._last_click = (cid, now)
        card = next(c for c in self.human.hand if c.id == cid)
        if (double or button == 3) and self.my_turn and self.game.has_drawn:
            self.selected = [cid]
            self.discard(card)
            return
        if cid in self.selected:
            self.selected.remove(cid)
            sfx.play("deselect")
        else:
            self.selected.append(cid)
            sfx.play("select")

    # ================================================================== update

    def update(self, dt: float):
        super().update(dt)
        for a in self.anims:
            a.t += dt
        self.anims = [a for a in self.anims if not a.done]
        if self.flash:
            msg, t = self.flash
            self.flash = (msg, t - dt) if t - dt > 0 else None
        if self.splash:
            title, sub, t, total = self.splash
            self.splash = (title, sub, t - dt, total) if t - dt > 0 else None
        if self._pending_overlay and not self.anims and not self.splash:
            self._set_overlay(self._pending_overlay)
            return
        g = self.game
        if self.busy or g.round_over or g.current == HUMAN:
            return
        self.ai_timer -= dt
        if self.ai_timer <= 0:
            self.run_ai()

    # ================================================================== drawing

    def draw(self, surf):
        backdrop(surf, self.clock, SPLIT_Y)
        hidden = {a.hide_id for a in self.anims if a.hide_id is not None}
        self.meld_rects, table_cards = self.table_layout()
        for i in self.opponent_indices():
            self._draw_opponent(surf, i, hidden, table_cards)
        self._draw_pot_and_log(surf)
        self._draw_piles(surf, hidden)
        self._draw_board(surf, hidden, table_cards)
        self._draw_my_box(surf, hidden)
        for a in self.anims:
            a.draw(surf)
        msg = self.flash[0] if self.flash else self._status()[0]
        status_bar(surf, msg)
        if self.splash:
            self._draw_splash(surf)
        if self.overlay:
            self._draw_overlay(surf)

    # ---------------------------------------------------------------- pieces

    def _chip(self, surf, label: str, pos, color, fg="OUTLINE", size: int = 12) -> pygame.Rect:
        img = theme.pixel_surface(label, size, fg, None)
        r = pygame.Rect(pos[0], pos[1], img.get_width() + 12, img.get_height() + 4)
        theme.rounded(surf, theme.OUTLINE, r.move(0, 2), r.h // 2)
        theme.rounded(surf, color, r, r.h // 2)
        surf.blit(img, img.get_rect(center=r.center))
        return r

    def _counts(self, surf, p: Player, right: int, y: int):
        """Card count and chip count, right-aligned."""
        r = theme.ptext(surf, str(len(p.hand)), (right, y), 18, anchor="topright")
        theme.mini_card_icon(surf, (r.x - 20, y + 1))
        r2 = theme.ptext(surf, str(p.chips), (right, y + 24), 18, theme.ACCENT, anchor="topright")
        theme.chip(surf, (r2.x - 14, y + 34), 9, theme.ACCENT)

    def _requirement_slot(self, surf, i: int, req, slot: pygame.Rect, meld, hidden, table_cards, preview=None):
        """Draw one phase requirement: the laid group, a progress preview, or an empty outline."""
        mine = i == HUMAN
        theme.rounded(surf, theme.INNER, slot, 8)
        sel = self.selected_cards()
        can_hit = meld is not None and self.my_turn and self.game.has_drawn and self.human.laid_down and sel
        if can_hit and any(meld.accepts(c) for c in sel):
            hover = slot.collidepoint(pygame.mouse.get_pos())
            theme.rounded(surf, theme.ACCENT if hover else theme.SUCCESS, slot, 8, 3)
        else:
            theme.rounded(surf, theme.PANEL_LIGHT, slot, 8, 2)
        label = REQ_LABEL[req.type].format(req.size)
        if mine:
            theme.ptext(surf, label, (slot.x + 12, slot.y + 10), 16, theme.ACCENT)
        if meld is not None:
            if mine:
                self._chip(surf, "DONE", (slot.x + 12, slot.y + 36), theme.SUCCESS, size=12)
            for c in meld.ordered():
                if c.id in hidden or c.id not in table_cards:
                    continue
                r = table_cards[c.id]
                img, _ = card_with_shadow(c, r.w, r.h)
                surf.blit(img, r)
            return
        if not mine:
            theme.ptext(surf, label, slot.center, 14, theme.TEXT_FAINT, anchor="center")
            return
        # Your slot before laying down: ghost outlines, filled in with the cards you already have.
        cards = preview or []
        rects, (cw, ch, _) = self._slot_cards(slot, [None] * req.size, self.label_width(i))
        for k, r in enumerate(rects):
            if k < len(cards):
                img, _ = card_with_shadow(cards[k], r.w, r.h)
                img = img.copy()
                img.set_alpha(215)
                surf.blit(img, r)
            else:
                theme.rounded(surf, theme.PANEL_LIGHT, r, 6, 2)
                theme.ptext(surf, "?", r.center, 16, theme.PANEL_LIGHT, None, anchor="center")
        if preview is not None:
            have = min(len(cards), req.size)
            color = theme.SUCCESS if have >= req.size else theme.TEXT
            theme.ptext(surf, f"{have}/{req.size}", (slot.x + 12, slot.y + 36), 22, color)

    def _draw_opponent(self, surf, i: int, hidden, table_cards):
        g = self.game
        p = g.players[i]
        r = self.panel_rect(i)
        active = g.current == i and not g.round_over
        targeting = self.choosing_skip is not None
        hover = targeting and r.collidepoint(pygame.mouse.get_pos())
        edge = theme.ACCENT if active else theme.DANGER if targeting else theme.PANEL_EDGE
        theme.panel(surf, r, theme.PANEL_HOVER if hover else theme.PANEL, edge, edge_w=3 if active or hover else 2)
        bob = math.sin(self.clock * 6) * 2 if active else 0
        theme.face(surf, (r.x + 30, int(r.y + 30 + bob)), 22, i)
        theme.ptext(surf, p.name, (r.x + 60, r.y + 8), 20)
        self._chip(surf, p.difficulty.upper(), (r.x + 60, r.y + 34), DIFF_COLORS[p.difficulty], size=10)
        self._counts(surf, p, r.right - 12, r.y + 8)

        inner = pygame.Rect(r.x + 8, r.y + 60, r.w - 16, r.h - 66)
        theme.rounded(surf, theme.INNER, inner, 8)
        shown = self.shown_phase(i)
        phase_txt = "ALL DONE" if shown >= NUM_PHASES else f"PHASE {shown + 1}"
        theme.ptext(surf, phase_txt, (inner.x + 8, inner.y + 6), 16, theme.ACCENT)
        desc = describe_phase(min(shown, NUM_PHASES - 1))
        f = theme.font(12, False)
        while f.size(desc)[0] > inner.w - 16 and len(desc) > 4:
            desc = desc[:-2]
        theme.text(surf, desc, (inner.x + 9, inner.y + 26), 12, theme.TEXT_DIM, bold=False)
        if p.skips_pending:
            self._chip(surf, "SKIPPED", (inner.right - 74, inner.y + 6), theme.DANGER, theme.TEXT, size=10)
        elif p.laid_down:
            self._chip(surf, "LAID", (inner.right - 50, inner.y + 6), theme.SUCCESS, size=10)
        melds = [m for m in g.melds if m.owner == i]
        for k, (req, slot) in enumerate(zip(self.shown_requirements(i), self.slot_rects(i))):
            meld = melds[k] if k < len(melds) else None
            self._requirement_slot(surf, i, req, slot, meld, hidden, table_cards)

    def _draw_pot_and_log(self, surf):
        g = self.game
        theme.panel(surf, POT_BOX)
        theme.ptext(surf, "POT", (POT_BOX.x + 14, POT_BOX.y + 12), 20, theme.ACCENT)
        stacks = [g.pot // 3 + (1 if g.pot % 3 > k else 0) for k in range(3)]
        for k, n in enumerate(stacks):
            x = POT_BOX.x + 34 + k * 42
            theme.chip_stack(surf, (x, POT_BOX.bottom - 22), 16, theme.CHIP_COLORS[k], max(1, n) if g.pot else 0)
        theme.ptext(surf, f"x{g.pot}", (POT_BOX.right - 16, POT_BOX.bottom - 14), 30, theme.ACCENT,
                    anchor="bottomright")
        self.btn_menu.draw(surf)

        theme.panel(surf, LOG_BOX)
        theme.ptext(surf, f"ROUND {g.round}", (LOG_BOX.x + 14, LOG_BOX.y + 10), 16, theme.ACCENT)
        lines = []
        for msg, color in self.log[-5:]:
            for chunk in _wrap(msg, 13, LOG_BOX.w - 28):
                lines.append((chunk, color))
        y = LOG_BOX.y + 36
        for chunk, color in lines[-6:]:
            theme.text(surf, chunk, (LOG_BOX.x + 14, y), 13, color, bold=False)
            y += 18

    def _arrow(self, surf, center, flip: bool):
        """Curved orange turn arrow."""
        cx, cy = center
        r = 30
        pts = []
        start, end = (200, 340) if not flip else (-160, -20)
        for k in range(13):
            a = math.radians(start + (end - start) * k / 12)
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        tip = pts[-1]
        prev = pts[-2]
        ang = math.atan2(tip[1] - prev[1], tip[0] - prev[0])
        head = [(tip[0] + math.cos(ang) * 14, tip[1] + math.sin(ang) * 14),
                (tip[0] + math.cos(ang + 2.2) * 13, tip[1] + math.sin(ang + 2.2) * 13),
                (tip[0] + math.cos(ang - 2.2) * 13, tip[1] + math.sin(ang - 2.2) * 13)]
        pygame.draw.lines(surf, theme.OUTLINE, False, [(x, y + 3) for x, y in pts], 14)
        pygame.draw.polygon(surf, theme.OUTLINE, [(x, y + 3) for x, y in head])
        pygame.draw.lines(surf, theme.OUTLINE, False, pts, 14)
        pygame.draw.polygon(surf, theme.OUTLINE, head)
        pygame.draw.lines(surf, theme.ORANGE, False, pts, 9)
        pygame.draw.polygon(surf, theme.ORANGE, head)

    def _draw_piles(self, surf, hidden):
        g = self.game
        can_draw = self.my_turn and not g.has_drawn
        mouse = pygame.mouse.get_pos()
        bob = math.sin(self.clock * 3) * 3
        self._arrow(surf, (DECK_RECT.x - 30, DECK_RECT.y + 78 + bob), flip=False)
        self._arrow(surf, (DISCARD_RECT.right + 34, DISCARD_RECT.y + 78 - bob), flip=True)

        for k in range(3, 0, -1):
            pygame.draw.rect(surf, theme.CARD_WHITE, DECK_RECT.move(k * 2, k * 2), border_radius=12)
            pygame.draw.rect(surf, theme.OUTLINE, DECK_RECT.move(k * 2, k * 2), 1, border_radius=12)
        lift = 6 if can_draw and DECK_RECT.collidepoint(mouse) else 0
        img, _ = card_with_shadow(None, DECK_RECT.w, DECK_RECT.h)
        surf.blit(img, DECK_RECT.move(0, -lift))
        if can_draw:
            theme.rounded(surf, theme.ACCENT, DECK_RECT.move(0, -lift).inflate(8, 8), 14, 3)
        theme.ptext(surf, f"DECK {len(g.deck)}", (DECK_RECT.centerx, DECK_RECT.y - 16), 14, anchor="center")

        visible = [c for c in g.discard_pile if c.id not in hidden]
        if len(visible) >= 2:
            under, _ = card_with_shadow(visible[-2], DISCARD_RECT.w, DISCARD_RECT.h)
            surf.blit(pygame.transform.rotate(under, 7), DISCARD_RECT.move(-8, -6))
        if visible:
            top = visible[-1]
            can_take = can_draw and not top.is_skip
            lift = 6 if can_take and DISCARD_RECT.collidepoint(mouse) else 0
            img, _ = card_with_shadow(top, DISCARD_RECT.w, DISCARD_RECT.h)
            surf.blit(img, DISCARD_RECT.move(0, -lift))
            if can_take:
                theme.rounded(surf, theme.ACCENT, DISCARD_RECT.move(0, -lift).inflate(8, 8), 14, 3)
        else:
            theme.rounded(surf, theme.PANEL_EDGE, DISCARD_RECT, 12, 2)
        if self.my_turn and g.has_drawn and len(self.selected) == 1:
            theme.rounded(surf, theme.INFO, DISCARD_RECT.inflate(8, 8), 14, 3)
        theme.ptext(surf, "DISCARD", (DISCARD_RECT.centerx, DISCARD_RECT.y - 16), 14, anchor="center")
        theme.logo(surf, "10 PHASES", ((DECK_RECT.x + DISCARD_RECT.right) // 2 + 6, DECK_RECT.bottom + 52), 38,
                   angle=10)

    def _draw_board(self, surf, hidden, table_cards):
        """Your phase board: which phase you're on, the tracker, and a slot per group."""
        h = self.human
        theme.panel(surf, BOARD)
        theme.ptext(surf, "YOUR PHASE", (BOARD.x + 16, BOARD.y + 10), 14, theme.TEXT_DIM)
        shown = self.shown_phase(HUMAN)
        title = "ALL 10 DONE!" if shown >= NUM_PHASES else f"PHASE {shown + 1}"
        theme.ptext(surf, title, (BOARD.x + 16, BOARD.y + 30), 30, theme.ACCENT)
        # 10-step tracker
        for k in range(NUM_PHASES):
            cx = BOARD.x + 222 + k * 34
            cy = BOARD.y + 38
            done = k < shown
            current = k == shown
            pulse = (math.sin(self.clock * 5) + 1) / 2 if current else 0
            pygame.draw.circle(surf, theme.OUTLINE, (cx, cy + 2), 15)
            fill = theme.ACCENT if done else theme.CARD_WHITE if current else theme.INNER
            pygame.draw.circle(surf, fill, (cx, cy), 14)
            if current:
                pygame.draw.circle(surf, theme.ACCENT, (cx, cy), int(16 + pulse * 3), 3)
            color = theme.OUTLINE if done or current else theme.TEXT_FAINT
            theme.ptext(surf, str(k + 1), (cx, cy), 12, color, None, anchor="center")
        reqs = self.shown_requirements(HUMAN)
        melds = [m for m in self.game.melds if m.owner == HUMAN]
        previews = self._phase_preview() if not h.laid_down and not self.game.round_over and self.app.settings.hints \
            else None
        for k, (req, slot) in enumerate(zip(reqs, self.slot_rects(HUMAN))):
            meld = melds[k] if k < len(melds) else None
            preview = previews[k] if previews is not None else None
            self._requirement_slot(surf, HUMAN, req, slot, meld, hidden, table_cards, preview)

    def _phase_preview(self) -> list[list[Card]]:
        """For each requirement, the cards in your hand that count towards it (wilds fill gaps)."""
        plan = plan_phase(self.human.requirements, self.human.hand)
        wilds = list(plan.wilds)
        out = []
        for req, take in plan.groups:
            cards = list(take)[:req.size]
            while len(cards) < req.size and wilds:
                cards.append(wilds.pop())
            out.append(cards)
        return out

    def _draw_my_box(self, surf, hidden):
        g = self.game
        h = self.human
        active = g.current == HUMAN and not g.round_over
        theme.panel(surf, MY_BOX, edge=theme.ACCENT if active else theme.PANEL_EDGE, edge_w=3 if active else 2)
        bob = math.sin(self.clock * 6) * 2 if active else 0
        theme.face(surf, (MY_BOX.x + 34, int(MY_BOX.y + 30 + bob)), 24, HUMAN)
        theme.ptext(surf, "YOU", (MY_BOX.x + 68, MY_BOX.y + 10), 22)
        x = MY_BOX.x + 140
        theme.mini_card_icon(surf, (x, MY_BOX.y + 15))
        theme.ptext(surf, str(len(h.hand)), (x + 20, MY_BOX.y + 12), 18)
        theme.chip(surf, (x + 70, MY_BOX.y + 24), 10, theme.ACCENT)
        theme.ptext(surf, str(h.chips), (x + 86, MY_BOX.y + 12), 18, theme.ACCENT)
        theme.ptext(surf, f"{h.score} PTS", (x + 150, MY_BOX.y + 12), 18, theme.TEXT_DIM)
        if active:
            self._chip(surf, "YOUR TURN!", (x + 270, MY_BOX.y + 12), theme.ACCENT, size=14)
        if h.skips_pending:
            self._chip(surf, "SKIPPED", (x + 420, MY_BOX.y + 12), theme.DANGER, theme.TEXT, size=14)

        layout = self.hand_layout()
        mouse = pygame.mouse.get_pos()
        hover_id = None
        for cid, rect in reversed(list(layout.items())):
            if rect.collidepoint(mouse):
                hover_id = cid
                break
        self.card_rects = {}
        for c in self.sorted_hand():
            rect = layout[c.id].copy()
            if c.id == hover_id and c.id not in self.selected:
                rect.y -= 10
            self.card_rects[c.id] = rect
            if c.id in hidden:
                continue
            img, _ = card_with_shadow(c, rect.w, rect.h, lift=12 if c.id in self.selected else 0)
            surf.blit(img, rect)
            if c.id in self.selected:
                theme.rounded(surf, theme.ACCENT, rect.inflate(6, 6), 14, 4)
            elif c.id == self.new_card_id:
                theme.rounded(surf, theme.INFO, rect.inflate(6, 6), 14, 3)

        drawn = self.my_turn and g.has_drawn
        self.btn_lay.enabled = drawn and not h.laid_down
        self.btn_discard.enabled = drawn and len(self.selected) == 1
        self.btn_hint.visible = self.app.settings.hints
        self.btn_hint.enabled = self.my_turn
        self.btn_sort.label = "1-12" if self.app.settings.sort_by == "number" else "COLOR"
        for b in (self.btn_lay, self.btn_discard, self.btn_sort, self.btn_hint):
            b.draw(surf)
        if self.selected:
            theme.ptext(surf, f"{len(self.selected)} SELECTED", (1146, 734), 14, theme.TEXT_DIM, anchor="center")

    def _status(self) -> tuple[str, tuple]:
        g = self.game
        if g.round_over:
            return "The round is over!", theme.TEXT
        if g.current != HUMAN:
            return "Wait until it is your turn.", theme.TEXT
        if self.choosing_skip:
            return "Click the player you want to skip. (Esc cancels)", theme.DANGER
        if not g.has_drawn:
            return "Draw from the deck or take the discard.", theme.TEXT
        if not self.human.laid_down:
            plan = plan_phase(self.human.requirements, self.human.hand)
            if plan.complete and self.app.settings.hints:
                return "You have your phase! Select the cards and LAY DOWN.", theme.SUCCESS
            return "Lay down your phase, or discard a card.", theme.TEXT
        return "Add cards to groups, then discard one.", theme.TEXT

    def _draw_splash(self, surf):
        title, sub, t, total = self.splash
        k = min(1.0, (total - t) / 0.25, t / 0.3)
        band = pygame.Rect(0, 300, theme.WIDTH, 170)
        shade = pygame.Surface(band.size, pygame.SRCALPHA)
        shade.fill((8, 26, 70, int(200 * k)))
        surf.blit(shade, band)
        pygame.draw.line(surf, theme.PANEL_EDGE, band.topleft, band.topright, 3)
        pygame.draw.line(surf, theme.PANEL_EDGE, band.bottomleft, band.bottomright, 3)
        x = theme.WIDTH // 2 + int((1 - k) * -300)
        theme.logo(surf, title, (x, band.y + 70), 72, angle=6)
        theme.ptext(surf, sub, (theme.WIDTH // 2, band.bottom - 26), 20, theme.TEXT, anchor="center")

    def _draw_overlay(self, surf):
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((6, 20, 60, 190))
        surf.blit(shade, (0, 0))
        cx = theme.WIDTH // 2
        g = self.game
        if self.overlay == "pause":
            theme.panel(surf, (cx - 200, 200, 400, 390))
            theme.logo(surf, "PAUSED", (cx, 250), 40, angle=4)
        else:
            panel = pygame.Rect(cx - 400, 90, 800, 640)
            theme.panel(surf, panel)
            if self.overlay == "game":
                winner = g.players[g.winner]
                title = "YOU WIN!" if g.winner == HUMAN else f"{winner.name} WINS!"
            else:
                title = f"ROUND {g.round} OVER"
            theme.logo(surf, title, (cx, 150), 52, angle=4)
            if self.overlay == "round":
                went = "You went out and won the pot!" if g.went_out == HUMAN else \
                    f"{self.name(g.went_out)} went out and won the pot!"
                theme.ptext(surf, went, (cx, 210), 18, theme.TEXT, anchor="center")
            heads = [("PLAYER", panel.x + 100), ("NEXT PHASE", panel.x + 380), ("POINTS", panel.x + 540),
                     ("CHIPS", panel.x + 680)]
            for label, x in heads:
                theme.ptext(surf, label, (x, 250), 14, theme.TEXT_DIM, anchor="midleft" if label == "PLAYER"
                            else "center")
            for k, i in enumerate(g.standings()):
                p = g.players[i]
                y = 274 + k * 60
                row = pygame.Rect(panel.x + 30, y, panel.w - 60, 52)
                theme.rounded(surf, theme.PANEL_HOVER if i == HUMAN else theme.INNER, row, 10)
                theme.face(surf, (row.x + 34, row.centery), 19, i)
                theme.ptext(surf, p.name, (row.x + 66, row.centery), 20, anchor="midleft")
                if p.difficulty:
                    self._chip(surf, p.difficulty.upper(), (row.x + 200, row.centery - 11),
                               DIFF_COLORS[p.difficulty], size=10)
                done = "DONE!" if p.finished_all else f"{p.phase + 1}"
                theme.ptext(surf, done, (panel.x + 380, row.centery), 22, theme.ACCENT, anchor="center")
                if p.completed_this_round:
                    tx, ty = panel.x + 420, row.centery
                    pygame.draw.polygon(surf, theme.SUCCESS, [(tx - 8, ty + 6), (tx + 8, ty + 6), (tx, ty - 8)])
                pts = g.round_points.get(i, 0)
                theme.ptext(surf, f"+{pts}  ({p.score})", (panel.x + 540, row.centery), 18,
                            theme.TEXT if pts else theme.SUCCESS, anchor="center")
                dc = g.round_chips.get(i, 0)
                theme.chip(surf, (panel.x + 640, row.centery + 2), 9, theme.ACCENT)
                theme.ptext(surf, f"{p.chips} ({dc:+d})", (panel.x + 690, row.centery), 18,
                            theme.ACCENT if dc > 0 else theme.TEXT_DIM, anchor="center")
        for b in self.overlay_buttons:
            b.draw(surf)
