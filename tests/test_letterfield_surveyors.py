"""Letterfield's surveyor list and emotes, against the survey's fakes.

The list is a fold of the survey panel, fetched from GET /v1/survey/surveyors
(tests/fake_survey.py answers it); emotes go out and come back on the sector
sockets. The real Worker's side is tested in worker/test/survey-social.test.js.
The game starts at cell (6, 6), territory (0, 0) of sector (0, 0).
"""

from __future__ import annotations

import hashlib
import re

from playwright.sync_api import Page, expect

from fake_survey import FakeSurvey
from test_letterfield_survey import eventually, open_game, open_people, open_you

TOKEN = "0" * 31 + "1"  # this browser's player token, as the game would make one
PID = hashlib.sha256(f"games-player:{TOKEN}".encode()).hexdigest()[:12]  # and the id the sectors give it

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
    expect(page.locator("#whoStatus")).to_have_text("5 other surveyors in the shared world, nearest first")
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
    assert errors == []


def test_an_emote_goes_from_a_row_and_says_what_became_of_it(page: Page, site_url, errors):
    fake = FakeSurvey(surveyors=[KIM, ZED, SAM], presence=[KIM_CARET])
    start(page, site_url, fake)
    open_list(page)
    page.get_by_role("button", name="More for ZED").click()
    expect(page.get_by_role("button", name="More for ZED")).to_have_attribute("aria-expanded", "true")
    expect(page.locator(".who-emotes .emote")).to_have_count(6)  # wave sits on the row itself
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
    page.get_by_role("button", name="Nice to KIM").click()
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
    expect(page.locator("#findSay")).to_have_text("KIM waved")
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


def test_the_list_and_emote_switches_tell_every_sector_and_are_remembered(page: Page, site_url, errors):
    fake = FakeSurvey(surveyors=[KIM], presence=[KIM_CARET])
    start(page, site_url, fake)
    open_list(page)
    sectors = {"-1,-1", "-1,0", "0,-1", "0,0"}
    eventually(page, lambda: {m["sector"] for m in fake.sent("me")} == sectors)
    assert all(m["token"] == TOKEN and "hide" not in m and "quiet" not in m for m in fake.sent("me"))

    def latest() -> dict:
        return {m["sector"]: m for m in fake.sent("me")}

    open_you(page)  # the switches are on your page
    page.uncheck("#whoListed")
    eventually(page, lambda: all(m.get("hide") for m in latest().values()))
    expect(page.locator("#whoStatus")).not_to_contain_text("off the list")  # the unticked box says so
    page.uncheck("#whoEmotes")
    eventually(page, lambda: all(m.get("hide") and m.get("quiet") for m in latest().values()))
    fake.emote("0,0", KIM[0], "KIM", "wave", [0, 0])
    page.wait_for_timeout(400)
    assert page.evaluate("window.__lf.pops()") == []

    fake.received.clear()
    page.reload()
    eventually(page, lambda: len(fake.sent("me")) == 4)
    assert all(m["hide"] is True and m["quiet"] is True and m["token"] == TOKEN for m in fake.sent("me"))
    open_list(page)
    expect(page.locator("#whoListed")).not_to_be_checked()
    expect(page.locator("#whoEmotes")).not_to_be_checked()
    assert errors == []


def test_presence_by_player_id_never_shows_us_to_ourselves(page: Page, site_url, errors):
    fake = FakeSurvey(presence=[[PID, "MLW", 6.0, 6.0], KIM_CARET])
    start(page, site_url, fake)
    expect(page.locator("#surveyText")).to_contain_text("Live · 1 other surveyor nearby")
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
    # On a phone the title is LF, and still Letterfield to a screen reader.
    expect(page.locator(".brand-short")).to_have_text("LF")
    expect(page.locator(".brand-short")).to_be_visible()
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
    # The list is just people, you first: what's yours waits on your page.
    expect(you).to_contain_text("MLW (you)")
    expect(you).to_contain_text("On the list · emotes on · this device only")
    for mine in ("#surveyMe", "#guildCard", "#pairCard", "#whoListed", "#whoEmotes"):
        expect(page.locator(mine)).to_be_hidden()
    you.click()
    expect(html).to_have_attribute("data-people-page", "you")
    expect(page.locator("#youBack")).to_be_focused()
    expect(page.locator("#peopleList")).to_be_hidden()
    expect(page.locator("#surveyMeName")).to_have_text("MLW")
    expect(page.locator("#pairHead")).to_have_text("Devices · this device only")
    page.uncheck("#whoListed")
    # Back to the list, with focus on the row that opened it, which says what changed.
    page.locator("#youBack").click()
    expect(html).to_have_attribute("data-people-page", "list")
    expect(you).to_be_focused()
    expect(you).to_contain_text("Off the list · emotes on")
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
