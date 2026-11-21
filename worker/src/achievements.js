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
//   finds alone, with the game's own rules (js/letterfield/achievements.js), or, until
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

import { MARK_DRAW, MARK_GROUPS, MARK_TEXT, UNIVERSE_EDGE, achievementsCore } from '../../js/letterfield/achievements.js';
import { CH, RC, THEMES, chunk, fdiv, keyOf, regionTheme, strayTheme, territoryTotal } from '../../js/letterfield/world.js';
import { HttpError, answered, corsHeaders, hashIp, json, mustPost, rateLimit, readBody } from './leaderboard.js';
import { playerId, tokenIn } from './survey-social.js';

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
// The badges' art, for the share Worker's cards of them (share/src/badge.js).
export { achievementsCore, CORE, MARK_DRAW, MARK_GROUPS, MARK_TEXT, UNIVERSE_EDGE };


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
