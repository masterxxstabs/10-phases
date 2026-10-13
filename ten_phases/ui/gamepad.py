"""Controller support for every screen (Xbox, PlayStation, Switch Pro and other SDL game controllers).

Screens don't need to know about controllers: this turns the pad into the mouse and keys they already handle.

- "cursor" screens (menus, card tables, shops): the left stick moves a pointer, A clicks (hold A to drag),
  the D-pad is the arrow keys and the right stick scrolls.
- "keys" screens (action games like Deep Dig): the left stick and D-pad are held arrow keys.

B and Start are Escape (back / pause) everywhere. A screen can change what the buttons do with
`pad_buttons` (a dict of button name -> pygame key, or "click"), and pick its mode with `pad_mode`
("cursor" or "keys"); both can be properties, so they can change with what's on screen.
Button names: A B X Y LB RB LT RT START BACK LS RS (the D-pad is always the arrow keys).
"""

from __future__ import annotations

import math

import pygame

from . import theme

try:   # SDL's game controller API: the same button names on every brand of pad
    from pygame._sdl2 import controller as sdl_controller
except Exception:   # pragma: no cover - very old pygame
    sdl_controller = None

BUTTONS = {
    pygame.CONTROLLER_BUTTON_A: "A", pygame.CONTROLLER_BUTTON_B: "B", pygame.CONTROLLER_BUTTON_X: "X",
    pygame.CONTROLLER_BUTTON_Y: "Y", pygame.CONTROLLER_BUTTON_LEFTSHOULDER: "LB",
    pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: "RB", pygame.CONTROLLER_BUTTON_START: "START",
    pygame.CONTROLLER_BUTTON_BACK: "BACK", pygame.CONTROLLER_BUTTON_LEFTSTICK: "LS",
    pygame.CONTROLLER_BUTTON_RIGHTSTICK: "RS", pygame.CONTROLLER_BUTTON_DPAD_UP: "UP",
    pygame.CONTROLLER_BUTTON_DPAD_DOWN: "DOWN", pygame.CONTROLLER_BUTTON_DPAD_LEFT: "LEFT",
    pygame.CONTROLLER_BUTTON_DPAD_RIGHT: "RIGHT",
}
DPAD = {"UP": pygame.K_UP, "DOWN": pygame.K_DOWN, "LEFT": pygame.K_LEFT, "RIGHT": pygame.K_RIGHT}
DEFAULT_BUTTONS = {"A": "click", "B": pygame.K_ESCAPE, "START": pygame.K_ESCAPE, "X": pygame.K_SPACE,
                   "Y": pygame.K_RETURN}
TRIGGERS = {pygame.CONTROLLER_AXIS_TRIGGERLEFT: "LT", pygame.CONTROLLER_AXIS_TRIGGERRIGHT: "RT"}
DEAD = 0.22             # stick dead zone
CURSOR_SPEED = 1150     # pixels a second at full tilt
SCROLL_EVERY = 0.12     # seconds between scroll steps with the right stick held

_real_get_pos = pygame.mouse.get_pos


class Gamepad:
    def __init__(self, app):
        self.app = app
        self.pads: dict[int, object] = {}
        self.active = False                 # True while the controller is what's being used
        self.cursor = [theme.WIDTH / 2, theme.HEIGHT / 2]
        self.axes = {"LX": 0.0, "LY": 0.0, "RX": 0.0, "RY": 0.0, "LT": 0.0, "RT": 0.0}
        self.held_keys: set[int] = set()    # arrow keys the stick is holding down (keys mode)
        self.pressed: dict[str, object] = {}   # button name -> what it did on the way down (released the same way)
        self.scroll_timer = 0.0
        self.scene = None
        if sdl_controller is not None:
            try:
                sdl_controller.init()
                for i in range(sdl_controller.get_count()):
                    self._open(i)
            except pygame.error:
                pass
        pygame.mouse.get_pos = self.mouse_pos   # every screen's hover checks follow the pad's pointer

    # ---------------------------------------------------------------- devices

    def _open(self, index: int) -> None:
        try:
            if sdl_controller.is_controller(index):
                pad = sdl_controller.Controller(index)
                self.pads[pad.as_joystick().get_instance_id()] = pad
        except (pygame.error, AttributeError):
            pass

    @property
    def connected(self) -> bool:
        return bool(self.pads)

    def mouse_pos(self) -> tuple[int, int]:
        if self.active:
            return int(self.cursor[0]), int(self.cursor[1])
        return _real_get_pos()

    # ---------------------------------------------------------------- what the screen wants

    def mode(self) -> str:
        return getattr(self.app.scene, "pad_mode", "cursor") or "cursor"

    def action(self, name: str):
        overrides = getattr(self.app.scene, "pad_buttons", None) or {}
        return overrides.get(name, DEFAULT_BUTTONS.get(name))

    # ---------------------------------------------------------------- events

    def translate(self, event) -> list:
        """Turn one SDL event into the events the screen should get (most pass straight through)."""
        t = event.type
        if t == pygame.CONTROLLERDEVICEADDED:
            if sdl_controller is not None:
                self._open(event.device_index)
            return []
        if t == pygame.CONTROLLERDEVICEREMOVED:
            self.pads.pop(getattr(event, "instance_id", -1), None)
            return self._release_all() if not self.pads else []
        if t in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP):
            name = BUTTONS.get(event.button)
            return self._button(name, t == pygame.CONTROLLERBUTTONDOWN) if name else []
        if t == pygame.CONTROLLERAXISMOTION:
            return self._axis(event.axis, event.value / 32767.0)
        if t in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP, pygame.JOYAXISMOTION, pygame.JOYHATMOTION,
                 pygame.JOYBALLMOTION) and self.pads:
            return []                       # the same presses again, raw: the controller events cover them
        if t in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN) and self.active:
            self._wake(False)               # the real mouse took over
        return [event]

    def _wake(self, on: bool) -> None:
        if on and not self.active:
            mx, my = _real_get_pos()
            if 0 <= mx < theme.WIDTH and 0 <= my < theme.HEIGHT and (mx, my) != (0, 0):
                self.cursor = [float(mx), float(my)]
        self.active = on
        try:
            pygame.mouse.set_visible(not on)
        except pygame.error:
            pass

    def _key(self, key: int, down: bool) -> pygame.event.Event:
        return pygame.event.Event(pygame.KEYDOWN if down else pygame.KEYUP, key=key, mod=0,
                                  unicode=" " if key == pygame.K_SPACE else "", scancode=0)

    def _click(self, down: bool) -> pygame.event.Event:
        pos = (int(self.cursor[0]), int(self.cursor[1]))
        return pygame.event.Event(pygame.MOUSEBUTTONDOWN if down else pygame.MOUSEBUTTONUP, pos=pos, button=1,
                                  touch=False)

    def _button(self, name: str, down: bool) -> list:
        self._wake(True)
        if name in DPAD:
            return [self._key(DPAD[name], down)]
        if down:
            act = self.action(name)
            if act is None:
                return []
            self.pressed[name] = act
        else:
            act = self.pressed.pop(name, None)     # let go of whatever it pressed, even if the screen changed
            if act is None:
                return []
        if act == "click":
            return [self._click(down)]
        return [self._key(act, down)]

    def _axis(self, axis: int, value: float) -> list:
        if axis in TRIGGERS:                       # triggers work as buttons
            name = TRIGGERS[axis]
            was = self.axes[name] > 0.5
            self.axes[name] = value
            if (value > 0.5) != was:
                return self._button(name, value > 0.5)
            return []
        key = {pygame.CONTROLLER_AXIS_LEFTX: "LX", pygame.CONTROLLER_AXIS_LEFTY: "LY",
               pygame.CONTROLLER_AXIS_RIGHTX: "RX", pygame.CONTROLLER_AXIS_RIGHTY: "RY"}.get(axis)
        if key:
            self.axes[key] = max(-1.0, min(1.0, value))
            if abs(value) > DEAD:
                self._wake(True)
        return []

    def _release_all(self) -> list:
        out = [self._key(k, False) for k in sorted(self.held_keys)]
        self.held_keys.clear()
        for name in list(self.pressed):
            out += self._button(name, False)
        return out

    # ---------------------------------------------------------------- every frame

    def update(self, dt: float) -> list:
        """Sticks are held, not pressed: move the pointer, hold arrow keys, scroll. Returns events to hand on."""
        out: list = []
        if self.app.scene is not self.scene:       # a new screen never saw the stick's keys go down: start fresh
            self.held_keys.clear()
            self.scene = self.app.scene
        lx, ly = self.axes["LX"], self.axes["LY"]
        if self.mode() == "keys":
            want = set()
            if lx < -0.5:
                want.add(pygame.K_LEFT)
            elif lx > 0.5:
                want.add(pygame.K_RIGHT)
            if ly < -0.5:
                want.add(pygame.K_UP)
            elif ly > 0.5:
                want.add(pygame.K_DOWN)
            out += [self._key(k, True) for k in sorted(want - self.held_keys)]
            out += [self._key(k, False) for k in sorted(self.held_keys - want)]
            self.held_keys = want
            return out
        if self.held_keys:
            out += [self._key(k, False) for k in sorted(self.held_keys)]
            self.held_keys.clear()
        mag = math.hypot(lx, ly)
        if mag > DEAD:
            k = ((mag - DEAD) / (1 - DEAD)) ** 1.6 * CURSOR_SPEED * dt / mag
            old = (int(self.cursor[0]), int(self.cursor[1]))
            self.cursor[0] = max(0.0, min(theme.WIDTH - 1.0, self.cursor[0] + lx * k))
            self.cursor[1] = max(0.0, min(theme.HEIGHT - 1.0, self.cursor[1] + ly * k))
            new = (int(self.cursor[0]), int(self.cursor[1]))
            if new != old:
                held = 1 if "click" in self.pressed.values() else 0
                out.append(pygame.event.Event(pygame.MOUSEMOTION, pos=new, rel=(new[0] - old[0], new[1] - old[1]),
                                              buttons=(held, 0, 0), touch=False))
        ry = self.axes["RY"]
        self.scroll_timer -= dt
        if abs(ry) > 0.5 and self.scroll_timer <= 0:
            self.scroll_timer = SCROLL_EVERY
            out.append(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1 if ry > 0 else 1, flipped=False,
                                          precise_x=0.0, precise_y=-1.0 if ry > 0 else 1.0, touch=False))
        return out

    # ---------------------------------------------------------------- the pointer

    def draw(self, surf) -> None:
        """The controller's pointer: an arrow with a ring, drawn over everything."""
        if not self.active or self.mode() != "cursor":
            return
        x, y = int(self.cursor[0]), int(self.cursor[1])
        held = "click" in self.pressed.values()
        pygame.draw.circle(surf, theme.OUTLINE, (x, y), 15, 4)
        pygame.draw.circle(surf, theme.ACCENT, (x, y), 13 if held else 15, 2)
        pts = [(x, y), (x, y + 20), (x + 5, y + 15), (x + 9, y + 23), (x + 12, y + 21), (x + 8, y + 14), (x + 15, y + 14)]
        pygame.draw.polygon(surf, theme.OUTLINE, [(px + 1, py + 2) for px, py in pts])
        pygame.draw.polygon(surf, (255, 255, 255), pts)
        pygame.draw.polygon(surf, theme.OUTLINE, pts, 2)
