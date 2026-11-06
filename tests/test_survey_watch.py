"""scripts/survey_watch.py, which the daily survey-watch workflow runs."""

from __future__ import annotations

import json

import survey_watch
from survey_watch import CAPPED_ALERT, RATE_ALERT, RATE_MIN_WORDS, check, main


def world(**yesterday):
    day = {"day": 20389, "charted": 0, "addresses": 0, "capped": 0, "playerHours": 0, **yesterday}
    return {"charted": 1, "total": 1_120_206, "players": 0, "today": {**day, "day": 20390}, "yesterday": day}


def test_a_day_of_people_playing_is_quiet():
    assert check(world(charted=4_000, addresses=300, capped=2, playerHours=150)) == []
    assert check(world(charted=RATE_MIN_WORDS - 1, playerHours=0)) == []  # too few words to judge
    assert check({"yesterday": None}) == []  # the survey's first day, or the Atlas started again
    assert check({}) == []


def test_many_addresses_at_the_daily_cap():
    [reason] = check(world(charted=6_000, addresses=CAPPED_ALERT, capped=CAPPED_ALERT, playerHours=200))
    assert f"{CAPPED_ALERT:,} addresses reached the daily cap" in reason


def test_words_charted_faster_than_people_could():
    [reason] = check(world(charted=10_000, addresses=50, playerHours=10_000 / RATE_ALERT))
    assert "an hour each" in reason
    [reason] = check(world(charted=1_000, addresses=5, playerHours=0))
    assert "nobody online" in reason


def test_prints_a_note_only_when_something_looks_wrong(tmp_path, capsys):
    quiet, busy = tmp_path / "quiet.json", tmp_path / "busy.json"
    quiet.write_text(json.dumps(world(charted=100, playerHours=5)))
    busy.write_text(json.dumps(world(charted=9_000, addresses=40, capped=30, playerHours=3)))
    assert main(["survey_watch.py", str(quiet)]) == 0
    assert capsys.readouterr().out == ""
    assert main(["survey_watch.py", str(busy)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Yesterday's numbers")
    assert "| 9,000 | 40 | 30 | 3 |" in out
    assert "TURNSTILE.md" in out


def test_an_unreachable_survey_prints_nothing(monkeypatch, capsys):
    monkeypatch.setenv("SURVEY_WORLD_URL", "http://127.0.0.1:9/v1/survey/world")  # nothing listens there
    assert survey_watch.main(["survey_watch.py"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "::warning::" in captured.err
