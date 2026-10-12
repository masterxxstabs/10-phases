"""Cards Against Humanity: card data, rules, computers, and a networked game with a picture on a blank card."""

import base64
import random
import time

import pytest

from ten_phases.cah import cards as cc
from ten_phases.cah.ai import CahAI
from ten_phases.cah.engine import CahGame, CahOptions, CahPlayer, RuleError


def fake_packs(n_packs: int = 3, whites: int = 60, blacks: int = 20) -> list[dict]:
    """Made-up packs in the API's GraphQL shape (no real card text in the tests)."""
    return [{"id": p, "name": f"Pack {p}",
             "white": [{"text": f"Answer {p}-{k}."} for k in range(whites)],
             "black": [{"text": f"Question {p}-{k}: _" + (" and _" if k % 4 == 0 else ""), "pick": 2 if k % 4 == 0
                        else 1} for k in range(blacks)]} for p in range(n_packs)]


PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da6364f8cf00000301010018dd8db00000000049454e44ae426082")).decode()


def test_normalize_accepts_graphql_rest_and_skips_junk():
    gql = {"data": {"packs": fake_packs(2)}}
    packs = cc.normalize(gql)
    assert [p["name"] for p in packs] == ["Pack 0", "Pack 1"]
    assert packs[0]["white"][0] == "Answer 0-0." and packs[0]["black"][0]["pick"] == 2
    rest = [{"name": "R", "white": ["plain text", {"text": "dict"}], "black": [{"text": "Q _?", "pick": 9}]}, 5,
            {"name": 3}]
    packs = cc.normalize(rest)
    assert len(packs) == 1 and packs[0]["white"] == ["plain text", "dict"] and packs[0]["black"][0]["pick"] == 1
    with pytest.raises(cc.CardDataError):
        cc.normalize({"errors": ["nope"]})


def test_fetch_tries_graphql_then_rest(monkeypatch):
    calls = []

    def fake_request(url, body=None, timeout=20.0):
        calls.append(url)
        if body is not None:
            raise OSError("graphql down")
        if url.endswith("/packs"):
            return ["Only Pack"]
        return {"white": [{"text": "W1"}, {"text": "W2"}], "black": [{"text": "B _", "pick": 1}]}
    monkeypatch.setattr(cc, "_request", fake_request)
    packs = cc.fetch_packs()
    assert packs[0]["name"] == "Only Pack" and packs[0]["white"] == ["W1", "W2"]
    assert calls[0] == cc.GQL_URLS[0]   # the API the owner picked is tried first


def test_cache_round_trip(tmp_path):
    path = tmp_path / "cards.json"
    cc.save_cache(cc.normalize(fake_packs(2)), path)
    assert cc.load_cache(path)[1]["name"] == "Pack 1"
    path.write_text("not json")
    assert cc.load_cache(path) is None


def make_game(n=4, **opts) -> CahGame:
    packs = cc.normalize(fake_packs())
    players = [CahPlayer(f"P{k}", is_human=k == 0, difficulty=None if k == 0 else "Medium") for k in range(n)]
    return CahGame(players, packs, CahOptions(**opts), random.Random(1))


def test_options_build_the_deck():
    g = make_game(packs=[1], blanks=7)
    assert g.pack_names == ["Pack 1"]
    everything = g.white_deck + [c for p in g.players for c in p.hand]
    assert sum(c.blank for c in everything) == 7
    assert all(c.blank or c.text.startswith("Answer 1-") for c in everything)
    with pytest.raises(ValueError):
        CahGame([CahPlayer("A"), CahPlayer("B")], cc.normalize(fake_packs()))   # needs 3 players


def test_a_round_with_a_blank_card_and_a_picture():
    g = make_game(blanks=0)
    czar = g.czar
    answerers = g.players_to_answer()
    me = answerers[0]
    blank = g._white("", blank=True)
    g.players[me].hand[0] = blank
    pick = g.black.pick
    with pytest.raises(RuleError):
        g.submit(czar, [c.id for c in g.players[czar].hand[:pick]])        # the Czar doesn't answer
    with pytest.raises(RuleError):
        g.submit(me, [c.id for c in g.players[me].hand[:pick + 1]])        # wrong number of cards
    ids = [blank.id] + [c.id for c in g.players[me].hand[1:pick]]
    with pytest.raises(RuleError):
        g.submit(me, ids, {blank.id: {"text": "   "}})                     # a blank needs words or a picture
    with pytest.raises(RuleError):
        g.submit(me, ids, {blank.id: {"text": "x", "image": "!!notbase64!!"}})
    g.submit(me, ids, {blank.id: {"text": "My own answer", "image": PNG}})
    assert len(g.players[me].hand) == 10 - pick
    for k in answerers[1:]:
        g.submit(k, [c.id for c in g.players[k].hand[:pick]])
    assert g.phase == "judging" and len(g.order) == len(answerers)
    mine = next(s for s in g.order if s.player == me)
    assert mine.card_text(blank) == "My own answer" and mine.written[blank.id].image == PNG
    with pytest.raises(RuleError):
        g.judge(me, mine.id)                                               # only the Czar judges
    g.judge(czar, mine.id)
    assert g.players[me].points == 1 and g.phase == "results"
    g.next_round()
    assert all(len(p.hand) == 10 for p in g.players) and g.czar == (czar + 1) % 4


def test_pictures_can_be_turned_off():
    g = make_game(images=False)
    me = g.players_to_answer()[0]
    blank = g._white("", blank=True)
    g.players[me].hand[0] = blank
    ids = [blank.id] + [c.id for c in g.players[me].hand[1:g.black.pick]]
    with pytest.raises(RuleError, match="turned off"):
        g.submit(me, ids, {blank.id: {"text": "hi", "image": PNG}})


@pytest.mark.parametrize("seed", range(20))
def test_computer_games_finish(seed):
    rng = random.Random(seed)
    n = rng.randint(3, 6)
    g = CahGame([CahPlayer(f"P{k}", difficulty=rng.choice(["Easy", "Medium", "Hard", "Expert"])) for k in range(n)],
                cc.normalize(fake_packs()), CahOptions(packs=[0, 1, 2], blanks=rng.randint(0, 40),
                                                       points_to_win=rng.choice([3, 5])), random.Random(seed))
    ais = [CahAI(p.difficulty, random.Random(k)) for k, p in enumerate(g.players)]
    for _ in range(5000):
        if g.game_over:
            break
        if g.phase == "picking":
            for k in g.waiting_on():
                g.submit(k, *ais[k].choose_cards(g, k))
        elif g.phase == "judging":
            g.judge(g.czar, ais[g.czar].choose_winner(g, g.czar))
        else:
            g.next_round()
    assert g.game_over
    assert max(p.points for p in g.players) >= 3 or not g.black_deck


def test_networked_game_with_pictures(app):
    from ten_phases.net.client import ClientSession
    from ten_phases.net.host import HostServer
    from ten_phases.net.protocol import NetError

    server = HostServer("HOSTY", port=0, announce=False, game="CAH")
    try:
        guests = [ClientSession(n, "127.0.0.1", server.port, server.key) for n in ("ANA", "BO")]

        errors = []

        def pump_all():
            server.pump()
            for c in guests:
                errors.extend(m.get("msg") for m in c.poll() if m.get("t") == "error")
        end = time.monotonic() + 5
        while not all(c.status == "joined" and len(c.members) == 3 for c in guests) and time.monotonic() < end:
            pump_all()
            time.sleep(0.01)
        guests.sort(key=lambda c: c.my_index)
        with pytest.raises(NetError, match="card packs"):
            server.start_game()
        server.in_game = False
        server.cah = (cc.normalize(fake_packs()), CahOptions(packs=[0, 1], blanks=0, points_to_win=3))
        session = server.start_game()
        game = session.game
        end = time.monotonic() + 5
        while not all(c.game and c.game.players for c in guests) and time.monotonic() < end:
            pump_all()
            time.sleep(0.01)
        assert all(type(c.game).__name__ == "RemoteCahGame" for c in guests)
        # Nobody sees anyone else's hand.
        for c in guests:
            assert all(card.id == -1 for p in c.game.players[1:] for card in p.hand)
        ais = {k: CahAI("Medium", random.Random(k)) for k in range(3)}
        pictured = False
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            pump_all()
            if game.game_over:
                break
            if game.phase == "results":
                game.next_round()
                continue
            if game.phase == "picking":
                for k in game.waiting_on():
                    if k == 0:
                        game.submit(0, *ais[0].choose_cards(game, 0))
                    else:
                        rg = guests[k - 1].game
                        if rg.pending or rg.round != game.round or rg.phase != "picking" or rg.players[0].submitted \
                                or rg.czar == 0:
                            continue
                        ids = [c.id for c in rg.players[0].hand[:rg.black.pick]]
                        written = {}
                        if k == 1 and not pictured:
                            # Turn ANA's first card into a blank with a picture (as the host could via admin).
                            real = game.players[1].hand
                            target = next(c for c in real if c.id == ids[0])
                            target.blank = True
                            written = {ids[0]: {"text": "drawn by ANA", "image": PNG}}
                            pictured = True
                        rg.submit(0, ids, written)
                time.sleep(0.001)
                continue
            if game.phase == "judging":
                if game.czar == 0:
                    game.judge(0, ais[0].choose_winner(game, 0))
                else:
                    rg = guests[game.czar - 1].game
                    if rg.phase == "judging" and rg.round == game.round and not rg.pending and rg.czar == 0:
                        rg.judge(0, rg.order[0].id)
                    time.sleep(0.001)
        assert game.game_over and pictured, (game.phase, game.round, errors[-5:])
        end = time.monotonic() + 5
        while not all(c.game.game_over for c in guests) and time.monotonic() < end:
            pump_all()
            time.sleep(0.01)
        # The other guest received ANA's picture once judging started.
        assert any(cc_data == PNG for cc_data in guests[1].game.images.values())
        for c in guests:
            seat = 1 + guests.index(c)
            assert c.game.players[0].points == game.players[seat].points
        guests[0].send({"t": "act", "a": "submit", "cards": "lots", "written": []})
        guests[0].send({"t": "act", "a": "judge", "sid": "x"})
        pump_all()
    finally:
        server.close()


def test_table_and_setup_screens(app, monkeypatch):
    import pygame

    from ten_phases.ui.cah_scene import CahScene
    from ten_phases.ui.cah_setup import CahSetupScene

    lib = cc.CardLibrary(fetch=lambda: cc.normalize(fake_packs()))
    lib.packs, lib.status = cc.normalize(fake_packs()), "ready"
    monkeypatch.setattr(cc, "_library", lib)
    app.settings.cah_packs, app.settings.cah_blanks = [0], 3
    app.go(CahSetupScene(app))
    setup = app.scene
    setup._toggle(1)
    assert app.settings.cah_packs == [0, 1]
    setup._blanks(100)
    assert app.settings.cah_blanks == 60
    setup._blanks(-57)
    setup.draw(app.screen)
    setup._go()
    scene = app.scene
    assert isinstance(scene, CahScene)
    scene.splash = None
    app.settings.ai_speed = "Fast"
    played = judged = False
    for _ in range(60 * 240):
        scene.update(1 / 60)
        scene.draw(app.screen)
        if scene.overlay == "game":
            break
        if scene.can_play():
            hand = scene.me.hand
            blank = next((c for c in hand if c.blank), None)
            if blank is not None and not played:
                scene.click_hand(blank)
                assert scene.editor is not None
                scene.editor.text.value = "typed on a blank"
                scene.editor._ok()
            for c in hand:
                if len(scene.selected) < scene.game.black.pick and c.id not in scene.selected and not c.blank:
                    scene.click_hand(c)
            scene.submit()
            played = True
        if scene.can_judge():
            scene.pick_sub = scene.game.order[0].id
            scene.judge()
            judged = True
        if scene.game.phase == "results":
            scene.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" "))
    assert played and scene.overlay == "game"
    assert judged or all(scene.game.czar != 0 for _ in [0])
