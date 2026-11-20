"""Letterfield's syncing of linked devices, against the survey's fakes.

Linking turns it on (tests/test_letterfield_linking.py links); from then on
the game sends what changed here and takes in what changed on the player's
other devices. tests/fake_survey.py's FakePlayers answers the Worker's sync
paths; the real Player is tested in worker/test/players.test.js.
"""

from __future__ import annotations

import json
import re

from playwright.sync_api import Page, expect

from fake_leaderboard import Held
from fake_survey import NOW_MS, FakeGuilds, FakeLinks, FakePlayers, FakeSurvey, player_id, receipt, reply
from test_letterfield_guilds import CODE, CODE2, MINE, WORK, in_both, in_cobalt, stored
from test_letterfield_guilds import start as start_guilds
from test_letterfield_survey import SURVEY, eventually, known_words, open_you
from test_letterfield_surveyors import KIM, PID, TOKEN

ON = {"on": True, "epoch": "", "at": 0, "f": [], "n": [], "settingsAt": 1}  # synced, nothing heard yet


def start(
    page: Page,
    site_url: str,
    players: FakePlayers,
    synced: bool = True,
    finds=(),
    query: str = "",
    links: FakeLinks | None = None,
    fake: FakeSurvey | None = None,
    held: Held | None = None,
) -> None:
    """Opens the game with our token and `finds` in the notes, synced through `players` (or
    `held`, holding some of its replies) as a link leaves it (every find waiting to go up), or
    not synced at all."""
    page.route(f"{SURVEY}/v1/player/**", (held or players).handle)
    page.route(f"{SURVEY}/v1/link**", (links or FakeLinks(players=players)).handle)
    start_guilds(page, site_url, fake or FakeSurvey(), FakeGuilds())
    page.evaluate("finds => localStorage.setItem('letterfield.finds.v4', finds)", json.dumps(list(finds)))
    if synced:
        page.reload()
        page.wait_for_function(f"window.__lf && window.__lf.found.size === {len(finds)}")
        page.evaluate(
            "on => localStorage.setItem('letterfield.sync.v1', JSON.stringify({ ...on, f: [...window.__lf.found.keys()] }))",
            ON,
        )
    players.calls.clear()
    page.goto("about:blank")
    page.goto(f"{site_url}/letterfield?survey={SURVEY}{query}#debug")
    page.wait_for_function(f"window.__lf && window.__lf.pid() === '{PID}'")


def words(page: Page, site_url: str, n: int) -> list[dict]:
    """`n` finds hidden near the origin, as the field notes keep them."""
    return [
        {"w": w, "x": x, "y": y, "d": d, "t": 1_700_000_000_000 + i, "s": 0}
        for i, (w, x, y, d) in enumerate(known_words(page, site_url)[:n])
    ]


def noted(page: Page) -> list[str]:
    return page.evaluate("[...window.__lf.found.values()].map(e => e.w).sort()")


def test_a_device_never_linked_keeps_everything_here(page: Page, site_url, errors):
    players = FakePlayers()
    start(page, site_url, players, synced=False)
    expect(page.locator("html")).to_have_attribute("data-sync", "off")
    page.locator("#whoEmotes").evaluate("e => e.click()")
    page.wait_for_timeout(3000)
    assert players.calls == []
    # Your page is the one place that says so: no Stop syncing, and no recovery code saved.
    open_you(page)
    card = page.locator("#pairCard")
    expect(card.get_by_role("button", name="Stop syncing")).to_have_count(0)
    expect(card.get_by_role("button", name="Recovery code")).to_contain_text("Not saved")
    assert errors == []


def test_finds_and_settings_go_both_ways(page: Page, site_url, errors):
    *mine, theirs = words(page, site_url, 3)
    players = FakePlayers(started=[PID])
    # The other device sent a find already, charted first.
    players.add(PID, finds=[{**theirs, "f": 1, "n": 77}])
    start(page, site_url, players, finds=mine)
    expect(page.locator("html")).not_to_have_attribute("data-sync", "off")
    eventually(page, lambda: len(players.sent()) >= 1)
    first = players.sent()[0]
    assert first["since"] == 0 and first["settingsAt"] == 1
    assert first["settings"] == {
        "initials": "MLW",
        "guilds": [],
        "guild": None,
        "labels": {},
        "muted": [],
        "mutedAs": {},
        "emotes": True,
        "badge": None,  # the badge shown to others (see test_letterfield_achievements.py)
        "card": None,  # their card of badges, which others see
    }
    page.wait_for_function(f"window.__lf.found.size === {len(mine) + 1}")
    assert noted(page) == sorted([f["w"] for f in mine] + [theirs["w"]])
    assert page.evaluate(f"[...window.__lf.found.values()].find(e => e.w === '{theirs['w']}').f") == 1
    # Every find is up there now.
    assert sorted(f["w"] for f in first["finds"]) == sorted(f["w"] for f in mine)
    saved = json.loads(page.evaluate("localStorage.getItem('letterfield.sync.v1')"))
    assert saved["f"] == [] and saved["at"] == 2 and saved["epoch"] == players.players[PID]["epoch"]

    # A change here goes up soon after...
    page.locator("#whoEmotes").evaluate("e => e.click()")
    eventually(page, lambda: players.players[PID]["settings"]["emotes"] is False, timeout_ms=8000)
    # ...and one there comes down: new initials, a mute, and two guilds with a label of ours for one.
    at = page.evaluate("Date.now()")  # just after our own change, so an echo of it would be later still
    players.add(
        PID,
        settings={
            "initials": "ZED",
            "guilds": [MINE, WORK],
            "guild": MINE,
            "labels": {CODE2: "Work"},
            "muted": [KIM[0]],
            "mutedAs": {KIM[0]: ["KIM", 9]},
            "emotes": True,
        },
        settings_at=at,
    )
    page.evaluate("window.__lf.syncNow()")
    expect(page.locator("#surveyMeName")).to_have_text("ZED")
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert json.loads(page.evaluate("localStorage.getItem('letterfield.guilds.v1')")) == [MINE, WORK]
    assert page.evaluate("window.__lf.labels()") == {CODE2: "Work"}
    assert page.evaluate("window.__lf.muted()") == [KIM[0]]
    # Who they muted comes with it, for the Muted list here.
    assert json.loads(page.evaluate("localStorage.getItem('letterfield.mutedAs.v1')")) == {KIM[0]: ["KIM", 9]}
    assert json.loads(page.evaluate("localStorage.getItem('games.initials')")) == "ZED"
    # Nothing it took in goes back up as a change of its own.
    page.wait_for_timeout(2500)
    assert players.players[PID]["settings_at"] == at
    assert errors == []


def test_stopping_here_or_everywhere(page: Page, site_url, errors):
    players = FakePlayers(started=[PID])
    start(page, site_url, players)
    open_you(page)
    card = page.locator("#pairCard")
    # The row that stops it is the one place that says you're backed up.
    expect(page.locator("#pairHead")).to_have_text("Devices")
    stop = card.get_by_role("button", name="Stop syncing")
    expect(stop).to_contain_text("Your notes and settings are backed up")
    expect(stop).to_have_class(re.compile(r"\bdanger\b"))  # red, as Leave guild is
    stop.click()
    # Where to stop is a choice between things to do, so it's rows, then a way out.
    expect(card.locator(".pair-ask")).to_have_text("Stop syncing where? Each device keeps its notes as they are.")
    expect(card.locator(".you-item")).to_have_text(
        [
            "This deviceThe others keep syncing",
            "Every deviceAlso deletes the copy kept for syncing, and any recovery code",
        ]
    )
    expect(card.get_by_role("button", name="This device")).to_be_focused()
    expect(card.get_by_role("button", name="Every device")).to_have_class(re.compile(r"\bdanger\b"))
    expect(card.get_by_role("button", name="Keep syncing", exact=True)).to_have_class(re.compile(r"\bbtn ghost\b"))
    card.get_by_role("button", name="Keep syncing", exact=True).click()
    expect(stop).to_be_focused()
    card.get_by_role("button", name="Stop syncing").click()
    card.get_by_role("button", name="This device").click()
    expect(page.locator("html")).to_have_attribute("data-sync", "off")
    expect(card).to_contain_text("Syncing stopped on this device.")
    expect(card.get_by_role("button", name="Stop syncing")).to_have_count(0)
    assert players.sent("forget") == [] and PID in players.players
    assert page.evaluate("localStorage.getItem('letterfield.sync.v1')") is None

    page.evaluate(f"localStorage.setItem('letterfield.sync.v1', {json.dumps(json.dumps(ON))})")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-sync", "idle")
    open_you(page)
    card.get_by_role("button", name="Stop syncing").click()
    card.get_by_role("button", name="Every device").click()
    expect(card).to_contain_text(
        "Syncing stopped on every device, and the copy kept for it is deleted, with any recovery code."
    )
    eventually(page, lambda: PID not in players.players)
    assert [b["token"] for b in players.sent("forget")] == [TOKEN]
    assert errors == []


def test_stopping_everywhere_waits_for_the_worker_and_answers_under_the_rows(page: Page, site_url, errors):
    """Its answer used to go into whatever card was open by then: once, over the recovery code's heading."""
    players = FakePlayers(started=[PID])
    start(page, site_url, players)
    held = Held(players, lambda r: r.url.endswith("/v1/player/forget"))
    page.route(f"{SURVEY}/v1/player/**", held.handle)
    open_you(page)
    html, card = page.locator("html"), page.locator("#pairCard")
    card.get_by_role("button", name="Stop syncing").click()
    card.get_by_role("button", name="Every device").click()
    held.wait_for(page)
    # Nothing else opens while it waits, so its answer can't land in another card.
    expect(card.get_by_role("button", name="Recovery code")).to_have_count(0)
    expect(card).to_have_text("Stopping syncing on every device…")
    expect(html).to_have_attribute("data-pair", "stopping")
    # Focus waits on the card too, and Escape doesn't take the page away from under the answer.
    expect(card.locator("#pairStopping")).to_be_focused()
    page.keyboard.press("Escape")
    expect(html).to_have_attribute("data-people-page", "you")
    held.release()
    expect(html).to_have_attribute("data-pair", "idle")
    note = card.locator(".pair-note")
    expect(note).to_have_text(
        "Syncing stopped on every device, and the copy kept for it is deleted, with any recovery code."
    )
    expect(note).to_be_focused()
    expect(card.get_by_role("button", name="Recovery code")).to_contain_text("Not saved")  # its row, whole
    eventually(page, lambda: PID not in players.players)
    assert errors == []


def test_stopping_everywhere_without_the_worker_keeps_syncing(page: Page, site_url, errors):
    """This device stopped before the Worker answered, so when it couldn't be reached the note said
    to try again, with the Stop syncing row already gone and nothing left to try again with."""
    players = FakePlayers(started=[PID])
    start(page, site_url, players)
    page.route(f"{SURVEY}/v1/player/forget", lambda r: reply(r, {"error": "down"}, 503))
    open_you(page)
    html, card = page.locator("html"), page.locator("#pairCard")
    card.get_by_role("button", name="Stop syncing").click()
    card.get_by_role("button", name="Every device").click()
    note = card.locator(".pair-note")
    expect(note).to_contain_text("Couldn’t reach the survey")
    expect(html).to_have_attribute("data-pair", "idle")
    expect(card.get_by_role("button", name="Stop syncing")).to_be_visible()  # to try again with
    expect(html).not_to_have_attribute("data-sync", "off")
    expect(note).to_have_text("Couldn’t reach the survey, so syncing hasn’t stopped. Try again in a moment.")
    assert page.evaluate("localStorage.getItem('letterfield.sync.v1')") is not None
    assert PID in players.players
    assert errors == [] or all("503" in e for e in errors)


def test_stopped_elsewhere_stops_here_too(page: Page, site_url, errors):
    # This device saved a recovery code, which stopping on every device took with it.
    page.add_init_script("""if (location.protocol.startsWith('http') && !sessionStorage.getItem('seeded')) {
      sessionStorage.setItem('seeded', '1'); localStorage.setItem('letterfield.recovery.v1', '1700000000000'); }""")
    start(page, site_url, FakePlayers())  # nothing started for us: stopped on every device
    expect(page.locator("html")).to_have_attribute("data-sync", "off", timeout=8000)
    expect(page.locator("#toast b")).to_have_text("Syncing has stopped")
    assert page.evaluate("localStorage.getItem('letterfield.sync.v1')") is None
    assert page.evaluate("localStorage.getItem('letterfield.recovery.v1')") is None
    open_you(page)
    expect(page.locator("#pairCard").get_by_role("button", name="Stop syncing")).to_have_count(0)
    expect(page.locator("#pairCard").get_by_role("button", name="Recovery code")).to_contain_text("Not saved")
    assert errors == []


def test_a_device_linked_with_a_code_sends_all_it_has(page: Page, site_url, errors):
    mine = words(page, site_url, 2)
    players = FakePlayers()
    links = FakeLinks({"CDEFGHJK": {"token": "f" * 32, "carry": {"initials": "MLW"}}}, players=players)
    start(page, site_url, players, synced=False, finds=mine, query="&link=CDEFGHJK", links=links)
    expect(page.locator("html")).to_have_attribute("data-sync", "off")
    page.locator("#pairOffer").get_by_role("button", name="Link", exact=True).click()
    eventually(page, lambda: len(players.sent()) >= 1, timeout_ms=10_000)
    body = players.sent()[0]
    assert sorted(f["w"] for f in body["finds"]) == sorted(f["w"] for f in mine)
    expect(page.locator("html")).to_have_attribute("data-sync", "idle")
    assert errors == []


def start_in_guilds(page: Page, site_url: str, players: FakePlayers, guilds: FakeGuilds, mine: list) -> None:
    """Opens the game synced, in the guilds `mine`, with `guilds` answering for them."""
    page.route(f"{SURVEY}/v1/player/**", players.handle)
    start_guilds(page, site_url, FakeSurvey(), guilds, mine=mine)
    page.evaluate("on => localStorage.setItem('letterfield.sync.v1', JSON.stringify(on))", ON)
    page.goto("about:blank")
    page.goto(f"{site_url}/letterfield?survey={SURVEY}#debug")
    page.wait_for_function(f"window.__lf && window.__lf.pid() === '{PID}'")
    eventually(page, lambda: len(players.sent()) >= 1)  # the first sync, which brings nothing


def guilds_from_there(page: Page, players: FakePlayers, guilds: list) -> None:
    """A linked device changes our guilds to `guilds`, and this one syncs."""
    players.add(
        PID,
        settings={"initials": "MLW", "guilds": guilds, "guild": guilds[0] if guilds else None},
        settings_at=page.evaluate("Date.now()"),
    )
    page.evaluate("window.__lf.syncNow()")


def test_a_guild_list_from_there_keeps_the_leave_being_asked_about(page: Page, site_url, errors):
    """It used to clear which guild was being asked about without a move, leaving the card asking
    nothing with data-guild still 'confirming' and every guild button refused."""
    players = FakePlayers(started=[PID])
    start_in_guilds(page, site_url, players, in_both(), [MINE, WORK])
    open_you(page)
    card, html = page.locator("#guildCard"), page.locator("html")
    card.get_by_role("button", name="Leave").first.click()
    expect(html).to_have_attribute("data-guild", "confirming")
    expect(card).to_contain_text("Leave the Cobalt Compass Society?")
    guilds_from_there(page, players, [MINE])  # left the other one there
    eventually(page, lambda: page.evaluate("window.__lf.myGuilds().map(g => g.code)") == [CODE])
    expect(html).to_have_attribute("data-guild", "confirming")
    expect(card).to_contain_text("Leave the Cobalt Compass Society?")
    card.get_by_role("button", name="Leave", exact=True).click()
    expect(html).to_have_attribute("data-guild", "out")
    assert errors == []


def test_a_guild_list_from_there_while_naming_one_here_keeps_both(page: Page, site_url, errors):
    """A list that came while this device was naming a guild used to be skipped, and the guild
    started here then went up as the whole list, dropping the one joined there everywhere."""
    players = FakePlayers(started=[PID])
    guilds = in_cobalt()
    start_in_guilds(page, site_url, players, guilds, [])
    open_you(page)
    card, html = page.locator("#guildCard"), page.locator("html")
    card.get_by_role("button", name="Start a guild").click()
    expect(html).to_have_attribute("data-guild", "naming")
    guilds_from_there(page, players, [MINE])
    eventually(page, lambda: page.evaluate("window.__lf.myGuilds().map(g => g.code)") == [CODE])
    expect(html).to_have_attribute("data-guild", "naming")
    card.get_by_role("button", name="Start it").click()
    expect(html).to_have_attribute("data-guild", "in")
    made = next(code for code in guilds.guilds if code != CODE)
    assert [g["code"] for g in stored(page)] == [CODE, made]
    eventually(
        page, lambda: [g["code"] for g in players.players[PID]["settings"]["guilds"]] == [CODE, made], timeout_ms=8000
    )
    assert errors == []


def test_a_tab_left_on_the_old_surveyor_starts_again_as_the_new_one(page: Page, site_url, errors):
    """Another tab linked (or recovered) and became another surveyor. This one used to sync on as the
    old self, whose Player says syncing has stopped, and so turned syncing off for the whole browser."""
    players = FakePlayers(started=[PID])
    start(page, site_url, players)
    eventually(page, lambda: len(players.sent()) >= 1)
    new = "e" * 32
    players.start(player_id(new))
    other = page.context.new_page()
    other.goto(f"{site_url}/letterfield?survey={SURVEY}")
    # What linking leaves behind: the new token, and syncing from here.
    other.evaluate(
        "t => { localStorage.setItem('letterfield.sync.v1', JSON.stringify({ on: true, epoch: '', at: 0, f: [], n: [], settingsAt: 1 })); localStorage.setItem('games.player', t); }",
        new,
    )
    page.wait_for_function(f"window.__lf && window.__lf.pid() === '{player_id(new)}'")
    page.evaluate("window.__lf.syncNow()")
    eventually(page, lambda: any(b["token"] == new for b in players.sent()))
    assert page.evaluate("localStorage.getItem('letterfield.sync.v1')") is not None
    assert all(b["token"] == new for b in players.sent()[1:])
    other.close()
    assert errors == []


def test_a_receipt_that_comes_while_its_find_is_going_up_goes_up_after(page: Page, site_url, errors):
    """A find that changed while the sync sending it was out was taken off what's waiting when the
    reply came, so its receipt (or charted first) never reached the other devices."""
    mine = words(page, site_url, 1)
    players = FakePlayers(started=[PID])
    held = Held(players, lambda r: r.url.endswith("/v1/player/sync"))
    held.holding = False
    fake = FakeSurvey(lose="claim")  # its claim goes unanswered, so nothing else changes it
    start(page, site_url, players, finds=mine, fake=fake, held=held)
    held.holding = True
    held.wait_for(page, timeout_ms=10_000)
    key = page.evaluate("[...window.__lf.found.keys()][0]")
    signed = receipt(NOW_MS, "f")
    eventually(page, lambda: "0,0" in fake.sockets)
    fake.sockets["0,0"].send(json.dumps({"t": "signed", "k": key, "r": signed}))
    page.wait_for_function("k => window.__lf.found.get(k).r", arg=key)
    held.release()
    eventually(
        page, lambda: any(f.get("r") == signed for f, _ in players.players[PID]["finds"].values()), timeout_ms=8000
    )
    assert errors == []


def test_initials_signed_in_another_game_reach_the_linked_devices(page: Page, site_url, errors):
    """The other games share the initials. A change from one never reached the linked devices, and
    their next change of settings brought the old initials back, in every game."""
    players = FakePlayers(started=[PID])
    start(page, site_url, players)
    eventually(page, lambda: len(players.sent()) >= 1)
    page.wait_for_function("window.__lf.sync() === 'idle'")
    other = page.context.new_page()
    other.goto(f"{site_url}/")
    other.evaluate("localStorage.setItem('games.initials', JSON.stringify('BOB'))")  # a score saved in another game
    expect(page.locator("#surveyMeName")).to_have_text("BOB")
    eventually(page, lambda: (players.players[PID]["settings"] or {}).get("initials") == "BOB", timeout_ms=8000)
    # And one changed while Letterfield wasn't open is seen when it next is.
    page.goto("about:blank")
    other.evaluate("localStorage.setItem('games.initials', JSON.stringify('SUE'))")
    page.goto(f"{site_url}/letterfield?survey={SURVEY}#debug")
    eventually(page, lambda: (players.players[PID]["settings"] or {}).get("initials") == "SUE", timeout_ms=8000)
    other.close()
    assert errors == []


def test_supernovas_from_a_linked_device_are_kept_with_your_own_first(page: Page, site_url, errors):
    """The game kept 200 supernovas to the Player's 1,000, the newest whoever's they were, and
    stored the whole list again for each one a sync brought: your own last word could fall out of
    your notes behind strangers' far-off ones, and a big sync wrote storage a thousand times."""

    def nova(i: int, **kw) -> dict:
        return {"rx": i, "ry": 50, "t": 1_700_000_000_000 + i, "w": "WORD", "x": 0, "y": 0, "d": 0, "by": "ZED", **kw}

    mine = nova(-1, mine=True, solo=False, by="")  # the oldest of all
    page.add_init_script(f"""
      if (location.protocol.startsWith('http') && !localStorage.getItem('letterfield.novas.v1'))
        localStorage.setItem('letterfield.novas.v1', {json.dumps(json.dumps([mine]))});
      window.__novaWrites = 0;
      const set = Storage.prototype.setItem;
      Storage.prototype.setItem = function (k, v) {{ if (k === 'letterfield.novas.v1') window.__novaWrites++; return set.call(this, k, v); }};
    """)
    players = FakePlayers(started=[PID])
    players.add(PID, novas=[nova(i) for i in range(1000)])
    start(page, site_url, players)
    page.wait_for_function("window.__lf.novas().length === 1000")
    kept = page.evaluate("window.__lf.novas().map(n => n.rx)")
    assert -1 in kept and 0 not in kept  # yours stays; the oldest of the others' goes
    assert page.evaluate("window.__novaWrites") <= 2
    assert errors == []
