"""Guilds in Letterfield's survey log page: top guilds and a guild's own view.

The log knows a guild by its log id, a random id of its own (never its code
or the tag its carets wear), and counts the words its members charted while
in it. See test_letterfield_log.py for the clock and the fake.
"""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Page, expect

from fake_survey_log import FakeSurveyLog
from test_letterfield_log import (
    ACORN,
    DAY_MS,
    HOUR_MS,
    MINUTE,
    MONET,
    NO_SHARE_SHEET,
    NOW_MS,
    PLACES,
    THEMES,
    ZEUS,
    open_log,
)

ROOT = Path(__file__).resolve().parent.parent
COBALT, AMBER = "c0ba17c0ba", "a3be7a3be7"
GUILDS = {COBALT: ["Cobalt Compass Society", 220], AMBER: ["Amber Lantern Circle", 38]}
# Words counted for a guild carry its log id as a ninth item (the fake's way; the real log keeps it in a column).
BIRCH = ["BIRCH", 7, 9, 0, 0, "ZED", NOW_MS - 40 * MINUTE, 11, COBALT]  # 2:50 PM
FERN = ["FERN", 9, 11, 0, 0, "KAT", NOW_MS - 70 * MINUTE, 11, COBALT]  # 2:20 PM
OAK = ["OAK", 61, 4, 0, 0, "LUX", NOW_MS - 2 * DAY_MS, 0, COBALT]  # Wednesday
MOSS = ["MOSS", 11, 13, 0, 0, "BOB", NOW_MS - 30 * MINUTE, 11, AMBER]  # 3:00 PM


def test_top_guilds_open_a_guilds_own_view_with_an_address_to_share(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog([ACORN, MONET, ZEUS, BIRCH, FERN, OAK, MOSS], PLACES, THEMES, guilds=GUILDS)
    page.add_init_script(NO_SHARE_SHEET)
    open_log(page, site_url, fake, query="&period=week")
    card = page.locator(".card", has_text="Top guilds")
    expect(card.locator(".rank .lbl")).to_have_text(["Cobalt Compass Society", "Amber Lantern Circle"])
    expect(card.locator(".rank .num")).to_have_text(["3", "1"])
    # It comes after the top surveyors, in each guild's colour.
    expect(page.locator(".card h3")).to_have_text(["Top surveyors", "Top guilds", "Top territories", "Themes"])
    assert card.locator(".rank .lbl").first.evaluate("e => getComputedStyle(e).getPropertyValue('--h').trim()") == "220"
    card.get_by_role("link", name="Cobalt Compass Society").click()

    expect(page.locator("#focusKind")).to_have_text("Guild")
    expect(page.locator("#focusName")).to_have_text("Cobalt Compass Society")
    expect(page.locator("#focusNote")).to_contain_text("Members who keep off the surveyor list aren’t counted")
    expect(page).to_have_title("Cobalt Compass Society · Letterfield survey log")
    assert f"guild={COBALT}" in page.url and "period=week" in page.url
    week = NOW_MS // HOUR_MS - 4 * 24 - 15  # Monday, midnight in Toronto, in UTC hours
    assert f"/guild/{COBALT}/{week}/{week + 7 * 24}" in fake.requests
    expect(page.locator("#tiles .tile").nth(0)).to_contain_text("Words charted3")
    expect(page.locator(".entry .word")).to_have_text(["BIRCH", "FERN", "OAK"])
    expect(page.locator(".card h3")).to_have_text(["Members who charted most", "Top territories", "Themes"])
    expect(page.locator(".card", has_text="Members who charted most").locator(".rank .lbl")).to_have_text(
        ["KAT", "LUX", "ZED"]
    )
    assert page.evaluate("document.documentElement.scrollWidth") <= 375

    page.click("#share")
    expect(page.locator("#share")).to_have_text("Copied")
    assert page.evaluate("window.__copied") == (
        "The Cobalt Compass Society charted 3 words first in Letterfield’s shared survey this week, most in Acorn Hollow."
        " Latest: BIRCH, FERN, OAK."
        f"\nhttps://share.michaelwarkentin.com/v/guild/{COBALT}/week/2026-11-02/{week}-{week + 7 * 24}"
    )
    # A member's initials open their own view, as anywhere in the log.
    page.locator(".card", has_text="Members who charted most").get_by_role("link", name="ZED").click()
    expect(page.locator("#focusKind")).to_have_text("Surveyor")
    page.go_back()
    expect(page.locator("#focusName")).to_have_text("Cobalt Compass Society")
    page.go_back()
    expect(page.locator("#focus")).to_be_hidden()
    assert errors == []


def test_a_period_with_no_guild_words_has_no_top_guilds(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES, guilds=GUILDS)
    open_log(page, site_url, fake, query="&period=week")
    expect(page.locator(".card h3")).to_have_text(["Top surveyors", "Top territories", "Themes"])
    # A day's top lists, counted by the hour, have them too.
    fake = FakeSurveyLog([ACORN, BIRCH], PLACES, THEMES, guilds=GUILDS)
    open_log(page, site_url, fake)
    expect(page.locator(".card", has_text="Top guilds").locator(".rank .lbl")).to_have_text(["Cobalt Compass Society"])
    assert errors == []


def test_a_guild_says_when_it_charted_nothing_and_when_the_log_has_never_heard_of_it(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, OAK], PLACES, THEMES, guilds=GUILDS)
    open_log(page, site_url, fake, query=f"&guild={COBALT}&period=day")
    expect(page.locator("#focusName")).to_have_text("Cobalt Compass Society")
    expect(page.locator(".status strong")).to_have_text("Nothing charted")
    expect(page.locator(".status")).to_contain_text("This guild’s members charted no words in this period.")
    # All time is a guild's first view, as a surveyor's.
    open_log(page, site_url, fake, query=f"&guild={COBALT}")
    expect(page.locator("#sumTitle")).to_have_text("All time")
    expect(page.locator(".entry .word")).to_have_text(["OAK"])
    open_log(page, site_url, fake, query="&guild=ffffffffff")
    expect(page.locator("#focusName")).to_have_text("A guild")
    expect(page.locator(".status")).to_contain_text("This guild hasn’t charted a word yet.")
    # Anything but a log id is no guild at all: a guild's code or caret tag opens everyone's log.
    open_log(page, site_url, fake, query="&guild=ABCDEF")
    expect(page.locator("#focus")).to_be_hidden()
    assert errors == []


def test_a_new_guilds_page_is_named_from_its_address(page: Page, site_url, errors):
    # The game's link carries the guild's name as its three word numbers: Cobalt (11) Compass (0) Society (0).
    fake = FakeSurveyLog([ACORN], PLACES, THEMES, guilds={})
    open_log(page, site_url, fake, query=f"&guild={COBALT}&name=11-0-0")
    expect(page.locator("#focusName")).to_have_text("Cobalt Compass Society")
    expect(page.locator(".status")).to_contain_text(
        "The Cobalt Compass Society hasn’t charted a word yet. Its members’ words show here as they chart them."
    )
    # Its timelapse would have nothing to play, so the link waits for a first word.
    expect(page.locator("#timelapseLink")).to_be_hidden()
    assert errors == []


def test_a_guilds_page_has_its_timelapse_and_its_name_in_its_address_once_it_has_words(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN, BIRCH], PLACES, THEMES, guilds=GUILDS)
    open_log(page, site_url, fake, query=f"&guild={COBALT}")
    expect(page.locator(".entry .word")).to_have_text(["BIRCH"])
    expect(page.locator("#timelapseLink")).to_be_visible()
    expect(page.locator("#timelapseLink")).to_have_attribute("href", re.compile(f"guild={COBALT}"))
    # Kept in the address, for whoever it's shared with.
    assert "name=11-0-0" in page.url
    assert errors == []


def test_a_name_out_of_range_names_nothing(page: Page, site_url, errors):
    fake = FakeSurveyLog([ACORN], PLACES, THEMES, guilds={})
    open_log(page, site_url, fake, query=f"&guild={COBALT}&name=16-0-0")
    expect(page.locator("#focusName")).to_have_text("A guild")
    expect(page.locator(".status")).to_contain_text("This guild hasn’t charted a word yet.")
    assert "name=" not in page.url
    assert errors == []


def test_the_logs_guild_words_are_the_games():
    def lists(path: str) -> dict[str, str]:
        text = (ROOT / path).read_text()
        return {
            k: re.search(rf"^const {k} = (\[.*?\]);$", text, re.M | re.S)[1]
            for k in ("GUILD_FIRST", "GUILD_SECOND", "GUILD_THIRD")
        }

    assert lists("letterfield-log.html") == lists("letterfield.html")
