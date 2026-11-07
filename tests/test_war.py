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
    box = page.locator("#slamBtn").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(ms)
    page.mouse.up()


def test_hold_to_charge_and_release_to_slam(page: Page, site_url, errors):
    start_solo(page, site_url)
    assert page.locator("#opponents .tile").count() == 1
    box = page.locator("#slamBtn").bounding_box()
    page.mouse.move(box["x"] + 40, box["y"] + 30)
    page.mouse.down()
    page.wait_for_timeout(900)
    expect(page.locator("#slamText")).not_to_have_text("Hold to slam")
    page.mouse.up()

    power = page.evaluate(f"{STATE}.slams[0][0]")
    assert power > 30, "nearly a second of charging is a decent slam"
    # The battle plays out once the bot has slammed too: a winner, or a war.
    page.wait_for_function(f"{STATE}.battle === 2 || {STATE}.stage === 1")
    counts = page.evaluate(f"{STATE}.counts")
    assert 40 < sum(counts) <= 54, "cards in a war's pot belong to nobody yet"
    expect(page.locator("#caption")).not_to_be_empty()
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
        expect(page.locator("#myWar .wpile .card")).to_have_count(n)
        assert page.evaluate(f"{STATE}.canSlam"), "the war isn't slammed until the last card"
    expect(page.locator("#myWar .wcount")).to_have_text("3 face down")
    expect(page.locator("#slamText")).to_have_text("The decider · hold")
    hold_slam(page, 300)
    assert page.evaluate(f"{STATE}.slams[0]") is not None
    assert len(page.evaluate(f"{STATE}.mine")) == 5, "one slam for the battle, four for the war"
    expect(page.locator("#caption")).to_contain_text("War power")
    # The bot slams its face-down cards too.
    expect(page.locator("#opponents .tile .downs")).to_have_text("+3")
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


def test_mash_to_slam(page: Page, site_url, errors):
    page.goto(f"{site_url}/war?seed=2#debug")
    page.click("#inputSeg button[data-input=mash]")
    page.click("#soloBtn")
    page.wait_for_function(f"{STATE}.canSlam")
    expect(page.locator("#slamText")).to_have_text("Tap fast to slam")
    box = page.locator("#slamBtn").bounding_box()
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


def test_won_cards_pile_up_and_clean_up_sorts_them(page: Page, site_url, errors):
    # Seed 14: you win the first two battles, a joker over a queen, then an
    # ace over a queen.
    start_solo(page, site_url, seed=14)
    heap = page.locator("#winnings .heap .card")
    expect(page.locator("#winnings")).to_be_hidden()
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 2 && {STATE}.canSlam")
    # The table clears, and what you won lands on the heap: the bot's queen in
    # the bot's deck, your joker in yours.
    expect(heap).to_have_count(2)
    expect(page.locator("#tidyBtn")).to_be_visible()
    # They were thrown from the table at the size they were there (bigger than
    # on the heap), the bot's first and then yours, landing on top.
    thrown = heap.evaluate_all("""cards => cards.map((c) => [
        c.getAttribute('aria-label'), Number(c.style.getPropertyValue('--fs')), parseInt(c.style.getPropertyValue('--d'))])""")
    assert thrown[0][0].startswith("queen") and thrown[1][0].endswith("joker"), thrown
    assert all(scale > 1 for _, scale, _ in thrown)
    assert thrown[0][2] < thrown[1][2]
    bot_deck = page.evaluate("deckOf(1)")
    expect(page.locator("#winnings .heap .card[aria-label^=queen]")).to_have_attribute("data-deck", bot_deck)
    page.evaluate("window.__war.slam(80)")
    page.wait_for_function(f"{STATE}.battle === 3")
    expect(heap).to_have_count(4)
    assert len(set(heap.evaluate_all("cards => cards.map((c) => c.style.getPropertyValue('--r'))"))) > 1, "it's a mess"

    counts = page.evaluate(f"{STATE}.counts")
    page.click("#tidyBtn")
    expect(page.locator("#tidyBtn")).to_be_hidden()
    assert page.evaluate(f"{STATE}.tidy")
    ranks = [rank(c) for c in page.evaluate(f"{STATE}.heap")]
    assert ranks == [10, 10, 12, 13], "sorted, twos at the bottom and the joker on top"
    angles = heap.evaluate_all("cards => cards.map((c) => c.style.getPropertyValue('--r'))")
    assert set(angles) == {"0deg"}
    top = heap.evaluate_all("cards => cards.sort((a, b) => b.style.zIndex - a.style.zIndex)[0].getAttribute('aria-label')")
    assert top.endswith("joker")
    expect(page.locator("#caption")).to_contain_text(re.compile(r"Squared away|tidied and sorted|neat stack"))
    assert page.evaluate(f"{STATE}.counts") == counts, "tidying changes nothing"
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


def test_how_you_slam_is_remembered(page: Page, site_url, errors):
    start_solo(page, site_url)
    expect(page.locator("#inputBtn")).to_have_text("✊ Hold")
    page.click("#inputBtn")
    expect(page.locator("#inputBtn")).to_have_text("👆 Mash")
    page.click("#inputBtn")
    expect(page.locator("#inputBtn")).to_have_text("🫳 Fling")
    expect(page.locator("#slamText")).to_have_text("Fling a card")
    assert page.evaluate("JSON.parse(localStorage.getItem('war:input'))") == "fling"
    page.reload()
    expect(page.locator("#inputSeg button[data-input=fling]")).to_have_attribute("aria-pressed", "true")
    assert errors == []


DECKS = ["classic", "neon", "pixel", "royal", "space", "spooky", "candy"]
KINGS = {"classic": "👑", "neon": "😎", "pixel": "🕹️", "royal": "🤴", "space": "🛸", "spooky": "💀", "candy": "🍩"}
JOKERS = {"classic": "🤡", "neon": "🤩", "pixel": "🐛", "royal": "🎭", "space": "☄️", "spooky": "👻", "candy": "🦷"}
TITLE_KING = ".title-cards .card:nth-child(3) .cc"  # the king of hearts on the menu
TITLE_JOKER = ".title-cards .card:nth-child(2)"     # and the red joker


def test_every_deck_looks_different(page: Page, site_url, errors):
    page.goto(f"{site_url}/war#debug")
    expect(page.locator("#menuDecks button")).to_have_count(len(DECKS))
    looks = {}
    for key in DECKS:
        page.evaluate(f"window.__war.deck('{key}')")
        expect(page.locator(TITLE_KING)).to_have_text(KINGS[key])
        expect(page.locator(f"{TITLE_JOKER} .cc")).to_have_text(JOKERS[key])
        looks[key] = page.evaluate("""() => {
            const face = getComputedStyle(document.querySelector('.title-cards .card'));
            const back = getComputedStyle(document.querySelector('#menuDecks button[aria-pressed=true] .card'));
            return [face.backgroundColor, face.fontFamily, back.backgroundImage].join(' | ');
        }""")
    assert len(set(looks.values())) == len(DECKS), looks
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
    expect(page.locator(TITLE_KING)).to_have_text("🍩")
    expect(page.locator("#menuDecks button[data-deck=candy]")).to_have_attribute("aria-pressed", "true")
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
    joker = page.locator("#opponents .tile .card.joker")
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
