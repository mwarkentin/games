# Letterfield's shared survey

What Letterfield could look like as a massively multiplayer game in the
spirit of [eieio.games](https://eieio.games/) (One Million Checkboxes, One
Million Chessboards), and whether Cloudflare Workers and D1 can carry it.
It's built and switched on:
- the server: `src/survey.js`, on the leaderboard Worker
- the map, shared with the game: `src/letterfield-world.js`
- the survey code in `letterfield.html`, which joins the Worker at
  `SURVEY_URL`

Its history is a page of its own, `letterfield-log.html` (see "The log").

## One Million Words

Letterfield already gives every player the same map, because every letter
comes from a fixed seed. The middle of that map, 100×100 territories around
the origin, hides **1,120,206 words**. The shared survey turns them into one
job for everyone: chart them all.

- **The first player to circle a word charts it.** Everyone else sees it
  outlined in its territory's colour; hovering it says who got there first
  ("Charted first by SIS · 3m ago"). You can still circle it for your own
  field notes, and the game tells you who beat you to it.
- **One number for the whole world.** The header shows "412,883 of
  1,120,206 charted", and it ticks up as words are charted nearby. The
  current territory has its own count ("83/120 charted"), and a territory
  goes supernova when its last hidden word is charted.
- **You can see the crowd.** Each other player is a coloured caret, like a
  collaborator's cursor, in the gap beside the letter in the middle of their
  screen. No names sit on the letters: hovering a caret shows their
  initials, and carets fade once a player has been idle for 20 seconds.
- **A world map.** It's in the notes panel: territories ink in as they're
  charted, dots show where people are, and tapping it flies you there.
- **New players land in the crowd.** You start in the middle of the busiest
  crowd that still has room. eieio found that players need to see "so many
  people" the moment they arrive; One Million Chessboards spread newcomers
  into small clusters and lost that moment. "The middle" is the median of
  where the crowd's players are looking. An earlier version used the latest
  claim, and a single straggler in the crowd's sector could pull newcomers
  100 cells away from everyone.
- **It fails gracefully.**
  - Field notes stay personal and still work offline.
  - If the server can't be reached, the notes panel says so in one line and
    the game carries on.
  - When a sector is full, or the whole survey is, the panel says that
    instead.

## What eieio's games teach, and where it shows up here

From [Scaling One Million Checkboxes][omcb] and
[Running a million-board chess MMO in a single process][chess]:

| eieio | here |
| --- | --- |
| OMCB's state was a 125 KB bitset: one bit per box | the shared world's state would be a 137 KB bitset: one bit per hidden word (claims are stored with initials for now; see "Not done yet") |
| Chessboards sent each player only moves in the 3×3 zones (50×50 tiles each) around them | sectors (192×192 cells); a player joins the ≤4 sectors in view |
| Moves went out in batches every 200 ms; batching "massively reduced load" | claims go out in batches every 200 ms. In the load test, this took a sector from saturating at ~630 players to handling 750 |
| Global data (players online) was served over HTTP with a low max-age so Cloudflare's cache absorbed it: "hundreds of millions of requests" | the world map is a `GET` with `max-age=5`, cached per Worker instance; the Atlas that builds it hears only from sectors, never from players |
| Bandwidth was "my one unbounded cost" (OMCB capped its server at 250 Mbit/s) | Cloudflare doesn't charge for egress, and outgoing WebSocket messages are free |
| "Bound my costs … instead of going serverless and scaling into bankruptcy" | `MAX_PLAYERS` per sector and `MAX_ONLINE` overall. Beyond them, players are told the survey is full; the bill can't run away |
| Validate everything: someone checked box 100,000,000 and broke OMCB | every claim is checked against the server's copy of the map generator |
| Bots pushed absurd traffic once the Go rewrite made things fast | a burst of 5 claims per socket, then one per 1.5 s; and per IP address, however many sockets it opens, 6 a minute and 300 a day (see "Limits per address") |
| Rollback netcode, so moves feel instant | not needed: a circled word is always kept locally, and the server only decides who gets the credit |
| One Go process on one box (16 cores, never above ~10% CPU, later shrunk to an ~$80/month box) | a Durable Object is one JavaScript thread, so the world is split by place into many objects |

## How it works

```
 browser ──wss──▶ Worker ──▶ Durable Object "sector 0,0"  (SQLite: claims) ──report──▶ Durable Object "atlas"
    │      │            └──▶ Durable Object "sector -1,0"                  every ≤10 s     (charted counts, players)
    │      └──GET /v1/survey/world (cached 5 s) ──────────────────────────────────────────────┘
    └── joins the ≤4 sectors in view, one WebSocket each
```

- **Sectors.** The map is cut into sectors of 4×4 territories. Each sector
  is a [Durable Object][do]: a single-threaded object with its own SQLite
  storage. It holds its claims and the sockets of everyone looking at it.
  - Only one message runs inside a sector at a time, so "first to claim
    wins" is a plain `INSERT … ON CONFLICT DO NOTHING`.
  - The server checks every claim against its own copy of the generator: the
    word must really be in the grid there, and inside this sector. A test
    runs the game's generator and the copy and compares them.
- **Positions** go only to the sector under the middle of your screen, at
  most once a second, and only after you've moved at least a cell. A sector
  sends one list of positions a second (up to 64 people, plus a head count)
  however many players moved.
- **The Atlas** is one object for the shared world. Each sector in the area
  reports its charted counts, player count and the middle of its crowd at
  most every 10 s while something is changing. Reports are absolute numbers, so a lost
  or repeated report does no harm. The Atlas writes the charted counts to
  storage at most once a minute.
- **The world map** is one byte per territory (10 KB), plus players per
  sector and a starting spot for newcomers. Each Worker instance fetches it
  from the Atlas at most every 5 s, and browsers cache it for 5 s.
- **Hibernation, and why there are almost no timers.** Sectors use the
  [WebSocket Hibernation API][hib]. Cloudflare bills a Durable Object for
  wall-clock time while it's running *or while it can't hibernate*, and a
  pending `setTimeout` stops it from hibernating ([lifecycle][lifecycle]).
  - The first version held a 1 s presence timer and a 10 s report timer.
    That kept every busy sector billed every second. It also billed a sector
    with a few people circling words almost as much as a full one, because
    its report timer was nearly always pending.
  - Now owed positions, claim batches and reports go out with the next
    message that arrives once they're due. While people are moving there's
    always a next message.
  - The only timers left are short ones in quiet sectors (under 32 sockets),
    for things that might be the last to happen there: someone leaving, or a
    claim waiting in a batch.
- **Attachments are expensive.** Each socket's state lives in its
  hibernation attachment, which survives eviction. Serializing it on every
  position update and deserializing all of them for every list of positions
  was the sector's biggest cost. Players are now kept in memory too, and
  positions are written to the attachment at most every 5 s.

Messages are listed at the top of `src/survey.js`.

### Limits per address

The map comes from a fixed seed, and its generator is in the page, so a
script can find every word without playing. Per-socket limits alone don't
stop it: it can open as many sockets in as many sectors as it likes. So the
survey also limits each IP address, wherever it plays:

- **Addresses are hashed.** The Worker hashes the player's address with
  `IP_SALT`, as the leaderboard does, and hands the sector only the hash, in
  a header it sets itself. An IPv6 address counts by its /64, because a
  device can pick any address in its /64.
- **Claims: 6 a minute per address, across every sector.** That's a
  [rate-limiting binding][ratelimit] (`SURVEY_CLAIMS` in `wrangler.toml`),
  on top of each socket's own limit. A player rarely finds more than one
  word a minute, and counting over a minute rather than 10 s means a few
  spotted together still all count. The cost is to players who share an
  address: a family, a classroom, or a mobile network that puts many phones
  behind one IPv4 address share those 6 (and the daily 300 below). A refused
  claim gets the same `slow down` as a socket claiming too fast, and the
  game says "Too quick to chart · kept in your notes".
- **Words charted: 300 a day per address, in the shared world.** At 6 a
  minute, a script left running all day would still chart 8,640 words a day.
  A person charting one a minute would need five hours to reach 300. With
  the cap, one address would take about 10 years to chart the world. The
  rate-limiting binding only counts over 10 or 60 seconds, so the Atlas
  keeps this count:
  - Each sector's reports, which already go out at most every 10 s while
    words are charted, also list how many words each address charted there
    since the last report.
  - The Atlas adds these up for the UTC day. It answers with the addresses
    past the cap, the most recent 2,000, but only when that list has
    changed since the sector last heard it.
  - The sector refuses those addresses' claims with `daily limit`, and the
    game says "Today's charting limit reached · kept in your notes".
  - This costs no extra requests and adds no wait to a claim. A sector only
    learns the list with its next report, so an address can chart a few
    words past 300 before every sector knows. The 6-a-minute limit keeps
    that small.
  - The counts live only in the Atlas's memory. It's rarely evicted, since
    sectors report to it every few seconds, but if it is, the day's counts
    start again. Saving them would cost a row written per active address
    every minute.
  - Sectors outside the shared world don't report, so words charted there
    aren't capped. They don't count toward the world's total.
- **Sockets: 40 per address in a sector, and 120 new ones a minute per
  address.** A sector counts its own sockets exactly, so a few addresses
  can't fill it and lock everyone else out. A second binding
  (`SURVEY_JOINS`) counts sockets opened anywhere. A player roaming the map
  opens about 10 an hour. Either limit is answered with `full`, and the
  game tries again in a minute or so.
- **Why a binding and not a Durable Object per address.** The binding keeps
  its counts in each Cloudflare location, in memory, and answers without
  waiting for other locations to agree. So it's approximate: counts are per
  location, and a burst can slip past. That's fine for stopping one script
  racing everyone else. A Durable Object per address would be exact, but
  every claim would wait on a round trip to another object, and pay for it.
  In the load test, claims took as long with the binding as without it
  (p50 3.6 ms against 3.4 ms). If the binding fails, the sector lets the
  claim through, and the per-socket and per-sector limits still hold.
- **Not checked: whether a claim is near the player.** A claim is only
  accepted in a sector the player has a socket in, and that's about as tight
  as a distance check could be:
  - The game only lets you circle words at 9 px a cell or closer. A
    2560 px desktop window still reaches about 160 cells from its middle,
    and a 5120 px ultrawide about 285. Positions also lag up to a second,
    and go only to the sector under the middle of the view.
  - A fair radius would be around 300 cells, wider than a sector
    (192 cells).
  - A script reports its own position anyway, and flying across the map is
    normal play, so it could send a position next to each word first.

### Watching for bots

The limits slow down one address. A pool of addresses, a botnet or a
proxy service, still gets them once per address, and that's when a
Turnstile check would be worth switching on (see `TURNSTILE.md`). So the
Atlas keeps the numbers that would show one, from the reports sectors
already send it:

- **For each UTC day:**
  - words charted in the shared world;
  - how many addresses charted them;
  - how many reached the daily cap;
  - player-hours, added up from the players online at each report;
  - sockets that joined without a Turnstile pass (`unpassed`, see
    `TURNSTILE.md`), once the Worker hands out passes.
- **Where they show up:**
  - The world map (`GET /v1/survey/world`) has `today` and `yesterday`.
  - Workers Logs gets an `{survey: 'hour'}` line with each hour's words,
    player-hours and words per player-hour.
  - Workers Logs also gets an `{survey: 'daily cap'}` line whenever an
    address reaches the cap. It holds the count only, never the address.
- **What would look like a pool:**
  - Many addresses at the cap in a day. One or two is a keen player or a
    single script.
  - Far more words per player-hour than people manage. A person charts a
    word a minute at most. A bot that claims without sending positions adds
    words but no player-hours, so its rate climbs.
  - Many joins without a Turnstile pass, once the game has a site key.
    Nearly every player then has a pass, so those joins are scripts, plus
    the few players whose browsers block Turnstile.
- **Telling you:** the **Watch the survey for bots** workflow
  (`.github/workflows/survey-watch.yml`) reads the world map just after
  midnight UTC. If yesterday had 20 or more addresses at the cap, or 120 or
  more words per player-hour over at least 500 words, or (with a site key
  in `letterfield.html`) 500 or more joins without a pass and at least 5
  per player-hour, it opens an issue labelled `survey-bots`, or comments on
  the one that's open.
  `scripts/survey_watch.py` holds the thresholds. If the survey can't be
  reached, it only warns.
- **Lost on eviction:** the numbers live in the Atlas's memory, like the
  daily counts per address, so an evicted Atlas starts the day again and
  forgets yesterday.

## The log

[letterfield-log](https://games.michaelwarkentin.com/letterfield-log) is a
page of the survey's history: every word charted first, with where, by whom
(their initials) and when, by the day, week, month, year or all time, and
any hour minute by minute. Each word links to
`/letterfield#f-<word>-<x>-<y>-<d>`, which flies the game to it. "Mine"
narrows it to the words this browser charted first.

### Where the history lives: D1, copied from each sector

Sectors already keep every claim, but a log can't ask 625 objects what
happened between 2 and 3 pm. The options were:

| | for | against |
| --- | --- | --- |
| **D1, written by each sector** (chosen) | indexed SQL over the whole world; a page reads one hour with one query; `wrangler d1 execute` for moderation | one database runs one query at a time, so writes must be batched (and the log gets a database of its own) |
| D1, written through the Atlas | the Atlas already hears from busy sectors every 10 s | only sectors in the shared world report; claims held in the Atlas's memory are lost if it's evicted, so sectors would have to keep them until it confirms anyway; one more load on one object |
| a Durable Object for the log (or one per day) | no new storage product | every read is a Durable Object request to the same few objects the writes go to; a viral day of readers lands on one single-threaded object; no ad hoc queries |
| each sector's own claims, read on demand | nothing to copy | an hour or a player's finds span up to 625 objects |

D1 was ruled out above for *live* state: polling, positions, pushes. A log is
the opposite load: rows appended a few times a minute per busy sector and read
by a page that can be cached, which is what D1 is for.

**How claims get there.** Each `Sector` copies its new claims to the
`survey_log` table (`migrations-log/0001_survey_log.sql`) like an outbox:

- A claim sets a Durable Object [alarm][alarms] for `LOG_MS` (30 s) later, if
  none is set. Claims that come in before it goes off go with it. Unlike a
  timer, an alarm doesn't stop the sector hibernating, and it wakes the
  sector if it was evicted.
- The alarm reads claims made since the last one D1 has (the sector's
  `logged` mark, with an index on the claims' time) and writes up to 240 in
  one D1 batch: 12 rows to an `INSERT` (D1 binds at most 100 values to a
  statement) and one transaction for the lot. Only then does the mark move.
- **If D1 fails**, nothing is lost: the claims are still in the sector, the
  mark stays, and the alarm tries again after 1, 2, 4… minutes, up to 10.
  Workers Logs gets a `{survey: 'log failed'}` line. A write that reached D1
  but whose answer was lost is sent again; rows are keyed by `(at, key)`, so
  D1 ignores the copy.
- A claim's time is always after the sector's previous claim, even if the
  object moved to a machine whose clock is behind, so the mark can't skip
  one.
- The table is `WITHOUT ROWID` and ordered by `(at, key)`, so reading an hour
  reads just that hour's rows, and there's no other index to write: one row
  written per claim. The tests check each query's plan.

**Backfill.** None needed by hand. A sector that charted words before the log
existed has no mark, so the first time it wakes after the deploy it sends
every claim it holds, a batch a second, with their original times. Sectors
nobody visits again keep theirs until someone does. Since `SURVEY_URL` was
still empty on main when the log was built, that's only words charted by
people trying `?survey=`.

### The API

```
GET /v1/survey/log/day/<day>     (day = UTC days since 1970)
  → {"day", "hours": [24 counts, one per UTC hour], "total"}
GET /v1/survey/log/hour/<hour>   (hour = UTC hours since 1970)
GET /v1/survey/log/hour/<hour>?after=<at>~<key>
  → {"hour", "entries": [[w, x, y, d, s, initials, at, th], ...],
     "places": {"rx,ry": "Monet Hollow"}, "themes": {"th": [name, hue]},
     "next": "<at>~<key>" | null}
GET /v1/survey/log/month/<month> (month = UTC months since January 1970)
  → {"month", "hours": [[hour, words, world], ...]}   hours with none left out
GET /v1/survey/log/top/<from>/<to>   (UTC days from..to-1, at most 3,660)
  → {"from", "to", "surveyors": [[initials, words], ...10],
     "territories": [[rx, ry, name, th, words], ...10],
     "themes": [[th, name, hue, words], ...], "hidden"}
```

An hour comes oldest first, 500 entries a page; `next` is the `after` for the
next page. A day, hour or month that hasn't started is a 400. `world` counts
the hidden words in the shared world, which go toward its 1,120,206. Top
lists count hidden and stray words for surveyors, but only hidden words for
territories and themes, since a stray's theme is its word's, not its
territory's. The day endpoint is still there for older copies of the page.

**Caching.** Past hours and days don't change, but a claim can reach D1 up to
`LOG_MS` late, or later while D1 is failing. So an hour or day that ended an
hour ago (`SETTLED_MS`) is cached for a day, and the one still running for
15 seconds:

- `Cache-Control` on every answer, for browsers;
- in each Worker instance's memory (up to 300 answers), so a crowd reading
  the current hour costs one D1 query per instance every 15 s;
- in Cloudflare's cache through the Cache API. It does nothing on
  `workers.dev`, so it only starts helping once the Worker is on a custom
  domain (see the Worker's README). The cached copy has no CORS headers; each
  answer adds its own origin's.

A backfilled sector's old claims can take up to a day to appear in hours that
were already cached.

### Periods

The page has tabs for a day, a week (Monday to Sunday), a month, a year and
all time, each in the player's own time zone, with arrows to the one before
or after. Each shows three numbers (words charted, the busiest piece of the
period, and how many were hidden words in the shared world), a chart, and
then what's in it:

| period | chart | below it |
| --- | --- | --- |
| hour | a column a minute | every word, newest first |
| day | a column an hour | each hour's words, loaded as they scroll into view |
| week, month | a column a day | top surveyors, territories and themes; each day as a row |
| year | twelve month calendars, a cell a day, in four shades of one hue | the top lists; each month as a row |
| all time | a column a month, a meter of the shared world charted, and, from the second month, a line of it filling in | the top lists; each month as a row |

Tapping a column, cell or row opens the shorter period inside it, down to an
hour. The rows say what the chart says without hovering, which is the
chart's table view; hovering or focusing a column shows its number too.

**The hour, minute by minute,** opens from a day (its column, or "Minute by
minute" on an hour's heading) rather than having a tab: most hours hold a
handful of words, and a day already lists them. It's there for a busy
hour. The hour still running says Live and reloads every 20 seconds while
the page is on screen; nothing else reloads by itself.

**Counts, not rows.** A week or a year of the log itself could be a
million rows to read, and the running ones change constantly, so the longer
periods never read it. A second migration
(`migrations-log/0002_survey_log_counts.sql`) keeps three tables of running
totals, updated by triggers in the same transaction as each row of the log:

- `survey_log_hours`: words per UTC hour, and how many were hidden words in
  the shared world;
- `survey_log_surveyors`: words per UTC day per set of initials;
- `survey_log_territories`: hidden words per UTC day per territory.

`INSERT OR IGNORE` doesn't fire a trigger for a row it skips, so a resent
batch counts nothing twice, and a delete takes its word back out. The
migration fills the tables from the rows already logged, after creating the
triggers, with absolute numbers, so a word logged while it runs is counted
once either way.

The page draws every chart from hourly counts, a UTC month at a time (at
most 744 rows read for a month, whatever happened in it), and puts each hour
in the local day, week, month or year it starts in. In a time zone a half
hour off UTC, an hour that starts at 11:30 pm counts toward that day.
Top lists come from the daily tables, so they cover whole UTC days and can
run a few hours past a local week's edges; the page says which days.

"Mine" for a week or longer counts this browser's finds by when they were
found, without asking the server. It has no top lists: they'd only ever say
"you".

**Caching the counts.** A month or a top list that ended an hour ago is
cached for a day, like an hour. The running month is cached for 15 seconds,
and a running top list over more than two days for 10 minutes: it changes
slowly and reads every day's rows in its range.

### Where, readably

Coordinates mean little, so each answer names the territories its entries
are in (`places`, such as "Monet Hollow") and gives each theme's name and
hue. The Worker works these out with `regionName`, now in
`src/letterfield-world.js` beside the themes it already had (a test checks
it names every territory in the shared world as the game does). The page
holds none of the map's 40 KB of theme data.

### "Mine"

Initials are three letters anyone can type, so they can't say which words
are yours. Two ways could:

- **The finds already on the device** (chosen). The log is on the same
  origin as the game, so it reads `letterfield.finds.v2`, where the game
  marks each word a sector said you charted first (`f`). Mine is the day's
  log narrowed to those words: the page fetches only the hours that hold
  one, plus the hour either side when a find is within 10 minutes of it, in
  case the device's clock was off. Everyone's log marks yours with "you".
  Nothing about the player is sent or stored.
- **A private player token**, like War's `war:token`, sent with each claim
  and kept by the server as a hash. It would be the server's own record, so
  a lost "you were first" answer wouldn't matter. But the token would live in
  the same `localStorage` as the finds, so it reaches no further: a new
  device or a cleared browser starts again either way. It would also add a
  column to every sector's claims, a field to the protocol, and a lasting
  pseudonymous ID for every claim, which would need keeping out of the API
  just like hashed addresses and socket ids.

The token would be worth it only with a way to carry it to another device
(a sync code, say). On an iPhone the Home Screen app keeps its own storage,
so the log is in Letterfield's app (see the build below) and opens there
with the same finds.

### How the page fits the site

`letterfield-log.html` is a top-level page like a game, so it's published,
listed in the README, smoke-tested at phone and desktop sizes, cached
offline by `sw.js` and gets telemetry and analytics. It isn't a game of its
own, though: `<meta name="games:app" content="letterfield">` puts it in
Letterfield's home-screen app (`app_of` in `scripts/common.py`). It gets no
manifest, icon or preview of its own, and since `/letterfield-log` starts
with `/letterfield`, it's inside Letterfield's app scope. Letterfield's
survey panel links to it. Its `SURVEY_URL` already points at the Worker,
since it only reads; until the survey is on, the log is empty.

### Cost

On Workers Paid, per word charted: up to four D1 rows written (the log's
row, and an update each to the hour's, the surveyor's and the territory's
counts; no initials or a stray word skips one), one more row written in
the sector (its time index), and a share of an alarm. Each busy sector's
alarm runs at most every 30 s: one Durable Object request and two rows
written (the alarm and the mark).

| | whole world charted (1.12 M words) | a busy day (30,000 words) | the ceiling (all 625 sectors charting nonstop) |
| --- | --- | --- | --- |
| D1 rows written | ~4.5 M (50 M a month included) | ~120,000 | 75,000 batches an hour |
| D1 storage | ~100 MB for the log, a few MB of counts (5 GB included) | ~3 MB | |
| alarms (DO requests) | | ≤ 2,880 per busy sector | ~$0.011 an hour |
| rows written in sectors | 1.12 M + 2 per alarm | | ~$0.15 an hour past the included 50 M |
| D1 rows read | see below | | |

So the log adds nothing past the included allowances at the survey's
expected sizes, and at the ceiling raises the worst case from about $0.75 to
about $0.92 an hour. `LOG_MS` is the knob: 60 s would halve the alarm costs.
The whole world, charted, would take about 4.5 million of the 50 million D1
rows written included each month.

Reading is cheap: 25 billion D1 rows read a month are included. An hour
reads its own rows, a month at most 744, and a settled one is read about
once a day per Worker instance. Top lists read every row of their range in
the daily tables: a busy day might have a few hundred sets of initials and
a thousand territories, so a running year's list could read a few hundred
thousand rows, at most every 10 minutes per instance. If that ever shows in
the bill, the next step is a monthly level of the same counts.

On the free plan, D1 and Durable Object storage each allow 100,000 rows
written a day, so the log, with its counts (four D1 rows a word), cuts the
claims a day the free plan allows to about a quarter (see "On the free
plan").

**A database of its own.** The log lives in `games-survey-log` (the
`LOG_DB` binding, with its migrations in `migrations-log/`), not in the
leaderboard's database. A D1 database runs one query at a time, so this way
a backfill, a busy day's batches or a crowd reading today's log never
queue with score saves, and the log can be emptied or rebuilt without going
near scores. D1 bills by rows, not by database, so it costs nothing extra.
mwarkentin/infra makes it (`cloudflare.tf`). Without the binding, sectors
don't log and the log's paths aren't answered.

## Do Workers and D1 scale for this?

**Workers: yes.** They're stateless, and Cloudflare runs as many copies as
there are requests. What matters is the request count: the free plan allows
100,000 a day, and the paid plan charges $0.30 per million after 10 million
a month. WebSocket messages don't count as Worker requests; only the
connection does.

**D1: not for the live part.** It's the right home for the leaderboards: a
few writes per game, read now and then. A shared live map is a different
load ([D1 limits][d1limits]):

1. **One database handles one query at a time.** That's about 1,000
   queries a second at 1 ms each, and fewer in practice because of
   per-request overhead. Writes take "several milliseconds" because they're
   persisted to several locations. You scale D1 with many databases, not a
   bigger one.
2. **D1 can't push changes.** "Live" would mean every browser polling. 1,000
   players polling every 3 seconds is ~330 queries a second, just to hear
   "nothing new".
3. **Positions are the worst case.** They're tiny writes that matter for a
   second. 1,000 players moving every 2 seconds is 500 durable writes a
   second, more than one database sustains.
4. **The free plan runs out in minutes.** Free D1 allows 100,000 rows
   written a day, and queries fail once you pass it. Free Workers allow
   100,000 requests a day. 1,000 polling players would use up the requests
   in about 5 minutes.

**Durable Objects: yes, split by place.** They're built for this, and they
run on the same Worker:

- **The server can push.** Outgoing messages are free, and incoming
  WebSocket messages are billed as one request per 20.
- **One object has limits.** Cloudflare's soft limit is 1,000 requests a
  second per object. Its guidance is 500–750 a second with JSON parsing and
  200–500 with storage writes ([rules][rules]). That's why there's an
  object per sector, a socket cap per sector, and players spread over
  sectors.
- **D1 still fits for cross-sector boards.** A board like "most words
  charted first" would get a total from each sector every minute or so:
  one write per active sector, however many players.

### Measured on the Workers runtime

`worker/bench/load.js` runs real WebSocket players against the Worker:
- each sends a position every ~2 s;
- each circles a random hidden word every 20–40 s;
- players connect at 40 a second.

These runs used `wrangler dev`, which is Cloudflare's `workerd` runtime
running locally, on a 4-core sandbox shared with the load generator. That's
not Cloudflare's edge, so treat the numbers as relative; the next step is
running the same script against a deployment.

| players on one sector | version | connected | claim round trip p50 / p95 / p99 | positions every | sector CPU |
| --- | --- | --- | --- | --- | --- |
| 200 | first | 200 | 38 / 261 / 459 ms | 1.0 s | |
| 750 | first | 410 (stalled) | 1.2 s / 17 s / 22 s | 1.1 s | 100% |
| 750 | positions kept in memory | 630 | 0.6 s / 9.6 s / 16 s | 1.1 s | 97% |
| 750 | + claims batched | 750 | 61 / 305 / 435 ms | 1.0 s | 84% |
| 1,000 | + claims batched | 990 | 148 ms / 12 s / 25 s | 1.1 s | 98% |
| 700 | final | 700 | 3 / 124 / 195 ms | 1.0 s | 55% |
| 900 | final (cap 750) | 750, 150 turned away | 3 / 128 / 190 ms | 1.0 s | |

So one sector comfortably holds ~750 sockets, and that's where
`MAX_PLAYERS` is set. New players are sent to a crowd only while it has
fewer than 300 people placed in it, leaving room for neighbours who are
also watching that sector.

`worker/bench/sector.js` times our own code in Node: about 3 ms of work per
second for 1,000 players. So almost all of a sector's load is the runtime's
own per-message work: receiving, dispatching and sending. A Node benchmark
alone would have overstated capacity several hundredfold.

### Cost

Published Workers Paid prices ([Workers][wpricing],
[Durable Objects][dopricing]):
- **Workers:** $5 a month, including 10 M requests, then $0.30 per million;
  no egress fees.
- **Durable Objects:** 1 M requests included, then $0.15 per million (each
  incoming WebSocket message counts as 1/20 of a request; outgoing messages
  are free).
- **Durable Object time:** 400,000 GB-s included, then $12.50 per million
  GB-s, billed at 128 MB per object.
- **SQLite storage:** 50 M rows written included, then $1 per million.

Usage per player-hour, from the design and the 700-player run:

| | per player-hour | how |
| --- | --- | --- |
| Worker requests | ~30 | ~10 connections as you roam, plus world map reads |
| Durable Object requests | ~106 | 10 connections + ~1,900 incoming messages ÷ 20 |
| Durable Object time | ~0.35 GB-s | ~0.8 ms of sector time per player per second, with no timers keeping it awake |
| Rows written | ≤ words charted | a claim is one row, and the world has ~1.1 M words to claim |

| scenario | player-hours | Worker requests | DO requests | DO time | total with the $5 plan |
| --- | --- | --- | --- | --- | --- |
| 1,000 players, 2 hours a day, for a month | 60,000 | included | ~$0.80 | included | **~$6** |
| an eieio-style viral fortnight: 5,000 online on average, up to the cap | 1.68 M | ~$12 | ~$27 | ~$12.50 | **~$57** |
| the ceiling: `MAX_ONLINE` (25,000) online all the time | 25,000 an hour | ~$0.22/h | ~$0.40/h | ~$0.11/h | **at most ~$0.75 an hour (~$18 a day)** |

The per-address limits don't change these figures. A rate-limiting binding
isn't a Durable Object, so it adds no Durable Object requests, and neither
pricing page lists a charge for it. The hashed address is worked out once
per connection, in the Worker. The daily cap rides on the reports sectors
already send the Atlas: they grow by one entry per address that charted
something in the last 10 s or so.

For comparison, OMCB cost about $850 to run, on 8 VMs, Redis and bandwidth.
One Million Chessboards cost "a few hundred dollars": a $450/month box,
later $80/month, plus about a terabyte of traffic a month. On Cloudflare,
the survey costs the $5 plan when nobody is playing.

The first version, with timers, would have been billed for every second
every busy sector existed: ~$0.0056 per sector-hour. That's ~$84 a day for
625 busy sectors, before counting the quiet ones.

### Why Workers Paid

The account moved to Workers Paid for the survey. On Workers Free, every
limit is per day, shared by the whole account (the leaderboards and War's
rooms included), and reset at 00:00 UTC. Past a limit, requests fail rather
than cost money ([Durable Objects][dopricing], [Workers][wpricing]):

| free plan, per day | allowance | survey use per player-hour | enough for |
| --- | --- | --- | --- |
| Durable Object requests | 100,000 | ~106 | **~940 player-hours** |
| Worker requests | 100,000 | ~30 | ~3,300 player-hours |
| Durable Object time | 13,000 GB-s | ~0.35 GB-s | ~37,000 player-hours |
| SQLite rows written | 100,000 | ≤ words charted | 100,000 claims |

So on Free, Durable Object requests would run out first, at about 940
player-hours a day: 100 people playing for 9 hours, or 450 for 2. Every
Durable Object on the account would then stop answering until midnight UTC,
War's rooms included. On Paid, a day that busy every day of the month costs
about 30 cents over the included million requests.

## Not done yet

- **A spending alert.** Workers Paid has no spending cap; `MAX_ONLINE`
  keeps the worst case near $18 a day. A scheduled check of Cloudflare's
  analytics API could open a GitHub issue when the month's usage passes a
  threshold.
- **Run `load.js` against a deployment.** That would confirm the per-sector
  limit and the 0.8 ms per player-second on Cloudflare's edge rather than a
  sandbox.
- **Bots from many addresses.** Each address is limited (see "Limits per
  address"), but a botnet or a pool of proxies still gets those limits once
  per address. "Watching for bots" says when it's happening. A
  [Turnstile][turnstile] check before joining is built and switched off:
  [TURNSTILE.md](TURNSTILE.md) covers how it works, what it costs and how
  much it stops (scripts and cheap proxies, not a bot that pays a solver
  service), and how to switch it on in steps. It needs a widget and secret
  made in mwarkentin/infra.
- **Smaller snapshots.** Hidden words are deterministic, so a claim could
  be one bit in its chunk's word list. A fully charted sector's snapshot
  would shrink from 68 KB to a few hundred bytes plus initials. eieio
  measured protobuf + zstd at about 30 times smaller than uncompressed JSON.
- **Edge caching.** The world map is cached per Worker instance. On a
  custom domain, Cloudflare's cache could serve it as chessboards did.
- **Zoomed-out views** only show live claims from the four nearest sectors.
  A cached per-sector snapshot could fill in the rest of the screen.
- **The log, live, beyond the hour.** The running hour reloads every 20
  seconds; a running day, week or longer shows what it had when opened. It
  could take claims from the sector sockets the game already uses.
- **The log's words by initials or by territory.** Top lists count both,
  but listing a surveyor's or a territory's words would need an index on
  the log, so a row written per claim more.
- **Finds made offline stay personal.** Uploading them later would let
  anyone backdate a pile of claims at once.

## Trying it

```sh
cd worker
npx wrangler@4.151.0 dev --port 8787     # the Worker and its Durable Objects, locally
node bench/load.js http://127.0.0.1:8787 300 30   # 300 players for 30 s
```

Each player in `load.js` sends its own `CF-Connecting-IP`, so the limits per
address don't turn them away. Only `wrangler dev` believes that header:
Cloudflare's edge sets it itself, so the same trick can't get round the
limits on the real Worker.

To play, serve the games from the repo root (`python3 -m http.server 8000`)
and open `http://localhost:8000/letterfield.html?survey=http://localhost:8787`
in a few windows. The deploy workflow's `wrangler deploy` creates the
`Sector` and `Atlas` classes from the migration in `wrangler.toml`, and
`SURVEY_URL` in `letterfield.html` points the live game at the deployed
Worker.

To try the log's weeks, months and years without weeks of play,
`bench/seed-log.js` prints made-up history (real words at their real places,
over the last 45 days by default) as SQL for a test database:

```sh
node worker/bench/seed-log.js 45 > /tmp/seed.sql
cd worker
npx wrangler@4.151.0 d1 execute games-survey-log --local --file /tmp/seed.sql   # with wrangler dev
npx wrangler@4.151.0 d1 execute games-survey-log-previews --remote \
  --config wrangler.previews-migrations.toml --file /tmp/seed.sql             # every Worker Preview's log
```

Never point it at `games-survey-log` with `--remote`: that's the real log.

[omcb]: https://eieio.games/blog/scaling-one-million-checkboxes
[chess]: https://eieio.games/blog/a-million-realtime-chess-boards-in-a-single-process
[do]: https://developers.cloudflare.com/durable-objects/
[hib]: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
[lifecycle]: https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/
[rules]: https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/
[d1limits]: https://developers.cloudflare.com/d1/platform/limits/
[wpricing]: https://developers.cloudflare.com/workers/platform/pricing/
[dopricing]: https://developers.cloudflare.com/durable-objects/platform/pricing/
[ratelimit]: https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
[turnstile]: https://developers.cloudflare.com/turnstile/
[alarms]: https://developers.cloudflare.com/durable-objects/api/alarms/
