"""A fake of the leaderboard Worker's API for game tests.

Games read the API's URL from ?leaderboard=, so tests point them at
https://leaderboard.test and route those requests here with Playwright's
page.route. The real Worker is tested in worker/test/.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Route

API = "https://leaderboard.test"


class FakeLeaderboard:
    """Answers the /v1 routes the way worker/src/leaderboard.js does."""

    def __init__(self, scores=(), groups=None, reject_with: str | None = None, status: int = 200):
        self.scores = [{"entry": f"seed-{i}", "at": i, **s} for i, s in enumerate(scores)]
        self.groups: dict[str, str] = dict(groups or {})
        self.new_codes = iter(["K7QP", "W3XY", "H8MN"])
        self.reject_with = reject_with
        self.status = status
        self.views: list[dict] = []   # query of every GET /v1/scores
        self.posts: list[dict] = []   # body of every POST /v1/scores

    def top(self, scope: str, difficulty: str = "all", mode: str = "all") -> list[dict]:
        rows = [
            s for s in self.scores
            if s["scope"] == scope and difficulty in ("all", s["difficulty"]) and mode in ("all", s["mode"])
        ]
        rows.sort(key=lambda s: (-s["score"], s["at"]))
        keys = ("entry", "initials", "score", "level", "difficulty", "mode", "at")
        return [{"rank": i + 1, **{k: s[k] for k in keys}} for i, s in enumerate(rows[:10])]

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
            if view["scope"] != "*" and view["scope"] not in self.groups:
                reply(404, {"error": "unknown group"})
            else:
                reply(200, {**view, "scores": self.top(view["scope"], view["difficulty"], view["mode"])})
        elif url.path == "/v1/scores":
            body = json.loads(request.post_data)
            self.posts.append(body)
            if self.reject_with:
                reply(400, {"error": self.reject_with})
                return
            entry, ranks = f"entry-{len(self.posts)}", {}
            for scope in (["*"] if body["public"] else []) + body["groups"]:
                row = {k: body[k] for k in ("initials", "score", "level", "difficulty", "mode")}
                self.scores.append({**row, "entry": entry, "scope": scope, "at": 1000 + len(self.scores)})
                board = self.top(scope, body["difficulty"], body["mode"])
                ranks[scope] = next((r["rank"] for r in board if r["entry"] == entry), 11)
            reply(201, {"entry": entry, "ranks": ranks})
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
