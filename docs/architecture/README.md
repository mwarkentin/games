# Letterfield's architecture, in figures

Figures, interactive explainers, clips and game screens for blog posts on
how Letterfield and its shared survey work, grouped into posts below with
each one's caption and alt text. Every number and name in them comes from
the code or from the map itself; [FACTS.md](FACTS.md) lists each fact with
its source, and the places where the docs and the code disagree.

None of this is part of the site. `build.sh` publishes only the top-level
pages, no test reads `docs/`, and everything rendered goes to
`_architecture/`, which git ignores.

## Making them

```sh
uv run --with fonttools --with uharfbuzz --with brotli docs/architecture/render.py
uv run docs/architecture/capture.py
```

- **`render.py`** draws the static figures in the game's light and dark
  colours, as SVG with every letter an outline (so they need no fonts) and
  as PNG at 2×, 1,600 pixels wide. It builds the interactive explainers with
  the game's fonts inlined, and writes the list of posts below and the list
  in FACTS.md. Name figures to draw only those; `--no-png` skips the PNGs,
  `--explainers` builds the explainers alone, and `--refresh` reads the live
  survey's public numbers again (`data/survey.json`, from GETs the log page
  makes itself, kept without anyone's initials) and `main`'s history
  (`data/history.json`).
- **`capture.py`** records the clips and the game screens. It builds the
  site into `_architecture/site`, serves it, and answers every address of
  the Worker with the tests' own fakes (`tests/fake_*.py`), refusing any
  other host but the fonts' and the CDNs', so nothing reaches production.
  Clips are captured a frame at a time with the page's clock stopped, then
  joined by ffmpeg. Name scenes (`claim`, `supernova`, `log`, `survey`) to
  record only those.

Both need Node (the figures and screens read the map through
`worker/src/letterfield-world.js`), Playwright's Chromium and, once, the
network for the fonts; `capture.py` also needs ffmpeg.

| Source | What it is |
| --- | --- |
| `kit.py` | the drawing kit: the game's palette and faces, text as outlines, panels and arrows |
| `figures.py` | the static figures, each with its caption, alt text and sources, and the posts |
| `extras.py` | the same for the explainers, clips and screens |
| `explainers/*.html` | the interactive explainers |
| `data.mjs` | the map, from the Worker's copy of the game's generator |
| `data/` | the live survey's public totals and `main`'s history, each read once |
| `render.py`, `explainers.py`, `capture.py` | the scripts above |

| Output, in `_architecture/` | What it is |
| --- | --- |
| `figures/<id>-light.svg`, `-dark.svg`, `.png` | the static figures |
| `explainers/<name>.html` | each explainer as a whole page, to host beside a post and embed with an iframe |
| `artifacts/<name>.html` | each explainer as published to claude.ai |
| `clips/<name>.mp4`, `.gif` | the clips: an MP4 for a `<video>`, and a smaller GIF |
| `screens/<name>-light.png`, `-dark.png` | the game screens, at 2× |

To embed an explainer, host its page beside the post and give the iframe
the column's width. Each page lays itself out for the width it gets (the
claim explainer's diagram has a wide, a medium and a phone layout),
follows the reader's light or dark setting and reduced motion, and tells
the page around it how tall it is, so a few lines fit the frame to it:

```html
<iframe src="claim.html" title="The life of a claim" style="width:100%;border:0" height="1400" loading="lazy"></iframe>
<script>
  addEventListener('message', (e) => {
    for (const f of document.querySelectorAll('iframe')) if (f.contentWindow === e.source && e.data?.height) f.height = e.data.height;
  });
</script>
```

Without the script, these heights fit a 680-pixel column: `sectors`
1,470, `claim` 1,390 and `cost` 1,830.

## The look

Everything takes Letterfield's own look: its paper, ink and accent in light
and dark, the hues of its 225 themes for territories, Big Shoulders Display
for titles, Martian Mono for labels and Schibsted Grotesk for text, and the
letter grid with a word circled, as on the game's icon. In the figures each
kind of part keeps one colour: Durable Objects teal, storage copper, Workers
indigo and browsers rose. The people in them are made up (ZED, KIM, SIS and
the rest); the map, its words and its territories are real.

## Posts

A suggested order, each with a line on what it covers and everything made
for it.

<!-- BEGIN POSTS -->
### 1. An endless word search from one seed

Letterfield's map has no edge and nothing stored: one seed, a deck of words for each territory and a few placement rules make every letter, so the server can check a word with the game's own code.

#### A map from a seed

Figure: `figures/map-from-a-seed-light.svg · -dark.svg · .png`

**Caption.** Letterfield's map has no file. Every letter comes from one fixed seed, through a generator small enough to run in the page: a chunk of 12 × 12 cells hashes its coordinates with the seed, deals itself the next nine cards from its territory's shuffled deck of theme words, places six to eight of them in eight directions, and fills the rest with letters drawn from its own words. So every player sees the same endless map, and the survey's server, which runs a copy of the same code, can check that every word anyone claims is really there. This is the real chunk at the origin, in Menorah Hollow, a Festivals territory.

**Alt text.** On the left, the 12 by 12 letter grid of chunk (0, 0) in Menorah Hollow, a Festivals territory, with its seven hidden words circled in the theme's green: TRADITION and YULETIDE reading down, WREATH down and right, DIWALI and RAMADAN down and left, NAVRATRI right to left, and PURIM up and right. On the right, six numbered steps: one seed; chunks of 12 by 12 cells in territories of 4 by 4 chunks whose theme is (rx + 15 ry) mod 225; a shuffled deck per territory, dealt nine cards a chunk; eight directions weighted towards reading forwards, shown as a rose; filler letters; and bonus words of six or more letters. Along the bottom, the four checks the server makes on every claim with its own copy of the generator.

#### 225 themes, laid out so neighbours differ

Figure: `figures/theme-layout-light.svg · -dark.svg · .png`

**Caption.** Each territory takes one of 225 themes, by a formula rather than a table: territory (rx, ry) gets theme (rx + 15·ry) mod 225, so a theme comes round again only 15 territories away in any direction, as far apart as 225 themes can be. The order of the themes in that list was found by a search, so that each territory's eight neighbours differ from it by at least 30 degrees of hue, are of another kind (no two bird themes side by side) and share none of its words. Here are the 900 territories nearest the origin, each in its theme's colour, with every Festivals territory outlined.

**Alt text.** A mosaic of 30 by 30 small squares, each a territory around the map's origin, filled with its theme's colour so that no two neighbours look alike. Four squares are outlined in ink: the Festivals territories at (0, 0), (0, -15), (-15, 1) and (-15, -14), showing that a theme repeats only 15 territories away; a dashed square marks the 15 by 15 block that each theme has to itself. On the right, the formula, and the origin's 3 by 3 neighbourhood with its nine themes: Hafnium Basin (Periodic Table) to the west, Swordtail Vale (Pet Shop) to the east, Pennette Steppe (Pasta) to the north and Sodden Wold (Campsite) to the south, with Menorah Hollow (Festivals) in the middle.

#### The map from far away

Game screen: `screens/far-view-light.png · -dark.png`

**Caption.** Zoomed all the way out, at 2 pixels a cell, the game draws each territory as a tile with its name and theme; the letters come back from 9 pixels a cell. Words charted on the survey show as dots.

**Alt text.** A grid of tinted tiles, each labelled with a made-up place name and its theme, such as Menorah Hollow, Festivals, and Swordtail Vale, Pet Shop. Tiles near the middle are speckled with dots for charted words.

### 2. A Durable Object for every patch of the map

The shared survey shards by place: 625 sectors, each a Durable Object with its own SQLite and sockets, joined four at a time, and one Atlas for the totals, in the spirit of One Million Checkboxes.

#### The universe, cut into sectors

Figure: `figures/universe-light.svg · -dark.svg · .png`

**Caption.** The map goes on for a billion cells each way, but the part everyone charts together, the universe, is the middle 100 × 100 territories: 1,119,752 hidden words. The server cuts it into 625 sectors of 4 × 4 territories, 192 × 192 cells each, and every sector is its own Durable Object. The colours are the territories' themes; the solid patches near the middle are what the survey had charted on 20 November 2026, from its public API, with a star on each territory that has gone supernova.

**Alt text.** A square map of 100 by 100 small territories, faintly tinted in their themes' colours, crossed by a grid of 25 by 25 sectors. Near the centre a small cluster of territories is filled in: the words charted so far. An inset on the right enlarges the 8 by 8 territories around the origin, showing four sectors' boundaries, how much of each territory is charted, and stars on the seven territories inside the universe that have gone supernova. Labels give the sizes: a territory is 48 by 48 cells, a sector 4 by 4 territories and one Durable Object, and the universe 625 sectors; and the live count: 907 of 1,119,752 words charted.

#### The big picture

Figure: `figures/big-picture-light.svg · -dark.svg · .png`

**Caption.** Letterfield is one HTML file on GitHub Pages. Everything shared lives behind one Cloudflare Worker at api.games.michaelwarkentin.com, which holds no state itself: it hashes the player's address, checks the per-address limits, and hands each request to the Durable Object that owns it. Each of the map's sectors is its own object, with its own SQLite storage and the WebSockets of everyone looking at it; one Atlas keeps the world's totals; guilds and linked players get objects of their own. Two D1 databases keep what has to be queried across the whole map: the survey's log, and the leaderboards with their link and recovery codes. A second Worker draws the link-preview cards.

**Alt text.** Architecture diagram. At the top, three pages in the browser served by GitHub Pages: the game letterfield.html, the survey log and the timelapse. Arrows lead down to one Cloudflare Worker, games-leaderboard, which lists its routes and its per-address checks. Below it are Durable Objects: Sector (625 in the shared world, more beyond), Atlas (one), Guild, Player and WarRoom, with arrows from sectors to the Atlas (reports every 10 seconds at most), to guilds (membership checks) and to each other (supernovas and emotes). At the bottom, two D1 databases: games-survey-log, written by sectors from an alarm, and games-leaderboard. On the right, the games-share Worker with its R2 bucket of cards, bound directly to the Sector and Atlas classes, and the outside services: Turnstile, Sentry, Counterscale and Wiktionary with Wikipedia.

#### Inside one sector

Figure: `figures/sector-anatomy-light.svg · -dark.svg · .png`

**Caption.** A sector is one Durable Object: a single thread with its own SQLite storage, holding the claims for 16 territories and the WebSockets of everyone looking at them. Because only one message runs inside it at a time, 'first to claim wins' is a plain INSERT … ON CONFLICT DO NOTHING. Sockets use the WebSocket Hibernation API, so a quiet sector can be evicted from memory while its players stay connected; anything it must still know after waking lives in storage or in each socket's attachment. And there are almost no timers, because a pending timer keeps a Durable Object awake and billed: owed positions and reports go out with the next message instead.

**Alt text.** A large panel labelled Sector 0,0, one Durable Object, in three columns. Left: up to 750 hibernating WebSockets, at most 40 from one address, each with an attachment holding who the player is, where they look and their claim allowance. Middle: its SQLite tables: claims (keyed by word and place, with an index by time), logged, novas, owed, relayed, guild_names and map. Right: what it keeps only in memory and rebuilds after waking: the players, every claim as JSON, charted and hidden counts for its 16 territories, the claim batch, the addresses past today's cap, and each socket's allowances. Along the bottom: the messages it takes and sends, and its only timers: a 200 ms batch, a presence timer when someone leaves a quiet sector, and an alarm that copies claims to the log.

#### Presence, and the Atlas

Figure: `figures/atlas-reports-light.svg · -dark.svg · .png`

**Caption.** Players never talk to the Atlas. Each sector in the universe tells it the sector's numbers at most every 10 seconds while something is changing (charted counts for its 16 territories, who is there, how many words each address charted), riding on the next message rather than a timer. Reports are absolute numbers, so a lost or repeated one does no harm. The Atlas answers with the world's totals, the addresses past today's cap, which guild members are online and any supernova news, and each sector passes those on to its players. Anything global, like the world map and the list of surveyors, is read over HTTP from a short cache, in the spirit of One Million Checkboxes.

**Alt text.** Three sectors on the left, each with players, send reports to the Atlas in the middle, at most every 10 seconds, each listing its players, the charted count of its 16 territories, the middle of its crowd, its surveyors by territory, words charted per address, and supernovas. The Atlas answers each with the world's totals, the addresses past the daily cap, guild members online and new supernovas. On the right, Worker instances fetch the world map from the Atlas at most every 5 seconds and the surveyor list every 10, and browsers cache each. Below the sectors, what players get from their sector: positions once a second for up to 64 people, and the world's totals as they change.

#### What One Million Checkboxes taught

Figure: `figures/eieio-lessons-light.svg · -dark.svg · .png`

**Caption.** The survey borrows its shape from eieio's One Million Checkboxes and One Million Chessboards, and from the two write-ups of how they scaled. Each row pairs a lesson from those games with where it shows up in Letterfield's survey, which runs on Cloudflare rather than one big server: state as small as possible, only nearby updates, batching, global data from a cache, a hard ceiling on the bill, validating everything, and limits per address.

**Alt text.** A two-column table with nine rows, eieio's games on the left and Letterfield's survey on the right. State: a 125 KB bitset of checkboxes, against claims stored with initials (a bitset of the hidden words would be 137 KB). Updates: 3 by 3 zones around a player, against the at most four sectors in view. Batching every 200 ms in both. Global data cached at the edge, against a world map cached for five seconds. Bandwidth as the one unbounded cost, against free egress on Cloudflare. Bounded costs, against caps per sector and on the whole survey. Validating everything, against every claim checked with the generator. Rate limits for bots, against limits per socket and per address. One process on one box, against a Durable Object per sector.

#### Sectors and sockets

Interactive explainer: `explainers/sectors.html (to embed) · artifacts/sectors.html (as published)`

**Caption.** Drag the map and watch the game join the four sectors nearest the middle of the screen, and leave one four seconds after it drops out of view; change the screen and the zoom to see why a wide screen far out still joins only four. Switch to a supernova and tap a territory: its sector tells the 3, 5 or 8 neighbours with a territory within three of it at once, and the Atlas passes the news to every other sector in the universe with their next report.

**Alt text.** An interactive map of the sectors around the origin, each a 4 by 4 block of territory tiles, with a rectangle for the screen. The joined sectors are outlined and a panel lists each one's state: connecting, live or leaving. In supernova mode, dots stand for surveyors: those within three territories of the burst see it, the rest of the universe a distant wave, and those outside it nothing until they visit.

#### The Universe map

Game screen: `screens/universe-light.png · -dark.png`

**Caption.** The Universe map, in the field notes: the shared universe's 100 × 100 territories shaded by how much of each is charted, and dots where people are. Its counts are the live survey's public totals on November 20, 2026; the crowds are made up.

**Alt text.** The game's map at its farthest zoom on the left. On the right, the field notes with the box 'Universe charted, 907 of 1.1M' open, showing a dark square map with a few marks near its middle.

#### The surveyors

Game screen: `screens/surveyors-light.png · -dark.png`

**Caption.** The list of surveyors, nearest first, each with the territory they're in, how far away it is, whether they're active, and a button to wave. Everyone on it is made up.

**Alt text.** The game's map close up, with words circled, and on the right a drawer titled Surveyors: you, ZED, at the top, then eleven others with coloured initials, each with a territory, a distance, active or idle, and a Wave button.

### 3. The life of a claim

One thread per sector settles a race with a plain insert; around it, limits per socket, per address and per day, and the generator's own check, keep it fair.

#### The life of a claim, and a race

Figure: `figures/claim-life-light.svg · -dark.svg · .png`

**Caption.** Circling a word sends a claim to the sector the word starts in, over the WebSocket already open to it. The sector checks it against each limit and against its own copy of the map, then inserts it. Two players who circle the same word at once can't both win: the sector runs one message at a time, so the second insert finds the row and that player hears 'taken', with who charted it and when. The winner's claim goes out to everyone in the sector in the next 200 ms batch, each claimer gets a signed receipt, and within 30 seconds an alarm copies it to the log. Either way, the word stays in both players' field notes.

**Alt text.** A sequence diagram with five columns: you, a rival, the sector, the Atlas and the log in D1. You send a claim for PURIM; at the sector it passes five checks in turn: messages per socket, claims per socket, claims per address per minute, today's cap, and the word really being on the map; then an INSERT succeeds. The rival's claim for the same word arrives 40 milliseconds later and its INSERT finds the row, so the rival gets 'taken', naming you. Within 200 milliseconds a batch broadcasts 'claimed' to everyone in the sector; each claimer gets a signed receipt; the sector's next report tells the Atlas how many words your address charted today; and within 30 seconds an alarm writes the claim to the survey log, where triggers update the counts.

#### Defence in depth

Figure: `figures/defence-in-depth-light.svg · -dark.svg · .png`

**Caption.** The map and its generator are in the page, so a script can list every word without playing. No single limit stops that; each layer bounds something different, from the Worker that sees every request down to the insert itself. Most count per hashed address, which bounds one script well and a pool of many addresses only once per address; that's where a Turnstile check would come in, built and handing out passes but not required. A daily workflow watches the Atlas's numbers for the signs of a pool.

**Alt text.** A table of eleven layers, from the outside in. For each: where it's enforced, its limit, what it stops and what it doesn't. Turnstile passes (not required), salted address hashes, joins per address, sockets per address and per survey, messages per socket, claims per socket, claims per address per minute, the daily cap of 300 words per address, every claim checked against the generator, no free text anywhere others can read it, and signed receipts and badges. Below it, the thresholds at which the daily bot watch opens an issue.

#### The life of a claim

Interactive explainer: `explainers/claim.html (to embed) · artifacts/claim.html (as published)`

**Caption.** Sixteen steps from circling PURIM in Menorah Hollow to the survey log, with KIM circling the same word a moment after ZED. The claim waits in the game's outbox, goes out on the socket that's already open, passes the sector's checks (message size and rate, claims per socket, claims per address, today's cap, the map itself), and the insert decides the race. Turn the race off, or start with the sector hibernating to see what a woken object has to work out again.

**Alt text.** A step-through diagram. Along the top, ZED's and KIM's phones and everyone else in the sector, each with the real letters around PURIM. Below, sector 0,0 with its six checks as rows, ending in the insert and the row kept in the sector. To the right, the Atlas, the log's alarm, D1 and the survey log. A token for each claim moves down through the checks, answers fly back to the phones, and a caption under the stage explains each step with the message or code it involves.

#### The claim race, played through

Clip: `clips/claim.mp4 · clips/claim.gif`

**Caption.** The claim explainer playing through in 37 seconds: ZED and KIM circle PURIM moments apart, both claims pass the sector's checks, ZED's insert lands first and KIM's gets 'taken', and ZED's word goes on to the log.

**Alt text.** A screen recording of the claim diagram stepping through sixteen steps: tokens move down the sector's checks, answers fly back to the two phones, and the caption under it changes at each step.

### 4. Supernovas: news that travels

When a territory's last hidden word is charted, its sector tells its neighbours at once and the Atlas tells every other sector in the universe, so everyone nearby sees the burst.

#### A supernova, from the last word to the shockwave

Figure: `figures/supernova-flow-light.svg · -dark.svg · .png`

**Caption.** A territory goes supernova when every one of its hidden words has been charted. A territory lies inside one sector, whose claims run one at a time, so exactly one claim can be the last, and the sector writes the supernova in the same step as that claim. Then the news spreads three ways: straight to the neighbouring sectors close enough for their players to see it (three, five or eight of them, depending on where the territory sits), to the Atlas with the sector's next report, which relays it to every other sector in the universe for two minutes, and to the log with the next batch. In the game it plays as a charge, a burst and a shockwave nearby, or a distant wave further off.

**Alt text.** Three small maps of 3 by 3 sectors, each 4 by 4 territories, show which neighbouring sectors a sector tells about a supernova within three territories: three for a territory in a sector's corner, five on an edge, eight for one of the middle four. Below them, a flow: the claim of the last hidden word, the supernova row written in the same step, then three branches: POST /near to the neighbours, who pass it to their players; the next report to the Atlas, which checks it and relays it to every sector for two minutes; and the log's next batch, once the log has its last word. At the bottom, the game's timeline: a 2.6 second charge, the burst, a 3.4 second shockwave and the remnant left behind, with the quieter distant wave for supernovas further off, and the live survey's eight supernovas so far.

#### Menorah Hollow goes supernova

Clip: `clips/supernova.mp4 · clips/supernova.gif`

**Caption.** Menorah Hollow going supernova in the game, played alone with all but one of its 113 hidden words found: the last find, light drawing in for 2.6 seconds, the burst, and the shockwave shoving the letters as it rolls out, then the note that it's kept in the field notes. Captured a frame at a time from the game itself.

**Alt text.** A green-tinted grid of letters with many words circled. Light gathers at the territory's middle, bursts into sparks and a white flash, and a ring rolls outward pushing the letters aside, before the map settles and a note in the corner says Menorah Hollow is kept in the field notes.

#### The burst, and the shockwave

Game screen: `screens/supernova-burst-light.png · -dark.png · supernova-wave-light.png · -dark.png`

**Caption.** Menorah Hollow a moment after it bursts, and a second later, as the shockwave rolls out across the map and swells the letters it passes.

**Alt text.** Two frames of the game. In the first, a glowing white and green sphere fills the middle of the map with sparks flying out. In the second, a pale ring spreads across a grid of circled words, the letters inside it pushed and enlarged.

### 5. Every word, in D1

Each sector copies its words to D1 from an alarm, triggers count them on the way in, and three layers of cache serve the log and the timelapse.

#### The log: from a sector's claims to a cached answer

Figure: `figures/log-pipeline-light.svg · -dark.svg · .png`

**Caption.** Sectors keep every claim, but a page can't ask 625 objects what happened between two and three o'clock. So each sector copies its new claims to a D1 database of their own, like an outbox: an alarm at most 30 seconds after a claim sends up to 240 at once in one transaction, and only then moves its mark. The table is ordered by time, so an hour reads just that hour's rows; triggers keep running counts per hour, per day per surveyor and per day per territory, so a year reads counts rather than a million rows; and virtual columns give every word its territory and theme for the indexes, at no cost per row. Answers are cached three times over, and a past hour, once settled, for a day.

**Alt text.** A pipeline from left to right. A sector's claims table and its 'logged' mark feed an alarm that fires at most 30 seconds after a claim and writes up to 240 claims in one D1 batch, retrying after 1, 2, 4 and up to 10 minutes if D1 fails. In the middle, the games-survey-log database: the survey_log table keyed by time and word, its virtual columns for territory and theme, four partial indexes, triggers feeding four count tables, and tables for supernovas and guilds. On the right, the Worker's log API with three caches (each instance's memory, Cloudflare's cache keyed by host and map, and the browser) and how long each kind of answer is kept: 15 seconds for an hour still running, a day once it has settled, and for good for a settled day of the timelapse.

#### The survey log

Game screen: `screens/log-week-light.png · -dark.png · log-day-light.png · -dark.png`

**Caption.** The survey log's week and one of its days: words charted, the busiest day or hour, a note when a territory went supernova, and the top lists of surveyors and territories. Made-up surveyors charting real words from the map.

**Alt text.** The Survey Log page: tabs for everyone, mine and supernovas; periods from day to all time; a bar chart of words charted; a note that Menorah Hollow went supernova; and top lists of surveyors and territories.

#### The timelapse

Game screen: `screens/timelapse-light.png · -dark.png`

**Caption.** The timelapse replaying the survey from its log, each charted word a stroke in its territory's colour, paused just after Menorah Hollow, in the middle, went supernova.

**Alt text.** A map of territory squares filled with short coloured strokes, the middle one full and glowing, under the heading Fri, Nov 20 and counts of 650 words charted, 1 supernova and 20 territories, with play controls and speeds below.

### 6. One surveyor, many devices

A surveyor is a hash of a random token; a one-time code or a recovery code makes another device the same surveyor, and a Player object keeps their notes in step.

#### One surveyor on every device

Figure: `figures/devices-sync-light.svg · -dark.svg · .png`

**Caption.** A surveyor is a random token in one browser's storage; the survey knows them by a hash of it. To be the same surveyor on a phone and a laptop, one device asks for a one-time code and the other redeems it for the token. With no other device to hand, a recovery code does the same, and the Worker can't read it: the code's own hash is both the key that seals the token and the address of the row. Linked devices then keep their field notes, supernovas, achievements and settings in step through a Player, a Durable Object per surveyor, whose merge rules can only ever add.

**Alt text.** Three panels. At the top, how a token of 32 hex digits becomes a player id: the first 48 bits of a SHA-256. Left, linking: device A asks for an eight-character code that lasts ten minutes and works once, shows it as a QR code, a link and the code itself, and device B redeems it for the token, which travels only in request bodies. Right, a recovery code of twenty characters: its SHA-512 splits into the D1 row's id and an AES-GCM key that seals the token, so D1 holds neither the code nor the token. Along the bottom, the Player object and its six merge rules: a find is kept once, charted first only comes on, a receipt stays, achievements keep the earliest time, the longest streak only goes up, and settings go with whichever device changed them last.

#### Who is who: every name the survey uses

Figure: `figures/ids-and-secrets-light.svg · -dark.svg · .png`

**Caption.** The survey has no accounts, and no free text anyone else can read, but it still has to tell people apart, count addresses and keep badges honest. Each job gets its own identifier, scoped so that what's public can't be traced back to what's secret: a guild, for one, has three ids, so its public page in the log can't be matched to the carets on the map that wear its colour. Addresses are only ever stored as salted hashes, and the Worker can't open a recovery code it holds.

**Alt text.** A table of eleven identifiers with what each is, who can see it and what it's for, each marked as secret, seen by the server only, or public. The token is secret; the player id derived from it is public, on carets and the surveyor list. Address hashes reach sectors only. Initials are public. A guild's code is secret to its members, its tag shows on the map and its log id in the survey log. Link and recovery codes are secret; receipts, badges and cards are signed so anyone can check them; and a Turnstile pass stays in the browser that earned it.

#### The field notes

Game screen: `screens/field-notes-light.png · -dark.png`

**Caption.** The field notes after Menorah Hollow went supernova: the supernova kept at the top of the day, then each find with its territory, the bearing it reads in, the time, a book for its meaning and a share button. Linked devices keep these notes in step.

**Alt text.** The game's map on the left and the Field Notes drawer on the right: totals of 113 words in 1 territory, an achievements row, filters, and a list headed Menorah Hollow, Festivals, with a Supernova entry and then words like Occasion, Valentine and Jubilee with times.

### 7. What it costs, and how far it goes

Worked out from the survey's use per player-hour: the $5 plan until about a hundred people are online around the clock, and at most about $0.73 an hour at the cap of 25,000.

#### What the survey costs, by players online

Figure: `figures/cost-curve-light.svg · -dark.svg · .png`

**Caption.** The survey's bill, worked out from SURVEY.md's figures per player-hour (about 30 Worker requests, 106 Durable Object requests and 0.35 GB-seconds of Durable Object time) and Workers Paid's published prices. It stays at the $5 plan until about a hundred people are online around the clock, because outgoing WebSocket messages are free and incoming ones count as a twentieth of a request. The ceiling is the cap itself: at 25,000 online, about $0.73 an hour. On the free plan, Durable Object requests would run out at about 940 player-hours a day, and every object on the account, War's rooms included, would stop until midnight UTC.

**Alt text.** A stacked area chart. The horizontal axis is players online around the clock for a month, on a log scale from 1 to 25,000; the vertical axis is the monthly bill in dollars, from 0 to 600. The bill is a flat $5 up to about a hundred players, about $20 at 1,000, about $210 at 10,000 and about $525 at the 25,000 cap, made mostly of Durable Object requests, then Worker requests, then Durable Object time. A dashed line at about 39 players marks where the free plan's daily Durable Object requests would run out.

#### How much one sector holds

Figure: `figures/load-test-light.svg · -dark.svg · .png`

**Caption.** Real WebSocket players against the Worker, each sending a position every two seconds and claiming a word every 20 to 40 seconds, on Cloudflare's workerd runtime running locally (so the numbers are relative, not Cloudflare's edge). The first version stalled at about 410 players. Keeping positions in memory, then batching claims every 200 ms, and finally dropping the timers took a sector to 700 players with a claim answered in 3 ms at the median and under 200 ms at the 99th percentile, so MAX_PLAYERS is 750.

**Alt text.** A dot plot on a log scale of claim round-trip time, from 1 millisecond to 30 seconds, one row per load test. Each row shows the median, 95th and 99th percentile joined by a line. The first version with 200 players: 38, 261 and 459 milliseconds. With 750 it stalled at 410 connected: 1.2, 17 and 22 seconds. Positions in memory: 0.6, 9.6 and 16 seconds. Claims batched: 61, 305 and 435 milliseconds at 750, but 148 milliseconds, 12 and 25 seconds at 1,000. The final version, highlighted: 3, 124 and 195 milliseconds at 700 players with 55 percent of a core, and 3, 128 and 190 with 900 players asking, 750 let in.

#### What the survey costs

Interactive explainer: `explainers/cost.html (to embed) · artifacts/cost.html (as published)`

**Caption.** Choose how many surveyors are online at once, for how many hours a day and days a month, and see the month's bill on Workers Paid, in its four parts, and when the free plan's daily Durable Object requests would run out. The curve shows the bill for every crowd up to the survey's cap of 25,000 at once.

**Alt text.** A calculator. On the left, four example scenarios, three sliders and the month's total in large type, with its four parts and a note on the free plan. On the right, a stacked area chart of the month's bill against surveyors online, on a log scale from 1 to 25,000, with the chosen number marked and a dashed line where the free plan runs out; a table of the same numbers folds out below it.

### 8. How it was built

118 pull requests in 24 days, each with its own copy of the site and the Worker to play on a phone before it merged.

#### 118 pull requests in 24 days

Figure: `figures/timeline-light.svg · -dark.svg · .png`

**Caption.** Letterfield began as a single-player word search on the site's first day, 28 October 2026. Everything since came as pull requests, almost all written by coding agents and each tested on its own preview before merging: 118 of them by 20 November. The lines show the game's one file, its three companion pages, the Worker's code and the tests growing PR by PR; the bars along the bottom count the pull requests merged each day. The tests grew fastest of all.

**Alt text.** A line chart from 28 October to 20 November 2026 of lines of code at each merge to main. Tests grow from nothing to about 20,000 lines; the game, letterfield.html, from about 1,200 to 8,248; the Worker's source to about 5,900; and the log, timelapse and soundtrack pages to about 3,800. Milestones are marked along the top: the shared survey explored on Durable Objects, the survey switched on with limits per address and the log on 6 November, map 4 with 225 themes, share cards, the timelapse, surveyors, guilds and linked devices on 13 November, achievements, and the soundtrack album on 20 November. Small bars along the bottom count the pull requests merged each day, up to 15 on 10 November.

#### How a change ships

Figure: `figures/ci-previews-light.svg · -dark.svg · .png`

**Caption.** Every change is a pull request. CI runs only the tests its files need, split across up to three shards of four workers each, plus the linters and the two Workers' own tests, and a single required check, test, stands for them all. Meanwhile a preview workflow builds the pull request's own copy of the site and of each Worker on Cloudflare, so it can be tried on a phone, with its own empty survey, before merging. Merging to main deploys the site to GitHub Pages and, when they changed, the Workers, migrations first.

**Alt text.** A flow from left to right. A pull request runs two workflows. Test: a plan job picks the tests the changes need, then pytest in up to three shards of four workers, the lint job, and node tests for the leaderboard Worker and the share Worker, all feeding one required check called test. Preview: a Worker Preview of games-leaderboard (taking turns when the branch brings migrations), a Preview of games-share when it changed, then the site built with build.sh, its URLs pointed at those Previews, uploaded as a Preview of games-preview, and a comment with the links. After merging to main: GitHub Pages deploys the site, the Worker deploy applies migrations then deploys, and the share Worker deploys. A nightly job watches the survey for bots.

<!-- END POSTS -->
