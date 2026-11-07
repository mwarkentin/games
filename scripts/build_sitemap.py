#!/usr/bin/env python3
"""Build sitemap.xml and robots.txt from games.json.

Adapted from build_sitemap.py in https://github.com/simonw/tools by Simon
Willison, licensed under the Apache License 2.0 (see LICENSE). Changed: writes
into the site directory and adds robots.txt pointing at the sitemap.

Usage: build_sitemap.py [SITE_DIR]
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from build_changelog import read_changelog
from common import BASE_URL, GENERATED_PAGES, ROOT, changelog_apps, changelog_path, parse_date

NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"


def lastmod(value: str | None) -> str | None:
    parsed = parse_date(value)
    return parsed.date().isoformat() if parsed else None


def build_sitemap(games: list[dict], changelogs: dict[str, str] | None = None) -> str:
    """changelogs maps each changelog's path to the date of its newest day."""
    entries = {game["url"]: lastmod(game.get("updated")) for game in games}
    # The home page and colophon change whenever any game does.
    newest = max((date for date in entries.values() if date), default=None)
    for path in GENERATED_PAGES.values():
        entries[path] = newest
    entries.update(changelogs or {})

    ET.register_namespace("", NAMESPACE)
    urlset = ET.Element(f"{{{NAMESPACE}}}urlset")
    for path, date in sorted(entries.items(), key=lambda item: (item[0] != "/", item[0])):
        url = ET.SubElement(urlset, f"{{{NAMESPACE}}}url")
        ET.SubElement(url, f"{{{NAMESPACE}}}loc").text = BASE_URL + quote(path)
        if date:
            ET.SubElement(url, f"{{{NAMESPACE}}}lastmod").text = date
    ET.indent(urlset, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(urlset, encoding="unicode") + "\n"


def main() -> None:
    site_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    games = json.loads((ROOT / "games.json").read_text("utf-8"))
    changelogs = {changelog_path(app): read_changelog(app)[0][0].isoformat() for app in changelog_apps()}
    (site_dir / "sitemap.xml").write_text(build_sitemap(games, changelogs), "utf-8")
    (site_dir / "robots.txt").write_text(f"Sitemap: {BASE_URL}/sitemap.xml\n", "utf-8")
    print(f"Built sitemap.xml with {len(games) + len(GENERATED_PAGES) + len(changelogs)} URLs")


if __name__ == "__main__":
    main()
