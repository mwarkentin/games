# Share worker

`games-share` draws link-preview cards for shared Letterfield finds, and for
the survey log's views (see "Survey log views" below), at
`https://share.michaelwarkentin.com`. The research and the decisions behind it
are in [docs/link-previews.md](../docs/link-previews.md).

A Letterfield find's link, `/letterfield#f-<word>-<x>-<y>-<d>`, keeps its
word in the `#fragment`, which never reaches a server, so every share used
to unfurl as the game's one fixed preview. With `SHARE_URL` set in
`letterfield.html`, Share hands out this Worker's address instead:

```
GET /f/<slug>        a small page whose og:image is the card. It sends
                     people on to /letterfield#<slug> (meta refresh and
                     location.replace); unfurlers read its tags and stop
GET /f/<slug>.png    the card, 1200×630, about 100 KB
GET /f/d/<slug>…     the same, with a dark card: what a dark page shares
GET /                to the game
```

`<slug>` is the game's own fragment (`hashOf()` in `letterfield.html`).

## What a card says

The word, its theme, its territory's name and where it is all come from the
map: `src/card.js` checks the word is really there with the survey's own
`checkClaim()` and draws `findImage()`'s layout as SVG, which resvg turns
into a PNG. A slug that isn't on today's map (a link from an older map)
still gets a page, with the game's own preview, and goes to the game.

Below that, two lines from the leaderboard Worker's survey, asked directly
through its Durable Objects (see "The share Worker" in
`worker/README.md`):

- **this word:** "CHARTED FIRST · by ZED · 9 Nov 2026", or "NOT YET
  CHARTED", from the word's sector, which knows at once (the survey log can
  be 30 s behind, and apps fetch a preview the moment Share is tapped). Only
  sectors in the shared world are asked, so a card never wakes one nobody has
  played in.
- **the shared map:** "0.4% of the shared map charted", from the Atlas: one
  decimal under 1%, whole percents rounded down after that, "Every word on
  the shared map charted" at the end.

Either line is left off if the survey doesn't answer within 1.5 s, and on
Worker Previews, which have no survey bindings.

## Caching and limits

The page names the card with its state, `/f/<slug>.png?s=cZED.20766.0.4`
(charted by ZED on that UTC day, at 0.4%), so a new state is a new image
URL and an old unfurl keeps its old card. The page is kept at the edge for a
minute.

- **Edge cache:** every card, by its URL. Cards asked for with the state
  they show are kept for a year; one asked for with an old or made-up state
  is drawn as it is now and kept for five minutes.
- **R2 (`games-share-cards`):** cards of charted words in the shared world,
  under `m<map>/<theme>/<slug>/<state>.png`, so each is drawn once
  worldwide. Nothing else goes there, so a script can't fill the bucket.
- **Render limit:** new cards are limited to 30 a minute per address (a
  salted hash, with `IP_SALT`). Over it, the request is sent to the game's
  own preview image. Cards already drawn are never limited.

Drawing a card takes 40–60 ms of CPU, so the Worker needs Workers Paid. The
account has it for the survey.

## Setup

The Cloudflare side is made with OpenTofu in mwarkentin/infra (`share.tf`
and `worker_domains.tf` there), in this order:

1. **R2 buckets** `games-share-cards` and `games-share-cards-previews`, and
   the **`SHARE_DEPLOY` Actions variable**, set to `true` once they exist.
   Until then **Deploy share worker** (`.github/workflows/share.yml`) is
   skipped. The deploy token (`CLOUDFLARE_API_TOKEN`, shared with the
   leaderboard Worker) needs nothing new: a Worker reaches its bucket through
   its binding.
2. **Deploy:** run **Deploy share worker** from the Actions tab, or push a
   change under `share/` (or `worker/src/`, whose code it imports). Deploy
   the leaderboard Worker first if its `/claim` and `/totals` paths are new:
   until then, cards just leave their charting lines off. The Worker then
   answers at `https://games-share.mwarkentin.workers.dev`.
3. **The custom domain** `share.michaelwarkentin.com`, made in infra once the
   Worker exists (a custom domain needs its Worker), as
   `api.games.michaelwarkentin.com` is for the leaderboard Worker. Keep
   `routes` out of `wrangler.toml`, or wrangler takes the domain over.
4. **Try it:** open `https://share.michaelwarkentin.com/f/<slug>` for a word
   you've found, and share it in Slack, iMessage, WhatsApp, Discord, Bluesky
   and Mastodon. Each app keeps the first card it fetches for a URL.
5. **Switch it on:** set `SHARE_URL` in `letterfield.html` to
   `https://share.michaelwarkentin.com`, and add a line to
   `changelog/letterfield.md` for that day.

## Survey log views

A surveyor's, theme's or territory's page of `letterfield-log.html` has a
Share button too. With `SHARE_URL` set in that page, Share hands out this
Worker's `/v/` address for the view instead of the page's own, and attaches
no picture of its own, since the link's card is one (`src/view.js`):

```
GET /v/surveyor/<initials>/<period>/<when>/<from>-<to>   a surveyor's day, week…
GET /v/theme/<th>/<period>/<when>/<from>-<to>            a theme's
GET /v/surveyor/<initials>/all, /v/theme/<th>/all        all time
GET /v/territory/<rx>,<ry>                               a territory (all time)
GET /v/d/…, ….png                                        dark; the card itself
```

- **Pinned:** `<period>` is `hour`, `day`, `week`, `month` or `year`;
  `<when>` is its first day in the sharer's time zone (`YYYY-MM-DD`, with
  `Thh` for an hour), which names it on the card and in the link back; and
  `<from>-<to>` are the UTC hours it covers, the very hours the page asked
  the log for. So a week shared on Monday is still that week on Friday, and
  a card counts what the page did. An address whose hours can't be that
  period in any time zone, or a week that doesn't start on a Monday, is not
  found.
- **The numbers** come from the leaderboard Worker's own log answers
  (`/v1/survey/log/…`), asked through a service binding (`LOG`) under
  `LOG_URL`'s host, so the cards and the page share its queries and its
  cache. If it doesn't answer within 3 s, or there's no binding (Worker
  Previews), the page carries the game's own preview and the card sends
  people to it.
- **What it shows** is the page's own share picture, `shareImage()` in
  `letterfield-log.html`: whose view, the period by its dates, three
  numbers, and the latest words with their themes' dots.
- **Caching:** the card's URL carries a token of its count and latest word,
  `?s=5.<time>`, so it changes with every new word, and a card asked for
  with the state it shows is kept for good at the edge. Views aren't kept in
  R2. New cards share the render limit with finds'.

## Previews

A pull request that changes `share/` doesn't get a Worker Preview of this
Worker yet, and previews blank `SHARE_URL`, so their shares link straight
to the preview's own game. `wrangler.toml` already has the `[previews]`
bindings (a previews bucket, a rate limit apart from production's, no survey
and no log)
for when `preview.yml` makes one, with `--var SITE_URL=<the site preview>`
so its pages send people to the preview.

## Fonts

`fonts/` holds the cards' fonts, subset to the characters cards draw:
Big Shoulders Display, Martian Mono and Schibsted Grotesk, all under the SIL
Open Font License 1.1 (their `*-OFL.txt` files; none has a Reserved Font
Name). `scripts/fonts.py` downloads and subsets them and writes
`src/metrics.json`, their advance widths, which stand in for canvas
`measureText`. Run it after changing a font or the characters:

```sh
uv run share/scripts/fonts.py
```

## Local development

```sh
cd share
npm ci
npx wrangler@4.151.0 dev     # then open http://localhost:8787/f/f-muddy-42-89-7
```

`wrangler dev` has no survey bindings to reach, so cards leave their
charting lines off. The tests run in Node, from the repo root:

```sh
node --disable-warning=ExperimentalWarning --test "share/test/*.test.js"
```

`test/render.test.js` draws real PNGs with the same wasm and fonts, and
checks their size and how long each takes.
