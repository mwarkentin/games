"""What telemetry.js sends to Sentry: nothing off the production site, and on it
errors, performance and replays, with IP addresses left out.

These tests serve the built site at https://games.michaelwarkentin.com with
Playwright's page.route, give telemetry.js a test DSN and catch every envelope
the Sentry SDK sends. The SDK itself comes from browser.sentry-cdn.com, so the
browser checks its integrity hashes.
"""

from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, Route

from common import BASE_URL

DSN = "https://public@sentry.test/1"
DSN_LINE = re.compile(r"const SENTRY_DSN = '[^']*';")


def with_test_dsn(text: str) -> str:
    assert DSN_LINE.search(text), "telemetry.js should set SENTRY_DSN"
    return DSN_LINE.sub(f"const SENTRY_DSN = '{DSN}';", text)


def envelope_items(body: bytes) -> list[tuple[dict, bytes]]:
    """Split an envelope into (item header, payload) pairs."""
    _, _, rest = body.partition(b"\n")
    items = []
    while rest.strip():
        line, _, rest = rest.partition(b"\n")
        header = json.loads(line)
        if "length" in header:
            payload, rest = rest[: header["length"]], rest[header["length"] :].removeprefix(b"\n")
        else:
            payload, _, rest = rest.partition(b"\n")
        items.append((header, payload))
    return items


class FakeSentry:
    """Answers the SDK's POSTs and keeps every envelope."""

    def __init__(self):
        self.bodies: list[bytes] = []

    def handle(self, route: Route) -> None:
        self.bodies.append(route.request.post_data_buffer or b"")
        route.fulfill(status=200, json={}, headers={"Access-Control-Allow-Origin": "*"})

    def items(self, kind: str) -> list[dict]:
        return [
            json.loads(payload)
            for body in self.bodies
            for header, payload in envelope_items(body)
            if header.get("type") == kind
        ]

    def wait_for(self, page: Page, kind: str, count: int = 1) -> list[dict]:
        for _ in range(200):
            if len(self.items(kind)) >= count:
                return self.items(kind)
            page.wait_for_timeout(100)
        pytest.fail(f"expected {count} {kind} item(s), got {self.items(kind)}")


@pytest.fixture
def sentry(page: Page) -> FakeSentry:
    fake = FakeSentry()
    page.route("https://sentry.test/**", fake.handle)
    return fake


@pytest.fixture
def production(page: Page, site_dir: Path) -> str:
    """Serve the built site as the production host, with the test DSN."""

    def handle(route: Route) -> None:
        path = urlparse(route.request.url).path.strip("/") or "index.html"
        file = next((f for f in (site_dir / path, site_dir / f"{path}.html") if f.is_file()), None)
        if file is None:
            route.fulfill(status=404)
            return
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        body = file.read_bytes()
        if file.suffix == ".html":
            body = with_test_dsn(body.decode("utf-8")).encode("utf-8")
        route.fulfill(status=200, body=body, content_type=content_type)

    page.route(f"{BASE_URL}/**", handle)
    return BASE_URL


def test_telemetry_does_nothing_on_other_hosts(page: Page, site_url, errors):
    def handle(route: Route) -> None:
        response = route.fetch()
        route.fulfill(response=response, body=with_test_dsn(response.text()))

    page.route(f"{site_url}/letterfield", handle)
    requested: list[str] = []
    page.on("request", lambda request: requested.append(request.url))
    page.goto(f"{site_url}/letterfield", wait_until="networkidle")

    assert [url for url in requested if "sentry" in url] == []
    assert errors == []


def test_errors_reach_sentry_with_a_replay(page: Page, production, sentry, errors):
    page.goto(f"{production}/funnels-and-buckets")
    page.wait_for_function("window.Sentry?.getClient()")
    assert page.evaluate("!!Sentry.getClient().getIntegrationByName('ReplayCanvas')")

    page.add_script_tag(content="setTimeout(() => { throw new Error('bucket overflow'); });")
    [event] = sentry.wait_for(page, "event")
    # A game never goes idle, so end the page load's trace rather than wait it out.
    page.evaluate("Sentry.getRootSpan(Sentry.getActiveSpan()).end()")
    [spans] = sentry.wait_for(page, "span")
    [replay] = sentry.wait_for(page, "replay_event")

    assert event["exception"]["values"][0]["value"] == "bucket overflow"
    assert event["release"].startswith("games@")
    assert event["sdk"]["settings"]["infer_ip"] == "never"
    assert event["event_id"] in replay["error_ids"]
    assert any(span.get("is_segment") and span["name"] == "Pageload" for span in spans["items"])
    assert not any(b"{{auto}}" in body for body in sentry.bodies)
    assert errors == ["Uncaught: bucket overflow"], "the SDK shouldn't log errors of its own"


def test_errors_before_the_sdk_loads_are_sent_once_it_does(page: Page, production, sentry):
    held: list[Route] = []
    page.route("https://browser.sentry-cdn.com/**", lambda route: held.append(route))
    page.add_init_script("addEventListener('DOMContentLoaded', () => { throw new Error('early'); })")
    page.goto(f"{production}/doodle-chomp", wait_until="domcontentloaded")
    while len(held) < 2:
        page.wait_for_timeout(50)
    assert sentry.bodies == []

    for route in held:
        route.continue_()
    [event] = sentry.wait_for(page, "event")
    assert event["exception"]["values"][0]["value"] == "early"
    assert event["exception"]["values"][0]["mechanism"]["handled"] is False
