"""Letterfield's guilds, against the survey's fakes.

A guild is started from the Surveyors fold or joined from an invite link
(?guild=<code>); tests/fake_survey.py's FakeGuilds answers the Worker's guild
paths, and FakeSurvey.guild() says which mates are online. The real Guild
object is tested in worker/test/survey-guild.test.js.
"""

from __future__ import annotations

import json
import re
import time

from playwright.sync_api import Page, expect

from fake_survey import NOW_MS, FakeGuilds, FakeSurvey, player_id
from test_letterfield_survey import SURVEY, eventually, open_game, open_people, open_you
from test_letterfield_surveyors import KIM, LOU, PID, TOKEN, ZED, open_list, wait_landed

CODE, TAG, NAME = "KMN234", "c0ffee42", [11, 0, 0]  # the Cobalt Compass Society
SHOWN = re.compile(r"\bshow\b")


def start(
    page: Page,
    site_url: str,
    fake: FakeSurvey,
    guilds: FakeGuilds,
    query: str = "",
    initials: str = "MLW",
    guild: dict | None = None,
    viewport: dict | None = None,
) -> None:
    """Opens the game on the survey with our token, signed as `initials` (none if empty), in `guild` if given."""
    page.route(f"{SURVEY}/v1/survey/guilds**", guilds.handle)
    open_game(page, site_url, fake, viewport=viewport)
    page.evaluate(
        """([t, ini, g]) => {
      localStorage.setItem('letterfield.coach.v1', '1'); localStorage.setItem('games.player', t); localStorage.removeItem('letterfield.cam.v1');
      if (ini) localStorage.setItem('games.initials', JSON.stringify(ini)); else localStorage.removeItem('games.initials');
      if (g) localStorage.setItem('letterfield.guild.v1', JSON.stringify(g)); else localStorage.removeItem('letterfield.guild.v1');
    }""",
        [TOKEN, initials, guild],
    )
    fake.received.clear()
    page.goto("about:blank")  # the same address again would only jump to its #debug, not load afresh
    page.goto(f"{site_url}/letterfield?survey={SURVEY}{query}#debug")
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    page.wait_for_function(f"window.__lf.pid() === '{PID}'")


def in_cobalt(*members) -> FakeGuilds:
    """A guild with us in it, and `members` ([id, initials, seen])."""
    return FakeGuilds({CODE: {"name": NAME, "tag": TAG, "members": [[PID, "MLW", NOW_MS], *members]}})


MINE = {"code": CODE, "name": NAME, "tag": TAG}


def test_starting_a_guild_names_it_from_the_lists_and_puts_you_in_it(page: Page, site_url, errors):
    fake, guilds = FakeSurvey(), FakeGuilds()
    start(page, site_url, fake, guilds)
    open_list(page)
    expect(page.locator(".who-guild")).to_have_count(0)  # no guild, no heading for one: starting one is on your page
    open_you(page)
    card = page.locator("#guildCard")
    expect(page.locator("html")).to_have_attribute("data-guild", "out")
    card.get_by_role("button", name="Start a guild").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "naming")
    name = card.locator(".guild-name")
    expect(name).to_have_text(re.compile(r"^\w+ \w+ \w+$"))
    first = name.text_content()
    card.get_by_role("button", name="Another name").click()
    expect(name).not_to_have_text(first)
    chosen = name.text_content()
    card.get_by_role("button", name="Start it").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    expect(card.locator(".guild-name")).to_have_text(chosen)
    expect(card.locator(".guild-meta")).to_have_text("1 member · 0 others online")
    method, path, body = next(c for c in guilds.calls if c[1] == "")
    assert (method, body["token"], body["initials"]) == ("POST", TOKEN, "MLW")
    words = page.evaluate("window.__lf.guildWords()")
    assert all(0 <= n < size for n, size in zip(body["name"], words, strict=True))
    saved = json.loads(page.evaluate("localStorage.getItem('letterfield.guild.v1')"))
    assert saved["code"] in guilds.guilds and saved["tag"] == guilds.guilds[saved["code"]]["tag"]
    # Every sector is told, so it can check and put the guild on our caret.
    eventually(
        page,
        lambda: (
            {m["sector"] for m in fake.sent("me") if m.get("guild") == saved["code"]}
            == {"-1,-1", "-1,0", "0,-1", "0,0"}
        ),
    )
    assert errors == []


def test_an_invite_link_asks_once_initials_are_in_then_joins(page: Page, site_url, errors):
    guilds = FakeGuilds({CODE: {"name": NAME, "tag": TAG, "members": [[KIM[0], "KIM", NOW_MS]]}})
    fake = FakeSurvey()
    start(page, site_url, fake, guilds, query=f"&guild={CODE.lower()}", initials="")
    invite = page.locator("#guildInvite")
    expect(page.locator("#signup")).to_be_visible()
    expect(invite).to_be_hidden()  # one card at a time: initials first
    assert "guild=" not in page.url  # read once, then off the address
    page.locator("#signupInitials").fill("MLW")
    page.locator("#signup button[type=submit]").click()
    expect(invite).to_be_visible()
    expect(invite.locator(".guild-name")).to_have_text("Cobalt Compass Society")
    expect(invite).to_contain_text("1 member so far")
    invite.get_by_role("button", name="Join").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    expect(invite).to_be_hidden()
    expect(page.locator("#toast b")).to_have_text("Cobalt Compass Society")
    assert any(path == f"/{CODE}/join" for _, path, _ in guilds.calls)
    assert json.loads(page.evaluate("localStorage.getItem('letterfield.guild.v1')")) == MINE
    assert errors == []


def test_an_invite_can_wait_or_be_no_good(page: Page, site_url, errors):
    guilds = FakeGuilds({CODE: {"name": NAME, "tag": TAG, "members": [[KIM[0], "KIM", NOW_MS]]}})
    start(page, site_url, FakeSurvey(), guilds, query=f"&guild={CODE}")
    invite = page.locator("#guildInvite")
    expect(invite).to_be_visible()
    invite.get_by_role("button", name="Not now").click()
    expect(invite).to_be_hidden()
    expect(page.locator("html")).to_have_attribute("data-guild", "out")
    assert all(path != f"/{CODE}/join" for _, path, _ in guilds.calls)

    page.goto(f"{site_url}/letterfield?survey={SURVEY}&guild=ZZZZZZ#debug")
    expect(invite).to_contain_text("That invite isn’t good any more")
    invite.get_by_role("button", name="Close").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "out")
    assert errors == [] or all("404" in e for e in errors)


def test_an_invite_while_in_another_guild_warns_before_switching(page: Page, site_url, errors):
    other, other_name = "QRT567", [3, 1, 2]
    guilds = in_cobalt()  # just us in it
    guilds.guilds[other] = {"name": other_name, "tag": "0ddba11a", "members": [[KIM[0], "KIM", NOW_MS]]}
    start(page, site_url, FakeSurvey(), guilds, query=f"&guild={other}", guild=MINE)
    invite = page.locator("#guildInvite")
    expect(invite).to_be_visible()
    # Both guilds by name, the one you're in first, and a warning that says what joining costs.
    expect(invite.locator(".eyebrow")).to_have_text("Switch guilds?")
    expect(invite.locator(".guild-name").first).to_have_text("Cobalt Compass Society")
    theirs = invite.locator("#guildInviteName").text_content()
    expect(invite.locator(".guild-warn")).to_contain_text(
        f"Joining the {theirs} takes you out of the Cobalt Compass Society, and you’d need a new invite to go back."
    )
    expect(invite.locator(".guild-warn")).to_contain_text("You’re its only member, so it ends when you leave.")
    expect(invite).to_contain_text("1 member so far")
    invite.get_by_role("button", name="Stay").click()
    expect(invite).to_be_hidden()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert json.loads(page.evaluate("localStorage.getItem('letterfield.guild.v1')")) == MINE
    assert all(path != f"/{other}/join" for _, path, _ in guilds.calls)

    page.goto("about:blank")
    page.goto(f"{site_url}/letterfield?survey={SURVEY}&guild={other}#debug")
    invite.get_by_role("button", name="Leave and join").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    expect(page.locator("#toast span")).to_have_text("You’re in, and out of the Cobalt Compass Society")
    eventually(page, lambda: any(path == f"/{CODE}/leave" for _, path, _ in guilds.calls))
    assert json.loads(page.evaluate("localStorage.getItem('letterfield.guild.v1')"))["code"] == other
    assert errors == []


def test_mates_come_first_with_when_the_rest_were_seen_and_a_note_when_one_comes_online(page: Page, site_url, errors):
    three_hours = int(time.time() * 1000) - 3 * 3_600_000 - 60_000
    guilds = in_cobalt([KIM[0], "KIM", NOW_MS], [ZED[0], "ZED", three_hours])
    fake = FakeSurvey(surveyors=[LOU, KIM], presence=[[KIM[0], "KIM", 9.5, 7.0, TAG]])
    start(page, site_url, fake, guilds, guild=MINE)
    open_list(page)
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    # The guild heads the list, by name, with who's online and a way to invite more.
    expect(page.locator(".who-head")).to_have_count(2)
    expect(page.locator(".who-guild .who-head-name")).to_have_text("Cobalt Compass Society")
    expect(page.locator(".who-guild .who-head-n")).to_have_text("1 online")
    expect(page.locator(".who-head").nth(1)).to_have_text("Everyone else")
    expect(page.locator(".who-ini")).to_have_text(["KIM", "ZED", "LOU"])
    expect(page.locator(".who-row.away .who-meta")).to_have_text("last seen 3h ago")
    # From the roster, on your page.
    expect(page.locator("#guildCard .guild-meta")).to_have_text("3 members · 1 other online")
    # A mate's caret wears the guild's colour, and its hover card names the guild.
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}')")
    at = page.evaluate(f"window.__lf.caretXY('{KIM[0]}')")
    page.mouse.move(at["x"], at["y"])
    expect(page.locator("#peek")).to_contain_text("Cobalt Compass Society")

    # Who's online comes from our sectors: the first word says who's here already...
    fake.guild("0,0", TAG, [[KIM[0], "KIM", 0, 0, 0]])
    page.wait_for_function(f"window.__lf.mates().includes('{KIM[0]}')")
    expect(page.locator("#toast")).not_to_have_class(SHOWN)
    # ...and anyone new after that gets a note, with a way there.
    fake.guild("0,0", TAG, [[KIM[0], "KIM", 0, 0, 0], [ZED[0], "ZED", 1, 0, 0]])
    toast = page.locator("#toast")
    expect(toast).to_have_class(SHOWN)
    expect(toast.locator("b")).to_have_text("ZED came online")
    expect(page.locator(".who-guild .who-head-n")).to_have_text("2 online")
    toast.get_by_role("button", name="Fly to ZED").click()
    wait_landed(page, 1.5 * 48, 0.5 * 48)

    assert errors == []


def test_leaving_takes_you_out_and_tells_every_sector(page: Page, site_url, errors):
    guilds = in_cobalt([KIM[0], "KIM", NOW_MS])
    fake = FakeSurvey(surveyors=[KIM])
    start(page, site_url, fake, guilds, guild=MINE)
    open_you(page)
    eventually(page, lambda: len([m for m in fake.sent("me") if m.get("guild") == CODE]) == 4)
    card = page.locator("#guildCard")
    card.get_by_role("button", name="Leave").click()
    expect(card).to_contain_text("Leave the Cobalt Compass Society?")
    card.get_by_role("button", name="Stay").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    card.get_by_role("button", name="Leave").click()
    card.get_by_role("button", name="Leave", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-guild", "out")
    assert any(path == f"/{CODE}/leave" for _, path, _ in guilds.calls)
    assert page.evaluate("localStorage.getItem('letterfield.guild.v1')") is None
    expect(page.locator(".who-head")).to_have_count(0)
    eventually(page, lambda: all("guild" not in m for m in list({m["sector"]: m for m in fake.sent("me")}.values())))
    assert errors == []


def test_a_guild_that_no_longer_has_you_lets_you_go(page: Page, site_url, errors):
    start(page, site_url, FakeSurvey(), FakeGuilds(), guild=MINE)
    open_people(page)
    expect(page.locator("html")).to_have_attribute("data-guild", "out")
    expect(page.locator("#toast span")).to_have_text("You’re not in this guild any more")
    assert page.evaluate("localStorage.getItem('letterfield.guild.v1')") is None
    assert errors == [] or all("404" in e for e in errors)


def test_guilds_fit_a_phone(page: Page, site_url, errors):
    guilds = FakeGuilds(
        {CODE: {"name": [8, 7, 7], "tag": TAG, "members": [[KIM[0], "KIM", NOW_MS]]}}
    )  # Jade Theodolite Fellowship, the longest
    start(
        page,
        site_url,
        FakeSurvey(surveyors=[KIM]),
        guilds,
        query=f"&guild={CODE}",
        viewport={"width": 375, "height": 740},
    )
    invite = page.locator("#guildInvite")
    expect(invite).to_be_visible()
    box = invite.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 375, box
    invite.get_by_role("button", name="Join").click()
    open_list(page)
    expect(page.locator(".who-guild .who-head-name")).to_have_text("Jade Theodolite Fellowship")
    fits = """() => ({ page: document.scrollingElement.scrollWidth,
      notes: [document.getElementById('people').scrollWidth, document.getElementById('people').clientWidth],
      invite: document.querySelector('.who-invite').getBoundingClientRect().right })"""
    sizes = page.evaluate(fits)
    assert sizes["page"] <= 375 and sizes["notes"][0] <= sizes["notes"][1] and sizes["invite"] <= 375, sizes
    open_you(page)
    expect(page.locator("#guildCard .guild-name")).to_have_text("Jade Theodolite Fellowship")
    sizes = page.evaluate(fits)
    assert sizes["page"] <= 375 and sizes["notes"][0] <= sizes["notes"][1], sizes
    assert player_id(TOKEN) == PID
    assert errors == []


def test_invite_from_the_lists_heading_and_sign_first_for_an_invite(page: Page, site_url, errors):
    guilds = FakeGuilds(
        {
            CODE: {"name": NAME, "tag": TAG, "members": [[PID, "MLW", NOW_MS], [KIM[0], "KIM", NOW_MS]]},
            "PQR789": {"name": [8, 7, 7], "tag": "0badf00d", "members": [[ZED[0], "ZED", NOW_MS]]},
        }
    )
    start(page, site_url, FakeSurvey(surveyors=[KIM]), guilds, guild=MINE)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.evaluate("Object.defineProperty(navigator, 'share', { value: undefined })")
    open_list(page)
    invite_button = page.get_by_role("button", name="Invite a mate to the Cobalt Compass Society")
    invite_button.click()
    expect(invite_button).to_have_text("Link copied")
    expect(invite_button).to_have_text("+ Invite", timeout=6000)
    expect(page.locator("#guildSaid")).to_have_text("Invite link copied: send it to whoever you’d like to join.")
    assert page.evaluate("navigator.clipboard.readText()").endswith(f"/letterfield?guild={CODE}")

    # An invite to another guild, with no initials to join as: your page, to sign.
    page.goto(f"{site_url}/letterfield?survey={SURVEY}&guild=PQR789#debug")
    invite = page.locator("#guildInvite")
    expect(invite.locator("#guildInviteName")).to_have_text("Jade Theodolite Fellowship")
    expect(invite.locator(".eyebrow")).to_have_text("Switch guilds?")  # we're in the Cobalt Compass Society
    page.evaluate("localStorage.removeItem('games.initials')")
    invite.get_by_role("button", name="Join").click()
    expect(page.locator("#people")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-people-page", "you")
    expect(page.locator("#surveyInitials")).to_be_focused()
    expect(page.locator("#surveyHint")).to_have_text("Sign your initials, then join the guild.")
    expect(invite).to_contain_text("Sign your initials first, then join.")
    page.keyboard.type("mlw")
    page.keyboard.press("Enter")
    page.locator("#youClose").click()
    invite.get_by_role("button", name="Join").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert any(path == "/PQR789/join" for _, path, _ in guilds.calls)
    assert errors == []
