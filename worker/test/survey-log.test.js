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
  DAY_MS, HOURS_SQL, HOUR_AFTER_SQL, HOUR_MS, HOUR_SQL, LIVE_CACHE_S, LOG_BATCH, LOG_MS, LOG_PAGE, LOG_RETRY_MAX_MS, SETTLED_MS,
  FIRST_SQL, LAST_SQL, SLICES, SLICE_MAX_HOURS, SLICE_PAGE, SLICE_SLOW_CACHE_S, SPAN_CACHE_S, SURVEYORS_SQL, TERRITORIES_SQL,
  TOP_MAX_DAYS, TOP_N, TOP_SLOW_CACHE_S, forgetLog, monthHours, readDay, readHour, readMonth, readSlice, readSpan, readTerritory,
  readTop, routeLog, sliceSql, writeLog,
} from '../src/survey-log.js';
import { AREA, SECTOR, Sector } from '../src/survey.js';

const MIGRATIONS = new URL('../migrations-log/', import.meta.url);
const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 10, 6, 14, 30);
const HOUR = Math.floor(NOW / HOUR_MS);
const DAY = Math.floor(NOW / DAY_MS);

const migrations = () => readdirSync(MIGRATIONS).sort().map((file) => readFileSync(new URL(file, MIGRATIONS), 'utf8'));

// D1 as it stands after the given number of migrations (all by default).
function fakeD1(applied = Infinity) {
  const db = new DatabaseSync(':memory:');
  for (const sql of migrations().slice(0, applied)) db.exec(sql);
  const log = [];
  const statement = (sql, params = []) => ({
    sql, params,
    bind: (...values) => statement(sql, values),
    all: async () => { log.push({ sql, params }); return { results: db.prepare(sql).all(...params) }; },
    first: async (column) => { log.push({ sql, params }); const row = db.prepare(sql).get(...params); return row ? (column ? row[column] : row) : null; },
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

const stored0 = (i, at) => stored(i, 0, 0, at);  // a hidden word in chunk (i, 0)
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
    for (const p of [plan(db, HOUR_SQL, from, to, 10), plan(db, HOUR_AFTER_SQL, from, to, from, 'A', 10)]) {
      assert.match(p, /SEARCH survey_log USING PRIMARY KEY \(at>\? AND at<\?\)/);
      assert.doesNotMatch(p, /SCAN|TEMP B-TREE FOR ORDER BY/);
    }
  });
});

describe('the log\'s counts', () => {
  let db;
  beforeEach(() => { db = fakeD1(); forgetLog(); });
  const counts = (table) => db.raw.prepare(`SELECT * FROM ${table} ORDER BY 1, 2, 3`).all().map((r) => ({ ...r }));
  const hours = () => counts('survey_log_hours');
  // A word anywhere on the map, as a sector stores it (the map isn't checked here).
  const at = (x, y, time, { s = 0, initials = 'ZED', w = 'ACORN' } = {}) => ({ key: keyOf(w, x, y, 0), w, x, y, d: 0, s, initials, at: time });

  test('count each word once per hour, and those in the shared world apart', async () => {
    const edge = (AREA + 1) * SECTOR;  // the first cell past the shared world
    await writeLog(db, [
      at(0, 0, NOW), at(-AREA * SECTOR, edge - 1, NOW + 1), at(edge, 0, NOW + 2), at(0, -AREA * SECTOR - 1, NOW + 3),
      at(5, 5, NOW + 4, { s: 1 }), at(9, 9, NOW - HOUR_MS),
    ]);
    assert.deepEqual(hours(), [{ hour: HOUR - 1, n: 1, world: 1 }, { hour: HOUR, n: 5, world: 2 }]);
    // A batch sent again counts nothing twice.
    await writeLog(db, [at(0, 0, NOW), at(9, 9, NOW - HOUR_MS)]);
    assert.deepEqual(hours(), [{ hour: HOUR - 1, n: 1, world: 1 }, { hour: HOUR, n: 5, world: 2 }]);
  });

  test('count surveyors by their initials and territories by their hidden words, per UTC day', async () => {
    await writeLog(db, [
      at(-1, -1, NOW), at(-48, -49, NOW + 1, { initials: 'AMY' }), at(47, 0, NOW + 2, { initials: '' }),
      at(48, 0, NOW + 3, { s: 1 }), at(0, 0, NOW + DAY_MS),
    ]);
    assert.deepEqual(counts('survey_log_surveyors'), [
      { day: DAY, initials: 'AMY', n: 1 }, { day: DAY, initials: 'ZED', n: 2 }, { day: DAY + 1, initials: 'ZED', n: 1 },
    ]);
    // Strays aren't counted to a territory: their theme is their word's, not its.
    assert.deepEqual(counts('survey_log_territories'), [
      { day: DAY, rx: -1, ry: -2, n: 1 }, { day: DAY, rx: -1, ry: -1, n: 1 }, { day: DAY, rx: 0, ry: 0, n: 1 }, { day: DAY + 1, rx: 0, ry: 0, n: 1 },
    ]);
  });

  test('take a deleted word back out', async () => {
    await writeLog(db, [at(0, 0, NOW), at(1, 1, NOW + 1, { w: 'BARK' })]);
    db.raw.exec(`DELETE FROM survey_log WHERE w = 'BARK'`);
    assert.deepEqual(hours(), [{ hour: HOUR, n: 1, world: 1 }]);
    assert.deepEqual(counts('survey_log_surveyors'), [{ day: DAY, initials: 'ZED', n: 1 }]);
    assert.deepEqual(counts('survey_log_territories'), [{ day: DAY, rx: 0, ry: 0, n: 1 }]);
  });

  test('count words logged before the counts existed', async () => {
    db = fakeD1(1);
    await writeLog(db, [at(0, 0, NOW), at(3000, 0, NOW + 1, { initials: 'AMY' }), at(5, 5, NOW + 2, { s: 1 })]);
    db.raw.exec(migrations()[1]);
    await writeLog(db, [at(7, 7, NOW + 3)]);
    assert.deepEqual(hours(), [{ hour: HOUR, n: 4, world: 2 }]);
    assert.deepEqual(counts('survey_log_surveyors'), [{ day: DAY, initials: 'AMY', n: 1 }, { day: DAY, initials: 'ZED', n: 3 }]);
    assert.deepEqual(counts('survey_log_territories'), [{ day: DAY, rx: 0, ry: 0, n: 2 }, { day: DAY, rx: 62, ry: 0, n: 1 }]);
  });

  test('give a UTC month hour by hour, leaving out hours with none', async () => {
    const month = (2026 - 1970) * 12 + 10;  // November 2026
    const [from, to] = monthHours(month);
    assert.equal(from * HOUR_MS, Date.UTC(2026, 10, 1));
    assert.equal(to * HOUR_MS, Date.UTC(2026, 11, 1));
    await writeLog(db, [at(0, 0, Date.UTC(2026, 9, 31, 23, 59)), at(1, 0, NOW), at(2, 0, NOW + 1), at(9000, 0, NOW + HOUR_MS), at(3, 0, Date.UTC(2026, 11, 1))]);
    assert.deepEqual(await readMonth(db, month), { month, hours: [[HOUR, 2, 2], [HOUR + 1, 1, 0]] });
    assert.deepEqual((await readDay(db, DAY)).hours.slice(14, 16), [2, 1]);
  });

  test('rank surveyors, territories and themes over a run of days', async () => {
    const rows = [];
    let t = NOW;
    const add = (x, y, initials, n) => { for (let i = 0; i < n; i++) rows.push(at(x + i, y, t++, { initials })); };
    add(0, 0, 'ZED', 5);      // territory 0,0
    add(48, 0, 'AMY', 3);     // territory 1,0
    add(-48, 0, 'ZED', 2);    // territory -1,0
    add(0, 48, '', 4);        // territory 0,1, no initials
    for (let i = 0; i < TOP_N + 2; i++) rows.push(at(i, 400, t++, { initials: `Q${String.fromCharCode(65 + i)}A` }));
    rows.push(at(0, 0, NOW - 3 * DAY_MS, { initials: 'OLD' }));
    await writeLog(db, rows);
    const top = await readTop(db, DAY, DAY + 1);
    assert.deepEqual(top.surveyors.slice(0, 2), [['ZED', 7], ['AMY', 3]]);
    assert.equal(top.surveyors.length, TOP_N);
    assert.ok(!top.surveyors.some(([i]) => i === '' || i === 'OLD'));
    assert.deepEqual(top.territories[0], [0, 8, regionName(0, 8), regionTheme(0, 8), TOP_N + 2]);
    assert.deepEqual(top.territories[1], [0, 0, regionName(0, 0), regionTheme(0, 0), 5]);
    assert.equal(top.hidden, 14 + TOP_N + 2);
    assert.equal(top.themes.reduce((a, r) => a + r[3], 0), top.hidden);
    const [th, name, hue] = top.themes.find((r) => r[0] === regionTheme(1, 0));
    assert.deepEqual([name, hue], [THEMES[th].name, THEMES[th].hue]);
    assert.equal((await readTop(db, DAY - 3, DAY + 1)).surveyors.find(([i]) => i === 'OLD')[1], 1);
  });

  test('say where the log starts and ends, words logged late included', async () => {
    assert.deepEqual(await readSpan(db), { first: null, last: null });
    await writeLog(db, [at(0, 0, NOW), at(1, 1, NOW - 40 * DAY_MS), at(2, 2, NOW + HOUR_MS)]);
    assert.deepEqual(await readSpan(db), { first: HOUR - 40 * 24, last: HOUR + 1 });
    // A word taken back out doesn't hold the start where it was.
    db.raw.exec(`DELETE FROM survey_log WHERE x = 1`);
    assert.deepEqual(await readSpan(db), { first: HOUR, last: HOUR + 1 });
    for (const sql of [FIRST_SQL, LAST_SQL]) assert.doesNotMatch(plan(db, sql), /TEMP B-TREE/);
  });

  test('start over with the new map: the log and its counts emptied, and counting again after', async () => {
    db = fakeD1(3);
    await writeLog(db, [at(0, 0, NOW), at(48, 0, NOW + 1, { initials: 'AMY' }), at(5, 5, NOW + 2, { s: 1 })]);
    db.raw.exec(migrations()[3]);
    for (const table of ['survey_log', 'survey_log_hours', 'survey_log_surveyors', 'survey_log_territories']) {
      assert.equal(db.raw.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n, 0, table);
    }
    await writeLog(db, [at(0, 0, NOW + 3), at(1, 1, NOW + 4, { w: 'BARK' })]);
    db.raw.exec(`DELETE FROM survey_log WHERE w = 'BARK'`);
    assert.deepEqual(hours(), [{ hour: HOUR, n: 1, world: 1 }]);
    assert.deepEqual(counts('survey_log_territories'), [{ day: DAY, rx: 0, ry: 0, n: 1 }]);
  });

  test('read only the counts asked for', () => {
    for (const p of [plan(db, HOURS_SQL, 1, 2)]) assert.match(p, /SEARCH survey_log_hours USING PRIMARY KEY \(hour>\? AND hour<\?\)/);
    assert.match(plan(db, SURVEYORS_SQL, 1, 2), /SEARCH survey_log_surveyors USING PRIMARY KEY \(day>\? AND day<\?\)/);
    assert.match(plan(db, TERRITORIES_SQL, 1, 2), /SEARCH survey_log_territories USING PRIMARY KEY \(day>\? AND day<\?\)/);
  });
});

describe('one surveyor, theme or territory', () => {
  let db;
  beforeEach(() => { db = fakeD1(); forgetLog(); });
  const at = (x, y, time, { s = 0, initials = 'ZED', w = 'ACORN' } = {}) => ({ key: keyOf(w, x, y, 0), w, x, y, d: 0, s, initials, at: time });

  test('work out each word\'s territory and theme in SQL as the game does', async () => {
    let seed = 7;
    const next = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed; };
    const rows = [];
    for (let i = 0; i < 400; i++) rows.push(at((next() % 20000) - 10000, (next() % 20000) - 10000, NOW + i));
    rows.push(at(-1, -1, NOW + 500), at(-48, -49, NOW + 501), at(47, 48, NOW + 502), at(0, 0, NOW + 503));
    await writeLog(db, rows);
    for (const r of db.raw.prepare('SELECT x, y, rx, ry, th FROM survey_log').all()) {
      const rx = fdiv(r.x, RC), ry = fdiv(r.y, RC);
      assert.deepEqual([r.rx, r.ry, r.th], [rx, ry, regionTheme(rx, ry)], `${r.x},${r.y}`);
    }
  });

  test('give one surveyor\'s words over a range of hours, newest first, a page at a time', async () => {
    const rows = [];
    for (let i = 0; i < SLICE_PAGE + 5; i++) rows.push(at(i, 0, NOW - i * 60000));       // 0,0 and 1,0 and 2,0
    rows.push(at(5, 5, NOW + 1, { s: 1, w: 'BARK' }), at(3000, 0, NOW + 2));            // a stray, a word outside the world
    rows.push(at(0, 9, NOW + 3, { initials: 'AMY' }), at(0, 10, NOW - 3 * DAY_MS));      // someone else, and a word too early
    await writeLog(db, rows);
    const from = HOUR - 24, to = HOUR + 1;
    const one = await readSlice(db, 'surveyor', 'ZED', from, to);
    assert.equal(one.words, SLICE_PAGE + 7);
    assert.equal(one.world, SLICE_PAGE + 5);
    assert.equal(one.hours.reduce((a, h) => a + h[1], 0), one.words);
    assert.ok(one.hours.every((h, i) => i === 0 || h[0] > one.hours[i - 1][0]));
    assert.deepEqual(one.topTerritories[0], [0, 0, regionName(0, 0), regionTheme(0, 0), 48]);
    assert.equal(one.topThemes.reduce((a, r) => a + r[3], 0), SLICE_PAGE + 6);  // hidden words only
    assert.equal(one.topSurveyors, undefined);
    assert.equal(one.entries.length, SLICE_PAGE);
    assert.deepEqual(one.entries.slice(0, 3).map((e) => e[0]), ['ACORN', 'BARK', 'ACORN']);
    assert.ok(one.entries.every((e) => e[5] === 'ZED'));
    assert.ok(one.entries.every((e, i) => i === 0 || e[6] < one.entries[i - 1][6]));
    assert.ok(one.next);
    const [atMs, ...key] = one.next.split('~');
    const two = await readSlice(db, 'surveyor', 'ZED', from, to, { at: Number(atMs), key: key.join('~') });
    assert.equal(two.entries.length, 7);
    assert.equal(two.next, null);
    assert.equal(new Set([...one.entries, ...two.entries].map((e) => e[6])).size, SLICE_PAGE + 7);
    assert.equal((await readSlice(db, 'surveyor', 'NOB', from, to)).words, 0);
  });

  test('give one theme\'s hidden words, with who charted them', async () => {
    const th = regionTheme(0, 0), far = [116 * 2, 0];  // another territory with the same theme
    assert.equal(regionTheme(far[0], far[1]), th);
    await writeLog(db, [
      at(1, 1, NOW), at(2, 2, NOW + 1, { initials: 'AMY' }), at(far[0] * RC, 0, NOW + 2, { initials: 'AMY' }),
      at(3, 3, NOW + 3, { s: 1, w: 'BARK' }), at(48, 0, NOW + 4), at(4, 4, NOW + 5, { initials: '' }),
    ]);
    const one = await readSlice(db, 'theme', th, HOUR, HOUR + 1);
    assert.equal(one.words, 4);
    assert.deepEqual(one.topSurveyors, [['AMY', 2], ['ZED', 1]]);
    assert.deepEqual(one.topTerritories.map((r) => [r[0], r[1], r[4]]), [[0, 0, 3], [far[0], 0, 1]]);
    assert.equal(one.topThemes, undefined);
    assert.deepEqual([one.name, one.hue], [THEMES[th].name, THEMES[th].hue]);
    assert.ok(one.entries.every((e) => e[7] === th && e[4] === 0));
  });

  test('give everything charted in a territory, with how many words it hides', async () => {
    const [w0, w1] = chunk(0, 0).words;
    await writeLog(db, [
      stored(0, 0, 0, NOW), stored(0, 0, 1, NOW + 1, 'AMY'), stored(3, 3, 0, NOW + 2, 'AMY'),
      at(5, 5, NOW + 3, { s: 1, w: 'BARK' }), stored(4, 0, 0, NOW + 4),
    ]);
    const t = await readTerritory(db, 0, 0);
    let total = 0;
    for (let cy = 0; cy < 4; cy++) for (let cx = 0; cx < 4; cx++) total += chunk(cx, cy).words.length;
    assert.deepEqual([t.rx, t.ry, t.name, t.th, t.total, t.charted], [0, 0, regionName(0, 0), regionTheme(0, 0), total, 3]);
    assert.deepEqual(t.topSurveyors, [['AMY', 2], ['ZED', 2]]);
    assert.deepEqual(t.entries.map((e) => e[0]), ['BARK', chunk(3, 3).words[0].w, w1.w, w0.w]);
    assert.ok(t.themes[regionTheme(0, 0)]);
    assert.equal((await readTerritory(db, -7, 3)).charted, 0);
  });

  test('read only the rows of the surveyor, theme or territory asked for', () => {
    for (const [kind, { index }] of Object.entries(SLICES)) {
      const sql = sliceSql(kind), args = kind === 'territory' ? [0, 0, 1, 2] : [1, 1, 2];
      for (const [part, q] of Object.entries({ ...sql, after: sliceSql(kind, true).entries })) {
        const p = plan(db, q, ...args, ...(part === 'after' ? [1, 'A'] : []), ...(/LIMIT \?$/.test(q) ? [10] : []));
        assert.match(p, new RegExp(`SEARCH survey_log USING (COVERING )?INDEX ${index} \\(`), `${kind} ${part}: ${p}`);
        if (part === 'entries' || part === 'after') assert.doesNotMatch(p, /TEMP B-TREE/, `${kind} ${part}: ${p}`);
      }
    }
  });
});

describe('routeLog', () => {
  let env;
  beforeEach(async () => {
    forgetLog();
    env = { LOG_DB: fakeD1(), ALLOWED_ORIGINS: ORIGIN };
    await writeLog(env.LOG_DB, [stored(0, 0, 0, NOW - 1000), stored(1, 0, 0, NOW - 2 * DAY_MS)]);
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
    const reads = () => env.LOG_DB.log.filter((q) => q.sql.startsWith('SELECT')).length;
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
    env.LOG_DB.log.length = 0;
    const again = await get(`/v1/survey/log/day/${DAY - 2}`, { origin: 'http://localhost:8000' });
    assert.equal(env.LOG_DB.log.length, 0);
    assert.equal((await again.json()).total, 1);
    assert.equal(again.headers.get('Access-Control-Allow-Origin'), null);  // not in ALLOWED_ORIGINS here
  });

  test('keeps each Worker\'s answers apart in Cloudflare\'s cache, so a preview never answers for production', async () => {
    // Every workers.dev Worker on the account shares one zone's cache, Worker Previews included.
    const stored = new Map();
    globalThis.caches = { default: { match: async (r) => stored.get(r.url)?.clone(), put: async (r, res) => { stored.set(r.url, res); } } };
    const preview = { LOG_DB: fakeD1(), ALLOWED_ORIGINS: ORIGIN };
    for (let i = 0; i < 5; i++) await writeLog(preview.LOG_DB, [stored0(i, NOW - 3 * DAY_MS + i)]);
    const ask = (host, which) => routeLog(new Request(`https://${host}/v1/survey/log/day/${DAY - 3}`, { headers: { Origin: ORIGIN } }), which, NOW);
    assert.equal((await (await ask('pr-43-games-leaderboard.example.workers.dev', preview)).json()).total, 5);
    forgetLog();  // another Worker instance
    assert.equal((await (await ask('games-leaderboard.example.workers.dev', env)).json()).total, 0);
    assert.deepEqual([...stored.keys()].sort(), [
      `https://games-leaderboard.example.workers.dev/_cache/survey-log/day/${DAY - 3}`,
      `https://pr-43-games-leaderboard.example.workers.dev/_cache/survey-log/day/${DAY - 3}`,
    ]);
  });

  test('answers a month and a top list, cached by how settled and how long they are', async () => {
    const month = (2026 - 1970) * 12 + 10;
    const m = await get(`/v1/survey/log/month/${month}`);
    assert.equal(m.headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    assert.equal((await m.json()).hours.reduce((a, h) => a + h[1], 0), 2);
    assert.equal((await get(`/v1/survey/log/month/${month - 1}`)).headers.get('Cache-Control'), 'public, max-age=86400');
    const day = await get(`/v1/survey/log/top/${DAY}/${DAY + 1}`);
    assert.equal(day.headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    assert.deepEqual((await day.json()).surveyors, [['ZED', 1]]);
    assert.equal((await get(`/v1/survey/log/top/${DAY - 6}/${DAY + 1}`)).headers.get('Cache-Control'), `public, max-age=${TOP_SLOW_CACHE_S}`);
    assert.equal((await get(`/v1/survey/log/top/${DAY - 6}/${DAY - 2}`)).headers.get('Cache-Control'), 'public, max-age=86400');
    assert.equal((await get(`/v1/survey/log/month/${month + 1}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/top/${DAY + 1}/${DAY + 2}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/top/${DAY}/${DAY}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/top/${DAY - TOP_MAX_DAYS - 1}/${DAY}`)).status, 400);
  });

  test('answers a surveyor, a theme and a territory, cached by how settled and how long they are', async () => {
    const one = await get(`/v1/survey/log/surveyor/ZED/${HOUR - 24}/${HOUR + 1}`);
    assert.equal(one.headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    assert.equal((await one.json()).words, 1);
    const week = await get(`/v1/survey/log/surveyor/ZED/${HOUR - 24 * 7}/${HOUR + 1}`);
    assert.equal(week.headers.get('Cache-Control'), `public, max-age=${SLICE_SLOW_CACHE_S}`);
    assert.equal((await week.json()).words, 2);
    assert.equal((await get(`/v1/survey/log/surveyor/ZED/${HOUR - 72}/${HOUR - 2}`)).headers.get('Cache-Control'), 'public, max-age=86400');
    const th = regionTheme(0, 0);
    const theme = await (await get(`/v1/survey/log/theme/${th}/${HOUR - 1}/${HOUR + 1}`)).json();
    assert.deepEqual([theme.kind, theme.key, theme.words], ['theme', th, 1]);
    const page = await get(`/v1/survey/log/surveyor/ZED/${HOUR - 1}/${HOUR + 1}?before=${NOW}~ACORN~1~-2~3`);
    assert.equal(page.status, 200);
    const place = await get('/v1/survey/log/territory/0/0');
    assert.equal(place.headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    assert.equal((await place.json()).charted, 2);  // chunks 0,0 and 1,0 are both in it
    assert.equal((await (await get('/v1/survey/log/territory/-3/-12')).json()).name, regionName(-3, -12));
    assert.equal((await get(`/v1/survey/log/theme/${THEMES.length}/${HOUR}/${HOUR + 1}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/surveyor/ZED/${HOUR + 1}/${HOUR + 2}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/surveyor/ZED/${HOUR}/${HOUR}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/surveyor/ZED/${HOUR - SLICE_MAX_HOURS - 1}/${HOUR}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/surveyor/ZED/${HOUR}/${HOUR + 1}?before=nope`)).status, 400);
    assert.equal(get(`/v1/survey/log/surveyor/zed/${HOUR}/${HOUR + 1}`), null);
  });

  test('answers the span, cached for minutes', async () => {
    const res = await get('/v1/survey/log/span');
    assert.equal(res.headers.get('Cache-Control'), `public, max-age=${SPAN_CACHE_S}`);
    assert.deepEqual(await res.json(), { first: Math.floor((NOW - 2 * DAY_MS) / HOUR_MS), last: Math.floor((NOW - 1000) / HOUR_MS) });
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
    env = { LOG_DB: fakeD1() };
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
    assert.deepEqual(env.LOG_DB.rows().map((r) => r.w), [word(0).w, word(1).w]);
    assert.equal(state.alarm, null);
    await claim(ws, 2);
    await fire();
    assert.equal(env.LOG_DB.rows().length, 3);
    assert.equal(env.LOG_DB.batches, 2);  // each claim went once
  });

  test('keeps claims D1 did not take, and tries again later and later', async () => {
    const ws = join();
    await claim(ws, 0);
    env.LOG_DB.fail = 'D1 is down';
    await fire();
    assert.equal(state.alarm, clock + LOG_MS * 2);
    await fire();
    assert.equal(state.alarm, clock + LOG_MS * 4);
    for (let i = 0; i < 10; i++) await fire();
    assert.equal(state.alarm, clock + LOG_RETRY_MAX_MS);
    assert.ok(logged.mock.calls.some((c) => c.arguments[0]?.survey === 'log failed'));
    env.LOG_DB.fail = null;
    await claim(ws, 1);
    await fire();
    assert.deepEqual(env.LOG_DB.rows().map((r) => r.w), [word(0).w, word(1).w]);
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
    assert.equal(env.LOG_DB.rows().length, LOG_BATCH);
    assert.equal(state.alarm, clock + 1000);  // more to come
    await fire();
    assert.equal(env.LOG_DB.rows().length, LOG_BATCH + 5);
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
    assert.deepEqual(env.LOG_DB.rows().map((r) => r.at), [first, first + 1]);
  });

  test('needs no alarm without a log', async () => {
    env = {};
    sector = make();
    const ws = join();
    await claim(ws, 0);
    assert.equal(state.alarm, null);
  });
});
