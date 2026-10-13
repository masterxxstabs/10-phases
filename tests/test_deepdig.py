"""Deep Dig: the world, the pod's physics, the shops, saving, and the screen."""

import math
import random

import pygame
import pytest

from ten_phases.deepdig import engine as dd
from ten_phases.deepdig.engine import (AIR, BEDROCK, CORE, DIRT, GAS, HALF, LAVA, ORE0, ROCK, DeepDig, DigError,
                                       generate)


def fresh(seed=3):
    return DeepDig(seed=seed)


def run(g, secs, **keys):
    for _ in range(int(secs * 60)):
        g.step(1 / 60, **keys)


def check(g):
    assert 0 <= g.fuel <= g.max_fuel + 1e-6
    assert 0 <= g.hull <= g.max_hull + 1e-6
    assert g.cash >= 0
    assert len(g.cargo) <= g.cargo_space
    assert HALF - 1e-6 <= g.x <= dd.W - HALF + 1e-6
    if g.drill is None:
        assert not g._hits(g.x, g.y), (g.x, g.y)


def test_world_generation():
    a, b = generate(42), generate(42)
    assert a == b and generate(43) != a                  # the same seed makes the same world
    assert len(a) == dd.H and all(len(r) == dd.W for r in a)
    assert all(t == BEDROCK for t in a[-1])
    assert sum(r.count(CORE) for r in a) == 1
    shallow = [t for r in a[1:60] for t in r]
    deep = [t for r in a[300:400] for t in r]
    assert dd.ORE0 in shallow and dd.ORE0 + 8 not in shallow            # diamonds aren't near the top
    assert any(t >= ORE0 + 6 for t in deep)
    assert deep.count(ROCK) > shallow.count(ROCK)                      # it gets harder further down
    for name, (lo, hi) in dd.BUILDINGS.items():
        assert all(a[0][c] == dd.CONCRETE for c in range(lo, hi + 1))  # no digging under the shops


def test_drilling_down_collects_ore_and_burns_fuel():
    g = fresh()
    col = int(g.x)
    for row in range(1, 6):
        g.set_tile(col, row, DIRT)
    g.set_tile(col, 3, ORE0 + 3)                                       # gold, 3 rows down
    fuel = g.fuel
    run(g, 6, down=True)
    assert g.row >= 5 and dd.ORE0 + 3 in g.cargo
    assert g.fuel < fuel and g.tile(col, 3) == AIR
    check(g)


def test_rock_cannot_be_drilled_but_dynamite_clears_it():
    g = fresh()
    col = int(g.x)
    g.set_tile(col, 0, DIRT)                                           # the topsoil under the pod is row 0
    g.set_tile(col, 1, ROCK)
    run(g, 2, down=True)
    assert g.row == 0 and any(e[0] == "rock" for e in g.pop_events())
    g.items["DYNAMITE"] = 1
    g.use_item("DYNAMITE")
    assert g.tile(col, 1) == AIR and g.items["DYNAMITE"] == 0
    with pytest.raises(DigError):
        g.use_item("DYNAMITE")


def test_sideways_drilling_and_falling():
    g = fresh()
    col = int(g.x)
    run(g, 1.5, down=True)          # into row 0
    g.drill = None
    g.set_tile(col, 1, ROCK)        # standing on rock
    g.set_tile(col + 1, 0, DIRT)
    for row in range(1, 8):
        g.set_tile(col + 1, row, AIR)
    run(g, 2, right=True)
    assert g.x > col + 1            # dug sideways and moved into the hole...
    run(g, 2)
    assert g.row >= 6               # ...then fell down the shaft
    check(g)


def test_hazards_hurt_and_heat_needs_a_radiator():
    g = fresh()
    col = int(g.x)
    g.set_tile(col, 0, GAS)
    run(g, 2, down=True)
    assert g.hull < g.max_hull and any(e[0] == "boom" for e in g.pop_events())
    hull = g.hull
    g.drill = None
    g.set_tile(col, g.row + 1, LAVA)
    run(g, 1, down=True)
    assert g.hull < hull
    hot = fresh()
    hot.x, hot.y = 10.5, dd.H - 10.4
    for c in range(9, 13):
        for r in range(dd.H - 12, dd.H - 9):
            hot.set_tile(c, r, AIR)
        hot.set_tile(c, dd.H - 9, ROCK)
    run(hot, 1)
    cool = DeepDig.from_dict({**hot.to_dict(), "levels": {"RADIATOR": 5}, "hull": hot.max_hull})
    hurt_plain = hot.max_hull - hot.hull
    run(cool, 1)
    assert hurt_plain > 0 and (cool.max_hull - cool.hull) < hurt_plain


def test_running_out_underground_means_a_tow():
    g = fresh()
    g.cash = 1000
    run(g, 2, down=True)
    g.cargo = [ORE0, ORE0]
    g.fuel = 0.001
    ev = []
    for _ in range(60):
        g.step(1 / 60, down=True)
        ev += g.pop_events()
        if any(e[0] == "tow" for e in ev):
            break
    tow = [e for e in ev if e[0] == "tow"]
    assert tow and g.on_surface and not g.cargo
    assert g.cash == 1000 - tow[0][2] and g.fuel == g.max_fuel


def test_town_buildings():
    g = fresh()
    g.cargo = [ORE0 + 3] * 3                                     # 3 gold = $900
    with pytest.raises(DigError):
        g.sell()                                                  # not parked at the ore buyer
    g.x = 12.5
    run(g, 0.2)
    assert g.building() == "SELL"
    total, chips = g.sell()
    assert total == 900 and chips == 1 and g.cash == 900 and g.chip_progress == 400
    g.x = 21.5
    run(g, 0.2)
    g.buy_upgrade("DRILL")
    assert g.levels["DRILL"] == 1 and g.cash == 150
    with pytest.raises(DigError):
        g.buy_upgrade("DRILL")                                    # can't afford level 2
    g.x, g.fuel = 3.5, 2.0
    run(g, 0.2)
    g.refuel()
    assert g.cash < 150 and g.fuel > 2.0
    g.x, g.hull = 30.5, 50
    run(g, 0.2)
    g.repair()
    assert g.hull > 50


def test_broke_and_empty_gets_emergency_fuel_and_can_still_roll():
    g = fresh()
    g.fuel, g.cash = 0.0, 0
    run(g, 3, left=True)                     # rolling along the surface needs no fuel
    assert g.x < 10
    g.x = 3.5
    run(g, 0.3)
    assert g.building() == "FUEL"
    assert g.refuel() == 0 and g.fuel > 0


def test_the_core_ends_the_quest_but_not_when_the_hold_is_full():
    g = fresh()
    mid = dd.W // 2
    g.x, g.y = mid - 1 + 0.5, dd.H - 4 + 1 - HALF - 1   # in the chamber, next to the core
    g.y = dd.H - 3 - HALF
    g.cargo = [ORE0] * g.cargo_space
    run(g, 2, right=True)
    assert g.tile(mid, dd.H - 4) == CORE and not g.won    # full: the core stays put
    g.cargo = []
    run(g, 3, right=True)
    assert g.won and CORE in g.cargo


def test_save_and_load_round_trip_and_bad_saves():
    g = fresh(9)
    run(g, 3, down=True)
    g.cash, g.levels["CARGO"], g.items["TELEPORTER"] = 1234, 2, 3
    g.cargo = [ORE0 + 1]
    h = DeepDig.from_dict(g.to_dict())
    assert h.grid == g.grid and h.cash == 1234 and h.levels["CARGO"] == 2 and h.items["TELEPORTER"] == 3
    sy = g.drill.start[1] if g.drill else g.y                         # mid-drill saves where the drill began
    assert h.cargo == [ORE0 + 1] and abs(h.y - sy) < 1e-6 and h.y > 0
    junk = DeepDig.from_dict({"seed": 4, "grid": "nope", "cash": -5, "levels": {"DRILL": 99}, "fuel": "x",
                              "cargo": [1, 2, 999], "x": 1e9})
    assert junk.cash == 0 and junk.levels["DRILL"] == 0 and junk.cargo == [] and junk.x <= dd.W
    check(junk)


def test_save_file(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.deepdig import save
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    assert save.load_game() is None
    g = fresh()
    g.cash = 77
    save.save_game(g)
    assert save.load_game().cash == 77
    save.save_path().write_text("{broken")
    assert save.load_game() is None
    save.delete_save()
    assert not save.save_path().exists()


def bot(g, rng, minutes=6):
    """A simple player: dig, go home to sell and refuel, buy upgrades."""
    phase, path = "dig", {}          # path: the column the pod dug through on each row, to fly back up it
    for _ in range(int(minutes * 60 * 30)):
        dt = 1 / 30
        if phase == "dig":
            if g.drill is None and g.grounded:
                path.setdefault(g.row, g.x)
            if len(g.cargo) >= g.cargo_space or g.fuel < g.max_fuel * 0.45 or g.hull < g.max_hull * 0.4:
                phase = "up"
            if g.drill:
                g.step(dt)
                continue
            col = int(g.x)
            below = g.tile(col, int(math.floor(g.y + HALF + 0.05)))
            side = [d for d in (-1, 1) if g.row >= 0 and dd.is_ore(g.tile(col + d, g.row))]
            if side and g.grounded and not dd.is_ore(below):                 # grab ore right next to the pod
                g.step(dt, left=side[0] < 0, right=side[0] > 0)
                path[g.row] = g.x
            elif below in dd.UNDRILLABLE:
                g.step(dt, left=rng.random() < 0.5, right=rng.random() >= 0.5)
            else:
                g.step(dt, down=True)
        elif phase == "up":
            if g.on_surface and g.y < -1.2:
                phase = "home"
            if g.items["TELEPORTER"]:
                g.use_item("TELEPORTER")
                phase = "home"
            goal = path.get(g.row - 1, path.get(g.row, g.x))       # line up under the shaft above
            g.step(dt, up=abs(goal - g.x) < 0.3 or not g.grounded,
                   left=goal < g.x - 0.1, right=goal > g.x + 0.1)
        else:   # fly over to each building, use it
            for name, (a, b) in (("SELL", dd.BUILDINGS["SELL"]), ("FUEL", dd.BUILDINGS["FUEL"]),
                                 ("REPAIR", dd.BUILDINGS["REPAIR"]), ("SHOP", dd.BUILDINGS["SHOP"])):
                g.x, g.y, g.vx, g.vy = (a + b + 1) / 2, -HALF, 0.0, 0.0
                g.step(dt)
                try:
                    {"SELL": lambda: g.cargo and g.sell(), "FUEL": g.refuel, "REPAIR": g.repair,
                     "SHOP": lambda: None}[name]()
                except DigError:
                    pass
                if name == "SHOP":
                    for up in ("DRILL", "FUEL TANK", "CARGO", "HULL", "ENGINE", "RADIATOR"):
                        try:
                            g.buy_upgrade(up)
                        except DigError:
                            pass
            g.x, g.y = rng.uniform(6.5, 9.5) if rng.random() < 0.5 else rng.uniform(25.5, 28.5), -HALF
            phase, path = "dig", {}
        check(g)


@pytest.mark.parametrize("seed", range(4))
def test_a_bot_digs_sells_and_upgrades(seed):
    g = fresh(seed)
    bot(g, random.Random(seed), minutes=6)
    assert g.earned > 0 and g.deepest > 20
    assert sum(g.levels.values()) >= 1


def test_mashing_every_key_never_breaks_the_rules():
    rng = random.Random(1)
    g = fresh(11)
    g.cash = 50000
    for _ in range(20000):
        keys = {k: rng.random() < 0.4 for k in ("left", "right", "up", "down")}
        g.step(rng.choice((1 / 60, 1 / 30, 0.05)), **keys)
        if rng.random() < 0.01:
            try:
                g.use_item(rng.choice(dd.ITEM_KEYS))
            except DigError:
                pass
        if rng.random() < 0.003:
            g.items[rng.choice(dd.ITEM_KEYS)] += 1
        check(g)


def test_the_sky_draws_at_every_camera_height(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.ui import deepdig_art
    from ten_phases.ui.deepdig_scene import DeepDigScene
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    scene = DeepDigScene(app, DeepDig(seed=2))
    scene.splash = None
    before = len(deepdig_art._cache)
    for cam_y in range(-9 * 40, 41, 7):                 # just above ground used to crash the clouds
        scene.cam = [0.0, float(cam_y)]
        scene._draw_world(app.screen)
    assert len(deepdig_art._cache) <= before + 120      # one sky, not one per camera height


def test_the_screen_plays(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.ui.deepdig_scene import DeepDigScene
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    scene = DeepDigScene(app, DeepDig(seed=2))
    app.go(scene)
    scene.splash = None
    press = lambda k: scene.handle(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))  # noqa: E731
    release = lambda k: scene.handle(pygame.event.Event(pygame.KEYUP, key=k, mod=0, unicode=""))  # noqa: E731
    press(pygame.K_DOWN)
    for _ in range(240):
        scene.update(1 / 30)
        scene.draw(app.screen)
    release(pygame.K_DOWN)
    assert scene.game.row > 2
    g = scene.game
    g.cargo = [ORE0 + 2] * 3
    g.drill = None
    g.x, g.y, g.vx, g.vy = 12.5, -HALF, 0.0, 0.0
    scene.update(1 / 30)
    press(pygame.K_e)
    assert scene.panel == "SELL"
    scene.draw(app.screen)
    bank = app.settings.chip_bank
    scene.panel_buttons[0].on_click()
    assert g.cash == 360 and not g.cargo
    assert app.settings.chip_bank == bank      # $360: not a whole chip yet
    press(pygame.K_ESCAPE)
    assert scene.panel is None
    g.x = 21.5
    g.cash = 5000
    scene.update(1 / 30)
    scene.use_building()
    assert scene.panel == "SHOP"
    scene.draw(app.screen)
    scene.close_panel()
    press(pygame.K_ESCAPE)
    assert scene.overlay == "pause"
    scene.draw(app.screen)
    from ten_phases.deepdig.save import load_game
    assert load_game().cash == g.cash                     # pausing saves
