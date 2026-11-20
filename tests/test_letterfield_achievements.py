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
import re
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import Page, expect

from fake_leaderboard import without_worker
from fake_survey import CARD_SIG, FakeBadges, FakePlayers, FakeSurvey, card
from test_letterfield_survey import LANDS, SHARE_SHEET_INIT, SURVEY, circle, eventually, known_words, open_game
from test_letterfield_surveyors import KIM, KIM_CARET, LOU, PID, ZED, open_list
from test_letterfield_surveyors import start as start_survey
from test_letterfield_sync import start as start_sync
from test_letterfield_sync import words as sync_words

TORONTO = ZoneInfo("America/Toronto")
NOW = dt.datetime(2026, 11, 17, 15, 0, tzinfo=TORONTO)
ALONE, ON_SURVEY = 31, 40  # achievements in the catalog alone and on the shared survey

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


# Hidden words in the first eight territories along the map centre's row, enough for 666 finds.
MANY_WORDS_JS = WORDS_JS.replace("[[0, 0], [1, 0]]", "[0, 1, 2, 3, 4, 5, 6, 7].map(rx => [rx, 0])")
BEAST = "#mk-number-of-the-beast"


def test_number_of_the_beast_is_a_secret_until_the_666th_find(page: Page, site_url, errors):
    words = known_words(page, site_url, MANY_WORDS_JS)
    assert len(words) >= 666
    earlier = dt.datetime(2026, 11, 25, 12, 0, tzinfo=TORONTO)
    seeds = [find(w, earlier + dt.timedelta(seconds=i)) for i, w in enumerate(words[:665])]
    record = json.dumps({"got": {}, "best": 0, "fresh": []})
    open_alone(
        page,
        site_url,
        seeds,
        store={"letterfield.marks.v1": record},
        now=dt.datetime(2026, 12, 1, 15, 0, tzinfo=TORONTO),
    )
    page.wait_for_function("'field-book' in window.__lf.marks.state().got", timeout=LANDS)
    assert "number-of-the-beast" not in marks(page)["got"]
    assert marks(page)["progress"]["number-of-the-beast"] == [665, 666]

    # On the page it sits after Field Book, a question mark with no arc of how far along it is.
    open_page(page)
    beast = page.locator(BEAST)
    expect(beast).to_contain_text("Secret")
    expect(beast).not_to_contain_text("666")
    expect(beast).to_have_class(re.compile(r"\blocked\b"))
    expect(beast.locator(".mk-arc")).to_have_count(0)
    expect(beast.locator(".mk-dash")).to_have_count(1)
    assert page.evaluate(f"document.querySelector('{BEAST}').previousElementSibling.id") == "mk-field-book"
    page.click("#marksBack")

    circle(page, words[665])
    toast = page.locator("#toast")
    expect(toast.locator("b")).to_have_text("Number of the Beast", timeout=LANDS)
    expect(toast).to_contain_text("Achievement · Keep 666 words in your field notes.")
    assert marks(page)["got"]["number-of-the-beast"][1] == 0  # earned in play
    open_page(page)
    expect(beast).to_have_class(re.compile(r"\bgot\b"))
    expect(beast).to_contain_text("Number of the Beast")
    expect(beast).to_contain_text("Earned")
    expect(beast.locator(".mk-disc")).to_have_count(1)
    assert errors == []


def test_a_player_already_past_666_gets_number_of_the_beast_quietly_from_their_notes(page: Page, site_url, errors):
    words = known_words(page, site_url, MANY_WORDS_JS)
    long_ago = dt.datetime(2026, 10, 1, 12, 0, tzinfo=TORONTO)
    finds = [find(w, long_ago + dt.timedelta(minutes=i)) for i, w in enumerate(words[:700])]
    # Their record already has what those notes earned before this achievement came along.
    got = {i: [finds[0]["t"], 1] for i in ("first-mark", "field-book", "compass-rose")}
    record = json.dumps({"got": got, "best": 0, "fresh": []})
    open_alone(page, site_url, finds, store={"letterfield.marks.v1": record})
    page.wait_for_function("'number-of-the-beast' in window.__lf.marks.state().got", timeout=LANDS)
    state = marks(page)
    assert state["got"]["number-of-the-beast"] == [finds[665]["t"], 1]  # dated by the 666th find, from the notes
    assert "number-of-the-beast" in state["fresh"]
    expect(page.locator("#marksNew")).to_be_visible()
    page.wait_for_timeout(2500)
    assert "Number of the Beast" not in notes(page)
    open_page(page)
    expect(page.locator(BEAST)).to_contain_text("from your notes")
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
    expect(strip.last).to_have_class("on today" if today >= 3 else "open part today" if today else "open today")
    rests = [d for d in range(-13, 0) if d not in plan and d > min(plan)]
    if name == "a missed day is a rest day":
        expect(card.locator(".days-strip li.rest")).to_have_count(1)
        expect(strip.nth(13 - 3)).to_have_class("rest")
    if name == "two missed days in a row end it":
        expect(card.locator(".days-strip li.miss")).to_have_count(len(rests))
    expect(card.locator(".days-today")).to_have_text("Today counts." if today >= 3 else f"Today: {today} of 3 words.")
    assert errors == []


def test_todays_dot_fills_a_slice_for_each_word_until_the_day_counts(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    open_alone(page, site_url, [find(words[0], NOW - dt.timedelta(hours=1))], now=NOW)
    open_page(page)
    today = page.locator("#daysCard .days-strip li.today")
    expect(today).to_have_attribute("class", "open part today")
    expect(today).to_have_attribute("style", "--p:0.333")
    expect(today).to_have_attribute("title", re.compile(r": today, 1 of 3 words$"))
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", words[1])
    expect(today).to_have_attribute("style", "--p:0.667")
    expect(page.locator(".days-today")).to_have_text("Today: 2 of 3 words.")
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", words[2])
    expect(today).to_have_attribute("class", "on today")
    expect(page.locator(".days-today")).to_have_text("Today counts.")
    assert errors == []


def test_past_days_with_a_word_or_two_keep_their_slices(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    # One word the day before the first that counted, then two on a rest day in a run that goes on.
    open_alone(page, site_url, on_days(words, {-6: 1, -5: 3, -4: 2, -3: 3, -2: 3, -1: 3}), now=NOW)
    open_page(page)
    days = page.locator("#daysCard .days-strip li")
    expect(days).to_have_count(14)
    first, rest, counted = days.nth(13 - 6), days.nth(13 - 4), days.nth(13 - 3)
    expect(rest).to_have_attribute("class", "rest part")
    expect(rest).to_have_attribute("style", "--p:0.667")
    expect(rest).to_have_attribute("title", re.compile(r": a rest day, 2 of 3 words$"))
    expect(first).to_have_attribute("class", "none part")
    expect(first).to_have_attribute("style", "--p:0.333")
    expect(first).to_have_attribute("title", re.compile(r": not counted, 1 of 3 words$"))
    expect(counted).to_have_attribute("class", "on")
    expect(counted).not_to_have_attribute("style", re.compile("."))
    expect(days.nth(13 - 7)).to_have_attribute("class", "none")  # nothing found that day
    assert errors == []


COLLECT = "([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)"
SHARE_WAIT = 15_000  # a note with a button stays 6 s, and the next waits for it to go


def test_a_day_that_counts_gets_one_quiet_note(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    # Two days counted, then two words today: the third makes three days running.
    open_alone(page, site_url, on_days(words, {-2: 3, -1: 3, 0: 2}), now=NOW)
    page.wait_for_timeout(1000)
    before, sounds = notes(page), marks(page)["sounds"]
    page.evaluate(COLLECT, words[8])
    expect(page.locator("#toast b")).to_have_text("Today counts", timeout=LANDS)
    expect(page.locator("#toast span").first).to_have_text("3 days running")
    expect(page.locator("#toast i.day-ico")).to_have_count(1)
    assert marks(page)["sounds"] == sounds  # no chime
    # See opens the days.
    page.locator("#toast").get_by_role("button", name="See your days surveyed").click()
    expect(page.locator("html")).to_have_attribute("data-notes-page", "marks")
    # Once a day: a fourth word brings no second note.
    page.evaluate(COLLECT, words[9])
    page.wait_for_timeout(2500)
    assert notes(page)[len(before) :] == ["Today counts"]
    assert errors == []


def test_a_first_day_gets_its_note_after_first_marks(page: Page, site_url, errors):
    # Three words at once on a first day earn First Mark too: its note, then the day's.
    words = known_words(page, site_url, WORDS_JS)
    open_alone(page, site_url, [], now=NOW)
    page.wait_for_timeout(1000)
    for w in words[:3]:
        page.evaluate(COLLECT, w)
    expect(page.locator("#toast b")).to_have_text("First Mark", timeout=LANDS)
    expect(page.locator("#toast b")).to_have_text("Today counts", timeout=SHARE_WAIT)
    expect(page.locator("#toast span").first).to_have_text("Your first day surveyed")
    assert errors == []


def test_a_day_after_a_break_says_how_many_days_surveyed(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    open_alone(page, site_url, on_days(words, {-5: 3, -4: 3, 0: 2}), now=NOW)
    page.evaluate(COLLECT, words[8])
    expect(page.locator("#toast b")).to_have_text("Today counts", timeout=LANDS)
    expect(page.locator("#toast span").first).to_have_text("3 days surveyed")  # never what was lost
    assert errors == []


def test_a_day_after_a_rest_day_says_so(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    open_alone(page, site_url, on_days(words, {-3: 3, -2: 3, 0: 2}), now=NOW)
    page.evaluate(COLLECT, words[8])
    expect(page.locator("#toast b")).to_have_text("Today counts", timeout=LANDS)
    expect(page.locator("#toast span").first).to_have_text("3 days running · yesterday was a rest day")
    assert errors == []


def test_a_day_that_earns_an_achievement_has_that_note_instead(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    # Six days counted, then the seventh's third word: Seven Days Running says it all.
    plan = {-6: 3, -5: 3, -4: 3, -3: 3, -2: 3, -1: 3, 0: 2}
    open_alone(
        page,
        site_url,
        on_days(words, plan),
        now=NOW,
        store={"letterfield.marks.v1": json.dumps({"got": {"first-mark": [1, 1]}, "best": 6})},
    )
    page.wait_for_timeout(1500)
    before = notes(page)
    page.evaluate(COLLECT, words[sum(plan.values())])
    expect(page.locator("#toast b")).to_have_text("Seven Days Running", timeout=LANDS)
    page.wait_for_timeout(2500)
    assert "Today counts" not in notes(page)[len(before) :]
    assert errors == []


def test_with_its_switch_off_a_day_that_counts_brings_no_note(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    open_alone(page, site_url, on_days(words, {-1: 3, 0: 2}), now=NOW)
    open_page(page)
    switch = page.get_by_role("switch", name="A note when a day counts")
    expect(switch).to_be_checked()
    switch.click()
    assert page.evaluate("JSON.parse(localStorage.getItem('letterfield.quiet.v1'))") == ["day"]
    expect(page.get_by_role("switch", name="Notes for new achievements")).to_be_checked()
    page.evaluate(COLLECT, words[5])
    page.wait_for_function("window.__lf.marks.streak().today === 3")
    page.wait_for_timeout(2500)
    assert "Today counts" not in notes(page)
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


# ---------- Stage 2: signed finds, badges others see, syncing and sharing ----------


def on_survey(page: Page, site_url: str, fake: FakeSurvey, badges: FakeBadges, finds=(), quiet=False) -> None:
    """Opens the game on the survey, signed as MLW with our token, `finds` in the notes and `badges` answering."""
    page.add_init_script(NOTES_JS)
    page.route(f"{SURVEY}/v1/survey/badges", badges.handle)
    start_survey(page, site_url, fake)
    if finds or quiet:
        page.evaluate(
            "([f, q]) => { localStorage.setItem('letterfield.finds.v4', f); localStorage.removeItem('letterfield.marks.v1');"
            " if (q) localStorage.setItem('letterfield.quiet.v1', '[\"achievement\"]'); }",
            [json.dumps(list(finds)), quiet],
        )
        page.reload()
    page.wait_for_function(f"window.__lf && window.__lf.marks && window.__lf.pid() === '{PID}'")


def test_a_find_circled_on_the_survey_keeps_its_receipt_and_proves_a_badge_to_show(page: Page, site_url, errors):
    word = known_words(page, site_url)[0]
    fake, badges = FakeSurvey(sign=True), FakeBadges(proven=["first-mark", "first-light"])
    on_survey(page, site_url, fake, badges)
    circle(page, word)
    page.wait_for_function("[...window.__lf.found.values()].some(e => e.r)")
    stored = page.evaluate("JSON.parse(localStorage.getItem('letterfield.finds.v4'))")
    assert stored[0]["r"].endswith(".f.SIGNEDSIGNED")
    # Earning First Mark asks the Worker, with the signed find, which badges it will sign.
    page.wait_for_function("(window.__lf.marks.state().got['first-mark'] || [])[2]", timeout=LANDS)
    ask = badges.calls[-1]
    assert ask["finds"] == [{"w": word[0], "x": word[1], "y": word[2], "d": word[3], "r": stored[0]["r"]}]
    assert "first-mark" in ask["earned"] and ask["token"] and isinstance(ask["z"], int)

    # Shown on our caret: the badge goes to the sector with who we are, and with our settings.
    open_page(page)
    card = page.locator("#mk-first-mark")
    card.get_by_role("button", name="Show First Mark on your caret").click()
    expect(card.get_by_role("button", name="Show First Mark on your caret")).to_have_attribute("aria-pressed", "true")
    expect(card).to_have_class("mk-card got shown")
    eventually(
        page, lambda: any(m.get("badge") == ["first-mark", FakeBadges.sig("first-mark")] for m in fake.sent("me"))
    )
    assert page.evaluate("JSON.parse(localStorage.getItem('letterfield.badge.v1'))") == [
        "first-mark",
        FakeBadges.sig("first-mark"),
    ]
    # Pressed again, it's taken off.
    card.get_by_role("button", name="Show First Mark on your caret").click()
    eventually(page, lambda: "badge" not in fake.sent("me")[-1])
    assert errors == []


def test_achievements_from_before_signing_are_signed_on_the_games_word(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    long_ago = dt.datetime(2025, 3, 2, 12, 0, tzinfo=TORONTO)
    finds = [find(w, long_ago + dt.timedelta(hours=i)) for i, w in enumerate(words[:120])]
    badges = FakeBadges(signs=["first-mark"])  # what a Worker inside TRUSTED_UNTIL takes our word for
    on_survey(page, site_url, FakeSurvey(), badges, finds=finds, quiet=True)
    page.wait_for_function("(window.__lf.marks.state().got['first-mark'] || [])[2]")
    earned = set(marks(page)["got"])
    assert badges.calls[0]["finds"] == []  # nothing signed: these are from before
    assert set(badges.calls[0]["earned"]) == earned and len(earned) > 1
    open_page(page)
    expect(page.locator("#mk-first-mark").get_by_role("button", name="Show First Mark on your caret")).to_be_visible()
    # One the Worker wouldn't sign can be shared, but not shown.
    other = next(
        a for a in page.evaluate("window.__lf.marks.catalog()") if a["id"] in earned and a["id"] != "first-mark"
    )
    card = page.locator(f"#mk-{other['id']}")
    expect(card.get_by_role("button", name=f"Share {other['name']}")).to_be_visible()
    expect(card.locator("[data-show]")).to_have_count(0)
    assert errors == []


def test_someones_badge_shows_on_their_caret_hover_card_and_menu(page: Page, site_url, errors):
    fake = FakeSurvey(
        presence=[[KIM[0], "KIM", 9.5, 7.0, [], "seven-seas"], ["4b1d00000001", "LOU", 11.5, 9.0, [], "no-such-badge"]]
    )
    start_survey(page, site_url, fake)
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}')")
    at = page.evaluate(f"window.__lf.caretXY('{KIM[0]}')")
    page.mouse.move(at["x"], at["y"])
    peek = page.locator("#peek")
    expect(peek).to_be_visible()
    expect(peek.locator(".peek-mk")).to_have_text("Seven Seas")
    page.mouse.click(at["x"], at["y"], button="right")
    expect(page.locator("#caretMenu .caret-who .peek-mk")).to_have_text("Seven Seas")
    page.keyboard.press("Escape")
    # A badge the game doesn't know shows nothing.
    lou = page.evaluate("window.__lf.caretXY('4b1d00000001')")
    page.mouse.move(lou["x"], lou["y"])
    expect(peek).to_contain_text("LOU")
    expect(peek.locator(".peek-mk")).to_have_count(0)
    assert errors == []


def test_our_card_goes_to_the_sector_with_who_we_are(page: Page, site_url, errors):
    words = known_words(page, site_url, WORDS_JS)
    began = dt.datetime(2026, 10, 4, 9, 0, tzinfo=TORONTO)
    finds = [find(w, began + dt.timedelta(hours=i)) for i, w in enumerate(words[:12])]
    fake, badges = FakeSurvey(), FakeBadges(signs=["first-mark", "first-light"], cards=True)
    on_survey(page, site_url, fake, badges, finds=finds, quiet=True)
    page.wait_for_function("window.__lf.marks.card() && window.__lf.marks.card().ids.length === 2")
    since = int(began.timestamp() * 1000)
    ask = badges.calls[0]
    assert ask["since"] == since and ask["held"] == {} and "card" not in ask  # when we began, on the game's word
    mine = card({"first-mark", "first-light"}, since // 86_400_000, signed=True)
    assert page.evaluate("localStorage.getItem('letterfield.card.v1')") == mine
    eventually(page, lambda: any(m.get("card") == mine for m in fake.sent("me")))
    # With everything we hold on it, the next visit doesn't ask again.
    asked = len(badges.calls)
    page.reload()
    page.wait_for_function("window.__lf && window.__lf.marks && window.__lf.marks.card()")
    page.wait_for_timeout(1500)
    assert len(badges.calls) == asked
    eventually(page, lambda: fake.sent("me")[-1].get("card") == mine)
    assert errors == []


def test_someones_card_shows_in_their_caret_menu(page: Page, site_url, errors):
    day = dt.date(2026, 10, 4).toordinal() - dt.date(1970, 1, 1).toordinal()
    theirs = card({"first-mark", "seven-seas", "here-be-dragons", "witness"}, day)
    lou = "4b1d00000001"
    fake = FakeSurvey(presence=[[KIM[0], "KIM", 9.5, 7.0, [], "seven-seas", theirs], [lou, "LOU", 11.5, 9.0, []]])
    start_survey(page, site_url, fake)
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}') && window.__lf.carets().includes('{lou}')")
    at = page.evaluate(f"window.__lf.caretXY('{KIM[0]}')")
    page.mouse.move(at["x"], at["y"])
    expect(page.locator("#peek")).to_contain_text("right-click for more")
    page.mouse.click(at["x"], at["y"], button="right")
    menu = page.locator("#caretMenu")
    expect(menu.locator("#caretWho")).to_have_text("KIM")
    # The badge they show, big; when they began; and every badge others may see, as small ones.
    expect(menu.locator(".pc-shown b")).to_have_text("Seven Seas")
    expect(menu.locator(".pc-since")).to_have_text("Surveying since Oct 2026 · 4 badges")
    shown = menu.locator(".pc-mk")
    expect(shown).to_have_count(4)
    assert [shown.nth(i).get_attribute("aria-label") for i in range(4)] == [
        "First Mark",
        "Seven Seas",
        "A secret achievement",  # Here Be Dragons, which we haven't found
        "Witness",  # no find proves it, so it's on the game's word
    ]
    # A badge tapped says what it is; tapped again, it's quiet.
    shown.nth(1).click()
    expect(menu.locator(".pc-say")).to_contain_text("Seven Seas · ")
    expect(shown.nth(1)).to_have_attribute("aria-pressed", "true")
    shown.nth(2).click()
    expect(menu.locator(".pc-say")).to_have_text("A secret achievement · find it yourself to see which")
    shown.nth(2).click()
    expect(menu.locator(".pc-say")).to_have_text("")
    expect(menu).not_to_contain_text("days")  # no streaks or days surveyed, ever
    expect(menu.locator(".emote")).not_to_have_count(0)  # the emotes and Mute, as before
    expect(menu.locator(".who-mute")).to_have_text("Mute KIM")
    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()
    # Someone without a card, from an older game, has the menu as it was.
    at = page.evaluate(f"window.__lf.caretXY('{lou}')")
    page.mouse.click(at["x"], at["y"], button="right")
    expect(menu.locator("#caretWho")).to_have_text("LOU")
    expect(menu.locator(".pc-since, .pc-mk, .pc-shown")).to_have_count(0)
    assert errors == []


def test_someones_card_shows_under_their_row_in_the_surveyors_list_while_theyre_near(page: Page, site_url, errors):
    day = dt.date(2026, 10, 4).toordinal() - dt.date(1970, 1, 1).toordinal()
    theirs = card({"first-mark", "seven-seas", "here-be-dragons"}, day)
    # KIM near with a card, ZED near on a game from before cards, LOU far off.
    zed = [ZED[0], "ZED", 12.5, 9.0]
    fake = FakeSurvey(surveyors=[KIM, ZED, LOU], presence=[[*KIM_CARET, [], "seven-seas", theirs], zed])
    start_survey(page, site_url, fake)
    page.wait_for_function(f"window.__lf.carets().includes('{KIM[0]}') && window.__lf.carets().includes('{ZED[0]}')")
    open_list(page)
    expect(page.locator(".who-foot")).to_contain_text("Their badges, more emotes and mute are under ⋯")
    page.get_by_role("button", name="More for KIM").click()
    panel = page.get_by_role("group", name="KIM’s badges and emotes")
    expect(panel.locator(".pc-shown b")).to_have_text("Seven Seas")
    expect(panel.locator(".pc-since")).to_have_text("Surveying since Oct 2026 · 3 badges")
    expect(panel.locator(".pc-mk")).to_have_count(3)
    expect(panel.locator(".emote")).not_to_have_count(0)  # the emotes and Mute, as before
    expect(panel.locator(".who-mute")).to_have_text("Mute KIM")
    # A badge tapped says what it is, and stays said when the list is drawn again.
    panel.get_by_role("button", name="Seven Seas").click()
    expect(panel.locator(".pc-say")).to_contain_text("Seven Seas · Find words from all 7 themes of the sea.")
    page.evaluate("window.__lf.renderWho()")
    expect(page.get_by_role("group", name="KIM’s badges and emotes").locator(".pc-say")).to_contain_text(
        "Seven Seas · "
    )
    expect(
        page.get_by_role("group", name="KIM’s badges and emotes").get_by_role("button", name="Seven Seas")
    ).to_be_focused()
    # Someone whose caret isn't on our map: how to see theirs.
    page.get_by_role("button", name="More for LOU").click()
    lou = page.get_by_role("group", name="LOU’s badges and emotes")
    expect(lou.locator(".pc-far")).to_have_text(
        "LOU’s badges show here once they’re near you on the map: tap their name to fly there."
    )
    expect(lou.locator(".pc-card")).to_have_count(0)
    # Someone right here with no card, as from a game from before cards: nothing to show, not "fly there".
    page.get_by_role("button", name="More for ZED").click()
    expect(page.get_by_role("group", name="ZED’s badges and emotes").locator(".pc-far")).to_have_text(
        "ZED has no badges to show yet."
    )
    assert errors == []


def test_a_card_synced_from_another_device_is_taken_if_it_has_everything_ours_has(page: Page, site_url, errors):
    players = FakePlayers(started=[PID])
    theirs = card({"first-mark", "seven-seas"}, 20365, signed=True)
    settings = {
        "initials": "MLW",
        "guilds": [],
        "labels": {},
        "muted": [],
        "mutedAs": {},
        "emotes": True,
        "badge": None,
    }
    players.add(PID, settings={**settings, "card": theirs}, settings_at=10**12)
    start_sync(page, site_url, players)
    page.wait_for_function(f"localStorage.getItem('letterfield.card.v1') === '{theirs}'")
    take = "c => window.__lf.marks.takeCard(c)"
    # One from before, with less on it or a later start, isn't.
    assert not page.evaluate(take, card({"first-mark"}, 20365, signed=True))
    assert not page.evaluate(take, card({"first-mark", "seven-seas", "map-key"}, 20400, signed=True))
    assert not page.evaluate(take, card({"first-mark", "seven-seas", "map-key"}, 20365))  # no signature
    assert page.evaluate(take, card({"first-mark", "seven-seas", "map-key"}, 20300, signed=True))
    assert page.evaluate("window.__lf.marks.card()") == {"ids": ["first-mark", "map-key", "seven-seas"], "day": 20300}
    assert page.evaluate("localStorage.getItem('letterfield.card.v1')").endswith(CARD_SIG)
    assert errors == []


def test_achievements_and_the_longest_streak_sync_between_linked_devices(page: Page, site_url, errors):
    page.add_init_script(NOTES_JS)
    mine = sync_words(page, site_url, 1)
    players = FakePlayers(started=[PID])
    earlier = int(dt.datetime(2026, 1, 3, 12, 0, tzinfo=TORONTO).timestamp() * 1000)
    # The other device earned Seven Seas, and had it signed; its longest streak was 9 days.
    players.add(PID, marks=[["seven-seas", earlier, 0, FakeBadges.sig("seven-seas")]], best=9)
    start_sync(page, site_url, players, finds=mine)
    page.wait_for_function("'seven-seas' in window.__lf.marks.state().got")
    state = marks(page)
    assert state["got"]["seven-seas"] == [earlier, 0, FakeBadges.sig("seven-seas")]
    assert state["best"] == 9 and "seven-seas" in state["fresh"]
    page.wait_for_timeout(2000)
    assert "Seven Seas" not in notes(page)  # it was noted on the device that earned it
    # Ours go up: First Mark, earned here from the notes.
    eventually(
        page, lambda: any(m[0] == "first-mark" for body in players.sent() for m in body.get("marks", [])), 10_000
    )
    assert errors == []


def test_an_earned_badge_can_be_shared(page: Page, site_url, errors):
    word = known_words(page, site_url)[0]
    page.add_init_script(SHARE_SHEET_INIT)
    open_alone(page, site_url, [find(word, NOW)])
    open_page(page)
    page.locator("#mk-first-mark").get_by_role("button", name="Share First Mark").click()
    page.wait_for_function("window.__shared.length === 1")
    shared = page.evaluate("window.__shared[0]")
    assert shared["text"] == "I earned First Mark in Letterfield: circle your first word."
    # With no share Worker (as here), the link is the game at the badge.
    assert shared["url"] == f"{site_url}/letterfield#a-first-mark"
    # Alone, there's no one to show a badge to.
    expect(page.locator("#mk-first-mark [data-show]")).to_have_count(0)
    assert errors == []


def test_with_a_share_worker_a_badge_links_to_its_card_in_the_sharers_theme(page: Page, site_url, errors):
    # ?share= stands in for SHARE_URL: the share Worker (share/), whose page
    # for the badge carries a card of it as its link preview.
    word = known_words(page, site_url)[0]
    page.add_init_script(SHARE_SHEET_INIT)
    page.add_init_script(NOTES_JS)
    without_worker(page, site_url, "letterfield")
    page.goto(f"{site_url}/letterfield?share=https://share.test/#debug")
    page.evaluate(
        "f => { localStorage.setItem('letterfield.finds.v4', f); localStorage.setItem('letterfield.coach.v1', '1'); }",
        json.dumps([find(word, NOW)]),
    )
    for scheme, path in (("light", "a/first-mark"), ("dark", "a/d/first-mark")):
        page.emulate_media(color_scheme=scheme)
        page.reload()
        page.wait_for_function("window.__lf && window.__lf.marks && 'first-mark' in window.__lf.marks.state().got")
        if not page.locator("#marksPage").is_visible():
            open_page(page)
        page.locator("#mk-first-mark").get_by_role("button", name="Share First Mark").click()
        page.wait_for_function("window.__shared.length === 1")
        assert page.evaluate("window.__shared[0].url") == f"https://share.test/{path}"
    assert errors == []


def test_a_shared_badge_opens_at_its_place_on_the_achievements_page(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")
    page.goto(f"{site_url}/letterfield#a-seven-seas")
    html = page.locator("html")
    # A first visit's card comes first; the badge once it's gone.
    expect(html).to_have_attribute("data-intro", "coach")
    page.wait_for_timeout(300)
    expect(html).to_have_attribute("data-notes-page", "finds")
    page.click("#coachOk")
    expect(html).to_have_attribute("data-notes-page", "marks")
    expect(html).to_have_attribute("data-panel", "notes")
    badge = page.locator("#mk-seven-seas")
    expect(badge).to_be_in_viewport()
    expect(badge).to_contain_text("Find words from all 7 themes of the sea.")
    # Come back to (a reload), it stays as it was left rather than opening it again.
    page.locator("#marksBack").click()
    expect(html).to_have_attribute("data-notes-page", "finds")
    page.reload()
    page.wait_for_timeout(500)
    expect(html).to_have_attribute("data-notes-page", "finds")
    # A link opened in the tab already on the map opens it too; one to no achievement, nothing.
    page.evaluate("location.hash = '#a-first-mark'")
    expect(html).to_have_attribute("data-notes-page", "marks")
    expect(page.locator("#mk-first-mark")).to_be_in_viewport()
    page.locator("#marksBack").click()
    page.evaluate("location.hash = '#a-no-such-badge'")
    page.wait_for_timeout(300)
    expect(html).to_have_attribute("data-notes-page", "finds")
    assert errors == []


def test_a_note_due_while_the_tab_is_hidden_waits_until_its_back(page: Page, site_url, errors):
    open_alone(page, site_url)
    hide = "h => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => h }); document.dispatchEvent(new Event('visibilitychange')); }"
    page.evaluate(hide, True)
    page.evaluate("window.__lf.marks.grant('first-mark')")
    # Past the 20 seconds a busy screen is waited out, it still hasn't shown in the hidden tab.
    page.wait_for_timeout(23_000)
    assert notes(page) == []
    assert marks(page)["sounds"] == 0
    page.evaluate(hide, False)
    expect(page.locator("#toast b")).to_have_text("First Mark")
    assert notes(page) == ["First Mark"]
    assert errors == []
