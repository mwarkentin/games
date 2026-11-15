"""Letterfield's game, survey log and timelapse: a link back steps back in history.

A link marked data-back, to the page this tab was on before this one, steps
back to it instead of opening it afresh, so the view and scroll you left come
back, in a Home Screen app with no Back button too. Each page keeps the same
helper between BEGIN BACK LINKS and END BACK LINKS markers.
"""

from __future__ import annotations

import re
import textwrap

from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from common import ROOT
from fake_leaderboard import Held
from fake_survey_log import SURVEY, FakeSurveyLog
from test_letterfield_log import ACORN, MINUTE, MONET, NOW_MS, PLACES, THEMES, ZEUS, entry, open_log

BLOCK = re.compile(r"^[ \t]*// ---- BEGIN BACK LINKS ----\n.*?^[ \t]*// ---- END BACK LINKS ----\n", re.M | re.S)
PAGES = ["letterfield.html", "letterfield-log.html"]


def test_every_page_keeps_the_same_helper():
    copies = {}
    for filename in PAGES:
        found = BLOCK.findall((ROOT / filename).read_text("utf-8"))
        assert len(found) == 1, f"{filename} has {len(found)} copies of the back links helper"
        copies[filename] = textwrap.dedent(found[0])
    first, *others = copies.items()
    for filename, text in others:
        assert text == first[1], f"{filename}'s back links helper differs from {first[0]}'s: change every copy"


def to_the_log(page: Page) -> None:
    """Follows the map's "Survey log and timelapse" link, pointed at the fake log."""
    page.locator("#survey a.survey-log").evaluate(
        "(a, survey) => { a.href += '?survey=' + encodeURIComponent(survey); a.click(); }", SURVEY
    )


def at(page: Page) -> tuple[str, int]:
    """Where the tab is: the page's address, less the site, and how many entries its history holds."""
    return tuple(page.evaluate("[location.pathname + location.search + location.hash, history.length]"))


def test_the_log_steps_back_to_the_map_it_came_from(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    page.route(f"{SURVEY}/v1/survey/log/**", FakeSurveyLog([ACORN], PLACES, THEMES).handle)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    game, n = at(page)
    # The map's link to the log is a normal one: the map was this tab's first page.
    to_the_log(page)
    page.wait_for_url("**/letterfield-log**")
    expect(page.locator(".home")).to_have_text("← Letterfield")
    assert at(page)[1] == n + 1
    # Its way back is a step back, to the map's own entry, not a new one.
    page.click(".home")
    page.wait_for_url(re.compile(r"/letterfield(#.*)?$"))
    assert at(page) == (game, n + 1)
    assert errors == []


# ZED's week of words, more than the log's placeholders hold the place of.
MANY = [
    [f"QU{chr(65 + i // 26)}{chr(65 + i % 26)}T", 5 + i % 40, 7, 0, 0, "ZED", NOW_MS - (i + 1) * 97 * MINUTE, 11]
    for i in range(40)
]


def test_the_map_steps_back_to_the_logs_view_where_it_was(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog([*MANY, MONET, ZEUS], PLACES, THEMES)
    held = Held(fake, lambda r: True)
    held.holding = False
    open_log(page, site_url, fake, "&surveyor=ZED&period=week")
    page.unroute(f"{SURVEY}/v1/survey/log/**")
    page.route(f"{SURVEY}/v1/survey/log/**", held.handle)
    acorn = entry(page, MANY[30][0])
    expect(acorn).to_be_visible()
    acorn.evaluate("e => e.scrollIntoView({ block: 'center', behavior: 'instant' })")
    page.wait_for_function("scrollY > 100")
    view, n = at(page)
    scrolled = page.evaluate("scrollY")
    try:  # kept with the entry once it settles (without that, the check of the scroll below fails)
        page.wait_for_function("history.state?.lfScroll === scrollY", timeout=2000)
    except PlaywrightTimeout:
        pass
    # To the word on the map, as a normal link...
    acorn.locator("a.fly").evaluate("a => a.click()")
    page.wait_for_url(re.compile(r"/letterfield#f-"))
    assert at(page)[1] == n + 1
    # ...and the map's "Survey log and timelapse" is a step back, to that view. The log, slow to
    # answer this time, is scrolled where it was once its words come.
    held.holding = True
    page.locator("#survey a.survey-log").evaluate("a => a.click()")
    page.wait_for_url(re.compile(r"/letterfield-log"))
    assert at(page) == (view, n + 1)
    expect(page.locator("#sumTitle")).to_have_text("This week")
    held.wait_for(page)
    held.release()
    expect(entry(page, MANY[30][0])).to_be_visible()
    page.wait_for_function(f"Math.abs(scrollY - {scrolled}) < 2", timeout=5000)
    assert errors == []


def test_moving_about_one_page_is_counted_on_the_way_back(page: Page, site_url, errors):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.clock.set_fixed_time(NOW_MS / 1000)  # the day of the fake log's words
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    fake.now_ms = NOW_MS
    page.route(f"{SURVEY}/v1/survey/log/**", fake.handle)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    game, n = at(page)
    to_the_log(page)
    expect(entry(page, "ACORN")).to_be_visible()
    # Into ZED's page and back to everyone's, each an entry of the log's own.
    page.locator("a", has_text=re.compile("^ZED$")).first.click()
    expect(page).to_have_url(re.compile(r"surveyor=ZED"))
    page.click("#everyone")
    expect(page).not_to_have_url(re.compile(r"surveyor=ZED"))
    assert at(page)[1] == n + 3
    # "← Letterfield" goes back past them all, to the map.
    page.click(".home")
    page.wait_for_url(re.compile(r"/letterfield(#.*)?$"))
    assert at(page) == (game, n + 3)
    assert errors == []


def test_a_tabs_first_page_has_nothing_to_step_back_to(page: Page, site_url, errors):
    # Opened in a new tab from the map, the log's referrer is the map, but there's no entry before it.
    page.context.route(f"{SURVEY}/v1/survey/log/**", FakeSurveyLog([ACORN], PLACES, THEMES).handle)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    with page.context.expect_page() as opened:
        page.evaluate(f"window.open('/letterfield-log?survey={SURVEY}')")
    tab = opened.value
    tab.wait_for_load_state()
    expect(tab.locator(".home")).to_be_visible()
    assert tab.evaluate("[document.referrer.includes('/letterfield'), history.length]") == [True, 1]
    tab.click(".home")
    tab.wait_for_url("**/letterfield")
    assert at(tab)[1] == 2
    assert errors == []
