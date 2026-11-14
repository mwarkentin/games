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
| 13 | Internal words show through | a: fix the words ("bonus word" for "stray"); 16 random guild words, without "Survey" | To build |
| 14 | The tools menu hides its state; the volume floats | c: a mixer, a slider each for effects and music; zoom in one row | To build |
| 15 | Buttons with the same job look different; risky ones look harmless | a: filled and outlined buttons, red to end or delete; Stop syncing as rows; white inputs | To build |
| 16 | Small visual glitches | a: fix each in place | To build |
| 17 | Small flow and copy fixes | 1a: a Muted list on your page; 2a: the link in a box; 3: a and b, "Survey log and timelapse ↗" and ↗ on links out | To build |
| 18 | Sharing the Supernovas page gives out a dead link | b: a Supernovas card in the share Worker | To build |
| 19 | "Live" on views that don't update | No badge: "So far" on any period still running; the hour still updates quietly | To build |
| 20 | On a phone, the words come last | a with c: words straight after the chart, its supernova note under it | To build |
| 21 | The hour view uses a day's controls; the log's header | A new header (a way back, tabs for what's listed, periods as tabs, the card's title as navigator); b with d: ‹ stops at the first word | To build |
| 22 | A new guild's page says "No such guild" | a plus c: named, "hasn't charted a word yet"; its Timelapse link waits for a first word | To build |
| 23 | Moving between the game, log and timelapse loses your place | a: a link back to the page you came from steps back in history | To build |
| 24 | Numbers nobody explains | a with c: the third tile fits the view; the UTC note under the Top lists heading | To build |
| 25 | One idea, many names, across the three pages | a: a glossary in AGENTS.md; "members" for a guild's people, "the universe" for the shared world | To build |
| 26 | The timelapse's territory card uses the theme as its name | a: "A Festivals territory" until the name comes, and the replay's date for "by then" | To build |
| 27 | Timelapse status is faint or wrong | a with b: disabled pills, singular labels, the guild named; "Waiting for Nov 13…" over the map | To build |
| 28 | Cramped at 375px, with small tap targets | a with b: "3–4 PM", names that wrap, rows on 10's grid, 40px buttons; a first tap on a bar shows its value | To build |
| 29 | Shared links show a half-drawn page | a: draw what the address says first, with placeholders holding the space of what loads | To build |

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
  40px, as now, even where they're drawn smaller; a bonus word (13's name
  for a stray) keeps its dashed dot (ringed if charted first) and says
  "bonus word" on the second line, as an
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
  - **"stray" becomes "bonus word"** (first decided as "found by chance",
    renamed while deciding 24, the usual name in word games for a real word
    that isn't on the list): under a find in the notes (10's second line),
    in the survey log's rows ("bonus circuitry word"), in what screen
    readers hear ("Bonus festivals word") and in a shared find's text
    ("LANTERN, a bonus festivals word,").
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
- **Decided: a, within a new header for the log**, which the owner asked
  for while deciding 20 (three options mocked; the second chosen, then
  refined). Today the header stacks the title, three links of different
  kinds (Supernovas, a list in the log; Timelapse, another page; the way
  back, last), three rows of controls and the date twice, with the first
  numbers 468px down on a phone. The new one, on every width:
  - **"← Letterfield"** above the title, the way back; the eyebrow
    "Letterfield · the shared survey" goes.
  - **"Survey log"** with **"▶ Timelapse"** beside it, the one link to
    another page, and a one-line intro: "Every word charted first. Tap a
    word to fly to it, or a name to see all of theirs."
  - **A tab bar across the full width for what's listed:** Everyone and
    Mine share one pill (two thirds), and "✦ Supernovas" has its own after
    a gap, set apart as a different kind of list. On Supernovas, Everyone
    and Mine show unselected, and the Supernovas card goes: its
    explanation becomes the period card's caption ("Every territory gone
    supernova since the first word, on Oct 22, 2026").
  - **The period as plain tabs on a rule** (Day, Week, Month, Year, All
    time), so the two rows don't read as twins: the pills choose what,
    the tabs when.
  - **No date row:** the period card's title is the navigator, "‹ TODAY ›",
    with the full date and "Pick a day" (week, month, year) under it, which
    opens the date picker; All time has no arrows. An hour shows "‹ 3:00 PM
    – 4:00 PM ›" with "Friday, November 13 · ↑ The whole day", which is a.
    A surveyor's, theme's, territory's or guild's page keeps its card,
    without the intro, then the periods and the navigator.
  - On a phone, the first numbers come 336px down instead of 468px.
  - **Machines:** none new; the tabs show what the address already says
    (Mine, `?supernovas`), and nothing waiting moves them.
- **And b with d**, for the ‹ that went back before the first word (into
  "Nobody charted a word this day", period after period): ‹ stops at the
  period holding the first word, as › stops at the present. The first
  word's day is only known once the log answers (it can come before the
  day the log began, since sectors sent older words when they first woke),
  so a new `span` machine (asking, known, failed) keeps ‹ working until
  it's known, and if the answer fails. An empty period before the first
  word, reached by a link, says "The survey log starts on Oct 22, 2026"
  with a link to that day, once the answer is in. The year chart keeps its
  twelve months (c not taken). `span` joins the machines table in
  AGENTS.md.

### 22. A new guild's page says "No such guild"

"Our words in the survey log" shows from the moment a guild is started, but
the log only learns a guild's name from its members' words, so until one is
charted the page says "No such guild". The timelapse, following such a
guild, quietly plays everyone's words.

- **a. "Nothing charted yet", with the name passed in the link.**
  *Recommended,* with c's part on the guild's page.
- **b. The timelapse says "No words from this guild yet".** Machine: a new
  `follow` (off, asking, on, unknown, failed).
- **c. Hide the game's link until the guild has words** (in the game, a new
  question to the log on every visit to your page; on the guild's log page,
  which knows, only its Timelapse link).
- **Decided: a plus c's part on the guild's page.** The game's link carries
  the guild's name as its three word numbers (checked in range by the log,
  so a doctored link can only show a name made of guild words), and the
  page says "The Cobalt Compass Society hasn't charted a word yet. Its
  members' words show here as they chart them." On that page the header's
  Timelapse link waits for the guild's first word. The game's own link
  stays, since it now lands on a page that names the guild. No new machine.

### 23. Moving between the game, log and timelapse loses your place

The links between the three pages always open a fresh copy: log (a past
week, a surveyor's page, scrolled) → a word on the map → the game's link
back opens today's log at the top; a guild's page → its timelapse → "← Log"
opens today's log; the timelapse → "See it in the log" → "▶ Timelapse"
starts the replay over. The browser's back button gets it right, but a Home
Screen app on an iPhone has none.

- **a. Go back in history when you came from the other page.**
  *Recommended:* the log's address holds its view, so a step back returns
  to it, scroll and all, in the Home Screen app too.
- **b. More links** that carry your place.
- **c. One way out of a guild's view.**
- **Machines:** none.
- **Decided: a.** Each page notes in the tab's session storage the pages
  of the three it came through. A link whose page is the one just before
  in the tab's history steps back instead (a general link, like "Survey
  log and timelapse", matches any view of the log; a specific one, like a
  guild's row, only that view), and anything else stays a normal link.

### 24. Numbers nobody explains

A day shows "Words charted 79" beside "In the shared world 72" with nothing
to say why they differ (the 7 are bonus words, which don't count towards
the world), and "<0.01% of its hidden words", a share that will read <0.01%
on any day or week for a long time. For a week or longer the top lists
count whole days in UTC, which only the first card says.

- **a. Make the third tile fit the view** (world percentage on All time
  only, first). *Recommended,* with c.
- **b. A one-line key.**
- **c. The UTC note on every card**, or once where it covers them all.
- **Machines:** none.
- **Decided: a with c** (after a mockup):
  - On a day, week, month or year the third tile is "Hidden words · 72 ·
    plus 7 bonus words", which explains the first tile's count; on All
    time it's "Universe · 0.09% charted · 1,030 of its hidden words" (25's
    name for the shared world),
    leading with the share where it means something. The bonus words are
    counted from the log's own data, with the rare word beyond the shared
    map counted in the same line.
  - The UTC note leaves the first card for the "Top lists" heading that 20
    adds ("Counted in whole days in UTC, Nov 9 – 13, 2026"), so it covers
    all four cards; the heading shows on every width, not only on a phone.

### 25. One idea, many names, across the three pages

"The shared survey" and "the survey"; "the shared world", "the shared map"
and "World"; "surveyor" and now and then "player"; a guild's "mates" in the
game and "members" in its counts and the log; "field notes", "your notes"
and "finds"; "hidden words" and plain "words"; "stray"; "timelapse" and
"replay".

- **a. One term per idea, in AGENTS.md's Letterfield section.**
  *Recommended:* agents write most of the game's text, and AGENTS.md is what
  every one of them reads first.
- **b. Fix the worst now.**
- **Machines:** none.
- **Decided: a.** A short glossary in AGENTS.md's Letterfield section, one
  name per idea and the words to avoid, and the three pages' text brought
  in line as each group is built:
  - **the shared survey** for playing together ("the survey" once that's
    clear); **surveyor** for someone playing it, never "player".
  - **the universe** for the area charted together (the owner's name,
    replacing "the shared world", "the shared map" and "World"): "Universe
    map" for the world map in the notes, "Universe: 48,211 of 1,119,752
    charted" in the survey panel, "Universe · 0.09% charted" for 24's All
    time tile, "word 1,234 of 1,119,752 in the universe" in a shared find.
    It suits the supernovas, and astronomers chart and survey the sky too.
    The map goes on past the universe's edge, where the survey doesn't
    reach, but at 4,800 cells a side nobody gets there; if someone does,
    the game can say they've left it.
  - **members** for a guild's people, never "mates": "Invite a mate"
    becomes "Invite someone", and "mates first on the list" becomes
    "members first on the list".
  - **field notes** for your list, and a **find** for a word in it.
  - **hidden words** for a territory's words, and **bonus words** for ones
    found by chance (13, 24).
  - **timelapse**, never "replay"; **territory** (never "region"),
    **theme**; **charted**, **charted first** and "charted by ZED" on the
    survey, **found** alone; **initials**, which **sign** your words.
  - The names this review settled: Map centre, Last find, crowded, So far,
    Top lists, and the guild words.

### 26. The timelapse's territory card uses the theme as its name

Until the log answers with the territory's name, the card shows its theme in
the name's place ("FESTIVALS"), and keeps it there if the answer fails. Its
line mixes two moments: "12 hidden words charted by then · 34 of 113 now".

- **a. "A Festivals territory" until the name arrives.** *Recommended.*
- **b. Two lines, "By Nov 5" and "Now".** Machine: a `chip` machine, since
  loading and failure would read differently.
- **c. Send names with the replay** (names come from the world generator,
  which the timelapse doesn't have, so the Worker would send them).
- **Decided: a**, with the replay's date in place of "by then": "12 hidden
  words charted by Nov 5 · 34 of 113 now". No machine; the card already
  keeps only the newest answer by counting its requests.

### 27. Timelapse status is faint or wrong

While loading, the Play button greys out but the speed pills and "Save
video" look ready and do nothing; the counters say "1 supernovas"; following
a guild, the third counter reads "111 their words", and a video saved then
shows the guild's colour without its name; and when the replay catches up
with days still loading, the map stops under a Pause button with only a
small "Loading…" under the bar.

- **a. A disabled style for pills, singular labels, the guild in the
  video.** *Recommended,* with b.
- **b. "Waiting for Nov 13…" over the map**, in the existing `tl` handling
  of `waiting`, keeping Pause.
- **c. End at the last word, drive the video's bar, time out.** The existing
  `rec`. On a second look the recording already stops at the last word and
  pauses while the tab is hidden; no stall was found.
- **Decided: a with b.** The pills look disabled while they are; labels
  are singular for one ("1 supernova", "1 territory"); "their words"
  becomes "by the guild"; a video saved while following a guild names it
  in its frames, in its colour; and while `tl` is `waiting`, "Waiting for
  Nov 13…" shows over the map, with Pause kept since it carries on by
  itself. No new machine.

### 28. Cramped at 375px, with small tap targets

Hour headings ("3:00 PM – 4:00 PM") wrap, with a 24px "Minute by minute"
button; each word row's second line runs place, grid reference, bearing and
theme together, as the notes did before 10; top-list names are cut short
("Emerald Theodol…"); and a day's 24 bars share about 300px, each about
12px to tap, opening its hour with no number shown first.

- **a. "3–4 PM", and rank labels that wrap.** *Recommended*, with b.
- **b. A 44px minimum; a first tap on a cell shows its value.**
- **Machines:** none.
- **Decided: a with b** (after a mockup):
  - Hour headings read "3–4 PM" ("11 AM – 12 PM" across noon), on one
    line; top-list names wrap rather than cut.
  - Word rows take 10's grid: marker, word with its drawn bearing, time
    and initials, and a second line of place and theme ("bonus circuitry
    word" for a bonus word); the grid reference goes, as in the notes.
  - Buttons are at least 40px tall, like the game's (15), and rows at
    least 44px.
  - A first tap on a chart bar, or a calendar's day, shows its value ("11
    AM – 12 PM · 13 words · Tap again to open") and a second opens it; on
    a computer, hovering shows it and a click opens at once. At most one
    is picked at a time, so no machine.

### 29. Shared links show a half-drawn page

A shared link to a guild's page shows, until the log answers, no period
selected, a blank date, "…" as the card's title and no guild card; then it
all arrives at once.

- **a. Draw the title and tabs first**, while `log` is loading.
  *Recommended.*
- **b. Use the log's start date until the answer arrives.** Needs 21's
  `span`. On a second look All time already does ("Since the log began on
  Nov 6" until it knows), and 21's b with d covers the first word's edge.
- **Decided: a**, with placeholders (the owner's addition). Everything the
  address says is drawn at once: the period tab, the navigator's title and
  date, and the view's card with what's known (a surveyor's initials, a
  theme's name and colour, a territory, a guild's name from the link, as
  22 has the game send it and the share card's page can pass on; "A guild"
  until known). Whatever waits on the log (the tiles, the chart, the top
  lists, the words) has a placeholder ahead of time the size of what will
  fill it, so nothing jumps as it loads in: still blocks under reduced
  motion, a gentle pulse otherwise. No new machine: `log`'s `loading`
  covers the wait. The rule is worth a line in AGENTS.md's rules for every
  page that loads something.

## Groups

Every issue is decided. The changes are grouped into pull requests, each a
coherent change with its own tests and changelog lines, numbered in the
order they should land. `letterfield.html` is one big file, so the game's
groups go one at a time (2 to 7), as do the log's (8 to 10); the timelapse
(11) can go alongside either, and 12, which touches all three pages, goes
last. A group that changes the Worker deploys it before the site.

| # | Group | Issues | Where |
|---|---|---|---|
| 1 | The glossary | 25 | AGENTS.md |
| 2 | Every find kept, the field notes rebuilt | 1, 6d, 10, 16 (badge), 17.2 | game |
| 3 | The title box and the survey panel | 5, 6b, 11, 13 ("crowded"), 16 (tablet) | game |
| 4 | Map controls | 7 (first-visit card), 9, 12, 14, 16 (hover card) | game |
| 5 | The Surveyors drawer's look and guilds | 7 (list foot), 8, 13 (guild words), 15, 16 (headings) | game, Worker |
| 6 | Everyone listed, and a way back from a mute | 4, 17.1 | game, Worker, log |
| 7 | Linking devices | 2, 15 (`pair`'s `stop` and `stopping`) | game, Worker |
| 8 | The log's header and loading | 19, 21, 22, 29 | log, game, share Worker |
| 9 | The log's body | 13 ("bonus word"), 20, 24, 28 | log |
| 10 | A Supernovas share card | 18 | share Worker, log |
| 11 | The timelapse | 26, 27 | timelapse |
| 12 | Between the pages | 17.3, 23 | game, log, timelapse |

1. **The glossary.** 25's names in AGENTS.md's Letterfield section, first,
   so every later group's text follows it; its copy pass happens in each
   group as it touches text, with 12 sweeping what's left. Also the rule
   from 29: anything a page loads gets a placeholder its own size.
2. **Every find kept, the field notes rebuilt.** `claim`'s `answered`
   split into `first`, `theirs` and `refused`, with every way a claim ends
   leading to one outcome (1), and claims still waiting kept in storage and
   restored on load (6d), both in the same machine; the notes' rows on one
   grid under day headings, with rings, "charted by ZED" (#103's added
   finds included), times and drawn bearings (10); no badge at 0 (16); the
   share fallback's link box (17.2).
3. **The title box and the survey panel.** The title saying "joining…",
   "offline" or "crowded" from the sector's state (6b, 13), "3/113" without
   "charted" and no LF on a phone (11), the tablet title stepping aside for
   the notes (16); one count of who's online, the panel's people line and
   the world map's note gone (5), and the panel's "Universe" names (25).
4. **Map controls.** The tools menu in three groups with the effects and
   music mixer (14), Map centre and Last find (12), the word bar's tags,
   count and switch (9), the hover card on the map's side (16) and the
   first-visit card's two lines (7).
5. **The Surveyors drawer's look and guilds.** Filled, outlined and red
   buttons, white inputs and the Stop syncing rows (15), with `guild`'s
   `confirming`; card headings at 10px (16); emote labels (8); the list
   foot's long-press line (7); "members" in its text (25); the guild words
   without "Survey" (13), in the game and the Worker.
6. **Everyone listed, and a way back from a mute.** The list switch gone,
   with `hide`, `FLAG_HIDDEN` and the guild credit rule in the Worker, the
   log's "off the surveyor list" line and SURVEY.md (4); the Muted list on
   your page, with initials saved and carried to linked devices through
   the Worker's check (17.1).
7. **Linking devices.** `pairCode`, so a code is watched until it's used or
   runs out, with the Worker retiring an older code (2); `pair`'s `stop` and
   `stopping`, fixing the reply that wrote into the wrong card, with a test
   that holds it back (15).
8. **The log's header and loading.** The new header, its tabs, the periods
   as tabs and the card's title as navigator, `span` and the ‹ that stops at
   the first word (21); no Live badge (19); everything the address says
   drawn first, with placeholders (29); a new guild's page named, with its
   Timelapse link waiting for a first word, the game's link and the share
   card's page carrying the name (22).
9. **The log's body.** Words first on a phone, the supernova note under the
   chart and the Top lists heading (20); the third tile fitted to the view
   and the UTC note under that heading (24); short hour headings, names that
   wrap, rows on 10's grid, 40px buttons and a first tap that shows a bar's
   value (28); "bonus word" in the rows (13).
10. **A Supernovas share card.** Its address, card and page in the share
    Worker, and `viewPath()` to match (18).
11. **The timelapse.** The territory card's placeholder and date (26);
    disabled pills, singular labels, the guild named in a video and
    "Waiting for Nov 13…" (27).
12. **Between the pages.** A link back to the page you came from steps back
    in history (23); "Survey log and timelapse ↗" and an arrow on every link
    out (17.3); and the glossary's sweep of whatever text is left.
