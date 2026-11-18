// Letterfield's achievements on the Worker (see ACHIEVEMENTS.md): the game
// works out a surveyor's achievements from their own notes, and keeps them
// there. Shown to others, a badge has to mean something, so:
//
// - A sector signs each word a surveyor circles on the shared survey, for
//   them alone: {t: 'signed', k, r} after its answer, where r says when the
//   sector had it, whether they charted it first or set off a supernova with
//   it, and a signature over that, the word, its place and their player id
//   (signFind). The game keeps r with the find, and it syncs with it.
// - POST /v1/survey/badges {token, z, finds, earned, since, held, card} →
//   {badges: {id: sig}, card}: the badges the Worker will stand behind, each
//   signed for this player (badgeSig). It works them out from the signed
//   finds alone, with the same rules as the game (the core below), or, until
//   TRUSTED_UNTIL, takes the game's word for any it has earned, and for when
//   it began (since), so achievements from before signing still count. The
//   few no find can prove (CATALOG's l and u) it always takes on the game's
//   word. z is
//   the surveyor's time zone (minutes behind UTC, as getTimezoneOffset), for
//   their days. held ({id: sig}) and card are what it already has signed,
//   which stay so.
// - The game sends its chosen badge in its `me` message ([id, sig]); the
//   sector checks the signature and shows it in presence.
// - The same answer brings the surveyor's card (signCard): every badge the
//   Worker stands behind for them, and the day they began surveying. The game
//   sends it in `me` too, and others see it in their caret's menu.
//
// Signatures are HMAC-SHA256, cut to 72 bits, under keys made from IP_SALT
// for each use, so there's no new secret to keep. Nothing here is stored:
// the proof lives with the surveyor's finds.

import { CH, RC, THEMES, chunk, fdiv, keyOf, regionTheme, strayTheme, territoryTotal } from './letterfield-world.js';
import { HttpError, answered, corsHeaders, hashIp, json, mustPost, rateLimit, readBody } from './leaderboard.js';
import { playerId, tokenIn } from './survey-social.js';

export const UNIVERSE_EDGE = 48;            // territories from the map centre to the universe's edge: AREA sectors of 4
// Until then, the game's word is taken for any badge it has earned: those
// from before finds were signed. Set to a couple of weeks after signing ships.
export const TRUSTED_UNTIL = Date.UTC(2026, 11, 15);
export const BADGE_FINDS_MAX = 30000;       // signed finds one request may bring (the notes keep 25,000)
const MAX_BODY = 3 * 1024 * 1024;
const BADGES_PATH = '/v1/survey/badges';
export const RECEIPT = /^([0-9a-z]{1,11})\.([fz]{0,2})\.([A-Za-z0-9_-]{12})$/;
export const BADGE = /^[a-z0-9-]{1,32}$/;
export const BADGE_SIG = /^[A-Za-z0-9_-]{12}$/;
export const CARD = /^([0-9a-z]{1,11})\.([0-9a-z]{1,4})\.([A-Za-z0-9_-]{12})$/;
const SINCE_MIN = Date.UTC(2025, 0, 1);    // before Letterfield
const DAY_MS = 864e5;

// ---- BEGIN ACHIEVEMENTS CORE ----
// The same in letterfield.html and worker/src/achievements.js, word for word
// (worker/test/achievements.test.js checks): what each achievement asks for,
// and one pass over a surveyor's finds and supernovas, in time order, that
// says how far along each is. The game works its own notes out with it; the
// Worker works out the signed finds a badge shown to others needs. `world`
// gives the map: THEMES, territoryTotal(rx, ry), RC (cells a territory),
// UNIVERSE_EDGE (territories to the universe's edge) and dayOf(t), the day
// a time falls on where the surveyor is, as a whole number.
function achievementsCore(world) {
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
    ['here-be-dragons', 'far', 'h', (T) => pair(T.far, 250)],
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
      first0: counted.length ? counted[0] : null, span: counted.length ? counted[counted.length - 1] - counted[0] : 0, today: perDay.has(today) ? perDay.get(today).n : 0 });
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
// ---- END ACHIEVEMENTS CORE ----

/* ---------- Signing ---------- */

const enc = (s) => new TextEncoder().encode(s);
const keys = new Map();
function keyFor(env, use) {
  const k = `${use}:${env.IP_SALT}`;
  if (!keys.has(k)) {
    keys.set(k, crypto.subtle.digest('SHA-256', enc(`letterfield-${use}:${env.IP_SALT}`))
      .then((raw) => crypto.subtle.importKey('raw', raw, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])));
  }
  return keys.get(k);
}
async function mac(env, use, text) {
  const sig = new Uint8Array(await crypto.subtle.sign('HMAC', await keyFor(env, use), enc(text)));
  return btoa(String.fromCharCode(...sig.slice(0, 9))).replace(/\+/g, '-').replace(/\//g, '_');
}
// Whether signing is on: only with a salt, so no signature can be made with a key anyone knows.
export const signing = (env) => typeof env.IP_SALT === 'string' && env.IP_SALT.length > 0;

// A find's receipt, for the player who circled it: when (the sector's time),
// f if they charted it first, z if it set off a supernova.
export async function signFind(env, pid, { w, x, y, d }, at, flags) {
  return `${at.toString(36)}.${flags}.${await mac(env, 'find', `${w}|${x}|${y}|${d}|${pid}|${at}|${flags}`)}`;
}

// What a find's receipt says, if it was made for this player and this find: {at, f, z}, or null.
export async function checkReceipt(env, pid, find) {
  const m = typeof find?.r === 'string' && RECEIPT.exec(find.r);
  if (!m || !signing(env) || typeof find.w !== 'string' || ![find.x, find.y, find.d].every(Number.isInteger)) return null;
  const at = parseInt(m[1], 36);
  if ((await mac(env, 'find', `${find.w}|${find.x}|${find.y}|${find.d}|${pid}|${at}|${m[2]}`)) !== m[3]) return null;
  return { at, f: m[2].includes('f'), z: m[2].includes('z') };
}

export const badgeSig = (env, pid, id) => mac(env, 'badge', `${pid}|${id}`);
// The badge a game shows, if its signature is good for this player: its id, or null.
export async function checkBadge(env, pid, badge) {
  if (!Array.isArray(badge) || typeof badge[0] !== 'string' || !BADGE.test(badge[0]) || typeof badge[1] !== 'string' || !BADGE_SIG.test(badge[1])) return null;
  if (!signing(env) || !CORE.CHECK.has(badge[0])) return null;
  return (await badgeSig(env, pid, badge[0])) === badge[1] ? badge[0] : null;
}

// A surveyor's card, for others to see in their caret's menu: the badges the
// Worker stands behind for them (CORE.cardMask) and the day they began
// surveying (UTC days since 1970, 0 if not known), each in base 36, then a
// signature over both for this player: `5k8jq0.k5x.Ab3dE_gh1JkL`. Others see
// the part before the signature.
const cardSig = (env, pid, mask, day) => mac(env, 'card', `${pid}|${mask}|${day}`);
export const signCard = async (env, pid, mask, day) => `${mask.toString(36)}.${day.toString(36)}.${await cardSig(env, pid, mask, day)}`;
// What a card says, if its signature is good for this player: {mask, day, shown}, or null.
export async function checkCard(env, pid, card) {
  const m = typeof card === 'string' && CARD.exec(card);
  if (!m || !signing(env)) return null;
  const mask = parseInt(m[1], 36), day = parseInt(m[2], 36);
  if (!Number.isSafeInteger(mask) || (await cardSig(env, pid, mask, day)) !== m[3]) return null;
  return { mask, day, shown: `${mask.toString(36)}.${day.toString(36)}` };
}

/* ---------- Badges others see ---------- */

const offsetDay = (z) => (t) => Math.floor((t - z * 60000) / 864e5);
const CORE = achievementsCore({ THEMES, territoryTotal, RC, UNIVERSE_EDGE, dayOf: offsetDay(0) });
export { achievementsCore, CORE };

// The badges signed finds show, worked out as the game does: each find as
// the sector signed it (when it had it, charted first or not), with its kind
// (hidden or bonus word) and theme from the map, and a supernova for each
// that set one off. Unproven ones (CATALOG's u) never come from here.
// {ids, since}: since is when the sector had the earliest of them.
export async function provenBadges(env, pid, finds, z, now) {
  const kept = new Map();
  let since = Infinity;
  for (const f of finds.slice(0, BADGE_FINDS_MAX)) {
    const got = await checkReceipt(env, pid, f);
    if (!got) continue;
    since = Math.min(since, got.at);
    const key = keyOf(f.w, f.x, f.y, f.d), had = kept.get(key);
    if (had && had.t <= got.at) continue;
    const rx = fdiv(f.x, RC), ry = fdiv(f.y, RC);
    const s = chunk(fdiv(f.x, CH), fdiv(f.y, CH)).words.some((p) => p.key === key) ? 0 : 1;
    kept.set(key, { w: f.w, x: f.x, y: f.y, d: f.d, t: got.at, s, f: got.f ? 1 : 0, n: 0, th: s ? strayTheme(f.w, rx, ry) : regionTheme(rx, ry), z: got.z });
  }
  const list = [...kept.values()], novas = list.filter((f) => f.z).map((f) => ({ t: f.t, mine: true, solo: false }));
  const { T } = achievementsCore({ THEMES, territoryTotal, RC, UNIVERSE_EDGE, dayOf: offsetDay(z) }).tally(list, novas, now);
  return { ids: CORE.CATALOG.filter(([id, , , check]) => CORE.PROVABLE.has(id) && check(T)[0] >= check(T)[1]).map(([id]) => id), since };
}

export function routeBadges(request, env, now = Date.now()) {
  if (new URL(request.url).pathname !== BADGES_PATH || !env.DB) return null;
  const cors = corsHeaders(request, env);
  return answered(request, cors, async () => {
    mustPost(request, cors);
    if (!signing(env)) throw new HttpError(503, 'badges are not set up here');
    const body = await readBody(request, MAX_BODY);
    const pid = await playerId(tokenIn(body));
    const z = Number.isInteger(body.z) && Math.abs(body.z) <= 840 ? body.z : 0;
    const finds = Array.isArray(body.finds) ? body.finds : [];
    const earned = Array.isArray(body.earned) ? body.earned.filter((id) => typeof id === 'string' && CORE.CHECK.has(id)) : [];
    const held = body.held && typeof body.held === 'object' && !Array.isArray(body.held) ? Object.entries(body.held).slice(0, CORE.CATALOG.length) : [];
    if (finds.length > BADGE_FINDS_MAX) throw new HttpError(413, 'too many finds');
    await rateLimit(env.DB, 'badges', await hashIp(request, env.IP_SALT), now);
    const proven = await provenBadges(env, pid, finds, z, now);
    const ids = new Set(proven.ids);
    let since = proven.since;
    // The game's word: always for those no find can prove, and for a while
    // for the rest, and for when its first find was.
    for (const id of earned) if (now < TRUSTED_UNTIL || !CORE.PROVABLE.has(id)) ids.add(id);
    if (now < TRUSTED_UNTIL && Number.isFinite(body.since) && body.since >= SINCE_MIN && body.since <= now) since = Math.min(since, body.since);
    // What's already signed for this player: badges it holds, and its last card.
    for (const [id, sig] of held) if (await checkBadge(env, pid, [id, sig])) ids.add(id);
    const was = await checkCard(env, pid, body.card);
    if (was) {
      for (const id of CORE.cardIds(was.mask)) ids.add(id);
      if (was.day) since = Math.min(since, was.day * DAY_MS);
    }
    const badges = {};
    for (const id of ids) badges[id] = await badgeSig(env, pid, id);
    const mask = CORE.cardMask(ids), day = Number.isFinite(since) ? Math.floor(since / DAY_MS) : 0;
    return json({ badges, ...(mask || day ? { card: await signCard(env, pid, mask, day) } : {}) }, 200, cors);
  });
}
