"""Cards Against Humanity over the network.

Only the host has the card data. Each guest gets the text of their own hand, the
black card, and the answers once judging starts (without names until the Czar
picks). Pictures drawn on blank cards travel separately ("img" messages), once
per guest, and snapshots refer to them by id.
"""

from __future__ import annotations

import random

from ..cah.ai import CahAI
from ..cah.engine import (BlackCard, CahEvent, CahGame, CahOptions, CahPlayer, RuleError, Submission, WhiteCard,
                          Written, image_id)
from ..skins import clean_skin, player_skin
from .protocol import Connection
from .snapshot import rotate

GAME_NAME = "CAH"


def _sub_out(sub: Submission, viewer: int, n: int, named: bool) -> dict:
    cards = []
    for c in sub.cards:
        w = sub.written.get(c.id)
        cards.append({"text": sub.card_text(c), "blank": c.blank, "image": w.image_id if w else None})
    return {"id": sub.id, "player": rotate(sub.player, viewer, n) if named else None, "cards": cards}


def cah_snapshot_for(game: CahGame, viewer: int) -> dict:
    n = len(game.players)
    order = [(viewer + k) % n for k in range(n)]
    reveal = game.phase in ("results", "game_over")
    subs = []
    if game.phase in ("judging", "results", "game_over"):
        subs = [_sub_out(s, viewer, n, reveal) for s in game.order]
    mine = game.submissions.get(viewer)
    return {
        "round": game.round, "phase": game.phase, "game_over": game.game_over,
        "czar": rotate(game.czar, viewer, n), "target": game.options.points_to_win, "images": game.options.images,
        "packs": game.pack_names[:80], "deck": len(game.white_deck), "blacks": len(game.black_deck),
        "black": {"text": game.black.text, "pick": game.black.pick} if game.black else None,
        "winner": rotate(game.winner, viewer, n), "winning": game.winning.id if game.winning else None,
        "submissions": subs, "mine": _sub_out(mine, viewer, n, True) if mine else None,
        "players": [{
            "name": game.players[r].name, "human": game.players[r].is_human, "difficulty": game.players[r].difficulty,
            "points": game.players[r].points, "submitted": game.players[r].submitted,
            "count": len(game.players[r].hand), "skin": list(player_skin(game.players[r])),
            "hand": [[c.id, c.text, c.blank] for c in game.players[r].hand] if r == viewer else None,
        } for r in order],
    }


def images_in(game: CahGame, viewer: int) -> dict[str, str]:
    """Pictures a viewer can see right now: their own answer's, plus every answer's once judging starts."""
    subs = list(game.order) if game.phase in ("judging", "results", "game_over") else []
    if viewer in game.submissions:
        subs.append(game.submissions[viewer])
    return {w.image_id: w.image for s in subs for w in s.written.values() if w.image}


def cah_events_for(events: list[CahEvent], viewer: int, n: int) -> list[dict]:
    return [{"k": e.kind, "p": rotate(e.player, viewer, n), "a": e.amount, "x": e.text} for e in events]


class _Count:
    def __init__(self, n: int):
        self.n = n

    def __len__(self) -> int:
        return self.n


class RemoteCahGame:
    """Looks like a CahGame to the table screen; moves are sent to the host."""

    def __init__(self, send):
        self._send = send
        self.events: list[CahEvent] = []
        self.history: list[CahEvent] = []
        self.pending = False
        self.players: list[CahPlayer] = []
        self.images: dict[str, str] = {}
        self.round, self.phase, self.game_over = 0, "picking", False
        self.czar = 0
        self.options = CahOptions()
        self.pack_names: list[str] = []
        self.white_deck, self.black_deck = _Count(0), _Count(0)
        self.black: BlackCard | None = None
        self.winner = None
        self.winning: Submission | None = None
        self.order: list[Submission] = []
        self.submissions: dict[int, Submission] = {}

    def add_image(self, iid, data) -> None:
        if isinstance(iid, str) and isinstance(data, str) and len(data) <= 200_000 and image_id(data) == iid:
            self.images[iid] = data

    def _sub_in(self, d: dict) -> Submission:
        cards, written = [], {}
        for k, c in enumerate(d["cards"]):
            card = WhiteCard(c["text"], -(k + 1), bool(c["blank"]))
            cards.append(card)
            if card.blank:
                iid = c.get("image")
                written[card.id] = Written(c["text"], self.images.get(iid), iid)
        return Submission(d["id"], d["player"] if d["player"] is not None else -1, cards, written)

    def apply(self, snap: dict, events: list[dict]) -> None:
        self.round, self.phase, self.game_over = snap["round"], snap["phase"], snap["game_over"]
        self.czar = snap["czar"]
        self.options = CahOptions(packs=[], points_to_win=snap["target"], images=snap["images"])
        self.pack_names = list(snap["packs"])
        self.white_deck, self.black_deck = _Count(snap["deck"]), _Count(snap["blacks"])
        b = snap["black"]
        self.black = BlackCard(b["text"], b["pick"], -1) if b else None
        self.winner = snap["winner"]
        self.order = [self._sub_in(d) for d in snap["submissions"]]
        self.winning = next((s for s in self.order if s.id == snap["winning"]), None)
        players = []
        for d in snap["players"]:
            p = CahPlayer(d["name"], is_human=d["human"], difficulty=d["difficulty"])
            p.points, p.submitted = d["points"], d["submitted"]
            p.skin = clean_skin(d.get("skin"))
            p.hand = [WhiteCard(t, cid, bool(blank)) for cid, t, blank in d["hand"]] if d["hand"] is not None else \
                [WhiteCard("", -1) for _ in range(d["count"])]
            players.append(p)
        self.players = players
        self.submissions = {}
        if snap.get("mine"):
            self.submissions[0] = self._sub_in(snap["mine"])
        for e in events:
            ev = CahEvent(e["k"], player=e.get("p"), amount=e.get("a", 0), text=e.get("x", ""))
            self.events.append(ev)
            self.history.append(ev)
        del self.history[:-300]
        self.pending = False

    # ---------------------------------------------------------------- CahGame-like helpers

    def pop_events(self) -> list[CahEvent]:
        ev, self.events = self.events, []
        return ev

    def waiting_on(self) -> list[int]:
        return [k for k, p in enumerate(self.players) if k != self.czar and not p.submitted] \
            if self.phase == "picking" else []

    def standings(self) -> list[int]:
        return sorted(range(len(self.players)), key=lambda k: -self.players[k].points)

    def winners(self) -> list[int]:
        best = max(p.points for p in self.players)
        return [k for k, p in enumerate(self.players) if p.points == best]

    def _request(self, msg: dict):
        if self.pending:
            raise RuleError("Waiting for the host…")
        self.pending = True
        self._send({"t": "act", **msg})

    def submit(self, i: int, card_ids: list[int], written: dict | None = None) -> None:
        if self.phase != "picking" or self.czar == 0 or self.players[0].submitted:
            raise RuleError("You can't play cards right now.")
        if len(card_ids) != self.black.pick:
            raise RuleError(f"Pick {self.black.pick} card{'s' if self.black.pick > 1 else ''}.")
        self._request({"a": "submit", "cards": list(card_ids),
                       "written": {str(k): v for k, v in (written or {}).items()}})

    def judge(self, i: int, submission_id: int) -> None:
        if self.phase != "judging" or self.czar != 0:
            raise RuleError("Only the Card Czar picks the winner.")
        self._request({"a": "judge", "sid": submission_id})

    def next_round(self):
        raise RuleError("The host starts the next round.")


class HostCahSession:
    """A running networked game, seen from the host (same shape as HostSession)."""

    game_name = GAME_NAME

    def __init__(self, server, game: CahGame, ais: dict[int, CahAI]):
        self.server = server
        self.game = game
        self.ais = ais
        self.seat_of: dict[Connection, int] = {g: i + 1 for i, g in enumerate(server.guests)}
        self.sent = 0
        self.notices: list[str] = []
        self.sent_images: dict[Connection, set[str]] = {}

    def handle_action(self, conn: Connection, msg: dict):
        seat = self.seat_of.get(conn)
        if seat is None:
            return
        g = self.game
        try:
            a = msg.get("a")
            if a == "submit":
                cards, written = msg.get("cards"), msg.get("written") or {}
                if not isinstance(cards, list) or not isinstance(written, dict):
                    raise RuleError("Unknown move.")
                notes = {}
                for k, v in written.items():
                    try:
                        notes[int(k)] = v
                    except (TypeError, ValueError):
                        raise RuleError("Unknown move.") from None
                g.submit(seat, cards, notes)
            elif a == "judge":
                if not isinstance(msg.get("sid"), int):
                    raise RuleError("Unknown move.")
                g.judge(seat, msg["sid"])
            else:
                raise RuleError("Unknown move.")
        except RuleError as e:
            conn.send({"t": "error", "msg": str(e)})
            self.flush(force=True, only=conn)

    def player_left(self, conn: Connection):
        seat = self.seat_of.pop(conn, None)
        self.sent_images.pop(conn, None)
        if seat is None:
            return
        p = self.game.players[seat]
        p.is_human = False
        p.difficulty = "Medium"
        self.ais[seat] = CahAI("Medium")
        msg = f"{p.name} left. A computer took their seat."
        self.notices.append(msg)
        for g in self.seat_of:
            g.send({"t": "notice", "msg": msg})
        self.flush(force=True)

    def flush(self, force: bool = False, only: Connection | None = None):
        history = self.game.history
        if len(history) == self.sent and not force:
            return
        new = history[self.sent:]
        if only is None:
            self.sent = len(history)
        n = len(self.game.players)
        for conn, seat in self.seat_of.items():
            if only is not None and conn is not only:
                continue
            sent = self.sent_images.setdefault(conn, set())
            for iid, data in images_in(self.game, seat).items():
                if iid not in sent:
                    sent.add(iid)
                    conn.send({"t": "img", "id": iid, "data": data})
            events = [] if only is not None else cah_events_for(new, seat, n)
            conn.send({"t": "state", "s": cah_snapshot_for(self.game, seat), "e": events})


def start_cah(server, ai_names: list[str], levels: list[str], packs: list[dict], options: CahOptions) -> HostCahSession:
    """Build the table for a lobby: host, then guests, then computers."""
    players = [CahPlayer(server.name, is_human=True)]
    players += [CahPlayer(g.tag, is_human=True) for g in server.guests]
    ais = {}
    for name, level in zip(ai_names, levels):
        players.append(CahPlayer(name, difficulty=level))
        ais[len(players) - 1] = CahAI(level)
    return HostCahSession(server, CahGame(players, packs, options, random.Random()), ais)
