# Leaderboard worker

A [Cloudflare Worker](https://developers.cloudflare.com/workers/) with a
[D1](https://developers.cloudflare.com/d1/) (SQLite) database that stores
global high scores for the games. It runs on Cloudflare's free plan: the
leaderboard uses a handful of requests and database rows per game played.

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

D1 counts every row a query scans against the free plan's 5 million a day,
so each view reads through an index of its own (named with `INDEXED BY` in
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
Worker: the runtime treats every export of the main module as an entry
point, so constants exported for tests can't live there.

## Setup

Everything below is done once. Until step 5, the deploy workflow is skipped
and the games keep their leaderboards hidden.

1. **Create a Cloudflare account** at https://dash.cloudflare.com/sign-up
   (the free plan is enough) and note your **account ID** from the dashboard.
2. **Create the database.** From this `worker/` folder:

   ```sh
   npx wrangler@4.151.0 login
   npx wrangler@4.151.0 d1 create games-leaderboard
   ```

   Copy the `database_id` it prints into `wrangler.toml`, replacing the
   placeholder `00000000-0000-0000-0000-000000000000`, and commit it. The id
   is not a secret.
3. **Set the IP hashing salt**, any long random string:

   ```sh
   npx wrangler@4.151.0 secret put IP_SALT
   ```

4. **Create an API token** at https://dash.cloudflare.com/profile/api-tokens:
   start from the **Edit Cloudflare Workers** template and add the
   **Account → D1 → Edit** permission.
5. **Give GitHub the credentials.** In this repo's Settings → Secrets and
   variables → Actions:
   - Secret `CLOUDFLARE_API_TOKEN`: the token from step 4.
   - Variable `CLOUDFLARE_ACCOUNT_ID`: your account ID.
6. **Deploy:** run the **Deploy leaderboard worker** workflow from the
   Actions tab, or push a change under `worker/`. It applies migrations, then
   deploys. The Worker's URL appears in the log, for example
   `https://games-leaderboard.<your-subdomain>.workers.dev`.
7. **Point the games at it:** set `LEADERBOARD_URL` in
   `funnels-and-buckets.html`, `doodle-chomp.html` and
   `air-traffic-controller.html` to that URL and merge.

Optional: serve the Worker from your own domain (such as
`api.games.michaelwarkentin.com`) under the Worker's Settings → Domains &
Routes. That needs the domain's DNS on Cloudflare; the `workers.dev` URL
works without it.

## Local development

```sh
cd worker
npx wrangler@4.151.0 d1 migrations apply games-leaderboard --local
echo "IP_SALT=dev" > .dev.vars
npx wrangler@4.151.0 dev --port 8787
```

Then serve the games with `python3 -m http.server 8000` from the repo root
and open
`http://localhost:8000/funnels-and-buckets.html?leaderboard=http://localhost:8787`
(or `doodle-chomp.html` or `air-traffic-controller.html` with the same
query).
`ALLOWED_ORIGINS` in `wrangler.toml` already allows `localhost:8000`.

Tests run with Node's built-in test runner against a real SQLite database
(node:sqlite stands in for D1):

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
