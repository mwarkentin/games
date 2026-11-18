"""Shared fixtures: build the site once, then serve it like GitHub Pages does."""

from __future__ import annotations

import fcntl
import functools
import http.server
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from common import ROOT
from fake_leaderboard import stand_in_for_worker
from fake_survey import FakeBadges


@pytest.fixture(scope="session")
def site_dir(tmp_path_factory) -> Path:
    """The site exactly as build.sh assembles it for deploy.

    Built once per run. Under pytest-xdist (`-n`) every worker asks for it,
    and the build writes gathered_links.json and games.json into the repo,
    so the first worker builds it under a lock in the run's shared temp
    directory and the others wait, then use that copy.
    """
    shared = tmp_path_factory.getbasetemp()
    if os.environ.get("PYTEST_XDIST_WORKER"):
        shared = shared.parent  # each worker's basetemp sits in the run's
    out = shared / "site"
    done = shared / "site.built"
    with open(shared / "site.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not done.exists():
            subprocess.run(
                ["bash", "build.sh"],
                cwd=ROOT,
                env={**os.environ, "SITE_DIR": str(out), "PYTHON": sys.executable},
                check=True,
            )
            done.touch()
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
    """Fixed locale and time zone, so dates render the same everywhere.

    Service workers are blocked, so sw.js never answers a request that a
    test means page.route to see. tests/test_pwa.py allows them.
    """
    return {
        **browser_context_args,
        "locale": "en-US",
        "timezone_id": "America/Toronto",
        "service_workers": "block",
    }


# Letterfield's achievement notes start quietened, so a test's first find doesn't bring a note
# it isn't about (a "First Mark" over the note it's watching). tests/test_letterfield_achievements.py
# turns them back on. Set only when nothing is stored, so a test's own choice is kept.
QUIET_ACHIEVEMENTS = """
try {
  if (location.protocol.startsWith('http') && localStorage.getItem('letterfield.quiet.v1') === null)
    localStorage.setItem('letterfield.quiet.v1', '["achievement"]');
} catch (_) {}
"""


@pytest.fixture
def context(context):
    """pytest-playwright's context, with the real Worker faked (see fake_leaderboard.py),
    Letterfield's achievement notes quietened (see QUIET_ACHIEVEMENTS) and its badges answered."""
    stand_in_for_worker(context)
    context.add_init_script(QUIET_ACHIEVEMENTS)
    # Letterfield asks the fake survey which badges it may show; a test that cares routes its own.
    context.route("https://survey.test/v1/survey/badges", FakeBadges().handle)
    return context


@pytest.fixture
def errors(page) -> list[str]:
    """Console errors, uncaught exceptions and failed requests on `page`."""
    found: list[str] = []
    page.on("console", lambda msg: found.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: found.append(f"Uncaught: {exc}"))
    page.on("requestfailed", lambda req: found.append(f"Failed: {req.url} ({req.failure})"))
    return found
