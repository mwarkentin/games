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
// never the cell they're on. The Atlas builds one snapshot of everyone at
// most every LIST_MS, each Worker instance fetches it at most that often, and
// works out each page itself, so a crowd reading the list costs the Atlas one
// request per instance per LIST_MS.
//
// Emotes go from the sender's sector (the one under the middle of their view,
// which knows where they are) to the recipient's: there and then if that's the
// same sector, or with an internal POST (EMOTE_PATH) to the recipient's sector,
// which only Workers binding SECTORS can reach. The recipient's sector sees
// every emote its players get, from anywhere, so it holds the limits that
// protect them: a few a minute from one sender, and a cap from everyone.

import { HttpError, corsHeaders, hex, initialsOrNone, isInt, json, underLimit } from './leaderboard.js';
import { RC, fdiv } from '../../js/letterfield/world.js';

export const PID = /^[0-9a-f]{12}$/;     // a player, as everyone else knows them
export const TOKEN = /^[0-9a-f]{32}$/;   // the secret the game keeps, which only it and the sectors see
export const GUILD_CODE = /^[A-HJKMNP-Z2-9]{6}$/;  // a guild's secret code: groups' alphabet, two letters longer (survey-guild.js)
export const GUILD_TAG = /^[0-9a-f]{8}$/;          // a guild as anyone can see it: a random id
export const GUILD_LOG_ID = /^[0-9a-f]{10}$/;      // a guild in the survey log: another random id, never its tag
export const GUILDS_MAX = 5;                       // guilds a surveyor can be in at once ("Guilds" in SURVEY.md)
// The emotes, in the order the game shows them. Fixed drawings, never text:
// see "The emotes" in SURVEY.md for why each is here and what was left out.
export const EMOTES = ['wave', 'thanks', 'nice', 'clap', 'great', 'here', 'what'];
export const FLAG_QUIET = 1;             // a surveyor who takes no emotes (2 was for one off the list, which there no longer is)
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
export const TERR = 4;                   // territories per sector side (survey.js's SECTOR is RC * TERR)
export const send = (ws, message) => { try { ws.send(JSON.stringify(message)); } catch { /* closing */ } };
export const atlas = (env) => env.ATLAS.get(env.ATLAS.idFromName('atlas'));

// The Atlas's answer to `path`, asked at most once per `ms` by each Worker
// instance and shared; a failed ask isn't kept.
export function fromAtlas(cache, env, path, ms, read) {
  const now = Date.now();
  let cached = cache.get(env.ATLAS);
  if (!cached || now - cached.at > ms) {
    cached = { at: now, answer: atlas(env).fetch(`https://atlas${path}`).then((r) => (r.ok ? read(r) : Promise.reject(new Error(`atlas ${r.status}`)))) };
    cache.set(env.ATLAS, cached);
    cached.answer.catch(() => { if (cache.get(env.ATLAS) === cached) cache.delete(env.ATLAS); });
  }
  return cached.answer;
}

// A player's id from their token: 48 bits of its SHA-256, plenty to tell
// apart everyone who ever plays, and no use for finding the token.
export async function playerId(token) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`games-player:${token}`));
  return hex(digest).slice(0, 12);
}

// The token a request's body names its player by, or a 400.
export function tokenIn(body) {
  if (typeof body?.token !== 'string' || !TOKEN.test(body.token)) throw new HttpError(400, 'token must be 32 hex digits');
  return body.token;
}

// What a `me` message says besides initials: the player's token, whether
// they take emotes (quiet) and their guilds' codes, in the game's order, which
// the sector checks with each guild (checkGuilds in survey-guild.js) before
// that guild's tag goes on their socket. No more than GUILDS_MAX are taken:
// any past the cap are refused. An older game's `guild`, one code, counts as
// a list of one. The flags count straight away; the id once its hash is worked
// out. Returns (a promise of) whether anything changed. A socket keeps the
// first id it's given.
export function takeMe(me, msg) {
  const quiet = msg.quiet === true;  // an older game's `hide` asks for nothing now: everyone online is listed
  const named = Array.isArray(msg.guilds) ? msg.guilds : typeof msg.guild === 'string' ? [msg.guild] : [];
  const codes = [...new Set(named.filter((c) => typeof c === 'string' && GUILD_CODE.test(c)))].slice(0, GUILDS_MAX);
  const had = upgradeGuilds(me);
  let changed = quiet !== !!me.quiet || codes.join() !== had.map((g) => g.code).join();
  me.quiet = quiet;
  // A guild the game still names keeps what its check found; a new one starts unchecked.
  if (changed) me.guilds = codes.map((code) => had.find((g) => g.code === code) ?? { code, tag: null, lid: null, at: 0 });
  if (me.pid || typeof msg.token !== 'string' || !TOKEN.test(msg.token)) return changed;
  return playerId(msg.token).then((pid) => {
    if (!me.pid) { me.pid = pid; changed = true; }
    return changed;
  });
}

// A socket's guilds, as a sector keeps them in its attachment: [{code, tag,
// lid, at}] in the game's order, where tag and lid stay null until the guild
// says the player is a member, and `at` is when it last answered. One saved
// by an older version ({guild, tag, lid, guildAt}) comes back as a list of one.
export function upgradeGuilds(me) {
  if (!me.guilds && typeof me.guild === 'string') {
    me.guilds = [{ code: me.guild, tag: me.tag ?? null, lid: me.lid ?? null, at: me.guildAt ?? 0 }];
    delete me.guild; delete me.tag; delete me.lid; delete me.guildAt;
  }
  me.guilds ??= [];
  return me.guilds;
}

// The tags of the guilds that have said a socket's player is a member, in the game's order.
export const tagsOf = (me) => (me.guilds ?? []).flatMap((g) => (g.tag ? [g.tag] : []));
// The log ids a claim counts for: those same guilds', in the survey log.
export const lidsOf = (me) => (me.guilds ?? []).flatMap((g) => (g.tag && g.lid ? [g.lid] : []));

// The sector's surveyors for its report: everyone placed here who has an id,
// once each (a player with two tabs open is one), by territory, most recently
// moved first: [pid, initials, rx, ry, idle, flags], and the tags of their
// guilds for a member of any.
export function listed(people, sx, sy, now) {
  const by = new Map();
  for (const p of people) {
    if (p.x === null || p.x === undefined || !p.pid) continue;
    const rx = fdiv(Math.floor(p.x), RC), ry = fdiv(Math.floor(p.y), RC);
    if (fdiv(rx, TERR) !== sx || fdiv(ry, TERR) !== sy) continue;  // a position outside the sector says nothing true
    const had = by.get(p.pid);
    if (had && had.moved >= p.moved) continue;
    by.set(p.pid, p);
  }
  return [...by.values()].sort((a, b) => b.moved - a.moved).map((p) => [
    p.pid, p.initials, fdiv(Math.floor(p.x), RC), fdiv(Math.floor(p.y), RC),
    Math.min(IDLE_MAX, Math.max(0, Math.round((now - p.moved) / 1000))), p.quiet ? FLAG_QUIET : 0,
    ...(tagsOf(p).length ? [tagsOf(p)] : []),
  ]);
}

// A surveyor's guild tags in a report: a list of up to GUILDS_MAX, or the one an older sector sent.
const goodTags = (t) => (typeof t === 'string' && GUILD_TAG.test(t))
  || (Array.isArray(t) && t.length >= 1 && t.length <= GUILDS_MAX && t.every((v) => typeof v === 'string' && GUILD_TAG.test(v)));

// Whether a report's surveyors can be listed: each a player in the reporting sector.
export function goodWho(who, sx, sy, max) {
  if (who === undefined) return true;
  return Array.isArray(who) && who.length <= max && who.every((e) => Array.isArray(e) && (e.length === 6 || (e.length === 7 && goodTags(e[6])))
    && typeof e[0] === 'string' && PID.test(e[0]) && initialsOrNone(e[1])
    && Number.isInteger(e[2]) && Number.isInteger(e[3]) && fdiv(e[2], TERR) === sx && fdiv(e[3], TERR) === sy
    && isInt(e[4], 0, IDLE_MAX) && isInt(e[5], 0, 255));
}

// The Atlas's snapshot of everyone listed, from sectors that reported in the
// last `online` ms: each player once, from the latest report that has them
// (someone crossing into another sector can be in two for a few seconds),
// with idle counted to now. Grouped by sector, for working out pages. Every
// guild's tag stays out of it.
export function snapshot(rows, now, online) {
  const latest = new Map();
  for (const r of rows) {
    if (now - r.at >= online || !r.who?.length) continue;
    for (const e of r.who) {
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
export function nearest(snap, rx, ry, page, me = null) {
  const need = (page + 1) * LIST_PAGE;
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
  return { n, page, size: LIST_PAGE, more: n > need, who: near.slice(page * LIST_PAGE, need).map((x) => x.e) };
}

// GET /v1/survey/surveyors, or null for any other path. Each Worker instance
// asks the Atlas for its snapshot at most once per LIST_MS and shares it.
const listCache = new WeakMap();
export function routeSurveyors(request, env) {
  const url = new URL(request.url);
  if (url.pathname !== LIST_PATH || !env.ATLAS) return null;
  const cors = corsHeaders(request, env);
  if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405, cors);
  const r = /^(-?\d{1,9}),(-?\d{1,9})$/.exec(url.searchParams.get('r') ?? '');
  const page = Number(url.searchParams.get('page') ?? 0), me = url.searchParams.get('me');
  if (!r || !isInt(page, 0, LIST_PAGES - 1) || (me !== null && !PID.test(me))) return json({ error: 'bad request' }, 400, cors);
  return (async () => {
    const body = nearest(await fromAtlas(listCache, env, ATLAS_LIST_PATH, LIST_MS, (res) => res.json()), Number(r[1]), Number(r[2]), page, me);
    return json(body, 200, { ...cors, 'Cache-Control': `public, max-age=${LIST_MS / 1000}` });
  })();
}

// An emote from one of this sector's sockets: {t: 'emote', to, e, s}, to the
// player `to`, whom the sender saw in sector s. The sender is who their socket
// says, never who the message says. Answered with {t: 'emoted', to, e} and
// ok, or why not: 'sign first' (no id or initials yet), 'slow down', 'gone'
// (not there), 'off' (they take no
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
  if (!(await underLimit(sector.env.SURVEY_EMOTES, me.address))) return answer('slow down');
  const [sx, sy] = sector.coords();
  // Where the sender is, by territory, for the recipient's "fly there".
  const r = me.x === null || me.x === undefined ? null : [fdiv(Math.floor(me.x), RC), fdiv(Math.floor(me.y), RC)];
  const card = { from: me.pid, ini: me.initials, e, to, r };
  if (s[0] === sx && s[1] === sy) return answer(deliver(sector, card));
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
  && EMOTES.includes(c.e) && initialsOrNone(c.ini)
  && (c.r === null || (Array.isArray(c.r) && c.r.length === 2 && c.r.every((v) => isInt(v, -1e8, 1e8))));

// POST EMOTE_PATH: an emote another sector passes on, for a player here.
export async function takeEmote(sector, request) {
  let card = null;
  try { card = await request.json(); } catch { /* answered below */ }
  if (!goodCard(card)) return Response.json({ error: 'bad emote' }, { status: 400 });
  return Response.json({ error: deliver(sector, { from: card.from, ini: card.ini, e: card.e, to: card.to, r: card.r }) });
}

// Hands an emote to the player it's for, if they're here and take it; returns
// null, or why not. The limits are kept here, where every emote for this
// player passes, in memory: a sector that hibernates forgets them, and the
// per-socket and per-address limits still hold.
export function deliver(sector, card) {
  const now = sector.now(), to = [];
  for (const [ws, p] of sector.everyone()) if (p.pid === card.to) to.push([ws, p]);
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
