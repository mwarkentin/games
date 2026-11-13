"""A fake of Letterfield's shared survey (worker/src/survey.js) for game tests.

The game reads the survey's address from SURVEY_URL, or from ?survey=, so
tests point it at https://survey.test and answer its sector WebSockets here
with Playwright's route_web_socket, and its world map with route. The real
Sector and Atlas are tested in worker/test/survey.test.js.

It also fakes the surveyor list (GET /v1/survey/surveyors) and emotes:
`surveyors` is everyone the list names, `emote()` sends the game one, and
the emotes the game sends are answered as `emote_error` says.

FakeGuilds answers the guilds' paths (/v1/survey/guilds...), and `guild()`
sends a sector's word of which of a guild are online.

FakeLinks answers the paths for linking another device (/v1/link...),
FakePlayers the ones that keep linked devices in step (/v1/player/...), and
FakeRecovery the recovery codes' (/v1/recovery...); the real ones are tested
in worker/test/players.test.js.

It also fakes Turnstile (worker/TURNSTILE.md): Cloudflare's widget script
and the Worker's POST /v1/survey/pass.

stand_in_for_worker() in fake_leaderboard.py also answers the real Worker's
survey with an empty FakeSurvey, and its Turnstile check with these fakes, so
loading Letterfield in any test never reaches either.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from urllib.parse import parse_qs, urlparse

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

    def __init__(self, claims=(), presence=(), taken=(), world=None, totals=None, full=None, refuse=None, refuse_passes=(),
                 require_pass=False, hold=None, lose=None, rate=False, surveyors=(), emote_error=None, list_status=200):
        self.claims = list(claims)        # [w, x, y, d, s, initials, at] already charted in sector 0,0
        self.presence = list(presence)    # [id, initials, x, y] of other players in sector 0,0
        self.taken = {tuple(c[:4]): c for c in taken}  # words someone else charts first, just before us
        self.world = world or world_map()  # what GET /v1/survey/world answers
        self.totals = totals              # a {t: world} message each sector sends after hello
        self.full = full                  # "sector" or "world": every sector turns players away
        self.refuse = refuse              # "slow down" or "daily limit": every claim is refused with it
        self.refuse_passes = set(refuse_passes)  # survey passes the Worker turns away, as expired or another address's
        self.require_pass = require_pass  # joins without a pass are turned away, as with TURNSTILE_REQUIRED = "true"
        self.hold = hold                  # a test of a socket's URL: those wait, unanswered, for welcome()
        self.lose = lose                  # "answer": the sector keeps each claim but its answer is lost; "claim": the claim is,
                                          # as when the socket drops with it on the way
        self.rate = rate                  # claims are limited per socket, as the sector's CLAIM_BURST and CLAIM_REFILL_MS
        self.surveyors = list(surveyors)  # [pid, initials, rx, ry, idle, flags] everyone the list names, nearest first
        self.emote_error = emote_error    # why every emote the game sends is refused ('gone', 'slow down'...), or None
        self.list_status = list_status    # what GET /v1/survey/surveyors answers with
        self.list_asks: list[dict] = []   # the query of every request for the list
        self.held: list[WebSocketRoute] = []
        self.urls: list[str] = []         # the URL of every connection
        self.sectors: list[str] = []      # path of every connection
        self.received: list[dict] = []    # every message from the game
        self.sockets: dict[str, WebSocketRoute] = {}

    def handle(self, ws: WebSocketRoute) -> None:
        if self.hold and self.hold(ws.url):
            self.held.append(ws)  # open, as far as the game can tell, but nothing comes back yet
            return
        self.welcome(ws)

    def welcome(self, ws: WebSocketRoute | None = None) -> None:
        """Answers a socket as the sector would: `ws`, or every one being held."""
        if ws is None:
            while self.held:
                self.welcome(self.held.pop(0))
            return
        sector = re.search(r"/v1/survey/(-?\d+)/(-?\d+)(?:\?pass=([^&]*))?$", ws.url)
        key = f"{sector[1]},{sector[2]}"
        self.urls.append(ws.url)
        if (sector[3] is None and self.require_pass) or (sector[3] is not None and sector[3] in self.refuse_passes):
            ws.send(json.dumps({"t": "unverified"}))  # the game closes it, as the Worker's close would
            return
        self.sectors.append(key)
        self.sockets[key] = ws
        you = f"you-{key}-{len(self.sectors)}"  # every socket is someone new to the sector
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
        me = {"initials": "", "tokens": 5.0, "at": time.monotonic()}

        def on_message(text: str) -> None:
            msg = json.loads(text)
            self.received.append({**msg, "sector": key})
            if msg["t"] == "me":
                me["initials"] = msg["initials"]
            if msg["t"] == "emote":
                answer = {"error": self.emote_error} if self.emote_error else {"ok": True}
                ws.send(json.dumps({"t": "emoted", "to": msg["to"], "e": msg["e"], **answer}))
                return
            if msg["t"] != "claim":
                return
            word = (msg["w"], msg["x"], msg["y"], msg["d"])
            word_key = f"{msg['w']}~{msg['x']}~{msg['y']}~{msg['d']}"
            if self.rate:
                now = time.monotonic()
                me["tokens"] = min(5.0, me["tokens"] + (now - me["at"]) / 1.5)
                me["at"] = now
                if me["tokens"] < 1:
                    ws.send(json.dumps({"t": "error", "key": word_key, "error": "slow down"}))
                    return
                me["tokens"] -= 1
            if self.refuse:
                ws.send(json.dumps({"t": "error", "key": word_key, "error": self.refuse}))
            elif word in self.taken:
                ws.send(json.dumps({"t": "taken", "c": self.taken[word]}))
            elif self.lose == "answer":
                self.claims.append([*word, 0, me["initials"], NOW_MS])
            elif self.lose == "claim":
                pass
            else:
                ws.send(json.dumps({"t": "claimed", "c": [*word, 0, "ZED", NOW_MS], "by": you}))

        ws.on_message(on_message)

    def nova(self, sector: str, rx: int, ry: int, word: list, initials: str = "", at: int = NOW_MS) -> None:
        """Sends sector `sector`'s players a neighbour's supernova, as the sector passes it on:
        territory (rx, ry) went supernova when `word` ([w, x, y, d]) was charted."""
        self.sockets[sector].send(json.dumps({"t": "nova", "n": [rx, ry, at, *word, initials]}))

    def handle_world(self, route: Route) -> None:
        route.fulfill(json=self.world, headers={"Access-Control-Allow-Origin": "*"})

    def handle_list(self, route: Route) -> None:
        """GET /v1/survey/surveyors, as worker/src/survey-social.js answers it, in the order given."""
        size = 40  # LIST_PAGE
        query = {k: v[0] for k, v in parse_qs(urlparse(route.request.url).query).items()}
        self.list_asks.append(query)
        cors = {"Access-Control-Allow-Origin": "*"}
        if self.list_status != 200:
            route.fulfill(status=self.list_status, json={"error": "atlas down"}, headers=cors)
            return
        page = int(query.get("page", 0))
        who = [e for e in self.surveyors if e[0] != query.get("me")]
        route.fulfill(json={"n": len(who), "page": page, "size": size, "more": len(who) > (page + 1) * size,
                            "who": who[page * size:(page + 1) * size]}, headers=cors)

    def guild(self, sector: str, tag: str, on: list) -> None:
        """Tells the game on sector `sector`'s socket who of guild `tag` is online: [[id, initials, rx, ry, idle], ...]."""
        self.sockets[sector].send(json.dumps({"t": "guild", "tag": tag, "on": on}))

    def emote(self, sector: str, sender: str, initials: str, e: str, r: list | None = None) -> None:
        """Sends the game emote `e` on sector `sector`'s socket, from player `sender` in territory r."""
        self.sockets[sector].send(json.dumps({"t": "emote", "from": sender, "ini": initials, "e": e, "r": r}))

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
      const id = 'w' + window.__tsRenders.length;
      // A box the size of Cloudflare's widget, as its iframe takes space in the page once it shows.
      const box = document.createElement('div');
      box.className = 'fake-turnstile';
      box.dataset.widget = id;
      box.style.cssText = 'width:300px;height:65px;display:none';
      document.querySelector(el).appendChild(box);
      if (mode === 'fail') setTimeout(() => o['error-callback']('600010'), 10);
      else if (mode === 'interactive') {
        setTimeout(() => { box.style.display = 'block'; box.textContent = 'Verify you are human'; o['before-interactive-callback'](); }, 10);
        window.__tsSolve = () => { box.textContent = 'Success!'; o['after-interactive-callback'](); o.callback('%s'); };
      } else setTimeout(() => o.callback('%s'), 10);
      return id;
    },
    remove(id) {
      (window.__tsRemoved = window.__tsRemoved || []).push(id);
      document.querySelector(`.fake-turnstile[data-widget="${id}"]`)?.remove();
    },
    reset() {},
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


def player_id(token: str) -> str:
    """A player's id from their token, as worker/src/survey-social.js works it out."""
    return hashlib.sha256(f"games-player:{token}".encode()).hexdigest()[:12]


class FakeGuilds:
    """The guilds' paths, as worker/src/survey-guild.js answers them. `guilds` maps a
    code to {"name": [a, b, c], "tag": "8 hex", "members": [[id, initials, seen], ...]}."""

    def __init__(self, guilds=None, status=None):
        self.guilds = {code: {**g, "members": [list(m) for m in g["members"]]} for code, g in (guilds or {}).items()}
        self.status = status          # answer everything with this status instead, as a Worker in trouble would
        self.calls: list[tuple] = []  # (method, path, body) of every request
        self.made = 0

    def handle(self, route: Route) -> None:
        request = route.request
        path = urlparse(request.url).path.removeprefix("/v1/survey/guilds")
        body = json.loads(request.post_data) if request.method == "POST" and request.post_data else None
        self.calls.append((request.method, path, body))
        cors = {"Access-Control-Allow-Origin": "*"}

        def reply(status: int, data: dict) -> None:
            route.fulfill(status=status, json=data, headers=cors)

        if self.status:
            return reply(self.status, {"error": "guild error"})
        pid = player_id(body["token"]) if body and "token" in body else None
        if path == "" and request.method == "POST":
            self.made += 1
            code = f"GDN{'ABCDEFGHJKMNPQRSTUVWXYZ23456789'[self.made]}22"  # the game's alphabet: no 0, 1, I, L or O
            tag = f"{0xC0DE0000 + self.made:08x}"
            self.guilds[code] = {"name": body["name"], "tag": tag, "members": [[pid, body["initials"], NOW_MS]]}
            return reply(201, {"code": code, **self.guilds[code]})
        parts = path.strip("/").split("/")
        g = self.guilds.get(parts[0])
        if not g:
            return reply(200, {"ok": True}) if parts[1:] == ["leave"] else reply(404, {"error": "unknown guild"})
        if len(parts) == 1:
            return reply(200, {"name": g["name"], "size": len(g["members"])})
        member = next((m for m in g["members"] if m[0] == pid), None)
        if parts[1] == "join":
            if not member:
                g["members"].insert(0, [pid, body["initials"], NOW_MS])
            return reply(200, {"code": parts[0], **g})
        if parts[1] == "leave":
            g["members"] = [m for m in g["members"] if m[0] != pid]
            return reply(200, {"ok": True})
        if not member:
            return reply(404, {"error": "not a member"})
        return reply(200, {"code": parts[0], **g})


class FakeLinks:
    """The paths for linking another device, as worker/src/players.js answers them. `codes`
    maps a code to {"token": 32 hex, "carry": {...}}: codes made elsewhere, for the game to redeem."""

    ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    def __init__(self, codes=None, status=None, players: FakePlayers | None = None):
        self.codes = {code: {"state": "waiting", **link} for code, link in (codes or {}).items()}
        self.players = players if players is not None else FakePlayers()  # redeeming a code starts syncing, as the Worker does
        self.status = status          # answer everything with this status instead, as a Worker in trouble would
        self.calls: list[tuple] = []  # (path, body) of every request
        self.made = 0

    def use(self, code: str) -> None:
        """Another device redeems `code`."""
        self.codes[code]["state"] = "used"
        self.players.start(player_id(self.codes[code]["token"]))

    def expire(self, code: str) -> None:
        self.codes[code]["state"] = "gone"

    def handle(self, route: Route) -> None:
        request = route.request
        path = urlparse(request.url).path.removeprefix("/v1/link")
        body = json.loads(request.post_data) if request.post_data else {}
        self.calls.append((path, body))

        def reply(status: int, data: dict) -> None:
            route.fulfill(status=status, json=data, headers={"Access-Control-Allow-Origin": "*"})

        if self.status:
            return reply(self.status, {"error": "link error"})
        if path == "":
            self.made += 1
            code = "CDEFGHJ" + self.ALPHABET[self.made]
            self.codes[code] = {"token": body["token"], "carry": body["carry"], "state": "waiting"}
            return reply(201, {"code": code, "expires": NOW_MS + 600_000})
        parts = path.strip("/").split("/")
        link = self.codes.get(parts[0].upper())
        if parts[1:] == ["status"]:
            return reply(200, {"state": link["state"] if link and link["token"] == body.get("token") else "gone"})
        if not link or link["state"] != "waiting":
            return reply(404, {"error": "no such code, or it has run out"})
        link["state"] = "used"
        self.players.start(player_id(link["token"]))
        return reply(200, {"token": link["token"], "carry": link["carry"]})


class FakePlayers:
    """The paths that keep linked devices in step, as worker/src/players.js's Player answers
    them, for the player ids `started` (linking starts one). `add()` puts in what another
    device would have sent."""

    def __init__(self, started=()):
        self.players: dict[str, dict] = {}
        self.calls: list[tuple] = []  # (path, body) of every request
        for pid in started:
            self.start(pid)

    def start(self, pid: str) -> None:
        self.players.setdefault(
            pid,
            {"v": 0, "epoch": f"e{len(self.players):07x}", "finds": {}, "novas": {}, "settings": None, "settings_at": 0},
        )

    def add(self, pid: str, finds=(), novas=(), settings=None, settings_at=0) -> None:
        p = self.players[pid]
        p["v"] += 1
        for f in finds:
            p["finds"][f"{f['w']}@{f['x']},{f['y']},{f['d']}"] = (f, p["v"])
        for n in novas:
            p["novas"][f"{n['rx']},{n['ry']}"] = (n, p["v"])
        if settings:
            p["settings"], p["settings_at"] = settings, settings_at

    def sent(self, path: str = "sync") -> list[dict]:
        return [body for p, body in self.calls if p == path]

    def handle(self, route: Route) -> None:
        request = route.request
        path = urlparse(request.url).path.removeprefix("/v1/player/")
        body = json.loads(request.post_data or "{}")
        self.calls.append((path, body))
        pid = player_id(body["token"])

        def reply(data: dict) -> None:
            route.fulfill(status=200, json=data, headers={"Access-Control-Allow-Origin": "*"})

        if path == "forget":
            self.players.pop(pid, None)
            return reply({"off": True})
        p = self.players.get(pid)
        if not p:
            return reply({"off": True})
        since = body.get("since", 0) if body.get("epoch") == p["epoch"] and body.get("since", 0) <= p["v"] else 0
        v, wrote = p["v"] + 1, False
        for f in body.get("finds", []):
            k = f"{f['w']}@{f['x']},{f['y']},{f['d']}"
            had = p["finds"].get(k)
            if not had or (f.get("f") and not had[0].get("f")):
                p["finds"][k], wrote = (f, v), True
        for n in body.get("novas", []):
            k = f"{n['rx']},{n['ry']}"
            if k not in p["novas"]:
                p["novas"][k], wrote = (n, v), True
        theirs = body.get("settingsAt", 0)
        if body.get("settings") and theirs > p["settings_at"]:
            p["settings"], p["settings_at"] = body["settings"], theirs
        if wrote:
            p["v"] = v

        def rows(table: str) -> list[dict]:
            return [b for b, at in sorted(p[table].values(), key=lambda r: r[1]) if since < at != v]

        out = {"epoch": p["epoch"], "at": p["v"], "finds": rows("finds"), "novas": rows("novas")}
        if p["settings"] and p["settings_at"] > theirs:
            out |= {"settings": p["settings"], "settingsAt": p["settings_at"]}
        reply(out)


class FakeRecovery:
    """The recovery codes' paths, as worker/src/players.js answers them. `codes` maps a code to
    the token it brings back; making or using one starts that player's backup in `players`."""

    def __init__(self, players: FakePlayers, codes=None):
        self.players = players
        self.codes = dict(codes or {})
        self.calls: list[tuple] = []  # (path, body) of every request
        self.made = 0

    def handle(self, route: Route) -> None:
        request = route.request
        path = urlparse(request.url).path.removeprefix("/v1/recovery")
        body = json.loads(request.post_data or "{}")
        self.calls.append((path, body))

        def reply(status: int, data: dict) -> None:
            route.fulfill(status=status, json=data, headers={"Access-Control-Allow-Origin": "*"})

        if path == "/use":
            token = self.codes.get(re.sub("[^A-Z0-9]", "", str(body.get("code", "")).upper()))
            if not token:
                return reply(404, {"error": "no such code"})
            self.players.start(player_id(token))
            return reply(200, {"token": token, "made": NOW_MS})
        self.codes = {c: t for c, t in self.codes.items() if t != body["token"]}  # one code a player
        if path == "/remove":
            return reply(200, {"ok": True})
        self.made += 1
        code = "KMNPQRSTUVWXYZ23456" + FakeLinks.ALPHABET[self.made]
        self.codes[code] = body["token"]
        self.players.start(player_id(body["token"]))
        return reply(201, {"code": code, "made": NOW_MS})
