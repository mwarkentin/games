// Letterfield's guilds: a few surveyors who want to find each other. Each
// guild is a Durable Object of its own (`Guild`, named by its code), holding
// its name and up to GUILD_MAX members with when each was last seen. See
// "Guilds" in SURVEY.md for the design and what it costs.
//
//   POST /v1/survey/guilds                 {token, initials, name: [a, b, c]}
//     → 201 {code, name, tag, members}     a new guild, with you in it
//   GET  /v1/survey/guilds/<code>          → {name, size}, to say what an invite is to
//   POST /v1/survey/guilds/<code>/join     {token, initials} → {code, name, tag, members}
//   POST /v1/survey/guilds/<code>/leave    {token} → {ok: true}; the last to leave ends it
//   POST /v1/survey/guilds/<code>/roster   {token} → {code, name, tag, members}, for members only
//     members are [[id, initials, seen], ...], most recently seen first
//
// No free text: a guild's name is three words from fixed lists, which the
// game keeps (GUILD_WORDS says how long each is), and its colour comes from
// the first. Joining needs the code, from an invite link; nobody browses guilds.
// The code stays secret among members: what everyone else can see is the
// guild's tag, a random id that only says which carets share a guild.
//
// Sectors check membership here (POST /check, internal) when a player's game
// names its guild, and again every GUILD_RECHECK_MS while they play, which is
// also how a member's "last seen" stays current. The Atlas keeps who's online
// in each guild from the reports sectors already send it (noteMates,
// matesFor), and sectors pass that on to members as {t: 'guild', tag, on}.

import { BLOCKED_INITIALS, CODE_ALPHABET, HttpError, INITIALS, corsHeaders, hashIp, json, rateLimit } from './leaderboard.js';
import { GUILD_CODE, GUILD_TAG, PID, TOKEN, playerId } from './survey-social.js';

export { GUILD_CODE, GUILD_TAG };
export const GUILD_MAX = 50;                 // members a guild holds
export const GUILD_WORDS = [16, 16, 8];      // the game's lists of words for names
export const GUILD_RECHECK_MS = 15 * 60000;  // a sector checks a playing member again this often
export const SEEN_MS = 10 * 60000;           // "last seen" is written at most this often
export const GUILD_TAGS_MAX = 100;           // guilds one report can ask about
const GUILDS_PATH = '/v1/survey/guilds';
const GUILD_PATH = /^\/v1\/survey\/guilds\/([^/]{1,16})(?:\/(join|leave|roster))?$/;
const MAX_BODY = 1024;

const isInt = (v, min, max) => Number.isInteger(v) && v >= min && v <= max;
const guildOf = (env, code) => env.GUILDS.get(env.GUILDS.idFromName(code));
const ask = (env, code, path, body) => guildOf(env, code).fetch(`https://guild${path}`, body === undefined ? undefined : { method: 'POST', body: JSON.stringify(body) });
export const goodName = (n) => Array.isArray(n) && n.length === 3 && n.every((v, i) => isInt(v, 0, GUILD_WORDS[i] - 1));

async function readBody(request) {
  const text = await request.text();
  if (text.length > MAX_BODY) throw new HttpError(413, 'body too large');
  try { return JSON.parse(text); } catch { throw new HttpError(400, 'body must be JSON'); }
}

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
  return (async () => {
    try {
      if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
      if (one && !GUILD_CODE.test(one[1])) throw new HttpError(404, 'unknown guild');
      if (one && !one[2] && request.method === 'GET') return json(await answer(await ask(env, one[1], '/info')), 200, cors);
      if (request.method !== 'POST') throw new HttpError(405, 'method not allowed');
      if (!cors['Access-Control-Allow-Origin']) throw new HttpError(403, 'origin not allowed');
      const body = await readBody(request);
      if (typeof body?.token !== 'string' || !TOKEN.test(body.token)) throw new HttpError(400, 'token must be 32 hex digits');
      const pid = await playerId(body.token);
      const initials = typeof body.initials === 'string' && INITIALS.test(body.initials) && !BLOCKED_INITIALS.has(body.initials) ? body.initials : null;
      const action = one ? one[2] : 'create';
      if ((action === 'create' || action === 'join') && !initials) throw new HttpError(400, 'pick initials first');
      if (action === 'create') {
        if (!goodName(body.name)) throw new HttpError(400, 'name must be three words from the lists');
        if (env.DB) await rateLimit(env.DB, 'guild', await hashIp(request, env.IP_SALT), now);
        for (let attempt = 0; attempt < 8; attempt++) {
          const code = [...crypto.getRandomValues(new Uint8Array(6))].map((b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
          const res = await ask(env, code, '/create', { pid, initials, name: body.name });
          if (res.status !== 409) return json({ code, ...(await answer(res)) }, 201, cors);
        }
        throw new HttpError(503, 'could not pick a free guild code, try again');
      }
      if (action === 'join' && env.DB) await rateLimit(env.DB, 'guildJoin', await hashIp(request, env.IP_SALT), now);
      const res = await ask(env, one[1], `/${action}`, { pid, initials });
      return json(action === 'leave' ? await answer(res) : { code: one[1], ...(await answer(res)) }, 200, cors);
    } catch (error) {
      if (error instanceof HttpError) return json({ error: error.message }, error.status, cors);
      throw error;
    }
  })();
}

// One guild. Its tables are made only when it's created, so a code someone
// guesses wrongly leaves nothing stored, and dropped when its last member
// leaves, which frees the code.
export class Guild {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.sql = ctx.storage.sql;
    this.now = () => Date.now();
  }

  meta() {
    if (!this.sql.exec("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'guild'").toArray().length) return null;
    return this.sql.exec('SELECT a, b, c, tag FROM guild WHERE id = 0').toArray()[0] ?? null;
  }

  members() {
    return this.sql.exec('SELECT pid, initials, seen FROM members ORDER BY seen DESC, pid').toArray().map((m) => [m.pid, m.initials, m.seen]);
  }

  whole(g) {
    return { name: [g.a, g.b, g.c], tag: g.tag, members: this.members() };
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
      this.sql.exec('CREATE TABLE IF NOT EXISTS guild (id INTEGER PRIMARY KEY CHECK (id = 0), a INTEGER NOT NULL, b INTEGER NOT NULL, c INTEGER NOT NULL, tag TEXT NOT NULL, created INTEGER NOT NULL)');
      this.sql.exec('CREATE TABLE IF NOT EXISTS members (pid TEXT PRIMARY KEY, initials TEXT NOT NULL, joined INTEGER NOT NULL, seen INTEGER NOT NULL) WITHOUT ROWID');
      const tag = [...crypto.getRandomValues(new Uint8Array(4))].map((b) => b.toString(16).padStart(2, '0')).join('');
      this.sql.exec('INSERT INTO guild (id, a, b, c, tag, created) VALUES (0, ?, ?, ?, ?, ?)', ...body.name, tag, now);
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
      return reply({ tag: g.tag });
    }
    return reply({ error: 'not found' }, 404);
  }
}

// A sector checking that one of its players is in the guild their game names,
// when it first does and every GUILD_RECHECK_MS after: the guild's tag goes on
// the socket (and so on their caret and in reports), or comes off it. A check
// that fails leaves things as they were and tries again on a later message.
export async function checkGuild(sector, ws, me) {
  if (!sector.env.GUILDS || !me.guild || !me.pid || me.checking) return;
  const code = me.guild;
  me.checking = true;
  let tag = me.tag ?? null;
  try {
    const res = await ask(sector.env, code, '/check', { pid: me.pid, initials: me.initials || null });
    if (res.ok) tag = (await res.json()).tag;
    else if (res.status === 404) tag = null;
    else return;
    me.guildAt = sector.now();
  } catch {
    return;
  } finally {
    me.checking = false;
  }
  if (me.guild !== code) return;  // the game named another guild while we asked
  if (typeof tag === 'string' && !GUILD_TAG.test(tag)) tag = null;
  if (tag === (me.tag ?? null)) return;
  me.tag = tag;
  sector.save(ws, me);
  sector.reportDue = true;
  sector.schedulePresence(false);
  const known = tag && sector.guildSent?.get(tag);
  if (known) try { ws.send(known); } catch { /* closing */ }
}

// What the Atlas said about guilds, passed on to the members here, but only
// what changed since the last time for each guild.
export function passMates(sector, guilds) {
  if (!guilds || typeof guilds !== 'object') return;
  sector.guildSent ??= new Map();
  for (const [tag, on] of Object.entries(guilds)) {
    if (!GUILD_TAG.test(tag) || !Array.isArray(on)) continue;
    const frame = JSON.stringify({ t: 'guild', tag, on });
    if (sector.guildSent.get(tag) === frame) continue;
    sector.guildSent.set(tag, frame);
    for (const [ws, p] of sector.everyone()) if (p.tag === tag) try { ws.send(frame); } catch { /* closing */ }
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
    if (!e[6]) continue;
    if (!atlas.mates.has(e[6])) atlas.mates.set(e[6], new Map());
    atlas.mates.get(e[6]).set(e[0], { e, key, at: now });
    named.push([e[6], e[0]]);
  }
  atlas.matesOf.set(key, named);
}

// Idle seconds as members see them: 0 while active (under 20 s), 20 for under
// a minute, then whole minutes. So a sector's frame for a guild changes, and
// goes out, when someone arrives, moves territory, leaves or idles another
// minute, not with every report.
export const idleShown = (s) => (s < 20 ? 0 : s < 60 ? 20 : Math.floor(s / 60) * 60);

// Who's online in each of these guilds: [[id, initials, rx, ry, idle], ...],
// from reports in the last `online` ms, with idle counted to now.
export function matesFor(atlas, tags, now, online) {
  const out = {};
  for (const tag of tags ?? []) {
    const m = atlas.mates?.get(tag);
    out[tag] = [];
    if (!m) continue;
    for (const [pid, { e, at }] of m) {
      if (now - at >= online) { m.delete(pid); continue; }
      out[tag].push([e[0], e[1], e[2], e[3], idleShown(e[4] + Math.round((now - at) / 1000))]);
    }
  }
  return out;
}
