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
from collections import Counter
from datetime import datetime, timezone

from playwright.sync_api import Route

SURVEY = "https://survey.test"
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
PAGE = 500
SLICE_PAGE = 100
AREA_CELLS = (-12 * 192, 13 * 192)  # the shared world, x and y from..to-1


def in_world(e) -> bool:
    return e[4] == 0 and all(AREA_CELLS[0] <= v < AREA_CELLS[1] for v in (e[1], e[2]))


def month_hours(m: int) -> tuple[int, int]:
    """A UTC month's first and last-plus-one hour, months since January 1970."""
    def start(k: int) -> int:
        return int(datetime(1970 + k // 12, k % 12 + 1, 1, tzinfo=timezone.utc).timestamp()) * 1000 // HOUR_MS
    return start(m), start(m + 1)


class FakeSurveyLog:
    def __init__(self, entries=(), places=None, themes=None, page=PAGE, fail=False, now_ms=None,
                 slice_page=SLICE_PAGE, totals=None):
        self.entries = sorted(entries, key=lambda e: (e[6], e[0], e[1], e[2], e[3]))
        self.places = places or {}    # 'rx,ry' -> name
        self.themes = themes or {}    # theme index -> [name, hue]
        self.totals = totals or {}    # 'rx,ry' -> hidden words in that territory (112 if not given)
        self.page = page
        self.slice_page = slice_page
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
        month = re.search(r"/v1/survey/log/month/(\d+)$", url)
        top = re.search(r"/v1/survey/log/top/(\d+)/(\d+)$", url)
        sliced = re.search(r"/v1/survey/log/(surveyor|theme)/([A-Z]{3}|\d+)/(\d+)/(\d+)(?:\?before=(\d+))?$", url)
        territory = re.search(r"/v1/survey/log/territory/(-?\d+)/(-?\d+)$", url)
        future = self.now_ms is not None and (
            (day and int(day[1]) > self.now_ms // DAY_MS) or (hour and int(hour[1]) > self.now_ms // HOUR_MS)
            or (month and month_hours(int(month[1]))[0] > self.now_ms // HOUR_MS)
            or (top and int(top[1]) > self.now_ms // DAY_MS)
            or (sliced and int(sliced[3]) > self.now_ms // HOUR_MS)
        )
        if future:
            route.fulfill(status=400, headers=headers, body=json.dumps({"error": "that day has not started"}))
            return
        if url.split("?")[0].endswith("/v1/survey/log/span"):
            hours = [e[6] // HOUR_MS for e in self.entries]
            body = {"first": min(hours, default=None), "last": max(hours, default=None)}
        elif month:
            first, last = month_hours(int(month[1]))
            counts = Counter(e[6] // HOUR_MS for e in self.entries if first <= e[6] // HOUR_MS < last)
            world = Counter(e[6] // HOUR_MS for e in self.entries if first <= e[6] // HOUR_MS < last and in_world(e))
            body = {"month": int(month[1]), "hours": [[h, n, world[h]] for h, n in sorted(counts.items())]}
        elif top:
            first, last = int(top[1]), int(top[2])
            rows = [e for e in self.entries if first <= e[6] // DAY_MS < last]
            surveyors = Counter(e[5] for e in rows if e[5])
            # Hidden words only, by territory; a hidden word's theme is its territory's.
            places = Counter((e[1] // 48, e[2] // 48) for e in rows if e[4] == 0)
            theme_of = {(e[1] // 48, e[2] // 48): e[7] for e in rows if e[4] == 0}
            themes = Counter()
            for place, n in places.items():
                themes[theme_of[place]] += n
            body = {
                "from": first, "to": last, "hidden": sum(places.values()),
                "surveyors": [[i, n] for i, n in sorted(surveyors.items(), key=lambda r: (-r[1], r[0]))[:10]],
                "territories": [
                    [rx, ry, self.places.get(f"{rx},{ry}", f"Place {rx},{ry}"), theme_of[(rx, ry)], n]
                    for (rx, ry), n in sorted(places.items(), key=lambda r: (-r[1], r[0][1], r[0][0]))[:10]
                ],
                "themes": [
                    [th, *self.themes.get(th, [f"Theme {th}", 200]), n]
                    for th, n in sorted(themes.items(), key=lambda r: (-r[1], r[0]))
                ],
            }
        elif sliced:
            kind, key, first, last, before = sliced[1], sliced[2], int(sliced[3]), int(sliced[4]), int(sliced[5] or 0)
            if kind == "theme" and int(key) not in self.themes:
                route.fulfill(status=400, headers=headers, body=json.dumps({"error": "no such theme"}))
                return
            mine = (lambda e: e[5] == key) if kind == "surveyor" else (lambda e: e[4] == 0 and e[7] == int(key))
            rows = [e for e in self.entries if mine(e) and first <= e[6] // HOUR_MS < last]
            counts = Counter(e[6] // HOUR_MS for e in rows)
            world = Counter(e[6] // HOUR_MS for e in rows if in_world(e))
            body = {
                "kind": kind, "key": key if kind == "surveyor" else int(key), "from": first, "to": last,
                "words": len(rows), "world": sum(world.values()),
                "hours": [[h, n, world[h]] for h, n in sorted(counts.items())],
                **self.tops(rows, kind),
                **self.page_of(list(reversed(rows)), before, self.slice_page),
            }
            if kind == "theme":
                body["name"], body["hue"] = self.themes[int(key)]
        elif territory:
            rx, ry = int(territory[1]), int(territory[2])
            rows = [e for e in reversed(self.entries) if (e[1] // 48, e[2] // 48) == (rx, ry)]
            th = next((e[7] for e in rows if e[4] == 0), (rx + 21 * ry) % 116)
            body = {
                "rx": rx, "ry": ry, "name": self.places.get(f"{rx},{ry}", f"Place {rx},{ry}"), "th": th,
                "total": self.totals.get(f"{rx},{ry}", 112), "charted": sum(1 for e in rows if e[4] == 0),
                "topSurveyors": self.tops(rows, "theme")["topSurveyors"],
                **self.page_of(rows, 0, 1000),
            }
            body["themes"].setdefault(str(th), self.themes.get(th, [f"Theme {th}", 200]))
            del body["next"]
        elif day:
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

    def page_of(self, rows, start, size):
        """A page of entries from `start`, with the names they need and an offset for the next."""
        part = rows[start : start + size]
        place = lambda e: f"{e[1] // 48},{e[2] // 48}"
        return {
            "entries": part,
            "places": {place(e): self.places[place(e)] for e in part if place(e) in self.places},
            "themes": {str(e[7]): self.themes[e[7]] for e in part if e[7] in self.themes},
            "next": str(start + size) if len(rows) > start + size else None,
        }

    def tops(self, rows, kind):
        """A surveyor's top territories and themes, or a theme's top surveyors and territories."""
        places = Counter((e[1] // 48, e[2] // 48) for e in rows if e[4] == 0)
        theme_of = {(e[1] // 48, e[2] // 48): e[7] for e in rows if e[4] == 0}
        out = {"topTerritories": [
            [rx, ry, self.places.get(f"{rx},{ry}", f"Place {rx},{ry}"), theme_of[(rx, ry)], n]
            for (rx, ry), n in sorted(places.items(), key=lambda r: (-r[1], r[0][1], r[0][0]))[:10]
        ]}
        if kind == "surveyor":
            themes = Counter()
            for place, n in places.items():
                themes[theme_of[place]] += n
            out["topThemes"] = [
                [th, *self.themes.get(th, [f"Theme {th}", 200]), n] for th, n in sorted(themes.items(), key=lambda r: (-r[1], r[0]))
            ]
        else:
            people = Counter(e[5] for e in rows if e[5])
            out["topSurveyors"] = [[i, n] for i, n in sorted(people.items(), key=lambda r: (-r[1], r[0]))[:10]]
        return out
