"""Letterfield's fourth piece of music, Lantern: a piano waltz made as it plays.
The music's switches, volume and turns are in test_letterfield.py."""

import math

from playwright.sync_api import Page, expect

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
