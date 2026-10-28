"""Shared fixtures: build the site once, then serve it like GitHub Pages does."""

from __future__ import annotations

import functools
import http.server
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from common import ROOT


@pytest.fixture(scope="session")
def site_dir(tmp_path_factory) -> Path:
    """The site exactly as build.sh assembles it for deploy."""
    out = tmp_path_factory.mktemp("site")
    subprocess.run(
        ["bash", "build.sh"],
        cwd=ROOT,
        env={**os.environ, "SITE_DIR": str(out), "PYTHON": sys.executable},
        check=True,
    )
    return out


class PagesHandler(http.server.SimpleHTTPRequestHandler):
    """Serves /foo from foo.html, as GitHub Pages does, without request logs."""

    def translate_path(self, path: str) -> str:
        fs_path = super().translate_path(path)
        if not os.path.exists(fs_path) and os.path.exists(fs_path + ".html"):
            return fs_path + ".html"
        return fs_path

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="session")
def site_url(site_dir):
    handler = functools.partial(PagesHandler, directory=str(site_dir))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Fixed locale and time zone, so dates render the same everywhere."""
    return {**browser_context_args, "locale": "en-US", "timezone_id": "America/Toronto"}


@pytest.fixture
def errors(page) -> list[str]:
    """Console errors, uncaught exceptions and failed requests on `page`."""
    found: list[str] = []
    page.on("console", lambda msg: found.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: found.append(f"Uncaught: {exc}"))
    page.on("requestfailed", lambda req: found.append(f"Failed: {req.url} ({req.failure})"))
    return found
