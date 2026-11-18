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

import pytest
from playwright.sync_api import Page, expect

from fake_survey import NOW_MS, FakeGuilds, FakeLinks, FakeRecovery, FakeSurvey, player_id
from test_letterfield_guilds import CODE, FIVE, MINE, NAME, TAG, in_cobalt
from test_letterfield_guilds import start as start_guilds
from test_letterfield_survey import OVERLAP, SURVEY, circle, eventually, known_words, open_you
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
    survey: FakeSurvey | None = None,
    **kw,
) -> None:
    """Opens the game on `survey` (an empty one by default) with our token, `links` answering the
    link paths, its `players` keeping linked devices in step, and `recovery` (or none) the recovery codes'."""
    page.route(f"{SURVEY}/v1/link**", links.handle)
    page.route(f"{SURVEY}/v1/player/**", links.players.handle)
    page.route(f"{SURVEY}/v1/recovery**", (recovery or FakeRecovery(links.players)).handle)
    start_guilds(page, site_url, survey or FakeSurvey(), guilds or FakeGuilds(), **kw)


def stored(page: Page) -> dict:
    return page.evaluate("""() => Object.fromEntries(['games.player', 'games.initials', 'letterfield.guild.v1',
      'letterfield.muted.v1', 'letterfield.mutedAs.v1', 'letterfield.emotes.v1'].map(k => [k, localStorage.getItem(k)]))""")


def linked(page: Page) -> None:
    """Waits for the reload that follows a link, as the other device's surveyor."""
    page.wait_for_function(f"window.__lf && window.__lf.pid() === '{THEIR_PID}'", timeout=10_000)


def test_a_code_shows_as_a_qr_code_and_a_link_and_hears_when_its_used(page: Page, site_url, errors):
    links = FakeLinks()
    start(page, site_url, links, in_cobalt(), guild=MINE)
    page.evaluate(f"localStorage.setItem('letterfield.muted.v1', JSON.stringify(['{LOU[0]}']))")
    page.evaluate(f"localStorage.setItem('letterfield.mutedAs.v1', JSON.stringify({{'{LOU[0]}': ['LOU', 5]}}))")
    page.reload()
    page.wait_for_function(f"window.__lf.pid() === '{PID}'")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    open_you(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="Link another device").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "showing")
    code = page.evaluate("window.__lf.pairCode()")
    expect(card.locator(".pair-code")).to_have_text(f"{code[:4]}-{code[4:]}")
    expect(card.locator(".pair-left")).to_have_text("Good for 10 more minutes, once")
    # It carries who we are and what we've set, and nothing else.
    path, body = links.calls[0]
    assert (path, body["token"]) == ("", TOKEN)
    assert body["carry"] == {
        "initials": "MLW",
        "guilds": [MINE],
        "guild": MINE,  # the first, for an older game on the other device
        "labels": {},
        "muted": [LOU[0]],
        "mutedAs": {LOU[0]: ["LOU", 5]},
        "emotes": True,
        "badge": None,  # the badge shown to others (see test_letterfield_achievements.py)
    }
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
    open_you(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="Link another device").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "showing")
    first = page.evaluate("window.__lf.pairCode()")
    # Another of this surveyor's devices makes a code, which retires this one well before its time.
    links.expire(first)
    expect(card).to_contain_text("A newer code replaced it.", timeout=10_000)
    expect(page.locator("html")).to_have_attribute("data-pair-code", "gone")
    expect(card.locator(".pair-qr")).to_have_count(0)
    card.get_by_role("button", name="New code").click()
    expect(page.locator("html")).to_have_attribute("data-pair", "showing")
    expect(page.locator("html")).to_have_attribute("data-pair-code", "waiting")
    expect(card.locator(".pair-code")).not_to_have_text(f"{first[:4]}-{first[4:]}")
    # Its ten minutes go by: it has run out.
    page.evaluate("() => { const real = Date.now; Date.now = () => real() + 11 * 60000; }")
    expect(card).to_contain_text("That code has run out.", timeout=10_000)
    card.get_by_role("button", name="New code").click()
    expect(page.locator("html")).to_have_attribute("data-pair-code", "waiting")
    # Escape puts it away.
    card.get_by_role("button", name="Done").focus()
    page.keyboard.press("Escape")
    expect(page.locator("html")).to_have_attribute("data-pair", "idle")
    assert errors == []


def test_done_leaves_the_code_watched_until_its_used_even_across_a_reload(page: Page, site_url, errors):
    """Done used to stop asking about a code that still worked, so a device that used it later
    linked and synced while this one never did, and never said so."""
    links = FakeLinks()
    start(page, site_url, links)
    open_you(page)
    html, card = page.locator("html"), page.locator("#pairCard")
    card.get_by_role("button", name="Link another device").click()
    expect(card.locator(".pair-code")).to_be_visible()
    code = page.evaluate("window.__lf.pairCode()")
    card.get_by_role("button", name="Done").click()
    # The page is reloaded, and the other device uses the code much later.
    page.reload()
    page.wait_for_function(f"window.__lf && window.__lf.pid() === '{PID}'")
    links.use(code)
    expect(page.locator("#toast b")).to_have_text("Linked", timeout=10_000)
    expect(page.locator("#toast span")).to_have_text("Your other device plays as MLW now")
    expect(html).not_to_have_attribute("data-sync", "off")  # this device keeps in step too
    expect(html).to_have_attribute("data-pair-code", "used")
    assert page.evaluate("localStorage.getItem('letterfield.linkCode.v1')") is None

    # A code still waiting, opened again, shows again, rather than being retired for a new one.
    open_you(page)
    card.get_by_role("button", name="Link another device").click()
    expect(card.locator(".pair-code")).to_be_visible()
    second = page.evaluate("window.__lf.pairCode()")
    card.get_by_role("button", name="Done").click()
    expect(html).to_have_attribute("data-pair-code", "waiting")
    card.get_by_role("button", name="Link another device").click()
    expect(card.locator(".pair-code")).to_have_text(f"{second[:4]}-{second[4:]}")
    assert links.made == 2
    assert errors == []


def test_a_link_from_another_device_offers_first_then_becomes_that_surveyor(page: Page, site_url, errors):
    carry = {"initials": "MLW", "guild": OTHER, "muted": [KIM[0]], "mutedAs": {KIM[0]: ["KIM", 7]}, "emotes": True}
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
        "letterfield.mutedAs.v1": json.dumps({KIM[0]: ["KIM", 7]}, separators=(",", ":")),
        "letterfield.emotes.v1": "1",
    }
    expect(page.locator("#toast b")).to_have_text("Linked")
    expect(page.locator("#toast span")).to_have_text("This device plays as MLW now, as your other one does")
    expect(page.locator("html")).to_have_attribute("data-intro", "exploring")  # signed, by the link
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert errors == []


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_a_note_never_covers_the_offer_to_link(page: Page, site_url, errors, size):
    """A note moved down below the title, the intro and the box for your initials, but not below the
    offer to link this device, which sits in their place: on a phone it landed on top of it."""
    words = known_words(page, site_url)
    links = FakeLinks({"CDEFGHJK": {"token": THEIRS, "carry": {}}})
    survey = FakeSurvey(claims=[[*words[0], 0, "MRW", NOW_MS - 60_000]])
    viewport = {"width": size[0], "height": size[1]}
    start(page, site_url, links, survey=survey, query="&link=CDEFGHJK", initials="", viewport=viewport)
    offer = page.locator("#pairOffer")
    expect(offer).to_be_visible()
    circle(page, words[0])  # charted by someone else, so a note says so
    toast = page.locator("#toast")
    expect(toast).to_have_class(re.compile(r"\bshow\b"))
    toast.evaluate("e => Promise.all(e.getAnimations().map(a => a.finished))")  # its slide in
    assert not page.evaluate(OVERLAP, ["#toast", "#pairOffer"]), (toast.bounding_box(), offer.bounding_box())
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


def test_this_devices_guilds_join_theirs_with_labels_from_both(page: Page, site_url, errors):
    carry = {
        "initials": "MLW",
        "guilds": [OTHER],
        "guild": OTHER,
        "labels": {OTHER["code"]: "Climbing", CODE: "Not this"},
    }
    links = FakeLinks({"CDEFGHJK": {"token": THEIRS, "carry": carry}})
    guilds = in_cobalt()
    guilds.guilds[OTHER["code"]] = {"name": OTHER["name"], "tag": OTHER["tag"], "members": [[THEIR_PID, "MLW", NOW_MS]]}
    start(page, site_url, links, guilds, query="&link=CDEFGHJK", mine=[MINE], labels={CODE: "Family"})
    offer = page.locator("#pairOffer")
    expect(offer).to_contain_text("The Cobalt Compass Society comes along too, up to 5 guilds in all.")
    offer.get_by_role("button", name="Link", exact=True).click()
    linked(page)
    # Theirs first, then this device's, joined as that surveyor; this device's old self leaves.
    assert [g["code"] for g in json.loads(page.evaluate("localStorage.getItem('letterfield.guilds.v1')"))] == [
        OTHER["code"],
        CODE,
    ]
    joins = [(p, b["token"]) for _, p, b in guilds.calls if p.endswith(("/join", "/leave"))]
    assert joins == [(f"/{CODE}/join", THEIRS), (f"/{CODE}/leave", TOKEN)]
    assert [m[0] for m in guilds.guilds[CODE]["members"]] == [THEIR_PID]
    assert (NAME, TAG) == (guilds.guilds[CODE]["name"], guilds.guilds[CODE]["tag"])
    # A label they had wins; one only this device had stays.
    assert json.loads(page.evaluate("localStorage.getItem('letterfield.guild-labels.v1')")) == {
        OTHER["code"]: "Climbing",
        CODE: "Not this",
    }
    assert errors == []


def test_linking_to_a_surveyor_in_five_guilds_leaves_this_devices_one_out(page: Page, site_url, errors):
    theirs = [g for g in FIVE if g["code"] != CODE] + [OTHER]
    links = FakeLinks({"CDEFGHJK": {"token": THEIRS, "carry": {"initials": "MLW", "guilds": theirs}}})
    guilds = in_cobalt()
    start(page, site_url, links, guilds, query="&link=CDEFGHJK", mine=[MINE])
    page.locator("#pairOffer").get_by_role("button", name="Link", exact=True).click()
    linked(page)
    assert [g["code"] for g in json.loads(page.evaluate("localStorage.getItem('letterfield.guilds.v1')"))] == [
        g["code"] for g in theirs
    ]
    # No room for this device's: its old self still leaves, so nothing joins.
    assert [(p, b["token"]) for _, p, b in guilds.calls if p.endswith(("/join", "/leave"))] == [
        (f"/{CODE}/leave", TOKEN)
    ]
    assert errors == []


def test_typing_a_code_links_and_a_bad_one_says_so(page: Page, site_url, errors):
    links = FakeLinks({"CDEFGHJK": {"token": THEIRS, "carry": {"initials": "ZED"}}})
    start(page, site_url, links, viewport={"width": 375, "height": 740})
    open_you(page)
    card = page.locator("#pairCard")
    card.get_by_role("button", name="I have a code").click()
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
      notes: [document.getElementById('people').scrollWidth, document.getElementById('people').clientWidth] })""")
    assert sizes["page"] <= 375 and sizes["notes"][0] <= sizes["notes"][1], sizes
    card.get_by_role("button", name="Link", exact=True).click()
    linked(page)
    assert stored(page)["games.initials"] == '"ZED"'
    assert [p for p, _ in links.calls] == ["/ABCDEFGH", "/CDEFGHJK"]
    assert errors == [] or all("404" in e for e in errors)


def test_the_code_fits_a_phone(page: Page, site_url, errors):
    start(page, site_url, FakeLinks(), viewport={"width": 375, "height": 740})
    open_you(page)
    page.locator("#pairCard").get_by_role("button", name="Link another device").click()
    expect(page.locator(".pair-qr svg")).to_be_visible()
    sizes = page.evaluate("""() => ({ page: document.scrollingElement.scrollWidth,
      notes: [document.getElementById('people').scrollWidth, document.getElementById('people').clientWidth] })""")
    assert sizes["page"] <= 375 and sizes["notes"][0] <= sizes["notes"][1], sizes
    expect(page.locator("#pairCard")).to_contain_text(re.compile(r"[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}"))
    assert errors == []


def test_the_code_stays_put_while_it_asks_whether_its_been_used(page: Page, site_url, errors):
    """Each ask redrew the whole card, QR code and all, so the notes jumped back up as it did."""
    links = FakeLinks()
    start(page, site_url, links, viewport={"width": 375, "height": 740})
    open_you(page)
    page.locator("#pairCard").get_by_role("button", name="Link another device").click()
    expect(page.locator(".pair-qr svg")).to_be_visible()
    # Read down to the bottom of the card, as a player scanning it would.
    before = page.evaluate("""() => { const n = document.getElementById('people');
      n.scrollTop = n.scrollHeight; window.__qr = document.querySelector('.pair-qr svg'); return n.scrollTop; }""")
    assert before > 0
    asked = len(links.calls)
    eventually(page, lambda: len(links.calls) > asked, timeout_ms=8000)  # the next ask, five seconds on
    page.wait_for_timeout(300)
    assert page.evaluate("window.__qr.isConnected"), "the QR code was drawn again"
    assert page.evaluate("document.getElementById('people').scrollTop") == before
    assert errors == []
