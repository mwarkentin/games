from playwright.sync_api import Page, expect


def test_play_starts_a_level(page: Page, site_url, errors):
    page.goto(f"{site_url}/doodle-chomp")
    # Off claude.ai there's no shared score board, so scores stay in the browser.
    expect(page.locator("#menuScoreNote")).to_have_text("Scores are kept in this browser only.")

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
    assert errors == []
