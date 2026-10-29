# Letterfield's shared survey

What Letterfield could look like as a massively multiplayer game in the
spirit of [eieio.games](https://eieio.games/) (One Million Checkboxes, One
Million Chessboards), and whether Cloudflare Workers and D1 can carry it.
This branch includes a working prototype:
- the server: `src/survey.js`
- the map, shared with the game: `src/letterfield-world.js`
- the survey code in `letterfield.html`

It stays switched off until `SURVEY_URL` is set.

## One Million Words

Letterfield already gives every player the same map, because every letter
comes from a fixed seed. The middle of that map, 100×100 territories around
the origin, hides **1,119,898 words**. The shared survey turns them into one
job for everyone: chart them all.

- **The first player to circle a word charts it.** Their initials appear
  next to it, and everyone else sees it outlined in its territory's colour.
  You can still circle it for your own field notes; the game tells you who
  got there first ("Charted first by SIS · 3m ago").
- **One number for the whole world.** The header shows "412,883 of
  1,119,898 charted", and it ticks up as words are charted nearby. The
  current territory has its own count ("83/120 charted"), and the game
  announces a territory once all of its hidden words are charted.
- **You can see the crowd.** Other players appear as coloured dots with
  their initials, at the middle of their screen.
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
| Bots pushed absurd traffic once the Go rewrite made things fast | a burst of 5 claims per socket, then one per 1.5 s; per-IP limits still to do |
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

For comparison, OMCB cost about $850 to run, on 8 VMs, Redis and bandwidth.
One Million Chessboards cost "a few hundred dollars": a $450/month box,
later $80/month, plus about a terabyte of traffic a month. On Cloudflare,
the survey costs the $5 plan when nobody is playing.

The first version, with timers, would have been billed for every second
every busy sector existed: ~$0.0056 per sector-hour. That's ~$84 a day for
625 busy sectors, before counting the quiet ones.

## Not done yet

- **Run `load.js` against a deployment.** That would confirm the per-sector
  limit and the 0.8 ms per player-second on Cloudflare's edge rather than a
  sandbox.
- **Bots.** The map can be generated from the page source, so a script
  could claim words as fast as the rate limit allows, from as many sockets
  as it opens. Next steps:
  - a limit per IP address across sectors (the Workers rate-limiting
    binding, or a Durable Object keyed by hashed IP);
  - a Turnstile check before joining;
  - accepting claims only near where the player has said they are.
- **Smaller snapshots.** Hidden words are deterministic, so a claim could
  be one bit in its chunk's word list. A fully charted sector's snapshot
  would shrink from 68 KB to a few hundred bytes plus initials. eieio
  measured protobuf + zstd at about 30 times smaller than uncompressed JSON.
- **Edge caching.** The world map is cached per Worker instance. On a
  custom domain, Cloudflare's cache could serve it as chessboards did.
- **Zoomed-out views** only show live claims from the four nearest sectors.
  A cached per-sector snapshot could fill in the rest of the screen.
- **Finds made offline stay personal.** Uploading them later would let
  anyone backdate a pile of claims at once.

## Trying it

```sh
cd worker
npx wrangler@4.151.0 dev --port 8787     # the Worker and its Durable Objects, locally
node bench/load.js http://127.0.0.1:8787 300 30   # 300 players for 30 s
```

To play, serve the games from the repo root (`python3 -m http.server 8000`)
and open `http://localhost:8000/letterfield.html?survey=http://localhost:8787`
in a few windows. The deploy workflow's `wrangler deploy` creates the
`Sector` and `Atlas` classes from the migration in `wrangler.toml`. After
deploying, set `SURVEY_URL` in `letterfield.html` to the Worker's URL.

[omcb]: https://eieio.games/blog/scaling-one-million-checkboxes
[chess]: https://eieio.games/blog/a-million-realtime-chess-boards-in-a-single-process
[do]: https://developers.cloudflare.com/durable-objects/
[hib]: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
[lifecycle]: https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/
[rules]: https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/
[d1limits]: https://developers.cloudflare.com/d1/platform/limits/
[wpricing]: https://developers.cloudflare.com/workers/platform/pricing/
[dopricing]: https://developers.cloudflare.com/durable-objects/platform/pricing/
