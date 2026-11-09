"""A fake of Letterfield's shared survey (worker/src/survey.js) for game tests.

The game reads the survey's address from SURVEY_URL, or from ?survey=, so
tests point it at https://survey.test and answer its sector WebSockets here
with Playwright's route_web_socket, and its world map with route. The real
Sector and Atlas are tested in worker/test/survey.test.js.

It also fakes Turnstile (worker/TURNSTILE.md): Cloudflare's widget script
and the Worker's POST /v1/survey/pass.

stand_in_for_worker() in fake_leaderboard.py also answers the real Worker's
survey with an empty FakeSurvey, and its Turnstile check with these fakes, so
loading Letterfield in any test never reaches either.
"""

from __future__ import annotations

import base64
import json
import re
import time

from playwright.sync_api import Route, WebSocketRoute

NOW_MS = 1_793_000_000_000
AREA, AREA_WORDS = 12, 1_119_752
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

    def __init__(self, claims=(), presence=(), taken=(), world=None, totals=None, full=None, refuse=None, refuse_passes=(), require_pass=False):
        self.claims = list(claims)        # [w, x, y, d, s, initials, at] already charted in sector 0,0
        self.presence = list(presence)    # [id, initials, x, y] of other players in sector 0,0
        self.taken = {tuple(c[:4]): c for c in taken}  # words someone else charts first, just before us
        self.world = world or world_map()  # what GET /v1/survey/world answers
        self.totals = totals              # a {t: world} message each sector sends after hello
        self.full = full                  # "sector" or "world": every sector turns players away
        self.refuse = refuse              # "slow down" or "daily limit": every claim is refused with it
        self.refuse_passes = set(refuse_passes)  # survey passes the Worker turns away, as expired or another address's
        self.require_pass = require_pass  # joins without a pass are turned away, as with TURNSTILE_REQUIRED = "true"
        self.urls: list[str] = []         # the URL of every connection
        self.sectors: list[str] = []      # path of every connection
        self.received: list[dict] = []    # every message from the game
        self.sockets: dict[str, WebSocketRoute] = {}

    def handle(self, ws: WebSocketRoute) -> None:
        sector = re.search(r"/v1/survey/(-?\d+)/(-?\d+)(?:\?pass=([^&]*))?$", ws.url)
        key = f"{sector[1]},{sector[2]}"
        self.urls.append(ws.url)
        if (sector[3] is None and self.require_pass) or (sector[3] is not None and sector[3] in self.refuse_passes):
            ws.send(json.dumps({"t": "unverified"}))  # the game closes it, as the Worker's close would
            return
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
            if self.refuse:
                word_key = f"{msg['w']}~{msg['x']}~{msg['y']}~{msg['d']}"
                ws.send(json.dumps({"t": "error", "key": word_key, "error": self.refuse}))
            elif word in self.taken:
                ws.send(json.dumps({"t": "taken", "c": self.taken[word]}))
            else:
                ws.send(json.dumps({"t": "claimed", "c": [*word, 0, "ZED", NOW_MS], "by": you}))

        ws.on_message(on_message)

    def handle_world(self, route: Route) -> None:
        route.fulfill(json=self.world, headers={"Access-Control-Allow-Origin": "*"})

    def sent(self, kind: str) -> list[dict]:
        return [m for m in self.received if m["t"] == kind]

# ---------- Turnstile (worker/TURNSTILE.md) ----------
# challenges.cloudflare.com is never reached: its script is answered with a
# fake `turnstile` that hands out Cloudflare's documented dummy token, and
# POST /v1/survey/pass with FakePassDesk.

DUMMY_TOKEN = "XXXX.DUMMY.TOKEN.XXXX"
TURNSTILE_JS = "https://challenges.cloudflare.com/turnstile/v0/api.js*"
FAKE_TURNSTILE = """
(() => {
  const mode = window.__tsMode || 'pass';  // 'pass', 'interactive' or 'fail'
  window.__tsRenders = window.__tsRenders || [];
  window.turnstile = {
    render(el, o) {
      window.__tsRenders.push({ el, sitekey: o.sitekey, action: o.action, appearance: o.appearance });
      if (mode === 'fail') setTimeout(() => o['error-callback']('600010'), 10);
      else if (mode === 'interactive') {
        setTimeout(() => o['before-interactive-callback'](), 10);
        window.__tsSolve = () => { o['after-interactive-callback'](); o.callback('%s'); };
      } else setTimeout(() => o.callback('%s'), 10);
      return 'w' + window.__tsRenders.length;
    },
    remove() {}, reset() {},
  };
  const onload = new URL(document.currentScript.src).searchParams.get('onload');
  window[onload]();
})();
""" % (DUMMY_TOKEN, DUMMY_TOKEN)


class FakePassDesk:
    """POST /v1/survey/pass, as worker/src/survey-pass.js answers it."""

    def __init__(self, status=200):
        self.status = status
        self.tokens: list[str] = []
        self.issued: list[str] = []

    def handle(self, route: Route) -> None:
        self.tokens.append(json.loads(route.request.post_data)["token"])
        cors = {"Access-Control-Allow-Origin": "*"}
        if self.status != 200:
            route.fulfill(status=self.status, json={"error": "not verified", "codes": []}, headers=cors)
            return
        pass_ = f"{NOW_MS + 3_600_000 + len(self.issued)}.pass{len(self.issued)}"
        self.issued.append(pass_)
        route.fulfill(json={"pass": pass_, "expires": int(time.time() * 1000) + 3_600_000}, headers=cors)
