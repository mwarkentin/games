#!/usr/bin/env python3
"""Copy everything publishable into the site directory.

Games are copied as they are apart from four additions, inserted before
</head>: link-preview tags (see inject_social in common.py), telemetry.js
(Sentry), analytics.js (Counterscale), and the links and script that make
each game a home-screen app (see build_pwa.py). Nothing is drawn on top of
them, because each one owns the whole screen. games.json is copied alongside
them, and so are the MIDI files in music/ that games play and the
link-preview images in previews/. Anything not listed here or in build_pwa.py
(scripts, tests, Markdown, the scripts' own files) never reaches the site.

Usage: publish.py [SITE_DIR]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from common import (
    ROOT,
    app_of,
    game_files,
    inject_analytics,
    inject_pwa,
    inject_social,
    inline_script,
    music_files,
    preview_files,
)

TELEMETRY = "telemetry.js"


def current_release(root: Path = ROOT) -> str:
    """The release Sentry files errors under: games@ and the commit being built."""
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    return f"games@{result.stdout.strip()}" if result.returncode == 0 else ""


def inject_telemetry(text: str, script: str, release: str) -> str:
    """Inline the telemetry script before </head>, or at the end, once.

    It's inline rather than a file so it runs before the game's own code
    without holding up the page for another request.
    """
    return inline_script(text, "data-telemetry", script, f' data-release="{release}"')


def publish(site_dir: Path, root: Path = ROOT) -> list[str]:
    site_dir.mkdir(parents=True, exist_ok=True)
    telemetry = (root / TELEMETRY).read_text("utf-8")
    release = current_release(root)

    published = game_files(root)
    for filename in published:
        slug = filename.removesuffix(".html")
        source = (root / filename).read_text("utf-8")
        app = app_of(source, slug)
        text = inject_social(source, app, f"/{slug}", root)
        text = inject_analytics(inject_telemetry(text, telemetry, release), root)
        text = inject_pwa(text, app)
        (site_dir / filename).write_text(text, "utf-8")
    games_json = root / "games.json"
    if games_json.exists():
        shutil.copy2(games_json, site_dir / "games.json")
    for name in [*music_files(root), *preview_files(root)]:
        (site_dir / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, site_dir / name)
    return published


def main() -> None:
    site_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    published = publish(site_dir)
    print(f"Published {len(published)} games to {site_dir}")


if __name__ == "__main__":
    main()
