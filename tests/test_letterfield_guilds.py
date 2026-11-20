"""Letterfield's guilds, against the survey's fakes.

A guild is started from the Surveyors fold or joined from an invite link
(?guild=<code>), up to five at once; tests/fake_survey.py's FakeGuilds
answers the Worker's guild paths, and FakeSurvey.guild() says which members
of a guild are online. The real Guild object, and sectors checking several
guilds, are tested in worker/test/survey-guild.test.js.
"""

from __future__ import annotations

import json
import re
import time

from playwright.sync_api import Page, expect

from fake_survey import NOW_MS, FakeGuilds, FakeSurvey, player_id
from test_letterfield_survey import OVERLAP, SURVEY, circle, eventually, known_words, open_game, open_people, open_you
from test_letterfield_surveyors import KIM, LOU, PID, SAM, TOKEN, ZED, open_list, wait_landed

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
    mine: list | None = None,
    labels: dict | None = None,
) -> None:
    """Opens the game on the survey with our token, signed as `initials` (none if empty). `mine` is
    the list of guilds we're in, as the game keeps it; `guild` one guild kept as it was when there
    was one at a time; `labels` our labels for them."""
    page.route(f"{SURVEY}/v1/survey/guilds**", guilds.handle)
    open_game(page, site_url, fake, viewport=viewport)
    page.evaluate(
        """([t, ini, g, list, labels]) => {
      localStorage.setItem('letterfield.coach.v1', '1'); localStorage.setItem('games.player', t); localStorage.removeItem('letterfield.cam.v1');
      if (ini) localStorage.setItem('games.initials', JSON.stringify(ini)); else localStorage.removeItem('games.initials');
      for (const k of ['letterfield.guild.v1', 'letterfield.guilds.v1', 'letterfield.guild-labels.v1', 'letterfield.guild-folded.v1']) localStorage.removeItem(k);
      if (g) localStorage.setItem('letterfield.guild.v1', JSON.stringify(g));
      if (list) localStorage.setItem('letterfield.guilds.v1', JSON.stringify(list));
      if (labels) localStorage.setItem('letterfield.guild-labels.v1', JSON.stringify(labels));
    }""",
        [TOKEN, initials, guild, mine, labels],
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
CODE2, TAG2, NAME2 = "QRT567", "0ddba11a", [3, 2, 11]  # the Amber Lantern Bureau
WORK = {"code": CODE2, "name": NAME2, "tag": TAG2}


def stored(page: Page, key: str = "letterfield.guilds.v1"):
    return json.loads(page.evaluate(f"localStorage.getItem('{key}')") or "null")


def in_both(*members, family=(), work=()) -> FakeGuilds:
    """Two guilds with us in both: the Cobalt Compass Society (with `family`) and the Amber Lantern Bureau (with `work`);
    `members` are in both."""
    return FakeGuilds(
        {
            CODE: {"name": NAME, "tag": TAG, "members": [[PID, "MLW", NOW_MS], *members, *family]},
            CODE2: {"name": NAME2, "tag": TAG2, "members": [[PID, "MLW", NOW_MS], *members, *work]},
        }
    )


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
    [saved] = stored(page)
    assert saved["code"] in guilds.guilds and saved["tag"] == guilds.guilds[saved["code"]]["tag"]
    # Every sector is told, so it can check and put the guild on our caret.
    eventually(
        page,
        lambda: (
            {m["sector"] for m in fake.sent("me") if m.get("guilds") == [saved["code"]]}
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
    expect(page.locator("#toast span")).to_have_text("You’re in: its members come first under Surveyors")
    assert any(path == f"/{CODE}/join" for _, path, _ in guilds.calls)
    assert stored(page) == [MINE]
    assert errors == []


def test_a_guild_kept_from_one_at_a_time_carries_over_and_every_sector_hears_the_list(page: Page, site_url, errors):
    guilds = in_cobalt([KIM[0], "KIM", NOW_MS])
    fake = FakeSurvey()
    start(page, site_url, fake, guilds, guild=MINE)  # kept as it was, under the old key
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert stored(page) == [MINE]
    eventually(
        page,
        lambda: {m["sector"] for m in fake.sent("me") if m.get("guilds") == [CODE]} == {"-1,-1", "-1,0", "0,-1", "0,0"},
    )
    # The first goes as `guild` too, which a Worker from before lists reads.
    assert all(m.get("guild") == CODE for m in fake.sent("me") if "guilds" in m)
    open_you(page)
    expect(page.locator("#guildCard .guild-name")).to_have_text("Cobalt Compass Society")
    expect(page.get_by_role("button", name="Start another guild")).to_contain_text("You’re in 1 of 5")
    assert errors == []


def test_a_note_never_covers_a_guild_invite(page: Page, site_url, errors):
    """A note moved down below the title and the cards at the top of the map, but not below a
    guild invite, which sits in their place: on a phone it landed on top of it."""
    words = known_words(page, site_url)
    guilds = FakeGuilds({CODE: {"name": NAME, "tag": TAG, "members": [[KIM[0], "KIM", NOW_MS]]}})
    fake = FakeSurvey(claims=[[*words[0], 0, "MRW", NOW_MS - 60_000]])
    start(page, site_url, fake, guilds, query=f"&guild={CODE}", viewport={"width": 375, "height": 740})
    invite = page.locator("#guildInvite")
    expect(invite.locator(".guild-name")).to_have_text("Cobalt Compass Society")
    circle(page, words[0])  # charted by someone else, so a note says so
    toast = page.locator("#toast")
    expect(toast).to_have_class(SHOWN)
    toast.evaluate("e => Promise.all(e.getAnimations().map(a => a.finished))")  # its slide in
    assert not page.evaluate(OVERLAP, ["#toast", "#guildInvite"]), (toast.bounding_box(), invite.bounding_box())
    assert errors == []


def test_the_note_for_joining_takes_the_top_once_the_invite_has_gone(page: Page, site_url, errors):
    """Joining said so while the invite was still on screen, so on a phone the note stepped down
    below a card that went a moment later, and floated halfway down the map."""
    guilds = FakeGuilds({CODE: {"name": NAME, "tag": TAG, "members": [[KIM[0], "KIM", NOW_MS]]}})
    start(page, site_url, FakeSurvey(), guilds, query=f"&guild={CODE}", viewport={"width": 375, "height": 740})
    invite = page.locator("#guildInvite")
    expect(invite.locator(".guild-name")).to_have_text("Cobalt Compass Society")
    invite.evaluate("e => Promise.all(e.getAnimations({ subtree: true }).map(a => a.finished))")
    was = invite.bounding_box()
    invite.get_by_role("button", name="Join").click()
    toast = page.locator("#toast")
    expect(toast).to_have_class(SHOWN)
    expect(invite).to_be_hidden()
    toast.evaluate("e => Promise.all(e.getAnimations().map(a => a.finished))")  # its slide in
    assert toast.bounding_box()["y"] < was["y"] + was["height"], (toast.bounding_box(), was)
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


def test_an_invite_while_in_a_guild_joins_a_second_and_keeps_the_first(page: Page, site_url, errors):
    guilds = in_cobalt()
    guilds.guilds[CODE2] = {"name": NAME2, "tag": TAG2, "members": [[KIM[0], "KIM", NOW_MS]]}
    fake = FakeSurvey()
    start(page, site_url, fake, guilds, query=f"&guild={CODE2}", mine=[MINE])
    invite = page.locator("#guildInvite")
    expect(invite.locator(".eyebrow")).to_have_text("Invited to a guild")
    expect(invite.locator("#guildInviteName")).to_have_text("Amber Lantern Bureau")
    expect(invite).to_contain_text(
        "1 member so far. You’ll be in 2 guilds: the Cobalt Compass Society stays as it is, and each finds its own members on the map."
    )
    expect(invite.locator(".guild-warn")).to_have_count(0)
    invite.get_by_role("button", name="Join").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    expect(page.locator("#toast span")).to_have_text(
        "You’re in: its members get a heading of their own under Surveyors"
    )
    assert stored(page) == [MINE, WORK]
    assert all(not path.endswith("/leave") for _, path, _ in guilds.calls)
    # Every sector hears both, in our order.
    eventually(
        page,
        lambda: (
            {m["sector"] for m in fake.sent("me") if m.get("guilds") == [CODE, CODE2]}
            == {"-1,-1", "-1,0", "0,-1", "0,0"}
        ),
    )
    open_you(page)
    expect(page.locator("#guildCard .guild-name")).to_have_text(["Cobalt Compass Society", "Amber Lantern Bureau"])
    expect(page.get_by_role("button", name="Start another guild")).to_contain_text("You’re in 2 of 5")
    assert errors == []


FIVE = [
    {"code": CODE, "name": NAME, "tag": TAG},
    {"code": CODE2, "name": NAME2, "tag": TAG2},
    {"code": "BCD234", "name": [0, 3, 3], "tag": "0a0a0a0a"},
    {"code": "BCD235", "name": [8, 11, 4], "tag": "0b0b0b0b"},
    {"code": "BCD236", "name": [13, 14, 5], "tag": "0c0c0c0c"},
]


def five_guilds() -> FakeGuilds:
    g = FakeGuilds({x["code"]: {"name": x["name"], "tag": x["tag"], "members": [[PID, "MLW", NOW_MS]]} for x in FIVE})
    g.guilds[CODE2]["members"].append([KIM[0], "KIM", NOW_MS])
    g.guilds["PQR789"] = {
        "name": [15, 6, 4],
        "tag": "0d0d0d0d",
        "members": [[ZED[0], "ZED", NOW_MS]],
    }  # the Rose Beacon Club
    return g


def test_at_five_guilds_an_invite_asks_which_to_leave_naming_them(page: Page, site_url, errors):
    guilds = five_guilds()
    start(
        page,
        site_url,
        FakeSurvey(),
        guilds,
        query="&guild=PQR789",
        mine=FIVE,
        labels={CODE: "Family", CODE2: "Work"},
        viewport={"width": 375, "height": 900},
    )
    invite = page.locator("#guildInvite")
    expect(invite.locator(".eyebrow")).to_have_text("Choose a guild to leave")
    expect(invite.locator("#guildInviteName")).to_have_text("Rose Beacon Club")
    expect(invite).to_contain_text("You’re in 5 guilds, the most at once. Leave one to join this one:")
    # Each of ours by name, with our label for it and how many members it has.
    options = invite.locator(".guild-opt")
    expect(options.locator(".guild-name")).to_have_text(
        [
            "Cobalt Compass Society",
            "Amber Lantern Bureau",
            "Crimson Quill Circle",
            "Jade Waypoint Club",
            "Violet Horizon Expedition",
        ]
    )
    expect(options.nth(0).locator(".guild-chip")).to_have_text("Family")
    expect(options.nth(1)).to_contain_text("2 members")
    join = invite.get_by_role("button", name="Leave and join")
    expect(join).to_be_disabled()
    # Choosing one says what leaving it costs; the only member's guild would end.
    invite.get_by_role("radio", name="Jade Waypoint Club").check()
    expect(invite.locator(".guild-warn")).to_have_text(
        "You’d need a new invite to go back to the Jade Waypoint Club. You’re its only member, so it ends when you leave."
    )
    expect(invite.get_by_role("radio", name="Jade Waypoint Club")).to_be_focused()
    invite.get_by_role("radio", name="Amber Lantern Bureau").check()
    expect(invite.locator(".guild-warn")).to_have_text(
        "You’d need a new invite to go back to the Amber Lantern Bureau."
    )
    box = invite.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 375, box
    assert page.evaluate("document.scrollingElement.scrollWidth") <= 375
    join.click()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    expect(page.locator("#toast span")).to_have_text("You’re in, and out of the Amber Lantern Bureau")
    eventually(page, lambda: any(path == f"/{CODE2}/leave" for _, path, _ in guilds.calls))
    assert [g["code"] for g in stored(page)] == [CODE, "BCD234", "BCD235", "BCD236", "PQR789"]
    # The label for the guild we left goes with it.
    assert stored(page, "letterfield.guild-labels.v1") == {CODE: "Family"}
    assert errors == []


def test_at_five_guilds_the_arrow_keys_choose_which_to_leave_not_move_the_map(page: Page, site_url, errors):
    start(page, site_url, FakeSurvey(), five_guilds(), query="&guild=PQR789", mine=FIVE)
    invite = page.locator("#guildInvite")
    invite.get_by_role("radio", name="Cobalt Compass Society").check()
    cam = "[window.__lf.cam.x, window.__lf.cam.y]"
    was = page.evaluate(cam)
    page.keyboard.press("ArrowDown")
    expect(invite.get_by_role("radio", name="Amber Lantern Bureau")).to_be_checked()
    page.keyboard.press("ArrowDown")
    expect(invite.get_by_role("radio", name="Crimson Quill Circle")).to_be_checked()
    expect(invite.get_by_role("radio", name="Crimson Quill Circle")).to_be_focused()
    page.wait_for_timeout(300)  # a flight would have started by now
    assert page.evaluate(cam) == was
    assert errors == []


def test_at_five_guilds_the_card_asking_which_to_leave_scrolls_on_a_short_phone(page: Page, site_url, errors):
    start(
        page,
        site_url,
        FakeSurvey(),
        five_guilds(),
        query="&guild=PQR789",
        mine=FIVE,
        labels={x["code"]: f"Label {i}" for i, x in enumerate(FIVE)},
        viewport={"width": 375, "height": 667},
    )
    invite = page.locator("#guildInvite")
    invite.get_by_role("radio", name="Violet Horizon Expedition").check()
    expect(invite.locator(".guild-warn")).to_contain_text("it ends when you leave")
    # Five guilds, each with a label, and the warning: taller than the phone, so the card stops
    # short of the screen's foot and scrolls, rather than leaving its buttons off the bottom.
    box = invite.bounding_box()
    assert box["y"] + box["height"] <= 667, box
    assert invite.evaluate("e => e.scrollHeight > e.clientHeight")
    join = invite.get_by_role("button", name="Leave and join")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, 2000)  # the card scrolls, not the map under it
    page.wait_for_function("document.querySelector('#guildInvite').scrollTop > 0")
    expect(join).to_be_in_viewport()
    join.click()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert errors == []


def test_at_five_guilds_starting_another_waits_for_one_to_go(page: Page, site_url, errors):
    start(page, site_url, FakeSurvey(), five_guilds(), mine=FIVE)
    open_you(page)
    expect(page.locator("#guildCard .guild-name")).to_have_count(5)
    expect(page.locator("#guildCard")).to_contain_text(
        "You’re in 5 guilds, the most at once. To join another, leave one."
    )
    expect(page.get_by_role("button", name="Start another guild")).to_have_count(0)
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
    # The guild's dot keeps clear of its name, and Invite is as tall as the drawer's other buttons,
    # measured once the drawer has finished sliding in.
    page.locator("#people").evaluate("e => Promise.all(e.getAnimations({ subtree: true }).map(a => a.finished))")
    gap, invite = page.evaluate("""() => { const box = s => document.querySelector(s).getBoundingClientRect();
      return [box('.who-guild .who-head-name').left - box('.who-guild .guild-dot').right, box('.who-invite').height]; }""")
    assert gap >= 8 and invite >= 40, (gap, invite)
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


def test_a_member_who_takes_no_emotes_shows_as_one(page: Page, site_url, errors):
    # SAM, in our guild, takes no emotes: the list says so (its last field), and so do our sectors.
    guilds = in_cobalt([SAM[0], "SAM", NOW_MS])
    fake = FakeSurvey(surveyors=[LOU, SAM])
    start(page, site_url, fake, guilds, guild=MINE)
    open_list(page)
    fake.guild("0,0", TAG, [[SAM[0], "SAM", -2, 3, 360, 1]])
    page.wait_for_function(f"window.__lf.mates().includes('{SAM[0]}')")
    expect(page.locator(".who-ini")).to_have_text(["SAM", "LOU"])
    # Under the guild's heading, as anywhere else on the list, they can't be sent one.
    expect(page.locator(".who-meta").first).to_have_text("3 territories away · idle 6m · no emotes")
    expect(page.get_by_role("button", name="Wave to SAM")).to_be_disabled()
    page.get_by_role("button", name="More for SAM").click()
    expect(page.locator(".who-emotes .emote").first).to_be_disabled()
    expect(page.locator(".who-said:not(:empty)")).to_have_text("SAM isn’t taking emotes.")
    # Once they take emotes again, our sectors say so.
    fake.guild("0,0", TAG, [[SAM[0], "SAM", -2, 3, 360, 0]])
    expect(page.get_by_role("button", name="Wave to SAM")).to_be_enabled()
    expect(page.locator(".who-meta").first).to_have_text("3 territories away · idle 6m")
    assert errors == []


def test_your_page_links_to_the_guilds_own_page_in_the_survey_log(page: Page, site_url, errors):
    lid = "c0ba17c0ba"
    guilds = FakeGuilds({CODE: {"name": NAME, "tag": TAG, "lid": lid, "members": [[PID, "MLW", NOW_MS]]}})
    fake = FakeSurvey()
    # Kept before the log knew guilds: no log id until the roster brings it.
    start(page, site_url, fake, guilds, guild=MINE)
    open_you(page)
    link = page.locator('#guildCard a[data-g="log"]')
    # With the guild's name as its word numbers, for a log that hasn't seen it chart a word.
    expect(link).to_have_attribute("href", f"/letterfield-log?guild={lid}&name={'-'.join(map(str, NAME))}")
    expect(link).to_contain_text("Our words in the survey log")
    # Every member's words count: there's no keeping off the list now.
    expect(page.locator("#guildCard")).to_contain_text(
        "Words you chart while in a guild count for it in the survey log"
    )
    expect(page.locator("#guildCard")).not_to_contain_text("off the list")
    assert stored(page) == [{**MINE, "lid": lid}]
    assert errors == []


def test_leaving_takes_you_out_and_tells_every_sector(page: Page, site_url, errors):
    guilds = in_cobalt([KIM[0], "KIM", NOW_MS])
    fake = FakeSurvey(surveyors=[KIM])
    start(page, site_url, fake, guilds, guild=MINE)
    open_you(page)
    eventually(page, lambda: len([m for m in fake.sent("me") if m.get("guilds") == [CODE]]) == 4)
    card = page.locator("#guildCard")
    card.get_by_role("button", name="Leave").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "confirming")
    expect(card).to_contain_text("Leave the Cobalt Compass Society?")
    # A yes or no: Leave in red, and Stay, which has the focus.
    expect(card.get_by_role("button", name="Leave", exact=True)).to_have_class(re.compile(r"\bbtn danger\b"))
    expect(card.get_by_role("button", name="Stay")).to_have_class(re.compile(r"\bbtn ghost\b"))
    expect(card.get_by_role("button", name="Stay")).to_be_focused()
    expect(page.locator(".who-head")).not_to_have_count(0)  # still in it while asked
    card.get_by_role("button", name="Stay").click()
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    expect(card.get_by_role("button", name="Leave guild")).to_be_focused()
    card.get_by_role("button", name="Leave").click()
    card.get_by_role("button", name="Leave", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-guild", "out")
    assert any(path == f"/{CODE}/leave" for _, path, _ in guilds.calls)
    assert stored(page) == [] and stored(page, "letterfield.guild.v1") is None
    expect(page.locator(".who-head")).to_have_count(0)
    eventually(page, lambda: all("guilds" not in m for m in list({m["sector"]: m for m in fake.sent("me")}.values())))
    assert errors == []


def test_a_guild_that_no_longer_has_you_lets_you_go(page: Page, site_url, errors):
    start(page, site_url, FakeSurvey(), FakeGuilds(), guild=MINE)
    open_people(page)
    expect(page.locator("html")).to_have_attribute("data-guild", "out")
    expect(page.locator("#toast span")).to_have_text("You’re not in this guild any more")
    assert page.evaluate("localStorage.getItem('letterfield.guild.v1')") is None and stored(page) == []
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
    invite_button = page.get_by_role("button", name="Invite someone to the Cobalt Compass Society")
    invite_button.click()
    expect(invite_button).to_have_text("Link copied")
    expect(invite_button).to_have_text("+ Invite", timeout=6000)
    expect(page.locator("#guildSaid")).to_have_text("Invite link copied: send it to whoever you’d like to join.")
    assert page.evaluate("navigator.clipboard.readText()").endswith(f"/letterfield?guild={CODE}")

    # An invite to another guild, with no initials to join as: your page, to sign.
    page.goto(f"{site_url}/letterfield?survey={SURVEY}&guild=PQR789#debug")
    invite = page.locator("#guildInvite")
    expect(invite.locator("#guildInviteName")).to_have_text("Jade Theodolite Fellowship")
    expect(invite).to_contain_text("You’ll be in 2 guilds")  # we're in the Cobalt Compass Society
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


BEA = ["e7f1a2b3c4d5", "BEA", 3, -2, 120, 0]


def test_each_guild_has_a_heading_with_a_mate_in_both_under_each_and_folds_away(page: Page, site_url, errors):
    guilds = in_both([LOU[0], "LOU", NOW_MS], family=[[KIM[0], "KIM", NOW_MS]], work=[[ZED[0], "ZED", NOW_MS]])
    start(page, site_url, FakeSurvey(surveyors=[KIM, ZED, LOU, BEA]), guilds, mine=[MINE, WORK])
    open_list(page)
    heads = page.locator(".who-guild")
    expect(heads.locator(".who-head-name")).to_have_text(["Cobalt Compass Society", "Amber Lantern Bureau"])
    expect(heads.locator(".who-head-n")).to_have_text(["2 online", "2 online"])
    # LOU is in both, so under both; BEA, in neither, under everyone else.
    expect(page.locator(".who-ini")).to_have_text(["KIM", "LOU", "ZED", "LOU", "BEA"])
    expect(page.locator(".who-head").last).to_have_text("Everyone else")
    expect(page.get_by_role("button", name="Invite someone to the Amber Lantern Bureau")).to_be_visible()
    # Each heading's dot on its own members.
    hues = page.locator(".who-row .who-av .guild-dot").evaluate_all(
        "ds => ds.map(d => d.style.getPropertyValue('--gh'))"
    )
    assert hues == ["220", "220", "38", "38"], hues
    # Opening LOU's emotes under one heading opens them there only.
    page.get_by_role("button", name="More for LOU").nth(1).click()
    expect(page.locator(".who-emotes")).to_have_count(1)
    expect(page.locator(f'.who-row[data-sec="{CODE2}:"] .who-emotes')).to_have_count(1)
    expect(page.get_by_role("button", name="More for LOU").nth(1)).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Escape")
    expect(page.locator(".who-emotes")).to_have_count(0)
    expect(page.get_by_role("button", name="More for LOU").nth(1)).to_be_focused()
    # A heading folds away its rows, keeps its count, and stays folded on this device.
    fold = page.get_by_role("button", name="Fold away the Amber Lantern Bureau")
    fold.click()
    expect(page.locator(".who-ini")).to_have_text(["KIM", "LOU", "BEA"])
    expect(heads.locator(".who-head-n")).to_have_text(["2 online", "2 online"])
    expect(page.get_by_role("button", name="Show the Amber Lantern Bureau")).to_have_attribute("aria-expanded", "false")
    assert stored(page, "letterfield.guild-folded.v1") == [CODE2]
    page.get_by_role("button", name="Show the Amber Lantern Bureau").click()
    expect(page.locator(".who-ini")).to_have_text(["KIM", "LOU", "ZED", "LOU", "BEA"])
    assert errors == []


def test_a_mates_caret_splits_between_the_guilds_you_share_and_its_card_names_them(page: Page, site_url, errors):
    guilds = in_both([LOU[0], "LOU", NOW_MS], family=[[KIM[0], "KIM", NOW_MS]], work=[[ZED[0], "ZED", NOW_MS]])
    presence = [
        [LOU[0], "LOU", 9.5, 7.0, [TAG, TAG2]],
        [ZED[0], "ZED", 15.5, 3.0, [TAG2, "feedface"]],
        [KIM[0], "KIM", 4.5, 11.0, TAG],
    ]
    start(
        page,
        site_url,
        FakeSurvey(surveyors=[KIM, ZED, LOU], presence=presence),
        guilds,
        mine=[MINE, WORK],
        labels={CODE: "Family", CODE2: "Work"},
    )
    for pid in (LOU[0], ZED[0], KIM[0]):
        page.wait_for_function(f"window.__lf.carets().includes('{pid}')")
    page.wait_for_timeout(300)
    cards = {}
    for pid, ini in ((LOU[0], "LOU"), (ZED[0], "ZED"), (KIM[0], "KIM")):
        at = page.evaluate(f"window.__lf.caretXY('{pid}')")
        page.mouse.move(at["x"], at["y"])
        expect(page.locator("#peek b")).to_have_text(ini)
        cards[ini] = page.locator("#peek span").text_content()
    # Labels name them, in our order; another guild's tag means nothing here; an older sector's single tag still counts.
    assert cards["LOU"].startswith("Family · Work · surveying here"), cards
    assert cards["ZED"].startswith("Work · surveying here"), cards
    assert cards["KIM"].startswith("Family · surveying here"), cards
    # LOU's dot: our first guild's colour on the right half, the second's on the left.
    page.mouse.move(5, 400)
    rgb = page.evaluate(
        """pid => { const c = document.querySelector('canvas'), r = c.getBoundingClientRect(), dpr = c.width / r.width;
      const at = window.__lf.caretXY(pid), cs = window.__lf.cam.cs, h = cs * .66, rad = Math.min(4, Math.max(2.5, cs * .09));
      const y = at.y - h / 2 - rad - 1, px = (x) => Array.from(c.getContext('2d').getImageData(Math.round((x - r.left) * dpr), Math.round((y - r.top) * dpr), 1, 1).data.slice(0, 3));
      return [px(at.x + rad * .55), px(at.x - rad * .55)]; }""",
        LOU[0],
    )
    (rr, rg, rb), (lr, lg, lb) = rgb
    assert rb > rr and lr > lb, rgb  # cobalt (blue) on the right, amber on the left
    assert errors == []


def test_a_mate_coming_online_in_two_shared_guilds_gets_one_note(page: Page, site_url, errors):
    guilds = in_both([LOU[0], "LOU", NOW_MS], family=[[KIM[0], "KIM", NOW_MS]], work=[[ZED[0], "ZED", NOW_MS]])
    fake = FakeSurvey(surveyors=[KIM, ZED, LOU])
    start(page, site_url, fake, guilds, mine=[MINE, WORK], labels={CODE2: "Work"})
    page.evaluate("""() => { window.__notes = [];
      new MutationObserver(recs => { for (const r of recs) for (const n of r.addedNodes) {
        const bs = n.nodeName === 'B' ? [n] : n.querySelectorAll ? [...n.querySelectorAll('b')] : [];
        for (const b of bs) if (/came online/.test(b.textContent)) window.__notes.push([b.textContent, b.parentElement.querySelector('span')?.textContent]);
      } }).observe(document.getElementById('toast'), { subtree: true, childList: true }); }""")
    # Each guild's first word just says who's here.
    fake.guild("0,0", TAG, [[KIM[0], "KIM", 0, 0, 0]])
    fake.guild("0,0", TAG2, [])
    page.wait_for_function(f"window.__lf.mates().includes('{KIM[0]}')")
    # LOU arrives, and both guilds say so: one note.
    fake.guild("0,0", TAG, [[KIM[0], "KIM", 0, 0, 0], [LOU[0], "LOU", 1, 0, 0]])
    page.wait_for_function(f"window.__lf.matesOf('{TAG}').includes('{LOU[0]}')")
    fake.guild("0,0", TAG2, [[LOU[0], "LOU", 1, 0, 0]])
    page.wait_for_function(f"window.__lf.matesOf('{TAG2}').includes('{LOU[0]}')")
    # ZED, in Work only, gets a note of their own, which names the guild by our label.
    fake.guild("0,0", TAG2, [[LOU[0], "LOU", 1, 0, 0], [ZED[0], "ZED", 1, 0, 0]])
    page.wait_for_function(f"window.__lf.matesOf('{TAG2}').includes('{ZED[0]}')")
    notes = page.evaluate("window.__notes")
    assert [n[0] for n in notes] == ["LOU came online", "ZED came online"], notes
    assert notes[0][1].startswith("Cobalt Compass Society · ") and notes[1][1].startswith("Work · "), notes
    assert errors == []


def test_a_label_of_your_own_names_a_guild_on_the_list_and_stays_as_text(page: Page, site_url, errors):
    guilds = in_both(work=[[ZED[0], "ZED", NOW_MS]])
    start(
        page, site_url, FakeSurvey(surveyors=[ZED]), guilds, mine=[MINE, WORK], viewport={"width": 375, "height": 900}
    )
    open_you(page)
    field = page.get_by_role("textbox", name="Your label for the Amber Lantern Bureau")
    assert field.evaluate("e => parseFloat(getComputedStyle(e).fontSize)") >= 16
    field.fill("  Work   friends  ")
    field.press("Enter")
    expect(field).to_have_value("Work friends")
    assert stored(page, "letterfield.guild-labels.v1") == {CODE2: "Work friends"}
    # It leads that guild's heading, with the guild's name under it.
    page.locator("#youBack").click()
    head = page.locator(f'.who-guild[data-code="{CODE2}"] .who-head-name')
    expect(head).to_have_text("Work friendsAmber Lantern Bureau")
    expect(head.locator("small")).to_have_text("Amber Lantern Bureau")
    # Whatever is typed stays text, and a label is at most 24 characters.
    open_you(page)
    field.fill("<b>Bold</b> & <i>more</i> and then some")
    field.press("Tab")
    expect(field).to_have_value("<b>Bold</b> & <i>more</i")
    page.locator("#youBack").click()
    expect(head).to_have_text("<b>Bold</b> & <i>more</iAmber Lantern Bureau")
    expect(head.locator("b, i")).to_have_count(0)
    # Emptied, it's gone, and the name leads again.
    open_you(page)
    field.fill("")
    field.press("Enter")
    assert stored(page, "letterfield.guild-labels.v1") == {}
    assert page.evaluate("document.scrollingElement.scrollWidth") <= 375
    assert errors == []


def test_a_guild_that_let_you_go_elsewhere_goes_and_the_others_stay(page: Page, site_url, errors):
    guilds = in_both()
    del guilds.guilds[CODE]  # left on another device, which was its last member
    start(page, site_url, FakeSurvey(), guilds, mine=[MINE, WORK], labels={CODE: "Family", CODE2: "Work"})
    open_people(page)
    expect(page.locator("#toast span")).to_have_text("You’re not in this guild any more")
    expect(page.locator("#toast b")).to_have_text("Cobalt Compass Society")
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert stored(page) == [WORK]
    assert stored(page, "letterfield.guild-labels.v1") == {CODE2: "Work"}
    expect(page.locator(".who-guild .who-head-name")).to_have_text(["WorkAmber Lantern Bureau"])
    assert errors == [] or all("404" in e for e in errors)
