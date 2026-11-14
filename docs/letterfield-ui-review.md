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
| 7–29 | | Open | |

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
- **Decided:** open.

### 8. Emotes are unlabelled icons on a phone

- **a. A label under each icon.** *Recommended.*
- **b. Long-press an icon to see its name first.**
- Either way, one tense in the notes emotes leave.
- **Machines:** none.
- **Decided:** open.

### 9. The word bar: chips look tappable, the count disagrees, the toggle doesn't look like one

- **a. Plain tags for chips you can't tap, and "14 of 21".** *Recommended.*
- **b. A real two-way switch** ("In view / Whole territory").
- **c. A sheet for the whole territory.** Machine: a third sheet on phones
  wants a `sheet` machine (none, notes, people, words), like War's `overlay`.
- **Decided:** open.

### 10. "Charted first" is on nearly every entry

- **a. Mark only the exceptions:** "· charted by ZED". *Recommended.* Pairs
  with 1a.
- **b. A small mark on the dot.**
- **c. A tally only.**
- **Machines:** none.
- **Decided:** open.

### 11. The theme is cut to "Fe…" on a phone

Measured at 375px: the count leaves the theme 22px.

- **a. Drop "charted" from the count.** *Recommended.* 75px: 204 of 225
  theme names fit.
- **b. Drop the "LF" mark.** Alone, 59px.
- **c. Leave the count to the word bar.**
- **Machines:** none.
- **Decided:** open.

### 12. "Origin" means nothing to most players

- **a. "Back to start"**, flying to where this device first started.
  *Recommended.*
- **b. Label it with its grid reference.**
- **c. "My last find".**
- **Machines:** none.
- **Decided:** open.

### 13. Internal words show through

"9 surveyors in 3 sectors"; guild names ending in "Survey".

- **a. Fix the words**, and swap the guild word "Survey" in both copies of
  the list (`letterfield.html`, `worker/src/survey-guild.js`). *Recommended.*
- **b. An "About the survey" fold.**
- **Machines:** none.
- **Decided:** open.

### 14. The tools menu hides its state; the shortcuts are uneven

- **a. "On" / "Off" at the end of each row**, from the settings.
  *Recommended.* Music's one hidden state (waiting for the first tap) can't
  be seen, since opening the menu is itself a tap.
- **b. Switches.**
- **c. Show N in the notes button's tooltip;** consider M muting everything.
- **Machines:** none, unless rows show playback ("Paused, tap to resume"),
  which needs a `music` machine first.
- **Decided:** open.

### 15. Buttons with the same job look different; destructive ones look harmless

- **a. Two button styles, pills for small in-row actions, danger colour on
  destructive choices.** *Recommended.*
- **b. Pills get the normal font and height.**
- **c. Danger colour only on "Leave" and "Every device".**
- **Machines (any option):** the two confirmations are flags outside their
  machines. Add `confirming` to `guild` and `stop` and `stopping` to `pair`.
  `stopping` fixes a confirmed bug: the reply to "Every device" writes into
  whatever card is open (it overwrote the recovery card's heading).
- **Decided:** open.

### 16. Small visual glitches

Card headings at 12.5–13.5px instead of 10px; the hover card under the
docked notes; the arrow split from its compass point; the badges at 0; on a
tablet, open notes over the title.

- **a. Fix each in place.** *Recommended.*
- **b. On a tablet, dock the notes from 768px or shorten the title box.**
- **Machines:** none.
- **Decided:** open.

### 17. Small flow and copy fixes

- Unmuting someone offline: a. a "Muted (3)" row on your page
  (*recommended*); b. mutes expire.
- The share fallback's wrong advice: a. show the link in a box
  (*recommended*); b. put the link in the address bar.
- The survey log link: a. "Survey log and timelapse →" (*recommended*); b.
  an ↗ on rows that leave the game.
- **Machines:** none.
- **Decided:** open.

## Survey log and timelapse

### 18. Sharing the Supernovas page gives out a dead link

`/v/novas/undefined/all`, which the share Worker doesn't serve.

- **a. Give that page no share address.** *Recommended.*
- **b. A Supernovas card in the share Worker.**
- **c. Hide Share there.**
- **Machines:** none.
- **Decided:** open.

### 19. "Live" on views that don't update

- **a. "Live" on the running hour only; "So far" elsewhere.** *Recommended.*
- **b. Reload days and weeks every minute.**
- **c. "Not updating · Try again" when stale.**
- **Machines:** a and c give `log` a move handler (it has none) and set the
  badge there from its state.
- **Decided:** open.

### 20. On a phone, the words come last

- **a. Words first.** *Recommended.*
- **b. Notes next to what they explain.**
- **c. The supernova strip under the chart, ✦ labelled.**
- **Machines:** none.
- **Decided:** open.

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
