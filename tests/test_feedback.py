"""Every game's "Send feedback" dialog (feedback.js) and the issue forms it fills in.

Without Sentry, as here, the dialog links to the Bug and Idea forms on
GitHub, filled in by their fields' ids. tests/test_telemetry.py covers the
form it shows once Sentry has loaded.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Browser, Page, expect

from common import BASE_URL, ROOT, game_files
from fake_leaderboard import stand_in_for_worker

ISSUES = "https://github.com/mwarkentin/games/issues/new"
TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"


def readme_titles() -> dict[str, str]:
    readme = (ROOT / "README.md").read_text("utf-8")
    return dict(
        (slug, title) for title, slug in re.findall(rf"^- \[([^\]]+)\]\({re.escape(BASE_URL)}/([\w-]+)\)", readme, re.M)
    )


def form_ids(template: str) -> set[str]:
    return set(re.findall(r"^\s+id: ([\w-]+)$", (TEMPLATES / template).read_text("utf-8"), re.M))


def query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def open_dialog(page: Page):
    link = page.locator("[data-feedback]")
    # Letterfield's sits in its field notes, which start closed.
    if link.is_visible():
        link.click()
    else:
        link.evaluate("link => link.click()")
    dialog = page.locator("dialog.games-feedback")
    expect(dialog).to_be_visible()
    return dialog


@pytest.fixture
def github(context):
    """github.com answered with an empty page, so following a link goes nowhere real."""
    context.route("https://github.com/**", lambda route: route.fulfill(body="", content_type="text/html"))


@pytest.mark.parametrize("filename", game_files())
def test_every_game_links_to_both_forms_filled_in_with_its_name(page: Page, site_url, errors, filename):
    slug = filename.removesuffix(".html")
    page.goto(f"{site_url}/{slug}")
    dialog = open_dialog(page)
    expect(dialog).to_have_attribute("data-mode", "github")
    expect(dialog.get_by_role("link", name="Report a bug")).to_be_focused()

    name = readme_titles()[slug]
    bug = query(dialog.get_by_role("link", name="Report a bug").get_attribute("href"))
    idea = query(dialog.get_by_role("link", name="Suggest an idea").get_attribute("href"))
    assert bug["template"] == "bug.yml" and idea["template"] == "idea.yml"
    assert bug["game"] == idea["game"] == name
    assert bug["title"] == idea["title"] == f"{name}: "

    dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).to_be_hidden()
    assert errors == []


def test_report_a_bug_fills_in_the_device_and_details_without_invite_codes(page: Page, site_url, github, errors):
    # Funnels & Buckets ignores a War room code, so the page stays on its menu.
    page.goto(f"{site_url}/funnels-and-buckets?room=ABCD#notes")
    dialog = open_dialog(page)
    with page.context.expect_page() as opened:
        dialog.get_by_role("link", name="Report a bug").click()
    url = opened.value.url
    expect(dialog).to_be_hidden()

    assert url.startswith(f"{ISSUES}?")
    fields = query(url)
    assert set(fields) - {"template", "title"} <= form_ids("bug.yml")
    assert re.fullmatch(r"Linux · Chrome \d+", fields["device"]), fields["device"]
    details = fields["details"].splitlines()
    assert details[0] == f"Page: {site_url}/funnels-and-buckets"
    assert any(line.startswith("State: ") and "screen=menu" in line for line in details)
    assert any(re.fullmatch(r"Window: \d+×\d+ at [\d.]+×, (light|dark) mode, browser tab", line) for line in details)
    assert any(re.fullmatch(r"Version: games@[0-9a-f]{7}", line) for line in details)
    assert details[-1].startswith("User agent: Mozilla/5.0")
    assert "ABCD" not in url and "notes" not in fields["details"]
    assert errors == []


def test_suggest_an_idea_fills_in_the_game_only(page: Page, site_url, github):
    page.goto(f"{site_url}/war")
    dialog = open_dialog(page)
    with page.context.expect_page() as opened:
        dialog.get_by_role("link", name="Suggest an idea").click()
    fields = query(opened.value.url)
    assert fields == {"template": "idea.yml", "title": "War: ", "game": "War"}
    assert set(fields) - {"template", "title"} <= form_ids("idea.yml")


def test_a_click_meant_for_a_new_tab_is_left_to_the_browser(page: Page, site_url):
    page.goto(f"{site_url}/doodle-chomp")
    # After feedback.js's own listener: note whether it let the click be,
    # then stop it, since a background tab can't be waited on here.
    page.evaluate("""() => addEventListener('click', (event) => {
      window.leftAlone = !event.defaultPrevented;
      event.preventDefault();
    }, true)""")
    page.locator("[data-feedback]").click(modifiers=["ControlOrMeta"])
    assert page.evaluate("leftAlone") is True
    expect(page.locator("dialog.games-feedback")).to_have_count(0)


def test_keys_and_taps_in_the_dialog_dont_reach_the_game(page: Page, site_url):
    page.goto(f"{site_url}/funnels-and-buckets")
    # Where games listen: on the window, after the dialog.
    page.evaluate("""() => {
      window.leaked = [];
      for (const type of ['keydown', 'keyup', 'pointerdown', 'click']) addEventListener(type, () => leaked.push(type));
    }""")
    dialog = open_dialog(page)
    page.evaluate("leaked.length = 0")
    page.keyboard.press("5")
    dialog.get_by_role("heading", name="Send feedback").click()
    assert page.evaluate("leaked") == []
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(page.locator("html")).to_have_attribute("data-screen", "menu")


@pytest.mark.parametrize(
    "user_agent, expected",
    [
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1",
            "iPhone · iOS 18.5 · Safari 18.5",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/138.0.7204.156 Mobile/15E148 Safari/604.1",
            "iPhone · iOS 18.5 · Chrome 138",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/22F76 Instagram 389.0.0.49.87 (iPhone16,2; iOS 18_5; en_CA; en; scale=3.00; 1290x2796; 7512345)",
            "iPhone · iOS 18.5 · Instagram's browser",
        ),
        (
            "Mozilla/5.0 (Linux; Android 15; SM-S921W) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/28.0 Chrome/130.0.0.0 Mobile Safari/537.36",
            "Android 15 · Samsung Internet 28",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) Gecko/20100101 Firefox/144.0",
            "Mac · Firefox 144",
        ),
    ],
)
def test_device_and_browser_read_well(browser: Browser, site_url, user_agent, expected):
    context = browser.new_context(user_agent=user_agent, service_workers="block")
    stand_in_for_worker(context)
    page = context.new_page()
    page.goto(f"{site_url}/doodle-chomp")
    dialog = open_dialog(page)
    bug = query(dialog.get_by_role("link", name="Report a bug").get_attribute("href"))
    assert bug["device"] == expected
    context.close()
