# Letterfield UI review

A review of Letterfield (the game, the survey log and the timelapse) for
inconsistencies and places that could confuse players, started 13 November
2026. Each issue gives its options, the one recommended and why, the state
machine work each option needs ("State machines" in AGENTS.md), and what the
owner decided. Issues are decided one at a time; once they all are, the
changes are grouped into pull requests under [Groups](#groups).

Line numbers are as of commit 7bae950 and drift as the files change.

## Decisions so far

| # | Issue | Decision | Status |
|---|---|---|---|
| 1 | A word someone else charted is kept in your notes, or not, by timing | a: keep them all, marked "charted by ZED" | To build |
| 2 | "Done" on a link code can leave this device out of sync | a: keep checking in the background | To build |
| 3 | Sync told three ways, and falsely after a recovery code | Each setting shown once, beside its control; Claude code removed | Built in #101 |
| 4 | "Show me on the list" also stops guild credit | Remove the option: everyone online is listed | To build |
| 5 | Four different counts of who's online | a: one count, in the badge and the list's line | To build |
| 6 | Nothing on a phone's map says the survey is offline | b with d: the title says it; waiting claims kept in storage | To build |
| 7 | Carets and circles only explain themselves to a mouse | b: two lines of copy; long press fixed on phones | Copy to build; long press built in #102 |
| 8 | Emotes are unlabelled icons on a phone | a: a label under each icon | To build |
| 9 | The word bar's chips, count and switch | a with b: plain tags, an honest count, a real switch | To build |
| 10 | "Charted first" on nearly every entry, and messy rows | a with b; cards under day headings, a time on each row, rows on one grid | To build |
| 11 | The theme cut to "Fe…" on a phone | b: "3/113" without "charted", and no LF mark on phones | To build |
| 12 | "Origin" means nothing to most players | b and c: Map centre, and Last find once you have a find | To build |
| 13 | Internal words show through | a: fix the words; 16 random guild words, without "Survey" | To build |
| 14 | The tools menu hides its state; the volume floats | c: a mixer, a slider each for effects and music; zoom in one row | To build |
| 15 | Buttons with the same job look different; risky ones look harmless | a: filled and outlined buttons, red to end or delete; Stop syncing as rows; white inputs | To build |
| 16 | Small visual glitches | a: fix each in place | To build |
| 17 | Small flow and copy fixes | 1a: a Muted list on your page; 2a: the link in a box; 3: a and b, "Survey log and timelapse ↗" and ↗ on links out | To build |
| 18 | Sharing the Supernovas page gives out a dead link | b: a Supernovas card in the share Worker | To build |
| 19 | "Live" on views that don't update | No badge: "So far" on any period still running; the hour still updates quietly | To build |
| 20 | On a phone, the words come last | a with c: words straight after the chart, its supernova note under it | To build |
| 21–29 | | Open | |

## The game

### 1. A word someone else charted is sometimes kept in your notes, sometimes not

Whether it stays depends on when the game learns it was someone else's:
before you circle it (not kept, "Already charted by ZED"), in a race (kept,
"Charted first by ZED"), or later: found offline, a reply lost in a
reconnect, or never sent before a reload (all kept, silently). The notes
promise "Every word you circle".

- **a. Keep them all, marked "charted by ZED".** *Recommended.* Nothing
  leaves your notes once it lands; the credit stays with whoever charted
  first; the word bar still leaves charted words out. Draw them as ZED's
  outline, so filled still means yours. Reverses the 11-11 changelog rule.
- **b. Keep none.** Remove the word once it turns out to be theirs, which
  means removing finds whenever another surveyor's claim arrives for one.
- **c. Keep them all, counted apart.** As a, plus "Charted first 41 · Also
  found 3" in the tally.
- **Machines (any option):** split `claim`'s `answered` into `first`,
  `theirs` and `refused`, and apply the rule once, when a claim reaches
  `theirs`; today five places end a claim and two say nothing. A test runs
  all five endings and expects one outcome.
- **Also:** on the shared survey, leave supernovas to the survey; the
  personal "found every word" check would replay one after a reload.
- **Decided: a.**
- **Since then:** #103 (merged) gave "Already charted by ZED" an "Add to
  notes" button, which adds the word as a find you didn't chart first. When
  1 and 10 are built, those finds take the same "charted by ZED" mark.

### 2. "Done" on a link code can leave this device out of sync, silently

"Done" stops the check for the code being used, but the code still works on
the Worker for ten minutes; if the other device uses it after that, it links
and syncs, and this one never does, and never says so.

- **a. Keep checking in the background** until the code is used or runs
  out, then say "Linked". *Recommended.* Keep the code in storage so a
  reload picks the check up; have the Worker retire an older code when a new
  one is made, as recovery codes already do.
- **b. "Cancel code"**, ending the code on the Worker: a new Worker path, a
  `cancelling` state, and still a's "already used" handling.
- **c. Unlinked devices ask on each visit** whether they've been linked: a
  request from nearly every player for a rare case.
- **Machines:** a: a new `pairCode` (none → making → waiting → used or
  gone), apart from `pair`, which keeps only the card; it replaces the
  `pairCode.gone` flag. b: `cancelling` in `pair`. c: the existing `sync`.
- **Decided: a.**

### 3. Saving a recovery code makes the game claim linked devices you don't have

The foot of the field notes, your row in the Surveyors list and the Devices
heading each worked out "synced or not" on their own, in three wordings, and
after only a recovery code claimed "linked devices". The Worker can't tell
how many devices sync.

- Options considered: a. three-way wording from a new `devices` machine,
  which goes stale without the Worker tracking devices; b. show it once, in
  the Devices heading; c. two-way wording ("Only on this device" / "Backed
  up") everywhere.
- **Decided: each of the player's settings shows once, beside the control
  that changes it.** The foot of the notes only offers feedback; your row
  says "Initials, guild and devices"; the Devices heading is plain; Stop
  syncing says "Your notes and settings are backed up"; the switches are the
  only place for the list and emotes. Also: Claude account syncing, and
  `window.claude` in every game, removed.
- **Built in #101.**

### 4. Turning off "Show me on the list" also stops your words counting for your guild

The switch only says "Off it, your guild and anyone near you still see you";
the cost is said once, in the guild card further up.

- **a. Say it on the switch.** *Recommended.*
- **b. Keep counting a hidden member's words for the guild.** Breaks the
  reason for the rule (SURVEY.md, "Who counts"): the log shows every word
  with its initials and time, so it would tie a hidden member to their guild.
- **c. Ask once** when someone in a guild turns it off. A single yes/no,
  allowed as a boolean.
- **Machines:** none.
- **Decided: remove the option entirely.** Letterfield is an MMO: everyone
  online is on the surveyor list, and every member's words count for their
  guild. Muting (⋯ beside a name, or a caret's menu) still hides a player's
  caret, emotes and come-online notes on all your devices, and "Take
  emotes" still turns emotes off for everyone.
- **Scope:** the game (the switch, `listedOn`, `hide` in the `me` message,
  `listed` in synced and linked settings, the guild card's "While you're
  off the list" clause); the Worker (`hide` and `FLAG_HIDDEN` in
  `survey-social.js`, hidden players' emote limits, and the guild credit
  rule in `survey.js`, with their tests); the log's "Members who keep off
  the surveyor list aren't counted"; SURVEY.md's "Off the list" sections;
  the changelog. No note for players who had it off (only two players so
  far). Makes issue 17's missing unmute for someone offline matter more,
  since mute is now the only tool.

### 5. Four different counts of who's online

The Surveyors button's badge, the survey panel ("2 other surveyors nearby ·
9 online"), the world map ("9 surveyors in 3 sectors") and the list's own
line ("5 other surveyors in the shared world") all count people, in three
phrasings, one with an internal word. The list left out players off the
list, so the badge jumped when it loaded; with issue 4 they agree, apart
from the Atlas's total trailing by a minute or so. "Nearby" counts only the
parts of the map the game is connected to.

- **a. One count, in the fewest places.** *Recommended.* The badge, and the
  list's line while it's open ("8 other surveyors online, nearest first").
  The panel's people line and the world map's note go; the list already
  says how near each person is. Issue 3's rule, applied to the world.
- **b. Keep every place, one wording and one source:** "8 online"
  everywhere, "nearby" relabelled or dropped.
- **c. Keep "near you" as a second number on purpose.**
- **Machines:** none. (The earlier option of always showing the list's count
  on the badge, with a background refresh and a `quiet` state in `who`,
  gains nothing once nobody is hidden.)
- **Decided: a.**

### 6. On a phone, nothing on the map says the survey is offline

Only the panel in the field notes says so; the title just loses its count.
Its wording undersells it: words found offline are claimed when it's back,
but only while the page stays open, since waiting claims live in memory.
The panel also repeats the title (this territory's count) and, on a
computer, the line under "Letterfield" (the world's count). The title only
checks the sector you're in, the panel any sector, so they can disagree.

- **a. A status chip in the top bar.** Needs room the phone's bar doesn't
  have, and a delay so it doesn't flash on every load.
- **b. The title says it, and the panel stops repeating the title.**
  *Recommended.* The title reads "Festivals · 3/113" when live and
  "Festivals · joining…", "· offline" or "· full" otherwise, from the state
  of the sector you're in. The panel drops its territory line and status
  dot, says what's wrong only when it isn't live, and keeps the world's
  count; the line under "Letterfield" goes back to "Endless word search".
- **c. Only honest wording in the panel**, with "as long as this page stays
  open".
- **d. With any: keep words waiting to be charted in storage**, so a reload
  doesn't lose their claim and the panel needn't add a caveat. *Recommended
  with b.*
- **Machines:** a: its delay checks nothing moved. b: none new; the title
  reads the existing `link` and `pass` machines. d: the `claim` machines
  restored from storage on load, with a test (find a word offline, reload,
  come online, expect the claim) that fails today.
- **Decided: b with d.**

### 7. Carets and circles only explain themselves to a mouse

Hovering names who's behind a caret and who charted an outlined word; long
press on a caret opens its menu, but nothing says so, and nothing explains
outlined (someone else's) versus filled (yours).

- **a. Long-press an outlined word to see who charted it**, and mention long
  press. Machine: put pressing in a new `gesture` machine first.
- **b. One line on the intro card.** *Recommended.* Circling an outlined
  word already says who charted it; what's missing is what the marks mean.
- **c. Initials beside carets when zoomed in.** Text on the map, crowding.
- **Decided: b.** The first-visit card says "Coloured bars are other
  surveyors. Outlined words are already charted.", and the Surveyors list's
  foot says how to long-press (or right-click) a surveyor on the map.
- **Found on the owner's phone:** a long press on the map selected text
  instead of opening the caret's menu: the phone's own long press, which
  nothing on the page stops (no `user-select` or `-webkit-touch-callout`
  rules). In Chromium, with real touch events, the menu opens and nothing
  is selected. The fix and a touch test were done in a session and pull
  request of their own, **merged as #102**, so the copy above can rely on
  them.

### 8. Emotes are unlabelled icons on a phone

- **a. A label under each icon.** *Recommended.*
- **b. Long-press an icon to see its name first.**
- Either way, one tense in the notes emotes leave.
- **Machines:** none.
- **Decided: a.** A label under each icon in the list's ⋯ panel and the
  caret's menu, which goes to two rows (4 and 3) for room; "Nice" becomes
  "Thumbs up" (names only; the Worker knows emotes by id); and the notes
  emotes leave all read in the present tense ("KIM waves", "gives you a
  thumbs up", "applauds").

### 9. The word bar: chips look tappable, the count disagrees, the toggle doesn't look like one

- **a. Plain tags for chips you can't tap, and "14 of 21".** *Recommended.*
- **b. A real two-way switch** ("In view / Whole territory").
- **c. A sheet for the whole territory.** Machine: a third sheet on phones
  wants a `sheet` machine (none, notes, people, words), like War's `overlay`.
- **Decided: a with b** (after mockups). Chips you can't tap lose their
  borders and read as plain words; the count says "14 of 21" when the bar
  cuts the list and "9 left" when it doesn't; the switch becomes a pill,
  "In view / Territory", styled like the log's.

### 10. "Charted first" is on nearly every entry

- **a. Mark only the exceptions:** "· charted by ZED". *Recommended.* Pairs
  with 1a.
- **b. A small mark on the dot.**
- **c. A tally only.**
- **Machines:** none.
- **Decided: a with b, and the rows rebuilt** (after four rounds of
  mockups). A ring around the dot marks a word you charted first; a word
  someone else charted first says "charted by ZED" on a second line. The
  owner also found the rows messy (places wrapping, uneven alignment), so:
  - **Grouped by day, then by visit.** A heading for each day (Today,
    Yesterday, then the weekday and date), newest first. Under it, each
    visit to a territory that day is a card: a stripe of the theme's colour
    down its left edge, and the territory and theme at its head. Coming
    back to a territory later that day starts a new card, so the list keeps
    its order in time.
  - **A time on each row,** the clock time ("3:42 PM") instead of how long
    ago.
  - **Every row on one grid:** marker, word with its bearing, time, book,
    share, each centred on the word's line. The marker (dot or ring) has one
    centre; the time column has a fixed width, right-aligned, with
    even-width figures; the card's heading starts where the words start.
    The second line sits under the word without moving anything on the
    first.
  - **The bearing is drawn,** an arrow beside the word, the same size in all
    eight directions; its compass point leaves the text but stays in what a
    screen reader hears ("reads south-west"). This also fixes 16's arrow
    split from its compass point.
  - **The grid reference leaves the rows;** tapping a row still flies there.
    The empty state's "with its territory, grid reference and the bearing it
    reads in" changes to match.
- **When building:** the book and share buttons keep a tap area of at least
  40px, as now, even where they're drawn smaller; a stray keeps its dashed
  dot (ringed if charted first) and says "stray" on the second line, as an
  exception does; a word's meaning opens full width under its row; the
  Supernovas list above takes the same columns (star, place, time, share);
  a theme filter keeps the day headings and cards. On a phone the title box
  hides the grid reference because "the grid reference is in each find's
  notes"; after this it shows nowhere on a phone, which is fine (nothing
  asks a player for one), but that comment changes.

### 11. The theme is cut to "Fe…" on a phone

Measured at 375px: the count ("· 3/113 charted", 106px) leaves the theme
22px, and only 2 of 225 theme names fit, though the theme is the clue to
what's hidden. With 6b the count also gives way to "joining…", "offline" or
"full", so the choice must fit those too ("offline" is as wide as the widest
count, "112/113").

- **a. Drop "charted"** (and "found" when playing alone): "Festivals ·
  3/113". The theme gets 62–75px: 204 of 225 fit at a low count, 167 at a
  three-digit count or offline. Keeps LF. Once 6b drops the panel's
  territory line, nothing on a phone says what's counted.
- **b. a, and no LF mark on phones.** *Recommended.* 99–112px: 220–223 of
  225 fit in every state (only "Weights & Measures" and "Pioneers of
  Science" are cut), and every territory name fits (13 in 2,601 are cut
  today). The mark tells a phone player nothing the tab or the Home Screen
  icon doesn't.
- **c. A percentage:** "Festivals · 2%". 82–95px while live, but "offline"
  needs as much room as a's widest count, and the territory's size is lost.
- Not offered: moving the count out of the title box, which would reverse
  11-11's "always shows how many words of the territory are found" and
  leave 6b's states nowhere to go.
- **Machines:** none.
- **Decided: b** (after mockups). On phones (under 700px) only: the count
  reads "3/113", with "3 of 113 words charted" as its accessible name, and
  the brand box goes, keeping its "Letterfield" heading for screen readers.
  Wider screens keep "Letterfield" and "3/113 charted".

### 12. "Origin" means nothing to most players

It flies to the middle of Menorah Hollow, where the grid references count
from. On the shared survey that's rarely where anyone started (new players
start in the busiest crowd with room, or where a shared link pointed), and
it's the oldest, most charted part of the map.

- **a. "Back to start"**, flying to where this device first started, saved
  on the first visit.
- **b. "Map centre":** the same place, named for what it is.
- **c. "Last find":** your newest find. *Recommended:* after flinging the
  map, following a surveyor or opening an old find, it's where you were
  hunting, and always somewhere you've been.
- **Machines:** none.
- **Decided: b and c** (after mockups). "Map centre" (crosshair, H) is
  always there; "Last find" (a pin, L) joins it, underneath, once you have a
  find, rather than greyed out before one. It flies to your newest find and
  pulses it, as tapping it in the notes does. The rest of the menu's shape
  is taken up with 14.

### 13. Internal words show through

"9 surveyors in 3 sectors" (gone with 5a); one guild name in eight ending in
"Survey", which reads like another survey beside "the shared survey" and
the survey log; "stray" on a find, which nothing explains (the changelog
says "words found by chance"); and 6b's "Festivals · full", which in the
count's place reads as every word charted.

- **a. Fix the words.** *Recommended:* a word or two each, and the text
  then says what it means where it's read.
- **b. An "About the survey" fold** in the notes, explaining the words.
- **Machines:** none.
- **Decided: a**, with more guild words:
  - **Guild names:** "Survey" leaves the third list. Its place (word 6)
    goes to "Lodge", so existing "… Survey" guilds become "… Lodge"
    everywhere at once (a name is kept as each word's number), and eight
    more words join the end, so the third list has 16 like the other two:
    League, Order, Corps, Bureau, Institute, Academy, Alliance, Caravan.
    Names are still drawn at random from the three lists, in both copies
    (`letterfield.html` and `worker/src/survey-guild.js`, kept the same by
    a test). None is longer than "Fellowship", which the guild tests use as
    the longest.
  - **"stray" becomes "found by chance"** under a find in the notes (10's
    second line), in what screen readers hear ("Festivals word found by
    chance") and in a shared find's text.
  - **6b's "full" becomes "crowded"** in the title. The panel's sentence,
    "This part of the map is full right now", stays.
- **When building:** deploy the Worker before the site, or a new guild drawn
  with one of the new words is refused until it does; a page left open from
  before shows such a guild as unknown until it reloads.

### 14. The tools menu hides its state; the shortcuts are uneven

Sound and Music show on or off only by a line through their icon. The music
volume floats in a row of its own, with no visible label and a bare number
("0" with music off), its thumb at 0 reading as a bullet. Nothing says N
opens the notes. Taken up when the owner asked about the menu's structure.

- **a. Tidy:** the rows as they are, "Sound" renamed "Sound effects" (it
  never touched music), "On" or "Off" at the end of each, and the volume
  tucked under Music while it plays.
- **b. Grouped:** zoom in one row, the switches your page in the Surveyors
  drawer already uses, and the volume under Music's switch while it plays.
  *Recommended:* one switch for every setting, and a volume that plainly
  belongs to Music.
- **c. A mixer:** a slider each for effects and music, 0 being off.
- In all three, the notes button's tooltip says "Field notes (N)", like the
  Surveyors button's "(P)".
- **Machines:** none, unless rows show playback ("Paused, tap to resume"),
  which needs a `music` machine first. Music's one hidden state (waiting for
  the first tap) can't be seen, since opening the menu is itself a tap.
- **Decided: c** (option 3 in the mockups). The menu, in three groups:
  - **Zoom,** one row, with − and + side by side.
  - **Map centre and Last find** (see 12).
  - **Effects and Music,** a row each: icon, name, slider. A slider at 0 is
    off; sliding up turns it on at that level; tapping the icon turns it
    off, or back on where it was, and a line goes through the icon while
    it's off. That's today's music button and slider, applied to both.
    Effects (today only supernovas, near and far) gain a volume of their
    own: a gain between them and the output, starting where they play now.
    Music left on from last time still waits for the first tap, which its
    icon then starts rather than switching it off unheard.
  - **Keys:** M and B still switch effects and music, and [ and ] still
    turn the music down and up; on a computer the tooltips say so (the −
    and + buttons' too), and the notes button's says "Field notes (N)".
  - Both levels stay on the device, as sound and music do now (they aren't
    among the settings linked devices share). Screen readers hear "Sound
    effects volume" and "Music volume", with "Off" at 0.

### 15. Buttons with the same job look different; destructive ones look harmless

The drawer's cards mix three styles for their choices with no rule between
them: filled ("Start it", "Done"), outlined ("Cancel" by your initials,
"Stay" on an invite) and small pills in the mono font ("Cancel" naming a
guild, "Stay" leaving one, "Close", "Copy"), which read as tags and stand
about 30px tall against the game's 40px. "Leave", "Every device" (which
deletes the copy kept for syncing and the recovery code) and "Remove it"
look just like the safe choices beside them, and the Stop syncing row isn't
red though Leave guild is.

- **a. Two kinds of button:** filled for a card's main choice and outlined
  for the rest, in the normal font at 40px, and red for one that ends or
  deletes something; pills only for small actions within a row (Change
  beside your initials, Try again on a meaning, the list's Mute and More).
  *Recommended:* one rule to learn, which the buttons outside the drawer
  already follow.
- **b. Pills in the normal font and height**, the main one filled, risky
  ones red.
- **c. Red on the risky ones only.**
- **Machines (any option):** the two confirmations are flags outside their
  machines (`askLeave`, `stopAsk`). Add `confirming` to `guild` and `stop`
  and `stopping` to `pair`. `stopping` fixes a confirmed bug: the reply to
  "Every device" writes into whatever card is open (it overwrote the
  recovery card's heading), with a test that holds the reply back.
- **Decided: a** (after two rounds of mockups), with:
  - **Stop syncing as rows:** "Stop syncing where? Each device keeps its
    notes as they are.", then two rows in a group, "This device" (the
    others keep syncing) and "Every device" in red (also deletes the copy
    kept for syncing, and your recovery code), then "Keep syncing" as an
    outlined button. The rule: a yes or no gets buttons (Leave and Stay); a
    choice between things to do gets rows, as the drawer's other choices
    do.
  - **Text inputs white in light mode** (initials, on the first-visit card
    and your page, and the code entry), so they read as fields to type in
    rather than greyed out. Dark mode's darker well stays as it is.
  - The Stop syncing row turns red, like Leave guild.
- **When building:** in the dark theme a red button's text is dark, since
  that theme's red is a light coral; the code entry's Cancel follows the
  rule too.

### 16. Small visual glitches

- **Card headings** in the devices card and the guild invite are 12.5px and
  13.5px, not 10px: `.pair p` and `.guild-invite p` outrank `.eyebrow`.
- **A caret's hover card** near the docked notes slides under them: it picks
  its side from the window's width (`W`), not the map's (`W - dock`).
- **The notes button's badge** shows 0 before a first find (the Surveyors
  button's already hides at 0).
- **On a tablet** (700 to 1,099px wide), the notes open over the map and
  cover the end of the title box, cutting off the count and shortening the
  theme.
- The arrow split from its compass point is fixed by 10's drawn bearing.

Options:

- **a. Fix each in place.** *Recommended.*
- **b. On a tablet, dock the notes from 768px.** Measured: at 768px the map
  would be 428px wide, shared with the buttons, which squeezes the title as
  on a phone.
- **Machines:** none.
- **Decided: a** (after mockups): a heading rule that outranks the cards'
  paragraphs; the hover card's side chosen from the map's width; no badge
  at 0, so the first find brings it in; and on a tablet, while the notes are
  open over the map, the Letterfield block steps aside and the title box
  ends before the notes, leaving room for the whole territory, theme and
  count.

### 17. Small flow and copy fixes

1. **Unmuting someone offline.** Only the ⋯ beside someone in the list, or
   their caret's menu, unmutes them, and both need them online; once gone,
   they stay muted. After 4, muting is the only tool. The note under the
   switches also says "on this device", though mutes follow you to linked
   devices.
   - a. A Muted row on your page, opening a list. *Recommended.*
   - b. Mutes run out after a while.
   - c. "Unmute everyone".
2. **The share fallback's wrong advice.** When a computer refuses the copy,
   the note says "Copy this page's address instead", but the page's address
   isn't the find's (or supernova's) link.
   - a. Show the link in a box. *Recommended.*
   - b. Put the link in the address bar (only works for the game's own
     links, not the share card address it uses now).
3. **Links that leave the game.** "Survey log: every word charted, hour by
   hour" undersells the log, leaves out the timelapse and wraps on a phone;
   "Our words in the survey log" wears the chevron of rows that open inside
   the drawer, though it goes to another page.
   - a. "Survey log and timelapse". *Recommended,* with b.
   - b. An arrow out (↗) on links that leave the game.
- **Machines:** none; the Muted list opens and closes like a fold.
- **Decided** (after mockups; muting checked as still in the game on
  `main`):
  1. **a.** A Muted row in "On the map" on your page, with the count and
     "Their carets, emotes and notes stay hidden on your devices", replacing
     the note. It opens a list: each muted surveyor's initials, when they
     were muted and an Unmute pill. The game saves the initials when you
     mute someone (it keeps only their id today) and sends them with the
     mutes to linked devices, so the Worker's check of linked settings
     (`worker/src/players.js`) takes them too; anyone muted before that, or
     whose initials haven't reached this device, shows as "A surveyor".
  2. **a.** The note says "Couldn't copy it" and shows the link in a box
     that one tap selects whole, staying until you tap elsewhere; for finds
     and supernovas alike.
  3. **a and b.** "Survey log and timelapse ↗" at the foot of the survey
     panel, and ↗ in place of the chevron on "Our words in the survey log":
     an arrow out on every link that leaves the game.

## Survey log and timelapse

### 18. Sharing the Supernovas page gives out a dead link

The page has no key of its own, so `viewPath()` makes
`/v/novas/undefined/all`, which the share Worker answers with a bare "not
found".

- **a. Give that page no share address**, so Share gives the log's own link.
  *Recommended:* a one-line fix, with b free to follow.
- **b. A Supernovas card in the share Worker.**
- **c. Hide Share there.**
- **Machines:** none.
- **Decided: b.**
  - **Its address:** `/v/novas/all`, or `/v/novas/<period>/<when>/<from>-<to>`
    pinned like the other views', with `d/` for a dark page and no key;
    `viewPath()` and `share/src/view.js` agree, as they must.
  - **Its card:** the share Worker asks the leaderboard Worker (through the
    `LOG` binding) for `/v1/survey/log/novas/<from>/<to>` and draws what the
    page's own picture shows: "Supernovas", the period, the counts
    (Supernovas, Latest, Quickest) and the latest supernovas' last words in
    their themes' colours, with the page's line as its text ("3 territories
    went supernova in Letterfield's shared survey this week, every hidden
    word charted. Latest: …"). The card's page sends people on to
    `/letterfield-log?supernovas` for the same period.
  - Tests in `share/test/` for the address, the card and where it sends
    people, and in the log's tests for the page's share address; AGENTS.md's
    Share cards section names Supernovas among the views with cards.

### 19. "Live" on views that don't update

Any period still running (today, this week, month or year, and the running
hour) wears "Live", but only the running hour reloads, every minute; the
others reload once, when they end, to drop the badge and open the way on.
Five words charted in five minutes left "Today · Live" unchanged. A failed
reload keeps the last copy and tries again, still saying Live.

- **a. "Live" on the running hour only; "So far" elsewhere.** *Recommended,*
  with c.
- **b. Reload days and weeks every minute:** the log's heaviest questions,
  from every open page, for numbers that move slowly.
- **c. "Not updating · Try again" when stale.**
- **Machines:** a and c give `log` a move handler (it has none) and set the
  badge there from its state.
- **Decided: no badge at all** (asked what Live means, the owner chose to
  drop it). A period still running says "So far", the running hour
  included; the running hour still reloads every minute, without saying so,
  and a period that ends while it's open still reloads once to open the way
  on. Nothing promises it's live, so a failed reload keeps retrying quietly
  as it does now, and `log` needs no change.

### 20. On a phone, the words come last

Four top-list cards (surveyors, guilds, territories, themes: about 1,150px)
stand between the chart and the first word, 2.7 screens down. The supernova
note sits between them and the words, far from the chart's unexplained ✦,
and one paragraph at the foot explains seven things.

- **a. Words first.** *Recommended,* with c.
- **b. Notes next to what they explain.**
- **c. The supernova strip under the chart, ✦ labelled.**
- **Machines:** none.
- **Decided: a with c** (after a mockup). On a phone (under 640px) the
  words follow the chart, and the top lists come after them under a "Top
  lists" heading, with a "Top lists ↓" link under the chart to jump there;
  on a computer, where the cards sit two abreast, the order stays. The
  supernova note sits right under the chart and starts with the chart's ✦,
  so the mark explains itself. The log's word rows wrap as the field notes'
  did before 10; that's taken up with 28.

### 21. The hour view uses a day's controls

- **a. Show the hour between the arrows.** *Recommended.*
- **b. Disable ‹ at the log's first day.** Machine: a new `span` (asking,
  known, failed), since the first day isn't known until the log answers.
- **c. Collapse months before the log.** The same `span`.
- **Decided:** open.

### 22. A new guild's page says "No such guild"

- **a. "Nothing charted yet", with the name passed in the link.**
  *Recommended.*
- **b. The timelapse says "No words from this guild yet".** Machine: a new
  `follow` (off, asking, on, unknown, failed).
- **c. Hide the game's link until the guild has words.**
- **Decided:** open.

### 23. Moving between the game, log and timelapse loses your place

- **a. Go back in history when you came from the other page.**
  *Recommended.*
- **b. More links.**
- **c. One way out of a guild's view.**
- **Machines:** none.
- **Decided:** open.

### 24. Numbers nobody explains

- **a. Make the third tile fit the view** (world percentage on All time
  only, first). *Recommended.*
- **b. A one-line key.**
- **c. The UTC note on every card.**
- **Machines:** none.
- **Decided:** open.

### 25. One idea, many names, across the three pages

- **a. One term per idea, in AGENTS.md's Letterfield section.**
  *Recommended.*
- **b. Fix the worst now.**
- **Machines:** none.
- **Decided:** open.

### 26. The timelapse's territory card uses the theme as its name

- **a. "A Festivals territory" until the name arrives.** *Recommended.*
- **b. Two lines, "By Nov 5" and "Now".** Machine: a `chip` machine, since
  loading and failure would read differently.
- **c. Send names with the replay.**
- **Decided:** open.

### 27. Timelapse status is faint or wrong

- **a. A disabled style for pills, singular labels, the guild in the
  video.** *Recommended.*
- **b. "Waiting for Nov 13…" over the map**, in the existing `tl` handling
  of `waiting`, keeping Pause.
- **c. End at the last word, drive the video's bar, time out.** The existing
  `rec`.
- **Decided:** open.

### 28. Cramped at 375px, with small tap targets

- **a. "3–4 PM", and rank labels that wrap.** *Recommended*, with b's 44px
  minimum for buttons.
- **b. A 44px minimum; a first tap on a cell shows its value.**
- **Machines:** none.
- **Decided:** open.

### 29. Shared links show a half-drawn page

- **a. Draw the title and tabs first**, while `log` is loading.
  *Recommended.*
- **b. Use the log's start date until the answer arrives.** Needs 21's
  `span`.
- **Decided:** open.

## Groups

Once every issue is decided, the changes are grouped here into pull
requests, each one a coherent change with its own tests.
