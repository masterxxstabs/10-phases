"""The Blackjack table, in the same handheld style.

  top screen     hand counter and rules, the dealer, the shoe
  bottom screen  the other players' seats, then your hand, bet and buttons
"""

from __future__ import annotations

import math

import pygame

from ..blackjack import ai as bj_ai
from ..blackjack.ai import BlackjackAI
from ..blackjack.engine import MAX_BET, MIN_BET, BJPlayer, BlackjackGame, RuleError, hand_value
from ..names import pick_ai_names
from ..settings import SPEED_DELAYS
from . import profile_art, sfx, theme
from .card_art import card_with_shadow
from .admin import AdminPanel
from .table_skins import TableSkins
from .game_scene import DIFF_COLORS, FlyingCard
from .menus import Scene, backdrop, status_bar
from .widgets import Button
from .xp import XpTracker

HUMAN = 0
SPLIT_Y = 222
INFO_BOX = pygame.Rect(20, 14, 300, 194)
DEALER_BOX = pygame.Rect(340, 14, 600, 194)
SHOE_BOX = pygame.Rect(960, 14, 300, 194)
SEATS = pygame.Rect(20, 238, 1240, 282)
MY_BOX = pygame.Rect(20, 532, 1240, 232)
MY_HANDS = pygame.Rect(260, 560, 760, 196)
CARD_W, CARD_H = 88, 132
RESULT_TEXT = {"win": ("WIN", theme.SUCCESS), "blackjack": ("BLACKJACK!", theme.ACCENT), "push": ("PUSH", theme.INFO),
               "lose": ("LOSE", theme.DANGER), "bust": ("BUST", theme.DANGER)}


RESULT_LETTER = {"win": "W", "blackjack": "21", "push": "P", "lose": "L", "bust": "X"}


class Bubble:
    def __init__(self, player, text, color, ttl=1.6):
        self.player, self.text, self.color, self.ttl = player, text, color, ttl


class BlackjackScene(Scene):
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
            players = [BJPlayer("YOU", is_human=True)] + [BJPlayer(n, difficulty=d) for n, d in zip(names, diffs)]
            self.game = BlackjackGame(players)
            self.ais = {i + 1: BlackjackAI(d) for i, d in enumerate(diffs)}
        self.skins = TableSkins(self)
        self.admin = AdminPanel(self)
        self.xp = XpTracker(self, "blackjack")
        self.delay = SPEED_DELAYS[s.ai_speed]
        self.bet_amount = 5
        self.anims: list[FlyingCard] = []
        self.bubbles: list[Bubble] = []
        self.flash: tuple[str, float] | None = None
        self.splash: tuple[str, str, float, float] | None = ("BLACKJACK", "BEAT THE DEALER IN 10 HANDS", 1.8, 1.8)
        self.overlay: str | None = None
        self._pending_overlay = False
        self.ai_timer = 0.8
        self.settle_timer = 0.0
        self.hint_action: str | None = None
        self._banked: int | None = None

        bx = 1046
        self.btn_hit = Button((bx, 548, 96, 50), "HIT", lambda: self.act("hit"), "ACCENT", "OUTLINE", 18)
        self.btn_stand = Button((bx + 104, 548, 96, 50), "STAND", lambda: self.act("stand"), size=18)
        self.btn_double = Button((bx, 606, 96, 46), "DOUBLE", lambda: self.act("double"), size=15)
        self.btn_split = Button((bx + 104, 606, 96, 46), "SPLIT", lambda: self.act("split"), size=15)
        self.btn_minus = Button((bx, 548, 54, 50), "-", lambda: self.change_bet(-1), size=24)
        self.btn_plus = Button((bx + 146, 548, 54, 50), "+", lambda: self.change_bet(1), size=24)
        self.btn_deal = Button((bx, 606, 200, 46), "DEAL", self.do_bet, "ACCENT", "OUTLINE", 20)
        self.btn_hint = Button((bx, 660, 96, 40), "HINT", self.do_hint, size=14)
        self.btn_menu = Button((bx + 104, 660, 96, 40), "MENU", lambda: self._set_overlay("pause"), size=14)
        self.play_buttons = [self.btn_hit, self.btn_stand, self.btn_double, self.btn_split]
        self.bet_buttons = [self.btn_minus, self.btn_plus, self.btn_deal]
        self.buttons = self.play_buttons + self.bet_buttons + [self.btn_hint, self.btn_menu]
        self.overlay_buttons: list[Button] = []
        self._consume_events()
        sfx.play("phase")

    # ================================================================== helpers

    @property
    def me(self) -> BJPlayer:
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
        return not self.busy and g.phase == "playing" and g.turn is not None and g.turn[0] == HUMAN

    def can_bet(self) -> bool:
        return not self.busy and HUMAN in self.game.waiting_for_bets()

    def name(self, i) -> str:
        return "DEALER" if i is None else ("YOU" if i == HUMAN else self.game.players[i].name)

    def role(self, i: int):
        p = self.game.players[i]
        return (p.difficulty.upper(), DIFF_COLORS[p.difficulty]) if p.difficulty else ("PLAYER", theme.CARD_WHITE)

    def error(self, msg: str):
        self.flash = (msg, 2.6)
        sfx.play("error")

    def bubble(self, i, text, color):
        self.bubbles = [b for b in self.bubbles if b.player != i]
        self.bubbles.append(Bubble(i, text, color))

    def others(self) -> list[int]:
        return list(range(1, len(self.game.players)))

    def seat_rect(self, i: int) -> pygame.Rect:
        others = self.others()
        n, gap = max(1, len(others)), 14
        w = min(400, (SEATS.w - (n - 1) * gap) // n)
        x0 = SEATS.x + (SEATS.w - (n * w + (n - 1) * gap)) // 2
        return pygame.Rect(x0 + others.index(i) * (w + gap), SEATS.y, w, SEATS.h)

    def shoe_rect(self) -> pygame.Rect:
        return pygame.Rect(SHOE_BOX.x + 30, SHOE_BOX.y + 50, 72, 108)

    def dealer_card_rect(self, k: int, n: int) -> pygame.Rect:
        step = min(80, (DEALER_BOX.w - 220 - 72) / max(1, n - 1)) if n > 1 else 0
        return pygame.Rect(int(DEALER_BOX.x + 190 + k * step), DEALER_BOX.y + 70, 72, 108)

    def card_rect(self, i: int, h: int, k: int) -> pygame.Rect:
        p = self.game.players[i]
        nh = max(1, len(p.hands))
        n = len(p.hands[h].cards) if h < len(p.hands) else 1
        if i == HUMAN:
            area_w = MY_HANDS.w // nh
            x0 = MY_HANDS.x + h * area_w
            step = min(CARD_W * 0.62, (area_w - CARD_W - 20) / max(1, n - 1)) if n > 1 else 0
            return pygame.Rect(int(x0 + 10 + k * step), MY_HANDS.y + 46, CARD_W, CARD_H)
        seat = self.seat_rect(i)
        area_w = (seat.w - 20) // nh
        cw, ch = 56, 84
        step = min(cw * 0.6, (area_w - cw - 8) / max(1, n - 1)) if n > 1 else 0
        return pygame.Rect(int(seat.x + 10 + h * area_w + k * step), seat.y + 128, cw, ch)

    def anchor(self, i) -> pygame.Rect:
        if i is None:
            return self.dealer_card_rect(0, 1)
        if i == HUMAN:
            return pygame.Rect(MY_HANDS.x + 20, MY_HANDS.y + 46, CARD_W, CARD_H)
        r = self.seat_rect(i)
        return pygame.Rect(r.centerx - 28, r.y + 128, 56, 84)

    # ================================================================== events -> animation

    def _consume_events(self):
        g = self.game
        stagger = 0.0
        for ev in g.pop_events():
            self.xp.event(ev)
            k = ev.kind
            if k in ("deal", "hit", "double", "split", "dealer_hit"):
                if ev.player is None:
                    n = len(g.dealer)
                    idx = n - 1 if k == "dealer_hit" else (1 if ev.hidden else 0)
                    end = self.dealer_card_rect(min(idx, n - 1), n)
                    card = None if ev.hidden else ev.card
                    face = None
                else:
                    hand = g.players[ev.player].hands[ev.hand] if ev.hand < len(g.players[ev.player].hands) else None
                    idx = (hand.cards.index(ev.card) if hand and ev.card in hand.cards else 0)
                    end = self.card_rect(ev.player, ev.hand, idx)
                    card = ev.card
                    face = self.skins.face(ev.player)
                self.anims.append(FlyingCard(card, self.shoe_rect(), end, 0.3, stagger,
                                             hide_id=card.id if card is not None else None, face=face))
                stagger += 0.12 if k == "deal" else 0.0
                sfx.play("draw")
                if k == "double":
                    self.bubble(ev.player, f"DOUBLE! ({ev.amount})", theme.ACCENT)
                elif k == "split":
                    self.bubble(ev.player, "SPLIT!", theme.ACCENT)
            elif k == "bet":
                self.bubble(ev.player, f"BET {ev.amount}", theme.TEXT)
                sfx.play("coin" if ev.player == HUMAN else "click")
            elif k == "stand":
                hands = g.players[ev.player].hands if ev.player is not None and ev.player < len(g.players) else []
                if ev.hand < len(hands):   # a late event can describe a hand that's already been cleared
                    self.bubble(ev.player, f"STAND ON {hands[ev.hand].value}", theme.TEXT)
            elif k == "bust":
                self.bubble(ev.player, "BUST!", theme.DANGER)
                sfx.play("skip")
            elif k == "blackjack":
                self.bubble(ev.player, "BLACKJACK!", theme.ACCENT)
                sfx.play("round_win" if ev.player in (HUMAN, None) else "coin")
            elif k == "reveal":
                sfx.play("click")
            elif k == "turn" and ev.player == HUMAN:
                sfx.play("turn")
                self.hint_action = None
            elif k == "settle":
                if ev.player == HUMAN:
                    label, color = RESULT_TEXT.get(ev.result, ("", theme.TEXT))
                    amount = f"+{ev.amount}" if ev.amount > 0 else (str(ev.amount) if ev.amount else "")
                    self.splash = (label, f"{amount} CHIPS" if amount else "BET RETURNED", 1.3, 1.3)
                    sfx.play("round_win" if ev.result in ("win", "blackjack") else
                             "round_end" if ev.result == "push" else "game_lose")
                self.settle_timer = 2.4
            elif k == "shuffle":
                self.bubble(None, "SHUFFLING THE SHOE", theme.INFO)
                sfx.play("shuffle")
            elif k == "game_over":
                self._pending_overlay = True

    # ================================================================== actions

    def change_bet(self, step: int):
        top = max(MIN_BET, self.game.max_bet(HUMAN))
        self.bet_amount = max(MIN_BET, min(top, self.bet_amount + step))
        sfx.play("select")

    def do_bet(self):
        if not self.can_bet():
            return
        self.bet_amount = max(MIN_BET, min(self.bet_amount, self.game.max_bet(HUMAN)))
        try:
            self.game.place_bet(HUMAN, self.bet_amount)
        except RuleError as e:
            self.error(str(e))
            return
        self._consume_events()

    def act(self, action: str):
        if not self.my_turn():
            return
        if action not in self.game.legal_actions(HUMAN):
            self.error({"double": "You can only double on your first two cards, with enough chips.",
                        "split": "You can only split a pair, once, with enough chips."}.get(action, "Not now."))
            return
        try:
            getattr(self.game, action)(HUMAN)
        except RuleError as e:
            self.error(str(e))
            return
        self.hint_action = None
        self._consume_events()
        self.ai_timer = self.delay + 0.3

    def do_hint(self):
        if not self.my_turn():
            if self.can_bet():
                self.flash = ("Hint: bet small and steady - the house edge is small if you play by the chart.", 3)
                sfx.play("turn")
            return
        action, reason = bj_ai.hint(self.game, HUMAN)
        self.hint_action = action
        self.flash = (f"Hint: {reason}.", 3.2)
        sfx.play("turn")

    def run_ai(self):
        g = self.game
        if g.phase == "betting":
            for i in g.waiting_for_bets():
                if i in self.ais:
                    g.place_bet(i, self.ais[i].choose_bet(g, i))
                    self._consume_events()
                    self.ai_timer = 0.15
                    return
        elif g.phase == "playing" and g.turn and g.turn[0] in self.ais:
            i = g.turn[0]
            getattr(g, self.ais[i].choose_action(g, i))(i)
            self._consume_events()
            self.ai_timer = self.delay * 1.2 + 0.25

    # ================================================================== network

    def _pump_network(self):
        if self.host is not None:
            self.host.pump()
            while self.session.notices:
                self.bubble(None, self.session.notices.pop(0), theme.DANGER)
                sfx.play("skip")
        if self.client is not None:
            for msg in self.client.poll():
                t = msg["t"]
                if t == "error":
                    self.error(msg.get("msg", "That move wasn't allowed."))
                elif t == "notice":
                    self.bubble(None, msg.get("msg", ""), theme.DANGER)
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
        restart = lambda: self.app.go(BlackjackScene(self.app))  # noqa: E731
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
            keys = {pygame.K_h: "hit", pygame.K_s: "stand", pygame.K_d: "double", pygame.K_p: "split"}
            if event.key == pygame.K_ESCAPE:
                self._set_overlay("pause")
            elif event.key in keys and self.my_turn():
                self.act(keys[event.key])
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.can_bet():
                self.do_bet()
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN) and self.can_bet():
                self.change_bet(1 if event.key in (pygame.K_RIGHT, pygame.K_UP) else -1)
            return
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
        if self.flow_blocked or g.game_over:
            return
        if g.phase == "settled" and self.client is None:
            # Show the results for a moment, then deal the next hand (the host does this for everyone).
            self.settle_timer -= dt
            if self.settle_timer <= 0:
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
        self._draw_dealer(surf, hidden)
        self._draw_shoe(surf)
        for i in self.others():
            self._draw_seat(surf, i, hidden)
        if not self.others():
            theme.panel(surf, SEATS)
            theme.ptext(surf, "JUST YOU AND THE DEALER", SEATS.center, 22, theme.TEXT_FAINT, anchor="center")
        self._draw_me(surf, hidden)
        for a in self.anims:
            a.draw(surf)
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
        if g.phase == "betting":
            if self.can_bet():
                return "Choose your bet with - and +, then press DEAL."
            return "Waiting for everyone to bet."
        if g.phase == "settled":
            return "Next hand coming up..."
        if self.my_turn():
            return "Your turn: HIT (H), STAND (S), DOUBLE (D) or SPLIT (P)."
        return "Wait until it is your turn."

    def _chip(self, surf, label, pos, color, fg="OUTLINE", size=11):
        img = theme.pixel_surface(label, size, fg, None)
        r = pygame.Rect(pos[0], pos[1], img.get_width() + 12, img.get_height() + 4)
        theme.rounded(surf, theme.OUTLINE, r.move(0, 2), r.h // 2)
        theme.rounded(surf, color, r, r.h // 2)
        surf.blit(img, img.get_rect(center=r.center))
        return r

    def _total_badge(self, surf, cards, pos, size=16, anchor="topleft"):
        if not cards:
            return
        total, soft = hand_value(cards)
        text = f"SOFT {total}" if soft and total < 21 else str(total)
        color = theme.DANGER if total > 21 else theme.ACCENT if total == 21 else theme.CARD_WHITE
        img = theme.pixel_surface(text, size, theme.OUTLINE, None)
        r = pygame.Rect(0, 0, img.get_width() + 14, img.get_height() + 6)
        setattr(r, anchor, pos)
        theme.rounded(surf, theme.OUTLINE, r.move(0, 2), r.h // 2)
        theme.rounded(surf, color, r, r.h // 2)
        surf.blit(img, img.get_rect(center=r.center))

    def _bet_stack(self, surf, base, bet: int, r: int = 12):
        for k in range(min(bet, 10)):
            theme.chip(surf, (base[0], base[1] - k * 4), r, theme.CHIP_COLORS[k % 3])

    def _draw_info(self, surf):
        g = self.game
        theme.panel(surf, INFO_BOX)
        theme.ptext(surf, "BLACKJACK", (INFO_BOX.x + 16, INFO_BOX.y + 12), 22, theme.ACCENT)
        theme.ptext(surf, f"HAND {min(g.round, g.hands_per_game)} OF {g.hands_per_game}",
                    (INFO_BOX.x + 16, INFO_BOX.y + 46), 20)
        for k, line in enumerate(("Dealer stands on 17", "Blackjack pays 3:2", f"Bets {MIN_BET}-{MAX_BET} chips",
                                  "Most chips after 10 hands wins")):
            theme.text(surf, line, (INFO_BOX.x + 18, INFO_BOX.y + 84 + k * 22), 14, theme.TEXT_DIM, bold=False)

    def _draw_dealer(self, surf, hidden):
        g = self.game
        theme.panel(surf, DEALER_BOX, edge=theme.ACCENT if g.phase == "settled" or (g.turn is None and g.phase ==
                                                                                      "playing") else theme.PANEL_EDGE)
        cx = DEALER_BOX.x + 60
        pygame.draw.circle(surf, theme.OUTLINE, (cx, DEALER_BOX.y + 62), 36)
        pygame.draw.circle(surf, theme.CARD_BLACK, (cx, DEALER_BOX.y + 60), 34)
        theme.ptext(surf, "21", (cx, DEALER_BOX.y + 60), 22, theme.ACCENT, anchor="center")
        theme.ptext(surf, "DEALER", (cx, DEALER_BOX.y + 116), 18, anchor="center")
        n = len(g.dealer)
        for k, c in enumerate(g.dealer):
            r = self.dealer_card_rect(k, n)
            face_down = k == 1 and g.hole_hidden
            if not face_down and c.id in hidden:
                continue
            img, _ = card_with_shadow(None if face_down else c, r.w, r.h)
            surf.blit(img, r)
        shown = [c for k, c in enumerate(g.dealer) if not (k == 1 and g.hole_hidden)]
        if shown:
            self._total_badge(surf, shown, (DEALER_BOX.x + 190, DEALER_BOX.y + 20), 16)
        if n and is_bj(g.dealer) and not g.hole_hidden:
            self._chip(surf, "BLACKJACK!", (DEALER_BOX.right - 130, DEALER_BOX.y + 20), theme.ACCENT, size=12)

    def _draw_shoe(self, surf):
        theme.panel(surf, SHOE_BOX)
        for k in range(4):
            img, _ = card_with_shadow(None, 72, 108)
            surf.blit(img, self.shoe_rect().move(k * 3, -k * 3))
        theme.ptext(surf, "SHOE", (SHOE_BOX.x + 140, SHOE_BOX.y + 54), 18, theme.ACCENT)
        theme.ptext(surf, f"{len(self.game.shoe)} CARDS", (SHOE_BOX.x + 140, SHOE_BOX.y + 80), 16)
        theme.text(surf, "4 decks", (SHOE_BOX.x + 140, SHOE_BOX.y + 108), 14, theme.TEXT_DIM, bold=False)

    def _draw_seat(self, surf, i: int, hidden):
        g = self.game
        p = g.players[i]
        r = self.seat_rect(i)
        active = g.turn is not None and g.turn[0] == i
        theme.panel(surf, r, edge=theme.ACCENT if active else theme.PANEL_EDGE, edge_w=3 if active else 2)
        bob = math.sin(self.clock * 6) * 2 if active else 0
        prof = profile_art.seat_profile(self, i)
        profile_art.avatar(surf, (r.x + 30, int(r.y + 30 + bob)), 22, prof, i, level=True)
        theme.ptext(surf, p.name, (r.x + 60, r.y + 8), 18, profile_art.name_rgb(prof, self.clock))
        label, color = self.role(i)
        self._chip(surf, label, (r.x + 60, r.y + 32), color)
        theme.chip(surf, (r.x + 22, r.y + 74), 9, theme.ACCENT)
        theme.ptext(surf, str(p.chips), (r.x + 36, r.y + 64), 18, theme.ACCENT)
        if g.phase == "betting" and p.bet is None and p.chips >= MIN_BET:
            theme.ptext(surf, "BETTING...", (r.right - 12, r.y + 66), 14, theme.TEXT_DIM, anchor="topright")
        elif p.chips < MIN_BET and not p.hands:
            theme.ptext(surf, "OUT OF CHIPS", (r.right - 12, r.y + 66), 14, theme.DANGER, anchor="topright")
        for h, hand in enumerate(p.hands):
            for k, c in enumerate(hand.cards):
                cr = self.card_rect(i, h, k)
                if c.id in hidden:
                    continue
                img, _ = card_with_shadow(c, cr.w, cr.h, face=self.skins.face(i))
                surf.blit(img, cr)
            first = self.card_rect(i, h, 0)
            self._total_badge(surf, hand.cards, (first.x, first.y - 26), 13)
            self._bet_stack(surf, (first.x + 14, r.bottom - 22), hand.bet, 9)
            theme.ptext(surf, str(hand.bet), (first.x + 30, r.bottom - 30), 14, theme.ACCENT)
            if hand.result:
                text, color = RESULT_TEXT[hand.result]
                self._chip(surf, text, (first.x + 56, r.bottom - 34), color, theme.OUTLINE, 11)
            elif active and g.turn[1] == h and len(p.hands) > 1:
                pygame.draw.rect(surf, theme.ACCENT, first.inflate(8, 8), 3, border_radius=8)

    def _draw_me(self, surf, hidden):
        g = self.game
        p = self.me
        active = self.my_turn() or self.can_bet()
        theme.panel(surf, MY_BOX, edge=theme.ACCENT if active else theme.PANEL_EDGE, edge_w=3 if active else 2)
        bob = math.sin(self.clock * 6) * 2 if active else 0
        prof = profile_art.seat_profile(self, HUMAN)
        profile_art.avatar(surf, (MY_BOX.x + 34, int(MY_BOX.y + 30 + bob)), 24, prof, HUMAN, level=True)
        theme.ptext(surf, "YOU", (MY_BOX.x + 68, MY_BOX.y + 10), 22, profile_art.name_rgb(prof, self.clock))
        theme.chip(surf, (MY_BOX.x + 34, MY_BOX.y + 84), 13, theme.ACCENT)
        theme.ptext(surf, str(p.chips), (MY_BOX.x + 56, MY_BOX.y + 70), 28, theme.ACCENT)
        net = f"+{p.net}" if p.net > 0 else str(p.net)
        theme.ptext(surf, f"THIS GAME {net}", (MY_BOX.x + 22, MY_BOX.y + 110), 14,
                    theme.SUCCESS if p.net > 0 else theme.DANGER if p.net < 0 else theme.TEXT_DIM)
        if p.results:
            theme.ptext(surf, "LAST HANDS", (MY_BOX.x + 22, MY_BOX.y + 136), 12, theme.TEXT_DIM)
            for k, res in enumerate(p.results[-6:]):
                color = RESULT_TEXT[res][1]
                pygame.draw.circle(surf, theme.OUTLINE, (MY_BOX.x + 30 + k * 24, MY_BOX.y + 166), 10)
                pygame.draw.circle(surf, color, (MY_BOX.x + 30 + k * 24, MY_BOX.y + 164), 9)
                theme.ptext(surf, RESULT_LETTER[res], (MY_BOX.x + 30 + k * 24, MY_BOX.y + 164),
                            10, theme.OUTLINE, None, anchor="center")
        if not p.hands:
            msg = "PLACE YOUR BET!" if self.can_bet() else "OUT OF CHIPS" if p.chips < MIN_BET else \
                (f"BET {p.bet} - WAITING FOR THE DEAL" if p.bet else "")
            if msg:
                theme.ptext(surf, msg, MY_HANDS.center, 22, theme.TEXT_DIM, anchor="center")
        for h, hand in enumerate(p.hands):
            for k, c in enumerate(hand.cards):
                cr = self.card_rect(HUMAN, h, k)
                if c.id in hidden:
                    continue
                img, _ = card_with_shadow(c, cr.w, cr.h)
                surf.blit(img, cr)
            first = self.card_rect(HUMAN, h, 0)
            self._total_badge(surf, hand.cards, (first.x, first.y - 34), 18)
            self._bet_stack(surf, (first.x + 120, first.y - 18), hand.bet, 10)
            theme.ptext(surf, f"BET {hand.bet}" + (" x2" if hand.doubled else ""), (first.x + 140, first.y - 34), 16,
                        theme.ACCENT)
            if hand.result:
                text, color = RESULT_TEXT[hand.result]
                self._chip(surf, text, (first.x, first.bottom - 10), color, theme.OUTLINE, 14)
            if g.turn == (HUMAN, h) and len(p.hands) > 1:
                pygame.draw.rect(surf, theme.ACCENT, first.inflate(10, 10), 4, border_radius=10)

        # Buttons
        betting = g.phase == "betting" and HUMAN in g.waiting_for_bets()
        for b in self.play_buttons:
            b.visible = not betting
        for b in self.bet_buttons:
            b.visible = betting
        legal = g.legal_actions(HUMAN) if self.my_turn() else []
        for b, name in zip(self.play_buttons, ("hit", "stand", "double", "split")):
            b.enabled = name in legal
        for b in self.bet_buttons:
            b.enabled = self.can_bet()
        self.btn_hint.visible = self.app.settings.hints
        self.btn_hint.enabled = self.my_turn() or self.can_bet()
        for b in self.buttons:
            b.draw(surf)
            if self.hint_action and b.visible and b.label.lower() == self.hint_action:
                pygame.draw.rect(surf, theme.ACCENT, b.rect.inflate(8, 8), 3, border_radius=12)
        if betting:
            box = pygame.Rect(self.btn_minus.rect.right + 4, self.btn_minus.rect.y, 84, 50)
            theme.rounded(surf, theme.INNER, box, 8)
            theme.ptext(surf, str(self.bet_amount), box.center, 26, theme.ACCENT, anchor="center")
            theme.ptext(surf, "YOUR BET", (box.centerx, box.y - 2), 10, theme.TEXT_DIM, anchor="midbottom")

    def _draw_bubbles(self, surf):
        for b in self.bubbles:
            img = theme.pixel_surface(b.text, 16, b.color if b.color != theme.TEXT else theme.OUTLINE, None)
            box = pygame.Rect(0, 0, img.get_width() + 24, img.get_height() + 14)
            if b.player is None:
                box.midtop = (DEALER_BOX.centerx, DEALER_BOX.bottom + 8)
            elif b.player == HUMAN:
                box.midbottom = (MY_BOX.x + 380, MY_BOX.y - 4)
            else:
                r = self.seat_rect(b.player)
                box.midtop = (r.centerx, r.y + 92)
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
        w, h = 460, 214
        rect = pygame.Rect(max(10, min(theme.WIDTH - w - 10, box.centerx - w // 2)), box.y + 96, w, h)
        profile_art.panel(surf, rect, profile_art.seat_profile(self, i)["b"], self.clock)
        prof = profile_art.seat_profile(self, i)
        profile_art.avatar(surf, (rect.x + 38, rect.y + 38), 24, prof, i, level=True)
        theme.ptext(surf, p.name, (rect.x + 72, rect.y + 12), 24, profile_art.name_rgb(prof, self.clock))
        label, color = self.role(i)
        self._chip(surf, label, (rect.x + 72, rect.y + 44), color, size=12)
        theme.ptext(surf, f"{p.chips} CHIPS", (rect.right - 18, rect.y + 12), 24, theme.ACCENT, anchor="topright")
        net = f"+{p.net}" if p.net > 0 else str(p.net)
        theme.ptext(surf, f"THIS GAME {net}", (rect.right - 18, rect.y + 46), 14,
                    theme.SUCCESS if p.net > 0 else theme.DANGER if p.net < 0 else theme.TEXT_DIM, anchor="topright")
        y = rect.y + 84
        for k, hand in enumerate(p.hands):
            total, soft = hand_value(hand.cards)
            res = RESULT_TEXT[hand.result][0] if hand.result else ("SOFT " if soft else "") + str(total)
            theme.ptext(surf, f"HAND {k + 1}: {res}   BET {hand.bet}", (rect.x + 20, y), 16)
            y += 24
        if not p.hands:
            theme.ptext(surf, "No cards this hand yet", (rect.x + 20, y), 16, theme.TEXT_FAINT)
            y += 24
        theme.ptext(surf, "LAST HANDS", (rect.x + 20, rect.bottom - 62), 12, theme.TEXT_DIM)
        for k, res in enumerate(p.results[-10:]):
            cx = rect.x + 30 + k * 26
            pygame.draw.circle(surf, theme.OUTLINE, (cx, rect.bottom - 28), 11)
            pygame.draw.circle(surf, RESULT_TEXT[res][1], (cx, rect.bottom - 30), 10)
            theme.ptext(surf, RESULT_LETTER[res], (cx, rect.bottom - 30), 10, theme.OUTLINE,
                        None, anchor="center")
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
                theme.ptext(surf, self.name(i), (row.x + 66, row.centery), 20, profile_art.name_rgb(prof, self.clock), anchor="midleft")
                theme.chip(surf, (row.x + 300, row.centery + 2), 11, theme.ACCENT)
                theme.ptext(surf, f"{p.chips} CHIPS", (row.x + 318, row.centery), 22, theme.ACCENT, anchor="midleft")
                net = f"+{p.net}" if p.net > 0 else str(p.net)
                theme.ptext(surf, net, (row.right - 20, row.centery), 20,
                            theme.SUCCESS if p.net > 0 else theme.DANGER if p.net < 0 else theme.TEXT_DIM,
                            anchor="midright")
        for b in self.overlay_buttons:
            b.draw(surf)


def is_bj(cards) -> bool:
    return len(cards) == 2 and hand_value(cards)[0] == 21

