"""A fake of the survey log's API (worker/src/survey-log.js) for page tests.

letterfield-log.html reads the Worker's URL from ?survey=, so tests point it
at https://survey.test and route those requests here with page.route. The
real API is tested in worker/test/survey-log.test.js. Entries are the API's
[w, x, y, d, s, initials, at, th]; places and themes come from the test, since
the names need the map's data, which only the Worker and the game hold.
"""

from __future__ import annotations

import json
import re

from playwright.sync_api import Route

SURVEY = "https://survey.test"
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
PAGE = 500


class FakeSurveyLog:
    def __init__(self, entries=(), places=None, themes=None, page=PAGE, fail=False, now_ms=None):
        self.entries = sorted(entries, key=lambda e: (e[6], e[0], e[1], e[2], e[3]))
        self.places = places or {}    # 'rx,ry' -> name
        self.themes = themes or {}    # theme index -> [name, hue]
        self.page = page
        self.fail = fail
        self.now_ms = now_ms  # the Worker refuses days and hours after this one's, as the real one does
        self.requests: list[str] = []  # path and query of every request

    def handle(self, route: Route) -> None:
        url = route.request.url
        self.requests.append(url.split("/v1/survey/log", 1)[1])
        headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
        if self.fail:
            route.fulfill(status=503, headers=headers, body=json.dumps({"error": "server error"}))
            return
        day = re.search(r"/v1/survey/log/day/(\d+)$", url)
        hour = re.search(r"/v1/survey/log/hour/(\d+)(?:\?after=(\d+))?$", url)
        future = self.now_ms is not None and (
            (day and int(day[1]) > self.now_ms // DAY_MS) or (hour and int(hour[1]) > self.now_ms // HOUR_MS)
        )
        if future:
            route.fulfill(status=400, headers=headers, body=json.dumps({"error": "that day has not started"}))
            return
        if day:
            d = int(day[1])
            hours = [0] * 24
            for e in self.entries:
                if e[6] // DAY_MS == d:
                    hours[e[6] // HOUR_MS - d * 24] += 1
            body = {"day": d, "hours": hours, "total": sum(hours)}
        elif hour:
            h, after = int(hour[1]), int(hour[2] or 0)
            rows = [e for e in self.entries if e[6] // HOUR_MS == h]
            more = len(rows) > after + self.page
            rows = rows[after : after + self.page]
            rx = lambda e: f"{e[1] // 48},{e[2] // 48}"
            body = {
                "hour": h,
                "entries": rows,
                "places": {rx(e): self.places[rx(e)] for e in rows if rx(e) in self.places},
                "themes": {str(e[7]): self.themes[e[7]] for e in rows if e[7] in self.themes},
                # The real cursor is the last entry's at~key; an offset does here.
                "next": str(after + self.page) if more else None,
            }
        else:
            route.fulfill(status=404, headers=headers, body=json.dumps({"error": "not found"}))
            return
        route.fulfill(status=200, headers=headers, body=json.dumps(body))
