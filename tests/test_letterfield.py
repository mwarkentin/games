import re

import pytest
from playwright.sync_api import Page, expect

from fake_leaderboard import without_worker

# Screen positions of a legend word's first and last letters, for a word whose
# ends are both on open map rather than under a panel. Mirrors the game's
# camera: it starts centred on cell (6, 6) with 38px cells.
FIND_WORD_JS = """() => {
  const cs = 38, start = 6, canvas = document.getElementById('map');
  const dock = document.body.classList.contains('docked') ? 340 : 0;
  const dirs = [[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1],[0,-1],[1,-1]];
  const screen = (x, y) => [(x + .5 - start) * cs + (innerWidth - dock) / 2, (y + .5 - start) * cs + innerHeight / 2];
  for (const chip of document.querySelectorAll('#legendList .chip:not(.found)')) {
    const [word, x, y, d] = chip.dataset.key.split('~');
    const n = word.length - 1, [dx, dy] = dirs[+d];
    const ends = [screen(+x, +y), screen(+x + dx * n, +y + dy * n)];
    if (ends.every(([sx, sy]) => document.elementFromPoint(sx, sy) === canvas)) return { word, ends };
  }
  return null;
}"""


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
    expect(page.locator("#notesBadge")).to_have_text("1")
    expect(page.locator("#toast")).to_contain_text(target["word"])

    # Finds are kept in this browser and survive a reload.
    page.reload()
    expect(page.locator("#notesBadge")).to_have_text("1")
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
    expect(page.locator("#notesBadge")).to_have_text("1")
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
    expect(page.locator("#notesBadge")).to_have_text("1")
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
    # It plays out, then the map is back to normal.
    expect(page.locator("#nova")).to_be_hidden(timeout=10000)
    page.wait_for_function("window.__lf.nova() === null", timeout=5000)
    assert errors == []


def test_sound_can_be_switched_off(page: Page, site_url, errors):
    page.add_init_script(COUNT_AUDIO)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
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
    toast = page.locator("#toast")
    expect(toast).to_contain_text(words[0][0])
    place = toast.locator("span").inner_text().split(" · ")[1]
    toast.get_by_role("button", name=f"Share {words[0][0]}").click()
    shared = page.evaluate("window.__shared")
    w, x, y, d = words[0]
    assert shared == [{
        "title": "Letterfield",
        "text": f"I just found {w} in {place} in Letterfield. That’s word 1 in my field notes.",
        "url": f"{site_url}/letterfield#f-{w.lower()}-{x}-{y}-{d}",
    }]
    assert page.evaluate("document.documentElement.scrollWidth") <= 375

    # Every find in the field notes can be shared too, counted by when it was found.
    page.evaluate("([w, x, y, d]) => window.__lf.collect(w, x, y, d, false)", words[1])
    page.click("#notesToggle")
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
    page.click("#toast .share")
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
    page.click("#toast .share")
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
    expect(page.locator("#notesBadge")).to_have_text("2")
    expect(other.locator("#notesBadge")).to_have_text("2")
    page.reload()
    expect(page.locator("#notesBadge")).to_have_text("2")
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


def chips_scroll_only_sideways(page: Page, phone: bool) -> None:
    """The word list never scrolls up and down: on a phone it's one row that
    scrolls sideways, on a computer the words wrap inside the box."""
    m = page.evaluate(CHIPS_JS)
    assert m["n"] > 0
    assert m["oy"] not in ("auto", "scroll"), m
    assert m["sh"] <= m["ch"], m
    # Every chip, struck through or not, sits inside the row's height.
    if phone:
        assert m["wrap"] == "nowrap" and m["ox"] == "auto", m
    else:
        assert m["wrap"] == "wrap" and m["sw"] <= m["cw"], m


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
    chips_scroll_only_sideways(page, phone=True)
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
    chips_scroll_only_sideways(page, phone=True)

    page.set_viewport_size({"width": 1280, "height": 900})
    page.evaluate(fill)
    chips_scroll_only_sideways(page, phone=False)
    assert errors == []


# Puts a hidden word's first letter's centre at screen position (sx, sy), with
# cells of cs pixels, and returns the word list once it has caught up.
PLACE_WORD_JS = """async ({ key, sx, sy, cs }) => {
  const lf = window.__lf, [, x, y] = key.split('~');
  const dock = document.body.classList.contains('docked') ? 340 : 0;
  lf.cam.cs = cs;
  lf.cam.x = +x + .5 - (sx - (innerWidth - dock) / 2) / cs;
  lf.cam.y = +y + .5 - (sy - innerHeight / 2) / cs;
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


@pytest.mark.parametrize("size", [(375, 740), (1280, 900)], ids=["phone", "desktop"])
def test_the_word_list_names_only_words_half_in_sight(page: Page, site_url, errors, size):
    without_worker(page, site_url, "letterfield")  # alone, so each chip names its word
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{site_url}/letterfield#debug")
    page.click("#coachOk")
    expect(page.locator("#legendList .chip").first).to_be_visible()
    # Five-letter words reading right, down and up: each counts once any three
    # of its letters (half, rounded up) can be seen.
    keys = page.evaluate("""() => {
      const keys = {};
      for (let cy = -3; cy <= 3; cy++) for (let cx = -3; cx <= 3; cx++)
        for (const w of window.__lf.chunk(cx, cy).words) if (w.w.length === 5) keys[w.d] ??= w.key;
      return [keys[0], keys[2], keys[6]];
    }""")
    assert all(keys), keys
    across, down, up = keys
    page.evaluate(ONLY_WORDS_JS, keys)
    right = page.evaluate("innerWidth - (document.body.classList.contains('docked') ? 340 : 0)")
    mid = size[1] / 2

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

    # Letters under a panel over the map can't be seen either. A word reading
    # away from the title box (down), or from the word list or, on a phone, the
    # zoom controls above it (up), with its first three letters under the panel
    # isn't listed, and with only its first two there it is, where the rest
    # lands on open map.
    cs = 12
    phone = size[0] < 700
    panels = [("header.cartouche", down, True), ("section.legend", up, not phone)]
    if phone:
        panels.append((".zoom", up, True))
    for sel, key, clear in panels:
        box = page.locator(sel).bounding_box()
        sx = box["x"] + box["width"] / 2
        if key == down:  # the first letters just inside its bottom edge
            hidden3, hidden2 = box["y"] + box["height"] - 2.5 * cs, box["y"] + box["height"] - 1.5 * cs
        else:  # just inside its top edge
            hidden3, hidden2 = box["y"] + 2.5 * cs, box["y"] + 1.5 * cs
        seen, got = listed(key, sx, hidden3, cs)
        assert not seen, (sel, got)
        if clear:
            seen, got = listed(key, sx, hidden2, cs)
            assert seen, (sel, got)
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
    expect(page.locator("#notesBadge")).to_have_text(str(finds))
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
    if size[0] >= 700:  # three rows on a computer, one on a phone
        tops = page.evaluate("[...new Set([...document.querySelectorAll('#legendList .chip')].map(c => c.getBoundingClientRect().top))].length")
        assert tops == 3, tops
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
