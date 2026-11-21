"""Letterfield past the universe's edge, on the shared survey: the void, a sector wide all round,
where loose letters drift and nothing can be circled, and the wilds beyond it, where the map goes
on and words are found alone. Neither joins a sector (see "The edge, the void and the wilds" in
worker/SURVEY.md). The universe is sectors -12 to 12 each way: cells -2304 to 2495."""

from __future__ import annotations

import json

from playwright.sync_api import Page, expect

from fake_survey import NOW_MS, FakeSurvey
from test_letterfield_survey import SURVEY, eventually, known_words, open_game, open_notes

EDGE0, EDGE1 = -2304, 2496

# Player Shore, at 2568W · 1512N: territory (-54, -32), in sector (-14, -8), 264 cells past the
# universe's edge, in the wilds.
WILDS = (-54, -32)
WILDS_WORDS = """() => {
  const out = [];
  for (let cy = -128; cy < -124; cy++) for (let cx = -216; cx < -212; cx++) for (const o of window.__lf.chunk(cx, cy).words) out.push([o.w, o.x, o.y, o.d]);
  return out;
}"""
# A word hidden in the void, 13 to 24 cells west of the universe, and one in the wilds.
OUTSIDE_WORDS = """() => {
  const of = (cx, cy) => { const o = window.__lf.chunk(cx, cy).words[0]; return [o.w, o.x, o.y, o.d]; };
  return { void: of(-194, 0), wilds: of(-216, -128) };
}"""


def start_at(page: Page, x: float, y: float, cs: int = 26) -> None:
    """Starts the camera at (x, y), with initials signed."""
    page.add_init_script(f"""
      localStorage.setItem('games.initials', JSON.stringify('MLW'));
      localStorage.setItem('letterfield.cam.v1', JSON.stringify({{ x: {x}, y: {y}, cs: {cs} }}));
    """)


def move_to(page: Page, x: float, y: float) -> None:
    page.evaluate(f"() => {{ window.__lf.cam.x = {x}; window.__lf.cam.y = {y}; dispatchEvent(new Event('resize')); }}")


def test_crossing_the_edge_leaves_the_survey_with_a_note_and_coming_back_joins_it(page: Page, site_url, errors):
    start_at(page, EDGE0 + 14, 6)
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    html = page.locator("html")
    expect(html).to_have_attribute("data-zone", "inside")
    eventually(page, lambda: page.evaluate("window.__lf.linkStates()").get("-12,0") == "live")

    move_to(page, EDGE0 - 30, 6)  # into the void
    expect(html).to_have_attribute("data-zone", "void")
    expect(page.locator("#toast")).to_contain_text("Past the edge of the universe")
    expect(page.locator("#toast")).to_contain_text("You’ve left the shared survey.")
    assert page.evaluate("window.__lf.linkStates()") == {}, "every sector is left at once"
    expect(page.locator("#tName")).to_have_text("The void")
    expect(page.locator("#tTheme")).to_have_text("Beyond the known universe")
    expect(page.locator("#tCharted")).to_be_hidden()
    open_notes(page)
    expect(page.locator("#surveyLabel")).to_have_text("The void")
    expect(page.locator("#surveyText")).to_have_text("Loose letters, nothing to find. The universe is behind you.")

    page.get_by_role("button", name="Back to the universe").click()
    expect(html).to_have_attribute("data-zone", "inside", timeout=6000)
    expect(page.locator("#toast")).to_contain_text("Back in the universe")
    eventually(page, lambda: page.evaluate("window.__lf.linkStates()").get("-12,0") == "live")
    assert EDGE0 <= page.evaluate("window.__lf.cam.x") < EDGE1

    move_to(page, EDGE0 - 30, 6)  # and the note comes every time
    expect(page.locator("#toast")).to_contain_text("Past the edge of the universe")
    assert errors == []


def test_nothing_in_the_void_can_be_circled(page: Page, site_url, errors):
    words = known_words(page, site_url, OUTSIDE_WORDS)
    start_at(page, EDGE0 - 20, 6)
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    expect(page.locator("html")).to_have_attribute("data-zone", "void")
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", words["void"])
    expect(page.locator("#toast")).to_contain_text("The void")
    assert page.evaluate("window.__lf.found.size") == 0
    assert fake.sectors == [] and fake.sent("claim") == []
    assert errors == []


def test_in_the_wilds_words_are_found_alone(page: Page, site_url, errors):
    """The map goes on past the void, but off the survey: a find goes in your notes alone, nothing
    is sent, nobody's joined, and the last of a territory sets it off for you alone."""
    words = known_words(page, site_url, WILDS_WORDS)
    assert {(w[1] // 48, w[2] // 48) for w in words} == {WILDS}
    start_at(page, -2568, -1512, 30)
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    expect(page.locator("html")).to_have_attribute("data-zone", "wilds")
    expect(page.locator("#toast")).not_to_contain_text("Past the edge")  # a reload out here brings no note
    expect(page.locator("#tName")).to_have_text(page.evaluate(f"window.__lf.territoryName{WILDS}"))
    expect(page.locator("#tCharted")).to_have_text(f" · 0/{len(words)} found · the wilds")
    open_notes(page)
    expect(page.locator("#surveyLabel")).to_have_text("The wilds")
    expect(page.locator("#surveyText")).to_have_text(
        "Words you find out here stay in your field notes, and nobody sees your caret."
    )

    for w in words[:-1]:
        page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", w)
    expect(page.locator("#tWords")).to_have_text(str(len(words) - 1), timeout=10_000)
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", words[-1])
    expect(page.locator("#nova")).to_be_visible(timeout=6000)
    expect(page.locator("#novaText")).to_contain_text(f"all {len(words)} hidden words found")
    assert fake.sectors == [] and fake.sent("claim") == [] and fake.received == []
    assert page.evaluate("window.__lf.outbox()") == []
    assert errors == []


def test_finds_from_before_the_void_stay_in_your_notes_marked_where_they_are(page: Page, site_url, errors):
    words = known_words(page, site_url, OUTSIDE_WORDS)
    notes = [
        {"w": w[0], "x": w[1], "y": w[2], "d": w[3], "t": NOW_MS - 86_400_000, "s": 0, "f": 1}
        for w in (words["void"], words["wilds"])
    ]
    page.add_init_script(
        f"if (!localStorage.getItem('letterfield.finds.v4')) localStorage.setItem('letterfield.finds.v4', {json.dumps(json.dumps(notes))})"
    )
    open_game(page, site_url, FakeSurvey(totals={"charted": 9, "total": 99, "players": 1}))
    open_notes(page)
    expect(page.locator("#tWords")).to_have_text("2")
    expect(page.locator(".find", has_text=words["void"][0]).locator(".find-meta")).to_have_text("the void")
    expect(page.locator(".find", has_text=words["wilds"][0]).locator(".find-meta")).to_have_text("the wilds")
    expect(page.locator("#surveyText")).to_have_text("0 of them charted first by you")
    assert errors == []


def test_without_the_survey_there_is_no_edge(page: Page, site_url, errors):
    """Playing alone, the map has no edge: no void, no wilds, and the void's letters can be circled."""
    words = known_words(page, site_url, OUTSIDE_WORDS)
    start_at(page, EDGE0 - 20, 6)
    open_game(page, site_url, None)
    expect(page.locator("html")).to_have_attribute("data-zone", "inside")
    expect(page.locator("#tName")).not_to_have_text("The void")
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", words["void"])
    expect(page.locator("#tWords")).to_have_text("1", timeout=10_000)
    assert SURVEY not in page.url
    assert errors == []
