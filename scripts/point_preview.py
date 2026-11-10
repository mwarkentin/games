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
  write to production's scores or rooms;
- the share Worker's address (Letterfield's SHARE_URL) to nothing, so a
  preview's shares link straight to the preview's own game, not to
  production's cards, which send people to the live site.

With --banner, the generated pages (home page, colophon, changelogs) get a strip along the top
naming the preview (the pull request and commit), linked to --banner-link.
Games are left without one: they own the whole screen. With --title-prefix,
every page's <title> starts with it instead, so a game opened straight from a
link still says it's a preview in its tab and history. Link-preview cards and
Home Screen names keep the page's own title.

Telemetry and analytics check the bare hostname, not these URLs, so they
stay off on a preview either way.

Usage: point_preview.py SITE_DIR --site URL [--worker URL] [--banner TEXT --banner-link URL] [--title-prefix TEXT]
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from common import BASE_URL, WORKER_URL, generated_pages

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
    return re.sub(r"\b(const SHARE_URL = )'[^']*'", r"\1''", text)


def add_banner(text: str, banner: str, link: str = "") -> str:
    """A strip at the top of a generated page, saying it's a preview and of what."""
    label = html.escape(banner)
    if link:
        label = f'<a href="{html.escape(link)}">{label}</a>'
    strip = (
        '<div class="preview-banner" style="background:#ffd84d;color:#1b1b1b;'
        'text-align:center;font-weight:600;padding:0.4rem 16px;overflow-wrap:anywhere">'
        f"{label}</div>"
    )
    style = "<style>.preview-banner a { color: inherit; }</style>"
    text = text.replace("</head>", f"{style}\n</head>", 1)
    return re.sub(r"(<body[^>]*>)", lambda m: f"{m.group(1)}\n{strip}", text, count=1)


def prefix_title(text: str, prefix: str) -> str:
    """Put prefix at the start of the page's <title>, once."""
    return re.sub(
        r"(<title[^>]*>)", lambda m: m.group(1) + html.escape(prefix, quote=False), text, count=1
    )


def point_site(
    site_dir: Path,
    site: str,
    worker: str = "",
    banner: str = "",
    banner_link: str = "",
    title_prefix: str = "",
) -> list[Path]:
    """Rewrite the site in place; returns the files that changed."""
    changed = []
    generated = set(generated_pages())
    for path in sorted(site_dir.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text("utf-8")
        pointed = point_text(text, site, worker)
        if banner and path.relative_to(site_dir).as_posix() in generated:
            pointed = add_banner(pointed, banner, banner_link)
        if title_prefix and path.suffix == ".html":
            pointed = prefix_title(pointed, title_prefix)
        if pointed != text:
            path.write_text(pointed, "utf-8")
            changed.append(path)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("site_dir", type=Path)
    parser.add_argument("--site", type=origin, required=True, help="the preview's own origin")
    # No default: argparse would run origin() on it.
    parser.add_argument("--worker", type=origin, help="the Worker Preview's origin, if any")
    parser.add_argument("--banner", default="", help="text for a strip atop the generated pages")
    parser.add_argument("--banner-link", default="", help="where the strip links to")
    parser.add_argument("--title-prefix", default="", help="text to start every page's <title> with")
    args = parser.parse_args()
    changed = point_site(args.site_dir, args.site, args.worker or "", args.banner, args.banner_link, args.title_prefix)
    target = args.worker or f"{WORKER_URL} (production's Worker)"
    print(f"Pointed {len(changed)} files at {args.site}, with {target}")


if __name__ == "__main__":
    main()
