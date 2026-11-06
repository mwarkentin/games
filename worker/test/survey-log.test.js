// Tests for the survey's log (src/survey-log.js, and the Sector's copying in
// src/survey.js), run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"
// D1 is a stand-in backed by node:sqlite and loaded with the real
// migrations, as in leaderboard.test.js, with batch() as one transaction.

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

import worker from '../src/index.js';
import { RC, THEMES, VOCAB, chunk, fdiv, keyOf, regionName, regionTheme } from '../src/letterfield-world.js';
import {
  DAY_MS, DAY_SQL, HOUR_AFTER_SQL, HOUR_MS, HOUR_SQL, LIVE_CACHE_S, LOG_BATCH, LOG_MS, LOG_PAGE, LOG_RETRY_MAX_MS, SETTLED_MS,
  forgetLog, readDay, readHour, routeLog, writeLog,
} from '../src/survey-log.js';
import { Sector } from '../src/survey.js';

const MIGRATIONS = new URL('../migrations/', import.meta.url);
const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 10, 6, 14, 30);
const HOUR = Math.floor(NOW / HOUR_MS);
const DAY = Math.floor(NOW / DAY_MS);

function fakeD1() {
  const db = new DatabaseSync(':memory:');
  for (const file of readdirSync(MIGRATIONS).sort()) db.exec(readFileSync(new URL(file, MIGRATIONS), 'utf8'));
  const log = [];
  const statement = (sql, params = []) => ({
    sql, params,
    bind: (...values) => statement(sql, values),
    all: async () => { log.push({ sql, params }); return { results: db.prepare(sql).all(...params) }; },
    run: () => db.prepare(sql).run(...params),
  });
  const d1 = {
    raw: db, log, fail: null, batches: 0,
    prepare: (sql) => statement(sql),
    async batch(statements) {
      if (d1.fail) throw new Error(d1.fail);
      d1.batches++;
      db.exec('BEGIN');
      try { for (const s of statements) { log.push({ sql: s.sql, params: s.params }); s.run(); } db.exec('COMMIT'); } catch (e) { db.exec('ROLLBACK'); throw e; }
    },
    rows: () => db.prepare('SELECT at, key, w, x, y, d, s, initials FROM survey_log ORDER BY at, key').all().map((r) => ({ ...r })),
  };
  return d1;
}

// A claim as a sector stores it, for a hidden word in chunk (cx, cy).
function stored(cx, cy, n, at, initials = 'ZED') {
  const { w, x, y, d } = chunk(cx, cy).words[n];
  return { key: keyOf(w, x, y, d), w, x, y, d, s: 0, initials, at };
}

const plan = (db, sql, ...params) => db.raw.prepare(`EXPLAIN QUERY PLAN ${sql}`).all(...params).map((r) => r.detail).join(' | ');

describe('writeLog', () => {
  test('copies claims in batches D1 can take, and ignores ones it already has', async () => {
    const db = fakeD1();
    const rows = Array.from({ length: 30 }, (_, i) => stored(i % 6, Math.floor(i / 6), 0, NOW + i));
    await writeLog(db, rows);
    assert.equal(db.rows().length, 30);
    // 12 rows a statement, since a row binds 8 values and D1 allows 100.
    assert.equal(db.log.length, 3);
    assert.ok(db.log.every((q) => q.params.length <= 100));
    await writeLog(db, rows.slice(0, 5));
    assert.equal(db.rows().length, 30);
    assert.deepEqual(db.rows()[0], { ...rows[0] });
  });
});

describe('reading the log', () => {
  let db;
  beforeEach(async () => {
    db = fakeD1();
    forgetLog();
    await writeLog(db, [
      stored(0, 0, 0, HOUR * HOUR_MS - 1),          // the hour before
      stored(0, 0, 1, HOUR * HOUR_MS),              // the first moment of this hour
      stored(-30, 5, 0, HOUR * HOUR_MS + 60000, ''),
      stored(3, -7, 2, NOW),
      stored(5, 5, 0, (HOUR + 1) * HOUR_MS),        // the next hour
    ]);
  });

  test('gives an hour oldest first, naming each place and theme', async () => {
    const page = await readHour(db, HOUR);
    assert.equal(page.hour, HOUR);
    assert.equal(page.next, null);
    assert.deepEqual(page.entries.map((e) => e[6]), [HOUR * HOUR_MS, HOUR * HOUR_MS + 60000, NOW]);
    const [w, x, y, d, s, initials, at, th] = page.entries[1];
    assert.deepEqual([w, x, y, d, s, initials, at], Object.values((({ w, x, y, d, s, initials, at }) => ({ w, x, y, d, s, initials, at }))(stored(-30, 5, 0, HOUR * HOUR_MS + 60000, ''))));
    const rx = fdiv(x, RC), ry = fdiv(y, RC);
    assert.equal(th, regionTheme(rx, ry));
    assert.equal(page.places[`${rx},${ry}`], regionName(rx, ry));
    assert.deepEqual(page.themes[th], [THEMES[th].name, THEMES[th].hue]);
    assert.equal(Object.keys(page.places).length, 3);
  });

  test('gives a stray word its own theme', async () => {
    await writeLog(db, [{ key: keyOf('MONET', 1, 2, 0), w: 'MONET', x: 1, y: 2, d: 0, s: 1, initials: 'ABC', at: NOW + 5 }]);
    const stray = (await readHour(db, HOUR)).entries.find((e) => e[0] === 'MONET');
    assert.equal(stray[4], 1);
    assert.equal(stray[7], VOCAB.get('MONET'));
  });

  test('pages through a busy hour', async () => {
    const busy = [];
    for (let i = 0; i < LOG_PAGE + 20; i++) busy.push(stored(i % 40, Math.floor(i / 40), 3, HOUR * HOUR_MS + 1000 + i));
    await writeLog(db, busy);
    const first = await readHour(db, HOUR);
    assert.equal(first.entries.length, LOG_PAGE);
    assert.match(first.next, /^\d+~[A-Z]+~-?\d+~-?\d+~[0-7]$/);
    const [at, ...key] = first.next.split('~');
    const second = await readHour(db, HOUR, { at: Number(at), key: key.join('~') });
    assert.equal(second.next, null);
    assert.equal(first.entries.length + second.entries.length, LOG_PAGE + 23);
    const seen = new Set([...first.entries, ...second.entries].map((e) => keyOf(e[0], e[1], e[2], e[3])));
    assert.equal(seen.size, LOG_PAGE + 23);
  });

  test('counts each hour of a day', async () => {
    const day = await readDay(db, DAY);
    assert.equal(day.hours.length, 24);
    assert.equal(day.hours[14], 3);
    assert.equal(day.hours[13], 1);
    assert.equal(day.hours[15], 1);
    assert.equal(day.total, 5);
  });

  test('reads only the rows asked for, along the table\'s own order', () => {
    const from = HOUR * HOUR_MS, to = from + HOUR_MS;
    for (const p of [plan(db, HOUR_SQL, from, to, 10), plan(db, HOUR_AFTER_SQL, from, to, from, 'A', 10), plan(db, DAY_SQL, from, to)]) {
      assert.match(p, /SEARCH survey_log USING PRIMARY KEY \(at>\? AND at<\?\)/);
      assert.doesNotMatch(p, /SCAN|TEMP B-TREE FOR ORDER BY/);
    }
  });
});

describe('routeLog', () => {
  let env;
  beforeEach(async () => {
    forgetLog();
    env = { DB: fakeD1(), ALLOWED_ORIGINS: ORIGIN };
    await writeLog(env.DB, [stored(0, 0, 0, NOW - 1000), stored(1, 0, 0, NOW - 2 * DAY_MS)]);
  });
  afterEach(() => { delete globalThis.caches; });
  const get = (path, { origin = ORIGIN, method = 'GET', now = NOW } = {}) =>
    routeLog(new Request(`https://survey.test${path}`, { method, headers: origin ? { Origin: origin } : {} }), env, now);

  test('answers an hour and a day, for pages on the site', async () => {
    const hour = await get(`/v1/survey/log/hour/${HOUR}`);
    assert.equal(hour.status, 200);
    assert.equal(hour.headers.get('Access-Control-Allow-Origin'), ORIGIN);
    assert.equal((await hour.json()).entries.length, 1);
    const day = await get(`/v1/survey/log/day/${DAY - 2}`);
    assert.equal((await day.json()).total, 1);
    assert.equal((await get(`/v1/survey/log/hour/${HOUR}`, { origin: 'https://evil.test' })).headers.get('Access-Control-Allow-Origin'), null);
  });

  test('caches an hour that is over for a day, and the hour still running for seconds', async () => {
    assert.equal((await get(`/v1/survey/log/hour/${HOUR}`)).headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    assert.equal((await get(`/v1/survey/log/day/${DAY}`)).headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    // A claim copied late can still land in the hour just gone, so it settles a while after it ends.
    assert.equal((await get(`/v1/survey/log/hour/${HOUR - 1}`)).headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    const later = HOUR * HOUR_MS + SETTLED_MS;
    assert.equal((await get(`/v1/survey/log/hour/${HOUR - 1}`, { now: later })).headers.get('Cache-Control'), 'public, max-age=86400');
    assert.equal((await get(`/v1/survey/log/day/${DAY - 1}`)).headers.get('Cache-Control'), 'public, max-age=86400');
  });

  test('reads D1 once per answer while it is fresh', async () => {
    const reads = () => env.DB.log.filter((q) => q.sql.startsWith('SELECT')).length;
    await get(`/v1/survey/log/hour/${HOUR}`);
    await get(`/v1/survey/log/hour/${HOUR}`);
    assert.equal(reads(), 1);
    await get(`/v1/survey/log/hour/${HOUR}`, { now: NOW + LIVE_CACHE_S * 1000 });
    assert.equal(reads(), 2);
  });

  test('uses Cloudflare\'s cache where there is one, with each origin\'s own CORS headers', async () => {
    const stored = new Map();
    globalThis.caches = { default: { match: async (r) => stored.get(r.url)?.clone(), put: async (r, res) => { stored.set(r.url, res); } } };
    await get(`/v1/survey/log/day/${DAY - 2}`);
    assert.equal(stored.size, 1);
    const [cached] = stored.values();
    assert.equal(cached.headers.get('Access-Control-Allow-Origin'), null);
    forgetLog();  // another Worker instance
    env.DB.log.length = 0;
    const again = await get(`/v1/survey/log/day/${DAY - 2}`, { origin: 'http://localhost:8000' });
    assert.equal(env.DB.log.length, 0);
    assert.equal((await again.json()).total, 1);
    assert.equal(again.headers.get('Access-Control-Allow-Origin'), null);  // not in ALLOWED_ORIGINS here
  });

  test('turns away times to come, bad cursors and writes', async () => {
    assert.equal((await get(`/v1/survey/log/hour/${HOUR + 1}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/day/${DAY + 1}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/hour/${HOUR}?after=nope`)).status, 400);
    assert.equal((await get(`/v1/survey/log/hour/${HOUR}?after=${NOW}~ZED`)).status, 400);
    assert.equal((await get(`/v1/survey/log/hour/${HOUR}?after=${NOW}~ACORN~1~-2~3`)).status, 200);
    assert.equal((await get(`/v1/survey/log/hour/${HOUR}`, { method: 'POST' })).status, 405);
  });

  test('leaves other paths alone, and is what the Worker does with log paths', async () => {
    assert.equal(get('/v1/survey/world'), null);
    assert.equal(get('/v1/survey/log/hour/-1'), null);
    assert.equal(routeLog(new Request(`https://survey.test/v1/survey/log/hour/${HOUR}`), {}), null);
    const res = await worker.fetch(new Request(`https://survey.test/v1/survey/log/day/${DAY}`, { headers: { Origin: ORIGIN } }), env);
    assert.equal(res.status, 200);
    assert.equal((await res.json()).day, DAY);
  });
});

// A Sector's state with alarms, and a socket that records what it's sent.
function fakeState(db = new DatabaseSync(':memory:')) {
  const sockets = [];
  const state = {
    db, sockets, alarm: null, alarms: 0,
    storage: {
      sql: {
        exec(query, ...bindings) {
          const rows = db.prepare(query).all(...bindings);
          return { toArray: () => rows, one: () => rows[0] };
        },
      },
      setAlarm: (at) => { state.alarm = at; state.alarms++; },
      getAlarm: () => state.alarm,
    },
    acceptWebSocket: (ws) => sockets.push(ws),
    getWebSockets: () => sockets.filter((ws) => ws.open),
  };
  return state;
}
function fakeSocket() {
  let attachment = null;
  return {
    open: true, sent: [],
    send(text) { const f = JSON.parse(text); this.sent.push(...(Array.isArray(f) ? f : [f])); },
    accept() {}, close() { this.open = false; },
    serializeAttachment(v) { attachment = structuredClone(v); },
    deserializeAttachment: () => structuredClone(attachment),
  };
}

describe('Sector copying claims to the log', () => {
  let state, env, sector, clock, logged;
  beforeEach(() => {
    logged = mock.method(console, 'log', () => {});
    mock.timers.enable({ apis: ['setTimeout'] });
    state = fakeState();
    env = { DB: fakeD1() };
    clock = NOW;
    sector = make();
  });
  afterEach(() => { mock.timers.reset(); logged.mock.restore(); });

  function make() {
    const s = new Sector(state, env);
    s.now = () => clock;
    return s;
  }
  function join(s = sector) { const ws = fakeSocket(); s.join(ws, 0, 0); return ws; }
  // A hidden word in sector 0,0, as the game claims it.
  const word = (n) => { const { w, x, y, d } = chunk(n % 16, Math.floor(n / 16)).words[0]; return { w, x, y, d }; };
  async function claim(ws, n) {
    clock += 2000;  // past the socket's claim limit
    await sector.webSocketMessage(ws, JSON.stringify({ t: 'claim', ...word(n) }));
  }
  const fire = async (s = sector) => { assert.ok(state.alarm !== null, 'no alarm set'); clock = Math.max(clock, state.alarm); state.alarm = null; await s.alarm(); };

  test('copies new claims to D1 within LOG_MS, from one alarm', async () => {
    const ws = join();
    assert.equal(state.alarm, null);
    await claim(ws, 0);
    assert.equal(state.alarm, NOW + 2000 + LOG_MS);
    await claim(ws, 1);
    assert.equal(state.alarms, 1);  // the second rides with the first's alarm
    await fire();
    assert.deepEqual(env.DB.rows().map((r) => r.w), [word(0).w, word(1).w]);
    assert.equal(state.alarm, null);
    await claim(ws, 2);
    await fire();
    assert.equal(env.DB.rows().length, 3);
    assert.equal(env.DB.batches, 2);  // each claim went once
  });

  test('keeps claims D1 did not take, and tries again later and later', async () => {
    const ws = join();
    await claim(ws, 0);
    env.DB.fail = 'D1 is down';
    await fire();
    assert.equal(state.alarm, clock + LOG_MS * 2);
    await fire();
    assert.equal(state.alarm, clock + LOG_MS * 4);
    for (let i = 0; i < 10; i++) await fire();
    assert.equal(state.alarm, clock + LOG_RETRY_MAX_MS);
    assert.ok(logged.mock.calls.some((c) => c.arguments[0]?.survey === 'log failed'));
    env.DB.fail = null;
    await claim(ws, 1);
    await fire();
    assert.deepEqual(env.DB.rows().map((r) => r.w), [word(0).w, word(1).w]);
    assert.equal(state.alarm, null);
  });

  test('sends claims made before the log existed, a batch at a time, after waking', async () => {
    // A sector from before the log: claims, but nothing marked as logged.
    const old = new Sector(state, {});
    old.now = () => clock;
    const ws = fakeSocket();
    old.join(ws, 0, 0);
    for (let i = 0; i < LOG_BATCH + 5; i++) {
      const { w, x, y, d } = chunk(i % 16, Math.floor(i / 16) % 16).words[Math.floor(i / 256)];
      state.storage.sql.exec('INSERT INTO claims (key, w, x, y, d, s, initials, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', keyOf(w, x, y, d), w, x, y, d, 0, 'OLD', NOW - 1e6 + i);
    }
    sector = make();  // woken, with the log's D1
    join();
    assert.equal(state.alarm, clock + 1000);
    await fire();
    assert.equal(env.DB.rows().length, LOG_BATCH);
    assert.equal(state.alarm, clock + 1000);  // more to come
    await fire();
    assert.equal(env.DB.rows().length, LOG_BATCH + 5);
    assert.equal(state.alarm, null);
    // Waking again with nothing new sets no alarm.
    sector = make();
    join();
    assert.equal(state.alarm, null);
  });

  test('gives each claim a later time than the last, even if the clock runs back', async () => {
    const ws = join();
    await claim(ws, 0);
    const first = state.storage.sql.exec('SELECT at FROM claims').one().at;
    sector = make();
    clock = first - 60000 - 2000;  // moved to a machine a minute behind
    const again = join();
    await claim(again, 1);
    const ats = state.storage.sql.exec('SELECT at FROM claims ORDER BY at').toArray().map((r) => r.at);
    assert.deepEqual(ats, [first, first + 1]);
    await fire();
    assert.deepEqual(env.DB.rows().map((r) => r.at), [first, first + 1]);
  });

  test('needs no alarm without a log', async () => {
    env = {};
    sector = make();
    const ws = join();
    await claim(ws, 0);
    assert.equal(state.alarm, null);
  });
});
