#!/usr/bin/env python3
"""Copy everything publishable into the site directory.

Games are copied as they are apart from one addition: telemetry.js, inlined
before </head>. Nothing is drawn on top of them, because each one owns the
whole screen. games.json is copied alongside them. Anything not listed here
(scripts, tests, Markdown, telemetry.js itself) never reaches the site.

Usage: publish.py [SITE_DIR]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from common import ROOT, game_files

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
    if "<script data-telemetry" in text:
        return text
    tag = f'<script data-telemetry data-release="{release}">\n{script.strip()}\n</script>\n'
    index = text.lower().find("</head>")
    if index == -1:
        return f"{text.rstrip()}\n{tag}"
    return f"{text[:index]}{tag}{text[index:]}"


def publish(site_dir: Path, root: Path = ROOT) -> list[str]:
    site_dir.mkdir(parents=True, exist_ok=True)
    telemetry = (root / TELEMETRY).read_text("utf-8")
    release = current_release(root)

    published = game_files(root)
    for filename in published:
        text = (root / filename).read_text("utf-8")
        (site_dir / filename).write_text(inject_telemetry(text, telemetry, release), "utf-8")
    games_json = root / "games.json"
    if games_json.exists():
        shutil.copy2(games_json, site_dir / "games.json")
    return published


def main() -> None:
    site_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    published = publish(site_dir)
    print(f"Published {len(published)} games to {site_dir}")


if __name__ == "__main__":
    main()
