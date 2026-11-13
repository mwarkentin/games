"""Letterfield's linking of another device, against the survey's fakes.

A device that's already you shows a one-time code (as a QR code, a link and
eight characters); another redeems it, from the link (?link=<code>) or by
typing it, and reloads as the same surveyor. tests/fake_survey.py's FakeLinks
answers the Worker's link paths; the real ones are tested in
worker/test/players.test.js.
"""

from __future__ import annotations

import json
import re

from playwright.sync_api import Page, expect

from fake_survey import FakeGuilds, FakeLinks, FakeRecovery, FakeSurvey, player_id
from test_letterfield_guilds import CODE, MINE, NAME, TAG, in_cobalt
from test_letterfield_guilds import start as start_guilds
from test_letterfield_survey import SURVEY, open_notes
from test_letterfield_surveyors import KIM, LOU, PID, TOKEN

THEIRS = "f" * 32  # the other device's token
THEIR_PID = player_id(THEIRS)
OTHER = {"code": "PQRS23", "name": [3, 4, 5], "tag": "0badf00d"}  # a guild of theirs


def start(
    page: Page,
    site_url: str,
    links: FakeLinks,
    guilds: FakeGuilds | None = None,
    recovery: FakeRecovery | None = None,
    **kw,
) -> None:
    """Opens the game on the survey with our token, `links` answering the link paths, its
    `players` keeping linked devices in step, and `recovery` (or none) the recovery codes'."""
    page.route(f"{SURVEY}/v1/link**", links.handle)
    page.route(f"{SURVEY}/v1/player/**", links.players.handle)
    page.route(f"{SURVEY}/v1/recovery**", (recovery or FakeRecovery(links.players)).handle)
    start_guilds(page, site_url, FakeSurvey(), guilds or FakeGuilds(), **kw)


def stored(page: Page) -> dict:
    return page.evaluate("""() => Object.fromEntries(['games.player', 'games.initials', 'letterfield.guild.v1',
      'letterfield.muted.v1', 'letterfield.listed.v1', 'letterfield.emotes.v1'].map(k => [k, localStorage.getItem(k)]))""")


def linked(page: Page) -> None:
    """Waits for the reload that follows a link, as the other device's surveyor."""
    page.wait_for_function(f"window.__lf && window.__lf.pid() === '{THEIR_PID}'", timeout=10_000)


def test_a_code_shows_as_a_qr_code_and_a_link_and_hears_when_its_used(page: Page, site_url, errors):
    links = FakeLinks()
    start(page, site_url, links, in_cobalt(), guild=MINE)
    page.evaluate(f"localStorage.setItem('letterfield.muted.v1', JSON.stringify(['{LOU[0]}']))")
    page.reload()
    page.wait_for_function(f"window.__lf.pid() === '{PID}'")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    open_notes(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="Link another device").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "showing")
    code = page.evaluate("window.__lf.pairCode()")
    expect(card.locator(".pair-code")).to_have_text(f"{code[:4]}-{code[4:]}")
    expect(card.locator(".pair-left")).to_have_text("Good for 10 more minutes, once")
    # It carries who we are and what we've set, and nothing else.
    path, body = links.calls[0]
    assert (path, body["token"]) == ("", TOKEN)
    assert body["carry"] == {"initials": "MLW", "guild": MINE, "muted": [LOU[0]], "listed": True, "emotes": True}
    qr = card.locator(".pair-qr svg")
    expect(qr).to_be_visible()
    assert qr.bounding_box()["width"] >= 150
    card.get_by_role("button", name="Copy link").click()
    expect(card.locator("#pairSaid")).to_contain_text("Link copied")
    assert (
        page.evaluate("navigator.clipboard.readText()")
        == f"{site_url}/letterfield?survey={SURVEY.replace(':', '%3A').replace('/', '%2F')}&link={code}"
    )
    # The other device redeems it; this one hears so on its next ask.
    links.use(code)
    expect(page.locator("html")).to_have_attribute("data-pair", "used", timeout=10_000)
    expect(card).to_contain_text("Linked. Your other device plays as MLW now.")
    card.get_by_role("button", name="Done").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "idle")
    asked = len(links.calls)
    page.wait_for_timeout(6000)
    assert len(links.calls) == asked  # and stops asking
    assert errors == []


def test_a_code_that_runs_out_can_be_made_again(page: Page, site_url, errors):
    links = FakeLinks()
    start(page, site_url, links)
    open_notes(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="Link another device").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "showing")
    first = page.evaluate("window.__lf.pairCode()")
    links.expire(first)
    expect(card).to_contain_text("That code has run out.", timeout=10_000)
    expect(card.locator(".pair-qr")).to_have_count(0)
    card.get_by_role("button", name="New code").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "showing")
    expect(card.locator(".pair-code")).not_to_have_text(f"{first[:4]}-{first[4:]}")
    # Escape puts it away.
    card.get_by_role("button", name="Done").focus()
    page.keyboard.press("Escape")
    expect(page.locator("html")).to_have_attribute("data-pair", "idle")
    assert errors == []


def test_a_link_from_another_device_offers_first_then_becomes_that_surveyor(page: Page, site_url, errors):
    carry = {"initials": "MLW", "guild": OTHER, "muted": [KIM[0]], "listed": False, "emotes": True}
    links = FakeLinks({"CDEFGHJK": {"token": THEIRS, "carry": carry}})
    start(page, site_url, links, query="&link=cdef-ghjk", initials="")
    offer = page.locator("#pairOffer")
    expect(offer).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-intro", "link")
    expect(page.locator("#signup")).to_be_hidden()  # one card at a time: the link first
    assert "link=" not in page.url  # read once, then off the address
    offer.get_by_role("button", name="Link", exact=True).click()
    linked(page)
    assert stored(page) == {
        "games.player": THEIRS,
        "games.initials": '"MLW"',
        "letterfield.guild.v1": json.dumps(OTHER, separators=(",", ":")),
        "letterfield.muted.v1": json.dumps([KIM[0]], separators=(",", ":")),
        "letterfield.listed.v1": "0",
        "letterfield.emotes.v1": "1",
    }
    expect(page.locator("#toast b")).to_have_text("Linked")
    expect(page.locator("#toast span")).to_have_text("This device plays as MLW now, as your other one does")
    expect(page.locator("html")).to_have_attribute("data-intro", "exploring")  # signed, by the link
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert errors == []


def test_not_now_goes_on_to_the_initials_card_and_a_spent_link_says_so(page: Page, site_url, errors):
    links = FakeLinks({"CDEFGHJK": {"token": THEIRS, "carry": {}, "state": "used"}})
    start(page, site_url, links, query="&link=CDEFGHJK", initials="")
    offer = page.locator("#pairOffer")
    offer.get_by_role("button", name="Link", exact=True).click()
    expect(offer).to_contain_text("That code has been used or has run out")
    expect(page.locator("html")).to_have_attribute("data-pair", "failed")
    expect(offer.get_by_role("button", name="Try again")).to_have_count(0)  # it won't come good
    offer.get_by_role("button", name="Close").click()
    expect(offer).to_be_hidden()
    expect(page.locator("#signup")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-pair", "idle")
    assert page.evaluate("localStorage.getItem('games.player')") == TOKEN
    assert errors == [] or all("404" in e for e in errors)


def test_this_devices_guild_comes_along_when_theirs_is_none(page: Page, site_url, errors):
    links = FakeLinks({"CDEFGHJK": {"token": THEIRS, "carry": {"initials": "MLW", "guild": None}}})
    guilds = in_cobalt()
    start(page, site_url, links, guilds, query="&link=CDEFGHJK", guild=MINE)
    offer = page.locator("#pairOffer")
    expect(offer).to_contain_text("If they’re in a guild, this device leaves the Cobalt Compass Society.")
    offer.get_by_role("button", name="Link", exact=True).click()
    linked(page)
    assert json.loads(stored(page)["letterfield.guild.v1"]) == MINE
    joins = [(p, b["token"]) for _, p, b in guilds.calls if p.endswith(("/join", "/leave"))]
    assert joins == [(f"/{CODE}/join", THEIRS), (f"/{CODE}/leave", TOKEN)]
    assert [m[0] for m in guilds.guilds[CODE]["members"]] == [THEIR_PID]
    assert (NAME, TAG) == (guilds.guilds[CODE]["name"], guilds.guilds[CODE]["tag"])
    assert errors == []


def test_typing_a_code_links_and_a_bad_one_says_so(page: Page, site_url, errors):
    links = FakeLinks({"CDEFGHJK": {"token": THEIRS, "carry": {"initials": "ZED"}}})
    start(page, site_url, links, viewport={"width": 375, "height": 740})
    open_notes(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="Use a code").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "entering")
    box = page.locator("#pairInput")
    expect(box).to_be_focused()
    assert page.evaluate("getComputedStyle(document.getElementById('pairInput')).fontSize") == "16px"
    box.press_sequentially("abcd")
    page.keyboard.press("Enter")
    expect(card.locator(".pair-err")).to_have_text(
        "A code is eight letters and digits, like ABCD-EFGH, or twenty for a recovery code."
    )
    box.press_sequentially("efgh")
    expect(box).to_have_value("ABCD-EFGH")
    page.keyboard.press("Enter")
    expect(card.locator(".pair-err")).to_contain_text("That code has been used or has run out")
    expect(page.locator("html")).to_have_attribute("data-pair", "entering")
    expect(box).to_be_focused()
    box.fill("cdef ghjk")
    sizes = page.evaluate("""() => ({ page: document.scrollingElement.scrollWidth,
      notes: [document.getElementById('notes').scrollWidth, document.getElementById('notes').clientWidth] })""")
    assert sizes["page"] <= 375 and sizes["notes"][0] <= sizes["notes"][1], sizes
    card.get_by_role("button", name="Link", exact=True).click()
    linked(page)
    assert stored(page)["games.initials"] == '"ZED"'
    assert [p for p, _ in links.calls] == ["/ABCDEFGH", "/CDEFGHJK"]
    assert errors == [] or all("404" in e for e in errors)


def test_the_code_fits_a_phone(page: Page, site_url, errors):
    start(page, site_url, FakeLinks(), viewport={"width": 375, "height": 740})
    open_notes(page)
    page.locator("#pairCard").get_by_role("button", name="Link another device").click()
    expect(page.locator(".pair-qr svg")).to_be_visible()
    sizes = page.evaluate("""() => ({ page: document.scrollingElement.scrollWidth,
      notes: [document.getElementById('notes').scrollWidth, document.getElementById('notes').clientWidth] })""")
    assert sizes["page"] <= 375 and sizes["notes"][0] <= sizes["notes"][1], sizes
    expect(page.locator("#pairCard")).to_contain_text(re.compile(r"[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}"))
    assert errors == []
