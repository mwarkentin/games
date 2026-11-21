"""The interactive explainers: one self-contained HTML file each.

Each source in explainers/ is a page fragment (its <title>, <style>, markup
and <script>, no <html> or <head>), as claude.ai's Artifact tool takes it,
with `/* FONTS */` where the game's fonts go. Real map data goes in the same
way, from the Worker's copy of the generator (data.mjs), so a page never
carries letters or numbers typed in by hand:

  [/* THEMES */]                  every theme as [name, hue]
  [/* AREA x y w h */]            the letters of a patch of cells, a row each
  [/* TERRITORY rx ry */]         [rx, ry, theme's index, hue, hidden words, name]

The build subsets the fonts to the characters a page can show, inlines them
as WOFF2, and writes two copies:

  _architecture/explainers/<name>.html   a whole page, to host and embed with an iframe
  _architecture/artifacts/<name>.html    the fragment, to publish as an Artifact
"""

from __future__ import annotations

import base64
import io
import json
import re

from kit import FAMILIES, HERE, OUT, font_path, world

SOURCES = HERE / "explainers"
# Printable ASCII and the few symbols the pages use; a face without one simply leaves it out.
CHARS = "".join(chr(c) for c in range(32, 127)) + "→←↑↓↘↙↖↗×≤≥·…’‘“”–—•½≈°"


def font_faces() -> str:
    """@font-face rules for the game's faces, each subset and inlined as WOFF2."""
    from fontTools import subset

    rules = []
    for key, (family, weight) in FAMILIES.items():
        options = subset.Options()
        options.flavor = "woff2"
        options.layout_features = ["kern", "liga", "tnum"]
        font = subset.load_font(str(font_path(key)), options)
        sub = subset.Subsetter(options)
        sub.populate(text=CHARS)
        sub.subset(font)
        buf = io.BytesIO()
        subset.save_font(font, buf, options)
        data = base64.b64encode(buf.getvalue()).decode()
        rules.append(
            f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:normal;font-display:swap;'
            f'src:url(data:font/woff2;base64,{data}) format("woff2")}}'
        )
    return "\n".join(rules)


def whole_page(fragment: str) -> str:
    """The fragment as a standalone page: its title and styles in a head, the rest in a body."""
    head = "".join(re.findall(r"<title>.*?</title>|<meta name=\"claude:[^>]*>|<style>.*?</style>", fragment, re.S))
    body = re.sub(r"<title>.*?</title>|<meta name=\"claude:[^>]*>|<style>.*?</style>", "", fragment, flags=re.S)
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f"{head}\n</head>\n<body>\n{body.strip()}\n</body>\n</html>\n"
    )


def map_data(fragment: str) -> str:
    """The page with its placeholders for map data filled in from the generator."""

    def compact(value) -> str:
        return json.dumps(value, separators=(",", ":"))

    def area(m: re.Match) -> str:
        return compact(world("area", *m.groups())["letters"])

    def territory(m: re.Match) -> str:
        rx, ry = m.groups()
        return compact(world("territories", rx, ry, rx, ry)[0])

    fragment = fragment.replace("[/* THEMES */]", compact([[name, hue] for name, hue, _ in world("themes")]))
    fragment = re.sub(r"\[/\* AREA (-?\d+) (-?\d+) (\d+) (\d+) \*/\]", area, fragment)
    fragment = re.sub(r"\[/\* TERRITORY (-?\d+) (-?\d+) \*/\]", territory, fragment)
    return fragment


def build_explainers() -> None:
    faces = font_faces()
    for folder in ("explainers", "artifacts"):
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    for src in sorted(SOURCES.glob("*.html")):
        fragment = map_data(src.read_text()).replace("/* FONTS */", faces)
        (OUT / "artifacts" / src.name).write_text(fragment)
        (OUT / "explainers" / src.name).write_text(whole_page(fragment))
        size = len(whole_page(fragment).encode()) / 1024
        print(f"  explainer {src.stem}: {size:.0f} KB")
