"""The sites bench.py compares, made from two builds in DIR: DIR/base (main's
_site) and DIR/proto (this branch's). Each is written to DIR/<name>:

    main-v2     main after a deploy that changed one line of the game's code
    proto-v2    the prototype after the same deploy (the page changes, its modules don't)
    proto-v2t   the prototype after a deploy that changed one theme (world.js changes)
    nopre       the prototype without its modulepreload links (each import found in turn)
    full        all of the script in modules: the page is markup and style,
                js/letterfield/game.js the rest (measured only, not proposed)
    full-v2     full after the one-line deploy (game.js changes)

    python3 docs/split-js-bench/variants.py DIR
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

MARK = "/* ---------- Boot ---------- */"
CHANGE = MARK + "\n// a deploy that changes one line of the game's code"
MODULES = ["/js/letterfield/world.js", "/js/letterfield/achievements.js", "/js/letterfield/game.js"]


def fresh(out: Path, src: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)
    return out


def edit(file: Path, old: str, new: str) -> None:
    text = file.read_text("utf-8")
    assert text.count(old) == 1, (file, old)
    file.write_text(text.replace(old, new), "utf-8")


def remap(site: Path) -> None:
    """Point the page's import map and preload links at its modules' current hashes."""
    page = (site / "letterfield.html").read_text("utf-8")
    for path in MODULES:
        if (site / path.lstrip("/")).exists():
            digest = hashlib.sha256((site / path.lstrip("/")).read_bytes()).hexdigest()[:10]
            page = re.sub(re.escape(path) + r"\?v=[0-9a-f]+", f"{path}?v={digest}", page)
    (site / "letterfield.html").write_text(page, "utf-8")


def make(root: Path) -> None:
    base, proto = root / "base", root / "proto"
    edit(fresh(root / "main-v2", base) / "letterfield.html", MARK, CHANGE)
    edit(fresh(root / "proto-v2", proto) / "letterfield.html", MARK, CHANGE)
    themes = fresh(root / "proto-v2t", proto)
    edit(themes / "js/letterfield/world.js", "Festivals|90|BIRTHDAY ", "Festivals|90|BIRTHDAY JAMBOREE ")
    remap(themes)

    nopre = fresh(root / "nopre", proto)
    page = (nopre / "letterfield.html").read_text("utf-8")
    (nopre / "letterfield.html").write_text(re.sub(r'<link rel="modulepreload" href="[^"]+">\n', "", page), "utf-8")

    full = fresh(root / "full", proto)
    page = (full / "letterfield.html").read_text("utf-8")
    script = re.search(r'<script type="module">\n(.*?)\n</script>', page, re.DOTALL)
    code = script[1].replace("'./js/letterfield/world.js'", "'./world.js'")
    code = code.replace("'./js/letterfield/achievements.js'", "'./achievements.js'")
    (full / "js/letterfield/game.js").write_text(code + "\n", "utf-8")
    page = (
        page[: script.start()]
        + "<script type=\"module\">import './js/letterfield/game.js';</script>"
        + page[script.end() :]
    )
    imports = re.search(r'<script type="importmap">\n(.*?)\n</script>', page, re.DOTALL)
    mapped = json.loads(imports[1])
    mapped["imports"]["/js/letterfield/game.js"] = "/js/letterfield/game.js?v=0"
    page = page[: imports.start(1)] + json.dumps(mapped, indent=1) + page[imports.end(1) :]
    first = '<link rel="modulepreload" href="/js/letterfield/world.js'
    page = page.replace(first, '<link rel="modulepreload" href="/js/letterfield/game.js?v=0">\n' + first, 1)
    (full / "letterfield.html").write_text(page, "utf-8")
    remap(full)
    edit(fresh(root / "full-v2", full) / "js/letterfield/game.js", MARK, CHANGE)
    remap(root / "full-v2")

    for name in ["base", "proto", "full"]:
        site = root / name
        files = ["letterfield.html", *sorted(str(p.relative_to(site)) for p in (site / "js").rglob("*.js"))]
        sizes = {f: (len((site / f).read_bytes()), len(gzip.compress((site / f).read_bytes(), 6))) for f in files}
        parts = " · ".join(f"{f.split('/')[-1]} {raw / 1000:.0f}/{gz / 1000:.0f} kB" for f, (raw, gz) in sizes.items())
        print(f"{name}: {parts} (raw/gzipped) = {sum(gz for _, gz in sizes.values()) / 1000:.0f} kB gzipped")


if __name__ == "__main__":
    make(Path(sys.argv[1]))
