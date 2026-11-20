"""Letterfield keeps up as the survey and the field notes grow.

These time the work a big universe or a wide notebook asks for, against limits far above
what it takes and far below what it took when a cache emptied itself partway through.
"""

from __future__ import annotations

from playwright.sync_api import Page

from fake_survey import FakeSurvey, world_map
from test_letterfield_survey import open_game

# Lays out one find in each of `n` territories, a 50-wide block of them.
SPREAD = """(n) => {
  const lf = window.__lf, finds = [], now = Date.now();
  for (let i = 0; i < n; i++) {
    const rx = i % 50 - 25, ry = Math.floor(i / 50) - 25, w = lf.chunk(rx * 4, ry * 4).words[0];
    finds.push({ w: w.w, x: w.x, y: w.y, d: w.d, t: now - i * 60000, s: 0 });
  }
  localStorage.setItem('letterfield.finds.v4', JSON.stringify(finds));
  localStorage.setItem('letterfield.coach.v1', '1');
}"""


def slowest(page: Page, js: str, runs: int = 3) -> float:
    """The longest of `runs` runs of `js`, a function of nothing, in milliseconds."""
    return max(
        page.evaluate(f"() => {{ const s = performance.now(); ({js})(); return performance.now() - s; }}")
        for _ in range(runs)
    )


def test_a_universe_with_thousands_of_full_territories_redraws_quickly(page: Page, site_url, errors):
    # 2,500 territories with 100 charted each: more than a cache of 2,000 totals held.
    charted = {(tx, ty): 100 for tx in range(-25, 25) for ty in range(-25, 25)}
    fake = FakeSurvey(world=world_map(charted))
    open_game(page, site_url, fake, viewport={"width": 390, "height": 844})
    page.wait_for_function("window.__lf && window.__lf.world() && window.__lf.world().charted === 250000")
    page.evaluate("() => window.__lf.remnants()")  # the first pass works out every total
    # Each word charted anywhere asks again; it took about 0.35 s every time, and more on a phone.
    took = slowest(
        page,
        """() => { window.__lf.claims.set('k' + Math.random(), { s: 1, x: 0, y: 0, ex: 0, ey: 0, w: 'ZZZ', th: 0, d: 0 }); window.__lf.remnants(); }""",
    )
    assert took < 250, took
    assert errors == []


def test_finds_in_thousands_of_territories_check_achievements_quickly(page: Page, site_url, errors):
    open_game(page, site_url, None, viewport={"width": 390, "height": 844})
    page.wait_for_function("window.__lf")
    page.evaluate(SPREAD, 2500)
    page.reload()
    page.wait_for_function("window.__lf && window.__lf.marks && window.__lf.found.size === 2500")
    page.evaluate("() => window.__lf.marks.check()")
    # The check after each find took about 0.45 s.
    took = slowest(page, "() => window.__lf.marks.check()")
    assert took < 250, took
    assert errors == []
