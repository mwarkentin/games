#!/usr/bin/env python3
"""Render every icons/<app>.svg to the PNGs the site links to.

The PNGs are committed, since the deploy has no browser to draw them. Run this
after adding or changing an icon:

    uv run scripts/render_icons.py

Each icon is a full-bleed 512x512 square with nothing important outside the
middle circle (radius 205), so iOS can round its corners and Android can crop
it to a circle. Draw with shapes rather than text, so it renders the same
everywhere and tests/test_pwa.py can check the PNGs still match.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from common import ICON_SIZES, ROOT

ICONS = ROOT / "icons"


def render(page: Page, svg: str, size: int) -> bytes:
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(
        f"<style>html,body{{margin:0}}svg{{display:block;width:{size}px;height:{size}px}}</style>{svg}"
    )
    return page.screenshot(type="png")


def render_icons(page: Page, icons: Path = ICONS) -> list[Path]:
    written = []
    for source in sorted(icons.glob("*.svg")):
        svg = source.read_text("utf-8")
        for size in ICON_SIZES:
            target = icons / f"{source.stem}-{size}.png"
            target.write_bytes(render(page, svg, size))
            written.append(target)
    return written


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        written = render_icons(browser.new_page(device_scale_factor=1))
        browser.close()
    print(f"Rendered {len(written)} icons in {ICONS.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
