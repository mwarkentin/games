#!/usr/bin/env python3
"""Write _headers and 404.html: how the site's Worker serves what's built.

Once the site moves from GitHub Pages to Workers static assets (the
games-site Worker in site/, see site/README.md), _headers sets each path's
Cache-Control, where Pages gives everything max-age=600:

- Pages, the modules in js/ and sw.js are checked again on every load
  (max-age=0 with the asset's ETag, so an unchanged file is a 304), so a
  deploy shows up at once. sw.js already re-reads its pages from the network
  first; this only stops the browser's own cache holding an old copy.
  Modules are named by a hash in their query string (?v=1a2b3c4d5e), but
  _headers matches paths alone, and browsers without import maps load the
  same path without a hash, so a long cache could pair a new page with an
  old module. sw.js keeps every module by its hashed address anyway.
- Manifests, games.json, sitemap.xml and robots.txt: ten minutes, as now.
- Icons, link previews and music: a week. They change rarely, and a stale
  one for a while does no harm.

Every response also gets Access-Control-Allow-Origin: *, as Pages sends.
Each path is in one rule only: Workers join two rules' values for the same
header with a comma. GitHub Pages ignores _headers (it serves it as a file,
harmlessly) and uses 404.html as its not-found page too.

Usage: build_headers.py [SITE_DIR]
"""

from __future__ import annotations

import sys
from pathlib import Path

from common import ROOT, game_files, generated_pages, insert_in_head, render_page

FRESH = "public, max-age=0, must-revalidate"
SHORT = "public, max-age=600"
LONG = "public, max-age=604800"
# Workers allow 100 rules in a _headers file.
MAX_RULES = 100


def page_paths(root: Path = ROOT) -> list[str]:
    """Every page's address, as sw.js lists them: /, /colophon, /war."""
    return [*generated_pages(root).values(), *(f"/{name.removesuffix('.html')}" for name in game_files(root))]


def header_rules(root: Path = ROOT) -> list[tuple[str, dict[str, str]]]:
    """[(path pattern, {header: value})], with no path matched by two rules for one header."""
    rules: list[tuple[str, dict[str, str]]] = [("/*", {"Access-Control-Allow-Origin": "*"})]
    rules += [(path, {"Cache-Control": FRESH}) for path in page_paths(root)]
    rules += [("/sw.js", {"Cache-Control": "no-cache"}), ("/js/*", {"Cache-Control": FRESH})]
    rules += [
        (path, {"Cache-Control": SHORT}) for path in ("/manifests/*", "/games.json", "/sitemap.xml", "/robots.txt")
    ]
    rules += [(path, {"Cache-Control": LONG}) for path in ("/icons/*", "/previews/*", "/music/*")]
    assert len(rules) <= MAX_RULES, f"_headers has {len(rules)} rules; Workers allow {MAX_RULES}"
    return rules


def build_headers(root: Path = ROOT) -> str:
    lines = ["# Built by scripts/build_headers.py; see its docstring."]
    for path, headers in header_rules(root):
        lines.append(path)
        lines += [f"  {name}: {value}" for name, value in headers.items()]
    return "\n".join(lines) + "\n"


def build_not_found() -> str:
    body = """<h1>Nothing here</h1>
<p>There's no page at this address. <a href="/">See all the games</a>.</p>"""
    page = render_page("Not found · games.michaelwarkentin.com", body, path="/404")
    return insert_in_head(page, '<meta name="robots" content="noindex">\n')


def main() -> None:
    site_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    (site_dir / "_headers").write_text(build_headers(), "utf-8")
    (site_dir / "404.html").write_text(build_not_found(), "utf-8")
    print(f"Built _headers with {len(header_rules())} rules, and 404.html")


if __name__ == "__main__":
    main()
