"""Home-screen apps: each page's manifest and icons, and the offline copies sw.js keeps.

Every other test blocks service workers (see conftest.py); the browser tests
here allow them. The worker's own requests ignore context.set_offline, so
"offline" here means every request to the site is aborted by context.route,
which does see them.
"""

from __future__ import annotations

import base64
import json
import re
import struct

import pytest
from playwright.sync_api import Browser, BrowserContext, Page

from build_pwa import build_service_worker
from common import GENERATED_PAGES, HOME_APP, ICON_SIZES, ROOT, extract_meta, extract_title, game_files
from render_icons import render

GAMES = game_files()
APPS = [*(filename.removesuffix(".html") for filename in GAMES), HOME_APP]
PAGES = [*GENERATED_PAGES.values(), *(f"/{filename.removesuffix('.html')}" for filename in GAMES)]
# iOS cuts off longer labels under a Home Screen icon.
SHORT_NAME_LIMIT = 12

# The mean difference per channel (0-255) between two images, drawn on canvases.
IMAGE_DIFFERENCE_JS = """async ([a, b]) => {
  const load = (src) => new Promise((resolve, reject) => {
    const img = new Image(); img.onload = () => resolve(img); img.onerror = reject; img.src = src;
  });
  const pixels = (img) => {
    const canvas = document.createElement('canvas');
    canvas.width = img.width; canvas.height = img.height;
    const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0);
    return ctx.getImageData(0, 0, img.width, img.height).data;
  };
  const [p, q] = (await Promise.all([load(a), load(b)])).map(pixels);
  if (p.length !== q.length) return 255;
  let total = 0;
  for (let i = 0; i < p.length; i++) total += Math.abs(p[i] - q[i]);
  return total / p.length;
}"""


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])


def png_url(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


@pytest.mark.parametrize("app", APPS)
def test_every_app_has_its_own_icons(app):
    assert (ROOT / "icons" / f"{app}.svg").exists(), f"draw icons/{app}.svg (see scripts/render_icons.py)"
    for size in ICON_SIZES:
        png = ROOT / "icons" / f"{app}-{size}.png"
        assert png.exists(), "run scripts/render_icons.py"
        assert png_size(png.read_bytes()) == (size, size)


@pytest.mark.parametrize("app", APPS)
def test_icons_match_their_svg(page: Page, app):
    svg = (ROOT / "icons" / f"{app}.svg").read_text("utf-8")
    for size in ICON_SIZES:
        fresh = render(page, svg, size)
        committed = (ROOT / "icons" / f"{app}-{size}.png").read_bytes()
        page.set_content("")
        difference = page.evaluate(IMAGE_DIFFERENCE_JS, [png_url(fresh), png_url(committed)])
        assert difference < 1, f"icons/{app}.svg changed: run scripts/render_icons.py"


@pytest.mark.parametrize("filename", GAMES)
def test_each_game_is_an_app_of_its_own(site_dir, filename):
    slug = filename.removesuffix(".html")
    source = (ROOT / filename).read_text("utf-8")
    manifest = json.loads((site_dir / "manifests" / f"{slug}.webmanifest").read_text("utf-8"))

    assert manifest["id"] == manifest["start_url"] == manifest["scope"] == f"/{slug}"
    assert manifest["name"] == extract_title(source, slug)
    assert manifest["display"] == "standalone"
    assert len(manifest["short_name"]) <= SHORT_NAME_LIMIT, (
        'add a shorter <meta name="apple-mobile-web-app-title" content="..."> for the Home Screen'
    )
    assert extract_meta(source, "theme-color"), 'add <meta name="theme-color" content="..."> to the <head>'
    assert manifest["theme_color"] == extract_meta(source, "theme-color")
    for icon in manifest["icons"]:
        assert (site_dir / icon["src"].lstrip("/")).exists()

    page = (site_dir / filename).read_text("utf-8")
    head = page[: page.lower().index("</head>")]
    assert head.count('rel="manifest"') == 1
    assert f'<link rel="manifest" href="/manifests/{slug}.webmanifest">' in head
    assert f'<link rel="apple-touch-icon" href="/icons/{slug}-180.png">' in head
    assert head.count("<script data-pwa>") == 1


@pytest.mark.parametrize("filename", GENERATED_PAGES)
def test_generated_pages_belong_to_the_home_app(site_dir, filename):
    manifest = json.loads((site_dir / "manifests" / f"{HOME_APP}.webmanifest").read_text("utf-8"))
    assert manifest["start_url"] == manifest["scope"] == "/"
    assert len(manifest["short_name"]) <= SHORT_NAME_LIMIT
    page = (site_dir / filename).read_text("utf-8")
    assert f'<link rel="manifest" href="/manifests/{HOME_APP}.webmanifest">' in page
    assert page.count("<script data-pwa>") == 1


def test_service_worker_keeps_every_page(site_dir):
    worker = (site_dir / "sw.js").read_text("utf-8")
    pages = json.loads(re.search(r"^const PAGES = (.*);$", worker, re.MULTILINE).group(1))
    assert sorted(pages) == sorted(PAGES)
    assert re.search(r'^const VERSION = "[0-9a-f]{16}";$', worker, re.MULTILINE)


def test_build_service_worker_fills_in_version_and_pages():
    template = "const VERSION = 'dev';\nconst PAGES = [];\nconst PAGE_CACHE = `pages-${VERSION}`;\n"
    assert build_service_worker(template, ["/", "/a"], "abc") == (
        'const VERSION = "abc";\nconst PAGES = ["/", "/a"];\nconst PAGE_CACHE = `pages-${VERSION}`;\n'
    )


@pytest.fixture
def sw_context(browser: Browser, browser_context_args) -> BrowserContext:
    """A context that lets sw.js install and answer."""
    context = browser.new_context(**{**browser_context_args, "service_workers": "allow"})
    yield context
    context.close()


def install(page: Page, url: str) -> None:
    page.goto(url)
    page.wait_for_function("navigator.serviceWorker.controller !== null")


def go_offline(context: BrowserContext, site_url: str) -> None:
    context.route(f"{site_url}/**", lambda route: route.abort("internetdisconnected"))


def test_every_page_opens_offline_after_visiting_one(sw_context: BrowserContext, site_url):
    page = sw_context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    install(page, f"{site_url}/letterfield")
    go_offline(sw_context, site_url)

    titles = {"/": "games.michaelwarkentin.com", "/colophon": "Colophon · games.michaelwarkentin.com"}
    titles |= {f"/{f.removesuffix('.html')}": extract_title((ROOT / f).read_text("utf-8"), f) for f in GAMES}
    for path, title in titles.items():
        response = page.goto(f"{site_url}{path}")
        assert response.from_service_worker, path
        assert page.title() == title, path
    # Invite links, .html addresses and the home page's own name are the same pages.
    for path, same_as in {"/war?room=ABCD": "/war", "/letterfield.html": "/letterfield", "/index.html": "/"}.items():
        page.goto(f"{site_url}{path}")
        assert page.title() == titles[same_as], path
    assert errors == []


def test_pages_come_from_the_network_first_and_update_the_offline_copy(sw_context: BrowserContext, site_url):
    page = sw_context.new_page()
    install(page, f"{site_url}/letterfield")

    newer = "<!DOCTYPE html><title>Letterfield, redeployed</title>"
    sw_context.route(f"{site_url}/letterfield", lambda route: route.fulfill(body=newer, content_type="text/html"))
    page.goto(f"{site_url}/letterfield")
    assert page.title() == "Letterfield, redeployed"

    sw_context.unroute(f"{site_url}/letterfield")
    # The copy is saved alongside the page; wait until it lands.
    page.wait_for_function(
        """async () => {
          const name = (await caches.keys()).find((key) => key.startsWith('pages-'));
          const copy = await (await caches.open(name)).match('/letterfield');
          return (await copy.text()).includes('redeployed');
        }"""
    )
    go_offline(sw_context, site_url)
    page.goto(f"{site_url}/letterfield")
    assert page.title() == "Letterfield, redeployed"


def test_service_worker_leaves_other_requests_alone(sw_context: BrowserContext, site_url):
    page = sw_context.new_page()
    install(page, f"{site_url}/letterfield")
    go_offline(sw_context, site_url)
    with pytest.raises(Exception, match="ERR_INTERNET_DISCONNECTED"):
        page.goto(f"{site_url}/robots.txt")
