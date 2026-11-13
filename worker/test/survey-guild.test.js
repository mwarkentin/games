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
import { GUILD_CODE, GUILD_MAX, GUILD_RECHECK_MS, GUILD_WORDS, Guild, SEEN_MS, idleShown, matesFor, noteMates, passMates } from '../src/survey-guild.js';
import { FLAG_HIDDEN, REFRESH_MS, playerId, snapshot } from '../src/survey-social.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 10, 13, 12);
const token = (n) => n.toString(16).padStart(32, '0');
const settle = async () => { for (let i = 0; i < 5; i++) await new Promise((resolve) => setImmediate(resolve)); };
const MIGRATIONS = new URL('../migrations/', import.meta.url);

function fakeState() {
  const db = new DatabaseSync(':memory:');
  const sockets = [];
  return {
    db,
    sockets,
    storage: { sql: { exec(query, ...b) { const rows = db.prepare(query).all(...b); return { toArray: () => rows, one: () => rows[0] }; } } },
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

// Sectors, an Atlas and guilds that reach each other, as the runtime's bindings would.
function world({ db = null } = {}) {
  const clock = { now: NOW }, sectors = new Map(), guilds = new Map();
  const env = { ALLOWED_ORIGINS: ORIGIN, ...(db ? { DB: db } : {}) };
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
  async function player(sx, sy, { id, initials = 'ABC', guild = null, hide = false, x, y } = {}) {
    const sector = sectorAt(`${sx},${sy}`), ws = fakeSocket();
    sector.join(ws, sx, sy);
    const p = { ws, sector, say: (m) => sector.webSocketMessage(ws, JSON.stringify(m)), pid: await playerId(token(id)) };
    await p.say({ t: 'me', initials, token: token(id), hide, ...(guild ? { guild } : {}) });
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
    assert.deepEqual(g.name, [3, 15, 7]);
    assert.deepEqual(g.members, [[await playerId(token(1)), 'ONE', NOW]]);
    assert.deepEqual(await w.call(`/v1/survey/guilds/${g.code}`), [200, { name: [3, 15, 7], size: 1 }]);
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
    assert.deepEqual(last.who.find((e) => e[0] === one.pid).slice(5), [0, g.tag]);
    assert.equal(last.who.find((e) => e[0] === pretender.pid).length, 6);
  });

  test("takes the tag off someone who has left, when it checks again, and keeps 'last seen' current", async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const seen = () => w.guildAt(g.code).sql.exec('SELECT seen FROM members WHERE pid = ?', one.pid).one().seen;
    assert.equal(one.sector.everyone().get(one.ws).tag, g.tag);
    await w.tick(one, SEEN_MS);
    assert.equal(seen(), NOW);  // not checked again yet
    await w.call(`/v1/survey/guilds/${g.code}/leave`, { token: token(1) });
    await w.tick(one, GUILD_RECHECK_MS - SEEN_MS);
    assert.equal(one.sector.everyone().get(one.ws).tag, null);
    // A member still in it is seen again at each check.
    const two = await w.player(0, 0, { id: 2, initials: 'TWO', guild: g.code, x: 6, y: 6 });
    const seenTwo = () => w.guildAt(g.code).sql.exec('SELECT seen FROM members WHERE pid = ?', two.pid).one().seen;
    const first = seenTwo();
    await w.tick(two, GUILD_RECHECK_MS);
    assert.equal(seenTwo(), first + GUILD_RECHECK_MS);
  });

  test('tells members which of their guild are online and where, as it changes, and nobody else', async () => {
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const outsider = await w.player(0, 0, { id: 7, initials: 'OUT', x: 7, y: 7 });
    const two = await w.player(3, 3, { id: 2, initials: 'TWO', guild: g.code, hide: true, x: 3 * SECTOR + 50, y: 3 * SECTOR + 2 });
    await w.tick(two);                // 3,3 reports TWO, hidden but in the guild
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
    // A member closing the game drops off at once, hidden or not, even just
    // after positions went out, when nothing else would report it.
    w.clock.now += REPORT_MS;
    await two.say({ t: 'pos', x: 3 * SECTOR + 51, y: 3 * SECTOR + 2 });
    await settle();
    w.clock.now += 10;
    two.ws.close();
    await two.sector.webSocketClose(two.ws);
    await settle();
    await w.tick(one, REFRESH_MS);
    assert.deepEqual(one.ws.last('guild').on.map((e) => e[0]), [one.pid]);
    // A hidden member stays off the public list, while their guild still sees them.
    assert.equal(snapshot(w.atlas.load().values(), w.clock.now, ONLINE_MS).sectors.flatMap((s) => s[2]).some((e) => e[0] === two.pid), false);
  });

  test('a hidden member hears emotes from their guild, from anywhere', async () => {
    const hidden = await w.player(3, 3, { id: 2, initials: 'TWO', guild: g.code, hide: true, x: 3 * SECTOR + 50, y: 3 * SECTOR + 2 });
    const mate = await w.player(0, 0, { id: 1, initials: 'ONE', guild: g.code, x: 5, y: 5 });
    const stranger = await w.player(0, 0, { id: 7, initials: 'OUT', x: 6, y: 6 });
    await mate.say({ t: 'emote', to: hidden.pid, e: 'wave', s: [3, 3] });
    await stranger.say({ t: 'emote', to: hidden.pid, e: 'wave', s: [3, 3] });
    assert.equal(mate.ws.last('emoted').ok, true);
    assert.equal(stranger.ws.last('emoted').error, 'gone');
    assert.deepEqual(hidden.ws.all('emote').map((m) => m.ini), ['ONE']);
  });
});

test("the Atlas's index of who's online forgets sectors that stop reporting", () => {
  const atlas = {};
  noteMates(atlas, '0,0', [['aaaaaaaaaaaa', 'ONE', 1, 1, 0, 0, 'deadbeef'], ['bbbbbbbbbbbb', 'TWO', 2, 2, 0, FLAG_HIDDEN, 'deadbeef']], NOW);
  noteMates(atlas, '1,0', [['cccccccccccc', 'SIX', 4, 1, 3, 0, 'deadbeef']], NOW + 1000);
  assert.deepEqual(matesFor(atlas, ['deadbeef', 'feedface'], NOW + 2000, ONLINE_MS), {
    deadbeef: [['aaaaaaaaaaaa', 'ONE', 1, 1, 0], ['bbbbbbbbbbbb', 'TWO', 2, 2, 0], ['cccccccccccc', 'SIX', 4, 1, 0]],
    feedface: [],
  });
  noteMates(atlas, '0,0', [], NOW + 3000);  // its members left
  assert.deepEqual(matesFor(atlas, ['deadbeef'], NOW + 3000, ONLINE_MS).deadbeef.map((e) => e[0]), ['cccccccccccc']);
  assert.deepEqual(matesFor(atlas, ['deadbeef'], NOW + 1000 + ONLINE_MS, ONLINE_MS).deadbeef, []);
  assert.deepEqual([0, 19, 20, 59, 60, 119, 120, 3601].map(idleShown), [0, 0, 20, 20, 60, 60, 120, 3600]);
});

test("the game's lists of words for names are as long as the Worker allows", () => {
  const html = readFileSync(new URL('../../letterfield.html', import.meta.url), 'utf8');
  const list = (name) => {
    const m = html.match(new RegExp(`const ${name} = \\[([\\s\\S]*?)\\];`));
    assert.ok(m, `letterfield.html lost ${name}`);
    return [...m[1].matchAll(/\[?'([A-Za-z]+)'/g)].map((w) => w[1]);
  };
  const lists = ['GUILD_FIRST', 'GUILD_SECOND', 'GUILD_THIRD'].map(list);
  assert.deepEqual(lists.map((l) => l.length), GUILD_WORDS);
  for (const l of lists) assert.equal(new Set(l).size, l.length, 'a word twice');
});
