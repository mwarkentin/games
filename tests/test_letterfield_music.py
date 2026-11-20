"""Letterfield's fourth piece of music, Lantern: a piano waltz made as it plays.
The music's switches, volume and turns are in test_letterfield.py."""

import math

import pytest
from playwright.sync_api import Page, expect

from test_letterfield_survey import HIDE

INIT = "localStorage.setItem('letterfield.coach.v1', '1'); localStorage.setItem('letterfield.music.v1', '1');"

# An offline context whose oscillators note when they start and stop, and the
# piece made in it with a seed: everything below needs no speakers.
LANTERN = """
const offline = (secs, rate = 44100) => {
  const a = new OfflineAudioContext(2, Math.ceil(rate * secs), rate), oscs = [], make = a.createOscillator.bind(a);
  a.createOscillator = () => {
    const o = make(), r = { start: null, stop: null }, start = o.start.bind(o), stop = o.stop.bind(o);
    oscs.push(r);
    o.start = (t = 0) => { r.start = t; start(t); };
    o.stop = (t = 0) => { r.stop = Math.max(t, a.currentTime); stop(t); };
    return o;
  };
  return { a, oscs };
};
const lantern = window.__lf.musicTracks.find(f => f.name === 'lanternTrack');
// The most oscillators sounding at once, and when, and the most sounding for
// all but 1% of the time.
const most = oscs => {
  const ev = [], time = [];
  for (const r of oscs) if (r.start !== null) { ev.push([r.start, 1]); if (r.stop !== null) ev.push([r.stop, -1]); }
  ev.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
  let k = 0, top = 0, at = 0, was = 0;
  for (const [t, d] of ev) { time[k] = (time[k] || 0) + t - was; was = t; k += d; if (k > top) { top = k; at = t; } }
  let p99 = top, past = 0;
  const total = time.reduce((s, v) => s + (v || 0), 0);
  for (let n = top; n >= 0 && past + (time[n] || 0) <= total / 100; n--) { past += time[n] || 0; p99 = n - 1; }
  return { top, at, p99 };
};
"""


def open_page(page: Page, site_url):
    page.add_init_script(INIT)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")


def test_lantern_keeps_to_its_voices_through_its_arc_and_stops_cleanly(page: Page, site_url, errors):
    open_page(page, site_url)
    for seed in (1, 2, 3):
        got = page.evaluate(
            LANTERN
            + """seed => {
              const { a, oscs } = offline(1), t = lantern(a, a.destination, seed);
              t.play(480);  // twice through its arc and into a third, without strings yet, all at once
              const { top, at, p99 } = most(oscs), open = oscs.filter(r => r.stop === null).length, started = oscs.length;
              t.stop();
              return { top, at, p99, open, started, left: t.nodes.size, unstopped: oscs.filter(r => r.stop === null).length };
            }""",
            seed,
        )
        # About twenty oscillators at once, as the other pieces keep to (a couple
        # more for an instant, as one bar's notes are damped under the next's
        # first), and every note stops by itself: only the two slow wobbles run
        # on until the piece stops.
        assert got["started"] > 1000, got
        assert got["p99"] <= 20 and got["top"] <= 23, got
        assert got["open"] == 2, got
        assert got["left"] == 0 and got["unstopped"] == 0, got
    assert errors == []


def test_lantern_schedules_as_it_plays_and_is_heard_throughout(page: Page, site_url, errors):
    open_page(page, site_url)
    # Played as the page plays it, a few seconds ahead from a timer every
    # second, for its first minute: it's never silent for long, never loud,
    # and the notes it's started drain away as they end.
    got = page.evaluate(
        LANTERN
        + """async () => {
          const secs = 60, { a, oscs } = offline(secs), t = lantern(a, a.destination, 7), sizes = [];
          t.bus.gain.value = .45;
          const tick = () => { t.play(a.currentTime + 3); sizes.push(t.nodes.size); };
          tick();
          for (let s = 1; s < secs; s++) a.suspend(s).then(() => { tick(); a.resume(); });
          const d = (await a.startRendering()).getChannelData(0), w = 44100;
          const rms = [];
          for (let i = 0; i + w <= d.length; i += w) { let s = 0; for (let j = i; j < i + w; j++) s += d[j] * d[j]; rms.push(Math.sqrt(s / w)); }
          let peak = 0; for (const x of d) peak = Math.max(peak, Math.abs(x));
          return { rms, peak, sizes, most: most(oscs).top };
        }"""
    )
    assert min(got["rms"][1:]) > 0.0005, got["rms"]  # the piano is there from the first bar
    assert got["peak"] < 0.25, got["peak"]
    assert got["most"] <= 22, got["most"]
    assert max(got["sizes"]) < 80, got["sizes"]
    assert errors == []


def test_lantern_peaks_stay_under_the_limiter_over_its_whole_arc(page: Page, site_url, errors):
    open_page(page, site_url)
    # Its whole arc, at the music's usual level, through the page's own output:
    # the loudest notes, at its peak, stay well under the limiter's -4 dB, so it
    # never squeezes the quiet notes around them.
    got = page.evaluate(
        LANTERN
        + """async () => {
          const secs = 240, { a } = offline(secs, 8000), out = window.__lf.audioOut(a);  // a low rate, to keep it quick
          const master = a.createGain(); master.gain.value = .45; master.connect(out);
          const t = lantern(a, master, 11); t.bus.gain.value = 1; t.play(secs);
          const b = await a.startRendering();
          let peak = 0, sum = 0;
          for (let c = 0; c < 2; c++) for (const x of b.getChannelData(c)) { peak = Math.max(peak, Math.abs(x)); sum += x * x; }
          return { peak, rms: Math.sqrt(sum / (2 * b.length)) };
        }"""
    )
    assert 20 * math.log10(got["peak"]) < -7, got
    assert 0.005 < got["rms"] < 0.05, got
    assert errors == []


def test_the_music_crossfades_from_chimes_into_lantern(page: Page, site_url, errors):
    open_page(page, site_url)
    page.keyboard.press("Shift")
    page.wait_for_function("window.__lf.music() !== null")
    while page.evaluate("window.__lf.music().track") != "chimes":
        page.evaluate("window.__lf.music().swap()")
    page.evaluate("window.__lf.music().swap()")
    assert page.evaluate("window.__lf.music().track") == "lantern"
    # It fades in over eight seconds, scheduling its first notes straight away.
    page.wait_for_function("window.__lf.music().fade > .05 && window.__lf.music().nodes > 4", timeout=5000)
    assert page.evaluate("window.__lf.music().fade") < 1
    page.keyboard.press("b")
    expect(page.locator("#music")).to_have_attribute("aria-pressed", "false")
    assert errors == []


def test_the_crossfade_into_lantern_has_no_gap(page: Page, site_url, errors):
    open_page(page, site_url)
    # The hand-over as playMusic makes it, offline: Chimes fades out over eight
    # seconds as Lantern fades in, and the music never drops out between them.
    got = page.evaluate(
        LANTERN
        + """async () => {
          const secs = 22, { a } = offline(secs), master = a.createGain();
          master.gain.value = .45; master.connect(a.destination);
          const chimes = window.__lf.musicTracks.find(f => f.name === 'chimesTrack');
          const glide = (p, to, s) => { const t = a.currentTime; p.cancelScheduledValues(t); p.setValueAtTime(p.value, t); p.linearRampToValueAtTime(to, t + s); };
          let old = chimes(a, master), track = old;
          old.bus.gain.value = 1;
          const tick = s => {
            if (s === 6) { glide(old.bus.gain, 0, 8); track = lantern(a, master, 5); glide(track.bus.gain, 1, 8); }
            if (s === 15) old.stop();
            track.play(a.currentTime + 3);
          };
          tick(0);
          for (let s = 1; s < secs; s++) a.suspend(s).then(() => { tick(s); a.resume(); });
          const d = (await a.startRendering()).getChannelData(0), w = 22050, rms = [];
          for (let i = 0; i + w <= d.length; i += w) { let s = 0; for (let j = i; j < i + w; j++) s += d[j] * d[j]; rms.push(Math.sqrt(s / w)); }
          return { rms, left: old.nodes.size };
        }"""
    )
    rms = got["rms"]
    assert min(rms[1:]) > 0.001, rms
    assert max(rms) < 0.1, rms
    assert got["left"] == 0  # Chimes, stopped after its fade, has nothing left playing
    assert errors == []


# The music player in the tools: a row with the piece playing, previous, play
# or pause and next, and a list of every piece.
PIECES = "[...document.querySelectorAll('#musicPieces button span')].map(b => b.textContent)"
TRACK = "window.__lf.music() && window.__lf.music().track"


def open_player(page: Page, site_url, init: str = "", size=(1280, 900)):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.add_init_script(INIT.replace("localStorage.setItem('letterfield.music.v1', '1');", "") + init)
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    page.evaluate("document.getElementById('toolsBtn').click()")  # no tap or key, which would start the audio
    expect(page.locator("#toolsBtn")).to_have_attribute("aria-expanded", "true")


def test_the_player_lists_every_piece_and_steps_through_them(page: Page, site_url, errors):
    # Orbit last heard, before this test (the init script runs again on reload).
    open_player(
        page,
        site_url,
        "if (!sessionStorage.getItem('seen')) { sessionStorage.setItem('seen', '1'); localStorage.setItem('letterfield.musicpiece.v1', '1'); }",
    )
    html, name, play = page.locator("html"), page.locator("#pieceName"), page.locator("#musicPlay")
    # Every piece, in the order they take turns, and the one that will play
    # (the last one heard) named and marked, before any music.
    order = page.evaluate("window.__lf.musicTracks.map(f => f.name.replace('Track', ''))")
    assert [n.lower() for n in page.evaluate(PIECES)] == order == ["drift", "orbit", "chimes", "lantern"]
    expect(html).to_have_attribute("data-music", "off")
    expect(name).to_have_text("Orbit")
    expect(page.locator("#musicPieces [aria-current='true'] span")).to_have_text("Orbit")
    expect(play).to_have_accessible_name("Play music")

    # Play switches the music on with that piece.
    play.click()
    expect(html).to_have_attribute("data-music", "playing")
    expect(page.locator("#music")).to_have_attribute("aria-pressed", "true")
    expect(play).to_have_accessible_name("Pause music")
    assert page.evaluate(TRACK) == "orbit"

    # Next and previous step through them, round from either end, each kept for next time.
    page.locator("#musicNext").click()
    page.wait_for_function(f"{TRACK} === 'chimes'")
    expect(name).to_have_text("Chimes")
    expect(page.locator("#musicPieces [aria-current='true'] span")).to_have_text("Chimes")
    assert page.evaluate("localStorage.getItem('letterfield.musicpiece.v1')") == "2"
    for _ in range(3):
        page.locator("#musicPrev").click()
    page.wait_for_function(f"{TRACK} === 'lantern'")
    expect(name).to_have_text("Lantern")

    # Picking one from the list plays it; picking the one playing carries on with it.
    page.locator("#musicPieces button", has_text="Orbit").click()
    page.wait_for_function(f"{TRACK} === 'orbit'")
    page.wait_for_function("!window.__lf.music().fading", timeout=6000)
    page.locator("#musicPieces button", has_text="Orbit").click()
    assert page.evaluate("window.__lf.music().fading") is False

    # A few quick taps on Next leave only the last two pieces sounding, and the
    # one before soon fades away.
    for _ in range(3):
        page.locator("#musicNext").click()
    page.wait_for_function(f"{TRACK} === 'drift'")
    page.wait_for_function("!window.__lf.music().fading", timeout=6000)

    # Next time, the music starts with the piece last heard.
    page.reload()
    page.wait_for_function("window.__lf")
    expect(page.locator("#pieceName")).to_have_text("Drift")
    assert errors == []


def test_pausing_holds_the_music_until_played_again(page: Page, site_url, errors):
    open_player(
        page,
        site_url,
        "localStorage.setItem('letterfield.music.v1', '1'); localStorage.setItem('letterfield.musicpiece.v1', '3');",
    )
    html, play = page.locator("html"), page.locator("#musicPlay")
    expect(html).to_have_attribute("data-music", "waiting")  # on, till the first tap or key
    assert page.evaluate("getComputedStyle(document.querySelector('#music svg')).animationName") == "none"
    page.keyboard.press("Shift")
    expect(html).to_have_attribute("data-music", "playing")
    page.wait_for_function("window.__lf.music().level > .1")

    icon = "getComputedStyle(document.querySelector('#music svg')).animationName"
    assert page.evaluate(icon) == "drift"  # the music's icon drifts while it plays
    play.click()
    expect(html).to_have_attribute("data-music", "paused")
    expect(play).to_have_accessible_name("Play music")
    expect(page.locator("#music")).to_have_attribute("aria-pressed", "true")  # paused, not switched off
    assert page.evaluate(icon) == "none"  # and is still while it's paused
    page.wait_for_function("window.__lf.music().level < .01")
    # Paused, the tab hidden and shown again doesn't bring the music back, and
    # nor does moving its slider.
    page.evaluate(HIDE, True)
    page.wait_for_function("window.__lf.music().state === 'suspended'")
    page.evaluate(HIDE, False)
    page.wait_for_function("window.__lf.music().state === 'running'")
    page.locator("#musicVol").fill("50")
    page.wait_for_timeout(1500)
    expect(html).to_have_attribute("data-music", "paused")
    assert page.evaluate("window.__lf.music().level") < 0.01

    # Played again, the same piece carries on, at the slider's new level.
    play.click()
    expect(html).to_have_attribute("data-music", "playing")
    page.wait_for_function("Math.abs(window.__lf.music().level - window.__lf.music().target) < 1e-3", timeout=4000)
    assert page.evaluate(TRACK) == "lantern"

    # Paused, the music's switch still switches it off.
    play.click()
    expect(html).to_have_attribute("data-music", "paused")
    page.keyboard.press("b")
    expect(html).to_have_attribute("data-music", "off")
    assert page.evaluate("window.__lf.music()") is None
    assert errors == []


def test_the_first_piece_heard_is_the_one_to_start_with_next_time(page: Page, site_url, errors):
    open_player(page, site_url, "localStorage.setItem('letterfield.music.v1', '1');")
    assert page.evaluate("localStorage.getItem('letterfield.musicpiece.v1')") is None  # one at random, not yet heard
    page.keyboard.press("Shift")
    expect(page.locator("html")).to_have_attribute("data-music", "playing")
    heard = page.locator("#pieceName").text_content()
    assert page.evaluate("localStorage.getItem('letterfield.musicpiece.v1')") == str(
        page.evaluate("window.__lf.musicPiece()")
    )
    page.reload()
    page.wait_for_function("window.__lf")
    expect(page.locator("#pieceName")).to_have_text(heard)
    assert errors == []


def test_picking_a_piece_with_the_music_off_switches_it_on_with_that_piece(page: Page, site_url, errors):
    open_player(page, site_url, "localStorage.setItem('letterfield.musicpiece.v1', '0');")
    page.locator("#musicPieces button", has_text="Lantern").click()
    expect(page.locator("html")).to_have_attribute("data-music", "playing")
    expect(page.locator("#musicVol")).to_have_value("75")
    assert page.evaluate(TRACK) == "lantern"
    assert page.evaluate("localStorage.getItem('letterfield.music.v1')") == "1"
    assert errors == []


MORE_PIECES = """() => {
  const l = document.getElementById('musicPieces');
  for (const n of ['Ember', 'Tidepool', 'Hollowmere', 'Vesper', 'Quarry', 'Lull']) {
    const li = l.children[0].cloneNode(true), b = li.querySelector('button');
    b.removeAttribute('aria-current'); b.querySelector('span').textContent = n;
    l.append(li);
  }
}"""


def test_the_list_of_pieces_scrolls_once_there_are_more_than_fit(page: Page, site_url, errors):
    open_player(page, site_url)
    pieces = page.locator("#musicPieces")
    assert pieces.evaluate("l => l.scrollHeight <= l.clientHeight"), "four pieces fit without scrolling"
    # Past six or so, the list scrolls on its own, the next one half in sight,
    # with the drawer and the page staying put.
    page.evaluate(MORE_PIECES)
    assert pieces.evaluate("l => l.scrollHeight > l.clientHeight && l.scrollWidth <= l.clientWidth")
    assert 6 * 40 < pieces.bounding_box()["height"] < 7 * 40
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []


@pytest.mark.parametrize("size", [(375, 667), (390, 844)], ids=["small-phone", "phone"])
def test_on_a_phone_the_player_is_one_row(page: Page, site_url, errors, size):
    # No list of pieces on a phone, where the tools' sheet must leave the
    # middle of the map in sight (see the tools' own test): Previous and Next
    # step through them, however many there are.
    open_player(page, site_url, "localStorage.setItem('letterfield.musicpiece.v1', '2');", size=size)
    expect(page.locator("#musicPieces")).to_be_hidden()
    expect(page.locator("#pieceName")).to_have_text("Chimes")
    for el in ["#musicPrev", "#musicPlay", "#musicNext"]:
        b = page.locator(el).bounding_box()
        assert b["width"] >= 36 and b["height"] >= 36, (el, b)
    page.locator("#musicNext").click()
    page.wait_for_function(f"{TRACK} === 'lantern'")
    expect(page.locator("#pieceName")).to_have_text("Lantern")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []


def test_paused_music_with_sound_off_lets_the_audio_sleep(page: Page, site_url, errors):
    open_player(
        page,
        site_url,
        "localStorage.setItem('letterfield.music.v1', '1'); localStorage.setItem('letterfield.musicpiece.v1', '3');"
        " localStorage.setItem('letterfield.sound.v1', '0');",
    )
    html, play = page.locator("html"), page.locator("#musicPlay")
    page.keyboard.press("Shift")
    expect(html).to_have_attribute("data-music", "playing")
    page.wait_for_function("window.__lf.music().level > .1")
    # Paused, with no sound effects to play, Lantern's held strings and the rest
    # stop running once it's quiet, and taps and keys leave them asleep.
    play.click()
    expect(html).to_have_attribute("data-music", "paused")
    page.wait_for_function("window.__lf.music().state === 'suspended'")
    page.keyboard.press("Shift")
    page.mouse.click(400, 500)
    page.evaluate(HIDE, True)
    page.evaluate(HIDE, False)
    page.wait_for_timeout(500)
    assert page.evaluate("window.__lf.music().state") == "suspended"
    # Sound switched on wakes it for effects; off again, it sleeps.
    page.locator("#sound").click()
    page.wait_for_function("window.__lf.music().state === 'running'")
    page.locator("#sound").click()
    page.wait_for_function("window.__lf.music().state === 'suspended'")
    # Played again, it wakes and carries on with the same piece.
    play.click()
    expect(html).to_have_attribute("data-music", "playing")
    page.wait_for_function("window.__lf.music().state === 'running'")
    page.wait_for_function("window.__lf.music().level > .1", timeout=4000)
    assert page.evaluate(TRACK) == "lantern"
    assert errors == []
