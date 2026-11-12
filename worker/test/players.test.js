// Tests for linking another device to a player (src/players.js). Run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { beforeEach, describe, test } from 'node:test';

import worker from '../src/index.js';
import { LINK_CODE, LINK_MS, cleanCarry, routeLinks } from '../src/players.js';

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

describe('linking a device', () => {
  let env, ip;
  beforeEach(() => { env = { ALLOWED_ORIGINS: ORIGIN, DB: fakeD1() }; ip = '203.0.113.5'; });
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
