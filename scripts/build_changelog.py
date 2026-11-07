#!/usr/bin/env python3
"""Build each game's changelog: changelog/<app>.md into /changelog/<app>.

The colophon shows every commit, written for whoever works on the games. A
changelog is written for players: what changed that they'd notice, a day at
a time, newest first. Each file is a list of days, each a heading with an
ISO date and then Markdown:

    ## 2026-11-06

    - Music from public-domain scores, with its own off switch.

    ## 2026-11-03

    - Seven deck themes to pick from.

A page that belongs to a game (see app_of in common.py) shares that game's
changelog. parse_changelog refuses anything else, so a mistake fails the
build rather than publishing a muddled page.

Usage: build_changelog.py [SITE_DIR]
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

import markdown

from common import CHANGELOGS, ROOT, SITE_NAME, changelog_apps, changelog_path, format_date, render_page

DAY_HEADING = re.compile(r"^## (.*?)\s*$", re.MULTILINE)

EXTRA_CSS = """
.links { margin-top: 0; }
.day { border-bottom: 1px solid var(--rule); padding-bottom: 0.5rem; }
.day h2 a { color: inherit; text-decoration: none; }
.day ul { padding-left: 1.2rem; }
"""


class ChangelogError(ValueError):
    pass


def parse_changelog(text: str) -> list[tuple[date, str]]:
    """Each day's date and Markdown, newest first, as written.

    Raises ChangelogError for text before the first day, a heading that isn't
    an ISO date, a day with nothing under it, or days out of order.
    """
    headings = list(DAY_HEADING.finditer(text))
    if not headings:
        raise ChangelogError("no days: start each with a heading like ## 2026-11-06")
    if text[: headings[0].start()].strip():
        raise ChangelogError("text before the first day")
    days = []
    for heading, following in zip(headings, [*headings[1:], None]):
        try:
            day = date.fromisoformat(heading.group(1))
        except ValueError:
            raise ChangelogError(f"## {heading.group(1)} isn't a date like 2026-11-06") from None
        body = text[heading.end() : following.start() if following else len(text)].strip()
        if not body:
            raise ChangelogError(f"nothing under ## {day}")
        if days and day >= days[-1][0]:
            raise ChangelogError(f"## {day} comes after ## {days[-1][0]}: newest first, one heading a day")
        days.append((day, body))
    return days


def read_changelog(app: str, root: Path = ROOT) -> list[tuple[date, str]]:
    path = root / CHANGELOGS / f"{app}.md"
    try:
        return parse_changelog(path.read_text("utf-8"))
    except ChangelogError as error:
        raise ChangelogError(f"{path.relative_to(root)}: {error}") from None


def build_changelog(game: dict, days: list[tuple[date, str]]) -> str:
    """The changelog page for a game from games.json."""
    title = game["title"]
    sections = "\n".join(
        f'<section class="day" id="{day.isoformat()}">\n'
        f'<h2><a href="#{day.isoformat()}"><time datetime="{day.isoformat()}">{format_date(day)}</time></a></h2>\n'
        f"{markdown.markdown(body, extensions=['extra'])}\n"
        "</section>"
        for day, body in days
    )
    body = f"""<h1>{html.escape(title)} changelog</h1>
<p class="links"><a href="{game["url"]}">Play {html.escape(title)}</a> ·
<a href="/colophon#{game["filename"]}">Every commit, in the colophon</a></p>
<p class="muted">What's changed that you'd notice, newest first.</p>
{sections}"""
    return render_page(
        f"{title} changelog · {SITE_NAME}",
        body,
        path=changelog_path(game["slug"]),
        extra_css=EXTRA_CSS,
        description=f"What's new in {title}, newest first.",
        tip_source="games-changelog",
    )


def publish_changelogs(site_dir: Path, games: list[dict], root: Path = ROOT) -> list[str]:
    """Write a page for every changelog. Returns the apps."""
    by_slug = {game["slug"]: game for game in games}
    (site_dir / CHANGELOGS).mkdir(parents=True, exist_ok=True)
    apps = changelog_apps(root)
    for app in apps:
        if app not in by_slug:
            raise ChangelogError(f"{CHANGELOGS}/{app}.md: there's no game called {app}")
        page = build_changelog(by_slug[app], read_changelog(app, root))
        (site_dir / CHANGELOGS / f"{app}.html").write_text(page, "utf-8")
    return apps


def main() -> None:
    site_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    games = json.loads((ROOT / "games.json").read_text("utf-8"))
    apps = publish_changelogs(site_dir, games)
    print(f"Built {len(apps)} changelogs")


if __name__ == "__main__":
    main()
