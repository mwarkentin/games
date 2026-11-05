from page_changes import repeated_no_op_writes
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


def strip_callsigns(page: Page) -> list[str]:
    return page.locator("#strips .strip .s-cs").all_inner_texts()


def edit_saved_shift(page: Page, script: str) -> None:
    """Reload with the saved shift changed by `script`, which gets it as `g`.

    The page saves the shift again as it unloads, so the edit runs at the
    start of the next load, before the game reads it.
    """
    page.add_init_script(
        f"""(() => {{
            const g = JSON.parse(localStorage.getItem('atc-shift'));
            if (!g) return;
            {script}
            localStorage.setItem('atc-shift', JSON.stringify(g));
        }})()"""
    )
    page.reload()


def test_unfinished_shift_is_saved_and_resumed(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller")
    page.click("#btnStart")
    for _ in range(3):
        page.click("#btnAdvance")
    callsigns = strip_callsigns(page)
    page.keyboard.press("Escape")
    summary = page.locator("#pauseSummary").inner_text()

    page.reload()
    expect(page.locator("#paused")).to_be_visible()
    expect(page.locator("#pauseSummary")).to_have_text(f"Picked up where you left off. {summary}")
    page.click("#btnResume")
    expect(page.locator("#overlay")).to_be_hidden()
    assert strip_callsigns(page) == callsigns
    assert errors == []


def test_ending_a_shift_clears_the_save(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller")
    page.click("#btnStart")
    page.click("#btnAdvance")
    page.keyboard.press("Escape")
    page.click("#btnQuit")
    page.reload()
    expect(page.locator("#menu")).to_be_visible()
    assert page.evaluate("localStorage.getItem('atc-shift')") is None
    assert errors == []


def test_clean_shift_offers_the_next_shift(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller")
    page.click("#btnStart")
    page.click("#btnAdvance")
    # Every aircraft handled, so the next sweep ends the shift clean.
    edit_saved_shift(page, "for (const a of g.ac) a.state = /^[ab]$/.test(a.dst) ? 'landed' : 'exited';")
    page.click("#btnResume")
    page.click("#btnAdvance")
    expect(page.locator("#resTitle")).to_have_text("Shift complete")
    assert page.evaluate("localStorage.getItem('atc-shift')") is None

    expect(page.locator("#btnNext")).to_have_text("Next shift: Easy")
    expect(page.locator("#btnNext")).to_be_focused()
    expect(page.locator("#btnAgain")).not_to_have_class("btn primary")
    page.click("#btnNext")
    expect(page.locator("#overlay")).to_be_hidden()
    expect(page.locator("#radio")).to_contain_text("easy shift, 26 aircraft expected")
    assert errors == []


def test_shift_that_runs_out_of_time_has_no_next_shift(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller")
    page.click("#btnStart")
    page.click("#btnAdvance")
    edit_saved_shift(page, "g.tick = g.shift - 1;")
    page.click("#btnResume")
    page.click("#btnAdvance")
    expect(page.locator("#resTitle")).to_have_text("Shift over")
    expect(page.locator("#btnNext")).to_be_hidden()
    expect(page.locator("#btnAgain")).to_have_class("btn primary")
    expect(page.locator("#btnAgain")).to_be_focused()
    assert errors == []


def test_a_shift_doesnt_keep_rewriting_the_page(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller")
    page.click("#btnStart")
    expect(page.locator("#overlay")).to_be_hidden()
    assert repeated_no_op_writes(page) == {}
    assert errors == []
