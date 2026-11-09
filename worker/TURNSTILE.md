# Turnstile for Letterfield's shared survey

Whether a [Turnstile][ts] check before joining would keep bots out of
Letterfield's shared survey ([SURVEY.md](SURVEY.md)), what it would cost
players and us, and what it needs outside this repo. This branch includes a
prototype, switched on in steps (see [Switching it on](#switching-it-on)):
- the Worker: `src/survey-pass.js`, and the pass check in `routeSurvey` in
  `src/survey.js`. With the `TURNSTILE_SECRET` secret it hands out passes;
  only with `TURNSTILE_REQUIRED = "true"` in `wrangler.toml` does it turn
  away joins without one.
- the game: `TURNSTILE_SITE_KEY` in `letterfield.html`. With a site key it
  gets a pass before joining.

Docs were read on 2026-11-06. Links are at the end.

**Recommendation, in short:** merge the prototype switched off. Hand out
passes and count joins without one if you want the signal, but require
passes only if the survey is being charted by many addresses at once. On its
own Turnstile stops cheap scripts, but a determined bot pays a solver
service about a tenth of a cent per address per day to get past it. The
per-address limits already in place do most of the work. See
[Recommendation](#recommendation).

## What's left to stop

The map and its generator are in the page, so a script can list every word
without playing. The survey already limits each hashed IP address (see
"Limits per address" in SURVEY.md):

| limit | per address | what it stops |
| --- | --- | --- |
| claims (rate-limiting binding) | 6 a minute | one script racing everyone |
| words charted in the shared world (counted by the Atlas) | 300 a UTC day | one address charting a lot slowly |
| sockets in one sector | 40 | a few addresses filling a sector |
| new sockets (rate-limiting binding) | 120 a minute | flooding every sector |

At 300 a day, charting all 1,119,752 words takes one address about 3,700
days. It takes 3,700 addresses one day. That's a small botnet, or a
residential proxy pool rented by the gigabyte. Everything an address is
allowed, a pool gets once per address. Turnstile is meant to make each of
those addresses also prove it's a browser with a person at it.

## How it would work

```
 page ──(1) api.js, challenge──▶ challenges.cloudflare.com
   │                                    ▲
   ├──(2) POST /v1/survey/pass {token}──▶ Worker ──(3) siteverify──┘
   │◀──── {pass, expires} ─────────────┘
   └──(4) wss /v1/survey/<sx>/<sy>?pass=… ──▶ Worker checks the pass ──▶ Sector
```

1. **The widget.** The game loads
   `https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit`
   only when it's about to join the survey and has no pass, and renders the
   widget into an empty box. The widget is made in **Managed** mode, and
   the game renders it with `appearance: 'interaction-only'` ([widget
   configurations][config]): Cloudflare
   decides whether a visitor needs to tick a box, "most visitors see no
   prompt" ([widget types][modes]), and the box takes no space until then.
   **Invisible** mode would never show a box, but it requires a privacy
   policy that references Cloudflare's Turnstile Privacy Addendum, which
   this site doesn't have, and it gives a visitor Cloudflare is unsure of no
   way through. **Non-interactive** shows a spinner to everyone. The game
   sets `action: 'survey'`, which siteverify hands back, so a token from
   some other widget on the account can't be used.
2. **The token goes to the Worker.** Tokens are at most 2,048 characters,
   last 300 s and can be checked once ([server-side validation][verify]).
   The page sends it as JSON with `Content-Type: text/plain`, like the
   leaderboard's POSTs, so there's no CORS preflight.
3. **The Worker asks siteverify.**
   `POST https://challenges.cloudflare.com/turnstile/v0/siteverify` with the
   secret, the token, the player's IP (`remoteip`) and an `idempotency_key`,
   so that one retry after a network error or `internal-error` can't be
   counted as a second use. The Worker checks `success`, then `action` and
   `hostname` against what it expects ([verify][verify]).
4. **A pass for every socket.** One token can't cover a player: they hold up
   to four sector sockets, open about ten an hour as they roam, and every
   socket reconnects after a deploy. So the Worker answers with a pass:
   `<expires>.<HMAC-SHA256 of the hashed address and the expiry>`. It lasts
   an hour. The game keeps it in `localStorage` (`letterfield.surveyPass.v1`)
   and adds `?pass=` to each sector's WebSocket URL; browsers can't set
   headers on a WebSocket. The Worker checks the HMAC itself: no storage, no
   Durable Object, no call to Cloudflare. The pass holds no address, only a
   signature over its hash.
   - **It works only from the address it was issued to** (the same /64 for
     IPv6). Otherwise one solved challenge could be handed to a whole proxy
     pool, which is the attack this is for. A phone that moves from Wi-Fi to
     mobile data is asked again; for almost everyone that's invisible.
   - **A join without a good pass** goes ahead while `TURNSTILE_REQUIRED`
     isn't `"true"`, and its sector counts it (see below). Once it is, the
     Worker answers the join itself, never waking the sector: it accepts the
     socket, sends `{t: 'unverified'}` and closes with code 4001. A refused
     WebSocket upgrade tells a browser nothing, so this is how the game
     learns to get a new pass. A pass refused within 15 s of being issued
     counts as a failure, so a fault can't loop the player through
     challenges.
   - **The game always tries for a pass** when it has a site key. If it
     can't get one (Turnstile blocked, refused or unreachable), it joins
     without one, unless a sector has already answered `unverified`; then
     it surveys alone and tries again later.
   - **The key** is derived from the Turnstile secret with an HMAC and its
     own label, so there's still one secret to manage, and rotating it ends
     every pass.
   - **Asking for passes** counts against the `SURVEY_JOINS` limit
     (120 a minute per address), under its own key.

The prototype answers:

```
POST /v1/survey/pass  {"token": "..."}
  → 200 {"pass": "1793003600000.Kq…", "expires": 1793003600000}
  → 400 malformed token · 403 refused by Turnstile, or another origin
  → 429 asked too often · 503 Turnstile unreachable · 404 while TURNSTILE_SECRET is unset
```

While `TURNSTILE_SECRET` is unset the Worker behaves exactly as before,
whatever `TURNSTILE_REQUIRED` says, and while `TURNSTILE_SITE_KEY` is empty
the game never loads Turnstile. `?turnstile=<site key>` turns it on in the
game for testing, the way `?survey=` does.

### Counting joins without a pass

With the secret set and passes not yet required, the Worker marks each join
without a good pass with an `X-Survey-Unpassed: 1` header on the request it
forwards, after deleting any copy the player sent (as it does
`X-Survey-Address`). The sector counts them and sends the number since its
last report as `unpassed` in its Atlas report, and puts it back if the
report fails. The Atlas adds them up with the rest of the day's numbers
(see "Watching for bots" in SURVEY.md), and `GET /v1/survey/world` shows
the day so far and the day before:

```
"today":     {"day": 20398, "charted": 412, "addresses": 31, "capped": 0, "playerHours": 9.5, "unpassed": 41},
"yesterday": {"day": 20397, "charted": 980, "addresses": 64, "capped": 1, "playerHours": 22.1, "unpassed": 12}
```

`day` is days since 1970, in UTC. The count lives in the Atlas's memory, so
an eviction restarts the day; sectors outside the shared world don't report,
so joins there aren't counted. The daily **Watch the survey for bots**
workflow (`scripts/survey_watch.py`) raises it once `TURNSTILE_SITE_KEY` is
set in `letterfield.html`, when yesterday had at least 500 joins without a
pass and at least 5 per player-hour: a player roaming opens about 10
sockets an hour, so that's as if half of all play came from browsers that
block Turnstile. Before the site key is in the game, every join comes
without a pass, so the script ignores the count. Once the site key is in the game, nearly
every player has a pass, so these joins are almost all scripts. A rising
count is the signal to require passes; a count near zero says there's
nothing to stop yet.

## Switching it on

1. **Infra apply** in mwarkentin/infra: the widget and the
   `TURNSTILE_SECRET` Actions secret (see below).
2. **Deploy** the Worker. It hands out passes and checks them, but enforces
   nothing: every join still goes ahead, and the game doesn't ask for passes
   yet, so the count is every join and means little.
3. **Optionally, commit the site key** in `TURNSTILE_SITE_KEY`. The game now
   gets a pass before joining, and `unpassed` fills in with the joins that
   came without one: scripts, mostly, plus players whose browser blocks
   Turnstile.
4. **To enforce,** set `TURNSTILE_REQUIRED = "true"` in `wrangler.toml` and
   deploy. Joins without a pass are turned away; players who can't pass
   survey alone. Setting it back to `"false"` and deploying undoes it.

Step 4 without step 3 would turn every player away, so do them in order.

Where it stands: steps 1 to 3 are done. mwarkentin/infra#8 made the widget
and the secret, a deploy gave the Worker the secret, and the widget's site
key is committed in `letterfield.html`. Passes aren't required. Until
`SURVEY_URL` is set, the survey itself, and so Turnstile, stays off on the
live site. On `localhost` the real key fails, because the widget only
allows games.michaelwarkentin.com, and the game then joins without a pass.
Test locally with `?turnstile=1x00000000000000000000BB` (see below).

## Tests

Nothing calls Cloudflare. `worker/test/survey-pass.test.js` fakes
siteverify and uses Cloudflare's documented always-passes test secret
(`1x0000000000000000000000000000000AA`) and dummy token
(`XXXX.DUMMY.TOKEN.XXXX`) ([testing][testing]). It covers passes (address,
expiry, tampering), siteverify's answers and retries, the endpoint, and
joins with and without a pass for each combination of secret and switch,
including the `X-Survey-Unpassed` mark (set by the Worker, never passed on
from the player). `worker/test/survey.test.js` checks that sectors count
joins without a pass in their reports, keeping the count if a report fails,
and that the Atlas adds them up per UTC day. `tests/test_letterfield_survey.py` answers
`api.js` with a fake `turnstile` object given the invisible always-passes
test site key (`1x00000000000000000000BB`). Its other tests serve the game
with `TURNSTILE_SITE_KEY` blanked (`without_turnstile`), and one checks that
the game uses the key it's published with when `?turnstile=` isn't given.
They check that:
- one check covers every sector, and a reload or roaming doesn't ask again;
- the box shows only when the widget wants a tap;
- a refused pass gets a new one;
- a failed check, a refused token or a blocked `challenges.cloudflare.com`
  joins without a pass while passes aren't required, and leaves the player
  surveying alone, with their finds saved, once a sector asks for one.

`wrangler dev` with the test keys would run the real siteverify call, but
this sandbox can't reach `challenges.cloudflare.com`, so it wasn't tried.

## What it costs players

- **Time before joining.** A script load from `challenges.cloudflare.com`,
  the challenge, and one round trip to the Worker, before the first sector
  joins. Cloudflare publishes no typical figure, and it couldn't be
  measured from here. It happens about once an hour per address; reloads
  and roaming reuse the pass. The game itself never waits: the map, circling
  and field notes work at once, and the survey panel says "Checking this is
  a person, not a bot…".
- **Privacy.** Turnstile runs Cloudflare's code in the player's browser,
  which collects browser signals; Cloudflare says it "processes only the
  data strictly necessary" and doesn't read form entries
  ([overview][ts]). Cloudflare also sees the player's IP address, which it
  sees when they load the script anyway; the Worker sends it again as
  `remoteip`. The Worker keeps nothing new, and the pass holds no address.
  The colophon should say the survey uses Turnstile. (Cloudflare's privacy
  addendum couldn't be fetched from this sandbox.)
- **Accessibility.** Managed mode never shows a puzzle, only a checkbox when
  it's unsure. Cloudflare's plans page says WCAG 2.2 AAA and its overview
  says WCAG 2.2 AA ([plans][plans], [overview][ts]). The game's box sits at
  the bottom middle, clear of the safe area, with a line saying why it's
  there. Players who can't pass join without a pass until passes are
  required, and after that survey alone, never locked out of the game.
- **When it fails.** A blocked `challenges.cloudflare.com` (ad blockers,
  school and work filters, some privacy browsers) usually fails as error
  200500 or a script that never loads; a wrong device clock as 110600 or
  200100; an unsupported browser through `unsupported-callback`
  ([client-side errors][errors]). VPN and Tor users are more likely to be
  challenged or refused. While passes aren't required, the game joins
  without one and nothing changes for the player. Once they are, the panel
  says "Couldn't check this is a person, so you're surveying alone for now"
  and the finds still save. Either way the game asks Turnstile again after
  30 s, then 1, 2, 4 and up to 10 minutes.
- **Offline and solo.** Unchanged. Without a survey there's no Turnstile at
  all. Offline, the script fails to load and the game goes on alone, as it
  does now. The service worker leaves `challenges.cloudflare.com` alone,
  which matters: Cloudflare says `api.js` must be loaded from its own
  address, and proxying or caching it breaks Turnstile
  ([client-side rendering][client]).
- **Home-screen apps** on iPhone keep their own `localStorage`, so they get
  their own pass.

## What it costs us

- **Turnstile is free.** The free plan has unlimited challenges and
  siteverify calls, up to 20 widgets per account and 10 hostnames per
  widget ([plans][plans]). Enterprise adds ephemeral IDs (a device
  identifier across addresses), Bot Fight Mode for widgets, and widgets for
  any hostname.
- **Worker requests.** One more per pass: at most one per player-hour, and
  usually less. The siteverify call is a subrequest from that same request,
  not another Worker request; the free plan allows 50 subrequests per
  request and this uses one or two ([limits][limits]). Checking a pass is an
  HMAC, well inside the free plan's 10 ms of CPU.
- **Durable Objects.** No change for players. A join without a pass never
  reaches a sector, so bots without passes cost less than they do now.

The effect on SURVEY.md's cost table:

| | now | with Turnstile |
| --- | --- | --- |
| Worker requests per player-hour | ~30 | ~31 |
| Durable Object requests per player-hour | ~106 | ~106 |
| free plan: player-hours a day before Worker requests run out | ~3,300 | ~3,200 |
| free plan: first limit hit | Durable Object requests, ~940 player-hours | the same |
| viral fortnight (1.68 M player-hours) | ~$57 | ~$57.50 |

## What it needs outside this repo

**mwarkentin/infra** (OpenTofu) would add a widget and hand its secret
here, as it does `IP_SALT`. A sketch, from the provider's
`cloudflare_turnstile_widget` resource ([provider docs][tf]):

```hcl
resource "cloudflare_turnstile_widget" "letterfield_survey" {
  account_id = var.cloudflare_account_id
  name       = "Letterfield shared survey"
  domains    = ["games.michaelwarkentin.com"]
  mode       = "managed"
  region     = "world"
}

resource "github_actions_secret" "games_turnstile_secret" {
  repository      = "games"
  secret_name     = "TURNSTILE_SECRET"
  plaintext_value = cloudflare_turnstile_widget.letterfield_survey.secret
}

output "letterfield_turnstile_sitekey" {
  value = cloudflare_turnstile_widget.letterfield_survey.sitekey   # public: goes in letterfield.html
}
```

- infra's own Cloudflare token needs permission to edit Turnstile widgets.
  The deploy token here doesn't: it only uploads the secret.
- `localhost` stays off the widget: local testing uses Cloudflare's test
  keys, which work anywhere.
- The site key isn't a secret. It's committed in `TURNSTILE_SITE_KEY` once
  infra has made it.

**This repo**, already on this branch:
- `.github/workflows/leaderboard.yml` uploads `TURNSTILE_SECRET` with
  `IP_SALT` when the Actions secret exists, and skips it when it doesn't,
  so deploys keep working before infra sets it.
- `wrangler.toml` sets `TURNSTILE_REQUIRED = "false"`, the switch in step 4
  of [Switching it on](#switching-it-on).
- `wrangler.toml` sets `TURNSTILE_HOSTNAMES` to the site's hostname, so
  siteverify's `hostname` is checked too. For `wrangler dev` with test keys,
  set `TURNSTILE_HOSTNAMES=` and `TURNSTILE_SECRET=1x0000000000000000000000000000000AA`
  in `.dev.vars`, and open the game with
  `?survey=http://localhost:8787&turnstile=1x00000000000000000000BB`.
- AGENTS.md's host rules now allow `challenges.cloudflare.com` for
  Letterfield's survey, loaded only once a site key is set.

**Other things to know:**
- **CSP.** The site sends none (GitHub Pages can't set headers, and no page
  has a `<meta>` policy). If one is added, Turnstile needs
  `https://challenges.cloudflare.com` in `script-src` and `frame-src`, or a
  nonce on the script tag ([CSP][csp]).
- **Sentry replays.** The widget is a cross-origin iframe, which replays
  can't look inside, so they show an empty box. The token goes in a POST
  body, and replays don't record request bodies unless
  `networkDetailAllowUrls` asks; `telemetry.js` doesn't. The pass is in the
  WebSocket URL, which Sentry doesn't record, and it's no use from another
  address anyway.
- **Analytics.** Counterscale sends the page path only, so `?turnstile=`
  never reaches it.

## How much it stops

- **Plain scripts** (a loop over the generator with a WebSocket client):
  stopped. They have no browser to run the challenge in, and every join
  without a pass ends at the Worker.
- **Headless browsers** (Playwright, Puppeteer): mostly challenged or
  refused, because Turnstile looks for automation. "Stealth" setups get
  through some of the time; how often isn't published, and it's an arms
  race Cloudflare runs, not us.
- **Solver services** (CapSolver, 2Captcha and others): get through. They
  sell Turnstile tokens for a site key, solved by their own browsers or
  people, for roughly $0.80 to $3 per 1,000 according to third-party
  comparisons ([Bright Data][bd], [ipcost][ipcost]); vendor prices weren't
  checked. A token isn't tied to the browser that solved it. siteverify
  takes `remoteip`, but the docs don't say it refuses a token solved
  elsewhere.
- **So against a botnet:** the 3,700 addresses that could chart the world
  in a day need one pass each per hour of claiming. 300 claims at 6 a
  minute take 50 minutes, so that's about one pass per address per day:
  roughly 3,700 solves, **$3 to $11**. Renting the addresses costs the bot
  far more than that. Turnstile raises the bar from "write a script" to
  "write a script and pay a solver", which deters the casual and barely
  slows the determined.
- **Compared with the per-address limits.** They do the heavy lifting:
  they're exact about what one address can do, cost nothing per player, and
  can't be bought past. Turnstile adds one thing they can't: it's a check
  per *browser*, so it prices out the cheapest addresses (free proxy lists,
  data-centre ranges) that come with no browser behind them.
- **What would do more:** Enterprise ephemeral IDs, which tie tokens to a
  device across addresses; or claims-per-pass budgets, which only help once
  passes cost something to get. Neither stops a solver service either.

## If the domain moves onto Cloudflare

With `michaelwarkentin.com` as a zone on the account (the site can stay on
GitHub Pages behind it):

- **A custom domain for the Worker,** such as
  `api.games.michaelwarkentin.com`. Cloudflare makes the DNS record and the
  certificate ([custom domains][domains]). It also puts the world map in
  front of Cloudflare's cache (see "Edge caching" in SURVEY.md).
- **Pre-clearance.** With the widget's hostname in the zone, a widget can
  also set a `cf_clearance` cookie, at a clearance level chosen on the
  widget, which lets the player skip WAF challenges on that zone up to that
  level, API requests included ([clearance][clearance]). The site and the
  Worker would be same-site, so the cookie goes with the sector WebSockets.
  It needs `connect-src 'self'` under a CSP ([CSP][csp]). Cloudflare
  recommends it mainly to Enterprise customers.
- **WAF rules on the survey path.** A rule could challenge or block
  `/v1/survey/*` without clearance. A WebSocket handshake can't show a
  challenge page, so it would only work with pre-clearance done first, and
  requests the WAF stops never run the Worker, so they cost nothing. Rate
  limiting rules could count per address before the Worker, too. That
  would replace this prototype's pass, but it's more moving parts than an
  HMAC, and the free plan's handful of WAF rules would be spent on one game.
- None of it changes the solver-service picture above.

## Recommendation

1. **Merge the prototype, switched off.** No secret and no site key means
   no change for players or the Worker, and the tests keep it working.
2. **Don't switch it on yet.** Launch with the per-address limits,
   and watch for the signs of a pool: many addresses each claiming near
   the 6-a-minute limit, the charted count climbing faster than the
   players online could manage, or, after steps 1 to 3 of [Switching it
   on](#switching-it-on), a rising `unpassed` count. A charted world is a vanity board; the cost
   of a bot is a less fun survey, not a bill, because `MAX_ONLINE` and the
   Durable Object limits already cap that.
3. **If it's needed,** follow [Switching it on](#switching-it-on): an infra
   apply, a deploy, the site key, then `TURNSTILE_REQUIRED = "true"` and
   another deploy. Expect it to stop scripts and cheap proxies, not a bot
   willing to pay a solver.

[ts]: https://developers.cloudflare.com/turnstile/
[modes]: https://developers.cloudflare.com/turnstile/concepts/widget/
[verify]: https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
[client]: https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/
[config]: https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/widget-configurations/
[testing]: https://developers.cloudflare.com/turnstile/troubleshooting/testing/
[errors]: https://developers.cloudflare.com/turnstile/troubleshooting/client-side-errors/error-codes/
[plans]: https://developers.cloudflare.com/turnstile/plans/
[csp]: https://developers.cloudflare.com/turnstile/reference/content-security-policy/
[clearance]: https://developers.cloudflare.com/cloudflare-challenges/concepts/clearance/
[limits]: https://developers.cloudflare.com/workers/platform/limits/
[domains]: https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
[tf]: https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/turnstile_widget.md
[bd]: https://brightdata.com/blog/web-data/capsolver-review
[ipcost]: https://ipcost.com/articles/best-captcha-solvers-2026-486
