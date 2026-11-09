"""A fake of War rooms (worker/src/war.js) for game tests.

war.html reads the server's URL from ?rooms=, so tests point it at
https://leaderboard.test: page.route answers its HTTP requests and
page.route_web_socket stands in for the room's WebSocket. The fake runs the
lobby the way the real room does (players, host, bots, length, dealing) and
passes slams, cheers, deck changes and clean-ups on; the battles themselves are up to each test,
which sends the room's messages with broadcast(). The real room is tested in
worker/test/war.test.js.

Picking up winnings (`gather`) is passed on as the room would, and the host's
`shuffle` setting kept; which cards are where is up to each test's messages.

A slow room (the host's `slow` setting) has no clock. The fake passes nudges
on to whoever hasn't slammed this stage, and lets the host flip their cards
over, without the real room's waits.

The real room says which card each slam turns face up. The fake only does
for the seats a test puts in `ups` (seat -> card), in slams and in the bots'
slams when a stage opens; for the rest it sends none, as a room server from
before cards showed early would.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from playwright.sync_api import Page, Route, WebSocketRoute

from fake_leaderboard import API

ROOM_PATH = re.compile(r"^/v1/war/rooms/([^/]+)$")


def card(rank: int, suit: int = 0) -> int:
    """A card as the room numbers them: rank 0 is a two, 12 an ace."""
    return suit * 13 + rank


def joker(which: int = 0) -> int:
    """One of the deck's two jokers, which beat every other card."""
    return 52 + which


class FakeWarRoom:
    def __init__(self, code: str = "K7QP", exists: bool = True):
        self.code = code
        self.rooms = {code} if exists else set()
        self.phase = "lobby"
        self.length = "standard"
        self.slow = False
        self.shuffle = False
        self.slammed: set[int] = set()  # seats that slammed this stage
        self.players: list[dict] = []    # {name, avatar, deck, bot, token}
        self.sockets: list[dict] = []    # {ws, token, open}
        self.received: list[dict] = []   # every message from a page
        self.game: dict | None = None
        self.ups: dict[int, int] = {}    # seat -> the card its slam turns face up

    def route(self, page: Page) -> None:
        page.route(f"{API}/**", self.handle_http)
        page.route_web_socket(re.compile(r"^wss://leaderboard\.test/v1/war/rooms/"), self.handle_ws)

    # ---- HTTP ----

    def handle_http(self, route: Route) -> None:
        request = route.request
        path = urlparse(request.url).path

        def reply(status: int, body: dict) -> None:
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            route.fulfill(status=status, headers=headers, body=json.dumps(body))

        found = ROOM_PATH.match(path)
        if path == "/v1/war/rooms" and request.method == "POST":
            self.rooms.add(self.code)
            reply(201, {"code": self.code})
        elif found and request.method == "GET":
            if found[1] in self.rooms:
                reply(200, {"code": found[1], "phase": self.phase, "players": len(self.players), "full": False})
            else:
                reply(404, {"error": "unknown room"})
        else:
            reply(404, {"error": "not found"})

    # ---- WebSocket ----

    def handle_ws(self, ws: WebSocketRoute) -> None:
        conn = {"ws": ws, "token": None, "open": True}
        self.sockets.append(conn)
        ws.on_message(lambda message: self.on_message(conn, message))
        ws.on_close(lambda code, reason: self.on_close(conn))

    def on_close(self, conn: dict) -> None:
        conn["open"] = False
        if self.phase != "playing":
            self.send_states()

    def open_sockets(self) -> list[dict]:
        return [c for c in self.sockets if c["open"]]

    def seat_of(self, conn: dict):
        for seat, p in enumerate(self.players):
            if p["token"] and p["token"] == conn["token"]:
                return seat
        return None

    def online(self) -> set[int]:
        return {s for s in (self.seat_of(c) for c in self.open_sockets()) if s is not None}

    def host(self):
        online = self.online()
        return next((seat for seat, p in enumerate(self.players) if not p["bot"] and seat in online), None)

    def snapshot(self, conn: dict) -> dict:
        online = self.online()
        return {
            "t": "state", "code": self.code, "phase": self.phase, "length": self.length, "slow": self.slow,
            "shuffle": self.shuffle,
            "you": self.seat_of(conn), "host": self.host(),
            "watchers": sum(1 for c in self.open_sockets() if self.seat_of(c) is None),
            "players": [
                {"name": p["name"], "avatar": p["avatar"], "deck": p.get("deck"), "bot": p["bot"], "online": p["bot"] or seat in online}
                for seat, p in enumerate(self.players)
            ],
            "game": self.game,
        }

    def send(self, conn: dict, message: dict) -> None:
        if conn["open"]:
            conn["ws"].send(json.dumps(message))

    def send_states(self) -> None:
        for conn in self.open_sockets():
            self.send(conn, self.snapshot(conn))

    def broadcast(self, message: dict) -> None:
        for conn in self.open_sockets():
            self.send(conn, message)

    def messages(self, kind: str) -> list[dict]:
        return [m for m in self.received if m.get("t") == kind]

    def on_message(self, conn: dict, text) -> None:
        message = json.loads(text)
        self.received.append(message)
        kind = message.get("t")
        seat = self.seat_of(conn)
        is_host = seat is not None and seat == self.host()
        if kind == "hello":
            conn["token"] = message["token"]
            seat = self.seat_of(conn)
            if seat is None and self.phase == "lobby":
                self.players.append({
                    "name": message["name"], "avatar": message["avatar"], "deck": message.get("deck"),
                    "bot": False, "token": message["token"],
                })
            elif seat is not None:
                self.players[seat]["deck"] = message.get("deck")
            self.send_states()
        elif kind == "leave":
            if seat is not None and self.phase == "lobby":
                self.players.pop(seat)
            conn["open"] = False
            self.send_states()
        elif kind == "bots" and is_host:
            humans = [p for p in self.players if not p["bot"]]
            bots = [{"name": f"Bot {i + 1}", "avatar": 23, "bot": True, "token": None} for i in range(message["n"])]
            self.players = humans + bots
            self.send_states()
        elif kind == "length" and is_host:
            self.length = message["length"]
            self.send_states()
        elif kind == "slow" and is_host and self.phase != "playing":
            self.slow = message["slow"]
            self.send_states()
        elif kind == "shuffle" and is_host and self.phase != "playing":
            self.shuffle = message["shuffle"]
            self.send_states()
        elif kind == "gather" and seat is not None and self.phase == "playing":
            self.broadcast({"t": "gather", "seat": seat})
        elif kind == "nudge" and self.slow and self.phase == "playing":
            seats = [s for s in self.waiting() if s != seat]
            if seats:
                self.broadcast({"t": "nudge", "seats": seats, "by": seat})
        elif kind == "flop" and is_host and self.slow and self.phase == "playing":
            for s in self.waiting():
                if s != seat:
                    self.slammed.add(s)
                    up = {"up": self.ups[s]} if s in self.ups else {}
                    self.broadcast({"t": "slam", "seat": s, "power": 0, "style": 0, **up, "flopped": True})
        elif kind == "start" and is_host:
            self.deal()
        elif kind in ("slam", "charge", "card") and seat is not None:
            relayed = {"t": kind, "seat": seat, **{k: v for k, v in message.items() if k != "t"}}
            if kind == "slam" and seat in self.ups:
                relayed["up"] = self.ups[seat]
            if kind == "slam":
                self.slammed.add(seat)
            self.broadcast(relayed)
        elif kind == "cheer":
            self.broadcast({"t": "cheer", "seat": seat, "e": message["e"]})
        elif kind == "deck" and seat is not None:
            self.players[seat]["deck"] = message["deck"]
            self.broadcast({"t": "deck", "seat": seat, "deck": message["deck"]})
        elif kind == "tidy" and seat is not None:
            self.broadcast({"t": "tidy", "seat": seat})

    def waiting(self) -> list[int]:
        """The players this stage waits for: online, not bots, not slammed."""
        online = self.online()
        fighters = self.game["fighters"] if self.game else []
        return [s for s in fighters if not self.players[s]["bot"] and s in online and s not in self.slammed]

    def deal(self) -> None:
        """Starts a game, with everyone holding 27 cards and the first battle open."""
        n = len(self.players)
        limit = {"quick": 20, "standard": 60, "long": 150, "total": 5000}[self.length]
        self.phase = "playing"
        self.game = {
            "battle": 1, "limit": limit, "stage": 0, "fighters": list(range(n)), "counts": [27] * n,
            "out": [0] * n, "pot": 0, "slams": {}, "opensIn": 0, "closesIn": None if self.slow else 8000,
            "naps": [0] * n, "slow": self.slow, "wars": 0, "over": None,
        }
        self.slammed = set()
        self.send_states()
        self.broadcast(self.stage(1))

    def stage(self, battle: int, stage: int = 0, fighters=None, opens_in: int = 0) -> dict:
        fighters = list(range(len(self.players))) if fighters is None else fighters
        self.slammed = set()
        self.game.update(battle=battle, stage=stage, fighters=fighters)
        bots = [[seat, 100, 1, 200, *([self.ups[seat]] if seat in self.ups else [])]
                for seat in fighters if self.players[seat]["bot"]]
        return {
            "t": "stage", "battle": battle, "stage": stage, "limit": self.game["limit"], "fighters": fighters,
            "opensIn": opens_in, "closesIn": None if self.slow else opens_in + 8000, "bots": bots,
        }
