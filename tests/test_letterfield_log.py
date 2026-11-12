"""Letterfield's survey log page, against a fake of the log's API.

The page reads the Worker's URL from ?survey=, so these tests point it at
https://survey.test (see fake_survey_log.py). The clock is fixed at 3:30 PM
on Friday, November 6, 2026, in Toronto, the time zone every test runs in,
so "this week" is Monday, November 2, to Sunday, November 8.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Page, expect

from fake_survey_log import SURVEY, FakeSurveyLog

NOW_MS = int(datetime(2026, 11, 6, 20, 30, tzinfo=UTC).timestamp() * 1000)  # 3:30 PM in Toronto
MINUTE = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
PLACES = {"0,0": "Acorn Hollow", "1,0": "Monet Reach", "-1,2": "Zeus Point"}
THEMES = {11: ["Forest", 40], 0: ["Old Masters", 56], 17: ["Olympus", 25]}

ACORN = ["ACORN", 5, 7, 0, 0, "ZED", NOW_MS - 80 * MINUTE, 11]  # 2:10 PM
MONET = ["MONET", 60, 3, 2, 1, "", NOW_MS - 25 * MINUTE, 0]  # 3:05 PM, a stray
ZEUS = ["ZEUS", -40, 100, 6, 0, "ABC", NOW_MS - 24 * 60 * MINUTE, 17]  # yesterday


def open_log(
    page: Page,
    site_url: str,
    fake: FakeSurveyLog,
    query: str = "",
    finds=None,
    now_ms: int = NOW_MS,
    running: bool = False,
    share: bool = True,
) -> None:
    """Opens the log at `now_ms`, with the clock stopped there, or `running` on from it
    (for what happens as time passes: page.clock.fast_forward moves it on). With
    share=False, SHARE_URL is blanked, as on a preview without a share Worker."""
    if not share:

        def blank(route):
            response = route.fetch()
            route.fulfill(response=response, body=re.sub(r"\b(const SHARE_URL = )'[^']*'", r"\1''", response.text()))

        page.route(lambda url: urlsplit(url).path == "/letterfield-log", blank)
    if running:
        page.clock.install(time=now_ms / 1000)
    else:
        page.clock.set_fixed_time(now_ms / 1000)
    if finds is not None:
        page.add_init_script(f"localStorage.setItem('letterfield.finds.v4', {json.dumps(json.dumps(finds))})")
    fake.now_ms = now_ms
    page.route(f"{SURVEY}/v1/survey/log/**", fake.handle)
    page.goto(f"{site_url}/letterfield-log?survey={SURVEY}{query}")


def entry(page: Page, word: str):
    """The row of one word (a place's name can hold another word's letters)."""
    return page.locator(".entry").filter(has=page.locator("a.fly", has_text=re.compile(f"^{word}$")))


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
    expect(acorn.locator("a.fly")).to_have_attribute("href", "/letterfield#f-acorn-5-7-0")
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
    expect(page.locator(".row .when")).to_have_text(
        ["Fri, Nov 6", "Thu, Nov 5", "Wed, Nov 4", "Tue, Nov 3", "Mon, Nov 2"]
    )
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
    # Shades go by rank among the year's days with words: the quietest is the palest.
    expect(page.get_by_role("button", name="Thu, Nov 5: 1 word")).to_have_class("cell l1 go")
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
    # ZEUS, the day before the log began, came from a sector sending its older words.
    expect(page.locator("#navLabel")).to_have_text("Since the first word, on Nov 5, 2026")
    expect(page.locator("#prev")).to_be_hidden()
    expect(page.locator(".chart .ymax").nth(1)).to_have_text("2 of 1,119,752 hidden words in the shared world · <0.01%")
    expect(page.locator(".meter")).to_have_attribute("aria-valuenow", "2")
    # One month is a meter; the line that rises toward the whole world needs two.
    expect(page.locator("svg.line")).to_have_count(0)
    expect(page.locator(".row .when")).to_have_text(["November 2026"])
    page.locator(".row").click()
    expect(page.locator("#sumTitle")).to_have_text("November 2026")
    assert errors == []


def test_all_time_draws_the_world_filling_in_month_by_month(page: Page, site_url, errors):
    later = int(datetime(2027, 1, 10, 17, 0, tzinfo=UTC).timestamp() * 1000)
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
    expect(page.locator("#chart .ticks span").first).to_have_text("Nov ’26")
    expect(page.locator("#navLabel")).to_have_text("Since the log began on Nov 6, 2026")
    # Eight themes, then the rest folded into one row with no bar of its own.
    themes_card = page.locator(".card", has_text="Themes")
    expect(themes_card.locator(".rank li")).to_have_count(9)
    expect(themes_card.locator(".rank li").last).to_contain_text("2 other themes")
    expect(themes_card.locator(".rank li").last.locator(".track i")).to_have_count(0)
    assert errors == []


def test_all_time_starts_with_the_first_word_logged(page: Page, site_url, errors):
    # Words a sector held from before the log began, sent when it woke.
    early = [["ACORN", 5, 7, 0, 0, "OLD", int(datetime(2026, 9, 20, tzinfo=UTC).timestamp() * 1000), 11]]
    fake = FakeSurveyLog(early + [ACORN, MONET], PLACES, THEMES)
    open_log(page, site_url, fake, query="&period=all")
    expect(page.locator("#navLabel")).to_have_text("Since the first word, on Sep 20, 2026")
    expect(page.locator("#chart .bar")).to_have_count(3)
    expect(page.locator(".row .when")).to_have_text(["November 2026", "October 2026", "September 2026"])
    expect(page.locator("svg.line")).to_have_count(1)
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


# Sharing without a share sheet copies the words and link; this keeps what's copied.
NO_SHARE_SHEET = """
  Object.defineProperty(Navigator.prototype, 'share', { value: undefined, configurable: true });
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: t => { window.__copied = t; return Promise.resolve(); } } });
"""


def test_a_surveyor_opens_from_a_top_list_with_an_address_to_share(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    birch = ["BIRCH", 100, 7, 0, 0, "ZED", NOW_MS - 20 * DAY_MS, 11]  # October 17
    fake = FakeSurveyLog([birch, ACORN, MONET, ZEUS], PLACES, THEMES)
    page.add_init_script(NO_SHARE_SHEET)
    open_log(page, site_url, fake, query="&period=week")
    page.locator(".card", has_text="Top surveyors").get_by_role("link", name="ZED").click()

    expect(page.locator("#focusKind")).to_have_text("Surveyor")
    expect(page.locator("#focusName")).to_have_text("ZED")
    expect(page.locator("#focusNote")).to_contain_text("Initials aren’t unique")
    expect(page).to_have_title("ZED · Letterfield survey log")
    expect(page.locator("#whose")).to_be_hidden()
    # It keeps the week it came from.
    expect(page.locator("#sumTitle")).to_have_text("This week")
    assert "surveyor=ZED" in page.url and "period=week" in page.url
    week = NOW_MS // HOUR_MS - 4 * 24 - 15  # Monday, midnight in Toronto, in UTC hours
    assert f"/surveyor/ZED/{week}/{week + 7 * 24}" in fake.requests
    expect(tile(page, 0)).to_contain_text("Words charted1")
    expect(page.locator(".entry .word")).to_have_text(["ACORN"])
    expect(page.locator(".hour h3")).to_have_text(["Friday, November 61 word"])
    cards = page.locator(".card")
    expect(cards.nth(0)).to_contain_text("Top territories")
    expect(cards.nth(0).locator(".rank .lbl")).to_have_text(["Acorn Hollow"])
    expect(cards.nth(1).locator(".rank .lbl")).to_have_text(["Forest"])
    assert page.evaluate("document.documentElement.scrollWidth") <= 375

    page.click("#share")
    expect(page.locator("#share")).to_have_text("Copied")
    # The share Worker's card of this week, pinned by its Monday and the hours
    # the page asked for, so it's still that week when it's read later; the
    # page's own address leaves the date out, so it stays this week.
    assert "day=" not in page.url
    assert page.evaluate("window.__copied") == (
        "ZED charted 1 word first in Letterfield’s shared survey this week, most in Acorn Hollow."
        f" Latest: ACORN.\nhttps://share.michaelwarkentin.com/v/surveyor/ZED/week/2026-11-02/{week}-{week + 7 * 24}"
    )
    # All time is a surveyor's own view's first, so its address needs no period.
    page.click("#periods [data-p=all]")
    expect(page.locator(".entry .word")).to_have_text(["ACORN", "BIRCH"])
    expect(page.locator(".hour h3")).to_have_count(2)
    assert "surveyor=ZED" in page.url and "period" not in page.url
    # Back is everyone's week again.
    page.go_back()
    expect(page.locator("#focus")).to_be_hidden()
    expect(page.locator("#whose")).to_be_visible()
    expect(page.locator("#sumTitle")).to_have_text("This week")
    expect(page.locator(".card").nth(0).locator(".rank .lbl")).to_have_text(["ABC", "ZED"])
    expect(page).to_have_title("Letterfield survey log")
    assert errors == []


def test_a_surveyors_territories_take_their_themes_hue(page: Page, site_url, errors):
    # Only the newest word is on the first page, so Zeus Point's theme comes from the top themes.
    zeus = ["ZEUS", -40, 100, 6, 0, "ZED", NOW_MS - 24 * 60 * MINUTE, 17]
    fake = FakeSurveyLog([ACORN, zeus], PLACES, THEMES, slice_page=1)
    open_log(page, site_url, fake, query="&surveyor=ZED")
    places = page.locator(".card", has_text="Top territories")
    expect(places.locator(".rank .lbl")).to_have_text(["Acorn Hollow", "Zeus Point"])
    expect(places.locator(".rank .lbl .dot")).to_have_count(2)
    expect(page.locator(".entry")).to_have_count(1)
    assert errors == []


def test_a_surveyors_day_opens_hour_by_hour(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, query="&surveyor=ZED&period=day")
    expect(page.locator("#sumTitle")).to_have_text("Today")
    expect(page.locator("#chart .bar.some")).to_have_count(1)
    page.locator("#chart .bar").nth(14).click()
    expect(page.locator("#sumTitle")).to_have_text("2:00 PM – 3:00 PM")
    expect(page.locator("#chart .bar.some")).to_have_attribute("aria-label", "2:10 PM: 1 word")
    expect(page.locator(".entry .word")).to_have_text(["ACORN"])
    assert "surveyor=ZED" in page.url and "hour=14" in page.url
    assert errors == []


def test_a_words_theme_and_territory_open_their_own_views(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fern = ["FERN", 10, 20, 0, 0, "AMY", NOW_MS - 30 * MINUTE, 11]  # 3:00 PM, in Acorn Hollow too
    fake = FakeSurveyLog([ACORN, MONET, ZEUS, fern], PLACES, THEMES, totals={"0,0": 110})
    open_log(page, site_url, fake)
    entry(page, "ACORN").get_by_role("link", name="Forest").click()

    expect(page.locator("#focusKind")).to_have_text("Theme")
    expect(page.locator("#focusName")).to_have_text("Forest")
    expect(page.locator("#sumTitle")).to_have_text("Today")
    assert "theme=11" in page.url and "period=day" in page.url
    expect(tile(page, 0)).to_contain_text("Hidden words charted2")
    expect(page.locator(".entry .word")).to_have_text(["FERN", "ACORN"])
    cards = page.locator(".card")
    expect(cards.nth(0).locator(".rank .lbl")).to_have_text(["AMY", "ZED"])
    expect(cards.nth(1).locator(".rank .lbl")).to_have_text(["Acorn Hollow"])
    # On the theme's own view, its name isn't a link; the territory still is.
    acorn = entry(page, "ACORN")
    expect(acorn.get_by_role("link", name="Forest")).to_have_count(0)
    acorn.get_by_role("link", name="Acorn Hollow").click()

    expect(page.locator("#focusKind")).to_have_text("Territory")
    expect(page.locator("#focusName")).to_have_text("Acorn Hollow")
    expect(page.locator("#focusNote")).to_have_text("24E · 24S, at its middle · Forest")
    expect(page.locator("#periods")).to_be_hidden()
    expect(page.locator(".nav")).to_be_hidden()
    assert "territory=0,0" in page.url and "period" not in page.url
    expect(page.locator("#sumTitle")).to_have_text("Charted so far")
    expect(tile(page, 0)).to_contain_text("Hidden words charted2 of 110")
    expect(tile(page, 1)).to_contain_text("Surveyors2")
    expect(page.locator("#chart .meter")).to_have_attribute("aria-valuenow", "2")
    expect(page.locator("#fly")).to_have_attribute("href", "/letterfield#f-fern-10-20-0")
    expect(page.locator(".entry .word")).to_have_text(["FERN", "ACORN"])
    expect(page.locator(".card .rank .lbl")).to_have_text(["AMY", "ZED"])
    assert page.evaluate("document.documentElement.scrollWidth") <= 375

    # Its theme opens from the bar, over all time, since a territory has no periods.
    page.locator("#focusNote").get_by_role("link", name="Forest").click()
    expect(page.locator("#focusName")).to_have_text("Forest")
    expect(page.locator("#sumTitle")).to_have_text("All time")
    page.click("#everyone")
    expect(page.locator("#focus")).to_be_hidden()
    expect(page.locator("#sumTitle")).to_have_text("All time")
    # Back goes through each view in turn.
    page.go_back()
    expect(page.locator("#focusName")).to_have_text("Forest")
    page.go_back()
    expect(page.locator("#focusName")).to_have_text("Acorn Hollow")
    page.go_back()
    expect(page.locator("#focusName")).to_have_text("Forest")
    expect(page.locator("#sumTitle")).to_have_text("Today")
    assert errors == []


def test_a_busy_surveyors_words_come_a_hundred_at_a_time(page: Page, site_url, errors):
    words = [["BIRCH", i, 0, 0, 0, "ZED", NOW_MS - (i + 1) * 5 * MINUTE, 11] for i in range(130)]
    fake = FakeSurveyLog(words, PLACES, THEMES)
    open_log(page, site_url, fake, query="&surveyor=ZED&period=month")
    expect(tile(page, 0)).to_contain_text("Words charted130")
    expect(page.locator(".entry")).to_have_count(100)
    page.click(".more")
    expect(page.locator(".entry")).to_have_count(130)
    expect(page.locator(".more")).to_have_count(0)
    # The second page carries on under the same day.
    expect(page.locator(".hour h3")).to_have_text(["Friday, November 6130 words"])
    assert any(r.endswith("?before=100") for r in fake.requests)
    assert errors == []


def test_a_theme_that_isnt_one_says_so(page: Page, site_url):
    open_log(page, site_url, FakeSurveyLog([ACORN], PLACES, THEMES), query="&theme=500")
    expect(page.locator(".status strong")).to_have_text("Not in the log")


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


# ---------- What the page shows as time passes (<html data-log>) ----------

HIDE = """hidden => {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event('visibilitychange'));
}"""


def wait_for_request(page: Page, fake: FakeSurveyLog, path: str, timeout_ms: int = 5000) -> None:
    """Waits until the fake has been asked for `path`: the page asks for some things only after others."""
    for _ in range(timeout_ms // 50):
        if path in fake.requests:
            return
        page.wait_for_timeout(50)
    assert path in fake.requests


def wait_for_requests(page: Page, fake: FakeSurveyLog, count: int, timeout_ms: int = 5000) -> None:
    """Waits until the fake has been asked `count` things: its handler runs between Playwright calls."""
    for _ in range(timeout_ms // 50):
        if len(fake.requests) >= count:
            return
        page.wait_for_timeout(50)
    assert len(fake.requests) >= count


def test_a_live_hour_that_fails_to_refresh_keeps_its_words_and_tries_again(page: Page, site_url):
    # Skips the errors fixture: the browser logs the 503s.
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, query="&period=hour", running=True)
    expect(page.locator(".entry")).to_have_count(1)  # MONET, at 3:05
    expect(page.locator("#sumText .live")).to_have_text("Live")
    fake.fail = True
    asked = len(fake.requests)
    page.clock.fast_forward(21_000)  # the hour reloads every 20 s
    wait_for_requests(page, fake, asked + 1)
    page.wait_for_timeout(500)  # for the page to take the failure in
    # Its words stay on screen, rather than "Can't reach the log".
    expect(page.locator(".entry")).to_have_count(1)
    expect(page.locator(".status")).to_have_count(0)
    expect(page.locator("#tiles .tile")).to_have_count(3)
    expect(page.locator("html")).to_have_attribute("data-log", "stale")
    # And the next reload, once the server's back, brings what was charted since.
    fake.fail = False
    fake.entries.append(["FERN", 10, 20, 0, 0, "AMY", NOW_MS + 10_000, 11])
    page.clock.fast_forward(21_000)
    expect(page.locator(".entry")).to_have_count(2)
    expect(page.locator("html")).to_have_attribute("data-log", "ready")


def test_a_day_that_ends_on_screen_stops_saying_live(page: Page, site_url, errors):
    late = int(datetime(2026, 11, 7, 4, 59, 30, tzinfo=UTC).timestamp() * 1000)  # 11:59:30 PM in Toronto
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, now_ms=late, running=True)
    expect(page.locator("#sumTitle")).to_have_text("Today")
    expect(page.locator("#sumText .live")).to_have_text("Live")
    expect(page.locator("#next")).to_be_disabled()
    page.clock.fast_forward(60_000)  # midnight passes
    expect(page.locator("#sumTitle")).to_have_text("Yesterday")
    expect(page.locator("#sumText .live")).to_have_count(0)
    expect(page.locator("#next")).to_be_enabled()
    assert "day=2026-11-06" in page.url
    expect(page.locator("html")).to_have_attribute("data-log", "ready")
    assert errors == []


def test_an_hour_that_ended_while_the_page_was_hidden_stops_saying_live(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    open_log(page, site_url, fake, query="&period=hour", now_ms=NOW_MS + 29 * MINUTE, running=True)  # 3:59 PM
    expect(page.locator("#sumText .live")).to_have_text("Live")
    expect(page.locator("#next")).to_be_disabled()
    page.evaluate(HIDE, True)
    page.clock.fast_forward("05:00")
    page.evaluate(HIDE, False)  # back at 4:04
    expect(page.locator("#sumText .live")).to_have_count(0)
    expect(page.locator("#next")).to_be_enabled()
    expect(page.locator("#sumTitle")).to_have_text("3:00 PM – 4:00 PM")
    assert errors == []


# A share sheet that takes files; this keeps what's shared, and the picture's size.
SHARE_SHEET = """
  Object.defineProperty(Navigator.prototype, 'canShare', { value: d => true, configurable: true });
  Object.defineProperty(Navigator.prototype, 'share', { configurable: true, value: async d => {
    const files = await Promise.all((d.files || []).map(async f => {
      const b = await createImageBitmap(f);
      return { name: f.name, type: f.type, width: b.width, height: b.height };
    }));
    window.__shared = { ...d, files };
  } });
"""


def test_a_surveyor_shares_a_line_and_a_picture_of_their_view(page: Page, site_url, errors, tmp_path):
    page.set_viewport_size({"width": 375, "height": 740})
    birch = ["BIRCH", 100, 7, 0, 0, "ZED", NOW_MS - 20 * DAY_MS, 11]
    fern = ["FERN", 9, 9, 0, 2, "ZED", NOW_MS - 30 * MINUTE, 11]
    fake = FakeSurveyLog([birch, ACORN, fern, ZEUS], PLACES, THEMES)
    page.add_init_script(SHARE_SHEET)
    # Without a share Worker (a preview that has none), Share attaches the page's own picture.
    open_log(page, site_url, fake, query="&surveyor=zed#debug", share=False)
    expect(page.locator(".entry .word")).to_have_text(["FERN", "ACORN", "BIRCH"])
    # The picture's made once the view's loaded, ready for the tap.
    page.wait_for_function("window.__log.share()?.file")
    page.click("#share")
    page.wait_for_function("window.__shared")
    shared = page.evaluate("window.__shared")
    assert shared["text"] == (
        "ZED charted 3 words first in Letterfield’s shared survey so far, most in Acorn Hollow."
        " Latest: FERN, ACORN, BIRCH."
    )
    assert shared["url"] == page.url.split("#")[0]  # all time has no date to pin
    assert shared["title"] == "ZED · Letterfield survey log"
    assert shared["files"] == [{"name": "letterfield-zed.png", "type": "image/png", "width": 1200, "height": 630}]

    # Another period is another line, made for it.
    page.evaluate("window.__shared = null")
    page.click("#periods [data-p=day]")
    expect(page.locator(".entry .word")).to_have_text(["FERN", "ACORN"])
    page.wait_for_function("window.__log.share()?.run === window.__log.state.run && window.__log.share().file")
    page.click("#share")
    page.wait_for_function("window.__shared")
    assert page.evaluate("window.__shared.text") == (
        "ZED charted 2 words first in Letterfield’s shared survey today, most in Acorn Hollow. Latest: FERN, ACORN."
    )
    url = urlsplit(page.evaluate("window.__shared.url"))
    assert f"{url.scheme}://{url.netloc}{url.path}" == f"{site_url}/letterfield-log"
    assert parse_qs(url.query) == {"survey": [SURVEY], "surveyor": ["ZED"], "period": ["day"], "day": ["2026-11-06"]}
    assert errors == []


def test_a_theme_and_a_territory_share_lines_of_their_own(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    page.add_init_script(SHARE_SHEET)
    open_log(page, site_url, fake, query="&theme=11#debug", share=False)
    expect(page.locator("#focusName")).to_have_text("Forest")
    page.wait_for_function("window.__log.share()?.file")
    page.click("#share")
    page.wait_for_function("window.__shared")
    assert page.evaluate("window.__shared.text") == (
        "1 hidden word charted in Letterfield’s Forest territories so far. Latest: ACORN."
    )
    page.evaluate("window.__shared = null")
    page.goto(f"{site_url}/letterfield-log?survey=https://survey.test&territory=0,0#debug")
    expect(page.locator("#focusName")).to_have_text("Acorn Hollow")
    page.wait_for_function("window.__log.share()?.file")
    page.click("#share")
    page.wait_for_function("window.__shared")
    assert page.evaluate("window.__shared.text") == (
        "Acorn Hollow, in Letterfield’s shared survey: 1 of its 112 hidden words charted so far, by 1 surveyor."
        " Latest: ACORN."
    )
    assert page.evaluate("window.__shared.files[0].name") == "letterfield-acorn-hollow.png"
    assert errors == []


def test_a_day_and_an_hour_have_top_lists_of_their_own(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    birch = ["BIRCH", 7, 9, 0, 0, "ZED", NOW_MS - 40 * MINUTE, 11]  # 2:50 PM
    fern = ["FERN", 9, 11, 0, 0, "ABC", NOW_MS - 70 * MINUTE, 11]  # 2:20 PM
    late = ["OAK", 11, 13, 0, 0, "ABC", NOW_MS - 16 * HOUR_MS, 11]  # 11:30 PM yesterday, the same UTC day
    fake = FakeSurveyLog([ACORN, MONET, ZEUS, birch, fern, late], PLACES, THEMES)
    open_log(page, site_url, fake)
    # Today in Toronto, counted by the hour: not the whole UTC day, which
    # began at 7 PM yesterday here and holds OAK.
    hour = NOW_MS // HOUR_MS
    wait_for_request(page, fake, f"/top/hours/{hour - 15}/{hour + 1}")
    cards = page.locator(".card")
    surveyors = cards.filter(has_text="Top surveyors")
    expect(surveyors.locator(".rank .lbl")).to_have_text(["ZED", "ABC"])
    expect(surveyors.locator(".num")).to_have_text(["2", "1"])
    expect(surveyors).not_to_contain_text("UTC")
    expect(cards.filter(has_text="Top territories").locator(".rank .lbl")).to_have_text(["Acorn Hollow"])
    assert page.evaluate("document.documentElement.scrollWidth") <= 375

    # Minute by minute, the hour's own.
    page.locator(".hour h3", has_text="2:00").get_by_role("button", name="Minute by minute").click()
    expect(page.locator("#sumTitle")).to_contain_text("2:00")
    wait_for_request(page, fake, f"/top/hours/{hour - 1}/{hour}")
    expect(surveyors.locator(".rank .lbl")).to_have_text(["ZED", "ABC"])
    expect(surveyors.locator(".num")).to_have_text(["2", "1"])
    # Each opens that surveyor's own view of the same hour.
    surveyors.get_by_role("link", name="ABC").click()
    expect(page.locator("#focusName")).to_have_text("ABC")
    assert "surveyor=ABC" in page.url and "period=hour" in page.url
    expect(page.locator(".entry .word")).to_have_text(["FERN"])
    assert errors == []


def test_an_hour_still_running_keeps_its_top_lists_while_it_refreshes(page: Page, site_url, errors):
    fake = FakeSurveyLog([MONET, ["ELM", 3, 3, 0, 0, "ZED", NOW_MS - 10 * MINUTE, 11]], PLACES, THEMES)
    open_log(page, site_url, fake, query="&period=hour", running=True)
    surveyors = page.locator(".card").filter(has_text="Top surveyors")
    expect(surveyors.locator(".rank .lbl")).to_have_text(["ZED"])
    fake.entries.append(["ASH", 4, 4, 0, 0, "AMY", NOW_MS + 5 * MINUTE, 11])
    fake.entries.append(["YEW", 5, 5, 0, 0, "AMY", NOW_MS + 6 * MINUTE, 11])
    seen = []
    page.expose_function("__cards", lambda n: seen.append(n))
    page.evaluate("""() => new MutationObserver(() => window.__cards(document.querySelectorAll('#cards .card').length))
      .observe(document.querySelector('#cards'), { childList: true })""")
    page.clock.fast_forward(7 * 60_000)
    expect(surveyors.locator(".rank .lbl")).to_have_text(["AMY", "ZED"])
    # It went from one set of cards to the next, never through none.
    assert 0 not in seen
    assert errors == []


def test_with_a_share_worker_a_view_links_to_its_card_with_no_picture_of_its_own(page: Page, site_url, errors):
    # ?share= stands in for SHARE_URL: the share Worker's /v/ addresses, whose
    # pages carry a card of the view as their link preview.
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES)
    page.add_init_script(SHARE_SHEET)
    open_log(page, site_url, fake, query="&share=https://share.test/&surveyor=zed&period=week#debug")
    expect(page.locator(".entry .word")).to_have_text(["ACORN"])
    page.wait_for_function("window.__log.share()?.run === window.__log.state.run")
    page.click("#share")
    page.wait_for_function("window.__shared")
    shared = page.evaluate("window.__shared")
    # This week in Toronto, pinned by its Monday and the UTC hours the page asked the log for.
    week = NOW_MS // HOUR_MS - 4 * 24 - 15
    assert f"/surveyor/ZED/{week}/{week + 7 * 24}" in fake.requests
    assert shared["url"] == f"https://share.test/v/surveyor/ZED/week/2026-11-02/{week}-{week + 7 * 24}"
    assert shared["text"].startswith("ZED charted 1 word first in Letterfield’s shared survey this week")
    # The link's card is the picture: none of the page's own goes with it.
    assert shared["files"] == []
    assert page.evaluate("window.__log.share().file") is None

    # All time, a dark page, and a territory.
    page.evaluate("window.__shared = null")
    page.emulate_media(color_scheme="dark")
    page.click("#periods [data-p=all]")
    expect(page.locator(".entry .word")).to_have_text(["ACORN"])
    page.wait_for_function("window.__log.share()?.run === window.__log.state.run")
    page.click("#share")
    page.wait_for_function("window.__shared")
    assert page.evaluate("window.__shared.url") == "https://share.test/v/d/surveyor/ZED/all"
    page.evaluate("window.__shared = null")
    page.emulate_media(color_scheme="light")
    page.locator(".card", has_text="Top territories").get_by_role("link", name="Acorn Hollow").click()
    expect(page.locator("#focusName")).to_have_text("Acorn Hollow")
    page.wait_for_function("window.__log.share()?.run === window.__log.state.run")
    page.click("#share")
    page.wait_for_function("window.__shared")
    assert page.evaluate("window.__shared.url") == "https://share.test/v/territory/0,0"
    assert errors == []


# Monet Reach (1,0) hides two words in these tests; OAK, its last, comes in at 3:10 PM.
BIRCH = ["BIRCH", 50, 4, 0, 0, "AMY", NOW_MS - 50 * MINUTE, 0]  # 2:40 PM
OAK = ["OAK", 70, 10, 2, 0, "ZED", NOW_MS - 20 * MINUTE, 0]  # 3:10 PM
NOVA_TOTALS = {"1,0": 2}


def test_supernovas_have_a_view_of_their_own(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog([ACORN, MONET, BIRCH, OAK, ZEUS], PLACES, THEMES, totals=NOVA_TOTALS)
    open_log(page, site_url, fake)
    page.locator("header").get_by_role("link", name="Supernovas").click()

    expect(page.locator("#focusName")).to_have_text("Supernovas")
    assert "supernovas" in page.url and "supernovas=" not in page.url
    expect(page.locator("#sumTitle")).to_have_text("All time")
    expect(tile(page, 0)).to_contain_text("Supernovas1")
    expect(tile(page, 1)).to_contain_text("LatestMonet Reach")
    expect(tile(page, 2)).to_contain_text("Quickest30 minutes")
    nova = page.locator(".nova")
    expect(nova).to_have_count(1)
    expect(nova.locator(".what")).to_have_text("Monet Reachwent supernova")
    expect(nova.locator(".when")).to_have_text(re.compile(r"Nov 6 · 3:10\s?PM"))
    expect(nova.locator(".meta")).to_have_text(
        "Every one of its 2 hidden words charted, in 30 minutes by 2 surveyors. The last, OAK, by ZED. Most by AMY (1)."
    )
    expect(nova.get_by_role("link", name="OAK")).to_have_attribute("href", "/letterfield#f-oak-70-10-2")
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    # The territory opens from it, saying when it went and how.
    nova.get_by_role("link", name="Monet Reach").click()
    expect(page.locator("#focusName")).to_have_text("Monet Reach")
    expect(page.locator("#sumTitle")).to_have_text("Supernova")
    expect(page.locator("#sumText")).to_have_text(
        re.compile(r"Every hidden word charted · Friday, November 6, 2026, 3:10\s?PM")
    )
    expect(tile(page, 0)).to_contain_text("Went supernovaNov 6")
    expect(tile(page, 1)).to_contain_text("First word to last30 minutes")
    expect(tile(page, 2)).to_contain_text("Most charted byAMY1 of its 2 · 2 surveyors in all")
    expect(page.locator("#chart .meter.whole")).to_have_attribute("aria-valuenow", "2")
    # Its fill runs the whole width (a meter is not a supernova's row).
    widths = page.evaluate(
        "(() => { const m = document.querySelector('#chart .meter'); return [m.clientWidth, m.querySelector('i').clientWidth]; })()"
    )
    assert widths[1] >= widths[0] - 1 and widths[0] > 100
    # Its supernova sits just above the word that set it off.
    expect(page.locator("#log .entries > li")).to_have_count(4)
    rows = page.locator("#log .entries > li")
    expect(rows.nth(0)).to_have_class(re.compile(r"\bnova\b"))
    expect(rows.nth(1).locator(".word")).to_have_text("OAK")
    page.go_back()
    expect(page.locator("#focusName")).to_have_text("Supernovas")
    # An empty period says so.
    page.locator("#periods [data-p=week]").click()
    expect(tile(page, 0)).to_contain_text("Supernovas1")
    page.click("#prev")
    expect(page.locator("#log .status")).to_contain_text("No supernovas")
    assert errors == []


def test_a_day_and_an_hour_show_their_supernovas_where_they_happened(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, MONET, BIRCH, OAK, ZEUS], PLACES, THEMES, totals=NOVA_TOTALS)
    open_log(page, site_url, fake)
    strip = page.locator("#novaStrip .strip")
    expect(strip).to_contain_text("Monet Reach went supernova today: every hidden word charted")
    expect(page.locator(".bar.starred")).to_have_count(1)
    expect(page.locator(".bar.starred")).to_have_attribute(
        "aria-label", re.compile(r"3:00\s?PM – 4:00\s?PM: 2 words · 1 supernova")
    )
    three = page.locator(".hour").first
    expect(three.locator(".entries > li").nth(0)).to_have_class(re.compile(r"\bnova\b"))
    expect(three.locator(".entries > li").nth(1).locator(".word")).to_have_text("OAK")
    expect(three.locator(".entries > li")).to_have_count(3)  # the supernova, OAK and MONET
    # Minute by minute, the same.
    three.get_by_role("button", name="Minute by minute").click()
    expect(page.locator("#sumTitle")).to_have_text(re.compile(r"3:00\s?PM – 4:00\s?PM"))
    expect(page.locator(".entries > li").nth(0)).to_have_class(re.compile(r"\bnova\b"))
    expect(page.locator(".bar.starred")).to_have_count(1)
    expect(strip).to_contain_text("Monet Reach went supernova")
    # The strip leads to them all, for the period on screen.
    page.click("#up")
    page.locator("#periods [data-p=week]").click()
    expect(strip).to_contain_text("Monet Reach went supernova this week")
    strip.get_by_role("link", name="Supernovas →").click()
    expect(page.locator("#focusName")).to_have_text("Supernovas")
    expect(page.locator("#sumTitle")).to_have_text("This week")
    # Yesterday had none, and shows no strip.
    page.click("#everyone")
    page.locator("#periods [data-p=day]").click()
    page.click("#prev")
    expect(page.locator(".entry")).to_have_count(1)
    expect(strip).to_have_count(0)
    assert errors == []


def test_a_period_shows_without_its_supernovas_when_they_cannot_load(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, BIRCH, OAK], PLACES, THEMES, totals=NOVA_TOTALS)
    fake.fail_novas = True
    open_log(page, site_url, fake)
    expect(page.locator(".hour")).to_have_count(2)
    expect(page.locator(".entry")).to_have_count(3)
    expect(page.locator("#novaStrip .strip")).to_have_count(0)
    expect(page.locator(".nova")).to_have_count(0)


def test_a_supernova_shares_a_line_of_its_own(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, BIRCH, OAK], PLACES, THEMES, totals=NOVA_TOTALS)
    page.add_init_script(SHARE_SHEET)
    open_log(page, site_url, fake, query="&territory=1,0#debug", share=False)
    expect(page.locator("#sumTitle")).to_have_text("Supernova")
    page.wait_for_function("window.__log.share()?.file")
    page.click("#share")
    page.wait_for_function("window.__shared")
    assert page.evaluate("window.__shared.text") == (
        "Monet Reach went supernova in Letterfield’s shared survey on Nov 6, 2026:"
        " all 2 hidden words charted by 2 surveyors in 30 minutes, the last, OAK, by ZED."
    )
    page.evaluate("window.__shared = null")
    page.goto(f"{site_url}/letterfield-log?survey=https://survey.test&supernovas#debug")
    expect(page.locator(".nova")).to_have_count(1)
    page.wait_for_function("window.__log.share()?.file")
    page.click("#share")
    page.wait_for_function("window.__shared")
    assert page.evaluate("window.__shared.text") == (
        "1 territory went supernova in Letterfield’s shared survey so far, every hidden word charted. Latest: Monet Reach."
    )
    assert errors == []
