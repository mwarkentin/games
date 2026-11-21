# Fact-check notes

Every fact each figure, explainer, clip and screen states, and where it
comes from. The list at the end is written by `render.py` from `figures.py`
and `extras.py`, so it stays with the figures; the notes before it are by
hand.

## How the facts were checked

- Numbers, names and limits come from the code, read for this: the Worker
  (`worker/src/`, `worker/wrangler.toml`, its migrations), the game
  (`letterfield.html`) and its pages, the share Worker and the workflows.
- Letters, words, territories, themes and totals come from the map itself:
  `data.mjs` runs the Worker's copy of the game's generator, so each one is
  what the game draws and the survey checks.
- Where the docs and the code disagree, the figures follow the code (below).
- Live numbers (907 words charted, the Universe map's counts, 8 supernovas)
  are the public survey's at 23:35 UTC on November 20, 2026, from GETs the
  survey log makes itself (`/v1/survey/world` and `/v1/survey/log/…`), kept
  in `data/survey.json` without anyone's initials.
- Letterfield's history is `main`'s first-parent log, in
  `data/history.json`: the 78 pull requests that touched Letterfield's files
  in its first 24 days, and the lines of its own code at each (its pages,
  its Worker modules and its tests).
- Costs are worked out from SURVEY.md's use per player-hour and
  Cloudflare's published prices, the same way in the figure and the
  calculator.

## What's made up

- Every surveyor and their id: ZED, KIM, SIS, ABE, JOY, REX and the others.
  No real person's initials appear anywhere.
- Timings in the race (KIM "a moment later"), the crowds, carets and idle
  times, and when the screens' words were charted.
- The 46 surveyors in the sectors explainer's supernova mode.

## Where the docs and the code disagree

1. `worker/TURNSTILE.md` ("Where it stands") says the survey, and so
   Turnstile, stays off on the live site until `SURVEY_URL` is set.
   `SURVEY_URL` is set (`letterfield.html`, line 1083), and the survey is
   live.
2. `worker/SURVEY.md` (line 1313) says a territory hides 102 to 122 words.
   Across the universe's 10,000 territories the generator gives 100 to 123:
   112 on average, 1,119,752 in all.
3. `worker/SURVEY.md`'s cost table (line 1776) puts Durable Object time in
   an eieio-style viral fortnight at about $12.50, for about $57 in all. At
   its own 0.35 GB-s per player-hour, 1.68 million player-hours are 588,000
   GB-s: $2.35 past the 400,000 included, or $7.35 with none included, so
   the fortnight comes to about $46. The cost figure and the calculator use
   $2.35.
4. `worker/src/players.js` (line 194, `MARKS_MAX`) says the achievements
   catalog has 39. It has 40.
5. The comment before `STRAY_MIN` (`worker/src/letterfield-world.js`,
   line 23, and `letterfield.html`, line 1073) says the word list has some
   17,700 words. `VOCAB` has 28,845.
6. `share/README.md`'s step 5, "Switch it on", is done: `SHARE_URL` is set
   (`letterfield.html`, line 1087).

SURVEY.md's "about 20" bonus words a territory holds up: over 60
territories sampled across the universe, 21 on average and 20 at the
median, and 532 at four letters or more against its "some 530".

## Every fact, by post

<!-- BEGIN FACTS -->
### 1. An endless word search from one seed

#### A map from a seed

| Fact | Source |
| --- | --- |
| SEED = 0x1E77E2; CH = 12 cells a chunk; RG = 4 chunks a territory; RC = 48 cells a territory | worker/src/letterfield-world.js; letterfield.html World constants |
| A territory's theme is (rx + 15·ry) mod 225 (LAT_B = 15, 225 themes) | letterfield-world.js regionTheme |
| Each chunk is dealt the next DEAL = 9 cards of its territory's shuffled deck, and places them in order until it has its target of 6 + floor(r() × 3), i.e. 6 to 8 | letterfield-world.js genChunk, deckOf |
| Direction weights [3, 2, 3, 1, 1, 1, 1, 2] of 14 for E, SE, S, SW, W, NW, N, NE; up to 40 tries a word; a word may cross another where letters agree, but not lie wholly on one | letterfield-world.js genChunk |
| Filler letters are drawn from 'AEIOUNRSTL' plus the chunk's placed words | letterfield-world.js genChunk |
| Bonus words (strays) count from STRAY_MIN = 6 letters | letterfield-world.js STRAY_MIN |
| About 21 bonus words a territory at 6+ letters (median 20) and 532 at 4+ (median 535), over 60 territories sampled across the universe with the Worker's generator; SURVEY.md says about 20 and some 530 | docs/architecture/data.mjs; worker/SURVEY.md |
| Chunk (0, 0) is in Menorah Hollow (Festivals, hue 90) and hides TRADITION, WREATH, DIWALI, YULETIDE, NAVRATRI, RAMADAN and PURIM | node docs/architecture/data.mjs chunk 0 0 |
| Theme sizes 144 to 184 words; 28,845 different words | letterfield-world.js THEME_DATA (counted) |
| checkClaim: the word is in VOCAB, its start cell is in this sector, every letter matches letterAt(), and it is one of its chunk's placed words or at least 6 letters long | worker/src/survey.js checkClaim |
| A test runs the game's generator and the Worker's copy and compares them | worker/test/survey.test.js |

#### 225 themes, laid out so neighbours differ

| Fact | Source |
| --- | --- |
| 225 themes; territory (rx, ry) has theme (rx + 15·ry) mod 225 | letterfield-world.js regionTheme, LAT_B |
| A theme comes round again only 15 territories away; each needs a 15 × 15 square to itself | worker/SURVEY.md, 'A new map' |
| The order of themes was searched (bench/layout.mjs) so the eight neighbours differ by 30° of hue or more, in kind (no two bird themes side by side), and share no words | worker/SURVEY.md; worker/bench/layout.mjs |
| Festivals (theme 0) is at (0, 0), (0, -15), (-15, 1) and (-15, -14) within -15..14 | computed with regionTheme |
| The origin's neighbours and names: Cater Shallows, Pennette Steppe, Danger Court, Hafnium Basin, Menorah Hollow, Swordtail Vale, Caress Gate, Sodden Wold, Cimabue Meadows | letterfield-world.js regionName |
| A word can be in up to three themes: 24,170 words are in one theme, 3,972 in two, 703 in three | worker/SURVEY.md; counted from THEME_DATA |

#### The map from far away

| Fact | Source |
| --- | --- |
| The game zooms from 2 to 80 pixels a cell; letters show from 9 | letterfield.html (ZMIN, ZMAX, LETTER_MIN) |
| Territory names and themes are the generator's | letterfield.html (regionName, regionTheme) |
| The charted words, and who charted them, are made up | capture.py |

### 2. A Durable Object for every patch of the map

#### The universe, cut into sectors

| Fact | Source |
| --- | --- |
| The universe is sectors -12 to 12 each way (AREA = 12): 625 sectors, 100 × 100 territories, territories -48 to 51 | worker/src/survey.js AREA; worker/src/achievements.js UNIVERSE_EDGE |
| It hides 1,119,752 words (AREA_WORDS), recounted by a test | worker/src/survey.js; recounted with data.mjs |
| A sector is 4 × 4 territories, 192 × 192 cells (SECTOR = RC × TERR) | worker/src/survey.js SECTOR |
| The game's map runs to ±1e9 cells (LIMIT) | worker/src/survey.js LIMIT |
| 907 of 1,119,752 charted and 24 territories with charted words in the universe on 20 Nov 2026 at 23:35 UTC; 8 supernovas in the log, 7 inside the universe | GET /v1/survey/world, /v1/survey/log/novas (data/survey.json) |
| Sectors outside the universe don't report to the Atlas, so their words don't count toward its total | worker/src/survey.js maybeReport, inArea; worker/SURVEY.md |

#### The big picture

| Fact | Source |
| --- | --- |
| The survey's Durable Object classes: Sector and Atlas (v2), Guild (v3) and Player (v4), all SQLite-backed | worker/wrangler.toml [[migrations]] |
| Two D1 databases: games-survey-log (binding LOG_DB), and games-leaderboard (binding DB), where Letterfield keeps its definitions, link codes and recovery codes | worker/wrangler.toml [[d1_databases]] |
| Rate-limit bindings: SURVEY_CLAIMS 6/60 s, SURVEY_JOINS 120/60 s, SURVEY_EMOTES 20/60 s, DEFINE_LOOKUPS 20/60 s | worker/wrangler.toml [[ratelimits]] |
| The router hands each path to its handler: the survey, surveyors, guilds, links, players, recovery, badges, the log and definitions | worker/src/index.js fetch() |
| 625 sectors in the universe: sectors -12 to 12 each way (AREA = 12) | worker/src/survey.js AREA |
| The share Worker binds Sector and Atlas from games-leaderboard and the Worker itself as LOG, and keeps cards in R2 (games-share-cards) | share/wrangler.toml |
| The game is one file, letterfield.html: 8,248 lines at commit 44fe976 (PR #126) | wc -l letterfield.html |
| Turnstile passes are handed out but not required (TURNSTILE_REQUIRED = "false") | worker/wrangler.toml [vars]; worker/TURNSTILE.md |
| Definitions come from Wiktionary or Wikipedia once per word and are kept in D1 | worker/src/define.js |

#### Inside one sector

| Fact | Source |
| --- | --- |
| MAX_PLAYERS = 750 sockets a sector; ADDRESS_SOCKETS = 40 from one address | worker/src/survey.js |
| Tables: claims (key PRIMARY KEY, w, x, y, d, s, initials, at, guild) WITHOUT ROWID with claims_by_time (at, key); logged; novas (PK rx, ry); relayed; owed; guild_names; map | worker/src/survey.js Sector constructor |
| First claim wins with INSERT … ON CONFLICT (key) DO NOTHING RETURNING key, run with nothing awaited | worker/src/survey.js Sector.claim |
| Hibernation API; players kept in memory too, positions written to the attachment at most every 5 s (SAVE_POS_MS) | worker/src/survey.js; worker/SURVEY.md 'Attachments are expensive' |
| Claims go out in batches at most every 200 ms (BATCH_MS); positions at most once a second (PRESENCE_MS), up to 64 (PRESENCE_MAX) with a head count | worker/src/survey.js |
| A presence timer only when someone leaves a sector with fewer than 32 sockets (QUIET) | worker/src/survey.js |
| The log alarm: LOG_MS = 30 s; retries back off up to 10 minutes | worker/src/survey-log.js; survey.js alarm() |
| Hidden words per territory worked out from the map in about 3 ms, once per waking | worker/src/survey.js hiddenCounts |
| Messages in: me, pos, claim, here, emote; out: hello, claimed, taken, signed, error, presence, emote, emoted, guild, world, nova, full | worker/src/survey.js header comment |

#### Presence, and the Atlas

| Fact | Source |
| --- | --- |
| REPORT_MS = 10 s; a sector reports at least every REFRESH_MS = 50 s while messages arrive, and at once when a listed player leaves | worker/src/survey.js; worker/src/survey-social.js |
| Report fields: sx, sy, players, perAddress, charted (16), hot, day, overAt, novaSeq, who, tags, by, unpassed, novas | worker/src/survey.js toAtlas, report |
| The Atlas answers with totals, day, overAt, the over-cap list when it changed (latest 2,000), guilds online and supernovas since novaSeq | worker/src/survey.js Atlas.fetch |
| The Atlas writes charted counts to storage at most once a minute (SAVE_MS), and a sector's at once when its last player leaves | worker/src/survey.js Atlas.save |
| World map: each Worker instance asks the Atlas at most every 5 s (VIEW_MS); browsers cache 5 s; about 10 KB, a byte per territory | worker/src/survey.js worldMap; SURVEY.md |
| Surveyor list: a snapshot at most every LIST_MS = 10 s; pages of 40 nearest, up to 1,000; the game asks every 20 s while open | worker/src/survey-social.js; letterfield.html WHO_REFRESH_MS |
| Positions: at most once a second, up to 64 (with each address's latest mover first past that) plus a head count | worker/src/survey.js sendPresence |
| Sectors round positions to territories before reporting; the Atlas never has cells | worker/SURVEY.md 'Privacy' |
| An address counts for at most ADDRESS_ONLINE = 40 toward MAX_ONLINE = 25,000 | worker/src/survey.js |

#### What One Million Checkboxes taught

| Fact | Source |
| --- | --- |
| The table's rows and figures | worker/SURVEY.md 'What eieio's games teach, and where it shows up here' |
| OMCB's state was a 125 KB bitset; the universe's would be 137 KB (1,119,752 bits) | worker/SURVEY.md |
| Batching 'took a sector from saturating at ~630 players to handling 750' | worker/SURVEY.md |
| OMCB cost about $850; One Million Chessboards 'a few hundred dollars' | worker/SURVEY.md 'Cost' |
| Sources: eieio.games/blog/scaling-one-million-checkboxes and eieio.games/blog/a-million-realtime-chess-boards-in-a-single-process | worker/SURVEY.md links |

#### Sectors and sockets

| Fact | Source |
| --- | --- |
| A sector is 4 × 4 territories, 192 × 192 cells | worker/src/survey.js (SECTOR = RC × TERR) |
| The game joins at most 4 sectors, those in view nearest the middle of the screen, and leaves one 4 s after it's out of view | letterfield.html (sectorsInView, syncSurvey, SECTOR_LINKS) |
| The universe is sectors −12 to 12 each way, 625 of them, hiding 1,119,752 words | worker/src/survey.js (AREA, AREA_WORDS); recounted with the generator |
| A supernova tells the 3, 5 or 8 sectors with a territory within 3 of it | worker/src/survey.js (novaNeighbours, NOVA_REACH) |
| The Atlas keeps supernovas for sectors to pass on for 2 minutes, at most 64 | worker/src/survey.js (RELAY_MS, RELAY_MAX) |
| Elsewhere in the universe a supernova plays as a distant wave if it's under 20 s old | letterfield.html (NOVA_LATE) |
| Letters, and circling words, start at 9 pixels a cell | letterfield.html (LETTER_MIN) |
| The 46 surveyors in supernova mode are made up, placed by a seeded random | explainers/sectors.html |

#### The Universe map

| Fact | Source |
| --- | --- |
| The universe is 100 × 100 territories around the origin | worker/src/survey.js (AREA) |
| 907 of 1,119,752 words charted on November 20, 2026 | GET /v1/survey/world, read once into data/survey.json |
| The Atlas rebuilds and caches the world map for 5 s | worker/src/survey.js (VIEW_MS) |

#### The surveyors

| Fact | Source |
| --- | --- |
| The list comes from the Atlas, through GET /v1/survey/surveyors, 40 a page | worker/src/survey-social.js |
| Emotes are a fixed set; nothing anyone else sees is free text | AGENTS.md; worker/SURVEY.md ('Surveyors and emotes') |

### 3. The life of a claim

#### The life of a claim, and a race

| Fact | Source |
| --- | --- |
| Frames: FRAME_BURST = 20, then one per FRAME_REFILL_MS = 100 ms; dropped unread past that | worker/src/survey.js webSocketMessage |
| Claims per socket: CLAIM_BURST = 5, then one per CLAIM_REFILL_MS = 1,500 ms ('slow down') | worker/src/survey.js claim |
| Claims per address: SURVEY_CLAIMS, 6 a minute, approximate per Cloudflare location | worker/wrangler.toml |
| Daily cap: DAILY_CLAIMS = 300 per address per UTC day in the universe; a sector that hasn't heard the list since waking asks the Atlas first ('daily limit') | worker/src/survey.js claim, ask, heard |
| checkClaim against the generator, then INSERT … ON CONFLICT (key) DO NOTHING; the loser gets {t: 'taken', c} | worker/src/survey.js claim |
| A claim's time is always after the sector's previous claim (claimTime) | worker/src/survey.js |
| 'claimed' frames are batched for up to 200 ms and broadcast to every socket in the sector | worker/src/survey.js sendBatch |
| A receipt {t: 'signed', k, r} follows for a claimer with a player id: f if first, z if it set off a supernova, and an HMAC | worker/src/survey.js receipt; worker/ACHIEVEMENTS.md |
| The game keeps a little inside the sector's limit: 4 at once, then one per 1.6 s; claims wait in an outbox, kept in localStorage, and a word always stays in the notes | letterfield.html CLAIM_MOVES, flushClaims |
| The log alarm fires at most LOG_MS = 30 s after a claim and writes up to 240 claims in one D1 batch | worker/src/survey.js logSoon, flushLog; survey-log.js |

#### Defence in depth

| Fact | Source |
| --- | --- |
| Turnstile passes last an hour, are an HMAC over the address hash and expiry, and are not required (TURNSTILE_REQUIRED = "false") | worker/src/survey-pass.js; worker/wrangler.toml |
| Solver services sell Turnstile tokens for roughly $0.80 to $3 per 1,000 (third-party comparisons) | worker/TURNSTILE.md 'How much it stops' |
| Addresses are hashed with IP_SALT, IPv6 by its /64, and never stored | worker/src/leaderboard.js addressOf, hashAddress |
| Joins: SURVEY_JOINS 120 a minute per address, counted before a sector is woken | worker/src/survey.js routeSurvey |
| 40 sockets per address per sector; an address counts for at most 40 toward MAX_ONLINE = 25,000 | worker/src/survey.js ADDRESS_SOCKETS, ADDRESS_ONLINE |
| Messages: 20 at once, then 10 a second, the rest dropped unread | worker/src/survey.js FRAME_BURST |
| Claims: 5 at once then 1 per 1.5 s per socket; 6 a minute per address (approximate, per location) | worker/src/survey.js; worker/wrangler.toml |
| Daily cap: 300 words a UTC day per address in the universe, counted by the Atlas from reports; one address would take about 10 years to chart the world; 3,700 addresses could do it in a day | worker/SURVEY.md 'Limits per address'; worker/TURNSTILE.md |
| Sectors outside the universe don't report, so their words aren't capped (only 6 a minute) | worker/SURVEY.md |
| 32 blocked initials; seven emote drawings; guild names from three fixed lists of 16 words | worker/src/leaderboard.js BLOCKED_INITIALS; survey-social.js EMOTES; survey-guild.js |
| Receipts, badges and cards are HMAC-SHA256 cut to 72 bits, keys from IP_SALT | worker/src/achievements.js |
| The bot watch opens an issue on ≥ 20 addresses at the cap, ≥ 120 words per player-hour over ≥ 500 words, or ≥ 500 joins without a pass and ≥ 5 per player-hour | worker/SURVEY.md 'Watching for bots' |

#### The life of a claim

| Fact | Source |
| --- | --- |
| PURIM is a hidden word at cell 5,5 reading up and to the right (d 7), in Menorah Hollow, a Festivals territory with 113 hidden words | worker/src/letterfield-world.js, through data.mjs |
| The game sends 4 claims at once to a sector, then one every 1.6 s, and rejoins if one isn't answered in 15 s | letterfield.html (CLAIM_BURST, CLAIM_REFILL_MS, CLAIM_ANSWER_MS) |
| Messages over 256 characters, or past 20 at once (then 10 a second), are dropped unread | worker/src/survey.js (MAX_MESSAGE, FRAME_BURST, FRAME_REFILL_MS) |
| A socket can claim 5 at once, then one every 1.5 s | worker/src/survey.js (CLAIM_BURST, CLAIM_REFILL_MS) |
| An address can claim 6 a minute across every sector; 'slow down' sends the claim back to the queue for a minute | worker/wrangler.toml (SURVEY_CLAIMS); letterfield.html (claimRefused) |
| An address can chart 300 words a UTC day in the universe; a woken sector asks the Atlas before the first claim | worker/src/survey.js (DAILY_CLAIMS, heardDay, ask) |
| checkClaim: in the word list, starts in this sector, every letter there, hidden or a bonus word of 6+ letters | worker/src/survey.js (checkClaim, STRAY_MIN) |
| The insert is INSERT … ON CONFLICT (key) DO NOTHING RETURNING key, with nothing awaited | worker/src/survey.js (Sector.claim) |
| 'claimed' goes to every socket, at once after a lull, otherwise batched for at most 200 ms; 'taken' to the loser | worker/src/survey.js (sendBatch, BATCH_MS) |
| Each claimer with a player id gets a signed receipt | worker/src/survey.js (receipt); worker/src/achievements.js (signFind) |
| Reports go to the Atlas at most every 10 s, with the next message | worker/src/survey.js (maybeReport, REPORT_MS) |
| An alarm copies up to 240 claims to D1 within 30 s; bonus words stay out of the public log | worker/src/survey.js (logSoon, flushLog); worker/src/survey-log.js (LOG_MS, LOG_BATCH) |
| D1 inserts with INSERT OR IGNORE and triggers add to the hour's, surveyor's and territory's counts | worker/src/survey-log.js (writeLog); worker/migrations-log/0002_survey_log_counts.sql |
| Log answers are cached 15 s while their hour runs, and a day once it ended an hour ago | worker/src/survey-log.js (LIVE_CACHE_S, SETTLED_MS, SETTLED_CACHE_S) |
| ZED, KIM and the order they arrive in are made up | explainers/claim.html |

#### The claim race, played through

| Fact | Source |
| --- | --- |
| Recorded from the explainer, a frame at a time with its clock stopped, at 25 frames a second | capture.py |

### 4. Supernovas: news that travels

#### A supernova, from the last word to the shockwave

| Fact | Source |
| --- | --- |
| Recorded by the sector in the same step as the claim that completed the territory, ON CONFLICT DO NOTHING, before anything is awaited | worker/src/survey.js Sector.supernova, claim |
| Neighbours within NOVA_REACH = 3 territories (the larger of the two distances): 3 for a corner territory, 5 for an edge, 8 for the middle four | worker/src/survey.js novaNeighbours |
| Neighbours hear by an internal POST /near inside ctx.waitUntil, and check it (checkNova) before passing {t: 'nova'} on | worker/src/survey.js passOn, near, checkNova |
| To the Atlas at once, or NOVA_REPORT_MS = 1 s after the last report; it checks the word and the report's counts, then relays for RELAY_MS = 2 minutes, at most RELAY_MAX = 64 | worker/src/survey.js |
| To the log in the alarm's batch, never before its last word is in D1 | worker/src/survey.js flushLog |
| In the game: NOVA_CHARGE = 2,600 ms, NOVA_WAVE = 3,400 ms; further than 3 territories, a wave only, DISTANT_WAVE = 2,400 ms, at most once a minute and only under 20 s old | letterfield.html Supernova |
| 8 supernovas in the log by 20 Nov 2026; the quickest took 5.3 hours from first word to last, the slowest 135.9; 108 to 116 hidden words each | GET /v1/survey/log/novas (data/survey.json) |
| Territories hide 100 to 123 hidden words (SURVEY.md says 'about 112, from 102 to 122') | counted with the Worker's generator over all 10,000 territories |

#### Menorah Hollow goes supernova

| Fact | Source |
| --- | --- |
| Charge 2.6 s, then the shockwave for 3.4 s | letterfield.html (NOVA_CHARGE, NOVA_WAVE) |
| Played alone, the last hidden word found sets the territory off | letterfield.html (collect) |
| Recorded at 30 frames a second with the page's clock stopped between frames | capture.py |

#### The burst, and the shockwave

| Fact | Source |
| --- | --- |
| 3.05 s and 3.95 s after the last word, at 2× | capture.py; letterfield.html (supernova) |

### 5. Every word, in D1

#### The log: from a sector's claims to a cached answer

| Fact | Source |
| --- | --- |
| LOG_MS = 30 s; LOG_BATCH = 240 claims; 11 rows to an INSERT (9 values a row, D1 binds at most 100); one D1 batch is one transaction | worker/src/survey-log.js; worker/SURVEY.md |
| The mark moves only after D1 answers; failures retry after 1, 2, 4… minutes, up to 10 (LOG_RETRY_MAX_MS) | worker/src/survey.js alarm, flushLog |
| Bonus words aren't copied to the log (the mark still moves past them) | worker/src/survey.js flushLog; migrations-log/0009 |
| survey_log (at, key, w, x, y, d, s, initials, guild) WITHOUT ROWID, PRIMARY KEY (at, key); INSERT OR IGNORE | worker/migrations-log/0001, 0007 |
| Virtual columns rx, ry and th = ((rx + 15·ry) % 225 + 225) % 225; indexes by initials, territory, theme (hidden only) and guild | worker/migrations-log/0003, 0005, 0007 |
| Triggers keep survey_log_hours, _surveyors, _territories and _guild_days; a skipped duplicate fires none | worker/migrations-log/0002, 0007, 0011 |
| Up to seven D1 rows written per word, two more in a guild | worker/SURVEY.md 'Cost' under 'The log' |
| Caches: each instance's memory (300 answers, 8 million characters), the Cache API keyed by host and map version, and Cache-Control | worker/src/survey-log.js |
| TTLs: running 15 s (LIVE_CACHE_S); settled (ended ≥ 1 h ago) a day; running ranges over 2 days 2 min, top lists 10 min; settled timelapse days a year, immutable | worker/src/survey-log.js |

#### The survey log

| Fact | Source |
| --- | --- |
| Its numbers come from D1's count tables, kept by triggers | worker/migrations-log/0002_survey_log_counts.sql |
| The words are the generator's; the surveyors and times are made up | capture.py (survey_history) |

#### The timelapse

| Fact | Source |
| --- | --- |
| Replayed from GET /v1/survey/log/timelapse and its days, a settled day cached for a year | worker/src/survey-log.js |

### 6. One surveyor, many devices

#### One surveyor on every device

| Fact | Source |
| --- | --- |
| The token is 32 hex digits (128 bits), kept as games.player; the player id is the first 12 hex digits (48 bits) of SHA-256('games-player:' + token) | worker/src/survey-social.js playerId, TOKEN, PID |
| Link codes: 8 characters from a 31-letter alphabet (852 billion), 10 minutes (LINK_MS), one use; making codes 10 an hour and tries 20 an hour per address | worker/src/players.js; worker/src/leaderboard.js LIMITS |
| One UPDATE … WHERE used = 0 … RETURNING redeems a code, and what it carried is wiped | worker/SURVEY.md |
| The making device polls /status every 5 s; anyone else hears 'gone' | letterfield.html LINK_POLL_MS; players.js |
| Recovery codes: 20 characters (about 99 bits); SHA-512('games-recovery:' + code): first half the row id, second half an AES-GCM key sealing the token; 5 new codes an hour | worker/src/players.js recoveryKeys |
| Player sync: rows carry their version; epoch restarts after a forget; limits 25,000 finds, 1,000 supernovas, 2,000 a sync, one sync every 2 s, 512 KB | worker/src/players.js |
| Merge rules: f only comes on, b until it's yours, a receipt stays; marks keep the earliest time and 'in play' over 'from notes'; best only goes up; settings by newest clock | worker/src/players.js mergedFind, mergedMark; worker/SURVEY.md |
| A Player nobody syncs for 180 days deletes itself, unless a recovery code is saved | worker/src/players.js KEEP_MS, alarm |
| Syncs on opening, a few seconds after a find, after a settings change, back in view, and every minute | worker/SURVEY.md; letterfield.html SYNC_EVERY_MS, SYNC_SOON_MS |

#### Who is who: every name the survey uses

| Fact | Source |
| --- | --- |
| Token 32 hex; player id 12 hex = 48 bits of SHA-256 | worker/src/survey-social.js TOKEN, PID, playerId |
| Addresses hashed with IP_SALT, IPv6 by /64, handed to sectors in X-Survey-Address, which the Worker sets | worker/src/leaderboard.js; worker/src/survey.js routeSurvey |
| Initials: three letters A–Z; 32 blocked combinations | worker/src/leaderboard.js INITIALS, BLOCKED_INITIALS |
| Guild code 6 characters (887 million), tag 8 hex, log id 10 hex | worker/src/survey-social.js; SURVEY.md |
| Link code 8 characters (852 billion), 10 minutes, once; recovery code 20 characters, about 99 bits | worker/src/players.js |
| Receipts, badges and cards: HMAC-SHA256 cut to 72 bits, keys from IP_SALT per use | worker/src/achievements.js |
| Turnstile pass: expiry + HMAC of address hash and expiry, an hour, key derived from TURNSTILE_SECRET | worker/src/survey-pass.js |

#### The field notes

| Fact | Source |
| --- | --- |
| Finds, supernovas and achievements sync between linked devices through a Player object | worker/src/players.js; worker/SURVEY.md ('Syncing linked devices') |

### 7. What it costs, and how far it goes

#### What the survey costs, by players online

| Fact | Source |
| --- | --- |
| Per player-hour: ~30 Worker requests, ~106 Durable Object requests, ~0.35 GB-s | worker/SURVEY.md 'Cost' |
| Workers Paid: $5 a month with 10 M requests, then $0.30 per million; Durable Objects: 1 M requests, then $0.15 per million, incoming WebSocket messages at 1/20 of a request, outgoing free; 400,000 GB-s, then $12.50 per million | worker/SURVEY.md 'Cost' (published prices) |
| Ceiling at MAX_ONLINE = 25,000: ~$0.22/h Worker requests, ~$0.40/h DO requests, ~$0.11/h DO time, at most ~$0.75 an hour (~$18 a day); this chart's model gives $0.73 | worker/SURVEY.md; monthly_bill() here |
| 1,000 players 2 hours a day for a month: about $6 | worker/SURVEY.md (and this model: $5.80) |
| Free plan: 100,000 Durable Object requests a day, enough for ~940 player-hours; every Durable Object stops until 00:00 UTC past it | worker/SURVEY.md 'Why Workers Paid' |
| The surveyor list and emotes add about $1.50 a day at 10,000 online, guilds about $0.30; not in the curve | worker/SURVEY.md |
| The first version, with timers, would have cost ~$0.0056 per busy sector-hour: ~$84 a day for 625 busy sectors | worker/SURVEY.md |

#### How much one sector holds

| Fact | Source |
| --- | --- |
| Load test: positions every ~2 s, a random hidden word every 20–40 s, players connecting at 40 a second, wrangler dev on a shared 4-core sandbox | worker/SURVEY.md 'Measured on the Workers runtime' |
| Each row's p50 / p95 / p99, connected count and sector CPU | worker/SURVEY.md table |
| MAX_PLAYERS = 750 ('one sector saturates between 750 and 1,000') | worker/src/survey.js |
| Our own code takes about 3 ms of work per second for 1,000 players in Node; the rest is the runtime's per-message work | worker/SURVEY.md; worker/bench/sector.js |
| Batching claims: 'took a sector from saturating at ~630 players to handling 750' | worker/SURVEY.md |

#### What the survey costs

| Fact | Source |
| --- | --- |
| Per player-hour: about 30 Worker requests, 106 Durable Object requests and 0.35 GB-s | worker/SURVEY.md ('Cost') |
| Workers Paid: $5 a month with 10 M requests, then $0.30 per million; Durable Objects 1 M, then $0.15 per million; 400,000 GB-s, then $12.50 per million | worker/SURVEY.md ('Cost'), from Cloudflare's published prices |
| Workers Free: 100,000 Durable Object requests a day, about 943 player-hours | worker/SURVEY.md ('Why Workers Paid') |
| At most 25,000 online at once, about $0.73 an hour | worker/src/survey.js (MAX_ONLINE); this model |
| 1,000 people for 2 hours a day for a month: $5.80 | this model; worker/SURVEY.md says about $6 |
| A viral fortnight, 5,000 online for 14 days: about $46 | this model; worker/SURVEY.md says about $57 (see the notes below) |

### 8. How it was built

#### 78 pull requests in 24 days

| Fact | Source |
| --- | --- |
| 78 pull requests merged to main between 28 October and 20 November 2026 touched Letterfield's files | git log --first-parent origin/main, each merge's changed files (render.py LETTERFIELD) |
| None of Letterfield's files changed on main except through a pull request | git log --first-parent origin/main |
| 73 of the 78 came from claude/ branches, the ones Claude Code sessions push to; the other five (#99, #100, #104, #106, #109) from branches named otherwise | the pull requests' head branches on GitHub |
| Every pull request got a preview of the site and the Worker from 7 November (#34, itself one of Letterfield's): 11 merged before it and 66 after | .github/workflows/preview.yml, added in 159010d |
| Line counts at each merge: letterfield.html; letterfield-log, -timelapse and -soundtrack.html; Letterfield's Worker modules (survey*.js, letterfield-world.js, players.js, achievements.js, define.js); its tests (tests/test_letterfield*, test_survey_watch, its fakes, and worker/test for those modules) | git show at each merge (data/history.json) |
| At 20 November: game 8,248 lines; pages 3,813; Worker code 4,401; tests 18,178 | data/history.json |
| The most Letterfield pull requests in a day: 14, on 10 November | data/history.json |
| Milestones: #1 Letterfield, #7 the survey explored, #26 limits per address, #30 the log, #48 state machines, #49 map 4, #58 share cards, #59 definitions, #81 timelapse, #83 CI sharded, #94 surveyors, guilds and devices, #115 achievements, #123 Lantern, #124 the album | PR titles in main's history |

#### How a change ships

| Fact | Source |
| --- | --- |
| Test: plan → pytest shards (up to 3, 4 workers each), lint, worker and share node tests → test | .github/workflows/test.yml; AGENTS.md 'Tests in parallel' |
| A pull request runs only the tests its changes need (scripts/select_tests.py); main runs them all | AGENTS.md |
| Previews: pr-<n>-games-leaderboard, pr-<n>-games-share (when share/ or worker/src/ changed) and pr-<n>-games-preview, on workers.dev, deleted when the PR closes | .github/workflows/preview.yml; AGENTS.md |
| Worker Previews take turns only when the branch brings migrations | worker/README.md 'Previews' |
| Pages: build.sh then GitHub Pages on every push to main | .github/workflows/pages.yml |
| Worker deploy on worker/** changes: d1 migrations apply (both databases), then wrangler deploy; the share Worker deploys on share/** or worker/src/** changes | .github/workflows/leaderboard.yml, share.yml |
| Survey watch at 00:23 UTC every day | .github/workflows/survey-watch.yml |
| 711 pytest functions, 422 Worker tests and 74 share Worker tests at commit 44fe976 | counted with grep |
| About 20 minutes one test at a time; CI sharding took it to about 3 | AGENTS.md; PR #83 |

<!-- END FACTS -->
