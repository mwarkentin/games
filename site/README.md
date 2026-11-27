# games-site: the live site on Workers static assets

`games-site` serves games.michaelwarkentin.com from Cloudflare instead of
GitHub Pages: the whole of `_site/`, as `build.sh` assembles it, as static
assets with no code (`wrangler.toml`). It has served the site since
2026-11-27. GitHub Pages still deploys the same build behind it, so moving
back stays one change (see Rolling back) until the end of the cutover.

`worker/VIRAL.md` (section "An option: serving the site from Workers static
assets") has the reasons: no Pages bandwidth or build limits, caching set per
path, rollbacks in seconds, and one platform for the site, the API, share
cards and previews. Static asset requests are free on Workers Paid, which
the account already has.

## How it serves the site

- **Addresses, as on Pages.** `/war` serves `war.html`; `/` serves
  `index.html`; `/changelog/war` serves `changelog/war.html`. Query strings
  are ignored for finding the file, so `/war?room=ABCD` is the War page.
- **One difference: `.html` and trailing-slash addresses redirect.** Pages
  answers `/war.html` with the page itself; here it's a 307 to `/war`
  (query string kept), and so is `/war/`, which Pages answers with a 404.
  `index.html` and `/index` go to `/`. `sw.js` already treats `/war.html` as
  `/war`, and saves pages without the redirect, which Safari would refuse.
  Pull request previews have done this all along.
- **Not found.** Any address with no file gets `404.html` (built by
  `scripts/build_headers.py`) with a 404. Pages uses that file too, in place
  of GitHub's own.
- **Caching,** from `_headers` (built by `scripts/build_headers.py`, which
  explains each choice):

  | Path | Cache-Control | On Pages |
  |---|---|---|
  | Pages (`/`, `/war`, `/changelog/war`...) | `public, max-age=0, must-revalidate` | `max-age=600` |
  | `/sw.js` | `no-cache` | `max-age=600` |
  | `/js/*` (modules, hashed or not) | `public, max-age=0, must-revalidate` | `max-age=600` |
  | `/manifests/*`, `/games.json`, `/sitemap.xml`, `/robots.txt` | `public, max-age=600` | the same |
  | `/icons/*`, `/previews/*`, `/music/*` | `public, max-age=604800` (a week) | `max-age=600` |

  Every response has `Access-Control-Allow-Origin: *`, as on Pages. Each
  file has an ETag, so revalidating an unchanged one is a 304.
- **The service worker** behaves as on Pages: the same origin and the same
  addresses, so every player's offline copies, `localStorage` and
  installed apps carry over untouched. Pages still come from the network
  first with the 4-second fallback, and modules from their hashed copies.
- **Nothing that reads the hostname changes:** telemetry, analytics,
  Turnstile's widget and the API's `ALLOWED_ORIGINS` all see
  games.michaelwarkentin.com as before.
- **Added by Cloudflare, not the build:**
  - Cloudflare Web Analytics' automatic setup puts its beacon
    (`static.cloudflareinsights.com`) into every page served to a browser.
    It's on purpose, on trial beside Counterscale (see Analytics in
    AGENTS.md), and switched off in the dashboard: Web Analytics → the
    site → disable automatic setup.
  - Network Error Logging headers (`report-to`, `nel`), Cloudflare's
    default, which report failed connections only.
  - Neither is in `_site/`, so local runs, `wrangler dev` and previews
    never have them.
- **No other address.** `workers_dev` and `preview_urls` are off: the Worker
  answers only through its route on games.michaelwarkentin.com, so there's
  never a second copy of the site on another origin. Pull requests keep their previews on
  `games-preview`, a separate Worker with the same asset rules, so no
  preview can become the live site.

`tests/test_site_worker.py` serves the built site through `wrangler dev`
with this config and checks all of the above.

## Deploying

`.github/workflows/site.yml` builds the site as `pages.yml` does and runs
`wrangler deploy` here, on every push to `main` and by hand, with the same
`CLOUDFLARE_API_TOKEN` secret and `CLOUDFLARE_ACCOUNT_ID` variable as the
leaderboard's deploy. It's skipped until the repository variable
`SITE_ON_WORKERS` is `true` (set by mwarkentin/infra, `games.tf`).

`pages.yml` keeps deploying the same build alongside, until the end of the
cutover.

## How the domain reaches it

All in mwarkentin/infra:
- **The route:** `cloudflare_workers_route.games_site` in
  `worker_domains.tf` sends `games.michaelwarkentin.com/*` to `games-site`.
- **The record:** `cloudflare_dns_record.games` in
  `dns_michaelwarkentin.tf` is proxied, so every request reaches the route.
  It still names `mwarkentin.github.io`, which nothing reaches while it's
  proxied.
- **Why not a custom domain:** a custom domain makes its own record, and
  Cloudflare won't make one while another exists for the name, so moving
  would have meant two applies with the site offline between them.
- **The certificate** is the zone's Universal SSL one.
- **HTTPS:** the zone's Always Use HTTPS redirects plain HTTP, which Pages
  did itself.

Wrangler leaves the route alone, because `wrangler.toml` declares no
`routes`. Keep it that way.

## The cutover

1. **Done, 2026-11-27:** the deploys turned on (infra#45), the first deploy
   ran by hand, and the route and proxied record went live (infra#46).
2. **Check it** whenever something about serving changes:

   ```sh
   curl -sI https://games.michaelwarkentin.com/war
   #   server: cloudflare and a cf-ray header (Pages sent server: GitHub.com, via: 1.1 varnish)
   #   content-type: text/html; charset=utf-8
   #   cache-control: public, max-age=0, must-revalidate
   #   access-control-allow-origin: *
   curl -sI https://games.michaelwarkentin.com/sw.js | grep -i cache-control     # no-cache
   curl -sI https://games.michaelwarkentin.com/icons/war-192.png | grep -i cache  # public, max-age=604800
   curl -sI 'https://games.michaelwarkentin.com/war.html?room=ABCD' | grep -i location   # /war?room=ABCD
   curl -s -o /dev/null -w '%{http_code}\n' https://games.michaelwarkentin.com/nope       # 404
   curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://games.michaelwarkentin.com/war   # 301 to https
   ```

   Then in a browser: a game plays, its leaderboard loads, Letterfield
   joins the survey, a page works offline once visited, and Sentry and
   Counterscale keep receiving. A phone that had the site installed should
   carry on as before.
3. **After a week or two,** once nothing has needed moving back:
   - Delete `pages.yml`, and update AGENTS.md and this file.
   - In mwarkentin/infra, make the `games` record's target something that
     isn't Pages.
   - Remove the custom domain from the repository's Pages settings, then
     turn Pages off.

Don't change any of this in the week of an expected traffic spike.

## Rolling back

- **A bad deploy** (the site's broken, the platform's fine): roll the
  Worker back to the version before. Each version holds its assets, so
  this brings the old site back at once, without a build:

  ```sh
  cd site
  npx wrangler@4.151.0 deployments list    # each version's message is its commit
  npx wrangler@4.151.0 rollback <version-id> --message "Back to <commit>"
  ```

  The next push to `main` deploys again, so fix or revert there too.
- **Back to Pages** (anything about Workers itself): one infra pull request
  setting `proxied = false` and `ttl = 600` on `cloudflare_dns_record.games`.
  The route can stay: DNS-only traffic never reaches it.
  - Pages has kept deploying every push, so it serves the current build.
  - This works only while GitHub's certificate for the name lasts, since
    GitHub can't renew it behind the proxy. That's one more reason to keep
    the fallback window short.
  - Set `SITE_ON_WORKERS` to `false` (`games.tf`) to stop the Worker's
    deploys until the next try.

Both keep every player's offline copies and `localStorage`: the origin
never changes.
