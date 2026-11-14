"""What a word means, opened from its row in Letterfield's survey log.

Every word in the log is charted, so its meaning gives nothing away. The
Worker's definitions are faked with page.route (fake_definitions.py) and the
page is pointed at them with ?define=; the log with ?survey= (see
test_letterfield_log.py for the clock and the fake).
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from fake_definitions import DEFINE_API, FakeDefinitions
from fake_survey_log import FakeSurveyLog
from test_letterfield_log import ACORN, MONET, PLACES, THEMES, ZEUS, open_log


def open_with(page: Page, site_url: str, fake: FakeDefinitions, define: str = DEFINE_API) -> None:
    page.set_viewport_size({"width": 375, "height": 740})
    page.route(f"{DEFINE_API}/**", fake.handle)
    open_log(page, site_url, FakeSurveyLog([ACORN, MONET, ZEUS], PLACES, THEMES), query=f"&define={define}#debug")
    expect(page.locator(".entry")).to_have_count(2)


def book(page: Page, word: str):
    return page.get_by_role("button", name=f"What {word} means")


def test_a_words_book_opens_its_meaning_under_its_row(page: Page, site_url, errors):
    fake = FakeDefinitions(
        senses=[{"pos": "noun", "text": "The nut of an oak."}, {"pos": "verb", "text": "To gather nuts."}]
    )
    open_with(page, site_url, fake)
    book(page, "ACORN").click()
    panel = page.locator(".def-row")
    expect(panel.locator(".def")).to_have_attribute("data-define", "ready")
    expect(panel.locator(".def-sense")).to_have_text(["nounThe nut of an oak.", "verbTo gather nuts."])
    expect(panel.get_by_role("link", name="From Wiktionary")).to_have_attribute(
        "href", "https://en.wiktionary.org/wiki/acorn#English"
    )
    expect(panel.get_by_role("link", name="CC BY-SA 4.0")).to_be_visible()
    assert fake.asked == ["ACORN/11"]
    # Right under its row, with the focus left on the book.
    assert page.evaluate("document.querySelector('.def-row').previousElementSibling.textContent.includes('ACORN')")
    expect(book(page, "ACORN")).to_be_focused()
    expect(book(page, "ACORN")).to_have_attribute("aria-expanded", "true")
    assert page.evaluate("window.__log.definitions()") == {"ACORN/11": "ready"}
    # One at a time: another word's closes it; its own book closes it, and opening again asks no more.
    book(page, "MONET").click()
    expect(page.locator(".def-row")).to_have_count(1)
    expect(book(page, "ACORN")).to_have_attribute("aria-expanded", "false")
    book(page, "MONET").click()
    expect(page.locator(".def-row")).to_have_count(0)
    book(page, "ACORN").click()
    expect(page.locator(".def-sense")).to_have_count(2)
    assert fake.asked == ["ACORN/11", "MONET/0"]
    # It fits a phone, and the rows stay tall enough for a finger.
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    assert book(page, "ACORN").evaluate("e => e.getBoundingClientRect().height") >= 40
    assert (
        min(page.evaluate("[...document.querySelectorAll('.entry')].map(e => e.getBoundingClientRect().height)")) >= 44
    )
    assert errors == []


def test_a_word_with_no_meaning_and_one_that_failed_then_comes(page: Page, site_url):
    # Skips the errors fixture: the browser logs the 503.
    fake = FakeDefinitions(answers={"ACORN": [], "MONET": 503})
    open_with(page, site_url, fake)
    book(page, "ACORN").click()
    expect(page.locator(".def-note")).to_have_text("No definition to hand for this one.")
    expect(page.locator(".def-links").get_by_role("link", name="Wiktionary")).to_be_visible()
    book(page, "MONET").click()
    expect(page.locator(".def-note")).to_have_text("Couldn’t look it up just now.")
    expect(page.locator(".def")).to_have_attribute("data-define", "failed")
    # Wikimedia is back: Try again looks it up.
    fake.answers["MONET"] = [{"pos": "noun", "text": "A painter."}]
    fake.holding = True
    page.get_by_role("button", name="Try again").click()
    expect(page.locator(".def-note")).to_have_text("Looking it up…")
    fake.holding = False
    for route in fake.held:
        fake.reply(route)
    expect(page.locator(".def-sense")).to_have_text("nounA painter.")
    assert page.evaluate("window.__log.definitions()") == {"ACORN/11": "none", "MONET/0": "ready"}


def test_the_workers_text_goes_in_as_text_and_only_wikimedia_links(page: Page, site_url, errors):
    fake = FakeDefinitions()
    original = fake.reply

    def reply(route):
        # A link to anywhere else is dropped.
        route_url = route.request.url
        if "ACORN" in route_url:
            route.fulfill(
                status=200,
                headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                body='{"senses":[{"pos":"<b>noun</b>","text":"<img src=x onerror=\\"window.__hacked=1\\">A nut."}],'
                '"source":"wiktionary","url":"https://evil.test/acorn"}',
            )
        else:
            original(route)

    fake.reply = reply
    open_with(page, site_url, fake)
    book(page, "ACORN").click()
    sense = page.locator(".def-sense")
    expect(sense).to_have_text('<b>noun</b><img src=x onerror="window.__hacked=1">A nut.')
    expect(sense.locator("img, b")).to_have_count(0)
    expect(page.locator(".def-row").get_by_role("link", name="From Wiktionary")).to_have_count(0)
    assert page.evaluate("window.__hacked") is None
    assert errors == []


def test_without_the_worker_a_word_only_links_out(page: Page, site_url, errors):
    fake = FakeDefinitions()
    open_with(page, site_url, fake, define="")
    book(page, "ACORN").click()
    links = page.locator(".def-links")
    expect(links).to_have_text("Look it up onWiktionaryWikipedia")
    expect(links.get_by_role("link", name="Wikipedia")).to_have_attribute(
        "href", "https://en.wikipedia.org/w/index.php?search=acorn%20Forest"
    )
    assert fake.asked == []
    assert errors == []


def test_the_book_is_level_with_its_word_and_scrolls_under_the_hours_heading(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 600})
    words = [
        "FORTY",
        "BOUQUET",
        "NEWLYWED",
        "TALC",
        "FLICK",
        "TIERED",
        "SLAG",
        "WOOER",
        "FINAL",
        "DEAREST",
        "BIRCH",
        "CEDAR",
    ]
    rows = [[w, 3 * i, 7, i % 8, 0, "ZED", ACORN[6] + i * 1000, 11] for i, w in enumerate(words)]
    page.route(f"{DEFINE_API}/**", FakeDefinitions().handle)
    open_log(page, site_url, FakeSurveyLog(rows, PLACES, THEMES), query=f"&define={DEFINE_API}")
    expect(page.locator(".entry")).to_have_count(12)
    middles = page.evaluate("""[...document.querySelectorAll('.entry')].map(e => {
      const w = e.querySelector('.word').getBoundingClientRect(), b = e.querySelector('.define').getBoundingClientRect();
      return Math.abs((w.top + w.height / 2) - (b.top + b.height / 2));
    })""")
    assert max(middles) <= 1, middles
    # Scrolled so rows pass under the hour's heading, which stays on top of their links and books.
    page.evaluate("document.querySelectorAll('.entry')[5].scrollIntoView({ block: 'start' })")
    page.wait_for_function("document.querySelector('.hour h3').getBoundingClientRect().top <= 1")
    covered = page.evaluate("""(() => {
      const h = document.querySelector('.hour h3').getBoundingClientRect();
      return [h.left + 4, h.right - 24, h.right - 4].flatMap(x => [h.top + h.height / 2, h.bottom - 4]
        .map(y => !!document.elementFromPoint(x, y)?.closest('.hour h3')));
    })()""")
    assert all(covered), covered
    assert errors == []
