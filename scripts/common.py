"""Settings and helpers shared by the build scripts."""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

BASE_URL = "https://games.michaelwarkentin.com"
SITE_NAME = "games.michaelwarkentin.com"
REPO_URL = "https://github.com/mwarkentin/games"
ROOT = Path(__file__).resolve().parent.parent

# Pages the build generates. A game can't use these filenames.
GENERATED_PAGES = {"index.html": "/", "colophon.html": "/colophon"}


def game_files(root: Path = ROOT) -> list[str]:
    """Every game: the .html files at the top level of the repo."""
    return sorted(
        path.name
        for path in root.glob("*.html")
        if path.name not in GENERATED_PAGES
    )


def extract_title(text: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    return html.unescape(match.group(1).strip()) if match else fallback


def extract_meta_description(text: str) -> str:
    for tag in re.findall(r"<meta\b[^>]*>", text, re.IGNORECASE):
        if re.search(r"""name\s*=\s*["']description["']""", tag, re.IGNORECASE):
            match = re.search(r"""content\s*=\s*(["'])(.*?)\1""", tag, re.DOTALL)
            if match:
                return html.unescape(match.group(2).strip())
    return ""


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_date(value: datetime) -> str:
    return f"{value:%b} {value.day}, {value.year}"


PAGE_CSS = """
:root {
  color-scheme: light dark;
  --bg: #ffffff;
  --fg: #1b1b1b;
  --muted: #666666;
  --link: #0a5bc4;
  --rule: #e2e2e2;
  --panel: #f5f5f5;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #141414;
    --fg: #e6e6e6;
    --muted: #9a9a9a;
    --link: #78b4ff;
    --rule: #333333;
    --panel: #1f1f1f;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
.bar, main { max-width: 46rem; margin: 0 auto; padding: 0 16px; }
.bar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  padding-top: 0.9rem;
  padding-bottom: 0.9rem;
}
.bar .home { font-weight: 600; color: var(--fg); text-decoration: none; }
.bar nav a { margin-left: 1rem; }
.bar nav a:first-child { margin-left: 0; }
header { border-bottom: 1px solid var(--rule); }
main { padding-bottom: 3rem; }
a { color: var(--link); }
h1 { font-size: 1.6rem; line-height: 1.25; margin: 1.5rem 0 0.75rem; overflow-wrap: anywhere; }
h2 { font-size: 1.2rem; margin: 2rem 0 0.5rem; }
code {
  background: var(--panel);
  border-radius: 4px;
  padding: 0.1em 0.35em;
  font-size: 0.9em;
}
li { margin: 0.3rem 0; }
.muted { color: var(--muted); }
"""


def render_page(title: str, body: str, *, extra_css: str = "", description: str = "") -> str:
    """Wrap generated content in the shared page chrome."""
    meta = (
        f'\n<meta name="description" content="{html.escape(description)}">'
        if description
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{meta}
<title>{html.escape(title)}</title>
<style>{PAGE_CSS}{extra_css}</style>
</head>
<body>
<header>
  <div class="bar">
    <a class="home" href="/">{SITE_NAME}</a>
    <nav><a href="/colophon">Colophon</a><a href="{REPO_URL}">GitHub</a></nav>
  </div>
</header>
<main>
{body}
</main>
</body>
</html>
"""
