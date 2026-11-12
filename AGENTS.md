# AGENTS.md

This repo is the source of [games.michaelwarkentin.com](https://games.michaelwarkentin.com):
small browser games, published by GitHub Pages on every push to `main`. Its
sibling, [mwarkentin/tools](https://github.com/mwarkentin/tools), holds
utilities; games live here so they get their own origin and their own rules.

## Layout

- `*.html` at the top level: one file per game. The filename is the URL:
  `foo.html` is served at `/foo`. A page that belongs to a game rather than
  being one, like `letterfield-log.html` (the survey's history), is built and
  tested the same way but says `<meta name="games:app" content="letterfield">`:
  it joins that game's home-screen app, so it needs no icon or manifest of
  its own and its path must start with the game's (see `app_of` in
  `scripts/common.py`).
- `README.md`: the game list. The build turns it into `index.html`.
- `changelog/`: each game's changelog for players, `<game>.md`, which the
  build turns into `/changelog/<game>` (see Changelogs).
- `build.sh` and `scripts/`: assemble the site in `_site/` (never committed).
  The build also generates `index.html`, `colophon.html`, the changelog
  pages, `sitemap.xml`, `games.json` and each page's web app manifest, so
  don't create those by hand. Games are published as committed, apart from
  link-preview tags, `telemetry.js`, `feedback.js`, `analytics.js` and the
  home-screen app links (see below).
- `TIP_URL` in `scripts/common.py`: the Stripe Payment Link for tips. Once
  it's set, the header of the home page, colophon and changelogs link to it
  as "Tip jar", tagged with `client_reference_id=games-home`,
  `games-colophon` or `games-changelog` so each payment shows where it came
  from. Games themselves get no link, since they own the whole screen.
- `telemetry.js`: error reporting, performance and session replays through
  Sentry. The build inlines it into every game's `<head>`.
- `feedback.js`: the "Send feedback" dialog (see Feedback). The build inlines
  it into every game's `<head>`.
- `analytics.js`: page views through Counterscale. The build inlines it into
  every page's `<head>`, the home page, colophon and changelogs included.
- `sw.js`: the service worker that keeps every page working offline. The
  build fills in its list of pages and a version.
- `previews/`: link-preview images, `<game>.jpg` at 1200×630 (see Link
  previews).
- `icons/`: each app's icon, drawn as `<app>.svg` and rendered to the PNGs
  beside it by `scripts/render_icons.py`.
- `music/`: public-domain MIDI files that games play, with a README of where
  each came from. The build publishes them as they are.
- `tests/`: pytest with Playwright.
- `worker/`: the leaderboard API, a Cloudflare Worker with a D1 database,
  which also runs War's multiplayer rooms and Letterfield's shared survey as
  Durable Objects (see `worker/SURVEY.md`, and `worker/TURNSTILE.md` for its
  optional bot check). It deploys through its own
  workflow and is never part of the site. A pull request that changes it
  gets a Worker Preview of its own (see Previews below, and in
  `worker/README.md`).
- `share/`: the `games-share` Worker, which draws link-preview cards for
  shared Letterfield finds (see Share cards). It deploys through its own
  workflow, has the repo's one npm dependency, and is never part of the site.
- `preview/`: the `games-preview` Worker, which has no code and serves each
  pull request's build of the site as a Worker Preview (see Previews). It's
  never deployed to production.

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
- Give players one "Send feedback" link marked `data-feedback` (see
  Feedback, under Telemetry).
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
- Keep each mode the game can be in (its screens, a save in flight, a
  connection) in an explicit state machine, not in flags (see State
  machines).

## State machines

A game is always in one of a few modes: on the menu, playing, paused or
over; a score offered, saving or saved; a socket connecting, open or
reconnecting. The bugs that hurt players most have come from modes kept
implicitly, spread over booleans, `hidden` attributes and the order things
happen in, where a timer, a reply or a key press lands after the player has
moved on. So a mode with more than two states, or one that waiting work
(timers, fetches, sockets) can move, lives in an explicit state machine:

```js
const Screen = machine('screen', {
  menu: ['playing'],
  playing: ['paused', 'ending'],
  paused: ['playing', 'menu'],
  ending: ['over'],
  over: ['playing', 'menu'],
}, 'menu', { onMove: showScreen });
```

- `machine()` is a few lines kept between `BEGIN STATE MACHINE` and `END
  STATE MACHINE` markers, the same in every page that uses it.
  `tests/test_state_machines.py` checks the copies match and that the helper
  keeps its promises, so change every copy together.
- The table is the one place to see how a game flows. `go(to)` makes a
  listed move and nothing else. Any other move is a bug: it's refused with a
  console error, which fails the tests, while the player carries on.
- Guard a move by the states it may start from, then make it:
  `if (!Screen.is('paused')) return;` and then `Screen.go('playing')`. Read
  the state with `is()` or `.state`, never a flag of your own.
- Derive what follows from the state in `onMove`, in one place: which
  overlay shows, which layer is `inert` (only the top one takes focus and
  taps), the wake lock. Don't toggle those wherever the state changes.
- Anything that waits checks nothing moved before it acts: keep
  `const at = Machine.seq`, and give up if `Machine.seq !== at` when the
  timer fires or the reply comes back, or check `is()` for the state it
  expects.
- The state shows as a `data-` attribute on `<html>`, named after the
  machine: `<html data-screen="over" data-save="offered">`. CSS can style
  by it, and tests and agents can read it without knowing the code:
  `expect(page.locator("html")).to_have_attribute("data-screen", "over")`.
  A machine for one element of many passes `el` to show it there instead,
  or `el: null` for nowhere. Debug hooks report each machine's state too.
- A fix for a state machine bug comes with a test that fails without it,
  failing at the bug itself rather than at a missing `data-` attribute.
  `Held` in `tests/fake_leaderboard.py` holds back replies to answer them
  later in any order, for testing what a page does while a request is out
  (set its `holding` or `match` as the test goes to choose which). Remember
  the page's 30-second cache of scores: hold from the start, or a list it
  already has never asks. For sockets, the fakes in `tests/` hold or drop
  messages from the test itself: a blocking `WebSocketRoute` call, such as
  `close()`, inside a `route_web_socket` handler spins forever.
- Leave alone modes that are fine as they are: a single boolean, a
  countdown in game time, a request counter that keeps only the newest
  reply, a render that checks its run number after each await.

The machines each page keeps:

| Page | Machine (`data-` name) | States |
|---|---|---|
| `air-traffic-controller.html` | `screen` | menu, playing, paused, ending, report, board |
| | `save` (the shift report's offer) | none, checking, ineligible, offered, saving, saved |
| `doodle-chomp.html` | `screen` | menu, play, paused, message, clearing, over |
| | `save` (the game-over card's offer) | none, checking, ineligible, offered, saving, saved |
| | `board` (the high-score screen) | closed, open |
| `funnels-and-buckets.html` | `screen` | menu, playing, paused, ending, over |
| | `save` (the game-over card's offer) | none, checking, ineligible, offered, saving, saved |
| | `board` (the leaderboard screen) | closed, open |
| `letterfield.html` | `intro` (the card over the map at the start) | sign, coach, exploring |
| | `pass` (the survey's Turnstile pass) | off, none, loading, checking, asking, sending, good, failed |
| | `link` (each sector's socket; `el: null`, see `__lf.linkStates()`) | connecting, open, live, backoff, closed |
| | `claim` (each claim of ours; `el: null`, see `__lf.outbox()`) | queued, sent, unanswered, answered |
| | `define` (each found word's meaning; `el: null`, see `__lf.definitions()`) | loading, ready, none, failed |
| `letterfield-log.html` | `log` (what the page shows) | loading, ready, refreshing, stale, failed |
| `war.html` | `screen` | menu, lobby, table, ending, over |
| | `overlay` (what covers the screen) | none, pause, invite, styles, history |
| | `session` (what the page plays through) | none, joining, solo, room |
| | `conn` (a room's WebSocket) | off, connecting, open, retrying |
| | `spoils` (the show for a war won) | none, haul, report, lite, leaving |

The Worker keeps its modes the same way, without the page helper: a
declared table of states and moves, one function that makes every move,
and a state read from what's stored, so an object woken from hibernation,
or a record saved by an earlier version, comes back in the state it left.
War rooms keep theirs in `worker/src/war.js`: `ROOM_MOVES` (absent, lobby,
playing, paused, over) and `ROOM_MESSAGES` (which messages each state
takes), with `roomState()`, `go()` and `deadline()`, outside the War core.
A refused move logs an error, and `worker/test/war.test.js` fails on it.
Anything a woken object must still know lives in storage or a socket's
attachment, never only in a field. Something an object only knows once
another has told it, like a sector's list of addresses past the daily cap,
treats "not known since waking" as a state of its own, never as "none".
And work that waited (an alarm, another object's reply, a message that
arrives after its moment) checks the state it expects before it acts: an
alarm works out `deadline()` again, and a slam for a stage already played
out is dropped.

## Changelogs

The colophon shows every commit, for whoever works on the games. Each game's
changelog, `changelog/<game>.md`, is for players: what changed that they'd
notice, in a sentence or two each, without file names or internals. A page
that belongs to a game, like `letterfield-log.html`, goes in that game's.

```markdown
## 2026-11-06

- Music from public-domain scores, with its own off switch.

## 2026-11-03

- Seven deck themes to pick from.
```

A day is the date the change reached the site (when it merged to `main`),
newest first and one heading a day. Changes still switched off on the site,
like a leaderboard before its URL is set, wait for the day they're switched
on. `scripts/build_changelog.py` builds `/changelog/<game>` from it, and
fails the build on text before the first day, a heading that isn't a date,
an empty day or days out of order. The home page's recent dates and the
colophon link to it. `tests/test_changelog.py` checks every game has one.

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

### Feedback

Every game has one "Send feedback" link, somewhere a player finds it
without it covering the game (the menu, or Letterfield's field notes):

```html
Found a bug or have an idea? <a href="https://github.com/mwarkentin/games/issues/new/choose" target="_blank" rel="noopener" data-feedback>Send feedback</a>
```

Without JavaScript it goes to the repo's issue forms
(`.github/ISSUE_TEMPLATE/`). With it, `feedback.js` opens a dialog instead,
which keeps its keys, taps and clicks from reaching the game:

- **Once Sentry's SDK has loaded,** it's a form that sends the message and
  an optional email to Sentry's User Feedback with the replay's last minute
  (`Sentry.captureFeedback`, in every CDN bundle). Sentry's own feedback
  button isn't used: games own the whole screen.
- **Either way,** it links to the Bug and Idea forms, filled in through the
  URL by their fields' ids: the game (the page's `<title>` up to any colon),
  the device and browser, and details (the address without its query string,
  which can hold invite codes, each machine's state, the window, the version
  and the user agent). From the Sentry form, the links also carry what was
  typed and the replay's id, and send the replay so far. GitHub only fills
  in text fields, so the forms ask for the game as text, not from a list.

A click meant for a new tab goes straight to the issue forms. The header of
the home page, colophon and changelogs links to them as "Feedback".
`tests/test_feedback.py` checks the dialog and that the forms have the
fields it fills in; `tests/test_build.py` that every game has the link;
`tests/test_telemetry.py` the Sentry form.

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

## Link previews

The build adds Open Graph and Twitter card tags to every page
(`inject_social` in `scripts/common.py`), so a link shared in Slack,
iMessage, Bluesky, Mastodon, Threads or Reddit shows a card. The title and
description come from the page's own `<head>`, and every URL is absolute,
built from `BASE_URL`.

- A game with `previews/<game>.jpg` gets a large card with that image. Make
  it 1200×630 and under 300 KB, since WhatsApp shows no image for bigger
  ones; `tests/test_build.py` checks both. Each game's is a screenshot taken
  mid-play at 2× with the game's real fonts, then scaled down. Shoot at a
  1200×630 window, or a wider one of the same shape (War's is 1440×756) if
  the game is cramped at that height.
- A game without one gets a small card with its 512px icon. The home page
  and colophon use `previews/index.jpg` if there is one, or the site's icon.
- A page that writes its own `og:title` keeps its own tags.

### Share cards

A page's preview is fixed, and a Letterfield find's word lives in the
`#fragment`, which no server sees. So a shared find links to the share
Worker instead (`share/`, at `share.michaelwarkentin.com`): a small page whose
`og:image` is a card it draws of that word, which sends people on to
`/letterfield#f-…`. `docs/link-previews.md` has the research and decisions
behind it, and `share/README.md` how it works.

- A `SHARE_URL` constant in `letterfield.html` holds the Worker's address.
  While it's empty, Share hands out the game's own fragment link.
  `?share=<url>` overrides it for tests. A dark page hands out `/f/d/…`, so
  the card follows the sharer's theme.
- The survey log's views (a surveyor's, theme's or territory's page) have
  cards too, at `/v/…`: `letterfield-log.html` has a `SHARE_URL` of its own,
  and while it's empty Share links to the page and attaches the page's own
  picture. Their numbers come from the leaderboard Worker's log answers,
  through a service binding (`LOG` in `share/wrangler.toml`), and their
  addresses pin the period by its first day and its UTC hours, so the page's
  `viewPath()` and `share/src/view.js` must agree.
- The Worker checks the word is on the map with `worker/src/`'s own code,
  asks the word's sector who charted it and the Atlas how much of the shared
  map is charted (internal paths on the leaderboard Worker's Durable
  Objects), and draws the card with `@resvg/resvg-wasm`. Its colours are
  `letterfield.html`'s; `share/test/card.test.js` checks they still match.
- A pull request that changes `share/` gets a Worker Preview of it (see
  Previews), and `scripts/point_preview.py` points `SHARE_URL` at that,
  whose pages send people to the site preview. Other previews blank
  `SHARE_URL`, so their shares stay on the preview. `without_worker()`
  blanks it too.

## Previews

Every pull request gets its own copy of the whole site, built from its
branch, at `https://pr-<number>-games-preview.mwarkentin.workers.dev`, so
it can be played on a phone before merging. The **Preview** workflow
(`.github/workflows/preview.yml`) makes it on each push, comments on the pull
request with its link and the games the pull request changes (one comment,
kept up to date), and deletes it when the pull request closes.

- **Hosting:** a [Worker Preview](https://developers.cloudflare.com/workers/previews/)
  of `games-preview` (`preview/wrangler.toml`), a Worker with nothing but
  static assets: the workflow runs `build.sh`, then `wrangler preview` uploads
  `_site/`. `/war` serves `war.html`, as on GitHub Pages. It uses the same
  Cloudflare token as the leaderboard Worker.
- **Its own URLs:** `scripts/point_preview.py` rewrites the built site so the
  live site's address (link previews, the sitemap, the game list) becomes
  the preview's. Games need nothing for this; just keep naming the Worker
  by its full URL (`WORKER_URL` in `scripts/common.py`). It also puts a
  yellow strip atop the preview's home page, colophon and changelogs naming the pull
  request and commit, linked to the pull request; games get none, but
  every page's `<title>` starts with "PR <number> · ", so a game's tab
  says it's a preview too.
- **The Worker:** a pull request whose branch changes `worker/` (or
  `preview.yml`) from `main`'s also gets a Worker Preview of the leaderboard Worker, made first, and
  `point_preview.py` points the games' `LEADERBOARD_URL`, `ROOMS_URL` and the
  survey log's `SURVEY_URL` at it, so the preview's War rooms, leaderboards
  and survey log run against the pull request's own Worker. That Preview
  also allows the site preview's origin in `ALLOWED_ORIGINS`, passed with
  `--var` for that Preview only; `wrangler.toml` doesn't change.
  Letterfield's survey still needs `?survey=`, which the comment links to.
  It's `main` it compares against, not the pull request's base, so one
  stacked on another pull request's branch gets a Worker Preview of its own
  when that branch changes the Worker, built from everything it carries.
  To try pages that need the Worker without changing it, such as
  Letterfield's log, label the pull request `worker-preview`: adding the
  label makes the previews again, with a Worker Preview.
- **Without one,** the preview keeps production's Worker, which only answers
  the live site's origin: leaderboards say they can't be reached and War's
  rooms can't start, and a preview can never write to production. Solo play
  is unaffected.
- **The share Worker:** a pull request whose branch changes `share/` or
  `worker/src/` (whose code it bundles), or `preview.yml`, from `main`'s gets
  a Worker Preview of `games-share` too, at
  `https://pr-<number>-games-share.mwarkentin.workers.dev`, made alongside
  the leaderboard's, and `point_preview.py --share` points Letterfield's
  `SHARE_URL` at it. Its `SITE_URL` is the site preview, passed with
  `--var`, so its pages send people back there; its other bindings are
  `[previews]` in `share/wrangler.toml` (the previews' R2 bucket and rate
  limit, no survey, so its cards leave their charting lines off). The
  comment links to it with an example card. Without one, the preview blanks
  `SHARE_URL`, so Share hands out the game's own link.
- **Apart from the live site:** each preview is its own origin, so its
  `localStorage`, service worker and offline copy are its own. Telemetry and
  analytics check the hostname, so they stay off. Turnstile's widget doesn't
  allow preview hostnames, so the survey joins without a pass, which Worker
  Previews accept.
- Pull requests from forks get no secrets and no previews. Locally, the
  same build serves with `cd preview && npx wrangler@4.151.0 dev` after
  `uv run ./build.sh`.

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
- The Worker answers at `https://api.games.michaelwarkentin.com`, a custom
  domain made by OpenTofu in mwarkentin/infra (`worker_domains.tf`), and
  still at `https://games-leaderboard.mwarkentin.workers.dev`. Keep `routes`
  out of `worker/wrangler.toml`: with routes there, wrangler would own the
  Worker's domains and drop that one. Its credentials (the
  `CLOUDFLARE_API_TOKEN` and `IP_SALT` secrets and the
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
- A slam says which card it turns over, so cards show face up as they're
  played. A game can be slow, with no clock: the room waits for everyone
  connected, and the host can flip over the cards of anyone holding it up.
  Each player's winnings stay beside their deck until they pick them up
  (see `worker/README.md`).
- Rooms have four-character codes from the same alphabet as groups, and
  invite links are `?room=<code>`. Players rejoin their seat with a random
  token kept in `localStorage` (`war:token`).
- Game tests fake a room with Playwright's `page.route_web_socket` and
  `tests/fake_war_room.py`; see `tests/test_war_rooms.py`.

## Letterfield's shared survey

Letterfield charts one shared map through the same Worker: a Durable Object
per sector of the map, plus an Atlas for the world's totals
(`worker/src/survey.js`; `worker/SURVEY.md` has the design and its costs).

- A `SURVEY_URL` constant holds the Worker's URL. While it's empty,
  Letterfield is single-player and connects nowhere. `?survey=<url>`
  overrides it for local testing and for tests.
- `worker/src/letterfield-world.js` is a copy of the game's map generator
  and themes, so the Worker can check a claimed word is really there.
  `worker/test/survey.test.js` runs the game's own code against it, so
  change both.
- Game tests fake the survey with `page.route_web_socket` and
  `tests/fake_survey.py`; see `tests/test_letterfield_survey.py`. The real
  Worker's stand-in answers the survey with an empty fake too, and its
  Turnstile check with a fake widget and pass, so no test reaches
  challenges.cloudflare.com. `without_worker()` blanks `SURVEY_URL` along
  with the other URLs.

## Letterfield's definitions

A word in the field notes opens to what it means, through the same Worker
(`worker/src/define.js`; "Letterfield's definitions" in `worker/README.md`),
which looks it up once on Wiktionary or Wikipedia and keeps it in D1, so the
page loads nothing from a new host.

- A `DEFINE_URL` constant holds the Worker's URL; `?define=<url>`
  overrides it. While it's empty, an entry only links out to Wiktionary and
  Wikipedia searches.
- Only found words: the page asks only from a find's entry, and nothing on
  the map, the toast or the legend shows a meaning.
- Show the source's link and CC BY-SA 4.0 beside the text, and put the
  Worker's text in the page as text, never HTML.
- Game tests fake it with `page.route` and `tests/fake_definitions.py`; the
  real Worker's stand-in answers it too.

## Adding or changing a game

1. Create or update `foo.html` following the rules above.
2. Link it from `README.md` under the right heading:
   `- [Title](https://games.michaelwarkentin.com/foo): what it is`, with
   the same title as the page's `<title>` up to any colon, and give the game
   its "Send feedback" link (see Feedback).
3. Note anything a player would notice in `changelog/foo.md`, under the day
   it reaches the site (see Changelogs). A new game's first day says it's
   here.
4. Draw its icon as `icons/foo.svg` and run `uv run scripts/render_icons.py`
   (see Home-screen apps). Optionally add `previews/foo.jpg` for a large
   link preview (see Link previews).
5. Add `tests/test_foo.py` that starts the game and plays a little: press
   Start, make a move, check the score or board changed. A debug hook such
   as Funnels & Buckets' `#debug` / `window.__fb` makes this much easier.
   `tests/test_games.py` already smoke-tests every game.
6. Run `uv run pytest` and `scripts/lint.sh`, and make sure both pass.
7. In the commit message, say what changed and include the URL of the chat,
   artifact or agent session behind it.

## Commands

```sh
uv run playwright install chromium   # once
uv run pytest -n auto                # builds the site into a temp dir, then tests it over every CPU
uv run pytest                        # the same, one test at a time
node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"   # the leaderboard Worker
(cd share && npm ci) && node --disable-warning=ExperimentalWarning --test "share/test/*.test.js"   # the share Worker
uv run ./build.sh && python3 -m http.server -d _site 8000   # preview the real site
uv run scripts/render_icons.py       # after drawing or changing an icon
scripts/lint.sh                      # lint everything, as CI does
scripts/lint.sh --fix                # fix and format what can be, then lint
```

The smoke tests load every game at phone and desktop sizes and fail on
console errors, uncaught exceptions, failed requests, sideways scrolling or
text inputs under 16px. They also check the `<head>` metadata, CDN version
pins and the README link.

### Linting

`scripts/lint.sh` runs one tool per language, each pinned to an exact
version, and CI's `lint` job (in `.github/workflows/test.yml`) runs it on
every push and pull request, in about half a minute. It fails on what it
finds; it never pushes fixes, since a push made with the workflow's token
starts no checks of its own and would race the sessions pushing to the same
branch. Run `scripts/lint.sh --fix` before you commit.

- **Python** (`scripts/`, `tests/`, `share/scripts/`): ruff, which lints
  (pyflakes, bugbear, sorted imports, modern syntax) and formats at 120
  columns. Its version and rules are in `pyproject.toml`.
- **JavaScript** (`worker/`, `share/`, the scripts the build inlines and
  every game's inline `<script>`): Biome, through `npx`, so the games still
  need no npm. Only its rules that catch bugs are on (`biome.jsonc`):
  undeclared names, unused variables and imports, impossible conditions.
  Its formatter is off, because it would rewrite nearly every line of the
  games. For a name used on purpose that it flags, write
  `// biome-ignore lint/<group>/<rule>: <why>` above it.
- **Shell:** shellcheck on `build.sh` and `scripts/lint.sh`, and actionlint
  on the workflows, which also runs shellcheck on their `run:` steps. Both
  report warnings and errors, not style.
- **Markdown, HTML and CSS** aren't linted. The build already checks the
  changelogs, and the smoke tests check what matters in each page.

ruff, shellcheck and actionlint are the `lint` group in `pyproject.toml`, apart
from `dev`, so the pytest jobs don't install them. Biome's version is in
`scripts/lint.sh` and `biome.jsonc`'s `$schema`; change both together. The
files that open pull requests change are listed under `[tool.ruff.format]
exclude` (and in `per-file-ignores`) and left unformatted, so they don't
conflict. Once a file's pull
requests have merged, take it off the list and run `scripts/lint.sh --fix`.

### Tests in parallel

The suite takes about 20 minutes one test at a time, mostly in real game
time (War's battles, animations), so `-n auto` runs it on
[pytest-xdist](https://pytest-xdist.readthedocs.io) workers, one per CPU.
CI (`.github/workflows/test.yml`) goes further: pytest-split cuts it into
up to three shards of about equal time, each a job of its own on four
workers, and a job named `test` passes once every shard has. A pull request
runs only the tests its changes need (`scripts/select_tests.py`): one that
only changes Letterfield runs Letterfield's tests and the ones covering
every game, not War's. A branch pushed before it has a pull request runs
what its changes from `main` need, the same way, and its later pushes
leave testing to the pull request. `main` always runs them all. So:

- **Every test must pass alongside others,** in any order and in any worker.
  Keep state in the test's own page, context or `tmp_path`, never in a
  module-level variable, a fixed port or a file in the repo. The site is
  built once per run (`site_dir` in `tests/conftest.py`, under a lock) and
  is read-only.
- **Measure what's at rest.** A busy machine runs pages slower, so a test
  that reads a size or position while something is still moving fails now
  and then. Wait for the animations on what's measured to finish (`e =>
  Promise.all(e.getAnimations().map(a => a.finished))`) or for the state
  the page reaches, never a fixed time.
- **`.test_durations`** holds each test's time, for splitting the shards
  evenly. New tests count as the average until it's refreshed, so refresh
  it now and then, or when the shards' times drift apart:
  `uv run pytest -n auto --store-durations`, and commit it.
- **A game's tests** are the files named for one of its pages
  (`tests/test_war_rooms.py` is War's) and any other test file that loads
  one, found by its address in the file (`/war`, `"war"`, `war.html`). A
  test named for no game runs for every game's pull request, and a change
  to anything shared (`scripts/`, the fakes, `feedback.js`, the workflow)
  runs the whole suite. Name a test file for its game, and give a page it
  loads by its plain address, so it's picked.
- **Files no test reads** (`worker/`, `share/`, `preview/`, `docs/`,
  `AGENTS.md`) don't count: a pull request of only those runs no pytest.
  A test that starts reading one needs it taken out of `UNREAD` in
  `scripts/select_tests.py`.

In a Claude Code on the web sandbox, the default network policy can block
`cdn.jsdelivr.net`, `cdnjs.cloudflare.com`, `fonts.googleapis.com`,
`fonts.gstatic.com`, `browser.sentry-cdn.com`, `cdn.playwright.dev` and
`registry.npmjs.org` (for `wrangler`, the share Worker and Biome). A test failing with
`Failed: https://...` for one of those hosts means the sandbox can't reach
it, not that the game is broken. Ask for those hosts to be allowed. CI has
full network access.

## Security

This repo is public. Keep secrets, internal hostnames and work specifics out
of games, tests and commit messages, and never host someone else's HTML here.
