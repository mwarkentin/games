"""Which pytest files a pull request needs, and over how many shards.

The Test workflow's plan job pipes in the pull request's changed files,
one per line, and reads back JSON:

    {"pytest": true, "tests": ["tests/test_war.py", ...], "shards": [1, 2]}

`tests` empty means the whole suite. A pull request whose every file belongs
to one game or a few (its pages, its tests, its changelog, its icon, its link
preview) runs those games' tests, and every test file named for no game,
which covers all of them at once (the smoke tests, the build, the PWA,
feedback, telemetry...). Anything else changed means the whole suite: shared
scripts, fakes, music, the workflow. Files no pytest test or build script
reads (UNREAD: the Workers, their docs, AGENTS.md, the linters' own
files) don't count either way, and a pull request that only changes those
runs no pytest at all. If a test starts reading one, take it out of UNREAD.

A game's tests are the test files named for one of its pages
(tests/test_war_rooms.py is War's) and any other test file that loads one
of them, as Air Traffic Controller's leaderboard tests load Doodle Chomp's
page. A page that belongs to a game, like letterfield-log.html, counts as
that game: a change to either runs both.

    python3 scripts/select_tests.py < changed.txt
    python3 scripts/select_tests.py --base origin/main   # a branch's changes from main
    python3 scripts/select_tests.py --all
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from common import ROOT, app_of, game_files

# Shards are about this many seconds of tests (from .test_durations), each
# run over four workers. The whole suite is about 1,200 s, so three shards.
SHARD_SECONDS = 450
MAX_SHARDS = 3
UNREAD = re.compile(r"^(worker/|share/|preview/|docs/|AGENTS\.md$|CLAUDE\.md$|biome\.jsonc$|scripts/lint\.sh$)")


def apps(root: Path) -> dict[str, str]:
    """Each page's slug, mapped to the app it belongs to."""
    return {
        name.removesuffix(".html"): app_of((root / name).read_text("utf-8"), name.removesuffix(".html"))
        for name in game_files(root)
    }


def owner(path: str, pages: dict[str, str]) -> str | None:
    """The app a changed file belongs to, or None if it's shared."""
    p = Path(path)
    if len(p.parts) == 1 and p.suffix == ".html":
        return pages.get(p.stem)
    if len(p.parts) == 2 and p.parts[0] == "tests" and p.name.startswith("test_") and p.suffix == ".py":
        return named_for(p.stem, pages)
    if len(p.parts) == 2 and p.parts[0] == "changelog" and p.suffix == ".md":
        return p.stem if p.stem in pages.values() else None
    if len(p.parts) == 2 and p.parts[0] == "previews" and p.suffix == ".jpg":
        return pages.get(p.stem)
    if len(p.parts) == 2 and p.parts[0] == "icons":
        app = re.sub(r"-\d+$", "", p.stem)  # foo.svg and foo-192.png
        return app if app in pages.values() else None
    return None


def named_for(stem: str, pages: dict[str, str]) -> str | None:
    """The app a test file is named for: test_war_rooms is War's."""
    name = stem.removeprefix("test_")
    for slug in sorted(pages, key=len, reverse=True):
        under = slug.replace("-", "_")
        if name == under or name.startswith(under + "_"):
            return pages[slug]
    return None


def loads(text: str, slug: str) -> bool:
    """Whether a test file's text refers to a page: /war#debug, "war", war.html."""
    return re.search(rf"[/'\"]{re.escape(slug)}(?:\.html)?[?#/'\"]", text) is not None


def select(changed: list[str], root: Path = ROOT) -> dict:
    """What to run for these changed files; see the module's docstring."""
    durations = json.loads((root / ".test_durations").read_text("utf-8"))
    whole = {"pytest": True, "tests": [], "shards": shards(sum(durations.values()))}
    if not changed:
        return whole
    changed = [path for path in changed if not UNREAD.match(path)]
    if not changed:
        return {"pytest": False, "tests": [], "shards": [1]}

    pages = apps(root)
    owners = {owner(path, pages) for path in changed}
    if None in owners:
        return whole
    slugs = [slug for slug, app in pages.items() if app in owners]

    tests = []
    for path in sorted((root / "tests").glob("test_*.py")):
        mine = named_for(path.stem, pages)
        text = path.read_text("utf-8")
        if mine is None or mine in owners or any(loads(text, slug) for slug in slugs):
            tests.append(path.relative_to(root).as_posix())

    average = sum(durations.values()) / len(durations)
    total = sum(seconds for test, seconds in durations.items() if test.split("::")[0] in tests)
    # New tests aren't in .test_durations yet: count each test file it doesn't
    # know at all as one average test, so a shard is never left with nothing.
    total += average * sum(1 for t in tests if not any(k.startswith(t + "::") for k in durations))
    return {"pytest": True, "tests": tests, "shards": shards(total)}


def changed_since(base: str, root: Path = ROOT) -> list[str] | None:
    """The files a branch changes from where it left `base`, both sides of a
    rename included as in a pull request's files, or None if git can't say."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
        cwd=root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Can't compare with {base}, so testing everything: {result.stderr.strip()}", file=sys.stderr)
        return None
    return result.stdout.split("\n")


def shards(seconds: float) -> list[int]:
    return list(range(1, max(1, min(MAX_SHARDS, math.ceil(seconds / SHARD_SECONDS))) + 1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="the whole suite, whatever changed")
    parser.add_argument("--base", help="select for this branch's changes from BASE, not stdin's list")
    args = parser.parse_args()
    if args.all:
        changed = []
    elif args.base:
        changed = changed_since(args.base) or []
        print(f"Changed from {args.base}: {' '.join(c for c in changed if c) or 'nothing'}", file=sys.stderr)
    else:
        changed = list(sys.stdin)
    changed = [line.strip() for line in changed if line.strip()]
    print(json.dumps(select(changed)))


if __name__ == "__main__":
    main()
