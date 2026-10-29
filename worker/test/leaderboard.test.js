// Tests for the leaderboard Worker, run with:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"
// The Worker talks to D1 through a small stand-in backed by node:sqlite,
// loaded with the real migrations, so the SQL runs against real SQLite.

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { beforeEach, describe, test } from 'node:test';

import { handle, validate } from '../src/leaderboard.js';

const MIGRATIONS = new URL('../migrations/', import.meta.url);
const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 9, 29, 12);
const BOARD = 'game=funnels-and-buckets&difficulty=classic&mode=normal';

// The parts of the D1 API the Worker uses: prepare().bind().all()/first()/run().
function fakeD1() {
  const db = new DatabaseSync(':memory:');
  for (const file of readdirSync(MIGRATIONS).sort()) db.exec(readFileSync(new URL(file, MIGRATIONS), 'utf8'));
  const statement = (sql, params = []) => ({
    bind: (...values) => statement(sql, values),
    all: async () => ({ results: db.prepare(sql).all(...params) }),
    first: async (column) => {
      const row = db.prepare(sql).get(...params);
      if (!row) return null;
      return column ? row[column] : row;
    },
    run: async () => {
      const result = db.prepare(sql).run(...params);
      return { success: true, meta: { changes: result.changes, last_row_id: Number(result.lastInsertRowid) } };
    },
  });
  return { prepare: (sql) => statement(sql), raw: db };
}

let env;
let clock;
beforeEach(() => {
  env = { DB: fakeD1(), ALLOWED_ORIGINS: `${ORIGIN},http://localhost:8000`, IP_SALT: 'test-salt' };
  clock = NOW;
});

function entry(overrides = {}) {
  return {
    game: 'funnels-and-buckets', difficulty: 'classic', mode: 'normal', initials: 'ABC',
    score: 150, level: 2, popped: 12, seconds: 90, ...overrides,
  };
}

function request(method, path, { body, origin = ORIGIN, ip = '203.0.113.7' } = {}) {
  const headers = { 'CF-Connecting-IP': ip };
  if (origin) headers.Origin = origin;
  if (body !== undefined) headers['Content-Type'] = 'text/plain;charset=UTF-8';
  const init = { method, headers };
  if (body !== undefined) init.body = typeof body === 'string' ? body : JSON.stringify(body);
  return handle(new Request(`https://leaderboard.test${path}`, init), env, clock++);
}

const save = (body, options) => request('POST', '/v1/scores', { body, ...options });
const view = (query, options) => request('GET', `/v1/scores?${query}`, options);
const createGroup = (name, options) => request('POST', '/v1/groups', { body: { name }, ...options });

async function newGroup(name = 'Family') {
  const response = await createGroup(name);
  assert.equal(response.status, 201);
  return (await response.json()).code;
}

async function initials(query) {
  return (await (await view(query)).json()).scores.map((s) => s.initials);
}

describe('validate', () => {
  test('accepts a plausible Funnels & Buckets game', () => {
    assert.equal(validate(entry()), null);
    assert.equal(validate(entry({ difficulty: 'starter', mode: 'easy', level: 1, popped: 29 })), null);
    assert.equal(validate(entry({ groups: ['AB2C'], public: false })), null);
  });

  test('rejects bad games, filters, initials and groups', () => {
    assert.equal(validate(entry({ game: 'pong' })), 'unknown game');
    assert.equal(validate(entry({ difficulty: 'hard' })), 'unknown difficulty');
    assert.equal(validate(entry({ mode: 'fast' })), 'unknown mode');
    assert.equal(validate(entry({ initials: 'abc' })), 'initials must be three letters A-Z');
    assert.equal(validate(entry({ initials: 'WTF' })), 'pick different initials');
    assert.equal(validate(entry({ groups: ['AB0C'] })), 'groups must be up to 5 group codes');
    assert.equal(validate(entry({ groups: ['AAAA', 'BBBB', 'CCCC', 'DDDD', 'EEEE', 'FFFF'] })), 'groups must be up to 5 group codes');
    assert.equal(validate(entry({ public: false })), 'save to the public board or at least one group');
  });

  test('rejects scores the game could not produce', () => {
    assert.equal(validate(entry({ score: 0 })), 'score must be a positive whole number');
    assert.equal(validate(entry({ score: 12 * 60 + 1 })), 'score is too high for the bubbles popped');
    assert.equal(validate(entry({ popped: 400, level: 41, score: 4000, seconds: 60 })), 'too many bubbles popped for the time played');
    assert.equal(validate(entry({ level: 5 })), 'level does not match bubbles popped');
    assert.equal(validate(entry({ mode: 'easy', level: 2 })), 'level does not match bubbles popped');
  });
});

describe('saving scores', () => {
  test('saves to the public board and returns the rank', async () => {
    const response = await save(entry());
    assert.equal(response.status, 201);
    assert.equal(response.headers.get('Access-Control-Allow-Origin'), ORIGIN);
    const body = await response.json();
    assert.match(body.entry, /^[0-9a-f-]{36}$/);
    assert.deepEqual(body.ranks, { '*': 1 });
  });

  test('ranks within the game’s own difficulty and mode, ties behind earlier scores', async () => {
    await save(entry({ initials: 'AAA', score: 100 }), { ip: '1' });
    await save(entry({ initials: 'BBB', score: 300 }), { ip: '2' });
    await save(entry({ initials: 'EZY', score: 500, mode: 'easy', level: 1 }), { ip: '3' });
    const body = await (await save(entry({ initials: 'CCC', score: 100 }), { ip: '4' })).json();
    assert.deepEqual(body.ranks, { '*': 3 });
  });

  test('saves to each group too, or only to groups', async () => {
    const family = await newGroup('Family');
    const friends = await newGroup('Friends');
    const both = await (await save(entry({ initials: 'MOM', groups: [family, friends] }))).json();
    assert.deepEqual(Object.keys(both.ranks).sort(), ['*', family, friends].sort());
    const quiet = await (await save(entry({ initials: 'KID', score: 400, groups: [family], public: false }))).json();
    assert.deepEqual(quiet.ranks, { [family]: 1 });

    assert.deepEqual(await initials(`${BOARD}&scope=*`), ['MOM']);
    assert.deepEqual(await initials(`${BOARD}&scope=${family}`), ['KID', 'MOM']);
    assert.deepEqual(await initials(`${BOARD}&scope=${friends}`), ['MOM']);
  });

  test('rejects groups that do not exist', async () => {
    const response = await save(entry({ groups: ['ZZZZ'] }));
    assert.equal(response.status, 400);
    assert.equal((await response.json()).error, 'unknown group ZZZZ');
  });

  test('keeps the top 100 per scope, difficulty and mode', async () => {
    for (let i = 1; i <= 105; i++) await save(entry({ score: i }), { ip: `ip-${i}` });
    await save(entry({ score: 1, mode: 'easy', level: 1 }), { ip: 'other' });
    const counts = env.DB.raw.prepare('SELECT mode, COUNT(*) AS n, MIN(score) AS low FROM scores GROUP BY mode ORDER BY mode').all();
    assert.deepEqual(counts.map((r) => ({ ...r })), [
      { mode: 'easy', n: 1, low: 1 },
      { mode: 'normal', n: 100, low: 6 },
    ]);
  });

  test('rejects invalid scores and bodies without saving', async () => {
    assert.equal((await save(entry({ score: 99999 }))).status, 400);
    assert.equal((await save('not json')).status, 400);
    assert.equal(env.DB.raw.prepare('SELECT COUNT(*) AS n FROM scores').get().n, 0);
  });

  test('refuses pages that are not on the allowed list', async () => {
    const other = await save(entry(), { origin: 'https://example.com' });
    assert.equal(other.status, 403);
    assert.equal(other.headers.get('Access-Control-Allow-Origin'), null);
    assert.equal((await save(entry(), { origin: null })).status, 403);
  });

  test('limits each IP address to 10 saves per 10 minutes', async () => {
    for (let i = 0; i < 10; i++) assert.equal((await save(entry())).status, 201);
    assert.equal((await save(entry())).status, 429);
    assert.equal((await save(entry(), { ip: '198.51.100.1' })).status, 201);
    clock += 10 * 60 * 1000;
    assert.equal((await save(entry())).status, 201);
  });

  test('stores a salted hash, not the IP address', async () => {
    await save(entry(), { ip: '203.0.113.7' });
    const row = env.DB.raw.prepare('SELECT ip_hash FROM submissions').get();
    assert.match(row.ip_hash, /^[0-9a-f]{64}$/);
    assert.ok(!row.ip_hash.includes('203.0.113.7'));
  });
});

describe('views', () => {
  beforeEach(async () => {
    await save(entry({ initials: 'CLA', score: 200 }), { ip: '1' });
    await save(entry({ initials: 'STA', score: 300, difficulty: 'starter' }), { ip: '2' });
    await save(entry({ initials: 'EZY', score: 250, mode: 'easy', level: 1 }), { ip: '3' });
    await save(entry({ initials: 'CHA', score: 100, difficulty: 'challenge' }), { ip: '4' });
  });

  test('everything, by default', async () => {
    const body = await (await view('game=funnels-and-buckets')).json();
    assert.equal(body.scope, '*');
    assert.deepEqual(body.scores.map((s) => [s.rank, s.initials, s.difficulty, s.mode]), [
      [1, 'STA', 'starter', 'normal'],
      [2, 'EZY', 'classic', 'easy'],
      [3, 'CLA', 'classic', 'normal'],
      [4, 'CHA', 'challenge', 'normal'],
    ]);
  });

  test('filtered by difficulty, mode or both', async () => {
    assert.deepEqual(await initials('game=funnels-and-buckets&difficulty=classic'), ['EZY', 'CLA']);
    assert.deepEqual(await initials('game=funnels-and-buckets&mode=normal'), ['STA', 'CLA', 'CHA']);
    assert.deepEqual(await initials(BOARD), ['CLA']);
  });

  test('returns at most 10', async () => {
    for (let i = 0; i < 12; i++) await save(entry({ score: 10 + i }), { ip: `x${i}` });
    assert.equal((await (await view('game=funnels-and-buckets')).json()).scores.length, 10);
  });

  test('rejects unknown filters and groups', async () => {
    assert.equal((await view('game=pong')).status, 400);
    assert.equal((await view('game=funnels-and-buckets&difficulty=hard')).status, 400);
    assert.equal((await view('game=funnels-and-buckets&mode=fast')).status, 400);
    assert.equal((await view('game=funnels-and-buckets&scope=ZZZZ')).status, 404);
  });

  test('omits CORS headers for other origins', async () => {
    const response = await view('game=funnels-and-buckets', { origin: 'https://example.com' });
    assert.equal(response.headers.get('Access-Control-Allow-Origin'), null);
  });
});

describe('groups', () => {
  test('creating one returns a readable four-character code', async () => {
    const response = await createGroup('  The   Warkentins ');
    assert.equal(response.status, 201);
    const body = await response.json();
    assert.match(body.code, /^[A-HJKMNP-Z2-9]{4}$/);
    assert.equal(body.name, 'The Warkentins');
  });

  test('looking one up by code', async () => {
    const code = await newGroup('Friends');
    const found = await request('GET', `/v1/groups/${code}`);
    assert.equal(found.status, 200);
    assert.deepEqual(await found.json(), { code, name: 'Friends' });
    assert.equal((await request('GET', '/v1/groups/ZZZZ')).status, 404);
    assert.equal((await request('GET', '/v1/groups/nope')).status, 404);
  });

  test('names must be short and plain', async () => {
    assert.equal((await createGroup('')).status, 400);
    assert.equal((await createGroup('x'.repeat(25))).status, 400);
    assert.equal((await createGroup('<script>')).status, 400);
    assert.equal((await createGroup('Ünïcode & Friends')).status, 201);
  });

  test('only allowed pages can create groups, five an hour per IP address', async () => {
    assert.equal((await createGroup('Nope', { origin: 'https://example.com' })).status, 403);
    for (let i = 0; i < 5; i++) assert.equal((await createGroup(`Group ${i}`)).status, 201);
    assert.equal((await createGroup('One more')).status, 429);
  });
});

test('answers CORS preflight and unknown paths', async () => {
  const preflight = await request('OPTIONS', '/v1/scores');
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get('Access-Control-Allow-Methods'), 'GET, POST, OPTIONS');
  assert.equal((await request('GET', '/')).status, 404);
  assert.equal((await request('DELETE', '/v1/scores')).status, 404);
});
