# Letterfield's shared survey

What Letterfield could look like with hundreds or thousands of players on
the same map at once, and whether Cloudflare Workers and D1 can carry it. This
branch includes a working prototype: `src/survey.js` (server),
`src/letterfield-world.js` (the map, shared with the game) and the survey
code in `letterfield.html`. It stays switched off until `SURVEY_URL` is set.

## The game

Letterfield already gives every player the same map: every letter comes from
a fixed seed. The shared survey makes everyone explore that map together.

- **The first player to circle a word is credited with charting it.** Their
  initials go next to the word, and everyone else sees it outlined in its
  territory's colour. You can still circle it for your own field notes, and
  the game tells you who got there first ("Charted first by SIS · 3m ago").
- **You can see other players.** Each one is a coloured dot with their
  initials, at the middle of their screen, moving as they pan around.
- **Territories fill up.** The header shows how much of the current
  territory is charted ("83/120 charted"), and the game announces a territory
  once every hidden word in it has been charted.
- **Your field notes are still yours.** They record the words you circled,
  marked "charted first" where you beat everyone else, and they still work
  offline. If the server can't be reached, the notes panel says so in one
  line and the game goes on as before.

With hundreds of players, everyone starts at the origin, so the words there
are charted within minutes. A **frontier** of uncharted territory then
moves outward, and fresh words are found by walking out to it. With
thousands of players the origin is a crowd: each sector draws its 64 most
recently active players and gives a head count for the rest ("760 other
surveyors nearby").

## How it works

```
 browser ──wss──▶ Worker ──▶ Durable Object "sector 0,0"   (SQLite: claims)
    │                   └──▶ Durable Object "sector -1,0"
    └── joins the ≤4 sectors in view, one WebSocket each
```

- **Sectors.** The map is cut into sectors of 4×4 territories (192×192
  cells). Each sector is one [Durable Object][do]: a single-threaded object
  with its own SQLite storage, holding the claims for its part of the map and
  every socket of the players looking at it. Because only one thing runs at
  a time inside a sector, "first to claim wins" is a plain
  `INSERT … ON CONFLICT DO NOTHING`, and two players can't both win a word.
  The map is endless, so sharding by place keeps working: two players in
  different sectors never touch the same object.
- **Joining.** The game joins the sectors in view, up to four, nearest the
  middle of the screen first. It leaves a sector once that sector has been
  out of view for 4 seconds, and leaves them all when the tab is hidden.
- **Claims.** The server checks every claim against its own copy of the map
  generator. The word has to really be in the grid at that spot, and inside
  this sector. A test runs the game's generator and the server's copy and
  compares their output.
- **Positions.** The game sends its position to one sector only, the one
  under the middle of the screen, at most once a second and only after
  moving at least a cell. Each sector sends one list of positions a second
  to all its sockets, however many players moved. That keeps a sector's
  traffic growing with the number of players, not with players squared.
- **Hibernation.** Sectors use the [WebSocket Hibernation API][hib]. When
  nobody in a sector is moving or circling, Cloudflare can evict the object
  from memory while the sockets stay open, so a quiet sector costs nothing.
  Everything a socket needs (id, initials, position, rate-limit tokens) is
  kept in the socket's attachment so it survives that.

Messages are listed at the top of `src/survey.js`.

## Do Workers and D1 scale for this?

**Workers: yes.** Workers are stateless and Cloudflare runs as many copies
as there are requests. They are never the bottleneck. What matters is the
number of requests, because each one counts toward the free plan's daily
limit or is billed on the paid plan.

**D1: not for the live part.** D1 is a good fit for the leaderboards: a
handful of writes per game played, read occasionally. A shared map is a
different kind of load:

1. **One database handles one query at a time.** Each D1 database runs on a
   single Durable Object and handles queries in order. Cloudflare's FAQ puts
   that at roughly 1,000 queries a second for 1 ms queries and about 10 a
   second for 100 ms ones. Extra queries queue, then fail as "overloaded".
   You scale D1 by spreading data across many databases, not by making one
   database bigger.
2. **D1 can't push changes.** To see other players' words "live", every
   browser has to ask over and over. At 1,000 players asking every 3 seconds
   that's about 330 requests and queries a second: a third of one database's
   ceiling just to say "nothing new", before anyone circles anything.
3. **Positions are the worst case.** Positions are many tiny writes that
   matter for a second and are then thrown away. Storing every player's
   position every 2 seconds is 500 writes a second at 1,000 players, every
   one durably committed, then read back by everyone polling. That's more
   than one database can sustain, and it costs a lot in rows written.
4. **The free plan runs out in minutes.** The Workers free plan allows
   100,000 requests a day (and 1,000 a minute). The D1 free plan allows
   100,000 rows written a day, and since 1 September 2026 queries fail once
   you pass it. 1,000 players polling would use up the day's requests in
   about 5 minutes, and their claims would use up the day's writes in about
   17.

**Durable Objects are the Cloudflare tool built for this,** and they run on
the same Worker:

- **The server can push.** A sector sends each claim and each list of
  positions to everyone the moment it has them. Outgoing messages aren't
  billed.
- **Incoming messages are cheap.** Messages arriving over WebSockets are
  billed as one request per 20 messages. With hibernation, a sector's time
  in memory is only billed while it is busy.
- **One object has a limit too, so the map is split.** Cloudflare's soft
  limit for one object is about 1,000 requests a second. Its guidance is
  200–500 a second when each request writes to storage. That's why there's
  a Durable Object per sector, and why a sector turns players away once it
  holds `MAX_PLAYERS` (1,000) sockets.
- **D1 keeps the leaderboards.** If the survey ever needs a board that spans
  sectors, such as "most words charted first", each sector would send D1 a
  total every minute or so. D1 then sees one write a minute per active
  sector, however many players there are.

### Measured: how busy one sector gets

`node worker/bench/sector.js` runs the Sector with 1,000 fake sockets in
Node. These numbers are from this branch's sandbox; Node isn't the Workers
runtime, so read them as an order of magnitude.

| work | time |
| --- | --- |
| check a claim against the map | 2–17 µs |
| claim a word and send it to 1,000 sockets | 66–87 µs |
| take in one position update | 7–10 µs |
| send one list of positions (1.5 KB) to 1,000 sockets | 3–4 ms |
| join (68 KB snapshot of a fully charted sector, kept in memory) | 25 µs |
| first join after the sector was evicted from memory | 8–12 ms |

Suppose 1,000 players in one sector each send a position every 2 seconds
and circle a word every 30 seconds. That's about 530 incoming messages a
second and about **10 ms of work per second**. Our own code isn't the limit.
The real limits are Cloudflare's per-object message rate, and the 1.5 MB a
second of position updates a crowded sector sends out. Both are reasons to
spread players out, not reasons to rewrite the sector.

The first version took 8 ms to build every join's snapshot. After a deploy,
which disconnects every socket, a crowded sector would have queued seconds
of rebuilding as everyone reconnected. The snapshot is now built once and
then appended to as words are claimed.

### Cost

Example: 1,000 players online at once, for 2 hours every day. That's 60,000
player-hours a month. Each player circles a word every 30 seconds, sends a
position every 2 seconds and opens about 10 connections an hour.

| | D1 + polling every 3 s (no positions) | Durable Objects + WebSockets |
| --- | --- | --- |
| Worker requests | ~79 M/month → ~$21 | ~0.6 M/month → included |
| Database or object requests | ~330 queries/s at peak, on one database | ~6.4 M/month (messages ÷ 20) → ~$0.80 |
| Rows written | ~22 M/month → included | ~7 M/month → included |
| Time in memory | none | ~25 busy sectors → ~$3.50 |
| Others' words show up | up to 3 s late | right away |
| Other players' positions | not practical (see above) | included |
| **Total, with the $5 Workers Paid plan** | **~$26 a month, at the edge of one database** | **~$9–10 a month** |

Prices are the published Workers Paid rates: $0.30 per million Worker
requests, $0.15 per million Durable Object requests, $12.50 per million GB-s
of duration and $1.00 per million rows written, each after a monthly
allowance. On the free plan, Durable Objects with SQLite storage are
available, with daily limits on requests and duration. Those limits cover a
few hundred player-hours a day; more needs the $5 plan. I couldn't reach
developers.cloudflare.com from the sandbox this was written in, so check the
[limits][limits] and [pricing][pricing] pages before relying on the exact
figures.

## Not done yet

- **Load test on Cloudflare.** The numbers above are from Node. The next
  step is a few hundred scripted sockets against a deployed sector, to see
  where Cloudflare's per-object limit actually bites.
- **Everyone starts in the same place.** New players start at cell (6, 6),
  the corner where four sectors meet, so all of them join the same four
  sectors. Splitting the map more finely won't help, because the crowd is
  all in one spot. Better options: start new players at a random spot on
  the frontier, join only one sector when a sector is crowded, or send
  crowded sectors' positions less often.
- **Bots.** The map can be generated from the page source, so a script could
  claim every word. Each socket is limited to a burst of 5 claims, then one
  every 1.5 seconds, but a bot can open more sockets. Next steps: a limit per
  IP address across all sectors (the Workers rate-limiting binding, or a
  Durable Object keyed by hashed IP), or a Turnstile check before joining.
- **Zoomed-out views.** Zoomed out, the game only shows live claims for the
  four nearest sectors. A cached `GET` snapshot per sector could fill in
  the rest of the screen.
- **Global numbers.** "Players online" and "words charted" for the whole map
  would need sectors to report to one aggregating object every few seconds
  (or to Workers Analytics Engine). That's easy, but isn't built.
- **Smaller snapshots.** Hidden words are deterministic, so a hidden word's
  claim could be sent as one bit in its chunk's word list. A fully charted
  sector's snapshot would then shrink from 68 KB to under 1 KB, plus the
  initials.
- **Finds made offline stay personal.** Uploading them later would let
  anyone backdate a pile of claims at once, so they aren't sent.

## Trying it

```sh
cd worker
npx wrangler@4.151.0 dev --port 8787     # runs the Durable Objects locally too
```

Then serve the games from the repo root (`python3 -m http.server 8000`) and
open `http://localhost:8000/letterfield.html?survey=http://localhost:8787`
in two windows. The deploy workflow's `wrangler deploy` creates the `Sector`
class from the migration in `wrangler.toml`. After deploying, set
`SURVEY_URL` in `letterfield.html` to the Worker's URL.

[do]: https://developers.cloudflare.com/durable-objects/
[hib]: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
[limits]: https://developers.cloudflare.com/durable-objects/platform/limits/
[pricing]: https://developers.cloudflare.com/durable-objects/platform/pricing/
