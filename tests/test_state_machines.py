"""The state machine helper every page shares (see "State machines" in AGENTS.md).

Pages keep their modes in explicit state machines made by one small
machine() function, copied between BEGIN STATE MACHINE and END STATE MACHINE
markers. The copies must match, so a fix to one is made in all of them, and
the helper must keep its promises: listed moves only, the state shown as a
data attribute, and a console error (which fails the tests) for anything else.
"""

from __future__ import annotations

import re
import textwrap

import pytest
from playwright.sync_api import Page

from common import ROOT, game_files

BLOCK = re.compile(r"^[ \t]*// ---- BEGIN STATE MACHINE ----\n.*?^[ \t]*// ---- END STATE MACHINE ----\n", re.M | re.S)


def helper_copies() -> dict[str, str]:
    """{page: its copy of the helper, dedented}, for every page that has one."""
    copies = {}
    for filename in game_files():
        found = BLOCK.findall((ROOT / filename).read_text("utf-8"))
        assert len(found) <= 1, f"{filename} has {len(found)} copies of the helper"
        if found:
            copies[filename] = textwrap.dedent(found[0])
    return copies


def test_every_copy_of_the_helper_is_the_same():
    copies = helper_copies()
    assert copies, "no page has the state machine helper"
    first, *others = copies.items()
    for filename, text in others:
        assert text == first[1], f"{filename}'s helper differs from {first[0]}'s: change every copy"


@pytest.fixture
def helper(page: Page) -> Page:
    """A blank page with the helper loaded, and the console errors it logs."""
    page.set_content("<!doctype html><html><body><p id=other></p></body></html>")
    page.evaluate("() => { window.logged = []; console.error = (m) => window.logged.push(String(m)); }")
    page.add_script_tag(content=next(iter(helper_copies().values())) + "\nwindow.machine = machine;")
    return page


def test_listed_moves_are_made_and_shown(helper: Page):
    result = helper.evaluate("""() => {
      const seen = [];
      const m = machine('screen', { menu: ['playing'], playing: ['menu'] }, 'menu',
        { onMove: (to, from, why) => seen.push([to, from, why]) });
      const before = [document.documentElement.dataset.screen, m.seq];
      const moved = m.go('playing', 'tap');
      return { before, moved, after: [document.documentElement.dataset.screen, m.state, m.seq],
               is: [m.is('playing'), m.is('menu', 'playing'), m.is('menu')],
               can: [m.can('menu'), m.can('playing')], seen, logged };
    }""")
    assert result["before"] == ["menu", 0]
    assert result["moved"] is True
    assert result["after"] == ["playing", "playing", 1]
    assert result["is"] == [True, True, False]
    assert result["can"] == [True, False]
    assert result["seen"] == [["playing", "menu", "tap"]]
    assert result["logged"] == []


def test_any_other_move_is_refused_with_a_console_error(helper: Page):
    result = helper.evaluate("""() => {
      let calls = 0;
      const m = machine('screen', { menu: ['playing'], playing: ['menu'] }, 'menu', { onMove: () => calls++ });
      const moved = m.go('menu');
      return { moved, state: m.state, seq: m.seq, shown: document.documentElement.dataset.screen, calls, logged };
    }""")
    assert result == {
        "moved": False, "state": "menu", "seq": 0, "shown": "menu", "calls": 0,
        "logged": ["screen: no move from menu to menu"],
    }


def test_states_the_table_doesnt_name_are_errors(helper: Page):
    logged = helper.evaluate("""() => {
      const m = machine('save', { none: ['saving'], saving: ['saved'] }, 'none');
      m.is('savd');
      m.can('nowhere');
      return logged;
    }""")
    assert logged == [
        "save: no state called saved",
        "save: no state called savd",
        "save: no state called nowhere",
    ]


def test_el_picks_where_the_state_shows(helper: Page):
    result = helper.evaluate("""() => {
      const p = document.getElementById('other');
      const mine = machine('link', { open: ['closed'], closed: ['open'] }, 'open', { el: p });
      const hidden = machine('quiet', { a: ['b'], b: ['a'] }, 'a', { el: null });
      mine.go('closed');
      hidden.go('b');
      return { p: p.dataset.link, html: { ...document.documentElement.dataset }, hidden: hidden.state, logged };
    }""")
    assert result == {"p": "closed", "html": {}, "hidden": "b", "logged": []}
