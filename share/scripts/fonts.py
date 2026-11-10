# /// script
# dependencies = ["fonttools==4.60.1"]
# ///
"""Downloads the cards' fonts from Google Fonts as TTF, subsets them to the
characters cards draw, and writes their licences and src/metrics.json (each
font's advance widths, in ems, so the Worker can fit text without a canvas).

Run from the repo root after changing CHARS or a font: uv run share/scripts/fonts.py
"""
import json
import re
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent.parent
CSS = ("https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@800"
       "&family=Martian+Mono:wght@400;500&family=Schibsted+Grotesk:wght@500;600")
NAMES = ["BigShouldersDisplay-800", "MartianMono-400", "MartianMono-500", "SchibstedGrotesk-500", "SchibstedGrotesk-600"]
LICENCES = {
    "BigShouldersDisplay": "bigshouldersdisplay",
    "MartianMono": "martianmono",
    "SchibstedGrotesk": "schibstedgrotesk",
}
# Printable ASCII, the eight direction arrows and a little punctuation.
CHARS = "".join(chr(c) for c in range(32, 127)) + "→↘↓↙←↖↑↗·…’–"


def get(url: str, agent: str = "Mozilla/4.0") -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": agent})) as r:
        return r.read()


def main() -> None:
    fonts = HERE / "fonts"
    fonts.mkdir(exist_ok=True)
    # An old user agent gets TTF rather than WOFF2, which resvg can't read.
    urls = re.findall(r"url\((https://[^)]+\.ttf)\)", get(CSS).decode())
    assert len(urls) == len(NAMES), urls
    options = subset.Options()
    options.layout_features = ["kern", "liga"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    metrics = {}
    for name, url in zip(NAMES, urls):
        path = fonts / f"{name}.ttf"
        path.write_bytes(get(url))
        font = subset.load_font(str(path), options)
        sub = subset.Subsetter(options)
        sub.populate(text=CHARS)
        sub.subset(font)
        subset.save_font(font, str(path), options)
        font = TTFont(path)
        upm, cmap, hmtx = font["head"].unitsPerEm, font.getBestCmap(), font["hmtx"]
        metrics[name] = {c: round(hmtx[cmap[ord(c)]][0] / upm, 4) for c in CHARS if ord(c) in cmap}
        print(f"{path.name}: {path.stat().st_size} bytes, {len(metrics[name])} characters")
    for family, slug in LICENCES.items():
        (fonts / f"{family}-OFL.txt").write_bytes(get(f"https://raw.githubusercontent.com/google/fonts/main/ofl/{slug}/OFL.txt"))
    (HERE / "src" / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
