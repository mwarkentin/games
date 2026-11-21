// Tests for Letterfield's guilds (src/survey-guild.js): the Guild object and
// its routes, membership checked by sectors, and who's online passed on from
// the Atlas. Run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

import worker from '../src/index.js';
import { Atlas, ONLINE_MS, REPORT_MS, SECTOR, Sector } from '../src/survey.js';
import { chunk } from '../../js/letterfield/world.js';
import {
  GUILD_CHECKS, GUILD_CHECK_REFILL_MS, GUILD_CODE, GUILD_FIRST, GUILD_LOG_ID, GUILD_MAX, GUILD_RECHECK_MS, GUILD_RETRY_MS, GUILD_SECOND, GUILD_THIRD, GUILD_WORDS, Guild, SEEN_MS,
  idleShown, matesFor, noteMates, passMates,
} from '../src/survey-guild.js';
import { FLAG_QUIET, GUILDS_MAX, REFRESH_MS, playerId, snapshot, tagsOf, takeMe } from '../src/survey-social.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 10, 13, 12);
const token = (n) => n.toString(16).padStart(32, '0');
const settle = async () => { for (let i = 0; i < 5; i++) await new Promise((resolve) => setImmediate(resolve)); };
const MIGRATIONS = new URL('../migrations/', import.meta.url);
const LOG_MIGRATIONS = new URL('../migrations-log/', import.meta.url);

function fakeState() {
  const db = new DatabaseSync(':memory:');
  const sockets = [];
  return {
    db,
    sockets,
    storage: { sql: { exec(query, ...b) { const rows = db.prepare(query).all(...b); return { toArray: () => rows, one: () => rows[0] }; } }, setAlarm() {} },
    acceptWebSocket: (ws) => sockets.push(ws),
    getWebSockets: () => sockets.filter((ws) => ws.open),
  };
}

function fakeSocket() {
  let attachment = null;
  return {
    open: true,
    sent: [],
    send(text) { if (!this.open) throw new Error('closed'); const f = JSON.parse(text); this.sent.push(...(Array.isArray(f) ? f : [f])); },
    accept() {},
    close() { this.open = false; },
    serializeAttachment(v) { attachment = structuredClone(v); },
    deserializeAttachment: () => structuredClone(attachment),
    all(type) { return this.sent.filter((m) => m.t === type); },
    last(type) { return this.all(type).at(-1); },
  };
}

// The parts of D1 the rate limit uses, with the leaderboard's migrations.
function fakeD1() {
  const db = new DatabaseSync(':memory:');
  for (const file of readdirSync(MIGRATIONS).sort()) db.exec(readFileSync(new URL(file, MIGRATIONS), 'utf8'));
  const statement = (sql, params = []) => ({
    bind: (...values) => statement(sql, values),
    first: async (column) => { const row = db.prepare(sql).get(...params); return row ? (column ? row[column] : row) : null; },
    run: async () => { db.prepare(sql).run(...params); return { success: true }; },
  });
  return { prepare: (sql) => statement(sql) };
}

// The survey log's D1, with its migrations, as much as sectors write to it.
function fakeLogD1() {
  const db = new DatabaseSync(':memory:');
  for (const file of readdirSync(LOG_MIGRATIONS).sort()) db.exec(readFileSync(new URL(file, LOG_MIGRATIONS), 'utf8'));
  const statement = (sql, params = []) => ({ bind: (...values) => statement(sql, values), run: () => db.prepare(sql).run(...params) });
  return {
    raw: db,
    prepare: (sql) => statement(sql),
    async batch(statements) { db.exec('BEGIN'); for (const st of statements) st.run(); db.exec('COMMIT'); },
  };
}

// Sectors, an Atlas and guilds that reach each other, as the runtime's bindings would.
function world({ db = null, log = null } = {}) {
  const clock = { now: NOW }, sectors = new Map(), guilds = new Map();
  const env = { ALLOWED_ORIGINS: ORIGIN, ...(db ? { DB: db } : {}), ...(log ? { LOG_DB: log } : {}) };
  const atlas = new Atlas(fakeState(), env);
  atlas.now = () => clock.now;
  const guildAt = (name) => {
    if (!guilds.has(name)) { const g = new Guild(fakeState(), env); g.now = () => clock.now; guilds.set(name, g); }
    return guilds.get(name);
  };
  const sectorAt = (name) => {
    if (!sectors.has(name)) { const s = new Sector(fakeState(), env); s.now = () => clock.now; sectors.set(name, s); }
    return sectors.get(name);
  };
  env.ATLAS = { idFromName: (n) => n, get: () => ({ fetch: (url, init) => atlas.fetch(new Request(url, init)) }) };
  env.SECTORS = { idFromName: (n) => n, get: (n) => ({ fetch: (url, init) => sectorAt(n).fetch(new Request(url, init)) }) };
  env.GUILDS = { idFromName: (n) => n, get: (n) => ({ fetch: (url, init) => guildAt(n).fetch(new Request(url, init)) }) };
  const call = async (path, body, { method = body === undefined ? 'GET' : 'POST', origin = ORIGIN } = {}) => {
    const res = await worker.fetch(new Request(`https://survey.test${path}`, {
      method, headers: { Origin: origin, 'CF-Connecting-IP': '203.0.113.9' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }), env);
    return [res.status, await res.json()];
  };
  const make = async (n = 1, initials = 'ONE', name = [0, 1, 2]) => (await call('/v1/survey/guilds', { token: token(n), initials, name }))[1];
  async function player(sx, sy, { id, initials = 'ABC', guild = null, guilds = null, hide = false, quiet = false, x, y } = {}) {
    const sector = sectorAt(`${sx},${sy}`), ws = fakeSocket();
    sector.join(ws, sx, sy);
    const p = {
      ws, sector, say: (m) => sector.webSocketMessage(ws, JSON.stringify(m)), pid: await playerId(token(id)),
      tags: () => tagsOf(sector.everyone().get(ws)),  // the guilds that have said they're a member, in the game's order
    };
    await p.say({ t: 'me', initials, token: token(id), hide, ...(quiet ? { quiet } : {}), ...(guild ? { guild } : {}), ...(guilds ? { guilds } : {}) });
    await settle();
    if (x !== undefined) await p.say({ t: 'pos', x, y });
    return p;
  }
  const tick = async (p, ms = REPORT_MS) => { clock.now += ms; await p.say({ t: 'here' }); await settle(); };
  return { env, clock, atlas, guildAt, sectorAt, call, make, player, tick };
}

describe('a guild', () => {
  let w;
  beforeEach(() => { w = world(); });

  test('is made with you in it, under a code of its own and a name of three listed words', async () => {
    const [status, g] = await w.call('/v1/survey/guilds', { token: token(1), initials: 'ONE', name: [3, 15, 7] });
    assert.equal(status, 201);
    assert.match(g.code, GUILD_CODE);
    assert.match(g.tag, /^[0-9a-f]{8}$/);
    // Its id in the survey log is another random one, so its page there says nothing of whose carets are whose.
    assert.match(g.lid, GUILD_LOG_ID);
    assert.notEqual(g.lid.slice(0, 8), g.tag);
    assert.deepEqual(g.name, [3, 15, 7]);
    assert.deepEqual(g.members, [[await playerId(token(1)), 'ONE', NOW]]);
    assert.deepEqual(await w.call(`/v1/survey/guilds/${g.code}`), [200, { name: [3, 15, 7], size: 1 }]);
  });

  test('made before the log knew guilds, gets a log id the next time it is asked, and keeps it', async () => {
    const g = await w.make();
    const sql = w.guildAt(g.code).sql;
    // As a guild from before: no lid column at all.
    sql.exec('ALTER TABLE guild DROP COLUMN lid');
    w.guildAt(g.code).lidReady = false;
    const roster = async () => (await w.call(`/v1/survey/guilds/${g.code}/roster`, { token: token(1) }))[1];
    const first = await roster();
    assert.match(first.lid, GUILD_LOG_ID);
    assert.equal((await roster()).lid, first.lid);
    assert.equal(sql.exec('SELECT lid FROM guild').one().lid, first.lid);
    // And the code is free again once it ends, for a guild with its own lid.
    await w.call(`/v1/survey/guilds/${g.code}/leave`, { token: token(1) });
    const again = await w.make(2, 'TWO', [1, 1, 1]);
    assert.notEqual(again.lid, first.lid);
  });

  test('takes nobody it cannot name, and no name off the lists', async () => {
    const base = { token: token(1), initials: 'ONE', name: [0, 0, 0] };
    for (const [body, error] of [
      [{ ...base, token: 'nope' }, 'token must be 32 hex digits'],
      [{ ...base, initials: '' }, 'pick initials first'],
      [{ ...base, initials: 'KKK' }, 'pick initials first'],
      [{ ...base, name: [GUILD_WORDS[0], 0, 0] }, 'name must be three words from the lists'],
      [{ ...base, name: ['The', 'Best', 'Guild'] }, 'name must be three words from the lists'],
      [{ ...base, name: [0, 0] }, 'name must be three words from the lists'],
    ]) assert.deepEqual(await w.call('/v1/survey/guilds', body), [400, { error }]);
    assert.equal((await w.call('/v1/survey/guilds', base, { origin: 'https://evil.test' }))[0], 403);
    assert.equal((await w.call('/v1/survey/guilds'))[0], 405);
  });

  test('is joined by its code, and only so many times', async () => {
    const g = await w.make();
    const [status, joined] = await w.call(`/v1/survey/guilds/${g.code}/join`, { token: token(2), initials: 'TWO' });
    assert.equal(status, 200);
    assert.deepEqual(joined.members.map((m) => m[1]).sort(), ['ONE', 'TWO']);
    assert.equal(joined.code, g.code);
    // Joining again changes nothing but initials.
    w.clock.now += 1000;
    assert.deepEqual((await w.call(`/v1/survey/guilds/${g.code}/join`, { token: token(2), initials: 'TOO' }))[1].members.map((m) => m[1]), ['TOO', 'ONE']);
    for (let i = 3; i <= GUILD_MAX; i++) await w.call(`/v1/survey/guilds/${g.code}/join`, { token: token(i), initials: 'ABC' });
    assert.deepEqual(await w.call(`/v1/survey/guilds/${g.code}/join`, { token: token(999), initials: 'ABC' }), [409, { error: 'guild is full' }]);
    assert.deepEqual(await w.call('/v1/survey/guilds/ABCDEF/join', { token: token(2), initials: 'TWO' }), [404, { error: 'unknown guild' }]);
    assert.deepEqual(await w.call('/v1/survey/guilds/abc/join', { token: token(2), initials: 'TWO' }), [404, { error: 'unknown guild' }]);
  });

  test('shows its members only to members, and says the same to everyone else as for no guild at all', async () => {
    const g = await w.make();
    assert.deepEqual((await w.call(`/v1/survey/guilds/${g.code}/roster`, { token: token(1) }))[1].members.map((m) => m[1]), ['ONE']);
    assert.deepEqual(await w.call(`/v1/survey/guilds/${g.code}/roster`, { token: token(2) }), [404, { error: 'not a member' }]);
    assert.equal((await w.call('/v1/survey/guilds/ABCDEF/roster', { token: token(2) }))[0], 404);
  });

  test('ends when its last member leaves, freeing its code', async () => {
    const g = await w.make();
    await w.call(`/v1/survey/guilds/${g.code}/join`, { token: token(2), initials: 'TWO' });
    assert.deepEqual(await w.call(`/v1/survey/guilds/${g.code}/leave`, { token: token(2) }), [200, { ok: true }]);
    assert.equal((await w.call(`/v1/survey/guilds/${g.code}`))[1].size, 1);
    await w.call(`/v1/survey/guilds/${g.code}/leave`, { token: token(1) });
    assert.equal((await w.call(`/v1/survey/guilds/${g.code}`))[0], 404);
    const tables = w.guildAt(g.code).sql.exec("SELECT name FROM sqlite_master WHERE type = 'table'").toArray();
    assert.deepEqual(tables, []);
    // A wrong guess at a code stores nothing either.
    await w.call('/v1/survey/guilds/ZZZZZZ');
    assert.deepEqual(w.guildAt('ZZZZZZ').sql.exec("SELECT name FROM sqlite_master WHERE type = 'table'").toArray(), []);
  });

  test('is made and joined only so often from one address', async () => {
    w = world({ db: fakeD1() });
    const made = [];
    for (let i = 0; i < 6; i++) made.push((await w.call('/v1/survey/guilds', { token: token(1), initials: 'ONE', name: [0, 0, 0] }))[0]);
    assert.deepEqual(made, [201, 201, 201, 201, 201, 429]);
  });
});

describe('membership in sectors', () => {
  let w, g, reports;
  beforeEach(async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    w = world();
    g = await w.make(1, 'ONE');
    await w.call(`/v1/survey/guilds/${g.code}/join`, { token: token(2), initials: 'TWO' });
    reports = [];
    const fetch = w.env.ATLAS.get().fetch;
    w.env.ATLAS.get = () => ({ fetch: async (url, init) => { if (url.endsWith('/report')) reports.push(JSON.parse(init.body)); return fetch(url, init); } });
  });
  afterEach(() => mock.timers.reset());

  test("puts a member's guild on their caret and in reports, once the guild says they're in it", async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const pretender = await w.player(0, 0, { id: 9, initials: 'NOT', guild: g.code, x: 9, y: 9 });
    const watcher = await w.player(0, 0, { id: 8, initials: 'WAT' });
    await w.tick(watcher);
    assert.deepEqual(watcher.ws.last('presence').p.map((e) => e.slice(4)).sort(), [[], [g.tag]]);  // the pretender gets no tag
    await w.tick(watcher);
    const last = reports.at(-1);
    assert.deepEqual(last.tags, [g.tag]);
    assert.deepEqual(last.who.find((e) => e[0] === one.pid).slice(5), [0, [g.tag]]);
    assert.equal(last.who.find((e) => e[0] === pretender.pid).length, 6);
  });

  test("takes the tag off someone who has left, when it checks again, and keeps 'last seen' current", async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const seen = () => w.guildAt(g.code).sql.exec('SELECT seen FROM members WHERE pid = ?', one.pid).one().seen;
    assert.deepEqual(one.tags(), [g.tag]);
    await w.tick(one, SEEN_MS);
    assert.equal(seen(), NOW);  // not checked again yet
    await w.call(`/v1/survey/guilds/${g.code}/leave`, { token: token(1) });
    await w.tick(one, GUILD_RECHECK_MS - SEEN_MS);
    assert.deepEqual(one.tags(), []);
    // A member still in it is seen again at each check.
    const two = await w.player(0, 0, { id: 2, initials: 'TWO', guild: g.code, x: 6, y: 6 });
    const seenTwo = () => w.guildAt(g.code).sql.exec('SELECT seen FROM members WHERE pid = ?', two.pid).one().seen;
    const first = seenTwo();
    await w.tick(two, GUILD_RECHECK_MS);
    assert.equal(seenTwo(), first + GUILD_RECHECK_MS);
  });

  test('still checks a member after the sector wakes, though their socket was saved while a check was out', async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    assert.deepEqual(one.tags(), [g.tag]);
    // A recheck goes out, and a move saves the socket before it comes back.
    w.clock.now += GUILD_RECHECK_MS;
    const here = one.say({ t: 'here' });
    const moved = one.say({ t: 'pos', x: 6, y: 5 });
    await here;
    await moved;
    await settle();
    one.sector.people = null;  // it sleeps, and wakes reading the attachments
    await w.call(`/v1/survey/guilds/${g.code}/leave`, { token: token(1) });
    await w.tick(one, GUILD_RECHECK_MS);
    assert.deepEqual(one.tags(), []);
  });

  test('checks a guild the game names while the last one is being checked, without waiting for the next recheck', async () => {
    const other = await w.make(1, 'ONE', [1, 1, 1]);
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    assert.deepEqual(one.tags(), [g.tag]);
    // A recheck of the first guild goes out, and the game names the other before it comes back.
    w.clock.now += GUILD_RECHECK_MS;
    const here = one.say({ t: 'here' });
    const named = one.say({ t: 'me', initials: 'ONE', token: token(1), guild: other.code });
    await here;
    await named;
    await settle();
    await w.tick(one, 60_000);
    assert.deepEqual(one.tags(), [other.tag]);
  });

  test("puts every guild that says they're a member on their socket, in the game's order", async () => {
    const other = await w.make(2, 'TWO', [3, 2, 11]);
    const stranger = await w.make(9, 'NIN', [5, 5, 5]);  // a guild they aren't in
    const one = await w.player(0, 0, { id: 2, initials: 'TWO', guilds: [other.code, stranger.code, g.code], x: 5, y: 5 });
    const watcher = await w.player(0, 0, { id: 8, initials: 'WAT' });
    assert.deepEqual(one.tags(), [other.tag, g.tag]);
    await w.tick(watcher);
    // Presence gives one tag as a string, as an older game reads it, and several as a list.
    assert.deepEqual(watcher.ws.last('presence').p.find((e) => e[0] === one.pid).slice(4), [[other.tag, g.tag]]);
    await w.tick(watcher);
    const last = reports.at(-1);
    assert.deepEqual(last.who.find((e) => e[0] === one.pid)[6], [other.tag, g.tag]);
    assert.deepEqual(new Set(last.tags), new Set([other.tag, g.tag]));
    // A guild the game stops naming comes off at once, and the others keep their tags unasked.
    const asked = [];
    const fetch = w.env.GUILDS.get;
    w.env.GUILDS.get = (n) => { asked.push(n); return fetch(n); };
    await one.say({ t: 'me', initials: 'TWO', token: token(2), guilds: [g.code] });
    await settle();
    assert.deepEqual([one.tags(), asked], [[g.tag], []]);
  });

  test('takes no more than five guilds from a game, and checks only those', async () => {
    const made = [];
    for (let i = 0; i < GUILDS_MAX + 2; i++) made.push(await w.make(1, 'ONE', [i, 0, 0]));
    const asked = new Set();
    const fetch = w.env.GUILDS.get;
    w.env.GUILDS.get = (n) => { asked.add(n); return fetch(n); };
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guilds: [...made.map((m) => m.code), 'nope', made[0].code], x: 5, y: 5 });
    assert.equal(GUILDS_MAX, 5);
    assert.deepEqual(one.tags(), made.slice(0, GUILDS_MAX).map((m) => m.tag));
    assert.deepEqual([...asked].sort(), made.slice(0, GUILDS_MAX).map((m) => m.code).sort());
    // And takeMe itself: a list past the cap is cut at it, duplicates and bad codes dropped.
    const me = {};
    takeMe(me, { guilds: [made[1].code, made[1].code, 'abc', ...made.map((m) => m.code)] });
    assert.deepEqual(me.guilds.map((x) => x.code), [made[1].code, made[0].code, ...made.slice(2, 5).map((m) => m.code)]);
  });

  test('checks only so many guilds for one socket, however many new codes its game names', async () => {
    let asked = 0;
    const fetch = w.env.GUILDS.get;
    w.env.GUILDS.get = (n) => { asked++; return fetch(n); };
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const code = (i, j) => `${'ABCDEFGHJK'[i % 10]}${'MNPQRSTVWX'[j]}CDEF`;
    for (let i = 0; i < 20; i++) {
      await one.say({ t: 'me', initials: 'ONE', token: token(1), guilds: Array.from({ length: GUILDS_MAX }, (_, j) => code(i, j)) });
    }
    await settle();
    assert.equal(asked, GUILD_CHECKS);
    // The allowance comes back over time, and a real guild named then is checked.
    w.clock.now += GUILD_CHECK_REFILL_MS;
    await one.say({ t: 'me', initials: 'ONE', token: token(1), guilds: [g.code] });
    await settle();
    assert.equal(asked, GUILD_CHECKS + 1);
    assert.deepEqual(one.tags(), [g.tag]);
  });

  test('asks a guild that failed to answer again only after a while, not with every message', async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', x: 5, y: 5 });
    let asked = 0, down = true;
    const fetch = w.env.GUILDS.get;
    w.env.GUILDS.get = (n) => ({ fetch: async (url, init) => { asked++; return down ? new Response('overloaded', { status: 503 }) : fetch(n).fetch(url, init); } });
    await one.say({ t: 'me', initials: 'ONE', token: token(1), guild: g.code });
    await settle();
    assert.equal(asked, 1);
    for (let i = 0; i < 10; i++) { w.clock.now += 1000; await one.say({ t: 'pos', x: 5 + i, y: 5 }); await settle(); }
    assert.equal(asked, 1);
    assert.deepEqual(one.tags(), []);
    down = false;
    w.clock.now += GUILD_RETRY_MS;
    await one.say({ t: 'here' });
    await settle();
    assert.equal(asked, 2);
    assert.deepEqual(one.tags(), [g.tag]);
  });

  test('drops a guild left on another device at its next check, and keeps the others', async () => {
    const other = await w.make(1, 'ONE', [3, 2, 11]);
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guilds: [g.code, other.code], x: 5, y: 5 });
    assert.deepEqual(one.tags(), [g.tag, other.tag]);
    // Another device of theirs leaves one; this game still names both.
    await w.call(`/v1/survey/guilds/${g.code}/leave`, { token: token(1) });
    await w.tick(one, GUILD_RECHECK_MS);
    assert.deepEqual(one.tags(), [other.tag]);
    // Their words count only for the one they're still in, and a guild named again is checked again.
    assert.deepEqual(one.sector.everyone().get(one.ws).guilds.map((x) => [x.code, x.tag]), [[g.code, null], [other.code, other.tag]]);
    await w.call(`/v1/survey/guilds/${g.code}/join`, { token: token(1), initials: 'ONE' });
    await w.tick(one, GUILD_RECHECK_MS);
    assert.deepEqual(one.tags(), [g.tag, other.tag]);
  });

  test('reads back a socket saved by an older version, with one guild, as a list of one', async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', x: 5, y: 5 });
    const old = one.sector.everyone().get(one.ws);
    delete old.guilds;
    Object.assign(old, { guild: g.code, tag: g.tag, lid: g.lid, guildAt: w.clock.now });
    one.ws.serializeAttachment(old);
    one.sector.people = null;  // it sleeps, and wakes reading the attachment
    await one.say({ t: 'here' });
    await settle();
    assert.deepEqual(one.tags(), [g.tag]);
    const me = one.sector.everyone().get(one.ws);
    assert.deepEqual([me.guilds.map((x) => x.code), 'guild' in me, 'tag' in me], [[g.code], false, false]);
  });

  test('tells members which of their guild are online and where, as it changes, and nobody else', async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const outsider = await w.player(0, 0, { id: 7, initials: 'OUT', x: 7, y: 7 });
    const two = await w.player(3, 3, { id: 2, initials: 'TWO', guild: g.code, x: 3 * SECTOR + 50, y: 3 * SECTOR + 2 });
    await w.tick(two);                // 3,3 reports TWO
    await w.tick(one, REFRESH_MS);    // 0,0 reports again, and hears who's online
    const frame = one.ws.last('guild');
    assert.equal(frame.tag, g.tag);
    assert.deepEqual(frame.on.map((e) => e.slice(0, 4)).sort(), [[one.pid, 'ONE', 0, 0], [two.pid, 'TWO', 13, 12]].sort());
    await w.tick(two, REFRESH_MS);
    assert.equal(two.ws.last('guild').on.length, 2);
    assert.equal(outsider.ws.all('guild').length, 0);
    // The same again isn't sent again.
    const sent = one.ws.all('guild').length;
    passMates(one.sector, { [g.tag]: frame.on });
    assert.equal(one.ws.all('guild').length, sent);
    // A member closing the game drops off at once, even just after positions
    // went out, when nothing else would report it.
    w.clock.now += REPORT_MS;
    await two.say({ t: 'pos', x: 3 * SECTOR + 51, y: 3 * SECTOR + 2 });
    await settle();
    w.clock.now += 10;
    two.ws.close();
    await two.sector.webSocketClose(two.ws);
    await settle();
    await w.tick(one, REFRESH_MS);
    assert.deepEqual(one.ws.last('guild').on.map((e) => e[0]), [one.pid]);
    // Members are on the public list like everyone else, until they go.
    const listedNow = snapshot(w.atlas.load().values(), w.clock.now, ONLINE_MS).sectors.flatMap((s) => s[2]).map((e) => e[0]);
    assert.ok(listedNow.includes(one.pid) && !listedNow.includes(two.pid), JSON.stringify(listedNow));
  });

  test("doesn't hand a member arriving in a sector the guild's frame from members who left it long ago", async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const outsider = await w.player(0, 0, { id: 7, initials: 'OUT', x: 7, y: 7 });  // keeps the sector awake
    await w.tick(one, REFRESH_MS);
    assert.deepEqual(one.ws.last('guild').on.map((e) => e[0]), [one.pid]);
    one.ws.close();
    await one.sector.webSocketClose(one.ws);
    await settle();
    await w.tick(outsider, 3 * 3600000);  // hours on
    const two = await w.player(0, 0, { id: 2, initials: 'TWO', guild: g.code, x: 6, y: 6 });
    await w.tick(two, REPORT_MS);
    const frames = two.ws.all('guild');
    assert.ok(frames.length > 0);
    assert.deepEqual(frames[0].on.map((e) => e[0]), [two.pid]);  // ONE never shows as online
  });

  test('tells a member of several guilds who is online in each, and members of each about them', async () => {
    const other = await w.make(3, 'TRI', [3, 2, 11]);
    await w.call(`/v1/survey/guilds/${other.code}/join`, { token: token(1), initials: 'ONE' });
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guilds: [g.code, other.code], x: 5, y: 5 });
    const two = await w.player(3, 3, { id: 2, initials: 'TWO', guild: g.code, x: 3 * SECTOR + 50, y: 3 * SECTOR + 2 });
    const tri = await w.player(-2, 1, { id: 3, initials: 'TRI', guild: other.code, x: -2 * SECTOR + 9, y: SECTOR + 9 });
    await w.tick(two);
    await w.tick(tri);
    await w.tick(one, REFRESH_MS);
    await w.tick(two, REFRESH_MS);
    await w.tick(tri, REFRESH_MS);
    const on = (p, tag) => p.ws.all('guild').filter((f) => f.tag === tag).at(-1)?.on.map((e) => e[1]).sort();
    // ONE hears each guild apart; each of the others hears ONE in theirs, and nothing of the other guild.
    assert.deepEqual(on(one, g.tag), ['ONE', 'TWO']);
    assert.deepEqual(on(one, other.tag), ['ONE', 'TRI']);
    assert.deepEqual([on(two, g.tag), on(two, other.tag)], [['ONE', 'TWO'], undefined]);
    assert.deepEqual([on(tri, other.tag), on(tri, g.tag)], [['ONE', 'TRI'], undefined]);
    // The Atlas keeps ONE under both guilds, from the one report that names them.
    assert.deepEqual(Object.fromEntries(Object.entries(matesFor(w.atlas, [g.tag, other.tag], w.clock.now, ONLINE_MS)).map(([t, l]) => [t, l.map((e) => e[1]).sort()])),
      { [g.tag]: ['ONE', 'TWO'], [other.tag]: ['ONE', 'TRI'] });
  });

  test('tells members which of their guild take no emotes, and when that changes', async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const two = await w.player(3, 3, { id: 2, initials: 'TWO', guild: g.code, quiet: true, x: 3 * SECTOR + 50, y: 3 * SECTOR + 2 });
    await w.tick(two);
    await w.tick(one, REFRESH_MS);
    const flags = () => Object.fromEntries(one.ws.last('guild').on.map((e) => [e[1], e[5]]));
    assert.deepEqual(flags(), { ONE: 0, TWO: FLAG_QUIET });
    // Taking emotes again changes the frame, so it goes out again.
    await two.say({ t: 'me', initials: 'TWO', token: token(2), guild: g.code });
    await settle();
    await w.tick(two, REFRESH_MS);
    await w.tick(one, REFRESH_MS);
    assert.deepEqual(flags(), { ONE: 0, TWO: 0 });
  });

  test("a member hears emotes from anyone, from anywhere, even asking to hide as older games could", async () => {
    const two = await w.player(3, 3, { id: 2, initials: 'TWO', guild: g.code, hide: true, x: 3 * SECTOR + 50, y: 3 * SECTOR + 2 });
    const mate = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const stranger = await w.player(0, 0, { id: 7, initials: 'OUT', x: 6, y: 6 });
    await mate.say({ t: 'emote', to: two.pid, e: 'wave', s: [3, 3] });
    await stranger.say({ t: 'emote', to: two.pid, e: 'wave', s: [3, 3] });
    assert.equal(mate.ws.last('emoted').ok, true);
    assert.equal(stranger.ws.last('emoted').ok, true);
    assert.deepEqual(two.ws.all('emote').map((m) => m.ini), ['ONE', 'OUT']);
  });
});

test("the Atlas's index of who's online forgets sectors that stop reporting", () => {
  const atlas = {};
  noteMates(atlas, '0,0', [['aaaaaaaaaaaa', 'ONE', 1, 1, 0, 0, 'deadbeef'], ['bbbbbbbbbbbb', 'TWO', 2, 2, 0, FLAG_QUIET, 'deadbeef']], NOW);
  noteMates(atlas, '1,0', [['cccccccccccc', 'SIX', 4, 1, 3, 0, 'deadbeef']], NOW + 1000);
  assert.deepEqual(matesFor(atlas, ['deadbeef', 'feedface'], NOW + 2000, ONLINE_MS), {
    deadbeef: [['aaaaaaaaaaaa', 'ONE', 1, 1, 0, 0], ['bbbbbbbbbbbb', 'TWO', 2, 2, 0, FLAG_QUIET], ['cccccccccccc', 'SIX', 4, 1, 0, 0]],
    feedface: [],
  });
  noteMates(atlas, '0,0', [], NOW + 3000);  // its members left
  assert.deepEqual(matesFor(atlas, ['deadbeef'], NOW + 3000, ONLINE_MS).deadbeef.map((e) => e[0]), ['cccccccccccc']);
  assert.deepEqual(matesFor(atlas, ['deadbeef'], NOW + 1000 + ONLINE_MS, ONLINE_MS).deadbeef, []);
  assert.deepEqual([0, 19, 20, 59, 60, 119, 120, 3601].map(idleShown), [0, 0, 20, 20, 60, 60, 120, 3600]);
});

test("the game's lists of words for names, and the first word's hues, are the Worker's", () => {
  const html = readFileSync(new URL('../../letterfield.html', import.meta.url), 'utf8');
  const list = (name) => {
    const m = html.match(new RegExp(`const ${name} = (\\[[\\s\\S]*?\\]);\\n`));
    assert.ok(m, `letterfield.html lost ${name}`);
    return JSON.parse(m[1].replace(/'/g, '"'));
  };
  assert.deepEqual(list('GUILD_FIRST'), GUILD_FIRST);
  assert.deepEqual(list('GUILD_SECOND'), GUILD_SECOND);
  assert.deepEqual(list('GUILD_THIRD'), GUILD_THIRD);
  assert.deepEqual([GUILD_FIRST, GUILD_SECOND, GUILD_THIRD].map((l) => l.length), GUILD_WORDS);
  for (const l of [GUILD_FIRST.map((w) => w[0]), GUILD_SECOND, GUILD_THIRD]) assert.equal(new Set(l).size, l.length, 'a word twice');
  // A name is kept as numbers, so a word keeps its place: "Survey" (6) became
  // "Lodge", and new words went on the end. The longest still fits a phone.
  assert.deepEqual(GUILD_THIRD.slice(0, 8), ['Society', 'Guild', 'Company', 'Circle', 'Club', 'Expedition', 'Lodge', 'Fellowship']);
  assert.ok(!GUILD_THIRD.includes('Survey'), 'a guild named like another survey');
  for (const l of [GUILD_FIRST.map((w) => w[0]), GUILD_SECOND, GUILD_THIRD]) for (const w of l) assert.ok(w.length <= 'Fellowship'.length, w);
});

describe("members' words in the survey log", () => {
  let w, g, log;
  beforeEach(async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    log = fakeLogD1();
    w = world({ log });
    g = await w.make(1, 'ONE', [11, 0, 0]);
    await w.call(`/v1/survey/guilds/${g.code}/join`, { token: token(2), initials: 'TWO' });
  });
  afterEach(() => mock.timers.reset());

  const word = (n) => { const { w: word, x, y, d } = chunk(n, 0).words[0]; return { w: word, x, y, d }; };
  const claim = async (p, n) => { w.clock.now += 2000; await p.say({ t: 'claim', ...word(n) }); };
  const logged = () => log.raw.prepare('SELECT w, initials, guild FROM survey_log ORDER BY at').all().map((r) => [r.w, r.initials, r.guild]);

  test("count for the guild a member was in, by its log id, and for nobody else", async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    // Every member's words count: an older game's ask to keep off the list changes nothing.
    const two = await w.player(0, 0, { id: 2, initials: 'TWO', guild: g.code, hide: true, x: 6, y: 6 });
    const pretender = await w.player(0, 0, { id: 9, initials: 'NOT', guild: g.code, x: 9, y: 9 });
    const loner = await w.player(0, 0, { id: 8, initials: 'SOL', x: 8, y: 8 });
    await claim(one, 0);
    await claim(two, 1);
    await claim(pretender, 2);
    await claim(loner, 3);
    await one.sector.alarm();
    assert.deepEqual(logged(), [[word(0).w, 'ONE', g.lid], [word(1).w, 'TWO', g.lid], [word(2).w, 'NOT', ''], [word(3).w, 'SOL', '']]);
    // The guild's name went with its first word, and the code and tag went nowhere.
    assert.deepEqual(log.raw.prepare('SELECT guild, a, b, c FROM survey_log_guilds').all().map((r) => ({ ...r })), [{ guild: g.lid, a: 11, b: 0, c: 0 }]);
    const everything = JSON.stringify(log.raw.prepare('SELECT * FROM survey_log').all());
    assert.ok(!everything.includes(g.code) && !everything.includes(g.tag));
  });

  test('count for every guild a member is in: the first in their row, the others beside it', async () => {
    const other = await w.make(1, 'ONE', [3, 2, 11]);
    const third = await w.make(1, 'ONE', [8, 7, 7]);
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guilds: [other.code, g.code, third.code], x: 5, y: 5 });
    const two = await w.player(0, 0, { id: 2, initials: 'TWO', guild: g.code, x: 6, y: 6 });
    await claim(one, 0);
    await claim(two, 1);
    await one.sector.alarm();
    assert.deepEqual(logged(), [[word(0).w, 'ONE', other.lid], [word(1).w, 'TWO', g.lid]]);
    const extra = log.raw.prepare('SELECT guild FROM survey_log_extra_guilds ORDER BY guild').all().map((r) => r.guild);
    assert.deepEqual(extra, [g.lid, third.lid].sort());
    // Each guild counts it, and every guild's name went to the log.
    const days = Object.fromEntries(log.raw.prepare('SELECT guild, n FROM survey_log_guild_days').all().map((r) => [r.guild, r.n]));
    assert.deepEqual(days, { [other.lid]: 1, [g.lid]: 2, [third.lid]: 1 });
    assert.equal(log.raw.prepare('SELECT COUNT(*) AS n FROM survey_log_guilds').get().n, 3);
  });

  test('stop counting for a guild once its member has left it', async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    await w.call(`/v1/survey/guilds/${g.code}/leave`, { token: token(1) });
    await w.tick(one, GUILD_RECHECK_MS);
    await claim(one, 0);
    await one.sector.alarm();
    assert.deepEqual(logged(), [[word(0).w, 'ONE', '']]);
  });
});
