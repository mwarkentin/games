"""Letterfield's recovery codes, against the survey's fakes.

A recovery code, saved by the player, brings their surveyor back on any
device with no other to hand: entered under "Use a code", like a link code.
tests/fake_survey.py's FakeRecovery answers the Worker's recovery paths; the
real ones are tested in worker/test/players.test.js.
"""

from __future__ import annotations

import json
import re

from playwright.sync_api import Page, expect

from fake_survey import FakeLinks, FakePlayers, FakeRecovery, player_id
from test_letterfield_linking import OTHER, THEIR_PID, THEIRS, start
from test_letterfield_survey import open_notes
from test_letterfield_surveyors import KIM, TOKEN
from test_letterfield_sync import noted, words

CODE = "BCDFGHJKMNPQRSTVWXYZ"  # a code saved earlier, for THEIRS


def test_a_recovery_code_is_shown_once_and_keeps_a_backup(page: Page, site_url, errors):
    links = FakeLinks()
    recovery = FakeRecovery(links.players)
    start(page, site_url, links, recovery=recovery)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    open_notes(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="Recovery code").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "recovery")
    expect(card).to_contain_text("brings this surveyor back on any device")
    card.get_by_role("button", name="Make one").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "kept")
    code = page.evaluate("window.__lf.recoveryCode()")
    shown = "-".join(re.findall(".{4}", code))
    expect(card.locator("#recoveryCode")).to_have_text(shown)
    assert recovery.codes == {code: TOKEN}
    # Saving one keeps a backup from now on.
    expect(page.locator("html")).to_have_attribute("data-sync", "idle")
    assert player_id(TOKEN) in links.players.players
    card.get_by_role("button", name="Copy").click()
    expect(card.locator("#pairSaid")).to_have_text("Copied.")
    assert page.evaluate("navigator.clipboard.readText()") == shown
    with page.expect_download() as saved:
        card.get_by_role("button", name="Save as a file").click()
    assert saved.value.suggested_filename == "letterfield-recovery-code.txt"
    assert shown in open(saved.value.path()).read()
    card.get_by_role("button", name="Done").click()
    assert page.evaluate("window.__lf.recoveryCode()") == ""  # shown once

    # Later: this device knows one was saved, and can replace or remove it.
    card.get_by_role("button", name="Recovery code").click()
    expect(card).to_contain_text("You saved one on")
    card.get_by_role("button", name="Remove it").click()
    expect(card).to_contain_text("Removed: that code works no more.")
    expect(card.get_by_role("button", name="Make one")).to_be_visible()
    assert recovery.codes == {}
    assert page.evaluate("localStorage.getItem('letterfield.recovery.v1')") is None
    page.keyboard.press("Escape")
    expect(page.locator("html")).to_have_attribute("data-pair", "idle")
    assert errors == []


def test_entering_a_recovery_code_brings_the_surveyor_back(page: Page, site_url, errors):
    theirs = words(page, site_url, 1)
    players = FakePlayers(started=[THEIR_PID])
    settings = {"initials": "ZED", "guild": OTHER, "muted": [KIM[0]], "listed": True, "emotes": True}
    players.add(THEIR_PID, finds=theirs, settings=settings, settings_at=5)
    links = FakeLinks(players=players)
    recovery = FakeRecovery(players, {CODE: THEIRS})
    start(page, site_url, links, recovery=recovery, initials="QQQ", viewport={"width": 375, "height": 740})
    open_notes(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="Use a code").click()
    box = page.locator("#pairInput")
    box.press_sequentially("bcdfghjkmnpqrstvwxyy")  # one wrong
    expect(box).to_have_value("BCDF-GHJK-MNPQ-RSTV-WXYY")
    page.keyboard.press("Enter")
    expect(card.locator(".pair-err")).to_contain_text("That isn’t a recovery code we know")
    box.fill(CODE.lower())
    sizes = page.evaluate(
        "[document.scrollingElement.scrollWidth, document.getElementById('notes').scrollWidth, document.getElementById('notes').clientWidth]"
    )
    assert sizes[0] <= 375 and sizes[1] <= sizes[2], sizes
    card.get_by_role("button", name="Link", exact=True).click()
    page.wait_for_function(f"window.__lf && window.__lf.pid() === '{THEIR_PID}'", timeout=10_000)
    expect(page.locator("#toast b")).to_have_text("Welcome back")
    # What they had comes back with the first sync: initials, guild, mutes and notes.
    expect(page.locator("#surveyMeName")).to_have_text("ZED", timeout=8000)
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert page.evaluate("window.__lf.muted()") == [KIM[0]]
    assert noted(page) == [theirs[0]["w"]]
    assert json.loads(page.evaluate("localStorage.getItem('letterfield.sync.v1')"))["on"] is True
    assert page.evaluate("localStorage.getItem('letterfield.recovery.v1')") is not None
    assert errors == [] or all("404" in e for e in errors)


def test_the_code_fits_a_phone_on_one_line(page: Page, site_url, errors):
    for width in (375, 320):
        links = FakeLinks()
        start(page, site_url, links, recovery=FakeRecovery(links.players), viewport={"width": width, "height": 740})
        open_notes(page)
        card = page.locator("#pairCard")
        card.get_by_role("button", name="Recovery code").click()
        card.get_by_role(
            "button", name=re.compile(r"^Make (one|a new one)$")
        ).click()  # the second time, it knows the first
        code = card.locator("#recoveryCode")
        expect(code).to_be_visible()
        sizes = page.evaluate(
            "[document.scrollingElement.scrollWidth, document.getElementById('notes').scrollWidth,"
            " document.getElementById('notes').clientWidth]"
        )
        assert sizes[0] <= width and sizes[1] <= sizes[2], (width, sizes)
        fit = code.evaluate(
            """e => { const r = document.createRange(); r.selectNodeContents(e);
          const t = r.getBoundingClientRect(), b = e.getBoundingClientRect();
          return { lines: r.getClientRects().length, inside: t.left >= b.left && t.right <= b.right }; }"""
        )
        assert fit == {"lines": 1, "inside": True}, (width, fit)
    assert errors == []
