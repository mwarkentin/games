"""Letterfield's survey log page, against a fake of the log's API.

The page reads the Worker's URL from ?survey=, so these tests point it at
https://survey.test (see fake_survey_log.py). The clock is fixed at 3:30 PM
on Friday, November 6, 2026, in Toronto, the time zone every test runs in.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from playwright.sync_api import Page, expect

from fake_survey_log import SURVEY, FakeSurveyLog

NOW_MS = int(datetime(2026, 11, 6, 20, 30, tzinfo=timezone.utc).timestamp() * 1000)  # 3:30 PM in Toronto
MINUTE = 60_000
PLACES = {"0,0": "Acorn Hollow", "1,0": "Monet Reach", "-1,2": "Zeus Point"}
THEMES = {11: ["Forest", 40], 0: ["Old Masters", 56], 17: ["Olympus", 25]}

ACORN = ["ACORN", 5, 7, 0, 0, "ZED", NOW_MS - 80 * MINUTE, 11]       # 2:10 PM
MONET = ["MONET", 60, 3, 2, 1, "", NOW_MS - 25 * MINUTE, 0]          # 3:05 PM, a stray
ZEUS = ["ZEUS", -40, 100, 6, 0, "ABC", NOW_MS - 24 * 60 * MINUTE, 17]  # yesterday


def open_log(page: Page, site_url: str, fake: FakeSurveyLog, query: str = "", finds=None) -> None:
    page.clock.set_fixed_time(NOW_MS / 1000)
    if finds is not None:
        page.add_init_script(f"localStorage.setItem('letterfield.finds.v2', {json.dumps(json.dumps(finds))})")
    fake.now_ms = NOW_MS
    page.route(f"{SURVEY}/v1/survey/log/**", fake.handle)
    page.goto(f"{site_url}/letterfield-log?survey={SURVEY}{query}")


def test_shows_the_days_words_hour_by_hour_newest_first(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake)

    expect(page.locator("#sumTitle")).to_have_text("Today")
    expect(page.locator("#sumText")).to_have_text("2 words charted · busiest 3:00 PM – 4:00 PM")
    hours = page.locator(".hour h3")
    expect(hours).to_have_count(2)
    expect(hours.nth(0)).to_contain_text("3:00 PM – 4:00 PM")
    expect(hours.nth(1)).to_contain_text("2:00 PM – 3:00 PM")

    acorn = page.locator(".entry", has_text="ACORN")
    expect(acorn).to_contain_text("2:10 PM · ZED")
    expect(acorn).to_contain_text("Acorn Hollow · 5E · 7S · → E · Forest")
    expect(acorn.locator("a")).to_have_attribute("href", "/letterfield#f-acorn-5-7-0")
    monet = page.locator(".entry", has_text="MONET")
    expect(monet).to_have_class("entry mark stray")
    expect(monet).to_contain_text("3:05 PM · —")
    expect(monet).to_contain_text("stray old masters word")
    # The day before has its own page, and today is as late as it goes.
    expect(page.locator("#nextDay")).to_be_disabled()
    page.click("#prevDay")
    expect(page.locator("#sumTitle")).to_have_text("Yesterday")
    expect(page.locator(".entry")).to_have_count(1)
    expect(page.locator(".entry")).to_contain_text("Zeus Point · 40W · 100S · ↑ N · Olympus")
    assert "day=2026-11-05" in page.url
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    assert errors == []


def test_mine_is_the_words_this_browser_charted_first(page: Page, site_url, errors):
    finds = [
        # Charted first here, a few seconds before the server's time for it.
        {"w": "MONET", "x": 60, "y": 3, "d": 2, "t": MONET[6] - 3000, "s": 1, "f": 1},
        # Found here after ZED charted it: in the notes, but not charted first.
        {"w": "ACORN", "x": 5, "y": 7, "d": 0, "t": ACORN[6] + 9 * MINUTE, "s": 0, "f": 0},
        # Charted first here yesterday.
        {"w": "ZEUS", "x": -40, "y": 100, "d": 6, "t": ZEUS[6], "s": 0, "f": 1},
    ]
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, finds=finds)

    # Everyone's log marks yours.
    expect(page.locator(".entry")).to_have_count(2)
    expect(page.locator(".entry", has_text="MONET").locator(".you")).to_have_text("you")
    expect(page.locator(".entry", has_text="ACORN").locator(".you")).to_have_count(0)

    page.click("#viewMine")
    expect(page.locator(".entry")).to_have_count(1)
    expect(page.locator(".entry")).to_contain_text("MONET")
    expect(page.locator("#sumText")).to_have_text("1 word charted first by you")
    expect(page.locator("#myDays button")).to_have_text(["Nov 6 · 1", "Nov 5 · 1"])
    assert "view=mine" in page.url
    # Only the hours within 10 minutes of a find (in case this device's clock
    # was off) were read, besides the day's counts: MONET's, and the one it's
    # 5 minutes into.
    hour = MONET[6] // 3_600_000
    assert sorted(r for r in fake.requests if "/hour/" in r) == [f"/hour/{hour - 1}", f"/hour/{hour}"]

    page.click("#myDays button >> nth=1")
    expect(page.locator(".entry")).to_have_count(1)
    expect(page.locator(".entry")).to_contain_text("ZEUS")
    assert errors == []


def test_mine_without_any_finds_says_how_to_get_some(page: Page, site_url):
    open_log(page, site_url, FakeSurveyLog([ACORN], PLACES, THEMES), query="&view=mine")
    expect(page.locator("#viewMine")).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".status")).to_contain_text("Words you chart first in Letterfield show up here")


def test_reads_every_page_of_a_busy_hour(page: Page, site_url, errors):
    words = ["ACORN", "BARK", "FERN", "GLADE", "MOSS"]
    busy = [[w, i, 0, 0, 0, "BOB", NOW_MS - 50 * MINUTE + i, 11] for i, w in enumerate(words)]
    fake = FakeSurveyLog(busy, PLACES, THEMES, page=2)
    open_log(page, site_url, fake)
    expect(page.locator(".entry")).to_have_count(5)
    # Newest first, across pages.
    expect(page.locator(".entry .word")).to_have_text(list(reversed(words)))
    assert len([r for r in fake.requests if "/hour/" in r]) == 3
    assert errors == []


def test_says_so_when_the_log_cannot_be_reached(page: Page, site_url):
    fake = FakeSurveyLog(fail=True)
    open_log(page, site_url, fake)
    expect(page.locator(".status strong")).to_have_text("Can’t reach the log")
    fake.fail = False
    page.click(".status button")
    expect(page.locator(".status strong")).to_have_text("Nothing charted")


def test_letterfield_links_to_the_log_from_its_survey_panel(page: Page, site_url):
    page.goto(f"{site_url}/letterfield")
    link = page.locator("#survey a.survey-log")
    expect(link).to_have_attribute("href", "/letterfield-log")
