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
    box = page.locator("#myPile .stack").bounding_box()
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
    expect(page.locator("#roomTag")).to_have_text("＋ K7QP")
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
    dana_on_bob = guest.locator("#opponents .tile").nth(0).locator(".tslot > .card")
    expect(dana_on_bob).to_have_class(re.compile(r"\bback\b"))
    expect(dana_on_bob).to_have_attribute("data-deck", "space")
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 0, "winner": 0, "tied": [0], "gods": False, "pot": 3,
        "plays": [[0, 0, joker(1), 120, 0, 0], [1, 0, card(3), 50, 1, 0], [2, 0, card(12, 1), 80, 0, 0]],
        "counts": [29, 26, 26], "out": [], "next": fake.stage(2, opens_in=2400),
    })
    expect(dana_on_bob).to_have_attribute("aria-label", "red joker")
    expect(dana_on_bob.locator(".cc")).to_have_text("☄️")
    # When the next battle opens, the pot lands on Dana's heap on Bob's
    # screen, each card in its player's deck, Bob's ace in his.
    dana_heap = guest.locator("#opponents .tile").nth(0).locator(".heap .card")
    expect(dana_heap).to_have_count(3)
    expect(dana_heap.locator("xpath=self::*[@aria-label='ace of hearts']")).to_have_attribute("data-deck", "candy")
    expect(dana_heap.locator("xpath=self::*[@aria-label='red joker']")).to_have_attribute("data-deck", "space")
    expect(page.locator("#opponents .tile").nth(1).locator(".tslot > .card")).to_have_attribute("data-deck", "candy")
    expect(page.locator("#opponents .tile").nth(0).locator(".tslot > .card")).to_have_attribute("data-deck", bot_deck)
    expect(guest.locator("#opponents .tile").nth(1).locator(".tslot > .card")).to_have_attribute("data-deck", bot_deck)
    # Your own cards are in your deck, on your screen.
    expect(page.locator("#mySlot .card")).not_to_have_attribute("data-deck", re.compile("."))
    assert page.evaluate("document.documentElement.dataset.deck") == "space"

    # A change mid-game shows on everyone's screen from your next card.
    guest.click("#menuBtn")
    guest.click("#pauseDecks button[data-deck=spooky]")
    guest.click("#resumeBtn")
    guest.wait_for_function(f"{STATE}.canSlam")
    guest.evaluate("window.__war.slam(50)")
    expect(page.locator("#opponents .tile").nth(1).locator(".tslot > .card")).to_have_attribute("data-deck", "spooky")
    guest_context.close()
    assert errors == []


def test_cleaning_up_shows_on_everyone_elses_screen(page: Page, browser, site_url, errors):
    fake = FakeWarRoom()
    open_war(page, site_url, fake)
    start_room(page, "Dana")
    guest_context = browser.new_context(viewport={"width": 375, "height": 740})
    guest = guest_context.new_page()
    open_war(guest, site_url, fake)
    join_room(guest, "k7qp", "Bob")
    page.click("#dealBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(120)")
    # Dana's ace takes Bob's five, and when the next battle opens both cards
    # land on her heap: beside her card on her screen, behind her tile on
    # Bob's, his five first and her ace on top.
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 0, "winner": 0, "tied": [0], "gods": False, "pot": 2,
        "plays": [[0, 0, card(12), 120, 0, 0], [1, 0, card(3, 1), 50, 0, 0]],
        "counts": [28, 26], "out": [], "next": fake.stage(2, opens_in=1200),
    })
    dana_on_bob = guest.locator("#opponents .tile").nth(0).locator(".heap .card")
    expect(dana_on_bob).to_have_count(2)
    expect(page.locator("#tidyBtn")).to_be_visible()
    z_order = """cards => cards.slice().sort((a, b) => a.style.zIndex - b.style.zIndex)
        .map((c) => c.getAttribute('aria-label'))"""
    stacked = dana_on_bob.evaluate_all(z_order)
    assert stacked == ["five of hearts", "ace of spades"], stacked

    # Dana cleans up, and the room tells Bob: her heap squares up on his
    # screen too, in the same order.
    page.click("#tidyBtn")
    expect(page.locator("#tidyBtn")).to_be_hidden()
    assert fake.messages("tidy") == [{"t": "tidy"}]
    expect(dana_on_bob.nth(0)).to_have_css("--r", "0deg")
    expect(dana_on_bob.nth(1)).to_have_css("--r", "0deg")
    assert dana_on_bob.evaluate_all(z_order) == stacked
    expect(guest.locator("#tidyBtn")).to_be_hidden()
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
    expect(page.locator("#myPile")).to_be_hidden()
    expect(page.locator("#slamText")).to_have_text("Watching")
    # Watching a game that ends doesn't count as playing it.
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 0, "winner": 0, "tied": [0], "gods": False, "pot": 2,
        "plays": [[0, 0, card(12), 50, 0, 0], [1, 0, card(1), 50, 0, 0]], "counts": [27, 25], "out": [],
        "over": {"winners": [0], "order": [0, 1], "counts": [27, 25], "out": [0, 0],
                 "battles": 1, "wars": 0, "biggest": 0, "deepest": 0},
    })
    expect(page.locator("#over")).to_be_visible()
    # The battle log has what Eve saw, with no pile of her own to count.
    expect(page.locator("#battleLog li")).to_have_count(1)
    expect(page.locator("#battleLog li .lr")).to_have_text("🦊 Dana takes 2 cards")
    expect(page.locator("#battleLog li .ld")).to_have_text("")
    assert page.evaluate("localStorage.getItem('war:history')") is None
    assert page.evaluate("localStorage.getItem('war:stats')") is None
    assert errors == []


def test_an_invite_link_opens_straight_to_joining(page: Page, site_url, errors):
    open_war(page, site_url, FakeWarRoom(), "&room=k7qp")
    # Joining comes first, above solo play, with nothing else to pick.
    expect(page.locator("#friendsTitle")).to_have_text("You’re invited to room K7QP")
    expect(page.locator("#codeInput")).to_have_value("K7QP")
    expect(page.locator("#joinBtn")).to_have_text("Join room K7QP")
    expect(page.locator("#newRoomBtn")).to_be_hidden()
    assert page.locator("#friends").bounding_box()["y"] < page.locator("#soloBtn").bounding_box()["y"]
    expect(page.locator("#friendsErr")).to_have_text("Pick a name and an animal, then join.")
    page.fill("#nameInput", "Grandma")
    page.click("#joinBtn")
    expect(page.locator("#lobby")).to_be_visible()
    expect(page.locator("#people")).to_contain_text("Grandma")
    assert errors == []


def test_invite_by_qr_code_or_link_from_the_lobby_or_mid_game(page: Page, site_url, errors):
    fake = FakeWarRoom()
    open_war(page, site_url, fake)
    start_room(page)
    # The lobby shows the invite link as a QR code to scan.
    qr = page.locator("#lobbyQr svg")
    expect(qr).to_be_visible()
    expect(qr).to_have_attribute("aria-label", re.compile(r"^QR code for http.*/war\?room=K7QP"))
    page.click("#botMore")
    page.click("#dealBtn")
    expect(page.locator("#app")).to_be_visible()

    # Mid-game, the room code in the top bar invites someone to the next game.
    page.click("#roomTag")
    expect(page.locator("#inviteOv")).to_be_visible()
    expect(page.locator("#inviteCode")).to_have_text("K7QP")
    expect(page.locator("#inviteHelp")).to_contain_text("dealt into the next one")
    expect(page.locator("#inviteQr svg")).to_be_visible()
    page.click("#inviteShareBtn")
    expect(page.locator("#inviteNote")).to_have_text(re.compile(r"Invite link copied|room=K7QP"))
    page.keyboard.press("Escape")
    expect(page.locator("#inviteOv")).to_be_hidden()
    # So does the menu.
    page.click("#menuBtn")
    page.click("#pauseInviteBtn")
    expect(page.locator("#inviteOv")).to_be_visible()
    expect(page.locator("#pause")).to_be_hidden()
    page.click("#inviteDone")
    expect(page.locator("#inviteOv")).to_be_hidden()
    assert errors == []


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


def test_a_many_way_war_at_a_big_table(page: Page, site_url, errors):
    fake = FakeWarRoom()
    open_war(page, site_url, fake)
    start_room(page)
    for n in range(6):
        page.click("#botMore")
        expect(page.locator("#people .person")).to_have_count(n + 2)
    page.click("#dealBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(90)")

    # Six of the seven turn over a nine. You're one, so you get the full
    # show, with four pictured and the rest counted.
    fighters = [0, 1, 2, 3, 4, 5]
    plays = [[s, 0, card(7, s % 4), 90, 1, 0] for s in fighters] + [[6, 0, card(2), 90, 1, 0]]
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 0, "winner": None, "tied": fighters, "gods": False, "pot": 7,
        "plays": plays, "counts": [26] * 7, "out": [],
        "next": fake.stage(1, stage=1, fighters=fighters, opens_in=3000),
    })
    expect(page.locator("#banner")).to_have_text("6-WAY WAR!")
    intro = page.locator("#fx .vs")
    expect(intro).to_have_class(re.compile(r"\bmany\b"))
    expect(intro.locator(".vs-name")).to_have_count(4)
    expect(intro.locator(".vs-name").nth(0)).to_have_text("You")
    expect(intro.locator(".vs-pre")).to_have_text("6-WAY")
    expect(intro.locator(".vs-more")).to_have_text("+2 more")
    assert page.evaluate("window.__war.versus()")["more"] == 2

    # The war opens and you slam through FIGHT!. Then three others tie again
    # without you: someone else's war at a big table is only a quick strip.
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    expect(page.locator("#fx .vs-fight")).to_have_count(1)
    page.evaluate("window.__war.slam(90)")
    again = [1, 2, 3]
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 1, "winner": None, "tied": again, "gods": False, "pot": 31,
        "plays": [[s, 3, card(4, s % 4), 90, 1, 0] for s in fighters], "counts": [22, 22, 22, 22, 22, 22, 26], "out": [],
        "next": fake.stage(1, stage=2, fighters=again, opens_in=3000),
    })
    expect(page.locator("#banner")).to_have_text("3-WAY WAR!")
    expect(page.locator("#fx .vs-lite")).to_have_count(1)
    expect(page.locator("#fx .vs")).to_have_count(0)
    assert page.evaluate("window.__war.versus()")["kind"] == "lite"
    assert errors == []


VERSUS = "window.__war.versus()"


def deal_head_to_head(page: Page, site_url, fake: FakeWarRoom) -> None:
    open_war(page, site_url, fake)
    start_room(page)
    page.click("#botMore")
    expect(page.locator("#people .person")).to_have_count(2)
    page.click("#dealBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(90)")


def tie(fake: FakeWarRoom, up: list[int], battle: int = 1, stage: int = 0, opens_in: int = 3000) -> None:
    """The room says both players tied on these cards, so a war breaks out."""
    downs = 3 if stage else 0
    fake.broadcast({
        "t": "flip", "battle": battle, "stage": stage, "winner": None, "tied": [0, 1], "gods": False, "pot": 2 + stage * 8,
        "plays": [[s, downs, up[s], 90, 1, 0] for s in (0, 1)], "counts": [26 - stage * 4] * 2, "out": [],
        "next": fake.stage(battle, stage=stage + 1, fighters=[0, 1], opens_in=opens_in),
    })


JOKER = "(window.__war.joker() || {})"
# How bright a canvas is, on average: the jester in the dark, then lit.
BRIGHTNESS = """(sel) => {
    const c = document.querySelector(sel), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let sum = 0;
    for (let i = 0; i < d.length; i += 4) sum += ((d[i] + d[i + 1] + d[i + 2]) * d[i + 3]) / 255;
    return sum / (c.width * c.height);
}"""


def test_a_joker_war_turns_out_the_lights(page: Page, site_url, errors):
    fake = FakeWarRoom()
    deal_head_to_head(page, site_url, fake)

    # The red and the black joker meet: the lights go out instead of the
    # usual versus intro, for the 4.5 seconds a joker war waits to open.
    tie(fake, [joker(0), joker(1)], opens_in=4500)
    expect(page.locator("#banner")).to_have_text("WAR!")
    show = page.locator("#fx .jk")
    expect(show).to_have_class(re.compile(r"\blv1\b"))
    expect(show.locator(".jk-fig.bust canvas")).to_have_count(2)
    expect(show.locator(".jk-word")).to_have_text("JOKER WAR!")
    expect(show.locator(".jk-cards .card.joker")).to_have_count(2)
    expect(page.locator("#fx .vs")).to_have_count(0)
    assert page.evaluate(VERSUS)["joker"] == 1
    assert page.evaluate("getComputedStyle(document.getElementById('fx')).pointerEvents") == "none"
    # It fits a phone without anything scrolling sideways.
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    # Two eyes open in the dark, then a lantern lights the jester from below.
    # It's drawn in the page, pixel by pixel.
    page.wait_for_function(f"{JOKER}.eyes > 0.9")
    dark = page.evaluate(BRIGHTNESS, "#fx .jk-fig.bust .px")
    page.wait_for_function(f"{JOKER}.lit > 0.8")
    page.wait_for_timeout(100)
    lit = page.evaluate(BRIGHTNESS, "#fx .jk-fig.bust .px")
    assert lit > dark * 1.5, f"the lantern lights it up ({dark:.1f} then {lit:.1f})"
    # It laughs, a HA! for every beat.
    page.wait_for_function(f"{JOKER}.bubbles > 0")

    # The war opens on time and slamming works.
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    hold_slam(page, 250)
    expect(page.locator("#myWar .wpile .card")).to_have_count(1)
    expect(page.locator("#fx .jk")).to_have_count(0)
    page.evaluate("window.__war.slam(90)")

    # The war ties on jokers again: red eyes, and more of them open in the dark.
    tie(fake, [joker(0), joker(1)], stage=1, opens_in=4500)
    show = page.locator("#fx .jk")
    expect(show).to_have_class(re.compile(r"\blv2\b"))
    expect(show.locator(".jk-fig.peek")).to_have_count(7)
    expect(show.locator(".jk-pre")).to_have_text("DOUBLE")
    assert page.evaluate(VERSUS)["joker"] == 2
    assert errors == []


def test_jokers_can_tie_while_the_joker_is_still_laughing(page: Page, site_url, errors):
    fake = FakeWarRoom()
    deal_head_to_head(page, site_url, fake)
    tie(fake, [joker(1), joker(0)], opens_in=1200)
    expect(page.locator("#fx .jk")).to_have_count(1)
    # Slam the moment the war opens, before the joker would have finished in a
    # slower game: nothing waits for it.
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    assert page.evaluate("window.__war.slam(120)") is True
    assert [m["n"] for m in fake.messages("card")] == [0, 1, 2]
    assert errors == []


def test_an_ordinary_war_keeps_the_versus_intro(page: Page, site_url, errors):
    fake = FakeWarRoom()
    deal_head_to_head(page, site_url, fake)
    tie(fake, [card(11), card(11, 2)])  # two kings
    expect(page.locator("#fx .vs")).to_have_count(1)
    expect(page.locator("#fx .jk")).to_have_count(0)
    assert page.evaluate(VERSUS)["joker"] == 0
    assert errors == []


def test_reduced_motion_gets_a_still_joker(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")
    fake = FakeWarRoom()
    deal_head_to_head(page, site_url, fake)
    tie(fake, [joker(0), joker(1)])
    show = page.locator("#fx .jk")
    expect(show).to_have_class(re.compile(r"\bcalm\b"))
    expect(show.locator(".jk-fig.bust")).to_be_visible()
    expect(show.locator(".jk-word")).to_have_text("JOKER WAR!")
    # A still picture of the jester lit by its lantern, and nothing moves,
    # not even a pixel.
    assert page.evaluate(f"{JOKER}.lit") == 1
    moving = page.evaluate("document.getAnimations().filter((a) => a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('.jk')).length")
    assert moving == 0
    picture = "document.querySelector('#fx .jk-fig.bust .px').toDataURL()"
    before = page.evaluate(picture)
    page.wait_for_timeout(1200)
    assert page.evaluate(picture) == before
    assert page.locator("#fx .jk-ha").count() == 0
    assert page.evaluate("document.getElementById('app').classList.contains('shake')") is False
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    expect(page.locator("#fx .jk")).to_have_count(0)
    assert errors == []


def test_someone_elses_joker_war_at_a_big_table_is_a_strip(page: Page, site_url, errors):
    fake = FakeWarRoom()
    open_war(page, site_url, fake)
    start_room(page)
    for n in range(5):
        page.click("#botMore")
        expect(page.locator("#people .person")).to_have_count(n + 2)
    page.click("#dealBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(90)")
    # Two bots turn over jokers; you don't. A big table has more decks, so
    # more jokers.
    plays = [[0, 0, card(5), 90, 1, 0], [1, 0, joker(0), 90, 1, 0], [2, 0, joker(1) + 54, 90, 1, 0]]
    plays += [[s, 0, card(2, s % 4), 90, 1, 0] for s in range(3, 6)]
    fake.broadcast({
        "t": "flip", "battle": 1, "stage": 0, "winner": None, "tied": [1, 2], "gods": False, "pot": 6,
        "plays": plays, "counts": [26] * 6, "out": [],
        "next": fake.stage(1, stage=1, fighters=[1, 2], opens_in=3000),
    })
    strip = page.locator("#fx .vs-lite")
    expect(strip).to_have_class(re.compile(r"\bjoker\b"))
    expect(strip.locator("canvas")).to_have_count(1)
    expect(strip.locator("b")).to_have_text("JOKER WAR!")
    expect(page.locator("#fx .jk")).to_have_count(0)
    assert page.evaluate(VERSUS)["kind"] == "lite"
    assert errors == []


def test_a_seven_over_a_six_is_a_six_seven_and_nothing_else_is(page: Page, site_url, errors):
    fake = FakeWarRoom()
    open_war(page, site_url, fake)
    start_room(page)
    page.click("#botMore")
    page.click("#botMore")
    expect(page.locator("#people .person")).to_have_count(3)
    page.click("#dealBtn")

    def flip(battle: int, ranks: list[int], winner: int) -> None:
        page.wait_for_function(f"{STATE}.battle === {battle} && {STATE}.canSlam")
        page.evaluate("window.__war.slam(90)")
        fake.broadcast({
            "t": "flip", "battle": battle, "stage": 0, "winner": winner, "tied": [winner], "gods": False, "pot": 3,
            "plays": [[s, 0, card(r, s), 90, 1, 0] for s, r in enumerate(ranks)],
            "counts": [27, 27, 27], "out": [], "next": fake.stage(battle + 1, opens_in=2400),
        })

    # Bot 1's seven beats your six and Bot 2's three: a six… seven.
    flip(1, [4, 5, 1], 1)
    expect(page.locator("#fx .ss")).to_have_count(1)
    expect(page.locator("#fx .ss .ss-word")).to_have_text("6-7!")
    held = page.locator("#fx .ss .ss-side .card")
    expect(held.nth(0)).to_have_attribute("aria-label", "six of spades")
    expect(held.nth(1)).to_have_attribute("aria-label", "seven of hearts")
    expect(page.locator("#caption")).to_contain_text("Bot 1's seven")
    expect(page.locator("#caption")).to_contain_text("your six")
    assert page.evaluate("window.__war.sixSeven()")["six"] == 0
    # It's gone as the next battle opens.
    page.wait_for_function(f"{STATE}.battle === 2")
    expect(page.locator("#fx .ss")).to_have_count(0)

    # A seven over a five, or an eight over a six, is just a battle.
    flip(2, [5, 3, 2], 0)
    expect(page.locator("#banner")).to_have_text("YOU WIN!")
    page.wait_for_function(f"{STATE}.battle === 3")
    flip(3, [4, 6, 2], 1)
    expect(page.locator("#caption")).to_contain_text("eight")
    page.wait_for_timeout(300)
    expect(page.locator("#fx .ss")).to_have_count(0)
    assert page.evaluate("window.__war.sixSeven()")["six"] == 0, "only the first battle was a six… seven"
    assert errors == []
