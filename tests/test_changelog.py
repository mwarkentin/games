"""Each game's changelog: changelog/<app>.md, built into /changelog/<app>."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from build_changelog import ChangelogError, build_changelog, parse_changelog, read_changelog
from common import CHANGELOGS, changelog_apps, own_apps

GAME = {"slug": "foo", "filename": "foo.html", "title": "Foo & Bar", "url": "/foo"}


def test_every_game_has_a_changelog_and_every_changelog_a_game():
    assert changelog_apps() == sorted(own_apps()), f"add {CHANGELOGS}/<game>.md for each game, and only for games"


@pytest.mark.parametrize("app", changelog_apps())
def test_changelog_is_well_formed_and_not_from_the_future(app):
    days = read_changelog(app)
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    assert days[0][0] <= tomorrow, "the newest day is in the future"


def test_parse_changelog_reads_days_newest_first():
    text = "## 2026-11-06\n\n- Newer.\n- Also.\n\n## 2026-10-28\n\nOlder, as a paragraph.\n"
    assert parse_changelog(text) == [
        (date(2026, 11, 6), "- Newer.\n- Also."),
        (date(2026, 10, 28), "Older, as a paragraph."),
    ]


@pytest.mark.parametrize(
    "text, problem",
    [
        ("", "no days"),
        ("- An entry without a day.\n", "no days"),
        ("# Foo\n\n## 2026-11-06\n\n- Hi.\n", "text before the first day"),
        ("## Nov 6, 2026\n\n- Hi.\n", "isn't a date"),
        ("## 2026-11-06\n\n## 2026-11-05\n\n- Hi.\n", "nothing under ## 2026-11-06"),
        ("## 2026-11-05\n\n- Hi.\n\n## 2026-11-06\n\n- Hi.\n", "newest first"),
        ("## 2026-11-05\n\n- Hi.\n\n## 2026-11-05\n\n- Hi.\n", "one heading a day"),
    ],
)
def test_parse_changelog_refuses_mistakes(text, problem):
    with pytest.raises(ChangelogError, match=re.escape(problem)):
        parse_changelog(text)


def test_build_changelog_lists_days_and_links_the_game_and_its_history():
    page = build_changelog(GAME, parse_changelog("## 2026-11-06\n\n- Music, *at last*.\n\n## 2026-10-28\n\n- Here.\n"))
    main = page[page.index("<main>") : page.index("</main>")]
    assert "<title>Foo &amp; Bar changelog · games.michaelwarkentin.com</title>" in page
    assert '<meta property="og:url" content="https://games.michaelwarkentin.com/changelog/foo">' in page
    assert "<h1>Foo &amp; Bar changelog</h1>" in main
    assert '<a href="/foo">Play Foo &amp; Bar</a>' in main
    assert '<a href="/colophon#foo.html">' in main
    assert main.index('id="2026-11-06"') < main.index('id="2026-10-28"')
    assert '<a href="#2026-11-06"><time datetime="2026-11-06">Nov 6, 2026</time></a>' in main
    assert "<li>Music, <em>at last</em>.</li>" in main


def test_site_has_a_changelog_for_every_game_and_links_to_them(site_dir):
    games = json.loads((site_dir / "games.json").read_text("utf-8"))
    colophon = (site_dir / "colophon.html").read_text("utf-8")
    for game in games:
        # Letterfield's survey log and timelapse are part of Letterfield, and share its changelog.
        app = "letterfield" if game["slug"] in ("letterfield-log", "letterfield-timelapse") else game["slug"]
        assert game["changelog"] == f"/changelog/{app}"
        assert f'<a class="source" href="/changelog/{app}">changelog</a>' in colophon
    for app in changelog_apps():
        page = (site_dir / CHANGELOGS / f"{app}.html").read_text("utf-8")
        newest = read_changelog(app)[0][0].isoformat()
        assert f'<section class="day" id="{newest}">' in page


def test_recent_dates_on_the_home_page_open_the_changelog(page, site_url, errors):
    page.goto(site_url)
    link = page.locator(".recent a.muted").first
    href = link.get_attribute("href")
    assert href.startswith("/changelog/")
    link.click()
    page.wait_for_url(f"{site_url}{href}")
    assert page.locator("h1").inner_text().endswith(" changelog")
    assert page.locator("section.day").count() >= 1
    assert errors == []
