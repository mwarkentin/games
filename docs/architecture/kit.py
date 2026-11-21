"""A small drawing kit for Letterfield's architecture figures (see README.md).

Every figure is drawn twice, in the game's light and dark colours, as SVG with
every letter an outline from the game's own fonts (Big Shoulders Display,
Martian Mono and Schibsted Grotesk, all SIL Open Font License), so a figure
renders the same anywhere, with no fonts and no network. The fonts come from
Google Fonts once, into _architecture/fonts/, as scripts/draw_album_art.py
fetches the album's.

Coordinates are CSS pixels: figures are 800 wide, for a blog column, and
render.py turns each into a PNG at 2x.
"""

from __future__ import annotations

import colorsys
import json
import math
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from functools import cache
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "_architecture"
FONT_DIR = OUT / "fonts"
WIDTH = 800

# The game's faces (letterfield.html's --f-display, --f-mono and --f-ui).
FAMILIES = {
    "display": ("Big Shoulders Display", 800),
    "display7": ("Big Shoulders Display", 700),
    "mono": ("Martian Mono", 400),
    "mono5": ("Martian Mono", 500),
    "ui": ("Schibsted Grotesk", 400),
    "ui5": ("Schibsted Grotesk", 500),
    "ui6": ("Schibsted Grotesk", 600),
}


def font_path(key: str) -> Path:
    """The TrueType file for one face, fetched from Google Fonts the first time."""
    family, weight = FAMILIES[key]
    path = FONT_DIR / f"{family.replace(' ', '')}-{weight}.ttf"
    if not path.exists():
        FONT_DIR.mkdir(parents=True, exist_ok=True)
        # Without a browser's User-Agent, Google Fonts answers with TrueType.
        query = f"{family.replace(' ', '+')}:wght@{weight}"
        css = urllib.request.urlopen(f"https://fonts.googleapis.com/css2?family={query}").read().decode()
        url = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)", css)[1]
        path.write_bytes(urllib.request.urlopen(url).read())
    return path


def hsl(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l / 100, s / 100)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


@dataclass(frozen=True)
class Theme:
    """letterfield.html's :root colours for one scheme, and the figures' own."""

    name: str
    paper: str
    panel: str
    field: str
    ink: str
    muted: str
    rule: str
    accent: str
    on_accent: str
    danger: str
    mark_s: float  # a territory's word marks: hsl(hue, mark_s, mark_l), as the game's --mark-s/--mark-l
    mark_l: float
    tint_a: float  # a territory's tint, hsl(hue, 45%, 50%), at this opacity (the game's tintAlpha up close)
    fill_a: float  # a circled word's fill, hsla(hue, 75%, 55%, fill_a)
    # Chart and diagram slots, validated with the dataviz skill's validator
    # against this paper: teal, copper, indigo, rose, in that order.
    series: tuple[str, str, str, str]

    def mark(self, hue: float) -> str:
        return hsl(hue, self.mark_s, self.mark_l)

    def tint(self, hue: float) -> str:
        return hsl(hue, 45, 50)

    def wash(self, hue: float) -> str:
        return hsl(hue, 75, 55)

    @property
    def dark(self) -> bool:
        return self.name == "dark"

    # What each kind of part of the system wears in a diagram.
    @property
    def kinds(self) -> dict[str, str]:
        teal, copper, indigo, rose = self.series
        return {"object": teal, "store": copper, "worker": indigo, "browser": rose, "other": self.muted}


LIGHT = Theme(
    "light",
    paper="#EBEEE7",
    panel="#F7F8F4",
    field="#FFFFFF",
    ink="#1B2428",
    muted="#59656A",
    rule="#C6CFC6",
    accent="#2A43C2",
    on_accent="#FFFFFF",
    danger="#B23A2C",
    mark_s=58,
    mark_l=38,
    tint_a=0.09,
    fill_a=0.26,
    series=("#259889", "#995629", "#2c48a5", "#992961"),
)
DARK = Theme(
    "dark",
    paper="#0F171A",
    panel="#162024",
    field="#0F171A",
    ink="#E2E7DE",
    muted="#93A19D",
    rule="#2B3A3E",
    accent="#97A9FF",
    on_accent="#0C1330",
    danger="#FF8D7C",
    mark_s=68,
    mark_l=68,
    tint_a=0.075,
    fill_a=0.22,
    series=("#21ab99", "#d97736", "#758fe6", "#e160a1"),
)
THEMES = (LIGHT, DARK)


class Face:
    """One font: shapes text with HarfBuzz and keeps each glyph's outline, in font units, baseline at 0."""

    def __init__(self, key: str):
        import uharfbuzz as hb
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.pens.transformPen import TransformPen
        from fontTools.ttLib import TTFont

        self.key = key
        self.path = font_path(key)
        self.font = TTFont(self.path)
        self.upm = self.font["head"].unitsPerEm
        self.cap = self.font["OS/2"].sCapHeight or 0.7 * self.upm
        self.xh = self.font["OS/2"].sxHeight or 0.5 * self.upm
        self.glyphs = self.font.getGlyphSet()
        self.hb = hb.Font(hb.Face(self.path.read_bytes()))
        self._pens = (SVGPathPen, TransformPen)
        self._outlines: dict[str, str] = {}

    def shape(self, text: str, tracking: float = 0) -> tuple[list[tuple[str, float]], float]:
        """Each inked glyph's name and its x in font units, and the run's advance, with kerning."""
        import uharfbuzz as hb

        if not text:
            return [], 0
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True})
        pen, out, track = 0.0, [], tracking * self.upm
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            if info.codepoint == 0:
                raise ValueError(f"{self.key} has no glyph for {text[info.cluster]!r} in {text!r}")
            name = self.font.getGlyphName(info.codepoint)
            if text[info.cluster] != " ":
                out.append((name, pen + pos.x_offset))
            pen += pos.x_advance + track
        return out, pen - track

    def outline(self, name: str) -> str:
        if name not in self._outlines:
            svg_pen, transform_pen = self._pens
            pen = svg_pen(self.glyphs, ntos=lambda v: f"{v:.0f}")
            self.glyphs[name].draw(transform_pen(pen, (1, 0, 0, -1, 0, 0)))
            self._outlines[name] = pen.getCommands()
        return self._outlines[name]


@cache
def face(key: str) -> Face:
    return Face(key)


def num(v: float) -> str:
    """A coordinate, short."""
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def fmt(n: float) -> str:
    """A count as the docs write it: 1,119,752."""
    return f"{n:,.0f}"


class Fig:
    """One figure in one theme: shapes and outlined text, then svg()."""

    def __init__(self, theme: Theme, height: int, width: int = WIDTH):
        self.t = theme
        self.w, self.h = width, height
        self.body: list[str] = []
        self.glyphs: dict[str, str] = {}
        self.clips = 0

    # -- text -----------------------------------------------------------------
    def width(self, text: str, font: str = "ui", size: float = 13, tracking: float = 0) -> float:
        return face(font).shape(text, tracking)[1] * size / face(font).upm

    def text(
        self,
        x: float,
        y: float,
        text: str,
        font: str = "ui",
        size: float = 13,
        fill: str | None = None,
        anchor: str = "start",
        tracking: float = 0,
        opacity: float | None = None,
        upper: bool = False,
    ) -> float:
        """A line of text as outlines, with y its baseline. Returns its width."""
        if upper:
            text = text.upper()
        f = face(font)
        placed, advance = f.shape(text, tracking)
        scale = size / f.upm
        width = advance * scale
        x0 = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
        uses = []
        for name, gx in placed:
            gid = f"{font}-{name}"
            if gid not in self.glyphs:
                self.glyphs[gid] = f.outline(name)
            uses.append(f'<use href="#{gid}" x="{gx:.0f}"/>')
        op = f' opacity="{num(opacity)}"' if opacity is not None else ""
        label = escape(text, quote=True)
        self.body.append(
            f'<g fill="{fill or self.t.ink}"{op} transform="translate({num(x0)} {num(y)}) scale({scale:.5f})"'
            f' aria-label="{label}">{"".join(uses)}</g>'
        )
        return width

    def wrap(self, text: str, width: float, font: str = "ui", size: float = 13) -> list[str]:
        lines: list[str] = []
        for para in text.split("\n"):
            line = ""
            for word in para.split(" "):
                trial = f"{line} {word}".strip()
                if line and self.width(trial, font, size) > width:
                    lines.append(line)
                    line = word
                else:
                    line = trial
            lines.append(line)
        return lines

    def para(
        self,
        x: float,
        y: float,
        text: str,
        width: float,
        font: str = "ui",
        size: float = 13,
        lh: float = 1.38,
        fill: str | None = None,
        anchor: str = "start",
    ) -> float:
        """Wrapped text from baseline y; returns the baseline after the last line."""
        for line in self.wrap(text, width, font, size):
            self.text(x, y, line, font, size, fill, anchor)
            y += size * lh
        return y

    def cap_height(self, font: str, size: float) -> float:
        return face(font).cap * size / face(font).upm

    # -- shapes ---------------------------------------------------------------
    def add(self, markup: str) -> None:
        self.body.append(markup)

    @staticmethod
    def _stroke(stroke, sw, dash, cap="round", join="round") -> str:
        if not stroke:
            return ""
        out = f' stroke="{stroke}" stroke-width="{num(sw)}" stroke-linecap="{cap}" stroke-linejoin="{join}"'
        return out + (f' stroke-dasharray="{dash}"' if dash else "")

    def rect(self, x, y, w, h, r=0, fill="none", stroke=None, sw=1, dash=None, opacity=None, fill_opacity=None):
        attrs = f'x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}"' + (f' rx="{num(r)}"' if r else "")
        attrs += f' fill="{fill}"' + (f' fill-opacity="{num(fill_opacity)}"' if fill_opacity is not None else "")
        attrs += self._stroke(stroke, sw, dash, cap="butt", join="miter") + (
            f' opacity="{num(opacity)}"' if opacity is not None else ""
        )
        self.body.append(f"<rect {attrs}/>")

    def circle(self, x, y, r, fill="none", stroke=None, sw=1, dash=None, opacity=None, fill_opacity=None):
        attrs = f'cx="{num(x)}" cy="{num(y)}" r="{num(r)}" fill="{fill}"'
        attrs += f' fill-opacity="{num(fill_opacity)}"' if fill_opacity is not None else ""
        attrs += self._stroke(stroke, sw, dash) + (f' opacity="{num(opacity)}"' if opacity is not None else "")
        self.body.append(f"<circle {attrs}/>")

    def line(self, x1, y1, x2, y2, stroke=None, sw=1, dash=None, opacity=None, cap="round"):
        attrs = f'x1="{num(x1)}" y1="{num(y1)}" x2="{num(x2)}" y2="{num(y2)}"'
        attrs += self._stroke(stroke or self.t.rule, sw, dash, cap=cap)
        attrs += f' opacity="{num(opacity)}"' if opacity is not None else ""
        self.body.append(f"<line {attrs}/>")

    def path(self, d, fill="none", stroke=None, sw=1.5, dash=None, opacity=None, fill_opacity=None, cap="round"):
        attrs = f'd="{d}" fill="{fill}"' + (f' fill-opacity="{num(fill_opacity)}"' if fill_opacity is not None else "")
        attrs += self._stroke(stroke, sw, dash, cap=cap) + (f' opacity="{num(opacity)}"' if opacity is not None else "")
        self.body.append(f"<path {attrs}/>")

    def arrow(self, pts, stroke=None, sw=1.5, head=6.5, dash=None, start=False, end=True, radius=8, opacity=None):
        """A polyline through pts with rounded corners and open arrowheads."""
        stroke = stroke or self.t.muted
        pts = [tuple(p) for p in pts]
        d = f"M{num(pts[0][0])} {num(pts[0][1])}"
        for i in range(1, len(pts) - 1):
            (ax, ay), (bx, by), (cx, cy) = pts[i - 1], pts[i], pts[i + 1]
            l1, l2 = math.hypot(bx - ax, by - ay), math.hypot(cx - bx, cy - by)
            r = min(radius, l1 / 2, l2 / 2)
            if r < 0.5:
                d += f" L{num(bx)} {num(by)}"
                continue
            p1 = (bx - (bx - ax) / l1 * r, by - (by - ay) / l1 * r)
            p2 = (bx + (cx - bx) / l2 * r, by + (cy - by) / l2 * r)
            d += f" L{num(p1[0])} {num(p1[1])} Q{num(bx)} {num(by)} {num(p2[0])} {num(p2[1])}"
        d += f" L{num(pts[-1][0])} {num(pts[-1][1])}"
        self.path(d, stroke=stroke, sw=sw, dash=dash, opacity=opacity)
        heads = ([(pts[-2], pts[-1])] if end else []) + ([(pts[1], pts[0])] if start else [])
        for (ax, ay), (bx, by) in heads:
            a = math.atan2(by - ay, bx - ax)
            wing = [(bx - head * math.cos(a - s * 0.5), by - head * math.sin(a - s * 0.5)) for s in (1, -1)]
            self.path(
                f"M{num(wing[0][0])} {num(wing[0][1])} L{num(bx)} {num(by)} L{num(wing[1][0])} {num(wing[1][1])}",
                stroke=stroke,
                sw=sw,
                opacity=opacity,
            )

    def capsule(self, x0, y0, x1, y1, r, stroke, fill=None, fill_opacity=0.2, sw=1.6, dash=None, opacity=None):
        """The game's circled word: a capsule from one letter's centre to another's."""
        a = math.atan2(y1 - y0, x1 - x0)
        length = math.hypot(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        attrs = f'x="{num(-length / 2 - r)}" y="{num(-r)}" width="{num(length + 2 * r)}" height="{num(2 * r)}"'
        attrs += f' rx="{num(r)}" fill="{fill or stroke}" fill-opacity="{num(fill_opacity)}"'
        attrs += self._stroke(stroke, sw, dash) + (f' opacity="{num(opacity)}"' if opacity is not None else "")
        self.body.append(f'<rect {attrs} transform="translate({num(cx)} {num(cy)}) rotate({num(math.degrees(a))})"/>')

    # -- the figures' furniture ----------------------------------------------
    def eyebrow(self, x, y, text, fill=None, size=8.5, anchor="start", knock=False):
        if knock:
            self.knock(x, y, text.upper(), "mono5", size, anchor, tracking=0.12)
        return self.text(x, y, text, "mono5", size, fill or self.t.muted, anchor, tracking=0.12, upper=True)

    def knock(self, x, y, text, font, size, anchor="start", tracking=0.0, pad=4):
        """Paper behind a label, so lines drawn earlier seem to pass under it."""
        w = self.width(text, font, size, tracking)
        x0 = x - w / 2 if anchor == "middle" else x - w if anchor == "end" else x
        cap = self.cap_height(font, size)
        self.rect(x0 - pad, y - cap - pad, w + 2 * pad, cap + 2 * pad, fill=self.t.paper)

    def label(self, x, y, text, font="ui5", size=9.5, fill=None, anchor="start", pad=3):
        """Text with paper behind it."""
        self.knock(x, y, text, font, size, anchor, pad=pad)
        return self.text(x, y, text, font, size, fill or self.t.muted, anchor)

    def badge(self, x: float, y: float, size: float = 40) -> None:
        """The game's icon in small: a 3x3 of letters with MAP circled on the diagonal."""
        t, cell = self.t, size / 3
        self.rect(x, y, size, size, r=size * 0.14, fill=t.panel, stroke=t.rule, sw=0.8)
        letters = {(0, 0): "M", (0, 1): "E", (0, 2): "L", (1, 0): "H", (1, 1): "A", (1, 2): "N",
                   (2, 0): "V", (2, 1): "T", (2, 2): "P"}  # fmt: skip
        self.capsule(x + cell / 2, y + cell / 2, x + 2.5 * cell, y + 2.5 * cell, cell * 0.4, t.accent, sw=1.1,
                     fill_opacity=0.16)  # fmt: skip
        for (r, c), ch in letters.items():
            size_ = cell * 0.56
            self.text(x + (c + 0.5) * cell, y + (r + 0.5) * cell + self.cap_height("mono5", size_) / 2, ch, "mono5",
                      size_, t.accent if r == c else t.ink, "middle")  # fmt: skip

    def header(self, eyebrow: str, title: str, subtitle: str | None = None, x: float = 32, y: float = 30) -> float:
        """The game's badge, an eyebrow and the title; returns the y below them."""
        self.badge(x, y, 42)
        self.eyebrow(x + 54, y + 12, eyebrow)
        self.text(x + 54, y + 40, title, "display", 29)
        y += 42
        if subtitle:
            y = self.para(x, y + 24, subtitle, self.w - 2 * x, "ui", 13, fill=self.t.muted) - 13 * 1.38
        return y + 24

    def footer(self, sources: str, x: float = 32) -> None:
        """Where the figure's facts come from, along the bottom; set self.h first."""
        self.line(x, self.h - 30, self.w - x, self.h - 30, self.t.rule, 1)
        self.text(x, self.h - 13, sources, "mono", 8, self.t.muted)

    def svg(self, title: str, desc: str) -> str:
        defs = "".join(f'<path id="{gid}" d="{d}"/>' for gid, d in self.glyphs.items())
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}"'
            f' height="{self.h}" role="img" aria-labelledby="t d">'
            f'<title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>'
            f"<defs>{defs}</defs>"
            f'<rect width="{self.w}" height="{self.h}" fill="{self.t.paper}"/>' + "".join(self.body) + "</svg>"
        )


# -- data from the game's own map, through the Worker's copy of its generator --
@cache
def world(what: str, *args) -> dict | list:
    """data.mjs's answer: the map as the survey's server sees it."""
    out = subprocess.run(
        ["node", str(HERE / "data.mjs"), what, *map(str, args)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def cell_box(fig: Fig, x: float, y: float, w: float, h: float, label: str, kind: str, sub: str | None = None,
             size: float = 12.5, align: str = "middle", stroke: str | None = None) -> None:  # fmt: skip
    """A part of the system: a panel with a key in its kind's colour down its left edge, its name and a line."""
    t = fig.t
    colour = t.kinds[kind]
    fig.rect(x, y, w, h, r=6, fill=t.panel, stroke=stroke or t.rule, sw=1)
    fig.clips += 1
    clip = f"k{fig.clips}"
    fig.add(
        f'<clipPath id="{clip}"><rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" rx="6"/></clipPath>'
        f'<rect x="{num(x)}" y="{num(y)}" width="4" height="{num(h)}" fill="{colour}" clip-path="url(#{clip})"/>'
    )
    tx = x + 4 + (w - 4) / 2 if align == "middle" else x + 14
    if sub:
        fig.text(tx, y + h / 2 - 1.5, label, "ui6", size, anchor=align)
        fig.text(tx, y + h / 2 + 12.5, sub, "ui", 10.5, t.muted, align)
    else:
        fig.text(tx, y + h / 2 + size * 0.36, label, "ui6", size, anchor=align)
