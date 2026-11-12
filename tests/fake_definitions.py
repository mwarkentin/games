"""A fake of the Worker's definitions for Letterfield (worker/src/define.js).

The game reads the Worker's address from DEFINE_URL, or from ?define=, so
tests point it at DEFINE_API and route GET /v1/define/<WORD>/<th> here. The
real Worker is tested in worker/test/define.test.js.
"""

from __future__ import annotations

import json
import re

from playwright.sync_api import Route

DEFINE_API = "https://define.test"
PATH = re.compile(r"/v1/define/([A-Z]+)/(\d+)$")


class FakeDefinitions:
    """Answers every word with `senses`, or with `answers[word]` if it's given.

    An answer is a list of senses ({"pos", "text"}; [] for none) or a bare
    status number, like 503 for Wikimedia being busy. `asked` lists every
    word asked for, as "WORD/th". With `holding`, requests wait in `held`
    until answer() or release() (see Held in fake_leaderboard.py).
    """

    def __init__(self, senses=None, answers=None):
        self.senses = senses if senses is not None else [{"pos": "noun", "text": "A thing you found."}]
        self.answers = dict(answers or {})
        self.asked: list[str] = []
        self.holding = False
        self.held: list[Route] = []

    def handle(self, route: Route) -> None:
        if self.holding:
            self.held.append(route)
            return
        self.reply(route)

    def reply(self, route: Route) -> None:
        m = PATH.search(route.request.url)
        headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
        if not m:
            route.fulfill(status=404, headers=headers, body='{"error":"not found"}')
            return
        word, th = m.group(1), m.group(2)
        self.asked.append(f"{word}/{th}")
        answer = self.answers.get(word, self.senses)
        if isinstance(answer, int):
            route.fulfill(status=answer, headers=headers, body='{"error":"try again later"}')
            return
        body = {
            "word": word,
            "senses": answer,
            "source": "wiktionary" if answer else None,
            "title": word.lower() if answer else None,
            "url": f"https://en.wiktionary.org/wiki/{word.lower()}#English" if answer else None,
        }
        route.fulfill(status=200, headers=headers, body=json.dumps(body))

    def answer(self, index: int = 0) -> None:
        """Answer one held request, the oldest unless `index` says otherwise."""
        self.reply(self.held.pop(index))
