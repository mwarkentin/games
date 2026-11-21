"""Record Letterfield's clips and game screens into _architecture/ (see README.md).

Clips are captured with the page's clock stopped, a frame at a time, so they
play smoothly however slowly this machine draws, then joined by ffmpeg into
an MP4 and a GIF:

  clips/claim.mp4, .gif        the claim explainer playing the race (explainers/claim.html)
  clips/supernova.mp4, .gif    a territory going supernova in the game, played alone

Screens are the game and its pages at 2x, light and dark, on the real map:

  screens/supernova-*.png      the burst, and the shockwave rolling out
  screens/field-notes-*.png    the field notes afterwards, the supernova kept at the top
  screens/far-view-*.png       zoomed all the way out on the shared survey
  screens/universe-*.png       the Universe map: the survey's 100 × 100 territories, charted so far
  screens/surveyors-*.png      the list of surveyors
  screens/log-week-*.png       the survey log's week, with its top lists
  screens/log-day-*.png        the log of one day, word by word
  screens/timelapse-*.png      the timelapse, part way through

Everyone in them is made up: the initials are invented, and the words they
chart are real words from the map. The Universe map's counts come from
data/survey.json, the live survey's public totals, which name nobody.

The site is built into _architecture/site and served from here. Every address
of the Worker is answered by the tests' own fakes (tests/fake_*.py), and any
host but this one, the fonts' and the CDNs' is refused, so nothing reaches
production.

    uv run docs/architecture/capture.py               everything (needs ffmpeg)
    uv run docs/architecture/capture.py supernova     the scenes named
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

from kit import HERE, OUT, ROOT, world

sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "scripts")]
from fake_leaderboard import blank_constants, stand_in_for_worker, without_worker  # noqa: E402
from fake_survey import FakeSurvey, world_map  # noqa: E402
from fake_survey_log import DAY_MS, HOUR_MS, SURVEY, FakeSurveyLog  # noqa: E402

SITE = OUT / "site"
CLIPS, SCREENS = OUT / "clips", OUT / "screens"
ALLOWED = {"127.0.0.1", "fonts.googleapis.com", "fonts.gstatic.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com"}
NOW_MS = 1_795_204_800_000  # Friday, November 20, 2026, 3 PM in Toronto: "now" in the survey's screens
INITIALS = ["ZED", "KIM", "SIS", "ABE", "JOY", "REX", "UMA", "OLI", "PIP", "DOT", "NED", "BEA"]  # made up
TOKEN = "5" * 32  # this browser's player token in the survey's screens, signed as ZED
# The welcome card seen, and achievement and day notes quietened, as in every test (tests/conftest.py).
QUIET = {"letterfield.coach.v1": "1", "letterfield.quiet.v1": '["achievement","day"]'}

# The hidden words of territory (0, 0), as the game's own test of a supernova finds them.
TERRITORY_WORDS = """() => {
  const out = [];
  for (let cy = 0; cy < 4; cy++) for (let cx = 0; cx < 4; cx++) for (const o of window.__lf.chunk(cx, cy).words) out.push([o.w, o.x, o.y, o.d]);
  return out;
}"""
COLLECT = "words => { for (const [w, x, y, d] of words) window.__lf.collect(w, x, y, d, false); }"


class PagesHandler(http.server.SimpleHTTPRequestHandler):
    """Serves /foo from foo.html, as GitHub Pages does (tests/conftest.py)."""

    def translate_path(self, path: str) -> str:
        fs_path = super().translate_path(path)
        return fs_path + ".html" if not os.path.exists(fs_path) and os.path.exists(fs_path + ".html") else fs_path

    def log_message(self, format, *args):
        pass


def serve() -> str:
    subprocess.run(["bash", "build.sh"], cwd=ROOT, env={**os.environ, "SITE_DIR": str(SITE), "PYTHON": sys.executable},
                   check=True, capture_output=True)  # fmt: skip
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(PagesHandler, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}"


def context(browser, size, scheme, scale=2):
    """A browser context that can only reach this server, the fonts and the CDNs; the Worker is faked."""
    ctx = browser.new_context(viewport={"width": size[0], "height": size[1]}, device_scale_factor=scale,
                              color_scheme=scheme, timezone_id="America/Toronto", locale="en-US",
                              service_workers="block")  # fmt: skip

    def guard(route):
        url = urlparse(route.request.url)
        if url.scheme == "file" or url.hostname in ALLOWED:
            route.continue_()
        else:
            route.abort()

    ctx.route("**/*", guard)
    stand_in_for_worker(ctx)  # routed later, so it answers the Worker's addresses before the guard
    return ctx


def remember(page, items: dict) -> None:
    """localStorage for the game before it loads: settings, and who this surveyor is."""
    page.add_init_script(f"for (const [k, v] of Object.entries({json.dumps(items)})) localStorage.setItem(k, v);")


# -- frames and clips --
def frames(page, folder: Path, seconds: float, fps: int, clip=None, at=None) -> int:
    """Screenshots of `seconds` of the page at `fps`, the stopped clock moved on between each.

    `at` maps a frame number to something to do just before it. Returns the frames taken."""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    n = round(seconds * fps)
    for i in range(n):
        if at and i in at:
            at[i]()
        page.clock.run_for(round((i + 1) * 1000 / fps) - round(i * 1000 / fps))
        page.screenshot(path=folder / f"f{i:05d}.png", clip=clip)
    return n


def stop_clock(page) -> None:
    """Stops the page's clock where it is (Playwright's clock counts in seconds)."""
    page.clock.pause_at(page.evaluate("Date.now()") / 1000 + 0.02)


def encode(
    folder: Path, name: str, fps: int, gif_width: int, gif_fps: int = 12, crf: int = 22, gif_seconds=None
) -> None:
    """The frames as an MP4 (H.264, for a blog's <video>) and a GIF, in clips/; the GIF can stop early, to stay small."""
    CLIPS.mkdir(parents=True, exist_ok=True)
    src = ["-framerate", str(fps), "-i", str(folder / "f%05d.png")]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *src, "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf), "-preset", "slow", "-movflags", "+faststart",
                    str(CLIPS / f"{name}.mp4")], check=True)  # fmt: skip
    palette = (f"fps={gif_fps},scale={gif_width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
               "[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle")  # fmt: skip
    until = ["-t", str(gif_seconds)] if gif_seconds else []
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *src, *until, "-vf", palette, str(CLIPS / f"{name}.gif")], check=True
    )
    sizes = ", ".join(f"{(CLIPS / f'{name}.{ext}').stat().st_size / 1e6:.1f} MB {ext}" for ext in ("mp4", "gif"))
    print(f"  clip {name}: {sizes}")


def shot(page, name: str, scheme: str, **kw) -> None:
    SCREENS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=SCREENS / f"{name}-{scheme}.png", **kw)
    print(f"  screen {name}-{scheme}")


# -- the scenes --
def claim_clip(browser, base: str) -> None:
    """The claim explainer, playing the race from ZED circling PURIM to the survey log."""
    ctx = context(browser, (1180, 1130), "light", scale=1)
    page = ctx.new_page()
    page.clock.install()
    page.goto((OUT / "explainers" / "claim.html").as_uri())
    page.wait_for_function("window.__claim")
    page.evaluate("window.__claim.show(0); window.__claim.speed(1.35)")
    stage, caption = page.locator("#wrap").bounding_box(), page.locator(".caption").bounding_box()
    clip = {"x": stage["x"] - 10, "y": stage["y"] - 10, "width": stage["width"] + 20,
            "height": caption["y"] + caption["height"] - stage["y"] + 14}  # fmt: skip
    stop_clock(page)
    page.evaluate("window.__claim.play()")
    last = page.evaluate("window.__claim.steps()") - 1
    folder, fps = OUT / "frames" / "claim", 25
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    i = tail = 0
    while tail < 2.5 * fps:  # until the last step has shown for a while
        page.clock.run_for(round((i + 1) * 1000 / fps) - round(i * 1000 / fps))
        page.screenshot(path=folder / f"f{i:05d}.png", clip=clip)
        i += 1
        if tail or (i % 10 == 0 and page.evaluate("window.__claim.step()") == last):
            tail += 1
    encode(folder, "claim", fps, gif_width=720, gif_fps=8)
    ctx.close()


def supernova(browser, base: str, scheme: str, clip: bool) -> None:
    """Territory (0, 0) played alone: every hidden word found but one, then the last."""
    ctx = context(browser, (1280, 720), scheme, scale=1 if clip else 2)
    page = ctx.new_page()
    without_worker(page, base, "letterfield")  # alone, so the territory counts your own finds
    remember(
        page, {**QUIET, "letterfield.notes.v1": "0", "letterfield.cam.v1": json.dumps({"x": 26, "y": 22, "cs": 15})}
    )
    page.clock.install(time=NOW_MS / 1000)
    page.goto(f"{base}/letterfield#debug")
    page.wait_for_function("window.__lf")
    words = page.evaluate(TERRITORY_WORDS)
    page.evaluate(COLLECT, words[1:])
    page.wait_for_timeout(5000)  # the finds fly into the notes, and the notes settle
    stop_clock(page)
    last = lambda: page.evaluate(COLLECT, words[:1])  # noqa: E731
    if clip:
        folder, fps = OUT / "frames" / "supernova", 30
        frames(page, folder, 9.5, fps, at={12: last})
        encode(folder, "supernova", fps, gif_width=560, gif_fps=12, crf=24, gif_seconds=7.5)
    else:
        last()
        page.clock.run_for(3050)
        shot(page, "supernova-burst", scheme)
        page.clock.run_for(900)
        shot(page, "supernova-wave", scheme)
        page.clock.run_for(9000)
        page.set_viewport_size({"width": 1280, "height": 800})
        page.click("#notesToggle")
        page.clock.run_for(1500)
        page.wait_for_timeout(600)  # the drawer slides in on CSS's own clock
        shot(page, "field-notes", scheme)
    ctx.close()


def survey_history() -> tuple[list, dict, dict, dict]:
    """Three days of the survey around the origin, for the log and the timelapse: real words from
    the map, charted by made-up surveyors, and territory (0, 0), Menorah Hollow, charted whole."""
    rng = random.Random(20261120)
    themes = world("themes")
    entries, places, names, totals = [], {}, {}, {}
    today = NOW_MS // DAY_MS
    for rx, ry, th, _hue, total, name in world("territories", -2, -1, 2, 2):
        places[f"{rx},{ry}"], names[th], totals[f"{rx},{ry}"] = name, themes[th][:2], total
        hidden = world("area", rx * 48, ry * 48, 48, 48)["hidden"]
        share = 1.0 if (rx, ry) == (0, 0) else rng.uniform(0.12, 0.55)
        for h in rng.sample(hidden, round(len(hidden) * share)):
            day = today - rng.choice([0, 1, 1, 2, 2, 2]) if (rx, ry) != (0, 0) else today - 1
            hour = rng.choices(
                range(24), weights=[1, 1, 1, 1, 1, 1, 1, 2, 3, 3, 3, 4, 5, 6, 6, 6, 7, 8, 9, 9, 8, 6, 4, 2]
            )[0]
            at = day * DAY_MS + hour * HOUR_MS + rng.randrange(HOUR_MS)
            if at >= NOW_MS:
                at = NOW_MS - rng.randrange(1, 6) * HOUR_MS - rng.randrange(HOUR_MS)
            who = rng.choice(INITIALS[:6] if (rx, ry) == (0, 0) else INITIALS + [""])
            entries.append([h["w"], h["x"], h["y"], h["d"], 0, who, at, th])
    return entries, places, names, totals


def log_pages(browser, base: str, scheme: str) -> None:
    """The survey log, and the timelapse part way through, against a fake of the log's API."""
    entries, places, themes, totals = survey_history()
    fake = FakeSurveyLog(entries, places, themes, totals=totals, now_ms=NOW_MS)
    ctx = context(browser, (1280, 900), scheme)
    page = ctx.new_page()
    page.clock.set_fixed_time(NOW_MS / 1000)
    page.route(f"{SURVEY}/v1/survey/log/**", fake.handle)
    page.goto(f"{base}/letterfield-log?survey={SURVEY}&period=week")
    page.wait_for_selector('html[data-log="ready"]')
    page.wait_for_timeout(1000)
    shot(page, "log-week", scheme)
    page.goto(f"{base}/letterfield-log?survey={SURVEY}&day=2026-11-19")  # the day Menorah Hollow went supernova
    page.wait_for_selector('html[data-log="ready"]')
    page.wait_for_timeout(1000)
    shot(page, "log-day", scheme)
    page.close()
    page = ctx.new_page()
    page.clock.install(time=NOW_MS / 1000)
    page.route(f"{SURVEY}/v1/survey/log/**", fake.handle)
    page.goto(f"{base}/letterfield-timelapse?survey={SURVEY}")
    page.wait_for_function("window.__tl && __tl.loaded.days >= 3", timeout=20000)
    page.get_by_role("button", name="4×").click()
    page.wait_for_function(f"__tl.shown.n > {len(entries) - 90}", timeout=120000)  # past Menorah Hollow's supernova
    page.click("#play")  # paused, part way through
    page.wait_for_timeout(500)
    shot(page, "timelapse", scheme)
    ctx.close()


def survey_game(browser, base: str, scheme: str) -> None:
    """The game on a fake of the shared survey: zoomed out, the Universe map, and the surveyors."""
    rng = random.Random(7)
    pid = lambda s: hashlib.sha256(s.encode()).hexdigest()[:12]  # noqa: E731
    # Words others charted in sector 0,0, the one this surveyor is in, and where some of them are looking.
    claims = []
    for rx in range(4):
        for ry in range(4):
            hidden = world("area", rx * 48, ry * 48, 48, 48)["hidden"]
            for h in rng.sample(hidden, round(len(hidden) * rng.uniform(0.2, 0.7))):
                claims.append(
                    [h["w"], h["x"], h["y"], h["d"], 0, rng.choice(INITIALS[1:]), NOW_MS - rng.randrange(3 * DAY_MS)]
                )
    carets = [
        [pid(i), i, x, y] for i, x, y in (("KIM", 21.5, 14), ("SIS", 44.5, 30), ("ABE", 30.5, 39), ("JOY", 12.5, 27))
    ]
    listed = [
        [pid(i), i, rng.randrange(-6, 7), rng.randrange(-5, 6), rng.choice([2, 5, 30, 90, 400]), 0]
        for i in INITIALS[1:]
    ]
    listed[:4] = [[pid(i), i, 0, 0, idle, 0] for i, idle in (("KIM", 2), ("SIS", 4), ("ABE", 11), ("JOY", 35))]
    snap = json.loads((HERE / "data" / "survey.json").read_text())["world"]
    counts = {(rx, ry): n for rx, ry, n in snap["territories"]}
    crowds = [[0, 0, 5], [-3, 2, 3], [4, -1, 2], [1, 5, 2]]  # sectors with people in them, made up
    fake = FakeSurvey(claims=claims, presence=carets, surveyors=listed,
                      world=world_map(counts, sectors=crowds, players=len(listed) + 1),
                      totals={"charted": snap["charted"], "total": snap["total"], "players": len(listed) + 1})  # fmt: skip

    def open_game(cam: dict):
        page = ctx.new_page()
        blank_constants(page, "letterfield", "TURNSTILE_SITE_KEY")
        page.route_web_socket(re.compile(r"^wss://survey\.test/"), fake.handle)
        page.route(f"{SURVEY}/v1/survey/world", fake.handle_world)
        page.route(f"{SURVEY}/v1/survey/surveyors*", fake.handle_list)
        remember(page, {**QUIET, "letterfield.notes.v1": "0", "games.initials": '"ZED"', "games.player": TOKEN,
                        "letterfield.cam.v1": json.dumps(cam)})  # fmt: skip
        page.clock.install(time=NOW_MS / 1000)
        page.goto(f"{base}/letterfield?survey={SURVEY}#debug")
        page.wait_for_function("window.__lf && window.__lf.surveyStatus() === 'live'", timeout=20000)
        page.wait_for_timeout(2500)
        return page

    ctx = context(browser, (1280, 800), scheme)
    page = open_game({"x": 24, "y": 24, "cs": 2})
    shot(page, "far-view", scheme)
    page.click("#notesToggle")
    page.click("#survey summary")
    page.wait_for_selector("#worldMap:not(.waiting)")
    page.wait_for_timeout(1200)
    shot(page, "universe", scheme)
    page.close()
    page = open_game({"x": 30, "y": 26, "cs": 22})
    page.click("#peopleBtn")
    page.wait_for_selector('html[data-who="ready"]', timeout=10000)
    page.wait_for_timeout(1200)
    shot(page, "surveyors", scheme)
    ctx.close()


SCENES = {
    "claim": lambda b, base: claim_clip(b, base),
    "supernova": lambda b, base: (
        supernova(b, base, "dark", clip=True),
        supernova(b, base, "dark", clip=False),
        supernova(b, base, "light", clip=False),
    ),  # fmt: skip
    "log": lambda b, base: (log_pages(b, base, "light"), log_pages(b, base, "dark")),
    "survey": lambda b, base: (survey_game(b, base, "light"), survey_game(b, base, "dark")),
}


def main() -> None:
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenes", nargs="*", help=f"scenes to record (default: all of {', '.join(SCENES)})")
    args = parser.parse_args()
    unknown = [s for s in args.scenes if s not in SCENES]
    if unknown:
        parser.error(f"no such scene: {', '.join(unknown)}")
    if not shutil.which("ffmpeg"):
        parser.error("ffmpeg is needed for the clips")
    base = serve()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in args.scenes or SCENES:
            print(name)
            SCENES[name](browser, base)
        browser.close()
    if (OUT / "frames").exists():
        shutil.rmtree(OUT / "frames")


if __name__ == "__main__":
    main()
