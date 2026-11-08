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
          localStorage.setItem('letterfield.finds.v1', JSON.stringify([old[1]]));
          localStorage.setItem('letterfield.finds.v2', JSON.stringify(old));
          localStorage.removeItem('letterfield.finds.v3');
          localStorage.setItem('letterfield.coach.v1', '1');
        }""",
        old,
    )
    page.goto(f"{site_url}/letterfield")
    expect(page.locator("#toast")).to_contain_text("The map has been redrawn")
    expect(page.locator("#toast")).to_contain_text("1 of your 2 finds are still on it")
    expect(page.locator("#notesBadge")).to_have_text("1")
    # A long note stays on a phone's screen, padding and all.
    box = page.locator("#toast").bounding_box()
    assert box["x"] >= 16 and box["x"] + box["width"] <= 375 - 16, box
    saved = page.evaluate("() => [localStorage.getItem('letterfield.finds.v2'), JSON.parse(localStorage.getItem('letterfield.finds.v3'))]")
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


def test_both_music_tracks_make_sound_and_take_turns(page: Page, site_url, errors):
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
    assert all(0.001 < level < 0.2 for level in levels), levels
    page.keyboard.press("Shift")
    page.wait_for_function("window.__lf.music() !== null")
    first = page.evaluate("window.__lf.music().track")
    page.evaluate("window.__lf.music().swap()")
    assert page.evaluate("window.__lf.music().track") != first
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
