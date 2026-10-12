import random
import time

import pytest

from ten_phases.ai import AIPlayer
from ten_phases.net.client import ClientSession
from ten_phases.net.host import HostServer
from ten_phases.net.protocol import NetError, decode_invite, encode_invite


def test_invite_code_round_trip():
    for ip, port, key in [("192.168.1.20", 47610, 0xABCDEF), ("100.64.0.1", 1, 0), ("255.255.255.255", 65535, 0xFFFFFF)]:
        code = encode_invite(ip, port, key)
        assert len(code) == 17 and code.count("-") == 2
        assert decode_invite(code) == (ip, port, key)
        assert decode_invite(code.lower().replace("-", " ")) == (ip, port, key)


def test_bad_invite_code():
    with pytest.raises(NetError):
        decode_invite("hello")


def wait_for(cond, pump, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        pump()
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_full_networked_game_over_localhost():
    """A host and two guests play a whole game through real sockets, all driven by AI."""
    server = HostServer("HOSTY", port=0, announce=False)
    try:
        guests = [ClientSession(n, "127.0.0.1", server.port, server.key) for n in ("ANA", "BO")]

        def pump_all():
            server.pump()
            for c in guests:
                c.poll()
        assert wait_for(lambda: all(c.status == "joined" and len(c.members) == 3 for c in guests), pump_all)
        names = [m["name"] for m in guests[0].members]
        assert names[0] == "HOSTY" and sorted(names[1:]) == ["ANA", "BO"]  # join order can vary
        for c in guests:
            assert c.members[c.my_index]["name"] == c.name
        guests.sort(key=lambda c: c.my_index)  # guests[k] sits in seat k + 1

        server.set_ai_count(1)
        session = server.start_game(0)
        host_ai = AIPlayer("Medium", random.Random(1))
        guest_ai = [AIPlayer("Medium", random.Random(2 + k)) for k in range(2)]
        game = session.game
        assert wait_for(lambda: all(c.game and c.game.players for c in guests), pump_all)

        # Guests only ever see their own cards.
        for c in guests:
            mine = {x.id for x in c.game.players[0].hand}
            real_seat = 1 + guests.index(c)
            assert mine == {x.id for x in game.players[real_seat].hand}
            assert all(x.id == -1 for p in c.game.players[1:] for x in p.hand)

        steps = 0
        while not game.game_over and steps < 30000:
            steps += 1
            pump_all()
            if game.game_over:  # a guest's move can end the game during the pump
                break
            if game.round_over:
                game.next_round()
                continue
            seat = game.current
            if seat in session.ais or seat == 0:
                ai = session.ais.get(seat, host_ai)
                a = ai.next_action(game, seat)
                if a[0] == "draw":
                    (game.draw_from_deck if a[1] == "deck" else game.draw_from_discard)(seat)
                elif a[0] == "lay":
                    game.lay_down(seat, a[1])
                elif a[0] == "hit":
                    game.hit(seat, a[1], a[2])
                else:
                    game.discard(seat, a[1], a[2])
                continue
            c = guests[seat - 1]
            rg = c.game
            # Wait for this guest's view to catch up to the real game.
            if rg.pending or rg.current != 0 or rg.round != game.round:
                time.sleep(0.001)
                continue
            a = guest_ai[seat - 1].next_action(rg, 0)
            if a[0] == "draw":
                (rg.draw_from_deck if a[1] == "deck" else rg.draw_from_discard)(0)
            elif a[0] == "lay":
                rg.lay_down_auto(0, [x for grp in a[1] for x in grp])
            elif a[0] == "hit":
                rg.hit(0, a[1], a[2])
            else:
                rg.discard(0, a[1], a[2])
        assert game.game_over
        assert wait_for(lambda: all(c.game.game_over for c in guests), pump_all)
        for c in guests:
            assert c.game.players[0].phase == game.players[1 + guests.index(c)].phase
    finally:
        server.close()


def test_wrong_key_is_rejected_and_leaver_becomes_ai():
    server = HostServer("H", port=0, announce=False)
    try:
        bad = ClientSession("X", "127.0.0.1", server.port, server.key ^ 1)
        good = ClientSession("Y", "127.0.0.1", server.port, server.key)
        pump = lambda: (server.pump(), bad.poll(), good.poll())  # noqa: E731
        assert wait_for(lambda: bad.status == "failed" and good.status == "joined", pump)
        assert "out of date" in bad.error
        session = server.start_game(0)
        good.leave()
        assert wait_for(lambda: 1 in session.ais, pump)
        assert session.game.players[1].difficulty == "Medium"
    finally:
        server.close()


def test_computer_names_never_clash_with_people():
    server = HostServer("ZACH", port=0, announce=False)
    try:
        guest = ClientSession("RACHEL", "127.0.0.1", server.port, server.key)
        assert wait_for(lambda: guest.status == "joined", lambda: (server.pump(), guest.poll()))
        server.set_ai_count(4)
        session = server.start_game(0)
        names = [p.name for p in session.game.players]
        assert len(set(names)) == len(names) == 6
    finally:
        server.close()


def test_garbled_state_from_host_disconnects_cleanly():
    server = HostServer("H", port=0, announce=False)
    try:
        guest = ClientSession("G", "127.0.0.1", server.port, server.key)
        assert wait_for(lambda: guest.status == "joined", lambda: (server.pump(), guest.poll()))
        conn = server.guests[0]
        conn.send({"t": "start"})
        conn.send({"t": "state", "s": {"round": 1}, "e": []})
        assert wait_for(lambda: guest.status == "closed", lambda: (server.pump(), guest.poll()))
        assert "understand" in guest.error
    finally:
        server.close()


def test_full_go_fish_game_over_localhost():
    from ten_phases.gofish.ai import GoFishAI

    server = HostServer("HOSTY", port=0, announce=False, game="GO FISH")
    try:
        guests = [ClientSession(n, "127.0.0.1", server.port, server.key) for n in ("ANA", "BO")]

        def pump_all():
            server.pump()
            for c in guests:
                c.poll()
        assert wait_for(lambda: all(c.status == "joined" and len(c.members) == 3 for c in guests), pump_all)
        assert all(c.game_name == "GO FISH" for c in guests)
        guests.sort(key=lambda c: c.my_index)
        server.set_ai_count(1)
        session = server.start_game()
        game = session.game
        assert wait_for(lambda: all(c.game is not None and c.game.players for c in guests), pump_all)
        assert all(type(c.game).__name__ == "RemoteFishGame" for c in guests)
        host_ai = GoFishAI("Hard", random.Random(1))
        guest_ai = [GoFishAI("Hard", random.Random(2 + k)) for k in range(2)]

        hidden_ok = True
        steps = 0
        while not game.game_over and steps < 40000:
            steps += 1
            pump_all()
            for c in guests:  # nobody may see another player's cards
                if any(x.id != -1 for p in c.game.players[1:] for x in p.hand):
                    hidden_ok = False
            if game.game_over:
                break
            seat = game.current
            if seat == 0 or seat in session.ais:
                ai = session.ais.get(seat, host_ai)
                game.ask(seat, *ai.choose_ask(game, seat))
                continue
            c = guests[seat - 1]
            rg = c.game
            if rg.pending or rg.current != 0 or rg.game_over:
                time.sleep(0.001)
                continue
            target, value = guest_ai[seat - 1].choose_ask(rg, 0)
            rg.ask(0, target, value)
        assert game.game_over and game.books_made() == 12 and hidden_ok
        assert wait_for(lambda: all(c.game.game_over for c in guests), pump_all)
        for c in guests:
            seat = 1 + guests.index(c)
            assert c.game.players[0].books == game.players[seat].books
            assert c.game.books_made() == 12
    finally:
        server.close()


def test_full_blackjack_game_over_localhost():
    from ten_phases.blackjack.ai import BlackjackAI

    server = HostServer("HOSTY", port=0, announce=False, game="BLACKJACK")
    try:
        guests = [ClientSession(n, "127.0.0.1", server.port, server.key) for n in ("ANA", "BO")]

        def pump_all():
            server.pump()
            for c in guests:
                c.poll()
        assert wait_for(lambda: all(c.status == "joined" and len(c.members) == 3 for c in guests), pump_all)
        guests.sort(key=lambda c: c.my_index)
        server.set_ai_count(2)
        session = server.start_game()
        game = session.game
        assert wait_for(lambda: all(c.game is not None and c.game.players for c in guests), pump_all)
        assert all(type(c.game).__name__ == "RemoteBlackjackGame" for c in guests)
        host_ai = BlackjackAI("Hard", random.Random(1))
        guest_ai = [BlackjackAI("Hard", random.Random(2 + k)) for k in range(2)]
        hole_leaked = False
        for _ in range(60000):
            pump_all()
            for c in guests:
                rg = c.game
                if rg.hole_hidden and len(rg.dealer) > 1 and rg.dealer[1].id != -3:
                    hole_leaked = True
            if game.game_over:
                break
            if game.phase == "settled":
                game.next_round()
                continue
            if game.phase == "betting":
                for i in game.waiting_for_bets():
                    if i == 0 or i in session.ais:
                        game.place_bet(i, (session.ais.get(i) or host_ai).choose_bet(game, i))
                for k, c in enumerate(guests):
                    rg = c.game
                    if rg.phase == "betting" and 0 in rg.waiting_for_bets() and not rg.pending:
                        rg.place_bet(0, guest_ai[k].choose_bet(rg, 0))
                continue
            seat = game.turn[0]
            if seat == 0 or seat in session.ais:
                ai = session.ais.get(seat, host_ai)
                getattr(game, ai.choose_action(game, seat))(seat)
                continue
            rg = guests[seat - 1].game
            if rg.pending or not rg.legal_actions(0):
                time.sleep(0.001)
                continue
            getattr(rg, guest_ai[seat - 1].choose_action(rg, 0))(0)
        assert game.game_over and not hole_leaked
        assert wait_for(lambda: all(c.game.game_over for c in guests), pump_all)
        for c in guests:
            seat = 1 + guests.index(c)
            assert c.game.players[0].chips == game.players[seat].chips
    finally:
        server.close()


@pytest.mark.parametrize("game_name", ["10 PHASES", "GO FISH", "BLACKJACK"])
def test_everyone_sees_everyone_elses_skins(game_name):
    server = HostServer("HOSTY", port=0, announce=False, game=game_name, skin=("neon", "galaxy"))
    try:
        guests = [ClientSession("ANA", "127.0.0.1", server.port, server.key, skin=("koi", "f003")),
                  ClientSession("BO", "127.0.0.1", server.port, server.key, skin=("not-a-skin", 7))]

        def pump_all():
            server.pump()
            for c in guests:
                c.poll()
        assert wait_for(lambda: all(c.status == "joined" and len(c.members) == 3 for c in guests), pump_all)
        server.set_ai_count(1)
        session = server.start_game(0)
        assert wait_for(lambda: all(c.game and c.game.players for c in guests), pump_all)
        real = {p.name: tuple(p.skin) for p in session.game.players}
        assert real["HOSTY"] == ("neon", "galaxy")
        assert real["ANA"] == ("koi", "f003")
        assert real["BO"] == ("classic", "classic")      # junk from the wire is cleaned up
        for c in guests:
            seen = {p.name: tuple(p.skin) for p in c.game.players}
            assert seen == real                          # including the computer's random pick
    finally:
        server.close()


def test_malformed_moves_never_crash_the_host():
    server = HostServer("H", port=0, announce=False)
    try:
        guest = ClientSession("G", "127.0.0.1", server.port, server.key)

        def pump_all():
            server.pump()
            guest.poll()
        assert wait_for(lambda: guest.status == "joined", pump_all)
        session = server.start_game(0)
        assert wait_for(lambda: guest.game and guest.game.players, pump_all)
        session.game.current = 1   # the guest's turn
        bad = [{"a": "lay", "cards": 5}, {"a": "hit", "card": [1]}, {"a": "discard", "card": {"x": 1}},
               {"a": "hit", "card": 3, "meld": "x"}, {"a": 42}, {"a": "lay", "cards": [None, "x"]}]
        for msg in bad:
            guest.send({"t": "act", **msg})
        errors = []
        assert wait_for(lambda: len(errors) >= len(bad),
                        lambda: (server.pump(), errors.extend(m for m in guest.poll() if m["t"] == "error")))
    finally:
        server.close()
