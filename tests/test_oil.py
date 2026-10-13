"""Deep Dig's Oil Field: land, scanning, rigs, pipes, pumping, trucks, buyers, saving, and the screen."""

import pygame
import pytest

from ten_phases.deepdig import oil as om
from ten_phases.deepdig.engine import BUILDINGS, DeepDig, DigError
from ten_phases.deepdig.oil import GAS, OIL, PLOT, ROCK, ROWS, OilError, OilField


class Wallet:
    def __init__(self, cash=100000):
        self.cash = cash


def field(seed=5, cash=100000):
    return OilField(seed, Wallet(cash))


def run(f, secs, dt=1 / 20):
    events = []
    for _ in range(int(secs / dt)):
        f.step(dt)
        events += f.pop_events()
    return events


def oil_pockets(f):
    return [p for p in f.pockets.values() if p.kind == OIL and f.owned(p.cells[0][0])]


def check(f):
    for rig in f.rigs:
        assert 0 <= rig.tank <= f.stat("TANKS") + 1e-6
    for t in f.trucks:
        assert 0 <= t.load <= f.stat("TRUCK SIZE") + 1e-6
    for p in f.pockets.values():
        assert 0 <= p.amount <= p.start + 1e-6
    owners = {}
    for i, rig in enumerate(f.rigs):
        for cell in rig.pipe + rig.queue:
            assert owners.setdefault(cell, i) == i              # no two rigs share a cell
    assert all(0.5 <= v <= 8.0 for v in f.prices.values())


def test_the_land_is_the_same_whenever_it_is_made():
    a, b = field(), field()
    for _ in range(3):
        b.buy_land()
    assert {k: v for k, v in b.tiles.items() if k[0] < a.width + PLOT} == a.tiles   # buying later changes nothing
    assert len(oil_pockets(a)) >= 4 and any(p.kind == GAS for p in a.pockets.values())
    assert field(6).tiles != a.tiles
    early = sum(p.start for p in a.pockets.values() if p.kind == OIL and p.cells[0][0] < 2 * PLOT)
    c = field(cash=10 ** 9)
    for _ in range(12):
        c.buy_land()
    late = sum(p.start for p in c.pockets.values() if p.kind == OIL and 12 * PLOT <= p.cells[0][0] < 14 * PLOT)
    assert late > early                                                        # richer further right


def test_scanning_rigs_and_land():
    f = field(cash=5000)
    with pytest.raises(OilError):
        f.scan(f.width + 2, 5)                                                 # not your land yet
    f.scan(4, 8)
    assert f.wallet.cash == 5000 - om.SCAN_PRICE and (4, 8) in f.revealed and (4, 8 + om.SCAN_RADIUS) in f.revealed
    assert (4, 8 + om.SCAN_RADIUS + 1) not in f.revealed
    f.wallet.cash = 100000
    f.place_rig(3)
    with pytest.raises(OilError):
        f.place_rig(4)                                                         # too close
    assert f.rig_price() == om.RIG_PRICE + om.RIG_STEP
    width, price = f.width, f.land_price()
    f.buy_land()
    assert f.width == width + PLOT and f.land_price() > price
    assert f.generated == f.plots + 1
    f.wallet.cash = 0
    with pytest.raises(OilError):
        f.buy_truck()


def test_pipes_go_around_known_rock_and_stop_at_hidden_rock():
    f = field()
    for r in range(ROWS):                                                      # a clean column to work in
        for c in range(0, 8):
            f.tiles.pop((c, r), None)
            f.pocket_at.pop((c, r), None)
    f.tiles[(2, 5)] = ROCK
    f.revealed.add((2, 5))
    i = f.place_rig(2)
    plan = f.plan_pipe(2, 8, i)
    assert plan and (2, 5) not in plan[1] and plan[1][-1] == (2, 8)
    cash = f.wallet.cash
    n = f.lay_pipe(2, 8, i)
    assert f.wallet.cash == cash - n * om.PIPE_PRICE
    run(f, 10)
    assert (2, 8) in f.rigs[i].pipe and not f.rigs[i].queue
    # Hidden rock: the drill stops there, and the rest is refunded.
    f.tiles[(5, 4)] = ROCK
    j = f.place_rig(5)
    run(f, 2)                                                                  # (the rig's first cell goes in)
    cash = f.wallet.cash
    n = f.lay_pipe(5, 9, j)
    events = run(f, 10)
    stop = [e for e in events if e[0] == "stopped"]
    assert stop and stop[0][2] == "rock" and (5, 4) in f.revealed and (5, 4) not in f.rigs[j].pipe
    dug = len(f.rigs[j].pipe) - 1
    assert stop[0][3] == om.PIPE_PRICE * (n - dug) and f.wallet.cash == cash - om.PIPE_PRICE * dug
    f.levels["ROCK BIT"] = 1                                                   # with a rock bit: straight through
    f.lay_pipe(5, 9, j)
    run(f, 10)
    assert (5, 4) in f.rigs[j].pipe and (5, 9) in f.rigs[j].pipe
    check(f)


def test_gas_blows_the_tip_off():
    f = field()
    for r in range(ROWS):
        f.tiles.pop((10, r), None)
        f.pocket_at.pop((10, r), None)
    f._add_pocket(9999, GAS, [(10, 6), (11, 6)], 0)
    i = f.place_rig(10)
    f.lay_pipe(10, 9, i)
    events = run(f, 10)
    assert any(e[0] == "boom" for e in events) and 9999 not in f.pockets
    assert (10, 6) not in f.rigs[i].pipe and f.tile(11, 6) != GAS
    assert len(f.rigs[i].pipe) <= 4 and not f.rigs[i].queue


def test_pumping_hauling_and_selling():
    f = field()
    pocket = oil_pockets(f)[0]
    c, r = pocket.cells[0]
    f.levels["ROCK BIT"] = 1
    i = f.place_rig(c)
    f.lay_pipe(c, r, i)
    events = run(f, 40)
    assert [e for e in events if e[0] == "strike"] == [("strike", i, pocket.id)]   # once per pocket
    assert f.rigs[i].tank > 50 and pocket.amount < pocket.start
    run(f, 200)
    assert f.rigs[i].tank == pytest.approx(f.stat("TANKS"))                    # the tank fills up, then waits
    left = pocket.amount
    run(f, 5)
    assert pocket.amount == left
    f.trucks[0].auto = True                                                     # (no dispatcher: it just sits)
    run(f, 5)
    assert f.trucks[0].goal is None and f.trucks[0].load == 0
    f.send(0, ("rig", i))
    run(f, 30)
    assert f.trucks[0].load == pytest.approx(f.stat("TRUCK SIZE"))
    cash = f.wallet.cash
    f.send(0, ("buyer", "R"))
    events = run(f, 30)
    sells = [e for e in events if e[0] == "sell"]
    assert len(sells) == 1 and sells[0][2] == "R" and f.trucks[0].load == 0    # paid once, at the end
    assert f.earned == sells[0][1] and 200 * 0.5 <= sells[0][1] <= 200 * 8
    price = f.prices["L"]
    f._sell("L", 1000)
    assert f.prices["L"] < price - 0.5                                         # flooding a buyer drops its price
    assert f.wallet.cash == cash                                                # (the game banks it, not the field)
    check(f)


def test_the_dispatcher_runs_the_business():
    f = field()
    f.levels.update({"ROCK BIT": 1, "DISPATCHER": 1})
    for pocket in oil_pockets(f)[:3]:
        c, r = pocket.cells[0]
        try:
            i = f.place_rig(c)
        except OilError:
            continue
        f.lay_pipe(c, r, i)
    f.buy_truck()
    assert all(t.auto for t in f.trucks)
    for _ in range(6 * 60 * 20):
        f.step(1 / 20)
        for e in f.pop_events():
            if e[0] == "sell":
                assert e[1] >= 100                    # full-ish loads, not dribbles
        check(f)
    assert f.earned > 4000
    f.set_auto(0, False)
    assert not f.trucks[0].auto


def test_saving_the_field():
    g = DeepDig(seed=4)
    g.cash = 10 ** 6
    a, b = BUILDINGS["OIL"]
    g.x = (a + b + 1) / 2
    with pytest.raises(DigError):
        DeepDig(seed=4).buy_oil()                     # not at the refinery
    g.buy_oil()
    with pytest.raises(DigError):
        g.buy_oil()
    f = g.oil
    f.levels.update({"ROCK BIT": 1, "PUMPS": 3})
    pocket = oil_pockets(f)[0]
    i = f.place_rig(pocket.cells[0][0])
    f.lay_pipe(*pocket.cells[0], i)
    f.buy_land()
    f.buy_truck()
    gas = next(p for p in f.pockets.values() if p.kind == GAS)
    f.pockets.pop(gas.id)
    run(f, 20)
    h = DeepDig.from_dict(g.to_dict())
    o = h.oil
    assert o.wallet is h and o.plots == f.plots and o.levels == f.levels and o.revealed == f.revealed
    assert [(r.col, r.pipe, r.queue, round(r.tank, 2)) for r in o.rigs] == \
           [(r.col, r.pipe, r.queue, round(r.tank, 2)) for r in f.rigs]
    assert gas.id not in o.pockets and o.pockets[pocket.id].amount == pytest.approx(pocket.amount, abs=0.01)
    assert len(o.trucks) == 2 and o.earned == f.earned
    junk = DeepDig.from_dict({**g.to_dict(), "oil": {"seed": 3, "plots": "x", "rigs": [{"col": 999}, 5],
                                                      "trucks": [{"x": "y", "load": 1e12}], "revealed": [[1], "a"]}})
    assert junk.oil.plots == om.START_PLOTS and not junk.oil.rigs and junk.oil.trucks[0].load <= 200
    check(junk.oil)


def test_it_keeps_going_while_you_dig(app, tmp_path, monkeypatch):
    from ten_phases import settings
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    g = DeepDig(seed=4)
    g.cash = 10 ** 6
    g.oil = OilField(9, g)
    f = g.oil
    f.levels.update({"ROCK BIT": 1, "DISPATCHER": 1, "TRUCK SPEED": 5})
    for pocket in oil_pockets(f)[:2]:
        try:
            i = f.place_rig(pocket.cells[0][0])
        except OilError:
            continue
        f.lay_pipe(*pocket.cells[0], i)
    assert f.rigs
    cash, events = g.cash, []
    for _ in range(4 * 60 * 30):                       # four minutes of digging (the pod just sits)
        g.step(1 / 30)
        events += g.pop_events()
    sells = [e for e in events if e[0] == "oil_sell"]
    assert sells and sum(e[1] for e in sells) == f.earned
    assert g.cash - cash >= f.earned                   # (plus any refunds from pipes that hit rock)
    assert g.earned >= f.earned                         # oil counts toward chips like ore does


def test_the_oil_field_screen(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.ui.deepdig_scene import DeepDigScene
    from ten_phases.ui.oil_scene import CELL, GROUND_Y, OilFieldScene
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    g = DeepDig(seed=6)
    g.cash = 10 ** 6
    dig = DeepDigScene(app, g)
    app.go(dig)
    dig.splash = None
    a, b = BUILDINGS["OIL"]
    g.x = (a + b + 1) / 2
    dig.update(1 / 30)
    dig.use_building()
    assert dig.panel == "OIL"
    dig.draw(app.screen)
    dig.panel_buttons[0].on_click()                     # buy the business
    assert g.oil is not None
    dig.panel_buttons[0].on_click()                     # go to the field
    scene = app.scene
    assert isinstance(scene, OilFieldScene)
    f = g.oil
    f.levels["ROCK BIT"] = 1

    def at(col, row=None):
        y = GROUND_Y - 40 if row is None else GROUND_Y + int((row + 0.5) * CELL)
        return (int((col + 0.5) * CELL - scene.cam), y)

    def click(pos):
        scene.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        scene.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))

    def key(k):
        scene.handle(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))

    pocket = oil_pockets(f)[0]
    c, r = pocket.cells[0]
    for rr in range(r):                                 # a clear way down (no gas to blow it up)
        if f.pocket_at.get((c, rr)) != pocket.id:
            f.tiles.pop((c, rr), None)
            f.pockets.pop(f.pocket_at.pop((c, rr), None), None)
    key(pygame.K_1)
    click(at(c, r))                                     # scan
    assert (c, r) in f.revealed
    key(pygame.K_2)
    click(at(c))                                        # build a rig
    assert f.rigs and scene.tool == "PIPE" and scene.sel_rig == 0
    scene.hover = at(c, r)
    scene.draw(app.screen)                              # the pipe's route and price show
    click(at(c, r))                                     # lay the pipe
    assert f.rigs[0].queue
    for _ in range(60 * 30):
        scene.update(1 / 30)
    assert f.rigs[0].tank > 0
    truck = scene._truck_rect(0)
    click(truck.center)                                 # pick the truck...
    assert scene.sel_truck == 0
    click(at(c))                                        # ...and send it to the rig
    assert f.trucks[0].goal == ("rig", 0)
    for _ in range(30 * 30):
        scene.update(1 / 30)
    click(scene._truck_rect(0).center)
    click(at(-3))                                       # then to ACME, on the left
    assert f.trucks[0].goal == ("buyer", "L")
    bank = app.settings.chip_bank
    for _ in range(60 * 30):
        scene.update(1 / 30)
    assert f.earned > 0 and app.settings.chip_bank >= bank
    scene.draw(app.screen)
    key(pygame.K_u)                                     # upgrades
    assert scene.panel
    scene.draw(app.screen)
    scene.panel_buttons[0].on_click()
    assert f.levels["PUMPS"] == 1
    key(pygame.K_ESCAPE)
    assert not scene.panel
    plots = f.plots
    key(pygame.K_l)                                     # buy land
    assert f.plots == plots + 1
    key(pygame.K_d)
    scene.update(0.5)
    scene.draw(app.screen)
    scene.sel_truck = None
    key(pygame.K_ESCAPE)                                # Esc lets go of the picked rig first...
    assert scene.sel_rig is None and app.scene is scene
    key(pygame.K_ESCAPE)                                # ...then goes back to town
    assert app.scene is dig


def test_the_oil_field_with_a_controller(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.ui.deepdig_scene import DeepDigScene
    from ten_phases.ui.oil_scene import CELL, GROUND_Y, OilFieldScene
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    g = DeepDig(seed=6)
    g.cash = 10 ** 6
    g.oil = OilField(3, g)
    scene = OilFieldScene(app, DeepDigScene(app, g))
    app.go(scene)
    pad = app.pad

    def tap(button):
        for kind in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP):
            for e in pad.translate(pygame.event.Event(kind, button=button, instance_id=0)):
                scene.handle(e)

    tool = scene.tool
    tap(pygame.CONTROLLER_BUTTON_RIGHTSHOULDER)          # RB: next tool
    assert scene.tool != tool
    while scene.tool != "RIG":
        tap(pygame.CONTROLLER_BUTTON_RIGHTSHOULDER)
    pad.cursor = [float((4 + 0.5) * CELL - scene.cam), float(GROUND_Y - 40)]
    tap(pygame.CONTROLLER_BUTTON_A)                     # A: build here
    assert g.oil.rigs and g.oil.rigs[0].col == 4
    tap(pygame.CONTROLLER_BUTTON_Y)                     # Y: upgrades
    assert scene.panel
    tap(pygame.CONTROLLER_BUTTON_B)                     # B: close
    assert not scene.panel
    tap(pygame.CONTROLLER_BUTTON_BACK)                  # BACK: pick a truck
    assert scene.sel_truck == 0
    pad.active = False
