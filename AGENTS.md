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
  The build also generates `index.html`, `colophon.html`, `sitemap.xml`,
  `games.json` and each page's web app manifest, so don't create those by
  hand. Games are published as committed, apart from `telemetry.js`,
  `analytics.js` and the home-screen app links (see below).
- `TIP_URL` in `scripts/common.py`: the Stripe Payment Link for tips. Once
  it's set, the header of the home page and colophon link to it as "Tip
  jar", tagged with `client_reference_id=games-home` or `games-colophon` so
  each payment shows where it came from. Games themselves get no link,
  since they own the whole screen.
- `telemetry.js`: error reporting, performance and session replays through
  Sentry. The build inlines it into every game's `<head>`.
- `analytics.js`: page views through Counterscale. The build inlines it into
  every page's `<head>`, the home page and colophon included.
- `sw.js`: the service worker that keeps every page working offline. The
  build fills in its list of pages and a version.
- `icons/`: each app's icon, drawn as `<app>.svg` and rendered to the PNGs
  beside it by `scripts/render_icons.py`.
- `music/`: public-domain MIDI files that games play, with a README of where
  each came from. The build publishes them as they are.
- `tests/`: pytest with Playwright.
- `worker/`: the leaderboard API, a Cloudflare Worker with a D1 database,
  which also runs War's multiplayer rooms and Letterfield's shared survey as
  Durable Objects (see `worker/SURVEY.md`, and `worker/TURNSTILE.md` for its
  optional bot check). It deploys through its own
  workflow and is never part of the site. See
  `worker/README.md`.

## Rules for every game

- One `.html` file with inline `<style>` and vanilla JavaScript. No React,
  no JSX, no npm, no build step. A game can run to a couple of thousand
  lines; keep it in one file anyway.
- Load libraries from `cdn.jsdelivr.net` or `cdnjs.cloudflare.com`, pinned
  to an exact version. Fonts may come from Google Fonts, with a system font
  later in every `font-family` so the game still works without them. The
  only other hosts are `browser.sentry-cdn.com`, for `telemetry.js`,
  Counterscale's own address, for `analytics.js`, and
  `challenges.cloudflare.com`, for Turnstile on Letterfield's shared survey
  (loaded only once `TURNSTILE_SITE_KEY` is set, never cached by `sw.js`;
  see `worker/TURNSTILE.md`).
- Phone first: playable at 375px wide in portrait with touch alone (an
  on-screen pad, taps or swipes), and with a keyboard on a computer. No
  sideways scrolling. Inputs, textareas and selects use `font-size: 16px`
  or larger so iOS doesn't zoom.
- The game owns the whole screen: use `viewport-fit=cover` and keep
  controls clear of `env(safe-area-inset-*)`.
- Respect `prefers-reduced-motion` and `prefers-color-scheme`. Give sound an
  off switch, and start audio only after the player's first tap or key.
- Music gets an off switch of its own, apart from sound effects. Play it
  from MIDI files in `music/` on voices made in the page, as War does (its
  Music section): notes, not recordings, so it's small and works offline.
  Only public-domain or CC0 pieces, each listed in `music/README.md` with
  its source at a fixed commit; `tests/test_music.py` checks.
  Ambient music with no tune to score, like Letterfield's drones and pads,
  can instead be generated in the page with the Web Audio API, still with
  no audio files.
- Pause when the tab is hidden (`visibilitychange`) if the game runs on a
  timer.
- Keep scores and settings in `localStorage`, with keys prefixed by the
  game's name: every game on this site shares one origin. Global
  leaderboards go through the leaderboard Worker (see below), never straight
  from the page to a database.
- The `<head>` has a `<title>`, a viewport meta tag and a one-sentence
  `<meta name="description" content="...">`. The index and colophon show
  that description.
- The `<head>` also has a `<meta name="theme-color">` matching the game's
  background (a light and a dark one if it has both, light first). If the
  title is longer than 12 characters, add
  `<meta name="apple-mobile-web-app-title" content="...">` with a shorter
  name for the Home Screen.

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

## Analytics

`analytics.js` counts page views with
[Counterscale](https://counterscale.dev), which runs on our Cloudflare
account (installed with its own CLI, not from this repo). It does nothing
until `COUNTERSCALE_URL` is set, and only runs on games.michaelwarkentin.com.
It loads Counterscale's tracker from jsDelivr with an integrity hash, so to
update it change the version and the hash together (the same `openssl`
command as for Sentry's SDK), and keep it on the version the Counterscale
install runs.

Each page view sends the page's path, never its query string or fragment
(which can hold group invite codes), and the other site a visitor came from
as its origin only; moves within the site have no referrer. Counterscale adds
the browser and device from the user agent and the country from the IP
address, which it doesn't keep, and sets no cookies. The tracker's own
defaults would read a referrer and UTM tags from the query string and watch
`history.pushState`, so keep passing it `url`, `referrer` and
`autoTrackPageviews: false`. `tests/test_analytics.py` checks all of this
against a fake Counterscale.

## Home-screen apps

Every page can be added to a phone's Home Screen and keeps working offline.
`scripts/build_pwa.py` gives each game a manifest of its own
(`/manifests/<game>.webmanifest`, scoped to the game), so adding a game makes
an app that opens straight into it. The home page and colophon share one for
the whole site (`index`), which opens at the game list. Names, descriptions
and colors come from each game's `<head>`.

The build links each page to its manifest and icons and registers `sw.js`.
It stores every page, and the music in `music/`, when it installs. After
that, pages come from the network first and fall back to the stored copy
when the network fails or takes more than four seconds; music comes from the
stored copy. Google Fonts are stored too. Nothing else goes through it, so
the leaderboard, War's rooms, Sentry and Counterscale behave as they would
without it. A hash of the pages and music is the worker's version, so each
deploy refreshes every stored copy.

Each app's icon is `icons/<app>.svg`, a full-bleed 512×512 square with
everything that matters inside the middle circle (radius 205), drawn with
shapes rather than text. Run `uv run scripts/render_icons.py` after drawing
or changing one and commit the PNGs: the deploy has no browser to render
them, and `tests/test_pwa.py` fails if they're out of date. A game without
an icon is deployed with the site's.

The other tests block service workers so `page.route` sees every request;
`tests/test_pwa.py` allows them. A service worker's own requests ignore
`context.set_offline`, so to test offline, abort the site's requests with
`context.route`.

iPhones keep a Home Screen app's `localStorage` apart from Safari's, so
scores, groups and initials saved in Safari don't carry over to it.

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
  `tests/test_doodle_chomp_leaderboard.py`. Every test's browser context
  also answers the real Worker's URL (`WORKER_URL` there) with an empty
  fake, so no test touches real scores; `without_worker()` serves a game
  with its URL blanked, to test it without a leaderboard.
- The Worker answers at `https://games-leaderboard.mwarkentin.workers.dev`.
  Its credentials (the `CLOUDFLARE_API_TOKEN` and `IP_SALT` secrets and the
  `CLOUDFLARE_ACCOUNT_ID` variable) are made and set by OpenTofu in
  mwarkentin/infra, live only there, in GitHub and in Cloudflare, and never
  in this repo.

## Multiplayer rooms

War plays live with friends through the same Worker: each room is a Durable
Object that holds the game and every player's WebSocket (`worker/src/war.js`).

- A `ROOMS_URL` constant holds the Worker's URL. While it's empty, playing
  with friends stays hidden and the game is solo only. `?rooms=<url>`
  overrides it for local testing and for tests.
- The room is in charge: it deals, waits for slams and plays every battle,
  and the page only shows what it's told. Solo games run the same rules in
  the page. The rules sit between `BEGIN WAR CORE` and `END WAR CORE`
  markers, word for word the same in `war.html` and `worker/src/war.js`, and
  `worker/test/war.test.js` checks they match, so change both.
- Rooms have four-character codes from the same alphabet as groups, and
  invite links are `?room=<code>`. Players rejoin their seat with a random
  token kept in `localStorage` (`war:token`).
- Game tests fake a room with Playwright's `page.route_web_socket` and
  `tests/fake_war_room.py`; see `tests/test_war_rooms.py`.

## Adding or changing a game

1. Create or update `foo.html` following the rules above.
2. Link it from `README.md` under the right heading:
   `- [Title](https://games.michaelwarkentin.com/foo): what it is`.
3. Draw its icon as `icons/foo.svg` and run `uv run scripts/render_icons.py`
   (see Home-screen apps).
4. Add `tests/test_foo.py` that starts the game and plays a little: press
   Start, make a move, check the score or board changed. A debug hook such
   as Funnels & Buckets' `#debug` / `window.__fb` makes this much easier.
   `tests/test_games.py` already smoke-tests every game.
5. Run `uv run pytest` and make sure it passes.
6. In the commit message, say what changed and include the URL of the chat,
   artifact or agent session behind it.

## Commands

```sh
uv run playwright install chromium   # once
uv run pytest                        # builds the site into a temp dir, then tests it
node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"   # the leaderboard Worker
uv run ./build.sh && python3 -m http.server -d _site 8000   # preview the real site
uv run scripts/render_icons.py       # after drawing or changing an icon
```

The smoke tests load every game at phone and desktop sizes and fail on
console errors, uncaught exceptions, failed requests, sideways scrolling or
text inputs under 16px. They also check the `<head>` metadata, CDN version
pins and the README link.

In a Claude Code on the web sandbox, the default network policy can block
`cdn.jsdelivr.net`, `cdnjs.cloudflare.com`, `fonts.googleapis.com`,
`fonts.gstatic.com`, `browser.sentry-cdn.com`, `cdn.playwright.dev` and
`registry.npmjs.org` (for `wrangler`). A test failing with
`Failed: https://...` for one of those hosts means the sandbox can't reach
it, not that the game is broken. Ask for those hosts to be allowed. CI has
full network access.

## Security

This repo is public. Keep secrets, internal hostnames and work specifics out
of games, tests and commit messages, and never host someone else's HTML here.
