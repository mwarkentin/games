#!/usr/bin/env python3
"""Copy everything publishable into the site directory.

Games are copied exactly as they are, with nothing injected: each one owns
the whole screen. games.json is copied alongside them. Anything not listed
here (scripts, tests, Markdown) never reaches the site.

Usage: publish.py [SITE_DIR]
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from common import ROOT, game_files


def publish(site_dir: Path, root: Path = ROOT) -> list[str]:
    site_dir.mkdir(parents=True, exist_ok=True)
    published = game_files(root)
    for filename in published:
        shutil.copy2(root / filename, site_dir / filename)
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
