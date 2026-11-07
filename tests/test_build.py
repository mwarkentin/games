"""Tests for the build scripts and the site they assemble."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import build_index
import pytest
from build_colophon import format_message
from build_sitemap import NAMESPACE, build_sitemap
from common import (
    BASE_URL,
    HOME_APP,
    ICON_SIZES,
    PREVIEW_SIZE,
    PREVIEWS,
    ROOT,
    WORKER_URL,
    app_of,
    extract_meta,
    extract_meta_description,
    game_files,
    generated_pages,
    inject_analytics,
    inject_pwa,
    inject_social,
    music_files,
    own_apps,
    preview_files,
)
from gather_links import extract_urls
from point_preview import origin, point_site, point_text
from publish import current_release, inject_telemetry


def test_extract_urls_trims_punctuation_and_duplicates():
    message = (
        "Built in https://claude.ai/share/abc. See (https://example.com/x),\n"
        "again https://claude.ai/share/abc"
    )
    assert extract_urls(message) == ["https://claude.ai/share/abc", "https://example.com/x"]


def test_extract_meta_description_handles_attribute_order():
    assert extract_meta_description('<meta content="Hi &amp; bye" name="description">') == "Hi & bye"
    assert extract_meta_description("<title>No meta</title>") == ""


def test_format_message_links_urls_and_issue_numbers():
    html = format_message("Fix <b> (#12)\nhttps://example.com/a#3.")
    assert "&lt;b&gt;" in html
    assert '<a href="https://github.com/mwarkentin/games/issues/12">#12</a>' in html
    # The #3 inside the URL stays part of the URL, and the full stop stays outside it.
    assert '<a href="https://example.com/a#3">https://example.com/a#3</a>.' in html


def test_format_message_reflows_wrapped_lines():
    message = (
        "Add a game that does\nsomething useful.\n\n"
        "- first item that\n  wraps\n- second item\n\n"
        "Co-Authored-By: Someone\nClaude-Session: https://claude.ai/code/x"
    )
    assert format_message(message).split("<br>\n") == [
        "Add a game that does something useful.",
        "",
        "- first item that wraps",
        "- second item",
        "",
        "Co-Authored-By: Someone",
        'Claude-Session: <a href="https://claude.ai/code/x">https://claude.ai/code/x</a>',
    ]


def test_build_index_fills_recent_section(monkeypatch):
    monkeypatch.setattr(build_index, "RECENT_LIMIT", 1)
    readme = "# Games\n\n<!-- recently starts -->\n<!-- recently stops -->\n\n## All\n"
    games = [
        {"slug": "old", "filename": "old.html", "title": "Old", "url": "/old", "changelog": "/changelog/old",
         "created": "2026-01-01T10:00:00-05:00", "updated": "2026-03-01T10:00:00-05:00"},
        {"slug": "new", "filename": "new.html", "title": "New", "url": "/new", "changelog": None,
         "created": "2026-02-01T10:00:00-05:00", "updated": "2026-02-01T10:00:00-05:00"},
    ]
    page = build_index.build_index(readme, games)
    assert page.index("Recently added") < page.index("Recently updated") < page.index("<h2>All</h2>")
    added, updated = page.split("Recently updated")
    assert '<a href="/new">New</a>' in added
    assert '<a class="muted" href="/colophon#new.html">Feb 1, 2026</a>' in added
    assert '<a href="/old">Old</a>' in updated
    # Dates lead to what changed: the changelog, or the colophon without one.
    assert '<a class="muted" href="/changelog/old">Mar 1, 2026</a>' in updated


def test_build_sitemap_lists_games_and_generated_pages():
    games = [
        {"url": "/b-game", "updated": "2026-10-01T09:00:00-04:00"},
        {"url": "/a-game", "updated": "2026-10-20T09:00:00-04:00"},
    ]
    root = ET.fromstring(build_sitemap(games, {"/changelog/a-game": "2026-10-19"}))
    entries = {
        url.findtext(f"{{{NAMESPACE}}}loc"): url.findtext(f"{{{NAMESPACE}}}lastmod")
        for url in root
    }
    assert list(entries) == [
        f"{BASE_URL}/",
        f"{BASE_URL}/a-game",
        f"{BASE_URL}/b-game",
        f"{BASE_URL}/changelog/a-game",
        f"{BASE_URL}/colophon",
    ]
    assert entries[f"{BASE_URL}/"] == "2026-10-20"
    assert entries[f"{BASE_URL}/changelog/a-game"] == "2026-10-19"
    assert entries[f"{BASE_URL}/b-game"] == "2026-10-01"


def test_site_contains_only_publishable_files(site_dir):
    published = {path.relative_to(site_dir).as_posix() for path in site_dir.rglob("*") if path.is_file()}
    apps = [*own_apps(), HOME_APP]
    expected = {
        *game_files(),
        *generated_pages(),
        "games.json",
        "sitemap.xml",
        "robots.txt",
        "sw.js",
        *(f"manifests/{app}.webmanifest" for app in apps),
        *(f"icons/{app}-{size}.png" for app in apps for size in ICON_SIZES),
        *music_files(),
        *preview_files(),
    }
    assert published == expected, "the site should hold the games, generated pages, their apps, music and previews only"


def test_inject_telemetry_goes_before_head_end_once():
    page = "<html><HEAD><title>t</title></HEAD><body></head></body>"
    injected = inject_telemetry(page, "run();\n", "games@abc")
    assert injected == (
        '<html><HEAD><title>t</title><script data-telemetry data-release="games@abc">\nrun();\n</script>\n'
        "</HEAD><body></head></body>"
    )
    assert inject_telemetry(injected, "run();", "games@abc") == injected
    no_head = inject_telemetry("<p>no head", "run();", "")
    assert no_head == '<p>no head\n<script data-telemetry data-release="">\nrun();\n</script>\n'


def test_games_are_published_with_only_previews_telemetry_analytics_and_app_links_added_and_colophon_entries(site_dir):
    colophon = (site_dir / "colophon.html").read_text("utf-8")
    telemetry = (ROOT / "telemetry.js").read_text("utf-8")
    for filename in game_files():
        source = (ROOT / filename).read_text("utf-8")
        published = (site_dir / filename).read_text("utf-8")
        slug = filename.removesuffix(".html")
        app = app_of(source, slug)
        social = inject_social(source, app, f"/{slug}")
        assert published == inject_pwa(inject_analytics(inject_telemetry(social, telemetry, current_release())), app)
        assert (
            published.index('<meta property="og:title"')
            < published.index("<script data-telemetry")
            < published.index("<script data-analytics")
            < published.index("<script data-pwa")
            < published.index("</head>")
        )
        assert f'id="{filename}"' in colophon


def test_generated_pages_get_analytics_but_not_telemetry(site_dir):
    for filename in generated_pages():
        page = (site_dir / filename).read_text("utf-8")
        assert page.count("<script data-analytics>") == 1
        assert page.index("<script data-analytics>") < page.index("</head>")
        assert "<script data-telemetry" not in page


def test_inject_pwa_links_the_app_and_registers_the_worker_once():
    page = "<html><head><title>t</title></head><body></body></html>"
    injected = inject_pwa(page, "foo")
    head = injected[: injected.index("</head>")]
    assert '<link rel="manifest" href="/manifests/foo.webmanifest">' in head
    assert '<link rel="apple-touch-icon" href="/icons/foo-180.png">' in head
    assert "navigator.serviceWorker.register('/sw.js')" in head
    assert inject_pwa(injected, "foo") == injected


def test_inject_social_uses_the_preview_or_falls_back_to_the_icon(tmp_path):
    page = '<html><head><title>Foo &amp; Bar</title><meta name="description" content="A &quot;quoted&quot; game."></head></html>'
    (tmp_path / PREVIEWS).mkdir()
    (tmp_path / PREVIEWS / "foo.jpg").write_bytes(b"")

    with_preview = inject_social(page, "foo", "/foo", tmp_path)
    head = with_preview[: with_preview.index("</head>")]
    assert extract_meta(head, "twitter:card") == "summary_large_image"
    assert f'<meta property="og:image" content="{BASE_URL}/previews/foo.jpg">' in head
    assert '<meta property="og:image:width" content="1200">' in head
    assert f'<meta property="og:url" content="{BASE_URL}/foo">' in head
    assert '<meta property="og:title" content="Foo &amp; Bar">' in head
    assert '<meta property="og:description" content="A &quot;quoted&quot; game.">' in head
    assert inject_social(with_preview, "foo", "/foo", tmp_path) == with_preview

    without = inject_social(page, "bar", "/bar", tmp_path)
    assert extract_meta(without, "twitter:card") == "summary"
    assert f'<meta property="og:image" content="{BASE_URL}/icons/bar-512.png">' in without


def test_inject_social_leaves_a_page_with_its_own_tags_alone():
    page = '<html><head><meta property="og:title" content="Mine"></head></html>'
    assert inject_social(page, "foo", "/foo") == page
    no_description = inject_social("<html><head><title>t</title></head></html>", "foo", "/foo")
    assert "og:description" not in no_description


def test_every_page_has_a_link_preview_whose_image_is_published(site_dir):
    pages = {f"/{name.removesuffix('.html')}": name for name in game_files()}
    pages.update({path: name for name, path in generated_pages().items()})
    for path, filename in pages.items():
        head = (site_dir / filename).read_text("utf-8").split("</head>")[0]
        tags = dict(re.findall(r'<meta property="(og:[a-z:_]+)" content="([^"]*)">', head))
        assert tags["og:url"] == f"{BASE_URL}{path}", filename
        assert tags["og:title"], filename
        assert tags["og:image"].startswith(f"{BASE_URL}/"), filename
        assert (site_dir / tags["og:image"].removeprefix(f"{BASE_URL}/")).is_file(), filename


def jpeg_size(data: bytes) -> tuple[int, int]:
    """Width and height from a JPEG's start-of-frame marker."""
    i = 2
    while i < len(data):
        marker, length = data[i + 1], int.from_bytes(data[i + 2 : i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            return int.from_bytes(data[i + 7 : i + 9], "big"), int.from_bytes(data[i + 5 : i + 7], "big")
        i += 2 + length
    raise ValueError("no start-of-frame marker")


def test_previews_are_1200x630_jpegs_small_enough_for_whatsapp():
    # WhatsApp shows no image for previews over about 300 KB.
    for name in preview_files():
        data = (ROOT / name).read_bytes()
        assert data[:2] == b"\xff\xd8", f"{name} isn't a JPEG"
        assert jpeg_size(data) == PREVIEW_SIZE, name
        assert len(data) < 300_000, f"{name} is {len(data) // 1000} KB"


def test_point_text_moves_site_and_worker_urls_to_the_preview():
    site, worker = "https://pr-7-games-preview.example.workers.dev", "https://pr-7-games-leaderboard.example.workers.dev"
    text = (
        f'<meta property="og:url" content="{BASE_URL}/war">'
        f"<a href=\"{BASE_URL}\">home</a>"
        f"const ROOMS_URL = '{WORKER_URL}';"
        f"<a href=\"{BASE_URL}.evil.example/\">not ours</a>"
        "if (location.hostname !== 'games.michaelwarkentin.com') return;"
    )
    pointed = point_text(text, site, worker)
    assert f'content="{site}/war"' in pointed
    assert f'href="{site}">home' in pointed
    assert f"ROOMS_URL = '{worker}'" in pointed
    # A longer hostname, and the bare hostname telemetry and analytics check, stay put.
    assert f"{BASE_URL}.evil.example/" in pointed
    assert "location.hostname !== 'games.michaelwarkentin.com'" in pointed
    # Without a Worker Preview, the pages keep production's Worker.
    assert f"ROOMS_URL = '{WORKER_URL}'" in point_text(text, site)


def test_point_site_leaves_no_production_url_in_the_preview(site_dir, tmp_path):
    preview = tmp_path / "site"
    shutil.copytree(site_dir, preview)
    site, worker = "https://pr-7-games-preview.example.workers.dev", "https://pr-7-games-leaderboard.example.workers.dev"
    changed = {path.relative_to(preview).as_posix() for path in point_site(preview, site, worker)}
    assert {"index.html", "war.html", "sitemap.xml", "robots.txt"} <= changed
    for path in preview.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".js", ".json", ".txt", ".xml", ".webmanifest"}:
            text = path.read_text("utf-8")
            assert BASE_URL not in text, path
            assert WORKER_URL not in text, path
    war = (preview / "war.html").read_text("utf-8")
    assert f"const ROOMS_URL = '{worker}';" in war
    assert f'<meta property="og:url" content="{site}/war">' in war
    # Images and music are copied untouched.
    for name in [*music_files(), *preview_files()]:
        assert (preview / name).read_bytes() == (ROOT / name).read_bytes()
    # The site it came from is left as it was.
    assert BASE_URL in (site_dir / "index.html").read_text("utf-8")


def test_point_preview_takes_only_https_origins():
    assert origin("https://pr-1-games-preview.mwarkentin.workers.dev/") == "https://pr-1-games-preview.mwarkentin.workers.dev"
    for bad in ["http://example.com", "https://example.com/path", "example.com", "https://ex ample.com"]:
        with pytest.raises(argparse.ArgumentTypeError):
            origin(bad)


def test_point_site_adds_a_banner_to_generated_pages_only(site_dir, tmp_path):
    preview = tmp_path / "site"
    shutil.copytree(site_dir, preview)
    link = "https://github.com/mwarkentin/games/pull/7"
    point_site(preview, "https://pr-7-games-preview.example.workers.dev", banner="Preview of #7 <x>", banner_link=link)
    for name in generated_pages():
        text = (preview / name).read_text("utf-8")
        assert text.count('class="preview-banner"') == 1
        assert f'<a href="{link}">Preview of #7 &lt;x&gt;</a>' in text
        assert text.index("<body") < text.index('class="preview-banner"')
    for filename in game_files():
        assert "preview-banner" not in (preview / filename).read_text("utf-8")


def test_point_preview_runs_without_a_worker_preview(site_dir, tmp_path):
    """As the workflow runs it for a pull request that doesn't touch worker/."""
    preview = tmp_path / "site"
    shutil.copytree(site_dir, preview)
    site = "https://pr-7-games-preview.example.workers.dev"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "point_preview.py"), str(preview), "--site", site,
         "--banner", "Preview of #7", "--banner-link", "https://github.com/mwarkentin/games/pull/7"],
        check=True,
    )
    war = (preview / "war.html").read_text("utf-8")
    assert f"const ROOMS_URL = '{WORKER_URL}';" in war
    assert f'content="{site}/war"' in war
    assert "Preview of #7" in (preview / "index.html").read_text("utf-8")


def test_point_site_prefixes_every_page_title_but_not_link_previews(site_dir, tmp_path):
    preview = tmp_path / "site"
    shutil.copytree(site_dir, preview)
    point_site(preview, "https://pr-7-games-preview.example.workers.dev", title_prefix="PR 7 · ")
    for name in [*game_files(), *generated_pages()]:
        before = (site_dir / name).read_text("utf-8")
        after = (preview / name).read_text("utf-8")
        title = re.search(r"<title>(.*?)</title>", before).group(1)
        assert f"<title>PR 7 · {title}</title>" in after, name
        assert after.count("PR 7 · ") == 1, name
        og_title = re.compile(r'<meta property="og:title" content="([^"]*)"')
        assert og_title.search(after).group(1) == og_title.search(before).group(1)
        assert not og_title.search(after).group(1).startswith("PR 7")
