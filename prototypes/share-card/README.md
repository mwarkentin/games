# Share-card prototype (throwaway)

Proof that a Cloudflare Worker can draw Letterfield's find picture as a PNG
for link previews. It goes with [docs/link-previews.md](../../docs/link-previews.md).
It is **not** part of the site or the real Worker: nothing builds, tests or
deploys it, and it can be deleted at any time.

- `src/card.js`: `findImage()` from `letterfield.html`, ported to SVG
  (light and dark themes), drawn from the Worker's own map (`worker/src/`), and
  `parseFind()`, which checks a `f-<word>-<x>-<y>-<d>` slug is really on the
  map.
- `src/index.js`: a Worker answering `/f/<slug>` (a tiny page with Open Graph
  tags that sends people on to the game) and `/f/<slug>.png` (the card,
  rendered with `@resvg/resvg-wasm` and kept in the Cache API). `/f/d/<slug>`
  draws the dark card.
- `src/metrics.json`: the fonts' advance widths, so text can be fitted
  without a canvas (`scripts/metrics.py` makes it).
- `scripts/bench.js`: renders a few cards in Node and times them.

## Trying it

```sh
cd prototypes/share-card
npm ci
sh scripts/fonts.sh                 # the three OFL fonts, from Google Fonts
node scripts/bench.js               # PNGs in out/ (the last two dark)
npx wrangler@4.151.0 dev            # then open http://localhost:8787/f/f-muddy-42-89-7
npx wrangler@4.151.0 deploy --dry-run --outdir dist   # bundle size
```

## What it showed (November 2026)

- Bundle: 3.0 MiB, or 1.26 MiB gzipped (resvg's wasm is 2.4 MiB of it;
  fonts 350 KiB). The real Worker today is 372 KiB, or 163 KiB gzipped.
- Rendering: 40–60 ms a card once warm, in Node and in `wrangler dev`, with
  the first one at 130–180 ms (wasm start-up). PNGs come out at 95–110 KB
  light and 99–132 KB dark.
- resvg 2.6 sets a whole `<text>` in the wrong face when a `<tspan>` changes
  font, so each run of one font is its own `<text>`.
- Martian Mono lacks the diagonal arrows (↘ ↙ ↖ ↗); the arrow is set in
  Schibsted Grotesk.
