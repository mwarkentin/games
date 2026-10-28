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
  `games.json`, so don't create those by hand. Games are published exactly as
  committed; nothing is injected into them.
- `tests/`: pytest with Playwright.

## Rules for every game

- One `.html` file with inline `<style>` and vanilla JavaScript. No React,
  no JSX, no npm, no build step. A game can run to a couple of thousand
  lines; keep it in one file anyway.
- Load libraries from `cdn.jsdelivr.net` or `cdnjs.cloudflare.com`, pinned
  to an exact version. Fonts may come from Google Fonts, with a system font
  later in every `font-family` so the game still works without them.
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
  game's name: every game on this site shares one origin.
- The `<head>` has a `<title>`, a viewport meta tag and a one-sentence
  `<meta name="description" content="...">`. The index and colophon show
  that description.

## Games that started as claude.ai artifacts

An artifact may call `window.claude` for shared storage or sign-in. That
never exists on this site, so every such call must sit behind a feature
check and fall back to `localStorage` (Doodle Chomp's high scores and
Letterfield's field notes already do). When bringing a new artifact over:

1. Read it with the Artifact tool, then move the `<title>`, `<link>` and
   first `<style>` tags the artifact service leaves at the top of `<body>`
   into a proper `<head>`, and add the description.
2. Drop `<meta name="claude:viewport-fit-sides">`; nothing here reads it.
3. Put the artifact's URL in the commit message so the colophon links back
   to it.

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
uv run ./build.sh && python3 -m http.server -d _site 8000   # preview the real site
```

The smoke tests load every game at phone and desktop sizes and fail on
console errors, uncaught exceptions, failed requests, sideways scrolling or
text inputs under 16px. They also check the `<head>` metadata, CDN version
pins and the README link.

In a Claude Code on the web sandbox, the default network policy can block
`cdn.jsdelivr.net`, `cdnjs.cloudflare.com`, `fonts.googleapis.com`,
`fonts.gstatic.com` and `cdn.playwright.dev`. A test failing with
`Failed: https://...` for one of those hosts means the sandbox can't reach
it, not that the game is broken. Ask for those hosts to be allowed. CI has
full network access.

## Security

This repo is public. Keep secrets, internal hostnames and work specifics out
of games, tests and commit messages, and never host someone else's HTML here.
