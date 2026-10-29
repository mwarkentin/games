// Tests for the leaderboard Worker, run with:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"
// The Worker talks to D1 through a small stand-in backed by node:sqlite,
// loaded with the real migrations, so the SQL runs against real SQLite.

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { beforeEach, describe, test } from 'node:test';

import { handle, validate } from '../src/index.js';

const MIGRATIONS = new URL('../migrations/', import.meta.url);
const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 9, 29, 12);

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
beforeEach(() => {
  env = { DB: fakeD1(), ALLOWED_ORIGINS: `${ORIGIN},http://localhost:8000`, IP_SALT: 'test-salt' };
});

function entry(overrides = {}) {
  return {
    game: 'funnels-and-buckets', board: 'classic', initials: 'ABC',
    score: 150, level: 2, popped: 12, seconds: 90, ...overrides,
  };
}

function post(body, { origin = ORIGIN, ip = '203.0.113.7', now = NOW } = {}) {
  const headers = { 'Content-Type': 'text/plain;charset=UTF-8', 'CF-Connecting-IP': ip };
  if (origin) headers.Origin = origin;
  const request = new Request('https://leaderboard.test/v1/scores', {
    method: 'POST', headers, body: typeof body === 'string' ? body : JSON.stringify(body),
  });
  return handle(request, env, now);
}

function get(query, { origin = ORIGIN } = {}) {
  const headers = origin ? { Origin: origin } : {};
  return handle(new Request(`https://leaderboard.test/v1/scores?${query}`, { headers }), env, NOW);
}

describe('validate', () => {
  test('accepts a plausible Funnels & Buckets game', () => {
    assert.equal(validate(entry()), null);
    assert.equal(validate(entry({ board: 'starter-easy', level: 1, popped: 29 })), null);
  });

  test('rejects bad games, boards and initials', () => {
    assert.equal(validate(entry({ game: 'pong' })), 'unknown game');
    assert.equal(validate(entry({ board: 'classic-2s' })), 'unknown board');
    assert.equal(validate(entry({ initials: 'ab' })), 'initials must be three letters A-Z');
    assert.equal(validate(entry({ initials: 'abc' })), 'initials must be three letters A-Z');
    assert.equal(validate(entry({ initials: 'WTF' })), 'pick different initials');
  });

  test('rejects scores the game could not produce', () => {
    assert.equal(validate(entry({ score: 0 })), 'score must be a positive whole number');
    assert.equal(validate(entry({ score: 12.5 })), 'score must be a positive whole number');
    assert.equal(validate(entry({ score: 12 * 60 + 1 })), 'score is too high for the bubbles popped');
    assert.equal(validate(entry({ popped: 400, level: 41, score: 4000, seconds: 60 })), 'too many bubbles popped for the time played');
    assert.equal(validate(entry({ level: 5 })), 'level does not match bubbles popped');
    assert.equal(validate(entry({ board: 'classic-easy', level: 2 })), 'level does not match bubbles popped');
  });
});

describe('POST /v1/scores', () => {
  test('saves a score and returns its rank and the top 10', async () => {
    const response = await post(entry());
    assert.equal(response.status, 201);
    assert.equal(response.headers.get('Access-Control-Allow-Origin'), ORIGIN);
    const body = await response.json();
    assert.equal(body.rank, 1);
    assert.deepEqual(body.scores.map((s) => [s.rank, s.initials, s.score]), [[1, 'ABC', 150]]);
    assert.equal(body.scores[0].id, body.id);
  });

  test('ranks ties behind earlier scores and orders by score', async () => {
    await post(entry({ initials: 'AAA', score: 100 }), { ip: '1' });
    await post(entry({ initials: 'BBB', score: 300 }), { ip: '2' });
    const response = await post(entry({ initials: 'CCC', score: 100 }), { ip: '3' });
    const body = await response.json();
    assert.equal(body.rank, 3);
    assert.deepEqual(body.scores.map((s) => s.initials), ['BBB', 'AAA', 'CCC']);
  });

  test('keeps boards separate', async () => {
    await post(entry({ initials: 'AAA' }));
    const response = await post(entry({ initials: 'EZY', board: 'classic-easy', level: 1 }), { ip: '2' });
    assert.deepEqual((await response.json()).scores.map((s) => s.initials), ['EZY']);
  });

  test('returns only the top 10 and stores at most 100 per board', async () => {
    for (let i = 1; i <= 105; i++) await post(entry({ score: i }), { ip: `ip-${i}` });
    const top = await (await get('game=funnels-and-buckets&board=classic')).json();
    assert.deepEqual(top.scores.map((s) => s.score), [105, 104, 103, 102, 101, 100, 99, 98, 97, 96]);
    const stored = env.DB.raw.prepare('SELECT COUNT(*) AS n, MIN(score) AS low FROM scores').get();
    assert.deepEqual({ ...stored }, { n: 100, low: 6 });
  });

  test('rejects invalid scores without saving them', async () => {
    const response = await post(entry({ score: 99999 }));
    assert.equal(response.status, 400);
    assert.equal((await response.json()).error, 'score is too high for the bubbles popped');
    assert.equal(env.DB.raw.prepare('SELECT COUNT(*) AS n FROM scores').get().n, 0);
  });

  test('rejects bodies that are not JSON', async () => {
    const response = await post('not json');
    assert.equal(response.status, 400);
  });

  test('refuses pages that are not on the allowed list', async () => {
    const other = await post(entry(), { origin: 'https://example.com' });
    assert.equal(other.status, 403);
    assert.equal(other.headers.get('Access-Control-Allow-Origin'), null);
    const none = await post(entry(), { origin: null });
    assert.equal(none.status, 403);
  });

  test('limits each IP address to 10 saves per 10 minutes', async () => {
    for (let i = 0; i < 10; i++) assert.equal((await post(entry(), { now: NOW + i })).status, 201);
    const limited = await post(entry(), { now: NOW + 11 });
    assert.equal(limited.status, 429);
    assert.equal((await post(entry(), { ip: '198.51.100.1', now: NOW + 12 })).status, 201);
    assert.equal((await post(entry(), { now: NOW + 10 * 60 * 1000 + 1 })).status, 201);
  });

  test('stores a salted hash, not the IP address', async () => {
    await post(entry(), { ip: '203.0.113.7' });
    const row = env.DB.raw.prepare('SELECT ip_hash FROM submissions').get();
    assert.match(row.ip_hash, /^[0-9a-f]{64}$/);
    assert.ok(!row.ip_hash.includes('203.0.113.7'));
  });
});

describe('GET /v1/scores', () => {
  test('returns an empty board', async () => {
    const response = await get('game=funnels-and-buckets&board=challenge');
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { game: 'funnels-and-buckets', board: 'challenge', scores: [] });
  });

  test('rejects unknown boards', async () => {
    assert.equal((await get('game=funnels-and-buckets&board=nope')).status, 400);
  });

  test('omits CORS headers for other origins', async () => {
    const response = await get('game=funnels-and-buckets&board=classic', { origin: 'https://example.com' });
    assert.equal(response.headers.get('Access-Control-Allow-Origin'), null);
  });
});

test('answers CORS preflight and unknown paths', async () => {
  const preflight = await handle(
    new Request('https://leaderboard.test/v1/scores', { method: 'OPTIONS', headers: { Origin: ORIGIN } }), env, NOW,
  );
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get('Access-Control-Allow-Methods'), 'GET, POST, OPTIONS');
  const missing = await handle(new Request('https://leaderboard.test/'), env, NOW);
  assert.equal(missing.status, 404);
});
