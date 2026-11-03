"""War, played solo against bots. Rooms are in test_war_rooms.py.

?seed= makes the deal repeat, and #debug exposes window.__war: state() reads
the table, slam(power) slams right away, pace(p) speeds the game up and
finish() plays the rest of it out at once.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

STATE = "window.__war.state()"


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
    assert 40 < sum(counts) <= 52, "cards in a war's pot belong to nobody yet"
    expect(page.locator("#caption")).not_to_be_empty()
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


def test_the_science_measures_your_slams(page: Page, site_url, errors):
    start_solo(page, site_url, opponents=1, length="quick", seed=3)
    page.evaluate("window.__war.pace(0.05)")
    page.click("#autoBtn")
    page.wait_for_selector("#over:not([hidden])", timeout=60_000)
    expect(page.locator("#science")).to_contain_text("Correlation between slam power and winning: r = ")
    mine = page.evaluate(f"{STATE}.mine")
    assert len(mine) >= 15 and all(won is not None for _, won in mine)
    assert errors == []


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
    page.goto(f"{site_url}/war?room=K7QP")
    expect(page.locator("#soloBtn")).to_be_visible()
    expect(page.locator("#friends")).to_be_hidden()
    assert errors == []
