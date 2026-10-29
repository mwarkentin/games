"""Funnels & Buckets' global leaderboard, against a fake of the Worker API.

The game reads the API's URL from ?leaderboard=, so these tests point it at
https://leaderboard.test and answer those requests in Python. The Worker
itself is tested in worker/test/.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, Route, expect

API = "https://leaderboard.test"
SINGLE_TABLE_NOTE = "Games with one times table are practice and don’t go on the leaderboard."
UNAVAILABLE = "The leaderboard is unavailable right now."


class FakeLeaderboard:
    """Answers GET and POST /v1/scores the way worker/src/index.js does."""

    def __init__(self, scores=(), reject_with: str | None = None, status: int = 200):
        self.scores = [{"id": i + 1, **s} for i, s in enumerate(scores)]
        self.posts: list[dict] = []
        self.reject_with = reject_with
        self.status = status

    def top(self, board: str) -> list[dict]:
        rows = sorted((s for s in self.scores if s["board"] == board), key=lambda s: -s["score"])
        return [
            {"rank": i + 1, "id": s["id"], "initials": s["initials"], "score": s["score"], "level": s["level"], "at": 0}
            for i, s in enumerate(rows[:10])
        ]

    def handle(self, route: Route) -> None:
        request = route.request
        headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
        if self.status >= 500:
            route.fulfill(status=self.status, headers=headers, body='{"error": "server error"}')
        elif request.method == "GET":
            board = parse_qs(urlparse(request.url).query)["board"][0]
            body = {"game": "funnels-and-buckets", "board": board, "scores": self.top(board)}
            route.fulfill(status=200, headers=headers, body=json.dumps(body))
        else:
            entry = json.loads(request.post_data)
            self.posts.append(entry)
            if self.reject_with:
                route.fulfill(status=400, headers=headers, body=json.dumps({"error": self.reject_with}))
                return
            row = {"id": len(self.scores) + 1, **entry}
            self.scores.append(row)
            top = self.top(entry["board"])
            rank = next((r["rank"] for r in top if r["id"] == row["id"]), 11)
            route.fulfill(status=201, headers=headers, body=json.dumps({"id": row["id"], "rank": rank, "scores": top}))


def classic(initials: str, score: int) -> dict:
    return {"board": "classic", "initials": initials, "score": score, "level": 3}


def open_game(page: Page, site_url: str, fake: FakeLeaderboard | None) -> None:
    if fake:
        page.route(f"{API}/**", fake.handle)
        page.goto(f"{site_url}/funnels-and-buckets?leaderboard={API}#debug")
    else:
        page.goto(f"{site_url}/funnels-and-buckets#debug")


def play_one_bubble(page: Page) -> None:
    """Pop one divide bubble (20 points), then end the game."""
    page.click("#startBtn")
    page.evaluate("window.__fb.queue([['div', 20, 4]])")
    page.wait_for_function("() => window.__fb.peek().bubbles.some((b) => b.ans === 5)", timeout=15000)
    page.keyboard.type("5")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__fb.peek().popped === 1")
    page.wait_for_timeout(1100)  # at least a second of play, which the API checks
    page.evaluate("window.__fb.end()")
    expect(page.locator("#overOv")).to_be_visible()


def test_leaderboard_stays_hidden_until_configured(page: Page, site_url, errors):
    open_game(page, site_url, None)
    expect(page.locator("#menuLb")).to_be_hidden()
    play_one_bubble(page)
    expect(page.locator("#overLb")).to_be_hidden()
    assert errors == []


def test_top_ten_score_saves_initials(page: Page, site_url, errors):
    fake = FakeLeaderboard([classic("KID", 300), classic("MRW", 245)])
    open_game(page, site_url, fake)
    expect(page.locator("#menuLb")).to_contain_text("Classic")
    expect(page.locator("#menuLbList li")).to_have_count(2)

    play_one_bubble(page)
    expect(page.locator("#lbForm")).to_be_visible()
    page.locator("#lbInitials").press_sequentially("z3e d")  # letters only, upper-cased as you type
    expect(page.locator("#lbInitials")).to_have_value("ZED")
    page.click("#lbSave")

    mine = page.locator("#overLbList li.mine")
    expect(mine).to_have_text("3ZED20")
    expect(page.locator("#overLbNote")).to_have_text("Saved! You’re number 3 on the Classic board.")
    expect(page.locator("#lbForm")).to_be_hidden()
    [entry] = fake.posts
    assert entry["seconds"] >= 1
    assert {k: v for k, v in entry.items() if k != "seconds"} == {
        "game": "funnels-and-buckets", "board": "classic", "initials": "ZED", "score": 20, "level": 1, "popped": 1,
    }

    # The menu shows the new entry, and the initials are remembered for next time.
    page.click("#settingsBtn")
    expect(page.locator("#menuLbList li")).to_have_count(3)
    play_one_bubble(page)
    expect(page.locator("#lbInitials")).to_have_value("ZED")
    assert errors == []


def test_score_below_tenth_place_only_shows_the_board(page: Page, site_url, errors):
    fake = FakeLeaderboard([classic(f"A{chr(65 + i)}A", 500 - i) for i in range(10)])
    open_game(page, site_url, fake)
    play_one_bubble(page)
    expect(page.locator("#overLbList li")).to_have_count(10)
    expect(page.locator("#lbForm")).to_be_hidden()
    assert fake.posts == []
    assert errors == []


def test_single_table_games_stay_off_the_board(page: Page, site_url, errors):
    fake = FakeLeaderboard()
    open_game(page, site_url, fake)
    page.select_option("#table", "7")
    expect(page.locator("#menuLbNote")).to_have_text(SINGLE_TABLE_NOTE)
    play_one_bubble(page)
    expect(page.locator("#overLbNote")).to_have_text(SINGLE_TABLE_NOTE)
    expect(page.locator("#lbForm")).to_be_hidden()
    assert errors == []


def test_rejected_initials_show_the_reason(page: Page, site_url):
    fake = FakeLeaderboard(reject_with="pick different initials")
    open_game(page, site_url, fake)
    play_one_bubble(page)
    page.fill("#lbInitials", "WTF")
    page.click("#lbSave")
    expect(page.locator("#overLbNote")).to_have_text("Couldn’t save: pick different initials.")
    expect(page.locator("#lbForm")).to_be_visible()


def test_unavailable_leaderboard_does_not_block_the_game(page: Page, site_url):
    fake = FakeLeaderboard(status=500)
    open_game(page, site_url, fake)
    expect(page.locator("#menuLbNote")).to_have_text(UNAVAILABLE)
    play_one_bubble(page)
    expect(page.locator("#overLbNote")).to_have_text(UNAVAILABLE)
    expect(page.locator("#againBtn")).to_be_enabled()
