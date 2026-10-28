from playwright.sync_api import Page, expect


def test_start_shift_and_give_an_instruction(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller")
    page.click("#btnStart")
    expect(page.locator("#overlay")).to_be_hidden()
    expect(page.locator("#clock")).not_to_have_text("--:--")

    # The first aircraft's strip posts as soon as the shift starts.
    strip = page.locator("#strips .strip").first
    expect(strip).to_be_visible()
    callsign = strip.locator(".s-cs").inner_text()
    strip.click()
    expect(page.locator("#hCs")).to_have_text(callsign)

    for _ in range(3):
        page.click("#btnAdvance")
    expect(page.locator("#radio")).not_to_have_text("Frequency quiet.")
    assert errors == []
