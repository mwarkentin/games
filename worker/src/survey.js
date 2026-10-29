// Letterfield's shared survey: everyone explores the same endless map, each
// word is credited to whoever circles it first, and players see each other
// wander. src/index.js routes to it and exports Sector as a Durable Object;
// tests import this module directly.
//
//   GET /v1/survey/<sx>/<sy>   WebSocket for one sector of the map
//
// The map is split into sectors of 4×4 territories (192×192 cells), and each
// sector is its own Durable Object: one single-threaded room that holds the
// sector's claims in its SQLite storage and every player's socket. A game
// joins the few sectors in view. Sharding by place is what lets this grow to
// thousands of players: no object sees more than the players near it. See
// SURVEY.md for the design and how far it scales.
//
// Messages are JSON. From the game:
//   {t: 'me', initials}             initials to credit claims to ('' for none)
//   {t: 'pos', x, y} / {t: 'pos', away: true}
//                                   where the player is looking, if in this sector
//   {t: 'claim', w, x, y, d}        a word the player just circled
// To the game:
//   {t: 'hello', you, sector, claims}   on joining; claims are [w, x, y, d, s, initials, at]
//   {t: 'claimed', c, by}           a new claim, to everyone; `by` is the claimer's id
//   {t: 'taken', c}                 to a claimer who wasn't first
//   {t: 'error', key, error}        to a claimer, for a word that isn't there
//   {t: 'presence', n, p}           players here ([id, initials, x, y]), about once a second

import { BLOCKED_INITIALS, INITIALS, corsHeaders } from './leaderboard.js';
import { CH, DIRS, RC, VOCAB, chunk, fdiv, keyOf, letterAt } from './letterfield-world.js';

export const SECTOR = RC * 4;         // cells per sector side
export const MAX_PLAYERS = 1000;      // sockets one sector accepts
export const PRESENCE_MS = 1000;      // how often positions go out
export const PRESENCE_MAX = 64;       // positions per update; `n` still counts everyone
export const CLAIM_BURST = 5;         // claims a socket can make at once,
export const CLAIM_REFILL_MS = 1500;  // then one per this many milliseconds
const MAX_MESSAGE = 256;
const LIMIT = 1e9;                    // the game's map runs to ±1e9 cells
export const SECTOR_PATH = /^\/v1\/survey\/(-?\d{1,7})\/(-?\d{1,7})$/;

const send = (ws, message) => { try { ws.send(JSON.stringify(message)); } catch { /* closing */ } };
const row = (r) => [r.w, r.x, r.y, r.d, r.s, r.initials, r.at];

// The word a claim names, checked against the map: {key, w, x, y, d, s} with
// s = 1 for a stray (a word the letters spell by chance), or {error}.
export function checkClaim(claim, sx, sy) {
  const { w, x, y, d } = claim ?? {};
  if (typeof w !== 'string' || !VOCAB.has(w)) return { error: 'not a Letterfield word' };
  if (![x, y].every((v) => Number.isInteger(v) && Math.abs(v) < LIMIT) || !Number.isInteger(d) || d < 0 || d > 7) {
    return { error: 'bad position' };
  }
  if (fdiv(x, SECTOR) !== sx || fdiv(y, SECTOR) !== sy) return { error: 'word starts in another sector' };
  const [dx, dy] = DIRS[d];
  for (let i = 0; i < w.length; i++) {
    if (letterAt(x + dx * i, y + dy * i) !== w.charCodeAt(i) - 65) return { error: 'word is not there' };
  }
  const key = keyOf(w, x, y, d);
  // Hidden words sit inside one chunk; strays count from four letters, as in the game.
  const placed = chunk(fdiv(x, CH), fdiv(y, CH)).words.some((p) => p.key === key);
  if (!placed && w.length < 4) return { error: 'word is not there' };
  return { key, w, x, y, d, s: placed ? 0 : 1 };
}

// Forwards a sector's WebSocket to its Durable Object, or returns null for any
// other path. CORS doesn't cover WebSockets, so the origin is checked here.
export function routeSurvey(request, env) {
  const m = new URL(request.url).pathname.match(SECTOR_PATH);
  if (!m || !env.SECTORS) return null;
  const text = (body, status) => new Response(body, { status, headers: { 'Content-Type': 'text/plain' } });
  if (request.method !== 'GET') return text('method not allowed', 405);
  if (!corsHeaders(request, env)['Access-Control-Allow-Origin']) return text('origin not allowed', 403);
  if (request.headers.get('Upgrade') !== 'websocket') return text('expected a WebSocket', 426);
  const name = `${Number(m[1])},${Number(m[2])}`;
  return env.SECTORS.get(env.SECTORS.idFromName(name)).fetch(request);
}

// One sector of the map. It uses the WebSocket Hibernation API: between
// messages the object can be evicted from memory while sockets stay open, so
// everything a socket needs is kept in its attachment, not on `this`.
export class Sector {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.sql = ctx.storage.sql;
    this.now = () => Date.now();
    this.presenceTimer = null;
    this.claimsJson = null;  // every claim as JSON, built on the first join after waking, then kept up to date
    this.sql.exec(`CREATE TABLE IF NOT EXISTS claims (
      key TEXT PRIMARY KEY, w TEXT NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL, d INTEGER NOT NULL,
      s INTEGER NOT NULL, initials TEXT NOT NULL, at INTEGER NOT NULL) WITHOUT ROWID`);
  }

  async fetch(request) {
    const m = new URL(request.url).pathname.match(SECTOR_PATH);
    if (!m) return new Response('not found', { status: 404 });
    if (request.headers.get('Upgrade') !== 'websocket') return new Response('expected a WebSocket', { status: 426 });
    if (this.ctx.getWebSockets().length >= MAX_PLAYERS) return new Response('sector is full', { status: 503 });
    const [client, server] = Object.values(new WebSocketPair());
    this.join(server, Number(m[1]), Number(m[2]));
    return new Response(null, { status: 101, webSocket: client });
  }

  join(ws, sx, sy) {
    this.ctx.acceptWebSocket(ws);
    const id = crypto.randomUUID().slice(0, 8);
    ws.serializeAttachment({ id, sx, sy, initials: '', x: null, y: null, moved: 0, tokens: CLAIM_BURST, refilled: this.now() });
    // When everyone reconnects at once (after a deploy, say), each join just
    // reuses the claims already turned into JSON.
    this.claimsJson ??= JSON.stringify(this.sql.exec('SELECT w, x, y, d, s, initials, at FROM claims').toArray().map(row));
    const hello = JSON.stringify({ t: 'hello', you: id, sector: [sx, sy], claims: [] });
    try { ws.send(hello.replace('"claims":[]', `"claims":${this.claimsJson}`)); } catch { /* closing */ }
  }

  async webSocketMessage(ws, message) {
    if (typeof message !== 'string' || message.length > MAX_MESSAGE) return;
    let msg;
    try { msg = JSON.parse(message); } catch { return; }
    const me = ws.deserializeAttachment();
    if (!me || !msg) return;
    if (msg.t === 'me') {
      const initials = typeof msg.initials === 'string' && INITIALS.test(msg.initials) && !BLOCKED_INITIALS.has(msg.initials) ? msg.initials : '';
      if (initials !== me.initials) { me.initials = initials; ws.serializeAttachment(me); this.schedulePresence(); }
    } else if (msg.t === 'pos') {
      const ok = [msg.x, msg.y].every((v) => Number.isFinite(v) && Math.abs(v) < LIMIT);
      if (msg.away || !ok) { me.x = null; me.y = null; }
      else { me.x = Math.round(msg.x * 10) / 10; me.y = Math.round(msg.y * 10) / 10; }
      me.moved = this.now();
      ws.serializeAttachment(me);
      this.schedulePresence();
    } else if (msg.t === 'claim') {
      this.claim(ws, me, msg);
    }
  }

  claim(ws, me, msg) {
    const now = this.now();
    const key = typeof msg.w === 'string' ? keyOf(msg.w, msg.x, msg.y, msg.d) : null;
    me.tokens = Math.min(CLAIM_BURST, me.tokens + (now - me.refilled) / CLAIM_REFILL_MS);
    me.refilled = now;
    if (me.tokens < 1) { ws.serializeAttachment(me); return send(ws, { t: 'error', key, error: 'slow down' }); }
    me.tokens -= 1;
    ws.serializeAttachment(me);
    const c = checkClaim(msg, me.sx, me.sy);
    if (c.error) return send(ws, { t: 'error', key, error: c.error });
    // The object handles one message at a time, so the first claim to arrive wins.
    const inserted = this.sql.exec(
      `INSERT INTO claims (key, w, x, y, d, s, initials, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (key) DO NOTHING RETURNING key`,
      c.key, c.w, c.x, c.y, c.d, c.s, me.initials, now,
    ).toArray().length;
    if (!inserted) {
      const first = this.sql.exec('SELECT w, x, y, d, s, initials, at FROM claims WHERE key = ?', c.key).one();
      return send(ws, { t: 'taken', c: row(first) });
    }
    const claimed = JSON.stringify([c.w, c.x, c.y, c.d, c.s, me.initials, now]);
    if (this.claimsJson) this.claimsJson = `${this.claimsJson.slice(0, -1)}${this.claimsJson === '[]' ? '' : ','}${claimed}]`;
    const frame = `{"t":"claimed","c":${claimed},"by":${JSON.stringify(me.id)}}`;
    for (const other of this.ctx.getWebSockets()) { try { other.send(frame); } catch { /* closing */ } }
  }

  async webSocketClose(ws) {
    try { ws.close(1000); } catch { /* already closed */ }
    this.schedulePresence();
  }

  async webSocketError() {
    this.schedulePresence();
  }

  here() {
    return this.ctx.getWebSockets().map((ws) => ws.deserializeAttachment()).filter((p) => p && p.x !== null);
  }

  // Positions go out together, at most once a second, however many players
  // move: that keeps the messages a sector sends proportional to its players,
  // not to its players squared.
  schedulePresence() {
    if (this.presenceTimer) return;
    this.presenceTimer = setTimeout(() => { this.presenceTimer = null; this.sendPresence(); }, PRESENCE_MS);
  }

  sendPresence() {
    const here = this.here().sort((a, b) => b.moved - a.moved);
    const frame = JSON.stringify({ t: 'presence', n: here.length, p: here.slice(0, PRESENCE_MAX).map((p) => [p.id, p.initials, p.x, p.y]) });
    for (const ws of this.ctx.getWebSockets()) { try { ws.send(frame); } catch { /* closing */ } }
  }
}
