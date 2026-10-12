"""The Cards Against Humanity table.

  top screen     round and score to win, the black card (with the winning answer
                 filled in once the Czar picks), and the scoreboard
  bottom screen  the answers on the table, then your hand of white cards

Blank cards open an editor: type your answer, and (if the game allows it) add a
picture by dropping an image file onto the window or pressing BROWSE.
"""

from __future__ import annotations

import pygame

from ..cah.ai import CahAI
from ..cah.engine import CHIPS_PER_POINT, CahGame, CahOptions, CahPlayer, RuleError, clean_written
from ..names import pick_ai_names
from ..settings import SPEED_DELAYS
from . import cah_art, sfx, theme
from .admin import AdminPanel
from .game_scene import DIFF_COLORS
from .menus import Scene, backdrop, status_bar
from .table_skins import TableSkins
from .widgets import Button, TextInput

HUMAN = 0
SPLIT_Y = 222
INFO_BOX = pygame.Rect(20, 14, 300, 194)
BLACK_BOX = pygame.Rect(340, 14, 600, 194)
SCORE_BOX = pygame.Rect(960, 14, 300, 194)
TABLE = pygame.Rect(20, 238, 1240, 262)
HAND_BOX = pygame.Rect(20, 510, 1240, 254)
CARD_W, CARD_H = 112, 156


def _browse_for_image() -> str | None:
    """A normal 'open file' window, if this computer has one (tkinter)."""
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        return None
    try:
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(title="Pick a picture for your card",
                                          filetypes=[("Pictures", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                                                     ("All files", "*.*")])
        root.destroy()
    except Exception:   # noqa: BLE001 - no display, no Tk: just say it isn't available
        return None
    return path or None


class BlankEditor:
    """The pop-up for writing on a blank card."""

    def __init__(self, scene, card, images_allowed: bool, current: dict | None = None):
        self.scene = scene
        self.card = card
        self.images_allowed = images_allowed
        current = current or {}
        cx = theme.WIDTH // 2
        self.text = TextInput((cx - 300, 520, 600, 54), current.get("text", ""), max_len=80,
                              placeholder="TYPE YOUR ANSWER", allowed=lambda ch: ch.isprintable(), upper=False,
                              size=18, on_enter=self._ok)
        self.text.focused = True
        self.image: str | None = current.get("image")
        self.error = ""
        self.btn_ok = Button((cx + 10, 650, 200, 54), "PLAY THIS", self._ok, "ACCENT", "OUTLINE", 20)
        self.btn_cancel = Button((cx - 210, 650, 200, 54), "CANCEL", self._cancel, size=20)
        self.btn_browse = Button((cx + 320, 340, 170, 48), "BROWSE...", self._browse, size=15)
        self.btn_clear = Button((cx + 320, 398, 170, 48), "NO PICTURE", self._clear, size=15)
        self.buttons = [self.btn_ok, self.btn_cancel] + ([self.btn_browse, self.btn_clear] if images_allowed else [])

    def written(self) -> dict:
        return {"text": self.text.value.strip(), "image": self.image}

    def _ok(self):
        try:
            clean_written(self.written(), self.images_allowed)
        except RuleError as e:
            self.error = str(e)
            sfx.play("error")
            return
        self.scene.finish_blank(self.card, self.written())

    def _cancel(self):
        self.scene.editor = None

    def _browse(self):
        path = _browse_for_image()
        if path:
            self.use_file(path)
        elif path is None:
            self.error = "No file window here - drag a picture onto the game window instead."

    def _clear(self):
        self.image = None

    def use_file(self, path: str):
        if not self.images_allowed:
            self.error = "Pictures are turned off for this game."
            sfx.play("error")
            return
        try:
            self.image = cah_art.encode_image_file(path)
            self.error = ""
            sfx.play("coin")
        except ValueError as e:
            self.error = str(e)
            sfx.play("error")

    def handle(self, event):
        if event.type == pygame.DROPFILE:
            self.use_file(event.file)
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._cancel()
            return
        if self.text.handle(event):
            return
        for b in self.buttons:
            if b.handle(event):
                return

    def draw(self, surf):
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, 200))
        surf.blit(shade, (0, 0))
        cx = theme.WIDTH // 2
        panel = pygame.Rect(cx - 340, 120, 680, 610)
        theme.panel(surf, panel, edge=theme.ACCENT, edge_w=3)
        theme.ptext(surf, "YOUR BLANK CARD", (cx, 150), 26, theme.ACCENT, anchor="center")
        w = self.written()
        card = cah_art.white_card(w["text"], 220, 300, blank=True, image=self.image,
                                  image_key=str(hash(self.image)) if self.image else None)
        surf.blit(card, card.get_rect(midtop=(cx, 180)))
        self.text.draw(surf)
        if self.images_allowed:
            theme.ptext(surf, "ADD A PICTURE:", (cx + 320, 220), 15, theme.ACCENT)
            theme.text(surf, "Drag an image file", (cx + 320, 248), 13, theme.TEXT_DIM, bold=False)
            theme.text(surf, "onto the game window,", (cx + 320, 266), 13, theme.TEXT_DIM, bold=False)
            theme.text(surf, "or press BROWSE.", (cx + 320, 284), 13, theme.TEXT_DIM, bold=False)
        if self.error:
            theme.ptext(surf, self.error, (cx, 600), 15, theme.DANGER, anchor="center")
        else:
            theme.ptext(surf, f"{len(self.text.value)}/80 characters", (cx, 600), 13, theme.TEXT_DIM, anchor="center")
        for b in self.buttons:
            b.draw(surf)


class CahScene(Scene):
    """Local by default (pass packs/options); `host` + `session` to host, or `client` to join."""

    def __init__(self, app, host=None, session=None, client=None, packs=None, options: CahOptions | None = None):
        super().__init__(app)
        s = app.settings
        self.host, self.session, self.client = host, session, client
        if session is not None:
            self.game, self.ais = session.game, session.ais
        elif client is not None:
            self.game, self.ais = client.game, {}
        else:
            diffs = s.opponent_difficulties()
            while len(diffs) < 2:   # it takes three to play
                diffs.append(diffs[-1] if diffs else "Medium")
            names = pick_ai_names(len(diffs), taken=["YOU", s.player_name])
            players = [CahPlayer("YOU", is_human=True)] + [CahPlayer(n, difficulty=d) for n, d in zip(names, diffs)]
            self.game = CahGame(players, packs or [], options)
            self.ais = {i + 1: CahAI(d) for i, d in enumerate(diffs)}
        self.skins = TableSkins(self)
        self.admin = AdminPanel(self)
        self.delay = SPEED_DELAYS[s.ai_speed]
        self.selected: list[int] = []          # card ids, in the order they'll be played
        self.written: dict[int, dict] = {}     # blank card id -> what you wrote
        self.editor: BlankEditor | None = None
        self.pick_sub: int | None = None       # the answer the Czar has clicked
        self.flash: tuple[str, float] | None = None
        self.splash: tuple[str, str, float, float] | None = ("CARDS AGAINST HUMANITY",
                                                             f"FIRST TO {self.game.options.points_to_win} POINTS WINS",
                                                             1.8, 1.8)
        self.overlay: str | None = None
        self._pending_overlay = False
        self._banked: int | None = None
        self.ai_timers: dict[int, float] = {}
        self.result_timer = 0.0
        self.judge_timer = 0.0
        self.btn_submit = Button((1040, 440, 210, 50), "PLAY CARDS", self.submit, "ACCENT", "OUTLINE", 18)
        self.btn_clear = Button((820, 440, 210, 50), "CLEAR", self.clear, size=16)
        self.btn_judge = Button((1040, 440, 210, 50), "PICK WINNER", self.judge, "ACCENT", "OUTLINE", 18)
        self.btn_menu = Button((30, 440, 120, 44), "MENU", lambda: self._set_overlay("pause"), size=15)
        self.buttons = [self.btn_submit, self.btn_clear, self.btn_judge, self.btn_menu]
        self.overlay_buttons: list[Button] = []
        self._consume_events()
        sfx.play("shuffle")

    # ================================================================== helpers

    @property
    def me(self) -> CahPlayer:
        return self.game.players[HUMAN]

    @property
    def networked(self) -> bool:
        return self.host is not None or self.client is not None

    @property
    def busy(self) -> bool:
        return self.splash is not None or self.overlay is not None or getattr(self.game, "pending", False)

    @property
    def flow_blocked(self) -> bool:
        if self.admin.blocking:
            return True
        if self.splash is not None:
            return True
        return self.overlay is not None and not (self.overlay == "pause" and self.networked)

    def i_am_czar(self) -> bool:
        return self.game.czar == HUMAN

    def can_play(self) -> bool:
        g = self.game
        return not self.busy and g.phase == "picking" and not self.i_am_czar() and not self.me.submitted

    def can_judge(self) -> bool:
        return not self.busy and self.game.phase == "judging" and self.i_am_czar()

    def name(self, i) -> str:
        return "YOU" if i == HUMAN else self.game.players[i].name

    def error(self, msg: str):
        self.flash = (msg, 2.8)
        sfx.play("error")

    def hand_rect(self, k: int, n: int) -> pygame.Rect:
        step = min(CARD_W + 10, (HAND_BOX.w - 40 - CARD_W) / max(1, n - 1)) if n > 1 else 0
        x0 = HAND_BOX.x + 20
        return pygame.Rect(int(x0 + k * step), HAND_BOX.y + 70, CARD_W, CARD_H)

    def answer_layout(self) -> list[tuple[object, list[pygame.Rect]]]:
        """Where each answer sits on the table during judging and results."""
        subs = self.game.order
        if not subs:
            return []
        pick = len(subs[0].cards)
        gap, inner = 26, 6
        total_cards = len(subs) * pick
        w = int(min(CARD_W, (TABLE.w - 40 - gap * (len(subs) - 1) - inner * (total_cards - len(subs))) / total_cards))
        h = int(w * CARD_H / CARD_W)
        group_w = pick * w + (pick - 1) * inner
        full = len(subs) * group_w + (len(subs) - 1) * gap
        x = TABLE.centerx - full // 2
        out = []
        for sub in subs:
            rects = [pygame.Rect(x + k * (w + inner), TABLE.y + 46, w, h) for k in range(len(sub.cards))]
            out.append((sub, rects))
            x += group_w + gap
        return out

    # ================================================================== events

    def _consume_events(self):
        g = self.game
        for ev in g.pop_events():
            k = ev.kind
            if k == "round_start":
                self.selected, self.pick_sub = [], None
                self.written = {}
                self.ai_timers = {}
                if ev.player == HUMAN:
                    self.flash = ("You're the Card Czar! Wait for the answers, then pick the funniest.", 3.5)
                sfx.play("turn" if ev.player == HUMAN else "draw")
            elif k == "submit":
                sfx.play("lay" if ev.player == HUMAN else "click")
            elif k == "judging":
                self.judge_timer = 1.6 + self.delay
                sfx.play("shuffle")
                if g.czar == HUMAN:
                    self.flash = ("Read them all, click the funniest, then press PICK WINNER.", 4.0)
            elif k == "win":
                self.result_timer = 4.5
                if ev.player == HUMAN:
                    sfx.play("round_win")
                    self.splash = ("YOU WIN THE ROUND!", f"{ev.amount} POINT{'S' if ev.amount != 1 else ''}", 1.4,
                                   1.4)
                else:
                    sfx.play("coin")
            elif k == "reshuffle":
                sfx.play("shuffle")
            elif k == "game_over":
                self._pending_overlay = True

    # ================================================================== actions

    def click_hand(self, card):
        if not self.can_play():
            if self.i_am_czar() and self.game.phase == "picking":
                self.error("You're the Card Czar this round - you'll judge the answers.")
            return
        if card.id in self.selected:
            self.selected.remove(card.id)
            self.written.pop(card.id, None)
            sfx.play("deselect")
            return
        if len(self.selected) >= self.game.black.pick:
            if self.game.black.pick == 1:
                self.selected, self.written = [], {}
            else:
                self.error(f"You've picked {self.game.black.pick} - click one to take it back.")
                return
        if card.blank:
            self.editor = BlankEditor(self, card, self.game.options.images, self.written.get(card.id))
            return
        self.selected.append(card.id)
        sfx.play("select")

    def finish_blank(self, card, written: dict):
        self.editor = None
        self.written[card.id] = written
        if card.id not in self.selected:
            self.selected.append(card.id)
        sfx.play("select")

    def clear(self):
        self.selected, self.written = [], {}
        sfx.play("deselect")

    def submit(self):
        if not self.can_play():
            return
        try:
            self.game.submit(HUMAN, list(self.selected), dict(self.written))
        except RuleError as e:
            self.error(str(e))
            return
        self.selected, self.written = [], {}
        self._consume_events()

    def judge(self):
        if not self.can_judge():
            return
        if self.pick_sub is None:
            self.error("Click the answer you like best first.")
            return
        try:
            self.game.judge(HUMAN, self.pick_sub)
        except RuleError as e:
            self.error(str(e))
            return
        self._consume_events()

    def run_ai(self, dt: float):
        g = self.game
        if g.phase == "picking":
            for i in g.waiting_on():
                if i not in self.ais:
                    continue
                t = self.ai_timers.setdefault(i, 0.8 + self.delay * (1 + 0.5 * (i % 3)))
                t -= dt
                self.ai_timers[i] = t
                if t <= 0:
                    ids, written = self.ais[i].choose_cards(g, i)
                    try:
                        g.submit(i, ids, written)
                    except RuleError:
                        continue
                    self._consume_events()
                    return
        elif g.phase == "judging" and g.czar in self.ais:
            self.judge_timer -= dt
            if self.judge_timer <= 0:
                g.judge(g.czar, self.ais[g.czar].choose_winner(g, g.czar))
                self._consume_events()
        elif g.phase == "results" and self.client is None:
            self.result_timer -= dt
            if self.result_timer <= 0:
                g.next_round()
                self._consume_events()

    # ================================================================== network

    def _pump_network(self):
        if self.host is not None:
            self.host.pump()
            while self.session.notices:
                self.flash = (self.session.notices.pop(0), 3.0)
                sfx.play("skip")
        if self.client is not None:
            for msg in self.client.poll():
                t = msg["t"]
                if t == "error":
                    self.error(msg.get("msg", "That move wasn't allowed."))
                elif t == "notice":
                    self.flash = (msg.get("msg", ""), 3.0)
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

        def restart():
            from .cah_setup import CahSetupScene
            self.app.go(CahSetupScene(self.app))
        if kind == "game":
            sfx.play("game_win" if HUMAN in self.game.winners() else "game_lose")
            if self._banked is None:
                self._banked = self.me.points * CHIPS_PER_POINT
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
                options = [("RESUME", resume), ("LEAVE GAME", self.to_menu)]
            else:
                options = [("RESUME", resume), ("NEW GAME", restart), ("MAIN MENU", self.to_menu)]
            self.overlay_buttons = [Button((cx - 140, 300 + k * 68, 280, 56), label, fn, size=22 if k == 0 else 20,
                                           **(primary if k == 0 else {})) for k, (label, fn) in enumerate(options)]
        else:
            self.overlay_buttons = []

    def to_menu(self):
        self.leave_network()
        from .menus import MenuScene
        self.app.go(MenuScene(self.app))

    # ================================================================== input

    def handle(self, event):
        if self.admin.handle(event):
            return
        if self.editor is not None:
            self.editor.handle(event)
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
            if event.key == pygame.K_ESCAPE:
                self._set_overlay("pause")
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.judge() if self.can_judge() else self.submit()
            return
        for b in self.buttons:
            if b.visible and b.handle(event):
                return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            g = self.game
            if g.phase == "judging":
                for sub, rects in self.answer_layout():
                    if any(r.collidepoint(event.pos) for r in rects):
                        if self.can_judge():
                            self.pick_sub = sub.id
                            sfx.play("select")
                        return
            hand = self.me.hand
            for k in reversed(range(len(hand))):
                if self.hand_rect(k, len(hand)).collidepoint(event.pos):
                    self.click_hand(hand[k])
                    return

    # ================================================================== update

    def update(self, dt: float):
        super().update(dt)
        self.admin.update(dt)
        self._pump_network()
        if self.game.events:
            self._consume_events()
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None
        if self.splash:
            t, s, left, total = self.splash
            self.splash = (t, s, left - dt, total) if left > dt else None
        if self._pending_overlay and not self.splash:
            self._set_overlay("game")
            return
        g = self.game
        ids = {c.id for c in self.me.hand}
        self.selected = [cid for cid in self.selected if cid in ids]
        if self.flow_blocked or g.game_over:
            return
        self.run_ai(dt)

    # ================================================================== drawing

    def draw(self, surf):
        backdrop(surf, self.clock, SPLIT_Y)
        self._draw_info(surf)
        self._draw_black(surf)
        self._draw_scores(surf)
        self._draw_table(surf)
        self._draw_hand(surf)
        status_bar(surf, self.flash[0] if self.flash else self._status())
        if self.splash:
            self._draw_splash(surf)
        if self.editor:
            self.editor.draw(surf)
        if self.overlay:
            self._draw_overlay(surf)
        self.admin.draw(surf)

    def _status(self) -> str:
        g = self.game
        if g.game_over:
            return "Game over!"
        if g.phase == "picking":
            if self.i_am_czar():
                return f"You're the Card Czar. Waiting for {len(g.waiting_on())} answer(s)..."
            if self.me.submitted:
                return f"Answer played! Waiting for {len(g.waiting_on())} more..."
            pick = g.black.pick
            return f"Pick {pick} white card{'s' if pick > 1 else ''}{' in order' if pick > 1 else ''}, " \
                   "then press PLAY CARDS. Blank cards let you write your own."
        if g.phase == "judging":
            return "Click the funniest answer, then PICK WINNER." if self.i_am_czar() else \
                f"{self.name(g.czar)} is picking the winner..."
        if g.phase == "results":
            return f"{self.name(g.winner)} won the round! Next round coming up..."
        return ""

    def _draw_info(self, surf):
        g = self.game
        theme.panel(surf, INFO_BOX)
        theme.ptext(surf, "CARDS AGAINST", (INFO_BOX.x + 16, INFO_BOX.y + 10), 20, theme.ACCENT)
        theme.ptext(surf, "HUMANITY", (INFO_BOX.x + 16, INFO_BOX.y + 34), 20, theme.ACCENT)
        theme.ptext(surf, f"ROUND {max(1, g.round)}", (INFO_BOX.x + 16, INFO_BOX.y + 66), 20)
        theme.ptext(surf, f"FIRST TO {g.options.points_to_win}", (INFO_BOX.x + 150, INFO_BOX.y + 68), 16, theme.INFO)
        theme.ptext(surf, f"CZAR: {self.name(g.czar)}", (INFO_BOX.x + 16, INFO_BOX.y + 96), 16, theme.CARD_WHITE)
        packs = g.pack_names
        label = f"{len(packs)} PACK{'S' if len(packs) != 1 else ''}: " + ", ".join(packs)
        for k, line in enumerate(cah_art.wrap(label, theme.font(12, False), INFO_BOX.w - 32)[:3]):
            theme.text(surf, line, (INFO_BOX.x + 16, INFO_BOX.y + 124 + k * 16), 12, theme.TEXT_DIM, bold=False)
        theme.text(surf, f"{len(g.white_deck)} white cards left", (INFO_BOX.x + 16, INFO_BOX.bottom - 22), 12,
                   theme.TEXT_FAINT, bold=False)

    def _draw_black(self, surf):
        g = self.game
        theme.panel(surf, BLACK_BOX, edge=theme.ACCENT if g.phase == "results" else theme.PANEL_EDGE)
        if not g.black:
            return
        card = cah_art.black_card(g.black.text, g.black.pick, 150, 182)
        surf.blit(card, (BLACK_BOX.x + 8, BLACK_BOX.y + 6))
        area = pygame.Rect(BLACK_BOX.x + 176, BLACK_BOX.y + 14, BLACK_BOX.w - 192, BLACK_BOX.h - 28)
        show = None
        if g.phase in ("results", "game_over") and g.winning:
            show = g.winning
        elif g.phase == "judging":
            mouse = pygame.mouse.get_pos()
            hovered = next((s for s, rects in self.answer_layout() if any(r.collidepoint(mouse) for r in rects)), None)
            show = hovered or next((s for s in g.order if s.id == self.pick_sub), None)
        if show:
            box = area.inflate(8, 8)
            theme.rounded(surf, cah_art.INK, box, 10)
            words = cah_art.filled_sentence(g.black.text, [show.card_text(c) or "[a picture]" for c in show.cards])
            cah_art.draw_sentence(surf, words, area.inflate(-8, -24), 24)
            if g.phase != "judging":
                theme.ptext(surf, f"{self.name(g.winner)} WINS THE ROUND!", (area.centerx, area.bottom - 6), 16,
                            theme.SUCCESS, anchor="midbottom")
        else:
            msg = {"picking": "Everyone plays their funniest answer.", "judging": "Hover an answer to read it."}
            theme.ptext(surf, msg.get(g.phase, ""), area.center, 18, theme.TEXT_DIM, anchor="center")

    def _draw_scores(self, surf):
        g = self.game
        theme.panel(surf, SCORE_BOX)
        theme.ptext(surf, "POINTS", (SCORE_BOX.x + 14, SCORE_BOX.y + 8), 16, theme.ACCENT)
        n = len(g.players)
        row_h = min(26, (SCORE_BOX.h - 36) // max(1, n))
        for k, i in enumerate(range(n)):
            p = g.players[i]
            y = SCORE_BOX.y + 32 + k * row_h
            theme.face(surf, (SCORE_BOX.x + 24, y + row_h // 2), max(8, row_h // 2 - 2), i)
            color = theme.ACCENT if i == g.czar else theme.TEXT
            theme.ptext(surf, self.name(i)[:12], (SCORE_BOX.x + 44, y + 2), 14, color)
            if i == g.czar:
                theme.ptext(surf, "CZAR", (SCORE_BOX.x + 170, y + 3), 11, theme.ACCENT)
            elif g.phase == "picking" and p.submitted:
                pygame.draw.lines(surf, theme.SUCCESS, False, [(SCORE_BOX.x + 172, y + 10), (SCORE_BOX.x + 178,
                                  y + 16), (SCORE_BOX.x + 190, y + 4)], 3)
            theme.ptext(surf, str(p.points), (SCORE_BOX.right - 16, y + 1), 16, theme.ACCENT, anchor="topright")

    def _draw_table(self, surf):
        g = self.game
        theme.panel(surf, TABLE)
        if g.phase == "picking":
            answers = [i for i, p in enumerate(g.players) if p.submitted and i != g.czar]
            theme.ptext(surf, "ANSWERS IN", (TABLE.x + 20, TABLE.y + 14), 18, theme.ACCENT)
            total = len(g.players) - 1
            for k in range(total):
                r = pygame.Rect(TABLE.x + 30 + k * 96, TABLE.y + 56, 80, 112)
                if k < len(answers):   # a face-down answer
                    theme.rounded(surf, cah_art.PAPER, r, 8)
                    pygame.draw.rect(surf, cah_art.INK, r.inflate(-12, -12), 0, border_radius=6)
                    theme.ptext(surf, "?", r.center, 30, cah_art.PAPER, None, anchor="center")
                else:
                    theme.rounded(surf, theme.INNER, r, 8)
                    theme.rounded(surf, theme.PANEL_LIGHT, r, 8, 2)
            mine = g.submissions.get(HUMAN)
            if mine:
                theme.ptext(surf, "YOUR ANSWER", (TABLE.x + 640, TABLE.y + 14), 16, theme.ACCENT)
                for k, c in enumerate(mine.cards):
                    w = mine.written.get(c.id)
                    img = cah_art.white_card(mine.card_text(c), CARD_W, CARD_H, c.blank, w.image if w else None,
                                             w.image_id if w else None)
                    surf.blit(img, (TABLE.x + 640 + k * (CARD_W + 8), TABLE.y + 46))
            elif self.i_am_czar():
                theme.ptext(surf, "YOU'RE THE CARD CZAR", (TABLE.x + 700, TABLE.y + 90), 24, theme.ACCENT)
                theme.ptext(surf, "Wait for the answers, then pick the funniest.", (TABLE.x + 700, TABLE.y + 130),
                            15, theme.TEXT_DIM)
            for b in (self.btn_submit, self.btn_clear):
                b.visible = self.can_play()
            self.btn_submit.enabled = len(self.selected) == g.black.pick
            self.btn_judge.visible = False
        else:
            title = "PICK THE FUNNIEST" if self.can_judge() else "THE ANSWERS"
            theme.ptext(surf, title, (TABLE.x + 20, TABLE.y + 12), 18, theme.ACCENT)
            mouse = pygame.mouse.get_pos()
            for sub, rects in self.answer_layout():
                winner = g.phase != "judging" and g.winning is not None and sub.id == g.winning.id
                chosen = sub.id == self.pick_sub
                hover = g.phase == "judging" and any(r.collidepoint(mouse) for r in rects)
                lift = -8 if hover or chosen else 0
                for c, r in zip(sub.cards, rects):
                    w = sub.written.get(c.id)
                    img = cah_art.white_card(sub.card_text(c), r.w, r.h, c.blank, w.image if w else None,
                                             w.image_id if w else None,
                                             dim=g.phase != "judging" and not winner)
                    surf.blit(img, r.move(0, lift))
                group = rects[0].unionall(rects[1:]).move(0, lift).inflate(10, 10)
                if winner or chosen:
                    pygame.draw.rect(surf, theme.SUCCESS if winner else theme.ACCENT, group, 4, border_radius=12)
                if g.phase != "judging" and sub.player is not None and sub.player >= 0:
                    theme.ptext(surf, self.name(sub.player), (group.centerx, group.bottom + 4), 15,
                                theme.SUCCESS if winner else theme.TEXT, anchor="midtop")
            for b in (self.btn_submit, self.btn_clear):
                b.visible = False
            self.btn_judge.visible = self.can_judge()
            self.btn_judge.enabled = self.pick_sub is not None
        for b in self.buttons:
            b.draw(surf)

    def _draw_hand(self, surf):
        g = self.game
        theme.panel(surf, HAND_BOX, edge=theme.ACCENT if self.can_play() else theme.PANEL_EDGE,
                    edge_w=3 if self.can_play() else 2)
        title = "YOUR CARDS" + ("  -  you're judging this round" if self.i_am_czar() and g.phase == "picking" else "")
        theme.ptext(surf, title, (HAND_BOX.x + 20, HAND_BOX.y + 12), 18, theme.ACCENT)
        if g.phase == "picking" and self.can_play():
            theme.ptext(surf, f"PICK {g.black.pick}: {len(self.selected)} CHOSEN", (HAND_BOX.right - 20,
                        HAND_BOX.y + 14), 16, theme.TEXT, anchor="topright")
        hand = self.me.hand
        mouse = pygame.mouse.get_pos()
        hovered = None
        for k, c in enumerate(hand):
            r = self.hand_rect(k, len(hand))
            order = self.selected.index(c.id) + 1 if c.id in self.selected else None
            w = self.written.get(c.id, {})
            text = w.get("text", "") if c.blank else c.text
            img = cah_art.white_card(text, r.w, r.h, c.blank, w.get("image"),
                                     str(hash(w["image"])) if w.get("image") else None,
                                     selected=order if g.black and g.black.pick > 1 else (1 if order else None),
                                     dim=not self.can_play())
            lift = -16 if order else (-6 if r.collidepoint(mouse) and self.can_play() else 0)
            surf.blit(img, r.move(0, lift))
            if order:
                pygame.draw.rect(surf, theme.ACCENT, r.move(0, lift).inflate(6, 6), 3, border_radius=12)
            if r.collidepoint(mouse):
                hovered = (c, text, w)
        if hovered and not self.editor and not self.overlay:
            c, text, w = hovered
            big = cah_art.white_card(text, 200, 276, c.blank, w.get("image"),
                                     str(hash(w["image"])) if w.get("image") else None)
            mx = max(10, min(theme.WIDTH - 210, mouse[0] - 100))
            surf.blit(big, (mx, HAND_BOX.y - 290))

    def _draw_splash(self, surf):
        title, sub, t, total = self.splash
        k = min(1.0, (total - t) / 0.25, t / 0.3)
        band = pygame.Rect(0, 300, theme.WIDTH, 170)
        shade = pygame.Surface(band.size, pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, int(200 * k)))
        surf.blit(shade, band)
        theme.logo(surf, title, (theme.WIDTH // 2 + int((1 - k) * -300), band.y + 70), 56, angle=4)
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
            bank = f"+{self._banked or 0} CHIPS BANKED ({CHIPS_PER_POINT} PER POINT)   BANK: " \
                   f"{self.app.settings.chip_bank:,}"
            r_ = theme.ptext(surf, bank, (cx + 12, 206), 16, theme.ACCENT, anchor="center")
            theme.chip(surf, (r_.x - 16, r_.centery + 2), 10, theme.ACCENT)
            for k, i in enumerate(g.standings()):
                p = g.players[i]
                row = pygame.Rect(panel.x + 30, 240 + k * 58, panel.w - 60, 50)
                theme.rounded(surf, theme.PANEL_HOVER if i == HUMAN else theme.INNER, row, 10)
                theme.face(surf, (row.x + 34, row.centery), 18, i)
                theme.ptext(surf, self.name(i), (row.x + 66, row.centery), 20, anchor="midleft")
                label = p.difficulty.upper() if p.difficulty else "PLAYER"
                color = DIFF_COLORS.get(p.difficulty, theme.CARD_WHITE)
                theme.ptext(surf, label, (row.x + 320, row.centery), 14, color, anchor="midleft")
                theme.ptext(surf, f"{p.points} POINT{'S' if p.points != 1 else ''}", (row.right - 20, row.centery),
                            22, theme.ACCENT, anchor="midright")
        for b in self.overlay_buttons:
            b.draw(surf)

