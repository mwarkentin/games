#!/usr/bin/env python3
"""Record Letterfield's music as a soundtrack album: MP3s, FLACs and cover art.

The game makes its music as it plays, with the Web Audio API (see "Music" in
letterfield.html). This plays the game's own code in headless Chromium, each
piece from a fixed seed into an OfflineAudioContext, through the same
compressor and limiter the game plays through, so the album is the game's
music and a render is the same every time: the same notes, the same length and
the same sound. (Not quite the same bits: Chromium adds up three or more
signals meeting at one node in no fixed order, which moves samples by about a
millionth of full scale, far under the quietest a 16-bit file can hold, and
enough to change the bytes LAME writes.) ffmpeg then measures each track's
loudness, brings them all to one level and encodes them, with tags and the
cover, into _album/ (never committed):

    _album/web/      what letterfield-soundtrack.html plays and offers, all
                     in one folder, to upload to the album's R2 bucket (see
                     "The soundtrack album" in AGENTS.md): the MP3s
                     (LAME VBR, 44.1 kHz stereo, ID3v2.3 tags), the cover at
                     3000 and 1400 pixels, and a zip of the MP3s and the art
    _album/flac/     the tracks at 24 bits, lossless, for stores
    _album/art/      the back cover at 3000 pixels
    _album/album.json   each track's length, loudness and size

Run it with:

    uv run scripts/render_album.py                  # art, then every track
    uv run scripts/render_album.py --tracks lantern # one track (by slug)
    uv run scripts/render_album.py --art            # only the art
    uv run scripts/render_album.py --upload         # put _album/web/ in the album's bucket

It needs ffmpeg (with libmp3lame) on the PATH, and nothing from the network:
the page is served from here with its Worker addresses blanked, and every
request for another host is refused. The art is albums/letterfield/*.svg,
drawn with its letters as outlines, so it needs no fonts either; the link
preview it renders, previews/letterfield-soundtrack.jpg, is committed.

Each track below is a cut of one piece: where it starts and stops, and the
fades, are written in the piece's own bars where it has them. The page,
letterfield-soundtrack.html, lists the same tracks; tests/
test_letterfield_soundtrack.py checks they agree.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from common import BASE_URL, PREVIEW_SIZE, ROOT

OUT = ROOT / "_album"
ART = ROOT / "albums" / "letterfield"
# Where the album is published: an R2 bucket (made in mwarkentin/infra) on a
# custom domain. letterfield-soundtrack.html's ALBUM_URL is ALBUM_HOME.
BUCKET, PREFIX = "games-media", "letterfield"
ALBUM_HOME = f"https://media.michaelwarkentin.com/{PREFIX}"
WRANGLER = ["npx", "--yes", "wrangler@4.151.0"]
PREVIEW = ROOT / "previews" / "letterfield-soundtrack.jpg"
RATE = 44100

# The tags.
ALBUM = "Letterfield (Original Soundtrack)"
ARTIST = "Michael Warkentin"
YEAR = "2026"
GENRE = "Ambient; Video Game"
COMMENT = f"{BASE_URL}/letterfield"
# The recordings and their art are CC BY 4.0 (the code that makes them is the
# repo's, Apache 2.0): in the tags, the zip, the page and on the back.
LICENSE = "CC BY 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
COPYRIGHT = f"{YEAR} {ARTIST}. Licensed under {LICENSE}: {LICENSE_URL}"
LICENSE_TXT = f"""{ALBUM}
Music and art (c) {YEAR} {ARTIST}

Licensed under the Creative Commons Attribution 4.0 International licence
({LICENSE}): share and adapt it, for any purpose, even commercially, as long
as you give credit, link to the licence and say if you changed anything.
{LICENSE_URL}

Credit it as: "{ALBUM}" by {ARTIST}, {LICENSE}
{BASE_URL}/letterfield-soundtrack
"""
FILE_STEM = "letterfield"

# How loud the album is: every track at TARGET_LUFS integrated, unless that
# would take its true peak over PEAK_CEILING, in which case it's as loud as
# that allows. The MP3s are measured again after encoding, which can add a
# few tenths of a decibel to the peaks; PEAK_LIMIT is what they must stay under.
TARGET_LUFS = -17.0
PEAK_CEILING = -1.5
PEAK_LIMIT = -1.0
# LAME's VBR quality: 0 is the best and largest, 2 transparent for most ears.
MP3_QUALITY = 2

# The music's level in the game at the volume it starts at, 75 of 100:
# MUSIC_MAX * .75 ** 2 (see musicLevel in letterfield.html). Effects play at 1.
MUSIC_LEVEL = 0.8 * 0.75**2

# The pieces' own units, from letterfield.html: every piece starts its first
# bar .05 s in.
START = 0.05
ORBIT_BAR = 16 * 0.42  # ORBIT_CHORD: one chord of sixteen eighths
CHIMES_CHORD = 16 * 0.33  # CHIMES_CHORD; four make a phrase


def orbit_bars(n: int) -> float:
    return START + n * ORBIT_BAR


def chimes_chords(n: int) -> float:
    return START + n * CHIMES_CHORD


# Each track: its title, its file's slug, and what RENDER_JS plays. A piece
# plays from `seed`, scheduled a few seconds ahead every second as the game
# schedules it, until `stop`, with its bus faded in over `fade_in` seconds and
# out between `fade_out`'s two times (to its third value, 0 unless given).
# `stop: "arc"` plays Lantern's arc once, to its own last chord. The render
# runs `tail` seconds past `stop`, and its silence at the end is trimmed.
TRACKS = [
    {
        "slug": "drift",
        "title": "Drift",
        # A random walk of chords, one every 15 to 19 seconds: stops starting
        # new ones at 6:36, and fades as the last one fades by itself.
        "render": {"piece": "drift", "seed": 20261101, "fade_in": 10, "stop": 396, "fade_out": [396, 420], "tail": 30},
    },
    {
        "slug": "orbit",
        "title": "Orbit",
        # Three times round its four rounds of four chords, then one more bar,
        # back on A minor: it fades from the last round's third bar to a
        # whisper, and the last bar rings out.
        "render": {
            "piece": "orbit",
            "seed": 20261102,
            "stop": orbit_bars(49) - 0.01,
            "fade_out": [orbit_bars(46), orbit_bars(48), 0.22],
            "tail": 8,
        },
    },
    {
        "slug": "supernova",
        "title": "Supernova (Interlude)",
        # Two far off, one on each side; then one right here, and the chime of
        # the achievement for seeing one, once its shimmer has rung out.
        "render": {
            "interlude": "supernova",
            "far": [[0.4, -0.75], [5.0, 0.7]],
            "nova": 9.8,
            "mark": 19.4,
            "stop": 19.4,
            "tail": 5,
        },
    },
    {
        "slug": "chimes",
        "title": "Chimes",
        # Sixteen phrases of four chords, fading away over the last one and a half.
        "render": {
            "piece": "chimes",
            "seed": 20261104,
            "fade_in": 3,
            "stop": chimes_chords(64) - 0.01,
            "fade_out": [chimes_chords(58), chimes_chords(64) + 2],
            "tail": 6,
        },
    },
    {
        "slug": "lantern",
        "title": "Lantern",
        # Once through its arc, as written, to the rolled chord at its end.
        "render": {"piece": "lantern", "seed": 20261105, "stop": "arc", "tail": 2},
    },
]

# Played in the game's page (letterfield.html#debug), with its own functions:
# the pieces from window.__lf.musicTracks, its output stage audioOut, the
# effects novaSound, distantSound and markSound, and Lantern's lanternArc. Leaves the render, trimmed,
# in window.__album for take_pcm, and answers with its length and peak.
RENDER_JS = """
async (o) => {
  const lf = window.__lf, rate = o.rate;
  let stop = o.stop;
  if (stop === 'arc') stop = .05 + lf.lanternArc(lf.rng(o.seed)).reduce((s, b) => s + b.len, 0) - .01;
  const length = o.length || stop + o.tail;
  const a = new OfflineAudioContext(2, Math.ceil(rate * length), rate), out = lf.audioOut(a);
  // An equal-power ease from one level to another.
  const ease = (p, from, to, t0, t1) => {
    const c = new Float32Array(256);
    for (let i = 0; i < c.length; i++) c[i] = from + (to - from) * (1 - Math.cos(Math.PI * i / (c.length - 1))) / 2;
    p.setValueCurveAtTime(c, t0, t1 - t0);
  };
  if (o.piece) {
    const master = a.createGain(); master.gain.value = o.level; master.connect(out);
    const make = lf.musicTracks.find(f => f.name === `${o.piece}Track`), t = make(a, master, o.seed), g = t.bus.gain;
    if (o.fade_in) ease(g, 0, 1, 0, o.fade_in); else g.value = 1;
    if (o.fade_out) ease(g, 1, o.fade_out[2] || 0, o.fade_out[0], o.fade_out[1]);
    // As the game plays it: a few seconds ahead, every second.
    const tick = () => { const until = Math.min(a.currentTime + 3, stop); if (until > a.currentTime) t.play(until); };
    tick();
    for (let s = 1; s < stop; s++) a.suspend(s).then(() => { tick(); a.resume(); });
  } else if (o.interlude === 'supernova') {
    for (const [t, pan] of o.far) lf.distantSound(a, out, t, pan);
    lf.novaSound(a, out, o.nova, 0);
    lf.markSound(a, out, o.mark);
  }
  const b = await a.startRendering(), ch = [b.getChannelData(0), b.getChannelData(1)];
  let peak = 0, sum = 0;
  for (const d of ch) for (let i = 0; i < d.length; i++) { const v = Math.abs(d[i]); sum += v * v; if (v > peak) peak = v; }
  // Trimmed half a second past the last sound within o.trim dB of the peak,
  // with that half second faded to nothing.
  const floor = peak * Math.pow(10, -o.trim / 20);
  let last = 0;
  for (const d of ch) for (let i = d.length - 1; i > last; i--) if (Math.abs(d[i]) > floor) { last = i; break; }
  const half = Math.round(rate * .5), end = Math.min(b.length, last + half);
  for (const d of ch) for (let i = 0; i < half; i++) { const k = end - half + i; if (k >= 0) d[k] *= Math.cos(i / half * Math.PI / 2) ** 2; }
  window.__album = { ch, end };
  return { frames: end, seconds: end / rate, stop, peak, rms: Math.sqrt(sum / (2 * b.length)), ringing: last > b.length - half };
}
"""

# A stretch of window.__album's render, interleaved, as base64 float32s.
TAKE_JS = """
async ([from, to]) => {
  const { ch } = window.__album, n = to - from, buf = new Float32Array(n * 2);
  for (let i = 0; i < n; i++) { buf[2 * i] = ch[0][from + i]; buf[2 * i + 1] = ch[1][from + i]; }
  return await new Promise(done => {
    const f = new FileReader();
    f.onload = () => done(f.result.slice(f.result.indexOf(',') + 1));
    f.readAsDataURL(new Blob([buf.buffer]));
  });
}
"""

# The Worker addresses the page would otherwise reach: blanked as it's served.
BLANK = re.compile(r"\b((?:SURVEY_URL|SHARE_URL|DEFINE_URL|TURNSTILE_SITE_KEY|LEADERBOARD_URL|ROOMS_URL) = )'[^']*'")


def render_options(track: dict, rate: int = RATE, **changes) -> dict:
    """What RENDER_JS is given for a track, with any of it changed."""
    return {"rate": rate, "level": MUSIC_LEVEL, "trim": 66, **track["render"], **changes}


class GameOnly(SimpleHTTPRequestHandler):
    """Serves letterfield.html, with its Worker addresses blanked, and the
    modules it imports (js/letterfield/), and nothing else."""

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if re.fullmatch(r"/js/letterfield/[a-z-]+\.js", path) and (ROOT / path.lstrip("/")).exists():
            body, kind = (ROOT / path.lstrip("/")).read_bytes(), "text/javascript; charset=utf-8"
        elif path in ("/letterfield", "/letterfield.html"):
            body = BLANK.sub(r"\1''", (ROOT / "letterfield.html").read_text("utf-8")).encode()
            kind = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def serve_game() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), GameOnly)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def refuse_other_hosts(page) -> None:
    """Refuse every request for anywhere but this machine: nothing reaches production."""
    page.route(
        "**/*",
        lambda route: (
            route.continue_() if urlparse(route.request.url).hostname in ("127.0.0.1", "localhost") else route.abort()
        ),
    )


def open_game(page, site_url: str) -> None:
    """The game's page with its debug hook, which hands over its music."""
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("!!(window.__lf && window.__lf.musicTracks && window.__lf.audioOut)")


def render(page, options: dict) -> dict:
    """Render a track in the open game page. Its samples stay in the page for take_pcm."""
    return page.evaluate(RENDER_JS, options)


def take_pcm(page, frames: int, chunk: int = 1 << 20) -> bytes:
    """The last render's samples, as interleaved little-endian float32 stereo."""
    parts = []
    for start in range(0, frames, chunk):
        parts.append(base64.b64decode(page.evaluate(TAKE_JS, [start, min(frames, start + chunk)])))
    return b"".join(parts)


def raw_input(path: Path) -> list[str]:
    return ["-f", "f32le", "-ar", str(RATE), "-ac", "2", "-i", str(path)]


def loudness(inputs: list[str], af: str = "") -> dict:
    """Integrated loudness (LUFS), loudness range (LU) and true peak (dBTP), by EBU R128."""
    chain = f"{af}," if af else ""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", *inputs, "-af", f"{chain}ebur128=peak=true", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    summary = result.stderr[result.stderr.rindex("Summary:") :]

    def number(pattern: str) -> float:
        value = re.search(pattern, summary)[1]
        return float("-inf") if value == "-inf" else float(value)

    return {
        "lufs": number(r"I:\s+(-?[\d.]+|-inf) LUFS"),
        "lra": number(r"LRA:\s+(-?[\d.]+) LU"),
        "peak": number(r"Peak:\s+(-?[\d.]+|-inf) dBFS"),
    }


def gain_for(measured: dict) -> float:
    """The gain, in dB, that brings a track to TARGET_LUFS with its true peak under PEAK_CEILING."""
    return round(min(TARGET_LUFS - measured["lufs"], PEAK_CEILING - measured["peak"]), 2)


def tags(track: dict) -> dict:
    return {
        "title": track["title"],
        "artist": ARTIST,
        "album_artist": ARTIST,
        "album": ALBUM,
        "date": YEAR,
        "genre": GENRE,
        "comment": COMMENT,
        "copyright": COPYRIGHT,
    }


def metadata_args(values: dict) -> list[str]:
    return [arg for key, value in values.items() for arg in ("-metadata", f"{key}={value}")]


def file_stem(track: dict) -> str:
    """A track's file name, without its extension: letterfield-01-drift."""
    return f"{FILE_STEM}-{TRACKS.index(track) + 1:02d}-{track['slug']}"


def encode(raw: Path, gain: float, track: dict, number: int, total: int, cover: dict[str, Path], out: Path) -> dict:
    """The MP3 and FLAC of a track, from its raw render, at `gain` dB, tagged, with the cover inside."""
    mp3, flac = out / "web" / f"{file_stem(track)}.mp3", out / "flac" / f"{file_stem(track)}.flac"
    mp3.parent.mkdir(parents=True, exist_ok=True)
    flac.parent.mkdir(parents=True, exist_ok=True)
    common = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *raw_input(raw)]
    base = tags(track)
    # The MP3 carries the 1400px cover: a 3000px one would hold up its first
    # note on the page, which reads the tags before the music.
    art = cover.get("1400")
    pic = ["-i", str(art), "-map", "0:a", "-map", "1:v", "-c:v", "copy"] if art else []
    subprocess.run(
        [
            *common,
            *pic,
            "-af",
            f"volume={gain}dB",
            "-c:a",
            "libmp3lame",
            "-q:a",
            str(MP3_QUALITY),
            "-ar",
            str(RATE),
            "-id3v2_version",
            "3",
            "-write_id3v1",
            "1",
            *(["-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"] if art else []),
            *metadata_args({**base, "track": f"{number}/{total}", "disc": "1/1"}),
            "-fflags",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            str(mp3),
        ],
        check=True,
    )
    art = cover.get("3000")
    pic = (
        ["-i", str(art), "-map", "0:a", "-map", "1:v", "-c:v", "copy", "-disposition:v", "attached_pic"] if art else []
    )
    subprocess.run(
        [
            *common,
            *pic,
            "-af",
            f"volume={gain}dB",
            "-c:a",
            "flac",
            "-sample_fmt",
            "s32",
            "-bits_per_raw_sample",
            "24",
            "-compression_level",
            "8",
            *(["-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"] if art else []),
            *metadata_args(
                {
                    **base,
                    "track": str(number),
                    "TRACKTOTAL": str(total),
                    "DISCNUMBER": "1",
                    "DISCTOTAL": "1",
                    "LICENSE": LICENSE_URL,
                }
            ),
            "-fflags",
            "+bitexact",
            str(flac),
        ],
        check=True,
    )
    return {"mp3": mp3, "flac": flac}


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout)


def clock(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 60}:{s % 60:02d}"


def screenshot_svg(page, svg: str, width: int, height: int, path: Path, kind: str = "jpeg") -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.set_content(
        f"<style>html,body{{margin:0;background:#000}}svg{{display:block;width:{width}px;height:{height}px}}</style>{svg}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), type=kind, **({"quality": 94} if kind == "jpeg" else {}))


def render_art(browser, out: Path) -> dict[str, Path]:
    """The cover at 3000 and 1400 pixels, the back at 3000, and the link preview."""
    page = browser.new_page(device_scale_factor=1)
    refuse_other_hosts(page)
    art, web = out / "art", out / "web"
    written = {}
    cover = (ART / "cover.svg").read_text("utf-8")
    for size in (3000, 1400):
        written[str(size)] = web / f"{FILE_STEM}-cover-{size}.jpg"
        screenshot_svg(page, cover, size, size, written[str(size)])
    if (ART / "back.svg").exists():
        written["back"] = art / f"{FILE_STEM}-back-3000.jpg"
        screenshot_svg(page, (ART / "back.svg").read_text("utf-8"), 3000, 3000, written["back"])
    if (ART / "preview.svg").exists():
        # Drawn at twice the size and scaled down, as the other previews are.
        width, height = PREVIEW_SIZE
        big = out / "art" / "preview-2x.png"
        screenshot_svg(page, (ART / "preview.svg").read_text("utf-8"), width * 2, height * 2, big, kind="png")
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(big)]
            + ["-vf", f"scale={width}:{height}:flags=lanczos", "-q:v", "3", str(PREVIEW)],
            check=True,
        )
        written["preview"] = PREVIEW
    page.close()
    return written


def render_tracks(browser, wanted: list[dict], out: Path, cover: dict[str, Path]) -> list[dict]:
    server, url = serve_game()
    page = browser.new_page()
    refuse_other_hosts(page)
    page.on("pageerror", lambda error: print(f"  page error: {error}", file=sys.stderr))
    open_game(page, url)
    work = out / ".work"
    work.mkdir(parents=True, exist_ok=True)
    total = len(TRACKS)
    report = []
    for track in wanted:
        number = TRACKS.index(track) + 1
        print(f"{number:02d} {track['title']}: rendering...", flush=True)
        got = render(page, render_options(track))
        if got["ringing"]:
            print("  still sounding at the end of its render: give it a longer tail", file=sys.stderr)
        raw = work / f"{track['slug']}.f32"
        raw.write_bytes(take_pcm(page, got["frames"]))
        measured = loudness(raw_input(raw))
        gain = gain_for(measured)
        files = encode(raw, gain, track, number, total, cover, out)
        final = loudness(["-i", str(files["mp3"])])
        mp3 = files["mp3"]
        entry = {
            "number": number,
            "slug": track["slug"],
            "title": track["title"],
            "file": mp3.name,
            "seconds": round(duration(mp3), 2),
            "rendered": measured,
            "gain": gain,
            "lufs": final["lufs"],
            "lra": final["lra"],
            "peak": final["peak"],
            "bytes": mp3.stat().st_size,
            "kbps": round(mp3.stat().st_size * 8 / duration(mp3) / 1000),
            "flac_bytes": files["flac"].stat().st_size,
        }
        report.append(entry)
        raw.unlink()
        print(
            f"  {clock(entry['seconds'])}  {entry['lufs']:.1f} LUFS  LRA {entry['lra']:.1f}  "
            f"peak {entry['peak']:.1f} dBTP  gain {gain:+.1f} dB  {entry['kbps']} kbps  {entry['bytes'] / 1e6:.1f} MB",
            flush=True,
        )
        if entry["peak"] > PEAK_LIMIT:
            print(f"  its true peak is over {PEAK_LIMIT} dBTP", file=sys.stderr)
    shutil.rmtree(work, ignore_errors=True)
    page.close()
    server.shutdown()
    return report


def zip_album(out: Path, cover: dict[str, Path]) -> Path:
    """The MP3s, the art and the licence in one file, named for people, stored as they are (MP3s don't shrink)."""
    path = out / "web" / f"{FILE_STEM}-soundtrack.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for number, track in enumerate(TRACKS, 1):
            z.write(out / "web" / f"{file_stem(track)}.mp3", f"{ALBUM}/{number:02d} {track['title']}.mp3")
        for key, name in (("3000", "cover.jpg"), ("back", "back.jpg")):
            if key in cover:
                z.write(cover[key], f"{ALBUM}/{name}")
        z.writestr(f"{ALBUM}/LICENSE.txt", LICENSE_TXT)
    return path


def megabytes(size: int) -> str:
    return f"{size / 1e6:.1f} MB" if size < 10e6 else f"{size / 1e6:.0f} MB"


def check_page(tracks: list[dict], zipped: Path) -> None:
    """Warns when letterfield-soundtrack.html's lengths and sizes aren't the render's."""
    page = (ROOT / "letterfield-soundtrack.html").read_text("utf-8")
    want = [(t["file"], clock(t["seconds"]), megabytes(t["bytes"])) for t in tracks]
    got = re.findall(
        r'data-file="([^"]+)">.*?<span class="len">([^<]+)</span>.*?class="dl"[^>]*>MP3 <small>([^<]+)</small>',
        page,
        re.S,
    )
    total = sum(t["seconds"] for t in tracks)
    if got != want:
        print(f"letterfield-soundtrack.html lists {got}, the render made {want}", file=sys.stderr)
    if f"{len(tracks)} tracks · {clock(total)}" not in page:
        print(f"letterfield-soundtrack.html should say {len(tracks)} tracks · {clock(total)}", file=sys.stderr)
    if f"ZIP · {megabytes(zipped.stat().st_size)}" not in page:
        print(f"letterfield-soundtrack.html should say ZIP · {megabytes(zipped.stat().st_size)}", file=sys.stderr)


def upload_commands(out: Path = OUT) -> list[list[str]]:
    """Wrangler commands that put each file of _album/web/ in the bucket, with its type, how long it's
    cached and, for the ones offered as downloads, the name it's saved as. The page is on another
    origin, where browsers ignore a link's download attribute, so Content-Disposition does that
    instead; the 1400px cover, which the page shows to the system's media controls, stays inline.
    An audio element ignores Content-Disposition, so the MP3s still play on the page."""
    web = out / "web"
    files = [
        (f"{file_stem(t)}.mp3", "audio/mpeg", f"{FILE_STEM.title()} - {n:02d} {t['title']}.mp3")
        for n, t in enumerate(TRACKS, 1)
    ]
    files += [
        (f"{FILE_STEM}-cover-1400.jpg", "image/jpeg", None),
        (f"{FILE_STEM}-cover-3000.jpg", "image/jpeg", f"{ALBUM} - cover.jpg"),
        (f"{FILE_STEM}-soundtrack.zip", "application/zip", f"{ALBUM}.zip"),
    ]
    commands = []
    for name, kind, saved in files:
        command = [*WRANGLER, "r2", "object", "put", f"{BUCKET}/{PREFIX}/{name}", "--file", str(web / name)]
        command += ["--content-type", kind, "--cache-control", "public, max-age=86400", "--remote"]
        if saved:
            command += ["--content-disposition", f'attachment; filename="{saved}"']
        commands.append(command)
    return commands


def upload(out: Path) -> None:
    """Puts the album in its bucket. Wrangler needs CLOUDFLARE_ACCOUNT_ID and a token that can
    write to it (the bucket's upload token from infra), or `npx wrangler login`."""
    commands = upload_commands(out)
    missing = [c[c.index("--file") + 1] for c in commands if not Path(c[c.index("--file") + 1]).exists()]
    if missing:
        sys.exit(f"render the album first: {', '.join(missing)} missing")
    for command in commands:
        print(command[command.index("put") + 1], flush=True)
        subprocess.run(command, check=True)
    print(f"Uploaded {len(commands)} files to {ALBUM_HOME}/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tracks", help="only these tracks, by slug, comma-separated")
    parser.add_argument("--art", action="store_true", help="only the art")
    parser.add_argument("--out", type=Path, default=OUT, help="where to write (default: _album/)")
    parser.add_argument(
        "--upload", action="store_true", help=f"put _album/web/ in {BUCKET}/{PREFIX}/, and nothing else"
    )
    args = parser.parse_args()
    if args.upload:
        upload(args.out)
        return
    if not shutil.which("ffmpeg"):
        sys.exit("render_album.py needs ffmpeg, with libmp3lame, on the PATH")
    wanted = TRACKS
    if args.tracks:
        slugs = args.tracks.split(",")
        wanted = [t for t in TRACKS if t["slug"] in slugs]
        if len(wanted) != len(slugs):
            sys.exit(f"tracks are: {', '.join(t['slug'] for t in TRACKS)}")

    from playwright.sync_api import sync_playwright

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        cover = render_art(browser, out) if (ART / "cover.svg").exists() else {}
        if args.art:
            browser.close()
            print(f"Art in {out / 'art'}" + (f", and {PREVIEW.relative_to(ROOT)}" if "preview" in cover else ""))
            return
        report = render_tracks(browser, wanted, out, cover)
        browser.close()

    known = {}
    album_json = out / "album.json"
    if album_json.exists():
        known = {t["slug"]: t for t in json.loads(album_json.read_text())["tracks"]}
    known.update({t["slug"]: t for t in report})
    tracks = [known[t["slug"]] for t in TRACKS if t["slug"] in known]
    album_json.write_text(json.dumps({"album": ALBUM, "artist": ARTIST, "tracks": tracks}, indent=2) + "\n")
    if len(tracks) == len(TRACKS):
        zipped = zip_album(out, cover)
        check_page(tracks, zipped)
        seconds = sum(t["seconds"] for t in tracks)
        size = sum(t["bytes"] for t in tracks)
        print(
            f"\n{ALBUM}: {len(tracks)} tracks, {clock(seconds)}, {size / 1e6:.1f} MB of MP3s, "
            f"{sum(t['flac_bytes'] for t in tracks) / 1e6:.1f} MB of FLAC, zip {zipped.stat().st_size / 1e6:.1f} MB"
        )
    print(f"Written to {out}")


if __name__ == "__main__":
    main()
