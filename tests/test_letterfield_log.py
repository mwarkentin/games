"""Letterfield's survey log page, against a fake of the log's API.

The page reads the Worker's URL from ?survey=, so these tests point it at
https://survey.test (see fake_survey_log.py). The clock is fixed at 3:30 PM
on Friday, November 6, 2026, in Toronto, the time zone every test runs in,
so "this week" is Monday, November 2, to Sunday, November 8.
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


def tile(page: Page, n: int):
    return page.locator("#tiles .tile").nth(n)


def test_shows_the_days_words_hour_by_hour_newest_first(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake)

    expect(page.locator("#sumTitle")).to_have_text("Today")
    expect(page.locator("#sumText .live")).to_have_text("Live")
    expect(tile(page, 0)).to_contain_text("Words charted2")
    # A tie goes to the earlier hour.
    expect(tile(page, 1)).to_contain_text("Busiest hour2:00 PM – 3:00 PM1 word")
    # ACORN is a hidden word in the shared world; MONET is a stray.
    expect(tile(page, 2)).to_contain_text("In the shared world1")
    expect(page.locator("#chart .bar")).to_have_count(24)
    expect(page.locator("#chart .bar.some")).to_have_count(2)
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
    expect(page.locator("#next")).to_be_disabled()
    page.click("#prev")
    expect(page.locator("#sumTitle")).to_have_text("Yesterday")
    expect(page.locator(".entry")).to_have_count(1)
    expect(page.locator(".entry")).to_contain_text("Zeus Point · 40W · 100S · ↑ N · Olympus")
    assert "day=2026-11-05" in page.url
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    assert errors == []


def test_an_hour_opens_minute_by_minute_and_the_running_one_is_live(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake)
    # Tapping the 2 PM column opens that hour.
    page.locator("#chart .bar").nth(14).click()
    expect(page.locator("#sumTitle")).to_have_text("2:00 PM – 3:00 PM")
    expect(page.locator("#sumText")).to_have_text("Friday, November 6")
    expect(page.locator("#chart .bar")).to_have_count(60)
    expect(page.locator("#chart .bar.some")).to_have_count(1)
    expect(page.locator("#chart .bar.some")).to_have_attribute("aria-label", "2:10 PM: 1 word")
    expect(tile(page, 1)).to_contain_text("Busiest minute2:10 PM1 word")
    expect(page.locator(".entry")).to_have_count(1)
    expect(page.locator(".entry")).to_contain_text("ACORN")
    expect(page.locator("#sumText .live")).to_have_count(0)
    assert "period=hour" in page.url and "hour=14" in page.url
    # The next hour is the one still running.
    page.click("#next")
    expect(page.locator("#sumTitle")).to_have_text("3:00 PM – 4:00 PM")
    expect(page.locator("#sumText .live")).to_have_text("Live")
    expect(page.locator(".entry")).to_contain_text("MONET")
    expect(page.locator("#next")).to_be_disabled()
    page.click("#up")
    expect(page.locator("#sumTitle")).to_have_text("Today")
    # Each hour of the day opens the same way.
    page.locator(".hour h3", has_text="2:00 PM").get_by_role("button", name="Minute by minute").click()
    expect(page.locator("#sumTitle")).to_have_text("2:00 PM – 3:00 PM")
    assert errors == []


def test_a_week_shows_its_days_and_who_and_where_charted_most(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, query="&period=week")
    expect(page.locator("#sumTitle")).to_have_text("This week")
    expect(page.locator("#navLabel")).to_have_text("Nov 2 – Nov 8, 2026")
    expect(page.locator("#sumText")).to_have_text("Live")
    expect(tile(page, 0)).to_contain_text("Words charted3")
    expect(tile(page, 1)).to_contain_text("Busiest dayFri, Nov 62 words")
    expect(tile(page, 2)).to_contain_text("In the shared world2")
    expect(page.locator("#chart .ticks span")).to_have_text(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    # Days to come can't be opened; days so far are listed newest first.
    expect(page.locator("#chart .bar.go")).to_have_count(5)
    expect(page.locator(".row .when")).to_have_text(["Fri, Nov 6", "Thu, Nov 5", "Wed, Nov 4", "Tue, Nov 3", "Mon, Nov 2"])
    expect(page.locator(".row .num")).to_have_text(["2", "1", "—", "—", "—"])

    cards = page.locator(".card")
    expect(cards.nth(0)).to_contain_text("Top surveyors")
    expect(cards.nth(0).locator(".rank .lbl")).to_have_text(["ABC", "ZED"])
    expect(cards.nth(1).locator(".rank .lbl")).to_have_text(["Acorn Hollow", "Zeus Point"])
    expect(cards.nth(2).locator(".rank .lbl")).to_have_text(["Forest", "Olympus"])
    # Over the whole UTC days the week has had so far.
    tops = [r for r in fake.requests if r.startswith("/top/")]
    first, last = NOW_MS // 86_400_000 - 4, NOW_MS // 86_400_000 + 1
    assert tops == [f"/top/{first}/{last}"]
    assert page.evaluate("document.documentElement.scrollWidth") <= 375

    # A day opens from its row.
    page.locator(".row", has_text="Thu, Nov 5").click()
    expect(page.locator("#sumTitle")).to_have_text("Yesterday")
    assert errors == []


def test_a_month_and_a_year(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, query="&period=month")
    expect(page.locator("#sumTitle")).to_have_text("November 2026")
    expect(page.locator("#chart .bar")).to_have_count(30)
    expect(page.locator(".row")).to_have_count(6)

    page.get_by_role("tab", name="Year").click()
    expect(page.locator("#sumTitle")).to_have_text("2026")
    expect(page.locator(".mcal")).to_have_count(12)
    expect(page.locator(".mcal .cell:not(.pad)")).to_have_count(365)
    nov6 = page.get_by_role("button", name="Fri, Nov 6: 2 words")
    expect(nov6).to_have_class("cell l4 go")
    expect(page.get_by_role("button", name="Thu, Nov 5: 1 word")).to_have_class("cell l2 go")
    expect(page.get_by_role("button", name="Sat, Nov 7: still to come")).to_have_class("cell later")
    # A year's rows are its months.
    expect(page.locator(".row .when").first).to_have_text("November 2026")
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    page.get_by_role("button", name="Thu, Nov 5: 1 word").click()
    expect(page.locator("#sumTitle")).to_have_text("Yesterday")
    expect(page.get_by_role("tab", name="Day")).to_have_attribute("aria-selected", "true")
    assert errors == []


def test_all_time_shows_how_much_of_the_world_is_charted(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, query="&period=all")
    expect(page.locator("#sumTitle")).to_have_text("All time")
    expect(page.locator("#navLabel")).to_have_text("Since the log began on Nov 6, 2026")
    expect(page.locator("#prev")).to_be_hidden()
    expect(page.locator(".chart .ymax").nth(1)).to_have_text("2 of 1,120,206 hidden words in the shared world · <0.01%")
    expect(page.locator(".meter")).to_have_attribute("aria-valuenow", "2")
    # One month is a meter; the line that rises toward the whole world needs two.
    expect(page.locator("svg.line")).to_have_count(0)
    expect(page.locator(".row .when")).to_have_text(["November 2026"])
    page.locator(".row").click()
    expect(page.locator("#sumTitle")).to_have_text("November 2026")
    assert errors == []


def test_all_time_draws_the_world_filling_in_month_by_month(page: Page, site_url, errors):
    later = int(datetime(2027, 1, 10, 17, 0, tzinfo=timezone.utc).timestamp() * 1000)
    day = 86_400_000
    # Hidden words in ten territories of ten themes, over three months.
    words = [[f"W{chr(65 + i)}X", i * 48, 0, 0, 0, "ZED", later - (60 - 6 * i) * day, i] for i in range(10)]
    themes = {i: [f"Theme {i}", 30 * i] for i in range(10)}
    fake = FakeSurveyLog(words, {}, themes)
    fake.now_ms = later
    page.clock.set_fixed_time(later / 1000)
    page.route(f"{SURVEY}/v1/survey/log/**", fake.handle)
    page.goto(f"{site_url}/letterfield-log?survey={SURVEY}&period=all")
    expect(page.locator("svg.line")).to_have_count(1)
    marks = page.locator(".overlay button")
    expect(marks).to_have_count(3)
    expect(marks.nth(0)).to_have_attribute("aria-label", "By the end of November 2026: 4 · <0.01%")
    expect(marks.nth(2)).to_have_attribute("aria-label", "By the end of January 2027: 10 · <0.01%")
    expect(page.locator("#chart .ticks span").first).to_have_text("Nov 2026")
    # Eight themes, then the rest folded into one row with no bar of its own.
    themes_card = page.locator(".card", has_text="Themes")
    expect(themes_card.locator(".rank li")).to_have_count(9)
    expect(themes_card.locator(".rank li").last).to_contain_text("2 other themes")
    expect(themes_card.locator(".rank li").last.locator(".track i")).to_have_count(0)
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
    expect(tile(page, 0)).to_contain_text("Charted first by you1")
    assert "view=mine" in page.url
    # Only the hours within 10 minutes of a find (in case this device's clock
    # was off) were read: MONET's, and the one it's 5 minutes into.
    hour = MONET[6] // 3_600_000
    assert sorted(r for r in fake.requests if "/hour/" in r) == [f"/hour/{hour - 1}", f"/hour/{hour}"]

    # Longer periods count this browser's finds, without asking the server.
    before = len(fake.requests)
    page.get_by_role("tab", name="Week").click()
    expect(tile(page, 0)).to_contain_text("Charted first by you2")
    expect(page.locator(".row .num")).to_have_text(["1", "1", "—", "—", "—"])
    expect(page.locator(".card")).to_have_count(0)
    assert fake.requests[before:] == []
    page.locator(".row", has_text="Thu, Nov 5").click()
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
