// Players across devices. The games name a player by a random token kept in
// localStorage (`games.player`; see "Who a player is" in SURVEY.md), which
// lives on one device. A link carries it to another: the first device asks
// for a one-time code, shows it (as a code, a link and a QR code), and the
// other device redeems it for the token and a few settings, and is then the
// same player. See "One player, several devices" in SURVEY.md.
//
//   POST /v1/link                   {token, carry} → 201 {code, expires}
//   POST /v1/link/<code>/status     {token} → {state}: waiting, used or gone (gone to anyone who didn't make it)
//   POST /v1/link/<code>            {} → {token, carry}, once; then 404
//
// carry: {initials, guild: {code, name, tag} | null, muted: [ids], mutedAs: {id: [initials, at]}, emotes}
//   mutedAs: who each muted player was when muted, and when, for the game's Muted list
//
// A code is eight characters from the groups' alphabet (850 billion codes),
// good for LINK_MS and for one use. Making codes and trying them are each
// limited per address, so guessing one is hopeless. The token only ever
// travels in a request's body, never in an address.
//
// Linked devices then keep in step through a Player, a Durable Object per
// player id ("Syncing linked devices" in SURVEY.md): field notes, supernovas
// seen and the settings a link carries. Only a link starts one, so a player
// who never linked a device keeps everything in their browser.
//
//   POST /v1/player/sync    {token, epoch, since, finds, novas, settings, settingsAt}
//                           → {epoch, at, finds, novas, settings?, settingsAt?} | {off: true}
//   POST /v1/player/forget  {token} → {off: true}: everything kept for syncing goes,
//                           and the recovery code with it
//
// A recovery code brings a player back on any device, with no other device
// to hand ("A recovery code" in SURVEY.md). Saving one also keeps their notes
// in a Player, out of reach of the half-yearly clear-out.
//
//   POST /v1/recovery         {token} → 201 {code, made}: a new code; any older one stops working
//   POST /v1/recovery/use     {code} → {token}, or 404
//   POST /v1/recovery/remove  {token} → {ok}

import { CODE_ALPHABET, HttpError, INITIALS, corsHeaders, hashIp, json, rateLimit } from './leaderboard.js';
import { goodName } from './survey-guild.js';
import { GUILD_CODE, GUILD_TAG, PID, TOKEN, playerId } from './survey-social.js';

export const LINK_MS = 10 * 60000;        // a code lasts this long
export const LINK_CODE = /^[A-HJKMNP-Z2-9]{8}$/;
const MUTED_MAX = 200;
const MAX_BODY = 16384;  // a carry with MUTED_MAX mutes, and who they were, is about 10 KB
const LINK_PATH = /^\/v1\/link(?:\/([^/]{1,16})(\/status)?)?$/;

// Who a muted player was when muted, and when: [initials ('' for none), ms].
const goodMutedAs = (v) => Array.isArray(v) && v.length === 2 && (v[0] === '' || (typeof v[0] === 'string' && INITIALS.test(v[0])))
  && Number.isInteger(v[1]) && v[1] >= 0 && v[1] <= 1e15;

// The settings a link carries, checked and in a fixed shape, or null. An
// older game's `listed` (from when surveyors could keep off the list) is
// dropped, and mutedAs keeps only the players in muted.
export function cleanCarry(c) {
  if (!c || typeof c !== 'object') return null;
  const { initials = '', guild = null, muted = [], mutedAs = {}, emotes = true } = c;
  if (!(initials === '' || (typeof initials === 'string' && INITIALS.test(initials)))) return null;
  if (guild !== null && !(guild && typeof guild.code === 'string' && GUILD_CODE.test(guild.code) && goodName(guild.name) && typeof guild.tag === 'string' && GUILD_TAG.test(guild.tag))) return null;
  if (!Array.isArray(muted) || muted.length > MUTED_MAX || !muted.every((p) => typeof p === 'string' && PID.test(p))) return null;
  if (!mutedAs || typeof mutedAs !== 'object' || Array.isArray(mutedAs)) return null;
  const as = Object.entries(mutedAs);
  if (as.length > MUTED_MAX || !as.every(([p, v]) => PID.test(p) && goodMutedAs(v))) return null;
  if (typeof emotes !== 'boolean') return null;
  return {
    initials, guild: guild && { code: guild.code, name: guild.name, tag: guild.tag }, muted,
    mutedAs: Object.fromEntries(as.filter(([p]) => muted.includes(p)).map(([p, v]) => [p, [v[0], v[1]]])), emotes,
  };
}

async function readBody(request) {
  const text = await request.text();
  if (text.length > MAX_BODY) throw new HttpError(413, 'body too large');
  if (!text) return {};
  try { return JSON.parse(text); } catch { throw new HttpError(400, 'body must be JSON'); }
}

// The link paths, or null for any other.
export function routeLinks(request, env, now = Date.now()) {
  const url = new URL(request.url);
  const m = url.pathname.match(LINK_PATH);
  if (!m || !env.DB) return null;
  const cors = corsHeaders(request, env);
  return (async () => {
    try {
      if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
      if (request.method !== 'POST') throw new HttpError(405, 'method not allowed');
      if (!cors['Access-Control-Allow-Origin']) throw new HttpError(403, 'origin not allowed');
      const body = await readBody(request);
      const db = env.DB, address = await hashIp(request, env.IP_SALT);
      if (!m[1]) {
        if (typeof body?.token !== 'string' || !TOKEN.test(body.token)) throw new HttpError(400, 'token must be 32 hex digits');
        const carry = cleanCarry(body.carry ?? {});
        if (!carry) throw new HttpError(400, 'carry is not something a link takes');
        await rateLimit(db, 'link', address, now);
        await db.prepare('DELETE FROM links WHERE expires < ?').bind(now).run();
        for (let attempt = 0; attempt < 8; attempt++) {
          const code = [...crypto.getRandomValues(new Uint8Array(8))].map((b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
          const made = await db.prepare('INSERT INTO links (code, token, carry, expires) VALUES (?, ?, ?, ?) ON CONFLICT (code) DO NOTHING RETURNING code')
            .bind(code, body.token, JSON.stringify(carry), now + LINK_MS).first('code');
          if (made) return json({ code, expires: now + LINK_MS }, 201, cors);
        }
        throw new HttpError(503, 'could not pick a free code, try again');
      }
      const code = m[1].toUpperCase();
      if (m[2]) {
        // Only whoever made the code, who knows the token, hears what became of it.
        const row = LINK_CODE.test(code) && typeof body?.token === 'string'
          ? await db.prepare('SELECT token, expires, used FROM links WHERE code = ?').bind(code).first() : null;
        const state = !row || row.token !== body.token || row.expires < now ? 'gone' : row.used ? 'used' : 'waiting';
        return json({ state }, 200, cors);
      }
      // Every try counts, right or wrong, so codes can't be guessed.
      await rateLimit(db, 'linkTry', address, now);
      // One statement claims it, so two tries at once can't both have it; then what it carried goes.
      const row = LINK_CODE.test(code)
        ? await db.prepare('UPDATE links SET used = 1 WHERE code = ? AND used = 0 AND expires >= ? RETURNING token, carry').bind(code, now).first()
        : null;
      if (!row) throw new HttpError(404, 'no such code, or it has run out');
      await db.prepare("UPDATE links SET carry = '' WHERE code = ?").bind(code).run();
      // Linked devices keep in step from now on.
      if (env.PLAYERS) await playerStub(env, await playerId(row.token)).fetch('https://player/start', { method: 'POST', body: '{}' });
      return json({ token: row.token, carry: JSON.parse(row.carry) }, 200, cors);
    } catch (error) {
      if (error instanceof HttpError) return json({ error: error.message }, error.status, cors);
      throw error;
    }
  })();
}

/* ---------- Syncing linked devices ---------- */

export const FINDS_MAX = 25000;        // finds kept for one player, as many as the old Claude storage took
export const NOVAS_MAX = 1000;         // supernovas seen
export const SYNC_BATCH = 2000;        // finds (or supernovas) sent up in one sync; more wait for the next
export const SYNC_GAP_MS = 2000;       // one player's syncs, at most this often
export const KEEP_MS = 180 * 86400000; // what nobody has synced for this long is deleted
const MAX_SYNC_BODY = 512 * 1024;
const SYNC_PATH = /^\/v1\/player\/(sync|forget)$/;

const playerStub = (env, pid) => env.PLAYERS.get(env.PLAYERS.idFromName(pid));
const int = (v, max) => Number.isInteger(v) && Math.abs(v) < max;

// A find as the game keeps it ({w, x, y, d, t, s, f?, n?, b?}), checked for
// its shape: b is who charted it first when it wasn't this player (initials,
// or ? for someone unsigned). The game checks it's on the map when it takes
// it in.
export function cleanFind(o) {
  if (!o || typeof o !== 'object' || typeof o.w !== 'string' || !/^[A-Z]{3,12}$/.test(o.w)) return null;
  const { w, x, y, d, t, s } = o;
  if (!int(x, 1e9) || !int(y, 1e9) || !int(d, 8) || d < 0 || !Number.isFinite(t) || (s !== 0 && s !== 1)) return null;
  const f = o.f === 1 ? 1 : 0, n = f && int(o.n, 1e8) && o.n > 0 ? o.n : 0;
  const b = !f && typeof o.b === 'string' && (INITIALS.test(o.b) || o.b === '?') ? o.b : '';
  return { w, x, y, d, t: Math.round(t), s, ...(f ? { f } : {}), ...(n ? { n } : {}), ...(b ? { b } : {}) };
}
export const findKey = (f) => `${f.w}@${f.x},${f.y},${f.d}`;

// A supernova seen, as the game keeps it ({rx, ry, t, w, x, y, d, by, mine, solo}).
export function cleanNova(o) {
  if (!o || typeof o !== 'object' || typeof o.w !== 'string' || !/^[A-Z]{3,12}$/.test(o.w)) return null;
  const n = { rx: o.rx, ry: o.ry, t: o.t, w: o.w, x: o.x, y: o.y, d: o.d, by: typeof o.by === 'string' && INITIALS.test(o.by) ? o.by : '', mine: o.mine === true, solo: o.solo === true };
  return [n.rx, n.ry, n.x, n.y].every((v) => int(v, 1e9)) && int(n.t, 1e15) && int(n.d, 8) && n.d >= 0 ? n : null;
}

// One player's notes, kept for their linked devices. Each row has the
// version it last changed in; a device asks for what changed since the
// version it last heard, so a sync carries only what's new. The epoch is
// made when syncing starts, so a device that last heard from an earlier
// start (before a "forget") starts over rather than trusting its version.
// Empty storage is "off": never started, or forgotten.
export class Player {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.sql = ctx.storage.sql;
    this.now = () => Date.now();
  }

  meta() {
    if (!this.sql.exec("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'meta'").toArray().length) return null;
    return this.sql.exec('SELECT v, epoch, settings, settings_at, synced, kept, saved FROM meta WHERE id = 0').toArray()[0] ?? null;
  }

  start() {
    if (this.meta()) return;
    this.sql.exec('CREATE TABLE IF NOT EXISTS finds (k TEXT PRIMARY KEY, body TEXT NOT NULL, v INTEGER NOT NULL) WITHOUT ROWID');
    this.sql.exec('CREATE INDEX IF NOT EXISTS finds_v ON finds (v)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS novas (k TEXT PRIMARY KEY, body TEXT NOT NULL, v INTEGER NOT NULL) WITHOUT ROWID');
    this.sql.exec('CREATE INDEX IF NOT EXISTS novas_v ON novas (v)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY, v INTEGER NOT NULL, epoch TEXT NOT NULL, settings TEXT, settings_at INTEGER NOT NULL, synced INTEGER NOT NULL, kept INTEGER NOT NULL, saved INTEGER NOT NULL DEFAULT 0)');
    const epoch = [...crypto.getRandomValues(new Uint8Array(4))].map((b) => b.toString(16).padStart(2, '0')).join('');
    this.sql.exec('INSERT INTO meta (id, v, epoch, settings, settings_at, synced, kept) VALUES (0, 0, ?, NULL, 0, ?, 0)', epoch, this.now());
  }

  async forget() {
    await this.ctx.storage.deleteAlarm();
    await this.ctx.storage.deleteAll();
  }

  async sync(body) {
    const m = this.meta(), now = this.now();
    if (!m) return [{ off: true }, 200];
    if (now - m.synced < SYNC_GAP_MS) return [{ error: 'too soon' }, 429];
    const finds = Array.isArray(body.finds) ? body.finds : [], novas = Array.isArray(body.novas) ? body.novas : [];
    if (finds.length > SYNC_BATCH || novas.length > SYNC_BATCH) return [{ error: 'too many at once' }, 413];
    const since = body.epoch === m.epoch && Number.isInteger(body.since) && body.since >= 0 && body.since <= m.v ? body.since : 0;
    const v = m.v + 1;
    let wrote = false, count = null;
    for (const o of finds) {
      const f = cleanFind(o);
      if (!f) continue;
      const k = findKey(f), had = this.sql.exec('SELECT body FROM finds WHERE k = ?', k).toArray()[0];
      if (had) {
        // Charted first only ever comes on, and so does who charted it
        // otherwise, until it's this player's.
        const was = JSON.parse(had.body);
        if ((f.f && !was.f) || (f.b && !was.b && !was.f)) { this.sql.exec('UPDATE finds SET body = ?, v = ? WHERE k = ?', JSON.stringify(f), v, k); wrote = true; }
        continue;
      }
      count ??= this.sql.exec('SELECT COUNT(*) AS n FROM finds').one().n;
      if (count >= FINDS_MAX) continue;
      this.sql.exec('INSERT INTO finds (k, body, v) VALUES (?, ?, ?)', k, JSON.stringify(f), v);
      count++;
      wrote = true;
    }
    let novaCount = null;
    for (const o of novas) {
      const n = cleanNova(o);
      if (!n) continue;
      novaCount ??= this.sql.exec('SELECT COUNT(*) AS n FROM novas').one().n;
      if (novaCount >= NOVAS_MAX) break;
      if (this.sql.exec('INSERT INTO novas (k, body, v) VALUES (?, ?, ?) ON CONFLICT (k) DO NOTHING RETURNING k', `${n.rx},${n.ry}`, JSON.stringify(n), v).toArray().length) { novaCount++; wrote = true; }
    }
    // Settings: whichever device changed them last.
    const settings = body.settings === undefined ? null : cleanCarry(body.settings);
    let settingsAt = m.settings_at, kept = m.settings;
    if (settings && int(body.settingsAt, 1e15) && body.settingsAt > m.settings_at) { settingsAt = body.settingsAt; kept = JSON.stringify(settings); }
    const at = wrote ? v : m.v;
    const keep = now - m.kept > 86400000;  // put off the clear-out, once a day at most
    this.sql.exec('UPDATE meta SET v = ?, settings = ?, settings_at = ?, synced = ?, kept = ? WHERE id = 0', at, kept, settingsAt, now, keep ? now : m.kept);
    if (keep) await this.ctx.storage.setAlarm(now + KEEP_MS);
    const rows = (table) => this.sql.exec(`SELECT body FROM ${table} WHERE v > ? AND v != ? ORDER BY v`, since, v).toArray().map((r) => JSON.parse(r.body));
    const theirs = int(body.settingsAt, 1e15) ? body.settingsAt : 0;
    return [{
      epoch: m.epoch, at, finds: rows('finds'), novas: rows('novas'),
      ...(kept && settingsAt > theirs ? { settings: JSON.parse(kept), settingsAt } : {}),
    }, 200];
  }

  // Whether a recovery code is saved for this player: if so, the clear-out leaves it be.
  async save(on) {
    this.start();
    this.sql.exec('UPDATE meta SET saved = ? WHERE id = 0', on ? 1 : 0);
    if (!on) await this.ctx.storage.setAlarm(this.now() + KEEP_MS);
  }

  async alarm() {
    const m = this.meta();
    if (m?.saved) return;  // a saved recovery code keeps it; removing the code sets the alarm again
    if (!m || this.now() - m.synced >= KEEP_MS) return this.forget();
    await this.ctx.storage.setAlarm(m.synced + KEEP_MS);
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);
    let body = {};
    try { body = await request.json(); } catch { return Response.json({ error: 'bad request' }, { status: 400 }); }
    if (pathname === '/start') { this.start(); return Response.json({ ok: true }); }
    if (pathname === '/save') { await this.save(body.on === true); return Response.json({ ok: true }); }
    if (pathname === '/forget') { await this.forget(); return Response.json({ off: true }); }
    if (pathname === '/sync') { const [out, status] = await this.sync(body); return Response.json(out, { status }); }
    return Response.json({ error: 'not found' }, { status: 404 });
  }
}

// The sync paths, or null for any other. The token names the player, so
// only their own devices reach their notes.
export function routePlayers(request, env) {
  const m = new URL(request.url).pathname.match(SYNC_PATH);
  if (!m || !env.PLAYERS) return null;
  const cors = corsHeaders(request, env);
  return (async () => {
    try {
      if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
      if (request.method !== 'POST') throw new HttpError(405, 'method not allowed');
      if (!cors['Access-Control-Allow-Origin']) throw new HttpError(403, 'origin not allowed');
      const text = await request.text();
      if (text.length > MAX_SYNC_BODY) throw new HttpError(413, 'body too large');
      let body;
      try { body = JSON.parse(text); } catch { throw new HttpError(400, 'body must be JSON'); }
      if (typeof body?.token !== 'string' || !TOKEN.test(body.token)) throw new HttpError(400, 'token must be 32 hex digits');
      const { token, ...rest } = body;
      const pid = await playerId(token);
      // Stopping everywhere takes the recovery code too: there'd be nothing kept for it to bring back.
      if (m[1] === 'forget' && env.DB) await env.DB.prepare('DELETE FROM recovery WHERE pid = ?').bind(pid).run();
      const res = await playerStub(env, pid).fetch(`https://player/${m[1]}`, { method: 'POST', body: JSON.stringify(rest) });
      return json(await res.json(), res.status, cors);
    } catch (error) {
      if (error instanceof HttpError) return json({ error: error.message }, error.status, cors);
      throw error;
    }
  })();
}

/* ---------- Recovery codes ---------- */

export const RECOVERY_CODE = /^[A-HJKMNP-Z2-9]{20}$/;  // 31^20, about 99 bits
const RECOVERY_PATH = /^\/v1\/recovery(?:\/(use|remove))?$/;
const hex = (bytes) => [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');

// A code's row id and the key its token is sealed with, both from its SHA-512.
export async function recoveryKeys(code) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-512', new TextEncoder().encode(`games-recovery:${code}`)));
  const key = await crypto.subtle.importKey('raw', digest.slice(32), 'AES-GCM', false, ['encrypt', 'decrypt']);
  return { id: hex(digest.slice(0, 16)), key };
}

async function seal(key, token) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(token)));
  return btoa(String.fromCharCode(...iv, ...sealed));
}

async function unseal(key, box) {
  const bytes = Uint8Array.from(atob(box), (c) => c.charCodeAt(0));
  return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: bytes.slice(0, 12) }, key, bytes.slice(12)));
}

// The recovery paths, or null for any other.
export function routeRecovery(request, env, now = Date.now()) {
  const m = new URL(request.url).pathname.match(RECOVERY_PATH);
  if (!m || !env.DB || !env.PLAYERS) return null;
  const cors = corsHeaders(request, env);
  return (async () => {
    try {
      if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
      if (request.method !== 'POST') throw new HttpError(405, 'method not allowed');
      if (!cors['Access-Control-Allow-Origin']) throw new HttpError(403, 'origin not allowed');
      const body = await readBody(request);
      const db = env.DB, address = await hashIp(request, env.IP_SALT);
      if (m[1] === 'use') {
        // Every try counts, with link codes', right or wrong.
        await rateLimit(db, 'linkTry', address, now);
        const code = typeof body?.code === 'string' ? body.code.toUpperCase().replace(/[^A-Z0-9]/g, '') : '';
        if (!RECOVERY_CODE.test(code)) throw new HttpError(404, 'no such code');
        const { id, key } = await recoveryKeys(code);
        const row = await db.prepare('SELECT pid, box FROM recovery WHERE id = ?').bind(id).first();
        if (!row) throw new HttpError(404, 'no such code');
        const token = await unseal(key, row.box);
        await playerStub(env, row.pid).fetch('https://player/save', { method: 'POST', body: '{"on":true}' });
        return json({ token }, 200, cors);
      }
      if (typeof body?.token !== 'string' || !TOKEN.test(body.token)) throw new HttpError(400, 'token must be 32 hex digits');
      const pid = await playerId(body.token);
      if (m[1] === 'remove') {
        await db.prepare('DELETE FROM recovery WHERE pid = ?').bind(pid).run();
        await playerStub(env, pid).fetch('https://player/save', { method: 'POST', body: '{"on":false}' });
        return json({ ok: true }, 200, cors);
      }
      await rateLimit(db, 'recovery', address, now);
      const code = [...crypto.getRandomValues(new Uint8Array(20))].map((b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
      const { id, key } = await recoveryKeys(code);
      // One code a player: a new one replaces the old.
      await db.prepare('DELETE FROM recovery WHERE pid = ?').bind(pid).run();
      await db.prepare('INSERT INTO recovery (id, pid, box, made) VALUES (?, ?, ?, ?)').bind(id, pid, await seal(key, body.token), now).run();
      await playerStub(env, pid).fetch('https://player/save', { method: 'POST', body: '{"on":true}' });
      return json({ code, made: now }, 201, cors);
    } catch (error) {
      if (error instanceof HttpError) return json({ error: error.message }, error.status, cors);
      throw error;
    }
  })();
}
