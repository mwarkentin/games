"""Letterfield's surveyor list and emotes, against the survey's fakes.

The list, in the surveyors' drawer, is fetched from GET /v1/survey/surveyors
(tests/fake_survey.py answers it); emotes go out and come back on the sector
sockets. The real Worker's side is tested in worker/test/survey-social.test.js.
The game starts at cell (6, 6), territory (0, 0) of sector (0, 0).
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Page, expect

from fake_survey import FakeSurvey, player_id
from test_letterfield_survey import eventually, open_game, open_people, open_you

TOKEN = "0" * 31 + "1"  # this browser's player token, as the game would make one
PID = player_id(TOKEN)  # and the id the sectors give it

# Everyone the list names: [id, initials, rx, ry, seconds idle, flags]. The
# fake hands them out in this order; the game puts the nearest first.
KIM = ["3f9a01c27be4", "KIM", 0, 0, 3, 0]
ZED = ["8d22e5a90f13", "ZED", 1, 0, 45, 0]
SAM = ["c41b7e0d9a55", "SAM", -2, 3, 400, 1]  # takes no emotes
LOU = ["17e6b3f04c8a", "LOU", 7, -4, 2, 0]
ANON = ["a90c5d2e61f7", "", 12, 9, 7300, 0]  # never signed
KIM_CARET = [KIM[0], "KIM", 9.5, 7.0]  # KIM's caret, in sector 0,0's presence
SHOWN = re.compile(r"\bshow\b")


def start(page: Page, site_url: str, fake: FakeSurvey, viewport: dict | None = None) -> None:
    """Opens the game on the survey, signed as MLW with our token, past the welcome card."""
    open_game(page, site_url, fake, viewport=viewport)
    page.evaluate(
        "t => { localStorage.setItem('games.initials', '\"MLW\"'); localStorage.setItem('letterfield.coach.v1', '1');"
        " localStorage.setItem('games.player', t); localStorage.removeItem('letterfield.cam.v1'); }",
        TOKEN,
    )
    fake.received.clear()  # what the first load, with a token of its own, sent
    page.reload()
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    page.wait_for_function(f"window.__lf.pid() === '{PID}'")


def open_list(page: Page) -> None:
    open_people(page)
    expect(page.locator("html")).to_have_attribute("data-who", "ready")


def wait_landed(page: Page, x: float, y: float) -> None:
    page.wait_for_function(
        "([x, y]) => Math.hypot(window.__lf.cam.x - x, window.__lf.cam.y - y) < .6", arg=[x, y], timeout=10_000
    )


def name_of(page: Page, rx: int, ry: int) -> str:
    return page.evaluate("([rx, ry]) => window.__lf.territoryName(rx, ry)", [rx, ry])


def test_the_list_names_everyone_nearest_first_and_flies_to_them(page: Page, site_url, errors):
    fake = FakeSurvey(surveyors=[LOU, KIM, ANON, SAM, ZED], presence=[KIM_CARET, [ZED[0], "ZED", 60.5, 10.0]])
    start(page, site_url, fake)
    open_list(page)
    expect(page.locator(".who-ini")).to_have_text(["KIM", "ZED", "SAM", "LOU", "···"])
    expect(page.locator(".who-meta")).to_have_text(
        [
            "in your territory · active",
            "1 territory away · idle",
            "3 territories away · idle 6m · no emotes",
            "7 territories away · active",
            "12 territories away · idle 2h",
        ]
    )
    expect(page.locator(".who-where").nth(3)).to_have_text(name_of(page, 7, -4))
    expect(page.locator("#whoStatus")).to_have_text("5 other surveyors online, nearest first")
    assert fake.list_asks[-1] == {"r": "0,0", "page": "0", "me": PID}  # asked from where we are, leaving us out

    # A row flies there: straight to the caret when one of our sectors shows it...
    page.locator(".who").nth(1).click()
    wait_landed(page, 60.5, 10.0)
    # ...and otherwise to the middle of their territory.
    page.get_by_role("button", name=re.compile(r"^LOU, ")).click()
    wait_landed(page, 7.5 * 48, -3.5 * 48)
    expect(page.locator(".who-ini").first).to_have_text("LOU")  # nearest first, from where we are now

    # Put away, it stops asking.
    page.locator("#peopleClose").click()
    expect(page.locator("html")).to_have_attribute("data-who", "closed")
    assert errors == []


def test_more_surveyors_come_a_page_at_a_time(page: Page, site_url, errors):
    many = [[f"{i:012x}", "ABC", i // 8, 0, 0, 0] for i in range(1, 46)]
    fake = FakeSurvey(surveyors=many)
    start(page, site_url, fake)
    open_list(page)
    expect(page.locator(".who-row")).to_have_count(40)
    page.click("#whoMore")
    expect(page.locator(".who-row")).to_have_count(45)
    expect(page.locator("#whoMore")).to_be_hidden()
    # Opened again, it starts from the first page: every refresh kept asking for all it had shown.
    page.locator("#peopleClose").click()
    expect(page.locator("html")).to_have_attribute("data-who", "closed")
    expect(page.locator("#people")).to_be_hidden()
    fake.list_asks.clear()
    open_list(page)
    expect(page.locator(".who-row")).to_have_count(40)
    assert [a["page"] for a in fake.list_asks] == ["0"]
    assert errors == []


def test_an_emote_goes_from_a_row_and_says_what_became_of_it(page: Page, site_url, errors):
    fake = FakeSurvey(surveyors=[KIM, ZED, SAM], presence=[KIM_CARET])
    start(page, site_url, fake)
    open_list(page)
    page.get_by_role("button", name="More for ZED").click()
    expect(page.get_by_role("button", name="More for ZED")).to_have_attribute("aria-expanded", "true")
    # Each named under its icon (wave sits on the row itself), in two rows.
    emotes = page.locator(".who-emotes .emote")
    expect(emotes).to_have_text(["Thanks", "Thumbs up", "Clap", "Great find", "Over here", "Question"])
    assert len({round(b["y"]) for b in (e.bounding_box() for e in emotes.all())}) == 2
    page.get_by_role("button", name="Thanks to ZED").click()
    eventually(page, lambda: fake.sent("emote"))
    # From the sector under the middle of the view, toward ZED's (territory 1,0 is in sector 0,0).
    assert fake.sent("emote")[-1] == {"t": "emote", "to": ZED[0], "e": "thanks", "s": [0, 0], "sector": "0,0"}
    expect(page.locator(".who-said:not(:empty)")).to_have_text("Thanks: sent to ZED.")

    # To a caret in view, it pops there for us too.
    page.get_by_role("button", name="More for KIM").click()
    expect(page.locator(".who-emotes")).to_have_count(1)  # one row of emotes open at a time
    page.get_by_role("button", name="Wave to KIM").click()
    page.wait_for_function(f"window.__lf.pops().some(p => p[0] === '{KIM[0]}' && p[1] === 'wave')")
    fake.emote_error = "off"
    page.get_by_role("button", name="Clap to KIM").click()
    expect(page.locator(".who-said:not(:empty)")).to_have_text("KIM isn’t taking emotes.")
    fake.emote_error = "slow down"
    page.get_by_role("button", name="Thumbs up to KIM").click()
    expect(page.locator(".who-said:not(:empty)")).to_have_text("Too quick: try again in a moment.")

    # Escape folds the row, and leaves the drawer open.
    page.keyboard.press("Escape")
    expect(page.locator(".who-emotes")).to_have_count(0)
    expect(page.get_by_role("button", name="More for KIM")).to_be_focused()
    expect(page.locator("#people")).to_be_visible()

    # Someone who takes no emotes can still be muted, but not sent one.
    page.get_by_role("button", name="More for SAM").click()
    expect(page.locator(".who-emotes .emote").first).to_be_disabled()
    expect(page.locator(".who-said:not(:empty)")).to_have_text("SAM isn’t taking emotes.")
    assert errors == []


def test_an_emote_pops_from_a_caret_in_view_or_comes_as_a_note_with_a_way_there(page: Page, site_url, errors):
    fake = FakeSurvey(presence=[KIM_CARET])
    start(page, site_url, fake)
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}')")
    toast = page.locator("#toast")

    fake.emote("0,0", KIM[0], "KIM", "wave", [0, 0])
    page.wait_for_function(f"window.__lf.pops().some(p => p[0] === '{KIM[0]}')")
    expect(page.locator("#findSay")).to_have_text("KIM waves")
    expect(toast).not_to_have_class(SHOWN)

    fake.emote("0,0", LOU[0], "LOU", "great", [7, -4])
    expect(toast).to_have_class(SHOWN)
    expect(toast.locator("b")).to_have_text("LOU says great find")
    expect(toast.locator("span")).to_have_text(f"{name_of(page, 7, -4)} · 7 territories away")
    toast.get_by_role("button", name="Fly to LOU").click()
    wait_landed(page, 7.5 * 48, -3.5 * 48)

    # Anything that isn't one of the emotes, or from no one, is ignored.
    for frame in (["0,0", LOU[0], "LOU", "kiss", [7, -4]], ["0,0", "not-an-id", "LOU", "wave", [7, -4]]):
        fake.emote(*frame)
    page.wait_for_timeout(300)
    assert page.evaluate("window.__lf.pops()") == []
    assert errors == []


def test_muting_hides_a_surveyors_caret_and_emotes_and_is_remembered(page: Page, site_url, errors):
    fake = FakeSurvey(surveyors=[KIM], presence=[KIM_CARET])
    start(page, site_url, fake)
    open_list(page)
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}')")
    page.get_by_role("button", name="More for KIM").click()
    page.get_by_role("button", name="Mute KIM").click()
    expect(page.locator(".who-row")).to_have_class(re.compile(r"\bmuted\b"))
    expect(page.locator(".who-meta")).to_have_text("in your territory · muted")
    page.wait_for_function(f"!window.__lf.carets().includes('{KIM[0]}')")
    fake.emote("0,0", KIM[0], "KIM", "wave", [0, 0])
    page.wait_for_timeout(400)
    assert page.evaluate("window.__lf.pops()") == []
    expect(page.locator("#toast")).not_to_have_class(SHOWN)

    # Remembered on this device.
    page.reload()
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert page.evaluate("window.__lf.muted()") == [KIM[0]]
    page.wait_for_timeout(500)
    assert KIM[0] not in page.evaluate("window.__lf.carets()")
    open_list(page)
    page.get_by_role("button", name="More for KIM").click()
    expect(page.locator(".who-emotes .emote")).to_have_count(0)  # nothing to send someone muted
    page.get_by_role("button", name="Unmute KIM").click()
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}')")
    assert errors == []


def test_everyone_is_listed_and_the_emote_switch_tells_every_sector(page: Page, site_url, errors):
    # A switch to keep off the list, left off from before it went, asks for nothing, and goes.
    page.add_init_script("localStorage.setItem('letterfield.listed.v1', '0')")
    fake = FakeSurvey(surveyors=[KIM], presence=[KIM_CARET])
    start(page, site_url, fake)
    open_list(page)
    sectors = {"-1,-1", "-1,0", "0,-1", "0,0"}
    eventually(page, lambda: {m["sector"] for m in fake.sent("me")} == sectors)
    assert all(m["token"] == TOKEN and "hide" not in m and "quiet" not in m for m in fake.sent("me"))
    assert page.evaluate("localStorage.getItem('letterfield.listed.v1')") is None

    def latest() -> dict:
        return {m["sector"]: m for m in fake.sent("me")}

    open_you(page)  # the switch is on your page, the only one there now
    expect(page.locator("#peopleYou .sw")).to_have_count(1)
    page.uncheck("#whoEmotes")
    eventually(page, lambda: all(m.get("quiet") for m in latest().values()))
    fake.emote("0,0", KIM[0], "KIM", "wave", [0, 0])
    page.wait_for_timeout(400)
    assert page.evaluate("window.__lf.pops()") == []

    fake.received.clear()
    page.reload()
    eventually(page, lambda: len(fake.sent("me")) == 4)
    assert all(m["quiet"] is True and "hide" not in m and m["token"] == TOKEN for m in fake.sent("me"))
    expect(page.locator("#whoEmotes")).not_to_be_checked()
    assert errors == []


def test_the_muted_list_unmutes_anyone_even_once_they_have_gone(page: Page, site_url, errors):
    # ZED was muted before the list kept who anyone was.
    page.add_init_script(f"""if (!sessionStorage.getItem('seeded')) {{
      sessionStorage.setItem('seeded', '1');
      localStorage.setItem('letterfield.muted.v1', JSON.stringify(['{ZED[0]}']));
    }}""")
    fake = FakeSurvey(surveyors=[KIM], presence=[KIM_CARET])
    start(page, site_url, fake)
    open_list(page)
    page.get_by_role("button", name="More for KIM").click()
    page.get_by_role("button", name="Mute KIM").click()
    page.wait_for_function(f"!window.__lf.carets().includes('{KIM[0]}')")
    kept = json.loads(page.evaluate("localStorage.getItem('letterfield.mutedAs.v1')"))
    assert list(kept) == [KIM[0]] and kept[KIM[0]][0] == "KIM"

    # KIM goes, and the page comes back: the list still knows who they were.
    fake.surveyors, fake.presence = [], []
    page.reload()
    open_you(page)
    row = page.locator("#mutedRow")
    expect(row).to_contain_text("Their carets, emotes and come-online notes stay hidden on your devices")
    expect(page.locator("#mutedCount")).to_have_text("2")
    expect(page.locator("#mutedList")).to_be_hidden()
    row.click()
    expect(row).to_have_attribute("aria-expanded", "true")
    rows = page.locator(".muted-row")
    # Newest first; one muted before the list kept names is "A surveyor".
    expect(rows.locator(".muted-ini")).to_have_text(["KIM", "A surveyor"])
    expect(rows.first.locator(".muted-when")).to_have_text(re.compile(r"^Muted [A-Z][a-z]{2} \d{1,2}$"))
    assert rows.first.locator(".pill").bounding_box()["height"] >= 40  # as tall as Change on the same page
    page.get_by_role("button", name="Unmute this surveyor").click()
    expect(rows).to_have_count(1)
    expect(page.get_by_role("button", name="Unmute KIM")).to_be_focused()
    page.get_by_role("button", name="Unmute KIM").click()
    expect(page.locator(".muted-none")).to_contain_text("Nobody’s muted.")
    expect(row).to_be_focused()
    expect(page.locator("#mutedCount")).to_have_text("None")
    assert page.evaluate("window.__lf.muted()") == []
    assert page.evaluate("localStorage.getItem('letterfield.mutedAs.v1')") == "{}"
    assert errors == []


def test_presence_by_player_id_never_shows_us_to_ourselves(page: Page, site_url, errors):
    fake = FakeSurvey(presence=[[PID, "MLW", 6.0, 6.0], KIM_CARET])
    start(page, site_url, fake)
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}')")
    assert page.evaluate("window.__lf.carets()") == [KIM[0]]
    assert errors == []


def test_a_caret_has_a_menu_of_emotes(page: Page, site_url, errors):
    fake = FakeSurvey(presence=[KIM_CARET])
    start(page, site_url, fake)
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}')")
    menu = page.locator("#caretMenu")
    at = page.evaluate(f"window.__lf.caretXY('{KIM[0]}')")
    page.mouse.click(at["x"], at["y"], button="right")
    expect(menu).to_be_visible()
    expect(menu.locator("#caretWho")).to_have_text("KIM")
    expect(menu.get_by_role("button", name="Wave to KIM")).to_be_focused()
    # All seven, each named under its icon, four and three to a row.
    emotes = menu.locator(".emote")
    expect(emotes).to_have_text(["Wave", "Thanks", "Thumbs up", "Clap", "Great find", "Over here", "Question"])
    rows = [round(e.bounding_box()["y"]) for e in emotes.all()]
    assert rows[:4] == [rows[0]] * 4 and rows[4:] == [rows[4]] * 3 and rows[4] > rows[0], rows
    menu.get_by_role("button", name="Over here to KIM").click()
    expect(menu).to_be_hidden()
    eventually(page, lambda: fake.sent("emote"))
    assert fake.sent("emote")[-1] == {"t": "emote", "to": KIM[0], "e": "here", "s": [0, 0], "sector": "0,0"}
    page.wait_for_function(f"window.__lf.pops().some(p => p[0] === '{KIM[0]}' && p[1] === 'here')")

    # Escape puts it away, back to the map; a right-click away from any caret opens nothing.
    page.mouse.click(at["x"], at["y"], button="right")
    expect(menu).to_be_visible()
    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()
    expect(page.locator("#map")).to_be_focused()
    page.mouse.click(at["x"] - 150, at["y"] + 120, button="right")
    expect(menu).to_be_hidden()
    assert errors == []


PRESSED = """() => ['#toolsBtn', '#peopleBtn', '#notesToggle'].filter(s => document.querySelector(s).getAttribute('aria-expanded') === 'true')"""
SETTLED_BG = "e => Promise.all(e.getAnimations().map(a => a.finished)).then(() => getComputedStyle(e).backgroundColor)"


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_the_corner_opens_one_panel_at_a_time(page: Page, site_url, errors, size):
    """Tools, Surveyors and field notes could be open together, each button pressed; the notes
    button never showed pressed at all."""
    start(page, site_url, FakeSurvey(surveyors=[KIM]), viewport={"width": size[0], "height": size[1]})
    html, desk = page.locator("html"), size[0] >= 1100
    # A computer opens with the notes docked; on a phone, open them.
    if not desk:
        page.click("#notesToggle")
    expect(page.locator("body")).to_have_class(re.compile(r"\bnotes-open\b"))
    map_width = page.locator("#map").bounding_box()["width"]

    page.click("#peopleBtn")  # in the notes' place
    expect(page.locator("#people")).to_be_visible()
    assert page.evaluate(PRESSED) == ["#peopleBtn"]
    expect(page.locator("body")).not_to_have_class(re.compile(r"\bnotes-open\b"))
    if desk:  # docked in the same slot: the map doesn't move
        expect(page.locator("body")).to_have_class(re.compile(r"\bdocked\b"))
        assert page.locator("#map").bounding_box()["width"] == map_width

    page.click("#toolsBtn")
    expect(page.locator("#toolsPanel")).to_be_visible()
    assert page.evaluate(PRESSED) == ["#toolsBtn"]
    expect(page.locator("#people")).to_be_hidden()
    expect(html).to_have_attribute("data-panel", "tools")
    if desk:  # in the same slot too
        expect(page.locator("body")).to_have_class(re.compile(r"\bdocked\b"))
        assert page.locator("#map").bounding_box()["width"] == map_width
    tools_bg = page.locator("#toolsBtn").evaluate(SETTLED_BG)

    # The keys too: N for the notes, P for the Surveyors, each putting away what was open.
    page.locator("#map").focus()
    page.keyboard.press("n")
    expect(html).to_have_attribute("data-panel", "notes")
    assert page.evaluate(PRESSED) == ["#notesToggle"]
    expect(page.locator("#toolsPanel")).to_be_hidden()
    # Open, the notes button shows pressed as the others do, docked or not.
    expect(page.locator("#notesToggle")).to_be_visible()
    assert page.locator("#notesToggle").evaluate(SETTLED_BG) == tools_bg
    page.locator("#map").focus()
    page.keyboard.press("p")
    expect(html).to_have_attribute("data-panel", "people")
    assert page.evaluate(PRESSED) == ["#peopleBtn"]
    # And shut, nothing is.
    page.click("#peopleBtn")
    expect(html).to_have_attribute("data-panel", "none")
    assert page.evaluate(PRESSED) == []
    assert errors == []


# Clicks `sel`, then measures every frame for half a second (past any slide): where the
# corner, the bar and the drawer now open are, how wide the map is, and where it's looking.
WATCH_SWITCH = """async sel => {
  const box = s => { const b = document.querySelector(s).getBoundingClientRect(); return [b.left, b.top, b.width, b.height].map(Math.round); };
  const open = () => ({ notes: '#notes', people: '#people', tools: '#toolsPanel' })[window.__lf.panel()];
  const frames = [];
  document.querySelector(sel).click();
  const t0 = performance.now();
  while (performance.now() - t0 < 500) {
    const c = window.__lf.cam;
    frames.push({ panel: window.__lf.panel(), corner: box('.corner'), bar: box('#bar'), map: window.__lf.mapWidth(),
      cam: [c.x, c.y, c.cs].map(v => +v.toFixed(3)), drawer: box(open()), toast: getComputedStyle(document.getElementById('toast')).right });
    await new Promise(requestAnimationFrame);
  }
  return frames;
}"""


def test_moving_between_the_corners_panels_on_a_computer_moves_nothing(page: Page, site_url, errors):
    """With the notes docked, opening the tools put the notes away: the map widened and
    moved, and the buttons, the bar and the notes slid right by the drawer's width, then
    back as the Surveyors docked in their place. Now notes, tools and Surveyors share the
    one place beside the map: from one to the next, the map, the corner, the bar and where a
    note pops up hold still, and the new drawer is in place from its first frame, not
    sliding in."""
    start(page, site_url, FakeSurvey(surveyors=[KIM]), viewport={"width": 1280, "height": 900})
    expect(page.locator("html")).to_have_attribute("data-panel", "notes")
    page.wait_for_timeout(400)  # the first frames settled
    before = page.evaluate(WATCH_SWITCH.replace("document.querySelector(sel).click();", ""), "")[-1]
    assert before["map"] == 1280 - 340 and before["drawer"] == [939, 0, 341, 900], before  # 340 wide, and its border
    for sel, panel in [
        ("#toolsBtn", "tools"),
        ("#peopleBtn", "people"),
        ("#notesToggle", "notes"),
        ("#toolsBtn", "tools"),
    ]:
        frames = page.evaluate(WATCH_SWITCH, sel)
        assert all(f["panel"] == panel for f in frames), (sel, frames[0])
        for f in frames:
            for k in ("corner", "bar", "map", "cam", "drawer", "toast"):
                assert f[k] == before[k], (sel, k, f[k], before[k])
    # The tools' own button shuts them, and the drawer they stood in for (the notes) is back.
    frames = page.evaluate(WATCH_SWITCH, "#toolsBtn")
    assert frames[-1]["panel"] == "notes" and frames[-1]["corner"] == before["corner"]
    assert errors == []


@pytest.mark.parametrize("width", [700, 768])
def test_on_a_tablet_the_title_makes_way_for_the_surveyors(page: Page, site_url, errors, width):
    """On a tablet the Surveyors drawer opens over the map in the notes' place, and covered the
    end of the title box (the territory's grid reference and count), which the notes never do."""
    start(page, site_url, FakeSurvey(surveyors=[KIM]), viewport={"width": width, "height": 1024})
    expect(page.locator(".brand")).to_be_visible()  # with the drawer shut, the title shows
    page.click("#peopleBtn")
    page.locator("#people").evaluate("e => Promise.all(e.getAnimations().map(a => a.finished))")
    m = page.evaluate("""() => { const box = s => document.querySelector(s).getBoundingClientRect();
      return { title: box('.cartouche').right, people: box('#people').left, brand: box('.brand').width }; }""")
    assert m["brand"] <= 1 and m["title"] <= m["people"], m
    expect(page.locator(".t-coord")).to_be_hidden()
    assert errors == []


def test_a_caret_menu_knows_who_takes_no_emotes_and_a_refusal_always_shows(page: Page, site_url, errors):
    """A caret's menu offered emotes to someone who takes none, and closed before the refusal came,
    which then went to a row in the closed list, or only to a screen reader, as "They isn't"."""
    fake = FakeSurvey(surveyors=[KIM, SAM], presence=[KIM_CARET, [SAM[0], "SAM", 13.5, 5.0]])
    start(page, site_url, fake)
    open_list(page)  # the list tells the page SAM takes no emotes
    page.click("#peopleBtn")
    expect(page.locator("#people")).to_be_hidden()
    page.wait_for_function(f"['{KIM[0]}', '{SAM[0]}'].every(id => window.__lf.carets().includes(id))")
    menu = page.locator("#caretMenu")
    at = page.evaluate(f"window.__lf.caretXY('{SAM[0]}')")
    page.mouse.click(at["x"], at["y"], button="right")
    expect(menu.locator("#caretWho")).to_have_text("SAM")
    expect(menu.locator(".emote:not(:disabled)")).to_have_count(0)
    expect(menu.locator(".who-said")).to_have_text("SAM isn’t taking emotes.")
    page.keyboard.press("Escape")
    # KIM turned emotes off since the list last heard: the refusal still shows, as a note.
    fake.emote_error = "off"
    at = page.evaluate(f"window.__lf.caretXY('{KIM[0]}')")
    page.mouse.click(at["x"], at["y"], button="right")
    menu.get_by_role("button", name="Thanks to KIM").click()
    expect(menu).to_be_hidden()
    expect(page.locator("#toast b")).to_have_text("KIM isn’t taking emotes.")
    assert errors == []


def test_an_emote_from_a_caret_menu_that_cant_go_says_why(page: Page, site_url, errors):
    """With the middle of the view over a crowded sector and a caret shown from a live one beside it,
    an emote from the caret's menu wrote why it couldn't go into the menu, which then shut at once."""
    fake = FakeSurvey(presence=[KIM_CARET], full={"-1,0": "sector"})
    start(page, site_url, fake)
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}')")
    page.evaluate("window.__lf.cam.x = -0.5")  # the middle of the view steps over into the crowded sector
    assert page.evaluate("window.__lf.linkStates()")["-1,0"] != "live"
    menu = page.locator("#caretMenu")
    at = page.evaluate(f"window.__lf.caretXY('{KIM[0]}')")
    page.mouse.click(at["x"], at["y"], button="right")
    menu.get_by_role("button", name="Wave to KIM").click()
    expect(menu).to_be_hidden()
    expect(page.locator("#toast")).to_have_class(SHOWN)
    expect(page.locator("#toast b")).to_have_text("Join the survey to send emotes.")
    assert fake.sent("emote") == []
    assert errors == []


@pytest.mark.browser_context_args(has_touch=True, is_mobile=True)
def test_a_long_press_on_a_caret_opens_its_menu_not_a_selection(page: Page, site_url, errors):
    fake = FakeSurvey(presence=[KIM_CARET])
    start(page, site_url, fake, viewport={"width": 375, "height": 740})
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}')")
    # A phone's own long press selects text or shows its copy callout, which cancels the game's
    # press; no iPhone runs here, so check the rules that stop it: the page isn't selectable, and
    # what players copy by hand still is.
    assert page.evaluate("getComputedStyle(document.body).userSelect") == "none"
    assert page.evaluate("getComputedStyle(document.querySelector('#notes')).userSelect") == "text"
    assert page.evaluate("getComputedStyle(document.querySelector('#people')).userSelect") == "text"

    cdp = page.context.new_cdp_session(page)

    def touch(kind: str, x: float, y: float) -> None:
        points = [] if kind == "touchEnd" else [{"x": x, "y": y}]
        cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})

    menu = page.locator("#caretMenu")
    at = page.evaluate(f"window.__lf.caretXY('{KIM[0]}')")
    touch("touchStart", at["x"], at["y"])
    page.wait_for_timeout(800)  # past the game's long press
    touch("touchEnd", at["x"], at["y"])
    expect(menu).to_be_visible()
    expect(menu.locator("#caretWho")).to_have_text("KIM")
    assert page.evaluate("String(getSelection())") == ""

    # Letting go moves focus to the map, so another touch, away from the caret, puts it away.
    touch("touchStart", at["x"] - 150, at["y"] + 120)
    touch("touchEnd", at["x"] - 150, at["y"] + 120)
    expect(menu).to_be_hidden()
    assert errors == []


def test_the_list_says_when_it_cant_be_loaded(page: Page, site_url, errors):
    fake = FakeSurvey(list_status=503)
    start(page, site_url, fake)
    open_people(page)
    expect(page.locator("html")).to_have_attribute("data-who", "failed")
    expect(page.locator("#whoStatus")).to_have_text("Couldn’t load the list. Trying again shortly.")
    expect(page.locator(".who-row")).to_have_count(0)
    # The browser logs the failed request; the game says so itself and carries on.
    assert [e for e in errors if "503" not in e and "surveyors" not in e] == []


def test_the_list_fits_a_phone(page: Page, site_url, errors):
    fake = FakeSurvey(surveyors=[KIM, ZED, SAM, LOU, ANON], presence=[KIM_CARET])
    start(page, site_url, fake, viewport={"width": 375, "height": 740})
    open_list(page)
    page.get_by_role("button", name="More for ZED").click()
    page.locator(".who-emotes").scroll_into_view_if_needed()
    sizes = page.evaluate("""() => ({
      page: document.scrollingElement.scrollWidth,
      notes: [document.getElementById('people').scrollWidth, document.getElementById('people').clientWidth],
      emotes: [...document.querySelectorAll('.who-emotes .emote')].map(b => b.getBoundingClientRect().width),
      act: document.querySelector('.who-act').getBoundingClientRect().width,
      wave: document.querySelector('.who-wave').getBoundingClientRect().height,
      rows: [...document.querySelectorAll('.who-row:not(.away) > .who')].map(b => b.getBoundingClientRect().width),
    })""")
    assert sizes["page"] <= 375, sizes
    assert sizes["notes"][0] <= sizes["notes"][1], sizes
    assert min(sizes["emotes"]) >= 36 and sizes["act"] >= 40 and sizes["wave"] >= 40, sizes
    assert min(sizes["rows"]) >= 150, sizes  # room for where they are beside Wave and ⋯
    page.get_by_role("button", name="Wave to ZED").click()
    expect(page.locator(".who-said:not(:empty)")).to_have_text("Wave: sent to ZED.")
    # A row flies there and puts the drawer away, which on a phone covers the map.
    page.get_by_role("button", name=re.compile(r"^LOU, ")).click()
    expect(page.locator("#people")).to_be_hidden()
    wait_landed(page, 7.5 * 48, -3.5 * 48)
    assert errors == []


def test_emotes_move_as_they_arrive_and_hold_still_under_reduced_motion(page: Page, site_url, errors):
    fake = FakeSurvey()
    start(page, site_url, fake)
    # On the map: a wave rocks from the wrist, then settles.
    turn, rise, width, height = page.evaluate("window.__lf.emoteMotion('wave', 180)")
    assert abs(turn) > 5 and (rise, width, height) == (0, 1, 1)
    assert page.evaluate("window.__lf.emoteMotion('wave', 1200)") == [0, 0, 1, 1]
    assert page.evaluate("window.__lf.emoteMotion('great', 400)")[2] > 1  # the sparkle swells
    # In a note, its icon plays the same move.
    fake.emote("0,0", LOU[0], "LOU", "great", [7, -4])
    icon = page.locator("#toast i.emo svg")
    expect(icon).to_be_visible()
    assert icon.evaluate("e => e.getAnimations().map(a => a.animationName)") == ["emo-great"]

    page.emulate_media(reduced_motion="reduce")
    page.reload()
    expect(page.locator("#survey")).to_have_attribute("data-state", "live")
    assert page.evaluate("window.__lf.emoteMotion('wave', 180)") == [0, 0, 1, 1]
    fake.emote("0,0", LOU[0], "LOU", "wave", [7, -4])
    expect(icon).to_be_visible()
    assert icon.evaluate("e => e.getAnimations().length") == 0
    assert errors == []


def test_the_surveyors_have_a_button_and_drawer_of_their_own(page: Page, site_url, errors):
    fake = FakeSurvey(surveyors=[KIM, ZED])
    start(page, site_url, fake, viewport={"width": 375, "height": 740})
    button = page.locator("#peopleBtn")
    expect(button).to_be_visible()
    # Nothing about surveyors is in the field notes now.
    assert page.locator("#notes #whoList, #notes #guildCard, #notes #surveyMe, #notes #pairCard").count() == 0
    # On a phone there's no title, to leave the territory the room; it's still Letterfield to a screen reader.
    assert page.evaluate("document.querySelector('.brand').getBoundingClientRect().width") <= 1
    expect(page.get_by_role("heading", level=1)).to_have_accessible_name("Letterfield")
    # P opens it, with the list; its count comes from the list.
    page.locator("#map").focus()
    page.keyboard.press("p")
    expect(page.locator("#people")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-who", "ready")
    expect(page.locator("#peopleBadge")).to_have_text("2")
    expect(button).to_have_attribute("aria-label", "Surveyors, 2 online")
    # The badge hangs over the notes button's corner, and shows on top of it.
    on_top = page.evaluate("""() => { const b = document.getElementById('peopleBadge').getBoundingClientRect();
      return document.elementFromPoint(b.right - 3, b.top + b.height / 2) === document.getElementById('peopleBadge'); }""")
    assert on_top
    # One sheet at a time on a phone: the notes take its place, and it theirs.
    page.click("#notesToggle")
    expect(page.locator("#notes")).to_be_visible()
    expect(page.locator("#people")).to_be_hidden()
    expect(page.locator("html")).to_have_attribute("data-who", "closed")
    button.click()
    expect(page.locator("#people")).to_be_visible()
    expect(page.locator("#notes")).to_be_hidden()
    # Escape puts it away and gives the button back the focus.
    page.keyboard.press("Escape")
    expect(page.locator("#people")).to_be_hidden()
    expect(button).to_be_focused()
    assert errors == []


def test_your_page_opens_from_the_first_row_and_goes_back(page: Page, site_url, errors):
    fake = FakeSurvey(surveyors=[KIM, ZED], presence=[KIM_CARET])
    start(page, site_url, fake, viewport={"width": 375, "height": 740})
    open_list(page)
    html, you = page.locator("html"), page.locator("#youRow")
    expect(html).to_have_attribute("data-people-page", "list")
    # The list is just people, you first: what's yours waits on your page. Your
    # row names what's there, never how it's set, which shows only on your page.
    expect(you).to_contain_text("MLW (you)")
    expect(you).to_contain_text("Initials, guilds and devices")
    for mine in ("#surveyMe", "#guildCard", "#pairCard", "#mutedRow", "#whoEmotes"):
        expect(page.locator(mine)).to_be_hidden()
    you.click()
    expect(html).to_have_attribute("data-people-page", "you")
    expect(page.locator("#youBack")).to_be_focused()
    expect(page.locator("#peopleList")).to_be_hidden()
    expect(page.locator("#surveyMeName")).to_have_text("MLW")
    expect(page.locator("#pairHead")).to_have_text("Devices")
    page.uncheck("#whoEmotes")
    # Back to the list, with focus on the row that opened it, which doesn't repeat the change.
    page.locator("#youBack").click()
    expect(html).to_have_attribute("data-people-page", "list")
    expect(you).to_be_focused()
    expect(you).not_to_contain_text("emotes")
    expect(you).to_contain_text("Initials, guilds and devices")
    # Escape goes back to the list first, then puts the drawer away.
    you.click()
    page.keyboard.press("Escape")
    expect(html).to_have_attribute("data-people-page", "list")
    expect(you).to_be_focused()
    expect(page.locator("#people")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#people")).to_be_hidden()
    # Shut from your page, it opens on the list again.
    open_you(page)
    page.locator("#youClose").click()
    expect(page.locator("#people")).to_be_hidden()
    expect(page.locator("#peopleBtn")).to_be_focused()
    page.click("#peopleBtn")
    expect(html).to_have_attribute("data-people-page", "list")
    expect(page.locator("#peopleList")).to_be_visible()
    assert errors == []


def test_an_emote_before_signing_opens_your_page_to_sign(page: Page, site_url, errors):
    fake = FakeSurvey(surveyors=[KIM], presence=[KIM_CARET])
    start(page, site_url, fake)
    page.evaluate("localStorage.removeItem('games.initials')")  # say another tab took them away
    open_list(page)
    page.get_by_role("button", name="Wave to KIM").click()
    expect(page.locator("html")).to_have_attribute("data-people-page", "you")
    expect(page.locator("#surveyInitials")).to_be_focused()
    expect(page.locator("#surveyHint")).to_have_text("Sign your initials to send emotes.")
    assert fake.sent("emote") == []
    page.keyboard.type("mlw")
    page.keyboard.press("Enter")
    expect(page.locator("#surveyMeName")).to_have_text("MLW")
    page.locator("#youBack").click()
    page.get_by_role("button", name="Wave to KIM").click()
    eventually(page, lambda: fake.sent("emote"))
    assert errors == []


# Every time the people button's badge hides, as the page sees it.
WATCH_BADGE = """() => { window.__hides = 0; new MutationObserver(() => { if (document.getElementById('peopleBadge').hidden) window.__hides++; })
  .observe(document.getElementById('peopleBadge'), { attributes: true, attributeFilter: ['hidden'] }); }"""


def test_the_badge_counts_everyone_else_by_whether_the_sector_counted_you(page: Page, site_url, errors):
    """The button's count is everyone else online: the world's total less one only when the
    sector says it counted us, so it's right whether or not we're in the total yet."""
    page.clock.install()
    fake = FakeSurvey()
    start(page, site_url, fake)
    badge = page.locator("#peopleBadge")
    expect(badge).to_be_hidden()
    # Our sector counted us and one other.
    fake.totals_to("0,0", 2, you=True)
    expect(badge).to_have_text("1")
    page.evaluate(WATCH_BADGE)
    # Another sector in view, which counts the other surveyor but not us: still one.
    fake.totals_to("-1,0", 2)
    page.clock.run_for(3000)
    expect(badge).to_have_text("1")
    # A total from before our sector reported us (one, the other surveyor): still one, not none.
    fake.totals_to("0,0", 1)
    page.clock.run_for(3000)
    expect(badge).to_have_text("1")
    assert page.evaluate("window.__hides") == 0
    expect(page.locator("#peopleBtn")).to_have_attribute("aria-label", "Surveyors, 1 online")
    assert errors == []


def test_the_badge_holds_through_a_gap_but_goes_when_everyone_has(page: Page, site_url, errors):
    """A count that dips to nothing and comes back within a few seconds (a sector between
    reports, a socket reconnecting) doesn't make the badge blink; one that stays at nothing
    hides it, after BADGE_HOLD_MS. A rise shows at once."""
    page.clock.install()
    fake = FakeSurvey()
    start(page, site_url, fake)
    badge = page.locator("#peopleBadge")
    fake.totals_to("0,0", 2, you=True)
    expect(badge).to_have_text("1")
    page.evaluate(WATCH_BADGE)
    # A gap: just us for a few seconds, then the other surveyor again.
    fake.totals_to("0,0", 1, you=True)
    page.clock.run_for(6000)
    expect(badge).to_have_text("1")
    fake.totals_to("0,0", 3, you=True)
    expect(badge).to_have_text("2")  # at once
    page.clock.run_for(20_000)
    assert page.evaluate("window.__hides") == 0
    # Everyone else really gone: the badge goes once the hold is up, and not before.
    fake.totals_to("0,0", 1, you=True)
    page.clock.run_for(10_000)
    expect(badge).to_have_text("2")
    page.clock.run_for(8000)
    expect(badge).to_be_hidden()
    expect(page.locator("#peopleBtn")).to_have_attribute("aria-label", "Surveyors")
    assert errors == []


def test_the_badge_goes_once_the_survey_cant_be_joined(page: Page, site_url, errors):
    """The count held while no sector was live, meant for a hidden tab or a reconnect, held for
    good once none could be joined: "Surveyors, 2 online" an hour after the survey was gone."""
    page.clock.install()
    fake = FakeSurvey()
    start(page, site_url, fake)
    badge = page.locator("#peopleBadge")
    fake.totals_to("0,0", 3, you=True)
    expect(badge).to_have_text("2")
    # Every sector drops us, and turns us away when we try again.
    fake.full = "sector"
    for ws in list(fake.sockets.values()):
        ws.close()
    page.clock.run_for(5000)
    expect(page.locator("#survey")).to_have_attribute("data-state", "offline")
    expect(badge).to_have_text("2")  # held a moment, as through any gap
    page.clock.run_for(20_000)
    expect(badge).to_be_hidden()
    expect(page.locator("#peopleBtn")).to_have_attribute("aria-label", "Surveyors")
    assert errors == []


def test_the_badge_agrees_with_the_list_when_the_drawer_opens_and_closes(page: Page, site_url, errors):
    """The list's count (others, by id) and the world's total less us are one number, so opening
    the drawer, and the list going stale after it shuts, don't change the badge."""
    page.clock.install()
    fake = FakeSurvey(surveyors=[KIM])
    start(page, site_url, fake)
    badge = page.locator("#peopleBadge")
    fake.totals_to("0,0", 2, you=True)
    expect(badge).to_have_text("1")
    page.evaluate(WATCH_BADGE)
    open_list(page)
    expect(badge).to_have_text("1")
    page.keyboard.press("Escape")
    expect(page.locator("#people")).to_be_hidden()
    page.clock.run_for(130_000)  # the list's count is stale now: the world's total takes over
    expect(badge).to_have_text("1")
    assert page.evaluate("window.__hides") == 0
    assert errors == []
