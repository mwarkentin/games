// Tests for linking another device to a player (src/players.js). Run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { beforeEach, describe, test } from 'node:test';

import worker from '../src/index.js';
import { FINDS_MAX, KEEP_MS, LINK_CODE, LINK_MS, Player, RECOVERY_CODE, SYNC_GAP_MS, cleanCarry, recoveryKeys, routeLinks, routePlayers, routeRecovery } from '../src/players.js';
import { playerId } from '../src/survey-social.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 10, 13, 12);
const MIGRATIONS = new URL('../migrations/', import.meta.url);
const token = (n) => n.toString(16).padStart(32, '0');

// The parts of D1 the links use, with the leaderboard's migrations.
function fakeD1() {
  const db = new DatabaseSync(':memory:');
  for (const file of readdirSync(MIGRATIONS).sort()) db.exec(readFileSync(new URL(file, MIGRATIONS), 'utf8'));
  const statement = (sql, params = []) => ({
    bind: (...values) => statement(sql, values),
    first: async (column) => { const row = db.prepare(sql).get(...params); return row ? (column ? row[column] : row) : null; },
    run: async () => { db.prepare(sql).run(...params); return { success: true }; },
  });
  return { prepare: (sql) => statement(sql), raw: db };
}

// A Durable Object's storage: SQLite, an alarm and deleteAll.
function fakeState() {
  let db = new DatabaseSync(':memory:');
  const state = {
    alarm: null,
    storage: {
      sql: { exec(query, ...b) { const rows = db.prepare(query).all(...b); return { toArray: () => rows, one: () => rows[0] }; } },
      setAlarm: async (t) => { state.alarm = t; },
      deleteAlarm: async () => { state.alarm = null; },
      deleteAll: async () => { db = new DatabaseSync(':memory:'); },
    },
    tables: () => db.prepare("SELECT name FROM sqlite_master WHERE type = 'table'").all().map((r) => r.name),
  };
  return state;
}

// The PLAYERS namespace: a Player per name, on one clock.
function fakePlayers(clock) {
  const players = new Map();
  const get = (name) => {
    if (!players.has(name)) { const state = fakeState(), p = new Player(state, {}); p.now = () => clock.now; p.state = state; players.set(name, p); }
    return players.get(name);
  };
  return { players, get: (id) => ({ fetch: (url, init) => get(id).fetch(new Request(url, init)) }), idFromName: (name) => name, player: get };
}

describe('linking a device', () => {
  let env, ip;
  beforeEach(() => { env = { ALLOWED_ORIGINS: ORIGIN, DB: fakeD1(), PLAYERS: fakePlayers({ now: NOW }) }; ip = '203.0.113.5'; });
  const call = async (path, body, { now = NOW, method = 'POST', origin = ORIGIN } = {}) => {
    const res = await routeLinks(new Request(`https://survey.test${path}`, {
      method, headers: { Origin: origin, 'CF-Connecting-IP': ip }, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }), env, now);
    return [res.status, await res.json()];
  };
  const carry = { initials: 'MLW', guild: { code: 'KMN234', name: [11, 0, 0], tag: 'c0ffee42' }, muted: ['3f9a01c27be4'], listed: false, emotes: true };

  test('hands the token and settings to whoever redeems the code, once', async () => {
    const [status, made] = await call('/v1/link', { token: token(1), carry });
    assert.equal(status, 201);
    assert.match(made.code, LINK_CODE);
    assert.equal(made.expires, NOW + LINK_MS);
    assert.deepEqual(await call(`/v1/link/${made.code}/status`, { token: token(1) }), [200, { state: 'waiting' }]);
    assert.deepEqual(await call(`/v1/link/${made.code.toLowerCase()}`, {}), [200, { token: token(1), carry }]);
    assert.deepEqual(await call(`/v1/link/${made.code}`, {}), [404, { error: 'no such code, or it has run out' }]);
    assert.deepEqual(await call(`/v1/link/${made.code}/status`, { token: token(1) }), [200, { state: 'used' }]);
    // What it carried isn't kept once it's been handed over.
    assert.equal(env.DB.raw.prepare('SELECT carry FROM links').get().carry, '');
    // And the player's devices keep in step from now on.
    assert.ok(env.PLAYERS.player(await playerId(token(1))).meta());
  });

  test('says nothing about a code to anyone who did not make it', async () => {
    const [, made] = await call('/v1/link', { token: token(1), carry });
    assert.deepEqual(await call(`/v1/link/${made.code}/status`, { token: token(2) }), [200, { state: 'gone' }]);
    assert.deepEqual(await call('/v1/link/ABCDEFGH/status', { token: token(1) }), [200, { state: 'gone' }]);
    await call(`/v1/link/${made.code}`, {});
    assert.deepEqual(await call(`/v1/link/${made.code}/status`, { token: token(2) }), [200, { state: 'gone' }]);
  });

  test('runs out after ten minutes', async () => {
    const [, made] = await call('/v1/link', { token: token(1), carry });
    assert.deepEqual(await call(`/v1/link/${made.code}/status`, { token: token(1) }, { now: NOW + LINK_MS + 1 }), [200, { state: 'gone' }]);
    assert.equal((await call(`/v1/link/${made.code}`, {}, { now: NOW + LINK_MS + 1 }))[0], 404);
    // Expired codes are swept when the next is made.
    await call('/v1/link', { token: token(2), carry: {} }, { now: NOW + LINK_MS + 2 });
    assert.equal(env.DB.raw.prepare('SELECT COUNT(*) AS n FROM links').get().n, 1);
  });

  test('takes only a real token and settings it knows', async () => {
    assert.equal((await call('/v1/link', { token: 'nope', carry }))[0], 400);
    for (const bad of [{ initials: 'mlw' }, { guild: { code: 'KMN234', name: ['x'], tag: 'c0ffee42' } }, { muted: ['nope'] }, { muted: Array(201).fill('3f9a01c27be4') }, { listed: 'yes' }]) {
      assert.equal((await call('/v1/link', { token: token(1), carry: bad }))[0], 400, JSON.stringify(bad));
    }
    assert.deepEqual(cleanCarry({ initials: 'ABC', extra: 'dropped' }), { initials: 'ABC', guild: null, muted: [], listed: true, emotes: true });
    assert.equal((await call('/v1/link', { token: token(1), carry }, { origin: 'https://evil.test' }))[0], 403);
    assert.equal((await call('/v1/link', undefined, { method: 'GET' }))[0], 405);
  });

  test('limits codes made and tried per address, wrong tries included', async () => {
    const made = [];
    for (let i = 0; i < 11; i++) made.push((await call('/v1/link', { token: token(1), carry: {} }))[0]);
    assert.deepEqual(made.slice(-2), [201, 429]);
    ip = '203.0.113.6';
    const tries = [];
    for (let i = 0; i < 21; i++) tries.push((await call('/v1/link/ABCDEFGH', {}))[0]);
    assert.deepEqual(tries.slice(-2), [404, 429]);
  });

  test('looks codes up by their key', () => {
    const plan = (sql) => env.DB.raw.prepare(`EXPLAIN QUERY PLAN ${sql}`).all('X').map((r) => r.detail).join(' | ');
    assert.match(plan('SELECT token, expires FROM links WHERE code = ?'), /USING PRIMARY KEY \(code=\?\)/);
    assert.match(plan('UPDATE links SET used = 1 WHERE code = ? AND used = 0 AND expires >= 0 RETURNING token, carry'), /USING PRIMARY KEY \(code=\?\)/);
  });

  test('is what the Worker does with the paths', async () => {
    const res = await worker.fetch(new Request('https://survey.test/v1/link', {
      method: 'POST', headers: { Origin: ORIGIN }, body: JSON.stringify({ token: token(1), carry: {} }),
    }), env);
    assert.equal(res.status, 201);
    assert.equal(routeLinks(new Request('https://survey.test/v1/linked'), env), null);
  });
});

describe('syncing linked devices', () => {
  let clock, env;
  const find = (w, x, more = {}) => ({ w, x, y: 3, d: 0, t: NOW, s: 0, ...more });
  const nova = (rx) => ({ rx, ry: 0, t: NOW, w: 'COMET', x: rx * 48, y: 2, d: 0, by: 'MLW', mine: true, solo: false });
  beforeEach(() => { clock = { now: NOW }; env = { ALLOWED_ORIGINS: ORIGIN, PLAYERS: fakePlayers(clock) }; });
  const sync = async (n, body, path = 'sync') => {
    clock.now += SYNC_GAP_MS;
    const res = await routePlayers(new Request(`https://survey.test/v1/player/${path}`, {
      method: 'POST', headers: { Origin: ORIGIN }, body: JSON.stringify({ token: token(n), ...body }),
    }), env);
    return [res.status, await res.json()];
  };
  const start = async (n) => env.PLAYERS.player(await playerId(token(n))).start();

  test('is off, and keeps nothing, until a link starts it', async () => {
    assert.deepEqual(await sync(1, { finds: [find('COMET', 1)] }), [200, { off: true }]);
    assert.deepEqual(env.PLAYERS.player(await playerId(token(1))).state.tables(), []);
  });

  test("carries one device's finds, supernovas and settings to another, and only what is new", async () => {
    await start(1);
    const settings = { initials: 'MLW', guild: null, muted: [], listed: true, emotes: true };
    const [, a] = await sync(1, { epoch: '', since: 0, finds: [find('COMET', 1), find('ORBIT', 2)], novas: [nova(1)], settings, settingsAt: 5 });
    assert.deepEqual([a.finds, a.novas, a.at], [[], [], 1]);  // its own come back to nobody
    assert.match(a.epoch, /^[0-9a-f]{8}$/);
    // The other device, new to it, hears everything, settings included.
    const [, b] = await sync(1, { epoch: '', since: 0, finds: [find('NEBULA', 3)], settingsAt: 0 });
    assert.deepEqual(b.finds.map((f) => f.w).sort(), ['COMET', 'ORBIT']);
    assert.deepEqual([b.novas, b.settings, b.settingsAt, b.at], [[nova(1)], settings, 5, 2]);
    // The first, next time, hears only the second's.
    const [, again] = await sync(1, { epoch: a.epoch, since: a.at, settingsAt: 5 });
    assert.deepEqual([again.finds.map((f) => f.w), again.novas, 'settings' in again], [['NEBULA'], [], false]);
  });

  test('keeps charted first once either device has it, and a find once', async () => {
    await start(1);
    const [, a] = await sync(1, { finds: [find('COMET', 1, { f: 1, n: 40 })] });
    await sync(1, { epoch: a.epoch, since: a.at, finds: [find('COMET', 1), find('COMET', 1)] });
    const [, b] = await sync(1, { since: 0 });
    assert.deepEqual(b.finds, [find('COMET', 1, { f: 1, n: 40 })]);
    await sync(1, { epoch: a.epoch, since: b.at, finds: [find('ORBIT', 2)] });
    const [, c] = await sync(1, { epoch: a.epoch, since: b.at });
    await sync(1, { epoch: a.epoch, since: c.at, finds: [find('ORBIT', 2, { f: 1 })] });
    const [, d] = await sync(1, { epoch: a.epoch, since: c.at });
    assert.deepEqual(d.finds, [find('ORBIT', 2, { f: 1 })]);
  });

  test('settings go with whichever device changed them last', async () => {
    await start(1);
    const as = (initials) => ({ initials, guild: null, muted: [], listed: true, emotes: true });
    await sync(1, { settings: as('AAA'), settingsAt: 10 });
    await sync(1, { settings: as('BBB'), settingsAt: 9 });
    const [, b] = await sync(1, { settingsAt: 0 });
    assert.deepEqual([b.settings.initials, b.settingsAt], ['AAA', 10]);
    assert.equal((await sync(1, { settings: { initials: 'nope' }, settingsAt: 11 }))[1].settings?.initials, undefined);
  });

  test('a device from before a forget starts over', async () => {
    await start(1);
    const [, a] = await sync(1, { finds: [find('COMET', 1)] });
    assert.deepEqual(await sync(1, {}, 'forget'), [200, { off: true }]);
    assert.deepEqual(await sync(1, { epoch: a.epoch, since: a.at }), [200, { off: true }]);
    await start(1);
    await sync(1, { finds: [find('ORBIT', 2)] });
    const [, b] = await sync(1, { epoch: a.epoch, since: a.at });  // its version means nothing now
    assert.notEqual(b.epoch, a.epoch);
    assert.deepEqual(b.finds.map((f) => f.w), ['ORBIT']);
  });

  test('takes only finds it can read, up to its limits, and a sync every few seconds', async () => {
    await start(1);
    const [, a] = await sync(1, { finds: [find('comet', 1), find('COMET', 1.5), { w: 'COMET' }, find('COMET', 1, { d: 9 }), find('COMET', 1)] });
    assert.equal(a.at, 1);
    const [, b] = await sync(1, { since: 0 });
    assert.deepEqual(b.finds.map((f) => f.w), ['COMET']);
    clock.now -= SYNC_GAP_MS - 1;
    assert.equal((await sync(1, {}))[0], 429);
    assert.equal((await sync(1, { finds: Array(2001).fill(find('ORBIT', 1)) }))[0], 413);
    // A full set of notes takes no more.
    const p = env.PLAYERS.player(await playerId(token(1)));
    for (let i = 1; i < FINDS_MAX; i++) p.sql.exec('INSERT INTO finds (k, body, v) VALUES (?, ?, 1)', `X${i}`, '{}');
    const [, c] = await sync(1, { since: 1, finds: [find('ORBIT', 5)] });
    assert.deepEqual([c.at, p.sql.exec('SELECT COUNT(*) AS n FROM finds').one().n], [1, FINDS_MAX]);
  });

  test("forgets a player nobody's synced for half a year", async () => {
    await start(1);
    await sync(1, { finds: [find('COMET', 1)] });
    const p = env.PLAYERS.player(await playerId(token(1)));
    const first = p.state.alarm;
    assert.equal(first, clock.now + KEEP_MS);
    clock.now += KEEP_MS - 1000;
    await sync(1, {});
    clock.now = first;  // the first alarm, put off by the later sync
    await p.alarm();
    assert.ok(p.meta(), 'synced within the half year');
    assert.equal(p.state.alarm, p.meta().synced + KEEP_MS);
    clock.now = p.state.alarm;
    await p.alarm();
    assert.equal(p.meta(), null);
  });

  test('needs a real token and the site, and is what the Worker does with the paths', async () => {
    assert.equal(routePlayers(new Request('https://survey.test/v1/player/nope'), env), null);
    const bad = await routePlayers(new Request('https://survey.test/v1/player/sync', { method: 'POST', headers: { Origin: ORIGIN }, body: '{"token":"x"}' }), env);
    assert.equal(bad.status, 400);
    const away = await routePlayers(new Request('https://survey.test/v1/player/sync', { method: 'POST', headers: { Origin: 'https://evil.test' }, body: JSON.stringify({ token: token(1) }) }), env);
    assert.equal(away.status, 403);
    const res = await worker.fetch(new Request('https://survey.test/v1/player/sync', { method: 'POST', headers: { Origin: ORIGIN }, body: JSON.stringify({ token: token(1) }) }), env);
    assert.deepEqual(await res.json(), { off: true });
  });
});

describe('recovery codes', () => {
  let clock, env, ip;
  beforeEach(() => { clock = { now: NOW }; env = { ALLOWED_ORIGINS: ORIGIN, DB: fakeD1(), PLAYERS: fakePlayers(clock) }; ip = '203.0.113.7'; });
  const call = async (path, body, { origin = ORIGIN } = {}) => {
    const res = await routeRecovery(new Request(`https://survey.test/v1/recovery${path}`, {
      method: 'POST', headers: { Origin: origin, 'CF-Connecting-IP': ip }, body: JSON.stringify(body),
    }), env, clock.now);
    return [res.status, await res.json()];
  };
  const player = async (n) => env.PLAYERS.player(await playerId(token(n)));

  test('brings the player back on any device, and keeps their notes while it does', async () => {
    const [status, made] = await call('', { token: token(1) });
    assert.equal(status, 201);
    assert.match(made.code, RECOVERY_CODE);
    assert.equal(made.made, NOW);
    assert.equal((await player(1)).meta().saved, 1);
    // Typed in any case, with or without its dashes.
    const typed = made.code.toLowerCase().match(/.{4}/g).join('-');
    assert.deepEqual(await call('/use', { code: typed }), [200, { token: token(1) }]);
    assert.deepEqual(await call('/use', { code: made.code }), [200, { token: token(1) }]);  // as often as it's needed
    assert.deepEqual(await call('/use', { code: 'ABCDEFGHJKMNPQRSTUVW' }), [404, { error: 'no such code' }]);
  });

  test("keeps neither the code nor the token where anyone could read them", async () => {
    const [, made] = await call('', { token: token(1) });
    const rows = env.DB.raw.prepare('SELECT * FROM recovery').all();
    assert.equal(rows.length, 1);
    const stored = JSON.stringify(rows);
    assert.ok(!stored.includes(token(1)) && !stored.includes(made.code), stored);
    assert.equal(rows[0].id, (await recoveryKeys(made.code)).id);
    assert.equal(rows[0].pid, await playerId(token(1)));
  });

  test('a new code replaces the old, and a removed one works no more', async () => {
    const [, first] = await call('', { token: token(1) });
    const [, second] = await call('', { token: token(1) });
    assert.notEqual(first.code, second.code);
    assert.equal((await call('/use', { code: first.code }))[0], 404);
    assert.equal((await call('/use', { code: second.code }))[0], 200);
    assert.deepEqual(await call('/remove', { token: token(1) }), [200, { ok: true }]);
    assert.equal((await call('/use', { code: second.code }))[0], 404);
    const p = await player(1);
    assert.equal(p.meta().saved, 0);
    assert.equal(p.state.alarm, clock.now + KEEP_MS);  // back under the clear-out
  });

  test('a saved code keeps the notes past the clear-out; stopping everywhere takes the code too', async () => {
    const [, made] = await call('', { token: token(1) });
    const p = await player(1);
    clock.now += 2 * KEEP_MS;
    await p.alarm();
    assert.ok(p.meta(), 'kept while a code is saved');
    const res = await routePlayers(new Request('https://survey.test/v1/player/forget', { method: 'POST', headers: { Origin: ORIGIN }, body: JSON.stringify({ token: token(1) }) }), env);
    assert.deepEqual(await res.json(), { off: true });
    assert.equal(p.meta(), null);
    assert.equal((await call('/use', { code: made.code }))[0], 404);
  });

  test('limits codes made, and tries along with link codes', async () => {
    const made = [];
    for (let i = 0; i < 6; i++) made.push((await call('', { token: token(1) }))[0]);
    assert.deepEqual(made.slice(-2), [201, 429]);
    ip = '203.0.113.8';
    const tries = [];
    for (let i = 0; i < 20; i++) tries.push((await call('/use', { code: 'nope' }))[0]);
    assert.ok(tries.every((t) => t === 404));
    const link = await routeLinks(new Request('https://survey.test/v1/link/ABCDEFGH', { method: 'POST', headers: { Origin: ORIGIN, 'CF-Connecting-IP': ip }, body: '{}' }), env, clock.now);
    assert.equal(link.status, 429);
  });

  test('needs a real token and the site, and is what the Worker does with the paths', async () => {
    assert.equal((await call('', { token: 'nope' }))[0], 400);
    assert.equal((await call('', { token: token(1) }, { origin: 'https://evil.test' }))[0], 403);
    assert.equal(routeRecovery(new Request('https://survey.test/v1/recovered'), env), null);
    const res = await worker.fetch(new Request('https://survey.test/v1/recovery', { method: 'POST', headers: { Origin: ORIGIN }, body: JSON.stringify({ token: token(2) }) }), env);
    assert.equal(res.status, 201);
  });
});
