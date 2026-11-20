"""Letterfield's soundtrack: the album scripts/render_album.py records from the
game's own music, and letterfield-soundtrack.html, its page.

The render tests run the script's own JavaScript against the game's page, a few
seconds of each track, so a change to the music that breaks the recording shows
up here rather than only when someone next renders the album."""

from __future__ import annotations

import io
import math
import re
import wave

import pytest
from playwright.sync_api import Page, Route, expect

import render_album
from common import ROOT
from fake_leaderboard import blank_constants

PAGE = ROOT / "letterfield-soundtrack.html"
ALBUM = "https://album.test"

# The last render, kept to compare the next one with: the most any sample
# moved, or null the first time.
COMPARE = """() => {
  const { ch, end } = window.__album, prev = window.__prev;
  window.__prev = ch.map(c => c.slice(0, end));
  if (!prev) return null;
  let most = prev[0].length === end ? 0 : Infinity;
  for (let k = 0; k < 2 && most < Infinity; k++) for (let i = 0; i < end; i++) most = Math.max(most, Math.abs(ch[k][i] - prev[k][i]));
  return most;
}"""
# How loud each second of the last render is, as RMS.
SECONDS = """rate => {
  const { ch, end } = window.__album, out = [];
  for (let s = 0; s + rate <= end; s += rate) {
    let sum = 0;
    for (const c of ch) for (let i = s; i < s + rate; i++) sum += c[i] * c[i];
    out.push(Math.sqrt(sum / (2 * rate)));
  }
  return out;
}"""
RATE = 22050


def short(track: dict, **changes) -> dict:
    """The track's render, cut to its first six seconds at a lower rate, without its fades."""
    if "piece" not in track["render"]:
        return render_album.render_options(track, rate=RATE, **changes)
    return render_album.render_options(
        track, rate=RATE, **{"stop": 6, "tail": 1, "fade_in": 0, "fade_out": None, **changes}
    )


@pytest.mark.parametrize("slug", [t["slug"] for t in render_album.TRACKS])
def test_each_track_renders_from_the_games_own_code(page: Page, site_url, errors, slug):
    track = next(t for t in render_album.TRACKS if t["slug"] == slug)
    render_album.open_game(page, site_url)
    got = render_album.render(page, short(track))
    loud = page.evaluate(SECONDS, RATE)
    # Sounding from the start and never silent for a second of it, under the
    # game's limiter (which the supernova's blast gets past for an instant, but
    # never as far as clipping).
    assert got["rms"] > 0.002, got
    if "piece" in track["render"]:
        assert got["peak"] < 0.7, got
        assert min(loud[:6]) > 0.001, loud
    else:
        # The interlude: two far off, then one here, then its chime, each heard,
        # and over by the end of its render.
        assert got["peak"] < 1, got
        assert min(loud[0:3]) > 0.001 and min(loud[5:7]) > 0.001 and min(loud[12:16]) > 0.003, loud
        assert max(loud[19:22]) > 0.0005, loud
        assert not got["ringing"], got
    # A seed plays the same each time, to well under the quietest a 16-bit file holds...
    page.evaluate(COMPARE)
    render_album.render(page, short(track))
    assert page.evaluate(COMPARE) < 1e-5
    # ...and another seed plays it another way, by half a minute in (Orbit's
    # first round, its ticking alone, can come out the same).
    if "piece" in track["render"]:
        render_album.render(page, short(track, stop=30))
        page.evaluate(COMPARE)
        render_album.render(page, short(track, stop=30, seed=track["render"]["seed"] + 1))
        assert page.evaluate(COMPARE) > 1e-3
    assert errors == []


def test_lanterns_cut_is_once_through_its_arc(page: Page, site_url, errors):
    # Lantern stops by itself, a few seconds over the game's four minutes: its
    # arc is fitted to them, and ends with its last chord ringing out over a rest
    # of a few bars. Rendered at a low rate, to be quick.
    track = next(t for t in render_album.TRACKS if t["slug"] == "lantern")
    render_album.open_game(page, site_url)
    got = render_album.render(page, render_album.render_options(track, rate=8000))
    assert 240 < got["stop"] < 262, got
    assert got["stop"] - 8 < got["seconds"] < got["stop"] + 2, got
    assert not got["ringing"], got
    assert errors == []


def page_tracks() -> list[tuple[str, str]]:
    text = PAGE.read_text("utf-8")
    return [
        (file, re.sub(r"<[^>]+>", " ", title).split())
        for file, title in re.findall(r'data-file="([^"]+)">\s*<div class="row">.*?<h3>(.*?)</h3>', text, re.S)
    ]


def test_the_page_lists_the_tracks_the_script_renders():
    want = [
        (f"{render_album.file_stem(t)}.mp3", t["title"].replace("(", "").replace(")", "").split())
        for t in render_album.TRACKS
    ]
    assert page_tracks() == want
    text = PAGE.read_text("utf-8")
    assert f"{len(render_album.TRACKS)} tracks · " in text
    # Credited and licensed as the tags are.
    assert f"{render_album.ARTIST} · " in text
    assert f'<link rel="license" href="{render_album.LICENSE_URL}">' in text
    assert f'<a href="{render_album.LICENSE_URL}" rel="license">{render_album.LICENSE}</a>' in text


def test_the_pages_cover_is_the_albums():
    text = PAGE.read_text("utf-8")
    cover = text.split("<!-- BEGIN COVER -->\n")[1].split("<!-- END COVER -->")[0]
    assert cover == (render_album.ART / "cover.svg").read_text("utf-8"), "run scripts/draw_album_art.py"


def test_the_art_needs_no_fonts_or_network():
    for name in ("cover", "back", "preview"):
        svg = (render_album.ART / f"{name}.svg").read_text("utf-8")
        assert "<text" not in svg and "font-family" not in svg and "@import" not in svg, name
        assert not re.search(r'(?:href|src)="(?:https?:)?//', svg), name


def test_the_page_plays_the_album_from_where_the_script_uploads_it():
    assert f"const ALBUM_URL = '{render_album.ALBUM_HOME}';" in PAGE.read_text("utf-8")


def options(args: list[str]) -> dict[str, str | bool]:
    """A command's options: each with its value, or True for a flag."""
    out, i = {}, 0
    while i < len(args):
        value = i + 1 < len(args) and not args[i + 1].startswith("--")
        out[args[i]] = args[i + 1] if value else True
        i += 2 if value else 1
    return out


def test_the_upload_puts_every_file_the_page_offers_with_its_type_and_name():
    commands = render_album.upload_commands()
    keys = [c[c.index("put") + 1] for c in commands]
    flags = [options(c[c.index("--file") :]) for c in commands]
    text = PAGE.read_text("utf-8")
    offered = set(re.findall(r'data-file="([^"]+)"', text)) | set(re.findall(r'class="dl" href="([^"]+)"', text))
    offered |= set(re.findall(r'<a id="\w+" href="([^"]+)" download>', text)) | {"letterfield-cover-1400.jpg"}
    assert {k.removeprefix(f"{render_album.BUCKET}/{render_album.PREFIX}/") for k in keys} == offered
    for key, f in zip(keys, flags):
        assert f["--remote"] is True
        assert (
            f["--content-type"]
            == {"mp3": "audio/mpeg", "jpg": "image/jpeg", "zip": "application/zip"}[key.rsplit(".", 1)[1]]
        )
        # Saved, not opened, from another origin, where a link's download attribute does nothing;
        # but the cover the system's media controls show stays inline.
        if key.endswith("cover-1400.jpg"):
            assert "--content-disposition" not in f
        else:
            assert re.fullmatch(
                r'attachment; filename="Letterfield[^"/]*\.(mp3|jpg|zip)"', f["--content-disposition"]
            ), f


def test_without_recordings_the_tracks_are_listed_without_players(page: Page, site_url, errors):
    blank_constants(page, "letterfield-soundtrack", "ALBUM_URL")
    requests = []
    page.on(
        "request",
        lambda r: requests.append(r.url) if not r.url.startswith(site_url) and "fonts.g" not in r.url else None,
    )
    page.goto(f"{site_url}/letterfield-soundtrack")
    expect(page.locator("html")).to_have_attribute("data-player", "off")
    expect(page.locator("#pending")).to_be_visible()
    expect(page.locator(".track")).to_have_count(len(render_album.TRACKS))
    expect(page.locator(".track audio").first).to_be_hidden()
    expect(page.locator(".dl").first).to_be_hidden()
    expect(page.locator(".downloads")).to_be_hidden()
    assert [r for r in requests if "counterscale" not in r and "sentry" not in r] == []
    assert errors == []


def tone(seconds: float = 0.4, rate: int = 8000) -> bytes:
    """A short tone as a WAV file, standing in for a track."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(
            b"".join(
                int(8000 * math.sin(2 * math.pi * 440 * i / rate)).to_bytes(2, "little", signed=True)
                for i in range(int(seconds * rate))
            )
        )
    return out.getvalue()


def serve_album(page: Page, missing: str = "") -> None:
    body = tone()

    def handle(route: Route) -> None:
        if missing and route.request.url.endswith(missing):
            route.fulfill(status=404, body="")
        else:
            route.fulfill(status=200, content_type="audio/wav", body=body, headers={"Accept-Ranges": "none"})

    page.route(f"{ALBUM}/**", handle)


def open_album(page: Page, site_url: str) -> None:
    page.goto(f"{site_url}/letterfield-soundtrack?album={ALBUM}#debug")
    page.wait_for_function("window.__album")
    # Muted, a track may play without a tap.
    page.evaluate("document.querySelectorAll('audio').forEach(a => { a.muted = true; })")


def play(page: Page, n: int) -> None:
    page.evaluate("n => document.querySelectorAll('audio')[n].play()", n)


def test_tracks_play_in_turn_from_wherever_one_starts(page: Page, site_url, errors):
    serve_album(page)
    open_album(page, site_url)
    html, rows = page.locator("html"), page.locator(".track")
    expect(html).to_have_attribute("data-player", "idle")
    expect(page.locator(".dl").first).to_have_attribute("href", f"{ALBUM}/letterfield-01-drift.mp3")
    expect(page.locator("#zip")).to_have_attribute("href", f"{ALBUM}/letterfield-soundtrack.zip")
    # Chimes, then Lantern after it, then the album's over.
    play(page, 3)
    expect(html).to_have_attribute("data-player", "playing")
    expect(rows.nth(3)).to_have_attribute("aria-current", "true")
    expect(rows.nth(4)).to_have_attribute("aria-current", "true")
    expect(html).to_have_attribute("data-player", "idle")
    expect(page.locator(".track[aria-current]")).to_have_count(0)
    assert errors == []


def test_one_track_plays_at_a_time_and_pauses_where_it_is(page: Page, site_url, errors):
    serve_album(page)
    open_album(page, site_url)
    html, audio = page.locator("html"), page.locator("audio")
    page.evaluate("document.querySelectorAll('audio').forEach(a => { a.loop = true; })")  # long enough to watch
    play(page, 0)
    expect(html).to_have_attribute("data-player", "playing")
    play(page, 2)
    expect(page.locator(".track").nth(2)).to_have_attribute("aria-current", "true")
    page.wait_for_function("document.querySelectorAll('audio')[0].paused")
    assert page.evaluate("__album.current()") == 2
    audio.nth(2).evaluate("a => a.pause()")
    expect(html).to_have_attribute("data-player", "paused")
    expect(page.locator(".track").nth(2)).to_have_attribute("aria-current", "true")
    play(page, 2)
    expect(html).to_have_attribute("data-player", "playing")
    assert errors == []


def test_a_track_that_wont_load_says_so(page: Page, site_url, errors):
    serve_album(page, missing="letterfield-02-orbit.mp3")
    open_album(page, site_url)
    page.evaluate("document.querySelectorAll('audio')[1].play().catch(() => {})")
    expect(page.locator("html")).to_have_attribute("data-player", "failed")
    expect(page.locator(".track").nth(1).locator(".failed")).to_be_visible()
    # Another track plays as ever.
    play(page, 0)
    expect(page.locator("html")).to_have_attribute("data-player", "playing")
    assert all("404" in e for e in errors), errors


def test_the_maps_tools_link_here_and_the_way_back_steps_back(page: Page, site_url, errors):
    page.goto(f"{site_url}/letterfield#debug")
    page.wait_for_function("window.__lf")
    expect(page.locator("#soundtrackLink")).to_have_attribute("href", "/letterfield-soundtrack")
    game, n = page.evaluate("[location.pathname + location.hash, history.length]")
    page.locator("#soundtrackLink").evaluate("a => a.click()")
    page.wait_for_url("**/letterfield-soundtrack")
    page.reload()  # it still knows where it came from
    page.click(".home")
    page.wait_for_url(re.compile(r"/letterfield(#.*)?$"))
    assert page.evaluate("[location.pathname + location.hash, history.length]") == [game, n + 1]
    assert errors == []


def test_opened_on_its_own_the_way_back_opens_the_map(page: Page, site_url, errors):
    page.goto(f"{site_url}/letterfield-soundtrack")
    n = page.evaluate("history.length")
    page.click(".home")
    page.wait_for_url(re.compile(r"/letterfield$"))
    assert page.evaluate("history.length") == n + 1
    assert errors == []
