# If Letterfield goes viral

What happens when a link to Letterfield reaches the front page of Hacker
News (or anywhere like it), what to check beforehand, the knobs, what to
watch, and the order to give things up in. The design is in
[SURVEY.md](SURVEY.md), and Turnstile in [TURNSTILE.md](TURNSTILE.md).

## The spike this plans for

- 20,000 to 100,000 visitors over a few hours, 1,000 to 5,000 playing at
  once at the peak, arriving in bursts, many on phones.
- Many behind shared IPv4 addresses: offices, campuses, mobile carriers
  (CGNAT). The survey limits each address, so they share one allowance.
- Curious people reading the API, and probably a few scripts.

## The verdict

**Fine up to about 5,000 at once, and the bill can't run away.** Nothing in
the Worker breaks at the spike's numbers. What players would notice first,
in order:

1. **Where newcomers start.** Everyone arriving in the same few seconds
   used to be sent to the same crowd, which filled past what a sector takes
   (750) at about 50 arrivals a second, telling newcomers "crowded" for a
   minute at a time. Fixed (see "What was fixed"); a burst now spreads over
   the crowds with room, and anyone who still lands in a full one is moved
   next door.
2. **Shared addresses.** An office or campus of more than about six
   players shares 6 claims a minute and 300 words a day. Claims past the
   minute wait quietly and go again (often after someone else has charted
   the word); past the day's 300 every player there sees "Today's charting
   limit reached · kept in your notes". See "Rate limits and shared
   addresses" for what to change.
3. **A deploy of the Worker** drops every socket and empties the Atlas's
   memory. Players come back within a few seconds now, but the day's
   cap counts and bot numbers start again. Don't deploy during the spike.

The ceilings past those are far off: the Atlas takes about 3,000 reports a
second against ~100 at the spike's peak, `MAX_ONLINE` is 25,000, and the
worst day costs about $18.

## Where the site is served from

**The HTML, modules, music and icons come from GitHub Pages.**
`.github/workflows/pages.yml` deploys `_site/` there on every push to
`main`. Only the API (`api.games.michaelwarkentin.com`), the share Worker,
the album's files in R2 and each pull request's preview are on Cloudflare.

The `michaelwarkentin.com` zone is on Cloudflare (the API's custom domain
needs it), but the `games.` record isn't proxied: Pages answers it directly,
through GitHub's Fastly CDN. To check, look at the response headers:

```sh
curl -sI https://games.michaelwarkentin.com/letterfield | grep -iE '^(server|via|x-served-by|cf-ray):'
```

`server: GitHub.com`, `via: 1.1 varnish` and `x-served-by: cache-…` with no
`cf-ray` mean Pages, straight. `server: cloudflare` with a `cf-ray` would
mean Cloudflare's proxy (or a Worker) sits in front. On 2026-11-27 it was
Pages, straight. The record itself is in mwarkentin/infra, and in the
dashboard under DNS: a grey cloud is DNS only, an orange one proxied.

## Each part against the spike

| part | its limit | at the spike's peak (5,000 at once) | verdict |
| --- | --- | --- | --- |
| GitHub Pages: page weight | first visit to Letterfield: 167 KB page + 149 KB modules (gzipped), + ~70 KB of Google Fonts | the same for every visitor; after that, the service worker and `max-age=600` | fine |
| GitHub Pages: bandwidth | soft limit 100 GB a month | ~0.8 MB a first visit (with the service worker's copy of every other page, ~0.5 MB): 16 GB for 20,000, 80 GB for 100,000 | near the soft limit at the top of the range; GitHub sends an email first, and Fastly serves it all (see "An option: serving the site from Workers static assets") |
| GitHub Pages: builds | soft limit 10 an hour | only on merges | fine; don't merge a burst of changes |
| One sector | ~750 sockets (`MAX_PLAYERS`, measured: 55% CPU at 700) | crowds of up to `SPAWN_MAX` (300) placed, ~400 with a burst's overshoot | fine |
| The spawn rule | the biggest crowd with room, read from a world map up to ~25 s old | at 40 arrivals a second, before: 607 in one sector; now 393 at most, over four | fixed |
| The Atlas | one object: ~0.3 ms a report in Node at any size now (2.4 ms at 25,000 online before), ~3,000 reports a second | ~6 a second from sectors, plus one per player leaving: ~50 | fine, to well past `MAX_ONLINE` |
| `MAX_ONLINE` | 25,000 surveyors (each address counts for at most 40) | 5,000 | fine; past it, "The survey is crowded right now" |
| Reconnects after a deploy | every socket drops at once | ~10,000 sockets | spread over 1–6 s now: 1,500 sockets rejoined at p95 2.1 s locally, against 5.6 s when they all came back within a second |
| Player, Guild, links | a Durable Object each, D1 for codes | per player, never shared | fine |
| D1 (the log) | one query at a time, ~1,000 a second | words charted: at 20 a player-hour, ~28 a second, copied in batches every 30 s per sector: ~2 batches a second | fine |
| D1 (log reads) | cached per instance and per Cloudflare location, 15 s while running, a day once settled | a crowd on the log page reads each answer once per location every 15 s | fine |
| Definitions | Wiktionary and Wikipedia, once per word ever, then D1 | at most 28,845 words ever; 20 new ones a minute per address | fine |
| Share cards | ~50 ms of CPU each, 30 new ones a minute per address | a card is drawn once per state and kept in R2; over the limit the game's own preview stands in | fine |
| Sentry | the plan's monthly quotas | before: a trace for every page load, a replay of every tenth session, every error | capped (see "What was fixed"); spike protection on top |
| Counterscale | Analytics Engine: a write per page view | 100,000 | fine, pennies |
| Fonts and CDNs | Google Fonts, jsDelivr, cdnjs, Sentry's CDN | their own CDNs | fine; every font has a system fallback |

## What was fixed

- **The Atlas's count of players** was worked out afresh on every report,
  walking everyone online: at 25,000 online, 2.4 ms of a 3 ms report, so the
  one object every sector reports to would have run out near 400 reports a
  second. It's kept report by report now (0.3 ms), and a test checks it
  against a recount. `bench/atlas.js` measures it.
- **Newcomers spread over the crowds with room.** The world map offers the
  biggest few (`spawns`, each with its size and room), and the game picks one
  by size or room, whichever is less. A sector whose crowd fills past
  `SPAWN_MAX`, or has room again, reports within a second rather than ten,
  and the Atlas builds the world map afresh for the next newcomer to ask.
  In `bench/spike.js`, 1,500 arriving at 40 a second put 607 in one sector
  before, and at most 393 over four after.
- **Moved next door.** A newcomer whose crowd filled before they got there
  is moved 24 cells into the emptiest sector beside it ("That spot is
  crowded · Starting you next door, beside the crowd"), at most twice, and
  only while they're still where they were sent.
- **Reconnects spread out.** A live socket that drops tries again after 1–6
  s, at random, rather than 0.5–1.5 s, so a deploy's crowd doesn't arrive at
  once.
- **Crowded says to keep playing:** "Keep finding words: they save in this
  browser, and you'll join as soon as there's room."
- **Sentry is sampled.** Traces for a fifth of page loads (from all of
  them), session replays for one session in fifty (from one in ten), a replay
  of every session with an error as before, and no more than 25 errors from
  one page load, 3 of any one message.

## An option: serving the site from Workers static assets

The `games-preview` Worker already serves `_site/` as static assets for
every pull request (`preview/wrangler.toml`), so the live site could be
served the same way, from a Worker of its own on Cloudflare, instead of
from Pages. Not done; this is what it would mean.

**What it would gain for a spike**

- **No Pages limits.** No 100 GB-a-month soft limit on bandwidth (the one
  Pages limit a big day could reach, at ~0.8 MB a first visit) and no 10
  builds an hour.
- **Cloudflare's network,** the same one the API is on, with requests to
  static assets free and unlimited (they don't count as Worker requests).
  Pages' Fastly CDN already serves a spike well, so this is about limits
  and control, not speed.
- **Its own cache headers.** Pages sets `max-age=600` on everything. A
  `_headers` file in `_site/` could set them per path: long for icons,
  previews and music, short for pages, `no-cache` for `sw.js`.
- **Rollback in seconds.** `wrangler rollback` brings back the last version
  at once, where Pages needs a revert, a build and a deploy.
- **One platform** for the site, the API, the share cards and the previews:
  one dashboard of metrics during the spike, with requests to the site
  beside the API's.
- **Deploying the site still wouldn't touch the survey.** A Worker for the
  site is a separate script, so its deploys drop no sockets.

**What it would take**

- **A production Worker of its own** (say `games-site`), never
  `games-preview`, so no preview can become the live site. Its
  `wrangler.toml` is `preview/`'s: `[assets]` with `directory = "../_site"`
  and `html_handling = "auto-trailing-slash"`, so `/war` serves `war.html`
  as it does on Pages.
- **A deploy job** in place of `pages.yml`: `build.sh`, then
  `wrangler deploy`, with the Cloudflare token the leaderboard's deploy
  already uses. It should run only on site changes, as `pages.yml` does.
- **DNS, in mwarkentin/infra:** a Workers custom domain for
  `games.michaelwarkentin.com` (as `worker_domains.tf` makes the API's),
  replacing the record that points at Pages. Cloudflare makes the
  certificate. Keep Pages deploying for a week or two, so moving back is
  changing the record back.
- **Caching and the service worker:** a `_headers` file built into
  `_site/`, with `sw.js` never cached long, and a check that `sw.js`'s
  network-first pages and hashed module addresses behave as on Pages. The
  same origin and paths mean every player's stored copy and `localStorage`
  carry over untouched. `tests/test_pwa.py` and the smoke tests run against
  a local server, so a short test against `wrangler dev` would be worth
  adding.
- **What reads the hostname,** such as telemetry, analytics, Turnstile's
  widget and `ALLOWED_ORIGINS`, keeps working: the hostname doesn't change.

**What it would cost:** nothing more. Static asset requests are free on
Workers Paid, which the account already pays for. Its limits are far above
the site's: 100,000 files a version, 25 MiB a file, against ~60 files and
3.6 MB.

**Not recommended instead:** proxying the Pages record through Cloudflare
(an orange cloud). It puts Cloudflare's cache in front, but GitHub can't
renew the site's certificate behind a proxy, and two CDNs make it harder to
tell which one served a stale page.

**Recommendation:** make the move, but at a quiet time, not as a reaction
to a spike. For one viral day Pages is fine: Fastly serves the traffic, and
going past the soft limit once brings an email, not an outage. The move
pays for itself afterwards, in limits that don't matter any more, per-path
caching, instant rollbacks and one place to look. If a spike is days away,
stay on Pages and don't change DNS the week of it.

## Rate limits and shared addresses

How soon players behind one IPv4 address (an office, a campus, CGNAT) meet
each limit, and what they see:

| limit | allowance per address | met by | what they see |
| --- | --- | --- | --- |
| claims (`SURVEY_CLAIMS`) | 6 a minute | 7+ players each charting a word a minute | nothing: the claim waits a minute in the outbox and goes again; meanwhile someone elsewhere may chart it first |
| words a day (`DAILY_CLAIMS`) | 300 a UTC day, in the shared world | 10 players charting 30 each; at 6 a minute, under an hour | "Today's charting limit reached · kept in your notes", for everyone there, until midnight UTC |
| joins (`SURVEY_JOINS`) | 120 sockets a minute | 40+ players arriving or reconnecting at once (each opens 1–4) | "This part of the map is crowded right now", and a try a minute later |
| sockets in one sector (`ADDRESS_SOCKETS`) | 40 | 40+ players from one address in one crowd, which the spawn rule makes likely | "crowded"; a newcomer is moved next door |
| toward `MAX_ONLINE` (`ADDRESS_ONLINE`) | 40 counted | only matters near 25,000 | nothing |
| emotes (`SURVEY_EMOTES`) | 20 a minute | rarely | "slow down" under the emote |
| new guilds / guild joins | 5 / 20 an hour, in D1 | a class or a team joining from one invite | "too many requests, try again in a few minutes" |
| link codes / tries / recovery codes | 10 / 20 / 5 an hour | rarely | the same |
| Turnstile passes | 120 a minute | never in play | |

Abuse is the other side: one address scripting the map gets 6 words a
minute and 300 a day, and the pool of addresses it would take to chart the
world is what Turnstile is for.

### Proposed, not done (each ships on merge, so it's the owner's call)

- **Count claims per surveyor with a pass, beside the address.** A socket
  that joined with a good Turnstile pass is a person on a real browser,
  already tied to its address. Limit those claims by player id (6 a minute,
  300 a day each) with a looser ceiling per address (say 60 a minute and
  3,000 a day), and keep today's limits for sockets without a pass. An
  office then gets what its people would separately; a script without a
  pass gets what it gets now, and one with a pool of passes still pays a
  solver for each. It needs the daily count by id in the Atlas (one entry
  per surveyor, as the surveyor list already holds) and a second limiter
  key in the sector.
- **Until then, for the day: `DAILY_CLAIMS` 300 → 1,000.** It's the limit
  shared addresses meet first and the one that shows. A script at 6 a minute
  still needs three hours to reach it, and the world would take one address
  three years.
- **`SURVEY_JOINS` 120 → 240 a minute.** A join it refuses wakes nothing,
  and the claims limit is what stops a script charting, so a looser one
  costs little and keeps a campus from being told "crowded" after a deploy.
- **Leave `SURVEY_CLAIMS` at 6 a minute.** It's the one that bounds a
  script; the per-surveyor limit above is the way to give shared addresses
  more.
- **Leave `TURNSTILE_REQUIRED` at `"false"`** unless the bot signs show (see
  "What to watch"). Required, every player whose browser blocks
  `challenges.cloudflare.com` (ad blockers, work and school filters, some
  privacy browsers, all common in a Hacker News crowd) surveys alone, and
  every newcomer waits for a challenge before joining. Passes are already
  handed out, so `unpassed` in the world map shows how many it would turn
  away.

## Beforehand

- **Merge what's waiting, early,** so no deploy has to happen during the day.
  Anything touching `worker/**`, `js/letterfield/**` or `js/war/**` deploys
  the leaderboard Worker (`leaderboard.yml`), even a change to the game
  alone.
- **Check the numbers are sane:**
  `curl -s https://api.games.michaelwarkentin.com/v1/survey/world -H 'Origin: https://games.michaelwarkentin.com' | jq 'del(.territories)'`
- **Set a spending alert** (see "A spending alert"); there's none yet.
- **Check Sentry's spike protection is on** for the games project, and that
  an issue alert reaches you.
- **Know the Workers dashboard:** Workers & Pages → games-leaderboard →
  Metrics (requests, errors, CPU), Durable Objects (requests and duration by
  class), and Logs.
- **Have the knobs ready** in a branch, unmerged, if you'd want them quickly.

## The knobs

Every knob below is a deploy of the Worker: a change to `wrangler.toml` or
`src/`, merged to `main`, deployed by `leaderboard.yml` in about two
minutes. **A deploy drops every socket** (players are back within a few
seconds) **and empties the Atlas's memory**: the day's counts per address
(so the daily cap starts again), the bot numbers in `today`, the supernovas
it's relaying. So turn knobs together, once, and only for a reason.

| knob | where | what it does |
| --- | --- | --- |
| `TURNSTILE_REQUIRED = "true"` | `[vars]` in `worker/wrangler.toml` | turns away joins without a pass; players who can't pass survey alone |
| `MAX_ONLINE` | `src/survey.js` | the whole survey's ceiling (25,000): past it, "The survey is crowded right now". Lower it to cap the bill |
| `MAX_PLAYERS` | `src/survey.js` | sockets a sector takes (750) |
| `SPAWN_MAX` | `src/survey.js` | how big a crowd newcomers are sent to (300): lower spreads them more |
| `DAILY_CLAIMS` | `src/survey.js` | words an address charts a day (300) |
| `SURVEY_CLAIMS`, `SURVEY_JOINS`, `SURVEY_EMOTES` | `[[ratelimits]]` in `worker/wrangler.toml` | per address, a minute |
| `VIEW_MS` | `src/survey.js` | how long the world map is cached (5 s) |
| `LIST_MS` | `src/survey-social.js` | how long the surveyor list is cached (10 s) |
| `SURVEY_URL` | `letterfield.html` | blank it, and the site's next deploy (Pages, a minute or two) makes everyone survey alone; the Worker needn't deploy |

Blanking `SURVEY_URL` is the one switch that doesn't touch the Worker: it's
a change to the site alone (keep `js/letterfield/` out of the same commit).
Open sockets stay until each player reloads, or their tab sleeps and comes
back.

## What to watch, and where

- **The world map** (read-only, cached 5 s): `players`, `sectors` (the
  crowds and their sizes), `today.capped` (addresses at the daily cap),
  `today.unpassed` (joins without a pass) and `today.charted`. Every minute
  or so:
  `watch -n 60 "curl -s https://api.games.michaelwarkentin.com/v1/survey/world -H 'Origin: https://games.michaelwarkentin.com' | jq -c 'del(.territories)'"`
- **Workers Logs** (games-leaderboard): `{survey: 'hour'}` lines with each
  hour's words, player-hours and words per player-hour; `{survey: 'daily
  cap'}` as addresses reach it; `{survey: 'log failed'}` if D1 is refusing
  the log; any uncaught error.
- **Workers metrics:** errors and CPU time per request for the Worker, and
  for Durable Objects requests and wall time by class. A sector near its
  limit shows as high duration on `Sector`; the Atlas is one object, so its
  duration is the one to watch.
- **Sentry:** new issues in letterfield, and the stats page for events
  dropped by quota or spike protection.
- **Counterscale:** page views and referrers as they come.
- **Survey watch** (`survey-watch.yml`) only runs after midnight UTC on
  yesterday's numbers. Run it by hand from the Actions tab on the day if the
  world map looks odd; it opens a `survey-bots` issue past its thresholds.

Signs of trouble, and what they mean:

| you see | it means |
| --- | --- |
| `today.capped` past 20, rising | shared addresses at the cap, or a pool of scripts; check words per player-hour |
| words per player-hour well past 60 | bots: a person charts a word a minute at most |
| `today.unpassed` large next to `players` | joins without a pass: scripts, or Turnstile failing for many |
| a `sectors` entry at 750 | that crowd is full; newcomers are moved next door |
| `players` near 25,000 | the survey is about to say "crowded" to everyone new |
| Atlas duration climbing, world map slow | the Atlas is the bottleneck: see the order below |
| Sentry events dropped for quota | the month's quota is gone; sample less |

## The order to give things up in

1. **Nothing, while it holds.** Crowded sectors move newcomers next door;
   shared addresses wait out their minute.
2. **Bots charting:** switch on `TURNSTILE_REQUIRED` (a deploy). Only on
   evidence: it costs every player whose browser blocks Turnstile.
3. **Too many at once, or the bill:** lower `MAX_ONLINE` (a deploy).
   Newcomers past it play alone, told the survey's crowded, with their
   finds kept.
4. **The Atlas struggling:** raise `VIEW_MS` and `LIST_MS` (10 s and 30 s),
   so each Worker instance asks it less (a deploy).
5. **The Worker itself failing:** blank `SURVEY_URL` in `letterfield.html`
   and let Pages deploy it. Everyone new plays alone; the game is the same
   game, and their finds stay theirs.

## What not to do

- **Don't deploy the Worker mid-spike** without a reason from the list
  above, and never just to tidy: every deploy drops every socket and resets
  the day's caps. Mind that `js/letterfield/**` deploys it too.
- **Don't run load tests against production.** Use `wrangler dev` or a pull
  request's Worker Preview (see "Load tests").
- **Don't require Turnstile pre-emptively.**
- **Don't merge several site changes in an hour:** Pages' builds have a soft
  limit of 10 an hour, and every deploy refreshes every visitor's offline
  copy (about 0.8 MB each).

## Recovering

- Undo knobs in one deploy, after the peak, rather than one at a time.
- Put `SURVEY_URL` back if it was blanked; players join at their next load.
- A deploy after the day resets the Atlas's counts, which is harmless then.
- Check the log caught up: `{survey: 'log failed'}` lines stop, and the log
  page's running hour fills in. Sectors keep every claim until D1 has it.
- Read the next morning's survey watch; close its issue if it was the crowd.
- Note in this file what happened and what helped.

## Cost

From the cost model in SURVEY.md (per player-hour: ~30 Worker requests,
~106 Durable Object requests, ~0.35 GB-s), on Workers Paid ($5 a month,
with 10 M Worker requests, 1 M Durable Object requests and 400,000 GB-s
included):

| day | player-hours | Worker requests | DO requests | DO time | over the plan |
| --- | --- | --- | --- | --- | --- |
| realistic: 50,000 visitors try the survey, 8 minutes each | ~6,700 | 200,000 | 710,000 | 2,300 GB-s | **~$0**, if the month was quiet |
| busy: 100,000 visitors, 15 minutes each | ~25,000 | 750,000 | 2.7 M | 8,800 GB-s | **~$0.25** (DO requests) |
| the ceiling: `MAX_ONLINE` (25,000) online all day, bots included | 600,000 | 18 M | 64 M | 210,000 GB-s | **~$18** |

The surveyor list, guilds, the log, definitions and share cards add cents.
GitHub Pages, Sentry (sampled) and Counterscale cost nothing more. So a
viral day costs less than a dollar, and the worst a day can cost, with
the survey full of scripts all day, is about $18.

## A spending alert

Workers Paid has no spending cap, and nothing tells you yet. Two ways, both
outside this repo (in mwarkentin/infra):

1. **Cloudflare's billing notification.** A usage-based billing
   notification (`cloudflare_notification_policy`, alert type
   `billing_usage_alert`) emails when a product's usage passes a threshold
   in the billing period. Set one for Workers requests (say 15 M) and, if
   it's offered, Durable Objects requests (say 5 M). Check which products
   the alert covers in the dashboard (Notifications → Add → Billing).
2. **A scheduled check**, if Durable Objects aren't covered: a daily
   workflow beside `survey-watch.yml` that asks Cloudflare's GraphQL
   Analytics API for the month's Worker and Durable Object requests and
   duration (`workersInvocationsAdaptive`,
   `durableObjectsInvocationsAdaptiveGroups`,
   `durableObjectsPeriodicGroups`), works out the bill from SURVEY.md's
   prices, and opens an issue past a threshold ($10, say). It needs an API
   token with Account Analytics read only, made in infra and set as a
   secret.

## Load tests

Never against production. Three benchmarks, in `worker/bench/`:

- `atlas.js`: the Atlas's work per report, in Node, at any number online:
  `node --disable-warning=ExperimentalWarning worker/bench/atlas.js 25000 625`.
- `spike.js`: newcomers arriving at a rate, each starting where the world
  map says, spread over as many sectors as that sends them to; with
  `STORM=<s>`, every socket dropping at once and coming back with the
  game's backoff; with `SHARED` and `ADDRESSES`, some players behind shared
  addresses. Against `wrangler dev` (`cd worker && npx wrangler@4.151.0 dev`,
  with an `IP_SALT` in `.dev.vars`):
  `node worker/bench/spike.js http://127.0.0.1:8787 1500 40 80`.
- `load.js`: one sector's capacity, as in SURVEY.md.

Measured on `wrangler dev`, a 4-core sandbox shared with the load generator
(so relative numbers, not the edge's):

| run | result |
| --- | --- |
| Atlas, 25,000 online over 625 sectors | 2.4 ms a report before, 0.3 ms after; the world map 0.7 ms to build, the surveyor list 9.5 ms |
| 1,200 arriving at 30 a second, old spawn | 607 in one sector, 444 and 149 in two more |
| 1,500 arriving at 40 a second, old spawn | 597, 565, 338 |
| the same, with `spawns` | 592, 449, 264, 195 |
| the same, with `spawns` and reporting as a crowd fills | 393, 393, 391, 323 |
| 1,000 sockets dropped at once, back within 0.5–1.5 s (the game before) | rejoined at p50 1.8 s, p95 2.8 s |
| the same, back within 1–8 s | p50 16 ms, p95 162 ms |
| 1,500 dropped at once, back within 0.5–1.5 s | p50 3.3 s, p95 5.6 s (this sandbox's one process saturated, holding every sector) |
| the same, back within 1–6 s (the game now) | p50 1.2 s, p95 2.1 s |
| 600 arriving, 30% behind 3 shared addresses | 415 of ~1,550 claims refused `slow down`, all from the shared addresses; 13 sockets turned away for 40 from one address in one sector |

**On a Worker Preview** (PR #135's, on Cloudflare's real edge, 2026-11-27),
from one machine, so every player was one address and the runs kept under
its limits: 40 sockets a sector, 120 joins and (on a Preview) 60 claims a
minute. A plain `GET /v1/survey/world` from that machine took 250–550 ms,
which every join below includes (a new TLS connection through its proxy).
Run it with `NODE_USE_ENV_PROXY=1` behind a proxy; `spike.js` sends no
`CF-Connecting-IP` there, since the edge refuses one.

| run | result |
| --- | --- |
| 38 players in one sector, a claim each every ~45 s, 2 minutes | all joined (hello p50 703 ms, p95 929 ms); 97 claims answered at p50 89 ms, p95 186 ms; none refused |
| 114 players over three sectors, arriving at 1.5 a second | all joined (p50 627 ms, p95 850 ms); 256 claims at p50 63 ms, p95 169 ms; the world map counted each wave within 5–15 s, and answered in 220–560 ms throughout |
| those 114 dropped at once, back over 1–6 s | all back, hello p50 605 ms, p95 805 ms: no slower than joining at all; the world map counted 0, then 76, then all 114 within 15 s |

So on the edge the survey behaves as it does locally, with no queueing at
this size. One address can't load a sector anywhere near its limit there, so
a sector's 750 and the Atlas's ceiling still rest on the local runs above.
Testing those on the edge would take players from hundreds of addresses.
