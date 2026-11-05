from page_changes import repeated_no_op_writes
from playwright.sync_api import Page, expect


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
