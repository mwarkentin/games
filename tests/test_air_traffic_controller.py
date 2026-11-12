import re

from playwright.sync_api import Page, expect

from page_changes import repeated_no_op_writes


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


def screen(page: Page) -> str:
    """The screen the game says it's on (see Screen in the page)."""
    return page.locator("html").get_attribute("data-screen")


def advance_until_over(page: Page, sweeps: int) -> None:
    """Sweep up to `sweeps` times, stopping when the shift ends."""
    for _ in range(sweeps):
        if page.evaluate("window.__atc.peek().state") != "running":
            return
        page.click("#btnAdvance")


def test_the_page_shows_which_screen_its_on(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller#debug")
    assert screen(page) == "menu"
    expect(page.locator("#app")).to_have_attribute("inert", "")  # the menu covers the console
    page.click("#btnStart")
    expect(page.locator("html")).to_have_attribute("data-screen", "playing")
    expect(page.locator("#app")).not_to_have_attribute("inert", "")
    page.keyboard.press("Escape")
    expect(page.locator("html")).to_have_attribute("data-screen", "paused")
    expect(page.locator("#paused")).to_be_visible()
    page.click("#btnResume")
    expect(page.locator("html")).to_have_attribute("data-screen", "playing")
    page.evaluate("window.__atc.finish(5, 44)")
    # The scope shows what went wrong for a moment, out of reach, before the report.
    expect(page.locator("html")).to_have_attribute("data-screen", "ending")
    expect(page.locator("#overlay")).to_be_hidden()
    expect(page.locator("#app")).to_have_attribute("inert", "")
    expect(page.locator("html")).to_have_attribute("data-screen", "report")
    expect(page.locator("#result")).to_be_visible()
    page.click("#btnMenu")
    expect(page.locator("html")).to_have_attribute("data-screen", "menu")
    expect(page.locator("#menu")).to_be_visible()
    assert page.evaluate("window.__atc.screen") == "menu"
    assert errors == []


def test_keys_tapped_as_a_shift_ends_dont_skip_its_report(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller#debug")
    page.click("#btnStart")
    page.evaluate("window.__atc.finish(8, 80)")  # a clean shift: its report comes up a moment later
    page.wait_for_function("document.activeElement && document.activeElement.id === 'btnNext'", polling="raf")
    page.keyboard.press("Enter")  # an Enter meant for a typed command, just as the report appears
    page.wait_for_timeout(700)
    page.keyboard.press(" ")  # Space sweeps the radar; on the report it presses nothing
    page.keyboard.press(" ")
    page.wait_for_timeout(200)
    assert page.evaluate("window.__atc.peek().state") == "over", "the report was skipped"
    expect(page.locator("#result")).to_be_visible()
    expect(page.locator("#btnNext")).to_be_focused()
    # Enter, once the report has been up a moment, takes the next shift.
    page.keyboard.press("Enter")
    expect(page.locator("#overlay")).to_be_hidden()
    expect(page.locator("#radio")).to_contain_text("easy shift, 26 aircraft expected")
    assert errors == []


def test_holding_escape_down_pauses_once(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller#debug")
    page.click("#btnStart")
    for _ in range(4):
        page.keyboard.down("Escape")  # the press, then the key repeating as it's held
    page.keyboard.up("Escape")
    assert page.evaluate("window.__atc.peek().state") == "paused"
    expect(page.locator("#paused")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-screen", "paused")
    assert errors == []


def test_holding_space_keeps_sweeping_but_cant_skip_the_report(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller#debug")
    page.click("#btnStart")
    tick = page.evaluate("window.__atc.peek().tick")
    for _ in range(5):
        page.keyboard.down(" ")  # the press, then the key repeating as it's held
    assert page.evaluate("window.__atc.peek().tick") == tick + 5, "holding Space fast-forwards"
    # Still held as the shift ends: its report comes up, and the repeats press nothing on it.
    page.evaluate("window.__atc.finish(8, 80)")
    page.wait_for_function("document.activeElement && document.activeElement.id === 'btnNext'", polling="raf")
    page.wait_for_timeout(700)  # past the moment the report ignores keys
    for _ in range(5):
        page.keyboard.down(" ")
    page.keyboard.up(" ")
    page.wait_for_timeout(200)
    assert page.evaluate("window.__atc.peek().state") == "over", "the report was skipped"
    expect(page.locator("#result")).to_be_visible()
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
    page.goto(f"{site_url}/air-traffic-controller#debug")
    page.click("#btnStart")
    page.keyboard.press("Escape")  # before the lock arrives
    page.wait_for_function("() => window.locks.length === 1")
    assert page.evaluate("window.locks.map((l) => l.released)") == [True]
    page.click("#btnResume")
    page.wait_for_function("() => window.locks.length === 2")
    assert page.evaluate("window.locks.map((l) => l.released)") == [True, False], "flying keeps the screen on"
    assert errors == []


# Every aircraft handled but the first, a jet for α in the air; `place` sets the rest.
ONE_ARRIVAL_LEFT = """
    const [a, ...rest] = g.ac;
    for (const x of rest) x.state = /^[ab]$/.test(x.dst) ? 'landed' : 'exited';
    Object.assign(a, { state: 'air', type: 'J', org: '0', dst: 'a', fuel: 60, ph: 0, ji: false, tl: 0, tdl: 0,
      app: null, landing: false, %s });
    g.sel = a.cs;
"""


def test_land_takes_an_arrival_past_the_navaid_it_would_hold_at(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller#debug")
    page.click("#btnStart")
    page.click("#btnAdvance")
    # Southbound for α, on the line through OXV, with the hold arrivals start with.
    edit_saved_shift(
        page,
        ONE_ARRIVAL_LEFT
        % "x: 5, y: 2, px: 5, py: 2, alt: 3, palt: 3, talt: 3, h: 4, hold: true, holding: false, hn: -1",
    )
    page.click("#btnResume")
    expect(page.locator("#kHold")).to_have_class(re.compile(r"\bon\b"))  # the hold, armed
    page.click("#kLand")
    page.click("#kLand")  # Confirm
    advance_until_over(page, 12)
    # The tower brings it straight down over OXV to α, rather than circling OXV till its fuel runs out.
    expect(page.locator("#resTitle")).to_have_text("Shift complete")
    assert errors == []


def test_land_waits_for_the_approach_when_an_arrival_is_holding(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller#debug")
    page.click("#btnStart")
    page.click("#btnAdvance")
    edit_saved_shift(
        page,
        ONE_ARRIVAL_LEFT
        % "x: 5, y: 6, px: 5, py: 6, alt: 2, palt: 2, talt: 2, h: 4, hold: true, holding: true, hn: 0, hs: 0",
    )
    page.click("#btnResume")
    cs = page.locator("#hCs").inner_text()
    page.click("#kLand")
    page.click("#kLand")
    expect(page.locator("#radio .now")).to_have_text(
        f"{cs} cleared to land UNABLE, holding at OXV, clear an approach first"
    )
    expect(page.locator("#kAppA")).to_be_enabled()  # still yours, and still holding
    page.click("#kAppA")
    page.click("#kLand")
    page.click("#kLand")
    expect(page.locator("#radio .now")).to_have_text(f"{cs} cleared to land ROGER, to tower")
    advance_until_over(page, 20)  # once round the hold to OXV, then final
    expect(page.locator("#resTitle")).to_have_text("Shift complete")
    assert errors == []


def test_tapping_a_strip_drops_a_command_typed_for_another_aircraft(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller#debug")
    page.click("#btnStart")
    page.click("#btnAdvance")
    # Two jets in the air, A and B, and nobody else on frequency.
    edit_saved_shift(
        page,
        """
        g.ac.forEach((x, i) => Object.assign(x, { cs: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[i], state: 'sched', post: 999, et: 999 }));
        Object.assign(g.ac[0], { state: 'air', type: 'J', org: '7', dst: '2', x: 3, y: 12, px: 3, py: 12,
          alt: 3, palt: 3, talt: 3, h: 2, hold: false, ji: false });
        Object.assign(g.ac[1], { state: 'air', type: 'J', org: '5', dst: '1', x: 15, y: 20, px: 15, py: 20,
          alt: 4, palt: 4, talt: 4, h: 0, hold: false, ji: false });
        g.sel = null;
    """,
    )
    page.click("#btnResume")
    page.keyboard.press("a")  # a command for A, begun
    expect(page.locator("#radio .kbd")).to_have_text("› A_")
    page.click("#strips [data-cs='B']")  # then B picked on screen
    expect(page.locator("#hCs")).to_have_text("B")
    expect(page.locator("#radio .kbd")).to_have_count(0)
    page.keyboard.press("m")
    expect(page.locator("#radio")).not_to_contain_text("A maintain")
    assert page.evaluate("[window.__atc.sel, window.__atc.kb]") == ["B", ""]
    page.keyboard.type("bm")  # B, maintain
    expect(page.locator("#radio .now")).to_have_text("B maintain 4,000 ROGER")
    assert errors == []


def test_a_shift_saved_before_sweeps_were_tracked_still_counts_its_slowest(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller#debug")
    page.click("#btnStart")
    page.click("#btnAdvance")
    edit_saved_shift(page, "delete g.slowest;")  # as shifts were saved before the leaderboard
    page.click("#btnResume")
    page.click("#btnSpeed")  # steady → rush
    page.click("#btnSpeed")  # rush → calm
    page.click("#btnSpeed")  # calm → steady
    assert page.evaluate("window.__atc.peek().slowest") == "calm"
    assert errors == []


def test_the_sweep_stays_put_once_a_shift_has_ended(page: Page, site_url, errors):
    page.goto(f"{site_url}/air-traffic-controller#debug")
    page.click("#btnStart")
    box = page.locator("#btnSpeed").bounding_box()
    page.evaluate("window.__atc.finish(5, 44)")  # lost: the scope shows why for a moment first
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)  # the sweep button, still in view
    assert page.evaluate("window.__atc.peek().speed") == "steady"
    expect(page.locator("#speedVal")).to_have_text("4s")
    page.click("#btnAgain")
    assert page.evaluate("window.__atc.peek().speed") == "steady"
    assert errors == []
