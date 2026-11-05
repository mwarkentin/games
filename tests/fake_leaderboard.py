"""A fake of the leaderboard Worker's API for game tests.

Games read the API's URL from ?leaderboard=, so tests point them at
https://leaderboard.test and route those requests here with Playwright's
page.route. The real Worker is tested in worker/test/.

Without ?leaderboard=, games call the real Worker (WORKER_URL). Every test
context routes it to an empty fake with stand_in_for_worker(), so no test
reads or writes real scores, and the smoke tests don't depend on the Worker
being up or on its CORS rules, which only allow the real site.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import BrowserContext, Page, Route

API = "https://leaderboard.test"
# LEADERBOARD_URL in the games and ROOMS_URL in war.html.
WORKER_URL = "https://games-leaderboard.mwarkentin.workers.dev"


DAY_MS = 24 * 60 * 60 * 1000


def now_ms() -> int:
    return int(time.time() * 1000)


class FakeLeaderboard:
    """Answers the /v1 routes the way worker/src/leaderboard.js does.

    Seeded scores were saved a minute ago unless they give `days_ago`.
    """

    def __init__(self, scores=(), groups=None, reject_with: str | None = None, status: int = 200):
        start = now_ms() - 60_000
        self.scores = []
        for i, s in enumerate(scores):
            s = dict(s)
            days_ago = s.pop("days_ago", None)
            at = start - days_ago * DAY_MS if days_ago is not None else start + i
            self.scores.append({"entry": f"seed-{i}", "at": at, **s})
        self.groups: dict[str, str] = dict(groups or {})
        self.new_codes = iter(["K7QP", "W3XY", "H8MN"])
        self.reject_with = reject_with
        self.status = status
        self.views: list[dict] = []   # query of every GET /v1/scores
        self.posts: list[dict] = []   # body of every POST /v1/scores

    def board(self, scope: str, difficulty: str = "all", mode: str = "all", since: int | None = None) -> list[dict]:
        rows = [
            s for s in self.scores
            if s["scope"] == scope and difficulty in ("all", s["difficulty"]) and mode in ("all", s["mode"])
            and (since is None or s["at"] >= since)
        ]
        return sorted(rows, key=lambda s: (-s["score"], s["at"]))

    def top(self, scope: str, difficulty: str = "all", mode: str = "all", since: int | None = None) -> list[dict]:
        keys = ("entry", "initials", "score", "level", "difficulty", "mode", "at")
        rows = self.board(scope, difficulty, mode, since)[:10]
        return [{"rank": i + 1, **{k: s[k] for k in keys}} for i, s in enumerate(rows)]

    def rank(self, row: dict, since: int | None = None) -> int:
        board = self.board(row["scope"], row["difficulty"], row["mode"], since)
        return 1 + sum(1 for s in board if s["score"] > row["score"] or (s["score"] == row["score"] and s["at"] < row["at"]))

    def handle(self, route: Route) -> None:
        request = route.request
        url = urlparse(request.url)

        def reply(status: int, body: dict) -> None:
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            route.fulfill(status=status, headers=headers, body=json.dumps(body))

        if self.status >= 500:
            reply(self.status, {"error": "server error"})
        elif url.path == "/v1/scores" and request.method == "GET":
            view = {k: v[0] for k, v in parse_qs(url.query).items()}
            self.views.append(view)
            since = int(view["since"]) if "since" in view else None
            if view["scope"] != "*" and view["scope"] not in self.groups:
                reply(404, {"error": "unknown group"})
            else:
                scores = self.top(view["scope"], view["difficulty"], view["mode"], since)
                reply(200, {**view, "since": since, "scores": scores})
        elif url.path == "/v1/scores":
            body = json.loads(request.post_data)
            self.posts.append(body)
            if self.reject_with:
                reply(400, {"error": self.reject_with})
                return
            entry, ranks, period_ranks = f"entry-{len(self.posts)}", {}, {}
            since = body.get("since")
            for scope in (["*"] if body["public"] else []) + body["groups"]:
                row = {k: body[k] for k in ("initials", "score", "level", "difficulty", "mode")}
                row = {**row, "entry": entry, "scope": scope, "at": now_ms()}
                self.scores.append(row)
                ranks[scope] = self.rank(row)
                if since is not None:
                    period_ranks[scope] = self.rank(row, since)
            reply(201, {"entry": entry, "ranks": ranks, **({"periodRanks": period_ranks} if since is not None else {})})
        elif url.path == "/v1/groups":
            name = " ".join(json.loads(request.post_data)["name"].split())
            code = next(self.new_codes)
            self.groups[code] = name
            reply(201, {"code": code, "name": name})
        else:
            code = url.path.rsplit("/", 1)[-1]
            if code in self.groups:
                reply(200, {"code": code, "name": self.groups[code]})
            else:
                reply(404, {"error": "unknown group"})


def stand_in_for_worker(context: BrowserContext) -> FakeLeaderboard:
    """Answer the real Worker's URL in `context` with an empty fake."""
    fake = FakeLeaderboard()
    context.route(f"{WORKER_URL}/**", fake.handle)
    return fake


def without_worker(page: Page, site_url: str, game: str) -> None:
    """Serve `game` with LEADERBOARD_URL and ROOMS_URL blanked, as it runs with no Worker set up."""

    def handle(route: Route) -> None:
        response = route.fetch()
        body = re.sub(r"\b((?:LEADERBOARD|ROOMS)_URL = )'[^']*'", r"\1''", response.text())
        route.fulfill(response=response, body=body)

    page.route(lambda url: urlparse(url).path == f"/{game}", handle)
