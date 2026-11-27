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
  `scripts/common.py`). `letterfield-timelapse.html`, the survey replayed on
  a map, is another. The log's way back to the map, "← Letterfield", steps
  back in the tab's history when the tab came from the map, so the map comes
  back as it was (`data-back`, and the helper beside it in the log), and the
  map keeps its place whenever an entry of its is come back to; links into
  the log open it at its start. The timelapse's "← Log" steps back the same
  way when the tab came from the log, so the log comes back at its view.
  `tests/test_letterfield_back_links.py` checks all of this. `letterfield-soundtrack.html`, the game's music as an album
  (see The soundtrack album), is another, linked from the music player in
  the game's tools, and its own "← Letterfield" steps back the same way.
- `js/<game>/`: modules a game's page imports (see Modules): Letterfield's
  map, `js/letterfield/world.js` (its themes and the code that lays out every
  letter), and its achievements' rules and badges,
  `js/letterfield/achievements.js`; War's rules, `js/war/core.js`, and its
  check on players' names, `js/war/names.js`. The Workers import them too, so
  each is written once.
- `README.md`: the game list. The build turns it into `index.html`.
- `changelog/`: each game's changelog for players, `<game>.md`, which the
  build turns into `/changelog/<game>` (see Changelogs).
- `build.sh` and `scripts/`: assemble the site in `_site/` (never committed).
  The build also generates `index.html`, `colophon.html`, the changelog
  pages, `sitemap.xml`, `games.json` and each page's web app manifest, so
  don't create those by hand. Games are published as committed, apart from
  link-preview tags, `telemetry.js`, `feedback.js`, `analytics.js`, the
  home-screen app links and, for a page that imports modules, an import map
  (see below).
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
- `albums/letterfield/`: the soundtrack album's art, drawn as SVG with its
  letters as outlines by `scripts/draw_album_art.py`. `scripts/render_album.py`
  records the album into `_album/` (never committed) from the game's own
  music (see The soundtrack album).
- `tests/`: pytest with Playwright.
- `worker/`: the leaderboard API, a Cloudflare Worker with a D1 database,
  which also runs War's multiplayer rooms and Letterfield's shared survey as
  Durable Objects (see `worker/SURVEY.md`, and `worker/TURNSTILE.md` for its
  optional bot check). It deploys through its own
  workflow and is never part of the site. Every pull request gets a Worker
  Preview of it, built from its branch (see Previews below, and in
  `worker/README.md`).
- `share/`: the `games-share` Worker, which draws link-preview cards for
  shared Letterfield finds (see Share cards). It deploys through its own
  workflow, has the repo's one npm dependency, and is never part of the site.
- `preview/`: the `games-preview` Worker, which has no code and serves each
  pull request's build of the site as a Worker Preview (see Previews). It's
  never deployed to production.

## Rules for every game

- One `.html` file with inline `<style>` and vanilla JavaScript. No React,
  no JSX, no npm, no build step: the page runs as it is from any static
  server. A game can run to thousands of lines; keep it in its page, apart
  from code a Worker runs too, which is a module in `js/<game>/` that both
  import, never a copy (see Modules).
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
  no audio files, and so can a piece composed for the game itself, like
  Letterfield's Lantern, whose notes are written into the page, or
  Hinterland, the one piece Letterfield plays in the wilds (Dripstone's cave
  drips replace the music in the void). A generated
  piece takes a seed for every choice it makes (a new one each time it
  plays), so it can be recorded the same way twice.
- Pause when the tab is hidden (`visibilitychange`) if the game runs on a
  timer.
- Anything a page loads gets a placeholder its own size ahead of time
  (numbers, a chart, a list, a name), so nothing jumps as it arrives: a still
  block under `prefers-reduced-motion`, a gentle pulse otherwise. Draw what
  the page already knows, from its address or storage, at once.
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
| `letterfield.html` | `intro` (the card over the map at the start) | link, sign, coach, exploring |
| | `panel` (what's open from the corner, one at a time) | none, tools, people, notes |
| | `pass` (the survey's Turnstile pass) | off, none, loading, checking, asking, sending, good, failed |
| | `link` (each sector's socket; `el: null`, see `__lf.linkStates()`) | connecting, open, live, backoff, closed |
| | `claim` (each claim of ours; `el: null`, see `__lf.outbox()`) | queued, sent, unanswered, first, theirs, refused |
| | `define` (each found word's meaning; `el: null`, see `__lf.definitions()`) | loading, ready, none, failed |
| | `who` (the list of surveyors) | closed, loading, ready, refreshing, failed |
| | `peoplePage` (the Surveyors drawer's page) | list, you |
| | `guild` (your guilds, up to five) | out, naming, making, invited, joining, in, confirming, leaving |
| | `pair` (linking another device, and the recovery code) | idle, making, showing, used, entering, redeeming, done, failed, recovery, keeping, kept, removing, stop, stopping |
| | `pairCode` (a link code made here, watched until used) | none, making, waiting, used, gone |
| | `sync` (keeping linked devices in step) | off, idle, syncing, failed |
| | `notesPage` (the field notes drawer's page) | finds, marks |
| | `music` (the music player in the tools) | off, waiting, playing, paused |
| | `zone` (where the view is, on the survey) | inside, void, wilds |
| `letterfield-log.html` | `log` (what the page shows) | loading, ready, refreshing, stale, failed |
| | `span` (where the log starts, which ‹ stops at) | asking, known, failed |
| | `define` (each word's meaning; `el: null`, see `__log.definitions()`) | loading, ready, none, failed |
| `letterfield-timelapse.html` | `tl` (the replay) | loading, empty, failed, paused, playing, waiting |
| | `rec` (saving a video) | off, preparing, recording, done, failed |
| `letterfield-soundtrack.html` | `player` (the album's tracks) | off, idle, playing, paused, failed |
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

## Modules

A game's page holds its markup, its style and its code, with one exception:
code that a Worker runs too, like Letterfield's map (the Worker checks a
claimed word is really there) and its achievements' rules (the Worker signs
badges by them), or War's rules (rooms play by them) and its name check.
That lives once, as a module in `js/<game>/`, imported by
the page and the Workers alike. Before, each was copied word for word into
the Worker and kept in step by tests that read the page as text; a module
retires the copy and the test.

- **In the page,** the script that imports one is `<script type="module">`,
  importing by plain relative path:
  `import { chunk } from './js/letterfield/world.js';`. So the page runs
  from any static server with nothing built, as before:
  `python3 -m http.server` at the top of the repo, then `/letterfield.html`.
  (Modules don't load from `file://`.) A module script is strict and has
  its own scope: its names aren't the window's, as a classic script's are.
  Letterfield's code was already inside `(() => { ... })()`, so nothing
  changed there; War's `#debug` lends the window the few names its tests
  reach into (`S`, `deck`...), beside `window.__war`.
- **In a Worker,** a relative import from `worker/src/` or `share/src/`
  (`'../../js/letterfield/world.js'`); wrangler bundles it. A module has no
  DOM and no state beyond caches, so node:test imports it as it is.
- **On the site,** the build (`inject_modules` in `scripts/common.py`) gives
  each page that imports modules an import map naming each module by a hash
  of its contents (`/js/letterfield/world.js?v=1a2b3c4d5e`), and a
  `modulepreload` link for each, so they download alongside the page rather
  than one after another. A page and its modules then always come from the
  same deploy: the page names the exact copies it was built with, and a
  deploy that changes one module changes that one's address alone, so the
  others stay cached (a deploy of Letterfield's game code leaves the 140 KB
  of themes in the browser). `sw.js` keeps every module by its hashed
  address, and keeps a page's fresh copy only once the modules it names are
  kept too, so an offline page never imports a module that isn't there.
  Browsers without import maps (Safari before 16.4) load the plain paths:
  they work online, without the offline copies.
- **Its tests** are its game's (`scripts/select_tests.py`), and the Workers'
  tests run on every pull request. A change to a module the Workers import
  also deploys and previews them (the `paths` of `leaderboard.yml` and
  `share.yml`, and `preview.yml`): add a new folder in `js/` there.
- **Not everything big belongs in a module.** Splitting a page by section
  doesn't avoid merge conflicts: separate files would have spared none of
  the 73 conflicts between Letterfield's recent pull requests, which all
  fell within one section (see `docs/split-js.md`). And most of a game's
  sections assign each other's variables, which an import can't do. Keep
  the rest in the page.

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
text inputs masked. Traces and session replays are sampled (a fifth of page
loads, one session in fifty), a session with an error always keeps its
replay, and one page load sends at most 25 errors, 3 of any one message, so
a busy day can't use up the month's quotas. To hide something else from replays, give it the
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
It stores every page, the modules in `js/` (see Modules), and the music in
`music/`, when it installs. After that, pages come from the network first
and fall back to the stored copy when the network fails or takes more than
four seconds; modules and music come from the stored copy. Google Fonts are
stored too. Nothing else goes through it, so the leaderboard, War's rooms,
Sentry and Counterscale behave as they would without it. A hash of the
pages, modules and music is the worker's version, so each deploy refreshes
every stored copy.

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
- A page in another game's app shares that game's preview, unless it has one
  of its own, `previews/<page>.jpg`, like the soundtrack's, drawn from its
  cover by `scripts/draw_album_art.py`.
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
- A shared achievement links to `/a/<id>` (`/a/d/<id>` dark), a card of its
  badge, which sends people on to `/letterfield#a-<id>`, the Achievements page
  at that badge (see "Share cards" in `worker/ACHIEVEMENTS.md`). The badges'
  drawings, names and groups are in `js/letterfield/achievements.js`, which
  the game and the share Worker both import.
- The survey log's views (a surveyor's, theme's, guild's or territory's page, and
  the Supernovas tab) have cards too, at `/v/…`: `letterfield-log.html` has a `SHARE_URL` of its own,
  and while it's empty Share links to the page and attaches the page's own
  picture. Their numbers come from the leaderboard Worker's log answers,
  through a service binding (`LOG` in `share/wrangler.toml`), and their
  addresses pin the period by its first day and its UTC hours, so the page's
  `viewPath()` and `share/src/view.js` must agree. The Supernovas card
  (`/v/novas/…`) counts the period's supernovas from `/v1/survey/log/novas/…`
  and shows the latest ones' last words. A guild's name rides along as
  `?name=<a>-<b>-<c>` on its `/v/` address and on the link to its page, so a
  guild with no words yet, which the log has no name for, is still named.
- The Worker checks the word is on the map with `worker/src/`'s own code,
  asks the word's sector who charted it and the Atlas how much of the shared
  map is charted (internal paths on the leaderboard Worker's Durable
  Objects), and draws the card with `@resvg/resvg-wasm`. Its colours are
  `letterfield.html`'s; `share/test/card.test.js` checks they still match.
  Cards are kept for good by the state they show, so when what they say
  changes, raise `CARD_WORDS` in `share/src/card.js` and they're drawn again.
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
- **The Worker:** every pull request also gets a Worker Preview of the
  leaderboard Worker, built from its branch and made first, at
  `https://pr-<number>-games-leaderboard.mwarkentin.workers.dev`, and
  `point_preview.py --worker` points every address of the Worker in the games
  at it (`LEADERBOARD_URL`, `ROOMS_URL`, and Letterfield's `SURVEY_URL` and
  `DEFINE_URL`), so the preview's leaderboards, War's rooms and Letterfield's
  survey, log and definitions run against the pull request's own Worker.
  That Preview also allows the site preview's origin in `ALLOWED_ORIGINS`,
  passed with `--var` for that Preview only; `wrangler.toml` doesn't change.
  Production's Worker only answers the live site, so a preview never points
  at it: if the Worker Preview can't be made, the site preview isn't either.
  Worker Previews take turns only when their branch brings database
  migrations, which go on the Previews' shared databases (see Previews in
  `worker/README.md`); every other pull request's is made at once.
- **The share Worker:** a pull request whose branch changes `share/`,
  `worker/src/` or `js/letterfield/` (whose code it bundles), or `preview.yml`, from `main`'s, or
  that's labelled `worker-preview`, gets a Worker Preview of `games-share`
  too, at `https://pr-<number>-games-share.mwarkentin.workers.dev`, made
  alongside the leaderboard's, and `point_preview.py --share` points
  Letterfield's `SHARE_URL` at it. It's `main` it compares against, not the
  pull request's base, so one stacked on another pull request's branch gets
  one when that branch changes the share Worker. Adding the label makes the
  previews again, with a share Preview. Its `SITE_URL` is the site preview, passed with
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
never exists on this site, and games here don't need to run as artifacts
any more, so drop such calls when bringing one over and keep its state in
`localStorage`. Shared high scores go through the leaderboard Worker
instead (see below). When bringing a new artifact over:

1. Read it with the Artifact tool, then move the `<title>`, `<link>` and
   first `<style>` tags the artifact service leaves at the top of `<body>`
   into a proper `<head>`, and add the description.
2. Drop `<meta name="claude:viewport-fit-sides">`; nothing here reads it.
3. Put the artifact's URL in the commit message so the colophon links back
   to it.

## The soundtrack album

Letterfield's music is also an album, `letterfield-soundtrack.html`: the four
pieces that take turns, each in a longer cut, a supernova between them, and
the two heard only past the universe's edge, Hinterland (the wilds) and
Dripstone (the void), with notes on how each is made, to play or download.
Tracks are numbered in their files' names, so a new one goes at the end,
never between, and the files people have linked to keep their names.

- **Recorded from the game:** `scripts/render_album.py` plays the game's own
  music in headless Chromium (`letterfield.html#debug`, whose `__lf` hands
  over the pieces in `musicTracks`, the places' own in `placeTracks`,
  `audioOut` and the sound effects), each piece from a fixed
  seed into an `OfflineAudioContext`, scheduled as the game schedules it and
  through the same compressor and limiter. Each track is a cut in `TRACKS`:
  where it stops and fades, in the piece's own bars, or in seconds for a
  piece with none (Hinterland's phrases, Dripstone's drips), chosen for its
  seed so the cut ends between phrases or drops. It serves the page from
  here with its Worker addresses blanked and refuses every other host, so it
  never reaches production. Renders are the same every time to about a
  millionth of full scale (Chromium sums three or more signals meeting at a
  node in no fixed order), so the MP3s' bytes can differ from one run to the
  next.
- **One level:** ffmpeg measures each track by EBU R128 and brings it to
  −17 LUFS, unless its true peak would pass −1.5 dBTP (so Dripstone, nearly
  all silence, stays well under the rest rather than having its quiet
  raised), then encodes LAME VBR
  (V2) MP3s at 44.1 kHz with ID3v2.3 tags and the 1400px cover, 24-bit FLACs
  with the 3000px cover for stores, and a zip. It prints each track's length,
  loudness and size, writes them to `_album/album.json`, and warns when the
  page's lengths and sizes aren't the render's.
- **Its files aren't in git.** They're in a public Cloudflare R2 bucket,
  `games-media`, under `letterfield/`, on `media.michaelwarkentin.com`
  (made by OpenTofu in mwarkentin/infra; no CORS needed, since audio
  elements and downloads don't ask for it), which is the page's `ALBUM_URL`.
  `uv run scripts/render_album.py --upload` puts `_album/web/` there, each
  file with its type, a day's caching and, for downloads, the name it's
  saved as (`Content-Disposition`, since browsers ignore a link's `download`
  attribute on another origin). It needs `CLOUDFLARE_ACCOUNT_ID` and the
  bucket's upload token (`tofu output -raw games_media_upload_token` in
  infra) as `CLOUDFLARE_API_TOKEN`, or `npx wrangler login`. The files are
  cached for a day, so a re-render that must show at once goes under a new
  prefix (`letterfield/v2/`, in `PREFIX` and `ALBUM_URL` both). Adding a
  track changes every MP3 (their tags count the tracks) and the zip, so
  upload them all. With
  `ALBUM_URL` empty, the page lists the tracks without players or
  downloads, and `?album=<url>` overrides it for tests. `sw.js` stores only
  pages and `music/*.mid`, so the MP3s always come from the network.
- **The art** is `albums/letterfield/`: the cover (a corner of the map, each
  piece circled in a territory of a theme that has its word, and Night Sky
  going supernova), the back and the link preview, drawn by
  `scripts/draw_album_art.py` with every letter an outline from the game's
  fonts, so rendering them needs no fonts or network. It also puts the cover
  into the page, inline, so it shows offline.
- **Credit and licence:** Michael Warkentin, and CC BY 4.0 for the
  recordings and their art (the code that makes them is the repo's, Apache
  2.0). `ARTIST`, `LICENSE` and `COPYRIGHT` in the script put them in the
  tags, the zip's `LICENSE.txt` and on the back; the page says so too.
- `tests/test_letterfield_soundtrack.py` renders a few seconds of every track
  with the script's own code, and checks the page against `TRACKS` and the
  cover; it fakes the recordings with a short tone.

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
  /v1/groups` starts one and `GET /v1/groups/<code>` looks one up. A
  group's name goes through the same word filter as War's players
  (`nameIsKind()`, see Multiplayer rooms), and a name that fails gets a 400
  the page shows as it is. Invite
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
  the page. The rules are `js/war/core.js`, which `war.html` and
  `worker/src/war.js` both import (see Modules).
- Players' names go through a word filter, `nameIsKind()` in
  `js/war/names.js`, which leaderboard groups' names go through too
  (`worker/src/leaderboard.js` imports it, as do `war.html` and
  `worker/src/war.js`). The page checks a name before it asks for a room, and the room refuses
  one that fails. Words that turn up inside ordinary names (ass in Cassandra, shit in
  Yamashita) count only on their own, so add a word to `NAME_ANYWHERE` only
  if no name hides it, and add an ordinary name that does to the test of
  names that get through.
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
- The map (its themes and the code that lays out every letter) is
  `js/letterfield/world.js`, which the game and the Workers all import, so
  the Worker checks a claimed word against the very map the game draws.
  `MAP_VERSION` there says which map it is: a change that redraws the map
  raises it (`worker/test/survey.test.js` keeps a digest of each).
- The survey stops at the universe's edge, sectors -12 to 12 each way (`AREA`
  in `worker/src/survey.js`, `SURVEY_AREA` in the game). Past it, a sector
  wide all round, is the void, where loose letters drift and nothing can be
  circled, and beyond that the wilds, where words are found alone. The game
  joins no sector out there (its `zone` machine), the Worker turns a join
  away, and the log keeps nothing from there; finds made out there stay in
  the finder's field notes ("The edge, the void and the wilds" in
  `worker/SURVEY.md`). Playing alone, the map has no edge.
- What happens when a crowd arrives at once (a link on a news site's front
  page), the knobs, what to watch and what not to do on the day are in
  `worker/VIRAL.md`. Every Worker deploy drops every socket and empties the
  Atlas's memory, so don't deploy one mid-spike; `js/letterfield/**`
  deploys it too.
- Its list of surveyors and their emotes are `worker/src/survey-social.js`
  ("Surveyors and emotes" in `worker/SURVEY.md`), and its guilds
  `worker/src/survey-guild.js`, a Durable Object per guild ("Guilds").
  Players are named by a hash of a random token the game keeps
  (`games.player`, shared by every game like `games.initials`), never their address; emotes are a fixed set of
  drawings, guild names are words from fixed lists, and nothing anyone else
  sees is free text (a player's own labels for their guilds sync between
  their devices, and nobody else ever sees them). A surveyor can be in up to
  five guilds. Guild invite links are `?guild=<code>`.
- Another device becomes the same player with a one-time code
  (`worker/src/players.js`, "One player, several devices" in
  `worker/SURVEY.md`), shown as a QR code, a `?link=<code>` link and eight
  characters to type. It carries the token, initials, guild and mutes, and
  starts a Player (a Durable Object per player) that keeps the linked
  devices' field notes, supernovas and settings in step ("Syncing linked
  devices"). Nothing syncs for a player who never linked a device. A
  recovery code, which the player saves, does the same with no other device
  to hand ("A recovery code"); the Worker keeps the token sealed with it,
  never the code or the token.
- Game tests fake the survey with `page.route_web_socket` and
  `tests/fake_survey.py`; see `tests/test_letterfield_survey.py`, and
  `tests/test_letterfield_surveyors.py` for the list and emotes,
  `tests/test_letterfield_guilds.py` for guilds,
  `tests/test_letterfield_linking.py` for linking devices,
  `tests/test_letterfield_sync.py` for syncing them and
  `tests/test_letterfield_recovery.py` for recovery codes. The real
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
- Only words already found or charted: the game asks only from a find's
  entry, and the survey log (`letterfield-log.html`, with a `DEFINE_URL` of
  its own) only from a word's row, since every word there is charted and its
  meaning gives nothing away. Nothing on the map, the toast or the legend
  shows a meaning.
- Show the source's link and CC BY-SA 4.0 beside the text, and put the
  Worker's text in the page as text, never HTML.
- Game tests fake it with `page.route` and `tests/fake_definitions.py`
  (`tests/test_letterfield_definitions.py`, and
  `tests/test_letterfield_log_definitions.py` for the log); the real
  Worker's stand-in answers it too.

## Letterfield's achievements

Achievements, their badges and days surveyed are worked out from the field
notes and supernovas seen, then latched in `letterfield.marks.v1`
(`worker/ACHIEVEMENTS.md` has the catalog and the design). Their page is in
the notes drawer (`notesPage`), and their note is a kind of its own,
`achievement`, which `letterfield.quiet.v1` can quieten; a day that counts
has a quieter note, `day`, which it can quieten apart.

- The rules are `js/letterfield/achievements.js` (`achievementsCore`, with
  the badges' art), which the game and `worker/src/achievements.js` both
  import.
- A surveyor can show one badge to others, on their caret's hover card and
  menu. The Worker signs it only from finds the sectors signed (each claim's
  answer is followed by a receipt, `{t: 'signed'}`), or, until
  `TRUSTED_UNTIL`, on the game's word for achievements from before signing.
  The few no find can prove (the catalog's `u` and `l`) it always signs on
  the game's word.
  Keys come from `IP_SALT`.
- A surveyor's caret menu is their card: every badge signed for them and
  when they began surveying, never a streak ("Profile cards"). The Worker
  signs it with their badges, and their sector checks it and adds it to
  presence. It names badges by their place in the core's catalog, so new
  achievements go at the end of it.
- Achievements, the longest streak, the badge shown and the card sync
  through the Player with the notes.
- Every test's browser starts with achievement and day notes quietened
  (`QUIET_ACHIEVEMENTS` in `tests/conftest.py`), so a test's first finds
  bring no note they aren't about, and answers the fake survey's
  `/v1/survey/badges` with none; `tests/test_letterfield_achievements.py`
  turns notes back on, and fakes receipts, badges and cards with
  `FakeSurvey(sign=True)` and `FakeBadges(cards=True)`.

## Letterfield's words

One name for each idea, in the game, the survey log, the timelapse, share
cards and the changelog, so players never wonder whether two words mean two
things. Use these in everything a player reads (code can keep its own
names, like `region` or `stray`):

| Idea | Say | Not |
|---|---|---|
| Playing on one map together | the shared survey ("the survey" once that's clear) | |
| Someone playing it | surveyor | player |
| The area charted together | the universe (its map: "Universe map") | the shared world, the shared map, World |
| Where it ends | the edge of the universe | the boundary, the border |
| The sector-wide ring past it, with no grid | the void | the gap, the edge zone |
| The map beyond the void, off the survey | the wilds | outside, far away, past the edge (once you mean the wilds) |
| A theme's patch of the map | territory | region, sector, area |
| The people in a guild | members | mates |
| Your list of words | field notes ("your notes" after that) | |
| A word in them | a find | |
| The words a territory hides | hidden words | words alone, where it matters |
| A real word turned up by chance | bonus word | stray, found by chance |
| Being first to a word on the survey | charted first; someone else's is "charted by ZED" | claimed |
| Circling a word alone | found | charted |
| The three letters | initials, which sign your words | name, tag |
| The map played back | timelapse | replay |
| The log's lists of the most charted | top lists | rankings |

And the names of the tools: Map centre, Last find, the Effects and Music
sliders. A survey that can't take more people here is "crowded", and a
period still running is "so far", never "live". Never show internal words
like sector, Atlas, claim or pass.

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
uv run scripts/render_album.py       # record Letterfield's soundtrack into _album/ (needs ffmpeg)
uv run scripts/render_album.py --upload   # then put it in its R2 bucket (needs a token that can write there)
uv run --with fonttools --with uharfbuzz scripts/draw_album_art.py   # after changing the album's art
scripts/lint.sh                      # lint everything, as CI does
scripts/lint.sh --fix                # fix and format what can be, then lint
uv run --only-group lint prek install   # once per clone: lint and fix staged files on each commit
```

The smoke tests load every game at phone and desktop sizes and fail on
console errors, uncaught exceptions, failed requests, sideways scrolling or
text inputs under 16px. They also check the `<head>` metadata, CDN version
pins and the README link.

### Linting

`scripts/lint.sh` runs one tool per language, each pinned to an exact
version, and CI's `lint` job (in `.github/workflows/test.yml`) runs it on
every push and pull request, in about 15 seconds. It fails on what it
finds; it never pushes fixes, since a push made with the workflow's token
starts no checks of its own and would race the sessions pushing to the same
branch. Fixes happen before the commit instead, with prek (below).

- **Python** (`scripts/`, `tests/`, `share/scripts/`): ruff, which lints
  (pyflakes, bugbear, sorted imports, modern syntax) and formats at 120
  columns. Its version and rules are in `pyproject.toml`.
- **JavaScript** (`worker/`, `share/`, `js/`, the scripts the build inlines
  and every game's inline `<script>`): Biome, through `npx`, so the games still
  need no npm. Only its rules that catch bugs are on (`biome.jsonc`):
  undeclared names, unused variables and imports, impossible conditions.
  Its formatter is off, because it would rewrite nearly every line of the
  games. For a name used on purpose that it flags, write
  `// biome-ignore lint/<group>/<rule>: <why>` above it.
- **Shell:** shellcheck on `build.sh` and the scripts beside it, and actionlint
  on the workflows, which also runs shellcheck on their `run:` steps. Both
  report warnings and errors, not style.
- **Markdown, HTML and CSS** aren't linted. The build already checks the
  changelogs, and the smoke tests check what matters in each page.

ruff, shellcheck, actionlint and prek are the `lint` group in `pyproject.toml`, apart
from `dev`, so the pytest jobs don't install them. Biome's version is in
`scripts/lint.sh` and `biome.jsonc`'s `$schema`; change both together. The
files that open pull requests change are listed under `[tool.ruff.format]
exclude` (and in `per-file-ignores`) and left unformatted, so they don't
conflict. Once a file's pull requests have merged, take it off the list and
run `scripts/lint.sh --fix`.

**Before each commit,** [prek](https://github.com/j178/prek)'s git hook runs
`scripts/lint.sh --fix` on the staged files (`.pre-commit-config.yaml`). If
it changes a file, the commit stops: look at the change, `git add` it and
commit again. If it finds something it can't fix, fix that and commit again.
Don't skip it with `--no-verify`; CI's `lint` job, which `test` requires,
would only fail later.

- **On your computer,** install the hook once per clone:
  `uv run --only-group lint prek install`.
- **In a Claude Code cloud session,** the clone is fresh and has no hook, so
  `.claude/hooks/session-start.sh` (a SessionStart hook in
  `.claude/settings.json`) installs the lint group and the hook when the
  session starts, and skips both once they're there. It does nothing on
  your own computer.

### Tests in parallel

The suite takes about 20 minutes one test at a time, mostly in real game
time (War's battles, animations), so `-n auto` runs it on
[pytest-xdist](https://pytest-xdist.readthedocs.io) workers, one per CPU.
CI (`.github/workflows/test.yml`) goes further: pytest-split cuts it into
up to three shards of about equal time, each a job of its own on four
workers, and a job named `test` passes once every shard, the lint job and
the two Workers' node tests have (see Merging). A pull request
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
  one, found by its address in the file (`/war`, `"war"`, `war.html`). Its
  modules in `js/<game>/` count as its pages do. A
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

## Merging

`main` takes a pull request only once its `test` check has passed: a
ruleset made by OpenTofu in mwarkentin/infra requires it, from GitHub
Actions. That one check stands for the whole Test workflow, since the jobs
under it change from one pull request to the next (`pytest (1/3)` is there
or not, by what the plan picks), so never require a shard by name.

- **It always reports.** `test` passes once every job the plan wanted has,
  and fails if one failed or was cancelled, so a pull request of only docs
  or only the Workers, which runs no pytest, still gets its answer. A run
  cancelled by a newer push leaves the old commit cancelled; the new one
  gets its own. A pull request from a fork runs it too, once its workflows
  are approved, without secrets, which no test needs.
- **Only pull requests make it.** A branch's push runs call the same job
  `test (push)`, because the push run of a branch with an open pull request
  skips everything and passes at once, and under the same name on the same
  commit it would let the pull request merge before its own run finished.
- **Not up to date.** A branch needn't have the latest `main` to merge:
  with many sessions each on its own pull request, that would mean merging
  `main` into every one after each merge. GitHub's merge queue would do
  that for us, but isn't offered on a repository owned by a person. So two
  pull requests that each pass can still break `main` together; `main`'s
  own run, of the whole suite, catches that, and the fix is a new pull
  request.
- **Preview isn't required.** It needs secrets, which forks don't get, and
  says nothing about whether the games work.
- **The owner can bypass it,** with the "merge without waiting" box, for a
  red CI that isn't the change's fault (a CDN down). Agents never merge.
- **Auto-merge** is on: "Enable auto-merge" on a pull request merges it
  (squashed) once `test` passes.

## Pull requests

Agents open a pull request once their work is pushed, without asking first,
and say in it what changed and how it was tested. Its Preview comment then
gives the link to try it on a phone (see Previews).

## Security

This repo is public. Keep secrets, internal hostnames and work specifics out
of games, tests and commit messages, and never host someone else's HTML here.
