"""A fake of the survey log's API (worker/src/survey-log.js) for page tests.

letterfield-log.html reads the Worker's URL from ?survey=, so tests point it
at https://survey.test and route those requests here with page.route. The
real API is tested in worker/test/survey-log.test.js. Entries are the API's
[w, x, y, d, s, initials, at, th]; places and themes come from the test, since
the names need the map's data, which only the Worker and the game hold.
Supernovas are worked out from the entries, as a sector does, for each
territory the test gives a total: once that many of its hidden words are in,
the one that made it is the last word. The timelapse's index names every
theme, so themes the test doesn't give get a made-up name and hue. An entry
can carry a ninth item, the log id of the guild it counts for, which the
real log keeps in a column of its own and never sends with entries; the
test names each guild in `guilds`.
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
TIMELAPSE_PAGE = 5000
THEME_COUNT, LAT_B = 225, 15  # a territory's theme is (rx + 15 ry) mod 225, as on map 4
AREA_CELLS = (-12 * 192, 13 * 192)  # the shared world, x and y from..to-1


def in_world(e) -> bool:
    return e[4] == 0 and all(AREA_CELLS[0] <= v < AREA_CELLS[1] for v in (e[1], e[2]))


def guild_of(e) -> str:
    """The log id of the guild an entry counts for, or '' for none."""
    return e[8] if len(e) > 8 else ""


def month_hours(m: int) -> tuple[int, int]:
    """A UTC month's first and last-plus-one hour, months since January 1970."""
    def start(k: int) -> int:
        return int(datetime(1970 + k // 12, k % 12 + 1, 1, tzinfo=timezone.utc).timestamp()) * 1000 // HOUR_MS
    return start(m), start(m + 1)


class FakeSurveyLog:
    def __init__(self, entries=(), places=None, themes=None, page=PAGE, fail=False, now_ms=None,
                 slice_page=SLICE_PAGE, totals=None, timelapse_page=TIMELAPSE_PAGE, guilds=None):
        self.entries = sorted(entries, key=lambda e: (e[6], e[0], e[1], e[2], e[3]))
        self.places = places or {}    # 'rx,ry' -> name
        self.themes = themes or {}    # theme index -> [name, hue]
        self.guilds = guilds or {}    # log id -> [name, hue]
        self.totals = totals or {}    # 'rx,ry' -> hidden words in that territory (112 if not given; only these go supernova)
        self.page = page
        self.slice_page = slice_page
        self.timelapse_page = timelapse_page
        self.fail = fail
        self.now_ms = now_ms  # the Worker refuses days and hours after this one's, as the real one does
        self.requests: list[str] = []  # path and query of every request
        self.fail_novas = False  # supernovas answer 503, as if only they were failing

    def handle(self, route: Route) -> None:
        # The page adds ?v=<CACHE_VERSION> (or &v=) to every request, for browsers' caches.
        url = route.request.url
        assert re.search(r"[?&]v=\d+$", url), url
        url = re.sub(r"[?&]v=\d+$", "", url)
        self.requests.append(url.split("/v1/survey/log", 1)[1])
        headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
        if self.fail:
            route.fulfill(status=503, headers=headers, body=json.dumps({"error": "server error"}))
            return
        day = re.search(r"/v1/survey/log/day/(\d+)$", url)
        hour = re.search(r"/v1/survey/log/hour/(\d+)(?:\?after=(\d+))?$", url)
        month = re.search(r"/v1/survey/log/month/(\d+)$", url)
        top = re.search(r"/v1/survey/log/top/(\d+)/(\d+)$", url)
        top_hours = re.search(r"/v1/survey/log/top/hours/(\d+)/(\d+)$", url)
        sliced = re.search(r"/v1/survey/log/(surveyor|theme|guild)/([A-Z]{3}|[0-9a-f]{10}|\d+)/(\d+)/(\d+)(?:\?before=(\d+))?$", url)
        territory = re.search(r"/v1/survey/log/territory/(-?\d+)/(-?\d+)$", url)
        novas = re.search(r"/v1/survey/log/novas/(\d+)/(\d+)(?:\?before=(\d+))?$", url)
        timelapse = re.search(r"/v1/survey/log/timelapse$", url)
        timelapse_day = re.search(r"/v1/survey/log/timelapse/(\d+)(?:\?after=(\d+))?$", url)
        future = self.now_ms is not None and (
            (day and int(day[1]) > self.now_ms // DAY_MS) or (hour and int(hour[1]) > self.now_ms // HOUR_MS)
            or (month and month_hours(int(month[1]))[0] > self.now_ms // HOUR_MS)
            or (top and int(top[1]) > self.now_ms // DAY_MS)
            or (top_hours and int(top_hours[1]) > self.now_ms // HOUR_MS)
            or (sliced and int(sliced[3]) > self.now_ms // HOUR_MS)
            or (novas and int(novas[1]) > self.now_ms // HOUR_MS)
            or (timelapse_day and int(timelapse_day[1]) > self.now_ms // DAY_MS)
        )
        if future:
            route.fulfill(status=400, headers=headers, body=json.dumps({"error": "that day has not started"}))
            return
        if url.split("?")[0].endswith("/v1/survey/log/span"):
            hours = [e[6] // HOUR_MS for e in self.entries]
            body = {"first": min(hours, default=None), "last": max(hours, default=None)}
        elif timelapse:
            hours = Counter(e[6] // HOUR_MS for e in self.entries)
            nova_hours = Counter(n[2] // HOUR_MS for n in self.novas())
            hidden = [(e[1] // 48, e[2] // 48) for e in self.entries if e[4] == 0]
            body = {
                "hours": [[h, n] for h, n in sorted(hours.items())],
                "novas": [[h, n] for h, n in sorted(nova_hours.items())],
                "bounds": [min(r[0] for r in hidden), min(r[1] for r in hidden), max(r[0] for r in hidden), max(r[1] for r in hidden)]
                if hidden else None,
                "themes": [self.themes.get(i, [f"Theme {i}", i * 37 % 360]) for i in range(THEME_COUNT)],
                "layout": [LAT_B, THEME_COUNT],
            }
        elif timelapse_day:
            d, after = int(timelapse_day[1]), int(timelapse_day[2] or 0)
            rows = [e for e in self.entries if e[6] // DAY_MS == d]
            part = rows[after : after + self.timelapse_page]
            body = {
                "day": d,
                "words": [[e[6] - d * DAY_MS, e[1], e[2], e[3], len(e[0]), e[7], e[4]] for e in part],
                "novas": [] if after else [[n[2] - d * DAY_MS, n[0], n[1], n[13]] for n in sorted(self.novas(), key=lambda n: n[2]) if n[2] // DAY_MS == d],
                # The real cursor is the last word's at~key; an offset does here.
                "next": str(after + self.timelapse_page) if len(rows) > after + self.timelapse_page else None,
            }
        elif month:
            first, last = month_hours(int(month[1]))
            counts = Counter(e[6] // HOUR_MS for e in self.entries if first <= e[6] // HOUR_MS < last)
            world = Counter(e[6] // HOUR_MS for e in self.entries if first <= e[6] // HOUR_MS < last and in_world(e))
            body = {"month": int(month[1]), "hours": [[h, n, world[h]] for h, n in sorted(counts.items())]}
        elif top or top_hours:
            # Over UTC days, or over UTC hours for a day or an hour in the page's time zone.
            unit = DAY_MS if top else HOUR_MS
            first, last = int((top or top_hours)[1]), int((top or top_hours)[2])
            rows = [e for e in self.entries if first <= e[6] // unit < last]
            surveyors = Counter(e[5] for e in rows if e[5])
            # Hidden words only, by territory; a hidden word's theme is its territory's.
            places = Counter((e[1] // 48, e[2] // 48) for e in rows if e[4] == 0)
            theme_of = {(e[1] // 48, e[2] // 48): e[7] for e in rows if e[4] == 0}
            themes = Counter()
            for place, n in places.items():
                themes[theme_of[place]] += n
            body = {
                "from": first, "to": last, "hidden": sum(places.values()), **({"hours": True} if top_hours else {}),
                "surveyors": [[i, n] for i, n in sorted(surveyors.items(), key=lambda r: (-r[1], r[0]))[:10]],
                "territories": [
                    [rx, ry, self.places.get(f"{rx},{ry}", f"Place {rx},{ry}"), theme_of[(rx, ry)], n]
                    for (rx, ry), n in sorted(places.items(), key=lambda r: (-r[1], r[0][1], r[0][0]))[:10]
                ],
                "themes": [
                    [th, *self.themes.get(th, [f"Theme {th}", 200]), n]
                    for th, n in sorted(themes.items(), key=lambda r: (-r[1], r[0]))
                ],
                "guilds": [
                    [g, *self.guilds[g], n]
                    for g, n in sorted(Counter(guild_of(e) for e in rows if guild_of(e) in self.guilds).items(), key=lambda r: (-r[1], r[0]))[:10]
                ],
            }
        elif sliced:
            kind, key, first, last, before = sliced[1], sliced[2], int(sliced[3]), int(sliced[4]), int(sliced[5] or 0)
            if kind == "theme" and int(key) not in self.themes:
                route.fulfill(status=400, headers=headers, body=json.dumps({"error": "no such theme"}))
                return
            mine = {
                "surveyor": lambda e: e[5] == key,
                "guild": lambda e: guild_of(e) == key,
                "theme": lambda e: e[4] == 0 and e[7] == int(key),
            }[kind]
            rows = [e for e in self.entries if mine(e) and first <= e[6] // HOUR_MS < last]
            counts = Counter(e[6] // HOUR_MS for e in rows)
            world = Counter(e[6] // HOUR_MS for e in rows if in_world(e))
            body = {
                "kind": kind, "key": int(key) if kind == "theme" else key, "from": first, "to": last,
                "words": len(rows), "world": sum(world.values()),
                "hours": [[h, n, world[h]] for h, n in sorted(counts.items())],
                **self.tops(rows, kind),
                **self.page_of(list(reversed(rows)), before, self.slice_page),
            }
            if kind == "theme":
                body["name"], body["hue"] = self.themes[int(key)]
            if kind == "guild":
                body["name"], body["hue"] = self.guilds.get(key, [None, None])
        elif novas and self.fail_novas:
            route.fulfill(status=503, headers=headers, body=json.dumps({"error": "server error"}))
            return
        elif novas:
            first, last, before = int(novas[1]), int(novas[2]), int(novas[3] or 0)
            rows = [n for n in self.novas() if first <= n[2] // HOUR_MS < last]
            counts = Counter(n[2] // HOUR_MS for n in rows)
            part = rows[before : before + self.slice_page]
            body = {
                "from": first, "to": last, "count": len(rows), "hours": [[h, n] for h, n in sorted(counts.items())],
                "novas": part,
                "places": {f"{n[0]},{n[1]}": self.places[f"{n[0]},{n[1]}"] for n in part if f"{n[0]},{n[1]}" in self.places},
                "themes": {str(n[13]): self.themes[n[13]] for n in part if n[13] in self.themes},
                # The real cursor is the last one's at~rx~ry; an offset does here.
                "next": str(before + self.slice_page) if len(rows) > before + self.slice_page else None,
            }
        elif territory:
            rx, ry = int(territory[1]), int(territory[2])
            rows = [e for e in reversed(self.entries) if (e[1] // 48, e[2] // 48) == (rx, ry)]
            th = next((e[7] for e in rows if e[4] == 0), (rx + 15 * ry) % 225)
            body = {
                "rx": rx, "ry": ry, "name": self.places.get(f"{rx},{ry}", f"Place {rx},{ry}"), "th": th,
                "total": self.totals.get(f"{rx},{ry}", 112), "charted": sum(1 for e in rows if e[4] == 0),
                "topSurveyors": self.tops(rows, "theme")["topSurveyors"],
                "nova": next((n for n in self.novas() if (n[0], n[1]) == (rx, ry)), None),
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
                "entries": [e[:8] for e in rows],
                "places": {rx(e): self.places[rx(e)] for e in rows if rx(e) in self.places},
                "themes": {str(e[7]): self.themes[e[7]] for e in rows if e[7] in self.themes},
                # The real cursor is the last entry's at~key; an offset does here.
                "next": str(after + self.page) if more else None,
            }
        else:
            route.fulfill(status=404, headers=headers, body=json.dumps({"error": "not found"}))
            return
        route.fulfill(status=200, headers=headers, body=json.dumps(body))

    def novas(self):
        """Every supernova, newest first: [rx, ry, at, w, x, y, d, initials, first, words, surveyors, top, topN, th]."""
        out = []
        for place, total in self.totals.items():
            rx, ry = (int(v) for v in place.split(","))
            hidden = [e for e in self.entries if e[4] == 0 and (e[1] // 48, e[2] // 48) == (rx, ry)][:total]
            if len(hidden) < total:
                continue
            last = hidden[-1]
            people = Counter(e[5] for e in hidden if e[5])
            top, top_n = min(people.items(), key=lambda r: (-r[1], r[0]), default=("", 0))
            out.append([rx, ry, last[6], last[0], last[1], last[2], last[3], last[5], hidden[0][6], total, len(people), top, top_n, last[7]])
        return sorted(out, key=lambda n: (-n[2], -n[0], -n[1]))

    def page_of(self, rows, start, size):
        """A page of entries from `start`, with the names they need and an offset for the next."""
        part = rows[start : start + size]
        place = lambda e: f"{e[1] // 48},{e[2] // 48}"
        return {
            "entries": [e[:8] for e in part],
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
        if kind in ("surveyor", "guild"):
            themes = Counter()
            for place, n in places.items():
                themes[theme_of[place]] += n
            out["topThemes"] = [
                [th, *self.themes.get(th, [f"Theme {th}", 200]), n] for th, n in sorted(themes.items(), key=lambda r: (-r[1], r[0]))
            ]
        if kind != "surveyor":
            people = Counter(e[5] for e in rows if e[5])
            out["topSurveyors"] = [[i, n] for i, n in sorted(people.items(), key=lambda r: (-r[1], r[0]))[:10]]
        return out
