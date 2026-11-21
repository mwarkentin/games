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


# The music out past the edge: the place's own, made offline here, needing no speakers.
PLACE_SOUND = """async ([key, seed, secs]) => {
  const a = new OfflineAudioContext(2, 44100 * secs, 44100), oscs = [], make = a.createOscillator.bind(a);
  a.createOscillator = () => {
    const o = make(), r = { start: null, stop: null }, start = o.start.bind(o), stop = o.stop.bind(o);
    oscs.push(r);
    o.start = (t = 0) => { r.start = t; start(t); };
    o.stop = (t = 0) => { r.stop = Math.max(t, a.currentTime); stop(t); };
    return o;
  };
  const t = window.__lf.placeTracks[key](a, a.destination, seed);
  t.bus.gain.value = .45;
  t.play(secs);
  const d = (await a.startRendering()).getChannelData(0);
  let s = 0; for (const x of d) s += x * x;
  t.play(600);  // ten minutes more, scheduled at once, to count its voices
  const ev = [];
  for (const r of oscs) if (r.start !== null) ev.push([r.start, 1], [r.stop === null ? 1e9 : r.stop, -1]);
  ev.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
  let k = 0, most = 0;
  for (const [, n] of ev) most = Math.max(most, k += n);
  t.stop();
  return { rms: Math.sqrt(s / d.length), most, left: t.nodes.size, unstopped: oscs.filter(r => r.start !== null && r.stop === null).length };
}"""


def test_hinterland_and_dripstone_make_sound_keep_to_their_voices_and_stop_cleanly(page: Page, site_url, errors):
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("!!(window.__lf && window.__lf.placeTracks)")
    for key, quiet, loud in (("wilds", 0.002, 0.1), ("void", 0.0003, 0.05)):
        for seed in (1, 2):
            got = page.evaluate(PLACE_SOUND, [key, seed, 14])
            assert quiet < got["rms"] < loud, (key, seed, got)
            assert got["most"] <= 20, (key, seed, got)  # about twenty oscillators at most, to go easy on phones
            assert got["left"] == 0 and got["unstopped"] == 0, (key, seed, got)
    assert errors == []


def test_out_past_the_edge_the_music_is_the_places_own(page: Page, site_url, errors):
    """In the void no music plays, only Dripstone's drips; in the wilds only Hinterland, which the
    pieces' turns don't move on from; back in the universe they take turns again."""
    page.add_init_script(
        "localStorage.setItem('letterfield.music.v1', '1'); localStorage.setItem('letterfield.musicpiece.v1', '2');"
    )
    start_at(page, EDGE0 + 14, 6)
    open_game(page, site_url, FakeSurvey())
    page.keyboard.press("Shift")  # the first key starts the music
    page.wait_for_function("window.__lf.music() !== null")
    music = "window.__lf.music() && [window.__lf.music().place, window.__lf.music().track]"
    name, step = page.locator("#pieceName"), page.locator("#musicNext")
    assert page.evaluate(music) == ["inside", "chimes"]
    expect(name).to_have_text("Chimes")

    move_to(page, EDGE0 - 30, 6)
    page.wait_for_function(f'JSON.stringify({music}) === \'["void","dripstone"]\'')
    expect(name).to_have_text("Dripstone")
    expect(step).to_be_disabled()

    move_to(page, -2568, 6)
    page.wait_for_function(f'JSON.stringify({music}) === \'["wilds","hinterland"]\'')
    expect(name).to_have_text("Hinterland")
    page.evaluate("window.__lf.music().swap()")  # a turn ends: out here it stays Hinterland
    assert page.evaluate(music) == ["wilds", "hinterland"]

    move_to(page, EDGE0 + 30, 6)
    page.wait_for_function(f'JSON.stringify({music}) === \'["inside","lantern"]\'')  # the turn that passed out there
    expect(name).to_have_text("Lantern")
    expect(step).to_be_enabled()
    assert errors == []
