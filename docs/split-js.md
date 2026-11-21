# Splitting a game's JavaScript out of its page

Should a game's script live in files of its own, rather than inline in its
one `.html` page? This looks at Letterfield first, since it's the biggest
page: on `main` (44fe976) it's 8,248 lines and 780 KB, a third of that its
225 themes' word lists, and it shares two blocks of code with the Worker by
copying them word for word.

**In short:** split out the code a Worker runs too, and nothing else. That
code lives once, as a module in `js/<game>/`, imported by the page and by
the Workers. Nothing is built: the page runs from any static server as it
did. The build only adds an import map, so a page and its modules always
come from the same deploy, and the service worker keeps both offline. The
rest of the page stays one file. Splitting it by section wouldn't avoid
merge conflicts: they all fall within one section. And most sections assign
each other's variables, which an import can't do.

The prototype on this branch does this for Letterfield. It moves the map
(`js/letterfield/world.js`) and the achievements' rules and badge art
(`js/letterfield/achievements.js`) out of the page, deletes the Worker's
282 KB copy of the map and its copies of the rules and art, and retires the
tests that compared the copies as text.

## The options

| | Where the code is | What the browser gets | Copies with the Worker |
|---|---|---|---|
| **(a) One file** (`main`) | all in the page | one 798 KB page (303 KB gzipped) | three, kept in step by tests |
| **(b) Shared code as modules** (prototype) | the page, plus `js/letterfield/*.js` | a 495 KB page, plus 284 KB and 23 KB modules (304 KB gzipped in all) | none |
| (b′) All of the script in modules | the page is markup and style; `game.js` the rest | a 110 KB page plus three modules (304 KB gzipped) | none |
| (c) Only the data split out | themes in a module, code in the page | as (b), within a few KB | the generator still copied |
| (d) Modules in source, one file published | modules, inlined by `build.sh` | as (a) | none, but needs a bundler |

(c) gets (b)'s bytes without retiring the copied generator. (d) serves
exactly what (a) does, so it measures as (a). It needs a step that rewrites
`import` and `export` to inline modules, which is a bundler, either from npm
or written by hand. It also loses (b)'s one runtime gain: an unchanged
module staying cached across a deploy. (b′) was built only to measure; it
isn't proposed (see "The rest of the page").

## First load

Measured with `docs/split-js-bench/`. The server is a stand-in for GitHub
Pages: HTTP/2, gzip, `Cache-Control: max-age=600`, ETags. The browser is
Chromium with DevTools' network presets and 4× CPU slowdown, at a phone's
390 × 844 viewport. Every other host fails to resolve, so fonts fall back
and nothing reaches production. "Map drawn" is the first letter drawn on the
map, which is when the game can be played. Medians of 5 runs. The same site measured twice differed by up to 120 ms,
so smaller differences are noise.

**A first visit:**

| | Map drawn, Fast 3G | Fast 4G | Unthrottled | Transferred (gzipped) | Requests |
|---|---|---|---|---|---|
| (a) One file (`main`) | 2,606 ms | 827 ms | 144 ms | 302 KB | 1 |
| **(b) Shared code as modules** | **2,611 ms** | **816 ms** | **133 ms** | 304 KB | 3 |
| (b) without its `modulepreload` links | 3,279 ms | 1,047 ms | 151 ms | 304 KB | 3 |
| (b′) All of the script in modules | 3,039 ms | 932 ms | 120 ms | 305 KB | 4 |

First paint was the same in all of them, within noise: 750–820 ms on Fast 3G
and 330–350 ms on Fast 4G.

So the prototype loads as fast as the single file. The page brings half the
bytes from the first round trip, and the preload links start the modules as
soon as the page's `<head>` arrives. Without those links, the browser finds
`world.js` only when it reaches the script at the end of the page, so the
modules download after the page instead of alongside it, 670 ms later on
Fast 3G. Moving all of the script out (b′) puts most of the bytes behind
that second round trip, which costs about one round trip (562 ms on Fast 3G)
of the page's own download time.

## Repeat visits and deploys

- **Within ten minutes** (Pages' `max-age`), a repeat visit takes nothing
  from the network in either layout.
- **After a deploy,** once the cache has to revalidate, a browser fetches
  again only what changed. On `main` that's always the whole page. With
  modules, a deploy of the game's code costs the page alone, and the
  unchanged modules answer 304. Since the map only changes when a theme does
  (1 of Letterfield's last 60 pull requests), most deploys leave its 140 KB
  in the browser:

  | A visit after a deploy that changed | Map drawn, Fast 3G | Fast 4G | Transferred |
  |---|---|---|---|
  | (a) anything | 2,530 ms | 762 ms | 302 KB |
  | **(b) the game's code** | **1,743 ms** | **602 ms** | **157 KB** |
  | (b) a theme | 2,431 ms | 698 ms | 296 KB |
  | (b′) the game's code | 2,218 ms | 732 ms | 157 KB |

  That's half the bytes and the map 790 ms sooner on Fast 3G for most
  returning players. (b′) moves as little, but waits for the page before
  it can ask for `game.js`.
- **Out of step:** the page names each module by a hash of its contents
  (`/js/letterfield/world.js?v=8ca5b42560`), so a page never runs against a
  module from another deploy, whether either comes from the HTTP cache, the
  service worker or the network.
- **Offline:** `sw.js` keeps every module by its hashed address with the
  pages. It keeps a page's fresh copy only once the modules that copy names
  are kept too, so the copy it serves offline always has its modules.
  `tests/test_pwa.py` checks Letterfield plays offline, and that a deploy
  whose module can't be fetched leaves the old page and module in place.
  Without that check it would keep the new page and lose its module.
- **Browsers without import maps** (Safari before 16.4) load the modules by
  their plain paths. They work online, as a 10-minute cache allows, and have
  no offline copy of the modules.

## Correctness

- **Scope:** the game's code already ran inside `(() => { ... })()`. A
  module script has its own scope too, and is strict, so `'use strict'`
  went. Nothing in the page used inline event handlers or globals the
  script declared. `window.__lf` and the other debug hooks are unchanged.
- **Order:** a module script runs once the page is parsed, like the script
  at the end of `<body>` did, and its imports run first.
- **The build:** telemetry, feedback, analytics, link previews and
  manifests are added to the page as before. The import map goes in
  first, ahead of any module.
- **Tests:** the smoke tests in `tests/test_games.py` pass unchanged.
  `test_build.py` checks every published module is the one its page's
  import map names. `test_pwa.py` checks the service worker keeps the
  modules, and plays Letterfield offline.
- **The Worker:** wrangler bundles `../../js/letterfield/world.js` like any
  other relative import. The Worker's and share Worker's tests import the
  same file the page does. A digest of the map, keyed by `MAP_VERSION`,
  replaces the test that compared the two copies, so a change that redraws
  the map still has to raise `MAP_VERSION`.
- **Local preview:** `python3 -m http.server` at the top of the repo serves
  `/letterfield.html`, modules and all, with nothing built. A page opened
  straight from disk (`file://`) can't load modules, where the single file
  could.

## Agents and merge conflicts

- **Reading:** the page drops from 780 KB to 477 KB, and from 8,248 lines to
  7,600. Its longest lines go too: each theme was one line of up to 2 KB.
- **Copies:** Letterfield's copies were edited on both sides in 3 of its
  last 60 pull requests, War's in 4 of 22. Each such edit, made twice, is
  now made once.
- **Merge conflicts:** splitting doesn't help. The analysis replayed each of
  Letterfield's last 60 pull requests onto the base of the one 1, 2 or 3
  before it, as if they had been open together (`git merge-file` on each
  pair's three versions). 27% of neighbouring pairs conflict, and 56% of
  pairs three apart. Separate files would have spared none of the 73
  conflicting pairs: 211 of their 215 conflicting blocks fall inside one
  section, and the other 4 edit a section the pull request in between had
  just added, which would conflict as files too. Half involve the CSS or
  markup, which stay in the page anyway, and pull requests are broad: a
  median of 4 sections each, and 37 of 60 change markup and script
  together.
- **The real hotspot** is one statement: `window.__lf = { ... }`, the debug
  hooks, which 16 pull requests edited and 19 conflicting pairs hit. Each
  section adding its own hooks (`Object.assign(__lf, { ... })` beside the
  code they expose) would remove those conflicts, split or not.
- **Linting and tests:** Biome lints `js/` as plain JavaScript files.
  node:test imports the game's own map and rules, with no copy and no
  `vm` evaluation of text cut from the page.

## The rest of the page

Each section of Letterfield's script was measured for what a module would
need: the names it uses from other sections, the names they use from it,
and assignments across sections. ES imports are read-only, so those last
would need rewriting. The analysis used eslint-scope on the script.

| Section | Lines | Names it uses from others | Names others use from it | Assignments to it from others |
|---|---|---|---|---|
| World constants + generation | 397 | 0 | 51 (20 of them the map's) | 0 |
| Sound + Music | 988 | 11 | 22 | 0 |
| Shared survey | 814 | 58 | 39 | 2 |
| Surveyors | 633 | 68 | 44 | 3 |
| Achievements (the UI) | 873 | 44 | 24 | 1 |
| Interaction state | 271 | 51 | 7 | 14 |
| Boot | 80 | 103 | 0 | 0 |

The map was the clean cut, and it's done. Sound and Music together are the
only other one: 11 names in, and nothing assigned across. But two of those
names are page helpers, the state machine and `LS`, which would have to
become modules first. Everything else depends on most of the page, with 33
assignments across sections (the canvas's `W`, `H`, `dpr` and `dock`; the
camera's `flight` and `inertia`...). Splitting those
sections would mean a shared state object and rewriting hot code, and every
open branch would conflict with it, for no conflicts saved afterwards. So
the rest stays in the page. Sound and Music can follow if the page's size
still gets in the way.

## Other pages

- **War** (8,560 lines) copied its rules (`BEGIN WAR CORE`) and name check
  (`BEGIN NAME CHECK`) into the Worker. They're now `js/war/core.js` and
  `js/war/names.js` the same way (in their own pull request), which retires
  two more copies and their tests. War's script had no
  `(() => { ... })()` around it, so its names were the window's, and a few
  tests read them (`S`, `deck`...); its `#debug` now lends the window just
  those.
- **letterfield-log.html, the timelapse and the smaller games** (at most
  2,900 lines) share no code with a Worker, so they stay single files.
- **The state machine helper**, copied into eight pages, could be one
  module too. But it's 35 lines that never change (no pull request edited
  Letterfield's copy), and each page would have to switch to a module
  script for it. Not worth it.

## Landing it

The split deletes big blocks from `letterfield.html` that other branches
rarely touch: the themes (1 of the last 60 pull requests), the generator (2),
and the achievements' rules and art (2 since they arrived). So a branch open while it lands conflicts
only if it edits those, and git sees a deleted block as one conflict to
resolve by moving the edit into the module. Two stages:

1. **This branch** (Letterfield's map and achievements as modules), merged
   at a quiet moment: when no open pull request changes the themes, the
   generator or the achievements' rules. Then rebase or merge `main` into
   any that do.
2. **War's rules and name check,** the same way, when no War pull request
   is open.

The debug-hook change can go in on its own whenever there's a gap.
