from playwright.sync_api import Page, expect

# Screen positions of a legend word's first and last letters, for a word whose
# ends are both on open map rather than under a panel. Mirrors the game's
# camera: it starts centred on cell (6, 6) with 38px cells.
FIND_WORD_JS = """() => {
  const cs = 38, start = 6, canvas = document.getElementById('map');
  const dock = document.body.classList.contains('docked') ? 340 : 0;
  const dirs = [[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1],[0,-1],[1,-1]];
  const screen = (x, y) => [(x + .5 - start) * cs + (innerWidth - dock) / 2, (y + .5 - start) * cs + innerHeight / 2];
  for (const chip of document.querySelectorAll('#legendList .chip:not(.found)')) {
    const [word, x, y, d] = chip.dataset.key.split('~');
    const n = word.length - 1, [dx, dy] = dirs[+d];
    const ends = [screen(+x, +y), screen(+x + dx * n, +y + dy * n)];
    if (ends.every(([sx, sy]) => document.elementFromPoint(sx, sy) === canvas)) return { word, ends };
  }
  return null;
}"""


def test_circling_a_word_adds_it_to_field_notes(page: Page, site_url, errors):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{site_url}/letterfield")
    page.click("#coachOk")
    expect(page.locator("#coach")).to_be_hidden()
    expect(page.locator("#legendList .chip").first).to_be_visible()

    target = page.evaluate(FIND_WORD_JS)
    assert target, "no legend word with both ends on open map"
    for x, y in target["ends"]:
        page.mouse.click(x, y)
    expect(page.locator("#notesBadge")).to_have_text("1")
    expect(page.locator("#toast")).to_contain_text(target["word"])

    # Finds are kept in this browser and survive a reload.
    page.reload()
    expect(page.locator("#notesBadge")).to_have_text("1")
    assert errors == []
