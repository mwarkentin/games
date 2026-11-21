"""Render Letterfield's architecture figures into _architecture/ (see README.md).

Each figure in figures.py is drawn in the game's light and dark colours as
SVG, with every letter an outline (kit.py), then rendered to a PNG at 2x in
Chromium. The interactive explainers in explainers/ are built with the
game's fonts inlined, so each is one self-contained HTML file. README.md's
list of figures and FACTS.md are written from the same registry, so a
figure's caption, alt text and sources never drift from the figure.

    uv run --with fonttools --with uharfbuzz --with brotli docs/architecture/render.py
    uv run --with fonttools --with uharfbuzz --with brotli docs/architecture/render.py big-picture claim-life
    ... render.py --no-png        SVGs only, for a quick look
    ... render.py --explainers    the interactive explainers alone
    ... render.py --clips         and each moving figure as an MP4 and a GIF too (needs ffmpeg)

It needs Node (the figures read the map from worker/src/letterfield-world.js),
Playwright's Chromium (`uv run playwright install chromium`, as the tests do)
and the network once, for the fonts.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from explainers import build_explainers
from figures import FIGURES, write_docs
from kit import HERE, OUT, THEMES

API = "https://api.games.michaelwarkentin.com"
SNAPSHOT = HERE / "data" / "survey.json"


def get(path: str):
    request = urllib.request.Request(API + path, headers={"User-Agent": "letterfield-architecture-figures"})
    with urllib.request.urlopen(request, timeout=30) as r:
        return json.load(r)


def refresh_snapshot() -> None:
    """The live survey's public numbers, read once, into data/survey.json: only GETs the log page makes itself.

    Kept without anyone's initials: the figures only need where, when and how many.
    """
    world, span = get("/v1/survey/world"), get("/v1/survey/log/span")
    first, last = span["first"], span["last"] + 1
    novas = get(f"/v1/survey/log/novas/{first}/{last}")
    timelapse = get("/v1/survey/log/timelapse")
    top = get(f"/v1/survey/log/top/{first // 24}/{last // 24 + 1}")
    charted = base64.b64decode(world["territories"])
    snap = {
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "world": {
            "charted": world["charted"],
            "total": world["total"],
            "players": world["players"],
            "area": world["area"],
            "territories": [[i % 100 - 48, i // 100 - 48, n] for i, n in enumerate(charted) if n],
        },  # fmt: skip
        "log": {
            "first": first,
            "last": last,
            "hours": timelapse["hours"],
            "words": sum(n for _, n in timelapse["hours"]),
            "bounds": timelapse["bounds"],
            "surveyors": len(top["surveyors"]),
            "guilds": len(top["guilds"]),
        },  # fmt: skip
        "novas": [
            {
                "rx": n[0],
                "ry": n[1],
                "at": n[2],
                "first": n[8],
                "words": n[9],
                "surveyors": n[10],
                "theme": novas["themes"][str(n[13])][0],
                "name": novas["places"][f"{n[0]},{n[1]}"],
            }
            for n in novas["novas"]
        ],  # fmt: skip
    }
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, indent=1) + "\n")
    print(
        f"snapshot of the live survey at {snap['at']}: {snap['world']['charted']} charted, {len(snap['novas'])} supernovas"
    )


def render_pngs(svgs: list[Path]) -> None:
    """Each SVG to a PNG beside it at 2x: about 1600 pixels across for a blog column."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2, reduced_motion="reduce")  # the still figure
        for svg in svgs:
            w, h = (round(float(v)) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg.read_text()).groups())
            page.set_viewport_size({"width": w, "height": h})
            page.goto(svg.as_uri())
            page.screenshot(path=svg.with_suffix(".png"), clip={"x": 0, "y": 0, "width": w, "height": h})
        browser.close()


# Letterfield's own files, as against the site's other games and what every game shares (the build, CI,
# telemetry, the leaderboards, War's rooms): a pull request that touches one of these is one of Letterfield's.
LETTERFIELD = re.compile(
    r"^(letterfield[^/]*\.html|changelog/letterfield\.md|albums/letterfield/|icons/letterfield|previews/letterfield"
    r"|worker/src/(survey[^/]*|letterfield-world|players|achievements|define)\.js|worker/(SURVEY|ACHIEVEMENTS|TURNSTILE)\.md"
    r"|worker/migrations-log/|worker/migrations/000[345]_|worker/bench/|worker/test/(survey|players|achievements|define)"
    r"|share/|tests/(test_letterfield|test_survey|fake_survey|fake_definitions)[^/]*\.py"
    r"|scripts/(render_album|draw_album_art|survey_watch)\.py|\.github/workflows/survey-watch\.yml|docs/link-previews\.md)"
)
# Letterfield's code in the Worker, and its tests (the game's in tests/, the Worker's in worker/test/).
LETTERFIELD_WORKER = re.compile(r"^worker/src/(survey[^/]*|letterfield-world|players|achievements|define)\.js$")
LETTERFIELD_TESTS = re.compile(
    r"^(tests/(test_letterfield|test_survey|fake_survey|fake_definitions)[^/]*\.py"
    r"|worker/test/(survey|players|achievements|define)[^/]*\.js)$"
)


# Steps an animated SVG's motion to `t` seconds: its SMIL dots through the SVG's own clock, its CSS
# animations through the Web Animations API, both paused, so every frame is exactly where it should be.
STEP_TO = """t => {
  const svg = document.documentElement;
  svg.pauseAnimations();
  svg.setCurrentTime(t);
  for (const a of document.getAnimations()) { a.pause(); a.currentTime = t * 1000; }
}"""


def frames(page, svg: Path, times: list[float], out: Path, scale: float = 1) -> None:
    """Screenshots of an animated figure at each of `times` seconds, as out/f00000.png onwards."""
    w, h = (round(float(v)) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg.read_text()).groups())
    page.set_viewport_size({"width": w, "height": h})
    page.goto(svg.as_uri())
    out.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(times):
        page.evaluate(STEP_TO, t)
        page.screenshot(path=out / f"f{i:05d}.png", clip={"x": 0, "y": 0, "width": w, "height": h})


def record_clips(ids: list[str], fps: int = 25) -> None:
    """Each animated figure's loop as an MP4 and a GIF beside its SVGs, in both themes (needs ffmpeg)."""
    import shutil
    import subprocess

    from playwright.sync_api import sync_playwright

    moving = [fid for fid in ids if FIGURES[fid].draw(THEMES[0]).cycle]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1.5)
        for fid in moving:
            cycle = FIGURES[fid].draw(THEMES[0]).cycle
            for theme in THEMES:
                svg = OUT / "figures" / f"{fid}-{theme.name}.svg"
                folder = OUT / "frames" / f"{fid}-{theme.name}"
                if folder.exists():
                    shutil.rmtree(folder)
                frames(page, svg, [i / fps for i in range(round(cycle * fps))], folder)
                src = ["-framerate", str(fps), "-i", str(folder / "f%05d.png")]
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *src, "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-preset", "slow",
                                "-movflags", "+faststart", str(svg.with_suffix(".mp4"))], check=True)  # fmt: skip
                palette = ("fps=12,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];"
                           "[b][p]paletteuse=dither=none:diff_mode=rectangle")  # fmt: skip
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *src, "-vf", palette, str(svg.with_suffix(".gif"))],
                               check=True)  # fmt: skip
                shutil.rmtree(folder)
            print(f"  clips of {fid}: {cycle:g} s loops, light and dark")
        browser.close()


def refresh_history() -> None:
    """Letterfield's growth, PR by PR, from main's first-parent history, into data/history.json.

    Each merge to main is a row: its pull request, date and title, whether it touched Letterfield
    (`lf`), and the lines then in the game, its three companion pages, its code in the Worker and
    its tests. The site's other games share the repo, so their pull requests are rows too, with
    `lf` false, and their code counts in none of the lines."""
    import subprocess

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=HERE.parents[1], capture_output=True, text=True, check=True).stdout

    def lines(rev: str, path: str) -> int:
        out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=HERE.parents[1], capture_output=True)
        return out.stdout.count(b"\n") if out.returncode == 0 else 0

    def matching(rev: str, pattern: re.Pattern) -> int:
        return sum(lines(rev, f) for f in git("ls-tree", "-r", "--name-only", rev).split() if pattern.match(f))

    rows = []
    log = git("log", "--first-parent", "origin/main", "--reverse", "--date=short", "--format=%H|%P|%ad|%s|%b%x1e")
    for entry in filter(None, (e.strip() for e in log.split("\x1e"))):
        sha, parents, date, subject, body = (entry.split("|", 4) + [""])[:5]
        merge = re.match(r"Merge pull request #(\d+) from (\S+)", subject)
        squash = re.search(r"\(#(\d+)\)\s*$", subject)
        if merge:
            body_lines = [b for b in body.splitlines() if b.strip()]
            pr, title = int(merge[1]), body_lines[0] if body_lines else merge[2].split("/", 1)[-1]
        elif squash:
            pr, title = int(squash[1]), re.sub(r"\s*\(#\d+\)\s*$", "", subject)
        else:
            pr, title = None, subject
        changed = git("diff", "--name-only", parents.split()[0], sha).split() if parents else []
        rows.append({
            "pr": pr, "date": date, "title": title, "lf": any(LETTERFIELD.match(f) for f in changed),
            "game": lines(sha, "letterfield.html"),
            "pages": sum(lines(sha, f) for f in ("letterfield-log.html", "letterfield-timelapse.html",
                                                 "letterfield-soundtrack.html")),
            "worker": matching(sha, LETTERFIELD_WORKER), "tests": matching(sha, LETTERFIELD_TESTS),
        })  # fmt: skip
    (HERE / "data" / "history.json").write_text(json.dumps(rows, indent=0) + "\n")
    prs = [r for r in rows if r["pr"]]
    print(
        f"history: {len(rows)} commits on main, {len(prs)} pull requests, {sum(r['lf'] for r in prs)} of them Letterfield's"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="*", help="figures to render (default: all)")
    parser.add_argument("--no-png", action="store_true", help="write the SVGs only")
    parser.add_argument("--no-explainers", action="store_true", help="skip building the interactive explainers")
    parser.add_argument("--explainers", action="store_true", help="build the interactive explainers alone")
    parser.add_argument("--refresh", action="store_true", help="read the live survey's public numbers again first")
    parser.add_argument(
        "--clips", action="store_true", help="also record each moving figure as MP4 and GIF (needs ffmpeg)"
    )
    args = parser.parse_args()
    if args.explainers:
        return build_explainers()
    if args.refresh or not SNAPSHOT.exists():
        refresh_snapshot()
    if args.refresh or not (HERE / "data" / "history.json").exists():
        refresh_history()
    unknown = [i for i in args.ids if i not in FIGURES]
    if unknown:
        parser.error(f"no such figure: {', '.join(unknown)} (there are {', '.join(FIGURES)})")
    ids = args.ids or list(FIGURES)
    (OUT / "figures").mkdir(parents=True, exist_ok=True)
    started, svgs = time.time(), []
    for fid in ids:
        f = FIGURES[fid]
        for theme in THEMES:
            path = OUT / "figures" / f"{fid}-{theme.name}.svg"
            path.write_text(f.draw(theme).svg(f.title, f.alt))
            svgs.append(path)
        print(f"  {fid}: {f.title}")
    if not args.no_png:
        render_pngs(svgs)
    if args.clips:
        record_clips(ids)
    if not args.ids:
        write_docs()
        if not args.no_explainers:
            build_explainers()
    print(f"{len(svgs)} SVGs{'' if args.no_png else ' and PNGs'} in {OUT / 'figures'} ({time.time() - started:.0f} s)")


if __name__ == "__main__":
    main()
