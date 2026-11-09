import re

from playwright.sync_api import Page, expect

# Nib's square, as the page places its sprite.
NIB = "() => { const s = document.querySelector('.sprite.player').style; return [+s.getPropertyValue('--x'), +s.getPropertyValue('--y')]; }"


def test_play_starts_a_level(page: Page, site_url, errors):
    page.goto(f"{site_url}/doodle-chomp")

    page.click("#playBtn")
    expect(page.locator("#menu")).to_be_hidden()
    expect(page.locator("#cells .cell").first).to_be_visible()
    expect(page.locator("#ruleKeyText")).not_to_be_empty()
    for key in ["ArrowRight", "ArrowDown", "Space", "ArrowLeft", "Space"]:
        page.keyboard.press(key)
        page.wait_for_timeout(150)
    expect(page.locator("#levelOut")).to_have_text("1")
    assert errors == []


def test_pause_and_resume(page: Page, site_url, errors):
    page.goto(f"{site_url}/doodle-chomp")
    page.click("#playBtn")
    page.keyboard.press("p")
    expect(page.locator("#overlay")).to_be_visible()
    expect(page.locator("#ovTitle")).to_have_text("Paused")
    page.keyboard.press("p")
    expect(page.locator("#overlay")).to_be_hidden()
    assert errors == []


def wrong_square(page: Page) -> tuple[int, int]:
    """A square Nib shouldn't chomp: on the first game, one that isn't a multiple of the rule's number."""
    assert page.locator("#rulePre").text_content() == "Chomp the multiples of"
    n = int(page.locator("#ruleKeyText").text_content())
    cols = int(page.evaluate("document.getElementById('board').style.getPropertyValue('--cols')"))
    labels = page.locator("#cells .cell").evaluate_all("cells => cells.map((c) => c.getAttribute('aria-label'))")
    i = next(i for i, text in enumerate(labels) if int(text) % n)
    return i % cols, i // cols


def walk_to(page: Page, c: int, r: int) -> None:
    """Step Nib there with the arrow keys, one square at a time (a step too soon after the last is dropped)."""
    for _ in range(40):
        x, y = page.evaluate(NIB)
        if (x, y) == (c, r):
            return
        page.keyboard.press("ArrowRight" if c > x else "ArrowLeft" if c < x else "ArrowDown" if r > y else "ArrowUp")
        page.wait_for_timeout(100)
    assert page.evaluate(NIB) == [c, r]


def keep_going(page: Page) -> None:
    """Wait for the card a lost life shows, then tap its button."""
    expect(page.locator("#overlay")).to_be_visible()
    page.wait_for_timeout(500)  # the card ignores taps for its first moments
    page.click("#ovActions button >> nth=0")


def test_the_page_shows_which_screen_its_on(page: Page, site_url, errors):
    page.goto(f"{site_url}/doodle-chomp#debug")
    html = page.locator("html")
    expect(html).to_have_attribute("data-screen", "menu")
    expect(page.locator("#stage")).to_have_attribute("inert", "")  # the menu covers the game
    page.click("#playBtn")
    expect(html).to_have_attribute("data-screen", "play")
    expect(page.locator("#stage")).not_to_have_attribute("inert", "")
    page.keyboard.press("p")
    expect(html).to_have_attribute("data-screen", "paused")
    expect(page.locator("#hud")).to_have_attribute("inert", "")  # the pause card covers it
    page.keyboard.press("p")
    expect(html).to_have_attribute("data-screen", "play")

    walk_to(page, *wrong_square(page))
    page.keyboard.press("Space")
    expect(html).to_have_attribute("data-screen", "message")
    expect(page.locator("#ovTitle")).to_have_text("Oops!")
    keep_going(page)
    expect(html).to_have_attribute("data-screen", "play")

    page.evaluate("window.__dc.end()")
    expect(html).to_have_attribute("data-screen", "over")
    page.wait_for_timeout(500)
    page.click("#ovActions button >> text=Change game")
    expect(html).to_have_attribute("data-screen", "menu")
    expect(page.locator("#menu")).to_be_visible()
    assert errors == []


def test_a_tap_that_ends_after_a_lost_life_doesnt_walk_nib(page: Page, site_url, errors):
    page.goto(f"{site_url}/doodle-chomp#debug")
    page.click("#playBtn")
    c, r = wrong_square(page)
    walk_to(page, c, r)
    # Press on a far square, and hold it while Nib chomps the wrong number.
    cols = int(page.evaluate("document.getElementById('board').style.getPropertyValue('--cols')"))
    rows = int(page.evaluate("document.getElementById('board').style.getPropertyValue('--rows')"))
    far = (0 if c >= cols / 2 else cols - 1) + (0 if r >= rows / 2 else rows - 1) * cols
    box = page.locator("#cells .cell").nth(far).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.keyboard.press("Space")
    page.wait_for_function("() => window.__dc.peek().phase === 'message'")
    page.mouse.up()  # the tap ends with the life already lost
    keep_going(page)
    page.wait_for_timeout(1000)
    assert page.evaluate(NIB) == [c, r], "Nib walked to a square tapped before it lost a life"
    assert errors == []


def test_nib_stops_blinking_when_the_game_ends(page: Page, site_url, errors):
    page.goto(f"{site_url}/doodle-chomp#debug")
    page.click("#playBtn")
    walk_to(page, *wrong_square(page))
    # The same wrong square three times: the last two while Nib blinks after "Keep going".
    for _ in range(3):
        page.keyboard.press("Space")
        page.wait_for_function("() => window.__dc.peek().phase === 'message'")
        keep_going(page)
        page.wait_for_timeout(150)
    expect(page.locator("#ovTitle")).to_have_text("Game over")
    expect(page.locator(".sprite.player")).not_to_have_class(re.compile(r"\bblink\b"))
    assert errors == []
