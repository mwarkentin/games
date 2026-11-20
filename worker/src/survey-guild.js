// Letterfield's guilds: a few surveyors who want to find each other. Each
// guild is a Durable Object of its own (`Guild`, named by its code), holding
// its name and up to GUILD_MAX members with when each was last seen. See
// "Guilds" in SURVEY.md for the design and what it costs.
//
//   POST /v1/survey/guilds                 {token, initials, name: [a, b, c]}
//     → 201 {code, name, tag, lid, members}     a new guild, with you in it
//   GET  /v1/survey/guilds/<code>          → {name, size}, to say what an invite is to
//   POST /v1/survey/guilds/<code>/join     {token, initials} → {code, name, tag, lid, members}
//   POST /v1/survey/guilds/<code>/leave    {token} → {ok: true}; the last to leave ends it
//   POST /v1/survey/guilds/<code>/roster   {token} → {code, name, tag, lid, members}, for members only
//     members are [[id, initials, seen], ...], most recently seen first, and
//     lid is the guild's id in the survey log, for its page there
//
// No free text: a guild's name is three words from fixed lists, which the
// game keeps (GUILD_WORDS says how long each is), and its colour comes from
// the first. Joining needs the code, from an invite link; nobody browses guilds.
// The code stays secret among members: what everyone else can see is the
// guild's tag, a random id that only says which carets share a guild.
//
// A guild has a third id, its log id, for the survey log (survey-log.js):
// random again, so a guild's public page in the log can't be matched to the
// carets wearing its tag. A guild made before the log knew guilds gets one
// the first time it's asked.
//
// A surveyor can be in up to GUILDS_MAX guilds at once. That's the game's
// rule and the sectors': each guild knows only its own roster, and nothing
// here knows a player's other guilds.
//
// Sectors check membership here (POST /check, internal) when a player's game
// names a guild, and again every GUILD_RECHECK_MS for each while they play,
// which is also how a member's "last seen" stays current. The answer gives the tag; the
// log id, which the sector logs with each claim the member makes; and the
// name, which it keeps once for the log (Sector.noteGuild). The Atlas keeps
// who's online in each guild from the reports sectors already send it
// (noteMates, matesFor), and sectors pass that on to members as
// {t: 'guild', tag, on}, one frame per guild.

import { HttpError, INITIALS, allowedInitials, answered, corsHeaders, hashIp, isInt, json, mustPost, randomCode, randomHex, rateLimit, readBody } from './leaderboard.js';
import { FLAG_QUIET, GUILD_CODE, GUILD_LOG_ID, GUILD_TAG, GUILDS_MAX, PID, playerId, tagsOf, tokenIn, upgradeGuilds } from './survey-social.js';

export { GUILD_CODE, GUILD_LOG_ID, GUILD_TAG, GUILDS_MAX };
export const GUILD_MAX = 50;                 // members a guild holds
// The words of guilds' names, with the first word's hue, as the game's lists
// (GUILD_FIRST, GUILD_SECOND, GUILD_THIRD in letterfield.html; a test checks
// they match), so the survey log can name a guild without the game.
export const GUILD_FIRST = [['Crimson', 350], ['Coral', 8], ['Copper', 22], ['Amber', 38], ['Golden', 50], ['Lime', 85], ['Fern', 115], ['Emerald', 145],
  ['Jade', 165], ['Teal', 182], ['Azure', 200], ['Cobalt', 220], ['Indigo', 245], ['Violet', 270], ['Plum', 295], ['Rose', 325]];
export const GUILD_SECOND = ['Compass', 'Sextant', 'Lantern', 'Quill', 'Atlas', 'Meridian', 'Beacon', 'Theodolite', 'Chart', 'Lodestar', 'Spyglass', 'Waypoint', 'Ledger', 'Inkwell', 'Horizon', 'Contour'];
// A name is kept as its words' numbers, so a word changed here changes every
// guild that has it: word 6 was "Survey", which read like another survey
// beside the shared one. New words only ever go on the end.
export const GUILD_THIRD = ['Society', 'Guild', 'Company', 'Circle', 'Club', 'Expedition', 'Lodge', 'Fellowship', 'League', 'Order', 'Corps', 'Bureau', 'Institute', 'Academy', 'Alliance', 'Caravan'];
export const GUILD_WORDS = [GUILD_FIRST.length, GUILD_SECOND.length, GUILD_THIRD.length];
export const guildName = (n) => `${GUILD_FIRST[n[0]][0]} ${GUILD_SECOND[n[1]]} ${GUILD_THIRD[n[2]]}`;
export const guildHue = (n) => GUILD_FIRST[n[0]][1];
export const GUILD_RECHECK_MS = 15 * 60000;  // a sector checks a playing member again this often
export const GUILD_CHECKS = GUILDS_MAX * 2;  // checks one socket can set off at once,
export const GUILD_CHECK_REFILL_MS = GUILD_RECHECK_MS / GUILD_CHECKS;  // then one per this long: twice what rechecks take
export const GUILD_RETRY_MS = 30000;         // a check that failed is tried again after this long
export const SEEN_MS = 10 * 60000;           // "last seen" is written at most this often
export const GUILD_TAGS_MAX = 100;           // guilds one report can ask about
const GUILDS_PATH = '/v1/survey/guilds';
const GUILD_PATH = /^\/v1\/survey\/guilds\/([^/]{1,16})(?:\/(join|leave|roster))?$/;
const MAX_BODY = 1024;

const guildOf = (env, code) => env.GUILDS.get(env.GUILDS.idFromName(code));
const ask = (env, code, path, body) => guildOf(env, code).fetch(`https://guild${path}`, body === undefined ? undefined : { method: 'POST', body: JSON.stringify(body) });
export const goodName = (n) => Array.isArray(n) && n.length === 3 && n.every((v, i) => isInt(v, 0, GUILD_WORDS[i] - 1));

// What a guild's object answered, passed on, or its error as the Worker's.
async function answer(res) {
  const body = await res.json();
  if (!res.ok) throw new HttpError(res.status, body.error ?? 'guild error');
  return body;
}

// The guilds' paths, or null for any other. POSTs come from allowed origins
// only, as JSON sent as text/plain, and name the player by their token.
export function routeGuilds(request, env, now = Date.now()) {
  const url = new URL(request.url);
  const one = url.pathname.match(GUILD_PATH);
  if ((url.pathname !== GUILDS_PATH && !one) || !env.GUILDS) return null;
  const cors = corsHeaders(request, env);
  return answered(request, cors, async () => {
    if (one && !GUILD_CODE.test(one[1])) throw new HttpError(404, 'unknown guild');
    if (one && !one[2] && request.method === 'GET') return json(await answer(await ask(env, one[1], '/info')), 200, cors);
    mustPost(request, cors);
    const body = await readBody(request, MAX_BODY);
    const pid = await playerId(tokenIn(body));
    const initials = allowedInitials(body.initials) ? body.initials : null;
    const action = one ? one[2] : 'create';
    if ((action === 'create' || action === 'join') && !initials) throw new HttpError(400, 'pick initials first');
    if (action === 'create') {
      if (!goodName(body.name)) throw new HttpError(400, 'name must be three words from the lists');
      if (env.DB) await rateLimit(env.DB, 'guild', await hashIp(request, env.IP_SALT), now);
      for (let attempt = 0; attempt < 8; attempt++) {
        const code = randomCode(6);
        const res = await ask(env, code, '/create', { pid, initials, name: body.name });
        if (res.status !== 409) return json({ code, ...(await answer(res)) }, 201, cors);
      }
      throw new HttpError(503, 'could not pick a free guild code, try again');
    }
    if (action === 'join' && env.DB) await rateLimit(env.DB, 'guildJoin', await hashIp(request, env.IP_SALT), now);
    const res = await ask(env, one[1], `/${action}`, { pid, initials });
    return json(action === 'leave' ? await answer(res) : { code: one[1], ...(await answer(res)) }, 200, cors);
  });
}

// One guild. Its tables are made only when it's created, so a code someone
// guesses wrongly leaves nothing stored, and dropped when its last member
// leaves, which frees the code.
export class Guild {
  constructor(ctx, env) {
    this.sql = ctx.storage.sql;
    this.now = () => Date.now();
  }

  meta() {
    if (!this.sql.exec("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'guild'").toArray().length) return null;
    // A guild from before the log knew guilds has no log id yet: it gets one now.
    if (!this.lidReady) {
      try { this.sql.exec('SELECT lid FROM guild LIMIT 0'); } catch { this.sql.exec('ALTER TABLE guild ADD COLUMN lid TEXT'); }
      this.sql.exec('UPDATE guild SET lid = ? WHERE id = 0 AND lid IS NULL', randomHex(5));
      this.lidReady = true;
    }
    return this.sql.exec('SELECT a, b, c, tag, lid FROM guild WHERE id = 0').toArray()[0] ?? null;
  }

  members() {
    return this.sql.exec('SELECT pid, initials, seen FROM members ORDER BY seen DESC, pid').toArray().map((m) => [m.pid, m.initials, m.seen]);
  }

  whole(g) {
    return { name: [g.a, g.b, g.c], tag: g.tag, lid: g.lid, members: this.members() };
  }

  isMember(pid) {
    return this.sql.exec('SELECT initials, seen FROM members WHERE pid = ?', pid).toArray()[0] ?? null;
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);
    const reply = (body, status = 200) => Response.json(body, { status });
    let body = {};
    if (request.method === 'POST') { try { body = await request.json(); } catch { return reply({ error: 'bad request' }, 400); } }
    const pid = typeof body.pid === 'string' && PID.test(body.pid) ? body.pid : null;
    const initials = typeof body.initials === 'string' && INITIALS.test(body.initials) ? body.initials : null;
    const now = this.now();
    const g = this.meta();
    if (pathname === '/info' && request.method === 'GET') {
      if (!g) return reply({ error: 'unknown guild' }, 404);
      return reply({ name: [g.a, g.b, g.c], size: this.sql.exec('SELECT COUNT(*) AS n FROM members').one().n });
    }
    if (request.method !== 'POST' || !pid) return reply({ error: 'bad request' }, 400);
    if (pathname === '/create') {
      if (g) return reply({ error: 'code taken' }, 409);
      if (!initials || !goodName(body.name)) return reply({ error: 'bad request' }, 400);
      this.sql.exec('CREATE TABLE IF NOT EXISTS guild (id INTEGER PRIMARY KEY CHECK (id = 0), a INTEGER NOT NULL, b INTEGER NOT NULL, c INTEGER NOT NULL, tag TEXT NOT NULL, created INTEGER NOT NULL, lid TEXT)');
      this.sql.exec('CREATE TABLE IF NOT EXISTS members (pid TEXT PRIMARY KEY, initials TEXT NOT NULL, joined INTEGER NOT NULL, seen INTEGER NOT NULL) WITHOUT ROWID');
      this.sql.exec('INSERT INTO guild (id, a, b, c, tag, created, lid) VALUES (0, ?, ?, ?, ?, ?, ?)', ...body.name, randomHex(4), now, randomHex(5));
      this.sql.exec('INSERT INTO members (pid, initials, joined, seen) VALUES (?, ?, ?, ?)', pid, initials, now, now);
      return reply(this.whole(this.meta()), 201);
    }
    if (pathname === '/leave') {
      if (g && this.isMember(pid)) {
        this.sql.exec('DELETE FROM members WHERE pid = ?', pid);
        if (!this.sql.exec('SELECT COUNT(*) AS n FROM members').one().n) {
          this.sql.exec('DROP TABLE members');
          this.sql.exec('DROP TABLE guild');
        }
      }
      return reply({ ok: true });
    }
    if (!g) return reply({ error: 'unknown guild' }, 404);
    const member = this.isMember(pid);
    if (pathname === '/join') {
      if (!initials) return reply({ error: 'bad request' }, 400);
      if (member) this.sql.exec('UPDATE members SET initials = ?, seen = ? WHERE pid = ?', initials, now, pid);
      else if (this.sql.exec('SELECT COUNT(*) AS n FROM members').one().n >= GUILD_MAX) return reply({ error: 'guild is full' }, 409);
      else this.sql.exec('INSERT INTO members (pid, initials, joined, seen) VALUES (?, ?, ?, ?)', pid, initials, now, now);
      return reply(this.whole(g));
    }
    // The rest are for members only, and say nothing else to anyone who isn't one.
    if (!member) return reply({ error: 'not a member' }, 404);
    if (pathname === '/roster') return reply(this.whole(g));
    if (pathname === '/check') {
      if (now - member.seen >= SEEN_MS || (initials && initials !== member.initials)) {
        this.sql.exec('UPDATE members SET initials = ?, seen = ? WHERE pid = ?', initials ?? member.initials, now, pid);
      }
      return reply({ tag: g.tag, lid: g.lid, name: [g.a, g.b, g.c] });
    }
    return reply({ error: 'not found' }, 404);
  }
}

// A sector checking that one of its players is in each guild their game
// names, when it first does and every GUILD_RECHECK_MS after, each guild on
// its own clock: a guild that says yes puts its tag on the socket (and so on
// their caret and in reports), and one that says no takes it off, as when
// they left it on another device. A check that fails leaves that guild as it
// was and tries again on a message GUILD_RETRY_MS or more later. The checks
// that are out are kept in memory (sector.guildChecks, socket → codes), never
// on `me`, which is the socket's attachment: a sector that sleeps and wakes
// would otherwise read back a check that will never come back, and never
// check again. A socket can set off GUILD_CHECKS at once and one every
// GUILD_CHECK_REFILL_MS after (sector.guildBudget, in memory too), so a
// game that names new codes in every message can't turn each into five
// requests to guilds; the checks past that wait for a later message.
export function checkGuilds(sector, ws, me) {
  if (!sector.env.GUILDS || !me.pid) return [];
  const out = sector.guildChecks.get(ws), now = sector.now();
  const due = upgradeGuilds(me).filter((g) => !out?.has(g.code) && now - (g.at ?? 0) >= GUILD_RECHECK_MS);
  if (!due.length) return [];
  sector.guildBudget ??= new WeakMap();
  const budget = sector.guildBudget.get(ws) ?? { tokens: GUILD_CHECKS, at: now };
  budget.tokens = Math.min(GUILD_CHECKS, budget.tokens + (now - budget.at) / GUILD_CHECK_REFILL_MS);
  budget.at = now;
  sector.guildBudget.set(ws, budget);
  const go = due.slice(0, Math.max(0, Math.floor(budget.tokens)));
  budget.tokens -= go.length;
  return go.map((g) => checkGuild(sector, ws, me, g.code));
}

async function checkGuild(sector, ws, me, code) {
  if (!sector.guildChecks.has(ws)) sector.guildChecks.set(ws, new Set());
  const out = sector.guildChecks.get(ws);
  out.add(code);
  let tag, lid = null, name = null;
  // A failed check is tried again GUILD_RETRY_MS on, not with the very next
  // message: a guild that's struggling isn't asked by every member's every move.
  const retry = () => {
    const g = me.guilds?.find((x) => x.code === code);
    if (g) g.at = Math.max(g.at ?? 0, sector.now() - GUILD_RECHECK_MS + GUILD_RETRY_MS);
  };
  try {
    const res = await ask(sector.env, code, '/check', { pid: me.pid, initials: me.initials || null });
    if (res.ok) ({ tag, lid = null, name = null } = await res.json());
    else if (res.status === 404) tag = null;
    else return retry();
  } catch {
    return retry();
  } finally {
    out.delete(code);
    if (!out.size && sector.guildChecks.get(ws) === out) sector.guildChecks.delete(ws);
  }
  const g = me.guilds?.find((x) => x.code === code);
  if (!g) return;  // the game stopped naming it while we asked
  g.at = sector.now();  // only now, so a guild named afresh while we asked is checked on the next message
  if (typeof tag !== 'string' || !GUILD_TAG.test(tag)) tag = null;
  // The log id goes with the member's claims, and the guild's name to the log
  // with them (Sector.noteGuild), unless the tag came off.
  if (!tag || typeof lid !== 'string' || !GUILD_LOG_ID.test(lid)) lid = null;
  if (lid && goodName(name)) sector.noteGuild?.(lid, name);
  else lid = null;
  const tagChanged = tag !== (g.tag ?? null);
  g.tag = tag;
  g.lid = lid;
  sector.save(ws, me);
  if (!tagChanged) return;
  sector.reportDue = true;
  sector.schedulePresence(false);
  // The guild's last frame here, if others here carry its tag, so reports
  // have kept it current. If nobody else does, it may be from hours ago: the
  // next report's answer goes to them instead, as new.
  const known = tag && sector.guildSent?.get(tag);
  if (!known) return;
  const others = [...sector.everyone()].some(([other, p]) => other !== ws && tagsOf(p).includes(tag));
  if (!others) sector.guildSent.delete(tag);
  else try { ws.send(known); } catch { /* closing */ }
}

// What the Atlas said about guilds, passed on to the members here, but only
// what changed since the last time for each guild.
export function passMates(sector, guilds) {
  if (!guilds || typeof guilds !== 'object') return;
  sector.guildSent ??= new Map();
  let members = null;  // tag → its members' sockets here, made once, when a frame first needs sending
  for (const [tag, on] of Object.entries(guilds)) {
    if (!GUILD_TAG.test(tag) || !Array.isArray(on)) continue;
    const frame = JSON.stringify({ t: 'guild', tag, on });
    if (sector.guildSent.get(tag) === frame) continue;
    sector.guildSent.set(tag, frame);
    if (!members) {
      members = new Map();
      for (const [ws, p] of sector.everyone()) {
        for (const t of new Set(tagsOf(p))) { if (!members.has(t)) members.set(t, []); members.get(t).push(ws); }
      }
    }
    for (const ws of members.get(tag) ?? []) try { ws.send(frame); } catch { /* closing */ }
  }
}

// The Atlas's index of who's online in each guild, kept up to date from each
// report's surveyors: what a sector said last replaces what it said before.
export function noteMates(atlas, key, who, now) {
  atlas.mates ??= new Map();     // tag → Map(id → {e, key, at})
  atlas.matesOf ??= new Map();   // sector key → [[tag, id], ...] it last named
  for (const [tag, pid] of atlas.matesOf.get(key) ?? []) {
    const m = atlas.mates.get(tag);
    if (m?.get(pid)?.key === key) m.delete(pid);
    if (m && !m.size) atlas.mates.delete(tag);
  }
  const named = [];
  for (const e of who ?? []) {
    // A surveyor in several guilds is online in each; an older sector sent one tag rather than a list.
    for (const tag of typeof e[6] === 'string' ? [e[6]] : e[6] ?? []) {
      if (!atlas.mates.has(tag)) atlas.mates.set(tag, new Map());
      atlas.mates.get(tag).set(e[0], { e, key, at: now });
      named.push([tag, e[0]]);
    }
  }
  atlas.matesOf.set(key, named);
}

// Idle seconds as members see them: 0 while active (under 20 s), 20 for under
// a minute, then whole minutes. So a sector's frame for a guild changes, and
// goes out, when someone arrives, moves territory, leaves or idles another
// minute, not with every report.
export const idleShown = (s) => (s < 20 ? 0 : s < 60 ? 20 : Math.floor(s / 60) * 60);

// Who's online in each of these guilds: [[id, initials, rx, ry, idle, flags], ...],
// from reports in the last `online` ms, with idle counted to now. The flags are
// the public list's FLAG_QUIET, so the game shows a member who takes no emotes
// as it shows anyone else (an older game reads only the first five).
export function matesFor(atlas, tags, now, online) {
  const out = {};
  for (const tag of tags ?? []) {
    const m = atlas.mates?.get(tag);
    out[tag] = [];
    if (!m) continue;
    for (const [pid, { e, at }] of m) {
      if (now - at >= online) { m.delete(pid); continue; }
      out[tag].push([e[0], e[1], e[2], e[3], idleShown(e[4] + Math.round((now - at) / 1000)), e[5] & FLAG_QUIET]);
    }
  }
  return out;
}
