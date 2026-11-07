"""War rooms in the page, against a fake of the room (tests/fake_war_room.py).

Tests that make the fake answer 4xx, or fail requests, skip the `errors`
fixture, because the browser logs those as console errors.
"""

from __future__ import annotations

import re

from fake_leaderboard import API
from fake_war_room import FakeWarRoom, card, joker
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
    # In the war, Dana slams each of her cards: three face down, as she goes,
    # then the one that decides it. Bob sees them land.
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    expect(page.locator("#slamText")).to_have_text("Face-down 1/3 · hold")
    page.evaluate("window.__war.slam(120)")
    assert [(m["n"], m["power"]) for m in fake.messages("card")] == [(0, 120), (1, 120), (2, 120)]
    assert fake.messages("slam")[-1]["power"] == 120
    expect(guest.locator("#opponents .tile .downs")).to_have_text("+3")
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


def test_everyone_sees_each_players_deck(page: Page, browser, site_url, errors):
    fake = FakeWarRoom()
    open_war(page, site_url, fake)
    page.click("#menuDecks button[data-deck=neon]")
    start_room(page, "Dana")
    assert fake.messages("hello")[0]["deck"] == "neon"
    page.click("#botMore")

    guest_context = browser.new_context(viewport={"width": 375, "height": 740})
    guest = guest_context.new_page()
    open_war(guest, site_url, fake)
    guest.click("#menuDecks button[data-deck=candy]")
    join_room(guest, "k7qp", "Bob")
    # In the lobby, each name has its deck beside it.
    people = page.locator("#people .person")
    expect(people).to_have_count(3)
    expect(people.nth(0).locator(".card")).to_have_attribute("data-deck", "neon")
    expect(people.nth(2).locator(".card")).to_have_attribute("data-deck", "candy")
    bot_deck = people.nth(1).locator(".card").get_attribute("data-deck")
    expect(guest.locator("#people .person").nth(1).locator(".card")).to_have_attribute("data-deck", bot_deck)

    # Dana changes her mind in the lobby, twice, and Bob sees where she ends
    # up: the room takes one change a second, so the second waits its turn.
    page.click("#lobbyDecks button[data-deck=pixel]")
    page.click("#lobbyDecks button[data-deck=space]")
    expect(guest.locator("#people .person").nth(0).locator(".card")).to_have_attribute("data-deck", "pixel")
    expect(guest.locator("#people .person").nth(0).locator(".card")).to_have_attribute("data-deck", "space")
    assert [m["deck"] for m in fake.messages("deck")] == ["pixel", "space"]

    page.click("#dealBtn")
    expect(guest.locator("#opponents .tile")).to_have_count(2)
    # Dana's cards land on Bob's screen in her deck, Bob's on hers in his,
    # and the bot's in the same deck for both.
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(120)")
    dana_on_bob = guest.locator("#opponents .tile").nth(0).locator(".card")
    expect(dana_on_bob).to_have_class(re.compile(r"\bback\b"))
    expect(dana_on_bob).to_have_attribute("data-deck", "space")
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 0, "winner": 0, "tied": [0], "gods": False, "pot": 3,
        "plays": [[0, 0, joker(1), 120, 0, 0], [1, 0, card(3), 50, 1, 0], [2, 0, card(12, 1), 80, 0, 0]],
        "counts": [29, 26, 26], "out": [], "next": fake.stage(2, opens_in=2400),
    })
    expect(dana_on_bob).to_have_attribute("aria-label", "red joker")
    expect(dana_on_bob.locator(".cc")).to_have_text("☄️")
    expect(page.locator("#opponents .tile").nth(1).locator(".card")).to_have_attribute("data-deck", "candy")
    expect(page.locator("#opponents .tile").nth(0).locator(".card")).to_have_attribute("data-deck", bot_deck)
    expect(guest.locator("#opponents .tile").nth(1).locator(".card")).to_have_attribute("data-deck", bot_deck)
    # Your own cards are in your deck, on your screen.
    expect(page.locator("#mySlot .card")).not_to_have_attribute("data-deck", re.compile("."))
    assert page.evaluate("document.documentElement.dataset.deck") == "space"

    # A change mid-game redraws your cards on everyone's screen.
    guest.click("#menuBtn")
    guest.click("#pauseDecks button[data-deck=spooky]")
    guest.click("#resumeBtn")
    expect(page.locator("#opponents .tile").nth(1).locator(".card")).to_have_attribute("data-deck", "spooky")
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
