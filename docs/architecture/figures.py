"""Letterfield's architecture figures: what each says, and how it's drawn.

Every figure is registered with its title, caption, alt text and the facts it
states, each with where it comes from, so README.md (the index) and FACTS.md
(the fact-check notes) are written from the same place as the drawing. A
figure draws itself in one theme (kit.Theme) and render.py does the rest.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from kit import HERE, THEMES, Fig, Theme, cell_box, fmt, world


@dataclass
class Figure:
    id: str
    post: str
    title: str
    caption: str
    alt: str
    facts: list[tuple[str, str]]
    draw: Callable[[Theme], Fig] = field(repr=False)


FIGURES: dict[str, Figure] = {}


def figure(id: str, post: str, title: str, caption: str, alt: str, facts: list[tuple[str, str]]):
    def register(draw: Callable[[Theme], Fig]) -> Callable[[Theme], Fig]:
        FIGURES[id] = Figure(id, post, title, caption, alt, facts, draw)
        return draw

    return register


DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
ARROWS = "→↘↓↙←↖↑↗"
DIR_NAMES = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]


def grid_letters(f: Fig, x: float, y: float, cell: float, rows: list[str], size: float | None = None,
                 fill: str | None = None, font: str = "mono") -> None:  # fmt: skip
    """Letters centred in a grid of cells, as the game draws the map."""
    size = size or cell * 0.5
    cap = f.cap_height(font, size)
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            f.text(x + (c + 0.5) * cell, y + (r + 0.5) * cell + cap / 2, ch, font, size, fill, "middle")


def circle_word(f: Fig, x: float, y: float, cell: float, col: float, row: float, length: int, d: int, hue: float,
                sw: float = 1.6, dash: str | None = None, opacity: float | None = None) -> None:  # fmt: skip
    """A word circled as the game circles it: a capsule in its theme's colour, end to end."""
    dx, dy = DIRS[d]
    n = length - 1
    f.capsule(x + (col + 0.5) * cell, y + (row + 0.5) * cell, x + (col + dx * n + 0.5) * cell,
              y + (row + dy * n + 0.5) * cell, cell * 0.42, f.t.mark(hue), f.t.wash(hue), f.t.fill_a, sw, dash,
              opacity)  # fmt: skip


def step(f: Fig, x: float, y: float, n: str, title: str, body: str, width: float) -> float:
    """A numbered step: its number, title and a line or two; returns the baseline after it."""
    f.text(x, y + 2, n, "display", 22, f.t.accent)
    f.text(x + 24, y, title, "ui6", 13)
    return f.para(x + 24, y + 17, body, width - 24, "ui", 11, lh=1.36, fill=f.t.muted)


# =============================================================================
# The map
# =============================================================================
@figure(
    "map-from-a-seed",
    "map",
    "A map from a seed",
    "Letterfield's map has no file. Every letter comes from one fixed seed, through a generator small enough "
    "to run in the page: a chunk of 12 × 12 cells hashes its coordinates with the seed, deals itself the next "
    "nine cards from its territory's shuffled deck of theme words, places six to eight of them in eight "
    "directions, and fills the rest with letters drawn from its own words. So every player sees the same "
    "endless map, and the survey's server, which runs a copy of the same code, can check that every word "
    "anyone claims is really there. This is the real chunk at the origin, in Menorah Hollow, a Festivals "
    "territory.",
    "On the left, the 12 by 12 letter grid of chunk (0, 0) in Menorah Hollow, a Festivals territory, with "
    "its seven hidden words circled in the theme's green: TRADITION and YULETIDE reading down, WREATH down "
    "and right, DIWALI and RAMADAN down and left, NAVRATRI right to left, and PURIM up and right. On the "
    "right, six numbered steps: one seed; chunks of 12 by 12 cells in territories of 4 by 4 chunks whose "
    "theme is (rx + 15 ry) mod 225; a shuffled deck per territory, dealt nine cards a chunk; eight "
    "directions weighted towards reading forwards, shown as a rose; filler letters; and bonus words of six "
    "or more letters. Along the bottom, the four checks the server makes on every claim with its own copy "
    "of the generator.",
    [
        (
            "SEED = 0x1E77E2; CH = 12 cells a chunk; RG = 4 chunks a territory; RC = 48 cells a territory",
            "worker/src/letterfield-world.js; letterfield.html World constants",
        ),
        ("A territory's theme is (rx + 15·ry) mod 225 (LAT_B = 15, 225 themes)", "letterfield-world.js regionTheme"),
        (
            "Each chunk is dealt the next DEAL = 9 cards of its territory's shuffled deck, and places them in order "
            "until it has its target of 6 + floor(r() × 3), i.e. 6 to 8",
            "letterfield-world.js genChunk, deckOf",
        ),
        (
            "Direction weights [3, 2, 3, 1, 1, 1, 1, 2] of 14 for E, SE, S, SW, W, NW, N, NE; up to 40 tries a word; "
            "a word may cross another where letters agree, but not lie wholly on one",
            "letterfield-world.js genChunk",
        ),
        ("Filler letters are drawn from 'AEIOUNRSTL' plus the chunk's placed words", "letterfield-world.js genChunk"),
        ("Bonus words (strays) count from STRAY_MIN = 6 letters", "letterfield-world.js STRAY_MIN"),
        (
            "About 21 bonus words a territory at 6+ letters (median 20) and 532 at 4+ (median 535), over 60 territories "
            "sampled across the universe with the Worker's generator; SURVEY.md says about 20 and some 530",
            "docs/architecture/data.mjs; worker/SURVEY.md",
        ),
        (
            "Chunk (0, 0) is in Menorah Hollow (Festivals, hue 90) and hides TRADITION, WREATH, DIWALI, YULETIDE, "
            "NAVRATRI, RAMADAN and PURIM",
            "node docs/architecture/data.mjs chunk 0 0",
        ),
        ("Theme sizes 144 to 184 words; 28,845 different words", "letterfield-world.js THEME_DATA (counted)"),
        (
            "checkClaim: the word is in VOCAB, its start cell is in this sector, every letter matches letterAt(), and "
            "it is one of its chunk's placed words or at least 6 letters long",
            "worker/src/survey.js checkClaim",
        ),
        ("A test runs the game's generator and the Worker's copy and compares them", "worker/test/survey.test.js"),
    ],
)
def map_from_a_seed(t: Theme) -> Fig:
    f = Fig(t, 720)
    f.header("Letterfield · the map", "A map from a seed")
    c = world("chunk", 0, 0)
    hue = c["hue"]
    x0, y0, cell = 32, 132, 26
    # It moves: the chunk builds itself as the generator does, word by word in the order placed, each in its
    # direction, then the filler letters, with the steps on the right lit as they happen.
    f.animate(13)
    first, every = 2.4, 0.95  # when the first word is placed, and how far apart the rest are
    filler_at = first + len(c["words"]) * every + 0.3
    out = 12.4  # everything fades, to start again

    def shown(at, until=out):
        return f.cue(
            [
                (0, "opacity:0"),
                (at, "opacity:0"),
                (at + 0.25, "opacity:1"),
                (until, "opacity:1"),
                (until + 0.5, "opacity:0"),
            ]
        )

    def popped(at):
        return f.cue([(0, "opacity:0;transform:scale(.6)"), (at, "opacity:0;transform:scale(.6)"),
                      (at + 0.3, "opacity:1;transform:scale(1.06)"), (at + 0.45, "opacity:1;transform:scale(1)"),
                      (out, "opacity:1;transform:scale(1)"), (out + 0.5, "opacity:0;transform:scale(1)")], origin=True)  # fmt: skip

    f.eyebrow(x0, y0 - 14, f"Chunk (0, 0) · {c['name']} · {c['theme']}")
    f.rect(x0 - 6, y0 - 6, 12 * cell + 12, 12 * cell + 12, r=8, fill=t.panel, stroke=t.rule)
    in_words = set()
    for i, w in enumerate(c["words"]):
        dx, dy = DIRS[w["d"]]
        cells = [(w["x"] + dx * k, w["y"] + dy * k) for k in range(len(w["w"]))]
        in_words.update(cells)
        with f.group(popped(first + i * every)):
            circle_word(f, x0, y0, cell, w["x"], w["y"], len(w["w"]), w["d"], hue)
        with f.group(shown(first + i * every + 0.1)):
            rows = [" " * 12 for _ in range(12)]
            for col, row in cells:
                rows[row] = rows[row][:col] + c["letters"][row][col] + rows[row][col + 1 :]
            grid_letters(f, x0, y0, cell, rows, 13.5)
    with f.group(shown(filler_at)):
        grid_letters(f, x0, y0, cell, ["".join(" " if (col, row) in in_words else ch for col, ch in enumerate(line))
                                       for row, line in enumerate(c["letters"])], 13.5)  # fmt: skip

    # The words it hid, in the order it placed them.
    ly = y0 + 12 * cell + 32
    f.eyebrow(x0, ly, f"{len(c['words'])} hidden words, in the order placed")
    for i, w in enumerate(c["words"]):
        col, row = i % 2, i // 2
        wx, wy = x0 + col * 160, ly + 22 + row * 20
        with f.group(shown(first + i * every)):
            f.rect(wx, wy - 11, 9, 14, r=2, fill=t.mark(hue), opacity=0.9)
            ww = f.text(wx + 16, wy, w["w"], "mono5", 11)
            f.text(wx + 22 + ww, wy + 0.5, ARROWS[w["d"]], "ui6", 12.5, t.muted)

    # The steps, each marked while it happens.
    sx, sw = 380, 388
    y = 128
    tops = [y]

    def now(top, start, end):
        with f.group(
            f"motion {f.cue([(0, 'opacity:0'), (start, 'opacity:0'), (start + 0.2, 'opacity:1'), (end, 'opacity:1'), (end + 0.2, 'opacity:0')])}"
        ):
            f.rect(sx - 12, top - 14, 4, 22, r=2, fill=t.accent)

    y = step(f, sx, y, "1", "One seed", "SEED = 0x1E77E2. A chunk's coordinates are hashed with it, and the "
             "hash seeds the generator that makes every choice in that chunk.", sw) + 12  # fmt: skip
    tops.append(y)
    y = step(f, sx, y, "2", "Chunks and territories", "A chunk is 12 × 12 cells and a territory 4 × 4 chunks, "
             "48 × 48 cells. Territory (rx, ry) has theme (rx + 15·ry) mod 225: (0, 0) is Festivals.", sw - 70) + 12  # fmt: skip
    # A territory's 16 chunks, this one lit.
    for r in range(4):
        for q in range(4):
            on = r == 0 and q == 0
            f.rect(sx + sw - 52 + q * 13, y - 74 + r * 13, 11, 11, r=1.5, fill=t.mark(hue) if on else t.panel,
                   stroke=t.rule if not on else None, sw=0.8)  # fmt: skip
    tops.append(y)
    y = step(f, sx, y, "3", "A deck per territory", "Its theme's 144 to 184 words, shuffled by the territory's own "
             "seed. Each chunk is dealt the next 9 cards and places them in order until it has its 6 to 8, so no "
             "word turns up twice in a territory.", sw) + 12  # fmt: skip
    rose_y = y
    tops.append(y)
    y = step(f, sx, y, "4", "Eight directions", "Weighted to read forwards: east and south 3 in 14 each, "
             "south-east and north-east 2, the rest 1. Up to 40 tries a word; words may cross where their "
             "letters agree.", sw - 96) + 12  # fmt: skip
    # The rose: each direction's share of the 14.
    rcx, rcy = sx + sw - 42, rose_y + 26
    for d, wt in enumerate([3, 2, 3, 1, 1, 1, 1, 2]):
        dx, dy = DIRS[d]
        n = math.hypot(dx, dy)
        length = 10 + wt * 10
        f.line(rcx, rcy, rcx + dx / n * length, rcy + dy / n * length, t.mark(hue), 3.2)
        f.text(rcx + dx / n * (length + 9), rcy + dy / n * (length + 9) + 3.5, str(wt), "ui6", 9.5, t.muted,
               "middle")  # fmt: skip
    f.circle(rcx, rcy, 3, fill=t.ink)
    # Each word's direction lights on the rose as it's placed.
    for i, w in enumerate(c["words"]):
        dx, dy = DIRS[w["d"]]
        n, at = math.hypot(dx, dy), first + i * every
        length = 10 + [3, 2, 3, 1, 1, 1, 1, 2][w["d"]] * 10
        with f.group(
            f"motion {f.cue([(0, 'opacity:0'), (at, 'opacity:0'), (at + 0.1, 'opacity:1'), (at + every - 0.1, 'opacity:1'), (at + every, 'opacity:0')])}"
        ):
            f.line(rcx, rcy, rcx + dx / n * length, rcy + dy / n * length, t.accent, 4.2)
    tops.append(y)
    y = step(f, sx, y, "5", "Filler", "Every other cell gets a letter drawn from AEIOUNRSTL and the chunk's own "
             "words, so near-misses are everywhere.", sw) + 12  # fmt: skip
    tops.append(y)
    y = step(f, sx, y, "6", "Bonus words", "Any real word of 6 or more letters the filler spells by chance counts "
             "too: about 20 a territory. Down to 4 letters there would be some 530.", sw)  # fmt: skip
    for top, (start, end) in zip(tops, [(0.2, 0.9), (0.9, 1.6), (1.6, first), (first, filler_at - 0.3),
                                        (filler_at - 0.2, filler_at + 1.2), (filler_at + 1.2, out)]):  # fmt: skip
        now(top, start, end)

    # The server checks every claim with the same code.
    by = 588
    f.eyebrow(32, by, "The survey's server runs the same code, and checks every claim (checkClaim)")
    checks = ["one of the 28,845 words", "starts in this sector", "each letter matches the map",
              "a hidden word, or 6+ letters"]  # fmt: skip
    bw, gap = 164, 26
    for i, label in enumerate(checks):
        bx = 32 + i * (bw + gap)
        f.rect(bx, by + 12, bw, 40, r=6, fill=t.panel, stroke=t.rule)
        f.text(bx + 12, by + 30, f"{i + 1}", "display", 15, t.accent)
        f.para(bx + 26, by + 29, label, bw - 34, "ui5", 11, lh=1.25)
        if i < 3:
            f.arrow([(bx + bw + 4, by + 32), (bx + bw + gap - 4, by + 32)], t.muted, 1.3, head=5)
    f.text(32, by + 74, "A test runs the game's generator and the Worker's copy side by side, so they can't drift.",
           "ui", 11, t.muted)  # fmt: skip
    f.footer("Sources: worker/src/letterfield-world.js · worker/src/survey.js checkClaim · worker/SURVEY.md")
    return f


@figure(
    "theme-layout",
    "map",
    "225 themes, laid out so neighbours differ",
    "Each territory takes one of 225 themes, by a formula rather than a table: territory (rx, ry) gets theme "
    "(rx + 15·ry) mod 225, so a theme comes round again only 15 territories away in any direction, as far "
    "apart as 225 themes can be. The order of the themes in that list was found by a search, so that each "
    "territory's eight neighbours differ from it by at least 30 degrees of hue, are of another kind (no two "
    "bird themes side by side) and share none of its words. Here are the 900 territories nearest the origin, "
    "each in its theme's colour, with every Festivals territory outlined.",
    "A mosaic of 30 by 30 small squares, each a territory around the map's origin, filled with its theme's "
    "colour so that no two neighbours look alike. Four squares are outlined in ink: the Festivals "
    "territories at (0, 0), (0, -15), (-15, 1) and (-15, -14), showing that a theme repeats only 15 "
    "territories away; a dashed square marks the 15 by 15 block that each theme has to itself. On the right, "
    "the formula, and the origin's 3 by 3 neighbourhood with its nine themes: Hafnium Basin (Periodic Table) "
    "to the west, Swordtail Vale (Pet Shop) to the east, Pennette Steppe (Pasta) to the north and Sodden "
    "Wold (Campsite) to the south, with Menorah Hollow (Festivals) in the middle.",
    [
        ("225 themes; territory (rx, ry) has theme (rx + 15·ry) mod 225", "letterfield-world.js regionTheme, LAT_B"),
        (
            "A theme comes round again only 15 territories away; each needs a 15 × 15 square to itself",
            "worker/SURVEY.md, 'A new map'",
        ),
        (
            "The order of themes was searched (bench/layout.mjs) so the eight neighbours differ by 30° of hue or more, "
            "in kind (no two bird themes side by side), and share no words",
            "worker/SURVEY.md; worker/bench/layout.mjs",
        ),
        (
            "Festivals (theme 0) is at (0, 0), (0, -15), (-15, 1) and (-15, -14) within -15..14",
            "computed with regionTheme",
        ),
        (
            "The origin's neighbours and names: Cater Shallows, Pennette Steppe, Danger Court, Hafnium Basin, Menorah "
            "Hollow, Swordtail Vale, Caress Gate, Sodden Wold, Cimabue Meadows",
            "letterfield-world.js regionName",
        ),
        (
            "A word can be in up to three themes: 24,170 words are in one theme, 3,972 in two, 703 in three",
            "worker/SURVEY.md; counted from THEME_DATA",
        ),
    ],
)
def theme_layout(t: Theme) -> Fig:
    f = Fig(t, 720)
    f.header("Letterfield · the map", "225 themes, laid out so neighbours differ")
    themes = world("themes")
    terr = world("territories", -15, -15, 14, 14)
    x0, y0, cell = 32, 118, 18
    by_hue: dict[int, list[str]] = {}
    for rx, ry, _th, hue, _, _ in terr:
        x, y = x0 + (rx + 15) * cell, y0 + (ry + 15) * cell
        by_hue.setdefault(hue, []).append(f"M{x + 1} {y + 1}h{cell - 2}v{cell - 2}h{2 - cell}z")
    for hue, parts in by_hue.items():
        f.path("".join(parts), fill=t.mark(hue), fill_opacity=0.62 if t.dark else 0.72)
    # Festivals, wherever it comes round, and the square it has to itself.
    homes = [(rx, ry) for rx, ry, th, *_ in terr if th == 0]
    f.rect(x0 + 8 * cell, y0 + 8 * cell, 15 * cell, 15 * cell, fill="none", stroke=t.ink, sw=1.4, dash="5 4")
    for rx, ry in homes:
        x, y = x0 + (rx + 15) * cell, y0 + (ry + 15) * cell
        f.rect(x - 1.5, y - 1.5, cell + 3, cell + 3, r=2, fill="none", stroke=t.ink, sw=2.4)
    ox, oy = x0 + 15 * cell, y0 + 15 * cell
    f.label(ox + cell + 6, oy + 13, "(0, 0) Festivals", "ui6", 10.5, t.ink, pad=3)
    f.text(x0, y0 + 30 * cell + 18, "rx -15", "mono", 8.5, t.muted)
    f.text(x0 + 30 * cell, y0 + 30 * cell + 18, "14", "mono", 8.5, t.muted, "end")
    f.text(x0 + 15 * cell + cell / 2, y0 + 30 * cell + 18, "0", "mono", 8.5, t.muted, "middle")

    # The rule, and the origin's neighbours.
    rx0 = 596
    f.eyebrow(rx0, 126, "The rule")
    f.text(rx0, 154, "(rx + 15·ry) mod 225", "mono5", 12.5)
    y = f.para(rx0, 176, "A theme comes round again only 15 territories away in any direction: each has a "
               "15 × 15 square to itself (dashed).", 172, "ui", 11, fill=t.muted)  # fmt: skip
    y = f.para(rx0, y + 8, "The themes' order was found by a search: every territory's eight neighbours differ "
               "from it by 30° of hue or more, are another kind (no two bird themes together), and share none "
               "of its words.", 172, "ui", 11, fill=t.muted)  # fmt: skip
    f.eyebrow(rx0, y + 18, "Around the origin")
    near = {(rx, ry): (th, hue, name) for rx, ry, th, hue, _, name in world("territories", -1, -1, 1, 1)}
    gy = y + 30
    for (rx, ry), (th, hue, _name) in near.items():
        cx, cy = rx0 + (rx + 1) * 58, gy + (ry + 1) * 58
        f.rect(cx, cy, 54, 54, r=5, fill=t.mark(hue), fill_opacity=0.62 if t.dark else 0.72,
               stroke=t.ink if (rx, ry) == (0, 0) else None, sw=2)  # fmt: skip
        f.para(cx + 5, cy + 14, themes[th][0], 46, "ui6", 8.6, lh=1.15, fill=t.paper if not t.dark else t.paper)
    f.footer("Sources: worker/src/letterfield-world.js regionTheme · worker/SURVEY.md 'A new map' · bench/layout.mjs")
    return f


@figure(
    "universe",
    "server",
    "The universe, cut into sectors",
    "The map goes on for a billion cells each way, but the part everyone charts together, the universe, is "
    "the middle 100 × 100 territories: 1,119,752 hidden words. The server cuts it into 625 sectors of 4 × 4 "
    "territories, 192 × 192 cells each, and every sector is its own Durable Object. The colours are the "
    "territories' themes; the solid patches near the middle are what the survey had charted on 20 November "
    "2026, from its public API, with a star on each territory that has gone supernova.",
    "A square map of 100 by 100 small territories, faintly tinted in their themes' colours, crossed by a "
    "grid of 25 by 25 sectors. Near the centre a small cluster of territories is filled in: the words "
    "charted so far. An inset on the right enlarges the 8 by 8 territories around the origin, showing four "
    "sectors' boundaries, how much of each territory is charted, and stars on the seven territories inside "
    "the universe that have gone supernova. Labels give the sizes: a territory is 48 by 48 cells, a sector "
    "4 by 4 territories and one Durable Object, and the universe 625 sectors; and the live count: 907 of "
    "1,119,752 words charted.",
    [
        (
            "The universe is sectors -12 to 12 each way (AREA = 12): 625 sectors, 100 × 100 territories, territories "
            "-48 to 51",
            "worker/src/survey.js AREA; worker/src/achievements.js UNIVERSE_EDGE",
        ),
        ("It hides 1,119,752 words (AREA_WORDS), recounted by a test", "worker/src/survey.js; recounted with data.mjs"),
        ("A sector is 4 × 4 territories, 192 × 192 cells (SECTOR = RC × TERR)", "worker/src/survey.js SECTOR"),
        ("The game's map runs to ±1e9 cells (LIMIT)", "worker/src/survey.js LIMIT"),
        (
            "907 of 1,119,752 charted and 24 territories with charted words in the universe on 20 Nov 2026 at 23:35 UTC; "
            "8 supernovas in the log, 7 inside the universe",
            "GET /v1/survey/world, /v1/survey/log/novas (data/survey.json)",
        ),
        (
            "Sectors outside the universe don't report to the Atlas, so their words don't count toward its total",
            "worker/src/survey.js maybeReport, inArea; worker/SURVEY.md",
        ),
    ],
)
def universe(t: Theme) -> Fig:
    f = Fig(t, 650)
    f.header("Letterfield · the shared survey", "The universe, cut into sectors")
    snap = json.loads((HERE / "data" / "survey.json").read_text())
    charted = {(rx, ry): n for rx, ry, n in snap["world"]["territories"]}
    novas = {(n["rx"], n["ry"]) for n in snap["novas"]}
    terr = world("territories", -48, -48, 51, 51)
    total = {(rx, ry): n for rx, ry, _, _, n, _ in terr}
    x0, y0, cell = 32, 118, 4.8
    tints: dict[int, list[str]] = {}
    for rx, ry, _, hue, _, _ in terr:
        x, y = x0 + (rx + 48) * cell, y0 + (ry + 48) * cell
        tints.setdefault(hue, []).append(f"M{x:.1f} {y:.1f}h{cell:.1f}v{cell:.1f}h{-cell:.1f}z")
    for hue, parts in tints.items():
        f.path("".join(parts), fill=t.tint(hue), fill_opacity=0.16 if t.dark else 0.22)
    size = 100 * cell
    for i in range(26):
        v = i * 4 * cell
        f.line(x0 + v, y0, x0 + v, y0 + size, t.muted, 0.7, opacity=0.55)
        f.line(x0, y0 + v, x0 + size, y0 + v, t.muted, 0.7, opacity=0.55)
    f.rect(x0, y0, size, size, fill="none", stroke=t.muted, sw=1)
    for (rx, ry), n in charted.items():
        x, y = x0 + (rx + 48) * cell, y0 + (ry + 48) * cell
        f.rect(x, y, cell, cell, fill=t.ink, opacity=0.35 + 0.65 * n / total[(rx, ry)])
    # The inset: 8 × 8 territories around the origin, 2 × 2 sectors.
    ix, iy, ic = 32 + size + 40, 150, 25
    a, b = -4, 4
    f.rect(x0 + (a + 48) * cell, y0 + (a + 48) * cell, 8 * cell, 8 * cell, fill="none", stroke=t.accent, sw=1.4)
    f.arrow([(x0 + (b + 48) * cell + 2, y0 + (a + 48) * cell), (ix - 8, iy + 10)], t.accent, 1.2, head=5)
    f.eyebrow(ix, iy - 12, "Around the origin: 4 sectors")
    for rx, ry, _, hue, n, _name in world("territories", a, a, b - 1, b - 1):
        x, y = ix + (rx - a) * ic, iy + (ry - a) * ic
        f.rect(x + 0.5, y + 0.5, ic - 1, ic - 1, fill=t.tint(hue), fill_opacity=0.32 if t.dark else 0.36)
        got = charted.get((rx, ry), 0)
        if got:
            h = (ic - 1) * got / n
            f.rect(x + 0.5, y + 0.5 + ic - 1 - h, ic - 1, h, fill=t.mark(hue), opacity=0.9)
        if (rx, ry) in novas:
            star(f, x + ic / 2, y + ic / 2, 6.5, t.paper if not t.dark else t.ink, t.ink if not t.dark else t.paper)
    for i in range(3):
        v = i * 4 * ic
        f.line(ix + v, iy, ix + v, iy + 8 * ic, t.ink, 1.6)
        f.line(ix, iy + v, ix + 8 * ic, iy + v, t.ink, 1.6)
    f.text(ix + 4 * ic, iy + 8 * ic + 16, "0", "mono", 8.5, t.muted, "middle")
    f.text(ix - 6, iy + 4 * ic + 3, "0", "mono", 8.5, t.muted, "end")
    # The key.
    ky = iy + 8 * ic + 40
    w = snap["world"]
    rows = [("territory", "48 × 48 cells, one theme"), ("sector", "4 × 4 territories, 192 × 192 cells: one Durable Object"),
            ("universe", "25 × 25 sectors: 625 objects, 1,119,752 hidden words"),
            ("beyond", "the map runs on to a billion cells each way; sectors out there don't report")]  # fmt: skip
    for k, v in rows:
        f.text(ix, ky, k, "ui6", 11.5)
        ky = f.para(ix + 64, ky, v, 768 - ix - 64, "ui", 10.5, lh=1.28, fill=t.muted) + 6
    inside = sum(1 for n in snap["novas"] if -48 <= n["rx"] <= 51 and -48 <= n["ry"] <= 51)
    f.rect(ix, ky + 2, 768 - ix, 52, r=6, fill=t.panel, stroke=t.rule)
    f.text(ix + 12, ky + 24, f"{w['charted']:,} of {w['total']:,} charted", "display", 19)
    pct = 100 * w["charted"] / w["total"]
    f.text(ix + 12, ky + 43, f"{pct:.2f}% · {len(charted)} territories · {inside} supernovas", "ui", 10.5,
           t.muted)  # fmt: skip
    f.text(x0, y0 + size + 18, "100 × 100 territories · each line is a sector edge", "ui", 10.5, t.muted)
    f.footer(f"Sources: worker/src/survey.js (AREA, SECTOR) · GET /v1/survey/world at {snap['at']}")
    return f


def star(f: Fig, x: float, y: float, r: float, fill: str, stroke: str) -> None:
    """The log's supernova star: four points and a dot."""
    pts = []
    for i in range(8):
        a = math.pi / 4 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.32
        pts.append(f"{x + rr * math.cos(a):.2f} {y + rr * math.sin(a):.2f}")
    f.path("M" + " L".join(pts) + "Z", fill=fill, stroke=stroke, sw=1)


# =============================================================================
# The big picture
# =============================================================================
@figure(
    "big-picture",
    "server",
    "The big picture",
    "Letterfield is one HTML file on GitHub Pages. Everything shared lives behind one Cloudflare Worker at "
    "api.games.michaelwarkentin.com, which holds no state itself: it hashes the player's address, checks the "
    "per-address limits, and hands each request to the Durable Object that owns it. Each of the map's sectors "
    "is its own object, with its own SQLite storage and the WebSockets of everyone looking at it; one Atlas "
    "keeps the universe's totals; guilds and linked players get objects of their own. Two D1 databases keep what "
    "has to be queried across the whole map: the survey's log, and one with Letterfield's link codes, recovery "
    "codes and definitions. A second Worker draws the link-preview cards.",
    "Architecture diagram. At the top, three pages in the browser served by GitHub Pages: the game "
    "letterfield.html, the survey log and the timelapse. Arrows lead down to one Cloudflare Worker, "
    "games-leaderboard, which lists its routes and its per-address checks. Below it are Durable Objects: "
    "Sector (625 in the universe, more beyond), Atlas (one), Guild and Player, with arrows from sectors to "
    "the Atlas (reports every 10 seconds at most), to guilds (membership checks) and to each other (supernovas "
    "and emotes). Below them, two D1 databases: games-survey-log, written by sectors from an alarm, and "
    "games-leaderboard, with the link codes, recovery codes and definitions. On the right, the games-share Worker with its R2 bucket of cards, bound "
    "directly to the Sector and Atlas classes. Along the bottom, the outside services: Turnstile, Sentry, "
    "Counterscale and Wiktionary with Wikipedia.",
    [
        (
            "The survey's Durable Object classes: Sector and Atlas (v2), Guild (v3) and Player (v4), all SQLite-backed",
            "worker/wrangler.toml [[migrations]]",
        ),
        (
            "Two D1 databases: games-survey-log (binding LOG_DB), and games-leaderboard (binding DB), where "
            "Letterfield keeps its definitions, link codes and recovery codes",
            "worker/wrangler.toml [[d1_databases]]",
        ),
        (
            "Rate-limit bindings: SURVEY_CLAIMS 6/60 s, SURVEY_JOINS 120/60 s, SURVEY_EMOTES 20/60 s, "
            "DEFINE_LOOKUPS 20/60 s",
            "worker/wrangler.toml [[ratelimits]]",
        ),
        (
            "The router hands each path to its handler: the survey, surveyors, guilds, links, players, recovery, "
            "badges, the log and definitions",
            "worker/src/index.js fetch()",
        ),
        ("625 sectors in the universe: sectors -12 to 12 each way (AREA = 12)", "worker/src/survey.js AREA"),
        (
            "The share Worker binds Sector and Atlas from games-leaderboard and the Worker itself as LOG, and keeps "
            "cards in R2 (games-share-cards)",
            "share/wrangler.toml",
        ),
        ("The game is one file, letterfield.html: 8,248 lines at commit 44fe976 (PR #126)", "wc -l letterfield.html"),
        (
            'Turnstile passes are handed out but not required (TURNSTILE_REQUIRED = "false")',
            "worker/wrangler.toml [vars]; worker/TURNSTILE.md",
        ),
        ("Definitions come from Wiktionary or Wikipedia once per word and are kept in D1", "worker/src/define.js"),
    ],
)
def big_picture(t: Theme) -> Fig:
    f = Fig(t, 660)
    k = t.kinds
    f.header("Letterfield · the shared survey", "The big picture")
    L, R, M = 32, 768, 572  # left, right, and where the right-hand column starts
    f.text(R, 52, "games.michaelwarkentin.com/letterfield", "mono", 8.5, t.muted, "end")

    # The browser.
    y = 118
    f.eyebrow(L, y, "In the browser · GitHub Pages · offline with sw.js")
    y += 9
    pages = [("letterfield.html", "the game: one file, 8,248 lines", 214),
             ("letterfield-log.html", "the survey log", 150), ("letterfield-timelapse.html", "the replay", 156)]  # fmt: skip
    x, at = L, {}
    for name, sub, w in pages:
        cell_box(f, x, y, w, 46, name, "browser", sub, size=12)
        at[name] = (x, w)
        x += w + 8

    # The Worker.
    wy, wh = 222, 92
    gx, _ = at["letterfield.html"]
    f.arrow([(gx + 54, y + 46), (gx + 54, wy)], k["browser"], 1.6)
    f.text(gx + 62, y + 70, "a WebSocket per sector,", "ui5", 10, t.ink)
    f.text(gx + 62, y + 83, "at most 4 at once", "ui5", 10, t.ink)
    for name in ("letterfield-log.html", "letterfield-timelapse.html"):
        x0, w = at[name]
        f.arrow([(x0 + 30, y + 46), (x0 + 30, wy)], k["browser"], 1.6, dash="1 4")
    lx, _ = at["letterfield-log.html"]
    f.text(lx + 38, y + 70, "HTTPS GETs, cached in", "ui5", 10, t.ink)
    f.text(lx + 38, y + 83, "the browser and at the edge", "ui5", 10, t.ink)

    f.rect(L, wy, M - 20 - L, wh, r=7, fill=t.panel, stroke=k["worker"], sw=1.4)
    f.text(L + 14, wy + 22, "games-leaderboard", "ui6", 14)
    f.text(L + 18 + f.width("games-leaderboard", "ui6", 14), wy + 22, "Worker · api.games.michaelwarkentin.com",
           "ui", 11, t.muted)  # fmt: skip
    routes = ["/v1/survey/<sx>/<sy>  /v1/survey/world  /v1/survey/surveyors",
              "/v1/survey/log/…  /v1/survey/guilds  /v1/player/sync  /v1/link",
              "/v1/recovery  /v1/survey/badges  /v1/define"]  # fmt: skip
    for i, r in enumerate(routes):
        f.text(L + 14, wy + 42 + i * 13, r, "mono", 8.3, t.ink)
    f.text(L + 14, wy + 84, "stateless: hashes the address, checks limits and the pass, forwards", "ui", 10, t.muted)

    # The share Worker, beside it.
    f.eyebrow(M, 118, "Link previews")
    cell_box(f, M, 127, R - M, 46, "games-share", "worker", "share.michaelwarkentin.com", size=12)
    cell_box(f, M, 181, R - M, 34, "R2: games-share-cards", "store", None, size=11)
    f.para(M, 232, "Draws link-preview cards with resvg. Binds Sector and Atlas directly (/claim, /nova, "
           "/totals) and the log through a service binding.", R - M, "ui", 10, lh=1.35, fill=t.muted)  # fmt: skip

    # Durable Objects.
    dy = 372
    objs = [("Sector", "× 625 in the universe", 196), ("Atlas", "× 1 for the universe", 150),
            ("Guild", "× 1 a guild", 150), ("Player", "× 1 a linked player", 0)]  # fmt: skip
    ox, ob = L, {}
    for name, sub, w in objs:
        w = w or R - ox
        cell_box(f, ox, dy, w, 46, name, "object", sub, size=12.5)
        ob[name] = (ox, w)
        ox += w + 8
    for name in ("Sector", "Atlas", "Guild"):
        ox, w = ob[name]
        f.arrow([(ox + w / 2, wy + wh), (ox + w / 2, dy)], k["worker"], 1.3)
    # Player sits past the Worker's right edge: its arrow leaves the side, under the share Worker's note.
    ox, w = ob["Player"]
    f.arrow([(M - 20, wy + wh - 22), (ox + w / 2, wy + wh - 22), (ox + w / 2, dy)], k["worker"], 1.3)
    f.eyebrow(L, dy - 12, "Durable Objects · one thread and its own SQLite each", knock=True)
    sx, sw_ = ob["Sector"]
    ax, aw = ob["Atlas"]
    gx2, gw2 = ob["Guild"]
    f.arrow([(sx + sw_ - 26, dy + 46), (sx + sw_ - 26, dy + 64), (ax + aw / 2, dy + 64), (ax + aw / 2, dy + 46)],
            k["object"], 1.3)  # fmt: skip
    f.arrow([(sx + 36, dy + 46), (sx + 36, dy + 64), (sx + 76, dy + 64), (sx + 76, dy + 46)], k["object"], 1.3)
    f.arrow([(sx + sw_ - 10, dy + 46), (sx + sw_ - 10, dy + 84), (gx2 + gw2 / 2, dy + 84), (gx2 + gw2 / 2, dy + 46)],
            k["object"], 1.3, dash="1 4")  # fmt: skip
    f.label(sx + 82, dy + 62, "/near")
    f.label(ax + aw / 2 + 8, dy + 62, "reports, ≤ every 10 s")
    f.label(gx2 + gw2 / 2 + 8, dy + 82, "membership checks, every 15 min while playing")

    # D1.
    by = 500
    cell_box(f, L, by, 262, 46, "games-survey-log", "store", "every word charted, counts, supernovas", size=12.5)
    cell_box(f, L + 270, by, R - L - 270, 46, "games-leaderboard", "store",
             "link and recovery codes, definitions", size=12.5)  # fmt: skip
    f.arrow([(sx + 16, dy + 46), (sx + 16, by)], k["object"], 1.3)
    f.eyebrow(L, by - 12, "D1 · SQLite to query across the map", knock=True)
    f.label(sx + 24, by - 32, "an alarm copies new claims, ≤ 30 s later")

    # The outside.
    oy = 580
    f.eyebrow(L, oy - 12, "Outside")
    outside = [("Turnstile", "a pass to join, not required"), ("Sentry", "errors and replays"),
               ("Counterscale", "page views"), ("Wiktionary, Wikipedia", "definitions, once a word")]  # fmt: skip
    ow = (R - L - 3 * 8) / 4
    for i, (name, sub) in enumerate(outside):
        cell_box(f, L + i * (ow + 8), oy, ow, 40, name, "other", sub, size=11.5)
    f.h = 660
    # It moves: the game's messages reach their sector through the Worker, the log page's reads stop at the
    # Worker's cache, the sector reports to the Atlas, tells a neighbour, and copies its claims to D1.
    f.animate(8)
    via = [(gx + 54, y + 46), (gx + 54, wy + wh - 6), (sx + sw_ / 2 - 30, wy + wh + 14), (sx + sw_ / 2 - 30, dy)]
    f.travel(via, 0.2, 1.3, k["browser"])
    f.glow(sx, dy, sw_, 46, 1.3, 0.7, k["object"])
    f.travel([(lx + 30, y + 46), (lx + 30, wy + 4)], 1.0, 1.6, k["browser"])
    f.glow(L, wy, M - 20 - L, wh, 1.6, 0.6, k["worker"], r=7)
    f.travel([(sx + sw_ - 26, dy + 46), (sx + sw_ - 26, dy + 64), (ax + aw / 2, dy + 64), (ax + aw / 2, dy + 46)],
             2.0, 2.8, k["object"])  # fmt: skip
    f.glow(ax, dy, aw, 46, 2.8, 0.7, k["object"])
    f.travel(via, 3.4, 4.5, k["browser"])
    f.travel([(sx + 36, dy + 46), (sx + 36, dy + 64), (sx + 76, dy + 64), (sx + 76, dy + 46)], 4.6, 5.2, k["object"])
    f.travel([(sx + 16, dy + 46), (sx + 16, by)], 5.6, 6.3, k["store"])
    f.glow(L, by, 262, 46, 6.3, 0.8, k["store"])
    f.footer("Sources: worker/wrangler.toml · worker/src/index.js · share/wrangler.toml · AGENTS.md")
    return f


# =============================================================================
# The server
# =============================================================================
def table_box(f: Fig, x: float, y: float, w: float, name: str, cols: str, note: str | None = None) -> float:
    """A SQLite table as a small card: its name and columns; returns the y below it."""
    t = f.t
    lines = f.wrap(cols, w - 20, "mono", 8.2)
    h = 26 + 11.5 * len(lines) + (14 if note else 0)
    f.rect(x, y, w, h, r=5, fill=t.field if not t.dark else t.paper, stroke=t.rule)
    f.text(x + 10, y + 16, name, "mono5", 9.5, t.kinds["store"])
    for i, line in enumerate(lines):
        f.text(x + 10, y + 30 + i * 11.5, line, "mono", 8.2, t.ink)
    if note:
        f.text(x + 10, y + h - 7, note, "ui", 9.5, t.muted)
    return y + h


def pill(f: Fig, x: float, y: float, text: str, fill: str | None = None, ink: str | None = None,
         size: float = 9.5, font: str = "ui5") -> float:  # fmt: skip
    """A small rounded label; returns its width."""
    w = f.width(text, font, size) + 14
    f.rect(x, y - size - 3.5, w, size + 8.5, r=(size + 8.5) / 2, fill=fill or f.t.paper, stroke=f.t.rule)
    f.text(x + 7, y, text, font, size, ink or f.t.ink)
    return w


@figure(
    "sector-anatomy",
    "server",
    "Inside one sector",
    "A sector is one Durable Object: a single thread with its own SQLite storage, holding the claims for 16 "
    "territories and the WebSockets of everyone looking at them. Because only one message runs inside it at "
    "a time, 'first to claim wins' is a plain INSERT … ON CONFLICT DO NOTHING. Sockets use the WebSocket "
    "Hibernation API, so a quiet sector can be evicted from memory while its players stay connected; "
    "anything it must still know after waking lives in storage or in each socket's attachment. And there "
    "are almost no timers, because a pending timer keeps a Durable Object awake and billed: owed positions "
    "and reports go out with the next message instead.",
    "A large panel labelled Sector 0,0, one Durable Object, in three columns. Left: up to 750 hibernating "
    "WebSockets, at most 40 from one address, each with an attachment holding who the player is, where "
    "they look and their claim allowance. Middle: its SQLite tables: claims (keyed by word and place, with "
    "an index by time), logged, novas, owed, relayed, guild_names and map. Right: what it keeps only in "
    "memory and rebuilds after waking: the players, every claim as JSON, charted and hidden counts for its "
    "16 territories, the claim batch, the addresses past today's cap, and each socket's allowances. Along "
    "the bottom: the messages it takes and sends, and its only timers: a 200 ms batch, a presence timer "
    "when someone leaves a quiet sector, and an alarm that copies claims to the log.",
    [
        ("MAX_PLAYERS = 750 sockets a sector; ADDRESS_SOCKETS = 40 from one address", "worker/src/survey.js"),
        (
            "Tables: claims (key PRIMARY KEY, w, x, y, d, s, initials, at, guild) WITHOUT ROWID with claims_by_time "
            "(at, key); logged; novas (PK rx, ry); relayed; owed; guild_names; map",
            "worker/src/survey.js Sector constructor",
        ),
        (
            "First claim wins with INSERT … ON CONFLICT (key) DO NOTHING RETURNING key, run with nothing awaited",
            "worker/src/survey.js Sector.claim",
        ),
        (
            "Hibernation API; players kept in memory too, positions written to the attachment at most every 5 s "
            "(SAVE_POS_MS)",
            "worker/src/survey.js; worker/SURVEY.md 'Attachments are expensive'",
        ),
        (
            "Claims go out in batches at most every 200 ms (BATCH_MS); positions at most once a second (PRESENCE_MS), "
            "up to 64 (PRESENCE_MAX) with a head count",
            "worker/src/survey.js",
        ),
        (
            "A presence timer only when someone leaves a sector with fewer than 32 sockets (QUIET)",
            "worker/src/survey.js",
        ),
        (
            "The log alarm: LOG_MS = 30 s; retries back off up to 10 minutes",
            "worker/src/survey-log.js; survey.js alarm()",
        ),
        (
            "Hidden words per territory worked out from the map in about 3 ms, once per waking",
            "worker/src/survey.js hiddenCounts",
        ),
        (
            "Messages in: me, pos, claim, here, emote; out: hello, claimed, taken, signed, error, presence, emote, "
            "emoted, guild, world, nova, full",
            "worker/src/survey.js header comment",
        ),
    ],
)
def sector_anatomy(t: Theme) -> Fig:
    f = Fig(t, 680)
    f.header("Letterfield · the server", "Inside one sector")
    k = t.kinds
    x0, y0, w0, h0 = 32, 112, 736, 380
    f.rect(x0, y0, w0, h0, r=10, fill=t.panel, stroke=k["object"], sw=1.6)
    f.text(x0 + 16, y0 + 26, "Sector 0,0", "ui6", 15)
    f.text(x0 + 20 + f.width("Sector 0,0", "ui6", 15), y0 + 26, "one Durable Object · territories (0, 0) to (3, 3) · "
           "cells 0 to 191 each way", "ui", 11, t.muted)  # fmt: skip
    cols = [(x0 + 16, 214), (x0 + 246, 250), (x0 + 512, 208)]
    heads = [("WebSockets", "hibernating, up to 750"), ("SQLite storage", "survives eviction"),
             ("In memory", "rebuilt after waking")]  # fmt: skip
    for (cx, _cw), (h, sub) in zip(cols, heads):
        f.eyebrow(cx, y0 + 54, h)
        f.text(cx, y0 + 70, sub, "ui", 10, t.muted)

    # The sockets, each with its attachment.
    cx, cw = cols[0]
    for i in range(5):
        yy = y0 + 84 + i * 30
        f.rect(cx, yy, cw, 24, r=12, fill=t.paper, stroke=t.rule)
        f.circle(cx + 13, yy + 12, 4.5, fill=k["browser"])
        label = ["you · ZED", "KIM", "SIS", "a phone, no initials yet", "…"][i]
        f.text(cx + 24, yy + 16, label, "ui5", 10.5, t.ink if i < 4 else t.muted)
    ay = y0 + 84 + 5 * 30 + 6
    f.text(cx, ay + 10, "each socket's attachment:", "ui5", 10, t.ink)
    for i, line in enumerate(["{id, pid, sx, sy, address,", " initials, x, y, moved, saved,", " tokens, refilled, joined,",
                              " guilds: [{code, tag, lid}]}"]):  # fmt: skip
        f.text(cx, ay + 26 + i * 12, line, "mono", 8.2, t.muted)
    f.para(cx, ay + 86, "At most 40 from one address. A full sector still answers {t: 'full'}, then closes.", cw,
           "ui", 10, fill=t.muted)  # fmt: skip

    # Storage.
    cx, cw = cols[1]
    yy = y0 + 84
    yy = table_box(f, cx, yy, cw, "claims", "key PK, w, x, y, d, s, initials, at, guild · WITHOUT ROWID",
                   "+ claims_by_time (at, key), for the log") + 7  # fmt: skip
    yy = table_box(f, cx, yy, cw, "novas", "rx, ry PK, at, w, x, y, d, initials, first, words, surveyors, top, "
                   "logged") + 7  # fmt: skip
    yy = table_box(f, cx, yy, cw, "owed", "k PK, n · what the next report owes the Atlas") + 7
    yy = table_box(f, cx, yy, cw, "logged, relayed, guild_names, map", "the log's mark · the last supernova "
                   "passed on · guilds' names · MAP_VERSION") + 7  # fmt: skip

    # Memory.
    cx, cw = cols[2]
    items = [("people", "socket → its attachment, read once"), ("claimsJson", "every claim, for each hello"),
             ("counts, hidden", "16 territories: charted and total"), ("batch", "claims waiting ≤ 200 ms"),
             ("over", "addresses past today's cap"), ("frames, tokens", "each socket's allowances"),
             ("novasSent", "supernovas already passed on")]  # fmt: skip
    yy = y0 + 84
    for name, what in items:
        f.text(cx, yy + 10, name, "mono5", 9.5, k["object"])
        f.text(cx, yy + 23, what, "ui", 10, t.muted)
        yy += 34

    # Messages and timers.
    my = y0 + h0 + 30
    f.eyebrow(x0, my, "Messages")
    for row, (label, names) in enumerate([("in", ["me", "pos", "claim", "here", "emote"]),
                                          ("out", ["hello", "claimed", "taken", "signed", "error", "presence", "emote",
                                                   "emoted", "guild", "world", "nova", "full"])]):  # fmt: skip
        px, yy = x0 + 104, my + row * 26
        f.text(px, yy, label, "ui5", 10, t.muted)
        px += 26
        for m in names:
            px += pill(f, px, yy + 1, m, font="mono", size=8.5) + 4
    my += 26
    ty = my + 34
    f.eyebrow(x0, ty, "Timers, all short")
    f.para(x0 + 140, ty, "A 200 ms timer for claims waiting in a batch; one for a player leaving a sector with "
           "fewer than 32 sockets; and a Durable Object alarm, at most 30 s after a claim, to copy claims to the log. "
           "Nothing else: positions and reports go with the next message, so a quiet sector can hibernate.",
           768 - x0 - 140, "ui", 10.5, lh=1.36, fill=t.muted)  # fmt: skip
    f.footer("Sources: worker/src/survey.js (Sector) · worker/SURVEY.md 'How it works'")
    return f


@figure(
    "claim-life",
    "claims",
    "The life of a claim, and a race",
    "Circling a word sends a claim to the sector the word starts in, over the WebSocket already open to it. "
    "The sector checks it against each limit and against its own copy of the map, then inserts it. Two "
    "players who circle the same word at once can't both win: the sector runs one message at a time, so the "
    "second insert finds the row and that player hears 'taken', with who charted it and when. The winner's "
    "claim goes out to everyone in the sector in the next 200 ms batch, each claimer gets a signed receipt, "
    "and within 30 seconds an alarm copies it to the log. Either way, the word stays in both players' field "
    "notes.",
    "A sequence diagram with five columns: you, a rival, the sector, the Atlas and the log in D1. You send "
    "a claim for PURIM; at the sector it passes five checks in turn: messages per socket, claims per socket, "
    "claims per address per minute, today's cap, and the word really being on the map; then an INSERT "
    "succeeds. The rival's claim for the same word arrives 40 milliseconds later and its INSERT finds the "
    "row, so the rival gets 'taken', naming you. Within 200 milliseconds a batch broadcasts 'claimed' to "
    "everyone in the sector; each claimer gets a signed receipt; the sector's next report tells the Atlas "
    "how many words your address charted today; and within 30 seconds an alarm writes the claim to the "
    "survey log, where triggers update the counts.",
    [
        (
            "Frames: FRAME_BURST = 20, then one per FRAME_REFILL_MS = 100 ms; dropped unread past that",
            "worker/src/survey.js webSocketMessage",
        ),
        (
            "Claims per socket: CLAIM_BURST = 5, then one per CLAIM_REFILL_MS = 1,500 ms ('slow down')",
            "worker/src/survey.js claim",
        ),
        ("Claims per address: SURVEY_CLAIMS, 6 a minute, approximate per Cloudflare location", "worker/wrangler.toml"),
        (
            "Daily cap: DAILY_CLAIMS = 300 per address per UTC day in the universe; a sector that hasn't heard the list "
            "since waking asks the Atlas first ('daily limit')",
            "worker/src/survey.js claim, ask, heard",
        ),
        (
            "checkClaim against the generator, then INSERT … ON CONFLICT (key) DO NOTHING; the loser gets "
            "{t: 'taken', c}",
            "worker/src/survey.js claim",
        ),
        ("A claim's time is always after the sector's previous claim (claimTime)", "worker/src/survey.js"),
        (
            "'claimed' frames are batched for up to 200 ms and broadcast to every socket in the sector",
            "worker/src/survey.js sendBatch",
        ),
        (
            "A receipt {t: 'signed', k, r} follows for a claimer with a player id: f if first, z if it set off a "
            "supernova, and an HMAC",
            "worker/src/survey.js receipt; worker/ACHIEVEMENTS.md",
        ),
        (
            "The game keeps a little inside the sector's limit: 4 at once, then one per 1.6 s; claims wait in an "
            "outbox, kept in localStorage, and a word always stays in the notes",
            "letterfield.html CLAIM_MOVES, flushClaims",
        ),
        (
            "The log alarm fires at most LOG_MS = 30 s after a claim and writes up to 240 claims in one D1 batch",
            "worker/src/survey.js logSoon, flushLog; survey-log.js",
        ),
    ],
)
def claim_life(t: Theme) -> Fig:
    f = Fig(t, 800)
    f.header("Letterfield · the server", "The life of a claim, and a race")
    k = t.kinds
    lanes = [("You", "browser · ZED", k["browser"], 76), ("Rival", "browser · KIM", k["browser"], 196),
             ("Sector 0,0", "Durable Object", k["object"], 400), ("Atlas", "Durable Object", k["object"], 598),
             ("Survey log", "D1", k["store"], 714)]  # fmt: skip
    top, bottom = 118, 736
    for name, sub, colour, x in lanes:
        f.rect(x - 52, top, 104, 38, r=6, fill=t.panel, stroke=colour, sw=1.3)
        f.text(x, top + 16, name, "ui6", 12, anchor="middle")
        f.text(x, top + 30, sub, "ui", 9.5, t.muted, "middle")
        f.line(x, top + 38, x, bottom, t.rule, 1.2, dash="2 4")
    X = {name: x for name, _, _, x in lanes}
    y = top + 66
    # It moves: each message runs along its arrow in turn, and each check lights as the claims pass it.
    f.animate(12)

    def msg(a, b, yy, text, colour=None, dash=None, below=False, at=None):
        f.arrow([(X[a], yy), (X[b], yy)], colour or t.ink, 1.4, dash=dash)
        mid = (X[a] + X[b]) / 2
        f.label(mid, yy + (13 if below else -6), text, "ui5", 10, t.ink, "middle")
        if at is not None:
            f.travel([(X[a], yy), (X[b], yy)], at, at + 0.7, colour or t.ink)

    # You circle PURIM; the rival does too, a moment later.
    f.capsule(X["You"] - 30, y - 4, X["You"] + 30, y - 4, 8, t.mark(90), t.wash(90), t.fill_a, 1.4)
    f.text(X["You"], y, "PURIM", "mono5", 9.5, anchor="middle")
    f.text(X["You"] - 60, y + 22, "outbox: queued → sent", "ui", 9.5, t.muted)
    msg("You", "Sector 0,0", y + 40, "{t: 'claim', w: 'PURIM', x: 5, y: 5, d: 7}", at=0.4)
    f.capsule(X["Rival"] - 30, y + 58, X["Rival"] + 30, y + 58, 8, t.mark(90), t.wash(90), t.fill_a, 1.4)
    f.text(X["Rival"], y + 62, "PURIM", "mono5", 9.5, anchor="middle")
    msg("Rival", "Sector 0,0", y + 86, "40 ms later, the same word", t.muted, at=0.8)
    f.text(X["Sector 0,0"] + 14, y + 4, "one message at a time:", "ui6", 10, t.ink)

    # The sector's checks, one message at a time.
    cx, cy = X["Sector 0,0"] + 14, y + 22
    checks = [("messages per socket", "20 at once, then 10 a second"), ("claims per socket", "5 at once, then 1 per 1.5 s"),
              ("claims per address", "6 a minute, every sector"), ("today's cap", "300 words an address"),
              ("on the map?", "checkClaim, with the generator")]  # fmt: skip
    for i, (a, b) in enumerate(checks):
        yy = cy + i * 24
        f.rect(cx, yy, 330, 20, r=4, fill=t.panel, stroke=t.rule)
        f.glow(cx, yy, 330, 20, 1.7 + i * 0.35, 0.8, k["object"], r=4)
        f.path(f"M{cx + 7} {yy + 10} l3 3.2 l6 -6.6", stroke=k["object"], sw=1.8)
        f.text(cx + 22, yy + 14, a, "ui5", 9.5, t.ink)
        f.text(cx + 322, yy + 14, b, "ui", 9.5, t.muted, "end")
    f.text(cx, cy + 5 * 24 + 12, "a refusal answers {t: 'error'}: 'slow down', 'daily limit' or why; the game "
           "keeps the word", "ui", 9.5, t.muted)  # fmt: skip
    iy = cy + 5 * 24 + 26
    f.rect(cx, iy, 196, 40, r=5, fill=t.field if not t.dark else t.paper, stroke=k["store"], sw=1.2)
    f.text(cx + 8, iy + 15, "INSERT INTO claims …", "mono5", 8.5, t.ink)
    f.text(cx + 8, iy + 29, "ON CONFLICT (key) DO NOTHING", "mono5", 8.5, t.ink)
    f.glow(cx, iy, 196, 40, 3.6, 1.2, k["store"], r=5)
    f.text(cx + 206, iy + 16, "ZED's: inserted", "ui5", 10, t.ink)
    f.text(cx + 206, iy + 31, "KIM's: the row is there", "ui5", 10, t.danger)

    # The batch first (at once after a lull, or within 200 ms), then the rival's answer.
    y3 = iy + 78
    f.rect(X["You"] - 50, y3 - 16, X["Sector 0,0"] - X["You"] + 50, 52, r=6, fill="none", stroke=t.rule, dash="3 3")
    f.text(X["You"] - 44, y3 - 3, "a batch: ≤ 200 ms", "ui5", 9.5, t.muted)
    msg("Sector 0,0", "You", y3 + 10, "{t: 'claimed', c: [PURIM, …], by}", k["object"], at=4.9)
    msg("Sector 0,0", "Rival", y3 + 28, "to every socket in the sector", k["object"], at=4.9)
    f.text(X["You"] - 50, y3 + 52, "outbox: first", "ui", 9.5, t.muted)
    y2 = y3 + 74
    msg("Sector 0,0", "Rival", y2, "{t: 'taken', c: [PURIM, … 'ZED', at]}", t.danger, at=5.9)
    f.text(X["Rival"] - 50, y2 + 20, "outbox: theirs · notes: charted by ZED", "ui", 9.5, t.muted)
    y4 = y2 + 48
    msg("Sector 0,0", "You", y4, "{t: 'signed', k, r}: each claimer's receipt", t.muted, dash="1 4", at=6.8)
    f.text(X["You"] - 50, y4 + 20, "kept with the find, for badges", "ui", 9.5, t.muted)

    # The Atlas and the log, later.
    y5 = y4 + 52
    msg("Sector 0,0", "Atlas", y5, "next report, ≤ 10 s", k["object"], at=7.8)
    f.text(X["Atlas"] - 40, y5 + 20, "your address: 1 more", "ui", 9.5, t.muted)
    f.text(X["Atlas"] - 40, y5 + 32, "word today, of 300", "ui", 9.5, t.muted)
    y6 = y5 + 58
    msg("Sector 0,0", "Survey log", y6, "alarm, ≤ 30 s: a batch of up to 240", k["store"], at=8.9)
    f.text(X["Survey log"] - 44, y6 + 20, "INSERT OR IGNORE;", "ui", 9.5, t.muted)
    f.text(X["Survey log"] - 44, y6 + 32, "triggers count it", "ui", 9.5, t.muted)
    f.footer("Sources: worker/src/survey.js (claim, sendBatch, receipt, flushLog) · letterfield.html (the outbox)")
    return f


@figure(
    "atlas-reports",
    "server",
    "Presence, and the Atlas",
    "Players never talk to the Atlas. Each sector in the universe tells it the sector's numbers at most every "
    "10 seconds while something is changing (charted counts for its 16 territories, who is there, how many "
    "words each address charted), riding on the next message rather than a timer. Reports are absolute "
    "numbers, so a lost or repeated one does no harm. The Atlas answers with the world's totals, the "
    "addresses past today's cap, which guild members are online and any supernova news, and each sector "
    "passes those on to its players. Anything global, like the world map and the list of surveyors, is read "
    "over HTTP from a short cache, in the spirit of One Million Checkboxes.",
    "Three sectors on the left, each with players, send reports to the Atlas in the middle, at most every "
    "10 seconds, each listing its players, the charted count of its 16 territories, the middle of its crowd, "
    "its surveyors by territory, words charted per address, and supernovas. The Atlas answers each with the "
    "world's totals, the addresses past the daily cap, guild members online and new supernovas. On the "
    "right, Worker instances fetch the world map from the Atlas at most every 5 seconds and the surveyor "
    "list every 10, and browsers cache each. Below the sectors, what players get from their sector: "
    "positions once a second for up to 64 people, and the world's totals as they change.",
    [
        (
            "REPORT_MS = 10 s; a sector reports at least every REFRESH_MS = 50 s while messages arrive, and at once "
            "when a listed player leaves",
            "worker/src/survey.js; worker/src/survey-social.js",
        ),
        (
            "Report fields: sx, sy, players, perAddress, charted (16), hot, day, overAt, novaSeq, who, tags, by, "
            "unpassed, novas",
            "worker/src/survey.js toAtlas, report",
        ),
        (
            "The Atlas answers with totals, day, overAt, the over-cap list when it changed (latest 2,000), guilds "
            "online and supernovas since novaSeq",
            "worker/src/survey.js Atlas.fetch",
        ),
        (
            "The Atlas writes charted counts to storage at most once a minute (SAVE_MS), and a sector's at once when "
            "its last player leaves",
            "worker/src/survey.js Atlas.save",
        ),
        (
            "World map: each Worker instance asks the Atlas at most every 5 s (VIEW_MS); browsers cache 5 s; about "
            "10 KB, a byte per territory",
            "worker/src/survey.js worldMap; SURVEY.md",
        ),
        (
            "Surveyor list: a snapshot at most every LIST_MS = 10 s; pages of 40 nearest, up to 1,000; the game asks "
            "every 20 s while open",
            "worker/src/survey-social.js; letterfield.html WHO_REFRESH_MS",
        ),
        (
            "Positions: at most once a second, up to 64 (with each address's latest mover first past that) plus a "
            "head count",
            "worker/src/survey.js sendPresence",
        ),
        (
            "Sectors round positions to territories before reporting; the Atlas never has cells",
            "worker/SURVEY.md 'Privacy'",
        ),
        ("An address counts for at most ADDRESS_ONLINE = 40 toward MAX_ONLINE = 25,000", "worker/src/survey.js"),
    ],
)
def atlas_reports(t: Theme) -> Fig:
    f = Fig(t, 650)
    f.header("Letterfield · the server", "Presence, and the Atlas")
    k = t.kinds
    # It moves through ten seconds: positions go out once a second, each busy sector reports once and hears
    # back, a Worker asks for the world map twice and the surveyor list once, and the sleeping sector sleeps.
    f.animate(10)
    tick = f.cue(
        [
            fr
            for sec in range(10)
            for fr in ((sec + 0.0, "opacity:1"), (sec + 0.12, "opacity:.35"), (sec + 0.45, "opacity:1"))
        ]
    )
    # Sectors.
    sx, sw = 32, 196
    names = [("Sector 0,0", 5), ("Sector 1,0", 2), ("Sector -1,0", 0)]
    ys = [128, 236, 344]
    for (name, n), y in zip(names, ys):
        f.rect(sx, y, sw, 80, r=7, fill=t.panel, stroke=k["object"], sw=1.3)
        f.text(sx + 12, y + 20, name, "ui6", 12)
        with f.group(tick if n else ""):
            for i in range(n):
                f.circle(sx + 18 + i * 16, y + 40, 5, fill=k["browser"])
        f.text(sx + 12, y + 64, f"{n} surveyors" if n else "nobody here: asleep", "ui", 10, t.muted)
    # The Atlas.
    ax, aw, ay, ah = 340, 172, 150, 290
    f.rect(ax, ay, aw, ah, r=9, fill=t.panel, stroke=k["object"], sw=1.6)
    f.text(ax + 14, ay + 24, "Atlas", "ui6", 15)
    f.text(ax + 14, ay + 40, "one for the universe", "ui", 10, t.muted)
    keeps = [("in storage", "charted counts, ≤ 1 a minute"), ("in memory", "who's where, by territory"),
             ("", "words per address today"), ("", "guild members online"), ("", "supernovas, for 2 minutes"),
             ("", "the day's bot signals")]  # fmt: skip
    yy = ay + 66
    for head, what in keeps:
        if head:
            f.eyebrow(ax + 14, yy, head)
            yy += 15
        f.text(ax + 14, yy, what, "ui", 10.5, t.ink)
        yy += 17
    # Reports and answers, straight across.
    for (_name, n), y in zip(names, ys):
        if not n:
            f.arrow([(sx + sw, y + 30), (ax, y + 30)], t.rule, 1.2, dash="2 4")
            continue
        f.arrow([(sx + sw, y + 30), (ax, y + 30)], k["object"], 1.5)
        f.arrow([(ax, y + 54), (sx + sw, y + 54)], t.muted, 1.2, dash="1 4")
        f.label((sx + sw + ax) / 2, y + 24, "report, ≤ 10 s", "ui6", 9.5, t.ink, "middle")
        f.label((sx + sw + ax) / 2, y + 68, "answer", "ui5", 9.5, t.muted, "middle")
    f.label((sx + sw + ax) / 2, ys[2] + 24, "asleep: nothing to say", "ui5", 9.5, t.muted, "middle")
    f.text(sx, 448, "Reports ride on the next message, never on a", "ui", 10, t.muted)
    f.text(sx, 461, "timer: a pending timer keeps an object billed.", "ui", 10, t.muted)
    # What's in them.
    f.eyebrow(sx, 492, "A report")
    rep = "{sx, sy, players, perAddress, charted: [16], hot, who: [[id, initials, rx, ry, idle, flags]], tags, by: [[address, words]], unpassed, novas, novaSeq, day, overAt}"
    f.para(sx, 508, rep, 300, "mono", 8.2, lh=1.42, fill=t.ink)
    f.eyebrow(sx + 330, 492, "The answer")
    ans = "{charted, total, players, day, overAt, over: [addresses past the cap], guilds: [who's online], novas: [news], novaSeq}"
    f.para(sx + 330, 508, ans, 220, "mono", 8.2, lh=1.42, fill=t.ink)
    # The read side.
    rx = 600
    f.eyebrow(rx, 136, "Read over HTTP, cached")
    for i, (route, every, cache) in enumerate([("/v1/survey/world", "each Worker instance asks ≤ every 5 s",
                                                 "browsers keep it 5 s · 10 KB"),
                                                ("/v1/survey/surveyors", "a snapshot ≤ every 10 s",
                                                 "pages of the nearest 40")]):  # fmt: skip
        y = 150 + i * 98
        f.rect(rx, y, 168, 80, r=7, fill=t.panel, stroke=k["worker"], sw=1.3)
        f.text(rx + 10, y + 19, route, "mono5", 8.6)
        f.para(rx + 10, y + 38, every, 150, "ui", 10, lh=1.25, fill=t.ink)
        f.text(rx + 10, y + 70, cache, "ui", 9.5, t.muted)
        f.arrow([(rx, y + 40), (ax + aw, ay + 60 + i * 60)], k["worker"], 1.2, start=True, end=False)
    f.para(rx, 376, "Global data is served the way One Million Checkboxes served it: a GET with a short "
           "max-age, so the Atlas hears from Workers, not players.", 168, "ui", 10, lh=1.32, fill=t.muted)  # fmt: skip
    f.eyebrow(rx, 492, "To players")
    for i, line in enumerate(["presence: ≤ once a second,", "  up to 64 positions + a count", "world: totals, as they change",
                              "guild: members online", "nova: news from elsewhere"]):  # fmt: skip
        f.text(rx, 510 + i * 14.5, line, "ui", 10, t.ink)
    # The motion: each busy sector's report and the Atlas's answer, and the Worker's reads.
    for (_name, n), y, at in zip(names, ys, (1.0, 4.4, None)):
        if not n:
            continue
        f.travel([(sx + sw, y + 30), (ax, y + 30)], at, at + 0.7, k["object"])
        f.glow(ax, ay, aw, ah, at + 0.7, 0.8, k["object"], r=9)
        f.travel([(ax, y + 54), (sx + sw, y + 54)], at + 1.0, at + 1.7, t.muted)
        f.glow(sx, y, sw, 80, at + 1.7, 0.8, k["object"], r=7)
    for i, times in enumerate(((2.8, 7.8), (6.2,))):
        y = 150 + i * 98
        for at in times:
            f.travel([(rx, y + 40), (ax + aw, ay + 60 + i * 60)], at, at + 0.6, k["worker"])
            f.travel([(ax + aw, ay + 60 + i * 60), (rx, y + 40)], at + 0.75, at + 1.35, k["worker"])
            f.glow(rx, y, 168, 80, at + 1.35, 0.7, k["worker"], r=7)
    f.footer("Sources: worker/src/survey.js (report, Atlas) · worker/src/survey-social.js · worker/SURVEY.md")
    return f


def nova_neighbours(rx: int, ry: int, reach: int = 3) -> list[tuple[int, int]]:
    """worker/src/survey.js novaNeighbours: other sectors with a territory within reach."""
    fd = lambda a: a // 4  # noqa: E731 - floor division, as fdiv
    sx, sy = fd(rx), fd(ry)
    return [(nx, ny) for ny in range(fd(ry - reach), fd(ry + reach) + 1) for nx in range(fd(rx - reach), fd(rx + reach) + 1)
            if (nx, ny) != (sx, sy)]  # fmt: skip


@figure(
    "supernova-flow",
    "supernova",
    "A supernova, from the last word to the shockwave",
    "A territory goes supernova when every one of its hidden words has been charted. A territory lies inside "
    "one sector, whose claims run one at a time, so exactly one claim can be the last, and the sector writes "
    "the supernova in the same step as that claim. Then the news spreads three ways: straight to the "
    "neighbouring sectors close enough for their players to see it (three, five or eight of them, depending "
    "on where the territory sits), to the Atlas with the sector's next report, which relays it to every other "
    "sector in the universe for two minutes, and to the log with the next batch. In the game it plays as a "
    "charge, a burst and a shockwave nearby, or a distant wave further off.",
    "Three small maps of 3 by 3 sectors, each 4 by 4 territories, show which neighbouring sectors a sector "
    "tells about a supernova within three territories: three for a territory in a sector's corner, five on an "
    "edge, eight for one of the middle four. Below them, a flow: the claim of the last hidden word, the "
    "supernova row written in the same step, then three branches: POST /near to the neighbours, who pass it "
    "to their players; the next report to the Atlas, which checks it and relays it to every sector for two "
    "minutes; and the log's next batch, once the log has its last word. At the bottom, the game's timeline: a "
    "2.6 second charge, the burst, a 3.4 second shockwave and the remnant left behind, with the quieter "
    "distant wave for supernovas further off, and the live survey's eight supernovas so far.",
    [
        (
            "Recorded by the sector in the same step as the claim that completed the territory, ON CONFLICT DO "
            "NOTHING, before anything is awaited",
            "worker/src/survey.js Sector.supernova, claim",
        ),
        (
            "Neighbours within NOVA_REACH = 3 territories (the larger of the two distances): 3 for a corner territory, "
            "5 for an edge, 8 for the middle four",
            "worker/src/survey.js novaNeighbours",
        ),
        (
            "Neighbours hear by an internal POST /near inside ctx.waitUntil, and check it (checkNova) before passing "
            "{t: 'nova'} on",
            "worker/src/survey.js passOn, near, checkNova",
        ),
        (
            "To the Atlas at once, or NOVA_REPORT_MS = 1 s after the last report; it checks the word and the report's "
            "counts, then relays for RELAY_MS = 2 minutes, at most RELAY_MAX = 64",
            "worker/src/survey.js",
        ),
        ("To the log in the alarm's batch, never before its last word is in D1", "worker/src/survey.js flushLog"),
        (
            "In the game: NOVA_CHARGE = 2,600 ms, NOVA_WAVE = 3,400 ms; further than 3 territories, a wave only, "
            "DISTANT_WAVE = 2,400 ms, at most once a minute and only under 20 s old",
            "letterfield.html Supernova",
        ),
        (
            "8 supernovas in the log by 20 Nov 2026; the quickest took 5.3 hours from first word to last, the slowest "
            "135.9; 108 to 116 hidden words each",
            "GET /v1/survey/log/novas (data/survey.json)",
        ),
        (
            "Territories hide 100 to 123 hidden words (SURVEY.md says 'about 112, from 102 to 122')",
            "counted with the Worker's generator over all 10,000 territories",
        ),
    ],
)
def supernova_flow(t: Theme) -> Fig:
    f = Fig(t, 786)
    f.header("Letterfield · the server", "A supernova, from the last word to the shockwave")
    k = t.kinds
    # It moves: the burst, the reach, the sectors told as the news arrives, the news down the flow, and the
    # game's own timeline played in real time.
    f.animate(14)
    told_cue = f.cue(
        [(0, "opacity:0"), (1.35, "opacity:0"), (1.7, "opacity:1"), (13.4, "opacity:1"), (14, "opacity:0")]
    )
    star_cue = f.cue([(0, "transform:scale(1)"), (0.3, "transform:scale(1)"), (0.55, "transform:scale(2.3)"),
                      (0.95, "transform:scale(1)")], origin=True)  # fmt: skip
    reach_cue = f.cue([(0, "opacity:0;transform:scale(.15)"), (0.45, "opacity:0;transform:scale(.15)"),
                       (1.25, "opacity:1;transform:scale(1)"), (13.4, "opacity:1;transform:scale(1)"),
                       (14, "opacity:0;transform:scale(1)")], origin=True)  # fmt: skip
    # Three cases of who's told.
    cases = [("a corner territory", (0, 0)), ("an edge territory", (1, 0)), ("one of the middle four", (1, 1))]
    cell, mx0, my0 = 15, 32, 128
    for i, (label, (lx, ly)) in enumerate(cases):
        x0 = mx0 + i * 252
        rx, ry = 4 + lx, 4 + ly  # in the middle sector of a 3 × 3
        told = nova_neighbours(rx, ry)
        for sy in range(3):
            for sx in range(3):
                own = (sx, sy) == (1, 1)
                f.rect(x0 + sx * 4 * cell, my0 + sy * 4 * cell, 4 * cell, 4 * cell,
                       fill=k["object"] if own else t.panel, fill_opacity=0.12 if own else 1, stroke=t.rule, sw=0.6)  # fmt: skip
        with f.group(told_cue):
            for sx, sy in told:
                f.rect(x0 + sx * 4 * cell, my0 + sy * 4 * cell, 4 * cell, 4 * cell, fill=k["object"],
                       fill_opacity=0.28, stroke=t.rule, sw=0.6)  # fmt: skip
        for v in range(13):
            f.line(x0 + v * cell, my0, x0 + v * cell, my0 + 12 * cell, t.rule, 0.5, opacity=0.8)
            f.line(x0, my0 + v * cell, x0 + 12 * cell, my0 + v * cell, t.rule, 0.5, opacity=0.8)
        for v in range(4):
            f.line(x0 + v * 4 * cell, my0, x0 + v * 4 * cell, my0 + 12 * cell, t.ink, 1.2)
            f.line(x0, my0 + v * 4 * cell, x0 + 12 * cell, my0 + v * 4 * cell, t.ink, 1.2)
        with f.group(reach_cue):
            f.rect(x0 + (rx - 3) * cell, my0 + (ry - 3) * cell, 7 * cell, 7 * cell, fill="none", stroke=t.accent,
                   sw=1.3, dash="4 3")  # fmt: skip
        with f.group(star_cue):
            star(f, x0 + (rx + 0.5) * cell, my0 + (ry + 0.5) * cell, 7.5, t.mark(30), t.ink)
        f.text(x0, my0 + 12 * cell + 20, f"{len(told)} sectors told", "ui6", 12)
        f.text(x0, my0 + 12 * cell + 35, label, "ui", 10.5, t.muted)
    f.text(32, my0 + 12 * cell + 56, "Each map is 3 × 3 sectors of 4 × 4 territories. Dashed: three territories each "
           "way, the reach of a full supernova on screen. Tinted: the sectors told at once.", "ui", 9.5, t.muted)  # fmt: skip

    # The flow.
    fy = my0 + 12 * cell + 92
    f.eyebrow(32, fy, "How the news spreads")
    b1 = (32, fy + 14, 170, 64)
    f.rect(*b1, r=6, fill=t.panel, stroke=k["object"], sw=1.3)
    f.text(44, fy + 34, "The last hidden word", "ui6", 11.5)
    f.para(44, fy + 50, "its claim makes charted = hidden for its territory", 150, "ui", 9.5, lh=1.25, fill=t.muted)
    b2 = (226, fy + 14, 170, 64)
    f.rect(*b2, r=6, fill=t.panel, stroke=k["store"], sw=1.3)
    f.text(238, fy + 34, "A row in novas", "ui6", 11.5)
    f.para(238, fy + 50, "in the same step, so it's written once, by one claim", 150, "ui", 9.5, lh=1.25, fill=t.muted)
    f.arrow([(202, fy + 46), (226, fy + 46)], t.muted, 1.4)
    branches = [("Neighbours", "POST /near, at once; each checks it and sends {t: 'nova'} to its players", k["object"]),
                ("The Atlas", "with the next report (≤ 1 s); checks it, then relays it to every sector for 2 minutes",
                 k["object"]),
                ("The log", "with the next batch, once D1 has its last word: the Supernovas list", k["store"])]  # fmt: skip
    for i, (head, body, colour) in enumerate(branches):
        by = fy + 6 + i * 50
        f.arrow([(396, fy + 46), (412, fy + 46), (412, by + 20), (430, by + 20)], t.muted, 1.4)
        f.rect(430, by, 338, 42, r=6, fill=t.panel, stroke=colour, sw=1.1)
        f.text(442, by + 17, head, "ui6", 11)
        f.para(442 + 80, by + 17, body, 338 - 92, "ui", 9.5, lh=1.25, fill=t.muted)

    # The news on its way: to the row in novas at once, then the neighbours at once, the Atlas with the next
    # report and the log with the next batch; each box lights as it arrives.
    def glow(box, at):
        x, y, w, h = box
        with f.group(f.cue([(0, "opacity:0"), (at, "opacity:0"), (at + 0.15, "opacity:1"), (at + 1.1, "opacity:0")])):
            f.rect(x - 2, y - 2, w + 4, h + 4, r=8, fill="none", stroke=t.accent, sw=2.2)

    glow(b1, 0.0)
    f.travel([(202, fy + 46), (226, fy + 46)], 0.55, 0.85, t.accent)
    glow(b2, 0.85)
    for i, (start, end) in enumerate([(1.0, 1.35), (1.6, 2.5), (3.2, 4.0)]):
        by = fy + 6 + i * 50
        f.travel([(396, fy + 46), (412, fy + 46), (412, by + 20), (430, by + 20)], start, end, t.accent)
        glow((430, by, 338, 42), end)
    # The game's timeline.
    gy = fy + 190
    f.eyebrow(32, gy, "In the game")
    x0, scale = 32, 64  # pixels a second
    seg = [("charge", 0, 2.6, 0.18), ("burst", 2.6, 2.75, 0.9), ("shockwave", 2.75, 6.0, 0.4),
           ("remnant, for good", 6.0, 11.4, 0.12)]  # fmt: skip
    for name, a, b, op in seg:
        f.rect(x0 + a * scale, gy + 14, (b - a) * scale - 2, 26, r=4, fill=t.mark(30), fill_opacity=op)
        if name != "burst":
            f.text(x0 + a * scale + 8, gy + 31, name, "ui6", 10.5, t.ink)
    f.arrow([(x0 + 11.4 * scale - 30, gy + 27), (x0 + 11.4 * scale + 4, gy + 27)], t.muted, 1.3, head=5)
    for sec in range(0, 12, 2):
        f.text(x0 + sec * scale, gy + 54, f"{sec} s", "mono", 8, t.muted, "middle" if sec else "start")
    play = f.cue([(0, "transform:translateX(0px)"), (1.4, "transform:translateX(0px)"),
                  (12.8, f"transform:translateX({11.4 * scale:.1f}px)"), (14, f"transform:translateX({11.4 * scale:.1f}px)")])  # fmt: skip
    with f.group(f"motion {play}"):
        f.line(x0, gy + 10, x0, gy + 44, t.ink, 2)
        f.circle(x0, gy + 10, 3.5, fill=t.ink)
    f.text(x0 + 2.6 * scale, gy + 8, "burst", "ui6", 9.5, t.ink, "middle")
    f.para(32, gy + 76, "Within 3 territories of the middle of the view (or your own): the charge for 2.6 s, the "
           "burst, a 3.4 s shockwave that shoves the letters, then a remnant: a deeper tint, a faint shell and a few "
           "stars. Further off: just a wave from that side, 2.4 s, at most one a minute and only while it's under "
           "20 s old. With reduced motion, words instead.", 736, "ui", 10.5, lh=1.36, fill=t.muted)  # fmt: skip
    snap = json.loads((HERE / "data" / "survey.json").read_text())
    nv = snap["novas"]
    hours = sorted((n["at"] - n["first"]) / 3_600_000 for n in nv)
    f.rect(32, gy + 132, 736, 34, r=6, fill=t.panel, stroke=t.rule)
    f.text(44, gy + 154, f"The live survey: {len(nv)} supernovas by {snap['at'][:10]} · first word to last in "
           f"{hours[0]:.1f} to {hours[-1]:.1f} hours · {min(n['words'] for n in nv)} to {max(n['words'] for n in nv)} "
           "hidden words each", "ui5", 10.5, t.ink)  # fmt: skip
    f.footer(
        "Sources: worker/src/survey.js (supernova, novaNeighbours, relay) · letterfield.html (Supernova) · the log API"
    )
    return f


@figure(
    "defence-in-depth",
    "claims",
    "Defence in depth",
    "The map and its generator are in the page, so a script can list every word without playing. No single "
    "limit stops that; each layer bounds something different, from the Worker that sees every request down "
    "to the insert itself. Most count per hashed address, which bounds one script well and a pool of many "
    "addresses only once per address; that's where a Turnstile check would come in, built and handing out "
    "passes but not required. A daily workflow watches the Atlas's numbers for the signs of a pool.",
    "A table of eleven layers, from the outside in. For each: where it's enforced, its limit, what it stops "
    "and what it doesn't. Turnstile passes (not required), salted address hashes, joins per address, sockets "
    "per address and per survey, messages per socket, claims per socket, claims per address per minute, the "
    "daily cap of 300 words per address, every claim checked against the generator, no free text anywhere "
    "others can read it, and signed receipts and badges. Below it, the thresholds at which the daily bot "
    "watch opens an issue.",
    [
        (
            "Turnstile passes last an hour, are an HMAC over the address hash and expiry, and are not required "
            '(TURNSTILE_REQUIRED = "false")',
            "worker/src/survey-pass.js; worker/wrangler.toml",
        ),
        (
            "Solver services sell Turnstile tokens for roughly $0.80 to $3 per 1,000 (third-party comparisons)",
            "worker/TURNSTILE.md 'How much it stops'",
        ),
        (
            "Addresses are hashed with IP_SALT, IPv6 by its /64, and never stored",
            "worker/src/leaderboard.js addressOf, hashAddress",
        ),
        (
            "Joins: SURVEY_JOINS 120 a minute per address, counted before a sector is woken",
            "worker/src/survey.js routeSurvey",
        ),
        (
            "40 sockets per address per sector; an address counts for at most 40 toward MAX_ONLINE = 25,000",
            "worker/src/survey.js ADDRESS_SOCKETS, ADDRESS_ONLINE",
        ),
        ("Messages: 20 at once, then 10 a second, the rest dropped unread", "worker/src/survey.js FRAME_BURST"),
        (
            "Claims: 5 at once then 1 per 1.5 s per socket; 6 a minute per address (approximate, per location)",
            "worker/src/survey.js; worker/wrangler.toml",
        ),
        (
            "Daily cap: 300 words a UTC day per address in the universe, counted by the Atlas from reports; one address "
            "would take about 10 years to chart the world; 3,700 addresses could do it in a day",
            "worker/SURVEY.md 'Limits per address'; worker/TURNSTILE.md",
        ),
        (
            "Sectors outside the universe don't report, so their words aren't capped (only 6 a minute)",
            "worker/SURVEY.md",
        ),
        (
            "32 blocked initials; seven emote drawings; guild names from three fixed lists of 16 words",
            "worker/src/leaderboard.js BLOCKED_INITIALS; survey-social.js EMOTES; survey-guild.js",
        ),
        ("Receipts, badges and cards are HMAC-SHA256 cut to 72 bits, keys from IP_SALT", "worker/src/achievements.js"),
        (
            "The bot watch opens an issue on ≥ 20 addresses at the cap, ≥ 120 words per player-hour over ≥ 500 words, "
            "or ≥ 500 joins without a pass and ≥ 5 per player-hour",
            "worker/SURVEY.md 'Watching for bots'",
        ),
    ],
)
def defence_in_depth(t: Theme) -> Fig:
    f = Fig(t, 820)
    f.header("Letterfield · the server", "Defence in depth")
    k = t.kinds
    rows = [
        (
            "Turnstile pass",
            "the Worker",
            "an hour's pass, only from one address",
            "scripts with no browser, once required",
            "solver services; it isn't required yet",
        ),
        (
            "Address hash",
            "the Worker",
            "SHA-256 with a salt; IPv6 by its /64",
            "keeping anyone's address; hopping a /64",
            "many addresses",
        ),
        ("Joins", "the Worker", "120 sockets a minute an address", "flooding every sector", "many addresses"),
        (
            "Sockets",
            "each sector, the Atlas",
            "40 an address a sector; ≤ 40 of 25,000 online",
            "a few addresses filling a sector or the survey",
            "sectors outside the universe",
        ),
        (
            "Messages",
            "each sector",
            "20 at once, then 10 a second",
            "one socket hogging the sector's one thread",
            "more sockets",
        ),
        ("Claims per socket", "each sector", "5 at once, then 1 per 1.5 s", "a fast client", "more sockets"),
        (
            "Claims per address",
            "each sector",
            "6 a minute, approximate",
            "one script racing everyone",
            "a pool; a burst can slip past",
        ),
        (
            "Daily cap",
            "the Atlas counts, sectors refuse",
            "300 words a day an address",
            "one address charting the world (10 years)",
            "3,700 addresses could in a day",
        ),
        (
            "The map",
            "each sector",
            "every claim run through the generator",
            "made-up words and places",
            "bots: every word is in the page",
        ),
        (
            "No free text",
            "everywhere",
            "3 initials (32 blocked), 7 drawings, guild names from word lists",
            "abuse in names and messages",
            "initials anyone can type",
        ),
        (
            "Signatures",
            "sectors, the Worker",
            "HMAC receipts, badges, cards",
            "badges that weren't earned",
            "the game's word on a few badges",
        ),
    ]
    cols = [
        (32, 104, "Layer"),
        (142, 92, "Where"),
        (240, 166, "Limit"),
        (412, 186, "Stops"),
        (604, 164, "Doesn't stop"),
    ]
    y = 120
    f.rect(32, y - 4, 736, 22, r=4, fill=t.panel)
    for x, _w, head in cols:
        f.eyebrow(x + 6, y + 11, head)
    y += 26
    spans = []  # each row's top and height, for the motion
    for i, (layer, where, limit, stops, not_) in enumerate(rows):
        cells = [layer, where, limit, stops, not_]
        lines = [f.wrap(c, w - 12, "ui6" if j == 0 else "ui", 10) for j, ((x, w, _), c) in enumerate(zip(cols, cells))]
        h = max(len(ls) for ls in lines) * 13.5 + 14
        spans.append((y, h))
        if i % 2 == 0:
            f.rect(32, y, 736, h, r=3, fill=t.panel, opacity=0.6)
        depth = i / (len(rows) - 1)
        f.rect(32, y + 2, 3, h - 4, fill=k["worker"] if depth < 0.3 else k["object"] if depth < 0.9 else k["store"])
        for j, ((x, _w, _), ls) in enumerate(zip(cols, lines)):
            for n, line in enumerate(ls):
                colour = t.ink if j in (0, 2, 3) else t.muted
                f.text(x + 6 + (4 if j == 0 else 0), y + 17 + n * 13.5, line, "ui6" if j == 0 else "ui", 10, colour)
        y += h + 2
    f.text(32, y + 16, "From the outside in: the Worker sees every request; sectors see their sockets; the Atlas "
           "sees the universe's reports.", "ui", 10, t.muted)  # fmt: skip
    wy = y + 44
    f.eyebrow(32, wy, "Watching for a pool of addresses · every night at 00:23 UTC")
    for i, (big, small) in enumerate([("≥ 20", "addresses at the daily cap"), ("≥ 120", "words per player-hour, over 500 words"),
                                      ("≥ 500", "joins without a pass, and ≥ 5 per player-hour")]):  # fmt: skip
        bx = 32 + i * 248
        f.rect(bx, wy + 12, 240, 52, r=6, fill=t.panel, stroke=t.rule)
        f.text(bx + 12, wy + 46, big, "display", 24, t.ink)
        f.para(bx + 74, wy + 34, small, 156, "ui", 10, lh=1.28, fill=t.muted)
    end = f.para(32, wy + 86, "Any one opens (or comments on) an issue labelled survey-bots. People manage about a word "
                 "a minute; a bot that claims without moving adds words but no player-hours.", 736, "ui", 10,
                 fill=t.muted)  # fmt: skip
    f.h = round(end + 30)
    # It moves: down a lane beside the table, surveyors pass every layer; each script stops at the layer that
    # bounds it (no pass is required, so none stops at the first); and a pool of addresses gets through them
    # all, to be seen only by the nightly watch.
    f.animate(13)
    lane, top, bottom = 19, spans[0][0] - 4, spans[-1][0] + spans[-1][1]
    mid = lambda i: spans[i][0] + spans[i][1] / 2  # noqa: E731
    per = (bottom - top) / 2.4  # how fast a dot falls, in units a second
    person, script = k["browser"], t.ink
    f.travel([(lane, top), (lane, bottom)], 0.3, 2.7, person)
    f.travel([(lane, top), (lane, bottom)], 5.2, 7.6, person)
    for at, row in [(1.0, 2), (1.9, 4), (2.8, 5), (3.8, 6), (6.0, 7), (7.0, 8), (8.0, 10)]:
        arrive = at + (mid(row) - top) / per
        f.travel([(lane, top), (lane, mid(row))], at, arrive, script, halo=False)
        x, w = cols[3][0], cols[3][1]
        f.glow(x, spans[row][0], w, spans[row][1], arrive, 0.9, t.danger, r=3)
    for n in range(5):  # a pool of addresses, each under every limit
        at = 9.0 + n * 0.16
        f.travel([(lane + (n - 2) * 1.5, top), (lane + (n - 2) * 1.5, wy + 38), (40, wy + 38)], at, at + 2.6, script,
                 r=3, halo=False)  # fmt: skip
    for i in range(3):
        f.glow(32 + i * 248, wy + 12, 240, 52, 11.7 + i * 0.12, 1.0, t.danger)
    f.footer(
        "Sources: worker/SURVEY.md 'Limits per address', 'Watching for bots' · worker/TURNSTILE.md · worker/src/survey.js"
    )
    return f


@figure(
    "log-pipeline",
    "log",
    "The log: from a sector's claims to a cached answer",
    "Sectors keep every claim, but a page can't ask 625 objects what happened between two and three o'clock. "
    "So each sector copies its new claims to a D1 database of their own, like an outbox: an alarm at most 30 "
    "seconds after a claim sends up to 240 at once in one transaction, and only then moves its mark. The "
    "table is ordered by time, so an hour reads just that hour's rows; triggers keep running counts per "
    "hour, per day per surveyor and per day per territory, so a year reads counts rather than a million "
    "rows; and virtual columns give every word its territory and theme for the indexes, at no cost per "
    "row. Answers are cached three times over, and a past hour, once settled, for a day.",
    "A pipeline from left to right. A sector's claims table and its 'logged' mark feed an alarm that fires at "
    "most 30 seconds after a claim and writes up to 240 claims in one D1 batch, retrying after 1, 2, 4 and up "
    "to 10 minutes if D1 fails. In the middle, the games-survey-log database: the survey_log table keyed by "
    "time and word, its virtual columns for territory and theme, four partial indexes, triggers feeding four "
    "count tables, and tables for supernovas and guilds. On the right, the Worker's log API with three "
    "caches (each instance's memory, Cloudflare's cache keyed by host and map, and the browser) and how long "
    "each kind of answer is kept: 15 seconds for an hour still running, a day once it has settled, and for "
    "good for a settled day of the timelapse.",
    [
        (
            "LOG_MS = 30 s; LOG_BATCH = 240 claims; 11 rows to an INSERT (9 values a row, D1 binds at most 100); "
            "one D1 batch is one transaction",
            "worker/src/survey-log.js; worker/SURVEY.md",
        ),
        (
            "The mark moves only after D1 answers; failures retry after 1, 2, 4… minutes, up to 10 (LOG_RETRY_MAX_MS)",
            "worker/src/survey.js alarm, flushLog",
        ),
        (
            "Bonus words aren't copied to the log (the mark still moves past them)",
            "worker/src/survey.js flushLog; migrations-log/0009",
        ),
        (
            "survey_log (at, key, w, x, y, d, s, initials, guild) WITHOUT ROWID, PRIMARY KEY (at, key); INSERT OR IGNORE",
            "worker/migrations-log/0001, 0007",
        ),
        (
            "Virtual columns rx, ry and th = ((rx + 15·ry) % 225 + 225) % 225; indexes by initials, territory, theme "
            "(hidden only) and guild",
            "worker/migrations-log/0003, 0005, 0007",
        ),
        (
            "Triggers keep survey_log_hours, _surveyors, _territories and _guild_days; a skipped duplicate fires none",
            "worker/migrations-log/0002, 0007, 0011",
        ),
        ("Up to seven D1 rows written per word, two more in a guild", "worker/SURVEY.md 'Cost' under 'The log'"),
        (
            "Caches: each instance's memory (300 answers, 8 million characters), the Cache API keyed by host and map "
            "version, and Cache-Control",
            "worker/src/survey-log.js",
        ),
        (
            "TTLs: running 15 s (LIVE_CACHE_S); settled (ended ≥ 1 h ago) a day; running ranges over 2 days 2 min, "
            "top lists 10 min; settled timelapse days a year, immutable",
            "worker/src/survey-log.js",
        ),
    ],
)
def log_pipeline(t: Theme) -> Fig:
    f = Fig(t, 660)
    f.header("Letterfield · the log", "From a sector's claims to a cached answer")
    k = t.kinds
    # It moves: claims come in, the alarm copies them to D1 in one batch, the triggers count them, and a
    # read goes all the way to D1 once, filling the caches, then comes back from the browser's own cache.
    f.animate(11)
    # The sector.
    sx, sy, sw = 32, 126, 176
    f.rect(sx, sy, sw, 236, r=8, fill=t.panel, stroke=k["object"], sw=1.4)
    f.text(sx + 12, sy + 22, "Each sector", "ui6", 12.5)
    claims_y = sy + 36
    yy = table_box(
        f, sx + 10, sy + 36, sw - 20, "claims", "key, w, x, y, d, s, initials, at, guild", "by time: (at, key)"
    )
    claims_h, logged_y = yy - claims_y, yy + 6
    yy = table_box(f, sx + 10, yy + 6, sw - 20, "logged", "at: the last claim D1 has")
    logged_h = yy - logged_y
    f.para(sx + 12, yy + 20, "A claim sets an alarm for 30 s later, if none is set. An alarm doesn't keep a sector "
           "awake, and wakes one that was evicted.", sw - 24, "ui", 9.5, lh=1.3, fill=t.muted)  # fmt: skip
    f.arrow([(sx + sw, sy + 118), (sx + sw + 34, sy + 118)], k["store"], 1.6)
    f.label(sx + sw + 17, sy + 108, "≤ 240", "ui6", 9.5, t.ink, "middle")
    f.text(sx, sy + 258, "if D1 fails: nothing lost; try again", "ui", 9.5, t.muted)
    f.text(sx, sy + 271, "after 1, 2, 4… minutes, up to 10", "ui", 9.5, t.muted)
    # D1.
    dx, dy, dw = 246, 126, 300
    f.rect(dx, dy, dw, 478, r=8, fill=t.panel, stroke=k["store"], sw=1.4)
    f.text(dx + 12, dy + 22, "games-survey-log", "ui6", 12.5)
    f.text(dx + 16 + f.width("games-survey-log", "ui6", 12.5), dy + 22, "D1", "ui", 11, t.muted)
    yy = table_box(f, dx + 10, dy + 36, dw - 20, "survey_log", "at, key PRIMARY KEY · w, x, y, d, s, initials, guild · "
                   "WITHOUT ROWID", "ordered by time: an hour reads just its rows")  # fmt: skip
    log_h = yy - (dy + 36)
    f.text(dx + 12, yy + 18, "virtual columns, stored only in indexes:", "ui5", 10, t.ink)
    f.text(dx + 12, yy + 33, "rx, ry = floor(x / 48), floor(y / 48)", "mono", 8.3, t.muted)
    f.text(dx + 12, yy + 46, "th = (rx + 15·ry) mod 225", "mono", 8.3, t.muted)
    iy = yy + 66
    f.text(dx + 12, iy, "partial indexes, each named in its query:", "ui5", 10, t.ink)
    for i, (name, cols) in enumerate([("by_initials", "(initials, at)"), ("by_territory", "(rx, ry, at)"),
                                      ("by_theme", "(th, at) hidden words"), ("by_guild", "(guild, at)")]):  # fmt: skip
        f.text(dx + 12, iy + 16 + i * 13, name, "mono5", 8.4, k["store"])
        f.text(dx + 110, iy + 16 + i * 13, cols, "mono", 8.4, t.muted)
    ty = iy + 66
    f.text(dx + 12, ty + 12, "triggers, in the same transaction:", "ui5", 10, t.ink)
    for i, (name, what) in enumerate([("survey_log_hours", "words per hour, and in the universe"),
                                      ("survey_log_surveyors", "per day per set of initials"),
                                      ("survey_log_territories", "hidden words per day per territory"),
                                      ("survey_log_guild_days", "per day per guild")]):  # fmt: skip
        f.text(dx + 12, ty + 30 + i * 26, name, "mono5", 8.6, k["store"])
        f.text(dx + 12, ty + 42 + i * 26, what, "ui", 9.5, t.muted)
    ny = ty + 140
    f.text(dx + 12, ny, "also: survey_log_novas, survey_log_guilds,", "mono", 8.3, t.muted)
    f.text(dx + 12, ny + 13, "survey_log_extra_guilds", "mono", 8.3, t.muted)
    f.para(dx + 12, ny + 34, "A resent batch is ignored row by row (INSERT OR IGNORE), and a skipped row fires no "
           "trigger, so nothing counts twice.", dw - 24, "ui", 9.5, lh=1.3, fill=t.muted)  # fmt: skip
    # The read side.
    f.arrow([(dx + dw, dy + 118), (dx + dw + 30, dy + 118)], k["worker"], 1.6)
    rx, rw = 580, 188
    f.rect(rx, dy, rw, 180, r=8, fill=t.panel, stroke=k["worker"], sw=1.4)
    f.text(rx + 12, dy + 22, "/v1/survey/log/…", "mono5", 9.5)
    f.para(rx + 12, dy + 40, "hours, days, months, top lists, a surveyor's, theme's, guild's or territory's words, "
           "supernovas, the timelapse", rw - 24, "ui", 9.5, lh=1.3, fill=t.muted)  # fmt: skip
    f.text(rx + 12, dy + 112, "three caches:", "ui5", 10, t.ink)
    for i, line in enumerate(["each instance's memory", "Cloudflare's cache, by host + map", "the browser"]):
        f.circle(rx + 16, dy + 128 + i * 15 - 3.5, 2.5, fill=k["worker"])
        f.text(rx + 24, dy + 128 + i * 15, line, "ui", 9.5, t.ink)
    f.eyebrow(rx, dy + 206, "Kept for")
    for i, (age, what) in enumerate([("15 s", "an hour or day still running"), ("2–10 min", "a long range still running"),
                                     ("1 day", "anything that ended ≥ 1 h ago"), ("for good", "a settled timelapse day")]):  # fmt: skip
        yy = dy + 226 + i * 34
        f.text(rx, yy + 4, age, "display", 17)
        f.para(rx + 72, yy, what, rw - 72, "ui", 9.5, lh=1.2, fill=t.muted)
    f.para(rx, dy + 372, "A crowd reading this hour costs one D1 query per instance every 15 s: the rest wait for "
           "that read.", rw, "ui", 9.5, lh=1.3, fill=t.muted)  # fmt: skip
    # The motion. Claims drop into the sector's table, a few seconds apart.
    for i, at in enumerate([0.3, 1.0, 1.6, 2.5, 3.1]):
        x = sx + 34 + i * 26
        f.travel([(x, sy + 2), (x, claims_y + 8)], at, at + 0.45, k["object"], r=3.2)
        f.glow(sx + 10, claims_y, sw - 20, claims_h, at + 0.45, 0.6, k["object"])
    # The alarm goes off: one batch to D1, and the mark moves past it.
    f.glow(sx + 10, logged_y, sw - 20, logged_h, 4.0, 1.0, k["store"])
    f.travel([(sx + sw, sy + 118), (dx + 4, sy + 118), (dx + 40, dy + 70)], 4.1, 4.9, k["store"], r=5)
    f.glow(dx + 10, dy + 36, dw - 20, log_h, 4.9, 1.0, k["store"])
    for i in range(4):  # each trigger counts it
        f.glow(dx + 8, ty + 18 + i * 26, dw - 16, 28, 5.2 + i * 0.22, 0.8, k["store"], r=4)
    # A read: past every cache to D1 once, and back, filling the caches on the way.
    edge, mid = rx + rw, dy + 118
    f.travel([(edge + 14, dy + 140), (rx + rw / 2, dy + 140), (rx, mid), (dx + dw, mid), (dx + dw - 30, dy + 150)],
             6.4, 7.3, k["worker"])  # fmt: skip
    f.travel([(dx + dw - 30, dy + 150), (dx + dw, mid), (rx, mid), (rx + rw / 2, dy + 140), (edge + 14, dy + 140)],
             7.5, 8.4, k["worker"])  # fmt: skip
    for i in range(3):
        f.glow(rx + 10, dy + 128 + i * 15 - 11, rw - 20, 15, 7.9 + i * 0.15, 0.9, k["worker"], r=3)
    # And again: this time the browser's own copy answers, and D1 never hears of it.
    f.travel([(edge + 14, dy + 158), (rx + 40, dy + 154)], 9.3, 9.75, k["worker"])
    f.glow(rx + 10, dy + 128 + 2 * 15 - 11, rw - 20, 15, 9.75, 0.9, k["worker"], r=3)
    f.travel([(rx + 40, dy + 154), (edge + 14, dy + 158)], 9.9, 10.35, k["worker"])
    f.footer("Sources: worker/src/survey-log.js · worker/migrations-log/*.sql · worker/SURVEY.md 'The log'")
    return f


# =============================================================================
# Devices
# =============================================================================
@figure(
    "devices-sync",
    "devices",
    "One surveyor on every device",
    "A surveyor is a random token in one browser's storage; the survey knows them by a hash of it. To be the "
    "same surveyor on a phone and a laptop, one device asks for a one-time code and the other redeems it for "
    "the token. With no other device to hand, a recovery code does the same, and the Worker can't read it: "
    "the code's own hash is both the key that seals the token and the address of the row. Linked devices "
    "then keep their field notes, supernovas, achievements and settings in step through a Player, a Durable "
    "Object per surveyor, whose merge rules can only ever add.",
    "Three panels. At the top, how a token of 32 hex digits becomes a player id: the first 48 bits of a "
    "SHA-256. Left, linking: device A asks for an eight-character code that lasts ten minutes and works "
    "once, shows it as a QR code, a link and the code itself, and device B redeems it for the token, which "
    "travels only in request bodies. Right, a recovery code of twenty characters: its SHA-512 splits into "
    "the D1 row's id and an AES-GCM key that seals the token, so D1 holds neither the code nor the token. "
    "Along the bottom, the Player object and its six merge rules: a find is kept once, charted first only "
    "comes on, a receipt stays, achievements keep the earliest time, the longest streak only goes up, and "
    "settings go with whichever device changed them last.",
    [
        (
            "The token is 32 hex digits (128 bits), kept as games.player; the player id is the first 12 hex digits "
            "(48 bits) of SHA-256('games-player:' + token)",
            "worker/src/survey-social.js playerId, TOKEN, PID",
        ),
        (
            "Link codes: 8 characters from a 31-letter alphabet (852 billion), 10 minutes (LINK_MS), one use; making "
            "codes 10 an hour and tries 20 an hour per address",
            "worker/src/players.js; worker/src/leaderboard.js LIMITS",
        ),
        ("One UPDATE … WHERE used = 0 … RETURNING redeems a code, and what it carried is wiped", "worker/SURVEY.md"),
        (
            "The making device polls /status every 5 s; anyone else hears 'gone'",
            "letterfield.html LINK_POLL_MS; players.js",
        ),
        (
            "Recovery codes: 20 characters (about 99 bits); SHA-512('games-recovery:' + code): first half the row id, "
            "second half an AES-GCM key sealing the token; 5 new codes an hour",
            "worker/src/players.js recoveryKeys",
        ),
        (
            "Player sync: rows carry their version; epoch restarts after a forget; limits 25,000 finds, 1,000 "
            "supernovas, 2,000 a sync, one sync every 2 s, 512 KB",
            "worker/src/players.js",
        ),
        (
            "Merge rules: f only comes on, b until it's yours, a receipt stays; marks keep the earliest time and "
            "'in play' over 'from notes'; best only goes up; settings by newest clock",
            "worker/src/players.js mergedFind, mergedMark; worker/SURVEY.md",
        ),
        (
            "A Player nobody syncs for 180 days deletes itself, unless a recovery code is saved",
            "worker/src/players.js KEEP_MS, alarm",
        ),
        (
            "Syncs on opening, a few seconds after a find, after a settings change, back in view, and every minute",
            "worker/SURVEY.md; letterfield.html SYNC_EVERY_MS, SYNC_SOON_MS",
        ),
    ],
)
def devices_sync(t: Theme) -> Fig:
    f = Fig(t, 760)
    f.header("Letterfield · devices", "One surveyor on every device")
    k = t.kinds
    # It moves: the token becomes an id; a code links device B; a recovery code seals the token; and the
    # Player keeps the devices in step.
    f.animate(11)
    # The token and the id.
    y = 120
    f.rect(32, y, 736, 54, r=7, fill=t.panel, stroke=t.rule)
    f.text(46, y + 22, "token", "ui6", 11.5)
    f.text(46, y + 40, "8f3c…a91e · 32 hex digits, random", "mono", 8.6, t.muted)
    f.arrow([(270, y + 27), (318, y + 27)], t.muted, 1.4)
    f.label(294, y + 21, "SHA-256", "mono5", 8.4, t.ink, "middle")
    f.text(330, y + 22, "player id", "ui6", 11.5)
    f.text(330, y + 40, "first 48 bits: 4d1f0c7a29b3", "mono", 8.6, t.muted)
    f.para(540, y + 22, "The id is the same in every sector, every visit; nobody else ever sees a token.", 220, "ui",
           9.5, lh=1.3, fill=t.muted)  # fmt: skip
    f.travel([(270, y + 27), (318, y + 27)], 0.3, 0.8, t.accent)
    f.glow(324, y + 8, 200, 40, 0.8, 0.8, t.accent, r=5)
    # Linking.
    ly = 204
    f.eyebrow(32, ly, "Linking another device")
    lanes = [("Device A", 70), ("Worker · D1", 210), ("Device B", 350)]
    for name, x in lanes:
        f.rect(x - 44, ly + 12, 88, 26, r=5, fill=t.panel, stroke=k["browser"] if "Device" in name else k["store"])
        f.text(x, ly + 29, name, "ui6", 10, anchor="middle")
        f.line(x, ly + 38, x, ly + 300, t.rule, 1, dash="2 4")
    X = {n: x for n, x in lanes}

    def step_msg(a, b, yy, text, colour=None, dash=None, at=None):
        f.arrow([(X[a], yy), (X[b], yy)], colour or t.ink, 1.3, dash=dash)
        f.label((X[a] + X[b]) / 2, yy - 5, text, "ui5", 9.2, t.ink, "middle")
        if at is not None:
            f.travel([(X[a], yy), (X[b], yy)], at, at + 0.6, colour or t.ink)

    step_msg("Device A", "Worker · D1", ly + 66, "POST /v1/link {token, carry}", at=1.2)
    f.text(X["Worker · D1"] + 8, ly + 86, "a code: 8 characters,", "ui", 9.2, t.muted)
    f.text(X["Worker · D1"] + 8, ly + 98, "10 minutes, one use", "ui", 9.2, t.muted)
    step_msg("Worker · D1", "Device A", ly + 116, "ABCD-EFGH", t.muted, at=2.1)
    f.glow(X["Device A"] - 40, ly + 128, 80, 46, 2.7, 0.9, t.accent, r=4)
    f.rect(X["Device A"] - 40, ly + 128, 80, 46, r=4, fill=t.paper, stroke=t.rule)
    for i in range(5):
        for j in range(5):
            if (i * 7 + j * 3) % 4 != 1:
                f.rect(X["Device A"] - 36 + j * 6, ly + 132 + i * 6, 5, 5, fill=t.ink)
    f.text(X["Device A"] + 2, ly + 146, "QR,", "ui", 8.8, t.muted)
    f.text(X["Device A"] + 2, ly + 157, "a link,", "ui", 8.8, t.muted)
    f.text(X["Device A"] + 2, ly + 168, "the code", "ui", 8.8, t.muted)
    step_msg("Device B", "Worker · D1", ly + 196, "POST /v1/link/ABCDEFGH", at=3.5)
    step_msg("Worker · D1", "Device B", ly + 226, "{token, carry}, once", k["browser"], at=4.3)
    f.glow(X["Device B"] - 44, ly + 12, 88, 26, 4.9, 0.9, k["browser"], r=5)
    step_msg("Device A", "Worker · D1", ly + 256, "every 5 s: /status → used", t.muted, dash="1 4", at=5.3)
    f.para(32, ly + 322, "B reloads as the same surveyor, with A's initials, guilds and mutes. The token only "
           "travels in request bodies, never in an address. 10 codes, 20 tries an hour per address.", 360, "ui", 9.5,
           lh=1.3, fill=t.muted)  # fmt: skip
    # Recovery.
    rx = 430
    f.eyebrow(rx, ly, "A recovery code")
    f.rect(rx, ly + 12, 338, 34, r=6, fill=t.panel, stroke=t.rule)
    f.text(rx + 169, ly + 34, "BCDF-GHJK-MNPQ-RSTV-WXYZ", "mono5", 11, t.ink, "middle")
    f.text(rx, ly + 64, "20 characters, about 99 bits, shown once", "ui", 9.5, t.muted)
    f.arrow([(rx + 169, ly + 72), (rx + 169, ly + 96)], t.muted, 1.4)
    f.label(rx + 169, ly + 88, "SHA-512", "mono5", 8.4, t.ink, "middle")
    f.rect(rx, ly + 100, 165, 40, r=5, fill=t.panel, stroke=k["store"])
    f.text(rx + 82, ly + 117, "first half", "ui6", 10, anchor="middle")
    f.text(rx + 82, ly + 131, "the row's id", "ui", 9.5, t.muted, "middle")
    f.rect(rx + 173, ly + 100, 165, 40, r=5, fill=t.panel, stroke=k["store"])
    f.text(rx + 255, ly + 117, "second half", "ui6", 10, anchor="middle")
    f.text(rx + 255, ly + 131, "an AES-GCM key", "ui", 9.5, t.muted, "middle")
    f.arrow([(rx + 255, ly + 140), (rx + 255, ly + 162)], t.muted, 1.3)
    f.arrow([(rx + 82, ly + 140), (rx + 82, ly + 162)], t.muted, 1.3)
    table_end = table_box(f, rx, ly + 166, 338, "recovery (D1)", "id · pid · box: the token, sealed · made",
                          "reading D1 gives no one a token; only the code opens its row")  # fmt: skip
    f.glow(rx, ly + 12, 338, 34, 6.1, 0.8, t.accent)
    f.travel([(rx + 169, ly + 72), (rx + 169, ly + 96)], 6.4, 6.8, t.accent)
    f.glow(rx, ly + 100, 165, 40, 6.85, 0.8, k["store"], r=5)
    f.glow(rx + 173, ly + 100, 165, 40, 6.85, 0.8, k["store"], r=5)
    for x in (rx + 82, rx + 255):
        f.travel([(x, ly + 140), (x, ly + 162)], 7.2, 7.5, k["store"])
    f.glow(rx, ly + 166, 338, table_end - (ly + 166), 7.55, 0.9, k["store"], r=5)
    f.para(rx, ly + 252, "One code a player: a new one stops the old. Saving one starts a Player and keeps it "
           "past the 180-day clear-out. 5 new codes an hour per address.", 338, "ui", 9.5, lh=1.3, fill=t.muted)  # fmt: skip
    # The Player.
    py = 590
    f.eyebrow(32, py, "Keeping devices in step: a Player, one Durable Object per surveyor")
    rules = [("A find is kept once", "keyed by word and place"), ("Charted first", "only ever comes on"),
             ("A receipt", "once there, stays"), ("Achievements", "the earliest time; in play beats from notes"),
             ("The longest streak", "only goes up"), ("Settings", "the device that changed them last")]  # fmt: skip
    for i, (a, b) in enumerate(rules):
        bx, by = 32 + (i % 3) * 248, py + 12 + (i // 3) * 50
        f.rect(bx, by, 240, 44, r=6, fill=t.panel, stroke=k["object"], sw=1)
        f.glow(bx, by, 240, 44, 8.4 + i * 0.2, 0.9, k["object"])
        f.text(bx + 12, by + 18, a, "ui6", 10.5)
        f.text(bx + 12, by + 33, b, "ui", 9.5, t.muted)
    f.text(32, py + 132, "Syncs on opening, a few seconds after a find, when the tab comes back, and every minute. Only "
           "a link or a recovery code starts one.", "ui", 9.5, t.muted)  # fmt: skip
    f.footer(
        "Sources: worker/src/players.js · worker/src/survey-social.js playerId · worker/SURVEY.md 'One player, several devices'"
    )
    return f


@figure(
    "ids-and-secrets",
    "devices",
    "Who is who: every name the survey uses",
    "The survey has no accounts, and no free text anyone else can read, but it still has to tell people "
    "apart, count addresses and keep badges honest. Each job gets its own identifier, scoped so that what's "
    "public can't be traced back to what's secret: a guild, for one, has three ids, so its public page in the "
    "log can't be matched to the carets on the map that wear its colour. Addresses are only ever stored as "
    "salted hashes, and the Worker can't open a recovery code it holds.",
    "A table of eleven identifiers with what each is, who can see it and what it's for, each marked as "
    "secret, seen by the server only, or public. The token is secret; the player id derived from it is "
    "public, on carets and the surveyor list. Address hashes reach sectors only. Initials are public. A "
    "guild's code is secret to its members, its tag shows on the map and its log id in the survey log. Link "
    "and recovery codes are secret; receipts, badges and cards are signed so anyone can check them; and a "
    "Turnstile pass stays in the browser that earned it.",
    [
        ("Token 32 hex; player id 12 hex = 48 bits of SHA-256", "worker/src/survey-social.js TOKEN, PID, playerId"),
        (
            "Addresses hashed with IP_SALT, IPv6 by /64, handed to sectors in X-Survey-Address, which the Worker sets",
            "worker/src/leaderboard.js; worker/src/survey.js routeSurvey",
        ),
        (
            "Initials: three letters A–Z; 32 blocked combinations",
            "worker/src/leaderboard.js INITIALS, BLOCKED_INITIALS",
        ),
        ("Guild code 6 characters (887 million), tag 8 hex, log id 10 hex", "worker/src/survey-social.js; SURVEY.md"),
        (
            "Link code 8 characters (852 billion), 10 minutes, once; recovery code 20 characters, about 99 bits",
            "worker/src/players.js",
        ),
        (
            "Receipts, badges and cards: HMAC-SHA256 cut to 72 bits, keys from IP_SALT per use",
            "worker/src/achievements.js",
        ),
        (
            "Turnstile pass: expiry + HMAC of address hash and expiry, an hour, key derived from TURNSTILE_SECRET",
            "worker/src/survey-pass.js",
        ),
    ],
)
def ids_and_secrets(t: Theme) -> Fig:
    f = Fig(t, 760)
    f.header("Letterfield · devices and privacy", "Who is who: every name the survey uses")
    k = t.kinds
    seen = {"you": (k["browser"], "secret"), "server": (k["object"], "the server"), "all": (k["worker"], "public")}
    rows = [
        ("Token", "32 hex digits, random, in this browser", "you", "naming you; never in an address"),
        ("Player id", "48 bits of the token's SHA-256", "all", "carets, the list, emotes: a lasting pseudonym"),
        ("Address hash", "your IP (IPv6: its /64), salted and hashed", "server", "counting limits; never the address"),
        ("Initials", "three letters you pick", "all", "signing your words; 32 combinations blocked"),
        ("Guild code", "6 characters: 887 million", "you", "joining, from an invite link"),
        ("Guild tag", "8 hex digits", "all", "which carets share a guild"),
        ("Guild log id", "10 hex digits", "all", "a guild's page in the log, unmatchable to carets"),
        ("Link code", "8 characters, 10 minutes, once", "you", "carrying the token to another device"),
        ("Recovery code", "20 characters, about 99 bits", "you", "bringing the token back; D1 keeps it sealed"),
        ("Receipts, badges", "HMAC-SHA256, 72 bits", "all", "proof anyone can check, with nothing stored"),
        ("Turnstile pass", "an expiry and an HMAC of the address hash", "you", "an hour's pass, from one address"),
    ]
    cols = [(32, 120, "Name"), (152, 250, "What it is"), (402, 92, "Seen by"), (494, 274, "For")]
    y = 120
    f.rect(32, y - 4, 736, 22, r=4, fill=t.panel)
    for x, _, head in cols:
        f.eyebrow(x + 8, y + 11, head)
    y += 28
    for i, (name, what, who, use) in enumerate(rows):
        if i % 2 == 0:
            f.rect(32, y - 4, 736, 40, r=3, fill=t.panel, opacity=0.6)
        f.text(40, y + 18, name, "ui6", 11)
        f.para(160, y + 18, what, 236, "ui", 10, lh=1.25)
        colour, label = seen[who]
        w = f.width(label, "ui6", 9) + 16
        f.rect(410, y + 6, w, 18, r=9, fill=colour, fill_opacity=0.18, stroke=colour, sw=1)
        f.text(418, y + 18.5, label, "ui6", 9, t.ink)
        f.para(502, y + 18, use, 262, "ui", 10, lh=1.25, fill=t.muted)
        y += 42
    end = f.para(32, y + 20, "A guild has three ids on purpose: members invite with the code, the map shows the tag, "
                 "and the log names the log id, so nobody can match a guild's public history to whose carets are where.",
                 736, "ui", 10.5, lh=1.36, fill=t.muted)  # fmt: skip
    f.h = round(end + 30)
    f.footer("Sources: worker/src/survey-social.js · players.js · achievements.js · survey-pass.js · leaderboard.js")
    return f


# =============================================================================
# Cost and scale
# =============================================================================
def lx(v: float, lo: float, hi: float, x0: float, x1: float) -> float:
    """A value on a log axis."""
    return x0 + (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (x1 - x0)


# Per player-hour, from SURVEY.md's design and the 700-player run, and Workers Paid's published prices.
PER_PLAYER_HOUR = {"worker": 30, "do": 106, "gbs": 0.35}


def monthly_bill(online: float, hours: float = 720) -> dict[str, float]:
    """A month on Workers Paid with `online` players around the clock, by part, in dollars."""
    ph = online * hours
    return {
        "base": 5.0,
        "do": max(0, PER_PLAYER_HOUR["do"] * ph - 1e6) * 0.15 / 1e6,
        "worker": max(0, PER_PLAYER_HOUR["worker"] * ph - 10e6) * 0.30 / 1e6,
        "gbs": max(0, PER_PLAYER_HOUR["gbs"] * ph - 400_000) * 12.50 / 1e6,
    }


@figure(
    "cost-curve",
    "cost",
    "What the survey costs, by players online",
    "The survey's bill, worked out from SURVEY.md's figures per player-hour (about 30 Worker requests, 106 "
    "Durable Object requests and 0.35 GB-seconds of Durable Object time) and Workers Paid's published prices. "
    "It stays at the $5 plan until about a hundred people are online around the clock, because outgoing "
    "WebSocket messages are free and incoming ones count as a twentieth of a request. The ceiling is the cap "
    "itself: at 25,000 online, about $0.73 an hour. On the free plan, Durable Object requests would run out "
    "at about 940 player-hours a day, and every Durable Object on the account would stop "
    "until midnight UTC.",
    "A stacked area chart. The horizontal axis is players online around the clock for a month, on a log "
    "scale from 1 to 25,000; the vertical axis is the monthly bill in dollars, from 0 to 600. The bill is a "
    "flat $5 up to about a hundred players, about $20 at 1,000, about $210 at 10,000 and about $525 at the "
    "25,000 cap, made mostly of Durable Object requests, then Worker requests, then Durable Object time. A "
    "dashed line at about 39 players marks where the free plan's daily Durable Object requests would run "
    "out.",
    [
        ("Per player-hour: ~30 Worker requests, ~106 Durable Object requests, ~0.35 GB-s", "worker/SURVEY.md 'Cost'"),
        (
            "Workers Paid: $5 a month with 10 M requests, then $0.30 per million; Durable Objects: 1 M requests, then "
            "$0.15 per million, incoming WebSocket messages at 1/20 of a request, outgoing free; 400,000 GB-s, then "
            "$12.50 per million",
            "worker/SURVEY.md 'Cost' (published prices)",
        ),
        (
            "Ceiling at MAX_ONLINE = 25,000: ~$0.22/h Worker requests, ~$0.40/h DO requests, ~$0.11/h DO time, at most "
            "~$0.75 an hour (~$18 a day); this chart's model gives $0.73",
            "worker/SURVEY.md; monthly_bill() here",
        ),
        ("1,000 players 2 hours a day for a month: about $6", "worker/SURVEY.md (and this model: $5.80)"),
        (
            "Free plan: 100,000 Durable Object requests a day, enough for ~940 player-hours; every Durable Object stops "
            "until 00:00 UTC past it",
            "worker/SURVEY.md 'Why Workers Paid'",
        ),
        (
            "The surveyor list and emotes add about $1.50 a day at 10,000 online, guilds about $0.30; not in the curve",
            "worker/SURVEY.md",
        ),
        (
            "The first version, with timers, would have cost ~$0.0056 per busy sector-hour: ~$84 a day for 625 busy "
            "sectors",
            "worker/SURVEY.md",
        ),
    ],
)
def cost_curve(t: Theme) -> Fig:
    f = Fig(t, 640)
    f.header("Letterfield · cost and scale", "What the survey costs, by players online")
    x0, x1, y0, y1 = 82, 560, 128, 470  # plot box: y0 top, y1 bottom
    lo, hi, ymax = 1, 25_000, 600
    yv = lambda v: y1 - v / ymax * (y1 - y0)  # noqa: E731
    for v in range(0, ymax + 1, 100):
        f.line(x0, yv(v), x1, yv(v), t.rule, 1)
        f.text(x0 - 8, yv(v) + 3.5, f"${v}", "ui", 9.5, t.muted, "end")
    for v in (1, 10, 100, 1000, 10_000, 25_000):
        f.line(lx(v, lo, hi, x0, x1), y1, lx(v, lo, hi, x0, x1), y1 + 4, t.muted, 1)
        f.text(lx(v, lo, hi, x0, x1), y1 + 18, fmt(v), "ui", 9.5, t.muted, "middle")
    f.text((x0 + x1) / 2, y1 + 38, "players online, around the clock (log scale)", "ui5", 10, t.ink, "middle")
    f.text(x0 - 50, y0 - 14, "a month", "ui5", 10, t.ink)
    # Stacked parts.
    teal, copper, indigo, _ = t.series
    parts = [("base", t.muted, "the $5 plan"), ("do", teal, "Durable Object requests"),
             ("worker", indigo, "Worker requests"), ("gbs", copper, "Durable Object time")]  # fmt: skip
    xs = [10 ** (i / 120 * math.log10(hi)) for i in range(121)]
    bills = [monthly_bill(v) for v in xs]
    below = [0.0] * len(xs)
    for key, colour, _ in parts:
        above = [b + bill[key] for b, bill in zip(below, bills)]
        top = " L".join(f"{lx(v, lo, hi, x0, x1):.1f} {yv(a):.1f}" for v, a in zip(xs, above))
        bottom = " L".join(f"{lx(v, lo, hi, x0, x1):.1f} {yv(b):.1f}" for v, b in reversed(list(zip(xs, below))))
        f.path(f"M{top} L{bottom}Z", fill=colour, fill_opacity=0.22 if key != "base" else 0.16)
        f.path("M" + top, stroke=colour, sw=2)
        below = above
    # Marks.
    free = 940 / 24
    fx = lx(free, lo, hi, x0, x1)
    f.line(fx, y0, fx, y1, t.danger, 1.3, dash="4 3")
    f.label(fx + 6, y0 + 12, "free plan runs out:", "ui6", 9.5, t.ink)
    f.label(fx + 6, y0 + 25, "~940 player-hours a day", "ui", 9.5, t.muted)
    for v, dx, anchor in ((1000, -6, "end"), (10_000, -8, "end"), (25_000, -6, "end")):
        total = sum(monthly_bill(v).values())
        px, py = lx(v, lo, hi, x0, x1), yv(total)
        f.circle(px, py, 4, fill=t.ink, stroke=t.paper, sw=2)
        f.label(px + dx, py - 9, f"${total:,.0f} a month", "ui6", 10, t.ink, anchor)
    f.text(x1 - 6, yv(sum(monthly_bill(25_000).values())) + 18, "the cap: 25,000 online", "ui", 9.5, t.muted, "end")
    # Legend and notes.
    lx0 = 594
    f.eyebrow(lx0, 136, "Parts of the bill")
    for i, (_key, colour, label) in enumerate(reversed(parts)):
        y = 156 + i * 20
        f.rect(lx0, y - 9, 12, 12, r=2, fill=colour, fill_opacity=0.5)
        f.text(lx0 + 20, y + 1, label, "ui", 10.5)
    f.eyebrow(lx0, 262, "Per player-hour")
    for i, line in enumerate(["~30 Worker requests", "~106 Durable Object requests", "~0.35 GB-s of object time"]):
        f.text(lx0, 280 + i * 16, line, "ui", 10.5)
    f.para(lx0, 346, "Outgoing WebSocket messages are free and incoming ones count as 1/20 of a request; there's no "
           "egress fee.", 174, "ui", 9.5, lh=1.3, fill=t.muted)  # fmt: skip
    f.para(lx0, 410, "The first version, with timers keeping sectors awake, would have cost ~$84 a day with all 625 "
           "sectors busy. Now the ceiling is ~$18.", 174, "ui", 9.5, lh=1.3, fill=t.muted)  # fmt: skip
    f.para(32, 534, "Worked out from SURVEY.md's usage per player-hour and Workers Paid's published prices, for a "
           "30-day month with the included allowances taken off. The surveyor list and emotes add about $1.50 a day at "
           "10,000 online and guilds about $0.30, which the curve leaves out.", 736, "ui", 10, lh=1.36, fill=t.muted)  # fmt: skip
    f.footer("Sources: worker/SURVEY.md 'Cost', 'Why Workers Paid' · prices as SURVEY.md quotes them")
    return f


LOAD_RUNS = [  # worker/SURVEY.md "Measured on the Workers runtime"
    ("first version", 200, "200 connected", 38, 261, 459, None, False),
    ("first version", 750, "410 connected, stalled", 1200, 17_000, 22_000, 100, False),
    ("positions kept in memory", 750, "630 connected", 600, 9600, 16_000, 97, False),
    ("+ claims batched", 750, "750 connected", 61, 305, 435, 84, False),
    ("+ claims batched", 1000, "990 connected", 148, 12_000, 25_000, 98, False),
    ("final", 700, "700 connected", 3, 124, 195, 55, True),
    ("final, capped at 750", 900, "750 in, 150 turned away", 3, 128, 190, None, True),
]


@figure(
    "load-test",
    "cost",
    "How much one sector holds",
    "Real WebSocket players against the Worker, each sending a position every two seconds and claiming a word "
    "every 20 to 40 seconds, on Cloudflare's workerd runtime running locally (so the numbers are relative, not "
    "Cloudflare's edge). The first version stalled at about 410 players. Keeping positions in memory, then "
    "batching claims every 200 ms, and finally dropping the timers took a sector to 700 players with a claim "
    "answered in 3 ms at the median and under 200 ms at the 99th percentile, so MAX_PLAYERS is 750.",
    "A dot plot on a log scale of claim round-trip time, from 1 millisecond to 30 seconds, one row per load "
    "test. Each row shows the median, 95th and 99th percentile joined by a line. The first version with 200 "
    "players: 38, 261 and 459 milliseconds. With 750 it stalled at 410 connected: 1.2, 17 and 22 seconds. "
    "Positions in memory: 0.6, 9.6 and 16 seconds. Claims batched: 61, 305 and 435 milliseconds at 750, but "
    "148 milliseconds, 12 and 25 seconds at 1,000. The final version, highlighted: 3, 124 and 195 milliseconds "
    "at 700 players with 55 percent of a core, and 3, 128 and 190 with 900 players asking, 750 let in.",
    [
        (
            "Load test: positions every ~2 s, a random hidden word every 20–40 s, players connecting at 40 a second, "
            "wrangler dev on a shared 4-core sandbox",
            "worker/SURVEY.md 'Measured on the Workers runtime'",
        ),
        ("Each row's p50 / p95 / p99, connected count and sector CPU", "worker/SURVEY.md table"),
        ("MAX_PLAYERS = 750 ('one sector saturates between 750 and 1,000')", "worker/src/survey.js"),
        (
            "Our own code takes about 3 ms of work per second for 1,000 players in Node; the rest is the runtime's "
            "per-message work",
            "worker/SURVEY.md; worker/bench/sector.js",
        ),
        ("Batching claims: 'took a sector from saturating at ~630 players to handling 750'", "worker/SURVEY.md"),
    ],
)
def load_test(t: Theme) -> Fig:
    f = Fig(t, 560)
    f.header("Letterfield · cost and scale", "How much one sector holds")
    x0, x1, lo, hi = 250, 596, 1, 30_000
    top = 142
    rows_y = [top + 26 + i * 44 for i in range(len(LOAD_RUNS))]
    for v, label in ((1, "1 ms"), (10, "10 ms"), (100, "100 ms"), (1000, "1 s"), (10_000, "10 s")):
        x = lx(v, lo, hi, x0, x1)
        f.line(x, top, x, rows_y[-1] + 18, t.rule, 1)
        f.text(x, top - 8, label, "ui", 9.5, t.muted, "middle")
    f.eyebrow(32, top - 8, "Run")
    f.eyebrow(684, top - 8, "Sector CPU")
    for (name, players, conn, p50, p95, p99, cpu, final), y in zip(LOAD_RUNS, rows_y):
        if final:
            f.rect(28, y - 22, 740, 40, r=5, fill=t.accent, fill_opacity=0.08)
        colour = t.accent if final else t.muted
        f.text(36, y - 3, f"{fmt(players)} players · {name}", "ui6", 10.5, t.ink)
        f.text(36, y + 11, conn, "ui", 9.5, t.muted)
        a, b, c = (lx(v, lo, hi, x0, x1) for v in (p50, p95, p99))
        f.line(a, y, c, y, colour, 2)
        for x, r in ((a, 4.5), (b, 4.5), (c, 4.5)):
            f.circle(x, y, r, fill=colour, stroke=t.paper, sw=2)
        ms = lambda v: f"{v / 1000:g} s" if v >= 1000 else f"{v} ms"  # noqa: E731
        f.text(a, y - 9, ms(p50), "ui", 8.8, t.ink, "middle")
        f.text(c + 8, y + 3.5, f"{ms(p95)} · {ms(p99)}", "ui", 8.8, t.muted)
        if cpu:
            f.rect(684, y - 5, 50, 10, r=5, fill=t.rule)
            f.rect(684, y - 5, cpu / 2, 10, r=5, fill=colour)
            f.text(740, y + 3.5, f"{cpu}%", "ui5", 9.5, t.ink)
    f.text(x0, rows_y[-1] + 36, "claim round trip: median (labelled), 95th and 99th percentile (right), log scale",
           "ui", 9.5, t.muted)  # fmt: skip
    f.para(32, rows_y[-1] + 62, "Measured with wrangler dev, Cloudflare's workerd runtime run locally on a 4-core "
           "sandbox shared with the load generator: compare the rows, not the numbers with Cloudflare's edge.", 736, "ui",
           10, lh=1.36, fill=t.muted)  # fmt: skip
    f.footer("Sources: worker/SURVEY.md 'Measured on the Workers runtime' · worker/bench/load.js")
    return f


# =============================================================================
# How it was built
# =============================================================================
MILESTONES = [  # from main's history (data/history.json); PR numbers in brackets
    ("2026-10-28", "Letterfield (#1)"),
    ("2026-11-05", "One Million Words explored on Durable Objects (#7)"),
    ("2026-11-06", "the survey on; limits per address (#26); the log (#30)"),
    ("2026-11-08", "state machines (#48); map 4: 225 themes (#49)"),
    ("2026-11-10", "share cards (#58); definitions (#59)"),
    ("2026-11-12", "timelapse (#81); CI sharded, 19 → 3 min (#83)"),
    ("2026-11-13", "surveyors, emotes, guilds, devices (#94)"),
    ("2026-11-18", "achievements (#115)"),
    ("2026-11-20", "Lantern (#123); the soundtrack album (#124)"),
]


@figure(
    "timeline",
    "built",
    "78 pull requests in 24 days",
    "Letterfield began as a single-player word search on the site's first day, 28 October 2026. Everything "
    "since came as pull requests, almost "
    "all written by coding agents: 78 of them by 20 November, and from 7 November each with a preview of its own "
    "to play before it merged. "
    "The lines count Letterfield's code, merge by merge: the game's one file, its three companion pages, its "
    "code in the Worker and its tests; the bars along the bottom count its pull requests merged each day. The "
    "tests grew fastest of all.",
    "A line chart from 28 October to 20 November 2026 of Letterfield's lines of code at each merge to main. Its "
    "tests, in the game and the Worker, grow from 38 lines to about 18,200; the game, letterfield.html, from "
    "about 1,200 to 8,248; its Worker code to about 4,400; and the log, timelapse and soundtrack pages to about "
    "3,800. Milestones are numbered along the top: the shared survey explored on Durable Objects, the survey "
    "switched on with limits per address and the log on 6 November, state machines and map 4 with 225 themes, "
    "share cards and definitions, the timelapse and the site's CI sharded, surveyors, guilds and linked "
    "devices on 13 November, achievements, and the soundtrack album on 20 November. Small bars along the bottom "
    "count Letterfield's pull requests merged each day, up to 14 on 10 November.",
    [
        (
            "78 pull requests merged to main between 28 October and 20 November 2026 touched Letterfield's files",
            "git log --first-parent origin/main, each merge's changed files (render.py LETTERFIELD)",
        ),
        (
            "None of Letterfield's files changed on main except through a pull request",
            "git log --first-parent origin/main",
        ),
        (
            "73 of the 78 came from claude/ branches, the ones Claude Code sessions push to; the other five "
            "(#99, #100, #104, #106, #109) from branches named otherwise",
            "the pull requests' head branches on GitHub",
        ),
        (
            "Every pull request got a preview of the site and the Worker from 7 November (#34, itself one of "
            "Letterfield's): 11 merged before it and 66 after",
            ".github/workflows/preview.yml, added in 159010d",
        ),
        (
            "Line counts at each merge: letterfield.html; letterfield-log, -timelapse and -soundtrack.html; "
            "Letterfield's Worker modules (survey*.js, letterfield-world.js, players.js, achievements.js, define.js); "
            "its tests (tests/test_letterfield*, test_survey_watch, its fakes, and worker/test for those modules)",
            "git show at each merge (data/history.json)",
        ),
        ("At 20 November: game 8,248 lines; pages 3,813; Worker code 4,401; tests 18,178", "data/history.json"),
        ("The most Letterfield pull requests in a day: 14, on 10 November", "data/history.json"),
        (
            "Milestones: #1 Letterfield, #7 the survey explored, #26 limits per address, #30 the log, #48 state "
            "machines, #49 map 4, #58 share cards, #59 definitions, #81 timelapse, #83 CI sharded, #94 "
            "surveyors, guilds and devices, #115 achievements, #123 Lantern, #124 the album",
            "PR titles in main's history",
        ),
    ],
)
def timeline(t: Theme) -> Fig:
    from datetime import date

    f = Fig(t, 720)
    hist = json.loads((HERE / "data" / "history.json").read_text())
    ours = [r for r in hist if r["pr"]]
    f.header("Letterfield · how it was built", f"{len(ours)} pull requests in 24 days")
    d0, d1 = date(2026, 10, 28), date(2026, 11, 21)
    x0, x1, y0, y1, ymax = 82, 640, 150, 470, 21_000
    xd = lambda d: x0 + (date.fromisoformat(d) - d0).days / (d1 - d0).days * (x1 - x0)  # noqa: E731
    yv = lambda v: y1 - v / ymax * (y1 - y0)  # noqa: E731
    # It moves: the lines draw themselves across the 24 days, and each day's bar and each milestone appear as
    # the lines reach them.
    f.animate(12)
    draw_from, draw_to, gone = 0.4, 8.4, 11.4
    when = lambda x: draw_from + (x - x0) / (x1 - x0) * (draw_to - draw_from)  # noqa: E731

    def appears(at):
        return f.cue([(at, "opacity:0"), (at + 0.25, "opacity:1"), (gone, "opacity:1"), (gone + 0.5, "opacity:0")])

    for v in range(0, ymax, 5000):
        f.line(x0, yv(v), x1, yv(v), t.rule, 1)
        f.text(x0 - 8, yv(v) + 3.5, f"{v // 1000}K" if v else "0", "ui", 9.5, t.muted, "end")
    f.text(x0 - 50, y0 - 38, "lines of code", "ui5", 10, t.ink)
    for i in range((d1 - d0).days + 1):
        d = date.fromordinal(d0.toordinal() + i)
        if d.day in (1, 5, 10, 15, 20, 28):
            f.text(xd(d.isoformat()), y1 + 16, d.strftime("%-d %b"), "ui", 9.5, t.muted, "middle")
    # PRs a day, as small bars under the axis.
    per_day: dict[str, int] = {}
    for r in ours:
        per_day[r["date"]] = per_day.get(r["date"], 0) + 1
    for d, n in per_day.items():
        x = xd(d) + (x1 - x0) / (d1 - d0).days / 2
        with f.group(appears(when(x))):
            f.rect(x - 4, y1 + 60 - n * 2.4, 8, n * 2.4, r=1.5, fill=t.muted, opacity=0.7)
    busiest = max(per_day, key=per_day.get)
    f.text(x0, y1 + 74, f"Letterfield's pull requests merged each day (the most: {per_day[busiest]}, on "
           f"{date.fromisoformat(busiest).strftime('%-d %b')})", "ui", 9.5, t.muted)  # fmt: skip
    # The series: each merge's line counts, as steps through the day.
    teal, copper, indigo, rose = t.series
    series = [("tests", rose, "its tests"), ("game", teal, "letterfield.html"), ("worker", indigo, "its Worker code"),
              ("pages", copper, "log, timelapse, album")]  # fmt: skip
    for key, colour, label in series:
        pts, seen = [], {}
        for r in hist:
            seen[r["date"]] = r[key]
        for d, v in sorted(seen.items()):
            pts.append((xd(d) + (x1 - x0) / (d1 - d0).days, yv(v)))
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        # Drawn by its dash: a path of length 1 whose dash's offset runs from 1 to 0 as the days go by.
        drawn = f.cue([(0, "stroke-dashoffset:1;opacity:1"), (draw_from, "stroke-dashoffset:1;opacity:1"),
                       (draw_to, "stroke-dashoffset:0;opacity:1"), (gone, "stroke-dashoffset:0;opacity:1"),
                       (gone + 0.5, "stroke-dashoffset:0;opacity:0")])  # fmt: skip
        f.add(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="2" stroke-linecap="round" pathLength="1"'
              f' stroke-dasharray="1" class="{drawn}"/>')  # fmt: skip
        ex, ey = pts[-1]
        with f.group(appears(draw_to)):
            f.circle(ex, ey, 4, fill=colour, stroke=t.paper, sw=2)
            f.text(ex + 10, ey + 3.5, f"{label} {fmt(hist[-1][key])}", "ui6", 10, t.ink)
    # Milestones: numbered on the chart, named in a key below it.
    for i, (d, label) in enumerate(MILESTONES):
        x = xd(d) + (x1 - x0) / (d1 - d0).days / 2
        with f.group(appears(when(x))):
            f.line(x, y0 - 8, x, y1, t.accent, 1, dash="2 3", opacity=0.55)
            f.circle(x, y0 - 16, 8, fill=t.accent)
            f.text(x, y0 - 12.5, str(i + 1), "ui6", 9.5, t.on_accent, "middle")
        kx, ky = 32 + (i // 5) * 372, y1 + 104 + (i % 5) * 17
        f.text(kx, ky, f"{i + 1}", "ui6", 9.5, t.accent)
        f.text(kx + 14, ky, f"{date.fromisoformat(d).strftime('%-d %b')} · {label}", "ui", 9.8, t.ink)
    f.footer(
        "Sources: git log --first-parent origin/main · Letterfield's files at each merge (docs/architecture/data/history.json)"
    )
    return f


@figure(
    "eieio-lessons",
    "server",
    "What One Million Checkboxes taught",
    "The survey borrows its shape from eieio's One Million Checkboxes and One Million Chessboards, and from "
    "the two write-ups of how they scaled. Each row pairs a lesson from those games with where it shows up in "
    "Letterfield's survey, which runs on Cloudflare rather than one big server: state as small as possible, "
    "only nearby updates, batching, global data from a cache, a hard ceiling on the bill, validating "
    "everything, and limits per address.",
    "A two-column table with nine rows, eieio's games on the left and Letterfield's survey on the right. "
    "State: a 125 KB bitset of checkboxes, against claims stored with initials (a bitset of the hidden words "
    "would be 137 KB). Updates: 3 by 3 zones around a player, against the at most four sectors in view. "
    "Batching every 200 ms in both. Global data cached at the edge, against a world map cached for five "
    "seconds. Bandwidth as the one unbounded cost, against free egress on Cloudflare. Bounded costs, against "
    "caps per sector and on the whole survey. Validating everything, against every claim checked with the "
    "generator. Rate limits for bots, against limits per socket and per address. One process on one box, "
    "against a Durable Object per sector.",
    [
        ("The table's rows and figures", "worker/SURVEY.md 'What eieio's games teach, and where it shows up here'"),
        ("OMCB's state was a 125 KB bitset; the universe's would be 137 KB (1,119,752 bits)", "worker/SURVEY.md"),
        ("Batching 'took a sector from saturating at ~630 players to handling 750'", "worker/SURVEY.md"),
        ("OMCB cost about $850; One Million Chessboards 'a few hundred dollars'", "worker/SURVEY.md 'Cost'"),
        (
            "Sources: eieio.games/blog/scaling-one-million-checkboxes and "
            "eieio.games/blog/a-million-realtime-chess-boards-in-a-single-process",
            "worker/SURVEY.md links",
        ),
    ],
)
def eieio_lessons(t: Theme) -> Fig:
    f = Fig(t, 760)
    f.header("Letterfield · the server", "What One Million Checkboxes taught")
    rows = [
        (
            "State",
            "OMCB's whole state was a 125 KB bitset, one bit per box",
            "claims with initials; a bitset of every hidden word would be 137 KB",
        ),
        (
            "Only what's near",
            "Chessboards sent each player moves in the 3 × 3 zones around them",
            "sectors of 192 × 192 cells; a player joins the ≤ 4 in view",
        ),
        (
            "Batching",
            "moves went out every 200 ms, which 'massively reduced load'",
            "claims go out every 200 ms: a sector held 750 players, up from ~630",
        ),
        (
            "Global data",
            "served over HTTP with a short max-age, absorbed by Cloudflare's cache",
            "the world map is a GET cached 5 s; the Atlas hears only from sectors",
        ),
        (
            "Bandwidth",
            "'my one unbounded cost'; OMCB capped its server at 250 Mbit/s",
            "Cloudflare charges no egress, and outgoing WebSocket messages are free",
        ),
        (
            "Bound the bill",
            "'instead of going serverless and scaling into bankruptcy'",
            "750 sockets a sector, 25,000 online in all: at most ~$18 a day",
        ),
        (
            "Validate everything",
            "someone checked box 100,000,000 and broke OMCB",
            "every claim is checked against the server's copy of the generator",
        ),
        (
            "Bots",
            "absurd traffic once the Go rewrite made things fast",
            "5 claims then 1 per 1.5 s a socket; 6 a minute and 300 a day an address",
        ),
        (
            "One machine",
            "one Go process on one box, later an ~$80/month one",
            "a Durable Object is one thread, so the world is split by place",
        ),
    ]
    y = 118
    f.rect(32, y, 736, 26, r=5, fill=t.panel)
    f.eyebrow(44, y + 17, "Lesson")
    f.eyebrow(176, y + 17, "eieio's games")
    f.eyebrow(476, y + 17, "Letterfield's survey")
    y += 34
    for i, (lesson, theirs, ours) in enumerate(rows):
        lt = f.wrap(theirs, 280, "ui", 10.5)
        lo = f.wrap(ours, 284, "ui", 10.5)
        h = max(len(lt), len(lo)) * 14.5 + 18
        if i % 2 == 0:
            f.rect(32, y, 736, h, r=4, fill=t.panel, opacity=0.6)
        f.text(44, y + 19, lesson, "ui6", 11)
        for n, line in enumerate(lt):
            f.text(176, y + 19 + n * 14.5, line, "ui", 10.5, t.muted)
        f.rect(462, y + 8, 3, h - 16, r=1.5, fill=t.kinds["object"])
        for n, line in enumerate(lo):
            f.text(476, y + 19 + n * 14.5, line, "ui", 10.5, t.ink)
        y += h + 3
    end = f.para(32, y + 22, "From 'Scaling One Million Checkboxes' and 'Running a million-board chess MMO in a single "
                 "process' on eieio.games, as SURVEY.md quotes them. OMCB cost about $850 to run; the survey costs the "
                 "$5 plan while nobody plays.", 736, "ui", 10, lh=1.36, fill=t.muted)  # fmt: skip
    f.h = round(end + 30)
    f.footer("Sources: worker/SURVEY.md 'What eieio's games teach' · eieio.games")
    return f


@figure(
    "ci-previews",
    "built",
    "How a change ships",
    "Every change is a pull request. CI runs only the tests its files need, split across up to three shards "
    "of four workers each, plus the linters and the two Workers' own tests, and a single required check, "
    "test, stands for them all. Meanwhile a preview workflow builds the pull request's own copy of the site "
    "and of each Worker on Cloudflare, so it can be tried on a phone, with its own empty survey, before "
    "merging. Merging to main deploys the site to GitHub Pages and, when they changed, the Workers, "
    "migrations first.",
    "A flow from left to right. A pull request runs two workflows. Test: a plan job picks the tests the "
    "changes need, then pytest in up to three shards of four workers, the lint job, and node tests for the "
    "two Workers, all feeding one required check called test. Preview: a Worker "
    "Preview of games-leaderboard (taking turns when the branch brings migrations), a Preview of games-share "
    "when it changed, then the site built with build.sh, its URLs pointed at those Previews, uploaded as a "
    "Preview of games-preview, and a comment with the links. After merging to main: GitHub Pages deploys the "
    "site, the Worker deploy applies migrations then deploys, and the share Worker deploys. A nightly job "
    "watches the survey for bots.",
    [
        (
            "Test: plan → pytest shards (up to 3, 4 workers each), lint, worker and share node tests → test",
            ".github/workflows/test.yml; AGENTS.md 'Tests in parallel'",
        ),
        (
            "A pull request runs only the tests its changes need (scripts/select_tests.py); main runs them all",
            "AGENTS.md",
        ),
        (
            "Previews: pr-<n>-games-leaderboard, pr-<n>-games-share (when share/ or worker/src/ changed) and "
            "pr-<n>-games-preview, on workers.dev, deleted when the PR closes",
            ".github/workflows/preview.yml; AGENTS.md",
        ),
        ("Worker Previews take turns only when the branch brings migrations", "worker/README.md 'Previews'"),
        ("Pages: build.sh then GitHub Pages on every push to main", ".github/workflows/pages.yml"),
        (
            "Worker deploy on worker/** changes: d1 migrations apply (both databases), then wrangler deploy; the share "
            "Worker deploys on share/** or worker/src/** changes",
            ".github/workflows/leaderboard.yml, share.yml",
        ),
        ("Survey watch at 00:23 UTC every day", ".github/workflows/survey-watch.yml"),
        ("711 pytest functions, 422 Worker tests and 74 share Worker tests at commit 44fe976", "counted with grep"),
        ("About 20 minutes one test at a time; CI sharding took it to about 3", "AGENTS.md; PR #83"),
    ],
)
def ci_previews(t: Theme) -> Fig:
    f = Fig(t, 640)
    f.header("Letterfield · how it was built", "How a change ships")
    k = t.kinds
    # The pull request.
    f.rect(32, 210, 112, 64, r=7, fill=t.panel, stroke=k["browser"], sw=1.4)
    f.text(88, 236, "A pull request", "ui6", 11.5, anchor="middle")
    f.text(88, 252, "from an agent's", "ui", 9.5, t.muted, "middle")
    f.text(88, 264, "branch", "ui", 9.5, t.muted, "middle")
    # Test.
    tx, ty = 176, 116
    f.rect(tx, ty, 300, 186, r=8, fill="none", stroke=t.rule, dash="3 3")
    f.eyebrow(tx + 12, ty + 18, "Test workflow")
    f.rect(tx + 12, ty + 30, 70, 30, r=5, fill=t.panel, stroke=t.rule)
    f.text(tx + 47, ty + 49, "plan", "ui6", 10.5, anchor="middle")
    jobs = [("pytest 1/3", "4 workers"), ("pytest 2/3", "4 workers"), ("pytest 3/3", "4 workers"), ("lint", "ruff, Biome…"),
            ("worker tests", "node --test"), ("share tests", "node --test")]  # fmt: skip
    for i, (name, sub) in enumerate(jobs):
        jx, jy = tx + 100 + (i % 2) * 96, ty + 30 + (i // 2) * 40
        f.rect(jx, jy, 88, 32, r=5, fill=t.panel, stroke=t.rule)
        f.text(jx + 8, jy + 14, name, "ui6", 9.5)
        f.text(jx + 8, jy + 26, sub, "ui", 8.6, t.muted)
    f.arrow([(tx + 82, ty + 45), (tx + 100, ty + 45)], t.muted, 1.2, head=4.5)
    f.rect(tx + 12, ty + 144, 276, 30, r=15, fill=k["object"], fill_opacity=0.16, stroke=k["object"])
    f.text(tx + 150, ty + 163, "test: the one check main requires", "ui6", 10.5, anchor="middle")
    f.para(tx + 12, ty + 208, "Only the tests a change needs; main runs all ~20 minutes of them, about 3 when sharded.",
           290, "ui", 9.5, lh=1.3, fill=t.muted)  # fmt: skip
    # Preview.
    px, py = 176, 360
    f.rect(px, py, 300, 156, r=8, fill="none", stroke=t.rule, dash="3 3")
    f.eyebrow(px + 12, py + 18, "Preview workflow")
    pv = [("games-leaderboard", "a Worker Preview of its own", k["worker"]),
          ("games-share", "when share/ or worker/src/ changed", k["worker"]),
          ("games-preview", "the site, built and pointed at them", k["worker"])]  # fmt: skip
    for i, (name, sub, _colour) in enumerate(pv):
        yy = py + 28 + i * 40
        cell_box(f, px + 12, yy, 276, 36, f"pr-<n>-{name}", "worker", sub, size=10, align="start")
    f.arrow([(144, 250), (160, 250), (160, 200), (tx, 200)], t.muted, 1.3)
    f.arrow([(160, 250), (160, py + 60), (px, py + 60)], t.muted, 1.3)
    f.para(px + 12, py + 172, "Each preview has its own empty survey and storage; a comment on the pull request "
           "links to them.", 290, "ui", 9.5, lh=1.3, fill=t.muted)  # fmt: skip
    # Merge and deploy.
    mx = 520
    f.arrow([(tx + 300, ty + 159), (mx - 4, ty + 159), (mx - 4, 300), (mx + 20, 300)], k["object"], 1.4)
    f.arrow([(px + 300, py + 75), (mx - 4, py + 75), (mx - 4, 300)], t.muted, 1.2, dash="1 4", end=False)
    f.rect(mx + 20, 276, 90, 48, r=7, fill=t.panel, stroke=t.ink, sw=1.3)
    f.text(mx + 65, 297, "merge", "ui6", 11.5, anchor="middle")
    f.text(mx + 65, 312, "squashed, to main", "ui", 8.8, t.muted, "middle")
    deploys = [("GitHub Pages", "build.sh, every push", "browser"), ("games-leaderboard", "migrations, then deploy",
               "worker"), ("games-share", "share/, worker/src/", "worker")]  # fmt: skip
    for i, (name, sub, kind) in enumerate(deploys):
        dy = 206 + i * 64
        cell_box(f, 646, dy, 122, 48, name, kind, sub, size=10.5)
        f.arrow([(mx + 110, 300), (630, 300), (630, dy + 24), (646, dy + 24)], t.muted, 1.2)
    f.eyebrow(646, 420, "Every night")
    cell_box(f, 646, 430, 122, 48, "survey watch", "other", "00:23 UTC, for bots", size=10.5)
    # It moves: a pull request runs both workflows at once; the jobs run in parallel to the one check, the
    # previews come up, the pull request merges, and main deploys what changed.
    f.animate(9)
    f.glow(32, 210, 112, 64, 0.1, 0.8, k["browser"], r=7)
    f.travel([(144, 250), (160, 250), (160, 200), (tx, 200)], 0.4, 1.0, k["browser"])
    f.travel([(144, 250), (160, 250), (160, py + 60), (px, py + 60)], 0.4, 1.2, k["browser"])
    f.glow(tx + 12, ty + 30, 70, 30, 1.0, 0.7, t.accent, r=5)
    for i in range(len(jobs)):
        f.glow(tx + 100 + (i % 2) * 96, ty + 30 + (i // 2) * 40, 88, 32, 1.6 + (i % 3) * 0.12, 1.4, t.accent, r=5)
    f.glow(tx + 12, ty + 144, 276, 30, 3.3, 1.0, k["object"], r=15)
    for i in range(3):
        f.glow(px + 12, py + 28 + i * 40, 276, 36, 1.4 + i * 0.8, 1.0, k["worker"])
    f.travel([(tx + 300, ty + 159), (mx - 4, ty + 159), (mx - 4, 300), (mx + 20, 300)], 4.2, 4.9, k["object"])
    f.glow(mx + 20, 276, 90, 48, 4.9, 0.9, t.ink, r=7)
    for i in range(3):
        dy = 206 + i * 64
        f.travel([(mx + 110, 300), (630, 300), (630, dy + 24), (646, dy + 24)], 5.3 + i * 0.15, 6.0 + i * 0.15, t.muted)
        f.glow(646, dy, 122, 48, 6.0 + i * 0.15, 1.0, k["worker"] if i else k["browser"])
    f.footer("Sources: .github/workflows/{test,preview,pages,leaderboard,share,survey-watch}.yml · AGENTS.md")
    return f


# =============================================================================
# The index and the fact-check notes
# =============================================================================
# The posts the figures are grouped into, in a suggested order: (key, title, a line on what it covers).
POSTS = [
    ("map", "An endless word search from one seed",
     "Letterfield's map has no edge and nothing stored: one seed, a deck of words for each territory and a few "
     "placement rules make every letter, so the server can check a word with the game's own code."),
    ("server", "A Durable Object for every patch of the map",
     "The shared survey shards by place: 625 sectors, each a Durable Object with its own SQLite and sockets, "
     "joined four at a time, and one Atlas for the totals, in the spirit of One Million Checkboxes."),
    ("claims", "The life of a claim",
     "One thread per sector settles a race with a plain insert; around it, limits per socket, per address and "
     "per day, and the generator's own check, keep it fair."),
    ("supernova", "Supernovas: news that travels",
     "When a territory's last hidden word is charted, its sector tells its neighbours at once and the Atlas tells "
     "every other sector in the universe, so everyone nearby sees the burst."),
    ("log", "Every word, in D1",
     "Each sector copies its words to D1 from an alarm, triggers count them on the way in, and three layers of "
     "cache serve the log and the timelapse."),
    ("devices", "One surveyor, many devices",
     "A surveyor is a hash of a random token; a one-time code or a recovery code makes another device the same "
     "surveyor, and a Player object keeps their notes in step."),
    ("cost", "What it costs, and how far it goes",
     "Worked out from the survey's use per player-hour: the $5 plan until about a hundred people are online around "
     "the clock, and at most about $0.73 an hour at the cap of 25,000."),
    ("built", "How it was built",
     "78 pull requests in 24 days, almost all by coding agents, and from 7 November each with its own copy of "
     "the site and the Worker to play on a phone before it merged."),
]  # fmt: skip


def _between(text: str, name: str, body: str) -> str:
    start, end = f"<!-- BEGIN {name} -->", f"<!-- END {name} -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    return pattern.sub(lambda _: f"{start}\n{body}\n{end}", text)


KINDS = {"explainer": "Interactive explainer", "clip": "Clip", "screen": "Game screen"}


def write_docs() -> None:
    """README.md's posts, with every figure's caption and alt text, and FACTS.md's list of facts, written
    from the figures here and the explainers, clips and screens in extras.py."""
    from extras import EXTRAS

    cell = lambda text: text.replace("|", "\\|")  # noqa: E731
    posts, facts = [], []
    for n, (key, title, outline) in enumerate(POSTS, 1):
        posts.append(f"### {n}. {title}\n\n{outline}\n")
        facts.append(f"### {n}. {title}\n")
        items = []
        for f in FIGURES.values():
            if f.post != key:
                continue
            moves = f.draw(THEMES[0]).cycle  # a figure that moves loops in its SVG, and has clips too
            files = f"figures/{f.id}-light.svg · -dark.svg · .png" + (" · .mp4 · .gif" if moves else "")
            label = "Figure"
            if moves:
                article = "an" if f"{moves:g}".startswith("8") or moves in (11, 18) else "a"
                label = f"Figure, moving in {article} {moves:g}-second loop"
            items.append((label, f.title, files, f))
        items += [(KINDS[e.kind], e.title, e.files, e) for e in EXTRAS if e.post == key]
        for kind, name, files, item in items:
            posts.append(
                f"#### {name}\n\n{kind}: `{files}`\n\n**Caption.** {item.caption}\n\n**Alt text.** {item.alt}\n"
            )
            rows = "\n".join(f"| {cell(fact)} | {cell(source)} |" for fact, source in item.facts)
            facts.append(f"#### {name}\n\n| Fact | Source |\n| --- | --- |\n{rows}\n")
    for name, block, body in (("README.md", "POSTS", posts), ("FACTS.md", "FACTS", facts)):
        path = HERE / name
        if path.exists():
            path.write_text(_between(path.read_text(), block, "\n".join(body)))
