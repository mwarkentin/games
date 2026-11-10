# Leaderboard worker

A [Cloudflare Worker](https://developers.cloudflare.com/workers/) with a
[D1](https://developers.cloudflare.com/d1/) (SQLite) database that stores
global high scores for the games, and a
[Durable Object](https://developers.cloudflare.com/durable-objects/) per
room for War's multiplayer games (see [War rooms](#war-rooms)). The account
is on Workers Paid ($5 a month), for Letterfield's survey (see SURVEY.md); the
leaderboard alone uses a handful of requests and database rows per game
played.

The same Worker hosts Letterfield's shared survey, an experiment in many
players exploring one map at once: a Durable Object per sector of the map,
reached over WebSockets, with a log of every word charted in D1 for
`letterfield-log.html`. [SURVEY.md](SURVEY.md) covers its design, its API
(the log's under "The log") and how far it scales, and [TURNSTILE.md](TURNSTILE.md) an optional
Turnstile check before joining: passes are handed out once the
`TURNSTILE_SECRET` secret is set, and required only once
`TURNSTILE_REQUIRED` is `"true"` in `wrangler.toml`.

## API

```
GET  /v1/scores?game=funnels-and-buckets&scope=*&difficulty=classic&mode=all&since=1792987200000
  → 200 {"game", "scope", "difficulty", "mode", "since",
         "scores": [{"rank", "entry", "initials", "score", "level", "difficulty", "mode", "at"}]}
  → 404 {"error": "unknown group"}

POST /v1/scores
  {"game": "funnels-and-buckets", "difficulty": "classic", "mode": "normal",
   "initials": "ABC", "score": 150, "level": 2, "popped": 12, "seconds": 90,
   "groups": ["K7QP"], "public": true, "since": 1792987200000}
  → 201 {"entry": "<uuid>", "ranks": {"*": 14, "K7QP": 1},
         "periodRanks": {"*": 2, "K7QP": 1}}

POST /v1/groups
  {"name": "Family"}
  → 201 {"code": "K7QP", "name": "Family"}

GET  /v1/groups/K7QP
  → 200 {"code": "K7QP", "name": "Family"}
  → 404 {"error": "unknown group"}

Errors: 400 {"error": "..."} for an invalid or implausible request,
        403 for a POST from a page not in ALLOWED_ORIGINS,
        429 for more than 10 scores in 10 minutes, or 5 new groups in an
        hour, from one IP address.
```

Games send POST bodies as JSON with `Content-Type: text/plain`, which
browsers treat as a simple request and send without a CORS preflight.

**Views.** A view is one scope (`*` for the public board, or a group code)
narrowed by `difficulty` and `mode`, each of which can be `all` (the
default). It returns the top 10.

**Periods.** `since` (milliseconds since 1970) narrows a view to scores
saved from then on: the games send the start of today, this week (Monday)
or this month in the player's own time zone. It must be within the last 32
days (or up to a day ahead, for a device clock that runs fast); leave it
out for all time.

**Ranks.** A POST returns each score's rank within its own difficulty and
mode: `ranks` for all time and, when the POST includes `since`,
`periodRanks` for that period. Counting stops at 1,000, so a rank past that
is `null` (the games say "beyond #1,000").

**Groups** are private boards for family or friends. Each has a
four-character code from `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (no 0/O or
1/I/L, so codes are easy to read aloud) and a name of up to 24 characters.
There are no accounts: anyone with the code can see the group's scores and
add to them. Games remember the groups a player has joined in
`localStorage` and send their codes with each score, up to five. A score
goes to the public board unless `public` is `false`, and to each listed
group.

**Storage.** Every place a score is shown is its own row in `scores`
(`scope` is `*` or a group code); the copies share an `entry` id. Every
score is kept. A copy is a few hundred bytes with its indexes, so the free
plan's 500 MB holds hundreds of thousands of saves.

The survey's log is the `survey_log` table in a second database,
`games-survey-log` (binding `LOG_DB`, migrations in `migrations-log/`), one
row per word charted, copied there by each sector (see "The log" in
SURVEY.md). Triggers keep running counts beside it, per hour, per day per
set of initials and per day per territory, for the log page's weeks,
months, years and top lists, and three indexes find one surveyor's,
territory's or theme's words. The whole shared world would be about 1.1
million rows and 150 MB. A new map (see "A new map" in SURVEY.md) empties
it with a migration. mwarkentin/infra makes it too; its id (the
`survey_log_database_id` output) goes in `wrangler.toml`.

D1 counts every row a query scans against the plan's allowance, so each
view reads through an index of its own (named with `INDEXED BY` in
`src/leaderboard.js`, and checked with `EXPLAIN QUERY PLAN` in the tests).
An all-time top 10 reads about 10 rows, and a period view reads only that
period's scores. The Worker checks that a
score is possible for the game (see `GAMES` in `src/leaderboard.js`), allows
only three letters A–Z as initials, and stores a salted hash of each IP
address, never the address itself, to rate-limit writes.

**Logs.** Workers Logs keeps the Worker's console output and uncaught
exceptions for a few days. Its per-request invocation logs are off in
`wrangler.toml`, because they would store each request's headers, the
client's IP address included.

`src/leaderboard.js` holds the logic and `src/index.js` only exports the
Worker and the Durable Object classes: the runtime treats every
export of the main module as an entry point, so constants exported for tests
can't live there. `src/survey.js`, `src/survey-log.js` and `src/letterfield-world.js` are the
survey.

## War rooms

`war.html` plays with friends through rooms. `src/war.js` holds the
`WarRoom` Durable Object class, one per room, which keeps the game and
every player's WebSocket, and deals, waits for slams and plays out each
battle itself. Pages only show what it tells them.

```
POST /v1/war/rooms
  → 201 {"code": "K7QP"}
  → 429 for more than 20 new rooms in an hour from one IP address

GET  /v1/war/rooms/K7QP
  → 200 {"code", "phase": "lobby" | "playing" | "over", "players", "full"}
  → 404 {"error": "unknown room"}

GET  /v1/war/rooms/K7QP  (Upgrade: websocket)  joins the room
```

Both writes and the WebSocket need an origin in `ALLOWED_ORIGINS`. Over the
WebSocket, pages send JSON messages:

| Message | Means |
| --- | --- |
| `{"t":"hello","name","avatar","token","deck"}` | join, or rejoin the same seat with the same token; `deck` is the deck theme your cards are drawn in |
| `{"t":"length","length"}`, `{"t":"slow","slow"}`, `{"t":"shuffle","shuffle"}`, `{"t":"bots","n"}`, `{"t":"start"}` | the host sets up the game (its length, whether it's slow, with no clock, and whether winnings are shuffled on their way back) and deals |
| `{"t":"gather"}` | put your winnings under your deck, any time in a game |
| `{"t":"charge","tier"}`, `{"t":"slam","power","style"}` | charging up, then slamming (for show only) |
| `{"t":"card","n","power"}` | in a war, slamming face-down card `n` (0 to 2) before the last one, which is the `slam` (for show only) |
| `{"t":"cheer","e"}` | an emoji for everyone, at most every 0.4 seconds |
| `{"t":"deck","deck"}` | change deck theme, even mid-game, at most once a second |
| `{"t":"tidy"}` | clean up the cards you've won into a neat stack, during or after a game, at most once a second (for show only) |
| `{"t":"nudge"}` | in a slow game, once a stage has been open 5 seconds: nudge everyone it's waiting for, at most every 3 seconds |
| `{"t":"flop"}` | in a slow game, from the host, once a stage has been open 30 seconds: flip over the cards of everyone it's still waiting for |
| `{"t":"leave"}` | leave the lobby |

The room answers with these:

| Message | Means |
| --- | --- |
| `state` | everything, sent on joining and when the lobby changes: `slow` and `shuffle` are the room's settings; mid-game, `game.counts` has every card each seat holds, `game.decks` the ones in their deck and `game.loot` the cards they've won (the latest last), `game.ups` the card each slam so far turned face up, `game.naps` how many cards in a row flopped for each seat, and `game.slow` and `game.shuffle` this game's settings, with `closesIn` null in a slow one |
| `online` | who's connected, and who's host |
| `stage` | a battle or war opens; `bots` is `[seat, power, style, delay, up]` for each bot, its slam and the card it turns face up; `gathered` lists the bots whose decks couldn't cover the stage, so their winnings went under them as it opened; `closesIn` is null in a slow game |
| `charge`, `card` | someone charging up, or slamming a face-down card in a war |
| `slam` | `{"seat","power","style","up"}`: someone slammed the card that counts, and `up` is that card, face up at once; with `"flopped":true`, the host flipped it over for them; with `"gathered":true`, their deck couldn't cover the stage, so their winnings went under it first |
| `nudge` | `{"seats","by"}`: someone (`by` is null for a spectator) nudged the players in `seats` |
| `flip` | the stage is played out: every card, `plays` as `[seat, down, up, power, style, flopped]`, the winner and pot, and the next stage or the final standings; `counts` is every card each seat holds and `decks` the ones in their deck; `gathered` lists the seats whose cards flopped from a deck that couldn't cover the stage, so their winnings went under it first; in a war, `downs` has the cards each seat laid face down, which show face up in the winner's loot |
| `gather` | `{"seat"}`: someone put their winnings under their deck |
| `cheer`, `deck`, `tidy` | someone cheered, changed deck or cleaned up their winnings |
| `error` | something went wrong, in words for the player |

Players get 8 seconds to slam in a battle and 20 in a war, where they slam
every card they lay down. A `charge`, `card` or `slam` counts only once its
stage has opened, after the last one's cards have turned over: one that
arrives after its stage was played out is dropped, not counted toward the
next. A stage's cards are fixed once it opens, so a slam
says which card it turns over: everyone sees it face up straight away, and
the winner comes with `flip`. Cards that flop over by themselves only show
at the `flip`. War has no decisions, so seeing a card early helps nobody.

**Decks and winnings.** Each player has a deck, face down, and the cards
they've won, face up beside it. A pot goes on its winner's winnings as it
lies: everyone else's cards in the order they were played, then the
winner's own on top. Winnings go back under the deck when the player picks
them up (`gather`), and only then: when a stage opens that a player's deck
can't cover (a card in a battle, four in a war), the page has them pick up
before they can slam (Auto picks up for them). Bots pick
up by themselves as the stage opens. A slam, a host's flip or a card that
flops at the end of the clock from a deck that can't cover the stage picks
up first, so a stage always has its cards. They go under as they lie, the
oldest first, unless the host picked shuffled winnings, which is how plenty
of people play. Picking up early changes no card to come, so it's a
player's own business. Kept in order, a long game can come round to where it
was and go in circles; total war's 5,000-battle limit ends it.

**Slow games.** The host can pick a slow game in the lobby: no clock, like
a real table. A stage waits until everyone connected has played, and
nobody's card flops over by itself; bots still play on their own. So that
one sleepy or vanished player can't stall the table for good:

- players who've left (no open connection) aren't waited for, and are
  waited for again when they come back;
- every page shows who the table is waiting for;
- after 5 seconds anyone, spectators included, can nudge them: their deck
  shakes and knocks on their screen;
- after 30 seconds the host can flip their cards over for them, which counts
  as a flop: two in a row and the room stops waiting for them until they
  slam again, as in a timed game.

A slow stage has no deadline, so the room's alarm is only its idle check,
and with people still connected it looks again every hour. A slow room
saves each slam, so a room woken from hibernation remembers who has
played.

The first player still connected is the host. Up to 50 play (people take
the place of bots in a full lobby) and up to 60 can be connected, the rest
watching; anyone who joins mid-game watches, and is dealt into the next
one. If a player's card flops over by itself twice in a row, the room stops
waiting for them until they slam again. A game with nobody connected waits
for someone to come back. A room deletes itself once nobody has used it for
six hours and nobody is connected; while someone is, its code stays taken.

**States.** A room is `absent`, in the `lobby`, `playing`, `paused` (a game
with nobody connected) or `over`, and makes only the moves listed in
`ROOM_MOVES` in `src/war.js`, all through one function, `go()`.
`ROOM_MESSAGES` says which messages it takes in each. What's stored keeps
its old shape (`phase` and `pausedAt`), so pages and rooms from before still
work.

The rules between `BEGIN WAR CORE` and `END WAR CORE` in `src/war.js` are
also in `war.html`, for solo games; `test/war.test.js` checks the two copies
match.

**Cost.** Rooms are SQLite-backed Durable Objects, as `wrangler.toml`'s
migration asks. A room writes its storage once per battle, except in a
slow game, which saves each slam. Slams in progress also stay on the socket
that made each one, whose attachment survives hibernation, so a room woken
mid-stage still has them (all but one that had to pick up its winnings
first, which flops when time runs out). WebSocket
messages from pages count as one request per 20. A busy evening of games is
well within the plan's included usage.

## Setup

The Cloudflare side is managed with OpenTofu in mwarkentin/infra
(`games.tf` there), not by hand. Its apply makes:

- the D1 database, whose id is already in `wrangler.toml` (it isn't a
  secret);
- an account-owned API token limited to Workers Scripts and D1, stored here
  as the `CLOUDFLARE_API_TOKEN` Actions secret;
- the salt the Worker hashes IP addresses with, stored here as the
  `IP_SALT` Actions secret;
- the `CLOUDFLARE_ACCOUNT_ID` Actions variable.

Until that variable exists, the deploy workflow is skipped and the games
keep their leaderboards hidden. After that:

1. **Deploy:** run the **Deploy leaderboard worker** workflow from the
   Actions tab, or push a change under `worker/`. It applies migrations,
   then deploys with `IP_SALT` as a Worker secret. Wrangler makes the
   Durable Object classes (War's rooms, and the survey's sectors and Atlas)
   from the `[[migrations]]` in `wrangler.toml`, and the survey's
   per-address rate limiters from its `[[ratelimits]]`. The Worker answers at
   `https://api.games.michaelwarkentin.com` (below) and at
   `https://games-leaderboard.mwarkentin.workers.dev`.
2. **The games already point at it:** `LEADERBOARD_URL` in
   `funnels-and-buckets.html`, `doodle-chomp.html` and
   `air-traffic-controller.html`, `ROOMS_URL` in `war.html` and
   `SURVEY_URL` in `letterfield.html`. If the Worker can't be reached they
   say so and carry on. If the URL ever changes, change it there and in
   `WORKER_URL` in `tests/fake_leaderboard.py`, which keeps tests off the
   real Worker.

Don't change the salt or the token here by hand: the next OpenTofu apply
would put them back. To replace the token, see mwarkentin/infra's README.

**Its own domain:** `api.games.michaelwarkentin.com` is a Workers custom
domain, made by OpenTofu in mwarkentin/infra (`worker_domains.tf`) along
with its DNS record and certificate. Wrangler leaves it alone because
`wrangler.toml` declares no `routes`; keep it that way, or wrangler takes
over the Worker's domains and drops this one. The `workers.dev` address
keeps working, and Worker Previews stay on `workers.dev`.

**The share Worker** (`share/`) binds this Worker's `Sector` and `Atlas`
classes directly and asks two internal paths that nothing on the internet
can reach (the router only ever forwards WebSocket upgrades to sectors):
`GET /claim/<key>` on a sector, who charted that word and when, or
`{"error": "not charted"}` with a 404; and `GET /totals` on the Atlas, the
shared map's totals. Keep both answering as they do, or share cards lose
their lines about charting (`share/test/app.test.js` fakes them, and
`test/survey.test.js` tests the real ones).

## Previews

Every pull request whose branch changes `worker/` from `main`'s, stacked
pull requests included, gets a
[Worker Preview](https://developers.cloudflare.com/workers/previews/): its
own copy of the Worker at
`https://pr-<number>-games-leaderboard.mwarkentin.workers.dev`. The
**Preview** workflow (`.github/workflows/preview.yml`) makes it, then builds
the pull request's own copy of the site at
`https://pr-<number>-games-preview.mwarkentin.workers.dev` with its games
pointed at the Worker Preview (see Previews in `AGENTS.md`), comments on the
pull request with both, and deletes both when the pull request closes. It's
the way to try War's rooms or the survey with real phones before merging.

- **One at a time:** Worker Previews are made one after another across pull
  requests, and GitHub keeps only the newest run waiting for that turn. A
  run still waiting when another queues behind it is cancelled, and fails
  (the `worker-cancelled` job) rather than leave its previews quietly out of
  date: re-run it.
- **After closing:** a run that gets its turn after its pull request has
  closed makes nothing, and its site job deletes the Previews in case
  cleanup didn't get to (cleanup shares the site job's group, so one cancels
  the other).

- **Origins:** the Worker Preview allows its own pull request's site
  preview, on top of `ALLOWED_ORIGINS` in `[previews.vars]`: the workflow
  passes the longer list with `--var` to that Preview alone. Production's
  `ALLOWED_ORIGINS` never includes a preview, so previews of pages without a
  Worker Preview can't write to production.

- **Durable Objects** are the Preview's own: its rooms and survey start
  empty and never touch production's, and go when it's deleted.
- **Scores and groups** go to `games-leaderboard-previews`, a database of
  test scores that all Previews share. The workflow applies the branch's
  migrations to it first, with `wrangler.previews-migrations.toml`, since
  `wrangler d1` reads only a config file's top-level databases. A branch's
  migrations stay on it after the branch closes; if that gets in the way,
  empty the database or replace it in mwarkentin/infra.
- **The survey log** goes to `games-survey-log-previews` in the same way,
  shared by every Preview and holding only test words. To give it some
  history to look at, see `bench/seed-log.js` ("Trying it" in SURVEY.md).
- **Settings** aren't inherited: `[previews]` in `wrangler.toml` sets the
  variables, the database, the Durable Object bindings and the rate limits
  (counted apart from production's) again. Keep it in step with the
  production settings above it. Observability is inherited.
- **Secrets:** each Preview gets `PREVIEW_IP_SALT` as its `IP_SALT`, never
  production's salt. Turnstile stays off.

mwarkentin/infra makes the database and the salt. The site previews'
Worker, `games-preview` (`../preview/wrangler.toml`), needs nothing from it
but the same token: the first Preview creates the Worker. Previews are public URLs,
like production's, and only accept writes from `ALLOWED_ORIGINS`. The free
plan keeps up to 100 per Worker, dropping the one deployed to least recently.
To try one by hand from a branch, after applying migrations as the workflow
does:

```sh
cd worker
npx wrangler@4.151.0 preview --name my-branch
npx wrangler@4.151.0 preview delete --name my-branch
```

## Local development

```sh
cd worker
npx wrangler@4.151.0 d1 migrations apply games-leaderboard --local
npx wrangler@4.151.0 d1 migrations apply games-survey-log --local
echo "IP_SALT=dev" > .dev.vars
npx wrangler@4.151.0 dev --port 8787
```

Then serve the games with `python3 -m http.server 8000` from the repo root
and open
`http://localhost:8000/funnels-and-buckets.html?leaderboard=http://localhost:8787`
(or `doodle-chomp.html` or `air-traffic-controller.html` with the same
query), or `http://localhost:8000/war.html?rooms=http://localhost:8787` for
War rooms. `wrangler dev` runs the Durable Objects locally too.
`ALLOWED_ORIGINS` in `wrangler.toml` already allows `localhost:8000`.

Tests run with Node's built-in test runner against a real SQLite database
(node:sqlite stands in for D1 and for the survey's Durable Object storage):

```sh
node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"
```

## Moderation

Remove a score from every board it's on by its `entry` id (shown in API
responses):

```sh
npx wrangler@4.151.0 d1 execute games-leaderboard --remote \
  --command "DELETE FROM scores WHERE entry = '<uuid>'"
```

Delete a group and its scores (its members then see "That group doesn't
exist any more"):

```sh
npx wrangler@4.151.0 d1 execute games-leaderboard --remote \
  --command "DELETE FROM scores WHERE scope = 'K7QP'; DELETE FROM groups WHERE code = 'K7QP'"
```

To add a word to the initials blocklist, edit `BLOCKED_INITIALS` in
`src/leaderboard.js`.

If the database ever grows too big, delete scores older than a year that
aren't in their board's all-time top 100:

```sh
npx wrangler@4.151.0 d1 execute games-leaderboard --remote --command "
  DELETE FROM scores WHERE created_at < (unixepoch('now', '-1 year') * 1000) AND id NOT IN (
    SELECT id FROM (SELECT id, ROW_NUMBER() OVER (
      PARTITION BY game, scope, difficulty, mode ORDER BY score DESC, created_at, id) AS n FROM scores)
    WHERE n <= 100)"
```

## Adding another game

Add an entry to `GAMES` in `src/leaderboard.js` with its difficulties and
modes and a `check()` that rejects scores the game couldn't produce, plus
tests in `test/leaderboard.test.js`. The game then calls the same endpoints
with its own `game` name. Groups aren't tied to a game, so a family's group
works in every game that has a leaderboard.
