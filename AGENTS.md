# AGENTS.md

This repo is the source of [games.michaelwarkentin.com](https://games.michaelwarkentin.com):
small browser games, published by GitHub Pages on every push to `main`. Its
sibling, [mwarkentin/tools](https://github.com/mwarkentin/tools), holds
utilities; games live here so they get their own origin and their own rules.

## Layout

- `*.html` at the top level: one file per game. The filename is the URL:
  `foo.html` is served at `/foo`.
- `README.md`: the game list. The build turns it into `index.html`.
- `build.sh` and `scripts/`: assemble the site in `_site/` (never committed).
  The build also generates `index.html`, `colophon.html`, `sitemap.xml` and
  `games.json`, so don't create those by hand. Games are published as
  committed, apart from `telemetry.js` (see below).
- `telemetry.js`: error reporting, performance and session replays through
  Sentry. The build inlines it into every game's `<head>`.
- `tests/`: pytest with Playwright.
- `worker/`: the leaderboard API, a Cloudflare Worker with a D1 database,
  and Letterfield's shared survey (Durable Objects; see `worker/SURVEY.md`).
  It deploys through its own workflow and is never part of the site. See
  `worker/README.md`.

## Rules for every game

- One `.html` file with inline `<style>` and vanilla JavaScript. No React,
  no JSX, no npm, no build step. A game can run to a couple of thousand
  lines; keep it in one file anyway.
- Load libraries from `cdn.jsdelivr.net` or `cdnjs.cloudflare.com`, pinned
  to an exact version. Fonts may come from Google Fonts, with a system font
  later in every `font-family` so the game still works without them. The one
  other host is `browser.sentry-cdn.com`, for `telemetry.js` only.
- Phone first: playable at 375px wide in portrait with touch alone (an
  on-screen pad, taps or swipes), and with a keyboard on a computer. No
  sideways scrolling. Inputs, textareas and selects use `font-size: 16px`
  or larger so iOS doesn't zoom.
- The game owns the whole screen: use `viewport-fit=cover` and keep
  controls clear of `env(safe-area-inset-*)`.
- Respect `prefers-reduced-motion` and `prefers-color-scheme`. Give sound an
  off switch, and start audio only after the player's first tap or key.
- Pause when the tab is hidden (`visibilitychange`) if the game runs on a
  timer.
- Keep scores and settings in `localStorage`, with keys prefixed by the
  game's name: every game on this site shares one origin. Global
  leaderboards go through the leaderboard Worker (see below), never straight
  from the page to a database.
- The `<head>` has a `<title>`, a viewport meta tag and a one-sentence
  `<meta name="description" content="...">`. The index and colophon show
  that description.

## Telemetry

`telemetry.js` sends errors, performance traces and session replays to
Sentry. It does nothing until `SENTRY_DSN` is set, and only runs on
games.michaelwarkentin.com, so local previews and tests send nothing. It
loads Sentry's SDK from `browser.sentry-cdn.com`, pinned to a version with
an integrity hash; to update it, change both URLs and both hashes
(`curl -s <url> | openssl dgst -sha384 -binary | openssl base64 -A`).

Everything it sends is labelled with the game's name, taken from the URL: a
`game` tag on errors and replays, and a `game` attribute on trace spans.
Filter on that rather than splitting games into projects or environments.

Replays show what was on screen, canvases and leaderboards included, with
text inputs masked. To hide something else from replays, give it the
`sentry-mask` class. IP addresses aren't sent. `tests/test_telemetry.py`
serves the site under its real hostname to check that it reports errors
with a replay and never sends anything from elsewhere.

## Games that started as claude.ai artifacts

An artifact may call `window.claude` for shared storage or sign-in. That
never exists on this site, so every such call must sit behind a feature
check and fall back to `localStorage` (Letterfield's field notes already
do). Shared high scores go through the leaderboard Worker instead (see
below). When bringing a new artifact over:

1. Read it with the Artifact tool, then move the `<title>`, `<link>` and
   first `<style>` tags the artifact service leaves at the top of `<body>`
   into a proper `<head>`, and add the description.
2. Drop `<meta name="claude:viewport-fit-sides">`; nothing here reads it.
3. Put the artifact's URL in the commit message so the colophon links back
   to it.

## Leaderboards

Global high scores live in the Worker under `worker/`, which checks every
score before saving it. Funnels & Buckets, Doodle Chomp and Air Traffic
Controller take part like this:

- A `LEADERBOARD_URL` constant holds the Worker's URL. While it's empty the
  leaderboard stays hidden, so a game works the same without it.
  `?leaderboard=<url>` overrides it for local testing and for tests.
- `GET /v1/scores?game=<game>&scope=<*|group code>&difficulty=<d|all>&mode=<m|all>&since=<ms>`
  reads the top 10 for a view. `POST /v1/scores` saves three-letter initials
  with the score, enough detail for the Worker's plausibility check, the
  player's group codes and whether it also goes on the public board. Send
  POSTs as JSON with `Content-Type: text/plain` to avoid a CORS preflight.
- Every score is kept, and views cover Today, This week, This month or All
  time (This week by default). The page sends `since`, the start of the
  period in the player's own time zone (Monday for weeks), on views and on
  saves, so the reply ranks the score for that period too.
- Split scores so they compare fairly (Funnels & Buckets files them by
  number range as difficulty and extra easy as mode; Air Traffic Controller
  by shift and the slowest radar sweep used), and keep practice variants off
  the board. Offer views that narrow to either or show all. A game without
  a points score encodes its ranking in one (see Air Traffic Controller in
  `GAMES`).
- Groups are private boards shared by a four-character code: `POST
  /v1/groups` starts one and `GET /v1/groups/<code>` looks one up. Invite
  links are `?join=<code>`. Groups work across games, so the joined groups
  (`games.groups`), the player's initials (`games.initials`) and their
  public-board choice (`games.public`) are shared `localStorage` keys
  without a game prefix.
- If the Worker can't be reached, say so in one line and let the game carry
  on.
- Add the game's difficulties, modes and a `check()` to `GAMES` in
  `worker/src/leaderboard.js`, with tests in `worker/test/`. Game tests fake
  the API with Playwright's `page.route` and `tests/fake_leaderboard.py`; see
  `tests/test_doodle_chomp_leaderboard.py`.
- Credentials live only in GitHub (the `CLOUDFLARE_API_TOKEN` secret and the
  `CLOUDFLARE_ACCOUNT_ID` variable) and in Cloudflare, never in the repo.

## Adding or changing a game

1. Create or update `foo.html` following the rules above.
2. Link it from `README.md` under the right heading:
   `- [Title](https://games.michaelwarkentin.com/foo): what it is`.
3. Add `tests/test_foo.py` that starts the game and plays a little: press
   Start, make a move, check the score or board changed. A debug hook such
   as Funnels & Buckets' `#debug` / `window.__fb` makes this much easier.
   `tests/test_games.py` already smoke-tests every game.
4. Run `uv run pytest` and make sure it passes.
5. In the commit message, say what changed and include the URL of the chat,
   artifact or agent session behind it.

## Commands

```sh
uv run playwright install chromium   # once
uv run pytest                        # builds the site into a temp dir, then tests it
node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"   # the leaderboard Worker
uv run ./build.sh && python3 -m http.server -d _site 8000   # preview the real site
```

The smoke tests load every game at phone and desktop sizes and fail on
console errors, uncaught exceptions, failed requests, sideways scrolling or
text inputs under 16px. They also check the `<head>` metadata, CDN version
pins and the README link.

In a Claude Code on the web sandbox, the default network policy can block
`cdn.jsdelivr.net`, `cdnjs.cloudflare.com`, `fonts.googleapis.com`,
`fonts.gstatic.com`, `browser.sentry-cdn.com`, `cdn.playwright.dev`,
`registry.npmjs.org` (for `wrangler`) and the leaderboard Worker's host. A
test failing with `Failed: https://...` for one of those hosts means the
sandbox can't reach it, not that the game is broken. Ask for those hosts to
be allowed. CI has full network access.

## Security

This repo is public. Keep secrets, internal hostnames and work specifics out
of games, tests and commit messages, and never host someone else's HTML here.
