# Letterfield's shared survey

What Letterfield could look like as a massively multiplayer game in the
spirit of [eieio.games](https://eieio.games/) (One Million Checkboxes, One
Million Chessboards), and whether Cloudflare Workers and D1 can carry it.
It's built and switched on:
- the server: `src/survey.js`, on the leaderboard Worker
- the map, shared with the game: `src/letterfield-world.js`
- the survey code in `letterfield.html`, which joins the Worker at
  `SURVEY_URL`

Its history is a page of its own, `letterfield-log.html` (see "The log").

## One Million Words

Letterfield already gives every player the same map, because every letter
comes from a fixed seed. The middle of that map, 100×100 territories around
the origin, hides **1,119,752 words**. The shared survey turns them into one
job for everyone: chart them all.

- **The first player to circle a word charts it.** Everyone else sees it
  outlined in its territory's colour; hovering it says who got there first
  ("Charted first by SIS · 3m ago"). You can still circle it for your own
  field notes, and the game tells you who beat you to it.
- **One number for the whole world.** The header shows "412,883 of
  1,119,752 charted", and it ticks up as words are charted nearby. The
  current territory has its own count ("83/120 charted"), and a territory
  goes supernova when its last hidden word is charted.
- **You can see the crowd.** Each other player is a coloured caret, like a
  collaborator's cursor, in the gap beside the letter in the middle of their
  screen. No names sit on the letters: hovering a caret shows their
  initials, and carets fade once a player has been idle for 20 seconds.
- **A world map.** It's in the notes panel: territories ink in as they're
  charted, dots show where people are, and tapping it flies you there.
- **New players land in the crowd.** You start in the middle of the busiest
  crowd that still has room. eieio found that players need to see "so many
  people" the moment they arrive; One Million Chessboards spread newcomers
  into small clusters and lost that moment. "The middle" is the median of
  where the crowd's players are looking. An earlier version used the latest
  claim, and a single straggler in the crowd's sector could pull newcomers
  100 cells away from everyone.
- **It fails gracefully.**
  - Field notes stay personal and still work offline.
  - If the server can't be reached, the notes panel says so in one line and
    the game carries on.
  - When a sector is full, or the whole survey is, the panel says that
    instead.

## What eieio's games teach, and where it shows up here

From [Scaling One Million Checkboxes][omcb] and
[Running a million-board chess MMO in a single process][chess]:

| eieio | here |
| --- | --- |
| OMCB's state was a 125 KB bitset: one bit per box | the shared world's state would be a 137 KB bitset: one bit per hidden word (claims are stored with initials for now; see "Not done yet") |
| Chessboards sent each player only moves in the 3×3 zones (50×50 tiles each) around them | sectors (192×192 cells); a player joins the ≤4 sectors in view |
| Moves went out in batches every 200 ms; batching "massively reduced load" | claims go out in batches every 200 ms. In the load test, this took a sector from saturating at ~630 players to handling 750 |
| Global data (players online) was served over HTTP with a low max-age so Cloudflare's cache absorbed it: "hundreds of millions of requests" | the world map is a `GET` with `max-age=5`, cached per Worker instance; the Atlas that builds it hears only from sectors, never from players |
| Bandwidth was "my one unbounded cost" (OMCB capped its server at 250 Mbit/s) | Cloudflare doesn't charge for egress, and outgoing WebSocket messages are free |
| "Bound my costs … instead of going serverless and scaling into bankruptcy" | `MAX_PLAYERS` per sector and `MAX_ONLINE` overall. Beyond them, players are told the survey is full; the bill can't run away |
| Validate everything: someone checked box 100,000,000 and broke OMCB | every claim is checked against the server's copy of the map generator |
| Bots pushed absurd traffic once the Go rewrite made things fast | a burst of 5 claims per socket, then one per 1.5 s; and per IP address, however many sockets it opens, 6 a minute and 300 a day (see "Limits per address") |
| Rollback netcode, so moves feel instant | not needed: a circled word is always kept locally, and the server only decides who gets the credit |
| One Go process on one box (16 cores, never above ~10% CPU, later shrunk to an ~$80/month box) | a Durable Object is one JavaScript thread, so the world is split by place into many objects |

## How it works

```
 browser ──wss──▶ Worker ──▶ Durable Object "sector 0,0"  (SQLite: claims) ──report──▶ Durable Object "atlas"
    │      │            └──▶ Durable Object "sector -1,0"                  every ≤10 s     (charted counts, players)
    │      └──GET /v1/survey/world (cached 5 s) ──────────────────────────────────────────────┘
    └── joins the ≤4 sectors in view, one WebSocket each
```

- **Sectors.** The map is cut into sectors of 4×4 territories. Each sector
  is a [Durable Object][do]: a single-threaded object with its own SQLite
  storage. It holds its claims and the sockets of everyone looking at it.
  - Only one message runs inside a sector at a time, so "first to claim
    wins" is a plain `INSERT … ON CONFLICT DO NOTHING`.
  - The server checks every claim against its own copy of the generator: the
    word must really be in the grid there, and inside this sector. A test
    runs the game's generator and the copy and compares them.
- **Positions** go only to the sector under the middle of your screen, at
  most once a second, and only after you've moved at least a cell. A sector
  sends one list of positions a second (up to 64 people, plus a head count)
  however many players moved.
- **The Atlas** is one object for the shared world. Each sector in the area
  reports its charted counts, player count and the middle of its crowd at
  most every 10 s while something is changing. Reports are absolute numbers, so a lost
  or repeated report does no harm. The Atlas writes the charted counts to
  storage at most once a minute.
- **The world map** is one byte per territory (10 KB), plus players per
  sector and a starting spot for newcomers. Each Worker instance fetches it
  from the Atlas at most every 5 s, and browsers cache it for 5 s.
- **Hibernation, and why there are almost no timers.** Sectors use the
  [WebSocket Hibernation API][hib]. Cloudflare bills a Durable Object for
  wall-clock time while it's running *or while it can't hibernate*, and a
  pending `setTimeout` stops it from hibernating ([lifecycle][lifecycle]).
  - The first version held a 1 s presence timer and a 10 s report timer.
    That kept every busy sector billed every second. It also billed a sector
    with a few people circling words almost as much as a full one, because
    its report timer was nearly always pending.
  - Now owed positions and reports go out with the next message that
    arrives once they're due. While people are moving there's always a next
    message.
  - The only timers left are short ones for things that might be the last
    to happen in a sector: someone leaving a quiet one (under 32 sockets),
    and claims waiting in a batch, in any sector. A batch's timer lasts at
    most 200 ms, well inside the idle time before a sector can hibernate,
    so it costs nothing. Without it, a busy sector that went quiet straight
    after a claim would hibernate with the claim unsent, and its claimer
    would never hear they were first.
- **Attachments are expensive.** Each socket's state lives in its
  hibernation attachment, which survives eviction. Serializing it on every
  position update and deserializing all of them for every list of positions
  was the sector's biggest cost. Players are now kept in memory too, and
  positions are written to the attachment at most every 5 s.

Messages are listed at the top of `src/survey.js`.

### A new map

The map is the game's themes and the way it deals their words, so changing
either redraws every territory, and a claim names a word that's no longer
there. `MAP_VERSION` in `src/letterfield-world.js` says which map this is,
and changing it starts the survey over:

- **Sectors and the Atlas** keep the version they last ran with in a table
  of their own (`map`). When one wakes on a newer map it deletes what it
  held for the old one: a sector its claims and its log mark, the Atlas its
  charted counts. Storage from before maps had versions counts as map 2. A
  sector nobody visits keeps its old claims until someone does, but nothing
  reads them until then, and the Atlas has already forgotten its counts.
- **The log** is emptied by a migration
  (`migrations-log/0004_survey_log_new_map.sql`, and `0005_survey_log_map_4.sql`,
  which also works out each word's theme the new way), which runs before the
  new Worker deploys. A sector still on the old code could log a claim in
  that gap of a few seconds. The log's cached answers are kept under the
  map's version (see Caching), so no day from the old map outlives it.
- **Field notes** move to a new key in the game (`letterfield.finds.v4`),
  carrying over only the finds whose word is still where it was, without
  being charted first, and the game says the map has been redrawn.

Map 4 has 225 themes of 144 to 184 words, 28,845 different words in all, where
map 2 had 116 themes of about 47 (map 3, the same 116 at about 150 words, only
ran in a pull request's preview). A territory deals its 16 chunks from one
shuffled deck of its theme, nine cards each (`DEAL`), and a chunk places six to
eight of its own nine, so no word comes up twice in a territory (a test checks
every territory in the shared world).

Territory (rx, ry) has theme `(rx + 15 ry) mod 225`, so a theme comes round
again only 15 territories away in any direction, as far apart as 225 themes
can be: each needs a 15 × 15 square to itself. The order of the themes was
found by a search (`bench/layout.mjs`) so that the eight territories around
each one differ from it in colour, by 30° of hue or more, and in kind (no two
bird themes side by side), and share no words with it.

A word can be in up to three themes where it belongs in each, like SPARKLE in
Glimmer and Yuletide, but at least half of every theme is its own: 24,170
words are in one theme, 3,972 in two and 703 in three. A stray takes its
territory's theme when that theme has the word, and otherwise the first that
does; territories are named only with words in one theme. Each word turns up
about 39 times in the shared world, where it was 63 on map 3 and 200 on map 2.
With this many words the letters spell plenty of them by chance, so a stray
needs six letters (`STRAY_MIN`): about 20 a territory, where four letters
would allow some 530.

### Limits per address

The map comes from a fixed seed, and its generator is in the page, so a
script can find every word without playing. Per-socket limits alone don't
stop it: it can open as many sockets in as many sectors as it likes. So the
survey also limits each IP address, wherever it plays:

- **Addresses are hashed.** The Worker hashes the player's address with
  `IP_SALT`, as the leaderboard does, and hands the sector only the hash, in
  a header it sets itself. An IPv6 address counts by its /64, because a
  device can pick any address in its /64.
- **Claims: 6 a minute per address, across every sector.** That's a
  [rate-limiting binding][ratelimit] (`SURVEY_CLAIMS` in `wrangler.toml`),
  on top of each socket's own limit. A player rarely finds more than one
  word a minute, and counting over a minute rather than 10 s means a few
  spotted together still all count. The cost is to players who share an
  address: a family, a classroom, or a mobile network that puts many phones
  behind one IPv4 address share those 6 (and the daily 300 below). A refused
  claim gets the same `slow down` as a socket claiming too fast, and the
  game says "Too quick to chart · kept in your notes".
- **Words charted: 300 a day per address, in the shared world.** At 6 a
  minute, a script left running all day would still chart 8,640 words a day.
  A person charting one a minute would need five hours to reach 300. With
  the cap, one address would take about 10 years to chart the world. The
  rate-limiting binding only counts over 10 or 60 seconds, so the Atlas
  keeps this count:
  - Each sector's reports, which already go out at most every 10 s while
    words are charted, also list how many words each address charted there
    since the last report.
  - The Atlas adds these up for the UTC day. It answers with the addresses
    past the cap, the most recent 2,000, but only when that list has
    changed since the sector last heard it.
  - The sector refuses those addresses' claims with `daily limit`, and the
    game says "Today's charting limit reached · kept in your notes".
  - A sector keeps the list in memory, so one just woken from hibernation
    doesn't know it. Until it has heard from the Atlas that day, it asks
    before taking a claim from an address: a report without the day's
    counts, shared by every claim that comes in while it's out. That's one
    request to the Atlas each time a sector wakes, and a few milliseconds'
    wait for the first claim after. If the Atlas can't be reached, claims go
    ahead. Before this, a capped address could chart again each time a quiet
    sector woke: one script could manage most of the 6 a minute all day.
  - Otherwise it costs no extra requests and adds no wait to a claim. The
    Atlas only counts an address's words when the sector reports them, so an
    address can chart a few words past 300 before every sector knows. The
    6-a-minute limit keeps that small.
  - Worker Previews allow 1,000 a day (`SURVEY_DAILY_CLAIMS` in
    `[previews.vars]`, read by `dailyClaims()`) and 60 claims a minute, so
    a test can chart several whole territories in a day.
  - The counts live only in the Atlas's memory. It's rarely evicted, since
    sectors report to it every few seconds, but if it is, the day's counts
    start again, and every deploy of the Worker evicts it. Saving them would
    cost a row written per active address every minute.
  - Sectors outside the shared world don't report, so words charted there
    aren't capped. They don't count toward the world's total.
- **Sockets: 40 per address in a sector, and 120 new ones a minute per
  address.** A sector counts its own sockets exactly, so a few addresses
  can't fill it and lock everyone else out. It counts again once the binding
  below has answered, since other joins can come in while it does: a burst
  of joins from one address, or everyone reconnecting after a deploy, still
  stops at the caps. A second binding
  (`SURVEY_JOINS`) counts sockets opened anywhere. A player roaming the map
  opens about 10 an hour. Either limit is answered with `full`, and the
  game tries again in a minute or so.
- **Why a binding and not a Durable Object per address.** The binding keeps
  its counts in each Cloudflare location, in memory, and answers without
  waiting for other locations to agree. So it's approximate: counts are per
  location, and a burst can slip past. That's fine for stopping one script
  racing everyone else. A Durable Object per address would be exact, but
  every claim would wait on a round trip to another object, and pay for it.
  In the load test, claims took as long with the binding as without it
  (p50 3.6 ms against 3.4 ms). If the binding fails, the sector lets the
  claim through, and the per-socket and per-sector limits still hold.
- **Not checked: whether a claim is near the player.** A claim is only
  accepted in a sector the player has a socket in, and that's about as tight
  as a distance check could be:
  - The game only lets you circle words at 9 px a cell or closer. A
    2560 px desktop window still reaches about 160 cells from its middle,
    and a 5120 px ultrawide about 285. Positions also lag up to a second,
    and go only to the sector under the middle of the view.
  - A fair radius would be around 300 cells, wider than a sector
    (192 cells).
  - A script reports its own position anyway, and flying across the map is
    normal play, so it could send a position next to each word first.

### Watching for bots

The limits slow down one address. A pool of addresses, a botnet or a
proxy service, still gets them once per address, and that's when a
Turnstile check would be worth switching on (see `TURNSTILE.md`). So the
Atlas keeps the numbers that would show one, from the reports sectors
already send it:

- **For each UTC day:**
  - words charted in the shared world;
  - how many addresses charted them;
  - how many reached the daily cap;
  - player-hours, added up from the players online at each report;
  - sockets that joined without a Turnstile pass (`unpassed`, see
    `TURNSTILE.md`), once the Worker hands out passes.
- **Where they show up:**
  - The world map (`GET /v1/survey/world`) has `today` and `yesterday`.
  - Workers Logs gets an `{survey: 'hour'}` line with each hour's words,
    player-hours and words per player-hour.
  - Workers Logs also gets an `{survey: 'daily cap'}` line whenever an
    address reaches the cap. It holds the count only, never the address.
- **What would look like a pool:**
  - Many addresses at the cap in a day. One or two is a keen player or a
    single script.
  - Far more words per player-hour than people manage. A person charts a
    word a minute at most. A bot that claims without sending positions adds
    words but no player-hours, so its rate climbs.
  - Many joins without a Turnstile pass, once the game has a site key.
    Nearly every player then has a pass, so those joins are scripts, plus
    the few players whose browsers block Turnstile.
- **Telling you:** the **Watch the survey for bots** workflow
  (`.github/workflows/survey-watch.yml`) reads the world map just after
  midnight UTC. If yesterday had 20 or more addresses at the cap, or 120 or
  more words per player-hour over at least 500 words, or (with a site key
  in `letterfield.html`) 500 or more joins without a pass and at least 5
  per player-hour, it opens an issue labelled `survey-bots`, or comments on
  the one that's open.
  `scripts/survey_watch.py` holds the thresholds. If the survey can't be
  reached, it only warns.
- **Lost on eviction:** the numbers live in the Atlas's memory, like the
  daily counts per address, so an evicted Atlas starts the day again and
  forgets yesterday.

## Surveyors and emotes

The **Surveyors** drawer lists everyone else in the shared
world, nearest first, each with their initials, the territory they're in (in
its theme's colour), how far away it is and whether they're active or idle.
A row flies you to their territory, and on to their caret once you're close
enough for its sector to say where they are. Each row shows their initials
in a disc of their caret's colour, with a **Wave** beside it, the emote sent
most, and ⋯ for the other six and mute; a right-click or a long press of
someone's caret offers all seven. These **emotes** are small drawings to send
them. The code is `src/survey-social.js`, with hooks in
`survey.js`, and a section of `letterfield.html` of its own.

### Where it lives: two doors

The social side has two doors on the survey, one for everyone else and one
for you, each to a drawer like the notes': a sheet from the bottom on a
phone, and on a computer a panel over the docked notes. One is open at a
time (the page's `sheet` machine: none, people or you), and on a phone the
notes take turns with them too. Escape closes whichever is open and gives
its door back the focus. They started as a fold of the field notes, but with
guilds, your initials, linking devices and recovery codes they outgrew them,
and the notes are about the map and your finds.

- **Surveyors** is a person between the tools and the field notes, with a
  count of everyone else online (the list's own count while it's recent, the
  world's total otherwise), and `P`. Its drawer is only other people: at the
  top, if you're in a guild, a strip of your mates' faces with the guild's
  name, how many are online and Invite (online mates bright, a tap from
  flying there; the rest dim, with when they were last seen); then everyone
  online, nearest first, mates marked with the guild's dot, mates who keep off
  the public list included. A row or a face puts a phone's drawer away as it
  flies, as a find does the notes. Each row is three buttons (fly there,
  wave, and ⋯), so it works from a keyboard, and Escape folds an open row of
  emotes before it closes the drawer. What became of the last emote sent
  shows under its row.
- **You** is your initials in a ring of your caret's colour, and `Y`. On a
  phone it takes the title's place in the top bar (the title was "LF" there,
  to leave room for the territory's name, and is still "Letterfield" to a
  screen reader); wider, where the whole title shows, it sits in the corner
  beside the other buttons. Unsigned, it's a dashed ring with a person, and
  opens on the form. Its drawer holds your initials with Change and your
  guild's name under them; **On the map**, the two switches (on the list,
  taking emotes); **Guild**, starting, inviting and leaving; and **Your
  devices**, which says first where your surveyor lives (only on this
  device, or backed up and kept in step), then offers each step by what it
  does: link another device, I have a code, save a recovery code. Anything
  that needs your initials first (an emote, a guild, joining from an invite)
  opens it at the form; signed to join, it makes way for the invite again.

### Who a player is

Initials aren't unique, and a socket's id lasts only as long as the socket.
So the game makes a random token (`games.player`, 128 bits, a key without a game prefix so any game can share it) and sends
it in its `me` message to every sector it joins. The sector names the player
by 48 bits of the token's SHA-256 (`playerId`): the same id in every sector
and every visit, used in presence, the list and emotes. Nobody else ever sees
a token, and the id can't be chosen, so nobody can send as someone else. A
game that sends no token (an older copy) keeps its socket's id, as before.

The trade-off is a lasting pseudonym. It's what lets a mute outlast a visit,
and it lets someone recognise "the same KIM" from day to day; it says nothing
else about the player, and clearing the browser's storage makes a new one.
Claims still aren't tied to it (see "Mine"). Each device has its own until
it's linked to another (see "One player, several devices"); an iPhone's Home
Screen app counts as a device of its own, since it keeps its own storage.

### Where the list comes from: the Atlas, from the reports sectors already send

Each sector already tells the Atlas its numbers every ≤ `REPORT_MS` while it's
busy. Its report now also lists its surveyors: `[id, initials, rx, ry, idle,
flags]` for each player whose view is centred in it, has an id and hasn't
asked to be hidden. The Atlas builds a snapshot of everyone at most every
`LIST_MS` (10 s), each Worker instance fetches it at most that often, and works
out pages itself. `GET /v1/survey/surveyors?r=<rx>,<ry>&page=<n>&me=<id>`
answers with the nearest 40 to territory (rx, ry), leaving the asker out, and
says how many there are; a page further on gives the next 40, up to the
nearest 1,000. Browsers keep an answer for 10 s, and the game asks every 20 s
while the fold is open, the notes are open and the tab is on screen.

- **Staying listed while still.** A sector only reports while messages come
  in, and an idle player sends none, so the Atlas would forget them after
  `ONLINE_MS`. An idle game now sends `{t: 'here'}` every 30 s, and a sector
  reports at least every `REFRESH_MS` (50 s) while messages arrive, changed or
  not. Players who sit still stay counted on the world map too.
- **Leaving.** A listed player whose socket closes is taken off with a report
  straight away, rather than lingering until `ONLINE_MS`.
- **Moving between sectors.** For a few seconds someone can be in two
  sectors' reports; the snapshot keeps them once, from the latest.
- **Outside the shared world** sectors don't report, so the list covers the
  shared world, like the world map. Emotes still reach a caret out there.

**Why not push it.** The cheapest list would ride on the reports: the Atlas
could answer each sector with the surveyors nearest it, and the sector pass
that to sockets that asked, for no requests at all. But every player in a
sector would get the same nearest 40, paging would mean asking the Atlas
anyway, a player out of the shared world (or whose sector is full) would have
no list, and the sector would send the list to each socket, which is the work
that limits how many players a sector holds. The list is "global data" in
eieio's sense, so it's served the way the world map is: over HTTP, cached.

**Cost and scale.** The reports were going out anyway; they grow by about 32
bytes a surveyor (24 KB for a full sector of 750). What's new is the list's
requests: one Worker request per reader every 20 s, and one Atlas request per
Worker instance every 10 s while anyone reads. Assuming one player in ten has
it open at a time:

| online | snapshot | readers | Worker requests a day | Worker instances reading | Atlas requests a day | a page's work in the Worker |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 0.3 KB | 1 | 4,300 | 1 | 8,600 | nothing |
| 1,000 | 33 KB | 100 | 430,000 (~$0.13) | ~20 | 170,000 (~$0.03) | sorts a few dozen |
| 10,000 | 330 KB | 1,000 | 4.3 M (~$1.30) | ~100 | 860,000 (~$0.13) | visits sectors nearest first, stops once the page is full |

So 10,000 online all day adds about $1.50 a day, next to the ~$0.75 an hour
the survey can cost at its ceiling. The page's work stays small at any size:
the snapshot is grouped by sector, and a page visits sectors nearest first
until it has its 40 and no nearer sector is left. The Atlas holds one entry
per listed player in memory (25,000 at `MAX_ONLINE`, a few MB). `LIST_MS` and
the game's 20 s are the knobs; past that, the push above.

**Privacy.**

- **Territory, not cell.** Sectors round each position to its territory
  before reporting, so the Atlas never has cells. A list of exact cells would
  let anyone follow a player across the whole world; a territory (48 × 48
  cells) is enough to find them, and close up you see their caret, as before.
- **Off the list.** "Show me on the list" (`letterfield.listed.v1`) sends
  `hide: true`: the sector leaves you out of its reports, and you still show
  as a caret to anyone near you. Hidden players only take emotes from players
  in their own sector, who can see the caret anyway, and from their guild, so
  an id saved from an earlier day can't reach them from afar.
- **No addresses.** The list and emotes carry ids, initials, territories and
  idle seconds. Hashed addresses stay in sectors, as before.

### Emotes

`{t: 'emote', to, e, s}` goes on the socket of the sector under the middle of
the sender's view, which knows where they are; `s` is the sector the sender
saw them in (their caret's, or their territory's from the list). If that's
the same sector it's handed over there; otherwise it goes with an internal
POST (`/emote`) to the recipient's sector, which only Workers binding
`SECTORS` can reach. The recipient gets `{t: 'emote', from, ini, e, r}`, with
the sender's territory, and the sender `{t: 'emoted', to, e}` with `ok` or why
not. In view, an emote pops from the sender's caret as a bubble that springs
up, drifts and fades, while the drawing in it moves once: the hand waves from
the wrist, the hat lifts and tips, the thumb bobs, the palms meet twice, the
sparkle twinkles, the flag flutters and the question mark tilts. Otherwise
it's a note saying who, what and where, with **Fly there**, and its icon makes
the same move (CSS made from the same table, `EMOTE_MOVES`). Under reduced
motion the bubble just shows and fades, and nothing moves. A
screen reader hears it either way.

**Nobody sends as someone else.** The sender is whoever their socket says,
from their token, never what the message says, and the internal path takes
only what one sector passes another.

**Limits.**

- Each socket: 3 at once, then one every 4 s.
- Each address: 20 a minute, across every sector (`SURVEY_EMOTES`, a
  rate-limiting binding like the claims').
- Kept by the recipient's sector, which every emote for its players passes
  through, from anywhere: 3 a minute from one sender to one player (`slow
  down`), and 6 every 10 s to one player from everyone (`busy`). Nobody can
  be flooded, and a sender's four sockets get no more than one.
- Only from players with initials and an id (`sign first`), and only to a
  sector in the shared world or beside the sender's (`gone`), so emotes can't
  be used to wake objects all over the endless map.
- These limits live in memory; a sector that hibernates forgets them, and the
  per-socket and per-address limits still hold.

**Turning them off and muting.** "Take emotes" (`letterfield.emotes.v1`)
sends `quiet: true`; the sector refuses emotes for them (`off`) and the list
greys out their emotes. **Mute**, from a row or a caret, is kept on the device
(`letterfield.muted.v1`, up to 200): a muted player's caret and emotes don't
show, and they're never told. A muted player who clears their storage comes
back with a new id; the per-address limits are what hold then.

### The emotes

Seven drawings on a 24 × 24 grid in the game's line style, the same paths in
the buttons, the notes and the canvas (as `Path2D`). Not emoji: they look
different on every device, and plenty of them can be made suggestive. None is
text, and one emote never combines with another: each shows alone, at the
sender's caret, and a new one from the same sender replaces the last, so they
can't be strung into a message.

| emote | means | why it's safe |
| --- | --- | --- |
| Wave | hello, goodbye | an open hand with its fingers together, leaning, with motion lines: no finger is singled out, and it reads as a wave rather than a raised palm |
| Thanks | a hat tipped | a hat, the old gesture of thanks; nothing bodily |
| Nice | a thumbs up | the near-universal "good" online. It's rude in a few places (parts of West Africa and the Middle East), which made it the closest call; it was asked for by name and kept |
| Clap | well done | two flat palms meeting, with no fingers drawn; it can be sarcastic, but no worse than words would be, and there are none |
| Great find | a sparkle | a four-pointed star |
| Over here | a survey flag | how surveyors mark a spot, and it comes with the sender's territory to fly to |
| Question | ? in a circle | punctuation, which can't spell anything |

Left out: hearts, kisses, faces (they wink and stick out tongues), fruit and
vegetables, every other hand shape (pointing, the OK sign, a fist, counted
fingers), fire, skulls, letters, numbers and arrows.

### Initials on a list

The list puts initials in front of everyone in the shared world, not just
whoever hovers a caret. Initials are still the only words anyone shows, so
`BLOCKED_INITIALS` (in `leaderboard.js`, shared with the leaderboards, whose
top 10s are just as public) now covers the common obscenities and slurs three
letters can spell, 32 in all. It stops there: every combination left out is
someone's real initials. A sector blanks blocked initials, and the list
shows a blank as "···".

## Guilds

A guild is a few surveyors who want to find each other. Its members' faces
head the Surveyors drawer (those online a tap from flying there, the rest
with when they were last seen), a note says when one comes online, and their
carets wear the guild's colour. One guild at a time, joined only from an
invite link. The code is `src/survey-guild.js`, hooks in `survey.js` and
`survey-social.js`, and the Guilds section of `letterfield.html`.

### Why these guilds

| | (a) leaderboard groups | (b) Letterfield guilds (chosen) | (c) follows |
| --- | --- | --- | --- |
| what | a group from `/v1/groups` is a guild; `games.groups` says which | one guild each, its own code, a name made from fixed words and a colour | follow a player from the list, on your device only |
| for | already exists, codes and `?join=` links work | one badge per caret; no typed names; a roster to cap and to keep "last seen" in | no server state at all |
| against | typed names in front of everyone; a player in five groups is in five guilds; groups keep no members, so no last seen; joining a War board would make you a guild mate here | new endpoints and an object per guild | one-sided; no badge; not really a guild |

### What a guild is

- **A Durable Object per guild** (`Guild`, named by its code), with its own
  SQLite storage: a name, a random tag, and up to 50 members, each with their
  initials and when they joined and were last seen. Its tables are made when
  it's created and dropped when its last member leaves, so a wrong guess at a
  code stores nothing and an ended guild's code is free again.
- **No free text.** A name is three words from the game's lists: 16 colours,
  16 instruments and 8 kinds of company ("Cobalt Compass Society"), 2,048
  names in all, drawn at random until the founder likes one. The Worker keeps
  only the three numbers (`GUILD_WORDS` says how long each list is, and a test
  checks the game's lists agree). The colour is the first word's.
- **The code is the key.** Six characters from the groups' alphabet (887
  million codes), passed in an invite link (`?guild=<code>`), which the game
  reads once and takes off the address. Everyone else only ever sees the
  guild's **tag**, a random id that says which carets share a guild and
  nothing more.

```
POST /v1/survey/guilds                 {token, initials, name: [a, b, c]} → 201 {code, name, tag, members}
GET  /v1/survey/guilds/<code>          → {name, size}, for an invite to say what it's to
POST /v1/survey/guilds/<code>/join     {token, initials} → {code, name, tag, members}
POST /v1/survey/guilds/<code>/leave    {token} → {ok: true}; the last to leave ends it
POST /v1/survey/guilds/<code>/roster   {token} → {code, name, tag, members}, members only
  members: [[id, initials, seen], ...], most recently seen first
```

Players are named by their token, as everywhere in the survey, so nobody can
join, leave or read a roster as someone else. A roster asked for by someone
who isn't a member gets the same answer as a guild that doesn't exist.

### Membership in the sectors

- **Checked by the guild.** The game sends its guild's code in its `me`
  message. The sector asks the guild (`POST /check`, internal) whether the
  player is a member, and only then puts the guild's tag on their socket, so
  knowing a code isn't enough to wear a guild's colour. It asks again every
  15 minutes while they play, which takes the tag off anyone who has left and
  keeps their "last seen" current (written at most every 10 minutes).
- **On the map.** Presence gives each player's tag; the game draws a dot in
  the guild's colour on top of a mate's caret (a ring when zoomed out), and
  their hover card names the guild. Other guilds' tags mean nothing to it.
- **Off the list, but not to your guild.** A hidden member stays out of the
  public list but is still reported to their guild (flagged `FLAG_HIDDEN`),
  and takes emotes from mates anywhere: an emote carries its sender's tag.

### Who's online rides on the reports

Each report's surveyors carry their guild's tag, and the report lists the
guilds of everyone in the sector. The Atlas keeps who's online in each guild,
replaced sector by sector as reports come in, and answers each report with
the online members of the guilds that sector asked about. The sector passes
`{t: 'guild', tag, on}` to its members whenever that changes. Idle time is
coarse in it (active, under a minute, then whole minutes), so it changes when
someone arrives, moves territory, leaves or idles another minute, not with
every report. It costs no requests of its own.

- **How soon:** within a report of the member's sector and of yours: 10 s
  while they're busy, up to about a minute when they're still.
- **In the game:** the first word after you arrive just says who's here;
  anyone new after that gets a note ("ZED came online", with **Fly there**),
  at most once in 10 minutes each.
- **Outside the shared world** sectors don't report, so a member out there
  shows as offline, with when they were last seen.

### Cost

- **The guild's object** is asked when a member makes, joins or leaves a
  guild, opens a socket while in one (about 10 an hour while roaming) and
  every 15 minutes while they play; and for the roster when the list opens,
  then at most once a minute while it's open.
- **Rows written:** "last seen" at most every 10 minutes per member playing.
- **At 10,000 online with 3,000 in guilds:** about 42,000 checks an hour
  (~$0.15 a day) and a few thousand roster reads (pennies). At 1,000 online,
  a few cents a day. The online word rides on reports and frames that were
  free already.
- **Limits:** 50 members a guild; 5 new guilds and 20 joins an hour per
  address, counted in D1 like new groups.

### Left for later

- **Web Push while the game is closed.** It needs VAPID keys made in
  mwarkentin/infra, a subscription per player in D1, payloads encrypted in the
  Worker (`aes128gcm` with Web Crypto), a `push` handler in `sw.js` and a
  permission prompt; on an iPhone only the Home Screen app gets it. Worth it
  once guilds are in use.
- **A guild view in the log:** the guild's words charted needs each claim's
  guild in the log (a column and an index, written by the sector, which knows
  it at claim time).
- **Running a guild.** There's no founder or removing a member: anyone can
  mute anyone, or leave and start another.
- **One guild at a time** is the game's rule; the Worker doesn't know a
  player's other guilds, so two devices could join two.

## One player, several devices

A player is a token in one browser's storage, so the same person on a phone,
a tablet and a computer was three surveyors: three ids, three sets of mutes,
and only one of them in their guild, all signing with the same initials.
Linking makes them one. It's built for Letterfield, but the token is kept as
`games.player`, without a game's prefix like `games.initials`, so any game
on the site can name the same player later.

### How it goes

1. On a device that's already you, **Link another device** (under "You" in
   the Surveyors drawer) asks the Worker for a code: `POST /v1/link
   {token, carry}`. The Worker keeps the token and what it carries in D1
   (`links`, migration 0004) under eight random characters from the groups'
   alphabet, for ten minutes and one use.
2. The device shows the code three ways: a QR code that opens
   `/letterfield?link=<code>`, the same link to copy or share, and the code
   itself, `ABCD-EFGH`, to type on a device with no camera or into an
   iPhone's Home Screen app (a scanned link opens Safari, whose storage the
   app doesn't share). While it shows, it asks every 5 seconds
   (`POST /v1/link/<code>/status {token}`) whether the code is still
   `waiting`, `used` or `gone`, and says "Linked" once it's used.
3. The other device opens the link, which offers to link before anything
   else (the `link` state of the page's `intro`), or types the code under
   **I have a code**. Either redeems it: `POST /v1/link/<code>` answers the
   token and the carried settings, once.
4. That device takes the token and settings and reloads as the same
   surveyor, with a note saying so. Both devices then keep in step (see
   "Syncing linked devices").

What a link carries, checked by `cleanCarry` in `worker/src/players.js`:
the initials, the guild (code, name and tag), the mutes, and the two
switches under Surveyors (on the list, taking emotes). Mutes from both
devices are kept. Their guild wins; if they're in none and this device is
in one, the linked surveyor joins this device's guild instead, so linking in
either direction doesn't lose one. Either way the device's old self leaves
its guild, since it won't be back. Field notes come from both devices from
then on, through syncing; sound and music stay each device's own.

### Why a code, and how it's kept safe

Whoever redeems a code becomes that player, so a code is as good as the
token for ten minutes:

- **It can't be guessed.** Eight characters from a 31-letter alphabet is
  852 billion codes, and every try counts against the address's limit
  (`linkTry`, 20 an hour, right or wrong), as making codes does (`link`, 10
  an hour). With a thousand codes live at once, a try has about one chance
  in 850 million.
- **It works once.** One `UPDATE … WHERE used = 0 … RETURNING` claims it, so
  two devices redeeming at once can't both have it, and what it carried is
  wiped from the row as soon as it's handed over. The row stays until it
  runs out, so the device that made it can hear it was used.
- **Only its maker hears about it.** `/status` answers `gone` to anyone who
  doesn't send the token that made the code.
- **The token never travels in an address.** It goes in request bodies
  only; the link holds just the code, and the page takes `?link=` off the
  address as soon as it's read. The page says that whoever uses a code
  plays as you, so keep it to your own devices.

A passkey would do this without a code, but needs an account to hang it on,
which nothing else here has.

### A recovery code

Linking needs a device that's already you. With none left (one phone,
lost; every browser cleared), the token is gone, and with it the surveyor:
their id, their guild and any synced notes. A recovery code is a long code
the player saves once and enters on any device, under **I have a code**, to be
that surveyor again.

    POST /v1/recovery         {token} → 201 {code, made}: a new code; any older one stops working
    POST /v1/recovery/use     {code} → {token, made}, or 404
    POST /v1/recovery/remove  {token} → {ok}

- **Twenty characters** from the groups' alphabet, about 99 bits, shown in
  fours: `BCDF-GHJK-MNPQ-RSTV-WXYZ`. It's shown once, with Copy and "Save as
  a file", and the warning that whoever has it plays as you.
- **The Worker keeps neither the code nor the token.** A code's SHA-512
  gives the D1 row's id (its first half) and an AES-GCM key (its second)
  that seals the token. The row holds the id, the player id, the sealed
  token and when it was made (`recovery`, migration 0005), so reading D1
  gives no one a token, and only the code opens its row.
- **One code a player.** A new one replaces the old, which stops working,
  so a code that gets out is put right by making another. "Remove it" takes
  it away, and stopping syncing on every device takes it too.
- **It keeps a backup.** Saving a code starts the player's Player and
  marks it saved, which exempts it from the 180-day clear-out while the
  code lasts. Using the code on a new device turns syncing on there with
  this device's settings older than the backup's, so the first sync brings
  back the initials, guild, mutes and notes; that device's own notes join
  them, and its old self leaves its guild.
- **Guessing it** is hopeless at 99 bits, and tries count against the same
  per-address limit as link codes' (`linkTry`). Making codes has a limit of
  its own (`recovery`, 5 an hour).
- **Cost:** a D1 row per player who saves one, and a Player kept for them.
  Nothing measurable.

### Syncing linked devices

Once linked, devices keep their field notes, supernovas seen and the
settings a link carries in step through a **Player**, a Durable Object per
player id (`worker/src/players.js`), named by the token's hash so only the
player's own devices reach it:

    POST /v1/player/sync    {token, epoch, since, finds, novas, settings, settingsAt}
                            → {epoch, at, finds, novas, settings?, settingsAt?} | {off: true}
    POST /v1/player/forget  {token} → {off: true}

- **Only a link starts one.** Redeeming a code starts the player's Player;
  until then a sync answers `off` and stores nothing. So a player who never
  linked a device keeps everything in their browser, as before, and making
  Players costs as much as making codes, which is limited per address.
- **A sync carries what's new.** Every row has the version it last changed
  in. A device sends what changed on it since its last sync (the finds and
  supernovas it's kept a list of, and its settings with when they last
  changed) and the version it last heard, and gets back everything that
  changed since then, apart from what it just sent. A Player that was
  forgotten and started again has a new epoch, so a device that last heard
  from the old one starts over and sends all it has.
- **Merging can't lose anything.** Finds are keyed by word and place, as
  between tabs: each is kept once, and "charted first" only ever comes on.
  Supernovas are kept once each. Settings (initials, guild, mutes and the
  two switches) go with whichever device changed them last, by its clock.
- **When.** On opening the game, a few seconds after a find, a couple after
  a settings change, when the tab comes back into view, and every minute
  while it's open, so two devices open at once catch up within a minute. A
  hidden tab doesn't sync.
- **Limits.** 25,000 finds and 1,000 supernovas a player, 2,000 of either a
  sync (more go in the next), one sync every 2 seconds, half a megabyte a
  request.
- **Stopping.** "Stop syncing" under the Surveyors drawer's linking card stops
  this device, or every device: that deletes the Player's storage, and the
  others hear `off` at their next sync and stop too, with a note. Each
  device keeps its notes as they are. A Player nobody has synced for 180
  days deletes itself (an alarm, put off by each day's first sync).

The game's `sync` machine (off, idle, syncing, failed) shows on `<html
data-sync>`, and the line at the foot of the field notes says "Synced with
your linked devices".

### Cost

D1 only, and small: making a code sweeps expired rows and writes one;
redeeming it is two writes; each ask while it shows reads one row by its
key (120 if left showing the full ten minutes, a few in a usual link). Even
if every one of 10,000 players linked a device every day, that's well
inside Workers Paid's included D1 reads and writes, so nothing extra.

Syncing is a Durable Object request a minute for each open device, plus
one per few finds, each writing a row per new find and one for the Player's
version. Say 1,000 of 10,000 players link devices and play an hour a day:
about 100,000 requests a day, 3 million a month, within the million
included plus 30 cents; the rows written (a few million a month) and the
storage (about 50 bytes a find, so 1,000 full notebooks are a gigabyte)
stay inside what Workers Paid includes. Under a dollar a month.

## The log

[letterfield-log](https://games.michaelwarkentin.com/letterfield-log) is a
page of the survey's history: every word charted first, with where, by whom
(their initials) and when, by the day, week, month, year or all time, and
any hour minute by minute. Each word links to
`/letterfield#f-<word>-<x>-<y>-<d>`, which flies the game to it, and its
surveyor, territory and theme each open a view of their own, with an
address to share. "Mine" narrows it to the words this browser charted
first. Territories whose every hidden word is charted have gone supernova,
and the log keeps a list of them (see "Supernovas").

### Where the history lives: D1, copied from each sector

Sectors already keep every claim, but a log can't ask 625 objects what
happened between 2 and 3 pm. The options were:

| | for | against |
| --- | --- | --- |
| **D1, written by each sector** (chosen) | indexed SQL over the whole world; a page reads one hour with one query; `wrangler d1 execute` for moderation | one database runs one query at a time, so writes must be batched (and the log gets a database of its own) |
| D1, written through the Atlas | the Atlas already hears from busy sectors every 10 s | only sectors in the shared world report; claims held in the Atlas's memory are lost if it's evicted, so sectors would have to keep them until it confirms anyway; one more load on one object |
| a Durable Object for the log (or one per day) | no new storage product | every read is a Durable Object request to the same few objects the writes go to; a viral day of readers lands on one single-threaded object; no ad hoc queries |
| each sector's own claims, read on demand | nothing to copy | an hour or a player's finds span up to 625 objects |

D1 was ruled out above for *live* state: polling, positions, pushes. A log is
the opposite load: rows appended a few times a minute per busy sector and read
by a page that can be cached, which is what D1 is for.

**How claims get there.** Each `Sector` copies its new claims to the
`survey_log` table (`migrations-log/0001_survey_log.sql`) like an outbox:

- A claim sets a Durable Object [alarm][alarms] for `LOG_MS` (30 s) later, if
  none is set. Claims that come in before it goes off go with it. Unlike a
  timer, an alarm doesn't stop the sector hibernating, and it wakes the
  sector if it was evicted. A sector woken from hibernation doesn't know the
  alarm it set before, so it sets one no later than 30 s after the oldest
  claim the log hasn't got. Otherwise a claim every 20 s or so, each to a
  freshly woken sector, would put the log off again and again.
- The alarm reads claims made since the last one D1 has (the sector's
  `logged` mark, with an index on the claims' time) and writes up to 240 in
  one D1 batch: 12 rows to an `INSERT` (D1 binds at most 100 values to a
  statement) and one transaction for the lot. Only then does the mark move.
- **If D1 fails**, nothing is lost: the claims are still in the sector, the
  mark stays, and the alarm tries again after 1, 2, 4… minutes, up to 10.
  Workers Logs gets a `{survey: 'log failed'}` line. A write that reached D1
  but whose answer was lost is sent again; rows are keyed by `(at, key)`, so
  D1 ignores the copy.
- A claim's time is always after the sector's previous claim, even if the
  object moved to a machine whose clock is behind, so the mark can't skip
  one.
- The table is `WITHOUT ROWID` and ordered by `(at, key)`, so reading an hour
  reads just that hour's rows, and there's no other index to write: one row
  written per claim. The tests check each query's plan.

**Backfill.** None needed by hand. A sector that charted words before the log
existed has no mark, so the first time it wakes after the deploy it sends
every claim it holds, a batch a second, with their original times. Sectors
nobody visits again keep theirs until someone does. Since `SURVEY_URL` was
still empty on main when the log was built, that's only words charted by
people trying `?survey=`.

### The API

```
GET /v1/survey/log/day/<day>     (day = UTC days since 1970)
  → {"day", "hours": [24 counts, one per UTC hour], "total"}
GET /v1/survey/log/hour/<hour>   (hour = UTC hours since 1970)
GET /v1/survey/log/hour/<hour>?after=<at>~<key>
  → {"hour", "entries": [[w, x, y, d, s, initials, at, th], ...],
     "places": {"rx,ry": "Monet Hollow"}, "themes": {"th": [name, hue]},
     "next": "<at>~<key>" | null}
GET /v1/survey/log/month/<month> (month = UTC months since January 1970)
  → {"month", "hours": [[hour, words, world], ...]}   hours with none left out
GET /v1/survey/log/top/<from>/<to>   (UTC days from..to-1, at most 3,660)
  → {"from", "to", "surveyors": [[initials, words], ...10],
     "territories": [[rx, ry, name, th, words], ...10],
     "themes": [[th, name, hue, words], ...], "hidden"}
GET /v1/survey/log/top/hours/<from>/<to>   (UTC hours from..to-1, at most 48)
  → the same, with "hours": true, for a day or an hour in the page's time zone
GET /v1/survey/log/surveyor/<initials>/<from>/<to>   (UTC hours from..to-1)
GET /v1/survey/log/theme/<th>/<from>/<to>
GET /v1/survey/log/…/<from>/<to>?before=<at>~<key>
  → {"kind", "key", "from", "to", "words", "world",
     "hours": [[hour, words, world], ...],          hours with none left out
     "topTerritories": [[rx, ry, name, th, words], ...10],
     "topThemes": [[th, name, hue, words], ...]     a surveyor's
     "topSurveyors": [[initials, words], ...10]     a theme's
     "name", "hue"                                  a theme's
     "entries", "places", "themes", "next"}         newest first, 100 a page
GET /v1/survey/log/territory/<rx>/<ry>
  → {"rx", "ry", "name", "th", "total", "charted",
     "topSurveyors": [[initials, words], ...10], "nova": [...] | null,
     "entries", "places", "themes"}
GET /v1/survey/log/novas/<from>/<to>   (UTC hours from..to-1, at most 3,660 days)
GET /v1/survey/log/novas/<from>/<to>?before=<at>~<rx>~<ry>
  → {"from", "to", "count", "hours": [[hour, supernovas], ...],
     "novas": [[rx, ry, at, w, x, y, d, initials, first, words,
                surveyors, top, topN, th], ...],   newest first, 100 a page
     "places", "themes", "next"}
GET /v1/survey/log/timelapse
  → {"hours": [[hour, words], ...], "novas": [[hour, supernovas], ...],
     "bounds": [rx0, ry0, rx1, ry1] | null,          territories with hidden words charted
     "themes": [[name, hue], ...],                    every theme, in order
     "layout": [a, n]}                                a territory's theme is (rx + a·ry) mod n
GET /v1/survey/log/timelapse/<day>   (day = UTC days since 1970)
GET /v1/survey/log/timelapse/<day>?after=<at>~<key>
  → {"day", "words": [[t, x, y, d, len, th, s], ...],   oldest first, 5,000 a page,
     "novas": [[t, rx, ry, th], ...],                    t in ms since the day began;
     "next": "<at>~<key>" | null}                        supernovas on the first page
```

An hour comes oldest first, 500 entries a page; `next` is the `after` for the
next page. A day, hour or month that hasn't started is a 400. `world` counts
the hidden words in the shared world, which go toward its 1,119,752. Top
lists count hidden and stray words for surveyors, but only hidden words for
territories and themes, since a stray's theme is one its word is in, not
always its territory's. The day endpoint is still there for older copies of
the page.

**Caching.** Past hours and days don't change, but a claim can reach D1 up to
`LOG_MS` late, or later while D1 is failing. So an hour or day that ended an
hour ago (`SETTLED_MS`) is cached for a day, and the one still running for
15 seconds:

- `Cache-Control` on every answer, for browsers;
- in each Worker instance's memory (up to 300 answers), so a crowd reading
  the current hour costs one D1 query per instance every 15 s;
- in Cloudflare's cache through the Cache API. The cached copy has no CORS
  headers; each answer adds its own origin's. That cache is shared by every
  Worker on the same zone, and all of this account's `workers.dev` Workers,
  Worker Previews included, are one zone, so each answer is kept under its
  own Worker's host and its map (`<host>/_cache/survey-log/m<MAP_VERSION>/<path>`).
  Before the host was in it, a pull request's preview put its test history's
  months in the cache and production read them back for a day; the map is
  there so that a new map, which empties the log, doesn't read back the old
  one's days. The page's requests carry a version (`CACHE_VERSION` in
  `letterfield-log.html`), raised each time so browsers drop the copies
  they've kept.

A backfilled sector's old claims can take up to a day to appear in hours that
were already cached.

### Periods

The page has tabs for a day, a week (Monday to Sunday), a month, a year and
all time, each in the player's own time zone, with arrows to the one before
or after. Each shows three numbers (words charted, the busiest piece of the
period, and how many were hidden words in the shared world), a chart, and
then what's in it:

| period | chart | below it |
| --- | --- | --- |
| hour | a column a minute | top surveyors, territories and themes; every word, newest first |
| day | a column an hour | the top lists; each hour's words, loaded as they scroll into view |
| week, month | a column a day | top surveyors, territories and themes; each day as a row |
| year | twelve month calendars, a cell a day, in four shades of one hue by rank among the year's days with words (so one huge day doesn't wash out the rest) | the top lists; each month as a row |
| all time | a column a month, a meter of the shared world charted, and, from the second month, a line of it filling in | the top lists; each month as a row |

Tapping a column, cell or row opens the shorter period inside it, down to an
hour. The rows say what the chart says without hovering, which is the
chart's table view; hovering or focusing a column shows its number too.

**The hour, minute by minute,** opens from a day (its column, or "Minute by
minute" on an hour's heading) rather than having a tab: most hours hold a
handful of words, and a day already lists them. It's there for a busy
hour. The hour still running says Live and reloads every 20 seconds while
the page is on screen; nothing else reloads by itself.

**Counts, not rows.** A week or a year of the log itself could be a
million rows to read, and the running ones change constantly, so the longer
periods never read it. A second migration
(`migrations-log/0002_survey_log_counts.sql`) keeps three tables of running
totals, updated by triggers in the same transaction as each row of the log:

- `survey_log_hours`: words per UTC hour, and how many were hidden words in
  the shared world;
- `survey_log_surveyors`: words per UTC day per set of initials;
- `survey_log_territories`: hidden words per UTC day per territory.

`INSERT OR IGNORE` doesn't fire a trigger for a row it skips, so a resent
batch counts nothing twice, and a delete takes its word back out. The
migration fills the tables from the rows already logged, after creating the
triggers, with absolute numbers, so a word logged while it runs is counted
once either way.

The page draws every chart from hourly counts, a UTC month at a time (at
most 744 rows read for a month, whatever happened in it), and puts each hour
in the local day, week, month or year it starts in. In a time zone a half
hour off UTC, an hour that starts at 11:30 pm counts toward that day.
A week's or longer period's top lists come from the daily tables, so they
cover whole UTC days and can run a few hours past a local week's edges; the
page says which days. A day's and an hour's are counted from the log's own
rows over those hours (`top/hours`), so they cover just that local day or
hour: a day is at most a day's rows, read in time order, which is cheap
where a week's wouldn't be.

"Mine" for a week or longer counts this browser's finds by when they were
found, without asking the server. It has no top lists: they'd only ever say
"you".

**Caching the counts.** A month or a top list that ended an hour ago is
cached for a day, like an hour. The running month is cached for 15 seconds,
and a running top list over more than two days for 10 minutes: it changes
slowly and reads every day's rows in its range.

### Surveyors, territories and themes

Every name in the log opens a view of its own: a word's initials, its
territory and its theme, and every row of the top lists. Each view's
address says what it is, so it can be shared or bookmarked:

| view | address | periods | shows |
| --- | --- | --- | --- |
| a surveyor | `?surveyor=ZED` | all of them, all time first | words signed ZED: chart, top territories and themes, the words by day |
| a theme | `?theme=<n>` | all of them, all time first | hidden words in its territories: chart, top surveyors and territories, the words |
| a territory | `?territory=<rx>,<ry>` | none: all time | how many of its hidden words are charted (a meter), top surveyors, every word, and a link to fly there |

A surveyor's or theme's view opened from a period keeps it, so ZED from this
week's top list is ZED's week; the period tabs then move through ZED's
history the same way as everyone's. Going into a view, or back to
everyone's, is a new entry in the browser's history, so Back returns to
where it came from; moving between periods replaces the address as before.
A view's Share button uses the phone's share sheet, or copies the link.
Link previews are still the page's own, since the site is static.

Initials aren't unique, so "ZED" is everyone who typed ZED, and the view
says so. A stray word's theme is its word's, not its territory's, so a theme
counts hidden words only, like the top lists, and strays don't link to one.

**Indexes, not counts.** These read rows of the log, not the count tables,
since a surveyor's words or a territory's are a small slice of it. A third
migration (`migrations-log/0003_survey_log_lookups.sql`) adds three indexes,
one for each:

- `survey_log_by_initials (initials, at)`, leaving out unsigned words;
- `survey_log_by_territory (rx, ry, at)`;
- `survey_log_by_theme (th, at)`, hidden words only.

A word's territory and theme aren't stored: they're virtual columns worked
out from its start cell as the game does (floor division by 48, and
`(rx + 15 ry) mod 225`), so only the indexes hold them. A test checks the
SQL matches `regionTheme` for random cells, negative ones included. A new
layout of the themes means a migration that redefines the theme column and
its index, as `migrations-log/0005_survey_log_map_4.sql` did for map 4. Each
query names its index with `INDEXED BY` and pages in `(at, key)` order,
which the index already holds (an index on a `WITHOUT ROWID` table carries
the primary key), so a page of words never sorts. The tests check every
plan.

A surveyor's or theme's answer is three queries over its rows in the range
(per hour, per territory, and a page of words), plus its top surveyors for a
theme. A territory's reads all its words at once: about 110 are hidden in
each, so even fully charted that's a short list, and the Worker counts its
hidden words from the map. Settled ranges are cached for a day, as
elsewhere; a running one for 15 seconds, or 2 minutes over more than two
days, and a territory for 15 seconds.

### Supernovas

A territory goes supernova when every one of its hidden words (about 112,
from 102 to 122) has been charted: the game plays a charge, a burst and a
shockwave, and the territory looks different afterwards (a deeper tint,
a faint shell and a few stars). The log keeps each one: where, when the
last word came in, that word and who charted it, when the first did, how
many sets of initials charted it, and who charted most.

**Where they're recorded.** The options were:

| | for | against |
| --- | --- | --- |
| **the sector, when the last word comes in** (chosen) | a territory lies inside one sector, whose claims run one at a time, so exactly one claim completes it, even when two land together; the sector already counts each territory's hidden words for the Atlas, and works out the totals from the map in about 3 ms | a table more in each sector, and a migration |
| worked out from the log | nothing new in sectors | the log doesn't know totals, so every territory with words would be counted and checked against the map, on every read; a claim that reaches D1 late would make a supernova appear, then move |
| triggers on the count tables | stays in D1 | SQL can't count a territory's hidden words without a table of 10,000 totals, made from the map and rebuilt with every new one, and "the claim that completed it" means the order rows arrive in, not the order they were made |

So `Sector.supernova()` writes a row to the sector's own `novas` table in
the same step as the claim that completed its territory, before anything is
awaited. A sector that's evicted and wakes works its counts out again from
storage, so the next claim still sees it. On the first join after waking,
a sector also looks for completed territories it has no row for
(`findNovas()`), so territories finished before supernovas were recorded
are found the first time anyone visits, with the times of the claims
themselves, as the log's own backfill works.

**How they reach D1.** The log's alarm sends them in the same batch as the
claims (`survey_log_novas`, `migrations-log/0006_survey_log_novas.sql`),
keyed by territory so a resent row is ignored. A supernova goes only once D1
has its last word: in a backlog of more than one batch, it waits for the
batch that carries that word, so the list never names a word the log
doesn't have yet. If D1 fails it stays unsent and goes with a later try. A
new map empties sectors' rows along with their claims. Taking a word out of
the log for moderation leaves its territory's supernova alone: delete or
edit that row too.

**On the page.**

- **A list** (`?supernovas`, from "Supernovas" in the header): every
  period, all time first, like a surveyor's view. Its chart counts
  supernovas, and each one says where (with its theme's colour, linking to
  the territory), when, how long it took from first word to last, how many
  surveyors, who charted most, and the last word, which flies to the map.
- **In everyone's periods:** a line above the log names the period's
  supernovas, with the way to the list for the same period; the chart's
  columns that held one wear a star; and a day's or an hour's words show
  each supernova just above the word that set it off.
- **A territory** that's gone supernova says so in place of "Charted so
  far": when, first word to last, and who charted most; its words show the
  supernova above the last one; and its share card says "Supernova" and
  how it went (`share/src/view.js`), with no new address.

**In the game,** every supernova a player sees (the burst nearby, or the
note for one further off) and every territory they find every word of
themselves is kept in their field notes (`letterfield.novas.v1`), and a
note after the burst offers to share it. A shared one links to the share
Worker's card of its territory (`/v/territory/<rx>,<ry>`), drawn as a
supernova. A player shares one seconds after it goes off, before the log
has it, so the share Worker asks the territory's sector for it
(`GET /nova/<rx>/<ry>`, an internal path like `/claim/<key>`) when the log
hasn't got it yet.

If the list can't be loaded, the period shows without its supernovas.

**Seen from a neighbouring sector.** A page holds only the claims of the
sectors it has joined (at most four, nearest the middle of the screen), so
on its own it would only see a supernova in one of those. A territory one
territory off, across the edge of a sector it hasn't joined, would go off
unseen. So when a claim sets off a supernova, its sector tells the sectors
nearby, and they tell their players:

- **Who's told:** every other sector with a territory within `NOVA_REACH`
  (3) territories of it, counting as the game's `nearView` does: the larger
  of the two distances. A player whose view is centred that close is in one
  of them, or in the territory's own sector, and the page always joins the
  sector under the middle of its view. Sectors are 4 territories wide, so a
  territory on a corner of its sector tells 3 neighbours, one on an edge 5,
  and one of the middle four all 8 (`novaNeighbours()`).
- **How:** after the claim has gone out, the sector POSTs
  `{nova: [rx, ry, at, w, x, y, d, initials]}` (the territory, its last word
  and who charted it, when) to each one's internal `/near` path, inside
  `ctx.waitUntil`, so nothing waits on them and one that fails doesn't stop
  the rest. Each broadcasts `{t: 'nova', n: [...]}` to its own players. Its
  own players already had the claim, as ever.
- **Only from a sector:** the public router forwards nothing but WebSocket
  upgrades of sector paths, so `/near` can't be reached from outside, as
  `/claim/<key>` and `/nova/<rx>/<ry>` can't. A neighbour still checks what
  it's sent (`checkNova()`): a hidden word that's really there, in the
  territory named, in another sector within reach of its own.
- **On the page:** a `nova` frame plays the supernova if it's within reach
  of the middle of the view, and is a note otherwise, as a claim that
  completes a territory is; it's kept in the notes' supernovas, and the
  territory becomes a remnant at once. A page joined to the territory's own
  sector too leaves it to that sector's claim, which says whether the last
  word was the player's own, and either way it goes off once.
- **Reach:** 3 territories, as `nearView` has always used. At the closest
  zoom that's far off screen, and the shockwave sweeps in from the edge
  nearest it, two or three seconds after the flash. Zoomed right out (2
  pixels a cell, 96 a territory), a phone shows about 2 territories each side
  of the middle and a computer 5 or 6, so a supernova at the edge of a wide
  screen is a note rather than a burst.

**Cost:** at most 8 Durable Object requests per supernova, one per
neighbour, and a broadcast in those with players. A neighbour with nobody in
it is woken only to answer at once. Asking the Atlas which neighbours have
players first would be a request too, and the Atlas only knows the shared
world, so it isn't done. With 10,000 territories in the shared world, every
supernova there ever will cost at most 80,000 requests: about a cent.

**Caching** is the same as a surveyor's view: a range that ended an hour
ago for a day, a running one for 15 seconds, or 2 minutes over more than two
days, and a page through its own cursor. `CACHE_VERSION` didn't need
raising: no answer a browser already holds has changed.

### The timelapse

[letterfield-timelapse](https://games.michaelwarkentin.com/letterfield-timelapse)
replays the log on a map. Each word appears as a stroke in its theme's
colour across the cells it covers, glowing as it lands. Territories fill
in with their theme's tint as their hidden words are charted. Supernovas
flash, throw off a shockwave and leave the remnant look the game uses. The
camera widens to keep the charting so far in view: territories within 8 of
each other count as one cluster, and it frames the cluster charting began
in (until another has twice its words and 3 more) plus any other with at
least 12 words and 5% of all of them. A few words
charted far out in the endless map stay drawn but off screen, rather than
shrinking everything else to a dot (a preview's test words did). The page has play
and pause, a scrubber, four speeds (the whole history in 80, 40, 20 or 10
seconds) and a running count of words, supernovas and territories. A tap
on a territory names it and links to its page in the log. Under reduced
motion it opens paused on the whole map, and draws no glows, flashes or
easing. It's its own page rather than a view of the log's: a canvas that
owns the screen and records itself, where the log is a document that
scrolls.

**Nothing to regenerate.** It plays from the log as it stands each time
it's opened. "Save video" records the same drawing in the browser
(`canvas.captureStream()` and `MediaRecorder`, MP4 where the browser can,
WebM otherwise) at 1080×1080, the whole history in 24 seconds, with the
date and counts in the frame, so anyone can make a current video in half a
minute without a server. It's hidden where the browser can't record.

**What it can and can't show.** The log keeps every word charted (where,
which way, how long, its theme, when) and every supernova, so the map
filling in is exact. It doesn't keep where anyone looked or moved (carets
are live only), how many were online over time (the Atlas knows only now),
or places visited where nothing was charted. So it shows the map being
charted, not people wandering.

**The API, for drawing only.** A day comes oldest first with only what
drawing needs: time into the day, start cell, direction, length, theme
(a stray's is its word's) and whether it's a stray. It sends no words or
initials. The index says which hours have words (and how many, so counts
can run ahead of what's loaded), when supernovas went off, the charted
territories' bounds, every theme's name and hue, and the layout of themes,
so the page tints any territory with none of the map's words. The page
loads the index, then days oldest first, three at a time, and starts
playing as soon as the first has arrived. Past what's loaded, it waits.
An hour with nothing charted takes a twentieth of the time of one with
words, so a quiet night goes by in a blink.

**Caching.** A day that ended an hour ago (`SETTLED_MS`) never changes, so
it's kept for good: a `max-age` of a year and `immutable` for browsers, and
the same in each Worker instance and Cloudflare's cache. Today is cached
for 15 seconds. The index is cached for a minute, but the part covering
settled days is kept for good, under the day it was cut at, and only the
days since are read each minute. Every key carries `TIMELAPSE_VERSION`,
and the page's requests carry its own `CACHE_VERSION`. Taking a word out
of the log for moderation means raising both, or the old day stays in
caches.

### Where, readably

Coordinates mean little, so each answer names the territories its entries
are in (`places`, such as "Monet Hollow") and gives each theme's name and
hue. The Worker works these out with `regionName`, now in
`src/letterfield-world.js` beside the themes it already had (a test checks
it names every territory in the shared world as the game does). The page
holds none of the map's 140 KB of theme data.

### "Mine"

Initials are three letters anyone can type, so they can't say which words
are yours. Two ways could:

- **The finds already on the device** (chosen). The log is on the same
  origin as the game, so it reads `letterfield.finds.v2`, where the game
  marks each word a sector said you charted first (`f`). Mine is the day's
  log narrowed to those words: the page fetches only the hours that hold
  one, plus the hour either side when a find is within 10 minutes of it, in
  case the device's clock was off. Everyone's log marks yours with "you".
  Nothing about the player is sent or stored.
- **A private player token**, like War's `war:token`, sent with each claim
  and kept by the server as a hash. It would be the server's own record, so
  a lost "you were first" answer wouldn't matter. But the token would live in
  the same `localStorage` as the finds, so it reaches no further: a new
  device or a cleared browser starts again either way. It would also add a
  column to every sector's claims, a field to the protocol, and a lasting
  pseudonymous ID for every claim, which would need keeping out of the API
  just like hashed addresses and socket ids.

The token would be worth it only with a way to carry it to another device
(a sync code, say). On an iPhone the Home Screen app keeps its own storage,
so the log is in Letterfield's app (see the build below) and opens there
with the same finds.

### How the page fits the site

`letterfield-log.html` is a top-level page like a game, so it's published,
listed in the README, smoke-tested at phone and desktop sizes, cached
offline by `sw.js` and gets telemetry and analytics. It isn't a game of its
own, though: `<meta name="games:app" content="letterfield">` puts it in
Letterfield's home-screen app (`app_of` in `scripts/common.py`). It gets no
manifest, icon or preview of its own, and since `/letterfield-log` starts
with `/letterfield`, it's inside Letterfield's app scope. Letterfield's
survey panel links to it. Its `SURVEY_URL` already points at the Worker,
since it only reads; until the survey is on, the log is empty.
`letterfield-timelapse.html` fits the same way, and the log's header links
to it.

### Cost

On Workers Paid, per word charted: up to seven D1 rows written (the log's
row, an update each to the hour's, the surveyor's and the territory's
counts, and a row in each of the three indexes; no initials or a stray word
skips two), one more row written in the sector (its time index), and a
share of an alarm. A supernova, once per territory (10,000 in the shared
world), adds two rows written in its sector (the row and marking it sent)
and two in D1 (the row and its index on time), and reads its territory's
claims once, about 110 rows: next to the 112 words that made it, nothing.
Reading the list costs the supernovas in its range, at most 100 a page,
plus one count for each. Each busy sector's
alarm runs at most every 30 s: one Durable Object request and two rows
written (the alarm and the mark).

| | whole world charted (1.12 M words) | a busy day (30,000 words) | the ceiling (all 625 sectors charting nonstop) |
| --- | --- | --- | --- |
| D1 rows written | ~8 M (50 M a month included) | ~210,000 | 75,000 batches an hour |
| D1 storage | ~100 MB for the log, ~50 MB of indexes, a few MB of counts (5 GB included) | ~4 MB | |
| alarms (DO requests) | | ≤ 2,880 per busy sector | ~$0.011 an hour |
| rows written in sectors | 1.12 M + 2 per alarm | | ~$0.15 an hour past the included 50 M |
| D1 rows read | see below | | |

So the log adds nothing past the included allowances at the survey's
expected sizes, and at the ceiling raises the worst case from about $0.75 to
about $0.92 an hour. `LOG_MS` is the knob: 60 s would halve the alarm costs.
The whole world, charted, would take about 8 million of the 50 million D1
rows written included each month.

Reading is cheap: 25 billion D1 rows read a month are included. An hour
reads its own rows, a month at most 744, and a settled one is read about
once a day per Worker instance. Top lists read every row of their range in
the daily tables: a busy day might have a few hundred sets of initials and
a thousand territories, so a running year's list could read a few hundred
thousand rows, at most every 10 minutes per instance. If that ever shows in
the bill, the next step is a monthly level of the same counts. A surveyor's
or theme's view reads its rows in the range three times: all time for
someone with 10,000 words is about 30,000 rows, at most every 2 minutes per
instance while it's running.

**The timelapse** reads each word's row once per day it's kept. A full
replay, cold, reads every word plus the index's count rows (one per hour
with words, per territory per day, and per supernova):

| | words | rows read, cold | sent to the browser |
| --- | --- | --- | --- |
| today (Nov 12, 2026) | 340 over 3 days, 2 supernovas | ~370 | ~9 KB of JSON |
| 10× | 3,400 | ~3,900 | ~85 KB |
| 100× | 34,000 | ~38,000 | ~850 KB (about a third gzipped) |
| the whole world | 1.12 M | ~1.2 M | ~28 MB |

Cold happens once per settled day per Cloudflare data centre, then never
again (see "Caching" under "The timelapse"). After that a replay reads
only today's rows, at most every 15 seconds per instance, and a day or two
of the index's count rows, at most every minute. Next to the 25 billion
rows read included each month, that's nothing. At whole-world scale it's
the page's download, not the bill, that would want a coarser format (see
"Not done yet").

On the free plan, D1 and Durable Object storage each allow 100,000 rows
written a day, so the log, with its counts and indexes (seven D1 rows a
word), cuts the claims a day the free plan allows to about a seventh (see
"On the free plan").

**A database of its own.** The log lives in `games-survey-log` (the
`LOG_DB` binding, with its migrations in `migrations-log/`), not in the
leaderboard's database. A D1 database runs one query at a time, so this way
a backfill, a busy day's batches or a crowd reading today's log never
queue with score saves, and the log can be emptied or rebuilt without going
near scores. D1 bills by rows, not by database, so it costs nothing extra.
mwarkentin/infra makes it (`cloudflare.tf`). Without the binding, sectors
don't log and the log's paths aren't answered.

## Do Workers and D1 scale for this?

**Workers: yes.** They're stateless, and Cloudflare runs as many copies as
there are requests. What matters is the request count: the free plan allows
100,000 a day, and the paid plan charges $0.30 per million after 10 million
a month. WebSocket messages don't count as Worker requests; only the
connection does.

**D1: not for the live part.** It's the right home for the leaderboards: a
few writes per game, read now and then. A shared live map is a different
load ([D1 limits][d1limits]):

1. **One database handles one query at a time.** That's about 1,000
   queries a second at 1 ms each, and fewer in practice because of
   per-request overhead. Writes take "several milliseconds" because they're
   persisted to several locations. You scale D1 with many databases, not a
   bigger one.
2. **D1 can't push changes.** "Live" would mean every browser polling. 1,000
   players polling every 3 seconds is ~330 queries a second, just to hear
   "nothing new".
3. **Positions are the worst case.** They're tiny writes that matter for a
   second. 1,000 players moving every 2 seconds is 500 durable writes a
   second, more than one database sustains.
4. **The free plan runs out in minutes.** Free D1 allows 100,000 rows
   written a day, and queries fail once you pass it. Free Workers allow
   100,000 requests a day. 1,000 polling players would use up the requests
   in about 5 minutes.

**Durable Objects: yes, split by place.** They're built for this, and they
run on the same Worker:

- **The server can push.** Outgoing messages are free, and incoming
  WebSocket messages are billed as one request per 20.
- **One object has limits.** Cloudflare's soft limit is 1,000 requests a
  second per object. Its guidance is 500–750 a second with JSON parsing and
  200–500 with storage writes ([rules][rules]). That's why there's an
  object per sector, a socket cap per sector, and players spread over
  sectors.
- **D1 still fits for cross-sector boards.** A board like "most words
  charted first" would get a total from each sector every minute or so:
  one write per active sector, however many players.

### Measured on the Workers runtime

`worker/bench/load.js` runs real WebSocket players against the Worker:
- each sends a position every ~2 s;
- each circles a random hidden word every 20–40 s;
- players connect at 40 a second.

These runs used `wrangler dev`, which is Cloudflare's `workerd` runtime
running locally, on a 4-core sandbox shared with the load generator. That's
not Cloudflare's edge, so treat the numbers as relative; the next step is
running the same script against a deployment.

| players on one sector | version | connected | claim round trip p50 / p95 / p99 | positions every | sector CPU |
| --- | --- | --- | --- | --- | --- |
| 200 | first | 200 | 38 / 261 / 459 ms | 1.0 s | |
| 750 | first | 410 (stalled) | 1.2 s / 17 s / 22 s | 1.1 s | 100% |
| 750 | positions kept in memory | 630 | 0.6 s / 9.6 s / 16 s | 1.1 s | 97% |
| 750 | + claims batched | 750 | 61 / 305 / 435 ms | 1.0 s | 84% |
| 1,000 | + claims batched | 990 | 148 ms / 12 s / 25 s | 1.1 s | 98% |
| 700 | final | 700 | 3 / 124 / 195 ms | 1.0 s | 55% |
| 900 | final (cap 750) | 750, 150 turned away | 3 / 128 / 190 ms | 1.0 s | |

So one sector comfortably holds ~750 sockets, and that's where
`MAX_PLAYERS` is set. New players are sent to a crowd only while it has
fewer than 300 people placed in it, leaving room for neighbours who are
also watching that sector.

`worker/bench/sector.js` times our own code in Node: about 3 ms of work per
second for 1,000 players. So almost all of a sector's load is the runtime's
own per-message work: receiving, dispatching and sending. A Node benchmark
alone would have overstated capacity several hundredfold.

### Cost

Published Workers Paid prices ([Workers][wpricing],
[Durable Objects][dopricing]):
- **Workers:** $5 a month, including 10 M requests, then $0.30 per million;
  no egress fees.
- **Durable Objects:** 1 M requests included, then $0.15 per million (each
  incoming WebSocket message counts as 1/20 of a request; outgoing messages
  are free).
- **Durable Object time:** 400,000 GB-s included, then $12.50 per million
  GB-s, billed at 128 MB per object.
- **SQLite storage:** 50 M rows written included, then $1 per million.

Usage per player-hour, from the design and the 700-player run:

| | per player-hour | how |
| --- | --- | --- |
| Worker requests | ~30 | ~10 connections as you roam, plus world map reads |
| Durable Object requests | ~106 | 10 connections + ~1,900 incoming messages ÷ 20 |
| Durable Object time | ~0.35 GB-s | ~0.8 ms of sector time per player per second, with no timers keeping it awake |
| Rows written | ≤ words charted | a claim is one row, and the world has ~1.1 M words to claim |

| scenario | player-hours | Worker requests | DO requests | DO time | total with the $5 plan |
| --- | --- | --- | --- | --- | --- |
| 1,000 players, 2 hours a day, for a month | 60,000 | included | ~$0.80 | included | **~$6** |
| an eieio-style viral fortnight: 5,000 online on average, up to the cap | 1.68 M | ~$12 | ~$27 | ~$12.50 | **~$57** |
| the ceiling: `MAX_ONLINE` (25,000) online all the time | 25,000 an hour | ~$0.22/h | ~$0.40/h | ~$0.11/h | **at most ~$0.75 an hour (~$18 a day)** |

The surveyor list and emotes add about $1.50 a day at 10,000 online (see
"Surveyors and emotes"), mostly the list's own requests, and guilds about
$0.30 more (see "Guilds"). The per-address
limits don't change these figures. A rate-limiting binding
isn't a Durable Object, so it adds no Durable Object requests, and neither
pricing page lists a charge for it. The hashed address is worked out once
per connection, in the Worker. The daily cap rides on the reports sectors
already send the Atlas: they grow by one entry per address that charted
something in the last 10 s or so.

For comparison, OMCB cost about $850 to run, on 8 VMs, Redis and bandwidth.
One Million Chessboards cost "a few hundred dollars": a $450/month box,
later $80/month, plus about a terabyte of traffic a month. On Cloudflare,
the survey costs the $5 plan when nobody is playing.

The first version, with timers, would have been billed for every second
every busy sector existed: ~$0.0056 per sector-hour. That's ~$84 a day for
625 busy sectors, before counting the quiet ones.

### Why Workers Paid

The account moved to Workers Paid for the survey. On Workers Free, every
limit is per day, shared by the whole account (the leaderboards and War's
rooms included), and reset at 00:00 UTC. Past a limit, requests fail rather
than cost money ([Durable Objects][dopricing], [Workers][wpricing]):

| free plan, per day | allowance | survey use per player-hour | enough for |
| --- | --- | --- | --- |
| Durable Object requests | 100,000 | ~106 | **~940 player-hours** |
| Worker requests | 100,000 | ~30 | ~3,300 player-hours |
| Durable Object time | 13,000 GB-s | ~0.35 GB-s | ~37,000 player-hours |
| SQLite rows written | 100,000 | ≤ words charted | 100,000 claims |

So on Free, Durable Object requests would run out first, at about 940
player-hours a day: 100 people playing for 9 hours, or 450 for 2. Every
Durable Object on the account would then stop answering until midnight UTC,
War's rooms included. On Paid, a day that busy every day of the month costs
about 30 cents over the included million requests.

## Not done yet

- **A spending alert.** Workers Paid has no spending cap; `MAX_ONLINE`
  keeps the worst case near $18 a day. A scheduled check of Cloudflare's
  analytics API could open a GitHub issue when the month's usage passes a
  threshold.
- **Run `load.js` against a deployment.** That would confirm the per-sector
  limit and the 0.8 ms per player-second on Cloudflare's edge rather than a
  sandbox.
- **Bots from many addresses.** Each address is limited (see "Limits per
  address"), but a botnet or a pool of proxies still gets those limits once
  per address. "Watching for bots" says when it's happening. A
  [Turnstile][turnstile] check before joining is built and switched off:
  [TURNSTILE.md](TURNSTILE.md) covers how it works, what it costs and how
  much it stops (scripts and cheap proxies, not a bot that pays a solver
  service), and how to switch it on in steps. It needs a widget and secret
  made in mwarkentin/infra.
- **Smaller snapshots.** Hidden words are deterministic, so a claim could
  be one bit in its chunk's word list. A fully charted sector's snapshot
  would shrink from 68 KB to a few hundred bytes plus initials. eieio
  measured protobuf + zstd at about 30 times smaller than uncompressed JSON.
- **Edge caching.** The world map is cached per Worker instance. On a
  custom domain, Cloudflare's cache could serve it as chessboards did.
- **Zoomed-out views** only show live claims from the four nearest sectors.
  A cached per-sector snapshot could fill in the rest of the screen.
- **The log, live, beyond the hour.** The running hour reloads every 20
  seconds; a running day, week or longer shows what it had when opened. It
  could take claims from the sector sockets the game already uses.
- **Supernovas, live.** A supernova more than 3 territories from the middle
  of your view is a toast in the game, even when it's on a wide, zoomed-out
  screen, and a line in the log once the log has it. Nearer ones reach you
  from neighbouring sectors too (see "Supernovas"). The log's list could
  take them from the sector sockets, as the running hour could.
- **Supernovas outside the shared world** are recorded and listed like any
  other, but the game's world map only covers the shared world, so far
  away ones only show as remnants when you're there.
- **A richer timelapse.** The log has nothing on where people went, only
  what they charted. The Atlas could write how many surveyors were online
  in each sector once an hour (625 rows an hour at most, a few cents a
  year), so a later timelapse could show the crowd moving. Sectors could
  also count visits to territories with nothing charted. Neither is
  recorded yet, and a timelapse can never show the past of either.
- **A smaller timelapse at world scale.** A day's words are about 25 bytes
  each as JSON, so a whole world charted would be 28 MB to download. Past
  a few hundred thousand words, each settled week could be served as one
  binary file (a word fits in 8 bytes), or the page could draw far zoom
  levels from the territory counts alone.
- **The surveyor list, pushed.** If its requests ever show in the bill, the
  Atlas can answer each sector's report with the surveyors nearest it, for
  the sector to pass on to sockets that asked (see "Why not push it").
- **Emotes and toasts.** An emote's note is a note like any other; once notes
  can be quietened by kind, emotes should be a kind of their own. "Take
  emotes" already turns them off entirely.
- **Reporting a player.** There's nothing to report but three letters, which
  `BLOCKED_INITIALS` screens, and seven drawings; mute is on the device. A
  muted player with a new token is a new id, held back only by the limits.
- **Guilds:** see "Left for later" under "Guilds".
- **Passkeys.** A passkey, synced by the player's own iCloud Keychain or
  Google account, could bring a surveyor back with no code to keep. It
  needs WebAuthn credentials stored and checked in the Worker.
- **Syncing as it happens.** Two linked devices open at once catch up
  within a minute. The Player could hold a WebSocket to each, hibernating,
  and push a find the moment it lands, if a minute ever feels slow.
- **Finds made offline stay personal.** Uploading them later would let
  anyone backdate a pile of claims at once.

## Trying it

```sh
cd worker
npx wrangler@4.151.0 dev --port 8787     # the Worker and its Durable Objects, locally
node bench/load.js http://127.0.0.1:8787 300 30   # 300 players for 30 s
```

Each player in `load.js` sends its own `CF-Connecting-IP`, so the limits per
address don't turn them away. Only `wrangler dev` believes that header:
Cloudflare's edge sets it itself, so the same trick can't get round the
limits on the real Worker.

To play, serve the games from the repo root (`python3 -m http.server 8000`)
and open `http://localhost:8000/letterfield.html?survey=http://localhost:8787`
in a few windows. The deploy workflow's `wrangler deploy` creates the
`Sector` and `Atlas` classes from the migration in `wrangler.toml`, and
`SURVEY_URL` in `letterfield.html` points the live game at the deployed
Worker.

To try the log's weeks, months and years without weeks of play,
`bench/seed-log.js` prints made-up history (real words at their real places,
over the last 45 days by default) as SQL for a test database:

```sh
node worker/bench/seed-log.js 45 > /tmp/seed.sql
cd worker
npx wrangler@4.151.0 d1 execute games-survey-log --local --file /tmp/seed.sql   # with wrangler dev
npx wrangler@4.151.0 d1 execute games-survey-log-previews --remote \
  --config wrangler.previews-migrations.toml --file /tmp/seed.sql             # every Worker Preview's log
```

Never point it at `games-survey-log` with `--remote`: that's the real log.
For the timelapse, `node worker/bench/seed-log.js 9 explore` has surveyors
push out from the origin a territory at a time and finish some, with their
supernovas, so there's something to watch.

[omcb]: https://eieio.games/blog/scaling-one-million-checkboxes
[chess]: https://eieio.games/blog/a-million-realtime-chess-boards-in-a-single-process
[do]: https://developers.cloudflare.com/durable-objects/
[hib]: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
[lifecycle]: https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/
[rules]: https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/
[d1limits]: https://developers.cloudflare.com/d1/platform/limits/
[wpricing]: https://developers.cloudflare.com/workers/platform/pricing/
[dopricing]: https://developers.cloudflare.com/durable-objects/platform/pricing/
[ratelimit]: https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
[turnstile]: https://developers.cloudflare.com/turnstile/
[alarms]: https://developers.cloudflare.com/durable-objects/api/alarms/
