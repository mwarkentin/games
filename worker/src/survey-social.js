// Letterfield's surveyors: who else is surveying the shared world, and the
// emotes they can send each other. survey.js calls into this from its Sector
// and Atlas, and src/index.js routes the list's path here. See "Surveyors and
// emotes" in SURVEY.md for the design, its limits and what it costs.
//
//   GET /v1/survey/surveyors?r=<rx>,<ry>&page=<n>&me=<pid>
//     → {n, page, size, more, who: [[pid, initials, rx, ry, idle, flags], ...]}
//     The surveyors listed in the shared world, nearest territory (rx, ry)
//     first, LIST_PAGE a page; `me` leaves the asker out. idle is seconds
//     since they last moved; flags & FLAG_QUIET means they take no emotes.
//
// Who a player is. Initials aren't unique, and a sector's socket ids last one
// socket. So the game keeps a random token (32 hex digits) in localStorage
// and sends it in its `me` message to every sector it joins. The sector names
// the player by the token's hash (playerId), the same in every sector and
// every visit: that's what presence, the list and emotes call them. Nobody
// learns another player's token, and a player can't pick their id, so nobody
// can send as someone else.
//
// Where the list comes from. Each sector already reports to the Atlas every
// ≤ REPORT_MS while busy; the report also lists its surveyors, by territory,
// never the cell they're on, and leaves out anyone who asked to be hidden.
// The Atlas builds one snapshot of everyone at most every LIST_MS, each
// Worker instance fetches it at most that often, and works out each page
// itself, so a crowd reading the list costs the Atlas one request per instance
// per LIST_MS.
//
// Emotes go from the sender's sector (the one under the middle of their view,
// which knows where they are) to the recipient's: there and then if that's the
// same sector, or with an internal POST (EMOTE_PATH) to the recipient's sector,
// which only Workers binding SECTORS can reach. The recipient's sector sees
// every emote its players get, from anywhere, so it holds the limits that
// protect them: a few a minute from one sender, and a cap from everyone.

import { INITIALS } from './leaderboard.js';
import { RC, fdiv } from './letterfield-world.js';

export const PID = /^[0-9a-f]{12}$/;     // a player, as everyone else knows them
export const TOKEN = /^[0-9a-f]{32}$/;   // the secret the game keeps, which only it and the sectors see
export const GUILD_CODE = /^[A-HJKMNP-Z2-9]{6}$/;  // a guild's secret code: groups' alphabet, two letters longer (survey-guild.js)
export const GUILD_TAG = /^[0-9a-f]{8}$/;          // a guild as anyone can see it: a random id
// The emotes, in the order the game shows them. Fixed drawings, never text:
// see "The emotes" in SURVEY.md for why each is here and what was left out.
export const EMOTES = ['wave', 'thanks', 'nice', 'clap', 'great', 'here', 'what'];
export const FLAG_QUIET = 1;             // a listed surveyor who takes no emotes
export const FLAG_HIDDEN = 2;            // off the list, but still shown to their guild
export const LIST_PATH = '/v1/survey/surveyors';
export const ATLAS_LIST_PATH = '/surveyors';
export const EMOTE_PATH = '/emote';      // internal: an emote for a player in this sector, from another
export const LIST_MS = 10000;            // the list is rebuilt, and cached, for this long
export const LIST_PAGE = 40;             // surveyors per page
export const LIST_PAGES = 25;            // pages anyone can read: the nearest 1,000
export const REFRESH_MS = 50000;         // a sector reports at least this often while messages come in
export const IDLE_MAX = 86400;           // seconds idle a report counts up to
export const EMOTE_BURST = 3;            // emotes a socket can send at once,
export const EMOTE_REFILL_MS = 4000;     // then one per this many milliseconds
export const PAIR_MAX = 3;               // emotes one player can send another
export const PAIR_MS = 60000;            //   in this long
export const INBOX_MAX = 6;              // emotes one player can be sent by everyone
export const INBOX_MS = 10000;           //   in this long
const TERR = 4;                          // territories per sector side
const isInt = (v, min, max) => Number.isInteger(v) && v >= min && v <= max;
const send = (ws, message) => { try { ws.send(JSON.stringify(message)); } catch { /* closing */ } };

// A player's id from their token: 48 bits of its SHA-256, plenty to tell
// apart everyone who ever plays, and no use for finding the token.
export async function playerId(token) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`games-player:${token}`));
  return [...new Uint8Array(digest).slice(0, 6)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

// What a `me` message says besides initials: the player's token, whether to
// leave them out of the list (hide), whether they take emotes (quiet) and
// their guild's code, which the sector checks with the guild (checkGuild in
// survey-guild.js) before the guild's tag goes on their socket. The flags
// count straight away; the id once its hash is worked out. Returns (a promise
// of) whether anything changed. A socket keeps the first id it's given.
export function takeMe(me, msg) {
  const hide = msg.hide === true, quiet = msg.quiet === true;
  const guild = typeof msg.guild === 'string' && GUILD_CODE.test(msg.guild) ? msg.guild : null;
  let changed = hide !== !!me.hide || quiet !== !!me.quiet || guild !== (me.guild ?? null);
  me.hide = hide;
  me.quiet = quiet;
  if (guild !== (me.guild ?? null)) { me.guild = guild; me.tag = null; me.guildAt = 0; }
  if (me.pid || typeof msg.token !== 'string' || !TOKEN.test(msg.token)) return changed;
  return playerId(msg.token).then((pid) => {
    if (!me.pid) { me.pid = pid; changed = true; }
    return changed;
  });
}

// The sector's surveyors for its report: those placed here who have an id and
// haven't hidden, once each (a player with two tabs open is one), by
// territory, most recently moved first: [pid, initials, rx, ry, idle, flags],
// and the guild's tag for a member. A hidden member is in it too, marked
// FLAG_HIDDEN, for their guild; the public list leaves them out.
export function listed(people, sx, sy, now) {
  const by = new Map();
  for (const p of people) {
    if (p.x === null || p.x === undefined || !p.pid || (p.hide && !p.tag)) continue;
    const rx = fdiv(Math.floor(p.x), RC), ry = fdiv(Math.floor(p.y), RC);
    if (fdiv(rx, TERR) !== sx || fdiv(ry, TERR) !== sy) continue;  // a position outside the sector says nothing true
    const had = by.get(p.pid);
    if (had && had.moved >= p.moved) continue;
    by.set(p.pid, p);
  }
  return [...by.values()].sort((a, b) => b.moved - a.moved).map((p) => [
    p.pid, p.initials, fdiv(Math.floor(p.x), RC), fdiv(Math.floor(p.y), RC),
    Math.min(IDLE_MAX, Math.max(0, Math.round((now - p.moved) / 1000))), (p.quiet ? FLAG_QUIET : 0) | (p.hide ? FLAG_HIDDEN : 0),
    ...(p.tag ? [p.tag] : []),
  ]);
}

// Whether a report's surveyors can be listed: each a player in the reporting sector.
export function goodWho(who, sx, sy, max) {
  if (who === undefined) return true;
  return Array.isArray(who) && who.length <= max && who.every((e) => Array.isArray(e) && (e.length === 6 || (e.length === 7 && typeof e[6] === 'string' && GUILD_TAG.test(e[6])))
    && typeof e[0] === 'string' && PID.test(e[0]) && (e[1] === '' || (typeof e[1] === 'string' && INITIALS.test(e[1])))
    && Number.isInteger(e[2]) && Number.isInteger(e[3]) && fdiv(e[2], TERR) === sx && fdiv(e[3], TERR) === sy
    && isInt(e[4], 0, IDLE_MAX) && isInt(e[5], 0, 255));
}

// The Atlas's snapshot of everyone listed, from sectors that reported in the
// last `online` ms: each player once, from the latest report that has them
// (someone crossing into another sector can be in two for a few seconds),
// with idle counted to now. Grouped by sector, for working out pages. Hidden
// guild members and every guild's tag stay out of it.
export function snapshot(rows, now, online) {
  const latest = new Map();
  for (const r of rows) {
    if (now - r.at >= online || !r.who?.length) continue;
    for (const e of r.who) {
      if (e[5] & FLAG_HIDDEN) continue;
      const had = latest.get(e[0]);
      if (!had || had.r.at < r.at) latest.set(e[0], { r, e });
    }
  }
  const sectors = new Map();
  for (const { r, e } of latest.values()) {
    const key = `${r.sx},${r.sy}`;
    if (!sectors.has(key)) sectors.set(key, [r.sx, r.sy, []]);
    const idle = Math.min(IDLE_MAX, e[4] + Math.round((now - r.at) / 1000));
    sectors.get(key)[2].push([e[0], e[1], e[2], e[3], idle, e[5] & FLAG_QUIET]);
  }
  return { at: now, n: latest.size, sectors: [...sectors.values()] };
}

// One page of the list, nearest territory (rx, ry) first: by territories
// away (the larger of the two distances, as the game's nearView counts), then
// straight-line distance, then the most recently active. Sectors are visited
// nearest first, and only as far as the page needs.
export function nearest(snap, rx, ry, page, me = null, size = LIST_PAGE) {
  const need = (page + 1) * size;
  const gap = (r, s) => Math.max(0, s * TERR - r, r - (s * TERR + TERR - 1));
  const order = snap.sectors.map(([sx, sy, who]) => ({ d: Math.max(gap(rx, sx), gap(ry, sy)), who })).sort((a, b) => a.d - b.d);
  const rank = (e) => ({ e, d: Math.max(Math.abs(e[2] - rx), Math.abs(e[3] - ry)), h: Math.hypot(e[2] - rx, e[3] - ry) });
  const before = (a, b) => a.d - b.d || a.h - b.h || a.e[4] - b.e[4] || (a.e[0] < b.e[0] ? -1 : 1);
  let near = [], n = 0;
  for (const s of order) n += s.who.length - (me && s.who.some((e) => e[0] === me) ? 1 : 0);
  for (const s of order) {
    if (near.length >= need) {
      near.sort(before);
      near = near.slice(0, need);
      if (s.d > near[need - 1].d) break;
    }
    for (const e of s.who) if (e[0] !== me) near.push(rank(e));
  }
  near.sort(before);
  return { n, page, size, more: n > need, who: near.slice(page * size, need).map((x) => x.e) };
}

// GET /v1/survey/surveyors, or null for any other path. Each Worker instance
// asks the Atlas for its snapshot at most once per LIST_MS and shares it.
const listCache = new WeakMap();
export function routeSurveyors(request, env, corsHeaders, json) {
  const url = new URL(request.url);
  if (url.pathname !== LIST_PATH || !env.ATLAS) return null;
  const cors = corsHeaders(request, env);
  if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405, cors);
  const r = /^(-?\d{1,9}),(-?\d{1,9})$/.exec(url.searchParams.get('r') ?? '');
  const page = Number(url.searchParams.get('page') ?? 0), me = url.searchParams.get('me');
  if (!r || !isInt(page, 0, LIST_PAGES - 1) || (me !== null && !PID.test(me))) return json({ error: 'bad request' }, 400, cors);
  return (async () => {
    const now = Date.now();
    let cached = listCache.get(env.ATLAS);
    if (!cached || now - cached.at > LIST_MS) {
      const atlas = env.ATLAS.get(env.ATLAS.idFromName('atlas'));
      cached = { at: now, snap: atlas.fetch(`https://atlas${ATLAS_LIST_PATH}`).then((res) => (res.ok ? res.json() : Promise.reject(new Error(`atlas ${res.status}`)))) };
      listCache.set(env.ATLAS, cached);
      cached.snap.catch(() => { if (listCache.get(env.ATLAS) === cached) listCache.delete(env.ATLAS); });
    }
    const body = nearest(await cached.snap, Number(r[1]), Number(r[2]), page, me);
    return json(body, 200, { ...cors, 'Cache-Control': `public, max-age=${LIST_MS / 1000}` });
  })();
}

// An emote from one of this sector's sockets: {t: 'emote', to, e, s}, to the
// player `to`, whom the sender saw in sector s. The sender is who their socket
// says, never who the message says. Answered with {t: 'emoted', to, e} and
// ok, or why not: 'sign first' (no id or initials yet), 'slow down', 'gone'
// (not there, or hidden from anyone not in their sector), 'off' (they take no
// emotes), 'busy' (they've been sent plenty just now) or 'bad emote'.
export async function sendEmote(sector, ws, me, msg) {
  const to = typeof msg.to === 'string' && PID.test(msg.to) ? msg.to : null, e = EMOTES.includes(msg.e) ? msg.e : null;
  const answer = (error) => send(ws, { t: 'emoted', to, e, ...(error ? { error } : { ok: true }) });
  const s = Array.isArray(msg.s) && msg.s.length === 2 && msg.s.every((v) => isInt(v, -1e7, 1e7)) ? msg.s : null;
  if (!to || !e || !s || to === me.pid) return answer('bad emote');
  if (!me.pid || !me.initials) return answer('sign first');
  const now = sector.now();
  me.emotes = Math.min(EMOTE_BURST, (me.emotes ?? EMOTE_BURST) + (now - (me.emoted ?? now)) / EMOTE_REFILL_MS);
  me.emoted = now;
  if (me.emotes < 1) return answer('slow down');
  me.emotes -= 1;
  // Every emote from the address counts, from any socket in any sector.
  if (!(await sector.allowed('SURVEY_EMOTES', me.address))) return answer('slow down');
  const [sx, sy] = sector.coords();
  // Where the sender is, by territory, for the recipient's "fly there".
  const r = me.x === null || me.x === undefined ? null : [fdiv(Math.floor(me.x), RC), fdiv(Math.floor(me.y), RC)];
  const card = { from: me.pid, ini: me.initials, e, to, r, tag: me.tag ?? null };
  if (s[0] === sx && s[1] === sy) return answer(deliver(sector, card, true));
  // Only to sectors a list or a caret could have shown: the shared world, or a neighbour in view.
  if (!sector.reaches(s[0], s[1])) return answer('gone');
  answer(await forward(sector.env, s, card));
}

async function forward(env, [sx, sy], card) {
  if (!env.SECTORS) return 'gone';
  try {
    const res = await env.SECTORS.get(env.SECTORS.idFromName(`${sx},${sy}`)).fetch(`https://sector${EMOTE_PATH}`, { method: 'POST', body: JSON.stringify(card) });
    if (!res.ok) return 'gone';
    return (await res.json()).error ?? null;
  } catch {
    return 'gone';
  }
}

const goodCard = (c) => c && typeof c.from === 'string' && PID.test(c.from) && typeof c.to === 'string' && PID.test(c.to) && c.from !== c.to
  && EMOTES.includes(c.e) && (c.ini === '' || (typeof c.ini === 'string' && INITIALS.test(c.ini)))
  && (c.r === null || (Array.isArray(c.r) && c.r.length === 2 && c.r.every((v) => isInt(v, -1e8, 1e8))))
  && (c.tag === undefined || c.tag === null || (typeof c.tag === 'string' && GUILD_TAG.test(c.tag)));

// POST EMOTE_PATH: an emote another sector passes on, for a player here.
export async function takeEmote(sector, request) {
  let card = null;
  try { card = await request.json(); } catch { /* answered below */ }
  if (!goodCard(card)) return Response.json({ error: 'bad emote' }, { status: 400 });
  return Response.json({ error: deliver(sector, { from: card.from, ini: card.ini, e: card.e, to: card.to, r: card.r, tag: card.tag ?? null }, false) });
}

// Hands an emote to the player it's for, if they're here and take it; returns
// null, or why not. `local`: the sender is in this sector too. A hidden player
// only hears from those (they can see the caret anyway), and from their guild. The limits are kept
// here, where every emote for this player passes, in memory: a sector that
// hibernates forgets them, and the per-socket and per-address limits still hold.
export function deliver(sector, card, local) {
  const now = sector.now(), to = [];
  for (const [ws, p] of sector.everyone()) if (p.pid === card.to && (local || !p.hide || (card.tag && card.tag === p.tag))) to.push([ws, p]);
  if (!to.length) return 'gone';
  if (to.every(([, p]) => p.quiet)) return 'off';
  const inbox = (sector.inbox ??= new Map());
  const recent = (inbox.get(card.to) ?? []).filter((m) => now - m.t < PAIR_MS);
  if (recent.filter((m) => m.from === card.from).length >= PAIR_MAX) return 'slow down';
  if (recent.filter((m) => now - m.t < INBOX_MS).length >= INBOX_MAX) return 'busy';
  recent.push({ t: now, from: card.from });
  inbox.set(card.to, recent);
  if (inbox.size > 2000) for (const [pid, list] of inbox) if (!list.some((m) => now - m.t < PAIR_MS)) inbox.delete(pid);
  const frame = JSON.stringify({ t: 'emote', from: card.from, ini: card.ini, e: card.e, r: card.r });
  for (const [ws, p] of to) if (!p.quiet) try { ws.send(frame); } catch { /* closing */ }
  return null;
}
