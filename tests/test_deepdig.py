"""Deep Dig: the world, the pod's physics, the shops, saving, and the screen."""

import math
import random

import pygame
import pytest

from ten_phases.deepdig import engine as dd
from ten_phases.deepdig.engine import (AIR, BEDROCK, CONCRETE, CORE, DIRT, GAS, HALF, LAVA, ORE0, ROCK, DeepDig,
                                       DigError, generate, make_chunk)


MINE_X = 16.5      # above the middle of the mine


def fresh(seed=3):
    g = DeepDig(seed=seed)
    g.x = MINE_X
    return g


def at(name):
    """The middle of a building in town."""
    a, b = dd.BUILDINGS[name]
    return (a + b + 1) / 2


def run(g, secs, **keys):
    for _ in range(int(secs * 60)):
        g.step(1 / 60, **keys)


def check(g):
    assert 0 <= g.fuel <= g.max_fuel + 1e-6
    assert 0 <= g.hull <= g.max_hull + 1e-6
    assert g.cash >= 0
    assert len(g.cargo) <= g.cargo_space
    assert -dd.TOWN_W + HALF - 1e-6 <= g.x <= dd.W - HALF + 1e-6
    if g.drill is None:
        assert not g._hits(g.x, g.y), (g.x, g.y)


def test_world_generation():
    a, b = generate(42), generate(42)
    assert a == b and generate(43) != a                  # the same seed makes the same world
    assert len(a) == dd.H and all(len(r) == dd.W for r in a)
    assert sum(r.count(CORE) for r in a) == 1
    assert a[dd.H - 3][dd.W // 2] == BEDROCK                          # the Heart sits on a bedrock plinth
    shallow = [t for r in a[1:60] for t in r]
    deep = [t for r in a[300:400] for t in r]
    assert dd.ORE0 in shallow and dd.ORE0 + 8 not in shallow            # diamonds aren't near the top
    assert any(t >= ORE0 + 6 for t in deep)
    assert deep.count(ROCK) > shallow.count(ROCK)                      # it gets harder further down
    assert dd.CONCRETE not in a[0]                                     # the mine's top is all topsoil
    g = DeepDig(seed=42)
    assert g.x < 0 and g.on_surface                                    # you start in town...
    for name, (lo, hi) in dd.BUILDINGS.items():
        assert hi < 0 and all(g.tile(c, r) in dd.UNDRILLABLE for c in range(lo, hi + 1) for r in (0, 1, 5, 400))


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
    g.x = at("SELL")
    run(g, 0.2)
    assert g.building() == "SELL"
    total, chips = g.sell()
    assert total == 900 and chips == 1 and g.cash == 900 and g.chip_progress == 400
    g.x = at("SHOP")
    run(g, 0.2)
    with pytest.raises(DigError):
        g.buy_upgrade("LAMP")                                     # gadgets are at the tech lab
    with pytest.raises(DigError):
        g.buy_item("DYNAMITE")
    g.buy_upgrade("DRILL")
    assert g.levels["DRILL"] == 1 and g.cash == 150
    with pytest.raises(DigError):
        g.buy_upgrade("DRILL")                                    # can't afford level 2
    g.x, g.fuel = at("FUEL"), 2.0
    run(g, 0.2)
    g.refuel()
    assert g.cash < 150 and g.fuel > 2.0
    g.x, g.hull = at("REPAIR"), 50
    run(g, 0.2)
    g.repair()
    assert g.hull > 50


def test_broke_and_empty_gets_emergency_fuel_and_can_still_roll():
    g = fresh()
    g.fuel, g.cash = 0.0, 0
    run(g, 3, left=True)                     # rolling along the surface needs no fuel
    assert g.x < 10
    g.x = at("FUEL")
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
            if g.x < 0.6:                       # towed back to town: roll over to the mine
                g.step(dt, right=True)
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
    scene = DeepDigScene(app, fresh(2))
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
    g.x, g.y, g.vx, g.vy = at("SELL"), -HALF, 0.0, 0.0
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
    g.x = at("SHOP")
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


def test_the_ground_goes_on_forever():
    g = fresh(5)
    assert len(g.grid) == dd.H
    deep = g.tile(4, 3000)                                    # asking for a row makes it
    assert len(g.grid) > 3000 and len(g.grid) % dd.CHUNK == 0 and deep != BEDROCK
    c = 3000 // dd.CHUNK
    assert g.grid[c * dd.CHUNK:(c + 1) * dd.CHUNK] == make_chunk(5, c)   # the same for a seed, whenever it's made
    assert all(t not in (BEDROCK, CONCRETE) for r in g.grid[dd.H:] for t in r)    # nothing blocks the way down
    assert not any(CORE in r for r in g.grid[dd.H:])
    below = [t for r in g.grid[900:1500] for t in r]
    near = [t for r in g.grid[300:400] for t in r]
    worth = lambda ts: sum(dd.tile_value(t) for t in ts)      # noqa: E731
    assert worth(below) > worth(near)                         # richer the deeper you go
    g.x, g.y = 10.5, 2000.6
    for c in range(9, 13):
        g.set_tile(c, 2000, AIR)
    g.set_tile(10, 2001, DIRT)
    g.drill = None
    g.levels["RADIATOR"] = 7
    run(g, 2, down=True)
    assert g.row >= 2001 and g.deepest >= 2001 and g.heat() > 1.0
    check(g)


def test_old_saves_still_load():
    g = fresh(6)
    d = g.to_dict()
    grid = [list(r) for r in d["grid"]]
    for row, r in enumerate(grid):                               # how v1 saved a world: core = 20, bedrock floor
        grid[row] = [chr(48 + 20) if ch == chr(48 + CORE) else chr(48 + DIRT) if ord(ch) - 48 >= 20 else ch
                     for ch in r]                              # (v1 had no ores past 19)
    for row in range(dd.H - 3, dd.H):
        grid[row] = [chr(48 + BEDROCK)] * dd.W
    old = {**d, "v": 1, "grid": ["".join(r) for r in grid], "cargo": [20, ORE0 + 2]}
    h = DeepDig.from_dict(old)
    assert h.cargo == [CORE, ORE0 + 2]
    assert sum(r.count(CORE) for r in h.grid) == 1
    assert h.grid[dd.H - 1] == [DIRT] * dd.W and h.grid[dd.H - 3][dd.W // 2] == BEDROCK
    assert h.tile(3, dd.H + 5) is not None and len(h.grid) > dd.H        # and it carries on below
    new = DeepDig.from_dict(h.to_dict())
    assert new.grid == h.grid and new.cargo == h.cargo


def test_new_upgrades_and_ores():
    assert len(dd.ORES) == 17 and len({o.name for o in dd.ORES}) == 17
    assert all(dd.is_ore(ORE0 + k) for k in range(17)) and dd.is_ore(CORE) and not dd.is_ore(ORE0 + 17)
    for name, (values, prices) in dd.UPGRADES.items():
        assert len(values) == len(prices) in (2, 4, 8) and list(prices) == sorted(prices)
        assert name in dd.UPGRADE_SHOP and name in dd.UPGRADE_INFO
        for lvl in range(len(values)):
            assert dd.upgrade_text(name, lvl)
    g = fresh()
    g.x, g.y = 10.5, 30.6
    for r in range(18, 31):
        for c in range(9, 13):
            g.set_tile(c, r, AIR)
    for c in range(9, 13):
        g.set_tile(c, 31, ROCK)
    g.y, g.vy, g.grounded = 18.6, 0.0, False
    run(g, 2)
    soft = fresh()
    soft.grid = [r[:] for r in g.grid]
    soft.levels["SHOCKS"] = 7
    assert g.hull < g.max_hull                                 # a long fall dents the hull...
    soft.x, soft.y, soft.vy, soft.grounded = 10.5, 18.6, 0.0, False
    run(soft, 2)
    assert soft.hull == soft.max_hull                          # ...but not with the best shocks


def test_bug_fixes():
    g = fresh()
    # The world's edge is a wall, not a rock to blast.
    g.x, g.y = dd.W - HALF, 5.6
    for c in range(dd.W - 2, dd.W):
        g.set_tile(c, 5, AIR)
        g.set_tile(c, 6, DIRT)
    g.pop_events()
    run(g, 0.5, right=True)
    assert not any(e[0] == "rock" for e in g.pop_events())
    # Broke with $1 and an empty tank: the station's free fuel, as the button says.
    h = fresh()
    h.cash, h.fuel = 1, 0.5
    h.x, h.y = at("FUEL"), -HALF
    assert h.emergency_fuel()
    assert h.refuel() == 0 and h.cash == 1 and h.fuel >= 0.3 * h.max_fuel
    # A slow frame is played in small steps: same place as many small ones.
    a, b = fresh(), fresh()
    a.step(0.2, right=True)
    for _ in range(6):
        b.step(1 / 30, right=True)
    assert abs(a.x - b.x) < 1e-9


def test_leaving_saves_and_starting_over_does_not(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.deepdig import save
    from ten_phases.ui.deepdig_scene import DeepDigScene
    from ten_phases.ui.menus import MenuScene
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    scene = DeepDigScene(app, DeepDig(seed=2))
    app.go(scene)
    scene.game.cash = 4321
    app.go(MenuScene(app))                                     # closing the window does the same
    assert save.load_game().cash == 4321
    scene = DeepDigScene(app)
    app.go(scene)
    scene.game.cash = 99
    scene.new_game()
    assert save.load_game() is None or save.load_game().cash != 99
    # Losing focus lets go of the keys and pauses.
    scene = app.scene
    scene.splash = None
    scene.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, mod=0, unicode=""))
    scene.handle(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    assert not scene.keys and scene.overlay == "pause"


def test_deep_screens_draw(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.ui.deepdig_scene import DeepDigScene
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    g = DeepDig(seed=4)
    g.levels.update({"SCANNER": 7, "LAMP": 7, "RADIATOR": 7, "HULL": 7})
    g.hull = g.max_hull
    scene = DeepDigScene(app, g)
    app.go(scene)
    scene.splash = None
    for depth in (30, 300, dd.H - 4, 1200):
        g.drill = None
        g.x, g.y = dd.W // 2 + 0.5, depth + 0.6
        for c in range(dd.W // 2 - 1, dd.W // 2 + 2):
            g.set_tile(c, depth, AIR)
        scene.cam = [g.x * 40 - 640, g.y * 40 - 300]
        scene.update(1 / 30)
        scene.draw(app.screen)
    g.cargo = [ORE0 + k for k in range(8)]
    g.x, g.y, g.vx, g.vy, g.drill = at("SELL"), -HALF, 0.0, 0.0, None
    scene.update(1 / 30)
    scene.use_building()
    scene.draw(app.screen)                                      # 8 kinds of ore: the list fits
    scene.close_panel()
    g.x, g.cash = at("SHOP"), 10 ** 7
    scene.update(1 / 30)
    scene.use_building()
    scene.draw(app.screen)
    assert scene.panel == "SHOP" and len(scene.panel_buttons) == 8 + 1
    scene.panel_buttons[0].on_click()                           # buy a drill upgrade
    assert g.levels["DRILL"] == 1
    scene.close_panel()
    g.x = at("LAB")
    scene.update(1 / 30)
    scene.use_building()
    scene.draw(app.screen)
    assert scene.panel == "LAB" and len(scene.panel_buttons) == 5 + 5 + 1
    scene.panel_buttons[5].on_click()                           # buy a repair kit
    assert g.items["REPAIR KIT"] == 1


def test_digging_up_needs_the_top_drill():
    g = fresh()
    g.x, g.y, g.drill = 10.5, 20.6, None
    for c in range(9, 13):
        g.set_tile(c, 20, AIR)
        g.set_tile(c, 21, ROCK)
    g.set_tile(10, 19, DIRT)
    g.set_tile(10, 18, ORE0 + 3)
    run(g, 1.5, up=True)
    assert g.tile(10, 19) == DIRT                                  # no roof drill: just bumps the ceiling
    g.levels["TOP DRILL"] = 1
    g.drill = None
    events = []
    for _ in range(int(4 * 60)):
        g.step(1 / 60, up=True)
        events += g.pop_events()
    assert g.tile(10, 19) == AIR and g.tile(10, 18) == AIR and ORE0 + 3 in g.cargo
    assert any(e[0] == "drill" and e[2] == 19 for e in events) and g.row <= 18
    check(g)


def test_armor_refinery_and_rescue():
    hurt = {}
    for lvl in (0, 7):
        g = fresh()
        g.levels["ARMOR"] = lvl
        g.set_tile(int(g.x), 0, GAS)
        run(g, 1.5, down=True)
        hurt[lvl] = g.max_hull - g.hull
    assert 0 < hurt[7] < hurt[0] * 0.5
    g = fresh()
    g.levels["REFINERY"] = 7
    g.cargo = [ORE0 + 3] * 2                                       # 2 gold: $600, +50%
    g.x = at("SELL")
    run(g, 0.2)
    assert g.cargo_value == 900 and g.sell()[0] == 900
    g = fresh()
    g.levels["RESCUE"] = 7
    g.cash = 1000
    g.cargo = [ORE0] * 6 + [ORE0 + 8] * 4                          # iron, and diamonds
    g.y, g.drill = 10.6, None
    g._tow("test")
    assert len(g.cargo) == 8 and g.cargo.count(ORE0 + 8) == 4     # keeps 85%, the best first
    assert g.cash > 1000 - 250 * 0.2 and g.x < 0


def test_no_digging_in_town_and_old_saves_lose_their_concrete():
    g = DeepDig(seed=3)
    g.x = at("SHOP")
    run(g, 0.3)
    g.pop_events()
    run(g, 1, down=True)
    assert g.on_surface and any(e[0] == "town" for e in g.pop_events())
    g.items["DYNAMITE"] = 1
    with pytest.raises(DigError):
        g.use_item("DYNAMITE")
    d = fresh(4).to_dict()
    row0 = list(d["grid"][0])
    for c in range(2, 6):                                           # v2 had the fuel station on the mine
        row0[c] = chr(48 + CONCRETE)
    h = DeepDig.from_dict({**d, "v": 2, "grid": ["".join(row0)] + d["grid"][1:], "x": 3.5})
    assert CONCRETE not in h.grid[0] and h.x == 3.5
    assert DeepDig.from_dict(h.to_dict()).to_dict()["v"] == 3


def test_dig_bots_mine_and_sell_for_you():
    g = fresh(8)
    g.cash = 10 ** 6
    with pytest.raises(DigError):
        g.buy_upgrade("DIG BOTS")                                  # sold at robotics
    g.x = at("BOTS")
    run(g, 0.2)
    for _ in range(3):
        g.buy_upgrade("DIG BOTS")
    assert len(g.bots) == dd.MAX_BOTS and g.upgrade_price("DIG BOTS") is None
    g.buy_upgrade("BOT LEVEL")
    g.x = MINE_X
    cash, events = g.cash, []
    heart = (dd.W // 2, dd.H - 4)
    for _ in range(int(4 * 60 * 30)):
        g.step(1 / 30)
        events += g.pop_events()
        for bot in g.bots:
            assert 0 <= bot.col < dd.W and bot.row >= -1
            if bot.row >= 0:
                assert g.tile(bot.col, bot.row) == AIR                 # only ever standing in dug-out space
            assert bot.row <= dd.BOT_DEPTH[g.levels["BOT LEVEL"]]
            assert len(bot.carry) <= dd.BOT_CARRY[g.levels["BOT LEVEL"]]
    sells = [e for e in events if e[0] == "bot_sell"]
    assert len(sells) >= 6 and g.cash - cash == sum(e[2] for e in sells) == g.bot_earned
    assert {e[1] for e in sells} == {0, 1, 2}                     # all three of them work
    assert g.tile(*heart) == CORE
    h = DeepDig.from_dict(g.to_dict())
    assert [(b.col, b.row, b.state, b.carry) for b in h.bots] == [(b.col, b.row, b.state, b.carry) for b in g.bots]
    assert h.bot_earned == g.bot_earned
    junk = DeepDig.from_dict({**g.to_dict(), "bots": [["x"], [999, 5, "dig", [1, ORE0, CORE, True]], 7]})
    assert len(junk.bots) == 3 and junk.bots[1].carry == [ORE0] and 0 <= junk.bots[1].col < dd.W


def test_a_boxed_in_bot_beams_home():
    g = fresh()
    g.levels["DIG BOTS"] = 1
    g._sync_bots()
    bot = g.bots[0]
    bot.col, bot.row = bot.to_col, bot.to_row = 10, 50
    bot.carry = [ORE0 + 3]
    g.set_tile(10, 50, AIR)
    for c, r in ((9, 50), (11, 50), (10, 49), (10, 51)):
        g.set_tile(c, r, ROCK)
    run(g, 4)
    assert any(e[0] == "bot_sell" for e in g.pop_events()) and g.cash >= 300


def test_robotics_screen(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.ui.deepdig_scene import DeepDigScene
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    g = DeepDig(seed=4)
    g.cash = 10 ** 6
    scene = DeepDigScene(app, g)
    app.go(scene)
    scene.splash = None
    g.x = at("BOTS")
    scene.update(1 / 30)
    scene.use_building()
    assert scene.panel == "BOTS"
    scene.draw(app.screen)
    scene.panel_buttons[0].on_click()                            # hire a bot
    assert len(g.bots) == 1
    scene.draw(app.screen)
    scene.close_panel()
    g.bots[0].carry = [ORE0 + 8] * 3                               # 3 diamonds: $150,000
    g.bots[0].state = "home"
    g.bots[0].row = g.bots[0].to_row = 0
    g.set_tile(g.bots[0].col, 0, AIR)
    bank = app.settings.chip_bank
    for _ in range(60):
        scene.update(1 / 30)
        scene.draw(app.screen)
    assert g.bot_earned == 150000 and app.settings.chip_bank == bank + 300


def test_the_bank_turns_cash_into_chips(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.ui.deepdig_scene import DeepDigScene
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    g = DeepDig(seed=2)
    g.cash = dd.BANK_RATE * 12 + 100
    with pytest.raises(DigError):
        g.exchange(1)                                             # not at the bank
    scene = DeepDigScene(app, g)
    app.go(scene)
    scene.splash = None
    g.x = at("BANK")
    scene.update(1 / 30)
    scene.use_building()
    assert scene.panel == "BANK"
    scene.draw(app.screen)
    bank = app.settings.chip_bank
    buttons = {b.label: b for b in scene.panel_buttons}
    assert not buttons["100 CHIPS"].enabled and buttons["10 CHIPS"].enabled
    buttons["10 CHIPS"].on_click()
    assert app.settings.chip_bank == bank + 10 and g.cash == dd.BANK_RATE * 2 + 100
    buttons = {b.label: b for b in scene.panel_buttons}
    buttons["ALL: 2"].on_click()
    assert app.settings.chip_bank == bank + 12 and g.cash == 100
    with pytest.raises(DigError):
        g.exchange(1)                                             # broke
    for bad in (0, -5, 1.5):
        with pytest.raises(DigError):
            g.exchange(bad)
    scene.draw(app.screen)
    assert all(not b.enabled for b in scene.panel_buttons if b.label != "X")
