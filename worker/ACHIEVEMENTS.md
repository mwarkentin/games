# Letterfield's achievements and days surveyed

Achievements, the badges that show them, and a daily streak, for
Letterfield. They're kept beside the survey's design (`SURVEY.md`) because
they sync through the same Player, and a badge shown to others is signed by
the same sectors.

**Where it stands.**

- **In the game** (`letterfield.html`, its Achievements section):
  everything is worked out from the surveyor's own field notes and
  supernovas.
- **Through the Player:** they sync between linked devices.
- **Shown to others:** one chosen badge, signed by the Worker from finds the
  sectors signed (see "Badges others see"), and a card in each surveyor's
  caret menu with every badge signed for them and when they began (see
  "Profile cards").
- **Shared code:** the rules are one block of code, word for word the same in
  the game and in `src/achievements.js`.

## What a player already has

Everything here comes from what the game keeps already:

- **Field notes** (`letterfield.finds.v4`): each find's word, start cell,
  direction, time, whether it's a bonus word (`s`), whether you charted it
  first (`f`), where it came in the universe's count (`n`), and who charted
  it when it wasn't you (`b`). Its theme and territory follow from where it
  is.
- **Supernovas seen** (`letterfield.novas.v1`): where, when, the last word,
  who charted it, whether that was you (`mine`), and whether it was yours
  alone (`solo`).
- **Settings:** initials, guilds, mutes and the emotes switch.

Linked devices already sync finds and supernovas through the Player, with a
merge that can't lose anything: each find is kept once, and "charted first"
only ever comes on. So almost every achievement, and the streak, can be
**worked out** from the notes on any device, rather than stored and synced
as a fact of its own. That's the core decision:

> Achievements are derived from the field notes, then **latched**: once
> earned, kept, with when, even if the notes that earned it are later lost
> to a redrawn map.

## Lessons from other games

| | what they do | borrow / avoid |
| --- | --- | --- |
| Wordle and NYT Games | streak counted by local date; stats keep **Max Streak** beside the current one; badges backfilled to existing players marked "Earned Retroactively" | borrow the local date, the longest kept for good, and marking badges earned from past play |
| Duolingo | streak freezes bought with gems, paid repair, guilt-tripping notifications | borrow forgiveness, but free and automatic; avoid the shop and any "you'll lose it" copy |
| Pokémon GO medals | bronze to platinum, each tier ten times the last; a daily bonus that peaks at 7 days | borrow tiers an order of magnitude apart, and runs whose reward stops at a week |
| Animal Crossing's Nook Miles | many small goals, some secret; a login bonus capped at 7 days; clock changes not punished | borrow small goals that teach, and not fighting the clock in solo play |
| Outer Wilds, Stardew Valley | the ship log and Collections tab are the progress screen | the field notes are the trophy case: achievements live there, not in a screen of their own |
| Celeste | the big collectible achievement is hidden; dying is framed as learning | hidden only to keep a surprise, never to make something missable; nothing for failing |
| GitHub, 2016 | dropped the contribution streak; a study found people had padded it with single, token commits | lead with **days surveyed** in total, not the run; ask for more than a token action |
| Apple's watchOS 11 | rings can rest without breaking a streak | a rest day doesn't end anything |
| Silverman and Barasch, 2023 | a broken streak shown to a player lowers engagement; one that can be repaired matters less | never show a run "lost"; keep the longest and the total beside it |
| Steam, Factorio | achievements earned offline arrive in a pile of pop-ups | one summary note, never thirty |

So, **avoid**: one counter that falls to zero, anything bought, "at risk"
copy, notifications outside the game, login rewards that keep growing,
endless tiers, badges for failing, badges that can be missed for good or
run out of time, badges for a time of day, comparing or ranking players'
streaks, and anything that pays for spamming emotes or joining guilds.

## The catalog

Thirty-nine achievements in nine groups. Each is checked from the notes
unless it says otherwise, and none needs a particular time of day. Five
are secret (hidden until earned, to keep the surprise, never to make them
missable). Nine are for the shared survey only, and don't show in solo play.

There are no solo-only ones on purpose: on the live site everyone is on the
shared survey (solo play is what the game does with `SURVEY_URL` empty, or
in a fork), so a solo-only badge would be one nobody could earn. Everything
that isn't about charting first or other surveyors works in both.

| group | achievement | to earn it | how it's checked |
| --- | --- | --- | --- |
| **Field notes** | First Mark | Circle your first word. | finds ≥ 1 |
| | Field Book | Keep 100 words in your field notes. | finds ≥ 100 |
| | Bound Volume | Keep 1,000 words in your field notes. | finds ≥ 1,000 |
| | Great Atlas | Keep 5,000 words in your field notes. | finds ≥ 5,000 |
| **Charting** (survey) | First Light | Chart a word first on the shared survey. | finds with `f` ≥ 1 |
| | Trailblazer | Chart 100 words first. | `f` ≥ 100 |
| | Pathfinder | Chart 1,000 words first. | `f` ≥ 1,000 |
| | Cairn (secret) | Chart a word that came in at a round thousand in the universe's count. | a find with `f` and `n % 1000 = 0` |
| **Territories** | Wanderer | Find words in 10 territories. | distinct territories of finds ≥ 10 |
| | Gazetteer | Find words in 50 territories. | ≥ 50 |
| | Every Last Word | Find every hidden word in one territory. | a territory whose hidden words found = `territoryTotal` |
| | Five Full Sheets | Find every hidden word in five territories. | ≥ 5 such territories |
| | Lion's Share (survey) | Chart first more than half of one territory's hidden words. | hidden finds with `f` in a territory > total ÷ 2 |
| **Themes** | Map Key | Find words from 25 themes. | distinct themes of finds ≥ 25 |
| | Full Legend | Find a word from every one of the 225 themes. | = 225 |
| | Lexicographer | Find every word one theme has. | distinct words found that are in a theme's list = its length, for any theme |
| | Dawn Chorus | Find words from all five bird themes. | Garden Birds, Birds of Prey, Aviary, Waterbirds, Birdwatching |
| | Seven Seas | Find words from all seven themes of the sea. | Deep Sea, Coral Reef, Whale Watch, Rock Pool, Seaside, Harbour, Sailing |
| | Star Chart | Find words from all four themes of the sky. | Space, Solar System, Night Sky, Sci-Fi |
| | Passport | Find words from all nine countries' themes. | India, Ireland, Mexico, France, Japan, Canada, Spain, Italy, Scotland |
| **Words** | Happy Accident | Find a bonus word, a real word the letters spell by chance. | finds with `s` ≥ 1 |
| | Serendipity | Find 25 bonus words. | `s` ≥ 25 |
| | Long Measure | Find a ten-letter word, the longest the map hides. | a find of 10 letters |
| | Compass Rose | Find words reading in all eight directions. | distinct `d` = 8 |
| | Mirror Image (secret) | Find a word that reads the same both ways. | a palindrome (KAYAK, RADAR, ROTOR…) |
| | Self-Portrait (secret) | Find the word SURVEYOR. | a find of SURVEYOR (Cartography, Building Site) |
| **Far afield** | Over the Horizon | Find a word 10 territories from the map centre. | the find's territory, `max(|rx|, |ry|)` ≥ 10 |
| | Edge of the Universe | Find a word 48 territories out, where the universe ends. | ≥ 48 (the universe runs from −48 to 51) |
| | Here Be Dragons (secret) | Find a word 250 territories from the map centre. | ≥ 250 |
| **Supernovas** | Witness | Be there when a territory goes supernova. | supernovas seen ≥ 1 |
| | Starfield | Be there for ten supernovas. | ≥ 10 |
| | Last Word (survey) | Chart the last hidden word of a territory, and set it off. | a supernova with `mine` and not `solo` |
| **Days** | Seven Days Running | Keep a streak going for seven days. | longest streak ≥ 7 |
| | Lunar Month | Keep a streak going for 28 days. | longest streak ≥ 28 |
| | Thirty Days Out | Survey on 30 different days. | days surveyed ≥ 30 |
| | Full Circle | Survey a year after your first find. | a day surveyed ≥ 365 days after the first |
| **Company** (survey) | Fellowship | Be in a guild. | latched when the game is in one |
| | Two Places at Once | Link another device, or save a recovery code. | latched when syncing is on or a code is saved |
| | Hats Off (secret) | Have someone tip their hat to you. | latched when a Thanks emote arrives |

**Why these.**

- **The first ones teach.** First Mark, First Light, Happy Accident,
  Compass Rose, Witness and Map Key each point at something the game has
  that a new surveyor might not notice: charting first, bonus words, the
  eight directions, supernovas, themes.
- **Tiers stop.** Counts go up roughly ten times a step (1, 100, 1,000,
  5,000) and then end. Great Atlas is a few months of steady play; past it
  there's nothing to chase, by design. Lexicographer and Full Legend are
  the long goals, and both are about seeing the whole map, not grinding one
  corner of it.
- **Theme groups** are the game's own kinds (the map keeps bird themes
  apart, see `THEME_DATA`): birds, the sea, the sky, countries. Every theme
  appears within 15 territories of the map centre, so each group is in reach
  of anyone who wanders.
- **Supernovas** are the survey's big moment. Witness and Starfield come
  from being there; Last Word and Lion's Share from the work. "Charting
  most of one territory" is Lion's Share, checked as more than half, since
  the game can't know everyone else's counts but more than half is always
  the most.
- **Company, with care.** Being in one guild is a single achievement, and
  joining more earns nothing. Nothing counts emotes sent. Hats Off is
  something another surveyor does for you, once; sending gains the sender
  nothing, so there's nothing to farm. Two Places at Once nudges toward
  keeping a surveyor safe (a recovery code), which is worth nudging.
- **Bots** gain nothing: badges are personal, the counts are capped, and the
  survey's own limits already bound how fast anyone charts.
- **Secrets** are found by playing (a palindrome, the word SURVEYOR, a round
  number, far travel, a hat tip). Each is shown as "Secret" with a question
  mark until earned, and nothing in its hint names a hidden word.

## Badges

Each achievement has a drawn badge: a ring with a line drawing inside, on a
32 × 32 grid, in the game's line style (the emotes' strokes and round caps).
Not emoji: they look different everywhere and mean different things to
different people.

- **Three states.**
  - **Earned:** a disc tinted in its group's colour, a solid ring, the
    drawing in the colour.
  - **Under way:** an empty ring whose arc fills clockwise from the top with
    the progress, and the drawing in the muted ink.
  - **Not started:** a dashed ring and a faint drawing, so you can see what
    there is to do. A secret one shows a question mark.
- **Two sizes.** 24 px, in the field notes' row and the unlock note, and
  64 px, on the Achievements page. The strokes are drawn thicker at the
  small size and thinner at the large one, so lines read the same at both;
  only the large one gets the bezel of ticks.
- **Colours** are a hue per group through the game's `--mark-s` and
  `--mark-l`, so they follow light and dark like the territories' colours.

## Days surveyed and the streak

**What counts:** a day counts once you've found **three words** that day:
hidden or bonus, charted first or not, or someone else's word you added to
your notes. One find can be a stray tap; three is a minute of play. GitHub's
experience is why it isn't one.

**Whose day:** the player's own local date where they are now, as the
leaderboards' periods and Wordle use. A day is a calendar date, so
daylight saving changes nothing. The page works it out from each find's
time, so:

- **Travelling** can move a late-night find to the next or the day before.
  A rest day absorbs that.
- **Two linked devices in different time zones** can each see a day's edges
  a little differently. Each is right for where it is.
- **Changing the clock** only fools yourself, so nothing fights it, as
  Animal Crossing doesn't. A day after today (a fast clock, or a find synced
  from one) isn't counted until it comes. A streak badge shown to others is
  worked out from the sectors' times instead (see "Badges others see").

**Missed days are gentle:**

- **One rest day in any seven.** A missed day doesn't end a streak, as long
  as no other day in the six before it was missed. Two missed days in a
  row, or two within a week, end it. It's free and automatic: nothing to buy,
  equip or remember. Rest days don't add to the streak; the streak counts
  days surveyed in the run.
- **Today is never missed.** Until midnight, today is still open, and the
  streak shows as it stood yesterday.
- **Nothing is ever lost.** The page leads with **days surveyed** in total,
  then the current streak, then the longest, which is kept for good. The
  longest is latched in the player's record, so it outlasts finds a redrawn
  map drops.
- **No notifications.** The game sends nothing outside itself, and inside it
  says nothing about a streak "at risk". The day's progress ("Today: 2 of 3
  words") shows only on the Achievements page, for whoever opens it.

The rule is a function of the set of days alone, so every device works out
the same streak from the same notes (forwards for the longest, backwards
from today for the current one; both give the same answer for any day).

## Where it shows

**In the field notes**, which are already the record of your survey:

- **A row under the tally:** the three newest badges at 24 px, how many of
  how many, and the streak ("12 of 39 · 4 days running"), with a dot when
  something's new since you last looked. It opens the page.
- **The Achievements page**, in the notes drawer in the finds' place
  (the page's `notesPage` machine: `finds` or `marks`, on
  `<html data-notes-page>`), with "‹ Field notes" to go back:
  - **Days surveyed** first: the total, the current streak and the longest,
    a strip of the last fortnight (counted, rest day, missed, today), today's
    progress, and the rule in one line.
  - **The badges,** by group, two to a row on a phone: each with its name,
    what to do, and when it was earned or how far along it is. Badges worked
    out from notes made before achievements existed say "From your notes".
  - **The switch** for unlock notes, and how many are secret.
  - **On each earned badge:** Share, which sends "I earned Seven Seas in
    Letterfield: …" and the game's address through the phone's share sheet,
    and, on the survey, **Show** for one the Worker has signed, which puts it
    on your caret (pressed again, it comes off). The one shown is outlined.

Not on the Surveyors drawer: it's about other people, and it only exists on
the shared survey, where solo play has achievements too.

**On the map, for others:** the badge a surveyor shows, on their caret's
hover card, and their card in their caret's menu (see "Profile cards").

## Earning one

- **A note of its own kind,** `achievement`: the badge, its name, and
  "Achievement · what you did", with **See**, which opens the page. It waits
  until the find's bead has landed, and never plays over a supernova: it
  waits for the burst and its own note first. More than two earned at once
  become one note ("3 achievements · Seven Seas, Compass Rose and 1 more").
- **Quietened** with "Notes for new achievements" on the page. The game has
  no settings for kinds of notes yet (`SURVEY.md`'s "Not done yet" wants
  them for emotes); this switch is kept as `letterfield.quiet.v1`, a list of
  quiet kinds, so the same key can hold emotes' and others' when they come,
  and the switches can move together into one place. Quiet means no note and
  no sound; the row's dot still says something's new.
- **A short sound:** two soft bell tones a fifth apart, under a second.
  It goes through the sound effects' bus, so the Effects slider, the mute
  and the supernova's limiter all apply, and it doesn't play while a
  supernova is sounding, or before the player's first tap or key (so a
  backfill's note, which comes as the page opens, is usually silent).
- **Reduced motion:** the badge in the note draws its ring in and settles
  with a little give; with `prefers-reduced-motion` it's simply there, and
  the note appears without moving, as every note does.
- **Backfill.** The first time a player with notes opens a game that has
  achievements, everything their notes have earned is earned at once, each
  dated from the find that earned it, and **one** note says so ("14
  achievements from your field notes so far", with See). Never a note each.
- **From elsewhere.** An achievement whose find came from a linked device or
  another tab is earned quietly: the dot shows, but there's no note. Only a
  find circled in this tab, a supernova seen in the last two minutes, or
  something that just happened here (a hat tipped) plays one.
- **Never over another note.** The note waits while a find's bead is still
  flying, a supernova is going off, or another note is showing (up to about
  20 seconds, then it shows anyway). Hats Off waits for the emote's own note.

## Storage and sync

**On the device:** `letterfield.marks.v1`:

```json
{ "got": { "first-mark": [1763390000000, 1], "compass-rose": [1763391234567, 0] },
  "best": 9, "fresh": ["compass-rose"] }
```

- `got`: each achievement earned, when, and whether it was worked out from
  older notes (1) or earned in play (0).
- `best`: the longest streak ever, for the latch.
- `fresh`: those earned since the page was last open, for the row's dot and
  each badge's "New". This one stays on the device.

Tabs share it as they share finds: each save reads what's stored first and
merges, and a save in another tab is taken in as it happens.

A badge the Worker has signed keeps its signature as a third value,
`[at, from, sig]`. The badge shown is `letterfield.badge.v1`, `[id, sig]`,
and the quiet switch, `letterfield.quiet.v1`, stays on each device, as
sound does.

**Linked devices.** Every achievement that comes from finds and supernovas,
and the streak itself, would follow the player anyway, since the notes do.
The Player adds what doesn't: the latch (an achievement whose finds a
redrawn map dropped), the Company achievements, `best`, when each was first
earned, and badges' signatures. It keeps a `marks` table beside finds and
novas, `(id, body, v)`, and a sync carries `marks: [[id, at, from, sig?]]`
changed since the last version, and `best`, as finds go:

- **Merging can't lose anything.** An achievement is kept once; if two
  devices disagree on when, the earlier wins, "earned in play" wins over
  "from your notes", and a signature, once there, stays. `best` is a row of
  its own (`~best`) that only goes up. Nothing is ever deleted except by
  "Stop syncing everywhere", which takes everything.
- **Checked for shape only** (`cleanMark` in `src/players.js`): an id is
  `[a-z0-9-]{1,32}`, a time is no later than a day past the Worker's clock,
  at most 200 rows. The Player doesn't need the catalog: a made-up id earns
  nothing anyone else sees, since showing one needs the Worker's signature.
- **Earned elsewhere comes quietly:** an achievement that arrives by sync is
  kept with the other device's time and marked new, with no note, since it
  was noted where it was earned.
- **Devices already syncing** when achievements arrived have nothing queued
  for them; their sync state reads as "everything" (`'*'`) until the first
  sync sends it all.
- **The badge shown and the card** go with the other synced settings
  (`badge` and `card` in a link's carry, cleaned by `cleanCarry`), and finds
  keep their receipts (`r`, merged by `mergedFind`). A card that arrives by
  sync takes the place of this device's only if it has every badge this one
  has and begins no later, so an older one never wins.

## Cost

- **Stage 1:** nothing on the server. On the device, working everything out
  again is one pass over the notes, run within a couple of seconds of
  something changing (a cheap signature of the notes is compared every
  1.5 s while the tab is on screen). At the 25,000-find cap it takes about
  16 ms on a laptop; dating what's newly earned is a second pass, only when
  something is. A few hundred finds take well under a millisecond.
- **Syncing:** at most 39 rows a player, written once each, plus `best` when
  it grows. Next to a find's row per word, unmeasurable. No new requests:
  marks ride the syncs that go anyway.
- **Signing finds:** one HMAC per word circled on the survey (microseconds),
  one small message back, and about 25 bytes more in each find, on the
  device and in the Player. Nothing new is stored on the server.
- **Badges:** one request when an achievement is earned, or when the
  surveyor's card is missing a badge they hold, each checking the player's
  signed finds (1,000 signatures is a few milliseconds), limited to 30 an
  hour per address. No storage.
- **Cards:** one HMAC in the sector when a surveyor joins it or their card
  changes, and about 15 bytes more for each surveyor with one in each
  presence message (once a second while anyone moves). No storage beyond the
  socket's attachment, which already holds the badge.

## Badges others see

A badge others can see means something only if it can't be faked, and
everything in `localStorage` can be. The Player's copy of the notes is no
better: it keeps what the devices sent, checked for shape alone.

**Why not a player id on every claim.** The sectors know who circles each
word, but they keep claims under initials only (see "Mine" in `SURVEY.md`).
Storing a player id with every claim, in sectors and the log, would let the
server count each player's words. It would also make a lasting link between
everything a surveyor has charted, held by us, a column in every sector and
in D1, and a table of counts. Too much for a badge.

**Signed finds instead: the proof travels with the find.**

- **A sector signs what it answers** (`receipt()` in `src/survey.js`). When a
  surveyor with a player id circles a word, the sector checks it's on the map
  as always, answers (charted first, or someone else's), and then sends them
  alone `{t: 'signed', k, r}`. `r` is when the sector had it, `f` if they
  charted it first, `z` if it set off a supernova, and an HMAC over those,
  the word, its place and their player id: `mjb3x9k0.fz.Ab3dE_gh1JkL`.
  Nothing is stored.
- **The game keeps r with the find**, and it syncs with it (`cleanFind` and
  `mergedFind` in `src/players.js`).
- **POST /v1/survey/badges** `{token, z, finds, earned, since, held, card}`
  → `{badges: {id: sig}, card}` (`routeBadges` in `src/achievements.js`).
  The Worker checks each find's receipt against the token's player id, works
  the badges out from the signed finds alone with the game's own rules (the
  shared core), and signs each badge for that player. A day is the
  surveyor's date by `z`, their time zone, from the sector's times, so a
  streak shown can't be had by changing the clock. The game asks when an
  achievement is earned or its card is due, and keeps the signatures with
  its achievements, synced. `since`, `held` and `card` are for the card (see
  "Profile cards").
- **Shown:** the player picks one on the Achievements page. It goes in their
  `me` message, `badge: [id, sig]`. Their sector checks the signature
  (`checkBadge`), one HMAC with no lookups, and puts the badge's id in
  presence: `[id, initials, x, y, tags, badge]`. The game draws it on their
  caret's hover card and in their caret's menu (the long press on a phone),
  with its name. It's never listed or ranked.
- **Keys** come from `IP_SALT`, one for each use (`letterfield-find:`,
  `letterfield-badge:`, `letterfield-card:`), so there's no new secret. Without a salt (a local
  `wrangler dev` without one) nothing is signed and nothing believed.

**What signed finds can show:** everything built from words circled on the
survey: notes, charting, territories, themes, words, far afield, Lion's Share,
Last Word and days. Not Cairn (the universe's count is the game's), Witness
and Starfield (being there isn't a claim), or the Company achievements;
those are `u` in the core's catalog. Since no find could ever prove them,
the Worker takes the game's word for them, always: they're small things to
fake, and leaving them off would leave out the friendliest badges. Finds
made alone, or before signing began, carry no receipt.

**Achievements from before signing** count on the game's word: until
`TRUSTED_UNTIL` in `src/achievements.js`, the Worker signs any badge the game
says it has earned, so what surveyors earned before receipts existed can be
shown. After that, only signed finds, and the game's word for the `u` and
`l` ones. A signature, once made, is kept with the achievement and
synced, so a badge signed in that window stays showable. Set it a couple of
weeks after this ships; while only a few people play, that window is the
whole risk.

## Profile cards

Long-press a surveyor's caret on a phone, or right-click it on a computer,
and its menu is their card:

- their initials, a dot of their caret's colour, and the territory they're
  in;
- the badge they show, big, with its name and what it's for;
- "Surveying since Oct 2026", and how many badges;
- every badge the Worker stands behind for them, small, in the catalog's
  order. Tap one and a line under them says what it is. A secret one the
  viewer hasn't found yet stays a question mark;
- the guilds the viewer shares with them;
- the emotes and Mute, as the menu always had.

**Never on it:** their streak or days surveyed. Comparing streaks between
people is what turns a calm streak into a chore (see "Lessons from other
games"), and the log already says who charts the most.

**For everyone, with no switch.** A surveyor's card shows to anyone whose
map shows their caret, just as their initials and caret do.

**How it's made, with nothing stored:**

- The badges endpoint also answers with the surveyor's **card**: which badges
  it signed for them, as the bits of a number over the catalog's order
  (`cardMask` in the core), and the day they began (UTC days since 1970),
  in base 36 and signed for their player id: `5k8jq0.k5x.Ab3dE_gh1JkL`
  (`signCard` in `src/achievements.js`).
- **Which badges:** those it signs now, those the game already holds
  signatures for (`held`), and those on the card the game sends back
  (`card`). So nothing signed is ever lost from a card.
- **When they began:** the earliest of their signed finds, the card they
  send back, and, until `TRUSTED_UNTIL`, the game's own earliest find
  (`since`). So a surveyor who began before signing keeps their real start.
- **The game** keeps it in `letterfield.card.v1`, sends it in its `me`
  message, and asks for a new one when it has none, or when it holds a badge
  the card doesn't have.
- **The sector** checks it (`checkCard`, one HMAC) and adds the part before
  the signature last in presence: `[id, initials, x, y, tags, badge, card]`,
  with `''` for the badge when there's none to show.
- **The catalog only grows at its end:** a card names badges by their place
  in it. The page groups them by their group, so a new achievement can go
  last whatever its group. `worker/test/achievements.test.js` checks the
  first 39 keep their places; there's room for 53.

**Limits:** a card only goes where presence goes, to surveyors in the same
sector, so the Surveyors drawer's rows for people further away don't have
one. Tapping a row flies to that surveyor's caret, though, and their card is
there once you land. Someone on a game from before cards gets the menu as
it was.

## Site-wide later

Every game here shares one origin and the `games.player` token, so a site
page of achievements across games could read each game's `localStorage`
directly, as the survey log reads Letterfield's finds, with no server at
all. It would need:

- a catalog per game in a shared, inlined script (as `telemetry.js` is), with
  each game's checks;
- a small `achievements.js` the build inlines into every game, with the
  badge drawing, the note and the record;
- a key per game (`<game>.marks.v1`), and, for linked devices, a Player that
  isn't Letterfield's (`players.js` already names it by `games.player`).

The other games keep scores, not a history of play, so most of their
achievements would be latched as they happen rather than worked out. That's
a different kind of system, so this is built for Letterfield alone, with
its catalog and checks in one section of the page, ready to move if the
other games ever want it.

## Trying it

- Open `letterfield.html#debug`. `window.__lf.marks` has:
  - `catalog()`, `state()` (what's earned, progress, how many chimes have
    played, whether notes are quiet) and `streak()`;
  - `grant(id)` (earned now, with its note and chime), `grantAll()`
    (quietly), `reset()` (as if achievements were new, so the next check is
    a backfill) and `check()`, for screenshots and tests;
  - `badge(id, state, fraction, big)`, a badge's markup;
  - `card()`, what our card says, and `takeCard(card)`, as a synced one
    arrives.
- To try badges on the survey locally, run `wrangler dev` with an `IP_SALT`
  (in `worker/.dev.vars`), and open the game with `?survey=`: circled words
  come back signed, and earned badges offer Show.
- To try days surveyed, put finds with the times you want in
  `letterfield.finds.v4` and reload; the tests fix the clock with
  Playwright's `page.clock`.

## Tests

`tests/test_letterfield_achievements.py`: earning one from a find (note,
chime, See, New), backfill with one note dated by the finds, several at once
as one note, the streak over local days (rest days, two missed, a day of two
finds, a day ahead of the clock, the clocks going back), the longest latched
after its finds go, quietened notes, sound off, reduced motion, the page in
the notes, the survey's achievements and Hats Off, and a find synced from a
linked device earning quietly. Stage 2's add:

- a find's receipt kept, and proving a badge to show;
- Show sending the badge to the sector;
- achievements from before signing signed on the game's word;
- someone's badge on their hover card and menu;
- our card asked for, sent to the sector and not asked for again;
- someone's card in their caret's menu, a secret badge kept a secret, and
  the menu as it was for someone without a card;
- a card synced from another device, taken only if it has everything ours
  has;
- achievements and the longest streak synced between linked devices;
- sharing a badge.

They use `FakeSurvey(sign=True)`, `FakeBadges` and `FakePlayers` from
`tests/fake_survey.py`.

Every other test's browser starts with achievement notes quietened
(`QUIET_ACHIEVEMENTS` in `tests/conftest.py`), so a first find brings no note
a test isn't about, and answers the fake survey's badges with none.

`worker/test/achievements.test.js` covers the Worker's side:

- that the core matches the game's, word for word;
- receipts, and a sector signing what it answers (with the supernova flag);
- a badge shown in presence only when signed for that player;
- a card in presence only when signed for that player, and a new one taking
  its place;
- the catalog keeping its order, and cards naming every badge;
- the badges endpoint: proven, trusted until `TRUSTED_UNTIL` (and always
  for those no find can prove), nothing from
  others' or tampered finds, days by the surveyor's dates, limits; its card,
  with the day the surveyor began, and what was signed before kept on it.

`worker/test/players.test.js` covers receipts, achievements, the badge and
the card in sync.
