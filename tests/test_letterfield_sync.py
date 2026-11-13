"""Letterfield's syncing of linked devices, against the survey's fakes.

Linking turns it on (tests/test_letterfield_linking.py links); from then on
the game sends what changed here and takes in what changed on the player's
other devices. tests/fake_survey.py's FakePlayers answers the Worker's sync
paths; the real Player is tested in worker/test/players.test.js.
"""

from __future__ import annotations

import json

from playwright.sync_api import Page, expect

from fake_survey import FakeGuilds, FakeLinks, FakePlayers, FakeSurvey
from test_letterfield_guilds import MINE
from test_letterfield_guilds import start as start_guilds
from test_letterfield_survey import SURVEY, eventually, open_you
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
) -> None:
    """Opens the game with our token and `finds` in the notes, synced through `players` as
    a link leaves it (every find waiting to go up), or not synced at all."""
    page.route(f"{SURVEY}/v1/player/**", players.handle)
    page.route(f"{SURVEY}/v1/link**", (links or FakeLinks(players=players)).handle)
    start_guilds(page, site_url, FakeSurvey(), FakeGuilds())
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
    page.goto(f"{site_url}/letterfield#debug")
    hidden = page.evaluate("window.__lf.chunk(0, 0).words.map(o => [o.w, o.x, o.y, o.d])")
    return [
        {"w": w, "x": x, "y": y, "d": d, "t": 1_700_000_000_000 + i, "s": 0}
        for i, (w, x, y, d) in enumerate(hidden[:n])
    ]


def noted(page: Page) -> list[str]:
    return page.evaluate("[...window.__lf.found.values()].map(e => e.w).sort()")


def test_a_device_never_linked_keeps_everything_here(page: Page, site_url, errors):
    players = FakePlayers()
    start(page, site_url, players, synced=False)
    expect(page.locator("html")).to_have_attribute("data-sync", "off")
    page.locator("#whoListed").evaluate("e => e.click()")
    page.wait_for_timeout(3000)
    assert players.calls == []
    expect(page.locator("#syncText")).to_have_text("Saved in this browser")
    assert errors == []


def test_finds_and_settings_go_both_ways(page: Page, site_url, errors):
    mine, theirs = words(page, site_url, 3)[:2], words(page, site_url, 3)[2]
    players = FakePlayers(started=[PID])
    # The other device sent a find already, charted first.
    players.add(PID, finds=[{**theirs, "f": 1, "n": 77}])
    start(page, site_url, players, finds=mine)
    expect(page.locator("#syncText")).to_have_text("Synced with your linked devices")
    eventually(page, lambda: len(players.sent()) >= 1)
    first = players.sent()[0]
    assert first["since"] == 0 and first["settingsAt"] == 1
    assert first["settings"] == {"initials": "MLW", "guild": None, "muted": [], "listed": True, "emotes": True}
    page.wait_for_function(f"window.__lf.found.size === {len(mine) + 1}")
    assert noted(page) == sorted([f["w"] for f in mine] + [theirs["w"]])
    assert page.evaluate(f"[...window.__lf.found.values()].find(e => e.w === '{theirs['w']}').f") == 1
    # Every find is up there now; the game says so in its notes too.
    assert sorted(f["w"] for f in first["finds"]) == sorted(f["w"] for f in mine)
    saved = json.loads(page.evaluate("localStorage.getItem('letterfield.sync.v1')"))
    assert saved["f"] == [] and saved["at"] == 2 and saved["epoch"] == players.players[PID]["epoch"]

    # A change here goes up soon after...
    page.locator("#whoListed").evaluate("e => e.click()")
    eventually(page, lambda: players.players[PID]["settings"]["listed"] is False, timeout_ms=8000)
    # ...and one there comes down: new initials, a mute and a guild.
    at = page.evaluate("Date.now()")  # just after our own change, so an echo of it would be later still
    players.add(
        PID,
        settings={"initials": "ZED", "guild": MINE, "muted": [KIM[0]], "listed": False, "emotes": True},
        settings_at=at,
    )
    page.evaluate("window.__lf.syncNow()")
    expect(page.locator("#surveyMeName")).to_have_text("ZED")
    expect(page.locator("html")).to_have_attribute("data-guild", "in")
    assert page.evaluate("window.__lf.muted()") == [KIM[0]]
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
    expect(page.locator("#pairHead")).to_have_text("Devices · backed up and in step")
    card.get_by_role("button", name="Stop syncing").click()
    expect(card).to_contain_text("Stop syncing this device, or every device?")
    card.get_by_role("button", name="Keep syncing").click()
    card.get_by_role("button", name="Stop syncing").click()
    card.get_by_role("button", name="This device").click()
    expect(page.locator("html")).to_have_attribute("data-sync", "off")
    expect(card).to_contain_text("Syncing stopped on this device.")
    expect(page.locator("#syncText")).to_have_text("Saved in this browser")
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


def test_stopped_elsewhere_stops_here_too(page: Page, site_url, errors):
    start(page, site_url, FakePlayers())  # nothing started for us: stopped on every device
    expect(page.locator("html")).to_have_attribute("data-sync", "off", timeout=8000)
    expect(page.locator("#toast b")).to_have_text("Syncing has stopped")
    assert page.evaluate("localStorage.getItem('letterfield.sync.v1')") is None
    expect(page.locator("#syncText")).to_have_text("Saved in this browser")
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
