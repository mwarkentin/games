"""scripts/select_tests.py: which tests CI runs for a pull request's changes."""

from __future__ import annotations

import subprocess

from common import ROOT
from select_tests import MAX_SHARDS, changed_since, select

ALL_TESTS = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_*.py"))


def names(result: dict) -> set[str]:
    return {t.removeprefix("tests/test_").removesuffix(".py") for t in result["tests"]}


def test_a_letterfield_change_runs_letterfield_and_the_shared_tests_but_not_war():
    result = select(["letterfield.html", "changelog/letterfield.md", "tests/test_letterfield.py"])
    assert result["pytest"]
    got = names(result)
    assert {"letterfield", "letterfield_survey", "letterfield_log", "letterfield_definitions"} <= got
    assert {"games", "build", "pwa", "feedback", "telemetry", "state_machines"} <= got, "the tests of every game"
    assert not got & {"war", "war_rooms", "doodle_chomp", "funnels_and_buckets"}
    assert len(result["shards"]) < MAX_SHARDS


def test_a_page_that_belongs_to_a_game_runs_that_games_tests():
    assert names(select(["letterfield-log.html"])) == names(select(["letterfield.html"]))


def test_a_game_runs_the_tests_of_other_games_that_load_its_page():
    # Groups are shared across games, so Air Traffic Controller's leaderboard
    # tests load Doodle Chomp too.
    got = names(select(["doodle-chomp.html"]))
    assert {"doodle_chomp", "doodle_chomp_leaderboard", "air_traffic_controller_leaderboard"} <= got
    assert "air_traffic_controller" not in got


def test_icons_previews_and_tests_belong_to_their_game():
    war = names(select(["war.html"]))
    for path in ("icons/war.svg", "icons/war-192.png", "tests/test_war_rooms.py", "changelog/war.md"):
        assert names(select([path])) == war, path
    assert "funnels_and_buckets" in names(select(["previews/funnels-and-buckets.jpg"]))


def test_anything_shared_runs_the_whole_suite():
    for path in ("feedback.js", "sw.js", "scripts/common.py", "tests/conftest.py", "tests/fake_survey.py",
                 "README.md", "music/README.md", ".github/workflows/test.yml", ".test_durations", "uv.lock"):
        result = select(["letterfield.html", path])
        assert result == {"pytest": True, "tests": [], "shards": list(range(1, MAX_SHARDS + 1))}, path


def test_files_no_test_reads_run_no_pytest_and_dont_widen_a_game():
    assert select(["worker/src/war.js", "share/src/card.js", "AGENTS.md", "docs/link-previews.md"])["pytest"] is False
    assert select(["worker/src/war.js", "war.html", "AGENTS.md"]) == select(["war.html"])
    assert select(["biome.jsonc", "scripts/lint.sh"])["pytest"] is False


def test_every_selection_is_a_set_of_real_test_files():
    for changed in (["letterfield.html"], ["war.html"], ["air-traffic-controller.html"], ["funnels-and-buckets.html"]):
        tests = select(changed)["tests"]
        assert tests and set(tests) <= set(ALL_TESTS), changed


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=root, check=True, capture_output=True)


def test_a_branch_pushed_before_its_pull_request_is_judged_by_its_changes_from_main(tmp_path):
    # A branch's first push, before it has a pull request, gets the same narrow
    # run its pull request would: what it changed since it left main, with both
    # sides of a rename, and not what main has changed since.
    git(tmp_path, "init", "-q", "-b", "main")
    for name in ("war.html", "old.txt", "letterfield.html"):
        (tmp_path / name).write_text(name)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "main")
    git(tmp_path, "checkout", "-qb", "claude/x")
    (tmp_path / "letterfield.html").write_text("changed")
    git(tmp_path, "mv", "old.txt", "new.txt")
    git(tmp_path, "commit", "-qam", "branch")
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "war.html").write_text("main moved on")
    git(tmp_path, "commit", "-qam", "later on main")
    git(tmp_path, "checkout", "-q", "claude/x")
    assert sorted(filter(None, changed_since("main", tmp_path))) == ["letterfield.html", "new.txt", "old.txt"]
    assert changed_since("no-such-branch", tmp_path) is None, "can't compare, so everything runs"

