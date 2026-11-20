"""Letterfield's survey log: its way back to the map steps back in history.

"← Letterfield" in the survey log, when the tab came to the log from the map,
steps back to the map instead of opening it afresh, so the map comes back as
it was, in a Home Screen app with no Back button too; the map keeps its place
when it's come back to, whatever find its address holds. Links into the log
are plain links: the log opens at its start.
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from fake_leaderboard import without_worker
from fake_survey_log import SURVEY, FakeSurveyLog
from test_letterfield_log import ACORN, MINUTE, MONET, NOW_MS, PLACES, THEMES, ZEUS, entry, open_log


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
    # The map's link to the log is a normal one.
    to_the_log(page)
    page.wait_for_url("**/letterfield-log**")
    expect(page.locator(".home")).to_have_text("← Letterfield")
    assert at(page)[1] == n + 1
    # Its way back is a step back, to the map's own entry, not a new one.
    page.click(".home")
    page.wait_for_url(re.compile(r"/letterfield(#.*)?$"))
    assert at(page) == (game, n + 1)
    assert errors == []


# The map has stopped away from `at` and saved where it is anew (not the save `before`): its title's
# coordinate is the saved place's, to the cell, give or take the saved place's rounding. Answers that
# place as the title shows it, and the save itself.
SETTLED = """([at, before]) => {
  const raw = localStorage.getItem('letterfield.cam.v1'), shown = document.getElementById('tCoord').textContent;
  const m = /^(\\d+)([EW]) · (\\d+)([NS])$/.exec(shown);
  if (!raw || raw === before || !m || shown === at) return false;
  const c = JSON.parse(raw), x = Math.floor(c.x), y = Math.floor(c.y);
  const sx = (m[2] === 'W' ? -1 : 1) * m[1], sy = (m[4] === 'N' ? -1 : 1) * m[3];
  if (Math.abs(x - sx) > 1 || Math.abs(y - sy) > 1) return false;
  return [`${Math.abs(x)}${x < 0 ? 'W' : 'E'} · ${Math.abs(y)}${y < 0 ? 'N' : 'S'}`, raw];
}"""


def test_the_map_keeps_its_place_when_it_comes_back(page: Page, site_url, errors):
    page.set_viewport_size({"width": 1280, "height": 900})
    # Signed and past the first-visit card, so no card takes the keys.
    page.add_init_script("""if (location.protocol.startsWith('http')) {
      localStorage.setItem('games.initials', JSON.stringify('MLW')); localStorage.setItem('letterfield.coach.v1', '1'); }""")
    # A real word on the map, as the log would list it.
    without_worker(page, site_url, "letterfield")
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    w = page.evaluate("window.__lf.chunk(0, 0).words[0]")
    word = [w["w"].upper(), w["x"], w["y"], w["d"], 0, "ZED", NOW_MS - 80 * MINUTE, 11]
    page.unroute_all()
    open_log(page, site_url, FakeSurveyLog([word, MONET, ZEUS], PLACES, THEMES))
    # To it on the map, whose address then holds it...
    before = page.evaluate("localStorage.getItem('letterfield.cam.v1')")
    entry(page, word[0]).locator("a.fly").click()
    page.wait_for_url(re.compile(rf"/letterfield#f-{w['w'].lower()}-"))
    at_word, there = page.wait_for_function(SETTLED, arg=["", before]).json_value()
    # ...and away from it, as the map saves where you are.
    for _ in range(3):
        page.locator("#map").press("ArrowRight")
    saved, _ = page.wait_for_function(SETTLED, arg=[at_word, there]).json_value()
    # To the log and back by its way back to the map, which comes back where it saved you, not at the word.
    to_the_log(page)
    page.wait_for_url("**/letterfield-log**")
    page.click(".home")
    page.wait_for_url(re.compile(rf"/letterfield#f-{w['w'].lower()}-"))
    expect(page.locator("#tCoord")).to_have_text(saved)
    assert saved != at_word
    assert errors == []


def test_the_maps_link_to_the_log_opens_it_at_its_start(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, "&surveyor=ZED&period=week")
    expect(page.locator("#sumTitle")).to_have_text("This week")
    entry(page, "ACORN").locator("a.fly").evaluate("a => a.click()")
    page.wait_for_url(re.compile(r"/letterfield#f-acorn-"))
    n = at(page)[1]
    to_the_log(page)
    page.wait_for_url("**/letterfield-log**")
    # Not back to ZED's week: the log as it opens, today's, at the top, in an entry of its own.
    expect(page.locator("#sumTitle")).to_have_text("Today")
    assert at(page)[1] == n + 1
    assert page.evaluate("scrollY") == 0
    assert errors == []


def test_moving_about_the_log_is_counted_on_the_way_back(page: Page, site_url, errors):
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


def test_the_timelapse_steps_back_to_the_log_it_came_from(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, query="&period=week&day=2026-10-19")  # three weeks back
    expect(page.locator("#sumTitle")).to_contain_text("Oct")
    log, n = at(page)
    page.click("#timelapseLink")
    page.wait_for_url("**/letterfield-timelapse**")
    assert at(page)[1] == n + 1
    # "← Log" is a step back, to the week the log was on, not the log afresh.
    page.click("#toLog")
    page.wait_for_url("**/letterfield-log**")
    assert at(page) == (log, n + 1)
    expect(page.locator("#sumTitle")).to_contain_text("Oct")
    assert errors == []
