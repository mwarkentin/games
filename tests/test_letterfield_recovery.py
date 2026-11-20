"""Letterfield's recovery codes, against the survey's fakes.

A recovery code, saved by the player, brings their surveyor back on any
device with no other to hand: entered under "I have a code", like a link code.
tests/fake_survey.py's FakeRecovery answers the Worker's recovery paths; the
real ones are tested in worker/test/players.test.js.
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Page, Route, expect

from fake_survey import NOW_MS, FakeLinks, FakePlayers, FakeRecovery, player_id, reply
from test_letterfield_guilds import CODE as COBALT
from test_letterfield_guilds import MINE, in_cobalt
from test_letterfield_linking import OTHER, THEIR_PID, THEIRS, start
from test_letterfield_survey import SURVEY, open_you
from test_letterfield_surveyors import KIM, TOKEN
from test_letterfield_sync import noted, words

CODE = "BCDFGHJKMNPQRSTVWXYZ"  # a code saved earlier, for THEIRS


def test_a_recovery_code_is_shown_once_and_keeps_a_backup(page: Page, site_url, errors):
    links = FakeLinks()
    recovery = FakeRecovery(links.players)
    start(page, site_url, links, recovery=recovery)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    open_you(page)
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


def test_a_retry_that_works_leaves_no_old_error(page: Page, site_url, errors):
    """A failure's words were cleared only on the way back to idle or to making a link code, so a
    removal that failed and then worked said both that it was removed and that the survey was down."""
    links = FakeLinks()
    recovery = FakeRecovery(links.players)
    start(page, site_url, links, recovery=recovery)
    tries = []

    def remove(route: Route) -> None:
        tries.append(route.request.url)
        if len(tries) == 1:
            return reply(route, {"error": "down"}, 503)
        recovery.handle(route)

    page.route(f"{SURVEY}/v1/recovery/remove", remove)
    open_you(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="Recovery code").click()
    card.get_by_role("button", name="Make one").click()
    card.get_by_role("button", name="Done").click()
    card.get_by_role("button", name="Recovery code").click()
    card.get_by_role("button", name="Remove it").click()
    expect(card.locator(".pair-err")).to_contain_text("Couldn’t reach the survey")
    card.get_by_role("button", name="Remove it").click()
    expect(card).to_contain_text("Removed: that code works no more.")
    expect(card.locator(".pair-err")).to_have_count(0)
    assert len(tries) == 2 and recovery.codes == {}
    assert errors == [] or all("503" in e for e in errors)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_devices_cards_buttons_follow_one_rule(page: Page, site_url, errors, scheme):
    page.emulate_media(color_scheme=scheme)
    links = FakeLinks()
    start(page, site_url, links)
    open_you(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="Recovery code").click()
    card.get_by_role("button", name="Make one").click()
    card.get_by_role("button", name="Done").click()
    card.get_by_role("button", name="Recovery code").click()
    # Its heading is an eyebrow, 10px, whatever size the card's paragraphs are.
    expect(card.locator(".eyebrow")).to_have_css("font-size", "10px")
    # Filled for the main choice, red for the one that deletes, outlined for the rest, all 40px tall.
    buttons = [card.get_by_role("button", name=n) for n in ("Make a new one", "Remove it", "Close")]
    for b, kind in zip(buttons, ("btn", "btn danger", "btn ghost"), strict=True):
        expect(b).to_have_class(kind)
        assert b.bounding_box()["height"] >= 40
    # Red's text is white on the light theme's red, and dark on the dark theme's coral.
    light = scheme == "light"
    expect(buttons[1]).to_have_css("color", "rgb(255, 255, 255)" if light else "rgb(42, 15, 10)")
    # A text input is white in the light theme, so it reads as a field to type in.
    buttons[2].click()
    card.get_by_role("button", name="I have a code").click()
    box = page.locator("#pairInput")
    expect(box).to_have_css("background-color", "rgb(255, 255, 255)" if light else "rgb(15, 23, 26)")
    assert box.bounding_box()["height"] >= 40
    expect(card.get_by_role("button", name="Cancel")).to_have_class("btn ghost")
    assert errors == []


def test_entering_a_recovery_code_brings_the_surveyor_back(page: Page, site_url, errors):
    theirs = words(page, site_url, 1)
    players = FakePlayers(started=[THEIR_PID])
    settings = {"initials": "ZED", "guild": OTHER, "muted": [KIM[0]], "mutedAs": {}, "emotes": True}
    players.add(THEIR_PID, finds=theirs, settings=settings, settings_at=5)
    links = FakeLinks(players=players)
    recovery = FakeRecovery(players, {CODE: THEIRS})
    start(page, site_url, links, recovery=recovery, initials="QQQ", viewport={"width": 375, "height": 740})
    open_you(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="I have a code").click()
    box = page.locator("#pairInput")
    box.press_sequentially("bcdfghjkmnpqrstvwxyy")  # one wrong
    expect(box).to_have_value("BCDF-GHJK-MNPQ-RSTV-WXYY")
    page.keyboard.press("Enter")
    expect(card.locator(".pair-err")).to_contain_text("That isn’t a recovery code we know")
    box.fill(CODE.lower())
    sizes = page.evaluate(
        "[document.scrollingElement.scrollWidth, document.getElementById('people').scrollWidth, document.getElementById('people').clientWidth]"
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


def test_a_change_made_before_the_backup_comes_doesnt_replace_it(page: Page, site_url, errors):
    """A setting changed after entering the code, before the first sync had brought the backup (one
    that failed, here), counted as newer than the backup, which was then lost for good."""
    players = FakePlayers(started=[THEIR_PID])
    settings = {"initials": "ZED", "guild": OTHER, "muted": [KIM[0]], "mutedAs": {}, "emotes": True}
    players.add(THEIR_PID, settings=settings, settings_at=5)
    links = FakeLinks(players=players)
    recovery = FakeRecovery(players, {CODE: THEIRS})
    start(page, site_url, links, recovery=recovery, initials="QQQ")
    failed = []

    def flaky(route: Route) -> None:
        if route.request.url.endswith("/sync") and not failed:
            failed.append(1)
            return reply(route, {"error": "down"}, 503)
        players.handle(route)

    page.route(f"{SURVEY}/v1/player/**", flaky)
    open_you(page)
    page.locator("#pairCard").get_by_role("button", name="I have a code").click()
    page.locator("#pairInput").fill(CODE.lower())
    page.keyboard.press("Enter")
    page.wait_for_function(f"window.__lf && window.__lf.pid() === '{THEIR_PID}'", timeout=10_000)
    expect(page.locator("html")).to_have_attribute("data-sync", "failed", timeout=8000)
    page.locator("#whoEmotes").evaluate("e => e.click()")  # a change here, before the backup has come
    page.evaluate("window.__lf.syncNow()")
    expect(page.locator("#surveyMeName")).to_have_text("ZED", timeout=8000)
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert page.evaluate("window.__lf.muted()") == [KIM[0]]
    page.wait_for_timeout(2500)
    assert players.players[THEIR_PID]["settings"]["initials"] == "ZED"
    assert players.players[THEIR_PID]["settings"]["guild"] == OTHER
    assert errors == [] or all("503" in e or "404" in e for e in errors)


def test_a_device_brought_back_keeps_its_guilds_beside_the_backups(page: Page, site_url, errors):
    players = FakePlayers(started=[THEIR_PID])
    settings = {
        "initials": "ZED",
        "guilds": [OTHER],
        "guild": OTHER,
        "labels": {OTHER["code"]: "Climbing"},
        "muted": [],
        "mutedAs": {},
        "emotes": True,
    }
    players.add(THEIR_PID, settings=settings, settings_at=5)
    links = FakeLinks(players=players)
    recovery = FakeRecovery(players, {CODE: THEIRS})
    guilds = in_cobalt()
    guilds.guilds[OTHER["code"]] = {"name": OTHER["name"], "tag": OTHER["tag"], "members": [[THEIR_PID, "ZED", NOW_MS]]}
    start(page, site_url, links, guilds, recovery=recovery, initials="QQQ", mine=[MINE], labels={COBALT: "Family"})
    open_you(page)
    page.locator("#pairCard").get_by_role("button", name="I have a code").click()
    page.locator("#pairInput").fill(CODE.lower())
    page.keyboard.press("Enter")
    page.wait_for_function(f"window.__lf && window.__lf.pid() === '{THEIR_PID}'", timeout=10_000)
    # This device's guild is joined as the surveyor it's become, and its old self leaves...
    assert [(p, b["token"]) for _, p, b in guilds.calls if p.endswith(("/join", "/leave"))] == [
        (f"/{COBALT}/join", THEIRS),
        (f"/{COBALT}/leave", TOKEN),
    ]
    # ...and once the backup's settings come, it goes beside theirs, and the whole list goes back up.
    expect(page.locator("#surveyMeName")).to_have_text("ZED", timeout=8000)
    page.wait_for_function(
        f"JSON.parse(localStorage.getItem('letterfield.guilds.v1')).map(g => g.code).join() === '{OTHER['code']},{COBALT}'"
    )
    assert page.evaluate("localStorage.getItem('letterfield.guild-merge.v1')") is None
    page.wait_for_function("window.__lf.sync() === 'idle'")
    page.evaluate("window.__lf.syncNow()")
    page.wait_for_function("window.__lf.sync() === 'idle'")
    assert [g["code"] for g in players.players[THEIR_PID]["settings"]["guilds"]] == [OTHER["code"], COBALT]
    # The backup's labels, and this device's for the guild it brought.
    assert players.players[THEIR_PID]["settings"]["labels"] == {OTHER["code"]: "Climbing", COBALT: "Family"}
    assert errors == [] or all("404" in e for e in errors)


def test_the_code_fits_a_phone_on_one_line(page: Page, site_url, errors):
    for width in (375, 320):
        links = FakeLinks()
        start(page, site_url, links, viewport={"width": width, "height": 740})
        open_you(page)
        card = page.locator("#pairCard")
        card.get_by_role("button", name="Recovery code").click()
        card.get_by_role(
            "button", name=re.compile(r"^Make (one|a new one)$")
        ).click()  # the second time, it knows the first
        code = card.locator("#recoveryCode")
        expect(code).to_be_visible()
        sizes = page.evaluate(
            "[document.scrollingElement.scrollWidth, document.getElementById('people').scrollWidth,"
            " document.getElementById('people').clientWidth]"
        )
        assert sizes[0] <= width and sizes[1] <= sizes[2], (width, sizes)
        fit = code.evaluate(
            """e => { const r = document.createRange(); r.selectNodeContents(e);
          const t = r.getBoundingClientRect(), b = e.getBoundingClientRect();
          return { lines: r.getClientRects().length, inside: t.left >= b.left && t.right <= b.right }; }"""
        )
        assert fit == {"lines": 1, "inside": True}, (width, fit)
    assert errors == []
