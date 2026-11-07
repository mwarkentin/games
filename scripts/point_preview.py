#!/usr/bin/env python3
"""Point a built site at a pull request's preview instead of production.

The preview workflow (.github/workflows/preview.yml) runs this on _site/
after build.sh, before uploading it as a Worker Preview of its own. It
rewrites, in every text file:

- the live site's address (link previews, the sitemap, the game list's
  links) to the preview's own, so moving around the preview stays on it;
- the leaderboard Worker's address (LEADERBOARD_URL, ROOMS_URL and the
  survey log's SURVEY_URL in the games) to the pull request's Worker
  Preview, when it has one. Without --worker the pages keep production's
  Worker, which answers only the live site's origin, so a preview can never
  write to production's scores or rooms.

Telemetry and analytics check the bare hostname, not these URLs, so they
stay off on a preview either way.

Usage: point_preview.py SITE_DIR --site URL [--worker URL]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import BASE_URL, WORKER_URL

# Everything the build writes as text. Images, icons and MIDI files are left alone.
TEXT_SUFFIXES = {".html", ".js", ".json", ".txt", ".xml", ".webmanifest"}
# An https origin with nothing after it: what --site and --worker must be.
ORIGIN = re.compile(r"https://[a-z0-9.-]+")


def origin(value: str) -> str:
    value = value.rstrip("/")
    if not ORIGIN.fullmatch(value):
        raise argparse.ArgumentTypeError(f"not an https origin: {value!r}")
    return value


def point_text(text: str, site: str, worker: str = "") -> str:
    # Only whole URLs: the address followed by a path, quote or end, never a
    # longer hostname that happens to start the same way.
    text = re.sub(re.escape(BASE_URL) + r"(?![\w.-])", site, text)
    if worker:
        text = re.sub(re.escape(WORKER_URL) + r"(?![\w.-])", worker, text)
    return text


def point_site(site_dir: Path, site: str, worker: str = "") -> list[Path]:
    """Rewrite the site in place; returns the files that changed."""
    changed = []
    for path in sorted(site_dir.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text("utf-8")
        pointed = point_text(text, site, worker)
        if pointed != text:
            path.write_text(pointed, "utf-8")
            changed.append(path)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("site_dir", type=Path)
    parser.add_argument("--site", type=origin, required=True, help="the preview's own origin")
    parser.add_argument("--worker", type=origin, default="", help="the Worker Preview's origin, if any")
    args = parser.parse_args()
    changed = point_site(args.site_dir, args.site, args.worker)
    target = args.worker or f"{WORKER_URL} (production's Worker)"
    print(f"Pointed {len(changed)} files at {args.site}, with {target}")


if __name__ == "__main__":
    main()
