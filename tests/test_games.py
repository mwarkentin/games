"""Checks every game gets for free. Add tests/test_<game>.py for gameplay."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page

from common import BASE_URL, ROOT, game_files
from page_changes import repeated_no_op_writes

GAMES = game_files()
SCREENS = {"phone": {"width": 375, "height": 740}, "desktop": {"width": 1280, "height": 800}}

# Text-like inputs that iOS zooms into when their font is under 16px.
SMALL_INPUTS_JS = """() => [...document.querySelectorAll('input, textarea, select')]
  .filter(el => !['checkbox', 'radio', 'range', 'color', 'file', 'button',
                  'submit', 'reset', 'image', 'hidden'].includes(el.type))
  .filter(el => el.getClientRects().length > 0)
  .filter(el => parseFloat(getComputedStyle(el).fontSize) < 16)
  .map(el => el.id || el.name || el.outerHTML.slice(0, 80))"""

CDN_URL = re.compile(r"https://(?:cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|unpkg\.com)/[^\s\"'`)]+")
PINNED_CDN_URL = re.compile(
    r"https://(?:"
    r"cdn\.jsdelivr\.net/npm/(?:@[^/]+/)?[^/@]+@\d+\.\d+\.\d+"
    r"|cdn\.jsdelivr\.net/gh/[^/]+/[^/@]+@[^/]+"
    r"|unpkg\.com/(?:@[^/]+/)?[^/@]+@\d+\.\d+\.\d+"
    r"|cdnjs\.cloudflare\.com/ajax/libs/[^/]+/\d+\.\d+\.\d+"
    r")(?:[-+][\w.]+)?(?:/|$)"
)


def test_there_are_games():
    assert GAMES, "no games found"


@pytest.mark.parametrize("filename", GAMES)
def test_game_has_required_metadata(filename):
    text = (ROOT / filename).read_text("utf-8")
    assert re.search(r"<title>\s*\S", text), "missing <title>"
    assert re.search(r'<meta\s+name="viewport"', text), "missing viewport meta tag"
    assert re.search(r'<meta\s+name="description"\s+content="\s*\S', text), (
        "missing <meta name=\"description\" content=\"...\">"
    )


@pytest.mark.parametrize("filename", GAMES)
def test_game_pins_cdn_versions(filename):
    text = (ROOT / filename).read_text("utf-8")
    unpinned = [url for url in CDN_URL.findall(text) if not PINNED_CDN_URL.match(url)]
    assert unpinned == [], "CDN URLs need an exact version"


@pytest.mark.parametrize("filename", GAMES)
def test_game_is_listed_in_readme(filename):
    readme = (ROOT / "README.md").read_text("utf-8")
    targets = {
        target.removeprefix(BASE_URL).strip("/").removesuffix(".html")
        for target in re.findall(r"\]\(([^)\s]+)\)", readme)
    }
    assert filename.removesuffix(".html") in targets, "add a link to README.md"


@pytest.mark.parametrize("screen", SCREENS)
@pytest.mark.parametrize("filename", GAMES)
def test_game_loads_cleanly(page: Page, site_url, errors, filename, screen):
    size = SCREENS[screen]
    page.set_viewport_size(size)
    page.goto(f"{site_url}/{filename.removesuffix('.html')}", wait_until="networkidle")

    assert errors == [], "console errors or failed requests"
    assert page.evaluate("document.documentElement.scrollWidth") <= size["width"], (
        "page scrolls sideways"
    )
    assert page.evaluate(SMALL_INPUTS_JS) == [], "inputs under 16px make iOS zoom"


@pytest.mark.parametrize("filename", GAMES)
def test_game_doesnt_keep_rewriting_its_page(page: Page, site_url, filename):
    page.set_viewport_size(SCREENS["phone"])
    page.goto(f"{site_url}/{filename.removesuffix('.html')}", wait_until="networkidle")
    assert repeated_no_op_writes(page) == {}, "only write what changed (see tests/page_changes.py)"


@pytest.mark.parametrize("path", ["/", "/colophon"])
def test_generated_page_loads(page: Page, site_url, errors, path):
    page.set_viewport_size(SCREENS["phone"])
    page.goto(f"{site_url}{path}", wait_until="networkidle")
    assert errors == []
    assert page.evaluate("document.documentElement.scrollWidth") <= SCREENS["phone"]["width"]
