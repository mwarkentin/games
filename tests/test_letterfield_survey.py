"""Letterfield's shared survey, against a fake of the sector WebSockets.

?survey= points the game at https://survey.test, which tests/fake_survey.py
answers. The real Sector Durable Object is tested in
worker/test/survey.test.js. The game starts at cell (6, 6), so a desktop
window sees the corner where sectors (0, 0), (-1, 0), (0, -1) and (-1, -1)
meet and joins all four.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, Route, expect

from fake_leaderboard import without_worker
from fake_survey import AREA_WORDS, DUMMY_TOKEN, FAKE_TURNSTILE, NOW_MS, TURNSTILE_JS, FakePassDesk, FakeSurvey, world_map

SURVEY = "https://survey.test"


def without_turnstile(page: Page) -> None:
    """Serve the game with TURNSTILE_SITE_KEY blanked, so the survey joins without Cloudflare's check.

    The real key would load challenges.cloudflare.com, which tests never reach. The
    Turnstile tests below turn it back on with ?turnstile= and a fake widget.
    """

    def handle(route: Route) -> None:
        response = route.fetch()
        body = re.sub(r"\b(TURNSTILE_SITE_KEY = )'[^']*'", r"\1''", response.text())
        route.fulfill(response=response, body=body)

    page.route(lambda url: urlparse(url).path == "/letterfield", handle)


def open_game(page: Page, site_url: str, fake: FakeSurvey | None, query: str = "", own_site_key: bool = False) -> None:
    """Opens the game, against `fake` if given. Its own Turnstile site key is blanked
    unless `own_site_key` is set or `query` brings one (?turnstile=)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    if not own_site_key and "turnstile=" not in query:
        without_turnstile(page)
    if fake:
        page.route_web_socket(re.compile(r"^wss://survey\.test/"), fake.handle)
        page.route(f"{SURVEY}/v1/survey/world", fake.handle_world)
        page.goto(f"{site_url}/letterfield?survey={SURVEY}{query}#debug")
    else:
        without_worker(page, site_url, "letterfield")  # SURVEY_URL blanked: playing alone
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


def test_without_a_survey_url_the_game_plays_alone(page: Page, site_url, errors):
    sockets = []
    page.on("websocket", lambda ws: sockets.append(ws.url))
    open_game(page, site_url, None)
    circle(page, hidden_words(page)[0])
    expect(page.locator("#notesBadge")).to_have_text("1")
    expect(page.locator("#survey")).to_be_hidden()
    expect(page.locator("#tCharted")).to_have_text(re.compile(r"^ · 1/\d+ found$"))
    expect(page.locator("#legendList button.chip").first).to_be_visible()  # on your own, the list gives hints
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


def test_claiming_too_fast_says_so_and_keeps_the_word(page: Page, site_url, errors):
    words = known_words(page, site_url)
    fake = FakeSurvey(refuse="slow down")
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    circle(page, words[0])
    expect(page.locator("#toast")).to_contain_text("Too quick to chart · kept in your notes")
    assert page.evaluate("window.__lf.found.size") == 1
    assert page.evaluate("window.__lf.found.values().next().value.f") == 0
    # Play carries on: the next word is found and claimed as usual.
    circle(page, words[1])
    eventually(page, lambda: len(fake.sent("claim")) == 2)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert errors == []


def test_past_the_daily_limit_says_so_and_keeps_the_word(page: Page, site_url, errors):
    words = known_words(page, site_url)
    open_game(page, site_url, FakeSurvey(refuse="daily limit"))
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    circle(page, words[0])
    expect(page.locator("#toast")).to_contain_text("Today’s charting limit reached · kept in your notes")
    assert page.evaluate("window.__lf.found.size") == 1
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


def territory_words(page: Page, site_url: str) -> list[list]:
    """Every word hidden in territory (0, 0), read before the test opens the game for real."""
    page.goto(f"{site_url}/letterfield#debug")
    words = page.evaluate("""() => {
      const out = [];
      for (let cy = 0; cy < 4; cy++) for (let cx = 0; cx < 4; cx++) for (const o of window.__lf.chunk(cx, cy).words) out.push([o.w, o.x, o.y, o.d]);
      return out;
    }""")
    page.evaluate("localStorage.clear()")
    page.goto("about:blank")
    return words


def test_charting_the_last_word_in_a_territory_sets_it_off(page: Page, site_url, errors):
    words = territory_words(page, site_url)
    fake = FakeSurvey(claims=[[*w, 0, "MRW", NOW_MS - 60_000] for w in words[1:]])
    open_game(page, site_url, fake)
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words) - 1}/{len(words)} charted")
    circle(page, words[0])
    expect(page.locator("#nova")).to_be_visible(timeout=6000)
    expect(page.locator("#novaText")).to_contain_text("every hidden word charted, the last by you")
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words)}/{len(words)} charted")
    assert errors == []


def test_someone_else_finishing_a_territory_nearby_sets_it_off_too(page: Page, site_url, errors):
    words = territory_words(page, site_url)
    fake = FakeSurvey(claims=[[*w, 0, "MRW", NOW_MS - 60_000] for w in words[1:]])
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets)
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words) - 1}/{len(words)} charted")
    cam = page.evaluate("({ ...window.__lf.cam })")
    fake.sockets["0,0"].send(json.dumps({"t": "claimed", "c": [*words[0], 0, "SIS", NOW_MS], "by": "someone"}))
    expect(page.locator("#nova")).to_be_visible(timeout=6000)
    expect(page.locator("#novaText")).to_contain_text("the last by SIS")
    # Only your own pulls the camera over to watch.
    assert page.evaluate("({ ...window.__lf.cam })") == cam
    assert errors == []


SCREEN_OF = """([x, y]) => {
  const cam = window.__lf.cam, dock = document.body.classList.contains('docked') ? 340 : 0;
  return [(x - cam.x) * cam.cs + (innerWidth - dock) / 2, (y - cam.y) * cam.cs + innerHeight / 2];
}"""


def test_hovering_names_surveyors_and_who_charted_a_word(page: Page, site_url, errors):
    words = known_words(page, site_url)
    w, x, y, d = words[0]
    fake = FakeSurvey(
        claims=[[*words[0], 0, "MRW", NOW_MS - 60_000]],
        presence=[["kid1", "KID", 9.5, 7.0], ["odd", "<b>", 3.4, 9.2]],
    )
    open_game(page, site_url, fake)
    expect(page.locator("#surveyText")).to_contain_text("2 other surveyors nearby")
    peek = page.locator("#peek")
    expect(peek).to_be_hidden()

    # The caret sits in the gap beside the cell in the middle of their view.
    page.mouse.move(*page.evaluate(SCREEN_OF, [10, 7.5]))
    expect(peek).to_be_visible()
    expect(peek).to_have_text("KIDsurveying here")
    page.mouse.move(*page.evaluate(SCREEN_OF, [3, 9.5]))
    expect(peek).to_have_text("A surveyorsurveying here")  # odd initials never reach the page

    # A charted word names who got there first.
    dirs = [[1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1], [0, -1], [1, -1]]
    mid = len(w) // 2
    page.mouse.move(*page.evaluate(SCREEN_OF, [x + dirs[d][0] * mid + .5, y + dirs[d][1] * mid + .5]))
    expect(peek).to_contain_text(f"{w}Charted first by MRW")

    # Panning hides it.
    page.mouse.wheel(0, 120)
    expect(peek).to_be_hidden()
    assert errors == []


def test_word_list_gives_no_hints_on_the_shared_survey(page: Page, site_url, errors):
    open_game(page, site_url, FakeSurvey())
    expect(page.locator("#survey")).to_be_visible()
    chips = page.locator("#legendList .chip")
    expect(chips.first).to_be_visible()
    # Plain labels: nothing to tap that would show where a word starts.
    expect(page.locator("#legendList button")).to_have_count(0)
    expect(page.locator("#legendList [title]")).to_have_count(0)
    assert errors == []


def test_the_game_joins_the_survey_on_the_worker_by_default(page: Page, site_url, errors):
    # No ?survey=, so the game uses SURVEY_URL: the real Worker, which every
    # test context answers with an empty fake (fake_leaderboard.py).
    # Its Turnstile check is answered by the stand-in too.
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{site_url}/letterfield#debug")
    expect(page.locator("#survey")).to_be_visible()
    expect(page.locator("#surveyText")).to_contain_text("Live")
    page.wait_for_function("[...window.__lf.links.values()].some(l => l.you)")
    assert errors == []


# ---------- Turnstile (worker/TURNSTILE.md) ----------
# A site key in ?turnstile= turns the check on, against the fake widget and
# pass desk in fake_survey.py. The site key is Cloudflare's invisible
# always-passes test key.

SITE_KEY = "1x00000000000000000000BB"


def with_turnstile(page: Page, mode: str = "pass", desk: FakePassDesk | None = None) -> FakePassDesk:
    desk = desk or FakePassDesk()
    page.add_init_script(f"window.__tsMode = {json.dumps(mode)}")
    page.route(TURNSTILE_JS, lambda route: route.fulfill(content_type="application/javascript", body=FAKE_TURNSTILE))
    page.route(f"{SURVEY}/v1/survey/pass", desk.handle)
    return desk


def test_turnstile_stays_off_without_a_site_key(page: Page, site_url, errors):
    scripts = []
    page.on("request", lambda r: scripts.append(r.url) if "challenges.cloudflare.com" in r.url else None)
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert scripts == []
    assert all("?" not in url for url in fake.urls)
    assert errors == []


def test_the_game_runs_turnstile_with_its_own_site_key(page: Page, site_url, errors):
    # Without ?turnstile=, the game uses the key it was published with.
    key = re.search(r"const TURNSTILE_SITE_KEY = '([^']*)'", (Path(__file__).parent.parent / "letterfield.html").read_text("utf-8"))[1]
    assert re.fullmatch(r"0x[\w-]{10,}", key), "letterfield.html should carry the widget's public site key"
    desk = with_turnstile(page)
    fake = FakeSurvey()
    open_game(page, site_url, fake, own_site_key=True)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert [r["sitekey"] for r in page.evaluate("window.__tsRenders.map(r => ({ sitekey: r.sitekey }))")] == [key]
    assert desk.tokens == [DUMMY_TOKEN]
    assert errors == []


def test_turnstile_pass_lets_every_sector_in(page: Page, site_url, errors):
    desk = with_turnstile(page)
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    renders = page.evaluate("window.__tsRenders")
    assert renders == [{"el": "#surveyWidget", "sitekey": SITE_KEY, "action": "survey", "appearance": "interaction-only"}]
    assert desk.tokens == [DUMMY_TOKEN]
    # One check covers all four sectors in view.
    assert sorted(fake.sectors) == ["-1,-1", "-1,0", "0,-1", "0,0"]
    assert all(url.endswith(f"?pass={desk.issued[0]}") for url in fake.urls)
    expect(page.locator("#surveyCheck")).not_to_have_class(re.compile("asking"))

    # A reload, or travelling to new sectors, reuses the pass: no new challenge.
    page.reload()
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    page.evaluate("window.__lf.cam.x = 600; window.__lf.cam.y = 600")
    eventually(page, lambda: "3,3" in fake.sectors, 6000)
    assert page.evaluate("window.__tsRenders") is None  # Turnstile wasn't even loaded
    assert desk.tokens == [DUMMY_TOKEN]
    assert errors == []


def test_turnstile_shows_its_box_only_when_it_wants_a_tap(page: Page, site_url, errors):
    with_turnstile(page, "interactive")
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#surveyCheck")).to_have_class(re.compile("asking"))
    expect(page.locator("#surveyCheck")).to_contain_text("One tap to join the shared survey")
    expect(page.locator("#surveyText")).to_have_text("Checking this is a person, not a bot…")
    assert fake.sectors == []
    page.evaluate("window.__tsSolve()")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    expect(page.locator("#surveyCheck")).not_to_have_class(re.compile("asking"))
    assert errors == []


def test_refused_pass_gets_a_new_one(page: Page, site_url, errors):
    # A pass from a stored session the Worker no longer takes, as when the player's address changed.
    page.add_init_script("""localStorage.setItem('letterfield.surveyPass.v1',
      JSON.stringify({ pass: 'old-pass', expires: Date.now() + 1800000 }))""")
    desk = with_turnstile(page)
    fake = FakeSurvey(refuse_passes={"old-pass"})
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert desk.tokens == [DUMMY_TOKEN]
    assert any(url.endswith("?pass=old-pass") for url in fake.urls)
    assert fake.urls[-1].endswith(f"?pass={desk.issued[0]}")
    assert errors == []


def test_failed_check_joins_without_a_pass_while_passes_arent_required(page: Page, site_url, errors):
    # With TURNSTILE_REQUIRED off, the Worker takes the join and only counts it.
    with_turnstile(page, "fail")
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert sorted(fake.sectors) == ["-1,-1", "-1,0", "0,-1", "0,0"]
    assert all("?" not in url for url in fake.urls)
    circle(page, hidden_words(page)[0])
    eventually(page, lambda: len(fake.sent("claim")) == 1)
    assert page.evaluate("window.__tsRenders.length") == 1  # it waits before asking again
    assert errors == []


def test_refused_token_joins_without_a_pass_while_passes_arent_required(page: Page, site_url):
    # Skips the errors fixture: the browser logs the 403.
    desk = with_turnstile(page, desk=FakePassDesk(status=403))
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert desk.tokens == [DUMMY_TOKEN]
    assert all("?" not in url for url in fake.urls)


def test_blocked_turnstile_joins_without_a_pass_while_passes_arent_required(page: Page, site_url):
    # An ad blocker or a school network that blocks challenges.cloudflare.com.
    # Skips the errors fixture: the browser logs the blocked script.
    page.route(TURNSTILE_JS, lambda route: route.abort("blockedbyclient"))
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert all("?" not in url for url in fake.urls)


def test_failed_check_leaves_you_surveying_alone_once_passes_are_required(page: Page, site_url, errors):
    with_turnstile(page, "fail")
    fake = FakeSurvey(require_pass=True)
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#surveyText")).to_have_text(
        "Couldn’t check this is a person, so you’re surveying alone for now. Your finds still save in this browser.")
    expect(page.locator("#survey")).to_have_attribute("data-state", "offline")
    circle(page, hidden_words(page)[0])
    expect(page.locator("#notesBadge")).to_have_text("1")
    page.wait_for_timeout(2500)
    assert fake.sectors == []
    tried = len(fake.urls)
    assert 1 <= tried <= 4  # one try without a pass per sector in view, then no more knocking
    page.wait_for_timeout(2500)
    assert len(fake.urls) == tried
    assert errors == []


def test_blocked_turnstile_leaves_you_surveying_alone_once_passes_are_required(page: Page, site_url):
    page.route(TURNSTILE_JS, lambda route: route.abort("blockedbyclient"))
    fake = FakeSurvey(require_pass=True)
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#surveyText")).to_contain_text("Couldn’t check this is a person")
    circle(page, hidden_words(page)[0])
    expect(page.locator("#notesBadge")).to_have_text("1")
    assert fake.sectors == []
