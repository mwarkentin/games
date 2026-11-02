"""The tip jar link in the header of the home page and colophon.

Games own the whole screen, so the build doesn't add the link to them.
"""

from __future__ import annotations

import build_colophon
import build_index
import common

from common import render_page, tip_link

FAKE_TIP_URL = "https://buy.stripe.com/test_tipjar"


def test_tip_link_tags_the_source(monkeypatch):
    monkeypatch.setattr(common, "TIP_URL", FAKE_TIP_URL)
    assert tip_link("games-home") == f"{FAKE_TIP_URL}?client_reference_id=games-home"
    # Stripe drops a reference with anything but letters, digits, - and _.
    assert tip_link("games-a.b c") == f"{FAKE_TIP_URL}?client_reference_id=games-a_b_c"
    monkeypatch.setattr(common, "TIP_URL", f"{FAKE_TIP_URL}?prefilled_promo_code=x")
    assert tip_link("games").endswith("?prefilled_promo_code=x&client_reference_id=games")


def test_header_has_no_tip_link_without_url(monkeypatch):
    monkeypatch.setattr(common, "TIP_URL", "")
    assert "Tip jar" not in render_page("Title", "<p>body</p>")


def test_home_and_colophon_link_the_tip_jar_once_url_is_set(monkeypatch):
    monkeypatch.setattr(common, "TIP_URL", FAKE_TIP_URL)
    home = build_index.build_index("# Games\n", [])
    colophon = build_colophon.build_colophon({}, [])
    assert f'<a href="{FAKE_TIP_URL}?client_reference_id=games-home">Tip jar</a></nav>' in home
    assert f'<a href="{FAKE_TIP_URL}?client_reference_id=games-colophon">Tip jar</a></nav>' in colophon


def test_games_get_no_tip_link(site_dir):
    for filename in common.game_files():
        assert "Tip jar" not in (site_dir / filename).read_text("utf-8"), filename
