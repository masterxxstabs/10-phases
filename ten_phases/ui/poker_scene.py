"""The Texas Hold'em table, in the same handheld style.

  top screen     hand counter and blinds, the five shared cards and the pot, the deck
  bottom screen  the other players' seats, then your two cards, your stack, and the
                 betting controls: FOLD / CHECK or CALL / RAISE, plus a bet picker
                 (slider, - and +, and MIN, 1/2 POT, POT and ALL IN shortcuts)
"""

from __future__ import annotations

import math
import random

import pygame

from ..names import pick_ai_names
from ..poker import ai as poker_ai
from ..poker.ai import PokerAI
from ..poker.engine import HANDS_PER_LEVEL, PokerGame, PokerPlayer, RuleError, describe, evaluate, key_cards
from ..settings import SPEED_DELAYS
from . import profile_art, sfx, theme
from .card_art import card_with_shadow
from .game_scene import DIFF_COLORS, FlyingCard
from .menus import Scene, backdrop, status_bar
from .admin import AdminPanel
from .table_skins import TableSkins
from .widgets import Button
from .xp import XpTracker

HUMAN = 0
SPLIT_Y = 222
INFO_BOX = pygame.Rect(20, 14, 300, 194)
BOARD_BOX = pygame.Rect(340, 14, 600, 194)
DECK_BOX = pygame.Rect(960, 14, 300, 194)
SEATS = pygame.Rect(20, 238, 1240, 250)
MY_BOX = pygame.Rect(20, 500, 1240, 264)
SLIDER = pygame.Rect(668, 590, 480, 48)
HOLE_W, HOLE_H = 100, 150
BOARD_W, BOARD_H = 72, 108
RESULT_COLORS = {"won": theme.SUCCESS, "split": theme.INFO, "lost": theme.DANGER, "fold": theme.TEXT_FAINT}
RESULT_LETTER = {"won": "W", "split": "S", "lost": "L", "fold": "F"}


class Bubble:
    def __init__(self, player, text, color, ttl=1.8):
        self.player, self.text, self.color, self.ttl = player, text, color, ttl


class ChipFly:
    """A little stack of chips sliding across the table (bets into the pot, the pot to the winner)."""

    def __init__(self, start, end, count: int = 3, delay: float = 0.0, duration: float = 0.45):
        self.start, self.end = start, end
        self.count = max(1, min(6, count))
        self.t = -delay
        self.duration = duration

    @property
    def done(self) -> bool:
        return self.t >= self.duration + 0.05 * self.count

    def draw(self, surf):
        for k in range(self.count):
            u = (self.t - 0.05 * k) / self.duration
            if u < 0 or u > 1:
                continue
            e = 1 - (1 - u) ** 3
            x = self.start[0] + (self.end[0] - self.start[0]) * e
            y = self.start[1] + (self.end[1] - self.start[1]) * e - 30 * math.sin(math.pi * u)
            theme.chip(surf, (int(x), int(y)), 10, theme.CHIP_COLORS[k % 3])


class PokerScene(Scene):
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
            players = [PokerPlayer("YOU", is_human=True)] + [PokerPlayer(n, difficulty=d) for n, d in zip(names, diffs)]
            self.game = PokerGame(players)
            self.ais = {i + 1: PokerAI(d) for i, d in enumerate(diffs)}
        self.skins = TableSkins(self)
        self.admin = AdminPanel(self)
        self.xp = XpTracker(self, "poker")
        self.xp.corner = (MY_BOX.right - 256, MY_BOX.bottom - 46)   # bottom-right, clear of the buttons
        self.delay = SPEED_DELAYS[s.ai_speed]
        self.anims: list[FlyingCard] = []
        self.chips: list[ChipFly] = []
        self.bubbles: list[Bubble] = []
        self.flash: tuple[str, float] | None = None
        self.splash: tuple[str, str, float, float] | None = ("TEXAS HOLD'EM",
                                                             f"MOST CHIPS AFTER {self.game.hands_per_game} HANDS WINS",
                                                             1.8, 1.8)
        self.overlay: str | None = None
        self._pending_overlay = False
        self.ai_timer = 0.9
        self.settle_timer = 0.0
        self.hint_action: str | None = None
        self._banked: int | None = None
        self.raise_to = 0              # the amount picked in the bet picker
        self._picked_for: tuple | None = None
        self.dragging = False
        self.hint_rng = random.Random()
        self.pre: str | None = None     # a move queued for your turn: check_fold, check or call_any
        self.typed = ""                 # digits typed to set the bet
        self.typed_timer = 0.0
        self.fast = False               # fast-forward the rest of a hand you've folded
        self.last_hand = ""

        self.btn_fold = Button((600, 518, 150, 56), "FOLD", lambda: self.act("fold"), size=20)
        self.btn_call = Button((760, 518, 200, 56), "CHECK", self.check_or_call, size=20)
        self.btn_raise = Button((970, 518, 250, 56), "RAISE", lambda: self.act("raise"), "ACCENT", "OUTLINE", 20)
        self.btn_minus = Button((600, 590, 58, 48), "-", lambda: self.nudge(-1), size=26)
        self.btn_plus = Button((1162, 590, 58, 48), "+", lambda: self.nudge(1), size=26)
        self.quick = [Button((600 + k * 158, 652, 148, 44), label, lambda f=f: self.pick(f), size=15)
                      for k, (label, f) in enumerate((("MIN", "min"), ("1/2 POT", 0.5), ("POT", 1.0),
                                                      ("ALL IN", "all")))]
        self.pre_buttons = [Button((600 + k * 210, 518, 200, 56), label, lambda w=what: self.toggle_pre(w), size=16)
                            for k, (label, what) in enumerate((("CHECK / FOLD", "check_fold"), ("CHECK", "check"),
                                                               ("CALL ANY", "call_any")))]
        self.btn_fast = Button((600, 518, 620, 56), "FAST FORWARD TO THE NEXT HAND", self.fast_forward, size=18)
        self.btn_hint = Button((40, 706, 120, 44), "HINT", self.do_hint, size=15)
        self.btn_menu = Button((170, 706, 120, 44), "MENU", lambda: self._set_overlay("pause"), size=15)
        self.action_buttons = [self.btn_fold, self.btn_call, self.btn_raise]
        self.picker_buttons = [self.btn_minus, self.btn_plus] + self.quick
        self.buttons = self.action_buttons + self.picker_buttons + [self.btn_hint, self.btn_menu] + \
            self.pre_buttons + [self.btn_fast]
        self.overlay_buttons: list[Button] = []
        self._consume_events()
        sfx.play("shuffle")

    # ================================================================== helpers

    @property
    def me(self) -> PokerPlayer:
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
        if self.admin.blocking:
            return True
        if self.anims or self.splash is not None:
            return True
        return self.overlay is not None and not (self.overlay == "pause" and self.networked)

    def my_turn(self) -> bool:
        g = self.game
        return not self.busy and g.phase == "playing" and g.current == HUMAN

    def name(self, i) -> str:
        return "YOU" if i == HUMAN else self.game.players[i].name

    def role(self, i: int):
        p = self.game.players[i]
        return (p.difficulty.upper(), DIFF_COLORS[p.difficulty]) if p.difficulty else ("PLAYER", theme.CARD_WHITE)

    def error(self, msg: str):
        self.flash = (msg, 2.6)
        sfx.play("error")

    def bubble(self, i, text, color=theme.TEXT, ttl=1.8):
        self.bubbles = [b for b in self.bubbles if b.player != i]
        self.bubbles.append(Bubble(i, text, color, ttl))

    def others(self) -> list[int]:
        return list(range(1, len(self.game.players)))

    def seat_rect(self, i: int) -> pygame.Rect:
        others = self.others()
        n, gap = max(1, len(others)), 14
        w = min(400, (SEATS.w - (n - 1) * gap) // n)
        x0 = SEATS.x + (SEATS.w - (n * w + (n - 1) * gap)) // 2
        return pygame.Rect(x0 + others.index(i) * (w + gap), SEATS.y, w, SEATS.h)

    def hole_rect(self, i: int, k: int) -> pygame.Rect:
        if i == HUMAN:
            return pygame.Rect(MY_BOX.x + 30 + k * 112, MY_BOX.y + 24, HOLE_W, HOLE_H)
        r = self.seat_rect(i)
        return pygame.Rect(r.x + 14 + k * 46, r.y + 70, 56, 84)

    def board_rect(self, k: int) -> pygame.Rect:
        x0 = BOARD_BOX.centerx - (5 * BOARD_W + 4 * 10) // 2
        return pygame.Rect(x0 + k * (BOARD_W + 10), BOARD_BOX.y + 42, BOARD_W, BOARD_H)

    def deck_rect(self) -> pygame.Rect:
        return pygame.Rect(DECK_BOX.x + 30, DECK_BOX.y + 50, 72, 108)

    def bet_spot(self, i: int) -> tuple[int, int]:
        if i == HUMAN:
            return MY_BOX.x + 300, MY_BOX.y + 70
        r = self.seat_rect(i)
        return r.x + 30, r.bottom - 34

    def pot_spot(self) -> tuple[int, int]:
        return BOARD_BOX.centerx - 40, BOARD_BOX.bottom - 22

    # ================================================================== the bet picker

    def raise_bounds(self) -> tuple[int, int] | None:
        g = self.game
        if g.phase != "playing" or g.current != HUMAN:
            return None
        return g.raise_range(HUMAN)

    def _sync_picker(self):
        """Start the picker at the minimum raise whenever a new decision comes up."""
        g = self.game
        key = (g.round, g.street, g.current, g.current_bet)
        bounds = self.raise_bounds()
        if key != self._picked_for:
            self._picked_for = key
            if bounds:
                self.raise_to = bounds[0]
        if bounds:
            self.raise_to = max(bounds[0], min(bounds[1], self.raise_to))

    def set_raise(self, amount: int):
        bounds = self.raise_bounds()
        if not bounds:
            return
        new = max(bounds[0], min(bounds[1], int(amount)))
        if new != self.raise_to:
            self.raise_to = new
            sfx.play("select")

    def nudge(self, step: int):
        self.set_raise(self.raise_to + step)

    def pick(self, how):
        bounds = self.raise_bounds()
        if not bounds:
            return
        g = self.game
        if how == "min":
            self.set_raise(bounds[0])
        elif how == "all":
            self.set_raise(bounds[1])
        else:
            pot_after_call = g.pot_total() + g.to_call(HUMAN)
            self.set_raise(g.current_bet + int(pot_after_call * how))

    def _slider_value(self, x: int) -> int:
        lo, hi = self.raise_bounds()
        u = max(0.0, min(1.0, (x - SLIDER.x - 14) / max(1, SLIDER.w - 28)))
        return round(lo + (hi - lo) * u)

    # ================================================================== events -> animation

    def _consume_events(self):
        g = self.game
        stagger = 0.0
        for ev in g.pop_events():
            self.xp.event(ev)
            k = ev.kind
            i = ev.player
            if k == "round_start":
                self.bubbles = []
                self.hint_action = None
                self.pre = None
                self.fast = False
                sfx.play("shuffle")
            elif k == "blind":
                self.bubble(i, f"{ev.name.upper()} BLIND {ev.amount}", theme.TEXT_DIM, 1.2)
                self.chips.append(ChipFly(self.seat_center(i), self.bet_spot(i), 2))
                sfx.play("click")
            elif k == "deal" and i is not None and i < len(g.players):
                sk = self.skins.seat(i)
                for n in range(2):
                    card = ev.cards[n] if i == HUMAN and n < len(ev.cards) else None
                    self.anims.append(FlyingCard(card, self.deck_rect(), self.hole_rect(i, n), 0.28, stagger,
                                                 hide_id=card.id if card is not None else None,
                                                 face=sk[0], back=sk[1]))
                    stagger += 0.06
                sfx.play("draw")
            elif k == "turn" and i == HUMAN:
                sfx.play("turn")
                self.hint_action = None
            elif k == "fold":
                self.bubble(i, "FOLD", theme.TEXT_FAINT)
                sfx.play("deselect")
            elif k == "check":
                self.bubble(i, "CHECK", theme.TEXT)
                sfx.play("click")
            elif k in ("call", "bet", "raise"):
                p = g.players[i] if i is not None and i < len(g.players) else None
                all_in = p is not None and p.all_in
                text = {"call": f"CALL {ev.amount}", "bet": f"BET {ev.amount}", "raise": f"RAISE TO {ev.amount}"}[k]
                self.bubble(i, "ALL IN!" if all_in else text, theme.DANGER if all_in else
                            theme.ACCENT if k != "call" else theme.TEXT)
                self.chips.append(ChipFly(self.seat_center(i), self.bet_spot(i), 2 if k == "call" else 4))
                sfx.play("coin" if k == "call" else "lay")
            elif k == "board":
                for p_i in range(len(g.players)):
                    if g.players[p_i].total_in:
                        self.chips.append(ChipFly(self.bet_spot(p_i), self.pot_spot(), 2, stagger))
                start = len(g.board) - len(ev.cards)
                for n, c in enumerate(ev.cards):
                    slot = max(0, min(4, start + n))
                    self.anims.append(FlyingCard(c, self.deck_rect(), self.board_rect(slot), 0.3, stagger + 0.25,
                                                 hide_id=c.id))
                    stagger += 0.12
                self.bubble("board", {"flop": "THE FLOP", "turn": "THE TURN", "river": "THE RIVER"}.get(ev.name, ""),
                            theme.ACCENT, 1.4)
                sfx.play("draw")
            elif k == "showdown":
                if ev.name:
                    self.bubble(i, ev.name, theme.INFO, 3.0)
                sfx.play("select")
            elif k == "win":
                self.chips.append(ChipFly(self.pot_spot(), self.seat_center(i), 5, stagger + 0.3, 0.6))
                self.bubble(i, f"WINS {ev.amount}!" + (f" {ev.name}" if ev.name and i != HUMAN else ""),
                            theme.SUCCESS, 3.2)
                if i == HUMAN:
                    self.splash = ("YOU WIN!", f"+{ev.amount} CHIPS" + (f" - {ev.name}" if ev.name else ""), 1.4, 1.4)
                    sfx.play("round_win")
                else:
                    sfx.play("coin")
            elif k == "settled":
                if g.last_wins:
                    w = max(g.last_wins, key=lambda x: x["amount"])
                    self.last_hand = f"Last hand: {self.name(w['player']).title()} won {w['amount']}" + \
                        (f" ({w['hand'].lower()})" if w["hand"] else "")
                showdown = len(g.revealed) > 1
                self.settle_timer = 3.6 if showdown else 2.2
                if g.players[HUMAN].in_hand and not any(w["player"] == HUMAN for w in g.last_wins) and \
                        not g.players[HUMAN].folded:
                    sfx.play("round_end")
            elif k == "game_over":
                self._pending_overlay = True

    def seat_center(self, i) -> tuple[int, int]:
        if i is None:
            return self.pot_spot()
        if i == HUMAN:
            return MY_BOX.x + 120, MY_BOX.y + 100
        return self.seat_rect(i).center

    # ================================================================== actions

    def check_or_call(self):
        self.act("call" if self.game.to_call(HUMAN) else "check")

    def act(self, action: str):
        if not self.my_turn():
            return
        if action not in self.game.legal_actions(HUMAN):
            self.error({"raise": "You can't raise right now.", "check": "There's a bet - call or fold."}.get(
                action, "Not now."))
            return
        try:
            self.game.act(HUMAN, action, self.raise_to if action == "raise" else 0)
        except RuleError as e:
            self.error(str(e))
            return
        self.hint_action = None
        self.typed = ""
        self._consume_events()
        self.ai_timer = self.delay + 0.3

    # ================================================================== quality of life

    def can_queue(self) -> bool:
        """Can you queue a move? (You're in the hand, it's not your turn yet, and betting is on.)"""
        g = self.game
        p = self.me
        return g.phase == "playing" and p.live and not p.all_in and g.current != HUMAN and \
            not getattr(self.game, "pending", False)

    def toggle_pre(self, what: str):
        if not self.can_queue():
            return
        self.pre = None if self.pre == what else what
        sfx.play("select" if self.pre else "deselect")

    def _run_pre(self):
        """Your turn came up with a move queued: make it (a queued CHECK waits if someone bet)."""
        what, self.pre = self.pre, None
        to_call = self.game.to_call(HUMAN)
        if what == "check_fold":
            self.act("check" if not to_call else "fold")
        elif what == "check" and not to_call:
            self.act("check")
        elif what == "call_any":
            self.act("call" if to_call else "check")
        elif what == "check":
            self.flash = ("Someone bet, so your CHECK was cancelled. Your move!", 2.6)
            sfx.play("turn")

    def can_fast_forward(self) -> bool:
        g = self.game
        return not self.networked and g.phase == "playing" and not self.me.live and not self.fast

    def fast_forward(self):
        if self.can_fast_forward():
            self.fast = True
            self.ai_timer = min(self.ai_timer, 0.1)
            sfx.play("select")

    def type_digit(self, d: str):
        if not self.raise_bounds() or not self.my_turn():
            return
        self.typed = (self.typed + d)[-5:]
        self.typed_timer = 2.0
        self.set_raise(int(self.typed))

    def pot_odds(self) -> int | None:
        """Percent of the time a call has to win to pay off (None when there's nothing to call)."""
        g = self.game
        to_call = g.to_call(HUMAN) if g.phase == "playing" else 0
        if not to_call:
            return None
        return round(100 * to_call / (g.pot_total() + to_call))

    def do_hint(self):
        if not self.my_turn():
            return
        action, reason = poker_ai.hint(self.game, HUMAN, self.hint_rng)
        self.hint_action = action
        if action == "raise":
            self.pick(0.5)
        self.flash = (f"Hint: {reason}.", 3.6)
        sfx.play("turn")

    def run_ai(self):
        g = self.game
        i = g.current
        if g.phase != "playing" or i not in self.ais:
            return
        action, amount = self.ais[i].choose(g, i)
        try:
            g.act(i, action, amount)
        except RuleError:
            g.act(i, "check" if g.to_call(i) == 0 else "fold")   # never let a computer stall the table
        self._consume_events()
        self.ai_timer = (self.delay * 1.3 + 0.3) * (0.12 if self.fast else 1.0)

    # ================================================================== network

    def _pump_network(self):
        if self.host is not None:
            self.host.pump()
            while self.session.notices:
                self.bubble("board", self.session.notices.pop(0), theme.DANGER, 3.0)
                sfx.play("skip")
        if self.client is not None:
            for msg in self.client.poll():
                t = msg["t"]
                if t == "error":
                    self.error(msg.get("msg", "That move wasn't allowed."))
                elif t == "notice":
                    self.bubble("board", msg.get("msg", ""), theme.DANGER, 3.0)
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
        restart = lambda: self.app.go(PokerScene(self.app))  # noqa: E731
        if kind == "game":
            sfx.play("game_win" if HUMAN in self.game.winners() else "game_lose")
            self.xp.game_end(HUMAN in self.game.winners())
            if self._banked is None:
                self._banked = max(0, self.me.chips)
                self.app.settings.chip_bank += self._banked
                self.app.settings.save()
            if self.host is not None:
                again = Button((cx - 290, 650, 270, 58), "BACK TO LOBBY", self.to_lobby, size=20, **primary)
            elif self.client is not None:
                again = Button((cx - 290, 650, 270, 58), "WAIT FOR HOST", lambda: None, size=18)
                again.enabled = False
            else:
                again = Button((cx - 290, 650, 270, 58), "PLAY AGAIN", restart, size=22, **primary)
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
                options = [("RESUME", resume), ("CUSTOMIZE", self.customize), ("RESTART", restart),
                           ("MAIN MENU", self.to_menu)]
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
        if event.type == pygame.KEYDOWN:
            big = self.game.blinds[1]
            if event.key == pygame.K_ESCAPE:
                self._set_overlay("pause")
            elif event.key == pygame.K_f:
                self.act("fold")
            elif event.key in (pygame.K_c, pygame.K_k, pygame.K_SPACE):
                self.check_or_call()
            elif event.key in (pygame.K_r, pygame.K_RETURN):
                self.act("raise")
            elif event.key in (pygame.K_LEFT, pygame.K_DOWN):
                self.nudge(-1 if event.mod & pygame.KMOD_SHIFT else -big)
            elif event.key in (pygame.K_RIGHT, pygame.K_UP):
                self.nudge(1 if event.mod & pygame.KMOD_SHIFT else big)
            elif event.unicode and event.unicode.isdigit():
                self.type_digit(event.unicode)
            elif event.key == pygame.K_BACKSPACE and self.typed:
                self.typed = self.typed[:-1]
                if self.typed:
                    self.set_raise(int(self.typed))
            return
        if self.raise_bounds() and self.my_turn():
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and SLIDER.collidepoint(event.pos):
                self.dragging = True
                self.set_raise(self._slider_value(event.pos[0]))
                return
            if event.type == pygame.MOUSEMOTION and self.dragging:
                self.set_raise(self._slider_value(event.pos[0]))
                return
            if event.type == pygame.MOUSEWHEEL and event.y:
                self.nudge(self.game.blinds[1] * (1 if event.y > 0 else -1))
                return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        for b in self.buttons:
            if b.visible and b.handle(event):
                return

    # ================================================================== update

    def update(self, dt: float):
        super().update(dt)
        self.admin.update(dt)
        self.xp.update(dt)
        self._pump_network()
        if self.game.events:
            self._consume_events()
        speed = 4.0 if self.fast else 1.0
        for a in self.anims:
            a.t += dt * speed
        self.anims = [a for a in self.anims if not a.done]
        for c in self.chips:
            c.t += dt * speed
        if self.typed_timer:
            self.typed_timer = max(0.0, self.typed_timer - dt)
            if not self.typed_timer:
                self.typed = ""
        if self.pre and not self.can_queue() and not self.my_turn():
            self.pre = None
        self.chips = [c for c in self.chips if not c.done]
        for b in self.bubbles:
            b.ttl -= dt
        self.bubbles = [b for b in self.bubbles if b.ttl > 0]
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None
        if self.splash:
            t, s, left, total = self.splash
            self.splash = (t, s, left - dt, total) if left > dt else None
        self._sync_picker()
        if self.pre and self.my_turn():
            self._run_pre()
        if self._pending_overlay and not self.anims and not self.splash:
            self._set_overlay("game")
            return
        g = self.game
        if self.flow_blocked or g.game_over:
            return
        if g.phase == "settled" and self.client is None:
            # Show the cards for a moment, then deal the next hand (the host does this for everyone).
            self.settle_timer -= dt * (3 if self.fast else 1)
            if self.settle_timer <= 0:
                if not self.networked and self.me.chips == 0:
                    g.end_now()   # you're out: no need to watch the computers play on
                    self._consume_events()
                    return
                g.next_round()
                self._consume_events()
            return
        self.ai_timer -= dt
        if self.ai_timer <= 0:
            self.run_ai()

    # ================================================================== drawing

    def draw(self, surf):
        backdrop(surf, self.clock, SPLIT_Y)
        hidden = {a.hide_id for a in self.anims if a.hide_id is not None}
        self._draw_info(surf)
        self._draw_board(surf, hidden)
        self._draw_deck(surf)
        for i in self.others():
            self._draw_seat(surf, i)
        self._draw_me(surf, hidden)
        self._draw_key_cards(surf, hidden)
        for a in self.anims:
            a.draw(surf)
        for c in self.chips:
            c.draw(surf)
        self._draw_bubbles(surf)
        if not self.overlay and not self.splash:
            mouse = pygame.mouse.get_pos()
            for i in self.others():
                if self.seat_rect(i).collidepoint(mouse):
                    self._draw_hover(surf, i)
                    break
        status_bar(surf, self.flash[0] if self.flash else self._status())
        if self.splash:
            self._draw_splash(surf)
        if self.overlay:
            self._draw_overlay(surf)
        self.xp.draw(surf)
        self.admin.draw(surf)

    def _status(self) -> str:
        g = self.game
        if g.game_over:
            return "That's the last hand!"
        if g.phase == "settled":
            return "Next hand coming up..."
        if not self.me.in_hand:
            return "You're out of chips - watch the rest of the game."
        if self.me.folded:
            return "You folded. Wait for the next hand."
        if self.my_turn():
            to_call = g.to_call(HUMAN)
            if to_call:
                odds = self.pot_odds()
                return f"Your turn: CALL {to_call} (C) into a pot of {g.pot_total()} - worth it if you win " \
                       f"{odds}% of the time. FOLD (F) or RAISE (R). Type a number to bet."
            return "Your turn: CHECK (C), or pick a bet and RAISE (R). Type a number or use the arrows."
        if self.pre and self.me.live:
            return {"check_fold": "Queued: CHECK, or FOLD if someone bets.", "check": "Queued: CHECK.",
                    "call_any": "Queued: CALL whatever the bet is."}[self.pre]
        if g.current is not None and g.current != HUMAN:
            return f"{self.name(g.current)} is thinking..."
        return "Wait until it is your turn."

    def _chip(self, surf, label, pos, color, fg="OUTLINE", size=11):
        img = theme.pixel_surface(label, size, fg, None)
        r = pygame.Rect(pos[0], pos[1], img.get_width() + 12, img.get_height() + 4)
        theme.rounded(surf, theme.OUTLINE, r.move(0, 2), r.h // 2)
        theme.rounded(surf, color, r, r.h // 2)
        surf.blit(img, img.get_rect(center=r.center))
        return r

    def _bet_stack(self, surf, base, amount: int, r: int = 10):
        if amount <= 0:
            return
        for k in range(min(8, 1 + amount // max(1, self.game.blinds[1]))):
            theme.chip(surf, (base[0], base[1] - k * 4), r, theme.CHIP_COLORS[k % 3])
        theme.ptext(surf, str(amount), (base[0] + r + 6, base[1] - 10), 16, theme.ACCENT)

    def _dealer_button(self, surf, center, label="D"):
        pygame.draw.circle(surf, theme.OUTLINE, (center[0], center[1] + 2), 13)
        pygame.draw.circle(surf, theme.CARD_WHITE, center, 12)
        theme.ptext(surf, label, center, 12 if len(label) == 1 else 10, theme.OUTLINE, None, anchor="center")

    def _draw_info(self, surf):
        g = self.game
        theme.panel(surf, INFO_BOX)
        theme.ptext(surf, "TEXAS HOLD'EM", (INFO_BOX.x + 16, INFO_BOX.y + 12), 22, theme.ACCENT)
        theme.ptext(surf, f"HAND {min(max(1, g.round), g.hands_per_game)} OF {g.hands_per_game}",
                    (INFO_BOX.x + 16, INFO_BOX.y + 46), 20)
        small, big = g.blinds
        theme.ptext(surf, f"BLINDS {small}/{big}", (INFO_BOX.x + 16, INFO_BOX.y + 76), 18, theme.INFO)
        left = HANDS_PER_LEVEL - (max(1, g.round) - 1) % HANDS_PER_LEVEL
        lines = [(f"Blinds double in {left} hand{'s' if left != 1 else ''}", theme.TEXT_DIM)]
        if self.last_hand:
            lines.append((self.last_hand, theme.TEXT))
        res = self.me.results
        if res:
            won = sum(r in ("won", "split") for r in res)
            lines.append((f"You've won {won} of {len(res)} hand{'s' if len(res) != 1 else ''}", theme.TEXT_DIM))
        else:
            lines.append(("Most chips at the end wins", theme.TEXT_DIM))
        f = theme.font(14, False)
        for k, (line, color) in enumerate(lines[:3]):
            while f.size(line)[0] > INFO_BOX.w - 32 and len(line) > 4:
                line = line[:-4].rstrip() + "..."
            theme.text(surf, line, (INFO_BOX.x + 18, INFO_BOX.y + 108 + k * 24), 14, color, bold=False)

    def _draw_board(self, surf, hidden):
        g = self.game
        theme.panel(surf, BOARD_BOX)
        label = {"preflop": "BEFORE THE FLOP", "flop": "THE FLOP", "turn": "THE TURN", "river": "THE RIVER"}
        theme.ptext(surf, label.get(g.street, ""), (BOARD_BOX.x + 16, BOARD_BOX.y + 12), 16, theme.TEXT_DIM)
        for k in range(5):
            r = self.board_rect(k)
            card = g.board[k] if k < len(g.board) else None
            if card is None or card.id in hidden:
                theme.rounded(surf, theme.INNER, r, 10)
                theme.rounded(surf, theme.PANEL_LIGHT, r, 10, 2)
                continue
            img, _ = card_with_shadow(card, r.w, r.h)
            surf.blit(img, r)
        pot = g.pot_total() if g.phase == "playing" else 0   # once settled, the pot has been paid out
        px, py = self.pot_spot()
        if pot:
            for k in range(min(6, 1 + pot // max(1, g.blinds[1] * 2))):
                theme.chip(surf, (px - 30 + (k % 3) * 8, py - (k // 3) * 6), 10, theme.CHIP_COLORS[k % 3])
            theme.ptext(surf, f"POT {pot}", (px, py), 22, theme.ACCENT, anchor="midleft")
        if g.phase == "settled" and g.last_wins:
            w = max(g.last_wins, key=lambda x: x["amount"])
            msg = f"{self.name(w['player'])} {'WIN' if w['player'] == HUMAN else 'WINS'}" + \
                (f" WITH {w['hand']}" if w["hand"] else "")
            theme.ptext(surf, msg, (BOARD_BOX.right - 16, BOARD_BOX.y + 12), 14, theme.SUCCESS, anchor="topright")

    def _draw_deck(self, surf):
        theme.panel(surf, DECK_BOX)
        for k in range(4):
            img, _ = card_with_shadow(None, 72, 108)
            surf.blit(img, self.deck_rect().move(k * 3, -k * 3))
        theme.ptext(surf, "DECK", (DECK_BOX.x + 140, DECK_BOX.y + 54), 18, theme.ACCENT)
        theme.ptext(surf, f"{len(self.game.deck)} CARDS", (DECK_BOX.x + 140, DECK_BOX.y + 80), 16)
        theme.text(surf, "52-card deck", (DECK_BOX.x + 140, DECK_BOX.y + 108), 14, theme.TEXT_DIM, bold=False)
        theme.text(surf, "Colors are suits", (DECK_BOX.x + 140, DECK_BOX.y + 130), 14, theme.TEXT_DIM, bold=False)

    def _hole_images(self, i: int, w: int, h: int):
        """The player's two cards as they should look to you right now (or None while nothing is dealt)."""
        g = self.game
        p = g.players[i]
        face, back = self.skins.seat(i)
        show = i == HUMAN or i in g.revealed
        out = []
        for c in p.hole:
            known = show and c.value is not None and c.color is not None
            img, _ = card_with_shadow(c if known else None, w, h, face=face, back=back)
            out.append((c, img))
        return out

    def _draw_seat(self, surf, i: int):
        g = self.game
        p = g.players[i]
        r = self.seat_rect(i)
        active = g.current == i and g.phase == "playing"
        winner = g.phase == "settled" and any(w["player"] == i for w in g.last_wins)
        edge = theme.ACCENT if active else theme.SUCCESS if winner else theme.PANEL_EDGE
        theme.panel(surf, r, edge=edge, edge_w=3 if active or winner else 2)
        bob = math.sin(self.clock * 6) * 2 if active else 0
        prof = profile_art.seat_profile(self, i)
        profile_art.avatar(surf, (r.x + 30, int(r.y + 30 + bob)), 22, prof, i, level=True)
        name_r = theme.ptext(surf, p.name, (r.x + 60, r.y + 8), 18, profile_art.name_rgb(prof, self.clock))
        profile_art.name_tag(surf, name_r, prof, 14)
        label, color = self.role(i)
        self._chip(surf, label, (r.x + 60, r.y + 32), color)
        cr = theme.ptext(surf, str(p.chips), (r.right - 12, r.y + 8), 20, theme.ACCENT, anchor="topright")
        theme.chip(surf, (cr.x - 14, cr.centery + 1), 9, theme.ACCENT)
        if i == g.button and p.in_hand:
            self._dealer_button(surf, (r.right - 22, r.y + 50))
        if not p.in_hand and g.phase != "game_over":
            theme.ptext(surf, "OUT OF CHIPS", (r.centerx, r.y + 110), 16, theme.TEXT_FAINT, anchor="center")
            return
        for k, (c, img) in enumerate(self._hole_images(i, 56, 84)):
            if p.folded:
                img = img.copy()
                img.set_alpha(90)
            surf.blit(img, self.hole_rect(i, k))
        tx = r.x + 124
        status = "FOLDED" if p.folded else "ALL IN" if p.all_in else p.last_action
        if status:
            theme.ptext(surf, status, (tx, r.y + 80), 15, theme.DANGER if p.all_in else theme.TEXT_DIM
                        if p.folded else theme.TEXT)
        if i in g.revealed and len(g.board) >= 3 and not p.folded:
            name = describe(evaluate(p.hole + g.board))
            theme.ptext(surf, name, (tx, r.y + 104), 13, theme.INFO)
        self._bet_stack(surf, self.bet_spot(i), p.bet)

    def _draw_key_cards(self, surf, hidden):
        """Glow around the cards that make your hand, and the winning hand at a showdown."""
        g = self.game
        if len(g.board) < 3 or self.anims:
            return
        glows = []
        if g.phase == "settled" and len(g.revealed) > 1 and g.last_wins:
            w = max(g.last_wins, key=lambda x: x["amount"])["player"]
            p = g.players[w]
            if p.hole and all(c.value is not None for c in p.hole):
                glows.append((w, key_cards(p.hole + g.board), theme.SUCCESS))
        elif self.me.live and self.me.hole and self.me.hole[0].value is not None:
            glows.append((HUMAN, key_cards(self.me.hole + g.board), theme.ACCENT))
        pulse = 2 + int(1.5 * (1 + math.sin(self.clock * 5)))
        for who, cards, color in glows:
            ids = {c.id for c in cards}
            rects = [self.board_rect(k) for k, c in enumerate(g.board) if c.id in ids and c.id not in hidden]
            rects += [self.hole_rect(who, k) for k, c in enumerate(g.players[who].hole) if c.id in ids]
            for r in rects:
                pygame.draw.rect(surf, color, r.inflate(8, 8), pulse, border_radius=12)

    def _draw_me(self, surf, hidden):
        g = self.game
        p = self.me
        mine = g.current == HUMAN and g.phase == "playing"
        winner = g.phase == "settled" and any(w["player"] == HUMAN for w in g.last_wins)
        theme.panel(surf, MY_BOX, edge=theme.ACCENT if mine else theme.SUCCESS if winner else theme.PANEL_EDGE,
                    edge_w=3 if mine or winner else 2)
        for k, (c, img) in enumerate(self._hole_images(HUMAN, HOLE_W, HOLE_H)):
            if c.id in hidden:
                continue
            if p.folded:
                img = img.copy()
                img.set_alpha(110)
            surf.blit(img, self.hole_rect(HUMAN, k).move(0, -6 if mine else 0))
        x = MY_BOX.x + 268
        theme.ptext(surf, "YOUR STACK", (x, MY_BOX.y + 104), 12, theme.TEXT_DIM)
        theme.chip(surf, (x + 10, MY_BOX.y + 136), 11, theme.ACCENT)
        theme.ptext(surf, str(p.chips), (x + 28, MY_BOX.y + 120), 30, theme.ACCENT)
        if p.folded:
            pass
        elif p.hole and len(g.board) >= 3 and p.hole[0].value is not None:
            theme.ptext(surf, describe(evaluate(p.hole + g.board)), (MY_BOX.x + 30, MY_BOX.y + 186), 18, theme.INFO)
        elif p.hole and p.hole[0].value is not None:
            a, b = p.hole
            pair = a.value == b.value
            suited = a.color == b.color
            note = "A PAIR!" if pair else "SAME COLOR (SUITED)" if suited else ""
            if note:
                theme.ptext(surf, note, (MY_BOX.x + 30, MY_BOX.y + 186), 18, theme.INFO)
        if p.folded:
            theme.ptext(surf, "FOLDED", (MY_BOX.x + 30, MY_BOX.y + 186), 18, theme.TEXT_FAINT)
        if HUMAN == g.button and p.in_hand:
            self._dealer_button(surf, (MY_BOX.x + 250, MY_BOX.y + 40))
        self._bet_stack(surf, self.bet_spot(HUMAN), p.bet)
        if p.bet:
            theme.ptext(surf, "IN THIS ROUND", (MY_BOX.x + 290, MY_BOX.y + 22), 11, theme.TEXT_DIM)
        net = f"+{p.net}" if p.net > 0 else str(p.net)
        theme.ptext(surf, f"THIS GAME {net}", (MY_BOX.x + 30, MY_BOX.y + 218), 13,
                    theme.SUCCESS if p.net > 0 else theme.DANGER if p.net < 0 else theme.TEXT_DIM)
        self._draw_controls(surf)

    def _draw_controls(self, surf):
        g = self.game
        my_turn = self.my_turn()
        legal = g.legal_actions(HUMAN) if my_turn else []
        to_call = g.to_call(HUMAN) if g.phase == "playing" else 0
        bounds = self.raise_bounds() if my_turn else None
        self.btn_fold.enabled = "fold" in legal
        self.btn_call.enabled = "call" in legal or "check" in legal
        self.btn_call.label = (f"ALL IN {to_call}" if to_call >= self.me.chips else f"CALL {to_call}") if to_call \
            else "CHECK"
        self.btn_raise.enabled = "raise" in legal
        if bounds:
            all_in = self.raise_to >= bounds[1]
            verb = "BET" if g.current_bet == 0 else "RAISE TO"
            self.btn_raise.label = f"ALL IN {self.raise_to}" if all_in else f"{verb} {self.raise_to}"
        else:
            self.btn_raise.label = "RAISE"
        for b in self.picker_buttons:
            b.enabled = bool(bounds)
        self.btn_hint.visible = self.app.settings.hints
        self.btn_hint.enabled = my_turn
        # Not your turn yet? Queue a move instead. Folded? Skip ahead.
        queue = not my_turn and self.can_queue()
        fast = not my_turn and not queue and not self.networked and g.phase == "playing" and not self.me.live
        for b in self.action_buttons:
            b.visible = not queue and not fast
        to_call_now = g.to_call(HUMAN) if g.phase == "playing" else 0
        for b, what in zip(self.pre_buttons, ("check_fold", "check", "call_any")):
            b.visible = queue
            on = self.pre == what
            b.color, b.text_color = ("ACCENT", "OUTLINE") if on else ("PANEL_LIGHT", "TEXT")
            label = {"check_fold": "CHECK / FOLD", "check": "CHECK", "call_any": "CALL ANY"}[what]
            b.label = ("[X] " if on else "") + label
            b.enabled = what != "check" or not to_call_now
        self.btn_fast.visible = fast
        self.btn_fast.enabled = not self.fast
        self.btn_fast.label = "FAST FORWARDING..." if self.fast else "FAST FORWARD TO THE NEXT HAND"
        for b in self.buttons:
            b.draw(surf)
            if self.hint_action and b in self.action_buttons and b.visible:
                want = {"fold": self.btn_fold, "check": self.btn_call, "call": self.btn_call,
                        "raise": self.btn_raise}[self.hint_action]
                if b is want:
                    pygame.draw.rect(surf, theme.ACCENT, b.rect.inflate(8, 8), 3, border_radius=12)
        # The slider: drag the chip along the track to pick how much to bet.
        theme.rounded(surf, theme.INNER, SLIDER, 10)
        track = pygame.Rect(SLIDER.x + 14, SLIDER.centery - 4, SLIDER.w - 28, 8)
        theme.rounded(surf, theme.OUTLINE, track, 4)
        if bounds:
            lo, hi = bounds
            u = (self.raise_to - lo) / (hi - lo) if hi > lo else 1.0
            fill = pygame.Rect(track.x, track.y, int(track.w * u), track.h)
            theme.rounded(surf, theme.ACCENT, fill, 4)
            kx = track.x + int(track.w * u)
            theme.chip(surf, (kx, SLIDER.centery), 16, theme.ACCENT)
            theme.ptext(surf, str(self.raise_to), (kx, SLIDER.centery), 12 if self.raise_to < 100 else 10,
                        theme.OUTLINE, None, anchor="center")
            theme.ptext(surf, str(lo), (track.x, SLIDER.bottom - 2), 11, theme.TEXT_DIM, anchor="topleft")
            if self.typed:
                theme.ptext(surf, f"TYPED {self.typed}", (SLIDER.centerx, SLIDER.y - 4), 11, theme.ACCENT,
                            anchor="midbottom")
            theme.ptext(surf, str(hi), (track.right, SLIDER.bottom - 2), 11, theme.TEXT_DIM, anchor="topright")
        else:
            theme.ptext(surf, "PICK YOUR BET HERE ON YOUR TURN", SLIDER.center, 14, theme.TEXT_FAINT, anchor="center")

    def _draw_bubbles(self, surf):
        for b in self.bubbles:
            img = theme.pixel_surface(b.text, 16, b.color if b.color != theme.TEXT else theme.OUTLINE, None)
            box = pygame.Rect(0, 0, img.get_width() + 24, img.get_height() + 14)
            if b.player == "board":
                box.midtop = (BOARD_BOX.centerx, BOARD_BOX.bottom + 8)
            elif b.player == HUMAN:
                box.midleft = (MY_BOX.x + 268, MY_BOX.y + 196)
            elif isinstance(b.player, int) and b.player < len(self.game.players):
                r = self.seat_rect(b.player)
                box.midtop = (r.centerx + 40, r.y + 140)
            else:
                continue
            box.clamp_ip(pygame.Rect(8, 0, theme.WIDTH - 16, theme.HEIGHT))
            layer = pygame.Surface(box.inflate(0, 6).size, pygame.SRCALPHA)
            inner = pygame.Rect(0, 0, box.w, box.h)
            theme.rounded(layer, theme.OUTLINE, inner.move(0, 3), 12)
            theme.rounded(layer, theme.CARD_WHITE, inner, 12)
            layer.blit(img, img.get_rect(center=inner.center))
            layer.set_alpha(int(255 * min(1.0, b.ttl / 0.25)))
            surf.blit(layer, box.topleft)

    def _draw_hover(self, surf, i: int):
        p = self.game.players[i]
        box = self.seat_rect(i)
        w, h = 440, 190
        rect = pygame.Rect(max(10, min(theme.WIDTH - w - 10, box.centerx - w // 2)), box.y + 96, w, h)
        profile_art.panel(surf, rect, profile_art.seat_profile(self, i)["b"], self.clock)
        prof = profile_art.seat_profile(self, i)
        profile_art.avatar(surf, (rect.x + 38, rect.y + 38), 24, prof, i, level=True)
        name_r = theme.ptext(surf, p.name, (rect.x + 72, rect.y + 12), 24, profile_art.name_rgb(prof, self.clock))
        profile_art.name_tag(surf, name_r, prof, 20)
        label, color = self.role(i)
        self._chip(surf, label, (rect.x + 72, rect.y + 44), color, size=12)
        theme.ptext(surf, f"{p.chips} CHIPS", (rect.right - 18, rect.y + 12), 24, theme.ACCENT, anchor="topright")
        net = f"+{p.net}" if p.net > 0 else str(p.net)
        theme.ptext(surf, f"THIS GAME {net}", (rect.right - 18, rect.y + 46), 14,
                    theme.SUCCESS if p.net > 0 else theme.DANGER if p.net < 0 else theme.TEXT_DIM, anchor="topright")
        put = f"Put in {p.total_in} this hand" if p.total_in else "Nothing in the pot this hand"
        theme.ptext(surf, put, (rect.x + 20, rect.y + 84), 16)
        theme.ptext(surf, "LAST HANDS", (rect.x + 20, rect.bottom - 62), 12, theme.TEXT_DIM)
        for k, res in enumerate(p.results[-12:]):
            cx = rect.x + 30 + k * 26
            pygame.draw.circle(surf, theme.OUTLINE, (cx, rect.bottom - 28), 11)
            pygame.draw.circle(surf, RESULT_COLORS[res], (cx, rect.bottom - 30), 10)
            theme.ptext(surf, RESULT_LETTER[res], (cx, rect.bottom - 30), 10, theme.OUTLINE, None, anchor="center")
        if not p.results:
            theme.ptext(surf, "None yet", (rect.x + 20, rect.bottom - 38), 14, theme.TEXT_FAINT)

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
                title = "YOU TIED FOR FIRST!" if HUMAN in winners else "IT'S A TIE!"
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
                prof = profile_art.seat_profile(self, i)
                profile_art.avatar(surf, (row.x + 34, row.centery), 20, prof, i)
                name_r = theme.ptext(surf, self.name(i), (row.x + 66, row.centery), 20,
                                     profile_art.name_rgb(prof, self.clock), anchor="midleft")
                profile_art.name_tag(surf, name_r, prof, 16)
                theme.chip(surf, (row.x + 300, row.centery + 2), 11, theme.ACCENT)
                theme.ptext(surf, f"{p.chips} CHIPS", (row.x + 318, row.centery), 22, theme.ACCENT, anchor="midleft")
                wins = sum(r == "won" for r in p.results)
                theme.ptext(surf, f"{wins} POT{'S' if wins != 1 else ''} WON", (row.x + 500, row.centery), 16,
                            theme.TEXT_DIM, anchor="midleft")
                net = f"+{p.net}" if p.net > 0 else str(p.net)
                theme.ptext(surf, net, (row.right - 20, row.centery), 20,
                            theme.SUCCESS if p.net > 0 else theme.DANGER if p.net < 0 else theme.TEXT_DIM,
                            anchor="midright")
        for b in self.overlay_buttons:
            b.draw(surf)
