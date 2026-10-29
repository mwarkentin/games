"""Letterfield's shared survey, against a fake of the sector WebSockets.

The game reads the survey server's URL from ?survey=, so these tests point it
at https://survey.test and answer its WebSockets with Playwright's
page.route_web_socket. The real Sector Durable Object is tested in
worker/test/survey.test.js. The game starts at cell (6, 6), so a desktop
window sees the corner where sectors (0, 0), (-1, 0), (0, -1) and (-1, -1)
meet and joins all four.
"""

from __future__ import annotations

import base64
import json
import re

from playwright.sync_api import Page, Route, WebSocketRoute, expect

SURVEY = "https://survey.test"
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


def open_game(page: Page, site_url: str, fake: FakeSurvey | None) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    if fake:
        page.route_web_socket(re.compile(r"^wss://survey\.test/"), fake.handle)
        page.route(f"{SURVEY}/v1/survey/world", fake.handle_world)
        page.goto(f"{site_url}/letterfield?survey={SURVEY}#debug")
    else:
        page.goto(f"{site_url}/letterfield#debug")
    if page.locator("#coach").is_visible():
        page.click("#coachOk")


def open_notes(page: Page) -> None:
    if page.locator("#notes").is_hidden():
        page.click("#notesToggle")


def hidden_words(page: Page) -> list[list]:
    """The words hidden in the chunk at the origin, as [w, x, y, d]."""
    return page.evaluate("window.__lf.chunk(0, 0).words.map(o => [o.w, o.x, o.y, o.d])")


def known_words(page: Page, site_url: str) -> list[list]:
    """hidden_words, read before the test opens the game for real."""
    page.goto(f"{site_url}/letterfield#debug")
    words = hidden_words(page)
    page.evaluate("localStorage.clear()")
    page.goto("about:blank")
    return words


def circle(page: Page, word: list) -> None:
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", word)


def eventually(page: Page, check, timeout_ms: int = 5000) -> None:
    """Waits for the fake to see what the game sent: its handlers run between Playwright calls."""
    for _ in range(timeout_ms // 50):
        if check():
            return
        page.wait_for_timeout(50)
    assert check()


def test_survey_stays_off_until_configured(page: Page, site_url, errors):
    sockets = []
    page.on("websocket", lambda ws: sockets.append(ws.url))
    open_game(page, site_url, None)
    circle(page, hidden_words(page)[0])
    expect(page.locator("#notesBadge")).to_have_text("1")
    expect(page.locator("#survey")).to_be_hidden()
    expect(page.locator("#tCharted")).to_be_hidden()
    assert sockets == []
    assert errors == []


def test_shared_map_shows_other_surveyors_and_their_words(page: Page, site_url, errors):
    words = known_words(page, site_url)
    fake = FakeSurvey(
        claims=[[*words[0], 0, "MRW", NOW_MS - 60_000]],
        presence=[["kid1", "KID", 9.5, 7.0], ["anon", "", 3.0, 4.0]],
    )
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_be_visible()
    expect(page.locator("#surveyText")).to_have_text(re.compile(
        r"^Live · 2 other surveyors nearby\nWorld: 0 of 1,120,206 charted · 0 online\n"
        r"\w[\w ]+: 1 of \d+ charted\n0 words charted first by you$"
    ))
    assert sorted(fake.sectors) == ["-1,-1", "-1,0", "0,-1", "0,0"]
    expect(page.locator("#tCharted")).to_have_text(re.compile(r"^ · 1/\d+ charted$"))
    eventually(page, lambda: len(fake.sent("me")) == 4 and fake.sent("pos"))
    assert {m["initials"] for m in fake.sent("me")} == {""}
    # Only the sector under the middle of the view hears where the player is.
    assert fake.sent("pos") == [{"t": "pos", "x": 6, "y": 6, "sector": "0,0"}]

    # Circling a word nobody has charted claims it and credits you.
    circle(page, words[1])
    expect(page.locator("#toast")).to_contain_text("First to chart it")
    expect(page.locator("#tCharted")).to_have_text(re.compile(r"^ · 2/\d+ charted$"))
    w, x, y, d = words[1]
    assert fake.sent("claim") == [{"t": "claim", "w": w, "x": x, "y": y, "d": d, "sector": "0,0"}]
    expect(page.locator("#surveyText")).to_contain_text("2 of")
    expect(page.locator("#surveyText")).to_contain_text("1 word charted first by you")
    open_notes(page)
    expect(page.locator("#finds .find-meta").first).to_contain_text("charted first")

    # Circling a word someone already charted keeps it in your notes, credited to them.
    circle(page, words[0])
    expect(page.locator("#notesBadge")).to_have_text("2")
    eventually(page, lambda: len(fake.sent("claim")) == 2)
    assert errors == []


def test_second_to_a_word_hears_who_was_first(page: Page, site_url, errors):
    word = known_words(page, site_url)[2]
    fake = FakeSurvey(taken=[[*word, 0, "SIS", NOW_MS]])
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    circle(page, word)
    expect(page.locator("#toast")).to_contain_text("Charted first by SIS")
    assert page.evaluate("window.__lf.found.values().next().value.f") == 0
    assert errors == []


def test_signing_initials_tells_every_sector(page: Page, site_url, errors):
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    open_notes(page)
    page.locator("#surveyInitials").press_sequentially("z3ed")
    expect(page.locator("#surveyInitials")).to_have_value("ZED")
    page.click("#surveySign button")
    expect(page.locator("#surveyHint")).to_have_text("Words you chart first are signed ZED.")
    assert page.evaluate("localStorage.getItem('games.initials')") == "ZED"
    signed = lambda: {m["sector"] for m in fake.sent("me") if m["initials"] == "ZED"}  # noqa: E731
    eventually(page, lambda: signed() == {"-1,-1", "-1,0", "0,-1", "0,0"})

    # Next time, the game signs in with them straight away.
    fake.received.clear()
    page.reload()
    expect(page.locator("#surveyInitials")).to_have_value("ZED")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    eventually(page, lambda: len(fake.sent("me")) == 4)
    assert {m["initials"] for m in fake.sent("me")} == {"ZED"}
    assert errors == []


def test_unreachable_survey_says_so_and_the_game_carries_on(page: Page, site_url):
    # Nothing answers: .test names never resolve. Skips the errors fixture,
    # because the browser logs each WebSocket that fails to connect.
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{site_url}/letterfield?survey={SURVEY}#debug")
    page.click("#coachOk")
    expect(page.locator("#surveyText")).to_have_text("Survey offline. Your finds still save in this browser.")
    expect(page.locator("#survey")).to_have_attribute("data-state", "offline")
    circle(page, hidden_words(page)[0])
    expect(page.locator("#notesBadge")).to_have_text("1")
    expect(page.locator("#tCharted")).to_be_hidden()


def test_hidden_tab_leaves_the_survey(page: Page, site_url, errors):
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    page.evaluate("""() => {
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
      document.dispatchEvent(new Event('visibilitychange'));
    }""")
    expect(page.locator("#surveyText")).to_have_text("Paused while this tab is hidden.")
    assert page.evaluate("window.__lf.links.size") == 0
    page.evaluate("""() => {
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
      document.dispatchEvent(new Event('visibilitychange'));
    }""")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert len(fake.sectors) == 8  # all four sectors, joined twice
    assert errors == []


def test_travelling_joins_the_sectors_where_you_land(page: Page, site_url, errors):
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    w, x, y, d = page.evaluate("(({ w, x, y, d }) => [w, x, y, d])(window.__lf.chunk(150, 40).words[0])")
    page.evaluate(f"location.hash = 'f-{w.lower()}-{x}-{y}-{d}'")  # flies there, as a field-notes link does
    home = f"{x // 192},{y // 192}"
    page.wait_for_function(f"window.__lf.links.get('{home}')?.you", timeout=8000)
    eventually(page, lambda: any(m["sector"] == home for m in fake.sent("pos")))
    # Nothing on the way was joined, and the sectors left behind are let go.
    assert all(abs(int(k.split(",")[0])) <= 1 or abs(int(k.split(",")[0]) - x // 192) <= 1 for k in fake.sectors)
    page.wait_for_function(f"[...window.__lf.links.keys()].every(k => Math.abs(+k.split(',')[0] - {x // 192}) <= 1)", timeout=8000)
    assert errors == []


def test_world_counter_ticks_up_as_words_are_charted(page: Page, site_url, errors):
    words = known_words(page, site_url)
    fake = FakeSurvey(totals={"charted": 412_883, "total": AREA_WORDS, "players": 3_201})
    open_game(page, site_url, fake)
    expect(page.locator("#surveyText")).to_contain_text("World: 412,883 of 1,120,206 charted · 3,201 online")
    expect(page.locator("#brandSub")).to_have_text("412,883 of 1,120,206 charted")
    circle(page, words[3])
    expect(page.locator("#brandSub")).to_have_text("412,884 of 1,120,206 charted")
    assert errors == []


def test_world_map_shows_where_people_are_and_flies_there(page: Page, site_url, errors):
    fake = FakeSurvey(world=world_map(charted={(0, 0): 60, (1, 0): 112, (-20, 30): 5},
                                      sectors=[[0, 0, 12], [-5, 7, 45]], players=57))
    open_game(page, site_url, fake)
    open_notes(page)
    page.click("#surveyMap summary")
    expect(page.locator("#worldNote")).to_have_text("57 surveyors in 2 sectors")
    expect(page.locator("#surveyText")).to_contain_text("World: 177 of 1,120,206 charted · 57 online")
    # Darker where charted: the territory at the origin is drawn stronger than an untouched one.
    shade = """([tx, ty]) => { const c = document.getElementById('worldMap'), g = c.getContext('2d');
      const cell = c.width / 100, [r, gr, b] = g.getImageData((tx + 48.5) * cell, (ty + 48.5) * cell, 1, 1).data;
      return r + gr + b; }"""
    assert page.evaluate(shade, [0, 0]) < page.evaluate(shade, [10, 10])

    # Tapping the map flies to that territory.
    box = page.locator("#worldMap").bounding_box()
    tx, ty = -40, 20
    page.mouse.click(box["x"] + (tx + 48.5) / 100 * box["width"], box["y"] + (ty + 48.5) / 100 * box["height"])
    page.wait_for_function(f"Math.floor(window.__lf.cam.x / 48) === {tx} && Math.floor(window.__lf.cam.y / 48) === {ty}", timeout=8000)
    assert errors == []


def test_new_players_start_where_the_atlas_suggests(page: Page, site_url, errors):
    fake = FakeSurvey(world=world_map(sectors=[[3, -2, 20]], spawn=[3 * 192 + 40, -2 * 192 + 70], players=20))
    open_game(page, site_url, fake)
    page.wait_for_function("window.__lf.links.get('3,-2')?.you")
    cam = page.evaluate("[window.__lf.cam.x, window.__lf.cam.y]")
    assert abs(cam[0] - (3 * 192 + 40.5)) <= 4 and abs(cam[1] - (-2 * 192 + 70.5)) <= 4  # beside the latest claim
    assert "0,0" not in fake.sectors  # it waited to hear where to start before joining

    # A returning player picks up where they left off.
    page.wait_for_timeout(600)  # the camera is saved half a second after it moves
    page.reload()
    page.wait_for_function("window.__lf.links.get('3,-2')?.you")
    assert page.evaluate("Math.floor(window.__lf.cam.x / 192)") == 3
    assert errors == []


def test_full_sector_says_so(page: Page, site_url, errors):
    fake = FakeSurvey(full="sector")
    open_game(page, site_url, fake)
    expect(page.locator("#surveyText")).to_have_text("This part of the map is full right now. Your finds still save in this browser.")
    circle(page, hidden_words(page)[0])
    expect(page.locator("#notesBadge")).to_have_text("1")
    page.wait_for_timeout(1500)
    assert len(fake.sectors) == 4  # and it doesn't keep knocking
    assert errors == []


def test_full_survey_says_so(page: Page, site_url, errors):
    fake = FakeSurvey(full="world")
    open_game(page, site_url, fake)
    expect(page.locator("#surveyText")).to_have_text("The survey is full right now. Your finds still save in this browser.")
    expect(page.locator("#survey")).to_have_attribute("data-state", "offline")
    assert errors == []
