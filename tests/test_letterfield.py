import re

import pytest
from playwright.sync_api import Page, expect

from fake_leaderboard import without_worker

# Screen positions of a legend word's first and last letters, for a word whose
# ends are both on open map rather than under a panel. Mirrors the game's
# camera: it starts centred on cell (6, 6) with 38px cells, in the middle of
# the map, which ends at the bottom bar.
FIND_WORD_JS = """() => {
  const cs = 38, start = 6, canvas = document.getElementById('map');
  const dock = document.body.classList.contains('docked') ? 340 : 0;
  const dirs = [[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1],[0,-1],[1,-1]];
  const screen = (x, y) => [(x + .5 - start) * cs + (innerWidth - dock) / 2, (y + .5 - start) * cs + (m => m.getBoundingClientRect().top + m.clientHeight / 2)(document.getElementById('map'))];
  for (const chip of document.querySelectorAll('#legendList .chip:not(.found)')) {
    const [word, x, y, d] = chip.dataset.key.split('~');
    const n = word.length - 1, [dx, dy] = dirs[+d];
    const ends = [screen(+x, +y), screen(+x + dx * n, +y + dy * n)];
    if (ends.every(([sx, sy]) => document.elementFromPoint(sx, sy) === canvas)) return { word, ends };
  }
  return null;
}"""

# A find's circle flies into the field notes, and the count ticks up as it
# lands: this long, at most, after the find.
LANDS = 10_000


def share_from_notes(page: Page, word: str) -> None:
    """Shares a find from the field notes, where every find can be shared."""
    if page.locator("#notesToggle").get_attribute("aria-expanded") != "true":
        page.click("#notesToggle")
    page.locator("#finds").get_by_role("button", name=f"Share {word}").click()


def test_circling_a_word_adds_it_to_field_notes(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")  # alone, so the word list gives hints
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{site_url}/letterfield")
    page.click("#coachOk")
    expect(page.locator("#coach")).to_be_hidden()
    expect(page.locator("#legendList .chip").first).to_be_visible()

    target = page.evaluate(FIND_WORD_JS)
    assert target, "no legend word with both ends on open map"
    for x, y in target["ends"]:
        page.mouse.click(x, y)
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
    expect(page.locator("#findSay")).to_contain_text(target["word"])

    # Finds are kept in this browser and survive a reload.
    page.reload()
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
    assert errors == []


def test_finds_from_an_older_map_carry_over_if_still_there(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    # One hidden word on today's map, and the same word somewhere it isn't. The
    # survey started over with the map, so being first to it doesn't carry over.
    word = page.evaluate("() => { const { w, x, y, d } = window.__lf.chunk(0, 0).words[0]; return { w, x, y, d }; }")
    old = [{**word, "t": 1, "s": 0, "f": 1, "n": 12}, {**word, "x": word["x"] + 4800, "t": 2, "s": 0}]
    page.evaluate(
        """old => {
          localStorage.setItem('letterfield.finds.v2', JSON.stringify([old[1]]));
          localStorage.setItem('letterfield.finds.v3', JSON.stringify(old));
          localStorage.removeItem('letterfield.finds.v4');
          localStorage.setItem('letterfield.coach.v1', '1');
        }""",
        old,
    )
    page.goto(f"{site_url}/letterfield")
    expect(page.locator("#toast")).to_contain_text("The map has been redrawn")
    expect(page.locator("#toast")).to_contain_text("1 of your 2 finds are still on it")
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
    # A long note stays on a phone's screen, padding and all, and wraps rather than cutting off.
    box = page.locator("#toast").bounding_box()
    assert box["x"] >= 16 and box["x"] + box["width"] <= 375 - 16, box
    line = page.locator("#toast span")
    assert line.evaluate("e => e.scrollWidth <= e.clientWidth"), "the note's line is cut off"
    saved = page.evaluate("() => [localStorage.getItem('letterfield.finds.v3'), JSON.parse(localStorage.getItem('letterfield.finds.v4'))]")
    assert len(saved[1]) == 1 and saved[1][0]["w"] == word["w"]
    assert "f" not in saved[1][0] and "n" not in saved[1][0]
    assert saved[0] is not None, "the old notes are left as they were"

    # The note shows once.
    page.reload()
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=LANDS)
    page.wait_for_timeout(1500)
    expect(page.locator("#toast")).not_to_contain_text("redrawn")
    assert errors == []


# Counts AudioContexts, to check sound waits for the player's first tap or key.
COUNT_AUDIO = """
window.__audio = 0;
const Real = window.AudioContext;
window.AudioContext = class extends Real { constructor(...a) { super(...a); window.__audio++; } };
localStorage.setItem('letterfield.coach.v1', '1');
"""
TERRITORY_WORDS = """() => {
  const out = [];
  for (let cy = 0; cy < 4; cy++) for (let cx = 0; cx < 4; cx++) for (const o of window.__lf.chunk(cx, cy).words) out.push([o.w, o.x, o.y, o.d]);
  return out;
}"""
COLLECT = "words => { for (const [w, x, y, d] of words) window.__lf.collect(w, x, y, d, false); }"


def test_finding_every_word_in_a_territory_goes_supernova(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")  # alone, so the territory counts your own finds
    page.add_init_script(COUNT_AUDIO)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    words = page.evaluate(TERRITORY_WORDS)
    page.evaluate(COLLECT, words[1:])
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words) - 1}/{len(words)} found")
    assert page.evaluate("window.__audio") == 0, "no sound before the first tap or key"

    page.keyboard.press("Shift")
    page.evaluate(COLLECT, words[:1])
    expect(page.locator("#tCharted")).to_have_text(f" · {len(words)}/{len(words)} found")
    assert page.evaluate("window.__lf.nova() !== null")
    assert page.evaluate("window.__audio") == 1
    expect(page.locator("#nova")).to_be_visible(timeout=5000)
    expect(page.locator("#nova")).to_contain_text("Supernova")
    expect(page.locator("#novaText")).to_contain_text(f"all {len(words)} hidden words found")
    # It plays out, then the map is back to normal, and a note offers to share it.
    expect(page.locator("#nova")).to_be_hidden(timeout=10000)
    page.wait_for_function("window.__lf.nova() === null", timeout=5000)
    expect(page.locator("#toast")).to_contain_text("Supernova · kept in your field notes")
    expect(page.locator("#toast .share")).to_be_visible()
    # Your field notes keep it: alone, it was all yours.
    if page.locator("#notes").is_hidden():
        page.click("#notesToggle")
    expect(page.locator("#novaList .find-meta")).to_have_text(f"Went supernova · {words[0][0]}, all found by you")
    record = page.evaluate("JSON.parse(localStorage.getItem('letterfield.novas.v1'))")
    assert [(n["rx"], n["ry"], n["w"], n["solo"], n["mine"]) for n in record] == [(0, 0, words[0][0], True, True)]
    # Sharing it alone links to the game, flying to its last word.
    page.evaluate("""() => { window.__shared = []; Object.defineProperty(navigator, 'share', { value: d => { window.__shared.push(d); return Promise.resolve(); }, configurable: true }); }""")
    page.locator("#novaList .find-share").click()
    page.wait_for_function("window.__shared.length === 1")
    shared = page.evaluate("window.__shared[0]")
    assert shared["text"].startswith("I found every hidden word in ") and shared["text"].endswith("in Letterfield, and it just went supernova.")
    w, x, y, d = words[0]
    assert shared["url"].endswith(f"/letterfield#f-{w.lower()}-{x}-{y}-{d}")
    assert errors == []


def open_tools(page: Page) -> None:
    """Opens the tools' stack from its button in the bottom bar."""
    page.click("#toolsBtn")
    expect(page.locator("#toolsBtn")).to_have_attribute("aria-expanded", "true")


def open_tools_quietly(page: Page) -> None:
    """Opens the tools' stack without a tap or key, either of which would start the audio."""
    page.evaluate("document.getElementById('toolsBtn').click()")
    expect(page.locator("#toolsBtn")).to_have_attribute("aria-expanded", "true")


def test_sound_can_be_switched_off(page: Page, site_url, errors):
    page.add_init_script(COUNT_AUDIO)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    open_tools_quietly(page)
    sound = page.locator("#sound")
    expect(sound).to_have_attribute("aria-pressed", "true")
    sound.click()
    expect(sound).to_have_attribute("aria-pressed", "false")
    page.evaluate("window.__lf.supernova(2, 2, { mine: true })")
    assert page.evaluate("window.__audio") == 0
    page.reload()
    expect(page.locator("#sound")).to_have_attribute("aria-pressed", "false")
    page.keyboard.press("m")
    expect(page.locator("#sound")).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("window.__audio") == 1
    assert errors == []


def test_supernova_with_reduced_motion_keeps_still(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script(COUNT_AUDIO)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    cam = page.evaluate("({ ...window.__lf.cam })")
    page.evaluate("window.__lf.supernova(0, 0, { mine: true })")
    expect(page.locator("#nova")).to_be_visible(timeout=5000)
    assert page.evaluate("({ ...window.__lf.cam })") == cam
    assert errors == []


def test_music_starts_off_and_can_be_switched_on_and_off(page: Page, site_url, errors):
    page.add_init_script(COUNT_AUDIO)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    open_tools_quietly(page)
    music = page.locator("#music")
    expect(music).to_have_attribute("aria-pressed", "false")
    page.keyboard.press("Shift")
    assert page.evaluate("window.__lf.music()") is None, "no music until it's switched on"

    music.click()
    expect(music).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("localStorage.getItem('letterfield.music.v1')") == "1"
    page.wait_for_function("window.__lf.music() && window.__lf.music().level > 0")
    # Sound effects keep their own switch.
    expect(page.locator("#sound")).to_have_attribute("aria-pressed", "true")

    page.keyboard.press("b")
    expect(music).to_have_attribute("aria-pressed", "false")
    assert page.evaluate("localStorage.getItem('letterfield.music.v1')") == "0"
    assert page.evaluate("window.__lf.music()") is None

    # The choice is kept, and the music waits for a tap or key after a reload.
    page.keyboard.press("b")
    page.reload()
    page.wait_for_function("window.__lf")
    expect(page.locator("#music")).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("window.__audio") == 0
    page.keyboard.press("Shift")
    page.wait_for_function("window.__lf.music() !== null")
    assert page.evaluate("window.__audio") == 1
    assert errors == []


def test_music_fades_out_while_the_tab_is_hidden(page: Page, site_url, errors):
    page.add_init_script("localStorage.setItem('letterfield.coach.v1', '1'); localStorage.setItem('letterfield.music.v1', '1');")
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    page.keyboard.press("Shift")
    page.wait_for_function("window.__lf.music() && window.__lf.music().level > .1")
    hide = """hidden => {
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
      document.dispatchEvent(new Event('visibilitychange'));
    }"""
    page.evaluate(hide, True)
    page.wait_for_function("window.__lf.music().state === 'suspended'")
    page.evaluate(hide, False)
    page.wait_for_function("window.__lf.music().state === 'running' && window.__lf.music().level > .1")
    assert errors == []


def test_every_music_track_makes_sound_and_they_take_turns(page: Page, site_url, errors):
    page.add_init_script("localStorage.setItem('letterfield.coach.v1', '1'); localStorage.setItem('letterfield.music.v1', '1');")
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    # Each piece, rendered offline for a few seconds, is audible but quiet.
    levels = page.evaluate(
        """async () => {
          const out = [];
          for (const track of window.__lf.musicTracks) {
            const a = new OfflineAudioContext(2, 44100 * 12, 44100), t = track(a, a.destination);
            t.bus.gain.value = .45; t.play(12);
            const d = (await a.startRendering()).getChannelData(0);
            let s = 0; for (const x of d) s += x * x;
            out.push(Math.sqrt(s / d.length));
          }
          return out;
        }"""
    )
    assert len(levels) == 3
    assert all(0.001 < level < 0.2 for level in levels), levels
    page.keyboard.press("Shift")
    page.wait_for_function("window.__lf.music() !== null")
    # Each swap hands over to the next piece, and all three come round.
    heard = [page.evaluate("window.__lf.music().track")]
    for _ in range(3):
        page.evaluate("window.__lf.music().swap()")
        heard.append(page.evaluate("window.__lf.music().track"))
    assert sorted(set(heard)) == ["chimes", "drift", "orbit"], heard
    assert heard[3] == heard[0] and len(set(heard[:3])) == 3, heard
    assert errors == []


def test_chimes_starts_and_stops_cleanly(page: Page, site_url, errors):
    page.add_init_script("localStorage.setItem('letterfield.coach.v1', '1'); localStorage.setItem('letterfield.music.v1', '1');")
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    page.keyboard.press("Shift")
    page.wait_for_function("window.__lf.music() !== null")
    while page.evaluate("window.__lf.music().track") != "chimes":
        page.evaluate("window.__lf.music().swap()")
    # It schedules its notes as it plays, and its reverb rings out of the bus.
    page.wait_for_function("window.__lf.music().nodes > 4", timeout=5000)
    page.keyboard.press("b")
    expect(page.locator("#music")).to_have_attribute("aria-pressed", "false")
    page.wait_for_timeout(3200)  # past the fade, when the piece stops its oscillators
    page.keyboard.press("b")
    page.wait_for_function("window.__lf.music() !== null")
    assert errors == []


# A share sheet that keeps what it's given, for checking what a find shares.
SHARE_SHEET = """
  window.__shared = [];
  Object.defineProperty(navigator, 'share', { value: data => { window.__shared.push(data); return Promise.resolve(); }, configurable: true });
"""


def test_a_find_shares_what_it_is_where_and_a_link_to_it(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")
    page.add_init_script(SHARE_SHEET)
    page.set_viewport_size({"width": 375, "height": 740})
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    page.wait_for_function("window.__lf")
    words = page.evaluate("window.__lf.chunk(0, 0).words.slice(0, 2).map(o => [o.w, o.x, o.y, o.d])")
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", words[0])
    share_from_notes(page, words[0][0])
    shared = page.evaluate("window.__shared")
    w, x, y, d = words[0]
    assert len(shared) == 1 and shared[0]["title"] == "Letterfield"
    assert re.fullmatch(rf"I just found {w} in [^.]+ in Letterfield\. That’s word 1 in my field notes\.", shared[0]["text"]), shared[0]["text"]
    assert shared[0]["url"] == f"{site_url}/letterfield#f-{w.lower()}-{x}-{y}-{d}"
    assert page.evaluate("document.documentElement.scrollWidth") <= 375

    # Every find in the field notes can be shared, counted by when it was found.
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", words[1])
    notes = page.locator("#finds")
    notes.get_by_role("button", name=f"Share {words[1][0]}").click()
    notes.get_by_role("button", name=f"Share {w}").click()
    texts = [s["text"] for s in page.evaluate("window.__shared")[1:]]
    assert texts[0].endswith("That’s word 2 in my field notes.")
    assert texts[1].endswith("That’s word 1 in my field notes.")
    assert errors == []


def test_with_a_share_worker_a_find_links_to_its_card_in_the_sharers_theme(page: Page, site_url, errors):
    # ?share= stands in for SHARE_URL: the share Worker (share/), whose page
    # carries a picture of the word as its link preview.
    without_worker(page, site_url, "letterfield")
    page.add_init_script(SHARE_SHEET)
    page.goto(f"{site_url}/letterfield?share=https://share.test/#debug")
    page.click("#coachOk")
    page.wait_for_function("window.__lf")
    w, x, y, d = page.evaluate("(() => { const o = window.__lf.chunk(0, 0).words[0]; return [o.w, o.x, o.y, o.d]; })()")
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", [w, x, y, d])
    share_from_notes(page, w)
    slug = f"f-{w.lower()}-{x}-{y}-{d}"
    assert page.evaluate("window.__shared")[0]["url"] == f"https://share.test/f/{slug}"

    # A dark page shares the dark card.
    page.emulate_media(color_scheme="dark")
    page.reload()
    page.wait_for_function("window.__lf")
    expect(page.locator("html")).to_have_attribute("data-intro", "exploring")
    # The find is still in the field notes, which stay open from before.
    if page.locator("#notesToggle").get_attribute("aria-expanded") != "true":
        page.click("#notesToggle")
    page.locator("#finds").get_by_role("button", name=f"Share {w}").click()
    assert page.evaluate("window.__shared")[0]["url"] == f"https://share.test/f/d/{slug}"
    assert errors == []


def test_without_a_share_sheet_a_find_is_copied(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")
    page.add_init_script("""
      Object.defineProperty(Navigator.prototype, 'share', { value: undefined, configurable: true });
      Object.defineProperty(navigator, 'clipboard', { value: { writeText: t => { window.__copied = t; return Promise.resolve(); } } });
    """)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    page.wait_for_function("window.__lf")
    w, x, y, d = page.evaluate("(() => { const o = window.__lf.chunk(0, 0).words[0]; return [o.w, o.x, o.y, o.d]; })()")
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", [w, x, y, d])
    share_from_notes(page, w)
    expect(page.locator("#toast")).to_contain_text("Copied")
    copied = page.evaluate("window.__copied")
    assert copied.startswith(f"I just found {w} in ")
    assert copied.endswith(f" {site_url}/letterfield#f-{w.lower()}-{x}-{y}-{d}")
    assert errors == []


def test_every_tab_keeps_the_field_notes_found_in_the_others(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    # A find's link, or a word in the survey log, opened in a new tab.
    other = page.context.new_page()
    without_worker(other, site_url, "letterfield")
    other.goto(f"{site_url}/letterfield#debug")
    other.wait_for_function("window.__lf")
    words = page.evaluate("window.__lf.chunk(0, 0).words.slice(0, 2).map(o => [o.w, o.x, o.y, o.d])")
    page.evaluate(COLLECT, words[:1])
    other.evaluate(COLLECT, words[1:])
    # Neither tab's find is lost from the notes kept in this browser (tabs hear of each other's saves a moment later).
    stored = "() => (JSON.parse(localStorage.getItem('letterfield.finds.v4')) || []).map(o => o.w).sort().join(' ')"
    want = " ".join(sorted(w[0] for w in words))
    for _ in range(60):
        if page.evaluate(stored) == want and other.evaluate(stored) == want:
            break
        page.wait_for_timeout(50)
    assert page.evaluate(stored) == want, "a tab's save wrote over the other's find"
    # Each tab takes in the other's as it's saved.
    expect(page.locator("#notesBadge")).to_have_text("2", timeout=LANDS)
    expect(other.locator("#notesBadge")).to_have_text("2", timeout=LANDS)
    page.reload()
    expect(page.locator("#notesBadge")).to_have_text("2", timeout=LANDS)
    assert errors == []


def test_escape_while_dragging_a_circle_lets_it_go(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    cam = page.evaluate("({ ...window.__lf.cam })")
    page.mouse.move(500, 450)
    page.keyboard.down("Shift")  # Shift-drag circles
    page.mouse.down()
    page.mouse.move(560, 450, steps=4)
    page.keyboard.press("Escape")
    page.mouse.move(640, 450, steps=4)  # still holding the button
    page.mouse.up()
    page.keyboard.up("Shift")
    assert errors == []
    assert page.evaluate("({ ...window.__lf.cam })") == cam, "the rest of the drag doesn't pan either"
    expect(page.locator("#notesBadge")).to_have_text("0")


def test_music_left_on_starts_with_the_first_tap_on_its_button(page: Page, site_url, errors):
    page.add_init_script(COUNT_AUDIO + "localStorage.setItem('letterfield.music.v1', '1');")
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    open_tools_quietly(page)
    music = page.locator("#music")
    expect(music).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("window.__lf.music()") is None  # on, but waiting for a tap
    music.click()
    page.wait_for_function("window.__lf.music() !== null", timeout=3000)
    expect(music).to_have_attribute("aria-pressed", "true")
    music.click()  # and the next tap switches it off
    expect(music).to_have_attribute("aria-pressed", "false")
    assert page.evaluate("window.__lf.music()") is None
    assert errors == []


# How the word list's row of chips sits in its box.
CHIPS_JS = """() => {
  const ul = document.getElementById('legendList'), cs = getComputedStyle(ul);
  return { sh: ul.scrollHeight, ch: ul.clientHeight, sw: ul.scrollWidth, cw: ul.clientWidth,
           ox: cs.overflowX, oy: cs.overflowY, wrap: cs.flexWrap,
           n: ul.querySelectorAll('.chip').length };
}"""


def chips_scroll_only_sideways(page: Page) -> None:
    """The word list never scrolls up and down: it's one row along the bottom
    bar that scrolls sideways."""
    m = page.evaluate(CHIPS_JS)
    assert m["n"] > 0
    assert m["oy"] not in ("auto", "scroll"), m
    assert m["sh"] <= m["ch"], m
    # Every chip, struck through or not, sits inside the row's height.
    assert m["wrap"] == "nowrap" and m["ox"] == "auto", m


def test_the_word_list_never_scrolls_up_and_down(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")  # alone, so the words are buttons
    page.set_viewport_size({"width": 375, "height": 740})
    page.goto(f"{site_url}/letterfield")
    page.click("#coachOk")
    expect(page.locator("#legendList .chip").first).to_be_visible()
    # Fill the list with long words, some found, to push it as far as it goes.
    fill = """() => {
      const ul = document.getElementById('legendList');
      ul.innerHTML = Array.from({length: 14}, (_, i) =>
        `<li><button type="button" class="chip mark${i % 3 ? '' : ' found'}">${'QUARTERMASTER'.slice(0, 6 + i % 8)}</button></li>`).join('');
    }"""
    page.evaluate(fill)
    chips_scroll_only_sideways(page)
    m = page.evaluate(CHIPS_JS)
    assert m["sw"] > m["cw"], m  # too many to fit, so it scrolls sideways
    page.evaluate("document.getElementById('legendList').scrollLeft = 99999")
    assert page.evaluate("document.getElementById('legendList').scrollLeft") > 0
    assert page.evaluate("document.getElementById('legendList').scrollTop") == 0

    # A keyboard's focus ring still shows in full on the chip it's on.
    chip = page.locator("#legendList .chip:not(.found)").first
    chip.focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.matches('#legendList .chip:focus-visible')")
    assert page.evaluate("""() => {
      const ul = document.getElementById('legendList'), a = document.activeElement;
      const r = ul.getBoundingClientRect(), c = a.getBoundingClientRect();
      const o = parseFloat(getComputedStyle(a).outlineWidth) + parseFloat(getComputedStyle(a).outlineOffset);
      return c.top - o >= r.top && c.bottom + o <= r.bottom;
    }""")
    chips_scroll_only_sideways(page)

    page.set_viewport_size({"width": 1280, "height": 900})
    page.evaluate(fill)
    chips_scroll_only_sideways(page)
    assert errors == []


# Puts a hidden word's first letter's centre at screen position (sx, sy), with
# cells of cs pixels, and returns the word list once it has caught up.
PLACE_WORD_JS = """async ({ key, sx, sy, cs }) => {
  const lf = window.__lf, [, x, y] = key.split('~');
  const dock = document.body.classList.contains('docked') ? 340 : 0;
  lf.cam.cs = cs;
  lf.cam.x = +x + .5 - (sx - (innerWidth - dock) / 2) / cs;
  lf.cam.y = +y + .5 - (sy - (m => m.getBoundingClientRect().top + m.clientHeight / 2)(document.getElementById('map'))) / cs;
  dispatchEvent(new Event('resize'));
  await new Promise(r => setTimeout(r, 300));
  return {
    keys: [...document.querySelectorAll('#legendList .chip')].map(c => c.dataset.key),
    count: document.getElementById('legendCount').textContent,
  };
}"""


# Leaves only the given words on the map around them, so the word list, which
# names the fourteen nearest the middle, can't leave one out for being far off.
ONLY_WORDS_JS = """keys => {
  const lf = window.__lf;
  for (const key of keys) {
    const [, x, y] = key.split('~'), cx = Math.floor(x / 12), cy = Math.floor(y / 12);
    for (let j = cy - 10; j <= cy + 10; j++) for (let i = cx - 10; i <= cx + 10; i++) {
      const c = lf.chunk(i, j);
      c.words = c.words.filter(w => keys.includes(w.key));
    }
  }
}"""


def five_letter_words(page: Page) -> list[str]:
    """Keys of a five-letter word reading right, one reading down and one
    reading up, near where the map starts."""
    keys = page.evaluate("""() => {
      const keys = {};
      for (let cy = -3; cy <= 3; cy++) for (let cx = -3; cx <= 3; cx++)
        for (const w of window.__lf.chunk(cx, cy).words) if (w.w.length === 5) keys[w.d] ??= w.key;
      return [keys[0], keys[2], keys[6]];
    }""")
    assert all(keys), keys
    return keys


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_the_word_list_names_only_words_half_in_sight(page: Page, site_url, errors, size):
    without_worker(page, site_url, "letterfield")  # alone, so each chip names its word
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    expect(page.locator("#legendList .chip").first).to_be_visible()
    # Five-letter words reading right, down and up: each counts once any three
    # of its letters (half, rounded up) can be seen.
    across, down, up = keys = five_letter_words(page)
    page.evaluate(ONLY_WORDS_JS, keys)
    right = page.evaluate("innerWidth - (document.body.classList.contains('docked') ? 340 : 0)")
    mid = page.evaluate("(m => m.getBoundingClientRect().top + m.clientHeight / 2)(document.getElementById('map'))")

    def listed(key, sx, sy, cs=80):
        got = page.evaluate(PLACE_WORD_JS, {"key": key, "sx": sx, "sy": sy, "cs": cs})
        return key in got["keys"], got

    cs = 80
    seen, got = listed(across, right / 2 - 2 * cs, mid)
    assert seen, got  # all of it in the middle of the map
    seen, got = listed(across, right - 1.5 * cs, mid)
    assert not seen, got  # two letters at the right edge
    seen, got = listed(across, right - 2.5 * cs, mid)
    assert seen, got  # its first three at the right edge
    seen, got = listed(across, -1.5 * cs, mid)
    assert seen, got  # its last three at the left edge, where it starts
    seen, got = listed(across, -2.5 * cs, mid)
    assert not seen, got  # only its last two at the left edge

    # Letters under a panel over the map, or under the bottom bar where the map
    # ends, can't be seen either. A word reading away from the title box (down),
    # or from the bar (up), with its first three letters under the panel isn't
    # listed, and with only its first two there it is, where the rest lands on
    # open map. The open tools don't count, so opening them never reshuffles
    # the list.
    cs = 12
    open_tools(page)
    # On a phone the map starts below the top bar, which holds the title box.
    panels = [("#topbar" if size[0] < 700 else "header.cartouche", down), ("#bar", up)]
    for sel, key in panels:
        box = page.locator(sel).bounding_box()
        # Over the bar, at its left end: the open tools stand over its right.
        sx = box["x"] + 60 if sel == "#bar" else box["x"] + box["width"] / 2
        if key == down:  # the first letters just inside its bottom edge
            hidden3, hidden2 = box["y"] + box["height"] - 2.5 * cs, box["y"] + box["height"] - 1.5 * cs
        else:  # just inside its top edge
            hidden3, hidden2 = box["y"] + 2.5 * cs, box["y"] + 1.5 * cs
        seen, got = listed(key, sx, hidden3, cs)
        assert not seen, (sel, got)
        seen, got = listed(key, sx, hidden2, cs)
        assert seen, (sel, got)
    page.wait_for_timeout(400)  # done dropping down
    box = page.locator("#toolStack").bounding_box()
    seen, got = listed(down, box["x"] + box["width"] / 2, box["y"] + box["height"] - 2.5 * cs, cs)
    assert seen, ("#toolStack", got)
    assert errors == []


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_the_word_list_counts_only_whole_letters(page: Page, site_url, errors, size):
    """A letter cut by the map's edge or a panel isn't seen: a row or column
    half off the screen, or half under the title box or the tools, leaves its
    word off the list, and the same word moved fully into view is on it. Each
    letter's centre sits a pixel on the open side of the edge, so all of every
    cell's centre is in sight while every letter is cut."""
    without_worker(page, site_url, "letterfield")  # alone, so each chip names its word
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    expect(page.locator("#legendList .chip").first).to_be_visible()
    across, down, _ = keys = five_letter_words(page)
    page.evaluate(ONLY_WORDS_JS, keys)
    # Desktop docks the notes beside the map, so its right edge is theirs.
    right = page.evaluate("innerWidth - (document.body.classList.contains('docked') ? 340 : 0)")
    map_box = page.locator("#map").bounding_box()
    top, bottom = map_box["y"], map_box["y"] + map_box["height"]
    mid = (top + bottom) / 2

    def listed(key, sx, sy, cs):
        got = page.evaluate(PLACE_WORD_JS, {"key": key, "sx": sx, "sy": sy, "cs": cs})
        return key in got["keys"]

    # The smallest cells that show letters, middling ones and, on a desktop,
    # cells zoomed right in.
    bars = set()
    for cs in (9, 30) + ((80,) if size[0] >= 700 else ()):
        # (key, where its first letter is when cut, and when whole, what cuts it)
        cases = [
            (across, (right / 2 - 2 * cs, bottom - 1), (right / 2 - 2 * cs, bottom - .6 * cs), "bottom"),
            (down, (1, mid - 2 * cs), (.6 * cs, mid - 2 * cs), "left"),
            (down, (right - 1, mid - 2 * cs), (right - .6 * cs, mid - 2 * cs), "right"),
        ]
        cart = page.locator("header.cartouche").bounding_box()
        if cart["y"] + cart["height"] > top:  # over the map: a row half under it
            y = cart["y"] + cart["height"]
            cases.append((across, (cart["x"] + 1.5 * cs, y + 1), (cart["x"] + 1.5 * cs, y + .6 * cs), "cartouche"))
        else:  # above it, in the top bar: a row half off the map's top
            cases.append((across, (right / 2 - 2 * cs, top + 1), (right / 2 - 2 * cs, top + .6 * cs), "top"))
        tools = page.locator(".corner").bounding_box()
        if tools["y"] + tools["height"] > top and cs < 30:  # a column half under its left edge
            y0 = max(tools["y"], top) + .5 * cs
            cases.append((down, (tools["x"] - 1, y0), (tools["x"] - .6 * cs, y0), "tools"))
        for key, cut, whole, what in cases:
            assert not listed(key, *cut, cs), (what, cs, "cut")
            bars.add(page.locator("#bar").bounding_box()["height"])
            assert listed(key, *whole, cs), (what, cs, "whole")
            bars.add(page.locator("#bar").bounding_box()["height"])
    # The bar stays the same height, empty or not, so the map doesn't move
    # under a word as it comes and goes.
    assert len(bars) == 1, bars
    assert errors == []


# The words left to find in the territory the camera is in, as the game deals
# them, in the list's order.
TERRITORY_LEFT_JS = """() => {
  const lf = window.__lf, rx = Math.floor(Math.floor(lf.cam.x) / 48), ry = Math.floor(Math.floor(lf.cam.y) / 48);
  const left = [];
  for (let cy = ry * 4; cy < ry * 4 + 4; cy++) for (let cx = rx * 4; cx < rx * 4 + 4; cx++)
    for (const w of lf.chunk(cx, cy).words) if (!lf.found.has(w.key)) left.push(w.w);
  return left.sort();
}"""


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_the_word_list_can_name_every_word_left_in_the_territory(page: Page, site_url, errors, size):
    without_worker(page, site_url, "letterfield")  # alone, so in view the words are buttons
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    # One word of this territory found already, away from where the map starts.
    kept = page.evaluate("""() => {
      const { w, x, y, d } = window.__lf.chunk(3, 3).words[0];
      localStorage.setItem('letterfield.finds.v4', JSON.stringify([{ w, x, y, d, t: 1 }]));
      localStorage.setItem('letterfield.coach.v1', '1');
      return w;
    }""")
    page.reload()
    chips = page.locator("#legendList .chip")
    expect(chips.first).to_be_visible()
    view, whole = page.locator("#listView"), page.locator("#listWhole")
    expect(view).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#legendList button.chip").first).to_be_visible()
    in_view = chips.count()
    finds = 1
    if size[0] >= 700:  # and one circled in view
        target = page.evaluate(FIND_WORD_JS)
        assert target, "no legend word with both ends on open map"
        for x, y in target["ends"]:
            page.mouse.click(x, y)
        finds = 2
        # Found, it leaves the list rather than staying there crossed out.
        expect(page.locator(f'#legendList .chip:text-is("{target["word"]}")')).to_have_count(0)
        expect(page.locator("#legendList .found")).to_have_count(0)
    expect(page.locator("#notesBadge")).to_have_text(str(finds), timeout=LANDS)
    whole.click()
    expect(whole).to_have_attribute("aria-pressed", "true")
    expect(view).to_have_attribute("aria-pressed", "false")
    expect(page.locator(".legend")).to_have_attribute("aria-label", "Words left to find in this territory")

    # Every word not yet found, in alphabetical order. They're labels, with no
    # hint of where.
    left = page.evaluate(TERRITORY_LEFT_JS)
    assert len(left) > in_view and kept not in left
    expect(chips).to_have_text(left)
    expect(page.locator("#legendCount")).to_have_text(f"{len(left)} left")
    expect(page.locator("#legendList button")).to_have_count(0)

    # So many words never make the list scroll up and down, or the page sideways.
    m = page.evaluate(CHIPS_JS)
    assert m["oy"] not in ("auto", "scroll") and m["sh"] <= m["ch"], m
    assert m["ox"] == "auto" and m["sw"] > m["cw"], m
    # One row along the bottom bar, at any size.
    tops = page.evaluate("[...new Set([...document.querySelectorAll('#legendList .chip')].map(c => c.getBoundingClientRect().top))].length")
    assert tops == 1, tops
    if size[0] >= 700:
        page.locator("#legendList").hover()
        page.mouse.wheel(0, 300)  # a mouse wheel moves it sideways
        page.wait_for_function("document.getElementById('legendList').scrollLeft > 0")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    # Zoomed out too far to read the letters, it still lists them.
    page.evaluate("() => { window.__lf.cam.cs = 4; dispatchEvent(new Event('resize')); }")
    page.wait_for_timeout(300)
    expect(chips).to_have_text(left)

    # The choice is kept, and switching back lists what's in view again.
    page.reload()
    expect(whole).to_have_attribute("aria-pressed", "true")
    expect(chips).to_have_count(len(left))
    view.click()
    expect(view).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#legendList .legend-note, #legendList .chip").first).to_be_visible()
    assert chips.count() < len(left)
    assert errors == []


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_the_title_box_always_shows_how_many_words_are_found(page: Page, site_url, errors, size):
    without_worker(page, site_url, "letterfield")
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{site_url}/letterfield")
    page.click("#coachOk")
    expect(page.locator("#tCharted")).to_have_text(re.compile(r"^ · 0/\d+ found$"))
    # Even beside a long theme name, the count shows whole: the name gives way.
    page.evaluate("document.getElementById('tTheme').textContent = 'Pioneers of Science'")
    fits = page.evaluate("""() => {
      const meta = document.querySelector('.t-meta').getBoundingClientRect();
      const count = document.getElementById('tCharted').getBoundingClientRect();
      return count.width > 0 && count.left >= meta.left && count.right <= meta.right + .5;
    }""")
    assert fits
    # On a phone the grid reference makes room for it; a computer has room for both.
    expect(page.locator("#tCoord")).to_be_visible() if size[0] >= 700 else expect(page.locator("#tCoord")).to_be_hidden()
    assert errors == []


# The mean colour of the map over cells 1..10 of territory (0, 0), from the
# canvas itself (device pixels), where the camera starts.
TERRITORY_SHADE = """() => {
  const c = document.getElementById('map'), g = c.getContext('2d'), { cam } = window.__lf;
  const dock = document.body.classList.contains('docked') ? 340 : 0, k = c.width / innerWidth;
  const sx = x => ((x - cam.x) * cam.cs + (innerWidth - dock) / 2) * k, sy = y => ((y - cam.y) * cam.cs + document.getElementById('map').clientHeight / 2) * k;
  const x0 = Math.round(sx(1)), y0 = Math.round(sy(1)), w = Math.round(sx(11)) - x0, h = Math.round(sy(11)) - y0;
  const d = g.getImageData(x0, y0, w, h).data, m = [0, 0, 0];
  for (let i = 0; i < d.length; i += 4) for (let j = 0; j < 3; j++) m[j] += d[i + j];
  return m.map(v => v / (d.length / 4));
}"""


def open_with_finds(page: Page, site_url: str, skip: int) -> list:
    """Opens the game alone with every hidden word of territory (0, 0) but the first `skip` in the notes."""
    without_worker(page, site_url, "letterfield")
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    words = page.evaluate(TERRITORY_WORDS)
    finds = [{"w": w, "x": x, "y": y, "d": d, "t": 1_793_000_000_000 + i, "s": 0} for i, (w, x, y, d) in enumerate(words[skip:])]
    page.evaluate("finds => { localStorage.setItem('letterfield.finds.v4', JSON.stringify(finds)); localStorage.setItem('letterfield.coach.v1', '1'); }", finds)
    page.reload()
    page.wait_for_function("window.__lf")
    page.wait_for_timeout(300)
    return words


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_territory_you_found_every_word_of_stays_a_remnant(page: Page, site_url, errors, scheme):
    page.emulate_media(color_scheme=scheme)
    page.set_viewport_size({"width": 1280, "height": 900})
    open_with_finds(page, site_url, 1)
    assert page.evaluate("window.__lf.remnants()") == []
    before = page.evaluate(TERRITORY_SHADE)
    open_with_finds(page, site_url, 0)
    assert page.evaluate("window.__lf.remnants()") == ["0,0"]
    after = page.evaluate(TERRITORY_SHADE)
    # A deeper tint: darker on paper; on the dark map, darker still.
    assert sum(after) < sum(before) - (30 if scheme == "light" else 6), (before, after)
    # Zoomed right out, it's a darker patch of the far view too.
    page.evaluate("window.__lf.cam.cs = 0.5")
    page.mouse.wheel(0, 1)
    page.wait_for_timeout(200)
    assert errors == []


def test_a_supernova_leaves_its_remnant_behind_the_shockwave(page: Page, site_url, errors):
    words = open_with_finds(page, site_url, 1)
    page.evaluate(COLLECT, words[:1])
    assert page.evaluate("window.__lf.nova() !== null")
    assert page.evaluate("window.__lf.remnants()") == ["0,0"]
    page.wait_for_function("window.__lf.nova() === null", timeout=12000)
    assert errors == []


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_the_tools_drop_down_from_their_button_and_go_again(page: Page, site_url, errors, size):
    without_worker(page, site_url, "letterfield")
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    button, stack = page.locator("#toolsBtn"), page.locator("#toolStack")
    # Closed at first: out of sight, out of reach of taps and Tab.
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(stack).to_be_hidden()
    assert page.evaluate("document.getElementById('toolStack').inert")

    # The map ends at the bar's top edge, and the bar runs to the screen's
    # bottom. On a phone it starts at the bottom of a bar along the top.
    bar = page.locator("#bar").bounding_box()
    box = page.locator("#map").bounding_box()
    assert round(box["y"] + box["height"]) == round(bar["y"])
    assert round(bar["y"] + bar["height"]) == size[1] and bar["x"] == 0
    if size[0] < 700:
        top = page.locator("#topbar").bounding_box()
        assert top["x"] == 0 and top["y"] == 0 and top["width"] == size[0] and round(box["y"]) == round(top["y"] + top["height"])
    else:
        assert box["y"] == 0

    # A tap opens it and focus moves in.
    button.click()
    expect(button).to_have_attribute("aria-expanded", "true")
    expect(stack).to_be_visible()
    expect(page.locator("#zoomIn")).to_be_focused()
    page.wait_for_timeout(300)  # done popping up
    box, tools = stack.bounding_box(), button.bounding_box()
    assert box["y"] >= tools["y"] + tools["height"] and box["y"] + box["height"] <= bar["y"], "it drops from its button, clear of the word list"
    assert abs(box["x"] + box["width"] - tools["x"] - tools["width"]) < 1
    for el in ["#toolsBtn", "#music", "#sound", "#home", "#zoomIn", "#zoomOut"]:
        b = page.locator(el).bounding_box()
        assert b["width"] >= 40 and b["height"] >= 40, (el, b)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # Left open, it starts shut all the same on the next visit.
    page.reload()
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(stack).to_be_hidden()
    button.click()

    # A second tap shuts it.
    button.click()
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(stack).to_be_hidden()

    # Escape shuts it and brings focus back to the button.
    button.click()
    page.keyboard.press("Tab")
    page.keyboard.press("Escape")
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(button).to_be_focused()

    # Dragging the map leaves it open; a tap on the map shuts it, and does nothing else.
    button.click()
    cx, cy = 80, page.evaluate("(m => m.getBoundingClientRect().top + m.clientHeight / 2)(document.getElementById('map'))")  # clear of the stack, top right
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 60, cy + 30, steps=5)
    page.mouse.up()
    expect(button).to_have_attribute("aria-expanded", "true")
    page.wait_for_timeout(1000)  # the drag's glide comes to rest
    cam = page.evaluate("({ ...window.__lf.cam })")
    page.mouse.click(cx, cy)
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(stack).to_be_hidden()
    assert page.evaluate("({ ...window.__lf.cam })") == cam
    assert errors == []


def test_the_shortcuts_work_with_the_tools_put_away(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")  # flights land at once
    without_worker(page, site_url, "letterfield")
    page.set_viewport_size({"width": 375, "height": 740})
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    expect(page.locator("#toolsBtn")).to_have_attribute("aria-expanded", "false")
    page.locator("#map").focus()
    cs = page.evaluate("window.__lf.cam.cs")
    page.keyboard.press("+")
    page.wait_for_function(f"window.__lf.cam.cs > {cs}")
    page.keyboard.press("-")
    page.wait_for_function(f"Math.abs(window.__lf.cam.cs - {cs}) < .01")
    page.keyboard.press("d")
    page.wait_for_function("window.__lf.cam.x > 7")
    page.keyboard.press("h")
    page.wait_for_function("window.__lf.cam.x === 6 && window.__lf.cam.y === 6")
    # Home lands in the middle of the map, above the bar.
    mid = page.evaluate("(m => m.getBoundingClientRect().top + m.clientHeight / 2)(document.getElementById('map'))")
    assert mid < page.locator("#bar").bounding_box()["y"] - 100
    page.keyboard.press("m")
    expect(page.locator("#sound")).to_have_attribute("aria-pressed", "false")
    page.keyboard.press("b")
    expect(page.locator("#music")).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("b")
    expect(page.locator("#music")).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#toolsBtn")).to_have_attribute("aria-expanded", "false")
    assert errors == []


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_a_finds_circle_flies_into_the_field_notes_before_it_counts(page: Page, site_url, errors, size):
    without_worker(page, site_url, "letterfield")
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    words = page.evaluate("window.__lf.chunk(0, 0).words.slice(0, 2).map(o => [o.w, o.x, o.y, o.d])")
    toast, count, bead = page.locator("#toast"), page.locator("#tWords" if size[0] >= 1100 else "#notesBadge"), page.locator(".gather")
    page.evaluate("([w, x, y]) => { window.__lf.cam.x = x; window.__lf.cam.y = y; }", words[0])  # in sight
    # No note: a copy of its circle draws in to a bead and flies to the count
    # (on the notes button, or atop the docked notes), which waits for it. A
    # screen reader still hears of the find.
    page.evaluate(COLLECT, words[:1])
    expect(page.locator("#findSay")).to_contain_text(words[0][0])
    expect(bead).to_have_count(1)
    assert bead.get_attribute("aria-hidden") == "true"
    expect(count).to_have_text("0")
    assert page.evaluate("JSON.parse(localStorage.getItem('letterfield.finds.v4')).length") == 1  # saved all the same
    expect(count).to_have_text("1", timeout=LANDS)
    expect(bead).to_have_count(0)
    expect(toast).not_to_have_class(re.compile(r"\bshow\b"))
    # Two at once fly in together, and each counts as it lands.
    page.evaluate("([w, x, y]) => { window.__lf.cam.x = x; window.__lf.cam.y = y; }", words[1])
    page.evaluate(COLLECT, words[1:])
    expect(count).to_have_text("2", timeout=LANDS)
    expect(bead).to_have_count(0)
    # Circling one again still answers, with a note: it's already in your notes.
    page.evaluate(COLLECT, words[:1])
    expect(toast).to_contain_text(f"{words[0][0]}Already in your notes")
    expect(toast).to_have_class(re.compile(r"\bshow\b"))
    assert errors == []


def test_with_reduced_motion_a_find_counts_at_once(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")
    without_worker(page, site_url, "letterfield")
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    word = page.evaluate("(o => [o.w, o.x, o.y, o.d])(window.__lf.chunk(0, 0).words[0])")
    page.evaluate("([w, x, y]) => { window.__lf.cam.x = x; window.__lf.cam.y = y; }", word)
    page.evaluate(COLLECT, [word])
    expect(page.locator("#notesBadge")).to_have_text("1", timeout=500)
    assert page.locator(".gather").count() == 0
    assert errors == []


@pytest.mark.parametrize("motion", ["no-preference", "reduce"])
def test_end_of_the_universe_prototype_plays_through(page: Page, site_url, errors, motion):
    # The endgame prototype (see "The end of the universe" in worker/SURVEY.md),
    # from the debug hook: every phase, its banners, and the map back after.
    without_worker(page, site_url, "letterfield")
    page.emulate_media(reduced_motion=motion)
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    page.mouse.click(200, 300)  # a first tap, so its sound can start
    assert page.evaluate("__lf.endgame({ tremor: .5, collapse: 1.5, dot: 1, build: 1, bang: .5, scatter: 1.5 })")
    assert not page.evaluate("__lf.endgame()"), "a second end while one is playing"
    banner = page.locator("#endgame")
    expect(banner).to_contain_text("The last word")
    page.wait_for_function("__lf.end() && __lf.end().name === 'dot'")
    expect(banner).to_contain_text("The universe has ended")
    page.wait_for_function("__lf.end() && __lf.end().name === 'scatter'")
    expect(banner).to_contain_text("Universe 2")
    page.wait_for_function("__lf.end() === null", timeout=10_000)
    expect(banner).to_be_hidden()
    expect(page.locator(".bar")).to_be_visible()


def test_end_of_the_universe_sound_renders_offline(page: Page, site_url, errors):
    without_worker(page, site_url, "letterfield")
    page.goto(f"{site_url}/letterfield#debug")
    size = page.evaluate("async () => (await __lf.endRender({ tremor: .5, collapse: 1, dot: 1, build: 1, bang: .5, scatter: .5, music: false })).size")
    assert size > 44 + 44100 * 4 * 8


def test_end_of_the_universe_keeps_your_initials(page: Page, site_url, errors):
    # A new universe starts the map again, not the player: someone signed
    # before the end isn't asked for initials after it, and is greeted by them.
    without_worker(page, site_url, "letterfield")
    page.add_init_script("""localStorage.setItem('games.initials', '"KAT"'); localStorage.setItem('letterfield.coach.v1', '1')""")
    page.goto(f"{site_url}/letterfield#debug")
    html = page.locator("html")
    expect(html).to_have_attribute("data-intro", "exploring")
    page.evaluate("__lf.endgame({ tremor: .3, collapse: .8, dot: .5, build: .5, bang: .3, scatter: 1.5, by: 'ABC' })")
    page.wait_for_function("__lf.end() && __lf.end().name === 'scatter'")
    expect(page.locator("#endgame")).to_contain_text("KAT, you were thrown to")
    page.wait_for_function("__lf.end() === null", timeout=10_000)
    expect(html).to_have_attribute("data-intro", "exploring")
    expect(page.locator("#signup")).to_be_hidden()
    assert page.evaluate("localStorage.getItem('games.initials')") == '"KAT"'
