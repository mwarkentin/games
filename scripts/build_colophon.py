#!/usr/bin/env python3
"""Build colophon.html: each game's description and commit history.

Commit messages are shown in full with their URLs linked, so a game's entry
leads back to the chat or agent session that produced it. Games are ordered
by their latest commit, newest first, and /colophon#<file>.html opens that
game's history.

Adapted from build_colophon.py in https://github.com/simonw/tools by Simon
Willison, licensed under the Apache License 2.0 (see LICENSE). Changed:
shares page chrome with the index, lists every game from games.json
(including ones not committed yet), links URLs and #123 references in a
single pass, and writes into the site directory.

Usage: build_colophon.py [SITE_DIR]
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import REPO_URL, ROOT, SITE_NAME, format_date, parse_date, render_page
from gather_links import URL_TRAILING_PUNCTUATION

TOKEN_PATTERN = re.compile(r"(https?://\S+)|(?<![\w/&])#(\d+)\b")
# Lines that start a new line even inside a paragraph: list items and trailers.
LINE_START_PATTERN = re.compile(r"([-*] |\d+\. |[A-Z][\w-]*: )")

EXTRA_CSS = """
.game { border-bottom: 1px solid var(--rule); padding-bottom: 1rem; }
.game h2 { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 0.6rem; }
.game h2 .anchor, .game h2 .source { font-size: 0.85rem; font-weight: normal; }
.game h2 .anchor { color: var(--muted); text-decoration: none; }
summary { cursor: pointer; color: var(--muted); }
.commit {
  background: var(--panel);
  border-left: 3px solid var(--link);
  border-radius: 4px;
  padding: 0.6rem 0.8rem;
  margin: 0.6rem 0;
  overflow-wrap: anywhere;
}
.commit .meta { font-size: 0.85rem; }
.commit .message { margin-top: 0.3rem; }
"""

OPEN_FROM_HASH = """<script type="module">
const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
const details = target?.querySelector("details");
if (details) details.open = true;
</script>"""


def unwrap(message: str) -> str:
    """Join hard-wrapped lines so paragraphs reflow on narrow screens."""
    lines: list[str] = []
    for line in message.split("\n"):
        if lines and lines[-1] and line.strip() and not LINE_START_PATTERN.match(line):
            lines[-1] += " " + line.strip()
        else:
            lines.append(line)
    return "\n".join(lines)


def format_message(message: str) -> str:
    """Escape a commit message, link its URLs and #123 references."""
    message = unwrap(message)
    parts = []
    position = 0
    for match in TOKEN_PATTERN.finditer(message):
        parts.append(html.escape(message[position : match.start()]))
        if match.group(1):
            url = match.group(1).rstrip(URL_TRAILING_PUNCTUATION)
            trailing = match.group(1)[len(url) :]
            parts.append(
                f'<a href="{html.escape(url)}">{html.escape(url)}</a>{html.escape(trailing)}'
            )
        else:
            number = match.group(2)
            parts.append(f'<a href="{REPO_URL}/issues/{number}">#{number}</a>')
        position = match.end()
    parts.append(html.escape(message[position:]))
    return "".join(parts).replace("\n", "<br>\n")


def render_commit(commit: dict) -> str:
    short = commit["hash"][:7]
    when = parse_date(commit["date"])
    date = f' <span class="muted">{format_date(when)}</span>' if when else ""
    return f"""<div class="commit">
  <div class="meta"><a href="{REPO_URL}/commit/{commit["hash"]}"><code>{short}</code></a>{date}</div>
  <div class="message">{format_message(commit["message"])}</div>
</div>"""


def render_history(commits: list[dict]) -> str:
    if not commits:
        return '<p class="muted">Not committed yet.</p>'
    summary = f"{len(commits)} commit{'s' if len(commits) != 1 else ''}"
    history = "\n".join(render_commit(commit) for commit in reversed(commits))
    return f"<details>\n<summary>{summary}</summary>\n{history}\n</details>"


def build_colophon(pages: dict, games: list[dict]) -> str:
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    # Most recently changed first; games with no commits yet go last.
    ordered = sorted(games, key=lambda game: parse_date(game.get("updated")) or oldest, reverse=True)

    articles = []
    for game in ordered:
        filename = game["filename"]
        description = game.get("description")
        commits = pages.get(filename, {}).get("commits", [])
        articles.append(f"""<article class="game" id="{filename}">
<h2><a class="anchor" href="#{filename}">#</a> <a href="{game["url"]}">{html.escape(game["title"])}</a> <a class="source" href="{REPO_URL}/blob/main/{filename}">source</a></h2>
{f"<p>{html.escape(description)}</p>" if description else ""}
{render_history(commits)}
</article>""")

    body = f"""<h1>Colophon</h1>
<p>Every game on {SITE_NAME} is a single HTML file, mostly written with help
from LLMs. Below is each game's commit history; the commit messages link to
the chat or agent session behind each change.</p>
<p class="muted">{len(articles)} game{"s" if len(articles) != 1 else ""}, most recently changed first.</p>
{chr(10).join(articles)}
{OPEN_FROM_HASH}"""
    return render_page(f"Colophon · {SITE_NAME}", body, extra_css=EXTRA_CSS)


def main() -> None:
    site_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    pages = json.loads((ROOT / "gathered_links.json").read_text("utf-8"))["pages"]
    games = json.loads((ROOT / "games.json").read_text("utf-8"))
    (site_dir / "colophon.html").write_text(build_colophon(pages, games), "utf-8")
    print("Built colophon.html")


if __name__ == "__main__":
    main()
