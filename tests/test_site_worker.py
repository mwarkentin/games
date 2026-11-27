"""The site as the games-site Worker serves it: _site/ through `wrangler dev`.

The live site is moving from GitHub Pages to Workers static assets (see
site/README.md). Every other test serves _site/ with Python's own server,
which acts like Pages; these run the real asset rules of site/wrangler.toml
(html_handling, not_found_handling and the built _headers) in wrangler's
local runtime, and check the addresses, redirects, 404s and caching players
and sw.js rely on, and that the service worker installs and keeps the pages
offline as it does on Pages.

They need Node 22 and npx, which fetches wrangler from registry.npmjs.org
the first time. Without npx they're skipped; a sandbox that can't reach the
registry fails them at start-up, saying so.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import tomllib
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Browser

from build_headers import FRESH, LONG, SHORT, header_rules, page_paths
from common import ROOT, extract_title, game_files, module_urls, music_files
from fake_leaderboard import stand_in_for_worker

WRANGLER = "wrangler@4.151.0"  # the version every workflow runs
START_SECONDS = 180  # the first run downloads wrangler


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def worker_url(site_dir, tmp_path_factory):
    """The built site served by site/wrangler.toml's rules, at a local address."""
    if shutil.which("npx") is None:
        pytest.skip("needs npx (Node 22) to run wrangler")
    config = (ROOT / "site" / "wrangler.toml").read_text("utf-8")
    assert 'directory = "../_site"' in config, "site/wrangler.toml should serve ../_site"
    # The same rules, pointed at this run's build of the site.
    work = tmp_path_factory.mktemp("site-worker")
    (work / "wrangler.toml").write_text(
        config.replace('directory = "../_site"', f"directory = {json.dumps(str(site_dir))}"), "utf-8"
    )
    # Each xdist worker runs its own, so each needs its own ports, its inspector's too.
    port, inspector = free_port(), free_port()
    log = (work / "wrangler.log").open("w")
    process = subprocess.Popen(
        ["npx", "--yes", WRANGLER, "dev", "--ip", "127.0.0.1", "--port", str(port), "--inspector-port", str(inspector)]
        + ["--log-level", "warn"],
        cwd=work,
        env={**os.environ, "WRANGLER_SEND_METRICS": "false", "CI": "true"},
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + START_SECONDS
        while True:
            if process.poll() is not None:
                pytest.fail(
                    f"wrangler dev stopped (can npx reach registry.npmjs.org?):\n{(work / 'wrangler.log').read_text()}"
                )
            try:
                get(url, "/sw.js")
                break
            except OSError:
                if time.monotonic() > deadline:
                    pytest.fail(
                        f"wrangler dev didn't answer in {START_SECONDS} s:\n{(work / 'wrangler.log').read_text()}"
                    )
                time.sleep(0.5)
        yield url
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
        log.close()


def get(url: str, path: str, headers: dict[str, str] | None = None) -> http.client.HTTPResponse:
    """One request, redirects not followed; the body is read into .body."""
    connection = http.client.HTTPConnection(urlparse(url).netloc, timeout=10)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    response.body = response.read()
    connection.close()
    return response


def served_path(name: str) -> str:
    """Where a file in _site/ is served: war.html at /war, index.html at /."""
    if name == "index.html":
        return "/"
    return "/" + name.removesuffix(".html") if name.endswith(".html") else "/" + name


def test_every_built_file_is_served(worker_url, site_dir):
    for path in sorted(p for p in site_dir.rglob("*") if p.is_file()):
        name = path.relative_to(site_dir).as_posix()
        if name == "_headers":
            continue
        response = get(worker_url, served_path(name))
        assert response.status == 200, name
        assert response.body == path.read_bytes(), name


def test_pages_are_served_without_html(worker_url):
    for filename in game_files():
        response = get(worker_url, served_path(filename))
        assert response.status == 200
        title = extract_title(response.body.decode(), filename)
        assert title == extract_title((ROOT / filename).read_text("utf-8"), filename), filename
        assert response.getheader("Content-Type") == "text/html; charset=utf-8"


@pytest.mark.parametrize(
    ("path", "location"),
    [
        # Old links and invite links keep working, query strings and all.
        ("/war.html", "/war"),
        ("/war.html?room=ABCD", "/war?room=ABCD"),
        ("/letterfield.html?guild=a-b-c", "/letterfield?guild=a-b-c"),
        ("/war/", "/war"),
        ("/index.html", "/"),
        ("/changelog/war.html", "/changelog/war"),
    ],
)
def test_html_and_trailing_slash_addresses_redirect_to_the_page(worker_url, path, location):
    response = get(worker_url, path)
    assert response.status in (307, 308), path
    assert response.getheader("Location") == location


@pytest.mark.parametrize("path", ["/nope", "/changelog/nope", "/changelog/", "/war/nope", "/js/nope.js", "/_headers"])
def test_unknown_addresses_get_the_not_found_page(worker_url, path):
    response = get(worker_url, path)
    assert response.status == 404
    assert b"Nothing here" in response.body
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"


def test_every_path_gets_its_caching(worker_url):
    examples = {
        **{path: FRESH for path in page_paths()},
        "/sw.js": "no-cache",
        **{url: FRESH for url in module_urls().values()},  # by their hashed address
        "/js/war/core.js": FRESH,  # and plain, for browsers without import maps
        "/manifests/war.webmanifest": SHORT,
        "/games.json": SHORT,
        "/sitemap.xml": SHORT,
        "/robots.txt": SHORT,
        "/icons/war-192.png": LONG,
        "/previews/war.jpg": LONG,
        **{f"/{name}": LONG for name in music_files()},
    }
    for path, cache_control in examples.items():
        response = get(worker_url, path)
        assert response.status == 200, path
        assert response.getheader("Cache-Control") == cache_control, path
        assert response.getheader("Access-Control-Allow-Origin") == "*", path


def test_no_path_is_in_two_rules_for_one_header():
    seen: dict[str, set[str]] = {}
    for path, headers in header_rules():
        for name in headers:
            assert path not in seen.setdefault(name, set()), f"{path} has two {name} rules"
            seen[name].add(path)
    # A splat only for folders no page is in, so it can't join a page's rule.
    splats = [path for path in seen["Cache-Control"] if path.endswith("/*")]
    for page in page_paths():
        assert not any(page.startswith(splat[:-1]) for splat in splats), page


def test_an_unchanged_page_is_a_304(worker_url):
    etag = get(worker_url, "/war").getheader("ETag")
    assert etag
    assert get(worker_url, "/war", {"If-None-Match": etag}).status == 304


def test_the_service_worker_installs_and_keeps_pages_offline(browser: Browser, browser_context_args, worker_url):
    context = browser.new_context(**{**browser_context_args, "service_workers": "allow"})
    stand_in_for_worker(context)
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(f"{worker_url}/letterfield")
        page.wait_for_function("navigator.serviceWorker.controller !== null")
        context.route(f"{worker_url}/**", lambda route: route.abort("internetdisconnected"))
        for filename in ["war.html", "letterfield-log.html"]:
            response = page.goto(f"{worker_url}{served_path(filename)}")
            assert response.from_service_worker, filename
            assert page.title() == extract_title((ROOT / filename).read_text("utf-8"), filename)
        page.goto(f"{worker_url}/changelog/war")
        assert page.title().startswith("War: Slam Edition changelog")
        assert errors == []
    finally:
        context.close()


def test_site_worker_is_never_the_preview_worker():
    site = tomllib.loads((ROOT / "site" / "wrangler.toml").read_text("utf-8"))
    preview = tomllib.loads((ROOT / "preview" / "wrangler.toml").read_text("utf-8"))
    assert site["name"] == "games-site" != preview["name"]
    # Only its custom domain, which OpenTofu owns: no workers.dev address, no Previews, no routes.
    assert site["workers_dev"] is False and site["preview_urls"] is False
    assert "routes" not in site and "previews" not in site
    # Previews serve by the same rules, so each pull request's shows what the live site would.
    assert site["assets"] == preview["assets"]
