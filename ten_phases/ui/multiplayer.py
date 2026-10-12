"""Multiplayer menus: host a lobby, join by code or from the nearby list."""

from __future__ import annotations

import pygame

from ..net.client import ClientSession
from ..net.discovery import Browser
from ..net.host import HostServer
from ..net.protocol import CODE_ALPHABET, MAX_PLAYERS, NetError, clean_name
from ..settings import DIFFICULTY_CHOICES, SPEED_DELAYS
from . import sfx, theme
from .menus import PRIMARY, Scene, backdrop, status_bar
from .widgets import Button, Segmented, TextInput, copy_text, paste_text

KIND_COLORS = {"host": "ACCENT", "guest": "INFO", "ai": "PANEL_LIGHT"}


def _code_char(ch: str) -> bool:
    return ch in CODE_ALPHABET or ch in "-01 "


class _Flash:
    def __init__(self):
        self.msg, self.t = None, 0.0

    def show(self, msg: str, seconds: float = 3.0):
        self.msg, self.t = msg, seconds

    def tick(self, dt: float):
        self.t -= dt
        if self.t <= 0:
            self.msg = None


def _seat_row(surf, rect: pygame.Rect, idx: int, name: str, kind: str, detail: str = "", you: bool = False):
    theme.rounded(surf, theme.PANEL_HOVER if you else theme.INNER, rect, 10)
    theme.face(surf, (rect.x + 28, rect.centery), 18, idx)
    theme.ptext(surf, name + ("  (YOU)" if you else ""), (rect.x + 58, rect.centery), 18, anchor="midleft")
    label = {"host": "HOST", "guest": "PLAYER", "ai": f"AI {detail.upper()}"}[kind]
    img = theme.pixel_surface(label, 11, theme.OUTLINE, None)
    chip = pygame.Rect(0, 0, img.get_width() + 14, img.get_height() + 4)
    chip.midright = (rect.right - 12, rect.centery)
    theme.rounded(surf, KIND_COLORS[kind], chip, chip.h // 2)
    surf.blit(img, img.get_rect(center=chip.center))
    return chip


# --------------------------------------------------------------------------- start screen


class MultiplayerScene(Scene):
    def __init__(self, app, message: str | None = None):
        super().__init__(app)
        self.flash = _Flash()
        if message:
            self.flash.show(message, 5)
        s = app.settings
        self.name = TextInput((80, 196, 500, 54), s.player_name, max_len=10, placeholder="YOUR NAME")
        self.code = TextInput((80, 450, 500, 58), "", max_len=19, placeholder="ABCDE-FGHJK-LMNPQ",
                              allowed=_code_char, size=22, on_enter=self._join_code)
        self.inputs = [self.name, self.code]
        self.buttons = [
            Button((80, 280, 500, 64), "HOST A GAME", self._host, size=26, **PRIMARY),
            Button((80, 524, 240, 54), "PASTE", self._paste, size=18),
            Button((340, 524, 240, 54), "JOIN", self._join_code, size=22, **PRIMARY),
            Button((80, 670, 240, 54), "BACK", self._back, size=20),
        ]
        self.browser = Browser()
        self.join_buttons: list[tuple[Button, dict]] = []
        self._join_cache: dict[tuple, Button] = {}

    def _player_name(self) -> str:
        name = clean_name(self.name.value)
        self.app.settings.player_name = name
        self.app.settings.save()
        return name

    def _leave(self):
        self.browser.stop()

    def _back(self):
        self._leave()
        from .menus import MenuScene
        self.app.go(MenuScene(self.app))

    def _host(self):
        try:
            server = HostServer(self._player_name(), game=self.app.settings.game)
        except NetError as e:
            sfx.play("error")
            self.flash.show(str(e))
            return
        self._leave()
        self.app.go(HostLobbyScene(self.app, server))

    def _paste(self):
        text = paste_text().strip()
        if not text:
            self.flash.show("Nothing to paste. Type the code instead.")
            return
        self.code.value = ""
        self.code._insert(text)
        self.code.focused = True

    def _join_code(self):
        if not self.code.value.strip():
            sfx.play("error")
            self.flash.show("Enter the invite code from the host.")
            return
        try:
            client = ClientSession.from_code(self._player_name(), self.code.value)
        except NetError as e:
            sfx.play("error")
            self.flash.show(str(e))
            return
        self._leave()
        self.app.go(GuestLobbyScene(self.app, client))

    def _join_nearby(self, game: dict):
        self._leave()
        client = ClientSession(self._player_name(), game["ip"], game["port"], game["key"])
        self.app.go(GuestLobbyScene(self.app, client))

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and not any(i.focused for i in self.inputs):
            self._back()
            return
        for b in self.buttons:
            if b.handle(event):
                return
        for b, _ in self.join_buttons:
            if b.handle(event):
                return
        for i in self.inputs:
            i.handle(event)

    def update(self, dt: float):
        super().update(dt)
        self.flash.tick(dt)
        games = self.browser.list()
        self.join_buttons = []
        for k, g in enumerate(games[:6]):
            key = (g["ip"], g["port"], g.get("key"))
            b = self._join_cache.get(key)
            if b is None:  # buttons must survive between frames or a click never completes
                b = self._join_cache[key] = Button((1094, 0, 120, 50), "JOIN", lambda: None, size=18, **PRIMARY)
            b.on_click = lambda g=g: self._join_nearby(g)
            b.rect.y = 222 + k * 76
            full = g.get("players", 0) >= g.get("max", MAX_PLAYERS)
            b.label = "FULL" if full else "JOIN"
            b.enabled = not full
            self.join_buttons.append((b, g))

    def draw(self, surf):
        backdrop(surf, self.clock)
        theme.logo(surf, "MULTIPLAYER", (theme.WIDTH // 2, 60), 54, angle=4)
        left = pygame.Rect(50, 120, 560, 530)
        theme.panel(surf, left)
        theme.ptext(surf, "YOUR NAME", (80, 152), 20, theme.ACCENT)
        self.name.draw(surf)
        theme.ptext(surf, "JOIN A FRIEND", (80, 384), 20, theme.ACCENT)
        theme.ptext(surf, "Paste the invite code they sent you", (80, 414), 14, theme.TEXT_DIM)
        self.code.draw(surf)
        theme.ptext(surf, "You host on this computer. Up to 6 players.", (80, 352), 13, theme.TEXT_DIM)

        right = pygame.Rect(640, 120, 590, 530)
        theme.panel(surf, right)
        theme.ptext(surf, "GAMES NEARBY", (670, 152), 20, theme.ACCENT)
        theme.ptext(surf, "Hosts on your Wi-Fi show up here", (670, 180), 14, theme.TEXT_DIM)
        if not self.join_buttons:
            dots = "." * (1 + int(self.clock * 2) % 3)
            msg = self.browser.error or f"Looking for games{dots}"
            theme.ptext(surf, msg, right.center, 16, theme.TEXT_DIM, anchor="center")
        for k, (b, g) in enumerate(self.join_buttons):
            row = pygame.Rect(664, 214 + k * 76, 544, 66)
            theme.rounded(surf, theme.INNER, row, 10)
            theme.face(surf, (row.x + 30, row.centery), 20, k + 1)
            theme.ptext(surf, f"{g.get('name', 'HOST')}'S {g.get('game', '10 PHASES')}", (row.x + 62, row.y + 12), 18)
            app_v = f"  -  V{g['app']}" if isinstance(g.get("app"), str) else ""
            theme.ptext(surf, f"{g.get('players', 1)}/{g.get('max', MAX_PLAYERS)} PLAYERS{app_v}",
                        (row.x + 62, row.y + 38), 13, theme.TEXT_DIM)
            b.draw(surf)
        for b in self.buttons:
            b.draw(surf)
        status_bar(surf, self.flash.msg or "Host a game and send the code, or join a friend's.")


# --------------------------------------------------------------------------- host lobby


class HostLobbyScene(Scene):
    def __init__(self, app, server: HostServer):
        super().__init__(app)
        self.server = server
        self.flash = _Flash()
        self.ai_count = Segmented((660, 568, 560, 50), [str(k) for k in range(6)], str(server.ai_count),
                                  self._set_ai, size=18)
        self.ai_level = Segmented((660, 646, 560, 50), list(DIFFICULTY_CHOICES), server.ai_level,
                                  lambda v: server.set_ai_level(v), size=16)
        self.game_pick = Segmented((84, 640, 486, 50), ["10 PHASES", "GO FISH"], server.game, self._set_game, size=16)
        self.public_ip = TextInput((84, 512, 330, 50), "", max_len=15, placeholder="PUBLIC IP",
                                   allowed=lambda ch: ch.isdigit() or ch == ".", size=18, on_enter=self._set_ip)
        self.buttons = [
            Button((84, 310, 250, 54), "COPY CODE", self._copy, size=18, **PRIMARY),
            Button((350, 310, 220, 54), "OTHER ADDRESS", self._next_ip, size=14),
            Button((424, 512, 146, 50), "USE IP", self._set_ip, size=16),
            Button((660, 712, 270, 56), "CANCEL", self._cancel, size=20),
            Button((950, 712, 270, 56), "START GAME", self._start, size=22, **PRIMARY),
        ]
        self.start_button = self.buttons[-1]
        self.kick_buttons: list[Button] = []
        self._kick_cache: dict = {}

    def _set_ai(self, v: str):
        self.server.set_ai_count(int(v))
        self.ai_count.value = str(self.server.ai_count)

    def _copy(self):
        if copy_text(self.server.invite_code):
            self.flash.show("Invite code copied! Send it to your friends.")
        else:
            self.flash.show("Couldn't copy here. Read the code out or type it.")

    def _next_ip(self):
        self.server.next_address()
        self.public_ip.value = ""

    def _set_ip(self):
        parts = self.public_ip.value.split(".")
        if len(parts) != 4 or not all(p.isdigit() and int(p) <= 255 for p in parts):
            sfx.play("error")
            self.flash.show("Type an address like 81.2.69.160")
            return
        self.server.custom_ip = self.public_ip.value
        self.public_ip.focused = False
        self.flash.show("Invite code now uses your public address.")

    def _cancel(self):
        self.server.close()
        self.app.go(MultiplayerScene(self.app))

    def _set_game(self, game: str):
        self.server.set_game(game)
        self.app.settings.game = game
        self.app.settings.save()

    def _start(self):
        try:
            session = self.server.start_game(SPEED_DELAYS[self.app.settings.ai_speed])
        except NetError as e:
            sfx.play("error")
            self.flash.show(str(e))
            return
        if self.server.game == "GO FISH":
            from .gofish_scene import GoFishScene
            self.app.go(GoFishScene(self.app, host=self.server, session=session))
        else:
            from .game_scene import GameScene
            self.app.go(GameScene(self.app, host=self.server, session=session))

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and not self.public_ip.focused:
            self._cancel()
            return
        for b in self.buttons + self.kick_buttons:
            if b.handle(event):
                return
        if self.public_ip.handle(event):
            return
        for c in (self.ai_count, self.ai_level, self.game_pick):
            if c.handle(event):
                return

    def update(self, dt: float):
        super().update(dt)
        self.flash.tick(dt)
        before = len(self.server.guests)
        self.server.pump()
        while self.server.notices:
            note = self.server.notices.pop(0)
            self.flash.show(note.upper() + "!")
            sfx.play("coin" if "joined" in note else "skip")
        if len(self.server.guests) != before:
            self.ai_count.value = str(self.server.ai_count)
        self.kick_buttons = []
        for g in self.server.guests:
            b = self._kick_cache.get(g)
            if b is None:
                b = self._kick_cache[g] = Button((0, 0, 80, 34), "KICK", lambda g=g: self.server.kick(g),
                                                 "DANGER", size=12, radius=8)
            self.kick_buttons.append(b)
        total = 1 + len(self.server.guests) + self.server.ai_count
        self.start_button.enabled = total >= 2

    def draw(self, surf):
        backdrop(surf, self.clock)
        s = self.server
        theme.logo(surf, "LOBBY", (theme.WIDTH // 2, 54), 50, angle=4)

        left = pygame.Rect(50, 110, 560, 600)
        theme.panel(surf, left)
        theme.ptext(surf, "INVITE CODE", (84, 138), 20, theme.ACCENT)
        code_box = pygame.Rect(84, 176, 486, 84)
        theme.rounded(surf, theme.INNER, code_box, 12)
        theme.rounded(surf, theme.ACCENT, code_box, 12, 3)
        theme.ptext(surf, s.invite_code, code_box.center, 34, theme.ACCENT, anchor="center")
        theme.ptext(surf, f"ADDRESS {s.address}  PORT {s.port}", (84, 274), 14, theme.TEXT_DIM)
        theme.ptext(surf, "PLAYING OVER THE INTERNET?", (84, 392), 16, theme.ACCENT)
        y = 418
        for line in ("Same Wi-Fi: friends just pick your game", "under GAMES NEARBY, or use the code.",
                     "Internet: forward TCP port %d on your" % s.port, "router to this PC, then enter your",
                     "public IP below. Or use a VPN like", "Tailscale and pick its 100.x address."):
            theme.ptext(surf, line, (84, y), 12, theme.TEXT_DIM)
            y += 15
        self.public_ip.draw(surf)
        theme.ptext(surf, "Invite codes change every time you host.", (84, 576), 12, theme.TEXT_FAINT)
        theme.ptext(surf, "GAME", (84, 612), 16, theme.ACCENT)
        self.game_pick.draw(surf)

        right = pygame.Rect(640, 110, 600, 586)
        theme.panel(surf, right)
        total = 1 + len(s.guests) + s.ai_count
        theme.ptext(surf, f"PLAYERS {total}/{MAX_PLAYERS}", (660, 138), 20, theme.ACCENT)
        members = s.members()
        for k in range(MAX_PLAYERS):
            row = pygame.Rect(660, 176 + k * 58, 560, 50)
            if k < len(members):
                m = members[k]
                chip = _seat_row(surf, row, k, m["name"], m["kind"], m.get("difficulty", ""), you=k == 0)
                if m["kind"] == "guest":
                    kb = self.kick_buttons[k - 1]
                    kb.rect.midright = (chip.x - 10, row.centery)
            else:
                theme.rounded(surf, theme.INNER, row, 10, 2)
                theme.ptext(surf, "OPEN SEAT - WAITING FOR A FRIEND", row.center, 14, theme.TEXT_FAINT,
                            anchor="center")
        theme.ptext(surf, "COMPUTER PLAYERS", (660, 540), 16, theme.ACCENT)
        theme.ptext(surf, "COMPUTER LEVEL", (660, 622), 16, theme.ACCENT)
        self.ai_count.draw(surf)
        self.ai_level.draw(surf)
        for b in self.buttons + self.kick_buttons:
            b.draw(surf)
        status_bar(surf, self.flash.msg or "Send the invite code to your friends, then press START GAME.")


# --------------------------------------------------------------------------- guest lobby


class GuestLobbyScene(Scene):
    def __init__(self, app, client: ClientSession):
        super().__init__(app)
        self.client = client
        self.flash = _Flash()
        self.leave = Button((theme.WIDTH // 2 - 140, 690, 280, 58), "LEAVE", self._leave, size=22)

    def _leave(self, message: str | None = None):
        self.client.leave()
        self.app.go(MultiplayerScene(self.app, message))

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._leave()
            return
        self.leave.handle(event)

    def update(self, dt: float):
        super().update(dt)
        self.flash.tick(dt)
        c = self.client
        before = len(c.members)
        c.poll()
        if c.status in ("failed", "closed"):
            sfx.play("error")
            self._leave(c.error)
            return
        if len(c.members) > before and before:
            sfx.play("coin")
        if c.game is not None and c.game.players:
            if c.game_name == "GO FISH":
                from .gofish_scene import GoFishScene
                self.app.go(GoFishScene(self.app, client=c))
            else:
                from .game_scene import GameScene
                self.app.go(GameScene(self.app, client=c))

    def draw(self, surf):
        backdrop(surf, self.clock)
        c = self.client
        theme.logo(surf, "LOBBY", (theme.WIDTH // 2, 54), 50, angle=4)
        box = pygame.Rect(theme.WIDTH // 2 - 340, 110, 680, 560)
        theme.panel(surf, box)
        dots = "." * (1 + int(self.clock * 2) % 3)
        if c.status == "connecting":
            title, sub = f"CONNECTING{dots}", f"Reaching {c.ip}:{c.port}"
        elif c.status == "waiting":
            title, sub = f"SAYING HELLO{dots}", "Connected. Joining the lobby"
        else:
            title, sub = f"{c.host_name}'S {c.game_name}", f"Waiting for {c.host_name} to start{dots}"
        theme.ptext(surf, title, (box.centerx, box.y + 36), 26, theme.ACCENT, anchor="center")
        theme.ptext(surf, sub, (box.centerx, box.y + 70), 15, theme.TEXT_DIM, anchor="center")
        for k, m in enumerate(c.members[:MAX_PLAYERS]):
            row = pygame.Rect(box.x + 40, box.y + 110 + k * 64, box.w - 80, 54)
            _seat_row(surf, row, k, m["name"], m["kind"], m.get("difficulty", ""), you=k == c.my_index)
        self.leave.draw(surf)
        status_bar(surf, self.flash.msg or "The host picks the computer players and starts the game.")
