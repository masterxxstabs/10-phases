"""The main table: opponents across the top, piles and table groups in the
middle, your hand along the bottom."""

from __future__ import annotations

import random

import pygame

from ..ai import AIPlayer, plan_phase
from ..cards import Card
from ..game import Game, Player, RuleError
from ..phases import NUM_PHASES, GroupType, describe_phase
from ..settings import SPEED_DELAYS
from . import theme
from .card_art import card_with_shadow, render_card
from .menus import Scene, _wrap
from .widgets import Button

HUMAN = 0
AI_NAMES = ["Ava", "Bolt", "Cleo", "Dex", "Echo"]
DIFF_COLORS = {"Easy": theme.SUCCESS, "Medium": theme.INFO, "Hard": (255, 150, 60), "Expert": theme.DANGER}

# Layout
TOP_H = 56
PANEL_Y, PANEL_H = 66, 116
PILES = pygame.Rect(20, 194, 280, 350)
DECK_RECT = pygame.Rect(42, 214, 104, 156)
DISCARD_RECT = pygame.Rect(170, 214, 104, 156)
TABLE = pygame.Rect(312, 194, 948, 350)
BAR_Y = 556
HAND_AREA = pygame.Rect(20, 616, 1010, 184)
HAND_W, HAND_H = 90, 135
HAND_Y = 650


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
        players = [Player("You", is_human=True)]
        players += [Player(AI_NAMES[i], difficulty=d) for i, d in enumerate(diffs)]
        self.game = Game(players)
        self.ais = {i + 1: AIPlayer(d) for i, d in enumerate(diffs)}
        self.hint_ai = AIPlayer("Expert", random.Random(0))
        self.delay = SPEED_DELAYS[s.ai_speed]

        self.selected: list[int] = []
        self.anims: list[FlyingCard] = []
        self.log: list[tuple[str, tuple]] = []
        self.flash: tuple[str, float] | None = None
        self.choosing_skip: Card | None = None
        self.overlay: str | None = None
        self.ai_timer = 0.8
        self.card_rects: dict[int, pygame.Rect] = {}
        self.meld_rects: dict[int, pygame.Rect] = {}
        self.new_card_id: int | None = None
        self._last_click = (None, 0)
        self._pending_overlay: str | None = None

        bx = 1048
        self.btn_lay = Button((bx, 628, 102, 52), "Lay Down", self.do_lay_down, theme.ACCENT, theme.BG_DARK, 18)
        self.btn_discard = Button((bx + 112, 628, 102, 52), "Discard", self.do_discard_button, size=18)
        self.btn_sort = Button((bx, 690, 102, 46), "Sort", self.toggle_sort, size=17)
        self.btn_hint = Button((bx + 112, 690, 102, 46), "Hint", self.do_hint, size=17)
        self.btn_menu = Button((1150, 10, 110, 38), "Menu", lambda: self._set_overlay("pause"), size=16, radius=10)
        self.buttons = [self.btn_lay, self.btn_discard, self.btn_sort, self.btn_hint, self.btn_menu]
        self.overlay_buttons: list[Button] = []

        self._consume_events()
        self.say(f"Round {self.game.round} — you're on phase 1: {describe_phase(0)}", theme.ACCENT)

    # ================================================================== helpers

    @property
    def human(self) -> Player:
        return self.game.players[HUMAN]

    @property
    def my_turn(self) -> bool:
        g = self.game
        return g.current == HUMAN and not g.round_over and not self.anims and self.overlay is None

    def say(self, msg: str, color=theme.TEXT):
        self.log.append((msg, color))
        self.log = self.log[-6:]

    def error(self, msg: str):
        self.flash = (msg, 2.4)

    def name(self, i: int) -> str:
        return self.game.players[i].name

    def sorted_hand(self) -> list[Card]:
        key = Card.color_sort_key if self.app.settings.sort_by == "color" else Card.sort_key
        return sorted(self.human.hand, key=key)

    def selected_cards(self) -> list[Card]:
        by_id = {c.id: c for c in self.human.hand}
        return [by_id[i] for i in self.selected if i in by_id]

    def opponent_indices(self) -> list[int]:
        return list(range(1, len(self.game.players)))

    def panel_rect(self, i: int) -> pygame.Rect:
        if i == HUMAN:
            return pygame.Rect(20, BAR_Y, 470, 52)
        opps = self.opponent_indices()
        n = len(opps)
        w = min(236, (1240 - (n - 1) * 12) // n)
        total = n * w + (n - 1) * 12
        x0 = (theme.WIDTH - total) // 2
        k = opps.index(i)
        return pygame.Rect(x0 + k * (w + 12), PANEL_Y, w, PANEL_H)

    def player_anchor(self, i: int) -> pygame.Rect:
        """Where cards fly to/from for a player."""
        if i == HUMAN:
            return pygame.Rect(HAND_AREA.centerx - HAND_W // 2, HAND_Y, HAND_W, HAND_H)
        r = self.panel_rect(i)
        return pygame.Rect(r.centerx - 30, r.centery - 45, 60, 90)

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
            lift = 28 if c.id in self.selected else 0
            rects[c.id] = pygame.Rect(int(x0 + k * step), HAND_Y - lift, HAND_W, HAND_H)
        return rects

    def table_layout(self):
        """Returns (rows, meld_rects, card_rects).

        rows: [(player_index, row_rect)], meld_rects: {meld_id: rect}, card_rects: {card_id: rect}
        """
        g = self.game
        owners = [i for i in range(len(g.players)) if any(m.owner == i for m in g.melds)]
        rows, meld_rects, card_rects = [], {}, {}
        if not owners:
            return rows, meld_rects, card_rects
        inner = TABLE.inflate(-24, -56)
        inner.y = TABLE.y + 44
        row_h = min(86, inner.h // len(owners))
        ch = min(66, row_h - 12)
        cw = int(ch * 2 / 3)
        label_w = 120
        for r, owner in enumerate(owners):
            row = pygame.Rect(inner.x, inner.y + r * row_h, inner.w, row_h - 6)
            rows.append((owner, row))
            melds = [m for m in g.melds if m.owner == owner]
            avail = (row.w - label_w - 16 * len(melds)) // len(melds)
            x = row.x + label_w
            for m in melds:
                cards = m.ordered()
                n = len(cards)
                step = min(cw * 0.72, (avail - cw) / max(1, n - 1)) if n > 1 else 0
                gw = int(cw + step * (n - 1))
                meld_rects[m.id] = pygame.Rect(x - 6, row.y + (row.h - ch) // 2 - 6, gw + 12, ch + 12)
                for k, c in enumerate(cards):
                    card_rects[c.id] = pygame.Rect(int(x + k * step), row.y + (row.h - ch) // 2, cw, ch)
                x += gw + 28
        return rows, meld_rects, card_rects

    # ================================================================== events -> animation

    def _consume_events(self, origin: dict[int, pygame.Rect] | None = None):
        origin = origin or {}
        g = self.game
        _, _, table_cards = self.table_layout()
        hand = self.hand_layout()
        stagger = 0.0
        for ev in g.pop_events():
            k = ev.kind
            if k == "draw":
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
                    where = f"took the {ev.card.label()}" if ev.source == "discard" else "drew from the deck"
                    self.say(f"{self.name(ev.player)} {where}", theme.TEXT_DIM)
            elif k == "discard":
                start = origin.get(ev.card.id, self.player_anchor(ev.player))
                self.anims.append(FlyingCard(ev.card, start, DISCARD_RECT, hide_id=ev.card.id))
                if ev.player != HUMAN:
                    self.say(f"{self.name(ev.player)} discarded {ev.card.label()}", theme.TEXT_DIM)
            elif k == "lay":
                p = g.players[ev.player]
                for m in [m for m in g.melds if m.owner == ev.player]:
                    for c in m.cards:
                        start = origin.get(c.id, self.player_anchor(ev.player))
                        self.anims.append(FlyingCard(c, start, table_cards[c.id], 0.34, stagger, hide_id=c.id))
                        stagger += 0.04
                who = "You" if ev.player == HUMAN else p.name
                self.say(f"{who} completed phase {p.phase + 1}!", theme.SUCCESS)
            elif k == "hit":
                start = origin.get(ev.card.id, self.player_anchor(ev.player))
                self.anims.append(FlyingCard(ev.card, start, table_cards[ev.card.id], 0.3, stagger, hide_id=ev.card.id))
                stagger += 0.06
                if ev.player != HUMAN:
                    self.say(f"{self.name(ev.player)} played {ev.card.label()} on the table", theme.TEXT_DIM)
            elif k == "skip":
                who = "You" if ev.player == HUMAN else self.name(ev.player)
                target = "you" if ev.target == HUMAN else self.name(ev.target)
                self.say(f"{who} skipped {target}", theme.DANGER)
            elif k == "skipped":
                who = "You lose" if ev.player == HUMAN else f"{self.name(ev.player)} loses"
                self.say(f"{who} a turn (skipped)", theme.DANGER)
            elif k == "reshuffle":
                self.say("Discard pile shuffled into the deck", theme.TEXT_DIM)
            elif k == "turn" and ev.player == HUMAN:
                self.new_card_id = None
            elif k in ("round_end", "game_over"):
                self._pending_overlay = "game" if g.game_over else "round"
        if self._pending_overlay and not self.anims:
            self._set_overlay(self._pending_overlay)

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
            self.error("You've already laid down. Click a table group to add cards.")
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
            self.error("Select cards from your hand, then click a group to add them.")
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
            self.error("Hint: take the discard." if action[1] == "discard" else "Hint: draw from the deck.")
        elif kind == "lay":
            self.selected = [c.id for g in action[1] for c in g]
            self.error("Hint: you have your phase! Press Lay Down.")
        elif kind == "hit":
            self.selected = [action[1].id]
            self.error(f"Hint: play the {action[1].label()} on the table.")
        else:
            self.selected = [action[1].id]
            self.error(f"Hint: discard the {action[1].label()}.")

    # ================================================================== AI

    def run_ai(self):
        g = self.game
        i = g.current
        ai = self.ais[i]
        action = ai.next_action(g, i)
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
        if kind == "round":
            self.overlay_buttons = [Button((cx - 130, 640, 260, 60), "Next Round", self.next_round,
                                           theme.ACCENT, theme.BG_DARK, 24)]
        elif kind == "game":
            self.overlay_buttons = [
                Button((cx - 280, 640, 260, 60), "Play Again", self.restart, theme.ACCENT, theme.BG_DARK, 24),
                Button((cx + 20, 640, 260, 60), "Main Menu", self.to_menu, size=22),
            ]
        elif kind == "pause":
            self.overlay_buttons = [
                Button((cx - 140, 330, 280, 58), "Resume", lambda: self._set_overlay(None), theme.ACCENT,
                       theme.BG_DARK, 22),
                Button((cx - 140, 400, 280, 58), "Restart", self.restart, size=20),
                Button((cx - 140, 470, 280, 58), "Main Menu", self.to_menu, size=20),
            ]
        else:
            self.overlay_buttons = []

    def next_round(self):
        self.game.next_round()
        self.selected = []
        self._set_overlay(None)
        self.log = []
        self.say(f"Round {self.game.round} — you're on phase {self.human.phase + 1}: "
                 f"{describe_phase(self.human.phase)}", theme.ACCENT)
        self._consume_events()
        self.ai_timer = 0.8

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

        # Hand (topmost card first)
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
        else:
            self.selected.append(cid)

    # ================================================================== update

    def update(self, dt: float):
        for a in self.anims:
            a.t += dt
        self.anims = [a for a in self.anims if not a.done]
        if self.flash:
            msg, t = self.flash
            self.flash = (msg, t - dt) if t - dt > 0 else None
        if self._pending_overlay and not self.anims:
            self._set_overlay(self._pending_overlay)
            return
        g = self.game
        if self.overlay or self.anims or g.round_over or g.current == HUMAN:
            return
        self.ai_timer -= dt
        if self.ai_timer <= 0:
            self.run_ai()

    # ================================================================== drawing

    def draw(self, surf):
        g = self.game
        surf.fill(theme.BG)
        hidden = {a.hide_id for a in self.anims if a.hide_id is not None}
        self._draw_top_bar(surf)
        for i in self.opponent_indices():
            self._draw_opponent(surf, i)
        self._draw_piles(surf, hidden)
        self._draw_table(surf, hidden)
        self._draw_bottom(surf, hidden)
        for a in self.anims:
            a.draw(surf)
        if self.flash:
            self._draw_flash(surf)
        if self.overlay:
            self._draw_overlay(surf)

    def _draw_top_bar(self, surf):
        pygame.draw.rect(surf, theme.BG_DARK, (0, 0, theme.WIDTH, TOP_H))
        theme.shadow_text(surf, "10 PHASES", (24, TOP_H // 2), 28, theme.ACCENT, shadow=(0, 0, 0), offset=2,
                          anchor="midleft")
        theme.text(surf, f"ROUND {self.game.round}", (230, TOP_H // 2), 18, theme.TEXT_DIM, anchor="midleft")
        diff = self.app.settings.difficulty
        theme.text(surf, f"AI: {diff.upper()}", (350, TOP_H // 2), 18, theme.TEXT_DIM, anchor="midleft")
        self.btn_menu.draw(surf)

    def _avatar(self, surf, i: int, center, r: int):
        color = theme.AVATAR_COLORS[i % len(theme.AVATAR_COLORS)]
        pygame.draw.circle(surf, color, center, r)
        theme.text(surf, self.game.players[i].name[0], center, int(r * 1.05), theme.BG_DARK, anchor="center")

    def _chip(self, surf, label: str, pos, color, fg=theme.BG_DARK, size: int = 12) -> pygame.Rect:
        f = theme.font(size)
        w = f.size(label)[0] + 14
        r = pygame.Rect(pos[0], pos[1], w, size + 10)
        theme.rounded(surf, color, r, r.h // 2)
        theme.text(surf, label, r.center, size, fg, anchor="center")
        return r

    def _draw_opponent(self, surf, i: int):
        g = self.game
        p = g.players[i]
        r = self.panel_rect(i)
        active = g.current == i and not g.round_over
        targeting = self.choosing_skip is not None
        hover = targeting and r.collidepoint(pygame.mouse.get_pos())
        theme.rounded(surf, theme.PANEL_HOVER if hover else theme.PANEL, r, 14)
        if active:
            theme.rounded(surf, theme.ACCENT, r, 14, 3)
        elif targeting:
            theme.rounded(surf, theme.DANGER, r, 14, 3 if hover else 2)
        self._avatar(surf, i, (r.x + 30, r.y + 30), 18)
        theme.text(surf, p.name, (r.x + 56, r.y + 12), 18)
        self._chip(surf, p.difficulty.upper(), (r.x + 56, r.y + 34), DIFF_COLORS[p.difficulty], size=11)
        # Card count with a mini card back
        back, _ = card_with_shadow(None, 26, 39)
        bx = r.right - 86
        for k in range(min(3, len(p.hand))):
            surf.blit(back, (bx + k * 5, r.y + 10 + k * 2))
        theme.text(surf, f"×{len(p.hand)}", (r.right - 14, r.y + 30), 18, anchor="midright")

        phase_txt = "DONE" if p.finished_all else f"PHASE {p.phase + 1}"
        theme.text(surf, phase_txt, (r.x + 14, r.y + 62), 17, theme.ACCENT)
        theme.text(surf, f"{p.score} pts", (r.right - 14, r.y + 62), 15, theme.TEXT_DIM, anchor="topright")
        desc = describe_phase(min(p.phase, NUM_PHASES - 1))
        f = theme.font(13, False)
        while f.size(desc)[0] > r.w - 28 and len(desc) > 4:
            desc = desc[:-2]
        theme.text(surf, desc, (r.x + 14, r.y + 86), 13, theme.TEXT_DIM, bold=False)
        if p.laid_down:
            self._chip(surf, "LAID DOWN", (r.right - 100, r.y + 84), theme.SUCCESS, size=10)
        if p.skips_pending:
            self._chip(surf, "SKIPPED", (r.right - 100, r.y + 84) if not p.laid_down else (r.right - 170, r.y + 84),
                       theme.DANGER, theme.TEXT, size=10)

    def _draw_piles(self, surf, hidden):
        g = self.game
        theme.rounded(surf, theme.PANEL, PILES, 16)
        can_draw = self.my_turn and not g.has_drawn
        mouse = pygame.mouse.get_pos()
        # Deck: a little stack
        for k in range(3, 0, -1):
            pygame.draw.rect(surf, theme.darken(theme.CARD_BLACK, -10), DECK_RECT.move(k * 2, k * 2), border_radius=12)
        lift = 6 if can_draw and DECK_RECT.collidepoint(mouse) else 0
        img, _ = card_with_shadow(None, DECK_RECT.w, DECK_RECT.h)
        surf.blit(img, DECK_RECT.move(0, -lift))
        if can_draw:
            theme.rounded(surf, theme.ACCENT, DECK_RECT.move(0, -lift).inflate(8, 8), 14, 3)
        theme.text(surf, f"DECK · {len(g.deck)}", (DECK_RECT.centerx, DECK_RECT.bottom + 14), 14, theme.TEXT_DIM,
                   anchor="center")

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
            theme.rounded(surf, theme.PANEL_LIGHT, DISCARD_RECT, 12, 2)
        if self.my_turn and g.has_drawn and len(self.selected) == 1:
            theme.rounded(surf, theme.INFO, DISCARD_RECT.inflate(8, 8), 14, 3)
        theme.text(surf, "DISCARD", (DISCARD_RECT.centerx, DISCARD_RECT.bottom + 14), 14, theme.TEXT_DIM,
                   anchor="center")

        # Activity log
        y = DECK_RECT.bottom + 40
        theme.text(surf, "ACTIVITY", (PILES.x + 16, y), 12, theme.TEXT_FAINT)
        y += 20
        lines = []
        for msg, color in self.log[-5:]:
            for chunk in _wrap(msg, 13, PILES.w - 32):
                lines.append((chunk, color))
        for chunk, color in lines[-7:]:
            theme.text(surf, chunk, (PILES.x + 16, y), 13, color, bold=False)
            y += 17

    def _draw_table(self, surf, hidden):
        g = self.game
        theme.rounded(surf, theme.PANEL, TABLE, 16)
        theme.text(surf, "TABLE", (TABLE.x + 18, TABLE.y + 14), 14, theme.TEXT_FAINT)
        rows, meld_rects, card_rects = self.table_layout()
        self.meld_rects = meld_rects
        if not rows:
            theme.text(surf, "Completed phases appear here", TABLE.center, 18, theme.TEXT_FAINT, bold=False,
                       anchor="center")
            return
        sel = self.selected_cards()
        can_hit = self.my_turn and g.has_drawn and self.human.laid_down and sel
        mouse = pygame.mouse.get_pos()
        for owner, row in rows:
            p = g.players[owner]
            self._avatar(surf, owner, (row.x + 16, row.centery - 9), 13)
            theme.text(surf, p.name, (row.x + 36, row.centery - 18), 15)
            phase = p.phase + (0 if g.round_over else 1)
            theme.text(surf, f"Phase {phase}", (row.x + 36, row.centery + 2), 12, theme.TEXT_DIM, bold=False)
        for m in g.melds:
            mr = meld_rects[m.id]
            if can_hit and any(m.accepts(c) for c in sel):
                color = theme.ACCENT if mr.collidepoint(mouse) else theme.SUCCESS
                theme.rounded(surf, color, mr, 10, 3)
            label = {GroupType.SET: "SET", GroupType.RUN: "RUN", GroupType.COLOR: "COLOR"}[m.type]
            theme.text(surf, label, (mr.x + 6, mr.y - 12), 10, theme.TEXT_FAINT)
            for c in m.ordered():
                if c.id in hidden:
                    continue
                r = card_rects[c.id]
                img, _ = card_with_shadow(c, r.w, r.h)
                surf.blit(img, r)

    def _draw_bottom(self, surf, hidden):
        g = self.game
        h = self.human
        # Your phase panel
        r = self.panel_rect(HUMAN)
        active = g.current == HUMAN and not g.round_over
        theme.rounded(surf, theme.PANEL, r, 14)
        if active:
            theme.rounded(surf, theme.ACCENT, r, 14, 3)
        self._avatar(surf, HUMAN, (r.x + 26, r.centery), 16)
        phase_txt = "ALL DONE" if h.finished_all else f"PHASE {h.phase + 1}"
        theme.text(surf, phase_txt, (r.x + 52, r.y + 7), 17, theme.ACCENT)
        theme.text(surf, describe_phase(min(h.phase, NUM_PHASES - 1)), (r.x + 52, r.y + 29), 15, bold=False)
        theme.text(surf, f"{h.score} pts", (r.right - 14, r.y + 8), 15, theme.TEXT_DIM, anchor="topright")
        if h.laid_down:
            self._chip(surf, "LAID DOWN", (r.right - 104, r.y + 28), theme.SUCCESS, size=10)

        # Status pill
        status, color = self._status()
        sr = pygame.Rect(504, BAR_Y, 756, 52)
        theme.rounded(surf, theme.BG_DARK, sr, 14)
        if active:
            self._chip(surf, "YOUR TURN", (sr.x + 14, sr.y + 14), theme.ACCENT, size=13)
            theme.text(surf, status, (sr.x + 128, sr.centery), 17, color, anchor="midleft")
        else:
            theme.text(surf, status, (sr.x + 18, sr.centery), 17, color, anchor="midleft")

        # Hand
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
            img, off = card_with_shadow(c, rect.w, rect.h, lift=12 if c.id in self.selected else 0)
            surf.blit(img, rect)
            if c.id in self.selected:
                theme.rounded(surf, theme.ACCENT, rect.inflate(6, 6), 14, 4)
            elif c.id == self.new_card_id:
                theme.rounded(surf, theme.INFO, rect.inflate(6, 6), 14, 3)

        # Buttons
        drawn = self.my_turn and g.has_drawn
        self.btn_lay.enabled = drawn and not h.laid_down
        self.btn_discard.enabled = drawn and len(self.selected) == 1
        self.btn_hint.visible = self.app.settings.hints
        self.btn_hint.enabled = self.my_turn
        self.btn_sort.label = "Sort: 1-12" if self.app.settings.sort_by == "number" else "Sort: Color"
        for b in (self.btn_lay, self.btn_discard, self.btn_sort, self.btn_hint):
            b.draw(surf)
        if self.selected:
            theme.text(surf, f"{len(self.selected)} selected", (1153, 760), 14, theme.TEXT_DIM, anchor="center")

    def _status(self) -> tuple[str, tuple]:
        g = self.game
        if g.round_over:
            return "Round over", theme.TEXT
        if g.current != HUMAN:
            return f"{self.name(g.current)} is thinking…", theme.TEXT_DIM
        if self.choosing_skip:
            return "Click the opponent you want to skip (Esc to cancel)", theme.DANGER
        if not g.has_drawn:
            return "Draw from the deck or take the discard", theme.TEXT
        if not self.human.laid_down:
            plan = plan_phase(self.human.requirements, self.human.hand)
            if plan.complete and self.app.settings.hints:
                return "You can complete your phase! Select the cards and Lay Down", theme.SUCCESS
            return "Lay down your phase, or select a card to discard", theme.TEXT
        return "Add cards to table groups, then discard one", theme.TEXT

    def _draw_flash(self, surf):
        msg, t = self.flash
        f = theme.font(18)
        w = f.size(msg)[0] + 40
        r = pygame.Rect(0, 0, w, 46)
        r.center = (TABLE.centerx, TABLE.bottom - 36)
        alpha = int(255 * min(1.0, t / 0.3))
        theme.alpha_rect(surf, (*theme.BG_DARK, min(235, alpha)), r, 23)
        img = f.render(msg, True, theme.ACCENT)
        img.set_alpha(alpha)
        surf.blit(img, img.get_rect(center=r.center))

    def _draw_overlay(self, surf):
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((10, 14, 24, 200))
        surf.blit(shade, (0, 0))
        cx = theme.WIDTH // 2
        g = self.game
        if self.overlay == "pause":
            theme.rounded(surf, theme.PANEL, (cx - 200, 230, 400, 330), 20)
            theme.text(surf, "PAUSED", (cx, 280), 34, theme.ACCENT, heavy=True, anchor="center")
        else:
            panel = pygame.Rect(cx - 360, 110, 720, 610)
            theme.rounded(surf, theme.PANEL, panel, 22)
            if self.overlay == "game":
                winner = g.players[g.winner]
                title = "YOU WIN!" if g.winner == HUMAN else f"{winner.name.upper()} WINS"
                color = theme.ACCENT if g.winner == HUMAN else theme.TEXT
            else:
                went = g.players[g.went_out]
                title = f"ROUND {g.round} COMPLETE"
                color = theme.ACCENT
            theme.shadow_text(surf, title, (cx, 168), 44, color, shadow=theme.BG_DARK, offset=4)
            if self.overlay == "round":
                who = "You went out" if g.went_out == HUMAN else f"{went.name} went out"
                theme.text(surf, who, (cx, 214), 18, theme.TEXT_DIM, anchor="center")
            heads = [("PLAYER", panel.x + 90), ("NEXT PHASE", panel.x + 330), ("ROUND", panel.x + 500),
                     ("TOTAL", panel.x + 620)]
            for label, x in heads:
                theme.text(surf, label, (x, 250), 13, theme.TEXT_FAINT, anchor="midleft" if label == "PLAYER"
                           else "center")
            for k, i in enumerate(g.standings()):
                p = g.players[i]
                y = 280 + k * 56
                row = pygame.Rect(panel.x + 30, y, panel.w - 60, 48)
                theme.rounded(surf, theme.PANEL_LIGHT if i == HUMAN else theme.BG_DARK, row, 12)
                self._avatar(surf, i, (row.x + 30, row.centery), 16)
                theme.text(surf, p.name, (row.x + 60, row.centery), 19, anchor="midleft")
                if p.difficulty:
                    self._chip(surf, p.difficulty.upper(), (row.x + 150, row.centery - 10),
                               DIFF_COLORS[p.difficulty], size=10)
                done = "ALL DONE" if p.finished_all else f"{p.phase + 1}"
                theme.text(surf, done, (panel.x + 330, row.centery), 20, anchor="center")
                if p.completed_this_round:
                    tx, ty = panel.x + 372, row.centery
                    pygame.draw.polygon(surf, theme.SUCCESS, [(tx - 7, ty + 5), (tx + 7, ty + 5), (tx, ty - 7)])
                pts = g.round_points.get(i, 0)
                theme.text(surf, f"+{pts}", (panel.x + 500, row.centery), 19,
                           theme.TEXT_DIM if pts else theme.SUCCESS, anchor="center")
                theme.text(surf, str(p.score), (panel.x + 620, row.centery), 20, anchor="center")
        for b in self.overlay_buttons:
            b.draw(surf)
