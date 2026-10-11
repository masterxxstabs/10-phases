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
