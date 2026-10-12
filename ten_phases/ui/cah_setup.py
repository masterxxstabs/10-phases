"""Cards Against Humanity house rules: which packs are in the deck, blank cards, pictures, points to win."""

from __future__ import annotations

import pygame

from ..cah.cards import library
from ..cah.engine import CahOptions
from ..settings import MAX_BLANKS
from . import sfx, theme
from .menus import PRIMARY, Scene, backdrop, status_bar
from .widgets import Button, Segmented

LIST = pygame.Rect(40, 170, 760, 500)
ROW_H = 34
SIDE = pygame.Rect(820, 120, 420, 550)
POINTS = ("5", "7", "10", "15")


def options_from(settings) -> CahOptions:
    return CahOptions(packs=list(settings.cah_packs), blanks=settings.cah_blanks, images=settings.cah_images,
                      points_to_win=settings.cah_points)


class CahSetupScene(Scene):
    """mode "solo" starts a game against computers; mode "lobby" saves and goes back to the host lobby."""

    def __init__(self, app, mode: str = "solo", back=None, server=None):
        super().__init__(app)
        self.mode, self._back, self.server = mode, back, server
        self.lib = library()
        if self.lib.status == "idle":
            self.lib.refresh()
        s = app.settings
        self.scroll = 0
        self.flash: tuple[str, float] | None = None
        self.btn_all = Button((LIST.x, 120, 120, 40), "ALL", self._all, size=15)
        self.btn_none = Button((LIST.x + 130, 120, 120, 40), "NONE", self._none, size=15)
        self.btn_base = Button((LIST.x + 260, 120, 170, 40), "BASE SET ONLY", self._base, size=14)
        self.btn_up = Button((LIST.right - 100, 120, 46, 40), "^", lambda: self._scroll(-5), size=18)
        self.btn_down = Button((LIST.right - 46, 120, 46, 40), "v", lambda: self._scroll(5), size=18)
        self.btn_minus = Button((SIDE.x + 20, SIDE.y + 84, 56, 48), "-", lambda: self._blanks(-1), size=24)
        self.btn_plus = Button((SIDE.x + 176, SIDE.y + 84, 56, 48), "+", lambda: self._blanks(1), size=24)
        self.btn_minus5 = Button((SIDE.x + 244, SIDE.y + 84, 76, 48), "-5", lambda: self._blanks(-5), size=18)
        self.btn_plus5 = Button((SIDE.x + 328, SIDE.y + 84, 76, 48), "+5", lambda: self._blanks(5), size=18)
        self.images = Segmented((SIDE.x + 20, SIDE.y + 186, 380, 46), ["PICTURES ON", "PICTURES OFF"],
                                "PICTURES ON" if s.cah_images else "PICTURES OFF", self._set_images, size=14)
        self.points = Segmented((SIDE.x + 20, SIDE.y + 286, 380, 46), list(POINTS),
                                str(s.cah_points) if str(s.cah_points) in POINTS else "7", self._set_points, size=16)
        self.btn_refresh = Button((SIDE.x + 20, SIDE.bottom - 120, 380, 44), "DOWNLOAD CARDS AGAIN",
                                  self.lib.refresh, size=14)
        label = "START GAME" if mode == "solo" else "DONE"
        self.btn_go = Button((theme.WIDTH // 2 + 10, 700, 280, 56), label, self._go, size=22, **PRIMARY)
        self.btn_back = Button((theme.WIDTH // 2 - 290, 700, 280, 56), "BACK", self._leave, size=22)
        self.buttons = [self.btn_all, self.btn_none, self.btn_base, self.btn_up, self.btn_down, self.btn_minus,
                        self.btn_plus, self.btn_minus5, self.btn_plus5, self.btn_refresh, self.btn_go, self.btn_back]

    # ------------------------------------------------------------------ choices

    @property
    def packs(self) -> list[dict]:
        return self.lib.packs or []

    def chosen(self) -> set[int]:
        return set(self.app.settings.cah_packs)

    def _save(self, packs: set[int] | None = None):
        s = self.app.settings
        if packs is not None:
            s.cah_packs = sorted(packs) or [0]
        s.save()

    def _toggle(self, pid: int):
        chosen = self.chosen()
        if pid in chosen:
            if len(chosen) == 1:
                self.flash = ("Keep at least one pack in the deck.", 2.0)
                sfx.play("error")
                return
            chosen.discard(pid)
            sfx.play("deselect")
        else:
            chosen.add(pid)
            sfx.play("select")
        self._save(chosen)

    def _all(self):
        self._save({p["id"] for p in self.packs})
        sfx.play("select")

    def _none(self):
        first = self.packs[0]["id"] if self.packs else 0
        self._save({first})
        self.flash = ("Only the first pack is left - pick the ones you want.", 2.5)
        sfx.play("deselect")

    def _base(self):
        self._none()
        self.flash = None

    def _blanks(self, step: int):
        s = self.app.settings
        s.cah_blanks = max(0, min(MAX_BLANKS, s.cah_blanks + step))
        self._save()
        sfx.play("select")

    def _set_images(self, v: str):
        self.app.settings.cah_images = v == "PICTURES ON"
        self._save()

    def _set_points(self, v: str):
        self.app.settings.cah_points = int(v)
        self._save()

    def _scroll(self, step: int):
        rows = LIST.h // ROW_H
        self.scroll = max(0, min(max(0, len(self.packs) - rows), self.scroll + step))

    def totals(self) -> tuple[int, int]:
        chosen = self.chosen()
        white = sum(len(p["white"]) for p in self.packs if p["id"] in chosen)
        black = sum(len(p["black"]) for p in self.packs if p["id"] in chosen)
        return white, black

    def _go(self):
        if not self.packs:
            self.flash = ("The cards haven't downloaded yet.", 2.5)
            sfx.play("error")
            return
        opts = options_from(self.app.settings)
        if self.mode == "lobby":
            if self.server is not None:
                self.server.cah = (self.packs, opts)
            self._leave()
            return
        from .cah_scene import CahScene
        try:
            scene = CahScene(self.app, packs=self.packs, options=opts)
        except ValueError as e:
            self.flash = (str(e), 3.0)
            sfx.play("error")
            return
        self.app.go(scene)

    def _leave(self):
        self.app.settings.save()
        if self._back:
            self._back()
        else:
            from .menus import MenuScene
            self.app.go(MenuScene(self.app))

    # ------------------------------------------------------------------ input

    def _row_rect(self, k: int) -> pygame.Rect:
        return pygame.Rect(LIST.x + 10, LIST.y + 8 + k * ROW_H, LIST.w - 20, ROW_H - 4)

    def handle(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._leave()
            elif event.key in (pygame.K_UP, pygame.K_DOWN):
                self._scroll(-1 if event.key == pygame.K_UP else 1)
            return
        if event.type == pygame.MOUSEWHEEL and event.y:
            self._scroll(-3 if event.y > 0 else 3)
            return
        for b in self.buttons:
            if b.handle(event):
                return
        if self.images.handle(event) or self.points.handle(event):
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and LIST.collidepoint(event.pos):
            for k, p in enumerate(self.visible()):
                if self._row_rect(k).collidepoint(event.pos):
                    self._toggle(p["id"])
                    return

    def visible(self) -> list[dict]:
        rows = (LIST.h - 10) // ROW_H
        return self.packs[self.scroll:self.scroll + rows]

    def update(self, dt: float):
        super().update(dt)
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None

    # ------------------------------------------------------------------ drawing

    def draw(self, surf):
        backdrop(surf, self.clock)
        theme.logo(surf, "CARDS AGAINST HUMANITY", (theme.WIDTH // 2, 58), 46, angle=3)
        theme.panel(surf, LIST.inflate(0, 0))
        s = self.app.settings
        chosen = self.chosen()
        lib = self.lib
        if not self.packs:
            msg = {"loading": "Downloading the cards...", "failed": lib.error or "Couldn't download the cards.",
                   "idle": "Getting ready..."}.get(lib.status, "")
            theme.ptext(surf, msg, LIST.center, 20, theme.TEXT_DIM, anchor="center")
            if lib.status == "failed":
                theme.ptext(surf, "Check your internet, then press DOWNLOAD CARDS AGAIN.", (LIST.centerx,
                            LIST.centery + 34), 15, theme.TEXT_FAINT, anchor="center")
        mouse = pygame.mouse.get_pos()
        for k, p in enumerate(self.visible()):
            r = self._row_rect(k)
            on = p["id"] in chosen
            if r.collidepoint(mouse):
                theme.rounded(surf, theme.PANEL_HOVER, r, 6)
            box = pygame.Rect(r.x + 6, r.y + 4, 22, 22)
            theme.rounded(surf, theme.SUCCESS if on else theme.INNER, box, 5)
            theme.rounded(surf, theme.OUTLINE, box, 5, 2)
            if on:
                pygame.draw.lines(surf, theme.OUTLINE, False, [(box.x + 5, box.y + 11), (box.x + 9, box.y + 16),
                                                               (box.x + 17, box.y + 6)], 3)
            name = p["name"]
            f = theme.font(15, True)
            while f.size(name)[0] > r.w - 230 and len(name) > 6:
                name = name[:-4] + "..."
            theme.text(surf, name, (r.x + 38, r.y + 5), 15, theme.TEXT if on else theme.TEXT_DIM)
            theme.ptext(surf, f"{len(p['white'])} W   {len(p['black'])} B", (r.right - 10, r.y + 3), 15,
                        theme.TEXT if on else theme.TEXT_FAINT, anchor="topright")
        if self.packs:
            rows = (LIST.h - 10) // ROW_H
            theme.ptext(surf, f"PACKS {self.scroll + 1}-{min(len(self.packs), self.scroll + rows)} OF "
                        f"{len(self.packs)}  -  {len(chosen & {p['id'] for p in self.packs})} IN THE DECK",
                        (LIST.x + 440, 128), 14, theme.TEXT_DIM)
        theme.panel(surf, SIDE)
        theme.ptext(surf, "BLANK CARDS", (SIDE.x + 20, SIDE.y + 18), 20, theme.ACCENT)
        theme.text(surf, "You write your own answer when you play one", (SIDE.x + 20, SIDE.y + 50), 13,
                   theme.TEXT_DIM, bold=False)
        box = pygame.Rect(SIDE.x + 84, SIDE.y + 84, 84, 48)
        theme.rounded(surf, theme.INNER, box, 8)
        theme.ptext(surf, str(s.cah_blanks), box.center, 26, theme.ACCENT, anchor="center")
        theme.ptext(surf, "PICTURES ON BLANK CARDS", (SIDE.x + 20, SIDE.y + 150), 18, theme.ACCENT)
        theme.ptext(surf, "POINTS TO WIN", (SIDE.x + 20, SIDE.y + 252), 18, theme.ACCENT)
        white, black = self.totals()
        theme.ptext(surf, "THE DECK", (SIDE.x + 20, SIDE.y + 352), 18, theme.ACCENT)
        theme.ptext(surf, f"{white:,} white + {s.cah_blanks} blank", (SIDE.x + 20, SIDE.y + 380), 16)
        theme.ptext(surf, f"{black:,} black cards", (SIDE.x + 20, SIDE.y + 404), 16)
        for line_k, line in enumerate(("Cards: REST Against Humanity API. Cards Against Humanity",
                                       "is CC BY-NC-SA, Cards Against Humanity LLC. For adults -",
                                       "pick the Family Edition pack for a cleaner game.")):
            theme.text(surf, line, (SIDE.x + 20, SIDE.bottom - 66 + line_k * 16), 11, theme.TEXT_FAINT, bold=False)
        for b in self.buttons:
            b.enabled = not (b is self.btn_refresh and lib.status == "loading")
            b.draw(surf)
        self.images.draw(surf)
        self.points.draw(surf)
        msg = self.flash[0] if self.flash else (
            "Downloading cards..." if lib.status == "loading" else
            lib.error if lib.error else "Click packs to add or remove them. Settings are saved for next time.")
        status_bar(surf, msg)
