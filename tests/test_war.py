"""War, played solo against bots. Rooms are in test_war_rooms.py.

?seed= makes the deal repeat, and #debug exposes window.__war: state() reads
the table, slam(power) slams right away, pace(p) speeds the game up,
finish() plays the rest of it out at once and odds() runs the win
probability model.
"""

from __future__ import annotations

import re

import pytest
from fake_leaderboard import without_worker
from playwright.sync_api import Page, expect

STATE = "window.__war.state()"
# Seed 589: both players turn over an eight in the first battle, then a three
# in the war: a double war.
WAR_SEED = 589


def start_solo(page: Page, site_url: str, opponents: int = 1, length: str = "standard", seed: int = 7) -> None:
    page.goto(f"{site_url}/war?seed={seed}#debug")
    page.fill("#oppRange", str(opponents))
    page.click(f"#soloLength button[data-length={length}]")
    page.click("#soloBtn")
    expect(page.locator("#app")).to_be_visible()
    page.wait_for_function(f"{STATE}.canSlam")


def hold_slam(page: Page, ms: int) -> None:
    box = page.locator("#myPile .stack").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(ms)
    page.mouse.up()


def test_hold_to_charge_and_release_to_slam(page: Page, site_url, errors):
    start_solo(page, site_url)
    assert page.locator("#opponents .tile").count() == 1
    # It's your turn: your deck says how to slam it.
    expect(page.locator("#me")).to_have_class(re.compile(r"\bready\b"))
    expect(page.locator("#deckHint")).to_have_text("Hold me")
    expect(page.locator("#slamText")).to_have_text("Hold your deck to slam")
    box = page.locator("#myPile .stack").bounding_box()
    page.mouse.move(box["x"] + 40, box["y"] + 30)
    page.mouse.down()
    page.wait_for_timeout(900)
    expect(page.locator("#slamText")).not_to_have_text("Hold your deck to slam")
    expect(page.locator("#deckHint")).to_be_hidden()
    page.mouse.up()

    power = page.evaluate(f"{STATE}.slams[0][0]")
    assert power > 30, "nearly a second of charging is a decent slam"
    # The battle plays out once the bot has slammed too: a winner, or a war.
    page.wait_for_function(f"{STATE}.battle === 2 || {STATE}.stage === 1")
    counts = page.evaluate(f"{STATE}.counts")
    assert 40 < sum(counts) <= 54, "cards in a war's pot belong to nobody yet"
    expect(page.locator("#caption")).not_to_be_empty()
    assert errors == []


def test_cards_land_face_up_as_they_are_played(page: Page, site_url, errors):
    start_solo(page, site_url)
    # The bot slams first: its card is face up straight away, though the
    # battle waits for you.
    bot = page.locator("#spots .spot .tslot > .card")
    expect(bot).to_have_attribute("aria-label", re.compile("."))
    assert page.evaluate(f"{STATE}.table") == {}, "nothing has been played out"
    expect(page.locator("#mySlot .card")).to_have_class(re.compile(r"\bempty\b"))

    # Your card lands face up the moment you slam it, before the flip.
    landed = page.evaluate(f"""() => {{
        window.__war.slam(90);
        const card = document.querySelector('#mySlot .card');
        return {{ label: card.getAttribute('aria-label'), back: card.classList.contains('back'), table: {STATE}.table }};
    }}""")
    assert not landed["back"] and landed["label"], landed
    assert landed["table"] == {}, "the flip hasn't come yet"

    # The flip turns over the same cards, and brings the winner.
    page.wait_for_function(f"Object.keys({STATE}.table).length === 2")
    expect(page.locator("#mySlot .card")).to_have_attribute("aria-label", landed["label"])
    ups = page.evaluate(f"{STATE}.ups")
    assert page.evaluate(f"{STATE}.table") == ups
    assert errors == []


def test_a_slow_game_never_flops_your_card(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=7#debug")
    page.click("#soloClock button[data-clock=slow]")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    assert page.evaluate(f"{STATE}.slow")
    page.evaluate("window.__war.pace(0.2)")
    expect(page.locator("#slamText")).to_have_text("Your turn. Take your time.")
    page.evaluate("window.__war.slam(90)")
    page.wait_for_function(f"{STATE}.canSlam && ({STATE}.battle === 2 || {STATE}.stage === 1)")
    where = page.evaluate(f"[{STATE}.battle, {STATE}.stage]")

    # Longer than a timed game's clock, and then some: nothing counts down,
    # nothing hurries, and your card stays in your hand.
    page.wait_for_timeout(9000)
    page.evaluate("window.__war.hurry()")
    page.wait_for_timeout(1000)
    assert page.evaluate(f"[{STATE}.battle, {STATE}.stage]") == where
    assert page.evaluate(f"{STATE}.canSlam"), "still your turn"
    expect(page.locator("#slamBar")).not_to_have_class(re.compile(r"\bhurry\b"))
    expect(page.locator("#slamText")).to_have_text(re.compile(r"Your turn\. Take your time\.|Face-down 1/3"))
    expect(page.locator("#waitRow")).to_be_hidden()
    page.evaluate("window.__war.slam(90)")
    page.wait_for_function(f"[{STATE}.battle, {STATE}.stage].join() !== {where!r}.join()".replace("'", ""))
    assert page.evaluate(f"{STATE}.mine.every(([power]) => power === 90)"), "every card was yours, none flopped"

    # The menu remembers the choice.
    page.click("#menuBtn")
    page.click("#quitBtn")
    expect(page.locator("#soloClock button[data-clock=slow]")).to_have_attribute("aria-pressed", "true")
    assert errors == []


def test_a_war_means_slamming_every_card(page: Page, site_url, errors):
    start_solo(page, site_url, seed=WAR_SEED)
    hold_slam(page, 400)
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    expect(page.locator("#caption")).to_contain_text("Slam all four of your cards!")
    expect(page.locator("#myWar .wcount")).to_have_text("Face down here")
    for n in (1, 2, 3):
        expect(page.locator("#slamText")).to_have_text(f"Face-down {n}/3 · hold")
        hold_slam(page, 300)
        expect(page.locator("#myWar .wpile .card.back")).to_have_count(n)
        assert page.evaluate(f"{STATE}.canSlam"), "the war isn't slammed until the last card"
    expect(page.locator("#myWar .wcount")).to_have_text("3 face down")
    expect(page.locator("#slamText")).to_have_text("The decider · hold")
    hold_slam(page, 300)
    assert page.evaluate(f"{STATE}.slams[0]") is not None
    assert len(page.evaluate(f"{STATE}.mine")) == 5, "one slam for the battle, four for the war"
    expect(page.locator("#caption")).to_contain_text("War power")
    # The bot slams its face-down cards too.
    expect(page.locator("#spots .downs")).to_have_text("+3")
    # ...and they fan out under its card, one for each, so you can count them.
    expect(page.locator("#spots .tdowns .card.back")).to_have_count(3)
    assert errors == []


def test_in_a_war_of_wars_the_cards_that_tied_stay_on_the_table(page: Page, site_url, errors):
    # Seed 589: both turn over an eight, then a three in the war.
    start_solo(page, site_url, seed=WAR_SEED)
    page.evaluate("window.__war.slam(60)")
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    page.evaluate("window.__war.slam(60)")
    page.wait_for_function(f"{STATE}.stage === 2 && {STATE}.canSlam")
    # The double war opens with each three on top, and each eight still
    # there, face up under the three face-down cards.
    bot_up = page.locator("#spots .tdowns .card:not(.back)")
    expect(bot_up).to_have_count(1)
    expect(bot_up).to_have_attribute("aria-label", re.compile(r"^eight of "))
    expect(page.locator("#spots .tdowns .card.back")).to_have_count(3)
    expect(page.locator("#spots .spot .tslot > .card")).to_have_attribute("aria-label", re.compile(r"^three of "))
    # Yours are all on your war pile: the eight, your three face-down cards,
    # and the three that tied on top.
    expect(page.locator("#mySlot")).to_be_hidden()
    my_up = page.locator("#myWar .wpile .card:not(.back)")
    expect(my_up).to_have_count(2)
    assert [l.split(" ")[0] for l in my_up.evaluate_all("cs => cs.map((c) => c.getAttribute('aria-label'))")] == ["eight", "three"]
    expect(page.locator("#myWar .wpile .card:last-child")).to_have_attribute("aria-label", re.compile(r"^three of "))
    expect(page.locator("#myWar .wpile .card.back")).to_have_count(3)
    # When the bot slams its next card, its three joins the pile, face up.
    page.wait_for_function("document.querySelectorAll('#spots .tdowns .card:not(.back)').length === 2", timeout=10_000)
    labels = bot_up.evaluate_all("cards => cards.map((c) => c.getAttribute('aria-label'))")
    assert labels[0].startswith("eight") and labels[1].startswith("three"), labels
    expect(page.locator("#spots .tdowns .card.back")).to_have_count(6)
    assert errors == []


def test_in_a_war_all_your_cards_are_on_one_pile(page: Page, site_url, errors):
    start_solo(page, site_url, seed=WAR_SEED)
    page.evaluate("window.__war.slam(60)")
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    landed = page.evaluate("""() => {
        window.__war.slam(60);
        const pile = [...document.querySelectorAll('#myWar .wpile .card')];
        return { pile: pile.map((c) => c.getAttribute('aria-label')) };
    }""")
    # One pile: the eight you tied with, three face down and the one that
    # decides it on top, face up.
    assert landed["pile"][0].startswith("eight"), landed
    assert landed["pile"][1:4] == [None, None, None] and landed["pile"][4], landed
    expect(page.locator("#mySlot")).to_be_hidden()
    assert errors == []


def test_as_a_war_opens_the_card_you_tied_with_stays_where_it_lies(page: Page, site_url, errors):
    start_solo(page, site_url, seed=WAR_SEED)
    page.evaluate("window.__war.slam(60)")
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    # Your eight moves onto your war pile as it lay: it isn't slammed down again.
    tied = page.locator("#myWar .wpile .card")
    expect(tied).to_have_count(1)
    expect(tied).to_have_attribute("aria-label", re.compile(r"^eight of "))
    assert "slam" not in (tied.get_attribute("class") or "")
    assert page.evaluate("document.querySelector('#myWar .wpile .card').getAnimations().length") == 0
    # The face-down cards you slam next land on it, one by one.
    hold_slam(page, 250)
    expect(page.locator("#myWar .wpile .card.back")).to_have_count(1)
    expect(page.locator("#myWar .wpile .card.back")).to_have_class(re.compile(r"\bslam\b"))
    assert "slam" not in (page.locator("#myWar .wpile .card").first.get_attribute("class") or "")
    assert errors == []


def test_a_war_you_started_is_finished_before_the_clock_runs_out(page: Page, site_url, errors):
    start_solo(page, site_url, seed=WAR_SEED)
    page.evaluate("window.__war.slam(50)")
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    hold_slam(page, 300)
    page.evaluate("window.__war.hurry()")
    page.wait_for_function(f"{STATE}.slams[0] !== undefined")
    assert len(page.evaluate(f"{STATE}.plan.done")) == 4, "the face-down cards left go down at no power"
    assert errors == []



VERSUS = "window.__war.versus()"


def test_a_war_gets_a_versus_intro_that_escalates(page: Page, site_url, errors):
    start_solo(page, site_url, seed=WAR_SEED)
    page.evaluate("window.__war.slam(60)")
    # The fighters slide in, you on the left, and WAR slams down between them.
    intro = page.locator("#fx .vs")
    expect(intro).to_have_class(re.compile(r"\blv1\b"))
    names = intro.locator(".vs-name")
    expect(names).to_have_count(2)
    expect(names.nth(0)).to_have_text("You")
    expect(names.nth(1)).to_have_text("Grumpy Pancake")  # the bot seed 589 deals
    pics = intro.locator(".vs-pic > span")
    expect(pics).to_have_count(2)
    assert all(pics.nth(i).inner_text().strip() for i in range(2)), "each fighter has a picture"
    # Each holds the eight they tied on, in their own deck.
    expect(intro.locator(".vs-pic .card")).to_have_count(2)
    expect(intro.locator(".vs-word")).to_have_text("WAR!")
    expect(intro.locator(".vs-round")).to_have_text("ROUND 1")
    expect(page.locator("#banner")).to_have_text("WAR!")
    assert page.evaluate(VERSUS)["kind"] == "full"
    # It's only a picture: taps go straight through it.
    assert page.evaluate("getComputedStyle(document.getElementById('fx')).pointerEvents") == "none"

    # FIGHT! lands as the war opens, and you can slam while it does.
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    expect(page.locator("#fx .vs-fight")).to_have_text("FIGHT!")
    expect(page.locator("#fx .vs")).to_have_count(0)
    hold_slam(page, 250)
    expect(page.locator("#myWar .wpile .card.back")).to_have_count(1)

    # The war ties again: a double war is bigger.
    page.evaluate("window.__war.slam(60)")
    intro = page.locator("#fx .vs")
    expect(intro).to_have_class(re.compile(r"\blv2\b"))
    expect(intro.locator(".vs-pre")).to_have_text("DOUBLE")
    expect(intro.locator(".vs-round")).to_have_text("ROUND 2")
    expect(page.locator("#banner")).to_have_text("DOUBLE WAR!")
    assert page.evaluate(VERSUS)["level"] == 2
    size = lambda: page.evaluate("parseFloat(getComputedStyle(document.querySelector('#fx .vs')).getPropertyValue('--word-size').match(/[\\d.]+(?=vw)/)[0])")
    assert size() > 27, "the double war's WAR is bigger than a war's"
    assert errors == []


# Seed 359: the first battle against one bot is joker against joker.
JOKER_SEED = 359


def test_a_joker_war_turns_out_the_lights_and_waits_longer_to_open(page: Page, site_url, errors):
    start_solo(page, site_url, seed=JOKER_SEED)
    page.evaluate("window.__war.slam(60)")
    expect(page.locator("#fx .jk")).to_have_count(1)
    assert page.evaluate(VERSUS)["joker"] == 1
    tied = page.evaluate("performance.now()")
    page.wait_for_function(f"{STATE}.stage === 1", timeout=10000)
    waited = page.evaluate("performance.now()") - tied
    assert waited > 4000, f"a joker war opens 4.5 seconds after the tie, not 3 ({waited:.0f} ms)"
    expect(page.locator("#fx .jk")).to_have_count(0)
    assert errors == []


def test_reduced_motion_gets_a_calm_versus(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")
    start_solo(page, site_url, seed=WAR_SEED)
    page.evaluate("window.__war.slam(60)")
    intro = page.locator("#fx .vs")
    expect(intro).to_have_class(re.compile(r"\bcalm\b"))
    expect(intro.locator(".vs-name")).to_have_count(2)
    expect(intro.locator(".vs-name").nth(0)).to_have_text("You")
    expect(intro.locator(".vs-word")).to_be_visible()
    # Nothing moves: no sliding, no shaking, no fireworks.
    moving = page.evaluate("document.getAnimations().filter((a) => a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('.vs')).length")
    assert moving == 0
    page.wait_for_timeout(1200)
    assert page.locator("#fx .bit").count() == 0
    assert page.evaluate("document.getElementById('app').classList.contains('shake')") is False
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    expect(page.locator("#fx .vs")).to_have_count(0)
    assert page.evaluate(VERSUS)["kind"] == "calm"
    assert errors == []

# Seed 309: your seven beats Sir Wombat's six in the first battle.
SIX_SEVEN_SEED = 309
SIX_SEVEN = "window.__war.sixSeven()"


def test_a_seven_over_a_six_is_a_six_seven(page: Page, site_url, errors):
    start_solo(page, site_url, seed=SIX_SEVEN_SEED)
    page.evaluate("window.__war.slam(60)")
    show = page.locator("#fx .ss")
    expect(show).to_have_count(1)
    # The very cards from the table ride on the palms, each in its own deck.
    held = show.locator(".ss-side .card")
    expect(held).to_have_count(2)
    expect(held.nth(0)).to_have_attribute("aria-label", re.compile(r"^six of "))
    expect(held.nth(1)).to_have_attribute("aria-label", re.compile(r"^seven of "))
    theirs = page.locator("#spots .card[aria-label]").first.get_attribute("data-deck")
    assert held.nth(0).get_attribute("data-deck") == theirs
    assert held.nth(1).get_attribute("data-deck") == page.evaluate("deck"), "your seven is in your deck"
    expect(show.locator(".ss-word")).to_have_text("6-7!")
    expect(show.locator(".ss-hand")).to_have_count(2)
    # The banner still says who won, and the caption has a line of its own.
    expect(page.locator("#banner")).to_have_text("YOU WIN!")
    expect(page.locator("#caption")).to_contain_text(re.compile(r"six… seven", re.I))
    expect(page.locator("#caption")).to_contain_text("Sir Wombat's six")
    assert page.evaluate(SIX_SEVEN) == {"kind": "full", "winner": 0, "six": 1, "k": 1}
    # It bobs, takes no taps, fits the phone and is gone before the next battle.
    assert page.evaluate("document.getAnimations().filter((a) => a.effect?.target?.closest?.('.ss')).length") >= 4
    assert page.evaluate("getComputedStyle(document.getElementById('fx')).pointerEvents") == "none"
    box = show.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"]
    page.wait_for_function(f"{STATE}.battle === 2 && {STATE}.canSlam")
    expect(page.locator("#fx .ss")).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth") <= page.viewport_size["width"]
    assert errors == []


def test_reduced_motion_gets_a_calm_six_seven(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")
    start_solo(page, site_url, seed=SIX_SEVEN_SEED)
    page.evaluate("window.__war.slam(60)")
    show = page.locator("#fx .ss")
    expect(show).to_have_class(re.compile(r"\bcalm\b"))
    expect(show.locator(".ss-word")).to_be_visible()
    expect(show.locator(".ss-side .card")).to_have_count(2)
    # Nothing moves.
    assert page.evaluate("document.getAnimations().filter((a) => a.effect?.target?.closest?.('.ss')).length") == 0
    assert page.evaluate(SIX_SEVEN)["kind"] == "calm"
    page.wait_for_function(f"{STATE}.battle === 2")
    expect(page.locator("#fx .ss")).to_have_count(0)
    assert errors == []


# Seed 489: an eight each, then the war ties again and your double war wins
# all 18 cards. Seed 130: a war you win, 10 cards. Seed 802: a triple war you
# win, 26 cards with a joker.
SPOILS_DOUBLE_SEED = 489
SPOILS_SEED = 130
SPOILS = "window.__war.spoils()"


def play_to_spoils(page: Page) -> None:
    """Slams through the opening battle and its war until the war is decided."""
    for _ in range(5):
        page.evaluate("window.__war.slam(60)")
        page.wait_for_function(f"{STATE}.spoils !== 'none' || ({STATE}.stage > 0 && {STATE}.canSlam)", timeout=10_000)
        if page.evaluate(f"{STATE}.spoils") != "none":
            return
    raise AssertionError("no war was decided")


def test_a_war_you_win_shows_its_spoils_then_they_land_on_your_loot(page: Page, site_url, errors):
    start_solo(page, site_url, seed=SPOILS_DOUBLE_SEED)
    play_to_spoils(page)
    show = page.locator("#fx .sp")
    expect(show).to_have_count(1)
    expect(show).to_have_class(re.compile(r"\blv2\b"))
    expect(show.locator(".sp-title")).to_have_text("SPOILS OF WAR!")
    expect(show.locator(".sp-pre")).to_have_text("DOUBLE")
    expect(page.locator("#banner")).to_have_text("WAR WON!")
    spoils = page.evaluate(SPOILS)
    assert spoils["kind"] == "full" and spoils["total"] == 18 and spoils["more"] == 0, spoils
    # Every card in the pot, the twelve laid face down included, each in its
    # deck, and those twelve start face down and turn over.
    cards = show.locator(".sp-c .sp-in > .card:not(.sp-back)")
    expect(cards).to_have_count(18)
    assert all(isinstance(c, int) for c in spoils["cards"]), spoils
    expect(show.locator(".sp-c .sp-back")).to_have_count(12)
    assert spoils["downs"] == 12
    for i in range(18):
        assert cards.nth(i).get_attribute("data-deck"), "each card keeps its deck's look"
    # It moves, takes no taps and fits a phone.
    assert page.evaluate("document.getAnimations().filter((a) => a.effect?.target?.closest?.('.sp')).length") >= 18
    assert page.evaluate("getComputedStyle(document.getElementById('fx')).pointerEvents") == "none"
    # The counter tallies them and the war report lists the haul.
    expect(page.locator("html")).to_have_attribute("data-spoils", "report", timeout=5000)
    expect(show.locator(".sp-count")).to_have_text("+18")
    report = show.locator(".sp-win")
    expect(report).to_be_visible()
    expect(report.locator(".sp-row").first).to_contain_text("Cards won")
    expect(report.locator(".sp-row").first).to_contain_text("+18")
    expect(report).to_contain_text("Double war")
    expect(report).to_contain_text("12 cards")
    expect(report).to_contain_text("+0, as always")
    expect(report).to_contain_text(re.compile(r"Win odds.*\d+% → \d+%"))
    box = report.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"]
    # The next battle opens: the cards fly to your loot pile, the show goes,
    # and the counts add up.
    page.wait_for_function(f"{STATE}.battle === 2")
    expect(page.locator("html")).to_have_attribute("data-spoils", "none", timeout=10_000)
    expect(page.locator("#fx .sp")).to_have_count(0)
    state = page.evaluate(STATE)
    assert sorted(state["heap"]) == sorted(spoils["cards"]), state["heap"]
    assert state["loot"] == [18, 0], state["loot"]
    assert state["counts"] == [36, 18], state["counts"]
    assert page.evaluate("document.documentElement.scrollWidth") <= page.viewport_size["width"]
    assert errors == []


def test_a_war_someone_else_wins_shows_a_strip_of_their_spoils(page: Page, site_url, errors):
    start_solo(page, site_url, seed=WAR_SEED)
    play_to_spoils(page)
    strip = page.locator("#fx .sp-lite")
    expect(strip).to_have_count(1)
    expect(page.locator("#fx .sp")).to_have_count(0)
    expect(strip.locator("p")).to_have_text("💰 Spoils to Grumpy Pancake: 18 cards")
    # Every card in the pot, face up, the face-down ones included.
    expect(strip.locator(".sp-mini .card")).to_have_count(18)
    expect(strip.locator(".sp-mini .card.back")).to_have_count(0)
    spoils = page.evaluate(SPOILS)
    assert spoils["kind"] == "lite" and spoils["downs"] == 12 and spoils["more"] == 0, spoils
    box = strip.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"]
    # They land on Grumpy Pancake's loot pile.
    page.wait_for_function(f"{STATE}.battle === 2")
    expect(page.locator("#fx .sp-lite")).to_have_count(0, timeout=5000)
    state = page.evaluate(STATE)
    assert state["loot"] == [0, 18] and sorted(state["heaps"]["1"]) == sorted(spoils["cards"]), state
    assert errors == []


def test_the_spoils_run_on_into_the_next_battle_and_a_slam_carries_on(page: Page, site_url, errors):
    start_solo(page, site_url, seed=SPOILS_SEED)
    play_to_spoils(page)
    # The next battle opens while the report is still up: the pot stays on
    # the fan, off your loot pile, with a word that a tap carries on.
    page.wait_for_function(f"{STATE}.battle === 2 && {STATE}.canSlam")
    assert page.evaluate(f"{STATE}.spoils") in ("haul", "report")
    expect(page.locator("#fx .sp .sp-next")).to_be_visible()
    expect(page.locator("#fx .sp .sp-next")).to_contain_text("Tap to play on")
    assert page.evaluate(f"{STATE}.heap") == []
    # Holding your deck slams as usual, sends the show off and throws the pot
    # onto your loot pile.
    hold_slam(page, 250)
    page.wait_for_function(f"{STATE}.slams[0] !== undefined")
    expect(page.locator("#fx .sp")).to_have_count(0)
    expect(page.locator("html")).to_have_attribute("data-spoils", "none")
    page.wait_for_function(f"{STATE}.heap.length === 10")
    assert errors == []


def test_the_spoils_leave_by_themselves_once_read(page: Page, site_url, errors):
    start_solo(page, site_url, seed=SPOILS_SEED)
    play_to_spoils(page)
    page.wait_for_function(f"{STATE}.battle === 2")
    # Nobody taps: the cards fly to your loot pile a little into the battle.
    expect(page.locator("html")).to_have_attribute("data-spoils", "leaving", timeout=6000)
    page.wait_for_function(f"{STATE}.heap.length === 10")
    expect(page.locator("html")).to_have_attribute("data-spoils", "none", timeout=5000)
    state = page.evaluate(STATE)
    assert state["loot"][0] == 10 and state["canSlam"], state
    assert errors == []


def test_a_tap_skips_the_spoils(page: Page, site_url, errors):
    start_solo(page, site_url, seed=SPOILS_SEED)
    play_to_spoils(page)
    page.wait_for_timeout(700)
    page.mouse.click(10, 300)
    expect(page.locator("#fx .sp")).to_have_count(0)
    # The cards still land on your loot pile.
    page.wait_for_function(f"{STATE}.battle === 2")
    page.wait_for_function(f"{STATE}.loot[0] === 10")
    assert errors == []


def test_a_triple_war_caps_the_fan_and_counts_the_rest(page: Page, site_url, errors):
    start_solo(page, site_url, seed=802)
    play_to_spoils(page)
    show = page.locator("#fx .sp")
    expect(show).to_have_class(re.compile(r"\blv3\b"))
    expect(show.locator(".sp-pre")).to_have_text("TRIPLE")
    expect(show.locator(".sp-c")).to_have_count(20)
    expect(show.locator(".sp-more")).to_have_text("+6 more")
    expect(show.locator(".sp-win")).to_contain_text("Jokers")
    title = show.locator(".sp-title")
    page.wait_for_function(f"{STATE}.spoils === 'report'", timeout=5000)
    box = title.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"], box
    page.wait_for_function(f"{STATE}.battle === 2")
    page.wait_for_function(f"{STATE}.loot[0] === 26")
    assert errors == []


def test_reduced_motion_gets_calm_spoils(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")
    start_solo(page, site_url, seed=SPOILS_SEED)
    play_to_spoils(page)
    show = page.locator("#fx .sp")
    expect(show).to_have_class(re.compile(r"\bcalm\b"))
    # The whole haul and the report straight away, face up, standing still.
    expect(page.locator("html")).to_have_attribute("data-spoils", "report")
    expect(show.locator(".sp-c .card")).to_have_count(10)
    expect(show.locator(".sp-c .card.back")).to_have_count(0)
    expect(show.locator(".sp-count")).to_have_text("+10")
    expect(show.locator(".sp-win")).to_be_visible()
    assert page.evaluate("document.getAnimations().filter((a) => a.effect?.target?.closest?.('.sp')).length") == 0
    page.wait_for_timeout(800)
    assert page.locator("#fx .bit").count() == 0
    assert page.evaluate("document.getElementById('app').classList.contains('shake')") is False
    assert page.evaluate(SPOILS)["kind"] == "calm"
    page.wait_for_function(f"{STATE}.battle === 2")
    page.wait_for_function(f"{STATE}.loot[0] === 10")
    expect(page.locator("#fx .sp")).to_have_count(0, timeout=5000)
    assert errors == []


def test_quiet_spoils_keep_the_show_but_drop_the_jokes(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed={SPOILS_SEED}#debug")
    page.click("#menuChat button[data-chat=quiet]")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    play_to_spoils(page)
    report = page.locator("#fx .sp .sp-win")
    expect(report).to_contain_text("Cards won")
    expect(report).to_contain_text("War depth")
    expect(report).not_to_contain_text("Slam power")
    expect(report).not_to_contain_text("Win odds")
    labels = [r[0] for r in page.evaluate(SPOILS)["rows"]]
    assert labels == ["Cards won", "Face down, now yours", "War depth"], labels
    assert errors == []


def test_quiet_commentary_says_just_what_happened(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed={SIX_SEVEN_SEED}#debug")
    expect(page.locator("html")).to_have_attribute("data-chat", "chatty")
    page.click("#menuChat button[data-chat=quiet]")
    expect(page.locator("html")).to_have_attribute("data-chat", "quiet")
    assert page.evaluate("JSON.parse(localStorage.getItem('war:chat'))") == "quiet"
    page.reload()
    expect(page.locator("#menuChat button[data-chat=quiet]")).to_have_attribute("aria-pressed", "true")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    # No joke to open the battle, and no joke about how it went.
    expect(page.locator("#caption")).to_be_empty()
    page.evaluate("window.__war.slam(60)")
    expect(page.locator("#caption")).to_have_text("Your seven takes 2 cards.")
    # The six… seven still plays: only the words go quiet.
    expect(page.locator("#fx .ss")).to_have_count(1)
    expect(page.locator("#banner")).to_have_text("YOU WIN!")
    # No win odds as you go.
    page.wait_for_function(f"{STATE}.chances !== null")
    expect(page.locator("#odds")).to_be_hidden()
    # Chatty again from the pause menu, and the odds come back.
    page.click("#menuBtn")
    page.click("#pauseChat button[data-chat=chatty]")
    page.click("#resumeBtn")
    expect(page.locator("#odds")).to_be_visible()
    page.click("#menuBtn")
    page.click("#pauseChat button[data-chat=quiet]")
    page.click("#resumeBtn")
    # The end screen leaves out the odds chart and the science.
    page.evaluate("window.__war.finish()")
    expect(page.locator("#over")).to_be_visible()
    expect(page.locator("#oddsSection")).to_be_hidden()
    expect(page.locator("#science")).to_be_hidden()
    expect(page.locator("#overStats")).not_to_be_empty()
    assert errors == []


def test_mash_to_slam(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=2#debug")
    page.click("#inputSeg button[data-input=mash]")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    expect(page.locator("#slamText")).to_have_text("Tap your deck fast")
    expect(page.locator("#deckHint")).to_have_text("Tap me!")
    box = page.locator("#myPile .stack").bounding_box()
    for _ in range(25):
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    expect(page.locator("#slamText")).to_contain_text("25 taps")
    # Five seconds after the first tap, the taps become a slam: 25 in 5 s is 90.
    page.wait_for_function(f"{STATE}.slams[0] !== undefined", timeout=8000)
    assert page.evaluate(f"{STATE}.slams[0][0]") == 90
    assert errors == []


def test_fling_to_slam(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=2#debug")
    page.click("#inputSeg button[data-input=fling]")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    deck = page.locator("#myPile .card").bounding_box()
    x, y = deck["x"] + deck["width"] / 2, deck["y"] + deck["height"] / 2
    # A twitch isn't a throw.
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 4, y - 6)
    page.mouse.up()
    assert page.evaluate(f"{STATE}.slams[0]") is None
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 20, y - 80, steps=4)
    expect(page.locator("#fx .card.ghost")).to_have_count(1)
    page.mouse.move(x + 40, y - 300, steps=3)
    page.mouse.up()
    assert page.evaluate(f"{STATE}.slams[0][0]") > 30
    assert errors == []


def rank(card: int) -> int:
    """A card's rank, as the page has it: 0 is a two, 12 an ace, 13 a joker."""
    face = card % 54
    return 13 if face >= 52 else face % 13


def test_won_cards_pile_up_and_clean_up_keeps_their_order(page: Page, site_url, errors):
    # Seed 14: you win the first two battles, a joker over a queen, then an
    # ace over a queen.
    start_solo(page, site_url, seed=14)
    heap = page.locator("#winnings .heap .card")
    expect(page.locator("#winnings")).to_be_hidden()
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 2 && {STATE}.canSlam")
    # The table clears, and what you won lands on the heap. Against one bot
    # there's one deck, so the bot's queen is in your theme too.
    expect(heap).to_have_count(2)
    expect(page.locator("#tidyBtn")).to_be_visible()
    # They were thrown from the table at the size they were there (bigger than
    # on the heap), the bot's first and then yours, landing on top.
    thrown = heap.evaluate_all("""cards => cards.map((c) => [
        c.getAttribute('aria-label'), Number(c.style.getPropertyValue('--fs')), parseInt(c.style.getPropertyValue('--d'))])""")
    assert thrown[0][0].startswith("queen") and thrown[1][0].endswith("joker"), thrown
    assert all(scale > 1 for _, scale, _ in thrown)
    assert thrown[0][2] < thrown[1][2]
    expect(page.locator("#winnings .heap .card[aria-label^=queen]")).to_have_attribute("data-deck", page.evaluate("deck"))
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 3")
    expect(heap).to_have_count(4)
    assert len(set(heap.evaluate_all("cards => cards.map((c) => c.style.getPropertyValue('--r'))"))) > 1, "it's a mess"

    # Thrown the bot's first and yours last, so your ace landed on top.
    z_order = """cards => cards.slice().sort((a, b) => a.style.zIndex - b.style.zIndex)
        .map((c) => c.getAttribute('aria-label'))"""
    before = page.evaluate(f"{STATE}.heap")
    assert [rank(c) for c in before] == [10, 13, 10, 12], "a queen, your joker, a queen, your ace"
    stacked = heap.evaluate_all(z_order)
    assert stacked[-1].startswith("ace"), stacked

    counts = page.evaluate(f"{STATE}.counts")
    page.click("#tidyBtn")
    expect(page.locator("#tidyBtn")).to_be_hidden()
    assert page.evaluate(f"{STATE}.tidy")
    assert page.evaluate(f"{STATE}.heap") == before, "the same order, not sorted"
    assert heap.evaluate_all(z_order) == stacked, "the same cards on top of each other"
    assert heap.evaluate_all(z_order)[-1].startswith("ace"), "your ace is still on top"
    angles = heap.evaluate_all("cards => cards.map((c) => c.style.getPropertyValue('--r'))")
    assert set(angles) == {"0deg"}
    expect(page.locator("#caption")).to_contain_text(re.compile(r"Squared away|tidied up|neat stack"))
    assert page.evaluate(f"{STATE}.counts") == counts, "tidying changes nothing"
    assert errors == []


def test_winnings_stay_apart_until_you_pick_them_up(page: Page, site_url, errors):
    # Seed 14: you win the first two battles.
    start_solo(page, site_url, seed=14)
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 2 && {STATE}.canSlam")
    # The two cards you won are beside your deck, not in it.
    assert page.evaluate(f"[{STATE}.counts[0], {STATE}.decks[0], {STATE}.loot[0]]") == [28, 26, 2]
    expect(page.locator("#deckCount")).to_have_text("26")
    expect(page.locator("#lootCount")).to_have_text("2")
    expect(page.locator("#myLabel")).to_contain_text("28 cards")
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 3 && {STATE}.canSlam")
    expect(page.locator("#winnings .heap .card")).to_have_count(4)
    won = page.evaluate(f"{STATE}.heap")

    # Pick up: they go under your deck, as they lie, and the heap is empty.
    page.click("#gatherBtn")
    expect(page.locator("#gatherBtn")).to_be_hidden()
    expect(page.locator("#winnings .heap .card")).to_have_count(0)
    assert page.evaluate(f"[{STATE}.counts[0], {STATE}.decks[0], {STATE}.loot[0]]") == [29, 29, 0]
    expect(page.locator("#deckCount")).to_have_text("29")
    expect(page.locator("#caption")).to_have_text("4 cards back under your deck, in the order you won them.")
    assert len(won) == 4
    assert errors == []


def test_an_empty_deck_waits_for_you_to_pick_up_unless_auto_is_on(page: Page, site_url, errors):
    # Seed 14: you win the first two battles. Leave just the top card in your
    # deck, the rest as winnings, so the deck is out after one battle.
    start_solo(page, site_url, seed=14)
    rig = "S.conn.game.loot[0] = S.conn.game.piles[0].splice(1)"
    page.evaluate(rig)
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 2")
    assert page.evaluate(f"{STATE}.decks[0]") == 0
    expect(page.locator("#slamText")).to_have_text("Pick up your winnings to play")
    page.wait_for_timeout(600)
    assert not page.evaluate(f"{STATE}.canSlam")
    assert page.evaluate("window.__war.slam(80)") is False, "you can't slam an empty deck"
    page.keyboard.press("Space")
    page.wait_for_function(f"{STATE}.canSlam")
    assert page.evaluate(f"{STATE}.decks[0]") == 28

    # Fast mode still leaves it to you.
    page.evaluate(rig)
    page.click("#fastBtn")
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 3")
    expect(page.locator("#slamText")).to_have_text("Pick up your winnings to play")
    page.wait_for_timeout(600)
    assert page.evaluate(f"[{STATE}.decks[0], {STATE}.loot[0], {STATE}.canSlam]") == [0, 29, False]

    # Auto picks them up and plays on, well before the clock would flop your card.
    slams = len(page.evaluate(f"{STATE}.mine"))
    page.click("#autoBtn")
    page.wait_for_function(f"{STATE}.battle >= 4", timeout=4000)
    assert len(page.evaluate(f"{STATE}.mine")) > slams, "Auto slammed the card it picked up"
    assert errors == []


def test_winnings_can_be_shuffled_on_their_way_back(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=14#debug")
    expect(page.locator("#soloWinnings button[data-winnings=kept]")).to_have_attribute("aria-pressed", "true")
    page.click("#soloWinnings button[data-winnings=shuffled]")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    assert page.evaluate(f"{STATE}.shuffle")
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 2 && {STATE}.canSlam")
    page.click("#gatherBtn")
    expect(page.locator("#caption")).to_have_text("2 cards back under your deck, shuffled.")
    page.click("#menuBtn")
    page.click("#quitBtn")
    expect(page.locator("#soloWinnings button[data-winnings=shuffled]")).to_have_attribute("aria-pressed", "true")
    assert errors == []


GATHERING = "document.querySelectorAll('#fx .gathering').length"


def win_two_and_pick_up(page: Page, site_url: str, shuffled: bool = False) -> None:
    """Seed 14: you win the first two battles, then pick up the four cards."""
    page.goto(f"{site_url}/war?seed=14#debug")
    if shuffled:
        page.click("#soloWinnings button[data-winnings=shuffled]")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    for battle in (2, 3):
        page.evaluate("window.__war.slam(80)")
        page.wait_for_function(f"{STATE}.battle === {battle} && {STATE}.canSlam")
    expect(page.locator("#winnings .heap .card")).to_have_count(4)
    page.click("#gatherBtn")
    page.wait_for_function(f"{GATHERING} > 0")


def test_picking_up_sweeps_the_pile_together_and_tucks_it_under_your_deck(page: Page, site_url, errors):
    win_two_and_pick_up(page, site_url)
    g = page.evaluate("window.__war.gather()")
    assert g["seat"] == 0 and g["cards"] == 4 and g["n"] == 4, g
    assert not g["brief"] and not g["calm"] and not g["shuffled"], g
    # The heap's four cards are on their way, under a copy of your deck's top
    # card that lifts as they go under it, and nothing riffles.
    moving = page.evaluate("""() => {
        const fx = [...document.querySelectorAll('#fx .gathering')];
        return {
            cards: fx.filter((n) => !n.classList.contains('back')).length,
            cover: document.querySelectorAll('#fx .tuckcover').length,
            riffle: document.querySelectorAll('#fx .riffling').length,
            running: fx.every((n) => n.getAnimations().some((a) => a.playState === 'running')),
            tucked: document.querySelector('#myPile .stack > .card').style.visibility,
        };
    }""")
    assert moving == {"cards": 4, "cover": 1, "riffle": 0, "running": True, "tucked": "hidden"}, moving
    # Each card has its back with it, and the squared stack turns over so its
    # backs are up as it goes under the deck: faces turned away, backs to us.
    assert page.evaluate("document.querySelectorAll('#fx .gathering.flipside').length") == 4
    turned = page.evaluate("""() => {
        const t = gatherTimes(4, false, false);
        const at = (when) => [...document.querySelectorAll('#fx .gathering:not(.tuckcover)')].map((n) => {
            const a = n.getAnimations()[0];
            a.pause();
            a.currentTime = when;
            return [n.classList.contains('flipside'), new DOMMatrix(getComputedStyle(n).transform).m11 > 0];
        });
        const before = at(t.sweep), after = at(t.settle + 20);
        for (const n of document.querySelectorAll('#fx .gathering')) n.getAnimations().forEach((a) => a.play());
        return { before, after };
    }""")
    assert all(facing == (not back) for back, facing in turned["before"]), "squared up face up"
    assert all(facing == back for back, facing in turned["after"]), "turned over, backs up"
    # The deck's count waits for them: it ticks up as they go under.
    assert page.evaluate(f"{STATE}.shownDecks[0]") < 29
    assert page.evaluate(f"{STATE}.decks[0]") == 29
    # When it's done, everything's where it belongs, and the copies are gone.
    page.wait_for_function(f"{GATHERING} === 0")
    expect(page.locator("#deckCount")).to_have_text("29")
    expect(page.locator("#winnings .heap .card")).to_have_count(0)
    assert page.evaluate(f"[{STATE}.counts[0], {STATE}.decks[0], {STATE}.loot[0], {STATE}.shownDecks[0]]") == [29, 29, 0, 29]
    expect(page.locator("#myPile .stack > .card")).to_be_visible()
    assert page.evaluate("document.querySelectorAll('[data-tucked]').length") == 0
    assert errors == []


def test_a_shuffled_pickup_riffles_the_deck(page: Page, site_url, errors):
    win_two_and_pick_up(page, site_url, shuffled=True)
    g = page.evaluate("window.__war.gather()")
    assert g["shuffled"] and not g["brief"], g
    # The deck splits in two halves that interleave: eight cards of it.
    assert page.evaluate("document.querySelectorAll('#fx .riffling').length") == 8
    kept = page.evaluate("gatherTimes(4, false, false).end")
    assert g["ms"] > kept, "the riffle comes after the cards go under"
    page.wait_for_function(f"{GATHERING} === 0")
    expect(page.locator("#deckCount")).to_have_text("29")
    # Fast mode keeps it in step with the game.
    page.click("#fastBtn")
    assert page.evaluate("gatherTimes(4, false, true).end") < g["ms"]
    assert errors == []


def test_you_can_slam_straight_after_picking_up(page: Page, site_url, errors):
    win_two_and_pick_up(page, site_url)
    # The pickup is still showing, and the slam doesn't wait for it.
    assert page.evaluate(f"{STATE}.canSlam")
    assert page.evaluate("window.__war.slam(80)") is True
    assert page.evaluate(GATHERING) > 0, "the slam came while the cards were still on their way"
    assert page.evaluate(f"{STATE}.slams[0]")
    page.wait_for_function(f"{STATE}.battle === 4")
    page.wait_for_function(f"{GATHERING} === 0")
    assert page.evaluate(f"{STATE}.shownDecks[0]") == page.evaluate(f"{STATE}.decks[0]")
    assert errors == []


def test_reduced_motion_picks_up_without_the_show(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"{site_url}/war?seed=14#debug")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    for battle in (2, 3):
        page.evaluate("window.__war.slam(80)")
        page.wait_for_function(f"{STATE}.battle === {battle} && {STATE}.canSlam")
    page.click("#gatherBtn")
    page.wait_for_function("window.__war.gather()?.started")
    # The cards just go, and the count changes at once.
    assert page.evaluate("window.__war.gather().calm")
    assert page.evaluate(GATHERING) == 0
    expect(page.locator("#winnings .heap .card")).to_have_count(0)
    assert page.evaluate(f"{STATE}.shownDecks[0]") == 29
    expect(page.locator("#deckCount")).to_have_text("29")
    assert errors == []


def test_the_end_screen_tells_the_game_battle_by_battle_and_shares_a_picture(page: Page, site_url, errors):
    start_solo(page, site_url, opponents=1, length="quick", seed=WAR_SEED)
    page.evaluate("window.__war.pace(0.05)")
    page.click("#autoBtn")
    page.wait_for_selector("#over:not([hidden])", timeout=60_000)
    over = page.evaluate(f"{STATE}.over")
    log = page.evaluate("window.__war.log()")
    assert [e["b"] for e in log] == list(range(1, over["battles"] + 1))
    rows = page.locator("#battleLog li")
    expect(rows).to_have_count(over["battles"])
    # The double war that opens the game: eights, threes, then the decider.
    assert len(log[0]["stages"]) == 3
    expect(rows.nth(0).locator(".lw")).to_have_text(["WAR", "DOUBLE WAR"])
    expect(rows.nth(0).locator(".mc")).to_have_count(6)
    expect(rows.nth(0).locator(".mc").nth(0)).to_have_text(re.compile(r"^8"))
    expect(rows.nth(0).locator(".mc").nth(2)).to_have_text(re.compile(r"^3"))
    # What each battle did to your pile adds up to what you ended with.
    deltas = [int(t.replace("−", "-") or 0) for t in rows.locator(".ld").all_text_contents()]
    assert sum(deltas) == over["counts"][0] - 27

    with page.expect_download() as download:
        page.click("#shareImgBtn")
    assert re.fullmatch(r"war-\d{4}-\d{2}-\d{2}\.png", download.value.suggested_filename)
    png = open(download.value.path(), "rb").read()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert (int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")) == (1080, 1350)
    expect(page.locator("#shareImgNote")).to_have_text("Saved the picture. Send it to whoever needs to know.")
    assert errors == []


def test_skipping_to_the_end_still_logs_every_battle(page: Page, site_url, errors):
    start_solo(page, site_url, opponents=3, seed=5)
    page.evaluate("window.__war.slam(50)")
    page.wait_for_function(f"{STATE}.battle >= 2")
    page.click("#menuBtn")
    page.click("#skipBtn")
    expect(page.locator("#over")).to_be_visible()
    battles = page.evaluate(f"{STATE}.over.battles")
    log = page.evaluate("window.__war.log()")
    assert [e["b"] for e in log] == list(range(1, battles + 1))
    expect(page.locator("#battleLog li")).to_have_count(battles)
    # At a bigger table, each row has your card and the one that won.
    expect(page.locator("#battleLog li").nth(0).locator(".lc")).to_contain_text("you")
    assert page.evaluate("window.__war.picture()").startswith("data:image/png;base64,")
    assert errors == []


def test_opponents_pile_up_what_they_win_too(page: Page, site_url, errors):
    # Seed 2: your four loses to the bot's joker in the first battle.
    start_solo(page, site_url, seed=2)
    bot_heap = page.locator("#opponents .tile .heap .card")
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 2")
    # Your four flies over to the bot's heap and its joker lands on top, both
    # in your theme: one bot, one deck.
    expect(bot_heap).to_have_count(2)
    labels = bot_heap.evaluate_all("cards => cards.map((c) => [c.getAttribute('aria-label'), c.dataset.deck, c.style.zIndex])")
    assert labels[0][0].startswith("four") and labels[0][1] == page.evaluate("deck")
    assert labels[1][0].endswith("joker") and labels[1][1] == page.evaluate("deck")
    assert int(labels[1][2]) > int(labels[0][2])
    heaps = page.evaluate(f"{STATE}.heaps")
    assert len(heaps["1"]) == 2 and not heaps.get("0"), heaps
    expect(page.locator("#winnings")).to_be_hidden()
    # The bot's loot pile is its own, beside its card, with a count.
    expect(page.locator("#opponents .tile .tloot .count")).to_have_text("2")
    assert errors == []


def test_bots_clean_up_their_winnings_every_so_often(page: Page, site_url, errors):
    start_solo(page, site_url, seed=WAR_SEED)
    page.evaluate("window.__war.pace(0.05)")
    page.click("#autoBtn")
    # Pots land on the bot's heap in a mess, and every so often it squares
    # them up into a neat stack, in the order it won them.
    page.wait_for_function(f"{STATE}.heaps[1]?.length >= 4 && !{STATE}.tidied[1]", timeout=60_000)
    page.wait_for_function(
        f"""(() => {{
            const cards = [...document.querySelectorAll('#opponents .tile .heap .card')];
            const layers = cards.map((c) => Number(c.style.zIndex));
            return {STATE}.tidied[1] && cards.length >= 4
                && cards.every((c) => c.style.getPropertyValue('--r') === '0deg')
                && layers.every((z, i) => z === i + 1);
        }})()""",
        timeout=60_000,
    )
    # A broom pops up out of its loot pile, so it's noticed.
    expect(page.locator("#fx .floaty.broom")).to_have_text("🧹")
    assert errors == []


def test_others_get_loot_piles_at_a_table_of_up_to_six(page: Page, site_url, errors):
    def play(opponents: int, seed: int) -> int:
        start_solo(page, site_url, opponents=opponents, seed=seed)
        page.evaluate("window.__war.pace(0.3)")
        for _ in range(6):
            page.wait_for_function(f"{STATE}.canSlam", timeout=15_000)
            page.evaluate("window.__war.slam(60)")
        page.wait_for_function(f"{STATE}.battle >= 6 && {STATE}.canSlam", timeout=15_000)
        page.wait_for_timeout(1200)
        return page.locator("#opponents .tile .tloot .heap .card").count()

    # Six players: everyone else has a deck and a loot pile on their tile, and
    # plays onto the table in the middle.
    assert play(5, 3) > 0
    expect(page.locator("#opponents")).to_have_class(re.compile(r"\bloots\b"))
    expect(page.locator("#opponents .tile .tdeck")).to_have_count(5)
    expect(page.locator("#opponents .tile .tslot")).to_have_count(0)
    expect(page.locator("#spots")).to_be_visible()
    expect(page.locator("#spots .spot")).to_have_count(5)
    # Seven: only your own, and each plays on their tile, to keep a busy table readable.
    assert play(6, 4) == 0
    expect(page.locator("#opponents")).not_to_have_class(re.compile(r"\bloots\b"))
    expect(page.locator("#opponents .tile .tdeck")).to_have_count(0)
    expect(page.locator("#opponents .tile .tslot")).to_have_count(6)
    expect(page.locator("#spots")).to_be_hidden()
    assert errors == []


def test_decks_are_as_thick_as_they_are_full(page: Page, site_url, errors):
    # Seed 14: you win the first battle, so the bot's deck goes down by one.
    start_solo(page, site_url, seed=14)
    depth = "(sel) => parseFloat(document.querySelector(sel).style.getPropertyValue('--d'))"
    bot_deck = page.locator("#opponents .tile .tdeck")
    expect(bot_deck.locator(".count")).to_have_text("27")
    full = page.evaluate(f"({depth})('#opponents .tile .tdeck')")
    mine = page.evaluate(f"({depth})('#myPile .stack')")
    assert full > 0.05 and mine == full
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 2")
    # The bot's count sits in its deck's corner, and the deck is thinner.
    expect(bot_deck.locator(".count")).to_have_text("26")
    assert page.evaluate(f"({depth})('#opponents .tile .tdeck')") < full
    # Its card was played onto the table in the middle, not onto its deck.
    expect(page.locator("#spots .spot .tslot > .card")).to_have_attribute("aria-label", re.compile("."))
    # A deck down to its last card is flat.
    page.evaluate("S.conn.game.loot[0] = S.conn.game.piles[0].splice(1)")
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 3")
    page.evaluate("S.decks[0] = 1; renderMe()")
    assert page.evaluate(f"({depth})('#myPile .stack')") == 0
    assert errors == []


def test_how_you_slam_is_remembered(page: Page, site_url, errors):
    start_solo(page, site_url)
    expect(page.locator("#inputBtn")).to_have_text("✊ Hold")
    page.click("#inputBtn")
    expect(page.locator("#inputBtn")).to_have_text("👆 Mash")
    page.click("#inputBtn")
    expect(page.locator("#inputBtn")).to_have_text("🫳 Fling")
    expect(page.locator("#slamText")).to_have_text("Throw a card off your deck")
    assert page.evaluate("JSON.parse(localStorage.getItem('war:input'))") == "fling"
    page.reload()
    expect(page.locator("#inputSeg button[data-input=fling]")).to_have_attribute("aria-pressed", "true")
    assert errors == []


DECKS = ["classic", "neon", "pixel", "royal", "space", "spooky", "candy"]
FACES = ["jack", "queen", "king", "joker"]
TITLE_KING = ".title-cards .card:nth-child(3) .cc"  # the king of hearts on the menu
TITLE_JOKER = ".title-cards .card:nth-child(2)"     # and the red joker


def test_every_deck_looks_different(page: Page, site_url, errors):
    page.goto(f"{site_url}/war#debug")
    expect(page.locator("#menuDecks button")).to_have_count(len(DECKS))
    looks = {}
    for key in DECKS:
        page.evaluate(f"window.__war.deck('{key}')")
        expect(page.locator(TITLE_KING)).to_have_attribute("data-pic", f"{key}-king")
        expect(page.locator(f"{TITLE_JOKER} .cc")).to_have_attribute("data-pic", f"{key}-joker")
        looks[key] = page.evaluate("""() => {
            const face = getComputedStyle(document.querySelector('.title-cards .card'));
            const back = getComputedStyle(document.querySelector('#menuDecks button[aria-pressed=true] .card'));
            return [face.backgroundColor, face.fontFamily, back.backgroundImage].join(' | ');
        }""")
    assert len(set(looks.values())) == len(DECKS), looks
    assert errors == []


def test_every_deck_has_pictures_of_its_own(page: Page, site_url, errors):
    # Each deck's jack, queen, king and joker are pixel art drawn in the
    # page: none blank, no two alike, and the cards show them.
    page.goto(f"{site_url}/war#debug")
    pictures = page.evaluate("""(faces) => Object.keys(DECKS).flatMap((key) => faces.map((face) => {
        const c = Pictures.canvas(key, face);
        const px = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let solid = 0;
        for (let i = 3; i < px.length; i += 4) if (px[i] === 255) solid++;
        return [key, face, solid, Pictures.url(key, face)];
    }))""", FACES)
    assert [(key, face) for key, face, *_ in pictures] == [(key, face) for key in DECKS for face in FACES]
    for key, face, solid, url in pictures:
        assert solid > 200, f"{key} {face} has only {solid} solid pixels"
        assert url.startswith("data:image/png;base64,")
    urls = {(key, face): url for key, face, _, url in pictures}
    assert len(set(urls.values())) == len(pictures)

    for key in DECKS:
        page.evaluate(f"window.__war.deck('{key}')")
        king = page.locator(TITLE_KING)
        expect(king).to_have_attribute("data-pic", f"{key}-king")
        expect(king).to_have_text("")
        shown = king.evaluate("(node) => getComputedStyle(node).backgroundImage")
        assert shown == f'url("{urls[(key, "king")]}")'
    assert errors == []


def test_cards_fall_back_to_emoji_without_pictures(page: Page, site_url, errors):
    # Where the browser can't draw a picture, a card shows its deck's emoji.
    page.add_init_script("""{
        const getContext = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (...args) {
            return this.width === 36 && this.height === 45 ? null : getContext.apply(this, args);
        };
    }""")
    page.goto(f"{site_url}/war#debug")
    page.evaluate("window.__war.deck('candy')")
    expect(page.locator(TITLE_KING)).to_have_text("🍩")
    expect(page.locator(f"{TITLE_JOKER} .cc")).to_have_text("🦷")
    expect(page.locator(".cc.pic")).to_have_count(0)
    assert errors == []


def test_pick_a_deck_in_the_menu_or_mid_game(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=2#debug")
    page.click("#menuDecks button[data-deck=space]")
    expect(page.locator("#menuDeckNote")).to_have_text("Space: Lost among the stars.")
    assert page.evaluate("document.documentElement.dataset.deck") == "space"
    assert page.evaluate("JSON.parse(localStorage.getItem('war:deck'))") == "space"

    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(100)")
    page.wait_for_function(f"{STATE}.battle === 2")
    page.click("#menuBtn")
    page.click("#pauseDecks button[data-deck=candy]")
    expect(page.locator("#pauseDeckNote")).to_have_text("Candy: Very sweet. No nutritional value.")
    page.click("#resumeBtn")
    assert page.evaluate("document.documentElement.dataset.deck") == "candy"
    expect(page.locator("#opponents .tile")).to_have_count(1)
    expect(page.locator("#mySlot .card")).to_have_count(1)

    page.reload()
    assert page.evaluate("document.documentElement.dataset.deck") == "candy"
    expect(page.locator(TITLE_KING)).to_have_attribute("data-pic", "candy-king")
    expect(page.locator("#menuDecks button[data-deck=candy]")).to_have_attribute("aria-pressed", "true")
    assert errors == []


# Every card on screen with the deck it's drawn in, and the theme of the deck
# it comes from, read in one go so nothing moves in between: what's on the
# table (yours, and each bot's spot) and on every loot pile.
SHOWN = """() => {
    const s = window.__war.state();
    const themes = window.__war.themes();
    const label = (card) => cardEl(card).getAttribute('aria-label');
    const out = [];
    for (const [seat, up] of Object.entries(s.table)) {
        const node = seat === '0' ? document.querySelector('#mySlot .card')
            : document.querySelectorAll('#spots .spot')[seat - 1].querySelector('.tslot > .card');
        // A card already laid in a war, or the next battle's, isn't this one.
        if (node.getAttribute('aria-label') !== label(up)) continue;
        out.push({ where: 'table', seat: Number(seat), card: up, shown: node.dataset.deck || null, theme: themes[Math.floor(up / 54)] });
    }
    for (const [seat, cards] of Object.entries(s.heaps)) {
        const box = seat === '0' ? document.querySelector('#winnings .heap')
            : document.querySelectorAll('#opponents .tile')[seat - 1].querySelector('.heap');
        const nodes = [...box.querySelectorAll('.card')];
        cards.forEach((card, i) => out.push({
            where: 'heap', seat: Number(seat), card, shown: nodes[i] && nodes[i].dataset.deck || null,
            theme: themes[Math.floor(card / 54)], label: nodes[i] && nodes[i].getAttribute('aria-label') === label(card),
        }));
    }
    return out;
}"""


def test_against_one_bot_every_card_is_in_your_theme(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=2#debug")
    page.click("#menuDecks button[data-deck=neon]")
    expect(page.locator("#menuDeckNote")).to_have_text("Neon: Glows in the dark.")
    start_solo(page, site_url, seed=2)
    assert page.evaluate("window.__war.themes()") == ["neon"]
    # The bot's card lands on the table in your theme, and its deck has your back.
    bot = page.locator("#spots .spot .tslot > .card")
    expect(bot).to_have_attribute("aria-label", re.compile("."))
    expect(bot).to_have_attribute("data-deck", "neon")
    expect(page.locator("#opponents .tile .tdeck")).to_have_attribute("data-deck", "neon")
    expect(page.locator("#opponents .tile .tdeck .card")).to_have_attribute("data-deck", "neon")
    # Seed 2: its joker beats your four, and both land on its loot pile in neon.
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 2")
    bot_heap = page.locator("#opponents .tile .heap .card")
    expect(bot_heap).to_have_count(2)
    assert bot_heap.evaluate_all("cards => cards.map((c) => c.dataset.deck)") == ["neon", "neon"]
    expect(bot_heap.nth(1).locator(".cc")).to_have_attribute("data-pic", "neon-joker")
    assert page.locator("#opponents .tile").get_attribute("title") == page.evaluate("S.players[1].name") + " (bot)"
    assert errors == []


def play_and_watch(page: Page, battles: int) -> list[dict]:
    """Plays some battles, slamming each card, and returns what was on screen."""
    seen = []
    for _ in range(battles):
        page.wait_for_function(f"{STATE}.canSlam || {STATE}.over")
        if page.evaluate(f"{STATE}.over"):
            break
        seen += page.evaluate(SHOWN)
        battle, stage = page.evaluate(f"[{STATE}.battle, {STATE}.stage]")
        page.evaluate("window.__war.slam(90)")
        # Played out: the cards are on the table until the next stage opens.
        page.wait_for_function(f"S.result && S.result.battle === {battle} && S.result.stage === {stage}")
        seen += page.evaluate(SHOWN)
    return seen


def test_with_several_bots_each_deck_has_a_theme_of_its_own(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=5#debug")
    page.fill("#oppRange", "3")
    page.click("#menuDecks button[data-deck=classic]")
    expect(page.locator("#menuDeckNote")).to_contain_text("2 decks: yours in Classic, the other in Neon.")
    page.fill("#oppRange", "5")
    expect(page.locator("#menuDeckNote")).to_contain_text("3 decks: yours in Classic, the others in Neon and 8-bit.")
    start_solo(page, site_url, opponents=3, seed=5)
    assert page.evaluate("window.__war.themes()") == ["classic", "neon"]
    page.evaluate("window.__war.pace(0.3)")
    seen = play_and_watch(page, 8)
    wrong = [x for x in seen if x["shown"] != x["theme"]]
    assert not wrong, wrong
    table = [x for x in seen if x["where"] == "table"]
    heaped = [x for x in seen if x["where"] == "heap"]
    # Cards from 54 up are the second deck's, below that yours, whoever plays them.
    bots = {(x["card"] >= 54) for x in table if x["seat"] > 0}
    assert bots == {True, False}, table
    assert {x["shown"] for x in heaped} == {"classic", "neon"}, heaped
    assert all(x["label"] for x in heaped)
    # A deck stack's back is its top card's.
    stacks = page.evaluate("""() => [...document.querySelectorAll('#opponents .tile')].map((t, i) => {
        const top = S.conn.game.piles[i + 1][0];
        return [t.querySelector('.tdeck').dataset.deck, top === undefined ? null : window.__war.themes()[Math.floor(top / 54)]];
    })""")
    assert all(shown == top for shown, top in stacks if top), stacks
    assert errors == []


def test_changing_theme_mid_game_keeps_the_decks_apart(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=5#debug")
    page.click("#menuDecks button[data-deck=classic]")
    start_solo(page, site_url, opponents=3, seed=5)
    page.evaluate("window.__war.pace(0.3)")
    play_and_watch(page, 4)
    page.click("#menuBtn")
    expect(page.locator("#pauseDeckNote")).to_contain_text("2 decks: yours in Classic, the other in Neon.")
    # Your deck takes the other deck's theme: the other deck takes yours.
    page.click("#pauseDecks button[data-deck=neon]")
    assert page.evaluate("window.__war.themes()") == ["neon", "classic"]
    expect(page.locator("#pauseDeckNote")).to_contain_text("2 decks: yours in Neon, the other in Classic.")
    page.click("#resumeBtn")
    seen = page.evaluate(SHOWN)
    assert seen and all(x["shown"] == x["theme"] for x in seen), seen
    assert {x["shown"] for x in seen if x["where"] == "heap"} <= {"neon", "classic"}
    # A theme no deck had just replaces yours.
    page.evaluate("window.__war.deck('candy')")
    assert page.evaluate("window.__war.themes()") == ["candy", "classic"]
    seen = page.evaluate(SHOWN)
    assert all(x["shown"] == x["theme"] for x in seen), seen
    assert any(x["shown"] == "candy" for x in seen) and any(x["shown"] == "classic" for x in seen), seen
    seen = play_and_watch(page, 3)
    assert all(x["shown"] == x["theme"] for x in seen), seen
    assert errors == []


def test_space_bar_slams(page: Page, site_url, errors):
    start_solo(page, site_url)
    page.keyboard.down(" ")
    page.wait_for_timeout(400)
    page.keyboard.up(" ")
    assert page.evaluate(f"{STATE}.slams[0]") is not None
    assert errors == []


def test_slam_power_changes_nothing(page: Page, site_url):
    def play(power: int) -> list:
        page.goto("about:blank")
        start_solo(page, site_url, opponents=3, seed=99)
        page.evaluate("window.__war.pace(0.05)")
        log = []
        for _ in range(6):
            page.wait_for_function(f"{STATE}.canSlam")
            battle, stage = page.evaluate(f"[{STATE}.battle, {STATE}.stage]")
            assert page.evaluate(f"window.__war.slam({power})")
            page.wait_for_function(f"{STATE}.battle !== {battle} || {STATE}.stage !== {stage}")
            log.append([battle, stage, page.evaluate(f"{STATE}.counts")])
        return log

    assert play(0) == play(200)


def test_a_table_of_fifty_fits_a_phone(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    start_solo(page, site_url, opponents=49)
    assert page.locator("#opponents .tile").count() == 49
    expect(page.locator("#battleSub")).to_contain_text("50 of 50 still in")
    page.evaluate("window.__war.slam(120)")
    page.wait_for_function(f"{STATE}.battle === 2 || {STATE}.stage === 1")
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    assert errors == []


def test_finishing_shows_the_results_and_unlocks_a_power_up(page: Page, site_url, errors):
    start_solo(page, site_url, opponents=4, length="quick")
    page.evaluate("window.__war.slam(80)")
    page.evaluate("window.__war.finish()")
    expect(page.locator("#over")).to_be_visible()
    expect(page.locator("#overSub")).to_contain_text("battles")
    expect(page.locator("#standings li.me")).to_be_visible()
    expect(page.locator("#science")).not_to_be_empty()
    expect(page.locator("#unlock")).to_contain_text("New power-up")
    styles = page.evaluate("JSON.parse(localStorage.getItem('war:styles'))")
    assert len(styles) == 2

    # Equip it from the menu.
    page.click("#overMenuBtn")
    page.click("#stylesBtn")
    unlocked = [i for i in styles if i != 0][0]
    page.click(f"#styleList button[data-i='{unlocked}']")
    page.click("#stylesDone")
    assert page.evaluate("JSON.parse(localStorage.getItem('war:style'))") == unlocked
    expect(page.locator("#lifetime")).to_contain_text("1 game played")

    # Slams carry the power-up's style, which is all it does.
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(50)")
    assert page.evaluate(f"{STATE}.slams[0]") == [50, unlocked]
    assert errors == []


def test_recent_games_are_listed_newest_first(page: Page, site_url, errors):
    page.goto(f"{site_url}/war#debug")
    page.click("#historyBtn")
    expect(page.locator("#historyNote")).to_have_text("No games yet. Finish one and it shows up here.")
    page.click("#historyDone")
    # Older games already on this device: only the last 30 are kept.
    page.evaluate("""localStorage.setItem('war:history', JSON.stringify(Array(29).fill({
        at: Date.now() - 3 * 86400000, mode: 'solo', code: null, length: 'standard', players: 3,
        rivals: ['Sir Toast', 'Lady Beans'], place: 2, won: false, shared: false, cards: 40, out: 0,
        battles: 60, wars: 4, best: 90, slams: 60, peak: 0.4 })))""")

    for opponents in (1, 4):
        page.fill("#oppRange", str(opponents))
        page.click("#soloLength button[data-length=quick]")
        page.click("#soloBtn")
        page.wait_for_function(f"{STATE}.canSlam")
        page.evaluate("window.__war.slam(180)")
        page.evaluate("window.__war.finish()")
        expect(page.locator("#over")).to_be_visible()
        page.click("#overMenuBtn")

    saved = page.evaluate("JSON.parse(localStorage.getItem('war:history'))")
    assert len(saved) == 30
    assert [g["players"] for g in saved[:3]] == [5, 2, 3]
    page.click("#historyBtn")
    games = page.locator("#historyList li")
    expect(games).to_have_count(30)
    expect(games.nth(0)).to_contain_text("Solo · Skirmish · vs ")
    expect(games.nth(0)).to_contain_text(" and 1 more")
    expect(games.nth(0)).to_contain_text("mightiest slam: COSMIC SLAM")
    expect(games.nth(0).locator(".g-when")).to_contain_text("Today")
    expect(games.nth(1)).not_to_contain_text("more")
    expect(games.nth(2)).to_contain_text("2nd of 3")
    expect(games.nth(2)).to_contain_text("best odds 40%")
    page.keyboard.press("Escape")
    expect(page.locator("#historyOv")).to_be_hidden()
    assert errors == []


def test_the_science_measures_your_slams(page: Page, site_url, errors):
    start_solo(page, site_url, opponents=1, length="quick", seed=3)
    page.evaluate("window.__war.pace(0.05)")
    page.click("#autoBtn")
    page.wait_for_selector("#over:not([hidden])", timeout=60_000)
    expect(page.locator("#science")).to_contain_text("Correlation between slam power and winning: r = ")
    mine = page.evaluate(f"{STATE}.mine")
    assert len(mine) >= 15 and all(won is not None for _, won in mine)
    # Your win probability through the game, with a verdict on it.
    expect(page.locator("#oddsChart svg polyline")).to_have_count(1)
    expect(page.locator("#oddsVerdict")).not_to_be_empty()
    assert errors == []


def test_win_probability_follows_the_game_and_ignores_slams(page: Page, site_url, errors):
    # Seed 2: your four loses to a joker in the first battle.
    start_solo(page, site_url, seed=2)
    expect(page.locator("#odds")).to_be_visible()
    expect(page.locator("#oddsYou")).to_have_text(re.compile(r"^You (\d+%|<1%|>99%)$"))
    expect(page.locator("#oddsFav")).to_contain_text("%")
    page.evaluate("window.__war.slam(150)")
    expect(page.locator("#oddsNote")).to_have_text("Slam impact on win probability: +0.0%")
    joker = page.locator("#spots .spot .tslot > .card.joker")
    expect(joker).to_be_visible()
    expect(joker).to_have_attribute("aria-label", re.compile(r"^(red|black) joker$"))
    expect(page.locator("#banner")).to_have_text("JOKER!")
    page.wait_for_function(f"{STATE}.odds.length === 2", timeout=15_000)
    (_, start), (_, after) = page.evaluate(f"{STATE}.odds")
    assert after < start, "losing a battle costs you"
    expect(page.locator("#oddsDelta")).to_have_text(re.compile(r"^▼\d+$"))
    assert errors == []


def test_the_win_probability_model(page: Page, site_url):
    page.goto(f"{site_url}/war#debug")
    odds = lambda counts, battle, limit, sims=200: page.evaluate(f"window.__war.odds({counts}, {battle}, {limit}, {sims})")
    # Head to head it's worked out, not simulated.
    assert odds([27, 27], 1, 60) == [pytest.approx(0.5), pytest.approx(0.5)]
    assert odds([26, 28], 2, 60)[0] < 0.5
    assert odds([47, 7], 55, 60)[0] > 0.99, "47 cards to 7 with six battles left is nearly certain"
    assert odds([54, 0], 10, 60) == [1, 0]
    # ...and agrees with playing it out with the real rules.
    for counts, battle, limit in [([31, 23], 40, 60), ([12, 42], 1, 400)]:
        worked_out = odds(counts, battle, limit)[0]
        simulated = page.evaluate(f"window.__war.simulate({counts}, {battle}, {limit}, 4000)")[0]
        assert abs(worked_out - simulated) < 0.04, (counts, worked_out, simulated)
    # More players are simulated.
    crowd = odds("Array(10).fill(26).map((n, i) => i ? n - 2 : n + 18)", 1, 60)
    assert abs(sum(crowd) - 1) < 1e-9
    assert crowd[0] == max(crowd), "the player with the most cards is the favorite"


def test_hiding_the_tab_pauses_a_solo_game(page: Page, site_url, errors):
    start_solo(page, site_url, opponents=2)
    page.evaluate("window.__war.pace(0.05)")
    page.evaluate("window.__war.slam(60)")
    page.evaluate(
        "Object.defineProperty(document, 'hidden', { value: true, configurable: true });"
        "document.dispatchEvent(new Event('visibilitychange'))"
    )
    expect(page.locator("#pause")).to_be_visible()
    page.wait_for_timeout(1000)  # a battle played out just before may still be on its way to the table
    battle, stage = page.evaluate(f"[{STATE}.battle, {STATE}.stage]")
    page.wait_for_timeout(1500)
    assert page.evaluate(f"[{STATE}.battle, {STATE}.stage]") == [battle, stage], "nothing happens while paused"
    page.evaluate("Object.defineProperty(document, 'hidden', { value: false, configurable: true })")
    page.click("#resumeBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(10)")
    page.wait_for_function(f"{STATE}.battle !== {battle} || {STATE}.stage !== {stage}")
    assert errors == []


def test_quit_to_menu(page: Page, site_url, errors):
    start_solo(page, site_url)
    page.click("#menuBtn")
    page.click("#quitBtn")
    expect(page.locator("#menu")).to_be_visible()
    expect(page.locator("#app")).to_be_hidden()
    assert errors == []


def test_reduced_motion_skips_the_fireworks(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")
    start_solo(page, site_url)
    page.evaluate("window.__war.slam(200)")
    page.wait_for_timeout(400)
    assert page.locator("#fx .bit").count() == 0
    assert page.evaluate("document.getElementById('app').classList.contains('shake')") is False
    assert errors == []


def test_rooms_stay_hidden_without_a_server(page: Page, site_url, errors):
    without_worker(page, site_url, "war")
    page.goto(f"{site_url}/war?room=K7QP")
    expect(page.locator("#soloBtn")).to_be_visible()
    expect(page.locator("#friends")).to_be_hidden()
    assert errors == []


MUSIC = "window.__war.music()"


def test_every_song_plays_well_below_clipping(page: Page, site_url, errors):
    page.goto(f"{site_url}/war#debug")
    levels = page.evaluate("window.__war.musicLevels()")
    assert sorted(levels) == sorted(page.evaluate(f"{MUSIC}.songs"))
    for name, level in levels.items():
        assert level["peak"] < 0.8, f"{name} is too loud"
        assert level["rms"] > 0.02, f"{name} is too quiet"
        assert level["seconds"] > 3, f"{name} is too short"
    assert errors == []


def test_the_jokers_laugh_is_loud_but_not_clipping(page: Page, site_url, errors):
    page.goto(f"{site_url}/war#debug")
    levels = page.evaluate("window.__war.laughLevels()")
    for level in ("1", "2"):
        assert levels[level]["peak"] < 0.9, f"level {level} is too loud"
        assert levels[level]["rms"] > 0.01, f"level {level} is too quiet"
    assert errors == []


def test_music_follows_the_game_and_can_be_turned_off(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed={WAR_SEED}#debug")
    assert page.evaluate(f"{MUSIC}.playing") is None, "no music before the first tap"
    page.click("#menu h1")
    page.wait_for_function(f"{MUSIC}.playing === 'menu'")
    page.click("#soloBtn")
    page.wait_for_function(f"{MUSIC}.playing === 'battle'")
    page.wait_for_function(f"{STATE}.canSlam")
    # The first battle is a tie, then a double war.
    page.evaluate("window.__war.slam(60)")
    page.wait_for_function(f"{MUSIC}.playing === 'war'")
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    page.evaluate("window.__war.slam(60)")
    page.wait_for_function(f"{MUSIC}.playing === 'war2'")

    toggle = page.locator("#app .music-toggle")
    toggle.click()
    assert page.evaluate(f"{MUSIC}.playing") is None
    expect(toggle).to_have_attribute("aria-label", "Music off")
    expect(toggle).to_have_class(re.compile(r"\boff\b"))
    assert page.evaluate("JSON.parse(localStorage.getItem('war:music'))") is False
    toggle.click()
    page.wait_for_function(f"{MUSIC}.playing === 'war2'")

    page.evaluate("window.__war.finish()")
    expect(page.locator("#over")).to_be_visible()
    page.wait_for_function(f"['win', 'lose'].includes({MUSIC}.playing)")
    page.wait_for_function(f"{MUSIC}.playing === null", timeout=15_000)  # a jingle plays once
    page.click("#overMenuBtn")
    page.wait_for_function(f"{MUSIC}.playing === 'menu'")
    assert errors == []


def test_music_stays_off_once_turned_off(page: Page, site_url, errors):
    page.goto(f"{site_url}/war#debug")
    page.click("#menu .music-toggle")
    page.reload()
    expect(page.locator("#menu .music-toggle")).to_have_attribute("aria-label", "Music off")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    assert page.evaluate(f"{MUSIC}.playing") is None
    # Sound effects have a switch of their own.
    expect(page.locator("#app .sound-toggle")).to_have_attribute("aria-label", "Sound effects on")
    assert errors == []


# ---- The page's state machines: screen, overlay, session ----


def hide_tab(page: Page, hidden: bool = True) -> None:
    page.evaluate("(h) => { Object.defineProperty(document, 'hidden', { value: h, configurable: true });"
                  " document.dispatchEvent(new Event('visibilitychange')); }", hidden)


def test_the_page_shows_which_screen_its_on(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=7#debug")
    html = page.locator("html")
    expect(html).to_have_attribute("data-screen", "menu")
    expect(html).to_have_attribute("data-session", "none")
    expect(html).to_have_attribute("data-overlay", "none")
    page.click("#stylesBtn")
    expect(html).to_have_attribute("data-overlay", "styles")
    expect(page.locator("#menu")).to_have_attribute("inert", "")  # only the top layer takes taps
    page.click("#stylesDone")
    page.click("#soloBtn")
    expect(html).to_have_attribute("data-screen", "table")
    expect(html).to_have_attribute("data-session", "solo")
    expect(page.locator("#app")).not_to_have_attribute("inert", "")
    page.click("#menuBtn")
    expect(html).to_have_attribute("data-overlay", "pause")
    expect(page.locator("#app")).to_have_attribute("inert", "")
    page.click("#resumeBtn")
    expect(html).to_have_attribute("data-overlay", "none")
    page.evaluate("window.__war.slam(60)")
    page.evaluate("window.__war.finish()")
    expect(html).to_have_attribute("data-screen", "over")
    expect(page.locator("#app")).to_have_attribute("inert", "")
    state = page.evaluate(STATE)
    assert (state["screen"], state["overlay"], state["session"], state["conn"]) == ("over", "none", "solo", "off")
    page.click("#overMenuBtn")
    expect(html).to_have_attribute("data-screen", "menu")
    expect(html).to_have_attribute("data-session", "none")
    assert errors == []


def test_escape_closes_the_power_ups_on_the_menu_too(page: Page, site_url, errors):
    page.goto(f"{site_url}/war#debug")
    page.click("#stylesBtn")
    expect(page.locator("#stylesOv")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#stylesOv")).to_be_hidden()
    assert errors == []


def test_enter_and_space_press_the_button_youre_on(page: Page, site_url, errors):
    start_solo(page, site_url)
    # On your deck they slam, as ever.
    page.focus("#myPile")
    page.keyboard.down(" ")
    page.wait_for_timeout(300)
    page.keyboard.up(" ")
    assert page.evaluate(f"{STATE}.slams[0]") is not None
    # On a button, they press it.
    page.focus("#autoBtn")
    page.keyboard.press("Enter")
    expect(page.locator("#autoBtn")).to_have_attribute("aria-pressed", "true")
    page.focus("#menuBtn")
    page.keyboard.press(" ")
    expect(page.locator("#pause")).to_be_visible()
    assert errors == []


def test_a_war_you_started_waits_while_youre_paused(page: Page, site_url, errors):
    start_solo(page, site_url, seed=WAR_SEED)
    page.evaluate("window.__war.slam(50)")
    page.wait_for_function(f"{STATE}.stage === 1 && {STATE}.canSlam")
    hold_slam(page, 300)  # one face-down card down
    page.wait_for_function(f"{STATE}.plan && {STATE}.plan.done.length === 1")
    page.click("#menuBtn")
    expect(page.locator("#pauseNote")).to_have_text("The war waits for you.")
    page.evaluate("window.__war.hurry()")  # as if the war's clock had all but run out while you were away
    page.wait_for_timeout(1500)
    assert len(page.evaluate(f"{STATE}.plan.done")) == 1, "nothing is slammed for you while you're paused"
    assert page.evaluate(f"{STATE}.slams[0]") is None
    # Back at the table, the war is still yours to finish.
    page.click("#resumeBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    assert page.evaluate("window.__war.slam(70)")
    done = page.evaluate(f"{STATE}.plan.done")
    assert len(done) == 4 and done[1:] == [70, 70, 70]
    assert errors == []


def test_the_next_battle_waits_while_youre_paused(page: Page, site_url, errors):
    start_solo(page, site_url, opponents=3)
    page.evaluate("() => { window.slams = 0; const slam = Sound.slam.bind(Sound); Sound.slam = (...a) => { window.slams++; return slam(...a); }; }")
    page.evaluate("window.__war.slam(60)")
    page.wait_for_function("S.pending !== null", polling=20)  # played, and the next stage on its way
    page.click("#menuBtn")
    paused = page.evaluate(f"[{STATE}.battle, {STATE}.stage, window.slams]")
    page.wait_for_timeout(3500)  # longer than the cards stay up before the next stage
    assert page.evaluate(f"[{STATE}.battle, {STATE}.stage, window.slams]") == paused, "it all waits for you, the bots too"
    page.click("#resumeBtn")
    page.wait_for_function(f"[{STATE}.battle, {STATE}.stage].join() !== '{paused[0]},{paused[1]}'")
    assert errors == []


def test_pausing_holds_the_joker_still_behind_the_pause_menu(page: Page, site_url, errors):
    start_solo(page, site_url, seed=JOKER_SEED)
    page.evaluate("window.__war.slam(60)")
    expect(page.locator("#fx .jk")).to_have_count(1)
    page.wait_for_function("window.__war.joker() && window.__war.joker().u > 0.5")
    page.click("#menuBtn")
    held = page.evaluate("window.__war.joker().u")
    page.wait_for_timeout(1200)
    assert page.evaluate("window.__war.joker().u") == held, "the show waits for you"
    # And it's under the pause menu, not over it.
    assert page.evaluate("+getComputedStyle(document.getElementById('fx')).zIndex < +getComputedStyle(document.getElementById('pause')).zIndex")
    page.click("#resumeBtn")
    page.wait_for_function(f"{STATE}.stage === 1", timeout=10000)
    expect(page.locator("#fx .jk")).to_have_count(0)
    assert errors == []


def test_skipping_to_the_end_as_a_battle_lands_still_logs_it(page: Page, site_url, errors):
    start_solo(page, site_url, length="quick", seed=5)
    page.wait_for_timeout(1600)  # past the bot's moment, so your slam plays the battle at once
    # The battle is played while your slam is still landing, and you skip to
    # the end right then.
    held = page.evaluate("""() => new Promise((done) => {
        window.__war.slam(60);
        const poll = () => {
            if (S.result !== null) done(false);
            else if (S.conn.game.battle === 2) { openPause(); document.getElementById('skipBtn').click(); done(true); }
            else setTimeout(poll, 1);
        };
        poll();
    })""")
    assert held, "the battle was played while the slam was landing"
    expect(page.locator("#over")).to_be_visible()
    battles = page.evaluate(f"{STATE}.over.battles")
    assert [e["b"] for e in page.evaluate("window.__war.log()")] == list(range(1, battles + 1))
    expect(page.locator("#logTitle")).to_have_text("Battle by battle")
    assert errors == []


def test_the_end_of_games_jingle_plays_once(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed={WAR_SEED}#debug")
    page.click("#menu h1")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    page.evaluate("window.__war.slam(60)")
    page.evaluate("window.__war.finish()")
    page.wait_for_function(f"['win', 'lose'].includes({MUSIC}.playing)")
    page.wait_for_function(f"{MUSIC}.playing === null", timeout=15_000)
    hide_tab(page)
    hide_tab(page, False)
    page.wait_for_timeout(1000)
    assert page.evaluate(f"{MUSIC}.playing") is None, "a jingle that has played doesn't play again"
    assert errors == []


def test_a_game_that_ends_while_the_tab_is_hidden_ends_quietly(page: Page, site_url, errors):
    start_solo(page, site_url, opponents=1, length="quick", seed=3)
    page.wait_for_function(f"{MUSIC}.playing === 'battle'")
    page.evaluate("window.__war.pace(0.05)")
    page.click("#autoBtn")
    page.wait_for_function(f"{STATE}.phase === 'over'", timeout=60_000, polling=20)
    hide_tab(page)  # right after the last battle, before the results come up
    expect(page.locator("#over")).to_be_visible()
    page.wait_for_timeout(300)
    assert page.evaluate(f"{MUSIC}.playing") is None, "no jingle in a hidden tab"
    hide_tab(page, False)
    page.wait_for_timeout(1000)
    assert page.evaluate(f"{MUSIC}.playing") is None, "nor battle music on the results"
    assert errors == []
