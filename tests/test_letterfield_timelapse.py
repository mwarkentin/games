"""Letterfield's survey timelapse, against a fake of the log's API.

Like the log, the page reads the Worker's URL from ?survey=, so these tests
point it at https://survey.test (see fake_survey_log.py). The history is three
days of made-up words around the origin, in Toronto's time zone, where every
test runs, with one territory charted whole: a supernova on the second day.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from playwright.sync_api import Page, expect

from fake_leaderboard import Held
from fake_survey_log import SURVEY, FakeSurveyLog

NOW_MS = int(datetime(2026, 11, 6, 20, 30, tzinfo=timezone.utc).timestamp() * 1000)  # 3:30 PM in Toronto
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
DAY = NOW_MS // DAY_MS
PLACES = {"0,0": "Acorn Hollow", "1,0": "Monet Reach"}


def theme(x: int, y: int) -> int:
    return (x // 48 + 15 * (y // 48)) % 225


def history():
    """Words over three UTC days: territory 0,0 charted whole (12 words) on the second, others around it."""
    out = []
    for i in range(12):  # day - 1, from 9 AM UTC: the supernova at the twelfth
        x, y = 2 + (i % 4) * 11, 3 + (i // 4) * 14
        out.append([f"W{i:02d}AAA", x, y, i % 8, 0, "ZED", (DAY - 1) * DAY_MS + 9 * HOUR_MS + i * 600_000, theme(x, y)])
    for i in range(6):  # two days ago, in territory 1,0
        x, y = 50 + i * 7, 10 + i * 5
        out.append([f"M{i:02d}AAA", x, y, 0, 0, "ABC", (DAY - 2) * DAY_MS + 15 * HOUR_MS + i * 900_000, theme(x, y)])
    for i in range(4):  # today, further out, one a stray
        x, y = -60 - i * 9, 70 + i * 4
        out.append([f"T{i:02d}AAA", x, y, 2, int(i == 3), "", DAY * DAY_MS + 13 * HOUR_MS + i * 300_000, theme(x, y)])
    return out


WORDS = history()


def open_timelapse(page: Page, site_url: str, fake: FakeSurveyLog, handler=None, query: str = "") -> None:
    page.clock.set_fixed_time(NOW_MS / 1000)
    fake.now_ms = NOW_MS
    page.route(f"{SURVEY}/v1/survey/log/**", handler or fake.handle)
    page.goto(f"{site_url}/letterfield-timelapse?survey={SURVEY}{query}")


def fake_log(**kw) -> FakeSurveyLog:
    return FakeSurveyLog(WORDS, PLACES, {theme(2, 3): ["Forest", 40]}, totals={"0,0": 12}, **kw)


def tl(page: Page):
    return page.evaluate("({state: __tl.state, pos: __tl.pos, P: __tl.P, loaded: __tl.loaded, shown: __tl.shown})")


def test_plays_the_survey_from_its_first_word(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = fake_log()
    open_timelapse(page, site_url, fake)
    html = page.locator("html")
    expect(html).to_have_attribute("data-tl", "playing")
    # It loads the index, then each day with words, oldest first.
    page.wait_for_function("__tl.loaded.days === 3")
    days = [r for r in fake.requests if r.startswith("/timelapse/")]
    assert days == [f"/timelapse/{DAY - 2}", f"/timelapse/{DAY - 1}", f"/timelapse/{DAY}"]
    assert fake.requests[0] == "/timelapse"
    # It starts at the first word, two days ago, and counts up as it plays.
    expect(page.locator("#startDay")).to_have_text("Nov 4")
    expect(page.locator("#endDay")).to_have_text("Nov 6")
    page.wait_for_function("__tl.shown.n >= 1")
    first = tl(page)
    page.wait_for_function(f"__tl.pos > {first['pos']} && __tl.shown.n > {first['shown']['n']}", timeout=20000)
    expect(page.locator("#when")).to_contain_text(re.compile(r"Nov [4-6]"))
    assert errors == []


def test_pauses_scrubs_and_counts_what_was_charted_by_then(page: Page, site_url, errors):
    fake = fake_log()
    open_timelapse(page, site_url, fake)
    html = page.locator("html")
    expect(html).to_have_attribute("data-tl", "playing")
    page.wait_for_function("__tl.loaded.days === 3")
    page.locator("#play").click()
    expect(html).to_have_attribute("data-tl", "paused")
    expect(page.locator("#play")).to_have_attribute("aria-label", "Play")
    # The end: every word, the supernova and the three territories with hidden words.
    page.locator("#scrub").fill("1000")
    expect(page.locator("#nWords")).to_have_text("22")
    expect(page.locator("#nNovas")).to_have_text("1")
    expect(page.locator("#nPlaces")).to_have_text("3")
    expect(page.locator("#when")).to_contain_text("Fri, Nov 6")
    expect(page.locator("#whenTime")).to_have_text("9:00 AM")  # the end of the last hour with words, 2 PM UTC
    # Back to the morning the supernova went off: day one's words and eleven of its twelve.
    supernova_at = WORDS[11][6]
    page.evaluate("__tl.seek(0)")
    expect(page.locator("#nWords")).to_have_text("1")
    # Keys work from anywhere but a control, which keeps its own.
    page.evaluate("document.activeElement.blur()")
    page.keyboard.press("End")
    expect(page.locator("#nWords")).to_have_text("22")
    page.keyboard.press("Home")
    expect(page.locator("#nNovas")).to_have_text("0")
    # Space plays from where it is, and pauses again.
    page.keyboard.press("Space")
    expect(html).to_have_attribute("data-tl", "playing")
    page.keyboard.press("Space")
    expect(html).to_have_attribute("data-tl", "paused")
    assert supernova_at // DAY_MS == DAY - 1
    assert errors == []


def test_plays_to_the_end_and_starts_again(page: Page, site_url, errors):
    fake = fake_log()
    open_timelapse(page, site_url, fake)
    html = page.locator("html")
    page.wait_for_function("__tl.loaded.days === 3")
    page.locator('#speeds button[data-speed="4"]').click()
    expect(page.locator('#speeds button[data-speed="4"]')).to_have_attribute("aria-pressed", "true")
    page.evaluate("__tl.seek(0.97)")
    expect(html).to_have_attribute("data-tl", "paused", timeout=10000)
    expect(page.locator("#nWords")).to_have_text("22")
    page.locator("#play").click()
    expect(html).to_have_attribute("data-tl", "playing")
    assert page.evaluate("__tl.pos") < page.evaluate("__tl.P") / 10
    # The speed is remembered.
    assert page.evaluate("localStorage.getItem('letterfield.timelapse.speed')") == "4"
    assert errors == []


def test_starts_before_every_day_has_arrived_and_waits_for_the_rest(page: Page, site_url, errors):
    fake = fake_log()
    held = Held(fake, lambda r: r.url.split("?")[0].endswith(f"/timelapse/{DAY}"))
    open_timelapse(page, site_url, fake, held.handle)
    html = page.locator("html")
    held.wait_for(page)
    # Two days are in: it plays them, with the last still on its way.
    expect(html).to_have_attribute("data-tl", "playing")
    expect(page.locator("#loadedNote")).to_have_text("67% loaded")
    # Jumped past them, it waits, counting the hours it doesn't have yet from the index.
    page.evaluate("__tl.seek(0.999)")
    expect(html).to_have_attribute("data-tl", "waiting")
    expect(page.locator("#loadedNote")).to_have_text("Loading…")
    expect(page.locator("#nWords")).to_have_text("18")
    held.release()
    expect(html).not_to_have_attribute("data-tl", "waiting")
    expect(page.locator("#nWords")).to_have_text("22")
    expect(page.locator("#loadedNote")).to_have_text("")
    assert errors == []


def view_span(page: Page) -> float:
    """How many cells wide the map's view is."""
    return page.evaluate("innerWidth * Math.min(devicePixelRatio || 1, 2) / __tl.cam.s")


def test_frames_where_the_charting_is_not_a_few_words_far_out(page: Page, site_url, errors):
    # Someone charted two words 170 territories east and 224 north of everyone else, as on a preview.
    far = [[f"FAR{i}AAA", 8186 + i * 9, -10719, 0, 0, "", (DAY - 1) * DAY_MS + 9 * HOUR_MS + 30_000 + i, theme(8186 + i * 9, -10719)]
           for i in range(2)]
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog(WORDS + far, PLACES, {}, totals={"0,0": 12})
    open_timelapse(page, site_url, fake)
    page.wait_for_function("__tl.loaded.days === 3")
    page.locator("#play").click()
    page.locator("#scrub").fill("1000")
    expect(page.locator("#nWords")).to_have_text("24")
    page.wait_for_timeout(100)
    # Everyone else is within a few territories; the far words stay on the map, off screen.
    assert view_span(page) < 8 * 48
    cam = page.evaluate("__tl.cam")
    assert -3 * 48 < cam["x"] < 2 * 48 and -48 < cam["y"] < 3 * 48, cam
    assert errors == []


def test_frames_a_second_cluster_once_it_has_real_charting(page: Page, site_url, errors):
    # Thirty words far out are charting in their own right: the camera takes them in.
    far = [[f"FAR{i:02d}AAA", 8186 + i % 40, -10719 + i, 0, 0, "", DAY * DAY_MS + 14 * HOUR_MS + i * 1000, theme(8186 + i % 40, -10719 + i)]
           for i in range(30)]
    page.set_viewport_size({"width": 375, "height": 740})
    fake = FakeSurveyLog(WORDS + far, PLACES, {}, totals={"0,0": 12})
    open_timelapse(page, site_url, fake)
    page.wait_for_function("__tl.loaded.days === 3")
    page.locator("#play").click()
    page.locator("#scrub").fill("1000")
    expect(page.locator("#nWords")).to_have_text("52")
    page.wait_for_timeout(100)
    assert view_span(page) > 8000
    assert errors == []


def test_follows_a_busy_days_pages(page: Page, site_url, errors):
    fake = fake_log(timelapse_page=5)
    open_timelapse(page, site_url, fake)
    page.wait_for_function("__tl.loaded.days === 3")
    assert f"/timelapse/{DAY - 1}?after=5" in fake.requests
    assert f"/timelapse/{DAY - 1}?after=10" in fake.requests
    assert page.evaluate("__tl.loaded") == {"days": 3, "of": 3, "words": 22, "novas": 1}
    assert errors == []


def test_starts_paused_on_the_whole_map_with_reduced_motion(page: Page, site_url, errors):
    page.emulate_media(reduced_motion="reduce")
    fake = fake_log()
    open_timelapse(page, site_url, fake)
    html = page.locator("html")
    expect(html).to_have_attribute("data-tl", "paused")
    page.wait_for_function("__tl.loaded.days === 3")
    expect(page.locator("#nWords")).to_have_text("22")
    expect(page.locator("#nNovas")).to_have_text("1")
    page.wait_for_timeout(300)
    assert page.evaluate("__tl.state") == "paused"
    page.locator("#play").click()
    expect(html).to_have_attribute("data-tl", "playing")
    assert errors == []


def test_a_tapped_territory_links_to_its_page_in_the_log(page: Page, site_url, errors):
    page.set_viewport_size({"width": 375, "height": 740})
    fake = fake_log()
    open_timelapse(page, site_url, fake)
    page.wait_for_function("__tl.loaded.days === 3")
    page.locator("#play").click()
    page.locator("#scrub").fill("1000")
    page.wait_for_timeout(100)
    # The middle of territory 0,0, where the camera puts it.
    x, y = page.evaluate("""() => {
      const c = __tl.cam, s = c.s / Math.min(devicePixelRatio || 1, 2);
      const top = document.querySelector('#top').getBoundingClientRect(), panel = document.querySelector('#panel').getBoundingClientRect();
      const vx = 10, vy = top.bottom - 10, vw = innerWidth - 20, vh = panel.top - vy - 10;
      return [vx + vw / 2 + (24 - c.x) * s, vy + vh / 2 + (24 - c.y) * s];
    }""")
    page.mouse.click(x, y)
    chip = page.locator("#chip")
    expect(chip).to_be_visible()
    expect(page.locator("#chipName")).to_have_text("Acorn Hollow")
    expect(page.locator("#chipNote")).to_contain_text("12 hidden words charted by then · gone supernova")
    expect(page.locator("#chipLink")).to_have_attribute("href", f"/letterfield-log?territory=0,0&survey={SURVEY.replace(':', '%3A').replace('/', '%2F')}")
    page.keyboard.press("Escape")
    expect(chip).to_be_hidden()
    assert errors == []


def test_saves_a_video_of_the_whole_survey(page: Page, site_url, errors):
    fake = fake_log()
    open_timelapse(page, site_url, fake)
    html = page.locator("html")
    save = page.locator("#save")
    expect(save).to_be_visible()
    expect(save).to_be_enabled()
    page.evaluate("__tl.videoSeconds = 1")
    save.click()
    # Playback pauses while the video records, and the page behind it is out of reach.
    expect(html).to_have_attribute("data-tl", "paused")
    expect(html).to_have_attribute("data-rec", re.compile("preparing|recording"))
    assert page.evaluate("document.querySelector('#panel').inert")
    expect(html).to_have_attribute("data-rec", "done", timeout=15000)
    assert page.evaluate("__tl.videoBytes") > 1000
    link = page.locator("#recDownload")
    expect(link).to_be_visible()
    expect(link).to_have_attribute("download", re.compile(r"^letterfield-timelapse-\d{4}-\d\d-\d\d\.(webm|mp4)$"))
    page.locator("#recCancel").click()
    expect(html).to_have_attribute("data-rec", "off")
    assert not page.evaluate("document.querySelector('#panel').inert")
    # The video's preview reads the recording through a blob: URL, and stops reading when a WebM
    # from MediaRecorder turns out to have no duration in its header. That's the browser, not the page.
    assert [e for e in errors if not re.match(r"^Failed: blob:.*ERR_ABORTED", e)] == []
    errors.clear()


def test_a_video_can_be_cancelled_while_it_records(page: Page, site_url, errors):
    fake = fake_log()
    open_timelapse(page, site_url, fake)
    html = page.locator("html")
    page.wait_for_function("__tl.loaded.days === 3")
    page.locator("#save").click()
    expect(html).to_have_attribute("data-rec", "recording")
    page.keyboard.press("Escape")
    expect(html).to_have_attribute("data-rec", "off")
    page.wait_for_timeout(700)
    assert page.evaluate("__tl.rec") == "off"
    assert page.evaluate("__tl.videoBytes") == 0
    assert errors == []


def test_hides_save_video_where_the_browser_cant_record(page: Page, site_url, errors):
    page.add_init_script("delete window.MediaRecorder")
    open_timelapse(page, site_url, fake_log())
    expect(page.locator("html")).to_have_attribute("data-tl", "playing")
    expect(page.locator("#save")).to_be_hidden()
    assert errors == []


def test_says_when_nothing_is_charted_yet(page: Page, site_url, errors):
    open_timelapse(page, site_url, FakeSurveyLog())
    expect(page.locator("html")).to_have_attribute("data-tl", "empty")
    expect(page.locator("#statusTitle")).to_have_text("Nothing charted yet")
    expect(page.locator("#play")).to_be_disabled()
    assert errors == []


def test_says_when_the_log_cant_be_reached_and_tries_again(page: Page, site_url, errors):
    fake = fake_log(fail=True)
    open_timelapse(page, site_url, fake)
    html = page.locator("html")
    expect(html).to_have_attribute("data-tl", "failed")
    expect(page.locator("#statusTitle")).to_have_text("The log can’t be reached")
    fake.fail = False
    page.locator("#retry").click()
    expect(html).to_have_attribute("data-tl", "playing")
    # The browser's own report of the failed request is the only error.
    assert all("503" in e for e in errors), errors
    errors.clear()


def test_the_log_links_to_the_timelapse(page: Page, site_url, errors):
    fake = fake_log()
    page.clock.set_fixed_time(NOW_MS / 1000)
    fake.now_ms = NOW_MS
    page.route(f"{SURVEY}/v1/survey/log/**", fake.handle)
    page.goto(f"{site_url}/letterfield-log?survey={SURVEY}")
    page.locator("#timelapseLink").click()
    page.wait_for_url(f"{site_url}/letterfield-timelapse")
    expect(page.locator("html")).to_have_attribute("data-tl", re.compile("loading|failed|empty|playing"))
    page.unroute(f"{SURVEY}/v1/survey/log/**")
    errors.clear()  # without ?survey=, it asks the real Worker's stand-in, which has nothing
