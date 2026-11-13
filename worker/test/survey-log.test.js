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
import { MAP_VERSION, RC, THEMES, VOCAB, chunk, fdiv, keyOf, regionName, regionTheme, territoryTotal } from '../src/letterfield-world.js';
import {
  DAY_MS, HOURS_SQL, HOUR_AFTER_SQL, HOUR_MS, HOUR_SQL, LIVE_CACHE_S, LOG_BATCH, LOG_MS, LOG_PAGE, LOG_RETRY_MAX_MS, SETTLED_MS,
  FIRST_SQL, LAST_SQL, SLICES, SLICE_MAX_HOURS, SLICE_PAGE, SLICE_SLOW_CACHE_S, SPAN_CACHE_S, SURVEYORS_SQL, TERRITORIES_SQL,
  TOP_MAX_DAYS, TOP_N, TOP_SLOW_CACHE_S, forgetLog, monthHours, readDay, readHour, readMonth, readSlice, readSpan, readTerritory,
  readTop, readTopHours, routeLog, sliceSql, writeLog, HOURS_SURVEYORS_SQL, HOURS_TERRITORIES_SQL, TOP_HOURS_MAX,
  NOVAS_SQL, NOVAS_BEFORE_SQL, NOVA_HOURS_SQL, NOVA_PAGE, NOVA_SQL, readNovas,
  GUILDS_SQL, GUILD_NAME_SQL, HOURS_GUILDS_SQL, LOG_ROWS_PER_INSERT,
  TIMELAPSE_GUILD_DAYS_SQL, TIMELAPSE_GUILD_DAY_SQL, TIMELAPSE_GUILD_DAY_AFTER_SQL,
  FOREVER_S, LAYOUT, TIMELAPSE_BOUNDS_SQL, TIMELAPSE_CACHE_S, TIMELAPSE_DAY_AFTER_SQL, TIMELAPSE_DAY_SQL, TIMELAPSE_HOURS_SQL,
  TIMELAPSE_NOVAS_SQL, TIMELAPSE_NOVA_HOURS_SQL, TIMELAPSE_PAGE, TIMELAPSE_VERSION, readTimelapse, readTimelapseDay, readTimelapseGuildDay,
} from '../src/survey-log.js';
import { AREA, NEAR_PATH, NOVA_REACH, SECTOR, Sector, checkNova, novaNeighbours } from '../src/survey.js';

const MIGRATIONS = new URL('../migrations-log/', import.meta.url);
const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 10, 6, 14, 30);
const HOUR = Math.floor(NOW / HOUR_MS);
const DAY = Math.floor(NOW / DAY_MS);

// The column today's writes need, for tests of an older log (it came in 0007).
const GUILD_COLUMN = "ALTER TABLE survey_log ADD COLUMN guild TEXT NOT NULL DEFAULT ''";
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
    db.raw.exec(GUILD_COLUMN);
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

  test('rank them over a run of hours too, for a day or an hour in the page’s time zone', async () => {
    const rows = [];
    let t = HOUR * HOUR_MS;
    const add = (x, y, initials, n, when = t) => { for (let i = 0; i < n; i++) rows.push(at(x + i, y, when + rows.length, { initials })); };
    add(0, 0, 'ZED', 3);                       // this hour, territory 0,0
    add(48, 0, 'AMY', 2);                      // this hour, territory 1,0
    add(0, 48, '', 4);                         // this hour, no initials
    rows.push(at(200, 0, t + 1000, { initials: 'ZED', s: 1 }));  // a stray: counts for ZED, not for a territory
    add(-48, 0, 'BOB', 5, t - HOUR_MS);        // the hour before
    await writeLog(db, rows);
    const hour = await readTopHours(db, HOUR, HOUR + 1);
    assert.equal(hour.hours, true);
    assert.deepEqual(hour.surveyors, [['ZED', 4], ['AMY', 2]]);
    assert.deepEqual(hour.territories.map((r) => [r[0], r[1], r[4]]), [[0, 1, 4], [0, 0, 3], [1, 0, 2]]);
    assert.equal(hour.hidden, 9);
    assert.equal(hour.themes.reduce((a, r) => a + r[3], 0), hour.hidden);
    assert.deepEqual((await readTopHours(db, HOUR - 1, HOUR + 1)).surveyors, [['BOB', 5], ['ZED', 4], ['AMY', 2]]);
    // Each reads only its run of the log, in time order.
    for (const sql of [HOURS_SURVEYORS_SQL, HOURS_TERRITORIES_SQL]) assert.match(plan(db, sql, 1, 2), /SEARCH survey_log USING PRIMARY KEY \(at>\? AND at<\?\)/);
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
    db.raw.exec(GUILD_COLUMN);
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
    const th = regionTheme(0, 0), far = [THEMES.length, 0];  // another territory with the same theme
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

describe('guilds in the log', () => {
  let db;
  beforeEach(() => { db = fakeD1(); forgetLog(); });
  const COBALT = 'c0ba17c0ba', AMBER = 'a3be7a3be7';
  const named = [{ lid: COBALT, a: 11, b: 0, c: 0 }, { lid: AMBER, a: 3, b: 2, c: 3 }];
  const at = (x, y, time, { s = 0, initials = 'ZED', w = 'ACORN', guild = COBALT } = {}) => ({ key: keyOf(w, x, y, 0), w, x, y, d: 0, s, initials, at: time, guild });

  test('keep each word\'s guild, and each guild\'s name once', async () => {
    await writeLog(db, [at(0, 0, NOW), at(1, 0, NOW + 1, { guild: '' }), at(2, 0, NOW + 2, { guild: 'not an id' })], [], named);
    await writeLog(db, [at(3, 0, NOW + 3)], [], [{ lid: COBALT, a: 0, b: 0, c: 0 }, { lid: 'bad', a: 0, b: 0, c: 0 }, { lid: 'abcdefabcd', a: 99, b: 0, c: 0 }]);
    assert.deepEqual(db.raw.prepare('SELECT guild FROM survey_log ORDER BY at').all().map((r) => r.guild), [COBALT, '', '', COBALT]);
    // A name never changes, so the first one sent stays; nothing off the lists goes in.
    assert.deepEqual(db.raw.prepare('SELECT guild, a, b, c FROM survey_log_guilds ORDER BY guild').all().map((r) => ({ ...r })),
      [{ guild: AMBER, a: 3, b: 2, c: 3 }, { guild: COBALT, a: 11, b: 0, c: 0 }]);
    assert.deepEqual(db.raw.prepare('SELECT day, guild, n FROM survey_log_guild_days').all().map((r) => ({ ...r })), [{ day: DAY, guild: COBALT, n: 2 }]);
    db.raw.exec(`DELETE FROM survey_log WHERE at = ${NOW}`);
    assert.equal(db.raw.prepare('SELECT n FROM survey_log_guild_days').get().n, 1);
    // A row binds 9 values now, and D1 takes 100 a statement.
    assert.ok(LOG_ROWS_PER_INSERT * 9 <= 100);
  });

  test('give one guild\'s words, with its name, colour, members and themes', async () => {
    await writeLog(db, [
      at(1, 1, NOW), at(2, 2, NOW + 1, { initials: 'AMY' }), at(48, 0, NOW + 2, { initials: 'AMY' }),
      at(5, 5, NOW + 3, { s: 1, w: 'BARK' }), at(6, 6, NOW + 4, { guild: AMBER }), at(7, 7, NOW + 5, { guild: '' }),
      at(8, 8, NOW - 2 * DAY_MS),
    ], [], named);
    const one = await readSlice(db, 'guild', COBALT, HOUR, HOUR + 1);
    assert.deepEqual([one.kind, one.key, one.name, one.hue], ['guild', COBALT, 'Cobalt Compass Society', 220]);
    assert.equal(one.words, 4);
    assert.deepEqual(one.topSurveyors, [['AMY', 2], ['ZED', 2]]);
    assert.deepEqual(one.topTerritories.map((r) => [r[0], r[1], r[4]]), [[0, 0, 2], [1, 0, 1]]);
    assert.equal(one.topThemes.reduce((a, r) => a + r[3], 0), 3);
    assert.deepEqual(one.entries.map((e) => e[0]), ['BARK', 'ACORN', 'ACORN', 'ACORN']);
    // A guild the log has no name for yet (or never had) says so.
    const none = await readSlice(db, 'guild', 'ffffffffff', HOUR, HOUR + 1);
    assert.deepEqual([none.name, none.hue, none.words], [null, null, 0]);
    assert.match(plan(db, GUILD_NAME_SQL, COBALT), /SEARCH survey_log_guilds USING PRIMARY KEY/);
  });

  test('rank guilds over days and over hours, leaving out any the log has no name for', async () => {
    await writeLog(db, [
      at(1, 1, NOW), at(2, 2, NOW + 1), at(3, 3, NOW + 2, { guild: AMBER }), at(4, 4, NOW + 3, { guild: '' }),
      at(5, 5, NOW + 4, { guild: 'eeeeeeeeee' }), at(6, 6, NOW - 2 * DAY_MS, { guild: AMBER }),
    ], [], named);
    const days = await readTop(db, DAY - 7, DAY + 1);
    // A tie goes to the lower id, as surveyors' ties go to the earlier initials.
    assert.deepEqual(days.guilds, [[AMBER, 'Amber Lantern Circle', 38, 2], [COBALT, 'Cobalt Compass Society', 220, 2]]);
    assert.deepEqual((await readTop(db, DAY, DAY + 1)).guilds, [[COBALT, 'Cobalt Compass Society', 220, 2], [AMBER, 'Amber Lantern Circle', 38, 1]]);
    assert.deepEqual((await readTopHours(db, HOUR, HOUR + 1)).guilds, [[COBALT, 'Cobalt Compass Society', 220, 2], [AMBER, 'Amber Lantern Circle', 38, 1]]);
    assert.match(plan(db, GUILDS_SQL, 1, 2), /SEARCH survey_log_guild_days USING PRIMARY KEY \(day>\? AND day<\?\)/);
    // Over hours, the log's own rows in time order, as for surveyors: never all of a guild's words.
    const p = plan(db, HOURS_GUILDS_SQL, 1, 2);
    assert.match(p, /SEARCH survey_log USING PRIMARY KEY \(at>\? AND at<\?\)/);
    assert.doesNotMatch(p, /survey_log_by_guild/);
  });

  test('are answered by their log id, cached as a surveyor is', async () => {
    await writeLog(db, [at(1, 1, NOW)], [], named);
    const env = { LOG_DB: db, ALLOWED_ORIGINS: ORIGIN };
    const get = async (path) => {
      const res = await routeLog(new Request(`https://survey.test${path}`, { headers: { Origin: ORIGIN } }), env, NOW);
      return [res.status, await res.json(), res.headers.get('Cache-Control')];
    };
    const [status, body, cache] = await get(`/v1/survey/log/guild/${COBALT}/${HOUR}/${HOUR + 1}`);
    assert.equal(status, 200);
    assert.equal(body.name, 'Cobalt Compass Society');
    assert.equal(cache, `public, max-age=${LIVE_CACHE_S}`);
    assert.equal((await get(`/v1/survey/log/guild/${COBALT}/${HOUR - 24 * 7}/${HOUR + 1}`))[2], `public, max-age=${SLICE_SLOW_CACHE_S}`);
    assert.equal((await get(`/v1/survey/log/guild/${COBALT}/${HOUR - 48}/${HOUR - 24}`))[2], 'public, max-age=86400');
    assert.equal((await get(`/v1/survey/log/guild/${COBALT}/${HOUR + 5}/${HOUR + 6}`))[0], 400);
    // A guild is only ever asked for by its log id: never a tag (8 digits) or a code.
    assert.equal(await routeLog(new Request(`https://survey.test/v1/survey/log/guild/c0ba17c0/${HOUR}/${HOUR + 1}`), env, NOW), null);
    assert.equal(await routeLog(new Request(`https://survey.test/v1/survey/log/guild/ABCDEF/${HOUR}/${HOUR + 1}`), env, NOW), null);
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

  test('keeps each Worker\'s and each map\'s answers apart in Cloudflare\'s cache, so a preview never answers for production', async () => {
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
      `https://games-leaderboard.example.workers.dev/_cache/survey-log/m${MAP_VERSION}/day/${DAY - 3}`,
      `https://pr-43-games-leaderboard.example.workers.dev/_cache/survey-log/m${MAP_VERSION}/day/${DAY - 3}`,
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
    // A top list over hours, for a day in the page's own time zone.
    const hours = await get(`/v1/survey/log/top/hours/${HOUR - 14}/${HOUR + 10}`);
    assert.equal(hours.headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    assert.deepEqual((await hours.json()).surveyors, [['ZED', 1]]);
    assert.equal((await get(`/v1/survey/log/top/hours/${HOUR - 30}/${HOUR - 6}`)).headers.get('Cache-Control'), 'public, max-age=86400');
    assert.equal((await get(`/v1/survey/log/top/hours/${HOUR + 1}/${HOUR + 2}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/top/hours/${HOUR}/${HOUR}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/top/hours/${HOUR - TOP_HOURS_MAX - 1}/${HOUR}`)).status, 400);
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

  test('keeps to LOG_MS when the next claim reaches a sector woken from hibernation', async () => {
    const ws = join();
    await claim(ws, 0);
    const due = state.alarm;
    clock += 18000;   // 20 seconds after the first claim, with claim()'s own 2
    sector = make();  // it hibernated in between, so this is a new object
    await claim(ws, 1);
    assert.equal(state.alarm, due, 'the first claim is logged when it was due to be, not put off');
    await fire();
    assert.deepEqual(env.LOG_DB.rows().map((r) => r.w), [word(0).w, word(1).w]);
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

// Every hidden word of territory (rx, ry), in chunk order.
const territoryWords = (rx, ry) => {
  const out = [];
  for (let cy = ry * 4; cy < ry * 4 + 4; cy++) for (let cx = rx * 4; cx < rx * 4 + 4; cx++) out.push(...chunk(cx, cy).words);
  return out;
};
// A supernova as a sector sends it to the log.
const nova = (rx, ry, at, { first = at - DAY_MS, initials = 'ZED', top = 'ZED', w = 'ACORN' } = {}) => ({
  rx, ry, at, w, x: rx * RC, y: ry * RC, d: 0, initials, first, words: territoryTotal(rx, ry), surveyors: 2, top, top_n: 60,
});

describe('supernovas in the log', () => {
  let db;
  beforeEach(() => { db = fakeD1(); forgetLog(); });

  test('go in with the claims, once each', async () => {
    await writeLog(db, [stored(0, 0, 0, NOW)], [nova(0, 0, NOW)]);
    await writeLog(db, [], [nova(0, 0, NOW + 5, { initials: 'AMY' }), ...Array.from({ length: 9 }, (_, i) => nova(i + 1, 0, NOW + i))]);
    const rows = db.raw.prepare('SELECT * FROM survey_log_novas ORDER BY rx').all();
    assert.equal(rows.length, 10);
    assert.equal(rows[0].initials, 'ZED');  // the first copy stands
    assert.ok(db.log.every((q) => q.params.length <= 100));
  });

  test('list newest first, a page at a time, with where, its theme and each hour\'s count', async () => {
    const list = Array.from({ length: NOVA_PAGE + 3 }, (_, i) => nova(i % 50, Math.floor(i / 50), NOW - i * 60000));
    await writeLog(db, [], [...list, nova(-5, -5, NOW - 30 * DAY_MS)]);
    const from = HOUR - 24, to = HOUR + 1;
    const first = await readNovas(db, from, to);
    assert.equal(first.count, NOVA_PAGE + 3);
    assert.equal(first.novas.length, NOVA_PAGE);
    assert.deepEqual(first.novas.map((n) => n[2]), list.slice(0, NOVA_PAGE).map((n) => n.at));
    const [rx, ry, at, w, x, y, d, initials, firstAt, words, surveyors, top, topN, th] = first.novas[0];
    assert.deepEqual([rx, ry, at, w, x, y, d, initials, firstAt, words, surveyors, top, topN], Object.values(list[0]));
    assert.equal(th, regionTheme(0, 0));
    assert.equal(first.places['0,0'], regionName(0, 0));
    assert.deepEqual(first.themes[th], [THEMES[th].name, THEMES[th].hue]);
    assert.deepEqual(first.hours.map((h) => h[0]), [...new Set(list.map((n) => Math.floor(n.at / HOUR_MS)))].sort((a, b) => a - b));
    assert.equal(first.hours.reduce((a, h) => a + h[1], 0), NOVA_PAGE + 3);
    const [a, b, c] = first.next.split('~').map(Number);
    const second = await readNovas(db, from, to, { at: a, rx: b, ry: c });
    assert.deepEqual(second.novas.map((n) => n[2]), list.slice(NOVA_PAGE).map((n) => n.at));
    assert.equal(second.next, null);
    assert.equal((await readNovas(db, HOUR - 24 * 40, HOUR)).count, NOVA_PAGE + 4 - list.filter((n) => n.at >= HOUR * HOUR_MS).length);
  });

  test('show on their territory\'s own view', async () => {
    await writeLog(db, [stored(0, 0, 0, NOW)], [nova(0, 0, NOW, { first: NOW - 3 * DAY_MS })]);
    const t = await readTerritory(db, 0, 0);
    assert.deepEqual(t.nova.slice(0, 13), Object.values(nova(0, 0, NOW, { first: NOW - 3 * DAY_MS })));
    assert.equal(t.nova[13], regionTheme(0, 0));
    assert.equal((await readTerritory(db, 1, 0)).nova, null);
  });

  test('read only the supernovas asked for, along their index', () => {
    for (const [sql, args] of [[NOVAS_SQL, [1, 2, 10]], [NOVAS_BEFORE_SQL, [1, 2, 1, 0, 0, 10]], [NOVA_HOURS_SQL, [1, 2]]]) {
      const p = plan(db, sql, ...args);
      assert.match(p, /SEARCH survey_log_novas USING (COVERING )?INDEX survey_log_novas_by_time \(at>\? AND at<\?\)/, p);
      if (sql !== NOVA_HOURS_SQL) assert.doesNotMatch(p, /TEMP B-TREE/, p);
    }
    assert.match(plan(db, NOVA_SQL, 0, 0), /SEARCH survey_log_novas USING PRIMARY KEY \(rx=\? AND ry=\?\)/);
  });

  test('are answered over a range of hours, cached by how settled and how long it is', async () => {
    const env = { LOG_DB: db, ALLOWED_ORIGINS: ORIGIN };
    await writeLog(db, [], [nova(0, 0, NOW - 1000), nova(1, 0, NOW - 3 * DAY_MS)]);
    const get = (path, now = NOW) => routeLog(new Request(`https://survey.test${path}`, { headers: { Origin: ORIGIN } }), env, now);
    const day = await get(`/v1/survey/log/novas/${HOUR - 14}/${HOUR + 10}`);
    assert.equal(day.headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    assert.equal((await day.json()).count, 1);
    const all = await get(`/v1/survey/log/novas/${HOUR - 24 * 30}/${HOUR + 1}`);
    assert.equal(all.headers.get('Cache-Control'), `public, max-age=${SLICE_SLOW_CACHE_S}`);
    assert.equal((await all.json()).novas.length, 2);
    assert.equal((await get(`/v1/survey/log/novas/${HOUR - 96}/${HOUR - 48}`)).headers.get('Cache-Control'), 'public, max-age=86400');
    assert.equal((await get(`/v1/survey/log/novas/${HOUR}/${HOUR + 1}?before=${NOW}~-1~2`)).status, 200);
    assert.equal((await get(`/v1/survey/log/novas/${HOUR}/${HOUR + 1}?before=nope`)).status, 400);
    assert.equal((await get(`/v1/survey/log/novas/${HOUR + 1}/${HOUR + 2}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/novas/${HOUR}/${HOUR}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/novas/${HOUR - SLICE_MAX_HOURS - 1}/${HOUR}`)).status, 400);
    const place = await (await get('/v1/survey/log/territory/0/0')).json();
    assert.equal(place.nova[2], NOW - 1000);
  });
});

describe('Sector recording supernovas', () => {
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

  function make(e = env) {
    const s = new Sector(state, e);
    s.now = () => clock;
    return s;
  }
  async function join(initials = 'ZED', s = sector) {
    const ws = fakeSocket();
    s.join(ws, 0, 0, initials.charCodeAt(0).toString(16).repeat(32));  // an address, which the claim limiter counts
    await s.webSocketMessage(ws, JSON.stringify({ t: 'me', initials }));
    return ws;
  }
  const words = territoryWords(1, 2);  // a territory in sector 0,0
  async function claim(ws, word, s = sector) {
    clock += 2000;  // past the socket's claim limit
    const { w, x, y, d } = word;
    await s.webSocketMessage(ws, JSON.stringify({ t: 'claim', w, x, y, d }));
  }
  const novas = () => state.storage.sql.exec('SELECT * FROM novas').toArray();
  const fire = async () => { clock = Math.max(clock, state.alarm); state.alarm = null; await sector.alarm(); };
  const logNovas = () => env.LOG_DB.raw.prepare('SELECT * FROM survey_log_novas').all().map((r) => ({ ...r }));
  // Claims stored as an older sector left them, without going through claim().
  const store = (list, initials, at) => list.forEach((o, i) => state.storage.sql.exec(
    'INSERT INTO claims (key, w, x, y, d, s, initials, at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)', o.key, o.w, o.x, o.y, o.d, initials, at + i,
  ));

  test('records the claim that charts a territory\'s last hidden word, once, and logs it with that claim', async () => {
    const amy = await join('AMY'), zed = await join('ZED');
    const start = clock;
    for (const [i, o] of words.entries()) {
      await claim(i % 3 ? amy : zed, o);
      if (i === words.length - 2) assert.deepEqual(novas(), []);
    }
    const [n] = novas();
    const last = words.at(-1), lastBy = (words.length - 1) % 3 ? 'AMY' : 'ZED';
    const amyN = words.filter((_, i) => i % 3).length;
    assert.deepEqual(
      [n.rx, n.ry, n.w, n.x, n.y, n.d, n.initials, n.at, n.first, n.words, n.surveyors, n.top, n.top_n],
      [1, 2, last.w, last.x, last.y, last.d, lastBy, clock, start + 2000, words.length, 2, 'AMY', amyN],
    );
    assert.equal(words.length, territoryTotal(1, 2));
    // A stray, or a word elsewhere, after it changes nothing.
    await claim(zed, chunk(0, 0).words[0]);
    assert.equal(novas().length, 1);
    while (state.alarm !== null) await fire();
    const [row] = logNovas();
    assert.deepEqual(row, Object.fromEntries(Object.entries(n).filter(([k]) => k !== 'logged')));
    assert.equal(novas()[0].logged, 1);
    assert.equal(env.LOG_DB.rows().length, words.length + 1);
  });

  test('records it once when the last two words are claimed together', async () => {
    store(words.slice(0, -2), 'OLD', NOW - 1e6);
    // The rate limiter answers late, so both claims are in flight at once.
    const waiting = [];
    env.SURVEY_CLAIMS = { limit: () => new Promise((resolve) => waiting.push(resolve)) };
    sector = make();
    const a = await join('AMY'), b = await join('BEA');
    clock += 2000;
    const one = sector.webSocketMessage(a, JSON.stringify({ t: 'claim', ...pick(words.at(-1)) }));
    const two = sector.webSocketMessage(b, JSON.stringify({ t: 'claim', ...pick(words.at(-2)) }));
    // And a third, of the same last word, from someone else.
    const c = await join('CAL');
    const three = sector.webSocketMessage(c, JSON.stringify({ t: 'claim', ...pick(words.at(-1)) }));
    for (let i = 0; i < 50 && waiting.length < 3; i++) await new Promise((r) => setImmediate(r));
    assert.equal(waiting.length, 3);
    waiting[1]({ success: true }); await two;
    waiting[2]({ success: true }); await three;
    waiting[0]({ success: true }); await one;
    const list = novas();
    assert.equal(list.length, 1);
    assert.deepEqual([list[0].w, list[0].initials], [words.at(-1).w, 'CAL']);
    assert.ok(a.sent.some((m) => m.t === 'taken'));
  });

  test('records it after the sector wakes with the territory nearly done', async () => {
    let ws = await join('AMY');
    for (const o of words.slice(0, -1)) await claim(ws, o);
    sector = make();  // evicted: counts and hidden words are worked out again
    ws = await join('ZED');
    await claim(ws, words.at(-1));
    assert.deepEqual(novas().map((n) => [n.initials, n.top, n.surveyors]), [['ZED', 'AMY', 2]]);
  });

  test('finds territories completed before supernovas were recorded, when the sector next wakes', async () => {
    store(words, 'OLD', NOW - 1e6);
    assert.deepEqual(novas(), []);
    // Before the log has those claims, the supernova waits for them.
    state.storage.sql.exec('INSERT INTO logged (id, at) VALUES (0, ?)', NOW - 1e6 - 1);
    sector = make();
    await join();
    const [n] = novas();
    assert.deepEqual([n.rx, n.ry, n.at, n.first, n.initials, n.top, n.top_n, n.logged], [1, 2, NOW - 1e6 + words.length - 1, NOW - 1e6, 'OLD', 'OLD', words.length, 0]);
    assert.equal(state.alarm, clock + 1000);
    await fire();
    assert.equal(logNovas().length, 1);
    // Waking again finds nothing new to send.
    sector = make();
    await join();
    assert.equal(novas().length, 1);
    assert.equal(state.alarm, null);
  });

  test('never reaches the log ahead of its last word', async () => {
    // A sector from before the log, with more claims than one batch takes,
    // and the territory's last word in the second batch.
    const other = [];
    for (let cy = 0; cy < 16 && other.length < LOG_BATCH; cy++) for (let cx = 0; cx < 4; cx++) {
      if (fdiv(cx, 4) === 1 && fdiv(cy, 4) === 2) continue;
      other.push(...chunk(cx, cy).words.slice(1));  // never a whole territory
    }
    store(other.slice(0, LOG_BATCH), 'OLD', NOW - 2e6);
    store(words, 'NEW', NOW - 1e6);
    sector = make();
    await join();
    assert.equal(novas().length, 1);
    await fire();
    assert.equal(env.LOG_DB.rows().length, LOG_BATCH);
    assert.deepEqual(logNovas(), []);
    await fire();
    assert.equal(env.LOG_DB.rows().length, LOG_BATCH + words.length);
    assert.equal(logNovas().length, 1);
    assert.equal(state.alarm, null);
  });

  test('keeps a supernova D1 did not take, and sends it with a later try', async () => {
    const ws = await join();
    for (const o of words) await claim(ws, o);
    env.LOG_DB.fail = 'D1 is down';
    await fire();
    assert.equal(novas()[0].logged, 0);
    env.LOG_DB.fail = null;
    await fire();
    assert.equal(logNovas().length, 1);
    assert.equal(novas()[0].logged, 1);
  });

  test('tells the share Worker about a supernova before the log has it', async () => {
    store(words, 'OLD', NOW - 1e6);
    sector = make();
    await join();
    const res = await sector.fetch(new Request('https://sector/nova/1/2'));
    assert.equal(res.status, 200);
    const { nova } = await res.json();
    assert.deepEqual(nova.slice(0, 4), [1, 2, NOW - 1e6 + words.length - 1, words.at(-1).w]);
    assert.equal(nova[13], regionTheme(1, 2));
    assert.equal((await sector.fetch(new Request('https://sector/nova/0/0'))).status, 404);
    assert.equal((await sector.fetch(new Request('https://sector/nova/1/2', { method: 'POST' }))).status, 404);
  });

  test('forgets supernovas from an older map', async () => {
    store(words, 'OLD', NOW - 1e6);
    sector = make();
    await join();
    assert.equal(novas().length, 1);
    state.storage.sql.exec('UPDATE map SET version = ?', MAP_VERSION - 1);
    sector = make();
    assert.deepEqual(novas(), []);
  });
});
const pick = ({ w, x, y, d }) => ({ w, x, y, d });

describe('supernovas reaching neighbouring sectors', () => {
  const sorted = (list) => list.map((s) => s.join(',')).sort();
  // Territory (lx, ly) of sector 0,0.
  const near = (lx, ly) => sorted(novaNeighbours(lx, ly));

  test('go to the sectors with a territory within NOVA_REACH, as the game\'s nearView counts', () => {
    assert.equal(NOVA_REACH, 3);
    // Corners: one beside, one above or below, one diagonal.
    assert.deepEqual(near(0, 0), sorted([[-1, -1], [-1, 0], [0, -1]]));
    assert.deepEqual(near(3, 0), sorted([[0, -1], [1, -1], [1, 0]]));
    assert.deepEqual(near(0, 3), sorted([[-1, 0], [-1, 1], [0, 1]]));
    assert.deepEqual(near(3, 3), sorted([[0, 1], [1, 0], [1, 1]]));
    // An edge: three territories reach across one side and both its corners.
    assert.deepEqual(near(1, 0), sorted([[-1, -1], [-1, 0], [0, -1], [1, -1], [1, 0]]));
    assert.deepEqual(near(3, 2), sorted([[0, -1], [0, 1], [1, -1], [1, 0], [1, 1]]));
    // The middle four reach every side.
    for (const [lx, ly] of [[1, 1], [2, 1], [1, 2], [2, 2]]) assert.equal(novaNeighbours(lx, ly).length, 8);
    // Away from the origin and below zero, the same.
    assert.deepEqual(sorted(novaNeighbours(-5, 7)), sorted([[-2, 2], [-1, 1], [-1, 2]]));  // the bottom right corner of sector -2,1
    assert.equal(novaNeighbours(-6, 6).length, 8);
    assert.deepEqual(sorted(novaNeighbours(-4, -4)), sorted([[-2, -2], [-2, -1], [-1, -2]]));
    // Each is right: every territory within reach is in this sector or one of them, and each has one in reach.
    for (let ly = 0; ly < 4; ly++) for (let lx = 0; lx < 4; lx++) {
      const list = new Set(near(lx, ly));
      for (let dy = -NOVA_REACH; dy <= NOVA_REACH; dy++) for (let dx = -NOVA_REACH; dx <= NOVA_REACH; dx++) {
        const sx = fdiv(lx + dx, 4), sy = fdiv(ly + dy, 4);
        if (sx || sy) assert.ok(list.has(`${sx},${sy}`), `${lx},${ly} misses ${sx},${sy}`);
      }
      for (const k of list) {
        const [sx, sy] = k.split(',').map(Number);
        const gap = (r, s) => Math.max(0, s * 4 - r, r - (s * 4 + 3));
        assert.ok(Math.max(gap(lx, sx), gap(ly, sy)) <= NOVA_REACH, `${lx},${ly} tells ${k}, out of reach`);
      }
    }
  });

  let clock, logged, sectors, pending, posts;
  beforeEach(() => {
    logged = mock.method(console, 'log', () => {});
    mock.timers.enable({ apis: ['setTimeout'] });
    clock = NOW;
    sectors = new Map();
    pending = [];
    posts = [];
  });
  afterEach(() => { mock.timers.reset(); logged.mock.restore(); });

  // The SECTORS binding: each name is a Sector of its own, made when first asked for, as Durable Objects are.
  const binding = {
    idFromName: (name) => name,
    get: (name) => ({
      fetch: (url, init) => {
        posts.push({ name, url: String(url), method: init?.method ?? 'GET' });
        return sectorAt(name).fetch(new Request(url, init));
      },
    }),
  };
  function sectorAt(name) {
    if (!sectors.has(name)) {
      const state = fakeState();
      state.waitUntil = (p) => pending.push(p);
      const s = new Sector(state, { SECTORS: binding });
      s.now = () => clock;
      sectors.set(name, s);
    }
    return sectors.get(name);
  }
  function join(name, initials = '') {
    const ws = fakeSocket();
    const [sx, sy] = name.split(',').map(Number);
    sectorAt(name).join(ws, sx, sy);
    if (initials) sectorAt(name).webSocketMessage(ws, JSON.stringify({ t: 'me', initials }));
    return ws;
  }
  const settle = async () => { while (pending.length) await pending.shift(); };
  // Every hidden word of territory (rx, ry) but the last stored, as a sector already holding them.
  function nearlyDone(rx, ry) {
    const words = territoryWords(rx, ry), name = `${fdiv(rx, 4)},${fdiv(ry, 4)}`;
    const sql = sectorAt(name).sql;
    words.slice(0, -1).forEach((o, i) => sql.exec(
      'INSERT INTO claims (key, w, x, y, d, s, initials, at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)', o.key, o.w, o.x, o.y, o.d, 'OLD', NOW - 1e6 + i,
    ));
    return { words, name, last: words.at(-1) };
  }
  async function chartLast(rx, ry, initials = 'AMY') {
    const t = nearlyDone(rx, ry), ws = join(t.name, initials);
    clock += 2000;
    await sectorAt(t.name).webSocketMessage(ws, JSON.stringify({ t: 'claim', ...pick(t.last) }));
    return { ...t, ws };
  }

  test('are passed on to the players of each neighbour, once the claim has its answer', async () => {
    // Territory (1, 2) of sector 0,0 reaches all eight of its neighbours; three have players.
    const left = join('-1,0'), above = join('0,-1'), corner = join('1,1'), corner2 = join('1,1');
    const { ws, last } = await chartLast(1, 2);
    // The claim went out first, and nothing waited on the neighbours.
    assert.equal(ws.sent.filter((m) => m.t === 'claimed').length, 1);
    assert.equal(pending.length, 1);
    await settle();
    const frame = { t: 'nova', n: [1, 2, clock, last.w, last.x, last.y, last.d, 'AMY'] };
    for (const p of [left, above, corner, corner2]) assert.deepEqual(p.sent.filter((m) => m.t === 'nova'), [frame]);
    assert.deepEqual(ws.sent.filter((m) => m.t === 'nova'), []);  // its own players had the claim
    assert.deepEqual(posts.map((p) => p.name).sort(), sorted(novaNeighbours(1, 2)));
    assert.ok(posts.every((p) => p.method === 'POST' && p.url === `https://sector${NEAR_PATH}`));
    // A claim after it, in the same territory or not, tells nobody again.
    posts.length = 0;
    clock += 2000;
    await sectorAt('0,0').webSocketMessage(ws, JSON.stringify({ t: 'claim', ...pick(chunk(0, 0).words[0]) }));
    await settle();
    assert.deepEqual(posts, []);
  });

  test('a neighbour with nobody in it answers at once and sends nothing', async () => {
    await chartLast(0, 0);
    await settle();
    assert.equal(posts.length, 3);
    for (const name of ['-1,-1', '-1,0', '0,-1']) assert.equal(sectorAt(name).ctx.getWebSockets().length, 0);
  });

  test('one neighbour failing doesn\'t stop the others or the claim', async () => {
    const fine = join('-1,0');
    const real = binding.get;
    binding.get = (name) => (name === '0,-1' ? { fetch: () => Promise.reject(new Error('gone')) } : real(name));
    try {
      const { ws } = await chartLast(0, 0);
      await settle();
      assert.equal(ws.sent.filter((m) => m.t === 'claimed').length, 1);
      assert.equal(fine.sent.filter((m) => m.t === 'nova').length, 1);
    } finally { binding.get = real; }
  });

  test('nothing is sent without the binding, or for a supernova found on waking', async () => {
    // Recorded on waking from claims made before supernovas were: no news to anyone.
    const { name } = nearlyDone(0, 0);
    const words = territoryWords(0, 0), o = words.at(-1);
    sectorAt(name).sql.exec('INSERT INTO claims (key, w, x, y, d, s, initials, at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)', o.key, o.w, o.x, o.y, o.d, 'OLD', NOW - 1);
    const other = join('-1,0');
    join(name);
    await settle();
    assert.equal(sectorAt(name).sql.exec('SELECT * FROM novas').toArray().length, 1);
    assert.deepEqual(posts, []);
    assert.deepEqual(other.sent.filter((m) => m.t === 'nova'), []);
    // A sector without SECTORS (as the share Worker's tests make them) records it and tells nobody.
    const state = fakeState(), lone = new Sector(state, {});
    lone.now = () => clock;
    const t = territoryWords(5, 5);
    t.slice(0, -1).forEach((w, i) => state.storage.sql.exec('INSERT INTO claims (key, w, x, y, d, s, initials, at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)', w.key, w.w, w.x, w.y, w.d, '', NOW - 1e6 + i));
    const ws = fakeSocket();
    lone.join(ws, 1, 1);
    clock += 2000;
    await lone.webSocketMessage(ws, JSON.stringify({ t: 'claim', ...pick(t.at(-1)) }));
    assert.equal(state.storage.sql.exec('SELECT * FROM novas').toArray().length, 1);
  });

  test('a forged supernova is refused, and none reaches the players', async () => {
    const p = join('-1,0'), s = sectorAt('-1,0');
    const words = territoryWords(0, 0), o = words.at(-1);
    const good = [0, 0, NOW, o.w, o.x, o.y, o.d, 'AMY'];
    const post = (nova, path = NEAR_PATH, method = 'POST') => s.fetch(new Request(`https://sector${path}`, { method, body: method === 'POST' ? JSON.stringify({ nova }) : undefined }));
    assert.ok(checkNova(good, -1, 0));
    const forged = [
      [0, 0, NOW, o.w, o.x + 1, o.y, o.d, 'AMY'],              // not where the word is
      [0, 0, NOW, 'ZZZZ', o.x, o.y, o.d, 'AMY'],               // not a word
      [1, 0, NOW, o.w, o.x, o.y, o.d, 'AMY'],                  // not the word's territory
      [0, 0, NOW, o.w, o.x, o.y, o.d, '<b>'],                  // not initials
      [0, 0, NOW, o.w, o.x, o.y, o.d],                         // too short
      null, 'nova',
    ];
    for (const n of forged) assert.equal((await post(n)).status, 400, JSON.stringify(n));
    // A real word, but in this sector's own territory, or too far off to see from here.
    const own = territoryWords(-1, 0)[0], far = territoryWords(4, 0)[0];
    assert.equal((await post([-1, 0, NOW, own.w, own.x, own.y, own.d, ''])).status, 400);
    assert.equal((await post([4, 0, NOW, far.w, far.x, far.y, far.d, ''])).status, 400);
    // The public router never reaches it: only WebSocket upgrades of sector paths go through.
    const env = { SECTORS: binding, ALLOWED_ORIGINS: ORIGIN };
    for (const path of [NEAR_PATH, `/v1/survey/-1/0${NEAR_PATH}`, `/v1/survey${NEAR_PATH}`]) {
      const res = await worker.fetch(new Request(`https://api.test${path}`, { method: 'POST', headers: { Origin: ORIGIN }, body: JSON.stringify({ nova: good }) }), env);
      assert.notEqual(res.status, 204, path);
    }
    assert.equal((await post(good, NEAR_PATH, 'GET')).status, 404);
    assert.deepEqual(p.sent.filter((m) => m.t === 'nova'), []);
    // The real one goes through.
    assert.equal((await post(good)).status, 204);
    assert.equal(p.sent.filter((m) => m.t === 'nova').length, 1);
  });
});

describe('the timelapse following a guild', () => {
  let db;
  beforeEach(() => { db = fakeD1(); forgetLog(); });
  const COBALT = 'c0ba17c0ba';
  const at = (x, y, time, guild = COBALT) => ({ key: keyOf('ACORN', x, y, 0), w: 'ACORN', x, y, d: 0, s: 0, initials: 'ZED', at: time, guild });
  const get = async (path, now = NOW) => {
    const res = await routeLog(new Request(`https://survey.test${path}`, { headers: { Origin: ORIGIN } }), { LOG_DB: db, ALLOWED_ORIGINS: ORIGIN }, now);
    return [res.status, await res.json(), res.headers.get('Cache-Control')];
  };

  test('says the guild\'s name and colour and the days it has words on, then each day\'s words', async () => {
    await writeLog(db, [at(1, 1, NOW - DAY_MS), at(2, 2, NOW), at(3, 3, NOW + 1, ''), at(4, 4, NOW + 2), at(5, 5, NOW + 3, 'eeeeeeeeee')],
      [], [{ lid: COBALT, a: 11, b: 0, c: 0 }]);
    const [, index, cache] = await get(`/v1/survey/log/timelapse/guild/${COBALT}`);
    assert.deepEqual(index, { name: 'Cobalt Compass Society', hue: 220, days: [[DAY - 1, 1], [DAY, 2]] });
    assert.equal(cache, `public, max-age=${TIMELAPSE_CACHE_S}`);
    const [, today, live] = await get(`/v1/survey/log/timelapse/guild/${COBALT}/${DAY}`);
    assert.deepEqual(today, { day: DAY, words: [[NOW - DAY * DAY_MS, 2, 2, 0], [NOW + 2 - DAY * DAY_MS, 4, 4, 0]], next: null });
    assert.equal(live, `public, max-age=${LIVE_CACHE_S}`);
    // A settled day is kept for good, as the day's own words are.
    const [, , kept] = await get(`/v1/survey/log/timelapse/guild/${COBALT}/${DAY - 1}`);
    assert.equal(kept, `public, max-age=${FOREVER_S}, immutable`);
    assert.deepEqual((await get('/v1/survey/log/timelapse/guild/ffffffffff'))[1], { name: null, hue: null, days: [] });
    assert.equal((await get(`/v1/survey/log/timelapse/guild/${COBALT}/${DAY + 1}`))[0], 400);
    assert.equal((await get(`/v1/survey/log/timelapse/guild/${COBALT}/${DAY}?after=nope`))[0], 400);
  });

  test('pages through a busy day of the guild\'s, along its own index', async () => {
    const rows = Array.from({ length: TIMELAPSE_PAGE + 3 }, (_, i) => at(i % 900, Math.floor(i / 900), NOW + i));
    await writeLog(db, rows, [], [{ lid: COBALT, a: 11, b: 0, c: 0 }]);
    const one = await readTimelapseGuildDay(db, COBALT, DAY);
    assert.equal(one.words.length, TIMELAPSE_PAGE);
    const [ms, ...key] = one.next.split('~');
    const two = await readTimelapseGuildDay(db, COBALT, DAY, { at: Number(ms), key: key.join('~') });
    assert.equal(two.words.length, 3);
    assert.equal(two.next, null);
    assert.match(plan(db, TIMELAPSE_GUILD_DAYS_SQL, COBALT), /SEARCH survey_log_guild_days USING (COVERING )?INDEX survey_log_guild_days_by_guild \(guild=\?\)/);
    for (const [sql, args] of [[TIMELAPSE_GUILD_DAY_SQL, [COBALT, 1, 2, 10]], [TIMELAPSE_GUILD_DAY_AFTER_SQL, [COBALT, 1, 2, 1, 'A', 10]]]) {
      const p = plan(db, sql, ...args);
      assert.match(p, /SEARCH survey_log USING (COVERING )?INDEX survey_log_by_guild/);
      assert.doesNotMatch(p, /TEMP B-TREE/);
    }
  });
});

describe('the timelapse', () => {
  let db;
  beforeEach(() => { db = fakeD1(); forgetLog(); });
  const get = (path, now = NOW, env = { LOG_DB: db, ALLOWED_ORIGINS: ORIGIN }) =>
    routeLog(new Request(`https://survey.test${path}`, { headers: { Origin: ORIGIN } }), env, now);

  test('gives a day as only what drawing needs, oldest first, with its supernovas', async () => {
    const day0 = DAY * DAY_MS;
    const a = stored(0, 0, 0, day0 + 5000), b = stored(-30, 5, 1, day0 + 60000, '');
    const stray = { key: keyOf('MONET', 1, 2, 3), w: 'MONET', x: 1, y: 2, d: 3, s: 1, initials: 'ABC', at: day0 + 90000 };
    await writeLog(db, [stored(1, 1, 0, day0 - 1), a, b, stray, stored(2, 2, 0, day0 + DAY_MS)], [nova(0, 0, day0 + 60000), nova(3, 3, day0 - 5)]);
    const page = await readTimelapseDay(db, DAY);
    assert.equal(page.day, DAY);
    assert.equal(page.next, null);
    assert.deepEqual(page.words, [
      [5000, a.x, a.y, a.d, a.w.length, regionTheme(fdiv(a.x, RC), fdiv(a.y, RC)), 0],
      [60000, b.x, b.y, b.d, b.w.length, regionTheme(fdiv(b.x, RC), fdiv(b.y, RC)), 0],
      [90000, 1, 2, 3, 5, VOCAB.get('MONET'), 1],  // a stray in its word's own theme
    ]);
    assert.deepEqual(page.novas, [[60000, 0, 0, regionTheme(0, 0)]]);
    // No words or initials: a replay draws them, it doesn't read them.
    assert.doesNotMatch(JSON.stringify(page), /ZED|ABC|MONET/);
  });

  test('pages through a busy day, with supernovas on the first page only', async () => {
    const day0 = DAY * DAY_MS, busy = [];
    for (let i = 0; i < TIMELAPSE_PAGE + 7; i++) busy.push(stored(i % 80, Math.floor(i / 80), i % 5, day0 + i));
    await writeLog(db, busy, [nova(0, 0, day0 + 10)]);
    const first = await readTimelapseDay(db, DAY);
    assert.equal(first.words.length, TIMELAPSE_PAGE);
    assert.equal(first.novas.length, 1);
    const [at, ...key] = first.next.split('~');
    const second = await readTimelapseDay(db, DAY, { at: Number(at), key: key.join('~') });
    assert.equal(second.words.length, 7);
    assert.deepEqual(second.novas, []);
    assert.equal(second.next, null);
    assert.deepEqual([...first.words, ...second.words].map((w) => w[0]), busy.map((r) => r.at - day0).sort((x, y) => x - y));
  });

  test('indexes the hours with words, the supernovas and the charted territories, with every theme', async () => {
    assert.deepEqual(await readTimelapse(db), { hours: [], novas: [], bounds: null, themes: THEMES.map((t) => [t.name, t.hue]), layout: LAYOUT });
    await writeLog(db, [stored(0, 0, 0, NOW), stored(0, 0, 1, NOW + 1), stored(-30, 5, 0, NOW - 2 * DAY_MS), stored(12, -9, 0, NOW - HOUR_MS),
      { key: keyOf('MONET', 9000, 9000, 0), w: 'MONET', x: 9000, y: 9000, d: 0, s: 1, initials: '', at: NOW }],
      [nova(0, 0, NOW), nova(1, 0, NOW + 2), nova(5, 5, NOW - 2 * DAY_MS)]);
    const index = await readTimelapse(db);
    assert.deepEqual(index.hours, [[HOUR - 48, 1], [HOUR - 1, 1], [HOUR, 3]]);
    assert.deepEqual(index.novas, [[HOUR - 48, 1], [HOUR, 2]]);
    // Hidden words only: the stray far out isn't in a territory's count.
    const cells = [chunk(0, 0).words[0], chunk(-30, 5).words[0], chunk(12, -9).words[0]].map((w) => [fdiv(w.x, RC), fdiv(w.y, RC)]);
    assert.deepEqual(index.bounds, [Math.min(...cells.map((c) => c[0])), Math.min(...cells.map((c) => c[1])),
      Math.max(...cells.map((c) => c[0])), Math.max(...cells.map((c) => c[1]))]);
  });

  test('says how to work out any territory\'s theme from the themes alone', () => {
    const [a, n] = LAYOUT;
    assert.equal(n, THEMES.length);
    for (let i = 0; i < 500; i++) {
      const rx = Math.floor(Math.random() * 400) - 200, ry = Math.floor(Math.random() * 400) - 200;
      assert.equal((((rx + a * ry) % n) + n) % n, regionTheme(rx, ry), `${rx},${ry}`);
    }
  });

  test('reads along the table\'s order and the supernovas\' index, never a scan of the log', () => {
    const from = DAY * DAY_MS, to = from + DAY_MS;
    for (const p of [plan(db, TIMELAPSE_DAY_SQL, from, to, 10), plan(db, TIMELAPSE_DAY_AFTER_SQL, from, to, from, 'A', 10)]) {
      assert.match(p, /SEARCH survey_log USING PRIMARY KEY \(at>\? AND at<\?\)/, p);
      assert.doesNotMatch(p, /SCAN|TEMP B-TREE/, p);
    }
    const novas = plan(db, TIMELAPSE_NOVAS_SQL, from, to);
    assert.match(novas, /SEARCH survey_log_novas USING COVERING INDEX survey_log_novas_by_time \(at>\? AND at<\?\)/, novas);
    assert.doesNotMatch(novas, /TEMP B-TREE/, novas);
    // The index reads the count tables and the supernovas over a range of days, never the log.
    const hours = plan(db, TIMELAPSE_HOURS_SQL, 1, 2);
    assert.match(hours, /SEARCH survey_log_hours USING PRIMARY KEY \(hour>\? AND hour<\?\)/, hours);
    const bounds = plan(db, TIMELAPSE_BOUNDS_SQL, 1, 2);
    assert.match(bounds, /SEARCH survey_log_territories USING PRIMARY KEY \(day>\? AND day<\?\)/, bounds);
    const novaHours = plan(db, TIMELAPSE_NOVA_HOURS_SQL, 1, 2);
    assert.match(novaHours, /SEARCH survey_log_novas USING COVERING INDEX survey_log_novas_by_time \(at>\? AND at<\?\)/, novaHours);
    for (const p of [hours, bounds, novaHours]) assert.doesNotMatch(p, /SCAN/, p);
  });

  test('reads the index\'s settled days once and keeps them, and only the days since each minute', async () => {
    await writeLog(db, [stored(0, 0, 0, NOW - 3 * DAY_MS), stored(-30, 5, 0, NOW - 1000)], [nova(0, 0, NOW - 3 * DAY_MS)]);
    const env = { LOG_DB: db, ALLOWED_ORIGINS: ORIGIN };
    const ranges = () => db.log.filter((q) => q.sql === TIMELAPSE_BOUNDS_SQL).map((q) => q.params);
    const whole = await (await get('/v1/survey/log/timelapse', NOW, env)).json();
    assert.deepEqual(whole.hours.map((h) => h[0]), [Math.floor((NOW - 3 * DAY_MS) / HOUR_MS), Math.floor((NOW - 1000) / HOUR_MS)]);
    assert.deepEqual(whole.novas, [[Math.floor((NOW - 3 * DAY_MS) / HOUR_MS), 1]]);
    const cut = Math.floor((NOW - SETTLED_MS) / DAY_MS);
    assert.deepEqual(ranges(), [[0, cut], [cut, 1e7]]);
    // A minute later: the recent days again, the settled ones from memory.
    await get('/v1/survey/log/timelapse', NOW + TIMELAPSE_CACHE_S * 1000, env);
    assert.deepEqual(ranges(), [[0, cut], [cut, 1e7], [cut, 1e7]]);
    // The same answer as reading everything at once.
    assert.deepEqual(whole, await readTimelapse(db));
  });

  test('keeps a settled day for good, today for seconds, and the index for a minute', async () => {
    await writeLog(db, [stored(0, 0, 0, NOW - 1000), stored(1, 0, 0, NOW - 2 * DAY_MS)]);
    const today = await get(`/v1/survey/log/timelapse/${DAY}`);
    assert.equal(today.headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    assert.equal(today.headers.get('Access-Control-Allow-Origin'), ORIGIN);
    assert.equal((await today.json()).words.length, 1);
    // Yesterday's last words can still be on their way just after midnight.
    const midnight = DAY * DAY_MS + 60000;
    assert.equal((await get(`/v1/survey/log/timelapse/${DAY - 1}`, midnight)).headers.get('Cache-Control'), `public, max-age=${LIVE_CACHE_S}`);
    const settled = await get(`/v1/survey/log/timelapse/${DAY - 2}`);
    assert.equal(settled.headers.get('Cache-Control'), `public, max-age=${FOREVER_S}, immutable`);
    assert.equal((await settled.json()).words.length, 1);
    const index = await get('/v1/survey/log/timelapse');
    assert.equal(index.headers.get('Cache-Control'), `public, max-age=${TIMELAPSE_CACHE_S}`);
    assert.equal((await index.json()).hours.length, 2);
    assert.equal((await get(`/v1/survey/log/timelapse/${DAY}?after=${NOW}~ACORN~1~-2~3`)).status, 200);
    assert.equal((await get(`/v1/survey/log/timelapse/${DAY}?after=nope`)).status, 400);
    assert.equal((await get(`/v1/survey/log/timelapse/${DAY + 1}`)).status, 400);
    assert.equal((await get(`/v1/survey/log/timelapse/${DAY}`, NOW, {})), null);
    assert.equal(get('/v1/survey/log/timelapse/x'), null);
  });

  test('reads a settled day from D1 once, and keeps it under its version in Cloudflare\'s cache', async () => {
    const kept = new Map();
    globalThis.caches = { default: { match: async (r) => kept.get(r.url)?.clone(), put: async (r, res) => { kept.set(r.url, res); } } };
    try {
      await writeLog(db, [stored(1, 0, 0, NOW - 2 * DAY_MS)]);
      const reads = () => db.log.filter((q) => q.sql.startsWith('SELECT')).length;
      await get(`/v1/survey/log/timelapse/${DAY - 2}`);
      const once = reads();
      await get(`/v1/survey/log/timelapse/${DAY - 2}`, NOW + 30 * DAY_MS);
      forgetLog();  // another Worker instance
      await get(`/v1/survey/log/timelapse/${DAY - 2}`, NOW + 30 * DAY_MS);
      assert.equal(reads(), once);
      assert.deepEqual([...kept.keys()], [`https://survey.test/_cache/survey-log/m${MAP_VERSION}/timelapse/v${TIMELAPSE_VERSION}/${DAY - 2}`]);
      assert.equal([...kept.values()][0].headers.get('Cache-Control'), `public, max-age=${FOREVER_S}, immutable`);
    } finally { delete globalThis.caches; }
  });
});
