"""Main menu, settings and how-to-play screens."""

from __future__ import annotations

import math
import random
import webbrowser

import pygame

from .. import __version__

from ..cards import COLORS, number, skip, wild
from ..phases import NUM_PHASES, describe_phase
from ..settings import DIFFICULTY_CHOICES, SFX_CHOICES, SPEED_CHOICES
from . import sfx, theme
from .card_art import card_with_shadow
from .widgets import Button, Segmented

PRIMARY = dict(color="ACCENT", text_color="OUTLINE")


class Scene:
    def __init__(self, app):
        self.app = app
        self.clock = 0.0

    def handle(self, event): ...

    def update(self, dt: float):
        self.clock += dt

    def draw(self, surf): ...


def backdrop(surf, t: float = 0.0, split_y: int | None = None):
    surf.blit(theme.background(split_y), (0, 0))
    theme.twinkle(surf, t)


def status_bar(surf, msg: str):
    pygame.draw.rect(surf, theme.STATUS_BAR, (0, theme.HEIGHT - 30, theme.WIDTH, 30))
    theme.ptext(surf, msg, (theme.WIDTH // 2, theme.HEIGHT - 15), 18, theme.TEXT, None, anchor="center")


UPDATE_CARD = pygame.Rect(896, 500, 364, 220)
GAMES = ("10 PHASES", "GO FISH", "BLACKJACK", "POKER", "CAH", "MONOPOLY", "DEEP DIG", "SLOTS")
TITLES = {"CAH": "CARDS AGAINST HUMANITY"}
SINGLE_PLAYER = ("SLOTS", "DEEP DIG")
ARROW_LEFT = pygame.Rect(278, 236, 76, 96)
PROFILE_CARD = pygame.Rect(20, 162, 250, 104)
ARROW_RIGHT = pygame.Rect(926, 236, 76, 96)


class MenuScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = theme.WIDTH // 2
        self.buttons = [
            Button((cx - 150, 410, 300, 58), "PLAY", self._play, size=30, **PRIMARY),
            Button((cx - 150, 476, 300, 48), "MULTIPLAYER", self._multiplayer),
            Button((cx - 150, 530, 300, 46), "SETTINGS", lambda: app.go(SettingsScene(app))),
            Button((cx - 150, 582, 300, 46), "CUSTOMIZE", self._customize),
            Button((cx - 150, 634, 300, 46), "HOW TO PLAY", self._how_to),
            Button((cx - 150, 686, 300, 46), "QUIT", app.quit),
        ]
        self.btn_multi = self.buttons[1]
        self.btn_shop = Button((20, 106, 250, 44), "SHOP", self._shop, size=18, **PRIMARY)
        self.buttons.append(self.btn_shop)
        self.game = app.settings.game if app.settings.game in GAMES else GAMES[0]
        self.slide = 0.0          # -1..1 while the title/fan slides after switching games
        self._build_fan()
        card = UPDATE_CARD
        self.btn_restart = Button((card.x + 18, card.bottom - 62, 196, 46), "RESTART NOW", app.restart_for_update,
                                  size=16, **PRIMARY)
        self.btn_later = Button((card.right - 120, card.bottom - 62, 102, 46), "LATER", self._later, size=16)
        self.btn_get = Button((card.x + 18, card.bottom - 62, card.w - 36, 46), "GET IT ON GITHUB", self._open_release,
                              size=16, **PRIMARY)
        self.update_buttons = [self.btn_restart, self.btn_later, self.btn_get]

    def _build_fan(self):
        rng = random.Random()
        if self.game in ("CAH", "MONOPOLY", "DEEP DIG"):
            self.fan = []   # drawn in draw()
        elif self.game == "SLOTS":
            self.fan = [None, None, None]   # three jackpot card backs
        elif self.game == "POKER":
            from ..poker.engine import poker_card
            col = rng.choice(COLORS)
            royal = [poker_card(col, v) for v in (10, 11, 12, 13, 14)]
            quads = [poker_card(c, 14) for c in COLORS] + [poker_card(rng.choice(COLORS), 13)]
            self.fan = royal if rng.random() < 0.5 else quads
        elif self.game == "BLACKJACK":
            from ..blackjack.engine import bj_card
            cols = rng.sample(COLORS, 4)
            self.fan = [bj_card(cols[0], 1), bj_card(cols[1], 13), bj_card(cols[2], 12), bj_card(cols[3], 11),
                        bj_card(cols[0], 10)][:rng.choice([2, 5])]
        elif self.game == "GO FISH":
            v = rng.randint(1, 12)
            w = rng.choice([x for x in range(1, 13) if x != v])
            self.fan = [number(c, w) for c in COLORS[:3]] + [number(c, v) for c in COLORS]
            self.fan = self.fan[3:] if rng.random() < 0.5 else self.fan
        else:
            deck = [number(c, v) for c in COLORS for v in range(1, 13)] + [wild(), wild(), skip()]
            self.fan = rng.sample(deck, 7)

    def switch_game(self, step: int):
        k = (GAMES.index(self.game) + step) % len(GAMES)
        self.game = GAMES[k]
        self.app.settings.game = self.game
        self.app.settings.save()
        self.slide = float(step)
        self._build_fan()
        sfx.play("phase")

    def _how_to(self):
        self.app.go(HowToScene(self.app, self.game))

    def _later(self):
        self.app.updater.dismissed = True

    def _open_release(self):
        info = self.app.updater.info
        webbrowser.open(info.page_url if info else "https://github.com")

    def _multiplayer(self):
        from .multiplayer import MultiplayerScene
        self.app.go(MultiplayerScene(self.app))

    def _customize(self):
        from .customize import CustomizeScene
        self.app.go(CustomizeScene(self.app))

    def _shop(self):
        from .shop_scene import ShopScene
        self.app.go(ShopScene(self.app))

    def _profile(self):
        from .profile_scene import ProfileScene
        self.app.go(ProfileScene(self.app))

    def _play(self):
        if self.game == "DEEP DIG":
            from .deepdig_scene import DeepDigScene
            self.app.go(DeepDigScene(self.app))
        elif self.game == "MONOPOLY":
            from .monopoly_setup import MonopolySetupScene
            self.app.go(MonopolySetupScene(self.app))
        elif self.game == "CAH":
            from .cah_setup import CahSetupScene
            self.app.go(CahSetupScene(self.app))
        elif self.game == "SLOTS":
            from .slots_scene import SlotsScene
            self.app.go(SlotsScene(self.app))
        elif self.game == "BLACKJACK":
            from .blackjack_scene import BlackjackScene
            self.app.go(BlackjackScene(self.app))
        elif self.game == "POKER":
            from .poker_scene import PokerScene
            self.app.go(PokerScene(self.app))
        elif self.game == "GO FISH":
            from .gofish_scene import GoFishScene
            self.app.go(GoFishScene(self.app))
        else:
            from .game_scene import GameScene
            self.app.go(GameScene(self.app))

    def handle(self, event):
        for b in self.buttons + self.update_buttons:
            if b.visible and b.handle(event):
                return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._play()
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.switch_game(-1 if event.key == pygame.K_LEFT else 1)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if PROFILE_CARD.collidepoint(event.pos):
                sfx.play("select")
                self._profile()
            elif ARROW_LEFT.collidepoint(event.pos):
                self.switch_game(-1)
            elif ARROW_RIGHT.collidepoint(event.pos):
                self.switch_game(1)

    def update(self, dt: float):
        super().update(dt)
        if self.slide:
            self.slide = max(0.0, self.slide - dt * 4) if self.slide > 0 else min(0.0, self.slide + dt * 4)

    def _draw_arrow(self, surf, rect: pygame.Rect, direction: int):
        """A chunky pixel-style arrow that bobs and grows on hover."""
        hover = rect.collidepoint(pygame.mouse.get_pos())
        bob = math.sin(self.clock * 4) * 5 * direction
        cx, cy = rect.centerx + bob, rect.centery
        size = 34 if hover else 28
        pts = [(cx - size * 0.6 * direction, cy - size), (cx + size * 0.8 * direction, cy),
               (cx - size * 0.6 * direction, cy + size)]
        pygame.draw.polygon(surf, theme.OUTLINE, [(x, y + 5) for x, y in pts])
        pygame.draw.polygon(surf, theme.OUTLINE, pts)
        inner = [(cx - (size - 6) * 0.6 * direction, cy - size + 9), (cx + (size - 8) * 0.8 * direction, cy),
                 (cx - (size - 6) * 0.6 * direction, cy + size - 9)]
        pygame.draw.polygon(surf, theme.ACCENT if hover else theme.CARD_WHITE, inner)

    def _draw_update(self, surf):
        """Version in the corner, plus a card while an update is downloading or ready."""
        up = self.app.updater
        for b in self.update_buttons:
            b.visible = False
        note = {"checking": "checking for updates...", "current": "up to date",
                "failed": up.error or "", "downloading": "downloading update...",
                "installed": "update installed"}.get(up.state, "")
        if up.state == "ready" and getattr(up, "dismissed", False):
            note = f"v{up.info.version} installs when you quit"
        version = f"v{__version__}" + (f"  -  {note}" if note else "")
        theme.ptext(surf, version, (16, theme.HEIGHT - 42), 14, theme.TEXT_DIM, anchor="bottomleft")
        if up.info is None or up.state not in ("downloading", "ready", "available") or getattr(up, "dismissed", False):
            return
        card = UPDATE_CARD
        theme.panel(surf, card, edge=theme.ACCENT, edge_w=3)
        title = {"downloading": "NEW VERSION!", "ready": "UPDATE READY!", "available": "NEW VERSION OUT!"}[up.state]
        theme.ptext(surf, title, (card.x + 18, card.y + 14), 20, theme.ACCENT)
        theme.ptext(surf, f"v{__version__}  >  v{up.info.version}", (card.x + 18, card.y + 44), 16)
        y = card.y + 72
        for line in up.info.notes[:3]:
            pygame.draw.circle(surf, theme.ACCENT, (card.x + 22, y + 8), 3)
            for chunk in _wrap(line, 13, card.w - 50)[:2]:
                theme.text(surf, chunk, (card.x + 30, y), 13, theme.TEXT_DIM, bold=False)
                y += 17
        if up.state == "downloading":
            bar = pygame.Rect(card.x + 18, card.bottom - 46, card.w - 36, 22)
            theme.rounded(surf, theme.INNER, bar, 11)
            fill = bar.copy()
            fill.w = max(22, int(bar.w * up.progress))
            theme.rounded(surf, theme.ACCENT, fill, 11)
            theme.ptext(surf, f"{int(up.progress * 100)}%", bar.center, 12, theme.OUTLINE, None, anchor="center")
        elif up.state == "ready":
            self.btn_restart.visible = self.btn_later.visible = True
        else:
            self.btn_get.visible = True
        for b in self.update_buttons:
            b.draw(surf)

    def draw(self, surf):
        backdrop(surf, self.clock)
        cx = theme.WIDTH // 2 + int(self.slide * 260)
        n = len(self.fan)
        for i, card in enumerate(self.fan):
            angle = (i - (n - 1) / 2) * 11
            img, _ = card_with_shadow(card, 100, 150)
            img = pygame.transform.rotozoom(img, -angle, 1)
            x = cx + (i - (n - 1) / 2) * 62
            y = 276 + abs(i - (n - 1) / 2) ** 2 * 5
            surf.blit(img, img.get_rect(center=(x, y)))
        if self.game == "CAH":
            from . import cah_art
            cards = [cah_art.black_card("Why can't I sleep at night? _", 1, 120, 168),
                     cah_art.white_card("A big pile of cards.", 120, 168), cah_art.white_card("", 120, 168, blank=True)]
            for i, img in enumerate(cards):
                img = pygame.transform.rotozoom(img, (1 - i) * 9, 1)
                surf.blit(img, img.get_rect(center=(cx + (i - 1) * 120, 276 + abs(i - 1) * 8)))
        if self.game == "MONOPOLY":
            _draw_monopoly_fan(surf, cx, 276, self.clock)
        elif self.game == "DEEP DIG":
            _draw_deepdig_fan(surf, cx, 276, self.clock)
        title = TITLES.get(self.game, self.game)
        theme.logo(surf, title, (cx + (40 if len(title) >= 14 else 0), 120), 92 if len(title) < 14 else 46,
                   angle=6 if len(title) < 14 else 3)
        self._draw_arrow(surf, ARROW_LEFT, -1)
        self._draw_arrow(surf, ARROW_RIGHT, 1)
        for k, name in enumerate(GAMES):  # which game is showing
            dot = (theme.WIDTH // 2 - 12 * (len(GAMES) - 1) + 24 * k, 392)
            pygame.draw.circle(surf, theme.OUTLINE, (dot[0], dot[1] + 2), 7)
            pygame.draw.circle(surf, theme.ACCENT if name == self.game else theme.PANEL_LIGHT, dot, 6)
        s = self.app.settings
        info = f"{s.opponents} OPPONENT{'S' if s.opponents > 1 else ''}  -  {s.difficulty.upper()}"
        solo = self.game in SINGLE_PLAYER
        self.btn_multi.enabled = not solo
        self.btn_multi.label = "SINGLE PLAYER GAME" if solo else "MULTIPLAYER"
        self.btn_multi.size = 14 if solo else 20
        for b in self.buttons:
            b.draw(surf)
        self._draw_update(surf)
        self._draw_bank(surf)
        self._draw_profile(surf)
        status_bar(surf, f"Press PLAY for {TITLES.get(self.game, self.game)}!   {info}   -   arrows switch games")

    def _draw_profile(self, surf):
        """Your picture, name, level and XP. Click it to change your profile."""
        from ..levels import progress
        from ..profile import my_profile
        from . import profile_art
        s = self.app.settings
        prof = my_profile(s)
        card = PROFILE_CARD
        hover = card.collidepoint(pygame.mouse.get_pos())
        profile_art.panel(surf, card, prof["b"], self.clock, edge=theme.ACCENT if hover else theme.PANEL_EDGE,
                          edge_w=3 if hover else 2)
        profile_art.avatar(surf, (card.x + 40, card.y + 42), 28, prof, 0)
        profile_art.level_badge(surf, (card.x + 40, card.y + 76), prof["l"], 13)
        name_r = theme.ptext(surf, s.player_name or "PLAYER", (card.x + 80, card.y + 14), 20,
                             profile_art.name_rgb(prof, self.clock))
        profile_art.name_tag(surf, name_r, prof, 12)
        level, into, need = progress(s.xp)
        theme.ptext(surf, f"LEVEL {level}", (card.x + 80, card.y + 42), 13, theme.TEXT_DIM)
        bar = pygame.Rect(card.x + 80, card.y + 62, card.w - 96, 10)
        pygame.draw.rect(surf, (50, 60, 90), bar, border_radius=5)
        pygame.draw.rect(surf, (110, 220, 255), (bar.x, bar.y, max(6, int(bar.w * into / max(1, need))), bar.h),
                         border_radius=5)
        theme.ptext(surf, "EDIT PROFILE" if hover else f"{into}/{need} XP", (card.x + 80, card.y + 78), 11,
                    theme.ACCENT if hover else theme.TEXT_FAINT)

    def _draw_bank(self, surf):
        """Chips kept from finished games."""
        box = pygame.Rect(20, 20, 250, 78)
        theme.panel(surf, box)
        for k in range(3):
            theme.chip_stack(surf, (box.x + 30 + k * 10, box.bottom - 22), 13, theme.CHIP_COLORS[k], 3 - k)
        theme.ptext(surf, "CHIP BANK", (box.x + 82, box.y + 10), 14, theme.TEXT_DIM)
        theme.ptext(surf, f"{self.app.settings.chip_bank:,}", (box.x + 82, box.bottom - 8), 30, theme.ACCENT,
                    anchor="bottomleft")


class SettingsScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        s = app.settings
        x, w = 470, 660
        self.rows = []

        def row(label, sub, control):
            self.rows.append((label, sub, control))

        def set_attr(name, conv=lambda v: v):
            return lambda v: setattr(s, name, conv(v))

        row("AI LEVEL", "Mixed: one of each, easiest first",
            Segmented((x, 140, w, 48), list(DIFFICULTY_CHOICES), s.difficulty, set_attr("difficulty")))
        row("OPPONENTS", "Computer players at the table",
            Segmented((x, 202, w, 48), ["1", "2", "3", "4", "5"], str(s.opponents), set_attr("opponents", int)))
        row("AI SPEED", "Pause between computer moves",
            Segmented((x, 264, w, 48), list(SPEED_CHOICES), s.ai_speed, set_attr("ai_speed")))
        row("HINTS", "Hint button + phase progress",
            Segmented((x, 326, w, 48), ["On", "Off"], "On" if s.hints else "Off",
                      set_attr("hints", lambda v: v == "On")))
        row("SORT HAND", "You can switch this in game",
            Segmented((x, 388, w, 48), ["Number", "Color"], s.sort_by.title(), set_attr("sort_by", str.lower)))

        def set_sfx(v):
            s.sfx = v
            sfx.set_volume(v)
            sfx.play("coin")
        row("SOUND FX", "Sound effect volume", Segmented((x, 450, w, 48), list(SFX_CHOICES), s.sfx, set_sfx))
        row("UPDATES", "Download new versions on start",
            Segmented((x, 512, w, 48), ["Auto", "Off"], "Auto" if s.auto_update else "Off",
                      set_attr("auto_update", lambda v: v == "Auto")))

        def set_display(v):
            self.app.set_fullscreen(v == "Fullscreen")
        row("DISPLAY", "Window or the whole screen (F11)",
            Segmented((x, 140 + 7 * 62, w, 48), ["Window", "Fullscreen"],
                      "Fullscreen" if getattr(app, "fullscreen", False) else "Window", set_display))
        self.back = Button((theme.WIDTH // 2 - 130, 660, 260, 60), "DONE", self._done, size=24, **PRIMARY)

    def _done(self):
        self.app.settings.save()
        if self.app.settings.auto_update:
            self.app.updater.start()  # no-op if it already ran
        self.app.go(MenuScene(self.app))

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._done()
            return
        if self.back.handle(event):
            return
        for _, _, c in self.rows:
            if c.handle(event):
                return

    def draw(self, surf):
        backdrop(surf, self.clock)
        theme.logo(surf, "SETTINGS", (theme.WIDTH // 2, 76), 52, angle=4)
        theme.panel(surf, (110, 124, 1060, 520), theme.PANEL)
        for label, sub, c in self.rows:
            theme.ptext(surf, label, (140, c.rect.y + 4), 22, theme.ACCENT)
            theme.ptext(surf, sub, (140, c.rect.y + 32), 14, theme.TEXT_DIM)
            c.draw(surf)
        self.back.draw(surf)
        status_bar(surf, f"10 Phases v{__version__}  -  settings are saved when you press DONE.")


HOW_TO = [
    "Be the first to complete all 10 phases. Each round you work on your current phase.",
    "On your turn: draw from the deck or the discard pile, then discard one card.",
    "When you hold your phase, select its cards and press LAY DOWN. Groups are worked out for you.",
    "After laying down, select cards and click any group on the table (or your own) to add to it.",
    "The round ends when someone empties their hand. Everyone who laid down moves up a phase.",
    "Chips: everyone antes 1 chip into the pot each round. Whoever goes out wins the pot!",
    "Cards left in hand cost points: 1-9 = 5, 10-12 = 10, Skip = 15, Wild = 25. Low score breaks ties.",
    "Hover over a player's box to see their phase, what they've laid down and their recent moves.",
    "Chips you finish a game with go into your CHIP BANK on the main menu.",
    "Space draws, double-click discards, Esc opens the menu.",
]

HOW_TO_BLACKJACK = [
    "Beat the dealer: get closer to 21 than the dealer without going over. Number cards count their number, "
    "J/Q/K count 10, and an Ace counts 1 or 11.",
    "Each hand, choose your bet (1-10 chips) with - and +, then press DEAL. Everyone starts with 50 chips.",
    "HIT takes a card, STAND keeps what you have. DOUBLE doubles your bet for exactly one more card.",
    "SPLIT turns a pair into two hands (once per hand). Split aces get one card each.",
    "The dealer reveals their face-down card, then hits until 17 or more. Win pays 1:1, blackjack pays 3:2.",
    "After 10 hands, most chips wins. The chips you finish with go into your CHIP BANK.",
    "Stuck? HINT shows the perfect basic-strategy move and why. Keys: H hit, S stand, D double, P split.",
]

HOW_TO_POKER = [
    "Texas Hold'em: make the best five-card hand from your two cards plus the five shared cards in the middle.",
    "Everyone starts with 50 chips. Two players post blinds (1 and 2 to start, doubling every 5 hands).",
    "There are four betting rounds: after your two cards, after the flop (3 shared cards), the turn and the river.",
    "On your turn: FOLD to give up, CHECK when there's nothing to pay, CALL to match the bet, or RAISE.",
    "Choose exactly how much to bet: drag the slider, use - and +, or tap MIN, 1/2 POT, POT or ALL IN.",
    "Colors are the suits. Best hands: royal flush, straight flush, four of a kind, full house, flush, straight.",
    "After 15 hands, most chips wins. The chips you finish with go into your CHIP BANK.",
    "Not sure? HINT shows your chance to win and what to do. Keys: F fold, C check/call, R raise.",
]

HOW_TO_CAH = [
    "Cards Against Humanity is a party game for adults. Each round one player is the CARD CZAR.",
    "The Czar's black card asks a question or has blanks. Everyone else plays their funniest white card(s).",
    "Pick 2 or Pick 3 cards? Click them in order: the first fills the first blank.",
    "The answers are shown without names. The Czar picks a favourite, and that player gets a point.",
    "BLANK cards let you write your own answer, and add a picture if the game allows it "
    "(drag an image onto the window, or BROWSE).",
    "Before playing, choose which packs are in the deck, how many blank cards there are, pictures on or off, "
    "and the points to win.",
    "The first card download needs the internet; after that the cards are saved on your computer.",
    "Each point is worth 10 chips for your CHIP BANK.",
]

HOW_TO_MONOPOLY = [
    "Roll the dice and move around the board. Doubles roll again, but three doubles in a row is jail!",
    "Land on an unowned property and you can BUY it. Don't want it? It goes to AUCTION and anyone can bid.",
    "Land on someone else's property and you pay them rent. Own a whole colour set and the rent doubles.",
    "With a full set, click your properties to BUILD houses (evenly), then a hotel. Rent shoots up!",
    "Short of cash? Sell houses back for half, or MORTGAGE properties. You can't collect rent on mortgaged ones.",
    "TRADE on your turn: swap properties and cash with anyone. Computers say yes to a good deal.",
    "Pass GO to collect £200. In jail: roll doubles, pay £50, or use a Get Out of Jail Free card.",
    "Can't pay what you owe and you're bankrupt. After the last round, the richest player wins.",
    "Every £50 you're worth at the end is 1 chip for your CHIP BANK. Hold SPACE to speed things up.",
]

HOW_TO_DEEPDIG = [
    "Fly your drill pod into the ground and dig for ore. Arrows or WASD: Down drills, Left/Right drill into walls, "
    "Up fires the thrusters.",
    "Ore gets rarer and worth more the deeper you go: coal, iron and copper near the top, down through gold, "
    "titanium and sapphires to diamonds, ancient relics and meteorites.",
    "Watch your FUEL and HULL. Run out underground and you're towed up for a fee, and your cargo is lost.",
    "The town is left of the mine, on ground you can't dig. Park at a building and press E: Robotics (dig bots), "
    "Fuel, Ore Buyer, Garage (pod parts), Tech Lab (gadgets and items) and Repairs.",
    "Upgrades: drill, a roof drill to dig UP, hull, engine, fuel tank, cargo, radiator, shocks, lamp, scanner, "
    "armor, refinery and rescue insurance.",
    "Watch out for gas pockets, lava, grey boulders you can't drill (blast them with dynamite) and long falls.",
    "Items, keys 1-5: repair kit, fuel can, dynamite, mega blast and a teleporter home.",
    "Every $500 of ore you sell puts 1 chip in your Chip Bank. Find the Heart of the Earth, then keep going: "
    "the ground never ends.",
]

HOW_TO_SLOTS = [
    "Slots plays with your real CHIP BANK: every spin costs your bet, and wins go straight back in.",
    "Pick a bet (1, 5, 10 or 25), then pull the lever, press SPIN or hit Space.",
    "Line up three matching symbols on the red payline. WILD counts as any symbol except the jackpot.",
    "Three 10 PHASES cards is the JACKPOT: 300 times your bet!",
    "Any two cherries pay 2x, and a cherry on the first reel gives your bet back.",
    "Over time the machine pays back about 95% of what's bet, so it's for fun, not profit.",
    "Out of chips? Win more playing 10 Phases, Go Fish, Blackjack or Poker.",
]

HOW_TO_FISH = [
    "Collect books: all four colors of one number (like a red, blue, green and yellow 7).",
    "On your turn, click a card in your hand, then click a player to ask them for that number.",
    "If they have any, they hand over every one and you go again.",
    "If not, they say GO FISH and you draw from the pond. Fish the number you asked for and you go again!",
    "Books are laid down automatically as soon as you complete one.",
    "Run out of cards? You fish one on your turn. When all 12 books are made, most books wins.",
    "Everyone hears every question: if someone asks for 7s, they have a 7. Use it!",
    "Each book you make is worth 5 chips for your CHIP BANK.",
]


class HowToScene(Scene):
    def __init__(self, app, game: str = "10 PHASES"):
        super().__init__(app)
        self.game = game
        self.back = Button((theme.WIDTH // 2 - 130, 690, 260, 58), "BACK", lambda: app.go(MenuScene(app)),
                           size=24, **PRIMARY)

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go(MenuScene(self.app))
            return
        self.back.handle(event)

    def _draw_fish_panel(self, surf, panel):
        _draw_fish_panel_impl(surf, panel)

    def draw(self, surf):
        backdrop(surf, self.clock)
        title = {"GO FISH": "GO FISH RULES", "BLACKJACK": "BLACKJACK RULES", "SLOTS": "SLOTS RULES",
                 "POKER": "POKER RULES", "CAH": "CARDS AGAINST HUMANITY", "MONOPOLY": "MONOPOLY RULES", "DEEP DIG": "DEEP DIG"}.get(
            self.game, "HOW TO PLAY")
        theme.logo(surf, title, (theme.WIDTH // 2, 64), 50, angle=4)
        left = pygame.Rect(40, 120, 720, 550)
        theme.panel(surf, left)
        y = left.y + 20
        rules = {"GO FISH": HOW_TO_FISH, "BLACKJACK": HOW_TO_BLACKJACK, "SLOTS": HOW_TO_SLOTS, "POKER": HOW_TO_POKER,
                 "CAH": HOW_TO_CAH, "MONOPOLY": HOW_TO_MONOPOLY,
                 "DEEP DIG": HOW_TO_DEEPDIG}
        for line in rules.get(self.game, HOW_TO):
            theme.star(surf, (left.x + 24, y + 10), 9, theme.ACCENT)
            for chunk in _wrap(line, 17, left.w - 70):
                theme.text(surf, chunk, (left.x + 44, y), 17, theme.TEXT, bold=False)
                y += 23
            y += 12
        panel = pygame.Rect(790, 120, 450, 550)
        theme.panel(surf, panel)
        if self.game == "GO FISH":
            self._draw_fish_panel(surf, panel)
            self.back.draw(surf)
            status_bar(surf, f"Go Fish  -  10 Phases v{__version__}")
            return
        if self.game == "SLOTS":
            from .slots_scene import symbol_surface
            from ..slots.engine import JACKPOT, SEVEN, WILD
            theme.ptext(surf, "THE JACKPOT", (panel.x + 24, panel.y + 18), 22, theme.ACCENT)
            for k, sym in enumerate((JACKPOT,) * 3):
                surf.blit(symbol_surface(sym, 110), (panel.x + 40 + k * 120, panel.y + 60))
            theme.ptext(surf, "300x YOUR BET", (panel.centerx, panel.y + 200), 26, theme.ACCENT, anchor="center")
            for k, sym in enumerate((WILD, SEVEN)):
                surf.blit(symbol_surface(sym, 80), (panel.x + 40, panel.y + 250 + k * 100))
            theme.ptext(surf, "WILD = ANY SYMBOL", (panel.x + 140, panel.y + 280), 18)
            theme.ptext(surf, "THREE 7s = 25x", (panel.x + 140, panel.y + 380), 18)
            self.back.draw(surf)
            status_bar(surf, f"Slots  -  10 Phases v{__version__}")
            return
        if self.game == "CAH":
            _draw_cah_panel(surf, panel)
            self.back.draw(surf)
            status_bar(surf, f"Cards Against Humanity  -  10 Phases v{__version__}")
            return
        if self.game == "DEEP DIG":
            _draw_deepdig_panel(surf, panel, self.clock)
            self.back.draw(surf)
            status_bar(surf, f"Deep Dig  -  10 Phases v{__version__}")
            return
        if self.game == "MONOPOLY":
            _draw_monopoly_panel(surf, panel, self.clock)
            self.back.draw(surf)
            status_bar(surf, f"Monopoly  -  10 Phases v{__version__}")
            return
        if self.game == "POKER":
            _draw_poker_panel(surf, panel)
            self.back.draw(surf)
            status_bar(surf, f"Poker  -  10 Phases v{__version__}")
            return
        if self.game == "BLACKJACK":
            _draw_blackjack_panel(surf, panel)
            self.back.draw(surf)
            status_bar(surf, f"Blackjack  -  10 Phases v{__version__}")
            return
        theme.ptext(surf, "THE 10 PHASES", (panel.x + 24, panel.y + 18), 22, theme.ACCENT)
        for i in range(NUM_PHASES):
            yy = panel.y + 66 + i * 47
            pygame.draw.circle(surf, theme.OUTLINE, (panel.x + 40, yy + 14), 19)
            pygame.draw.circle(surf, theme.ACCENT, (panel.x + 40, yy + 12), 18)
            theme.ptext(surf, str(i + 1), (panel.x + 40, yy + 12), 16, theme.OUTLINE, None, anchor="center")
            theme.ptext(surf, describe_phase(i), (panel.x + 72, yy + 2), 18)
        self.back.draw(surf)
        status_bar(surf, f"10 Phases v{__version__}  -  good luck!")


def _fish_example(surf, x, y, value):
    for k, c in enumerate(COLORS):
        img, _ = card_with_shadow(number(c, value), 70, 105)
        surf.blit(pygame.transform.rotate(img, 12 - k * 8), (x + k * 46, y + abs(k - 1.5) * 6))


def _draw_fish_panel_impl(surf, panel):
    theme.ptext(surf, "A BOOK", (panel.x + 24, panel.y + 18), 22, theme.ACCENT)
    theme.ptext(surf, "All four colors of one number", (panel.x + 24, panel.y + 50), 15, theme.TEXT_DIM)
    _fish_example(surf, panel.x + 70, panel.y + 90, 7)
    theme.ptext(surf, "12 BOOKS IN THE GAME", (panel.x + 24, panel.y + 260), 18, theme.ACCENT)
    theme.ptext(surf, "Numbers 1 to 12, one card per color", (panel.x + 24, panel.y + 290), 15, theme.TEXT_DIM)
    theme.ptext(surf, "48 CARDS IN THE POND", (panel.x + 24, panel.y + 340), 18, theme.ACCENT)
    theme.ptext(surf, "7 each with 2-3 players, 5 each with 4-6", (panel.x + 24, panel.y + 370), 15, theme.TEXT_DIM)
    theme.logo(surf, "GO FISH!", (panel.centerx, panel.bottom - 80), 52, angle=6)


def _draw_blackjack_panel(surf, panel):
    from ..blackjack.engine import bj_card
    theme.ptext(surf, "BLACKJACK!", (panel.x + 24, panel.y + 18), 22, theme.ACCENT)
    theme.ptext(surf, "An Ace with a 10, J, Q or K", (panel.x + 24, panel.y + 50), 15, theme.TEXT_DIM)
    for k, (c, v) in enumerate(((COLORS[0], 1), (COLORS[1], 13))):
        img, _ = card_with_shadow(bj_card(c, v), 84, 126)
        surf.blit(pygame.transform.rotate(img, 8 - k * 16), (panel.x + 120 + k * 90, panel.y + 86))
    rows = [("CARD VALUES", "2-10 = number, J Q K = 10, A = 1 or 11"), ("PAYOUTS", "Win 1:1, Blackjack 3:2, tie pushes"),
            ("THE DEALER", "Hits 16 or less, stands on 17+")]
    for k, (head, line) in enumerate(rows):
        theme.ptext(surf, head, (panel.x + 24, panel.y + 260 + k * 70), 18, theme.ACCENT)
        theme.ptext(surf, line, (panel.x + 24, panel.y + 290 + k * 70), 15, theme.TEXT_DIM)
    theme.logo(surf, "21!", (panel.centerx, panel.bottom - 50), 52, angle=6)


def _draw_deepdig_fan(surf, cx, cy, clock):
    """A slice of ground with ore and the drill pod digging in."""
    from ..deepdig.engine import CORE, DIRT, ORE0, ROCK
    from . import deepdig_art as art
    tiles = [DIRT, ORE0 + 3, DIRT, ROCK, ORE0 + 8, DIRT, ORE0 + 6, DIRT, CORE]
    for k, t in enumerate(tiles):
        col = k % 9
        x = cx - 4.5 * 52 + col * 52
        img = pygame.transform.smoothscale(art.tile_surface(t, 260 if t != DIRT else 120, col), (52, 52))
        surf.blit(img, (x, cy + 10))
        img2 = pygame.transform.smoothscale(art.tile_surface(DIRT, 200, col + 3), (52, 52))
        surf.blit(img2, (x, cy + 62))
    pod = art.pod(1, "down", clock * 3, False, clock, 0, 44)
    surf.blit(pod, pod.get_rect(center=(cx - 20, cy - 26 + int(math.sin(clock * 6) * 3))))


def _draw_deepdig_panel(surf, panel, clock):
    from ..deepdig.engine import ORES
    from . import deepdig_art as art
    theme.ptext(surf, "ORE VALUES", (panel.x + 24, panel.y + 18), 22, theme.ACCENT)
    for k, ore in enumerate(ORES):
        y = panel.y + 58 + k * 44
        img = pygame.transform.smoothscale(art.tile_surface(10 + k, ore.peak, 2), (36, 36))
        surf.blit(img, (panel.x + 24, y))
        theme.ptext(surf, ore.name, (panel.x + 72, y + 8), 18)
        theme.ptext(surf, f"${ore.value:,}", (panel.right - 30, y + 8), 18, theme.SUCCESS, anchor="topright")
    theme.ptext(surf, "Single player - your game is saved as you play", (panel.centerx, panel.bottom - 30), 13,
                theme.TEXT_DIM, anchor="center")


def _draw_monopoly_fan(surf, cx, cy, clock):
    """Title deeds, dice and a token for the main menu."""
    from . import monopoly_art as art
    for k, (sq, angle) in enumerate(((37, 14), (39, 0), (24, -14))):
        img = pygame.transform.rotozoom(art.deed(sq, 220), angle, 0.52)
        surf.blit(img, img.get_rect(center=(cx + (k - 1) * 104, cy + abs(k - 1) * 10)))
    for k, v in enumerate((6, 6)):
        img = pygame.transform.rotate(art.die(v, 46), 20 - k * 35 + math.sin(clock * 2 + k) * 6)
        surf.blit(img, img.get_rect(center=(cx + 190 + k * 40, cy + 40 - k * 20)))
    tok = art.token("car", art.TOKEN_COLORS["car"], 64)
    surf.blit(tok, tok.get_rect(center=(cx - 200, cy + 34 + int(math.sin(clock * 4) * 5))))


def _draw_monopoly_panel(surf, panel, clock):
    from . import monopoly_art as art
    theme.ptext(surf, "BUILD AN EMPIRE", (panel.x + 24, panel.y + 18), 22, theme.ACCENT)
    img = pygame.transform.rotozoom(art.deed(39, 220, "YOU", 3, False, True), 4, 0.9)
    surf.blit(img, img.get_rect(center=(panel.x + 130, panel.y + 200)))
    for k, kind in enumerate(("car", "hat", "dog", "ship", "boot", "cat")):
        tok = art.token(kind, art.TOKEN_COLORS[kind], 48)
        bob = math.sin(clock * 4 + k) * 4
        surf.blit(tok, tok.get_rect(center=(panel.x + 280 + (k % 2) * 70, panel.y + 90 + (k // 2) * 70 + bob)))
    for k in range(4):
        h = art.house(22, hotel=k == 3)
        surf.blit(h, h.get_rect(center=(panel.x + 270 + k * 34, panel.y + 330)))
    rows = [("MAYFAIR, 3 HOUSES", "£1,400 rent!"), ("PASS GO", "Collect £200"),
            ("BASED ON MONOPYLY", "github.com/richard-shepherd/monopyly")]
    for k, (head, line) in enumerate(rows):
        theme.ptext(surf, head, (panel.x + 24, panel.y + 380 + k * 52), 17, theme.ACCENT)
        theme.ptext(surf, line, (panel.x + 24, panel.y + 404 + k * 52), 13, theme.TEXT_DIM)


def _draw_poker_panel(surf, panel):
    from ..poker.engine import poker_card
    theme.ptext(surf, "WINNING HANDS", (panel.x + 24, panel.y + 18), 22, theme.ACCENT)
    c = COLORS
    rows = [("ROYAL FLUSH", [(c[0], v) for v in (10, 11, 12, 13, 14)]),
            ("STRAIGHT FLUSH", [(c[1], v) for v in (5, 6, 7, 8, 9)]),
            ("FOUR OF A KIND", [(k, 9) for k in c] + [(c[0], 2)]),
            ("FULL HOUSE", [(c[0], 13), (c[1], 13), (c[2], 13), (c[0], 4), (c[3], 4)]),
            ("FLUSH", [(c[2], v) for v in (2, 6, 9, 11, 13)]),
            ("STRAIGHT", [(c[0], 3), (c[1], 4), (c[3], 5), (c[2], 6), (c[0], 7)]),
            ("THREE OF A KIND", [(c[0], 8), (c[1], 8), (c[3], 8)]),
            ("TWO PAIR", [(c[0], 12), (c[2], 12), (c[1], 5), (c[3], 5)]),
            ("PAIR", [(c[2], 14), (c[3], 14)])]
    for k, (name, cards) in enumerate(rows):
        y = panel.y + 58 + k * 52
        theme.ptext(surf, f"{k + 1}. {name}", (panel.x + 24, y + 12), 15)
        for n, (col, v) in enumerate(cards):
            img, _ = card_with_shadow(poker_card(col, v), 30, 45)
            surf.blit(img, (panel.x + 236 + n * 40, y))


def _draw_cah_panel(surf, panel):
    from . import cah_art
    theme.ptext(surf, "A ROUND", (panel.x + 24, panel.y + 18), 22, theme.ACCENT)
    black = cah_art.black_card("What's my secret power? _", 1, 170, 236)
    surf.blit(pygame.transform.rotozoom(black, 5, 1), (panel.x + 24, panel.y + 60))
    for k, text in enumerate(("Free refills.", "")):
        card = cah_art.white_card(text, 150, 210, blank=not text)
        surf.blit(pygame.transform.rotozoom(card, -4 - k * 6, 1), (panel.x + 210 + k * 100, panel.y + 90 + k * 20))
    theme.ptext(surf, "The Czar reads the black card,", (panel.x + 24, panel.y + 350), 16)
    theme.ptext(surf, "everyone answers with white cards,", (panel.x + 24, panel.y + 376), 16)
    theme.ptext(surf, "and the funniest answer scores!", (panel.x + 24, panel.y + 402), 16)
    theme.text(surf, "Cards: REST Against Humanity API.", (panel.x + 24, panel.bottom - 70), 13, theme.TEXT_FAINT,
               bold=False)
    theme.text(surf, "Cards Against Humanity is CC BY-NC-SA,", (panel.x + 24, panel.bottom - 52), 13,
               theme.TEXT_FAINT, bold=False)
    theme.text(surf, "Cards Against Humanity LLC.", (panel.x + 24, panel.bottom - 34), 13, theme.TEXT_FAINT,
               bold=False)


def _wrap(msg: str, size: int, width: int, pixel: bool = False) -> list[str]:
    measure = (lambda t: theme.pixel_width(t, size)) if pixel else (lambda t: theme.font(size, False).size(t)[0])
    words, lines, cur = msg.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if measure(trial) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines
