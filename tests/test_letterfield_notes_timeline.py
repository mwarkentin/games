"""Letterfield's field notes as one timeline: your finds and the supernovas you saw, by time.

A supernova sits in the card of the visit it ended, when you were charting in its territory
then, or in a card of its own when it was seen from afar. The Supernovas pill narrows the
notes to them alone, still under their days.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from fake_leaderboard import without_worker
from fake_survey import FakeSurvey
from test_letterfield_survey import SHARE_SHEET_INIT, eventually, open_game, open_notes

# Lays out field notes and supernovas from a story: each entry is
# ['f', rx, ry, i, day, minute] for a find, the i-th word hidden in territory (rx, ry), or
# ['n', rx, ry, i, day, minute, by, mine, solo] for that territory going supernova with that
# word as its last; day 0 is today and -1 yesterday, minute counts from midnight.
STORY = """(story) => {
  const lf = window.__lf, day0 = new Date();
  day0.setHours(0, 0, 0, 0);
  const at = (day, minute) => { const d = new Date(day0); d.setDate(d.getDate() + day); return d.getTime() + minute * 60000; };
  const words = (rx, ry) => { const out = []; for (let cy = 0; cy < 4; cy++) for (let cx = 0; cx < 4; cx++) out.push(...lf.chunk(rx * 4 + cx, ry * 4 + cy).words); return out; };
  const finds = [], novas = [];
  for (const [k, rx, ry, i, day, minute, by, mine, solo] of story) {
    const w = words(rx, ry)[i], t = at(day, minute);
    if (k === 'f') finds.push({ w: w.w, x: w.x, y: w.y, d: w.d, t, s: 0 });
    else novas.push({ rx, ry, t, w: w.w, x: w.x, y: w.y, d: w.d, by: by || '', mine: !!mine, solo: !!solo });
  }
  localStorage.setItem('letterfield.finds.v4', JSON.stringify(finds));
  localStorage.setItem('letterfield.novas.v1', JSON.stringify(novas));
  localStorage.setItem('letterfield.coach.v1', '1');
  return { finds: finds.map(f => f.w), novas: novas.map(n => n.w) };
}"""

# The notes as a list: each day, each card's territory, and each row in it, a find's word or
# a supernova's last word.
SHAPE = """() => [...document.querySelectorAll('#finds > li')].flatMap(li =>
  li.classList.contains('day') ? ['day ' + li.textContent]
  : li.classList.contains('run') ? ['card ' + li.querySelector('.run-head b').textContent,
      ...[...li.querySelectorAll('li.row')].map(r => r.classList.contains('nova-row') ? 'nova ' + r.querySelector('.find-meta b.w').textContent : 'find ' + r.querySelector('.find-w').textContent)]
  : [li.className])"""

NAME = "([rx, ry]) => window.__lf.territoryName(rx, ry)"

# Today: a visit to (1, 0); before it, (5, -3) went supernova far off; before that, a visit
# to (0, 0) that ended with its last word, yours. Yesterday: a visit to (0, 1), (-2, 2) going
# supernova far off, then back to (0, 1).
DAYS = [
    ["f", 0, 1, 0, -1, 900],
    ["f", 0, 1, 1, -1, 905],
    ["n", -2, 2, 0, -1, 930, "SIS"],
    ["f", 0, 1, 2, -1, 960],
    ["f", 0, 0, 0, 0, 600],
    ["f", 0, 0, 1, 0, 605],
    ["f", 0, 0, 2, 0, 610],
    ["n", 0, 0, 2, 0, 610, "", True],
    ["n", 5, -3, 0, 0, 620, "ZED"],
    ["f", 1, 0, 0, 0, 630],
    ["f", 1, 0, 1, 0, 635],
]


def seed(page: Page, site_url: str, story: list, viewport: dict | None = None) -> dict:
    """Opens the game alone with the notes and supernovas `story` lays out, and opens the notes."""
    without_worker(page, site_url, "letterfield")
    page.set_viewport_size(viewport or {"width": 390, "height": 844})
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    words = page.evaluate(STORY, story)
    page.reload()
    page.wait_for_function(f"window.__lf && window.__lf.found.size === {len(words['finds'])}")
    open_notes(page)
    return words


def test_supernovas_take_their_place_among_the_finds_by_time(page: Page, site_url, errors):
    words = seed(page, site_url, DAYS)
    f, n = words["finds"], words["novas"]
    name = {k: page.evaluate(NAME, k) for k in [(0, 1), (-2, 2), (0, 0), (5, -3), (1, 0)]}
    assert page.evaluate(SHAPE) == [
        "day Today",
        f"card {name[(1, 0)]}",
        f"find {f[7]}",
        f"find {f[6]}",
        # Seen from afar: a card of its own.
        f"card {name[(5, -3)]}",
        f"nova {n[2]}",
        # The visit it ended: in its card, above the word that set it off.
        f"card {name[(0, 0)]}",
        f"nova {n[1]}",
        f"find {f[5]}",
        f"find {f[4]}",
        f"find {f[3]}",
        "day Yesterday",
        f"card {name[(0, 1)]}",
        f"find {f[2]}",
        f"card {name[(-2, 2)]}",
        f"nova {n[0]}",
        f"card {name[(0, 1)]}",
        f"find {f[1]}",
        f"find {f[0]}",
    ]
    # Each says what happened, in a sentence a screen reader reads as one.
    mine = page.locator('#finds a.nova-find[data-nova="0,0"]')
    expect(mine).to_have_attribute(
        "aria-label", f"{name[(0, 0)]} went supernova when you charted its last hidden word, {n[1]}; fly there"
    )
    expect(mine.locator(".find-meta")).to_have_text(f"{n[1]} · you")
    expect(mine.locator(".find-meta b.you")).to_have_text("you")
    far = page.locator('#finds a.nova-find[data-nova="5,-3"]')
    expect(far).to_have_attribute(
        "aria-label", f"{name[(5, -3)]} went supernova when ZED charted its last hidden word, {n[2]}; fly there"
    )
    expect(far.locator(".find-meta")).to_have_text(f"{n[2]} · ZED")
    # The separate list of supernovas is gone.
    expect(page.locator("#novasSec, #novaList")).to_have_count(0)
    assert errors == []


def test_the_supernovas_pill_shows_them_alone_under_their_days(page: Page, site_url, errors):
    words = seed(page, site_url, DAYS)
    n = words["novas"]
    pills = page.locator("#filters .filter")
    # All counts words, as the tally does; the star's pill counts supernovas, and comes next.
    expect(pills.nth(0)).to_have_text("All 8")
    expect(page.locator("#tWords")).to_have_text("8")
    nova = pills.nth(1)
    expect(nova).to_have_text("Supernovas 3")
    expect(nova.locator("svg.nova-star")).to_have_count(1)
    expect(nova).to_have_attribute("aria-pressed", "false")
    nova.click()
    expect(nova).to_have_attribute("aria-pressed", "true")
    expect(pills.nth(0)).to_have_attribute("aria-pressed", "false")
    name = {k: page.evaluate(NAME, k) for k in [(-2, 2), (0, 0), (5, -3)]}
    assert page.evaluate(SHAPE) == [
        "day Today",
        f"card {name[(5, -3)]}",
        f"nova {n[2]}",
        f"card {name[(0, 0)]}",
        f"nova {n[1]}",
        "day Yesterday",
        f"card {name[(-2, 2)]}",
        f"nova {n[0]}",
    ]
    # A theme's pill keeps its territories' supernovas, though it counts their words.
    theme = page.locator('#finds li.run:has(a[data-nova="0,0"]) .run-head span').text_content()
    pill = page.locator("#filters .filter.mark", has_text=theme)
    expect(pill).to_have_text(f"{theme} 3")
    pill.click()
    expect(page.locator('#finds a[data-nova="0,0"]')).to_have_count(1)
    expect(page.locator("#finds li.row:not(.nova-row)")).to_have_count(3)
    # Back to everything, from the keyboard: the pill pressed keeps focus once they're redrawn.
    pills.nth(0).focus()
    page.keyboard.press("Enter")
    expect(pills.nth(0)).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("document.activeElement.dataset.f") == ""
    expect(page.locator("#finds li.nova-row")).to_have_count(3)
    assert errors == []


def test_the_pill_shows_with_one_theme_of_finds(page: Page, site_url, errors):
    seed(page, site_url, [["f", 0, 0, 0, 0, 600], ["f", 0, 0, 1, 0, 605], ["n", 5, -3, 0, 0, 620, "ZED"]])
    expect(page.locator("#filters .filter")).to_have_count(3)  # All, Supernovas and the one theme
    expect(page.locator("#filters .nova-pill")).to_have_text("Supernovas 1")
    assert errors == []


def test_with_no_words_yet_the_supernovas_still_show(page: Page, site_url, errors):
    words = seed(page, site_url, [["n", 5, -3, 0, 0, 620, "ZED"], ["n", -2, 2, 0, -1, 930, "SIS"]])
    empty = page.locator("#finds .finds-empty")
    expect(empty).to_contain_text("No words yet")
    expect(empty).to_contain_text("among the supernovas you’ve seen")
    expect(page.locator("#finds li.nova-row")).to_have_count(2)
    expect(page.locator("#filters .filter")).to_have_text(["All 0", "Supernovas 2"])
    page.click("#filters .nova-pill")
    expect(empty).to_have_count(0)
    expect(page.locator("#finds li.nova-row")).to_have_count(2)
    # Another tab clears them while the pill has focus: back to All, which takes the focus.
    page.focus("#filters .nova-pill")
    other = page.context.new_page()
    other.goto(page.url.split("#")[0])
    other.evaluate("localStorage.setItem('letterfield.novas.v1', '[]')")
    expect(page.locator("#filters .filter")).to_have_count(0)
    expect(page.locator("#finds .finds-empty")).to_contain_text("Circle a word on the map")
    expect(page.locator("#finds li.nova-row")).to_have_count(0)
    assert words["novas"]
    assert errors == []


def test_with_supernovas_filtered_and_none_left_the_notes_show_all(page: Page, site_url, errors):
    seed(page, site_url, [["f", 0, 0, 0, 0, 600], ["n", 5, -3, 0, 0, 620, "ZED"]])
    page.locator("#filters .nova-pill").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#finds li.row")).to_have_count(1)
    other = page.context.new_page()
    other.goto(page.url.split("#")[0])
    other.evaluate("localStorage.setItem('letterfield.novas.v1', '[]')")
    expect(page.locator("#filters .nova-pill")).to_have_count(0)
    expect(page.locator("#finds li.row")).to_have_count(1)
    expect(page.locator("#finds li.nova-row")).to_have_count(0)
    # With one theme and no supernovas there's nothing to filter, so no pills.
    expect(page.locator("#filters .filter")).to_have_count(0)
    assert errors == []


def test_tapping_a_supernova_flies_to_its_last_word_and_share_shares_it(page: Page, site_url, errors):
    page.add_init_script(SHARE_SHEET_INIT)
    words = seed(page, site_url, DAYS)
    row = page.locator('#finds li.nova-row:has(a[data-nova="-2,2"])')
    row.locator(".find-share").click()
    page.wait_for_function("window.__shared.length === 1")
    shared = page.evaluate("window.__shared[0]")
    place = page.evaluate(NAME, [-2, 2])
    assert (
        shared["text"]
        == f"{place} went supernova in Letterfield’s shared survey: every hidden word charted, the last, {words['novas'][0]}, by SIS."
    )
    assert shared["url"].endswith("/letterfield-log?territory=-2,2")
    row.locator("a.nova-find").click()
    # On a phone the notes go, and the map flies to the word, far off.
    expect(page.locator("html")).not_to_have_attribute("data-panel", "notes")
    page.wait_for_function(
        """() => {
      const lf = window.__lf, n = lf.novas().find(n => n.rx === -2), [ex, ey] = lf.wordEnd(n);
      return Math.abs(lf.cam.x - ((n.x + ex) / 2 + .5)) < .05 && Math.abs(lf.cam.y - ((n.y + ey) / 2 + .5)) < .05;
    }""",
        timeout=8000,
    )
    assert errors == []


@pytest.mark.parametrize("motion", ["no-preference", "reduce"])
def test_a_supernova_arriving_while_the_notes_are_open_joins_them_in_place(page: Page, site_url, errors, motion):
    page.emulate_media(reduced_motion=motion)
    fake = FakeSurvey()
    open_game(page, site_url, fake)
    eventually(page, lambda: "0,0" in fake.sockets)
    # Sixty finds in (0, 0), so the notes scroll.
    page.evaluate("""() => {
      const lf = window.__lf, out = [], t = Date.now() - 3600000;
      for (let cy = 0; cy < 4; cy++) for (let cx = 0; cx < 4; cx++) out.push(...lf.chunk(cx, cy).words);
      localStorage.setItem('letterfield.finds.v4', JSON.stringify(out.slice(0, 60).map((w, i) => ({ w: w.w, x: w.x, y: w.y, d: w.d, t: t + i * 1000, s: 0 }))));
    }""")
    page.reload()
    page.wait_for_function("window.__lf && window.__lf.found.size === 60")
    eventually(page, lambda: "0,0" in fake.sockets)
    open_notes(page)
    # Scrolled down the list, with focus on a find's share button.
    held = page.evaluate("""() => {
      const sc = document.getElementById('notes').classList.contains('has-survey') ? document.getElementById('notes') : document.getElementById('finds');
      sc.scrollTop = 900;
      const top = sc.getBoundingClientRect().top;
      const a = [...document.querySelectorAll('#finds a.find')].find(a => a.getBoundingClientRect().top > top + 60);
      a.parentElement.querySelector('.find-share').focus();
      return { key: a.dataset.key, y: a.getBoundingClientRect().top, scrolled: sc.scrollTop };
    }""")
    assert held["scrolled"] > 0
    word = page.evaluate("window.__lf.chunk(16, 0).words.map(o => [o.w, o.x, o.y, o.d])[0]")
    fake.nova("0,0", 4, 0, word, "SIS")
    row = page.locator('#finds li.nova-row:has(a[data-nova="4,0"])')
    expect(row).to_have_count(1)
    # Newest, it's at the top, while what was in view stays where it was, focus and all.
    assert page.evaluate("document.querySelector('#finds li.row').classList.contains('nova-row')")
    after = page.evaluate(
        """key => {
      const a = document.querySelector(`#finds a.find[data-key="${key}"]`);
      return { y: a.getBoundingClientRect().top, focused: document.activeElement.classList.contains('find-share') && document.activeElement.dataset.key };
    }""",
        held["key"],
    )
    assert abs(after["y"] - held["y"]) <= 2, (held, after)
    assert after["focused"] == held["key"]
    # It glows once as it arrives, unless motion is reduced.
    assert row.evaluate("e => e.classList.contains('fresh')")
    animations = row.evaluate("e => e.getAnimations().length")
    assert animations == (0 if motion == "reduce" else 1)
    assert errors == []


def test_a_long_survey_opens_its_notes_at_once_and_draws_more_as_it_scrolls(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    # 25,000 finds in visits of 25 words to 1,000 territories, a third ending in a supernova,
    # and 667 more supernovas seen from afar.
    page.evaluate("""() => {
      const lf = window.__lf, finds = [], novas = [], start = Date.now() - 120 * 86400000;
      const words = (rx, ry) => { const out = []; for (let cy = 0; cy < 4; cy++) for (let cx = 0; cx < 4; cx++) out.push(...lf.chunk(rx * 4 + cx, ry * 4 + cy).words); return out; };
      let t = start;
      for (let r = 0; r < 1000; r++) {
        const rx = r % 50 - 25, ry = Math.floor(r / 50) - 10, ws = words(rx, ry).slice(0, 25);
        for (const w of ws) { t += 15000; finds.push({ w: w.w, x: w.x, y: w.y, d: w.d, t, s: 0 }); }
        if (r % 3 === 1) { const w = ws[ws.length - 1]; novas.push({ rx, ry, t, w: w.w, x: w.x, y: w.y, d: w.d, by: '', mine: true, solo: false }); }
        t += 9000000;
      }
      for (let a = 0; a < 667; a++) { const rx = 200 + a, ry = -100, w = words(rx, ry)[0]; novas.push({ rx, ry, t: start + a * 15000000, w: w.w, x: w.x, y: w.y, d: w.d, by: 'ZED', mine: false, solo: false }); }
      localStorage.setItem('letterfield.finds.v4', JSON.stringify(finds));
      localStorage.setItem('letterfield.novas.v1', JSON.stringify(novas));
      localStorage.setItem('letterfield.notes.v1', '0');
      localStorage.setItem('letterfield.coach.v1', '1');
    }""")
    page.reload()
    page.wait_for_function(
        "window.__lf && window.__lf.found.size === 25000 && window.__lf.novas().length === 1000", timeout=60_000
    )
    expect(page.locator("html")).not_to_have_attribute("data-panel", "notes")
    took = page.evaluate(
        """() => { const t = performance.now(); document.getElementById('notesToggle').click(); document.body.offsetHeight; return performance.now() - t; }"""
    )
    assert took < 1000, took  # drawing every entry took seconds
    expect(page.locator("#filters .nova-pill")).to_have_text("Supernovas 1000")
    rows = page.locator("#finds li.row")
    first = rows.count()
    assert 200 <= first <= 400, first
    expect(page.locator("#finds .finds-more")).to_have_count(1)
    # Scrolled near its end, the list draws the next page, carrying on its days and cards.
    page.evaluate("document.getElementById('finds').scrollTop = 1e9")
    page.wait_for_function(f"document.querySelectorAll('#finds li.row').length > {first}")
    days = page.evaluate("[...document.querySelectorAll('#finds > li.day')].map(li => li.textContent)")
    assert len(days) == len(set(days)), days
    # Each card is one visit: never the same territory twice in a row on one day.
    cards = page.evaluate("""() => { const out = []; let day = ''; for (const li of document.querySelectorAll('#finds > li')) {
      if (li.classList.contains('day')) day = li.textContent; else if (li.classList.contains('run')) out.push(day + '|' + li.querySelector('.run-head b').textContent); }
      return out; }""")
    assert all(a != b for a, b in zip(cards, cards[1:], strict=False))
    # The Supernovas pill shows them under their days, a page at a time too.
    took = page.evaluate(
        """() => { const t = performance.now(); document.querySelector('#filters .nova-pill').click(); document.body.offsetHeight; return performance.now() - t; }"""
    )
    assert took < 1000, took
    assert 200 <= page.locator("#finds li.nova-row").count() <= 400
    expect(page.locator("#finds li.row:not(.nova-row)")).to_have_count(0)
    assert errors == []


def test_notes_scrolled_deep_draw_a_page_again_once_closed_or_back_at_the_top(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    # 2,000 finds in visits of 25 words to 80 territories.
    page.evaluate("""() => {
      const lf = window.__lf, finds = [], start = Date.now() - 40 * 86400000;
      const words = (rx, ry) => { const out = []; for (let cy = 0; cy < 4; cy++) for (let cx = 0; cx < 4; cx++) out.push(...lf.chunk(rx * 4 + cx, ry * 4 + cy).words); return out; };
      let t = start;
      for (let r = 0; r < 80; r++) {
        const rx = r % 10 - 5, ry = Math.floor(r / 10) - 4;
        for (const w of words(rx, ry).slice(0, 25)) { t += 15000; finds.push({ w: w.w, x: w.x, y: w.y, d: w.d, t, s: 0 }); }
        t += 9000000;
      }
      localStorage.setItem('letterfield.finds.v4', JSON.stringify(finds));
      localStorage.setItem('letterfield.notes.v1', '0');
      localStorage.setItem('letterfield.coach.v1', '1');
    }""")
    page.reload()
    page.wait_for_function("window.__lf && window.__lf.found.size === 2000")
    rows = page.locator("#finds li.row")

    def scroll_to_the_end():
        while page.locator("#finds .finds-more").count():
            n = rows.count()
            page.evaluate(
                "document.getElementById('notes').scrollTop = document.getElementById('finds').scrollTop = 1e9"
            )
            page.wait_for_function(f"document.querySelectorAll('#finds li.row').length > {n}")
        assert rows.count() == 2000

    open_notes(page)
    assert rows.count() <= 400
    scroll_to_the_end()
    # Shut and opened again, the notes start a page long, not with every row scrolled through.
    page.click("#notesToggle")
    expect(page.locator("html")).not_to_have_attribute("data-panel", "notes")
    open_notes(page)
    assert rows.count() <= 400, rows.count()
    # Scrolled deep, then back to the top, the next redraw (a find here) draws a page too.
    scroll_to_the_end()
    page.evaluate("document.getElementById('notes').scrollTop = document.getElementById('finds').scrollTop = 0")
    page.evaluate(
        """() => { const lf = window.__lf, w = lf.chunk(40, 40).words[0]; lf.collect(w.w, w.x, w.y, w.d); }"""
    )
    page.wait_for_function("window.__lf.found.size === 2001")
    expect(page.locator("#finds li.row").first).to_be_visible()
    assert rows.count() <= 401, rows.count()
    assert errors == []
