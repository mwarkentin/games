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
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, Route, expect

from fake_leaderboard import without_worker
from fake_survey import AREA_WORDS, DUMMY_TOKEN, FAKE_TURNSTILE, NOW_MS, TURNSTILE_JS, FakePassDesk, FakeSurvey, world_map

SURVEY = "https://survey.test"

# A find's note shows a while, then folds into the field notes, and the count
# ticks up as it lands: this long, at most, after the find.
LANDS = 10_000


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


def open_game(page: Page, site_url: str, fake: FakeSurvey | None, query: str = "", own_site_key: bool = False,
              viewport: dict | None = None) -> None:
    """Opens the game, against `fake` if given. Its own Turnstile site key is blanked
    unless `own_site_key` is set or `query` brings one (?turnstile=)."""
    page.set_viewport_size(viewport or {"width": 1280, "height": 900})
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
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
    expect(page.locator("#survey")).to_be_hidden()
    expect(page.locator("#signup")).to_be_hidden()  # nothing to sign when playing alone
    expect(page.locator("#tCharted")).to_have_text(re.compile(r"^ · 1/\d+ found$"))
    expect(page.locator("#legendList button.chip").first).to_be_visible()  # on your own, the list gives hints
    assert sockets == []
    assert errors == []


def test_shared_word_list_scrolls_only_sideways(page: Page, site_url, errors):
    from test_letterfield import CHIPS_JS, chips_scroll_only_sideways

    open_game(page, site_url, FakeSurvey())
    expect(page.locator("#legendList span.chip").first).to_be_visible()  # plain labels, no hints
    # Each size waits for the list to catch up with it: a check made straight
    # after a resize would measure the list from before. On a phone, zoomed
    # out enough that the row holds more words than fit across.
    full = "n => document.querySelectorAll('#legendList span.chip').length >= n"
    for phone, size in ((False, {"width": 1280, "height": 900}), (True, {"width": 375, "height": 740})):
        page.set_viewport_size(size)
        # At the origin, not wherever the survey's random spawn put the camera,
        # which on a phone's shorter map (between its bars) can hold too few words.
        page.evaluate("cs => { Object.assign(window.__lf.cam, { x: 6, y: 6, cs }); dispatchEvent(new Event('resize')); }", 12 if phone else 38)
        page.wait_for_function(full, arg=12 if phone else 10)
        page.wait_for_timeout(300)  # and any update still to come
        chips_scroll_only_sideways(page)
    m = page.evaluate(CHIPS_JS)
    assert m["sw"] > m["cw"], m
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
        r"^Live · 2 other surveyors nearby\nWorld: 0 of 1,119,752 charted · 0 online\n"
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
    expect(page.locator("#findSay")).to_contain_text(f"{words[1][0]} · First to chart it")  # said, with no note
    expect(page.locator("#toast")).not_to_have_class(re.compile(r"\bshow\b"))
    expect(page.locator("#tCharted")).to_have_text(re.compile(r"^ · 2/\d+ charted$"))
    w, x, y, d = words[1]
    assert fake.sent("claim") == [{"t": "claim", "w": w, "x": x, "y": y, "d": d, "sector": "0,0"}]
    expect(page.locator("#surveyText")).to_contain_text("2 of")
    expect(page.locator("#surveyText")).to_contain_text("1 word charted first by you")
    open_notes(page)
    expect(page.locator("#finds .find-meta").first).to_contain_text("charted first")

    # Circling a word someone already charted finds nothing new: it's theirs.
    circle(page, words[0])
    expect(page.locator("#toast")).to_contain_text("Already charted by MRW")
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
    page.wait_for_timeout(300)
    assert len(fake.sent("claim")) == 1
    assert errors == []


def test_a_word_charted_first_shares_where_it_came_in_the_worlds_count(page: Page, site_url, errors):
    word = known_words(page, site_url)[3]
    fake = FakeSurvey(totals={"charted": 412_883, "total": AREA_WORDS, "players": 3_201})
    page.add_init_script("""
      window.__shared = [];
      Object.defineProperty(navigator, 'share', { value: data => { window.__shared.push(data); return Promise.resolve(); }, configurable: true });
    """)
    open_game(page, site_url, fake)
    expect(page.locator("#brandSub")).to_have_text("412,883 of 1,119,752 charted")
    circle(page, word)
    expect(page.locator("#findSay")).to_contain_text("First to chart it")
    open_notes(page)
    page.locator("#finds").get_by_role("button", name=f"Share {word[0]}").click()
    pattern = rf"I just found {word[0]} in [A-Z][a-z]+ [A-Z][a-z]+ in Letterfield, before anyone else\. That was word 412,884 of 1,119,752 on the shared map\."
    assert re.fullmatch(pattern, page.evaluate("window.__shared[0].text"))
    # The link goes to the share Worker, whose page carries a picture of the word.
    assert page.evaluate("window.__shared[0].url") == f"https://share.michaelwarkentin.com/f/f-{word[0].lower()}-{word[1]}-{word[2]}-{word[3]}"
    # Where it came is kept with the find, so the field notes share it later too.
    page.reload()
    open_notes(page)
    page.locator("#finds").get_by_role("button", name=f"Share {word[0]}").click()
    assert re.fullmatch(pattern, page.evaluate("window.__shared[0].text"))
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


def test_circling_a_word_someone_charted_finds_nothing_new(page: Page, site_url, errors):
    words = known_words(page, site_url)
    fake = FakeSurvey(claims=[[*words[0], 0, "MRW", NOW_MS - 60_000]])
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    circle(page, words[0])
    expect(page.locator("#toast")).to_contain_text(f"{words[0][0]}Already charted by MRW")
    expect(page.locator("#toast .share")).to_have_count(0)
    assert page.evaluate("window.__lf.found.size") == 0
    expect(page.locator("#notesBadge")).to_have_text("0")
    # A word nobody has charted is found and claimed as ever.
    circle(page, words[1])
    eventually(page, lambda: len(fake.sent("claim")) == 1)
    assert fake.sent("claim")[0]["w"] == words[1][0]
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
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
    page.click("#surveySign button[type=submit]")
    expect(page.locator("#surveyMeName")).to_have_text("ZED")  # the form gives way to who you are
    expect(page.locator("#surveySign")).to_be_hidden()
    assert page.evaluate("localStorage.getItem('games.initials')") == '"ZED"'  # JSON, as the other games keep it
    signed = lambda: {m["sector"] for m in fake.sent("me") if m["initials"] == "ZED"}  # noqa: E731
    eventually(page, lambda: signed() == {"-1,-1", "-1,0", "0,-1", "0,0"})

    # Next time, the game signs in with them straight away.
    fake.received.clear()
    page.reload()
    open_notes(page)
    expect(page.locator("#surveyMe")).to_be_visible()
    expect(page.locator("#surveyMeName")).to_have_text("ZED")
    expect(page.locator("#surveySign")).to_be_hidden()
    expect(page.locator("#signup")).to_be_hidden()
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    eventually(page, lambda: len(fake.sent("me")) == 4)
    assert {m["initials"] for m in fake.sent("me")} == {"ZED"}
    assert errors == []



def test_the_pencil_changes_your_initials(page: Page, site_url, errors):
    fake = FakeSurvey()
    page.add_init_script("localStorage.setItem('games.initials', JSON.stringify('MLW'))")
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    open_notes(page)
    expect(page.locator("#surveyMe")).to_have_text(re.compile(r"Surveyor\s*MLW"))
    expect(page.locator("#surveySign")).to_be_hidden()

    # Escape puts the pencil back without changing anything, and leaves the notes open.
    page.click("#surveyEdit")
    expect(page.locator("#surveyInitials")).to_be_focused()
    expect(page.locator("#surveyInitials")).to_have_value("MLW")
    page.keyboard.press("Escape")
    expect(page.locator("#surveySign")).to_be_hidden()
    expect(page.locator("#surveyEdit")).to_be_focused()
    expect(page.locator("#notes")).to_be_visible()

    # Three letters or nothing; then the new ones go to every sector.
    page.click("#surveyEdit")
    page.keyboard.type("zz")
    page.keyboard.press("Enter")
    expect(page.locator("#surveyHint")).to_have_text("Use three letters, A to Z.")
    page.keyboard.type("q")
    page.keyboard.press("Enter")
    expect(page.locator("#surveyMeName")).to_have_text("ZZQ")
    expect(page.locator("#surveyHint")).to_have_text("")
    expect(page.locator("#surveyEdit")).to_be_focused()
    assert page.evaluate("localStorage.getItem('games.initials')") == '"ZZQ"'  # JSON, as the other games keep it
    eventually(page, lambda: {m["sector"] for m in fake.sent("me") if m["initials"] == "ZZQ"} == {"-1,-1", "-1,0", "0,-1", "0,0"})

    # Cancel works the same as Escape.
    page.click("#surveyEdit")
    page.click("#surveyCancel")
    expect(page.locator("#surveyMeName")).to_have_text("ZZQ")
    assert errors == []


# Both ends of a word hidden at the origin, on screen and clear of the cards over the map.
WORD_ENDS = """() => {
  const lf = window.__lf, dock = document.body.classList.contains('docked') ? 340 : 0;
  const at = (x, y) => [(x + .5 - lf.cam.x) * lf.cam.cs + (innerWidth - dock) / 2, (y + .5 - lf.cam.y) * lf.cam.cs + (m => m.getBoundingClientRect().top + m.clientHeight / 2)(document.getElementById('map'))];
  const clear = ([px, py]) => document.elementFromPoint(px, py) === document.querySelector('canvas');
  for (const w of lf.chunk(0, 0).words) {
    const ends = [at(w.x, w.y), at(...lf.wordEnd(w))];
    if (ends.every(clear)) return { word: w.w, ends };
  }
  return null;
}"""


def test_initials_come_before_the_first_word(page: Page, site_url, errors):
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    signup, html = page.locator("#signup"), page.locator("html")
    expect(html).to_have_attribute("data-intro", "sign")
    expect(signup).to_be_visible()
    # One card for a new player: how to play and the initials together.
    expect(page.locator("#signupHow")).to_be_visible()
    expect(page.locator("#signupHow")).to_contain_text("tap a word's first letter, then its last")
    expect(page.locator("#signupKbd")).to_have_text("Shift-drag also circles")
    expect(page.locator("#signupOnly")).to_be_hidden()
    expect(page.locator("#coach")).to_be_hidden()

    # Tapping a word's ends circles nothing yet, and asks again.
    target = page.evaluate(WORD_ENDS)
    assert target, "no hidden word with both ends clear on screen"
    for x, y in target["ends"]:
        page.mouse.click(x, y)
    expect(page.locator("#signupHint")).to_have_text("Initials first, then circle away.")
    expect(page.locator("#signupInitials")).to_be_focused()
    expect(page.locator("#notesBadge")).to_have_text("0")
    expect(html).to_have_attribute("data-intro", "sign")
    assert fake.sent("claim") == []

    # Typing in the card doesn't move the map; three letters sign them.
    cam = page.evaluate("({ ...window.__lf.cam })")
    page.locator("#signupInitials").press_sequentially("as")
    page.click("#signup button")
    expect(page.locator("#signupHint")).to_have_text("Use three letters, A to Z.")
    expect(signup).to_be_visible()
    expect(page.locator("#signupInitials")).to_be_focused()  # back to the box to fix them
    page.keyboard.press("End")
    page.keyboard.type("d")
    page.keyboard.press("Enter")
    expect(signup).to_be_hidden()
    expect(html).to_have_attribute("data-intro", "exploring")  # straight to the map
    expect(page.locator("#coach")).to_be_hidden()  # no second card to dismiss
    expect(page.locator("#toast")).not_to_have_class(re.compile(r"\bshow\b"))  # nor a note after it
    assert page.evaluate("localStorage.getItem('letterfield.coach.v1')") == "1"
    assert page.evaluate("({ ...window.__lf.cam })") == cam
    assert page.evaluate("localStorage.getItem('games.initials')") == '"ASD"'  # JSON, as the other games keep it
    expect(page.locator("#surveyMeName")).to_have_text("ASD")
    eventually(page, lambda: {m["initials"] for m in fake.sent("me")} >= {"ASD"})

    # Now the same taps circle the word.
    for x, y in target["ends"]:
        page.mouse.click(x, y)
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
    expect(page.locator("#findSay")).to_contain_text(target["word"])
    eventually(page, lambda: len(fake.sent("claim")) == 1)

    # Next time, straight to the map.
    page.reload()
    expect(html).to_have_attribute("data-intro", "exploring")
    expect(signup).to_be_hidden()
    expect(page.locator("#coach")).to_be_hidden()
    assert errors == []


def test_a_player_who_has_seen_the_tips_is_only_asked_for_initials(page: Page, site_url, errors):
    page.add_init_script("localStorage.setItem('letterfield.coach.v1', '1')")
    open_game(page, site_url, FakeSurvey())
    html = page.locator("html")
    expect(html).to_have_attribute("data-intro", "sign")
    expect(page.locator("#signupOnly")).to_be_visible()
    expect(page.locator("#signupOnly")).to_contain_text("Pick your initials to start.")
    expect(page.locator("#signupHow")).to_be_hidden()
    expect(page.locator("#signupKbd")).to_be_hidden()
    page.fill("#signupInitials", "TIP")
    page.click("#signup button")
    expect(html).to_have_attribute("data-intro", "exploring")
    expect(page.locator("#coach")).to_be_hidden()
    expect(page.locator("#toast")).not_to_have_class(re.compile(r"\bshow\b"))
    assert errors == []


def test_a_player_with_initials_from_another_game_only_sees_how_to_play(page: Page, site_url, errors):
    # games.initials is shared with the other games' leaderboards.
    page.add_init_script("localStorage.setItem('games.initials', JSON.stringify('LBD'))")
    page.set_viewport_size({"width": 1280, "height": 900})
    without_turnstile(page)
    fake = FakeSurvey()
    page.route_web_socket(re.compile(r"^wss://survey\.test/"), fake.handle)
    page.route(f"{SURVEY}/v1/survey/world", fake.handle_world)
    page.goto(f"{site_url}/letterfield?survey={SURVEY}#debug")
    html = page.locator("html")
    expect(html).to_have_attribute("data-intro", "coach")
    expect(page.locator("#coach")).to_be_visible()
    expect(page.locator("#signup")).to_be_hidden()
    page.click("#coachOk")
    expect(html).to_have_attribute("data-intro", "exploring")
    expect(page.locator("#coach")).to_be_hidden()
    page.reload()
    expect(html).to_have_attribute("data-intro", "exploring")
    assert errors == []


def test_initials_are_shared_with_the_leaderboard_games(page: Page, site_url, errors):
    # Letterfield once kept initials bare (ABC) where the other games keep
    # JSON ("ABC"), so neither could read the other's. Signed here, they
    # read as the leaderboard games read them (their store.get: JSON.parse).
    open_game(page, site_url, FakeSurvey())
    page.fill("#signupInitials", "SHR")
    page.click("#signup button")
    expect(page.locator("html")).to_have_attribute("data-intro", "exploring")
    assert page.evaluate("JSON.parse(localStorage.getItem('games.initials'))") == "SHR"

    # And a leaderboard's, saved as JSON (their store.set), sign Letterfield without asking.
    page.evaluate("localStorage.setItem('games.initials', JSON.stringify('ATC'))")
    page.goto(f"{site_url}/letterfield?survey={SURVEY}#debug")
    expect(page.locator("html")).not_to_have_attribute("data-intro", "sign")
    expect(page.locator("#signup")).to_be_hidden()
    assert errors == []


def test_initials_saved_bare_by_an_earlier_version_still_count(page: Page, site_url, errors):
    page.add_init_script("localStorage.setItem('games.initials', 'OLD'); localStorage.setItem('letterfield.coach.v1', '1')")
    open_game(page, site_url, FakeSurvey())
    expect(page.locator("html")).to_have_attribute("data-intro", "exploring")
    open_notes(page)
    expect(page.locator("#surveyMeName")).to_have_text("OLD")
    assert errors == []


def test_unreachable_survey_says_so_and_the_game_carries_on(page: Page, site_url):
    # Nothing answers: .test names never resolve. Skips the errors fixture,
    # because the browser logs each WebSocket that fails to connect.
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{site_url}/letterfield?survey={SURVEY}#debug")
    page.fill("#signupInitials", "OFF")
    page.click("#signup button")
    expect(page.locator("#surveyText")).to_have_text("Survey offline. Your finds still save in this browser.")
    expect(page.locator("#survey")).to_have_attribute("data-state", "offline")
    circle(page, hidden_words(page)[0])
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
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
    expect(page.locator("#surveyText")).to_contain_text("World: 412,883 of 1,119,752 charted · 3,201 online")
    expect(page.locator("#brandSub")).to_have_text("412,883 of 1,119,752 charted")
    circle(page, words[3])
    expect(page.locator("#brandSub")).to_have_text("412,884 of 1,119,752 charted")
    assert errors == []


def test_world_map_shows_where_people_are_and_flies_there(page: Page, site_url, errors):
    fake = FakeSurvey(world=world_map(charted={(0, 0): 60, (1, 0): 112, (-20, 30): 5},
                                      sectors=[[0, 0, 12], [-5, 7, 45]], players=57))
    open_game(page, site_url, fake)
    open_notes(page)
    page.click("#surveyMap summary")
    expect(page.locator("#worldNote")).to_have_text("57 surveyors in 2 sectors")
    expect(page.locator("#surveyText")).to_contain_text("World: 177 of 1,119,752 charted · 57 online")
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
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
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


@pytest.mark.parametrize("motion", ["no-preference", "reduce"])
def test_a_supernova_shows_rather_than_says_unless_motion_is_reduced(page: Page, site_url, errors, motion):
    words = territory_words(page, site_url)
    page.emulate_media(reduced_motion=motion)
    fake = FakeSurvey(claims=[[*w, 0, "MRW", NOW_MS - 60_000] for w in words[1:]])
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets)
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words) - 1}/{len(words)} charted")
    fake.sockets["0,0"].send(json.dumps({"t": "claimed", "c": [*words[0], 0, "SIS", NOW_MS], "by": "someone"}))
    banner = page.locator("#nova")
    expect(banner).to_have_attribute("role", "status")
    expect(page.locator("#novaText")).to_contain_text("the last by SIS", timeout=6000)  # a screen reader still hears it
    box = banner.bounding_box()
    if motion == "reduce":
        assert box["width"] > 200 and box["height"] > 40  # no shockwave to watch, so the words show
    else:
        assert box["width"] <= 1 and box["height"] <= 1
    expect(page.locator("#toast")).to_contain_text("Supernova · kept in your field notes", timeout=8000)
    assert errors == []


SHARE_SHEET_INIT = """
  window.__shared = [];
  Object.defineProperty(navigator, 'share', { value: data => { window.__shared.push(data); return Promise.resolve(); }, configurable: true });
"""


def test_a_supernova_you_saw_is_kept_in_your_notes_and_shares_its_card(page: Page, site_url, errors):
    words = territory_words(page, site_url)
    fake = FakeSurvey(claims=[[*w, 0, "MRW", NOW_MS - 60_000] for w in words[1:]])
    page.add_init_script(SHARE_SHEET_INIT)
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets)
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words) - 1}/{len(words)} charted")
    fake.sockets["0,0"].send(json.dumps({"t": "claimed", "c": [*words[0], 0, "SIS", NOW_MS], "by": "someone"}))
    expect(page.locator("#nova")).to_be_visible(timeout=6000)
    # Once the banner has gone, a note offers to share it.
    place = page.evaluate("window.__lf.territoryName(0, 0)")
    toast = page.locator("#toast")
    expect(toast).to_contain_text("Supernova · kept in your field notes", timeout=12000)
    expect(toast).to_contain_text(place)
    toast.locator(".share").click()
    page.wait_for_function("window.__shared.length === 1")
    shared = page.evaluate("window.__shared[0]")
    assert shared["text"] == f"{place} just went supernova in Letterfield’s shared survey: every hidden word charted, the last, {words[0][0]}, by SIS."
    assert shared["url"] == "https://share.michaelwarkentin.com/v/territory/0,0"
    # It's in the field notes, and stays there after a reload.
    open_notes(page)
    row = page.locator("#novaList li")
    expect(row).to_have_count(1)
    expect(row.locator(".find-word")).to_have_text(place)
    expect(row.locator(".find-meta")).to_have_text(f"Went supernova · {words[0][0]}, the last by SIS")
    page.reload()
    open_notes(page)
    expect(page.locator("#novaList li")).to_have_count(1)
    page.locator("#novaList .find-share").click()
    page.wait_for_function("window.__shared.length === 1")  # a fresh page: its first share
    assert page.evaluate("window.__shared[0].url") == "https://share.michaelwarkentin.com/v/territory/0,0"
    assert errors == []


def test_a_supernova_far_away_passes_as_a_distant_wave_and_is_kept(page: Page, site_url, errors):
    words = territory_words(page, site_url)
    fake = FakeSurvey(claims=[[*w, 0, "MRW", NOW_MS - 60_000] for w in words[1:]])
    page.add_init_script(SHARE_SHEET_INIT)
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets)
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words) - 1}/{len(words)} charted")
    page.evaluate("window.__lf.cam.x = 600; window.__lf.cam.y = 600")  # more than three territories off
    fake.sockets["0,0"].send(json.dumps({"t": "claimed", "c": [*words[0], 0, "", NOW_MS], "by": "someone"}))
    # No charge and no dimming: its shockwave comes straight in from the side it's on,
    # bursting on the first frame drawn rather than after a charge of NOVA_CHARGE (2.6 s).
    page.wait_for_function("window.__lf.nova()?.distant === true", timeout=3000)
    page.wait_for_function("window.__lf.nova()?.burst === true", timeout=1000)
    toast = page.locator("#toast")
    expect(toast).to_contain_text("Supernova · kept in your field notes", timeout=6000)
    toast.locator(".share").click()
    page.wait_for_function("window.__shared.length === 1")
    assert page.evaluate("window.__shared[0].text").endswith(f"the last, {words[0][0]}.")
    open_notes(page)
    expect(page.locator("#novaList .find-meta")).to_have_text(f"Went supernova · {words[0][0]}, every word charted")
    assert errors == []


# Territory (4, 0) is the top left corner of sector (1, 0), which a view
# centred at (100, 6) doesn't reach: it sees sectors (0, 0) and (0, -1) only,
# two territories off. Sector (0, 0) passes on its supernova.
NEIGHBOUR = (4, 0)
NEAR_CAM = "window.__lf.cam.x = 100; window.__lf.cam.y = 6"
COUNT_NOTES = """() => {
  window.__notes = [];
  new MutationObserver(() => {
    const t = document.getElementById('toast').textContent;
    if (/supernova/i.test(t) && window.__notes.at(-1) !== t) window.__notes.push(t);
  }).observe(document.getElementById('toast'), { childList: true, subtree: true, characterData: true });
}"""


def neighbour_word(page: Page) -> list:
    """A word hidden in territory NEIGHBOUR, as its last."""
    return page.evaluate("window.__lf.chunk(16, 0).words.map(o => [o.w, o.x, o.y, o.d])[0]")


def test_a_supernova_in_a_neighbouring_sector_sweeps_across_the_view(page: Page, site_url, errors):
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets)
    page.evaluate(NEAR_CAM)
    assert "1,0" not in fake.sockets
    word = neighbour_word(page)
    fake.nova("0,0", *NEIGHBOUR, word, "SIS")
    expect(page.locator("#nova")).to_be_visible(timeout=6000)
    place = page.evaluate("window.__lf.territoryName(4, 0)")
    expect(page.locator("#novaText")).to_have_text(f"{place} · every hidden word charted, the last by SIS")
    assert page.evaluate("[window.__lf.nova()?.rx, window.__lf.nova()?.ry]") == list(NEIGHBOUR)
    # It's a remnant now, though this page holds none of that sector's claims, and in your notes.
    assert "4,0" in page.evaluate("window.__lf.remnants()")
    open_notes(page)
    expect(page.locator("#novaList li")).to_have_count(1)
    expect(page.locator("#novaList .find-meta")).to_have_text(f"Went supernova · {word[0]}, the last by SIS")
    assert errors == []


def test_supernovas_further_off_pass_at_most_one_a_minute_and_all_are_kept(page: Page, site_url, errors):
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets)
    page.evaluate(COUNT_NOTES)
    # From the start at (6, 6), territory (4, 0) is four territories off: its wave passes.
    word = neighbour_word(page)
    fake.nova("0,0", *NEIGHBOUR, word, "SIS")
    page.wait_for_function("window.__lf.nova()?.rx === 4", timeout=3000)
    assert page.evaluate("window.__lf.nova().distant")
    assert "4,0" in page.evaluate("window.__lf.remnants()")
    expect(page.locator("#toast")).to_contain_text("Supernova · kept in your field notes", timeout=6000)
    page.wait_for_function("window.__lf.nova() === null", timeout=6000)
    # Another neighbour passing on the same one changes nothing.
    fake.nova("0,-1", *NEIGHBOUR, word, "SIS")
    # One far across the shared world, from the Atlas, inside the minute: kept, but quietly.
    far = page.evaluate("window.__lf.chunk(200, -120).words.map(o => [o.w, o.x, o.y, o.d])[0]")
    fake.nova("0,0", 50, -30, far, "AMY", ago=4000)
    page.wait_for_timeout(1500)
    assert page.evaluate("window.__lf.nova()") is None
    assert len(page.evaluate("window.__notes")) == 1
    assert sorted(page.evaluate("window.__lf.novas().map(n => n.rx + ',' + n.ry)")) == ["4,0", "50,-30"]
    # A minute on, the next one passes, but not one that went off too long ago to be news.
    page.evaluate("window.__lf.distantAt(-Infinity)")
    old = page.evaluate("window.__lf.chunk(-200, 120).words.map(o => [o.w, o.x, o.y, o.d])[0]")
    fake.nova("0,0", -50, 30, old, "", ago=30_000)
    page.wait_for_timeout(800)
    assert page.evaluate("window.__lf.nova()") is None
    assert len(page.evaluate("window.__lf.novas()")) == 3
    news = page.evaluate("window.__lf.chunk(-200, -120).words.map(o => [o.w, o.x, o.y, o.d])[0]")
    fake.nova("0,0", -50, -30, news, "", ago=9000)
    page.wait_for_function("window.__lf.nova()?.rx === -50", timeout=3000)
    open_notes(page)
    expect(page.locator("#novaList li")).to_have_count(4)
    assert errors == []


def test_a_distant_supernova_comes_in_from_its_side(page: Page, site_url, errors):
    fake = FakeSurvey()
    open_game(page, site_url, fake, viewport={"width": 390, "height": 844})
    eventually(page, lambda: "0,0" in fake.sockets)
    # Far off to the east, 40 territories away: its wave starts just off the right of the screen.
    word = page.evaluate("window.__lf.chunk(160, 0).words.map(o => [o.w, o.x, o.y, o.d])[0]")
    fake.nova("0,0", 40, 0, word, "", ago=3000)
    page.wait_for_function("window.__lf.nova()?.distant === true", timeout=3000)
    page.wait_for_function("window.__lf.novaWave()?.R > 0", timeout=2000)  # drawn, and on its way
    wave = page.evaluate("window.__lf.novaWave()")
    assert wave["virtual"] and 390 < wave["cx"] < 390 * 3
    page.wait_for_timeout(1200)
    later = page.evaluate("window.__lf.novaWave()")
    assert later["R"] > wave["R"] and later["amp"] > 0  # sweeping across, still strong
    assert errors == []


def test_two_neighbours_passing_on_one_supernova_play_it_once(page: Page, site_url, errors):
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets and "0,-1" in fake.sockets)
    page.evaluate(NEAR_CAM)
    word = neighbour_word(page)
    fake.nova("0,0", *NEIGHBOUR, word, "SIS")
    expect(page.locator("#nova")).to_be_visible(timeout=6000)
    started = page.evaluate("window.__lf.nova().t0")
    fake.nova("0,-1", *NEIGHBOUR, word, "SIS")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__lf.nova()?.t0") == started
    assert errors == []


@pytest.mark.parametrize("first", ["claimed", "nova"])
def test_the_claim_and_a_neighbours_news_of_it_play_it_once(page: Page, site_url, errors, first):
    words = territory_words(page, site_url)
    fake = FakeSurvey(claims=[[*w, 0, "MRW", NOW_MS - 60_000] for w in words[1:]])
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets and "-1,0" in fake.sockets)
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words) - 1}/{len(words)} charted")
    page.evaluate(COUNT_NOTES)
    claimed = json.dumps({"t": "claimed", "c": [*words[0], 0, "SIS", NOW_MS], "by": "someone"})
    send = {"claimed": lambda: fake.sockets["0,0"].send(claimed), "nova": lambda: fake.nova("-1,0", 0, 0, words[0], "SIS")}
    send[first]()
    send["nova" if first == "claimed" else "claimed"]()
    expect(page.locator("#nova")).to_be_visible(timeout=6000)
    started = page.evaluate("window.__lf.nova().t0")
    expect(page.locator("#novaText")).to_contain_text("the last by SIS")
    expect(page.locator("#toast")).to_contain_text("Supernova · kept in your field notes", timeout=12000)
    page.wait_for_timeout(500)
    assert page.evaluate("window.__notes").count(page.evaluate("window.__notes")[0]) == 1
    assert len(page.evaluate("window.__notes")) == 1
    assert page.evaluate("window.__lf.nova()?.t0 ?? null") in (None, started)
    open_notes(page)
    expect(page.locator("#novaList li")).to_have_count(1)
    assert errors == []


SCREEN_OF = """([x, y]) => {
  const cam = window.__lf.cam, dock = document.body.classList.contains('docked') ? 340 : 0;
  return [(x - cam.x) * cam.cs + (innerWidth - dock) / 2, (y - cam.y) * cam.cs + (m => m.getBoundingClientRect().top + m.clientHeight / 2)(document.getElementById('map'))];
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


OVERLAP = """([a, b]) => {
  const r = document.querySelector(a).getBoundingClientRect(), q = document.querySelector(b).getBoundingClientRect();
  return r.width > 0 && q.width > 0 && r.left < q.right && q.left < r.right && r.top < q.bottom && q.top < r.bottom;
}"""
# What a tap at the middle of each of an element's chips lands on: true where it reaches that chip.
TAPS_REACH = """sel => [...document.querySelectorAll(sel)].map(el => {
  const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  return x < 0 || x >= innerWidth ? true : el.contains(document.elementFromPoint(x, y));  // off screen at the edge itself
})"""


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
    page.add_init_script("localStorage.setItem('games.initials', JSON.stringify('MLW'))")
    with_turnstile(page, "interactive")
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#surveyCheck")).to_have_class(re.compile("asking"))
    expect(page.locator("#surveyCheck")).to_contain_text("One tap to join the shared survey")
    expect(page.locator("#surveyText")).to_have_text("Checking this is a person, not a bot…")
    for other in ["#bar", "#signup", "#notes"]:
        assert not page.evaluate(OVERLAP, ["#surveyCheck", other]), f"the box covers {other}"
    assert fake.sectors == []
    page.evaluate("window.__tsSolve()")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    expect(page.locator("#surveyCheck")).not_to_have_class(re.compile("asking"))
    assert errors == []


def test_turnstile_box_keeps_clear_of_the_game_and_goes_once_passed(page: Page, site_url, errors):
    # On a phone, Turnstile's box once stayed over the word legend after "Success!".
    phone = {"width": 375, "height": 667}
    with_turnstile(page, "interactive")
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}", viewport=phone)
    check = page.locator("#surveyCheck")
    expect(check).to_have_class(re.compile("asking"))
    # A first visit asks one thing at a time: the box waits for the card asking for initials.
    expect(page.locator("#signup")).to_be_visible()
    expect(check).to_be_hidden()
    expect(page.locator(".fake-turnstile")).to_be_hidden()
    page.fill("#signupInitials", "NEW")
    page.click("#signup button")
    expect(page.locator("#signup")).to_be_hidden()
    expect(page.locator(".fake-turnstile")).to_be_visible()
    # While it asks, it's a small panel with its reason, clear of the bottom bar,
    # and of the tools' stack once that's open.
    expect(check.locator("p")).to_be_visible()
    expect(check.locator("p")).to_have_text("One tap to join the shared survey")
    box = check.bounding_box()
    assert box["x"] >= 16 and box["x"] + box["width"] <= phone["width"] - 16
    for other in ["#bar", ".cartouche", "#notesToggle"]:
        assert not page.evaluate(OVERLAP, ["#surveyCheck", other]), f"the box covers {other}"
    page.click("#toolsBtn")
    expect(page.locator("#toolsBtn")).to_have_attribute("aria-expanded", "true")
    for other in ["#bar", "#toolStack", ".cartouche", "#notesToggle"]:
        assert not page.evaluate(OVERLAP, ["#surveyCheck", other]), f"the box covers {other} with the tools open"
    page.click("#toolsBtn")

    page.evaluate("window.__tsSolve()")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    expect(page.locator("html")).to_have_attribute("data-pass", "good")
    # "Success!" shows for a moment, then the widget and its box are gone.
    expect(page.locator(".fake-turnstile")).to_have_count(0, timeout=3000)
    assert page.evaluate("window.__tsRemoved") == ["w1"]
    expect(check).not_to_have_class(re.compile("shown|asking"))
    assert check.bounding_box() is None or check.bounding_box()["height"] == 0
    # Every word in the legend takes a tap where it is.
    expect(page.locator("#legendList .chip").first).to_be_visible()
    assert all(page.evaluate(TAPS_REACH, "#legendList .chip"))
    assert errors == []


def test_turnstile_box_goes_when_a_player_already_in_the_survey_is_not_asked(page: Page, site_url, errors):
    # A pass that runs out while the player is in the survey: a check that
    # wants a tap is dropped while passes aren't required, and nothing is left on screen.
    page.add_init_script("""localStorage.setItem('letterfield.surveyPass.v1',
      JSON.stringify({ pass: 'old-pass', expires: Date.now() + 62000 }))""")
    with_turnstile(page, "interactive")
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}", viewport={"width": 375, "height": 667})
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    expect(page.locator("html")).to_have_attribute("data-pass", "failed", timeout=8000)
    assert page.evaluate("window.__tsRenders.length") == 1
    expect(page.locator(".fake-turnstile")).to_have_count(0)
    expect(page.locator("#surveyCheck")).not_to_have_class(re.compile("shown|asking"))
    assert all(page.evaluate(TAPS_REACH, "#legendList .chip"))
    assert errors == []


def test_turnstile_box_asks_a_player_already_in_the_survey_once_passes_are_required(page: Page, site_url, errors):
    # A sector turns the stored pass away: passes are required, so the player is asked to stay, then the box goes.
    page.add_init_script("""localStorage.setItem('letterfield.surveyPass.v1',
      JSON.stringify({ pass: 'old-pass', expires: Date.now() + 1800000 }));
      localStorage.setItem('games.initials', JSON.stringify('MLW'))""")
    with_turnstile(page, "interactive")
    fake = FakeSurvey(refuse_passes={"old-pass"}, require_pass=True)
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}", viewport={"width": 375, "height": 667})
    expect(page.locator("#surveyCheck")).to_have_class(re.compile("asking"))
    expect(page.locator("#surveyCheck p")).to_be_visible()
    for other in ["#bar"]:
        assert not page.evaluate(OVERLAP, ["#surveyCheck", other]), f"the box covers {other}"
    page.evaluate("window.__tsSolve()")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    expect(page.locator(".fake-turnstile")).to_have_count(0, timeout=3000)
    expect(page.locator("#surveyCheck")).not_to_have_class(re.compile("shown|asking"))
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
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
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
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
    assert fake.sectors == []


# ---------- The survey's state machines ----------
# Each sector's link (connecting, open, live, backoff, closed), each of our
# claims (queued, sent, unanswered, answered) and the pass (on <html data-pass>)
# are state machines in the page; window.__lf reports them.

HIDE = """hidden => {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event('visibilitychange'));
}"""


def test_words_circled_while_joining_are_claimed_once_the_sector_is_live(page: Page, site_url, errors):
    words = known_words(page, site_url)[:6]
    # Every sector holds back its hello, and takes claims only as fast as a real one does.
    fake = FakeSurvey(hold=lambda url: True, rate=True)
    open_game(page, site_url, fake)
    eventually(page, lambda: len(fake.held) == 4)
    expect(page.locator("#surveyText")).to_have_text("Joining the survey…")
    for word in words:
        circle(page, word)
    page.wait_for_timeout(300)
    assert fake.sent("claim") == []  # nothing to send them on yet
    fake.hold = None
    fake.welcome()
    # Once the sector's live they all go, as fast as it takes them, and none is turned away.
    eventually(page, lambda: len(fake.sent("claim")) == len(words), 10000)
    assert [m["w"] for m in fake.sent("claim")] == [w[0] for w in words]
    expect(page.locator("#surveyText")).to_contain_text(f"{len(words)} words charted first by you")
    assert page.evaluate("window.__lf.outbox()") == []
    assert page.evaluate("window.__lf.linkStates()") == {"0,0": "live", "-1,0": "live", "0,-1": "live", "-1,-1": "live"}
    assert errors == []


def test_a_claim_whose_answer_was_lost_with_its_socket_is_still_credited(page: Page, site_url, errors):
    word = known_words(page, site_url)[0]
    page.add_init_script("localStorage.setItem('games.initials', JSON.stringify('ZED'))")
    fake = FakeSurvey(lose="answer")  # the sector keeps the claim, but the socket drops before its answer
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    circle(page, word)
    eventually(page, lambda: len(fake.claims) == 1)
    assert fake.claims[0][5] == "ZED"
    page.evaluate(HIDE, True)  # switching apps closes every socket
    page.evaluate(HIDE, False)
    expect(page.locator("#surveyText")).to_contain_text("1 word charted first by you")
    assert page.evaluate("[...window.__lf.found.values()][0].f") == 1
    expect(page.locator("#findSay")).to_contain_text("First to chart it")
    assert len(fake.sent("claim")) == 1  # the sector already had it: not sent again
    assert errors == []


def test_a_claim_lost_on_the_way_is_sent_again_when_the_sector_is_rejoined(page: Page, site_url, errors):
    word = known_words(page, site_url)[0]
    fake = FakeSurvey(lose="claim")
    open_game(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    circle(page, word)
    eventually(page, lambda: len(fake.sent("claim")) == 1)
    fake.lose = None
    page.evaluate(HIDE, True)
    page.evaluate(HIDE, False)
    eventually(page, lambda: len(fake.sent("claim")) == 2)
    expect(page.locator("#findSay")).to_contain_text("First to chart it")
    assert page.evaluate("window.__lf.outbox()") == []
    assert errors == []


def test_the_panel_says_its_joining_while_it_looks_for_where_to_start(page: Page, site_url, errors):
    page.set_viewport_size({"width": 1280, "height": 900})
    without_turnstile(page)
    fake = FakeSurvey()
    asked: list[Route] = []
    page.route_web_socket(re.compile(r"^wss://survey\.test/"), fake.handle)
    page.route(f"{SURVEY}/v1/survey/world", lambda route: asked.append(route))  # a new player waits to hear where to start
    page.goto(f"{site_url}/letterfield?survey={SURVEY}#debug")
    eventually(page, lambda: asked)
    expect(page.locator("#surveyText")).to_have_text("Joining the survey…")
    expect(page.locator("#survey")).to_have_attribute("data-state", "connecting")
    fake.handle_world(asked[0])
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert errors == []


def test_a_device_clock_an_hour_fast_gets_one_pass_and_joins(page: Page, site_url, errors):
    # The Worker gives a pass's end on its own clock; this device's says an hour later.
    page.clock.install(time=time.time() + 3600)
    desk = with_turnstile(page)
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    page.wait_for_timeout(2500)
    assert len(desk.issued) == 1, "one pass covers the hour, whatever the device's clock says"
    assert page.evaluate("window.__tsRenders.length") == 1
    assert all(url.endswith(f"?pass={desk.issued[0]}") for url in fake.urls)
    expect(page.locator("html")).to_have_attribute("data-pass", "good")
    assert errors == []


def test_a_late_refusal_of_an_old_pass_leaves_the_new_one_alone(page: Page, site_url, errors):
    # A stored pass the Worker no longer takes: every sector refuses it, but sector 0,0's refusal
    # comes back only after the new pass is in and the other sectors have joined with it.
    page.add_init_script("""localStorage.setItem('letterfield.surveyPass.v1',
      JSON.stringify({ pass: 'old-pass', expires: Date.now() + 1800000 }))""")
    desk = with_turnstile(page)
    fake = FakeSurvey(refuse_passes={"old-pass"}, hold=lambda url: url.endswith("/0/0?pass=old-pass"))
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    eventually(page, lambda: len(fake.held) == 1 and len(desk.issued) == 1 and len(fake.sectors) == 3)
    fake.hold = None
    fake.welcome()
    page.wait_for_function("window.__lf.links.get('0,0')?.you", timeout=5000)
    assert page.evaluate("JSON.parse(localStorage.getItem('letterfield.surveyPass.v1')).pass") == desk.issued[0]
    assert len(desk.issued) == 1, "no second challenge"
    assert fake.urls[-1].endswith(f"/0/0?pass={desk.issued[0]}")
    expect(page.locator("html")).to_have_attribute("data-pass", "good")
    assert errors == []


def test_a_check_nobody_taps_goes_away_and_isnt_asked_for_while_in_the_survey(page: Page, site_url, errors):
    page.clock.install()
    desk = with_turnstile(page, "interactive")
    fake = FakeSurvey()
    open_game(page, site_url, fake, f"&turnstile={SITE_KEY}")
    expect(page.locator("#surveyCheck")).to_have_class(re.compile("asking"))
    page.clock.fast_forward("02:01")  # nobody taps
    expect(page.locator("#surveyCheck")).not_to_have_class(re.compile("asking"))
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")  # joined without a pass
    assert page.evaluate("window.__tsRemoved") == ["w1"], "the widget goes with its try"
    expect(page.locator("html")).to_have_attribute("data-pass", "failed")
    # Asked again later, a tap isn't asked for while the player is already in the survey.
    page.clock.fast_forward("00:33")
    page.wait_for_function("window.__tsRenders.length === 2", timeout=5000)
    page.wait_for_function("window.__tsRemoved && window.__tsRemoved.length === 2", timeout=5000)
    expect(page.locator("#surveyCheck")).not_to_have_class(re.compile("asking"))
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert desk.tokens == []
    assert errors == []


def test_word_list_leaves_out_words_anyone_has_charted(page: Page, site_url, errors):
    words = territory_words(page, site_url)
    near = [w for w in words if 0 <= w[1] < 12 and 0 <= w[2] < 12]  # the chunk the map opens on
    free = near[::2]
    fake = FakeSurvey(claims=[[*w, 0, "MRW", NOW_MS - 60_000] for w in words if w not in free])
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets)
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words) - len(free)}/{len(words)} charted")
    chips = page.locator("#legendList .chip")

    # In view, none of the charted ones (words of the territories beside it
    # may show too).
    expect(chips.first).to_be_visible()
    named = chips.all_inner_texts()
    charted = {w[0] for w in words} - {w[0] for w in free}
    assert not charted & set(named), named
    assert {w[0] for w in free} & set(named), named
    # The count is of every such word in view; the list names the nearest 14.
    left = int(page.locator("#legendCount").inner_text().split()[0])
    assert left == len(named) if len(named) < 14 else left >= 14, (left, named)

    # Across the territory, the same.
    page.click("#listWhole")
    expect(chips).to_have_text(sorted(w[0] for w in free))
    expect(page.locator("#legendCount")).to_have_text(f"{len(free)} left")

    # A word someone charts just now drops out, and so does one you circle.
    fake.sockets["0,0"].send(json.dumps({"t": "claimed", "c": [*free[0], 0, "SIS", NOW_MS], "by": "someone"}))
    expect(chips).to_have_text(sorted(w[0] for w in free[1:]))
    for w in free[1:]:
        circle(page, w)
    expect(chips).to_have_count(0)
    expect(page.locator("#legendList .legend-note")).to_have_text("Every word here is charted.")
    assert errors == []


NOTES_LAYOUT_JS = """() => {
  const box = el => el.getBoundingClientRect();
  const notes = document.getElementById('notes'), filters = document.getElementById('filters');
  const lis = [...document.querySelectorAll('#finds > li')];
  return {
    survey: box(document.getElementById('survey')).toJSON(),
    filters: box(filters).toJSON(),
    // Every section's content fits its box: none is squashed below its content's height.
    squashed: [...notes.children].filter(el => !el.hidden && el.id !== 'finds' && el.scrollHeight > el.clientHeight + 1).map(el => el.id || el.className),
    chip: box(filters.querySelector('.filter')).height,
    first: box(lis[0]).toJSON(), last: box(lis[lis.length - 1]).toJSON(),
    notes: box(notes).toJSON(), n: lis.length,
  };
}"""


def fill_notes(page: Page, count: int = 40) -> None:
    """Circles `count` words from the chunks around the start, across several themes."""
    page.evaluate("""(count) => {
      let n = 0;
      for (let r = 0; n < count && r < 4; r++)
        for (let cx = -r; cx <= r; cx++) for (let cy = -r; cy <= r; cy++) {
          if (Math.max(Math.abs(cx), Math.abs(cy)) !== r) continue;
          for (const o of window.__lf.chunk(cx, cy).words) {
            if (n >= count) return;
            window.__lf.collect(o.w, o.x, o.y, o.d, false); n++;
          }
        }
    }""", count)


def notes_sections_keep_their_height(page: Page) -> dict:
    """No section of the drawer is squashed or overlaps the next; returns the measures."""
    m = page.evaluate(NOTES_LAYOUT_JS)
    assert m["n"] >= 30, m
    # The theme chips keep their full height instead of being squashed to a sliver...
    assert m["squashed"] == [], m
    assert m["chip"] >= 24 and m["filters"]["height"] >= m["chip"], m
    # ...and nothing overlaps the section below it.
    assert m["survey"]["bottom"] <= m["filters"]["top"] + 0.5, m
    assert m["filters"]["bottom"] <= m["first"]["top"] + 0.5, m
    return m


def test_field_notes_scroll_whole_on_a_phone_with_the_survey(page: Page, site_url, errors):
    open_game(page, site_url, FakeSurvey(), viewport={"width": 375, "height": 812})
    fill_notes(page)
    open_notes(page)
    expect(page.locator("#survey")).to_be_visible()
    expect(page.locator("#filters .filter").nth(2)).to_be_attached()
    page.wait_for_timeout(400)  # the drawer slides up
    notes_sections_keep_their_height(page)

    # An up-and-down scroll over the theme chips scrolls the drawer, not the row;
    # a sideways one scrolls the row.
    scroll = "() => [document.getElementById('notes').scrollTop, document.getElementById('filters').scrollTop, document.getElementById('filters').scrollLeft]"
    page.hover("#filters .filter >> nth=1")
    page.mouse.wheel(0, 200)
    eventually(page, lambda: page.evaluate(scroll)[0] > 0)
    assert page.evaluate(scroll)[1] == 0
    page.evaluate("document.getElementById('notes').scrollTop = 0")
    page.hover("#filters .filter >> nth=1")
    page.mouse.wheel(200, 0)
    eventually(page, lambda: page.evaluate(scroll)[2] > 0)
    assert page.evaluate(scroll)[0] == 0

    # The drawer scrolls down to the last find, and the feedback line under it,
    # with the theme chips held at its top.
    page.evaluate("document.getElementById('filters').scrollLeft = 0; document.getElementById('notes').scrollTop = 1e6")
    page.wait_for_timeout(100)
    m = page.evaluate(NOTES_LAYOUT_JS)
    assert m["last"]["bottom"] <= m["notes"]["bottom"], m
    expect(page.locator("#sync")).to_be_in_viewport()
    assert abs(m["filters"]["top"] - m["notes"]["top"]) <= 1, m
    expect(page.locator("#filters .filter").first).to_be_in_viewport()

    # Docked beside the map on a computer, the same.
    page.evaluate("document.getElementById('notes').scrollTop = 0")
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_timeout(400)
    notes_sections_keep_their_height(page)
    assert errors == []


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_a_note_never_covers_the_box_for_your_initials(page: Page, site_url, errors, size):
    words = known_words(page, site_url)
    fake = FakeSurvey(claims=[[*words[0], 0, "MRW", NOW_MS - 60_000]])
    open_game(page, site_url, fake, viewport={"width": size[0], "height": size[1]})
    expect(page.locator("#signup")).to_be_visible()
    circle(page, words[0])
    expect(page.locator("#toast")).to_have_class(re.compile(r"\bshow\b"))
    page.wait_for_timeout(300)  # its slide in
    toast, box = page.locator("#toast").bounding_box(), page.locator("#signup").bounding_box()
    apart = (toast["y"] >= box["y"] + box["height"] or toast["y"] + toast["height"] <= box["y"]
             or toast["x"] >= box["x"] + box["width"] or toast["x"] + toast["width"] <= box["x"])
    assert apart, (toast, box)
    assert errors == []


TERRITORY_WORDS = """() => {
  const out = [];
  for (let cy = 0; cy < 4; cy++) for (let cx = 0; cx < 4; cx++) for (const o of window.__lf.chunk(cx, cy).words) out.push([o.w, o.x, o.y, o.d]);
  return out;
}"""


def test_a_territory_charted_in_full_is_a_remnant(page: Page, site_url, errors):
    page.goto(f"{site_url}/letterfield#debug")
    words = page.evaluate(TERRITORY_WORDS)
    page.goto("about:blank")
    # All but one charted: not yet.
    fake = FakeSurvey(claims=[[w, x, y, d, 0, "ZED", NOW_MS - 1000 + i] for i, (w, x, y, d) in enumerate(words[1:])])
    open_game(page, site_url, fake)
    page.wait_for_function(f"window.__lf.claims.size >= {len(words) - 1}")
    assert page.evaluate("window.__lf.remnants()") == []
    page.goto("about:blank")
    fake = FakeSurvey(claims=[[w, x, y, d, 0, "ZED", NOW_MS - 1000 + i] for i, (w, x, y, d) in enumerate(words)])
    open_game(page, site_url, fake)
    page.wait_for_function(f"window.__lf.claims.size >= {len(words)}")
    assert page.evaluate("window.__lf.remnants()") == ["0,0"]
    assert errors == []


def test_the_world_map_shows_territories_charted_in_full_far_afield(page: Page, site_url, errors):
    page.goto(f"{site_url}/letterfield#debug")
    total = page.evaluate("(() => { let t = 0; for (let cy = 80; cy < 84; cy++) for (let cx = -40; cx < -36; cx++) t += window.__lf.chunk(cx, cy).words.length; return t; })()")
    page.goto("about:blank")
    fake = FakeSurvey(world=world_map(charted={(-10, 20): total, (-11, 20): total - 1}))
    open_game(page, site_url, fake)
    open_notes(page)
    page.click("#surveyMap summary")
    page.wait_for_function("window.__lf.remnants().length > 0")
    assert page.evaluate("window.__lf.remnants()") == ["-10,20"]
    assert errors == []
