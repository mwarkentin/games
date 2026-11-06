"""Checks yesterday's numbers from Letterfield's shared survey for signs of bots.

.github/workflows/survey-watch.yml runs this once a day. It reads the
public world map from the Worker (GET /v1/survey/world, which the game
reads too) and prints a Markdown note when yesterday looks like a pool of
addresses at work; the workflow opens or updates an issue with it. When
nothing's wrong, or the survey can't be reached, it prints nothing. See
"Limits per address" in worker/SURVEY.md, and worker/TURNSTILE.md for what
to do about it.

    python3 scripts/survey_watch.py [world.json]
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

WORLD_URL = "https://games-leaderboard.mwarkentin.workers.dev/v1/survey/world"

# One address at the daily cap is a keen player or a single script; this
# many in a day is a pool of addresses, which is what Turnstile is for.
CAPPED_ALERT = 20
# People chart about a word a minute at most. Bots that claim without saying
# where they are add words but no player-hours, so the rate climbs far past it.
RATE_ALERT = 120
RATE_MIN_WORDS = 500  # too few words to judge a rate by


def check(world: dict) -> list[str]:
    """Reasons yesterday looks like bots, or none."""
    day = world.get("yesterday") if isinstance(world, dict) else None
    today = world.get("today") if isinstance(world, dict) else None
    if not isinstance(day, dict):
        return []
    # Only the day just gone: an older one has been checked already.
    if isinstance(today, dict) and day.get("day") != today.get("day", 0) - 1:
        return []
    reasons = []
    capped, charted, hours = day.get("capped", 0), day.get("charted", 0), day.get("playerHours", 0)
    if capped >= CAPPED_ALERT:
        reasons.append(f"{capped:,} addresses reached the daily cap of charted words (alert at {CAPPED_ALERT}).")
    if charted >= RATE_MIN_WORDS:
        if not hours:
            reasons.append(f"{charted:,} words were charted with nobody online to chart them.")
        elif charted / hours >= RATE_ALERT:
            reasons.append(
                f"{charted:,} words were charted in {hours:,} player-hours: {charted / hours:,.0f} an hour each "
                f"(alert at {RATE_ALERT}; people manage about 60)."
            )
    return reasons


def note(world: dict, reasons: list[str]) -> str:
    day = world["yesterday"]
    lines = [f"Yesterday's numbers from Letterfield's shared survey (UTC day {day.get('day')}) look like bots:", ""]
    lines += [f"- {r}" for r in reasons]
    lines += [
        "",
        "| words charted | addresses charting | at the daily cap | player-hours |",
        "| --- | --- | --- | --- |",
        f"| {day.get('charted', 0):,} | {day.get('addresses', 0):,} | {day.get('capped', 0):,} | {day.get('playerHours', 0):,} |",
        "",
        "If it keeps up, see `worker/TURNSTILE.md` for switching on the Turnstile check.",
    ]
    return "\n".join(lines) + "\n"


def fetch(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "games-survey-watch"}), timeout=20) as r:
            return json.load(r)
    except (OSError, ValueError) as e:
        print(f"::warning::Couldn't read the survey's world map: {e}", file=sys.stderr)
        return None


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        with open(argv[1], encoding="utf-8") as f:
            world = json.load(f)
    else:
        world = fetch(os.environ.get("SURVEY_WORLD_URL", WORLD_URL))
    reasons = check(world) if world else []
    if reasons:
        sys.stdout.write(note(world, reasons))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
