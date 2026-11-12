"""What a found word means, opened from Letterfield's field notes.

The Worker's definitions are faked with page.route (fake_definitions.py); the
game is pointed at them with ?define=.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from fake_definitions import DEFINE_API, FakeDefinitions
from fake_leaderboard import without_worker


def find_words(page: Page, count: int = 1) -> list[dict]:
    """Circle `count` hidden words near the start through the debug hook; returns them as finds."""
    return page.evaluate(
        """n => {
          const words = window.__lf.chunk(0, 0).words.slice(0, n);
          for (const { w, x, y, d } of words) window.__lf.collect(w, x, y, d, false);
          return words.map(({ w, x, y, d }) => { const e = [...window.__lf.found.values()].find(f => f.w === w && f.x === x && f.y === y); return { w, key: e.key, th: e.th }; });
        }""",
        count,
    )


@pytest.fixture
def fake(page: Page) -> FakeDefinitions:
    fake = FakeDefinitions()
    page.route(f"{DEFINE_API}/**", fake.handle)
    return fake


def open_game(
    page: Page, site_url: str, width: int = 375, height: int = 740, query: str = f"?define={DEFINE_API}"
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{site_url}/letterfield{query}#debug")
    page.wait_for_function("window.__lf")
    page.evaluate("() => localStorage.setItem('letterfield.coach.v1', '1')")


def open_notes(page: Page) -> None:
    """Open the field notes, unless they're already open (docked on a wide screen)."""
    if page.locator("#notesToggle").get_attribute("aria-expanded") != "true":
        page.click("#notesToggle")
    expect(page.locator("body")).to_have_class(re.compile(r"\bnotes-open\b"))


def book(page: Page, key: str):
    return page.locator(f'.find-define[data-key="{key}"]')


def panel(page: Page, key: str):
    return page.locator(f'[id="def-{key}"]')


def test_a_found_words_meaning_opens_under_its_entry(page: Page, site_url, fake, errors):
    fake.senses = [{"pos": "noun", "text": "A fragrant herb."}, {"pos": "verb", "text": "To grind a tool's edge."}]
    open_game(page, site_url)
    [word] = find_words(page)
    open_notes(page)
    expect(book(page, word["key"])).to_have_attribute("aria-expanded", "false")
    assert fake.asked == []  # nothing is looked up until it's asked for

    book(page, word["key"]).click()
    expect(book(page, word["key"])).to_have_attribute("aria-expanded", "true")
    p = panel(page, word["key"])
    expect(p).to_have_attribute("data-define", "ready")
    expect(p.locator(".def-sense")).to_have_count(2)
    expect(p.locator(".def-sense").first).to_have_text("nounA fragrant herb.")
    expect(p.get_by_role("link", name="From Wiktionary")).to_have_attribute(
        "href", f"https://en.wiktionary.org/wiki/{word['w'].lower()}#English"
    )
    expect(p.get_by_role("link", name="CC BY-SA 4.0")).to_be_visible()
    assert fake.asked == [f"{word['w']}/{word['th']}"]
    assert page.evaluate("() => window.__lf.definitions()") == {f"{word['w']}/{word['th']}": "ready"}

    # Closed and opened again: kept, not asked twice. The book doesn't fly the map.
    book(page, word["key"]).click()
    expect(panel(page, word["key"])).to_have_count(0)
    book(page, word["key"]).click()
    expect(panel(page, word["key"])).to_have_attribute("data-define", "ready")
    assert fake.asked == [f"{word['w']}/{word['th']}"]
    expect(page.locator("body")).to_have_class(re.compile(r"\bnotes-open\b"))

    # The answer's text is shown as text, never as HTML.
    assert page.locator(".find-def script, .find-def img").count() == 0
    assert errors == []


def test_text_from_the_worker_is_never_html(page: Page, site_url, fake, errors):
    fake.senses = [{"pos": "<b>noun</b>", "text": '<img src=x onerror="window.pwned=1">A thing.'}]
    open_game(page, site_url)
    [word] = find_words(page)
    open_notes(page)
    book(page, word["key"]).click()
    expect(panel(page, word["key"]).locator(".def-sense")).to_contain_text("<img src=x")
    assert page.locator(".find-def img, .find-def b").count() == 0
    assert page.evaluate("() => window.pwned") is None
    assert errors == []


def test_a_word_with_no_definition_offers_to_search(page: Page, site_url, fake, errors):
    open_game(page, site_url)
    [word] = find_words(page)
    fake.answers[word["w"]] = []
    open_notes(page)
    book(page, word["key"]).click()
    p = panel(page, word["key"])
    expect(p).to_have_attribute("data-define", "none")
    expect(p).to_contain_text("No definition to hand")
    expect(p.get_by_role("link", name="Wiktionary")).to_have_attribute(
        "href", re.compile(r"^https://en\.wiktionary\.org/wiki/Special:Search\?search=")
    )
    expect(p.get_by_role("link", name="Wikipedia")).to_have_attribute(
        "href", re.compile(r"^https://en\.wikipedia\.org/w/index\.php\?search=")
    )
    assert errors == []


def test_a_failed_lookup_can_be_tried_again(page: Page, site_url, fake, errors):
    open_game(page, site_url)
    [word] = find_words(page)
    fake.answers[word["w"]] = 503
    open_notes(page)
    book(page, word["key"]).click()
    p = panel(page, word["key"])
    expect(p).to_have_attribute("data-define", "failed")
    expect(p).to_contain_text("Couldn’t look it up just now")
    del fake.answers[word["w"]]
    p.get_by_role("button", name="Try again").click()
    expect(panel(page, word["key"])).to_have_attribute("data-define", "ready")
    assert len(fake.asked) == 2
    # A 503 is a failed request in the console, which the errors fixture counts.
    assert all("503" in e for e in errors), errors


def test_a_late_answer_lands_on_its_own_word(page: Page, site_url, fake, errors):
    open_game(page, site_url)
    first, second = find_words(page, 2)
    fake.answers[first["w"]] = [{"pos": "noun", "text": "The first word."}]
    fake.answers[second["w"]] = [{"pos": "noun", "text": "The second word."}]
    open_notes(page)
    fake.holding = True
    book(page, first["key"]).click()
    expect(panel(page, first["key"])).to_have_attribute("data-define", "loading")
    page.wait_for_function("() => true")
    # The player moves on to the second word before the first's answer comes back.
    book(page, second["key"]).click()
    expect(panel(page, first["key"])).to_have_count(0)
    expect(panel(page, second["key"])).to_have_attribute("data-define", "loading")
    assert len(fake.held) == 2
    fake.answer(0)  # the first word's answer, late
    page.wait_for_function("() => window.__lf.definitions()[Object.keys(window.__lf.definitions())[0]] === 'ready'")
    expect(panel(page, second["key"])).to_have_attribute("data-define", "loading")
    expect(page.locator(".find-def")).to_have_count(1)
    fake.answer(0)
    expect(panel(page, second["key"])).to_contain_text("The second word.")
    # And the first word's answer was kept for when it's opened again.
    fake.holding = False
    book(page, first["key"]).click()
    expect(panel(page, first["key"])).to_contain_text("The first word.")
    assert len(fake.asked) == 2
    assert errors == []


def test_without_the_worker_it_only_links_out(page: Page, site_url, errors):
    asked = []
    page.route("**/v1/define/**", lambda route: (asked.append(route.request.url), route.abort()))
    without_worker(page, site_url, "letterfield")
    open_game(page, site_url, query="")
    [word] = find_words(page)
    open_notes(page)
    book(page, word["key"]).click()
    p = panel(page, word["key"])
    expect(p).to_contain_text("Look it up on")
    expect(p.get_by_role("link", name="Wiktionary")).to_be_visible()
    assert asked == []
    assert errors == []


@pytest.mark.parametrize("width,height", [(375, 740), (1280, 900)])
def test_the_meaning_fits_at_phone_and_desktop_sizes(page: Page, site_url, fake, width, height, errors):
    fake.senses = [{"pos": "noun", "text": "A long sense " + "that goes on and on " * 8 + "."}]
    open_game(page, site_url, width, height)
    [word] = find_words(page)
    open_notes(page)
    book(page, word["key"]).click()
    p = panel(page, word["key"])
    expect(p).to_have_attribute("data-define", "ready")
    box, notes = p.bounding_box(), page.locator("#notes").bounding_box()
    assert box["x"] >= notes["x"] and box["x"] + box["width"] <= notes["x"] + notes["width"] + 0.5
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    # The book and its links are big enough to tap.
    b = book(page, word["key"]).bounding_box()
    assert b["width"] >= 40 and b["height"] >= 40
    assert errors == []
