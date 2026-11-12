"""scripts/survey_watch.py, which the daily survey-watch workflow runs."""

from __future__ import annotations

import json

import survey_watch
from survey_watch import (
    CAPPED_ALERT,
    RATE_ALERT,
    RATE_MIN_WORDS,
    UNPASSED_MIN_JOINS,
    UNPASSED_PER_HOUR,
    check,
    main,
    site_key_set,
)


def world(**yesterday):
    day = {"day": 20389, "charted": 0, "addresses": 0, "capped": 0, "playerHours": 0, "unpassed": 0, **yesterday}
    return {"charted": 1, "total": 1_120_206, "players": 0, "today": {**day, "day": 20390}, "yesterday": day}


def test_a_day_of_people_playing_is_quiet():
    assert check(world(charted=4_000, addresses=300, capped=2, playerHours=150)) == []
    assert check(world(charted=RATE_MIN_WORDS - 1, playerHours=0)) == []  # too few words to judge
    assert check({"yesterday": None}) == []  # the survey's first day, or the Atlas started again
    assert check({}) == []
    stale = world(charted=9_000, capped=50, playerHours=1)
    stale["today"]["day"] += 1  # yesterday's numbers are from two days ago, already checked
    assert check(stale) == []


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
    assert "| 9,000 | 40 | 30 | 3 | 0 |" in out
    assert "TURNSTILE.md" in out


def test_an_unreachable_survey_prints_nothing(monkeypatch, capsys):
    monkeypatch.setenv("SURVEY_WORLD_URL", "http://127.0.0.1:9/v1/survey/world")  # nothing listens there
    assert survey_watch.main(["survey_watch.py"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "::warning::" in captured.err


def test_many_joins_without_a_turnstile_pass_once_the_game_has_a_site_key():
    bots = world(charted=200, addresses=30, playerHours=40, unpassed=2_000)
    [reason] = check(bots, site_key=True)
    assert "2,000 sockets joined without a Turnstile pass" in reason
    # Before the site key is in the game every join comes without a pass, so it says nothing.
    assert check(bots, site_key=False) == []
    # Players whose browsers block Turnstile, on a busy day: below UNPASSED_PER_HOUR.
    assert check(world(playerHours=1_000, unpassed=UNPASSED_PER_HOUR * 1_000 - 1), site_key=True) == []
    # A quiet day is too few joins to judge.
    assert check(world(playerHours=0, unpassed=UNPASSED_MIN_JOINS - 1), site_key=True) == []
    [reason] = check(world(playerHours=0, unpassed=UNPASSED_MIN_JOINS), site_key=True)
    # Older days, before the count existed, have none.
    day = world()
    del day["yesterday"]["unpassed"]
    assert check(day, site_key=True) == []


def test_reads_the_site_key_from_the_game(tmp_path):
    game = tmp_path / "letterfield.html"
    game.write_text("const SURVEY_URL = '';\nconst TURNSTILE_SITE_KEY = '';\n")
    assert site_key_set(game) is False
    game.write_text("const TURNSTILE_SITE_KEY = '0x4AAAAAAAexample';\n")
    assert site_key_set(game) is True
    assert site_key_set(tmp_path / "missing.html") is False
    assert isinstance(site_key_set(), bool)  # and reads the real game
