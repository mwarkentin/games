from playwright.sync_api import Page, expect

from page_changes import repeated_no_op_writes


def test_typing_the_answer_pops_the_bubble(page: Page, site_url, errors):
    # #debug exposes window.__fb, which lets the test pick the next problem.
    page.goto(f"{site_url}/funnels-and-buckets#debug")
    page.click("#startBtn")
    expect(page.locator("#menu")).to_be_hidden()
    # Queue after starting: the menu's demo bubbles would use it up otherwise.
    page.evaluate("window.__fb.queue([['add', 2, 3]])")

    page.wait_for_function("() => window.__fb.peek().bubbles.some((b) => b.ans === 5)", timeout=15000)
    page.keyboard.type("5")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__fb.peek().popped === 1")
    assert page.evaluate("window.__fb.peek().wrongs") == 0
    assert errors == []


def test_escape_pauses(page: Page, site_url, errors):
    page.goto(f"{site_url}/funnels-and-buckets")
    page.click("#startBtn")
    page.keyboard.press("Escape")
    expect(page.locator("#pauseOv")).to_be_visible()
    page.click("#resumeBtn")
    expect(page.locator("#pauseOv")).to_be_hidden()
    assert errors == []


def test_playing_doesnt_keep_rewriting_the_page(page: Page, site_url, errors):
    page.goto(f"{site_url}/funnels-and-buckets#debug")
    page.click("#startBtn")
    expect(page.locator("#menu")).to_be_hidden()
    assert repeated_no_op_writes(page) == {}
    assert errors == []


def screen(page: Page) -> str:
    """The screen the game says it's on (see Screen in the page)."""
    return page.locator("html").get_attribute("data-screen")


def test_the_page_shows_which_screen_its_on(page: Page, site_url, errors):
    page.goto(f"{site_url}/funnels-and-buckets#debug")
    assert screen(page) == "menu"
    expect(page.locator("#app")).to_have_attribute("inert", "")  # the menu covers the game
    page.click("#startBtn")
    expect(page.locator("html")).to_have_attribute("data-screen", "playing")
    expect(page.locator("#app")).not_to_have_attribute("inert", "")
    page.keyboard.press("Escape")
    expect(page.locator("html")).to_have_attribute("data-screen", "paused")
    page.click("#resumeBtn")
    expect(page.locator("html")).to_have_attribute("data-screen", "playing")
    page.evaluate("window.__fb.end()")
    expect(page.locator("html")).to_have_attribute("data-screen", "ending")
    expect(page.locator("html")).to_have_attribute("data-screen", "over")
    expect(page.locator("#overOv")).to_be_visible()

    # Back on the menu, nothing of the old game shows behind it.
    page.click("#settingsBtn")
    expect(page.locator("html")).to_have_attribute("data-screen", "menu")
    expect(page.locator("#hudScore")).to_have_text("0")
    assert errors == []


def test_resuming_doesnt_send_a_half_typed_answer(page: Page, site_url, errors):
    page.goto(f"{site_url}/funnels-and-buckets#debug")
    page.click("#startBtn")
    # 1 and 12 falling together: a typed "1" waits to see if a 2 follows.
    page.evaluate("window.__fb.queue([['add', 0, 1], ['add', 5, 7]]); window.__fb.speed(3)")
    page.wait_for_function(
        "() => { const b = window.__fb.peek().bubbles; return b.some((x) => x.ans === 1) && b.some((x) => x.ans === 12); }",
        timeout=20000,
    )
    page.evaluate("window.__fb.speed(1)")
    page.keyboard.type("1")
    page.keyboard.press("Escape")
    page.wait_for_timeout(1500)  # longer than the game waits before sending "1"
    page.click("#resumeBtn")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__fb.peek()")["popped"] == 0, "time spent paused isn't hesitation"
    assert page.evaluate("window.__fb.peek().input") == "1"
    # Hesitate for real and it goes as 1.
    page.wait_for_function("() => window.__fb.peek().popped === 1")
    assert errors == []


def test_a_wake_lock_that_comes_after_pausing_is_let_go(page: Page, site_url, errors):
    # A stand-in for navigator.wakeLock that takes 300 ms to grant a lock.
    page.add_init_script("""
      window.locks = [];
      Object.defineProperty(navigator, 'wakeLock', { value: {
        request: () => new Promise((resolve) => setTimeout(() => {
          const lock = { released: false, release() { this.released = true; return Promise.resolve(); }, addEventListener() {} };
          window.locks.push(lock);
          resolve(lock);
        }, 300)),
      } });
    """)
    page.goto(f"{site_url}/funnels-and-buckets#debug")
    page.click("#startBtn")
    page.keyboard.press("Escape")  # before the lock arrives
    page.wait_for_function("() => window.locks.length === 1")
    assert page.evaluate("window.locks.map((l) => l.released)") == [True]
    page.click("#resumeBtn")
    page.wait_for_function("() => window.locks.length === 2")
    assert page.evaluate("window.locks.map((l) => l.released)") == [True, False], "playing keeps the screen on"
    assert errors == []
