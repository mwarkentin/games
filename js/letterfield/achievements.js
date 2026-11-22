// Letterfield's achievements (see worker/ACHIEVEMENTS.md), for everything
// that works them out or shows them: the game (letterfield.html) for its own
// field notes, the leaderboard Worker (worker/src/achievements.js) for the
// signed finds a badge shown to others needs, and the share Worker for a
// badge's card. One file, so they always agree.
//
// No DOM: node:test imports it as it is (worker/test/achievements.test.js).

import { NT, THEMES } from './world.js';

// Territories from the map centre to the universe's edge, which runs from −48
// to 51: the survey's 12 sectors of 4 territories each way (SURVEY_AREA in
// letterfield.html and AREA in worker/src/survey.js; the tests check).
export const UNIVERSE_EDGE = 48;

// What each achievement asks for, and one pass over a surveyor's finds and
// supernovas, in time order, that says how far along each is. The game works its own notes out with it; the
// Worker works out the signed finds a badge shown to others needs. `world`
// gives the map: THEMES, territoryTotal(rx, ry), RC (cells a territory),
// UNIVERSE_EDGE (territories to the universe's edge) and dayOf(t), the day
// a time falls on where the surveyor is, as a whole number.
export function achievementsCore(world) {
  const { THEMES, territoryTotal, RC, UNIVERSE_EDGE, dayOf } = world;
  const NT = THEMES.length;
  const STREAK_MIN = 3;  // finds that make a day count
  const REST_GAP = 7;    // a missed day keeps a streak going if no other was missed in the six before it
  const fdiv = (a, b) => Math.floor(a / b);
  // Themes that go together, by name (-1 for a name the map no longer has).
  const themeIds = (names) => names.map((n) => THEMES.findIndex((t) => t.name === n));
  const BIRDS = themeIds(['Garden Birds', 'Birds of Prey', 'Aviary', 'Waterbirds', 'Birdwatching']);
  const SEAS = themeIds(['Deep Sea', 'Coral Reef', 'Whale Watch', 'Rock Pool', 'Seaside', 'Harbour', 'Sailing']);
  const SKIES = themeIds(['Space', 'Solar System', 'Night Sky', 'Sci-Fi']);
  const NATIONS = themeIds(['India', 'Ireland', 'Mexico', 'France', 'Japan', 'Canada', 'Spain', 'Italy', 'Scotland']);
  // How far along the tally T is: [have, need, what it's about ({rx, ry} or {th}) or null].
  const pair = (have, need, of = null) => [Math.min(have, need), need, of];
  const allOf = (ids) => (T) => pair(ids.filter((i) => T.themes.has(i)).length, ids.length);
  // [id, group, flags, check]. Flags: s, on the shared survey only; h, secret
  // until earned; l, latched when it happens, as nothing in the notes says;
  // u, unproven: signed finds can't prove it, so the game's word is taken
  // for it (see "Badges others see").
  const CATALOG = [
    ['first-mark', 'notes', '', (T) => pair(T.finds, 1)],
    ['field-book', 'notes', '', (T) => pair(T.finds, 100)],
    ['bound-volume', 'notes', '', (T) => pair(T.finds, 1000)],
    ['great-atlas', 'notes', '', (T) => pair(T.finds, 5000)],
    ['first-light', 'charting', 's', (T) => pair(T.first, 1)],
    ['trailblazer', 'charting', 's', (T) => pair(T.first, 100)],
    ['pathfinder', 'charting', 's', (T) => pair(T.first, 1000)],
    ['cairn', 'charting', 'shu', (T) => pair(T.cairn, 1)],
    ['wanderer', 'territories', '', (T) => pair(T.terr.size, 10)],
    ['gazetteer', 'territories', '', (T) => pair(T.terr.size, 50)],
    ['every-last-word', 'territories', '', (T) => (T.full ? pair(1, 1) : T.near ? pair(T.near.n, T.near.of, T.near) : pair(0, 1))],
    ['five-sheets', 'territories', '', (T) => pair(T.full, 5)],
    ['lions-share', 'territories', 's', (T) => (T.lion ? pair(1, 1) : T.lionNear ? pair(T.lionNear.n, T.lionNear.of, T.lionNear) : pair(0, 1))],
    ['map-key', 'themes', '', (T) => pair(T.themes.size, 25)],
    ['full-legend', 'themes', '', (T) => pair(T.themes.size, NT)],
    ['lexicographer', 'themes', '', (T) => (T.lex ? pair(T.lex.n, THEMES[T.lex.th].words.length, T.lex) : pair(0, 1))],
    ['dawn-chorus', 'themes', '', allOf(BIRDS)],
    ['seven-seas', 'themes', '', allOf(SEAS)],
    ['star-chart', 'themes', '', allOf(SKIES)],
    ['passport', 'themes', '', allOf(NATIONS)],
    ['happy-accident', 'words', '', (T) => pair(T.bonus, 1)],
    ['serendipity', 'words', '', (T) => pair(T.bonus, 25)],
    ['long-measure', 'words', '', (T) => pair(T.longest >= 10 ? 1 : 0, 1)],
    ['compass-rose', 'words', '', (T) => pair(T.dirs.size, 8)],
    ['mirror-image', 'words', 'h', (T) => pair(T.mirror, 1)],
    ['self-portrait', 'words', 'h', (T) => pair(T.surveyor, 1)],
    ['over-the-horizon', 'far', '', (T) => pair(T.far, 10)],
    ['edge-of-the-universe', 'far', '', (T) => pair(T.far, UNIVERSE_EDGE)],
    ['here-be-dragons', 'far', 'hu', (T) => pair(T.far, 250)],  // u: 250 out is in the wilds, off the survey, where no find is signed
    ['witness', 'novas', 'u', (T) => pair(T.novas, 1)],
    ['starfield', 'novas', 'u', (T) => pair(T.novas, 10)],
    ['last-word', 'novas', 's', (T) => pair(T.lastWord, 1)],
    ['seven-days', 'days', '', (T) => pair(T.best, 7)],
    ['lunar-month', 'days', '', (T) => pair(T.best, 28)],
    ['thirty-days', 'days', '', (T) => pair(T.days, 30)],
    ['full-circle', 'days', '', (T) => pair(T.span, 365)],
    ['fellowship', 'company', 'slu', null],
    ['two-places', 'company', 'slu', null],
    ['hats-off', 'company', 'shlu', null],
    ['number-of-the-beast', 'notes', 'h', (T) => pair(T.finds, 666)],
  ];
  const CHECK = new Map(CATALOG.map(([id, , , check]) => [id, check]));
  // The ones signed finds can prove: all but l and u.
  const PROVABLE = new Set(CATALOG.filter(([, , flags]) => !/[lu]/.test(flags)).map(([id]) => id));
  // A surveyor's card names their badges by their places in CATALOG, as the
  // bits of a number (see "Profile cards"). So a new achievement goes at the
  // end of CATALOG, never between (the page groups them by their group), and
  // there's room for 53.
  const cardMask = (ids) => CATALOG.reduce((m, [id], i) => (ids.has(id) ? m + 2 ** i : m), 0);
  const cardIds = (mask) => CATALOG.filter((_, i) => Math.floor(mask / 2 ** i) % 2 === 1).map(([id]) => id);

  // Runs of counted days, forwards: a missed day is a rest day if no other was
  // missed in the six before it; otherwise the run starts again after the
  // earlier one. So any day's streak is the longest run back from it that holds
  // at most one missed day in any seven. Today is never missed: it's open
  // until it ends. `counted` is ascending; `reach` says when the run first
  // reached each length asked about.
  function runsOf(counted, today, reach = []) {
    let run = [], prev = null, lastMiss = null, best = 0;
    const at = {};
    const miss = (m) => {
      if (lastMiss !== null && m - lastMiss < REST_GAP) run = run.filter((x) => x > lastMiss);
      lastMiss = m;
    };
    for (const d of counted) {
      if (d > today) break;
      if (prev !== null) for (let m = prev + 1; m < d; m++) miss(m);
      run.push(d); prev = d;
      if (run.length > best) best = run.length;
      for (const k of reach) if (!(k in at) && run.length >= k) at[k] = d;
    }
    if (prev !== null) for (let m = prev + 1; m < today; m++) miss(m);
    return { run, best, at };
  }

  const wordThemes = new Map();  // word → the themes whose lists have it
  THEMES.forEach((t, i) => t.words.forEach((w) => { const l = wordThemes.get(w); if (l) l.push(i); else wordThemes.set(w, [i]); }));
  const isPalindrome = (w) => w.length >= 3 && w === [...w].reverse().join('');

  // The tally of finds ({w, x, y, d, t, s, f, n, th}: s a bonus word, f charted
  // first, n where it came in the universe's count, th its theme) and
  // supernovas seen ({t, mine, solo}), as of `now`. Given `want`, ids to date,
  // it also says when each was first earned and by what (`reached`): checking
  // after every find is most of the work, so it's done only when asked. Days
  // are dated from the days themselves.
  function tally(finds, novas, now, want = []) {
    const T = { finds: 0, first: 0, cairn: 0, bonus: 0, longest: 0, mirror: 0, surveyor: 0, far: 0, dirs: new Set(), themes: new Set(),
      terr: new Map(), full: 0, near: null, lion: 0, lionNear: null, lex: null, lexWords: new Map(), novas: 0, lastWord: 0, best: 0, days: 0, span: 0, current: 0, today: 0 };
    const reached = {};  // id → {at, by}: when it was first earned, and the find or supernova (`by`, as {e} or {n}) that did it
    let left = want.filter((id) => CHECK.get(id) && !['seven-days', 'lunar-month', 'thirty-days', 'full-circle'].includes(id));
    const reach = (by) => {
      left = left.filter((id) => {
        const [have, need] = CHECK.get(id)(T);
        if (have < need) return true;
        reached[id] = { at: by.t, by };
        return false;
      });
    };
    const items = finds.map((e) => ({ e, t: e.t })).concat(novas.map((n) => ({ n, t: n.t })));
    items.sort((a, b) => a.t - b.t);
    const perDay = new Map(), today = dayOf(now);  // day → {n: finds, by: the find that made it count}
    for (const it of items) {
      if (it.n) {
        T.novas++;
        if (it.n.mine && !it.n.solo) T.lastWord = 1;
        if (left.length) reach(it);
        continue;
      }
      const e = it.e, rx = fdiv(e.x, RC), ry = fdiv(e.y, RC), k = `${rx},${ry}`;
      T.finds++;
      if (e.f) { T.first++; if (e.n && e.n % 1000 === 0) T.cairn = 1; }
      if (e.s) T.bonus++;
      if (e.w.length > T.longest) T.longest = e.w.length;
      if (isPalindrome(e.w)) T.mirror = 1;
      if (e.w === 'SURVEYOR') T.surveyor = 1;
      T.far = Math.max(T.far, Math.abs(rx), Math.abs(ry));
      T.dirs.add(e.d);
      T.themes.add(e.th);
      for (const th of wordThemes.get(e.w) || []) {
        let s = T.lexWords.get(th);
        if (!s) T.lexWords.set(th, s = new Set());
        s.add(e.w);
        if (!T.lex || s.size / THEMES[th].words.length > T.lex.n / THEMES[T.lex.th].words.length) T.lex = { th, n: s.size };
      }
      let tr = T.terr.get(k);
      if (!tr) T.terr.set(k, tr = { hid: 0, first: 0, done: false, lion: false });
      if (!e.s) {
        const total = territoryTotal(rx, ry);
        tr.hid++;
        if (!tr.done && tr.hid >= total) { tr.done = true; T.full++; }
        if (!tr.done && (!T.near || tr.hid / total > T.near.n / T.near.of)) T.near = { rx, ry, n: tr.hid, of: total };
        if (e.f) {
          tr.first++;
          const most = Math.floor(total / 2) + 1;
          if (!tr.lion && tr.first >= most) { tr.lion = true; T.lion = 1; }
          if (!T.lion && (!T.lionNear || tr.first / most > T.lionNear.n / T.lionNear.of)) T.lionNear = { rx, ry, n: tr.first, of: most };
        }
      }
      const dn = dayOf(e.t);
      let day = perDay.get(dn);
      if (!day) perDay.set(dn, day = { n: 0, by: null });
      if (++day.n === STREAK_MIN) day.by = it;
      if (left.length) reach(it);
    }
    const counted = [...perDay].filter(([d, v]) => v.n >= STREAK_MIN && d <= today).map(([d]) => d).sort((a, b) => a - b);
    const runs = runsOf(counted, today, [7, 28]);
    Object.assign(T, { best: runs.best, current: runs.run.length, run: runs.run, days: counted.length, counted: new Set(counted),
      first0: counted.length ? counted[0] : null, span: counted.length ? counted[counted.length - 1] - counted[0] : 0, today: perDay.has(today) ? perDay.get(today).n : 0, perDay });
    // A day's achievement is dated by the find that made the day that earned it count.
    const byDay = (id, d) => { if (d !== undefined) { const by = perDay.get(d).by; reached[id] = { at: by.t, by }; } };
    byDay('seven-days', runs.at[7]);
    byDay('lunar-month', runs.at[28]);
    byDay('thirty-days', counted[29]);
    byDay('full-circle', counted.find((d) => d - counted[0] >= 365));
    return { T, reached };
  }

  return { CATALOG, CHECK, PROVABLE, BIRDS, SEAS, SKIES, NATIONS, STREAK_MIN, cardMask, cardIds, runsOf, tally };
}

// The badges' words count the themes in each group, which only the themes
// decide, so the rules are worked out once here just for those.
const { BIRDS, SEAS, SKIES, NATIONS } = achievementsCore({ THEMES });

// The badges, for the game and for the share Worker's cards of them
// (share/src/badge.js), so a card draws a badge as the game does: the groups
// and their hues, each badge's drawing, its name and what it asks for.
export const MARK_GROUPS = [
  { id: 'notes', name: 'Field notes', h: 215 },
  { id: 'charting', name: 'Charting', h: 38 },
  { id: 'territories', name: 'Territories', h: 150 },
  { id: 'themes', name: 'Themes', h: 275 },
  { id: 'words', name: 'Words', h: 185 },
  { id: 'far', name: 'Far afield', h: 18 },
  { id: 'novas', name: 'Supernovas', h: 325 },
  { id: 'days', name: 'Days', h: 50 },
  { id: 'company', name: 'Company', h: 245 },
];
// Each badge's drawing, on a 32 × 32 grid inside its ring, in the emotes'
// line style: strokes, round caps, and `f` for the few filled dots.
const star4 = (x, y, s) => `<path d="M${x} ${y - s}Q${x} ${y} ${x + s} ${y}Q${x} ${y} ${x} ${y + s}Q${x} ${y} ${x - s} ${y}Q${x} ${y} ${x} ${y - s}z"/>`;
export const MARK_DRAW = {
  mark: '<rect x="7.5" y="12.9" width="17" height="6.2" rx="3.1" transform="rotate(-32 16 16)"/>',
  book: '<path d="M10 8h9.5a2.5 2.5 0 0 1 2.5 2.5V24H12.5A2.5 2.5 0 0 1 10 21.5z"/><path d="M10 21.5A2.5 2.5 0 0 1 12.5 19H22"/><path d="M13.5 12.5h5"/>',
  shelf: '<path d="M8 10h4v14H8zM13 8h4v16h-4z"/><path d="M18.6 10.8l3.8-1 3 12.4-3.8 1z"/>',
  atlas: '<path d="M16 10.5c-2.6-1.6-5.4-2.1-8.5-1.6v13.2c3.1-.5 5.9 0 8.5 1.6 2.6-1.6 5.4-2.1 8.5-1.6V8.9c-3.1-.5-5.9 0-8.5 1.6zM16 10.5v13.2"/><path d="M10 14.6c1.6-.4 2.9-.2 3.8.3M18.2 14.9c.9-.5 2.2-.7 3.8-.3"/>',
  first: '<circle class="f" cx="16" cy="16" r="2.6"/><circle cx="16" cy="16" r="6.2"/><path d="M16 5.5v2.6M16 23.9v2.6M5.5 16h2.6M23.9 16h2.6"/>',
  flag: '<path d="M11 25V7"/><path d="M11 8h11l-2.6 4 2.6 4H11"/>',
  trail: '<path d="M8 24.5c3.5-.8 3.5-4.5 6.5-4.8s4.4-2.4 4-5.7" stroke-dasharray="1.4 2.6"/><path d="M18.5 14V6.5"/><path d="M18.5 7h6.2l-1.6 2.4 1.6 2.4h-6.2"/>',
  cairn: '<ellipse cx="16" cy="22.6" rx="7.2" ry="2.6"/><ellipse cx="16" cy="17.1" rx="5.1" ry="2.3"/><ellipse cx="16" cy="12.3" rx="3.3" ry="2"/>',
  wander: '<circle class="f" cx="9" cy="22.5" r="1.7"/><circle class="f" cx="23" cy="9.5" r="1.7"/><path d="M10.8 21.4c4.5-.8 1.6-6.4 5.8-6.4s3.8-3.6 5-4.3" stroke-dasharray="1.4 2.6"/>',
  grid: '<path d="M8 8h16v16H8z"/><path d="M8 13.3h16M8 18.7h16M13.3 8v16M18.7 8v16"/>',
  sheet: '<path d="M9 7.5h10.5l3.5 3.5v13.5H9z"/><path d="M19.5 7.5V11H23"/><path d="M12.5 17l2.5 2.5 5-5.5"/>',
  sheets: '<path d="M12 6.5h9l3 3v11.5H12z"/><path d="M9 10v15.5h12"/><path d="M15 14.8l2 2 4-4.3"/>',
  lion: '<circle cx="16" cy="16" r="8.5"/><path class="f" opacity=".45" d="M16 16V7.5a8.5 8.5 0 1 1-8.1 11.1z"/>',
  key: '<circle cx="10.5" cy="16" r="3.8"/><path d="M14.3 16H25M21.5 16v3.6M24.6 16v2.8"/>',
  legend: '<path d="M8 8.5h16v15H8z"/><path class="f" d="M10.8 11.6h3v3h-3zM10.8 17.4h3v3h-3z"/><path d="M16.5 13.1h5M16.5 18.9h5"/>',
  quill: '<path d="M24 7.5c-7 .3-12.5 5.6-14 14.5 8.6-1.3 13.9-7.2 14-14.5z"/><path d="M10 22l-2.5 2.5M14 18l4.5-4.5"/>',
  birds: '<path d="M6.5 18c2.7-2 6.3-1.8 9.5 1.6 3.2-3.4 6.8-3.6 9.5-1.6"/><path d="M15.5 10.5c1.2-.9 2.9-.8 4.2.8 1.3-1.6 3-1.7 4.2-.8"/>',
  waves: '<path d="M6.5 11.5c1.6-1.6 3.2-1.6 4.8 0s3.2 1.6 4.8 0 3.2-1.6 4.8 0 3.2 1.6 4.8 0M6.5 16.5c1.6-1.6 3.2-1.6 4.8 0s3.2 1.6 4.8 0 3.2-1.6 4.8 0 3.2 1.6 4.8 0M6.5 21.5c1.6-1.6 3.2-1.6 4.8 0s3.2 1.6 4.8 0 3.2-1.6 4.8 0 3.2 1.6 4.8 0"/>',
  stars: '<path d="M9 21.5l4-8.5 6 3 4-7M19 16l3.5 6"/><circle class="f" cx="9" cy="21.5" r="1.6"/><circle class="f" cx="13" cy="13" r="1.6"/><circle class="f" cx="19" cy="16" r="1.6"/><circle class="f" cx="23" cy="9" r="1.6"/><circle class="f" cx="22.5" cy="22" r="1.6"/>',
  passport: '<rect x="10" y="7" width="12" height="18" rx="1.5"/><circle cx="16" cy="14" r="3.6"/><path d="M12.4 14h7.2M16 10.4c-1.6 2.2-1.6 5 0 7.2M13.2 21h5.6"/>',
  bonus: '<rect x="7.5" y="12.9" width="17" height="6.2" rx="3.1" transform="rotate(-32 16 16)" stroke-dasharray="2.4 2.2"/>',
  bonuses: '<rect x="7" y="13.2" width="18" height="5.6" rx="2.8" transform="rotate(-35 16 16)" stroke-dasharray="2.4 2.2"/><rect x="7" y="13.2" width="18" height="5.6" rx="2.8" transform="rotate(35 16 16)" stroke-dasharray="2.4 2.2"/>',
  ruler: '<g transform="rotate(-35 16 16)"><rect x="5.5" y="12.8" width="21" height="6.4" rx="1"/><path d="M9 12.8v2.6M12.5 12.8v1.7M16 12.8v2.6M19.5 12.8v1.7M23 12.8v2.6"/></g>',
  rose: '<path d="M16 5.5l2.1 8.4 8.4 2.1-8.4 2.1-2.1 8.4-2.1-8.4-8.4-2.1 8.4-2.1z"/><path d="M10 10l3 3M22 10l-3 3M10 22l3-3M22 22l-3-3"/>',
  mirror: '<path d="M16 7v18" stroke-dasharray="1.6 2.2"/><path d="M12.5 11l-4.5 5 4.5 5M19.5 11l4.5 5-4.5 5"/>',
  theodolite: '<rect x="11.5" y="7.5" width="9" height="6" rx="1.6"/><path d="M20.5 10.5h3.5M16 13.5v3M9.5 25.5l6.5-9 6.5 9M16 16.5v9"/>',
  horizon: '<path d="M6.5 20.5h19M10.5 20.5a5.5 5.5 0 0 1 11 0M16 9v2.4M9.4 12l1.7 1.7M22.6 12l-1.7 1.7M10 24.5h12"/>',
  edge: '<path d="M7.5 23.5a11 11 0 0 1 16-14.5"/><path d="M10.8 23.5a7.6 7.6 0 0 1 10-9.2"/><circle class="f" cx="13.8" cy="22.2" r="1.9"/><circle class="f" cx="24.4" cy="7.4" r="1.4"/>',
  dragon: '<path d="M5.5 19.5c1.5-4 4.3-4 5.5 0s4 4 5.5 0 4-4 5.5 0c.3-2.6 1.6-4.6 3.6-5"/><path d="M6 24h20" stroke-dasharray="1.6 2.4"/>',
  burst: '<circle class="f" cx="16" cy="16" r="2.8"/><path d="M16 6v4.2M16 21.8V26M6 16h4.2M21.8 16H26M8.9 8.9l3 3M23.1 8.9l-3 3M8.9 23.1l3-3M23.1 23.1l-3-3"/>',
  sparkles: star4(12, 15, 5.5) + star4(21.5, 9.5, 3.4) + star4(20.5, 21.5, 4.2),
  last: '<rect x="5" y="17" width="13" height="5.4" rx="2.7" transform="rotate(-35 11.5 19.7)"/><path d="M21.5 5.8v2.6M21.5 13.6v2.6M16.4 11h2.6M24 11h2.6M17.9 7.4l1.7 1.7M25.1 7.4l-1.7 1.7M25.1 14.6l-1.7-1.7"/><circle class="f" cx="21.5" cy="11" r="1.5"/>',
  week: '<rect x="7.5" y="9" width="17" height="15" rx="2"/><path d="M7.5 13.5h17M12 7v4M20 7v4M12.5 18.6l2.4 2.4 4.6-4.6"/>',
  moon: '<path d="M20.5 7.2a9.4 9.4 0 1 0 4.8 13.4 7.4 7.4 0 0 1-4.8-13.4z"/>',
  tally: '<path d="M9.5 9.5v13M13 9.5v13M16.5 9.5v13M20 9.5v13M7.5 20l15-8"/>',
  orbit: '<circle cx="16" cy="16" r="8.8"/><circle class="f" cx="16" cy="16" r="2.6"/><circle class="f" cx="22.2" cy="9.8" r="1.9"/>',
  carets: '<path d="M10.5 11v10M16 8.5v15M21.5 11v10" stroke-width="2.8"/>',
  devices: '<rect x="6.5" y="10" width="7" height="12.5" rx="1.4"/><path d="M16 11.5h9.5v8.5H16zM14.5 23h12.5"/>',
  beast: '<path d="M11.8 14.2a1.8 1.8 0 0 0 -3.6 0V21.2a1.8 1.8 0 0 0 3.6 0V19.288a1.8 1.8 0 0 0 -3.6 0M17.8 14.2a1.8 1.8 0 0 0 -3.6 0V21.2a1.8 1.8 0 0 0 3.6 0V19.288a1.8 1.8 0 0 0 -3.6 0M23.8 14.2a1.8 1.8 0 0 0 -3.6 0V21.2a1.8 1.8 0 0 0 3.6 0V19.288a1.8 1.8 0 0 0 -3.6 0"/><path d="M13.4 10.7c-2.2-.3-3.4-2.4-2.4-5 .3 1.7 1.4 2.8 3.2 3.2M18.6 10.7c2.2-.3 3.4-2.4 2.4-5-.3 1.7-1.4 2.8-3.2 3.2"/>',
  hat: '<path d="M7.5 21.6c4.4 1.7 12.6 1.7 17 0"/><path d="M11 21.2v-6.4c0-2.2 2.2-3.8 5-3.8s5 1.6 5 3.8v6.4"/><path d="M11 18.2h10"/>',
  secret: '<path d="M12.6 12.4a3.5 3.5 0 1 1 4.9 3.2c-.9.4-1.5 1.2-1.5 2.2v.8"/><circle class="f" cx="16" cy="22" r="1.3"/>',
};
// What each says to a surveyor: its drawing, its name and what to do.
export const MARK_TEXT = {
  'first-mark': ['mark', 'First Mark', 'Circle your first word.'],
  'field-book': ['book', 'Field Book', 'Keep 100 words in your field notes.'],
  'bound-volume': ['shelf', 'Bound Volume', 'Keep 1,000 words in your field notes.'],
  'great-atlas': ['atlas', 'Great Atlas', 'Keep 5,000 words in your field notes.'],
  'first-light': ['first', 'First Light', 'Chart a word first on the shared survey.'],
  'trailblazer': ['flag', 'Trailblazer', 'Chart 100 words first.'],
  'pathfinder': ['trail', 'Pathfinder', 'Chart 1,000 words first.'],
  'cairn': ['cairn', 'Cairn', 'Chart a word that came in at a round thousand in the universe’s count.'],
  'wanderer': ['wander', 'Wanderer', 'Find words in 10 territories.'],
  'gazetteer': ['grid', 'Gazetteer', 'Find words in 50 territories.'],
  'every-last-word': ['sheet', 'Every Last Word', 'Find every hidden word in one territory.'],
  'five-sheets': ['sheets', 'Five Full Sheets', 'Find every hidden word in five territories.'],
  'lions-share': ['lion', 'Lion’s Share', 'Chart first more than half of one territory’s hidden words.'],
  'map-key': ['key', 'Map Key', 'Find words from 25 themes.'],
  'full-legend': ['legend', 'Full Legend', `Find a word from every one of the ${NT} themes.`],
  'lexicographer': ['quill', 'Lexicographer', 'Find every word one theme has.'],
  'dawn-chorus': ['birds', 'Dawn Chorus', `Find words from all ${BIRDS.length} bird themes.`],
  'seven-seas': ['waves', 'Seven Seas', `Find words from all ${SEAS.length} themes of the sea.`],
  'star-chart': ['stars', 'Star Chart', `Find words from all ${SKIES.length} themes of the sky.`],
  'passport': ['passport', 'Passport', `Find words from all ${NATIONS.length} countries’ themes.`],
  'happy-accident': ['bonus', 'Happy Accident', 'Find a bonus word, a real word the letters spell by chance.'],
  'serendipity': ['bonuses', 'Serendipity', 'Find 25 bonus words.'],
  'long-measure': ['ruler', 'Long Measure', 'Find a ten-letter word, the longest the map hides.'],
  'compass-rose': ['rose', 'Compass Rose', 'Find words reading in all eight directions.'],
  'mirror-image': ['mirror', 'Mirror Image', 'Find a word that reads the same both ways.'],
  'self-portrait': ['theodolite', 'Self-Portrait', 'Find the word SURVEYOR.'],
  'over-the-horizon': ['horizon', 'Over the Horizon', 'Find a word 10 territories from the map centre.'],
  'edge-of-the-universe': ['edge', 'Edge of the Universe', `Find a word ${UNIVERSE_EDGE} territories out, where the universe ends.`],
  'here-be-dragons': ['dragon', 'Here Be Dragons', 'Find a word 250 territories from the map centre.'],
  'witness': ['burst', 'Witness', 'Be there when a territory goes supernova.'],
  'starfield': ['sparkles', 'Starfield', 'Be there for ten supernovas.'],
  'last-word': ['last', 'Last Word', 'Chart the last hidden word of a territory, and set it off.'],
  'seven-days': ['week', 'Seven Days Running', 'Keep a streak going for seven days.'],
  'lunar-month': ['moon', 'Lunar Month', 'Keep a streak going for 28 days.'],
  'thirty-days': ['tally', 'Thirty Days Out', 'Survey on 30 different days.'],
  'full-circle': ['orbit', 'Full Circle', 'Survey a year after your first find.'],
  'fellowship': ['carets', 'Fellowship', 'Be in a guild.'],
  'two-places': ['devices', 'Two Places at Once', 'Link another device, or save a recovery code.'],
  'hats-off': ['hat', 'Hats Off', 'Have someone tip their hat to you.'],
  'number-of-the-beast': ['beast', 'Number of the Beast', 'Keep 666 words in your field notes.'],
};
