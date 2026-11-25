"""Letterfield's survey log, timelapse and soundtrack never scroll sideways on a phone.

Nothing on these pages is meant to scroll that way, so at 320 and 375 px wide,
through every view and with a chart's tooltip open at either end, the page is
no wider than the screen and nothing sticks out past its edges. The pages also
clip what might (overflow-x: clip), so the check looks at each element's box
rather than only at scrollWidth, which the clip would hide. A phone's context
(touch, a mobile viewport) is used, as a finger's first tap on a bar shows its
tooltip and a page too wide is dragged sideways there. Day data is the shape a
player saw it overflow: a busy evening hour and a supernova in the day's last.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from fake_definitions import DEFINE_API, FakeDefinitions
from fake_survey_log import HOUR_MS, FakeSurveyLog
from test_letterfield_log import MINUTE, NOW_MS, open_log
from test_letterfield_timelapse import fake_log, open_timelapse, tap_territory_0_0

PHONE = pytest.mark.browser_context_args(has_touch=True, is_mobile=True)
WIDTHS = pytest.mark.parametrize("width", [320, 375])

# Elements whose box passes the screen's edges, unless an ancestor that clips
# (overflow other than visible) keeps them inside it.
STICKING_OUT = """() => {
  const W = innerWidth, out = [];
  const clipped = e => { for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
    const s = getComputedStyle(a), r = a.getBoundingClientRect();
    if (s.overflowX !== 'visible' && r.left >= -0.5 && r.right <= W + 0.5) return true; } return false; };
  for (const e of document.body.querySelectorAll('*')) {
    const r = e.getBoundingClientRect();
    if (!r.width || (r.right <= W + 0.5 && r.left >= -0.5) || clipped(e)) continue;
    out.push(`${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}.${[...e.classList].join('.')} ${Math.round(r.left)}..${Math.round(r.right)}: ${(e.textContent || '').trim().slice(0, 40)}`);
  }
  return out;
}"""


def fits(page: Page, where: str) -> None:
    width = page.evaluate("innerWidth")
    assert page.evaluate("document.documentElement.scrollWidth") <= width, where
    assert page.evaluate("document.body.scrollWidth") <= width, where
    assert page.evaluate(STICKING_OUT) == [], where


COBALT = "c0ba17c0ba"
GUILDS = {COBALT: ["Theodolite Lodestar Fellowship", 220]}
PLACES = {
    "20,20": "Acai Knoll",
    "21,20": "Supercalifragilistic Overlook Of The Long Hills",
    "22,20": "Monet Reach",
}
THEMES = {
    80: ["Acai And Every Berry Of The Northern Woods", 100],
    81: ["Old Masters", 56],
    82: ["Olympus", 25],
}
EVENING = NOW_MS - 19 * HOUR_MS - 30 * MINUTE  # 8 PM yesterday, Thursday, November 5
NIGHT = NOW_MS - 16 * HOUR_MS - 30 * MINUTE  # 11 PM yesterday


def busy_day():
    """56 words yesterday: 24 between 8 and 9 PM, and six in its last hour,
    the sixth of them sending Acai Knoll supernova, as in the player's day."""

    def word(i, rx, at, th, initials="ZED", guild=COBALT):
        return [
            "WORD" + chr(65 + i // 26) + chr(65 + i % 26),
            rx * 48 + i % 40,
            20 * 48 + i // 40,
            0,
            0,
            initials,
            at,
            th,
            guild,
        ]

    out = [word(i, 22, EVENING + i * 2 * MINUTE, 82, "KAT") for i in range(24)]
    out += [word(24 + i, 21, EVENING - (i + 1) * 25 * MINUTE, 81, "BOB", "") for i in range(26)]
    out += [word(50 + i, 20, NIGHT + (50 + i) * MINUTE, 80) for i in range(6)]
    # And a few today, so Today's chart has a word in its last hour so far.
    out += [word(60 + i, 21, NOW_MS - (i + 1) * 3 * MINUTE, 81) for i in range(3)]
    return out


def fake() -> FakeSurveyLog:
    return FakeSurveyLog(busy_day(), PLACES, THEMES, totals={"20,20": 6}, guilds=GUILDS)


VIEWS = [
    "&day=2026-11-05",  # the player's: yesterday, the Day view
    "",
    "&period=week",
    "&period=month",
    "&period=year",
    "&period=all",
    "&view=mine",
    "&supernovas&period=week",
    "&supernovas&period=all",
    "&surveyor=ZED&period=week",
    "&theme=80",
    "&territory=20,20",
    f"&guild={COBALT}&period=week&name=11-0-0",
    "&period=hour&day=2026-11-05&hour=20",
]
PICKABLE = "#chart .bar, #chart .overlay button, #chart button.cell"


def tap_each_end(page: Page, where: str) -> None:
    """Shows the tooltip of the chart's last and first bar (or day), as a first tap does."""
    bars = page.locator(PICKABLE)
    if not bars.count():
        return
    for i in sorted({bars.count() - 1, 0}, reverse=True):
        bars.nth(i).tap()
        expect(page.locator("#tip")).to_be_visible()
        fits(page, f"{where}, tooltip of #{i}")


@PHONE
@WIDTHS
def test_the_log_fits_a_phone_in_every_view(page: Page, site_url, errors, width):
    page.set_viewport_size({"width": width, "height": 740})
    finds = [{"w": "WORDBY", "x": 20 * 48 + 10, "y": 20 * 48 + 1, "d": 0, "at": NIGHT, "first": True}]
    for query in VIEWS:
        open_log(page, site_url, fake(), query=query, finds=finds)
        expect(page.locator("html")).to_have_attribute("data-log", "ready")
        page.evaluate("document.fonts.ready")
        fits(page, query or "today")
        tap_each_end(page, query or "today")
        # A tooltip shown and put down leaves the page where it was.
        page.locator("h1").first.tap()
        fits(page, f"{query}, after the tooltip")


@PHONE
@WIDTHS
def test_the_days_last_bar_keeps_its_tooltip_on_screen(page: Page, site_url, errors, width):
    """The player's day: the supernova's ✦ on the last hour's bar, and its tooltip over it."""
    page.set_viewport_size({"width": width, "height": 740})
    open_log(page, site_url, fake(), query="&day=2026-11-05")
    last = page.locator("#chart .bar").last
    expect(last).to_have_class(re.compile(r"\bstarred\b"))
    last.tap()
    tip = page.locator("#tip")
    expect(tip).to_contain_text("1 supernova")
    box = tip.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    fits(page, "the day's last bar")


@PHONE
@WIDTHS
def test_the_log_fits_a_phone_after_picking_a_day_and_opening_a_meaning(page: Page, site_url, errors, width):
    page.set_viewport_size({"width": width, "height": 740})
    page.route(
        f"{DEFINE_API}/**",
        FakeDefinitions(senses=[{"pos": "noun", "text": "Pneumonoultramicroscopicsilicovolcanoconiosis " * 3}]).handle,
    )
    open_log(page, site_url, fake(), query=f"&define={DEFINE_API}")
    expect(page.locator("html")).to_have_attribute("data-log", "ready")
    page.locator("#dayInput").fill("2026-11-05")
    page.locator("#dayInput").dispatch_event("change")
    expect(page.locator("#sumTitle")).to_have_text("Yesterday")
    fits(page, "a day picked")
    page.get_by_role("button", name="What WORDCD means").tap()
    expect(page.locator(".def")).to_have_attribute("data-define", "ready")
    fits(page, "a meaning open")


@PHONE
@WIDTHS
def test_the_timelapse_fits_a_phone(page: Page, site_url, errors, width):
    page.set_viewport_size({"width": width, "height": 740})
    log = fake_log(guilds=GUILDS)
    open_timelapse(page, site_url, log, query=f"&guild={COBALT}&name=11-0-0")
    expect(page.locator("#follow")).to_be_visible()
    fits(page, "the timelapse following a guild")
    open_timelapse(page, site_url, fake_log())
    page.wait_for_function("__tl.loaded.days === 3")
    page.locator("#play").click()
    page.locator("#scrub").fill("1000")
    page.wait_for_timeout(100)
    tap_territory_0_0(page)
    expect(page.locator("#chip")).to_be_visible()
    fits(page, "a territory's chip")


@PHONE
@WIDTHS
@pytest.mark.parametrize("path", ["/letterfield-soundtrack", "/", "/colophon"])
def test_the_soundtrack_home_and_colophon_fit_a_phone(page: Page, site_url, errors, width, path):
    page.set_viewport_size({"width": width, "height": 740})
    page.goto(site_url + path)
    page.evaluate("document.fonts.ready")
    fits(page, path)
