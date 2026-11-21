"""Everything that isn't a static figure: the interactive explainers, the clips and the game screens.

Each has the same parts as a figure in figures.py (a post, a title, a caption, alt text and the facts it
states with their sources), so README.md and FACTS.md list them from here, the same way.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Extra:
    id: str
    kind: str  # "explainer", "clip" or "screen"
    post: str
    title: str
    files: str  # where render.py or capture.py writes it, under _architecture/
    caption: str
    alt: str
    facts: list[tuple[str, str]]


EXTRAS: list[Extra] = [
    Extra(
        "sectors",
        "explainer",
        "server",
        "Sectors and sockets",
        "explainers/sectors.html (to embed) · artifacts/sectors.html (as published)",
        "Drag the map and watch the game join the four sectors nearest the middle of the screen, and leave one "
        "four seconds after it drops out of view; change the screen and the zoom to see why a wide screen far out "
        "still joins only four. Switch to a supernova and tap a territory: its sector tells the 3, 5 or 8 "
        "neighbours with a territory within three of it at once, and the Atlas passes the news to every other "
        "sector in the universe with their next report.",
        "An interactive map of the sectors around the origin, each a 4 by 4 block of territory tiles, with a "
        "rectangle for the screen. The joined sectors are outlined and a panel lists each one's state: connecting, "
        "live or leaving. In supernova mode, dots stand for surveyors: those within three territories of the "
        "burst see it, the rest of the universe a distant wave, and those outside it nothing until they visit.",
        [
            ("A sector is 4 × 4 territories, 192 × 192 cells", "worker/src/survey.js (SECTOR = RC × TERR)"),
            (
                "The game joins at most 4 sectors, those in view nearest the middle of the screen, and leaves one 4 s "
                "after it's out of view",
                "letterfield.html (sectorsInView, syncSurvey, SECTOR_LINKS)",
            ),
            (
                "The universe is sectors −12 to 12 each way, 625 of them, hiding 1,119,752 words",
                "worker/src/survey.js (AREA, AREA_WORDS); recounted with the generator",
            ),
            (
                "A supernova tells the 3, 5 or 8 sectors with a territory within 3 of it",
                "worker/src/survey.js (novaNeighbours, NOVA_REACH)",
            ),
            (
                "The Atlas keeps supernovas for sectors to pass on for 2 minutes, at most 64",
                "worker/src/survey.js (RELAY_MS, RELAY_MAX)",
            ),
            (
                "Elsewhere in the universe a supernova plays as a distant wave if it's under 20 s old",
                "letterfield.html (NOVA_LATE)",
            ),
            ("Letters, and circling words, start at 9 pixels a cell", "letterfield.html (LETTER_MIN)"),
            ("The 46 surveyors in supernova mode are made up, placed by a seeded random", "explainers/sectors.html"),
        ],
    ),  # fmt: skip
    Extra(
        "claim",
        "explainer",
        "claims",
        "The life of a claim",
        "explainers/claim.html (to embed) · artifacts/claim.html (as published)",
        "Sixteen steps from circling PURIM in Menorah Hollow to the survey log, with KIM circling the same word "
        "a moment after ZED. The claim waits in the game's outbox, goes out on the socket that's already open, "
        "passes the sector's checks (message size and rate, claims per socket, claims per address, today's cap, "
        "the map itself), and the insert decides the race. Turn the race off, or start with the sector "
        "hibernating to see what a woken object has to work out again.",
        "A step-through diagram. Along the top, ZED's and KIM's phones and everyone else in the sector, each with "
        "the real letters around PURIM. Below, sector 0,0 with its six checks as rows, ending in the insert and the "
        "row kept in the sector. To the right, the Atlas, the log's alarm, D1 and the survey log. A token for each "
        "claim moves down through the checks, answers fly back to the phones, and a caption under the stage "
        "explains each step with the message or code it involves.",
        [
            (
                "PURIM is a hidden word at cell 5,5 reading up and to the right (d 7), in Menorah Hollow, a Festivals "
                "territory with 113 hidden words",
                "worker/src/letterfield-world.js, through data.mjs",
            ),
            (
                "The game sends 4 claims at once to a sector, then one every 1.6 s, and rejoins if one isn't answered in 15 s",
                "letterfield.html (CLAIM_BURST, CLAIM_REFILL_MS, CLAIM_ANSWER_MS)",
            ),
            (
                "Messages over 256 characters, or past 20 at once (then 10 a second), are dropped unread",
                "worker/src/survey.js (MAX_MESSAGE, FRAME_BURST, FRAME_REFILL_MS)",
            ),
            (
                "A socket can claim 5 at once, then one every 1.5 s",
                "worker/src/survey.js (CLAIM_BURST, CLAIM_REFILL_MS)",
            ),
            (
                "An address can claim 6 a minute across every sector; 'slow down' sends the claim back to the queue for a minute",
                "worker/wrangler.toml (SURVEY_CLAIMS); letterfield.html (claimRefused)",
            ),
            (
                "An address can chart 300 words a UTC day in the universe; a woken sector asks the Atlas before the first claim",
                "worker/src/survey.js (DAILY_CLAIMS, heardDay, ask)",
            ),
            (
                "checkClaim: in the word list, starts in this sector, every letter there, hidden or a bonus word of 6+ letters",
                "worker/src/survey.js (checkClaim, STRAY_MIN)",
            ),
            (
                "The insert is INSERT … ON CONFLICT (key) DO NOTHING RETURNING key, with nothing awaited",
                "worker/src/survey.js (Sector.claim)",
            ),
            (
                "'claimed' goes to every socket, at once after a lull, otherwise batched for at most 200 ms; 'taken' to the loser",
                "worker/src/survey.js (sendBatch, BATCH_MS)",
            ),
            (
                "Each claimer with a player id gets a signed receipt",
                "worker/src/survey.js (receipt); worker/src/achievements.js (signFind)",
            ),
            (
                "Reports go to the Atlas at most every 10 s, with the next message",
                "worker/src/survey.js (maybeReport, REPORT_MS)",
            ),
            (
                "An alarm copies up to 240 claims to D1 within 30 s; bonus words stay out of the public log",
                "worker/src/survey.js (logSoon, flushLog); worker/src/survey-log.js (LOG_MS, LOG_BATCH)",
            ),
            (
                "D1 inserts with INSERT OR IGNORE and triggers add to the hour's, surveyor's and territory's counts",
                "worker/src/survey-log.js (writeLog); worker/migrations-log/0002_survey_log_counts.sql",
            ),
            (
                "Log answers are cached 15 s while their hour runs, and a day once it ended an hour ago",
                "worker/src/survey-log.js (LIVE_CACHE_S, SETTLED_MS, SETTLED_CACHE_S)",
            ),
            ("ZED, KIM and the order they arrive in are made up", "explainers/claim.html"),
        ],
    ),  # fmt: skip
    Extra(
        "cost",
        "explainer",
        "cost",
        "What the survey costs",
        "explainers/cost.html (to embed) · artifacts/cost.html (as published)",
        "Choose how many surveyors are online at once, for how many hours a day and days a month, and see the "
        "month's bill on Workers Paid, in its four parts, and when the free plan's daily Durable Object requests "
        "would run out. The curve shows the bill for every crowd up to the survey's cap of 25,000 at once.",
        "A calculator. On the left, four example scenarios, three sliders and the month's total in large type, "
        "with its four parts and a note on the free plan. On the right, a stacked area chart of the month's bill "
        "against surveyors online, on a log scale from 1 to 25,000, with the chosen number marked and a dashed line "
        "where the free plan runs out; a table of the same numbers folds out below it.",
        [
            (
                "Per player-hour: about 30 Worker requests, 106 Durable Object requests and 0.35 GB-s",
                "worker/SURVEY.md ('Cost')",
            ),
            (
                "Workers Paid: $5 a month with 10 M requests, then $0.30 per million; Durable Objects 1 M, then $0.15 per "
                "million; 400,000 GB-s, then $12.50 per million",
                "worker/SURVEY.md ('Cost'), from Cloudflare's published prices",
            ),
            (
                "Workers Free: 100,000 Durable Object requests a day, about 943 player-hours",
                "worker/SURVEY.md ('Why Workers Paid')",
            ),
            ("At most 25,000 online at once, about $0.73 an hour", "worker/src/survey.js (MAX_ONLINE); this model"),
            ("1,000 people for 2 hours a day for a month: $5.80", "this model; worker/SURVEY.md says about $6"),
            (
                "A viral fortnight, 5,000 online for 14 days: about $46",
                "this model; worker/SURVEY.md says about $57 (see the notes below)",
            ),
        ],
    ),  # fmt: skip
    Extra(
        "claim-clip",
        "clip",
        "claims",
        "The claim race, played through",
        "clips/claim.mp4 · clips/claim.gif",
        "The claim explainer playing through in 37 seconds: ZED and KIM circle PURIM moments apart, both claims "
        "pass the sector's checks, ZED's insert lands first and KIM's gets 'taken', and ZED's word goes on to "
        "the log.",
        "A screen recording of the claim diagram stepping through sixteen steps: tokens move down the sector's "
        "checks, answers fly back to the two phones, and the caption under it changes at each step.",
        [
            (
                "Recorded from the explainer, a frame at a time with its clock stopped, at 25 frames a second",
                "capture.py",
            )
        ],
    ),  # fmt: skip
    Extra(
        "supernova-clip",
        "clip",
        "supernova",
        "Menorah Hollow goes supernova",
        "clips/supernova.mp4 · clips/supernova.gif",
        "Menorah Hollow going supernova in the game, played alone with all but one of its 113 hidden words "
        "found: the last find, light drawing in for 2.6 seconds, the burst, and the shockwave shoving the letters "
        "as it rolls out, then the note that it's kept in the field notes. Captured a frame at a time from the "
        "game itself.",
        "A green-tinted grid of letters with many words circled. Light gathers at the territory's middle, bursts "
        "into sparks and a white flash, and a ring rolls outward pushing the letters aside, before the map settles "
        "and a note in the corner says Menorah Hollow is kept in the field notes.",
        [
            ("Charge 2.6 s, then the shockwave for 3.4 s", "letterfield.html (NOVA_CHARGE, NOVA_WAVE)"),
            ("Played alone, the last hidden word found sets the territory off", "letterfield.html (collect)"),
            ("Recorded at 30 frames a second with the page's clock stopped between frames", "capture.py"),
        ],
    ),  # fmt: skip
    Extra(
        "far-view",
        "screen",
        "map",
        "The map from far away",
        "screens/far-view-light.png · -dark.png",
        "Zoomed all the way out, at 2 pixels a cell, the game draws each territory as a tile with its name and "
        "theme; the letters come back from 9 pixels a cell. Words charted on the survey show as dots.",
        "A grid of tinted tiles, each labelled with a made-up place name and its theme, such as Menorah Hollow, "
        "Festivals, and Swordtail Vale, Pet Shop. Tiles near the middle are speckled with dots for charted words.",
        [
            (
                "The game zooms from 2 to 80 pixels a cell; letters show from 9",
                "letterfield.html (ZMIN, ZMAX, LETTER_MIN)",
            ),
            ("Territory names and themes are the generator's", "letterfield.html (regionName, regionTheme)"),
            ("The charted words, and who charted them, are made up", "capture.py"),
        ],
    ),  # fmt: skip
    Extra(
        "universe",
        "screen",
        "server",
        "The Universe map",
        "screens/universe-light.png · -dark.png",
        "The Universe map, in the field notes: the shared universe's 100 × 100 territories shaded by how much of "
        "each is charted, and dots where people are. Its counts are the live survey's public totals on November "
        "20, 2026; the crowds are made up.",
        "The game's map at its farthest zoom on the left. On the right, the field notes with the box 'Universe "
        "charted, 907 of 1.1M' open, showing a dark square map with a few marks near its middle.",
        [
            ("The universe is 100 × 100 territories around the origin", "worker/src/survey.js (AREA)"),
            (
                "907 of 1,119,752 words charted on November 20, 2026",
                "GET /v1/survey/world, read once into data/survey.json",
            ),
            ("The Atlas rebuilds and caches the world map for 5 s", "worker/src/survey.js (VIEW_MS)"),
        ],
    ),  # fmt: skip
    Extra(
        "surveyors",
        "screen",
        "server",
        "The surveyors",
        "screens/surveyors-light.png · -dark.png",
        "The list of surveyors, nearest first, each with the territory they're in, how far away it is, whether "
        "they're active, and a button to wave. Everyone on it is made up.",
        "The game's map close up, with words circled, and on the right a drawer titled Surveyors: you, ZED, at the "
        "top, then eleven others with coloured initials, each with a territory, a distance, active or idle, and a "
        "Wave button.",
        [
            (
                "The list comes from the Atlas, through GET /v1/survey/surveyors, 40 a page",
                "worker/src/survey-social.js",
            ),
            (
                "Emotes are a fixed set; nothing anyone else sees is free text",
                "AGENTS.md; worker/SURVEY.md ('Surveyors and emotes')",
            ),
        ],
    ),  # fmt: skip
    Extra(
        "supernova-screens",
        "screen",
        "supernova",
        "The burst, and the shockwave",
        "screens/supernova-burst-light.png · -dark.png · supernova-wave-light.png · -dark.png",
        "Menorah Hollow a moment after it bursts, and a second later, as the shockwave rolls out across the map "
        "and swells the letters it passes.",
        "Two frames of the game. In the first, a glowing white and green sphere fills the middle of the map with "
        "sparks flying out. In the second, a pale ring spreads across a grid of circled words, the letters inside "
        "it pushed and enlarged.",
        [("3.05 s and 3.95 s after the last word, at 2×", "capture.py; letterfield.html (supernova)")],
    ),  # fmt: skip
    Extra(
        "field-notes",
        "screen",
        "devices",
        "The field notes",
        "screens/field-notes-light.png · -dark.png",
        "The field notes after Menorah Hollow went supernova: the supernova kept at the top of the day, then each "
        "find with its territory, the bearing it reads in, the time, a book for its meaning and a share button. "
        "Linked devices keep these notes in step.",
        "The game's map on the left and the Field Notes drawer on the right: totals of 113 words in 1 territory, "
        "an achievements row, filters, and a list headed Menorah Hollow, Festivals, with a Supernova entry and "
        "then words like Occasion, Valentine and Jubilee with times.",
        [
            (
                "Finds, supernovas and achievements sync between linked devices through a Player object",
                "worker/src/players.js; worker/SURVEY.md ('Syncing linked devices')",
            )
        ],
    ),  # fmt: skip
    Extra(
        "log-screens",
        "screen",
        "log",
        "The survey log",
        "screens/log-week-light.png · -dark.png · log-day-light.png · -dark.png",
        "The survey log's week and one of its days: words charted, the busiest day or hour, a note when a "
        "territory went supernova, and the top lists of surveyors and territories. Made-up surveyors charting "
        "real words from the map.",
        "The Survey Log page: tabs for everyone, mine and supernovas; periods from day to all time; a bar chart of "
        "words charted; a note that Menorah Hollow went supernova; and top lists of surveyors and territories.",
        [
            (
                "Its numbers come from D1's count tables, kept by triggers",
                "worker/migrations-log/0002_survey_log_counts.sql",
            ),
            ("The words are the generator's; the surveyors and times are made up", "capture.py (survey_history)"),
        ],
    ),  # fmt: skip
    Extra(
        "timelapse",
        "screen",
        "log",
        "The timelapse",
        "screens/timelapse-light.png · -dark.png",
        "The timelapse replaying the survey from its log, each charted word a stroke in its territory's colour, "
        "paused just after Menorah Hollow, in the middle, went supernova.",
        "A map of territory squares filled with short coloured strokes, the middle one full and glowing, under "
        "the heading Fri, Nov 20 and counts of 650 words charted, 1 supernova and 20 territories, with play "
        "controls and speeds below.",
        [
            (
                "Replayed from GET /v1/survey/log/timelapse and its days, a settled day cached for a year",
                "worker/src/survey-log.js",
            )
        ],
    ),  # fmt: skip
]
