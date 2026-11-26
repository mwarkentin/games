#!/usr/bin/env python3
"""Draw the Letterfield soundtrack's art: albums/letterfield/{cover,back,preview}.svg.

The cover is a corner of the map: four territories of the game's own themes,
each with the piece named after one of its words circled in its colour (DRIFT
in Deep Sea, ORBIT in Space, CHIMES in Orchestra, LANTERN in Glimmer), and a
fifth, Night Sky, going supernova, its shockwave pushing the letters aside.
The title sits in a panel like the game's own. The back lists the tracks, and
the preview is a link-preview card of the two. The cover also goes into
letterfield-soundtrack.html, inline.

Every letter is drawn as an outline from the game's fonts (Big Shoulders
Display and Martian Mono, both SIL Open Font License), so the SVGs render the
same anywhere, with no fonts and no network. Drawing them needs the fonts,
which this fetches from Google Fonts once into _album/fonts/, and fontTools
and uharfbuzz:

    uv run --with fonttools --with uharfbuzz scripts/draw_album_art.py

Then scripts/render_album.py renders them to JPGs. The SVGs are committed;
run this again only to change the art, and commit what it writes.
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
import urllib.request
from functools import cache
from pathlib import Path

from common import ROOT

sys.path.insert(0, str(Path(__file__).parent))
from render_album import ARTIST, LICENSE, TRACKS, YEAR  # noqa: E402

ART = ROOT / "albums" / "letterfield"
FONTS = ROOT / "_album" / "fonts"
FAMILIES = {
    "display": "Big+Shoulders+Display:wght@800",
    "mono": "Martian+Mono:wght@400",
    "mono-medium": "Martian+Mono:wght@500",
}

# letterfield.html's dark colours.
PAPER, PANEL, INK, MUTED, RULE, ACCENT = "#0F171A", "#162024", "#E2E7DE", "#93A19D", "#2B3A3E", "#97A9FF"

N = 14  # cells across and down
SIZE = 1200  # the cover's viewBox
CELL = SIZE / N
GLYPH = 0.44  # a letter's size in its cell (the game's is .42)

# Territories: [first column, first row, last column, last row], the theme
# whose colour it takes, and its word as (row, column, step down, step across).
TERRITORIES = [
    {"theme": "Orchestra", "hue": 223, "box": [0, 0, 7, 5], "word": ("CHIMES", 5, 1, 0, 1)},
    {"theme": "Night Sky", "hue": 168, "box": [8, 0, 13, 5], "word": None},
    {"theme": "Deep Sea", "hue": 298, "box": [0, 6, 4, 13], "word": ("DRIFT", 7, 2, 1, 0)},
    {"theme": "Space", "hue": 115, "box": [5, 6, 9, 13], "word": ("ORBIT", 8, 5, 1, 1)},
    {"theme": "Glimmer", "hue": 55, "box": [10, 6, 13, 13], "word": ("LANTERN", 6, 12, 1, 0)},
]
# The supernova, in Night Sky: its core, in cells, and its shockwave's reach.
NOVA = {"col": 11.1, "row": 2.2, "R": 300.0}
# The width of its front: thinner than the game's at this size, which would fill the circle.
BAND = 26.0

# Letters to fill the rest, by how often they turn up in English.
FREQ = "E" * 12 + "T" * 9 + "A" * 8 + "O" * 8 + "I" * 7 + "N" * 7 + "S" * 6 + "H" * 6 + "R" * 6 + "D" * 4 + "L" * 4
FREQ += "C" * 3 + "U" * 3 + "M" * 2 + "W" * 2 + "F" * 2 + "G" * 2 + "Y" * 2 + "P" * 2 + "B" * 2 + "VKJXQZ"


def fetch_fonts() -> dict[str, Path]:
    FONTS.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, family in FAMILIES.items():
        path = FONTS / f"{name}.ttf"
        if not path.exists():
            # Without a browser's User-Agent, Google Fonts answers with TrueType.
            css = urllib.request.urlopen(f"https://fonts.googleapis.com/css2?family={family}").read().decode()
            url = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)", css)[1]
            path.write_bytes(urllib.request.urlopen(url).read())
        paths[name] = path
    return paths


class Face:
    """A font's capitals as outlines, centred on the cap height, in font units."""

    def __init__(self, path: Path, prefix: str):
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.pens.transformPen import TransformPen
        from fontTools.ttLib import TTFont

        self.path, self.prefix = path, prefix
        self.font = TTFont(path)
        self.upm = self.font["head"].unitsPerEm
        self.cap = self.font["OS/2"].sCapHeight
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.used: dict[str, str] = {}
        self._pens = (SVGPathPen, TransformPen)

    def glyph_name(self, char: str) -> str:
        return self.cmap[ord(char)]

    def advance(self, char: str) -> int:
        return self.font["hmtx"][self.glyph_name(char)][0]

    def define(self, name: str, centred: bool) -> str:
        """The id of a glyph's outline, defined once; centred on its advance, or from its origin."""
        key = f"{self.prefix}-{name}" + ("" if centred else "-o")
        if key not in self.used:
            svg_pen, transform_pen = self._pens
            pen = svg_pen(self.glyphs, ntos=lambda v: str(round(v)))
            dx = -self.font["hmtx"][name][0] / 2 if centred else 0
            self.glyphs[name].draw(transform_pen(pen, (1, 0, 0, -1, dx, self.cap / 2)))
            self.used[key] = pen.getCommands()
        return key

    def defs(self) -> str:
        return "".join(f'<path id="{key}" d="{d}"/>' for key, d in self.used.items())

    @cache  # noqa: B019 - a few faces, alive for the whole run
    def shaper(self):
        import uharfbuzz as hb

        return hb.Font(hb.Face(self.path.read_bytes()))

    def run(self, text: str, x: float, y: float, size: float, fill: str, tracking: float = 0, anchor="start") -> str:
        """A line of text as outlines, with its kerning: y is the middle of its capitals."""
        import uharfbuzz as hb

        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.shaper(), buf, {"kern": True})
        scale = size / self.upm
        track = tracking * self.upm
        pen, placed = 0.0, []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            name = self.font.getGlyphName(info.codepoint)
            if self.glyphs[name].width and text[info.cluster] != " ":
                placed.append((self.define(name, centred=False), pen + pos.x_offset))
            pen += pos.x_advance + track
        width = (pen - track) * scale
        x0 = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
        uses = "".join(f'<use href="#{key}" x="{gx:.0f}"/>' for key, gx in placed)
        return f'<g fill="{fill}" transform="translate({x0:.2f} {y:.2f}) scale({scale:.6f})">{uses}</g>'

    def width(self, text: str, size: float, tracking: float = 0) -> float:
        import uharfbuzz as hb

        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.shaper(), buf, {"kern": True})
        return (sum(p.x_advance for p in buf.glyph_positions) + tracking * self.upm * (len(text) - 1)) * size / self.upm


def hsl(h: float, s: float, l: float, a: float = 1) -> str:
    return f"hsla({h:g},{s:g}%,{l:g}%,{a:g})" if a < 1 else f"hsl({h:g},{s:g}%,{l:g}%)"


def centre(col: float, row: float) -> tuple[float, float]:
    return (col + 0.5) * CELL, (row + 0.5) * CELL


def grid() -> tuple[list[list[str]], dict[tuple[int, int], dict]]:
    """Every cell's letter, and which cells hold a circled word's letters."""
    rnd = random.Random(20261120)
    cells = [[rnd.choice(FREQ) for _ in range(N)] for _ in range(N)]
    words = {}
    for t in TERRITORIES:
        if not t["word"]:
            continue
        word, row, col, dr, dc = t["word"]
        for i, ch in enumerate(word):
            r, c = row + dr * i, col + dc * i
            c0, r0, c1, r1 = t["box"]
            assert c0 <= c <= c1 and r0 <= r <= r1, f"{word} leaves {t['theme']}"
            assert (r, c) not in words, f"{word} crosses another word"
            cells[r][c] = ch
            words[(r, c)] = t
    return cells, words


def pill(t: dict) -> str:
    """The circle round a found word: a rounded band from its first letter to its last, in its theme's colour."""
    word, row, col, dr, dc = t["word"]
    x0, y0 = centre(col, row)
    x1, y1 = centre(col + dc * (len(word) - 1), row + dr * (len(word) - 1))
    length = math.hypot(x1 - x0, y1 - y0)
    angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
    h = CELL * 0.74
    return (
        f'<rect x="{-h / 2:.1f}" y="{-h / 2:.1f}" width="{length + h:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" '
        f'transform="translate({x0:.1f} {y0:.1f}) rotate({angle:g})" fill="{hsl(t["hue"], 75, 55, 0.22)}" '
        f'stroke="{hsl(t["hue"], 68, 68)}" stroke-width="5"/>'
    )


def nova_push(x: float, y: float) -> tuple[float, float, float, float]:
    """How far the shockwave moves a letter at x, y, how much it swells it, and how much it lights it.

    The game's novaLetter, with the wave stopped where it is."""
    cx, cy = centre(NOVA["col"], NOVA["row"])
    vx, vy = x - cx, y - cy
    d = math.hypot(vx, vy) or 1
    R, band, amp = NOVA["R"], BAND, 0.42
    u, u2 = (d - R) / band, (d - R * 0.74) / band
    g = math.exp(-u * u * 3) if u > 0 else math.exp(-u * u * 0.7) - 0.4 * math.exp(-((u + 1.8) ** 2))
    g = (g + 0.35 * math.exp(-u2 * u2 * 1.5)) * amp
    push = g * CELL * 0.9
    return vx / d * push, vy / d * push, 1 + max(0, g) * 1.5, max(0, g)


def nova_layers() -> tuple[str, str, str]:
    """The supernova's defs, what goes under the letters (the territory heating) and over them."""
    cx, cy = centre(NOVA["col"], NOVA["row"])
    R, band, hue = NOVA["R"], BAND, 168
    glow = lambda l, a: hsl(hue, 95, l, a)  # noqa: E731
    defs = [
        # The world dark ahead of the wave, lit behind it.
        f'<radialGradient id="lf-shade" gradientUnits="userSpaceOnUse" cx="{cx:.1f}" cy="{cy:.1f}" r="{R + band + 900:.1f}">'
        f'<stop offset="0" stop-color="#040716" stop-opacity="0"/>'
        f'<stop offset="{(R - band * 3) / (R + band + 900):.3f}" stop-color="#040716" stop-opacity="0"/>'
        f'<stop offset="{(R + band) / (R + band + 900):.3f}" stop-color="#040716" stop-opacity=".1"/>'
        f'<stop offset="1" stop-color="#040716" stop-opacity=".14"/></radialGradient>',
        f'<radialGradient id="lf-core" gradientUnits="userSpaceOnUse" cx="{cx:.1f}" cy="{cy:.1f}" r="210">'
        f'<stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset=".07" stop-color="{glow(88, 1)}" stop-opacity=".8"/>'
        f'<stop offset=".25" stop-color="{glow(60, 1)}" stop-opacity=".2"/><stop offset="1" stop-color="{glow(50, 1)}" stop-opacity="0"/></radialGradient>',
        f'<radialGradient id="lf-heat" gradientUnits="userSpaceOnUse" cx="{cx:.1f}" cy="{cy:.1f}" r="{R * 1.6:.1f}">'
        f'<stop offset="0" stop-color="{glow(45, 1)}" stop-opacity=".12"/><stop offset="1" stop-color="{glow(45, 1)}" stop-opacity=".03"/></radialGradient>',
    ]
    rings = []
    for i, (f, a) in enumerate([(1, 1), (0.74, 0.32), (0.52, 0.16)]):
        r, w = R * f, band * (2.2 if f == 1 else 1.5)
        outer = r + w * 0.3
        stops = [(max(0, r - w) / outer, glow(55, 1), 0), ((r - w + 0.7 * w) / outer, glow(55, 1), a * 0.5)]
        stops += [((r - w + 0.93 * w) / outer, "#fff", a * 0.85), (1, glow(55, 1), 0)]
        defs.append(
            f'<radialGradient id="lf-ring{i}" gradientUnits="userSpaceOnUse" cx="{cx:.1f}" cy="{cy:.1f}" r="{outer:.1f}">'
            + "".join(f'<stop offset="{o:.4f}" stop-color="{c}" stop-opacity="{op:.3f}"/>' for o, c, op in stops)
            + "</radialGradient>"
        )
        rings.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{outer:.1f}" fill="url(#lf-ring{i})"/>')
    c0, r0, c1, r1 = TERRITORIES[1]["box"]
    under = f'<rect x="{c0 * CELL:.1f}" y="{r0 * CELL:.1f}" width="{(c1 - c0 + 1) * CELL:.1f}" height="{(r1 - r0 + 1) * CELL:.1f}" fill="url(#lf-heat)"/>'
    # Sparks flung out from the core.
    rnd = random.Random(168)
    sparks = []
    for _ in range(34):
        a, d = rnd.uniform(0, 2 * math.pi), rnd.uniform(30, R * 0.95)
        length, wd = rnd.uniform(6, 26) * (1 - d / R / 1.4), rnd.uniform(1.4, 3.2)
        x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
        sparks.append(
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + math.cos(a) * length:.1f}" y2="{y + math.sin(a) * length:.1f}" '
            f'stroke="{glow(80, 1)}" stroke-width="{wd:.1f}" stroke-linecap="round" opacity="{rnd.uniform(0.35, 0.9):.2f}"/>'
        )
    over = (
        f'<rect width="{SIZE}" height="{SIZE}" fill="url(#lf-shade)"/>'
        f'<g style="mix-blend-mode:screen">{"".join(rings)}{"".join(sparks)}'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="210" fill="url(#lf-core)"/></g>'
    )
    return "".join(defs), under, over


def map_layer(mono: Face) -> str:
    """The territories, their borders, the letters and the circled words."""
    cells, words = grid()
    out = [f'<rect width="{SIZE}" height="{SIZE}" fill="{PAPER}"/>']
    for t in TERRITORIES:
        c0, r0, c1, r1 = t["box"]
        out.append(
            f'<rect x="{c0 * CELL:.1f}" y="{r0 * CELL:.1f}" width="{(c1 - c0 + 1) * CELL:.1f}" '
            f'height="{(r1 - r0 + 1) * CELL:.1f}" fill="{hsl(t["hue"], 45, 50, 0.15)}"/>'
        )
    nova_defs, nova_under, nova_over = nova_layers()
    out.append(nova_under)
    # Borders between territories, dashed, as the map draws them.
    edges = set()
    for t in TERRITORIES:
        c0, r0, c1, r1 = t["box"]
        for x0, y0, x1, y1 in [
            (c0, r0, c1 + 1, r0),
            (c0, r1 + 1, c1 + 1, r1 + 1),
            (c0, r0, c0, r1 + 1),
            (c1 + 1, r0, c1 + 1, r1 + 1),
        ]:
            if 0 < x0 == x1 < N or 0 < y0 == y1 < N:
                edges.add((x0, y0, x1, y1))
    out.append(
        f'<g stroke="{MUTED}" stroke-opacity=".38" stroke-width="2.4" stroke-dasharray="7 9" fill="none">'
        + "".join(
            f'<line x1="{x0 * CELL:.1f}" y1="{y0 * CELL:.1f}" x2="{x1 * CELL:.1f}" y2="{y1 * CELL:.1f}"/>'
            for x0, y0, x1, y1 in sorted(edges)
        )
        + "</g>"
    )
    out.extend(pill(t) for t in TERRITORIES if t["word"])
    size = CELL * GLYPH
    letters = []
    for r in range(N):
        for c in range(N):
            x, y = centre(c, r)
            ch = cells[r][c]
            key = mono.define(mono.glyph_name(ch), centred=True)
            if (r, c) in words:
                k, fill, op = 1, INK, 1
            else:
                dx, dy, k, lit = nova_push(x, y)
                x, y = x + dx, y + dy
                fill, op = (hsl(168, 90, 88) if lit > 0.12 else INK), min(1, 0.56 + lit * 1.6)
            s = size * k / mono.upm
            letters.append(
                f'<use href="#{key}" transform="translate({x:.1f} {y:.1f}) scale({s:.5f})" fill="{fill}"'
                + (f' fill-opacity="{op:.2f}"' if op < 1 else "")
                + "/>"
            )
    out.append("".join(letters))
    out.append(nova_over)
    return nova_defs, "".join(out)


# Each track's colour: its territory's on the cover, Night Sky's for the
# supernova, and for the two from past the universe's edge, which no territory
# holds, an ochre for the wilds and a cold blue for the void's cave.
HUES = {"drift": 298, "orbit": 115, "supernova": 168, "chimes": 223, "lantern": 55, "hinterland": 22, "dripstone": 195}


def title_panel(faces: dict[str, Face], x: float, y: float, title_size: float = 128) -> tuple[str, float, float]:
    """The title in a panel like the one atop the game's map: the SVG, and the panel's width and height."""
    display, medium = faces["display"], faces["mono-medium"]
    sub_size, pad = title_size * 0.195, title_size * 0.266
    w = display.width("LETTERFIELD", title_size, 0.01) + pad * 2
    h = pad * 2 + title_size * 0.8 + title_size * 0.19 + sub_size * 0.8
    return (
        (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{title_size * 0.11:.1f}" fill="{PANEL}" '
            f'stroke="{RULE}" stroke-width="{title_size * 0.023:.2f}"/>'
            + display.run("LETTERFIELD", x + pad, y + pad + title_size * 0.4, title_size, INK, 0.01)
            + medium.run(
                "ORIGINAL SOUNDTRACK", x + pad + title_size * 0.016, y + h - pad - sub_size * 0.4, sub_size, MUTED, 0.16
            )
        ),
        w,
        h,
    )


def cover_body(faces: dict[str, Face]) -> tuple[str, str]:
    defs, body = map_layer(faces["mono"])
    panel, _, _ = title_panel(faces, 40, 40)
    return defs, body + panel


def cover(faces: dict[str, Face]) -> str:
    defs, body = cover_body(faces)
    return svg(SIZE, SIZE, faces, defs, body, "Letterfield (Original Soundtrack): cover")


def lengths() -> dict[str, str]:
    """Each track's length as rendered, from _album/album.json."""
    album = ROOT / "_album" / "album.json"
    if not album.exists():
        sys.exit("render the album first (uv run scripts/render_album.py): the back lists each track's length")
    tracks = json.loads(album.read_text())["tracks"]
    return {t["slug"]: t["seconds"] for t in tracks}


def clock(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 60}:{s % 60:02d}"


def track_list(faces: dict[str, Face], x: float, y: float, width: float, row: float, size: float) -> str:
    """The tracks, each title circled in its colour, with its number and length."""
    display, mono, medium = faces["display"], faces["mono"], faces["mono-medium"]
    secs = lengths()
    out = []
    for i, track in enumerate(TRACKS):
        cy = y + row * (i + 0.5)
        name, _, rest = track["title"].partition(" (")
        hue = HUES[track["slug"]]
        num = mono.run(f"{i + 1:02d}", x, cy, size * 0.42, MUTED, 0.06)
        length = clock(secs[track["slug"]])
        tx = x + size * 1.35
        tw = display.width(name.upper(), size, 0.02)
        ph, px = size * 1.16, size * 0.34
        # The word after the title, "Interlude", where there's room for it before the length.
        lx = tx + tw + px + size * 0.4
        label = rest.rstrip(")").upper()
        fits = (
            bool(label)
            and lx + medium.width(label, size * 0.34, 0.16) < x + width - mono.width(length, size * 0.48, 0.02) - size
        )
        out.append(
            num
            + f'<rect x="{tx - px:.1f}" y="{cy - ph / 2:.1f}" width="{tw + px * 2:.1f}" height="{ph:.1f}" rx="{ph / 2:.1f}" '
            f'fill="{hsl(hue, 75, 55, 0.22)}" stroke="{hsl(hue, 68, 68)}" stroke-width="{size * 0.06:.2f}"/>'
            + display.run(name.upper(), tx, cy, size, INK, 0.02)
            + (medium.run(rest.rstrip(")").upper(), lx, cy, size * 0.34, MUTED, 0.16) if rest and fits else "")
            + mono.run(length, x + width, cy, size * 0.48, INK, 0.02, anchor="end")
        )
    return "".join(out)


def faint_grid(mono: Face, opacity: float) -> str:
    cells, _ = grid()
    size = CELL * GLYPH / mono.upm
    return (
        f'<g fill="{INK}" fill-opacity="{opacity}">'
        + "".join(
            f'<use href="#{mono.define(mono.glyph_name(cells[r][c]), centred=True)}" '
            f'transform="translate({centre(c, r)[0]:.1f} {centre(c, r)[1]:.1f}) scale({size:.5f})"/>'
            for r in range(N)
            for c in range(N)
        )
        + "</g>"
    )


def back(faces: dict[str, Face]) -> str:
    """The back: the map faint behind a panel of the tracks, and how they were made."""
    mono = faces["mono"]
    secs = lengths()
    body = [f'<rect width="{SIZE}" height="{SIZE}" fill="{PAPER}"/>', faint_grid(mono, 0.16)]
    x0, y0, w, h = 80, 80, SIZE - 160, SIZE - 160
    body.append(
        f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="16" fill="{PANEL}" stroke="{RULE}" stroke-width="3"/>'
    )
    panel, _, ph = title_panel(faces, x0 + 50, y0 + 50, 84)
    body.append(panel)
    notes = [
        "Made as it plays by the game's own code, with the Web Audio API:",
        "oscillators, filters, delays and noise. No recordings, no samples.",
        f"Recorded from fixed seeds at 44.1 kHz.  {len(TRACKS)} tracks, {clock(sum(secs.values()))}.",
    ]
    ny = y0 + h - 60 - 34 * len(notes) - 20 - 34
    # The tracks fill the space between the title and the notes, each row at most 118 high.
    top = y0 + 50 + ph + 50
    row = min(118, (ny - 40 - top) / len(TRACKS))
    body.append(track_list(faces, x0 + 70, top, w - 140, row, row * 62 / 118))
    for i, line in enumerate(notes):
        body.append(mono.run(line, x0 + 70, ny + i * 34, 19, MUTED))
    medium = faces["mono-medium"]
    body.append(medium.run(f"{ARTIST.upper()}  ·  {YEAR}  ·  {LICENSE}", x0 + 70, y0 + h - 60 - 34, 19, INK, 0.08))
    body.append(medium.run("GAMES.MICHAELWARKENTIN.COM/LETTERFIELD", x0 + 70, y0 + h - 60, 19, ACCENT, 0.08))
    return svg(SIZE, SIZE, faces, "", "".join(body), "Letterfield (Original Soundtrack): back")


def preview(faces: dict[str, Face]) -> str:
    """A link-preview card, 1200 by 630: the cover, and the tracks beside it."""
    defs, cover_svg = cover_body(faces)
    width, height = 1200, 630
    body = [
        f'<rect width="{width}" height="{height}" fill="{PANEL}"/>',
        f'<clipPath id="lf-cover"><rect width="{SIZE}" height="{SIZE}"/></clipPath>',
        f'<g transform="scale({height / SIZE:.6f})" clip-path="url(#lf-cover)">{cover_svg}</g>',
        f'<line x1="{height}" y1="0" x2="{height}" y2="{height}" stroke="{RULE}" stroke-width="2"/>',
    ]
    x = height + 52
    body.append(faces["mono-medium"].run("THE SOUNDTRACK", x, 92, 19, MUTED, 0.16))
    row = min(84, 420 / len(TRACKS))
    body.append(track_list(faces, x, 132, width - x - 52, row, row * 44 / 84))
    secs = lengths()
    body.append(
        faces["mono"].run(f"{len(TRACKS)} tracks, {clock(sum(secs.values()))}, to play or download", x, 584, 17, MUTED)
    )
    return svg(width, height, faces, defs, "".join(body), "Letterfield (Original Soundtrack)")


def svg(width: float, height: float, faces: dict[str, Face], defs: str, body: str, title: str) -> str:
    glyphs = "".join(f.defs() for f in faces.values())
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" role="img" aria-label="{title}">'
        f"<title>{title}</title><defs>{glyphs}{defs}</defs>{body}</svg>\n"
    )


PAGE = ROOT / "letterfield-soundtrack.html"
COVER_MARKERS = ("<!-- BEGIN COVER -->\n", "<!-- END COVER -->")


def put_cover_in_page() -> None:
    """The page shows the cover as it is, inline, so it's there offline too.

    tests/test_letterfield_soundtrack.py checks the two are the same."""
    page = PAGE.read_text("utf-8")
    begin, end = COVER_MARKERS
    head, rest = page.split(begin)
    _, tail = rest.split(end)
    PAGE.write_text(head + begin + (ART / "cover.svg").read_text("utf-8") + end + tail, "utf-8")


def main() -> None:
    paths = fetch_fonts()
    ART.mkdir(parents=True, exist_ok=True)
    for name, draw in (("cover", cover), ("back", back), ("preview", preview)):
        # Fresh faces for each, so each holds only the outlines it uses.
        faces = {face: Face(path, f"lf-{face}") for face, path in paths.items()}
        (ART / f"{name}.svg").write_text(draw(faces), "utf-8")
    put_cover_in_page()
    print(json.dumps({p.name: p.stat().st_size for p in sorted(ART.glob("*.svg"))}))


if __name__ == "__main__":
    main()
