"""The music in music/: real MIDI files, each listed with its source and a
licence that lets anyone use it (see music/README.md)."""

from __future__ import annotations

import re

import pytest

from common import ROOT, music_files

README = (ROOT / "music" / "README.md").read_text("utf-8")
MUSIC = music_files()


def test_there_is_music():
    assert MUSIC


@pytest.mark.parametrize("name", MUSIC)
def test_music_is_a_small_midi_file(name):
    data = (ROOT / name).read_bytes()
    assert data[:4] == b"MThd", "not a MIDI file"
    assert len(data) < 64 * 1024, "notes only: no recordings or samples"


@pytest.mark.parametrize("name", MUSIC)
def test_music_is_listed_with_a_free_licence_and_a_source(name):
    row = next((line for line in README.splitlines() if line.startswith(f"| `{name.removeprefix('music/')}`")), None)
    assert row, f"add {name} to music/README.md"
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells[-1] in ("Public Domain", "CC0"), "only music anyone may use, with no credit owed"
    assert re.search(r"\]\(https://github\.com/MutopiaProject/MutopiaProject/blob/[0-9a-f]{40}/", cells[-2]), (
        "link the source at a fixed commit"
    )


def test_the_readme_lists_nothing_that_isnt_there():
    listed = re.findall(r"^\| `([^`]+\.mid)`", README, re.MULTILINE)
    assert sorted(listed) == sorted(name.removeprefix("music/") for name in MUSIC)
