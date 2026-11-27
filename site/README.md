# games-site: the live site on Workers static assets

`games-site` serves games.michaelwarkentin.com from Cloudflare instead of
GitHub Pages: the whole of `_site/`, as `build.sh` assembles it, as static
assets with no code (`wrangler.toml`). It's ready but not switched on. Until
the cutover below, GitHub Pages serves the site as before.

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
- **No other address.** `workers_dev` and `preview_urls` are off: the Worker
  answers only at its custom domain, so there's never a second copy of the
  site on another origin. Pull requests keep their previews on
  `games-preview`, a separate Worker with the same asset rules, so no
  preview can become the live site.

`tests/test_site_worker.py` serves the built site through `wrangler dev`
with this config and checks all of the above.

## Deploying

`.github/workflows/site.yml` builds the site as `pages.yml` does and runs
`wrangler deploy` here, on every push to `main` and by hand, with the same
`CLOUDFLARE_API_TOKEN` secret and `CLOUDFLARE_ACCOUNT_ID` variable as the
leaderboard's deploy. It's skipped until the repository variable
`SITE_ON_WORKERS` is `true`. A deploy alone makes nothing live: until
mwarkentin/infra gives the Worker its domain, it answers nowhere.

`pages.yml` keeps deploying the same build alongside, until the end of the
cutover.

## The cutover

Do it at a quiet time. **Not in the week of an expected traffic spike** (a
launch, a post, a mention), and not as a reaction to one: Pages serves a
spike fine, and going past its soft bandwidth limit once brings an email,
not an outage. A DNS change mid-spike is a risk for no gain.

### 1. Turn on the deploys

1. Merge this pull request. Nothing changes for players.
2. In the repository's Settings → Secrets and variables → Actions →
   Variables, add `SITE_ON_WORKERS` = `true`.
3. Run **Deploy site to Workers** by hand (Actions → the workflow → Run
   workflow) and check it succeeds. This creates the `games-site` Worker.
   The token needs Workers Scripts: Edit on the account, which the
   leaderboard's deploy already uses; if it's limited to named scripts,
   add `games-site` in mwarkentin/infra first.
4. Check the latest pull request's preview, which serves the same build by
   the same rules, on a phone: a game, the offline copy, a 404.

### 2. Move the domain (in mwarkentin/infra)

The `games.` record is DNS only today, pointing at GitHub Pages. It's
replaced by a Workers custom domain, made the same way `worker_domains.tf`
makes `api.games.michaelwarkentin.com`; Cloudflare makes the DNS record and
the certificate itself. Follow the existing resource for the API's domain,
which has the provider version's exact arguments; with the Cloudflare
provider's v5 it's:

```hcl
# worker_domains.tf
resource "cloudflare_workers_custom_domain" "games_site" {
  account_id = var.cloudflare_account_id   # as the API's domain does
  zone_id    = cloudflare_zone.michaelwarkentin_com.id   # or the zone variable it uses
  hostname   = "games.michaelwarkentin.com"
  service    = "games-site"
  # environment = "production"   # v4 of the provider needs this; v5 doesn't take it
}
```

and the record that points at Pages goes, whatever it's called there, for
example:

```hcl
# remove:
resource "cloudflare_dns_record" "games" {
  zone_id = ...
  name    = "games"
  type    = "CNAME"
  content = "mwarkentin.github.io"
  proxied = false
}
```

Cloudflare won't make a custom domain for a hostname that already has a DNS
record, so this takes two applies, a minute apart at most (players with the
site installed keep playing from their offline copies meanwhile):

1. `tofu apply` with the record removed (or
   `tofu apply -target=<the record's address>` after deleting it from the
   config).
2. `tofu apply` with the custom domain added. Wait for its certificate
   (usually under a minute; the dashboard's Worker → Settings → Domains &
   Routes shows it).

If the repository's GitHub Pages settings are managed there too (a
`github_repository`'s `pages` block with a `cname`), leave them as they are
for now: Pages keeps the custom domain set, and its certificate, so moving
back is only DNS. In the GitHub UI the same applies: don't remove the
custom domain from Settings → Pages yet. GitHub will say the domain's DNS
no longer points at it; that's expected.

### 3. Check it

Each of these from outside Cloudflare's dashboard, after DNS has had a few
minutes (`dig +short games.michaelwarkentin.com` gives Cloudflare's
addresses, not GitHub's 185.199.108–111.153):

```sh
curl -sI https://games.michaelwarkentin.com/war
#   server: cloudflare
#   cf-ray: ...                      (Pages sends neither; it says server: GitHub.com, via: 1.1 varnish)
#   cache-control: public, max-age=0, must-revalidate
#   access-control-allow-origin: *
curl -sI https://games.michaelwarkentin.com/sw.js | grep -i cache-control     # no-cache
curl -sI https://games.michaelwarkentin.com/icons/war-192.png | grep -i cache  # public, max-age=604800
curl -sI 'https://games.michaelwarkentin.com/war.html?room=ABCD' | grep -i location   # /war?room=ABCD
curl -s -o /dev/null -w '%{http_code}\n' https://games.michaelwarkentin.com/nope       # 404
```

Then in a browser: a game plays, its leaderboard loads (the API checks the
origin, which hasn't changed), Letterfield joins the survey, the page
works offline once visited, and Sentry and Counterscale keep receiving
(both check the hostname). A phone that had the site installed should
carry on as before.

### 4. After a week or two

Once nothing has needed moving back:

1. Delete `pages.yml`, and update AGENTS.md and this file to say the site
   is on Workers.
2. Remove the custom domain from the repository's Pages settings (in
   mwarkentin/infra, or Settings → Pages), then turn Pages off.

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
- **Back to Pages** (anything about Workers itself): the reverse of step 2.
  Remove the custom domain, then put the DNS-only record pointing at Pages
  back, two applies as before. Pages has kept deploying every push, so it
  serves the current build. Set `SITE_ON_WORKERS` to `false` (or delete
  it) to stop the Worker's deploys until the next try.

Both keep every player's offline copies and `localStorage`: the origin
never changes.
