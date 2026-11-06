// Letterfield's shared survey: everyone explores the same endless map, each
// word is credited to whoever circles it first, and players see each other
// wander. src/index.js routes to it and exports Sector and Atlas as Durable
// Objects; tests import this module directly.
//
//   GET /v1/survey/<sx>/<sy>   WebSocket for one sector of the map
//   GET /v1/survey/world       the world map: charted territories, players, where to start
//   POST /v1/survey/pass       a Turnstile token for a pass that sector joins need (survey-pass.js),
//                              only while TURNSTILE_SECRET is set
//
// The map is split into sectors of 4×4 territories (192×192 cells), and each
// sector is its own Durable Object: one single-threaded room that holds the
// sector's claims in its SQLite storage and every player's socket. A game
// joins the few sectors in view. Sharding by place is what lets this grow to
// thousands of players: no object sees more than the players near it.
//
// The middle of the map, 100×100 territories around the origin, is the world
// everyone charts together: it hides 1,120,206 words. One Atlas object keeps
// the totals and the world map. Sectors in that area report their numbers to
// it every few seconds while busy; players only read its cached world map.
//
// Cost: a Durable Object is billed for every second it holds a pending timer,
// because it can't hibernate, but otherwise only for the time it spends
// running. So a sector sends owed positions, claims and reports with the next
// message that arrives once they're due, rather than on timers. While people
// are moving there's always a next message; the only timers are short ones in
// quiet sectors, for something that might be the last thing to happen there
// (a player leaving, a claim). See SURVEY.md for the design and how far it
// scales.
//
// Messages are JSON. From the game:
//   {t: 'me', initials}             initials to credit claims to ('' for none)
//   {t: 'pos', x, y} / {t: 'pos', away: true}
//                                   where the player is looking, if in this sector
//   {t: 'claim', w, x, y, d}        a word the player just circled
// To the game (a frame may also be a JSON array of these, sent together):
//   {t: 'hello', you, sector, claims}   on joining; claims are [w, x, y, d, s, initials, at]
//   {t: 'claimed', c, by}           a new claim, to everyone; `by` is the claimer's id
//   {t: 'taken', c}                 to a claimer who wasn't first
//   {t: 'error', key, error}        to a claimer, for a word that isn't there, 'slow down'
//                                   when the socket or its address claims too fast, or
//                                   'daily limit' once its address has charted DAILY_CLAIMS today
//   {t: 'presence', n, p}           players here ([id, initials, x, y]), about once a second
//   {t: 'world', charted, total, players}   the whole world's totals, as they change
//   {t: 'unverified'}               from the Worker, while TURNSTILE_REQUIRED is "true", for a join
//                                   without a good pass, which then
//                                   closes with code 4001: the game gets a new pass and retries
//   {t: 'full', world}              no room in the sector (or, with world: true, in the whole
//                                   survey), or the player's address holds or opens too many
//                                   sockets; the socket then closes with code 4000
//
// Limits per address (see "Bots" in SURVEY.md): the Worker hands each sector
// a salted hash of the player's IP address, never the address itself. A
// sector takes at most ADDRESS_SOCKETS sockets from one address, and two
// rate-limiting bindings, set in wrangler.toml, count joins and claims per
// address across every sector. For a daily cap, sectors in the shared world
// add each address's charted words to their reports, and the Atlas answers
// with the addresses past DAILY_CLAIMS today, which every sector then refuses.

import { BLOCKED_INITIALS, INITIALS, corsHeaders, hashAddress, json } from './leaderboard.js';
import { PASS_PATH, checkPass, handlePass } from './survey-pass.js';
import { CH, DIRS, RC, VOCAB, chunk, fdiv, keyOf, letterAt } from './letterfield-world.js';

export const SECTOR = RC * 4;         // cells per sector side
export const MAX_PLAYERS = 750;       // sockets one sector accepts (bench/load.js: one sector saturates between 750 and 1,000)
export const PRESENCE_MS = 1000;      // how often positions go out
export const BATCH_MS = 200;          // claims go out together at most this often
export const PRESENCE_MAX = 64;       // positions per update; `n` still counts everyone
export const CLAIM_BURST = 5;         // claims a socket can make at once,
export const CLAIM_REFILL_MS = 1500;  // then one per this many milliseconds
export const AREA = 12;               // the shared world: sectors -12 to 12 each way
export const AREA_WORDS = 1120206;    // hidden words in it (test/survey.test.js recounts them)
export const REPORT_MS = 10000;       // a busy sector reports to the atlas at most this often
export const SAVE_MS = 60000;         // the atlas writes changed numbers to storage at most this often
export const VIEW_MS = 5000;          // the world map is rebuilt, and cached, for this long
export const ONLINE_MS = 2 * 60000;   // players count as online this long after their sector reported them
export const SPAWN_MAX = 300;         // new players join the biggest crowd with fewer players than this
export const MAX_ONLINE = 25000;      // players the whole survey takes at once: a ceiling on the bill
export const QUIET = 32;              // a sector with fewer sockets than this sets short timers
export const SAVE_POS_MS = 5000;      // a moving player's position is saved to their socket this often
export const ADDRESS_SOCKETS = 40;    // sockets one address can hold in one sector (a classroom shares an address)
export const ADDRESS_HEADER = 'X-Survey-Address';  // the hashed address, from the Worker to the sector
export const UNPASSED_HEADER = 'X-Survey-Unpassed';  // '1' on a join without a good Turnstile pass, from the Worker
export const DAILY_CLAIMS = 300;      // words one address can chart in the shared world each UTC day
export const DAILY_LIST_MAX = 2000;   // addresses past the daily cap that the Atlas hands out, latest first
const DAY_MS = 86400000;
const HASH = /^[0-9a-f]{64}$/;
const TERR = SECTOR / RC;             // territories per sector side
const MAX_MESSAGE = 256;
const LIMIT = 1e9;                    // the game's map runs to ±1e9 cells
export const SECTOR_PATH = /^\/v1\/survey\/(-?\d{1,7})\/(-?\d{1,7})$/;
export const WORLD_PATH = '/v1/survey/world';

const send = (ws, message) => { try { ws.send(JSON.stringify(message)); } catch { /* closing */ } };
const broadcast = (ctx, frame) => { for (const ws of ctx.getWebSockets()) { try { ws.send(frame); } catch { /* closing */ } } };
const row = (r) => [r.w, r.x, r.y, r.d, r.s, r.initials, r.at];
const isInt = (v, min, max) => Number.isInteger(v) && v >= min && v <= max;
export const inArea = (sx, sy) => Math.abs(sx) <= AREA && Math.abs(sy) <= AREA;
const atlas = (env) => env.ATLAS.get(env.ATLAS.idFromName('atlas'));

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

// Answers the survey's paths, or returns null for any other path: a sector's
// WebSocket goes to its Durable Object, and the world map comes from the
// Atlas through a short cache. CORS doesn't cover WebSockets, so the origin
// is checked here. With TURNSTILE_SECRET set, POST /v1/survey/pass hands out
// passes (see survey-pass.js and TURNSTILE.md). A join without a good pass is
// turned away only when TURNSTILE_REQUIRED is "true"; until then it goes
// ahead, marked so its sector counts it.
export function routeSurvey(request, env) {
  const url = new URL(request.url);
  const m = url.pathname.match(SECTOR_PATH);
  const world = url.pathname === WORLD_PATH;
  const passing = url.pathname === PASS_PATH;
  if (!(m && env.SECTORS) && !(world && env.ATLAS) && !(passing && env.SECTORS)) return null;
  const cors = corsHeaders(request, env);
  const text = (body, status) => new Response(body, { status, headers: { ...cors, 'Content-Type': 'text/plain' } });
  if (passing) {
    if (request.method !== 'POST') return text('method not allowed', 405);
    return addressHash(request, env).then((address) => handlePass(request, env, address, cors, json));
  }
  if (request.method !== 'GET') return text('method not allowed', 405);
  if (world) return worldMap(env, cors);
  if (!cors['Access-Control-Allow-Origin']) return text('origin not allowed', 403);
  if (request.headers.get('Upgrade') !== 'websocket') return text('expected a WebSocket', 426);
  const name = `${Number(m[1])},${Number(m[2])}`;
  return (async () => {
    const address = await addressHash(request, env);
    const unpassed = !!env.TURNSTILE_SECRET && !(await checkPass(env.TURNSTILE_SECRET, address, url.searchParams.get('pass')));
    if (unpassed && turnstileRequired(env)) return unverified();
    // The pass stays here: the sector only needs the path, the address and
    // whether the join had a pass. The Worker sets both headers itself, so a
    // player can't choose either.
    url.search = '';
    const headers = new Headers(request.headers);
    headers.set(ADDRESS_HEADER, address);
    headers.delete(UNPASSED_HEADER);
    if (unpassed) headers.set(UNPASSED_HEADER, '1');
    return env.SECTORS.get(env.SECTORS.idFromName(name)).fetch(new Request(url, { headers }));
  })();
}

// Whether joins without a pass are turned away: a var in wrangler.toml, so
// passes can be handed out (and joins without one counted) before anyone is
// refused.
export const turnstileRequired = (env) => env.TURNSTILE_REQUIRED === true || env.TURNSTILE_REQUIRED === 'true';

// A join without a good pass, while passes are required, is answered by the Worker itself, without waking
// the sector, and in words the game can read: a browser learns nothing from a
// refused WebSocket upgrade.
function unverified() {
  const [client, server] = Object.values(new WebSocketPair());
  server.accept();
  send(server, { t: 'unverified' });
  server.close(4001, 'survey pass needed');
  return new Response(null, { status: 101, webSocket: client });
}

// The player's address as the survey counts it, salted and hashed. The
// Worker sets the header the sector reads itself, so a player can't choose
// their own.
const addressHash = (request, env) => hashAddress(addressOf(request.headers.get('CF-Connecting-IP') || 'unknown'), env.IP_SALT);

// The part of an IP address that names one household or device: all of an
// IPv4 address, or the /64 network of an IPv6 one, since a device can pick
// any address in its /64 and change it at will.
export function addressOf(ip) {
  if (!ip.includes(':')) return ip;
  const [head, tail] = ip.toLowerCase().split('::');
  const before = head ? head.split(':') : [];
  const after = tail === undefined ? [] : tail ? tail.split(':') : [];
  const groups = tail === undefined ? before : [...before, ...Array(Math.max(0, 8 - before.length - after.length)).fill('0'), ...after];
  const prefix = groups.slice(0, 4).map((g) => parseInt(g, 16));
  return prefix.length === 4 && prefix.every((g) => g >= 0 && g <= 0xffff) ? `${prefix.map((g) => g.toString(16)).join(':')}::/64` : ip;
}

// Each Worker instance asks the Atlas for the world map at most once per
// VIEW_MS and shares the answer, so players checking the map can't swamp it.
const worldCache = new WeakMap();
async function worldMap(env, cors) {
  const now = Date.now();
  let cached = worldCache.get(env.ATLAS);
  if (!cached || now - cached.at > VIEW_MS) {
    cached = { at: now, body: atlas(env).fetch('https://atlas/world').then((r) => (r.ok ? r.text() : Promise.reject(new Error(`atlas ${r.status}`)))) };
    worldCache.set(env.ATLAS, cached);
    cached.body.catch(() => { if (worldCache.get(env.ATLAS) === cached) worldCache.delete(env.ATLAS); });
  }
  return new Response(await cached.body, {
    headers: { ...cors, 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': `public, max-age=${VIEW_MS / 1000}` },
  });
}

// One sector of the map. It uses the WebSocket Hibernation API: between
// messages the object can be evicted from memory while sockets stay open, so
// everything a socket needs is kept in its attachment. Reading and writing
// attachments is the most expensive thing a busy sector does, though, so the
// players are also kept in memory (`people`): positions, which change every
// second or two, are written to the attachment at most every SAVE_POS_MS.
export class Sector {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.sql = ctx.storage.sql;
    this.now = () => Date.now();
    this.batch = [];         // claims waiting to go out together
    this.batchAt = 0;
    this.batchTimer = null;
    this.presenceTimer = null;
    this.presenceAt = 0;     // when positions last went out
    this.presenceDue = false;
    this.reportedAt = 0;     // when the Atlas last heard from this sector
    this.reportDue = false;
    this.reporting = false;
    this.hot = null;         // [x, y] of the latest claim, for where new players land when nobody's placed
    this.where = null;       // [sx, sy], from the first socket to join or wake it
    this.claimsJson = null;  // every claim as JSON, built on the first join after waking, then kept up to date
    this.counts = null;      // hidden words charted in each of the sector's 16 territories, likewise
    this.world = null;       // the last totals the Atlas sent back
    this.people = null;      // socket → its attachment, read from the sockets on first use after waking
    this.chartedBy = new Map();  // address → words it charted here since the last report
    this.unpassed = 0;           // joins without a Turnstile pass since the last report (a bot signal)
    this.overDay = -1;       // the UTC day `over` is for
    this.over = new Set();   // addresses past the daily cap today, as the Atlas last said
    this.overAt = 0;         // how many the Atlas had counted then; it only resends the list when this changes
    this.sql.exec(`CREATE TABLE IF NOT EXISTS claims (
      key TEXT PRIMARY KEY, w TEXT NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL, d INTEGER NOT NULL,
      s INTEGER NOT NULL, initials TEXT NOT NULL, at INTEGER NOT NULL) WITHOUT ROWID`);
  }

  async fetch(request) {
    const m = new URL(request.url).pathname.match(SECTOR_PATH);
    if (!m) return new Response('not found', { status: 404 });
    if (request.headers.get('Upgrade') !== 'websocket') return new Response('expected a WebSocket', { status: 426 });
    const [client, server] = Object.values(new WebSocketPair());
    const address = request.headers.get(ADDRESS_HEADER) || null;
    if (request.headers.get(UNPASSED_HEADER) === '1') { this.unpassed++; this.reportDue = true; }
    if (this.world && this.world.players >= MAX_ONLINE) this.turnAway(server, true);
    else if (this.ctx.getWebSockets().length >= MAX_PLAYERS) this.turnAway(server, false);
    else if (address && this.fromAddress(address) >= ADDRESS_SOCKETS) this.turnAway(server, false);
    else if (!(await this.allowed('SURVEY_JOINS', address))) this.turnAway(server, false);
    else this.join(server, Number(m[1]), Number(m[2]), address);
    return new Response(null, { status: 101, webSocket: client });
  }

  fromAddress(address) {
    let n = 0;
    for (const p of this.everyone().values()) if (p.address === address) n++;
    return n;
  }

  // Asks one of the per-address rate limiters (wrangler.toml) whether to go
  // ahead. Without the binding, or if it fails, the answer is yes: the limits
  // per socket and per sector still hold.
  async allowed(binding, address) {
    const limiter = this.env[binding];
    if (!limiter || !address) return true;
    try { return (await limiter.limit({ key: address })).success !== false; } catch { return true; }
  }

  // A full sector (or survey) still answers, so the game can say why it isn't joining.
  turnAway(ws, world) {
    ws.accept();
    send(ws, { t: 'full', world });
    ws.close(4000, world ? 'survey is full' : 'sector is full');
  }

  join(ws, sx, sy, address = null) {
    this.ctx.acceptWebSocket(ws);
    this.where ??= [sx, sy];
    const id = crypto.randomUUID().slice(0, 8);
    const me = { id, sx, sy, address, initials: '', x: null, y: null, moved: 0, saved: 0, tokens: CLAIM_BURST, refilled: this.now() };
    ws.serializeAttachment(me);
    this.everyone().set(ws, me);
    // When everyone reconnects at once (after a deploy, say), each join just
    // reuses the claims already turned into JSON.
    this.claimsJson ??= JSON.stringify(this.sql.exec('SELECT w, x, y, d, s, initials, at FROM claims').toArray().map(row));
    const hello = JSON.stringify({ t: 'hello', you: id, sector: [sx, sy], claims: [] });
    try { ws.send(hello.replace('"claims":[]', `"claims":${this.claimsJson}`)); } catch { /* closing */ }
    if (this.world) send(ws, { t: 'world', ...this.world });
  }

  everyone() {
    if (!this.people) {
      this.people = new Map();
      for (const ws of this.ctx.getWebSockets()) { const me = ws.deserializeAttachment(); if (me) this.people.set(ws, me); }
    }
    return this.people;
  }

  person(ws) {
    let me = this.everyone().get(ws);
    if (!me && (me = ws.deserializeAttachment())) this.people.set(ws, me);
    return me;
  }

  coords() {
    if (!this.where) {
      const first = this.ctx.getWebSockets()[0]?.deserializeAttachment();
      if (first) this.where = [first.sx, first.sy];
    }
    return this.where;
  }

  async webSocketMessage(ws, message) {
    if (typeof message !== 'string' || message.length > MAX_MESSAGE) return;
    let msg;
    try { msg = JSON.parse(message); } catch { return; }
    const me = this.person(ws);
    if (!me || !msg) return;
    if (msg.t === 'me') {
      const initials = typeof msg.initials === 'string' && INITIALS.test(msg.initials) && !BLOCKED_INITIALS.has(msg.initials) ? msg.initials : '';
      if (initials !== me.initials) { me.initials = initials; this.save(ws, me); this.schedulePresence(false); }
    } else if (msg.t === 'pos') {
      const ok = [msg.x, msg.y].every((v) => Number.isFinite(v) && Math.abs(v) < LIMIT);
      const away = msg.away || !ok;
      if (away) { me.x = null; me.y = null; }
      else { me.x = Math.round(msg.x * 10) / 10; me.y = Math.round(msg.y * 10) / 10; }
      me.moved = this.now();
      if (away || me.moved - me.saved >= SAVE_POS_MS) this.save(ws, me);
      this.schedulePresence(away);
    } else if (msg.t === 'claim') {
      await this.claim(ws, me, msg);
    }
    this.catchUp();
  }

  async claim(ws, me, msg) {
    const now = this.now();
    const key = typeof msg.w === 'string' ? keyOf(msg.w, msg.x, msg.y, msg.d) : null;
    me.tokens = Math.min(CLAIM_BURST, me.tokens + (now - me.refilled) / CLAIM_REFILL_MS);
    me.refilled = now;
    if (me.tokens < 1) { this.save(ws, me); return send(ws, { t: 'error', key, error: 'slow down' }); }
    me.tokens -= 1;
    this.save(ws, me);
    // Every claim from the address counts, wherever it's made, so more
    // sockets in more sectors don't let a script claim any faster.
    if (!(await this.allowed('SURVEY_CLAIMS', me.address))) return send(ws, { t: 'error', key, error: 'slow down' });
    if (me.address && this.overToday().has(me.address)) return send(ws, { t: 'error', key, error: 'daily limit' });
    const c = checkClaim(msg, me.sx, me.sy);
    if (c.error) return send(ws, { t: 'error', key, error: c.error });
    // The insert runs as one statement with nothing awaited, so even if
    // another claim ran while the limiter answered, the first to get here wins.
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
    if (this.counts && !c.s) this.counts[this.territory(c.x, c.y)]++;
    this.hot = [c.x, c.y];
    if (me.address && inArea(...this.coords())) this.chartedBy.set(me.address, (this.chartedBy.get(me.address) ?? 0) + 1);
    this.batch.push(`{"t":"claimed","c":${claimed},"by":${JSON.stringify(me.id)}}`);
    this.sendBatch();
    this.maybeReport();
  }

  async webSocketClose(ws) {
    try { ws.close(1000); } catch { /* already closed */ }
    this.people?.delete(ws);
    this.left();
  }

  async webSocketError(ws) {
    this.people?.delete(ws);
    this.left();
  }

  save(ws, me) {
    me.saved = this.now();
    try { ws.serializeAttachment(me); } catch { /* closing */ }
  }

  // Someone left: the sector may go quiet now, so anything owed goes out.
  left() {
    this.sendBatch(true);
    this.schedulePresence(true);
    if (this.reportDue) this.maybeReport(true);
  }

  // Claims, positions or a report that came due since the last message.
  catchUp() {
    if (this.batch.length) this.sendBatch();
    if (this.presenceDue && this.now() - this.presenceAt >= PRESENCE_MS) this.sendPresence();
    if (this.reportDue) this.maybeReport();
  }

  // Sending each claim to every socket costs players × claims sends, which
  // grows with the square of the crowd; batching claims for BATCH_MS cuts
  // that to players × 5 a second. The first claim after a lull goes at once.
  sendBatch(force = false) {
    if (!this.batch.length) return;
    const wait = BATCH_MS - (this.now() - this.batchAt);
    if (wait > 0 && !force) {
      if (!this.batchTimer && this.ctx.getWebSockets().length < QUIET) {
        this.batchTimer = setTimeout(() => { this.batchTimer = null; this.sendBatch(true); }, wait);
      }
      return;
    }
    const frames = this.batch;
    this.batch = [];
    this.batchAt = this.now();
    broadcast(this.ctx, frames.length === 1 ? frames[0] : `[${frames.join(',')}]`);
  }

  here() {
    return [...this.everyone().values()].filter((p) => p.x !== null);
  }

  // Positions go out together, at most once a second, however many players
  // move: that keeps the messages a sector sends proportional to its players,
  // not to its players squared. Changes that aren't due yet go out with a
  // later message; a player leaving might be the last thing that happens in a
  // quiet sector, so that sets a timer instead of leaving a ghost behind.
  schedulePresence(leaving) {
    const wait = PRESENCE_MS - (this.now() - this.presenceAt);
    if (wait <= 0) return this.sendPresence();
    this.presenceDue = true;
    if (leaving && !this.presenceTimer && this.ctx.getWebSockets().length < QUIET) {
      this.presenceTimer = setTimeout(() => { this.presenceTimer = null; if (this.presenceDue) this.sendPresence(); }, wait);
    }
  }

  sendPresence() {
    this.presenceAt = this.now();
    this.presenceDue = false;
    const here = this.here().sort((a, b) => b.moved - a.moved);
    broadcast(this.ctx, JSON.stringify({ t: 'presence', n: here.length, p: here.slice(0, PRESENCE_MAX).map((p) => [p.id, p.initials, p.x, p.y]) }));
    this.maybeReport();
  }

  // The middle of the crowd: the median of where players are looking, which
  // a few people wandering off on their own don't pull away from everyone else.
  crowd() {
    const here = this.here();
    if (!here.length) return null;
    const median = (values) => Math.floor(values.sort((a, b) => a - b)[values.length >> 1]);
    return [median(here.map((p) => p.x)), median(here.map((p) => p.y))];
  }

  // Addresses past the daily cap; a new UTC day starts with none.
  overToday() {
    const day = Math.floor(this.now() / DAY_MS);
    if (day !== this.overDay) { this.overDay = day; this.over = new Set(); this.overAt = 0; }
    return this.over;
  }

  // Index of the sector's territory that holds cell (x, y), row by row.
  territory(x, y) {
    const [sx, sy] = this.coords();
    return (fdiv(y, RC) - sy * TERR) * TERR + fdiv(x, RC) - sx * TERR;
  }

  chartedCounts() {
    if (!this.counts) {
      this.counts = new Array(TERR * TERR).fill(0);
      for (const { x, y } of this.sql.exec('SELECT x, y FROM claims WHERE s = 0').toArray()) this.counts[this.territory(x, y)]++;
    }
    return this.counts;
  }

  // Sectors in the shared world tell the Atlas their numbers at most every
  // REPORT_MS, when something changed: with a later message, or when a player
  // leaves (`force`). A report timer would be pending most of the time in a
  // sector with a few people circling words, and bill it for all of it. The
  // Atlas answers with the world's totals, which are passed on to players.
  maybeReport(force = false) {
    const where = this.coords();
    if (!this.env.ATLAS || !where || !inArea(...where)) return;
    if (this.reporting || (!force && this.now() - this.reportedAt < REPORT_MS)) { this.reportDue = true; return; }
    this.report();
  }

  async report() {
    const [sx, sy] = this.coords();
    this.reportedAt = this.now();
    this.reportDue = false;
    this.reporting = true;
    // Words charted by each address since the last report: sent once, or
    // put back to go with the next report if this one fails.
    const by = this.chartedBy, unpassed = this.unpassed;
    this.chartedBy = new Map();
    this.unpassed = 0;
    this.overToday();
    let world;
    try {
      const res = await atlas(this.env).fetch('https://atlas/report', {
        method: 'POST',
        body: JSON.stringify({
          sx, sy, players: this.here().length, charted: this.chartedCounts(), hot: this.crowd() ?? this.hot,
          by: [...by], day: this.overDay, overAt: this.overAt, ...(unpassed ? { unpassed } : {}),
        }),
      });
      if (!res.ok) throw new Error(`atlas ${res.status}`);
      world = await res.json();
    } catch {
      for (const [address, n] of by) this.chartedBy.set(address, (this.chartedBy.get(address) ?? 0) + n);
      this.unpassed += unpassed;
      return;  // the totals just go out later
    } finally {
      this.reporting = false;
    }
    this.overToday();  // in case the day turned while the report was out
    if (Array.isArray(world?.over) && world.day === this.overDay) {
      this.over = new Set(world.over.filter((a) => typeof a === 'string' && HASH.test(a)));
      this.overAt = isInt(world.overAt, 0, 1e9) ? world.overAt : 0;
    }
    if (!isInt(world?.charted, 0, AREA_WORDS) || !isInt(world?.players, 0, 1e9)) return;
    if (this.world && world.charted === this.world.charted && world.players === this.world.players) return;
    this.world = { charted: world.charted, total: AREA_WORDS, players: world.players };
    broadcast(this.ctx, JSON.stringify({ t: 'world', ...this.world }));
  }
}

// The whole shared world at a glance: hidden words charted in each of its
// 10,000 territories and players online in each sector. Sectors send it
// absolute numbers, never changes, so a lost or repeated report does no harm
// and a sector that reports again puts right anything the Atlas lost.
export class Atlas {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.sql = ctx.storage.sql;
    this.now = () => Date.now();
    this.rows = null;      // 'sx,sy' → {sx, sy, players, charted: [16 counts], done, at}, loaded on first use
    this.dirty = new Set();
    this.saveTimer = null;
    this.view = null;      // the world map as JSON, rebuilt at most every VIEW_MS
    // Words each address charted today (UTC), and those past DAILY_CLAIMS in
    // the order they got there. Kept in memory only: the Atlas hears from
    // every busy sector every few seconds, so it's rarely evicted, and if it
    // is, the day's counts start again.
    this.day = -1;
    this.chartedToday = new Map();
    this.overList = [];
    // The UTC day's numbers, in memory like the counts above, and the day
    // before's. So far only joins without a Turnstile pass (TURNSTILE.md).
    this.stats = null;
    this.yesterday = null;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS sectors (
      sx INTEGER NOT NULL, sy INTEGER NOT NULL, charted TEXT NOT NULL, done INTEGER NOT NULL,
      PRIMARY KEY (sx, sy)) WITHOUT ROWID`);
  }

  load() {
    if (!this.rows) {
      this.rows = new Map();
      for (const r of this.sql.exec('SELECT sx, sy, charted, done FROM sectors').toArray()) {
        this.rows.set(`${r.sx},${r.sy}`, { sx: r.sx, sy: r.sy, players: 0, charted: r.charted.split(',').map(Number), done: r.done, hot: null, at: 0 });
      }
    }
    return this.rows;
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);
    const json = (body, status = 200) => Response.json(body, { status });
    if (request.method === 'POST' && pathname === '/report') {
      let r = null;
      try { r = await request.json(); } catch { /* answered below */ }
      const by = r?.by ?? [];
      const ok = r && Number.isInteger(r.sx) && Number.isInteger(r.sy) && inArea(r.sx, r.sy) && isInt(r.players, 0, MAX_PLAYERS)
        && Array.isArray(r.charted) && r.charted.length === TERR * TERR && r.charted.every((n) => isInt(n, 0, 1000))
        && Array.isArray(by) && by.length <= MAX_PLAYERS * 4
        && by.every((e) => Array.isArray(e) && typeof e[0] === 'string' && HASH.test(e[0]) && isInt(e[1], 1, TERR * TERR * 1000))
        && (r.unpassed === undefined || isInt(r.unpassed, 0, 1e6));
      if (!ok) return json({ error: 'bad report' }, 400);
      this.countCharted(by);
      this.today().unpassed += r.unpassed ?? 0;
      const key = `${r.sx},${r.sy}`, done = r.charted.reduce((a, b) => a + b, 0), old = this.load().get(key);
      const inside = (v, s) => Number.isInteger(v) && fdiv(v, SECTOR) === s;
      const hot = Array.isArray(r.hot) && inside(r.hot[0], r.sx) && inside(r.hot[1], r.sy) ? r.hot.slice(0, 2) : old?.hot ?? null;
      this.rows.set(key, { sx: r.sx, sy: r.sy, players: r.players, charted: r.charted, done, hot, at: this.now() });
      if (!old || old.done !== done) this.save(key);
      // The list of addresses past the cap goes back only when it has
      // changed since this sector last heard it.
      const fresh = r.day === this.day && r.overAt === this.overList.length;
      return json({ ...this.totals(), day: this.day, overAt: this.overList.length, ...(fresh ? {} : { over: this.overList.slice(-DAILY_LIST_MAX) }) });
    }
    if (request.method === 'GET' && pathname === '/world') {
      const now = this.now();
      if (!this.view || now - this.view.at >= VIEW_MS) this.view = { at: now, body: JSON.stringify(this.worldMap()) };
      return new Response(this.view.body, { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
    }
    return json({ error: 'not found' }, 404);
  }

  // Today's stats, rolling the last day's into `yesterday` when the day turns.
  today() {
    const day = Math.floor(this.now() / DAY_MS);
    if (this.stats?.day !== day) {
      this.yesterday = this.stats?.day === day - 1 ? this.stats : { day: day - 1, unpassed: 0 };
      this.stats = { day, unpassed: 0 };
    }
    return this.stats;
  }

  countCharted(by) {
    const day = Math.floor(this.now() / DAY_MS);
    if (day !== this.day) { this.day = day; this.chartedToday = new Map(); this.overList = []; }
    for (const [address, n] of by) {
      const before = this.chartedToday.get(address) ?? 0;
      this.chartedToday.set(address, before + n);
      if (before < DAILY_CLAIMS && before + n >= DAILY_CLAIMS) this.overList.push(address);
    }
  }

  // Charted counts only change storage once a minute per sector at most:
  // writing every report would cost a row written per busy sector every
  // REPORT_MS, and players online don't need storing at all.
  save(key) {
    this.dirty.add(key);
    this.saveTimer ??= setTimeout(() => this.flush(), SAVE_MS);
  }

  flush() {
    this.saveTimer = null;
    for (const key of this.dirty) {
      const r = this.rows.get(key);
      this.sql.exec(
        'INSERT INTO sectors (sx, sy, charted, done) VALUES (?, ?, ?, ?) ON CONFLICT (sx, sy) DO UPDATE SET charted = excluded.charted, done = excluded.done',
        r.sx, r.sy, r.charted.join(','), r.done,
      );
    }
    this.dirty.clear();
  }

  totals() {
    const now = this.now();
    let charted = 0, players = 0;
    for (const r of this.load().values()) {
      charted += r.done;
      if (now - r.at < ONLINE_MS) players += r.players;
    }
    return { charted, total: AREA_WORDS, players };
  }

  worldMap() {
    const now = this.now(), size = (2 * AREA + 1) * TERR, bytes = new Uint8Array(size * size), sectors = [], live = [];
    for (const r of this.load().values()) {
      for (let i = 0; i < TERR * TERR; i++) {
        const tx = (r.sx + AREA) * TERR + (i % TERR), ty = (r.sy + AREA) * TERR + Math.floor(i / TERR);
        bytes[ty * size + tx] = Math.min(255, r.charted[i]);
      }
      if (r.players && now - r.at < ONLINE_MS) { sectors.push([r.sx, r.sy, r.players]); live.push(r); }
    }
    let territories = '';
    for (const b of bytes) territories += String.fromCharCode(b);
    const today = this.today();
    return { ...this.totals(), area: AREA, territories: btoa(territories), sectors, spawn: this.spawn(live), today: { ...today }, yesterday: { ...this.yesterday } };
  }

  // Where a new player should start, as a cell: in the middle of the biggest
  // crowd that still has room, so the first thing they see is lots of people
  // at work; beside the biggest crowd if every crowd is full; or at the
  // origin (null) while nobody is playing.
  spawn(live) {
    const centre = (r) => [r.sx * SECTOR + SECTOR / 2, r.sy * SECTOR + SECTOR / 2];
    const open = live.filter((r) => r.players < SPAWN_MAX).sort((a, b) => b.players - a.players);
    if (open.length) return open[0].hot ?? centre(open[0]);
    if (!live.length) return null;
    const biggest = live.reduce((a, b) => (b.players > a.players ? b : a));
    const [dx, dy] = DIRS[Math.floor(Math.random() * 8)];
    const clamp = (v) => Math.max(-AREA, Math.min(AREA, v));
    return centre({ sx: clamp(biggest.sx + dx), sy: clamp(biggest.sy + dy) });
  }
}
