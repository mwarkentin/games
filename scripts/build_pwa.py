#!/usr/bin/env python3
"""Make every page installable as a home-screen app that works offline.

Each game gets a web app manifest, so adding it to the Home Screen gives that
game an app of its own, opening full screen at the game. The home page and
colophon share a manifest for the whole collection. Names, descriptions and
colors come from each game's <head>: its <title>, description, theme-color
and, for a short label under the icon, apple-mobile-web-app-title.

Icons are the PNGs in icons/, drawn from the SVGs there by render_icons.py.
sw.js keeps an offline copy of every page, and of the music in music/. It's
the template at the root of the repo with those lists and a version filled
in; the version is a hash of the pages and music, so each deploy that changes
one refreshes every copy.

Run after the pages are built (see build.sh). Usage: build_pwa.py [SITE_DIR]
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from common import (
    GENERATED_PAGES,
    HOME_APP,
    ICON_SIZES,
    ROOT,
    SITE_NAME,
    extract_meta,
    extract_meta_description,
    extract_title,
    game_files,
    music_files,
)

SERVICE_WORKER = "sw.js"
HOME_SHORT_NAME = "Games"
HOME_DESCRIPTION = "Small browser games that run on a phone or a computer."
DEFAULT_COLOR = "#ffffff"

VERSION_LINE = re.compile(r"^const VERSION = .*;$", re.MULTILINE)
PAGES_LINE = re.compile(r"^const PAGES = .*;$", re.MULTILINE)
MUSIC_LINE = re.compile(r"^const MUSIC = .*;$", re.MULTILINE)


def build_manifest(
    app: str, path: str, *, name: str, short_name: str, description: str, color: str
) -> dict:
    icons = [
        {"src": f"/icons/{app}-{size}.png", "sizes": f"{size}x{size}", "type": "image/png"}
        for size in ICON_SIZES
        if size != 180  # the apple-touch-icon, linked from the page instead
    ]
    # The icons keep everything that matters inside the middle circle, so
    # Android can crop them to any shape.
    icons.append({**icons[-1], "purpose": "maskable"})
    return {
        "id": path,
        "name": name,
        "short_name": short_name,
        "description": description,
        "start_url": path,
        "scope": path,
        "display": "standalone",
        "background_color": color,
        "theme_color": color,
        "icons": icons,
    }


def game_manifest(filename: str, text: str) -> dict:
    slug = filename.removesuffix(".html")
    title = extract_title(text, slug)
    return build_manifest(
        slug,
        f"/{slug}",
        name=title,
        short_name=extract_meta(text, "apple-mobile-web-app-title") or title,
        description=extract_meta_description(text),
        color=extract_meta(text, "theme-color") or DEFAULT_COLOR,
    )


def home_manifest() -> dict:
    return build_manifest(
        HOME_APP,
        "/",
        name=SITE_NAME,
        short_name=HOME_SHORT_NAME,
        description=HOME_DESCRIPTION,
        color=DEFAULT_COLOR,
    )


def build_service_worker(template: str, pages: list[str], music: list[str], version: str) -> str:
    """Fill in the template's VERSION, PAGES and MUSIC lines."""
    assert VERSION_LINE.search(template) and PAGES_LINE.search(template) and MUSIC_LINE.search(template), (
        "sw.js needs VERSION, PAGES and MUSIC"
    )
    worker = VERSION_LINE.sub(lambda _: f"const VERSION = {json.dumps(version)};", template, count=1)
    worker = PAGES_LINE.sub(lambda _: f"const PAGES = {json.dumps(pages)};", worker, count=1)
    return MUSIC_LINE.sub(lambda _: f"const MUSIC = {json.dumps(music)};", worker, count=1)


def page_version(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()[:16]


def publish_pwa(site_dir: Path, root: Path = ROOT) -> dict[str, dict]:
    """Write the manifests, icons and sw.js into site_dir. Returns the manifests."""
    manifests = {
        filename.removesuffix(".html"): game_manifest(filename, (root / filename).read_text("utf-8"))
        for filename in game_files(root)
    }
    manifests[HOME_APP] = home_manifest()

    (site_dir / "manifests").mkdir(parents=True, exist_ok=True)
    (site_dir / "icons").mkdir(parents=True, exist_ok=True)
    for app, manifest in manifests.items():
        (site_dir / "manifests" / f"{app}.webmanifest").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8"
        )
        for size in ICON_SIZES:
            icon = root / "icons" / f"{app}-{size}.png"
            if not icon.exists():
                # Deploy anyway with the site's icon; tests/test_pwa.py insists on one.
                print(f"warning: no {icon.relative_to(root)}, using the home page's icon")
                icon = root / "icons" / f"{HOME_APP}-{size}.png"
            shutil.copy2(icon, site_dir / "icons" / f"{app}-{size}.png")

    pages = [*GENERATED_PAGES.values(), *(f"/{filename.removesuffix('.html')}" for filename in game_files(root))]
    music = [f"/{name}" for name in music_files(root)]
    files = [site_dir / name for name in [*GENERATED_PAGES, *game_files(root)]]
    files += [root / name for name in music_files(root)]
    template = (root / SERVICE_WORKER).read_text("utf-8")
    worker = build_service_worker(template, pages, music, page_version([*files, root / SERVICE_WORKER]))
    (site_dir / SERVICE_WORKER).write_text(worker, "utf-8")
    return manifests


def main() -> None:
    site_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    manifests = publish_pwa(site_dir)
    print(f"Built {len(manifests)} app manifests and {SERVICE_WORKER}")


if __name__ == "__main__":
    main()
