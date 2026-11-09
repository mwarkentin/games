# /// script
# dependencies = ["fonttools==4.60.1"]
# ///
"""Write src/metrics.json: each font's advance widths, in ems, for the
characters the card draws, so the Worker can fit text without a canvas.
Run after scripts/fonts.sh: uv run scripts/metrics.py"""
import json
from pathlib import Path
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent.parent
CHARS = "".join(chr(c) for c in range(32, 127)) + "→↘↓↙←↖↑↗·…’"
out = {}
for path in sorted((HERE / "fonts").glob("*.ttf")):
    font = TTFont(path)
    upm, cmap, hmtx = font["head"].unitsPerEm, font.getBestCmap(), font["hmtx"]
    out[path.stem] = {c: round(hmtx[cmap[ord(c)]][0] / upm, 4) for c in CHARS if ord(c) in cmap}
(HERE / "src" / "metrics.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
print({k: len(v) for k, v in out.items()})
