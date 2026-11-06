"""A fake of Letterfield's shared survey (worker/src/survey.js) for game tests.

The game reads the survey's address from SURVEY_URL, or from ?survey=, so
tests point it at https://survey.test and answer its sector WebSockets here
with Playwright's route_web_socket, and its world map with route. The real
Sector and Atlas are tested in worker/test/survey.test.js.

stand_in_for_worker() in fake_leaderboard.py also answers the real Worker's
survey with an empty FakeSurvey, so loading Letterfield in any test never
reaches it.
"""

from __future__ import annotations

import base64
import json
import re

from playwright.sync_api import Route, WebSocketRoute

NOW_MS = 1_793_000_000_000
AREA, AREA_WORDS = 12, 1_120_206
SIZE = (2 * AREA + 1) * 4  # territories per side of the shared world


def world_map(charted=None, sectors=(), spawn=None, players=0):
    """A GET /v1/survey/world answer. `charted` maps (tx, ty) territories to counts."""
    data = bytearray(SIZE * SIZE)
    for (tx, ty), n in (charted or {}).items():
        data[(ty + AREA * 4) * SIZE + tx + AREA * 4] = n
    return {"charted": sum(data), "total": AREA_WORDS, "players": players, "area": AREA,
            "territories": base64.b64encode(bytes(data)).decode(), "sectors": list(sectors), "spawn": spawn}


class FakeSurvey:
    """Answers each sector's WebSocket the way worker/src/survey.js does."""

    def __init__(self, claims=(), presence=(), taken=(), world=None, totals=None, full=None):
        self.claims = list(claims)        # [w, x, y, d, s, initials, at] already charted in sector 0,0
        self.presence = list(presence)    # [id, initials, x, y] of other players in sector 0,0
        self.taken = {tuple(c[:4]): c for c in taken}  # words someone else charts first, just before us
        self.world = world or world_map()  # what GET /v1/survey/world answers
        self.totals = totals              # a {t: world} message each sector sends after hello
        self.full = full                  # "sector" or "world": every sector turns players away
        self.sectors: list[str] = []      # path of every connection
        self.received: list[dict] = []    # every message from the game
        self.sockets: dict[str, WebSocketRoute] = {}

    def handle(self, ws: WebSocketRoute) -> None:
        sector = re.search(r"/v1/survey/(-?\d+)/(-?\d+)$", ws.url)
        key = f"{sector[1]},{sector[2]}"
        self.sectors.append(key)
        self.sockets[key] = ws
        you = f"you-{key}"
        home = key == "0,0"
        if self.full:
            ws.send(json.dumps({"t": "full", "world": self.full == "world"}))
            return
        ws.send(json.dumps({"t": "hello", "you": you, "sector": [int(sector[1]), int(sector[2])],
                            "claims": self.claims if home else []}))
        if self.totals:
            ws.send(json.dumps({"t": "world", **self.totals}))
        if home and self.presence:
            ws.send(json.dumps({"t": "presence", "n": len(self.presence), "p": self.presence}))

        def on_message(text: str) -> None:
            msg = json.loads(text)
            self.received.append({**msg, "sector": key})
            if msg["t"] != "claim":
                return
            word = (msg["w"], msg["x"], msg["y"], msg["d"])
            if word in self.taken:
                ws.send(json.dumps({"t": "taken", "c": self.taken[word]}))
            else:
                ws.send(json.dumps({"t": "claimed", "c": [*word, 0, "ZED", NOW_MS], "by": you}))

        ws.on_message(on_message)

    def handle_world(self, route: Route) -> None:
        route.fulfill(json=self.world, headers={"Access-Control-Allow-Origin": "*"})

    def sent(self, kind: str) -> list[dict]:
        return [m for m in self.received if m["t"] == kind]
