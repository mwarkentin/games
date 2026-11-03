"""War rooms in the page, against a fake of the room (tests/fake_war_room.py).

Tests that make the fake answer 4xx, or fail requests, skip the `errors`
fixture, because the browser logs those as console errors.
"""

from __future__ import annotations

from fake_leaderboard import API
from fake_war_room import FakeWarRoom, card
from playwright.sync_api import Page, expect

STATE = "window.__war.state()"


def open_war(page: Page, site_url: str, fake: FakeWarRoom, query: str = "") -> None:
    fake.route(page)
    page.goto(f"{site_url}/war?rooms={API}{query}#debug")


def start_room(page: Page, name: str = "Dana") -> None:
    page.fill("#nameInput", name)
    page.click("#newRoomBtn")
    expect(page.locator("#lobby")).to_be_visible()


def join_room(page: Page, code: str, name: str) -> None:
    page.fill("#nameInput", name)
    page.fill("#codeInput", code.lower())
    page.click("#joinBtn")
    expect(page.locator("#lobby")).to_be_visible()


def hold_slam(page: Page, ms: int) -> None:
    box = page.locator("#slamBtn").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(ms)
    page.mouse.up()


def test_start_a_room_add_bots_and_play_a_battle(page: Page, site_url, errors):
    fake = FakeWarRoom()
    open_war(page, site_url, fake)
    expect(page.locator("#friends")).to_be_visible()
    start_room(page)
    expect(page.locator("#lobbyCode")).to_have_text("K7QP")
    expect(page.locator("#people")).to_contain_text("Dana (host)")
    hello = fake.messages("hello")[0]
    assert hello["name"] == "Dana" and len(hello["token"]) >= 16

    page.click("#botMore")
    expect(page.locator("#people .person")).to_have_count(2)
    page.click("#roomLength button[data-length=quick]")
    expect(page.locator("#roomLength button[data-length=quick]")).to_have_attribute("aria-pressed", "true")
    page.click("#dealBtn")
    expect(page.locator("#app")).to_be_visible()
    expect(page.locator("#roomTag")).to_have_text("K7QP")
    expect(page.locator("#battleSub")).to_contain_text("of 20")

    page.wait_for_function(f"{STATE}.canSlam")
    hold_slam(page, 1000)
    page.wait_for_function(f"{STATE}.slams[0] !== undefined")
    slam = fake.messages("slam")[0]
    assert slam["power"] > 50
    assert fake.messages("charge"), "the room hears you charging up"

    # The room plays the battle out: your ace beats the bot's three.
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 0, "winner": 0, "tied": [0], "gods": False, "pot": 2,
        "plays": [[0, 0, card(12), slam["power"], 0, 0], [1, 0, card(1), 100, 1, 0]],
        "counts": [27, 25], "out": [], "next": fake.stage(2, opens_in=2400),
    })
    expect(page.locator("#banner")).to_have_text("YOU WIN!")
    expect(page.locator("#myLabel")).to_contain_text("27 cards")
    expect(page.locator("#opponents .tile .tcount")).to_have_text("25")
    page.wait_for_function(f"{STATE}.battle === 2 && {STATE}.canSlam")
    assert errors == []


def test_friends_join_with_the_code_and_see_each_other(page: Page, browser, site_url, errors):
    fake = FakeWarRoom()
    open_war(page, site_url, fake)
    start_room(page, "Dana")

    guest_context = browser.new_context(viewport={"width": 375, "height": 740})
    guest = guest_context.new_page()
    open_war(guest, site_url, fake)
    join_room(guest, "k7qp", "Bob")
    expect(guest.locator("#lobbyNote")).to_have_text("Waiting for Dana to deal.")
    expect(guest.locator("#dealBtn")).to_be_hidden()
    expect(page.locator("#people .person")).to_have_count(2)

    page.click("#dealBtn")
    expect(guest.locator("#app")).to_be_visible()
    expect(guest.locator("#opponents .tile")).to_have_count(1)
    expect(guest.locator("#opponents .tile")).to_contain_text("Dana")

    # Dana's slam shows up on Bob's screen.
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(180)")
    expect(guest.locator("#opponents .tile .tstat")).to_contain_text("COSMIC SLAM")

    # Cheers fly across.
    guest.click("#cheers button >> nth=0")
    page.wait_for_selector("#fx .floaty")

    # A war, then the end of the game: Bob waits for Dana to deal again.
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 0, "winner": None, "tied": [0, 1], "gods": False, "pot": 2,
        "plays": [[0, 0, card(9), 180, 0, 0], [1, 0, card(9, 1), 0, 0, 1]],
        "counts": [25, 25], "next": fake.stage(1, stage=1, fighters=[0, 1], opens_in=500),
    })
    expect(guest.locator("#banner")).to_have_text("WAR!")
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 1, "winner": 0, "tied": [0], "gods": False, "pot": 10,
        "plays": [[0, 3, card(12), 0, 0, 1], [1, 3, card(4), 0, 0, 1]], "counts": [31, 21], "out": [],
        "over": {
            "winners": [0], "order": [0, 1], "counts": [31, 21], "out": [0, 0],
            "battles": 1, "wars": 1, "biggest": 2, "deepest": 1,
        },
    })
    expect(guest.locator("#over")).to_be_visible()
    expect(guest.locator("#overTitle")).to_have_text("Dana wins!")
    expect(guest.locator("#overNote")).to_have_text("Waiting for Dana to deal again…")
    expect(guest.locator("#againBtn")).to_be_hidden()
    expect(page.locator("#overTitle")).to_have_text("Victory!")
    played = guest.evaluate("JSON.parse(localStorage.getItem('war:history'))[0]")
    assert (played["mode"], played["code"], played["place"], played["won"]) == ("room", "K7QP", 2, False)
    page.click("#againBtn")
    expect(guest.locator("#over")).to_be_hidden()
    guest.wait_for_function(f"{STATE}.battle === 1 && {STATE}.phase === 'playing'")
    guest_context.close()
    assert errors == []


def test_latecomers_watch(page: Page, site_url, errors):
    fake = FakeWarRoom()
    fake.players = [{"name": "Dana", "avatar": 0, "bot": False, "token": "dana-token-123456"},
                    {"name": "Bot 1", "avatar": 23, "bot": True, "token": None}]
    fake.deal()
    open_war(page, site_url, fake)
    page.fill("#nameInput", "Eve")
    page.fill("#codeInput", "K7QP")
    page.click("#joinBtn")
    expect(page.locator("#app")).to_be_visible()
    expect(page.locator("#meNote")).to_contain_text("watching")
    expect(page.locator("#opponents .tile")).to_have_count(2)
    expect(page.locator("#slamBtn")).to_be_disabled()
    # Watching a game that ends doesn't count as playing it.
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 0, "winner": 0, "tied": [0], "gods": False, "pot": 2,
        "plays": [[0, 0, card(12), 50, 0, 0], [1, 0, card(1), 50, 0, 0]], "counts": [27, 25], "out": [],
        "over": {"winners": [0], "order": [0, 1], "counts": [27, 25], "out": [0, 0],
                 "battles": 1, "wars": 0, "biggest": 0, "deepest": 0},
    })
    expect(page.locator("#over")).to_be_visible()
    assert page.evaluate("localStorage.getItem('war:history')") is None
    assert page.evaluate("localStorage.getItem('war:stats')") is None
    assert errors == []


def test_an_invite_link_fills_in_the_code(page: Page, site_url, errors):
    open_war(page, site_url, FakeWarRoom(), "&room=k7qp")
    expect(page.locator("#codeInput")).to_have_value("K7QP")
    expect(page.locator("#joinBtn")).to_have_text("Join room K7QP")


def test_a_name_is_needed(page: Page, site_url, errors):
    open_war(page, site_url, FakeWarRoom())
    page.fill("#nameInput", "")
    page.click("#newRoomBtn")
    expect(page.locator("#friendsErr")).to_contain_text("Pick a name")
    expect(page.locator("#lobby")).to_be_hidden()
    assert errors == []


def test_an_unknown_code_says_so(page: Page, site_url):
    open_war(page, site_url, FakeWarRoom())
    page.fill("#nameInput", "Dana")
    page.fill("#codeInput", "ZZZZ")
    page.click("#joinBtn")
    expect(page.locator("#friendsErr")).to_have_text("There’s no room ZZZZ. Check the code?")
    expect(page.locator("#lobby")).to_be_hidden()


def test_an_unreachable_server_says_so_and_solo_still_works(page: Page, site_url):
    page.route(f"{API}/**", lambda route: route.abort())
    page.goto(f"{site_url}/war?rooms={API}#debug")
    page.fill("#nameInput", "Dana")
    page.click("#newRoomBtn")
    expect(page.locator("#friendsErr")).to_have_text("The War server is unavailable right now. Try solo instead.")
    page.click("#soloBtn")
    expect(page.locator("#app")).to_be_visible()
