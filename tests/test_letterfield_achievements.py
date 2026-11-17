"""Letterfield's achievements and days surveyed (see worker/ACHIEVEMENTS.md).

They're worked out from the field notes and supernovas seen, so most tests
seed the notes in localStorage and read what the game made of them through
the debug hook (`window.__lf.marks`). The clock is fixed where the day
matters; every test's browser runs in Toronto's time (tests/conftest.py).
Every test's browser starts with achievement notes quietened
(QUIET_ACHIEVEMENTS in tests/conftest.py), so these turn them on.
"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import Page, expect

from fake_survey import FakePlayers, FakeSurvey
from test_letterfield_survey import LANDS, circle, known_words, open_game
from test_letterfield_surveyors import KIM, PID
from test_letterfield_surveyors import start as start_survey
from test_letterfield_sync import start as start_sync
from test_letterfield_sync import words as sync_words

TORONTO = ZoneInfo("America/Toronto")
NOW = dt.datetime(2026, 11, 17, 15, 0, tzinfo=TORONTO)
ALONE, ON_SURVEY = 30, 39  # achievements in the catalog alone and on the shared survey

# Hidden words in territories (0, 0) and (1, 0), as [w, x, y, d].
WORDS_JS = """() => {
  const out = [];
  for (const [rx, ry] of [[0, 0], [1, 0]])
    for (let cy = ry * 4; cy < ry * 4 + 4; cy++) for (let cx = rx * 4; cx < rx * 4 + 4; cx++)
      for (const o of window.__lf.chunk(cx, cy).words) out.push([o.w, o.x, o.y, o.d]);
  return out;
}"""
# Achievement notes on (tests/conftest.py quietens them), and each note's heading as it appears, in order.
NOTES_JS = """
try { if (location.protocol.startsWith('http')) localStorage.setItem('letterfield.quiet.v1', '[]'); } catch (_) {}
window.__notes = [];
new MutationObserver(() => {
  const t = document.getElementById('toast'), b = t && t.querySelector('b'), last = window.__notes[window.__notes.length - 1];
  if (b && t.classList.contains('show') && b.textContent !== last) window.__notes.push(b.textContent);
}).observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
"""


def find(word: list, when: dt.datetime, **more) -> dict:
    w, x, y, d = word
    return {"w": w, "x": x, "y": y, "d": d, "t": int(when.timestamp() * 1000), "s": 0, **more}


def on_days(words: list, plan: dict[int, int], now: dt.datetime = NOW) -> list[dict]:
    """Finds on the days before `now` that `plan` names ({-2: 3} is three finds the day before yesterday)."""
    out, i = [], 0
    for back, n in sorted(plan.items()):
        day = (now + dt.timedelta(days=back)).replace(hour=10, minute=0)
        for k in range(n):
            out.append(find(words[i], day + dt.timedelta(minutes=k)))
            i += 1
    return out


def open_alone(
    page: Page, site_url: str, finds=(), novas=(), store: dict | None = None, now: dt.datetime | None = None
) -> None:
    """Opens the game alone, with `finds` and `novas` in the notes and `store` in localStorage, as a
    returning player who has never had achievements (unless `store` brings a record)."""
    page.add_init_script(NOTES_JS)
    if now:
        page.clock.set_fixed_time(now)
    open_game(page, site_url, None)
    page.evaluate(
        "([f, n, s]) => { localStorage.removeItem('letterfield.marks.v1'); localStorage.setItem('letterfield.finds.v4', f);"
        " localStorage.setItem('letterfield.novas.v1', n); localStorage.setItem('letterfield.coach.v1', '1');"
        " for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v); }",
        [json.dumps(list(finds)), json.dumps(list(novas)), store or {}],
    )
    page.reload()
    page.wait_for_function("window.__lf && window.__lf.marks")
    if store and "letterfield.quiet.v1" in store:  # NOTES_JS turned them on as the page loaded
        page.evaluate("v => localStorage.setItem('letterfield.quiet.v1', v)", store["letterfield.quiet.v1"])
    page.locator("#bar").click(position={"x": 4, "y": 4})  # a first tap, which lets sound start


def marks(page: Page) -> dict:
    return page.evaluate("window.__lf.marks.state()")


def streak(page: Page) -> dict:
    return page.evaluate("window.__lf.marks.streak()")


def notes(page: Page) -> list[str]:
    return page.evaluate("window.__notes")


def open_page(page: Page) -> None:
    if page.locator("html").get_attribute("data-panel") != "notes":
        page.click("#notesToggle")
    page.click("#marksRow")
    expect(page.locator("html")).to_have_attribute("data-notes-page", "marks")


def test_a_find_earns_first_mark_with_a_note_and_a_chime(page: Page, site_url, errors):
    word = known_words(page, site_url)[0]
    open_alone(page, site_url)
    expect(page.locator("#marksLine")).to_have_text(f"0 of {ALONE}")
    assert marks(page)["got"] == {}

    circle(page, word)
    toast = page.locator("#toast")
    expect(toast.locator("b")).to_have_text("First Mark", timeout=LANDS)
    expect(toast).to_contain_text("Achievement · Circle your first word.")
    # Its badge draws itself in, and it chimes once.
    assert page.evaluate("document.querySelector('#toast .mk-disc').getAnimations().length") > 0
    state = marks(page)
    assert state["got"]["first-mark"][1] == 0  # earned in play, not from older notes
    assert state["sounds"] == 1
    expect(page.locator("#marksLine")).to_have_text(f"1 of {ALONE}")
    expect(page.locator("#marksNew")).to_be_visible()

    # See opens the page at it, marked new; going back says it's been seen.
    toast.get_by_role("button", name="See your achievements").click()
    expect(page.locator("html")).to_have_attribute("data-notes-page", "marks")
    card = page.locator("#mk-first-mark")
    expect(card).to_contain_text("Earned")
    expect(card.locator(".mk-new")).to_have_text("New")
    expect(page.locator("#mk-field-book")).to_contain_text("1 of 100")
    page.click("#marksBack")
    expect(page.locator("html")).to_have_attribute("data-notes-page", "finds")
    expect(page.locator("#marksNew")).to_be_hidden()
    assert marks(page)["fresh"] == []
    assert errors == []


def test_a_returning_player_gets_one_note_for_everything_their_notes_earned(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    long_ago = dt.datetime(2025, 3, 2, 12, 0, tzinfo=TORONTO)
    finds = [find(w, long_ago + dt.timedelta(hours=i)) for i, w in enumerate(words[:120])]
    open_alone(page, site_url, finds)
    toast = page.locator("#toast")
    expect(toast).to_contain_text("Earned from your field notes so far", timeout=LANDS)
    state = marks(page)
    earned = state["got"]
    assert {"first-mark", "field-book", "compass-rose"} <= set(earned)
    assert all(from_notes == 1 for _, from_notes in earned.values())
    expect(toast.locator("b")).to_have_text(f"{len(earned)} achievements")
    # Each is dated by the find that earned it: Field Book by the hundredth.
    assert earned["first-mark"][0] == finds[0]["t"]
    assert earned["field-book"][0] == finds[99]["t"]
    page.wait_for_timeout(2500)
    assert len(notes(page)) == 1
    assert state["sounds"] == 0  # it comes before the first tap, and nothing sounds before one

    open_page(page)
    expect(page.locator("#mk-field-book")).to_contain_text("from your notes")
    # They're kept: coming back plays nothing.
    page.reload()
    page.wait_for_function("window.__lf && window.__lf.marks")
    page.wait_for_timeout(2500)
    assert notes(page) == []
    assert set(marks(page)["got"]) == set(earned)
    assert errors == []


def test_several_at_once_in_play_are_one_note(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    # A ten-letter word whose direction the notes haven't got, after 99 finds in the other seven.
    target = next(w for w in words if len(w[0]) == 10)
    seeds = [w for w in words if w[3] != target[3] and len(w[0]) < 10][:99]
    assert len({w[3] for w in seeds}) == 7
    earlier = dt.datetime(2026, 1, 5, 12, 0, tzinfo=TORONTO)
    record = json.dumps({"got": {}, "best": 0, "fresh": []})
    open_alone(page, site_url, [find(w, earlier) for w in seeds], store={"letterfield.marks.v1": record})
    page.wait_for_timeout(2000)
    assert "first-mark" in marks(page)["got"]
    assert notes(page) == []  # earned by finds from before this visit: quietly

    circle(page, target)
    toast = page.locator("#toast")
    expect(toast.locator("b")).to_have_text("3 achievements", timeout=LANDS)
    expect(toast).to_contain_text("Field Book, Long Measure and 1 more")
    page.wait_for_timeout(2500)
    assert notes(page) == ["3 achievements"]
    assert errors == []


STREAKS = {
    # name: (finds a day, by days before today; expected days surveyed, running, longest, today's finds)
    "five days running": ({-4: 3, -3: 3, -2: 4, -1: 3, 0: 3}, 5, 5, 5, 3),
    "today is still open": ({-3: 3, -2: 3, -1: 3, 0: 1}, 3, 3, 3, 1),
    "a missed day is a rest day": ({-6: 3, -5: 3, -4: 3, -2: 3, -1: 3, 0: 3}, 6, 6, 6, 3),
    "a rest day once a week": ({d: 3 for d in range(-15, 1) if d not in (-14, -7)}, 14, 14, 14, 3),
    "two rest days in a week end it": ({-9: 3, -8: 3, -7: 3, -5: 3, -4: 3, -2: 3, -1: 3, 0: 3}, 8, 5, 5, 3),
    "two missed days in a row end it": ({-6: 3, -5: 3, -4: 3, -3: 3, 0: 3}, 5, 1, 4, 3),
    "two finds don't make a day": ({-2: 3, -1: 2, 0: 3}, 2, 2, 2, 3),
    "a day after today waits for it": ({-1: 3, 0: 3, 1: 3}, 2, 2, 2, 3),
}


@pytest.mark.parametrize("name", STREAKS)
def test_days_surveyed_and_the_streak(page: Page, site_url, errors, name):
    plan, days, running, longest, today = STREAKS[name]
    words = known_words(page, site_url, WORDS_JS)
    open_alone(page, site_url, on_days(words, plan), now=NOW)
    s = streak(page)
    assert (s["days"], s["current"], s["best"], s["today"]) == (days, running, longest, today)
    open_page(page)
    card = page.locator("#daysCard")
    expect(card.locator(".days-top b")).to_have_text([str(days), str(running), str(longest)])
    strip = card.locator(".days-strip li")
    expect(strip).to_have_count(14)
    expect(strip.last).to_have_class("open today" if today < 3 else "on today")
    rests = [d for d in range(-13, 0) if d not in plan and d > min(plan)]
    if name == "a missed day is a rest day":
        expect(card.locator(".days-strip li.rest")).to_have_count(1)
        expect(strip.nth(13 - 3)).to_have_class("rest")
    if name == "two missed days in a row end it":
        expect(card.locator(".days-strip li.miss")).to_have_count(len(rests))
    expect(card.locator(".days-today")).to_have_text("Today counts." if today >= 3 else f"Today: {today} of 3 words.")
    assert errors == []


def test_a_streak_of_a_week_earns_seven_days_and_counts_toward_a_lunar_month(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    open_alone(page, site_url, on_days(words, STREAKS["a rest day once a week"][0]), now=NOW)
    state = marks(page)
    assert "seven-days" in state["got"]
    assert state["progress"]["lunar-month"] == [14, 28]
    assert state["best"] == 14
    # The longest is kept, even once the finds behind it are gone (a redrawn map drops some).
    page.evaluate("localStorage.setItem('letterfield.finds.v4', '[]')")
    page.reload()
    page.wait_for_function("window.__lf && window.__lf.marks")
    assert streak(page)["best"] == 14
    assert streak(page)["current"] == 0
    assert errors == []


def test_days_are_local_dates_across_the_clocks_going_back(page: Page, site_url, errors):
    # Toronto's clocks went back an hour on 1 November 2026. Finds late each evening count on that evening's
    # date, never the next day's, either side of the change.
    words = known_words(page, site_url, WORDS_JS)
    late = [dt.datetime(2026, 10, d, 23, 40, tzinfo=TORONTO) for d in (30, 31)] + [
        dt.datetime(2026, 11, d, 23, 40, tzinfo=TORONTO) for d in (1, 2)
    ]
    finds = [find(words[i * 3 + k], t + dt.timedelta(minutes=k * 5)) for i, t in enumerate(late) for k in range(3)]
    open_alone(page, site_url, finds, now=dt.datetime(2026, 11, 3, 9, 0, tzinfo=TORONTO))
    s = streak(page)
    assert s["counted"] == ["Fri Oct 30 2026", "Sat Oct 31 2026", "Sun Nov 01 2026", "Mon Nov 02 2026"]
    assert (s["current"], s["best"]) == (4, 4)
    assert errors == []


def test_quietened_notes_earn_without_a_note_or_a_chime(page: Page, site_url, errors):
    word = known_words(page, site_url)[0]
    open_alone(page, site_url, store={"letterfield.quiet.v1": '["achievement"]'})
    circle(page, word)
    page.wait_for_function("'first-mark' in window.__lf.marks.state().got", timeout=LANDS)
    page.wait_for_timeout(3000)
    assert "First Mark" not in notes(page)
    assert marks(page)["sounds"] == 0
    expect(page.locator("#marksNew")).to_be_visible()  # the row still says something's new

    # The switch on the page turns them back on.
    open_page(page)
    switch = page.locator("#marksNotes")
    expect(switch).not_to_be_checked()
    switch.evaluate("e => e.click()")
    assert page.evaluate("localStorage.getItem('letterfield.quiet.v1')") == "[]"
    assert errors == []


def test_with_sound_off_a_note_comes_without_a_chime(page: Page, site_url, errors):
    word = known_words(page, site_url)[0]
    open_alone(page, site_url, store={"letterfield.sound.v1": "0"})
    circle(page, word)
    expect(page.locator("#toast b")).to_have_text("First Mark", timeout=LANDS)
    assert marks(page)["sounds"] == 0
    assert errors == []


def test_with_reduced_motion_the_badge_is_simply_there(page: Page, site_url, errors):
    word = known_words(page, site_url)[0]
    page.emulate_media(reduced_motion="reduce")
    open_alone(page, site_url)
    circle(page, word)
    expect(page.locator("#toast b")).to_have_text("First Mark", timeout=LANDS)
    assert page.evaluate("[...document.querySelectorAll('#toast .mk *')].every(e => !e.getAnimations().length)")
    assert errors == []


def test_the_page_is_in_the_notes_and_escape_goes_back(page: Page, site_url, errors):
    open_alone(page, site_url)
    open_page(page)
    expect(page.locator("#finds")).to_be_hidden()
    expect(page.locator("#marksBack")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator("html")).to_have_attribute("data-notes-page", "finds")
    expect(page.locator("#marksRow")).to_be_focused()
    # Closing the notes leaves the page: they open on the finds again.
    open_page(page)
    page.click("#marksClose")
    expect(page.locator("html")).to_have_attribute("data-panel", "none")
    expect(page.locator("html")).to_have_attribute("data-notes-page", "finds")
    # Alone, the survey's achievements aren't offered.
    open_page(page)
    expect(page.locator("#mk-first-light")).to_have_count(0)
    expect(page.locator(".mk-card")).to_have_count(ALONE)
    assert errors == []


def test_on_the_survey_its_achievements_are_offered_and_a_hat_tipped_is_one(page: Page, site_url, errors):
    page.add_init_script(NOTES_JS)
    fake = FakeSurvey()
    start_survey(page, site_url, fake)
    page.wait_for_function("window.__lf.marks")
    expect(page.locator("#marksLine")).to_have_text(f"0 of {ON_SURVEY}")
    fake.emote("0,0", KIM[0], "KIM", "thanks", [0, 0])
    page.wait_for_function("'hats-off' in window.__lf.marks.state().got")
    expect(page.locator("#toast b")).to_have_text("Hats Off", timeout=LANDS)
    assert errors == []


def test_a_find_from_a_linked_device_earns_it_quietly(page: Page, site_url, errors):
    page.add_init_script(NOTES_JS)
    theirs = sync_words(page, site_url, 1)[0]
    players = FakePlayers(started=[PID])
    players.add(PID, finds=[theirs])  # found on the player's other device
    start_sync(page, site_url, players)
    page.wait_for_function("window.__lf.found.size === 1")
    page.wait_for_function("window.__lf.marks && 'first-mark' in window.__lf.marks.state().got", timeout=LANDS)
    page.wait_for_timeout(2500)
    assert "First Mark" not in notes(page)  # it was celebrated on the device that found it
    expect(page.locator("#marksNew")).to_be_visible()
    assert errors == []
