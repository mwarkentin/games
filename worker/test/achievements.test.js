// Tests for Letterfield's achievements on the Worker (src/achievements.js):
// the rules shared with the game, receipts for signed finds, the badges they
// prove, and a sector that signs and shows them. Run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

import worker from '../src/index.js';
import { CORE, TRUSTED_UNTIL, UNIVERSE_EDGE, badgeSig, checkBadge, checkReceipt, routeBadges, signFind } from '../src/achievements.js';
import { chunk } from '../src/letterfield-world.js';
import { AREA, Sector } from '../src/survey.js';
import { playerId } from '../src/survey-social.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const SALT = 'test-salt';
const DAY = 86400000;
const token = (n) => n.toString(16).padStart(32, '0');
// Every hidden word of territory (rx, ry), in chunk order.
const territoryWords = (rx, ry) => {
  const out = [];
  for (let cy = ry * 4; cy < ry * 4 + 4; cy++) for (let cx = rx * 4; cx < rx * 4 + 4; cx++) out.push(...chunk(cx, cy).words);
  return out;
};
const bare = ({ w, x, y, d }) => ({ w, x, y, d });

describe('the achievements core', () => {
  const block = (text) => {
    const start = text.indexOf('// ---- BEGIN ACHIEVEMENTS CORE ----'), end = text.indexOf('// ---- END ACHIEVEMENTS CORE ----');
    assert.ok(start >= 0 && end > start, 'lost its ACHIEVEMENTS CORE markers');
    return text.slice(start, end);
  };

  test('is the same in letterfield.html, word for word', () => {
    const game = readFileSync(new URL('../../letterfield.html', import.meta.url), 'utf8');
    const ours = readFileSync(new URL('../src/achievements.js', import.meta.url), 'utf8');
    assert.equal(block(ours), block(game));
  });

  test("names only themes the map has, and puts the universe's edge where the survey's is", () => {
    for (const i of [...CORE.BIRDS, ...CORE.SEAS, ...CORE.SKIES, ...CORE.NATIONS]) assert.ok(i >= 0);
    assert.equal(UNIVERSE_EDGE, AREA * 4);
    assert.equal(CORE.CATALOG.length, 39);
  });
});

describe('receipts', () => {
  const env = { IP_SALT: SALT };

  test("prove a find for the player they were made for, and nothing else", async () => {
    const pid = await playerId(token(1)), other = await playerId(token(2));
    const word = bare(chunk(0, 0).words[0]), at = Date.UTC(2026, 11, 1, 9);
    const r = await signFind(env, pid, word, at, 'f');
    assert.deepEqual(await checkReceipt(env, pid, { ...word, r }), { at, f: true, z: false });
    assert.equal(await checkReceipt(env, other, { ...word, r }), null);
    assert.equal(await checkReceipt(env, pid, { ...word, x: word.x + 1, r }), null);
    assert.equal(await checkReceipt(env, pid, { ...word, r: r.replace('.f.', '.fz.') }), null);
    assert.equal(await checkReceipt({ IP_SALT: 'another salt' }, pid, { ...word, r }), null);
    // Without a salt there's no key worth trusting, so nothing is signed or believed.
    assert.equal(await checkReceipt({}, pid, { ...word, r }), null);
  });
});

// The parts of a Durable Object's state a Sector uses, and its sockets.
function fakeState() {
  const db = new DatabaseSync(':memory:');
  const sockets = [];
  return {
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
    send(text) { const frame = JSON.parse(text); this.sent.push(...(Array.isArray(frame) ? frame : [frame])); },
    accept() {},
    close() { this.open = false; },
    serializeAttachment(value) { attachment = structuredClone(value); },
    deserializeAttachment: () => structuredClone(attachment),
    all(type) { return this.sent.filter((m) => m.t === type); },
  };
}

describe('a sector', () => {
  let sector, clock;
  const env = { IP_SALT: SALT };
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout'] });
    sector = new Sector(fakeState(), env);
    clock = Date.UTC(2026, 11, 20, 12);
    sector.now = () => clock;
  });
  afterEach(() => mock.timers.reset());
  const say = (ws, message) => sector.webSocketMessage(ws, JSON.stringify(message));
  async function join(n, initials, more = {}) {
    const ws = fakeSocket();
    sector.join(ws, 0, 0);
    await say(ws, { t: 'me', initials, ...(n ? { token: token(n) } : {}), ...more });
    return ws;
  }
  const claim = async (ws, word) => { clock += 2000; await say(ws, { t: 'claim', ...bare(word) }); };

  test("signs each word a surveyor circles, for them alone: charted first, or someone else's", async () => {
    const amy = await join(1, 'AMY'), zed = await join(2, 'ZED'), old = await join(0, 'OLD');
    const word = chunk(0, 0).words[0];
    await claim(amy, word);
    const [signed] = amy.all('signed');
    assert.equal(signed.k, word.key);
    assert.deepEqual(await checkReceipt(env, await playerId(token(1)), { ...bare(word), r: signed.r }), { at: clock, f: true, z: false });
    assert.deepEqual(zed.all('signed'), []);
    // Zed circles it too: theirs isn't first, but it's still theirs to prove.
    await claim(zed, word);
    assert.deepEqual(await checkReceipt(env, await playerId(token(2)), { ...bare(word), r: zed.all('signed')[0].r }), { at: clock, f: false, z: false });
    // A game that sends no token (an older one) gets no receipt.
    await claim(old, chunk(0, 0).words[1]);
    assert.deepEqual(old.all('signed'), []);
  });

  test('says which word set off a supernova', async () => {
    const amy = await join(1, 'AMY'), pid = await playerId(token(1));
    const words = territoryWords(1, 2);
    for (const o of words) await claim(amy, o);
    const receipts = amy.all('signed');
    assert.equal(receipts.length, words.length);
    const last = await checkReceipt(env, pid, { ...bare(words.at(-1)), r: receipts.at(-1).r });
    assert.deepEqual([last.f, last.z], [true, true]);
    assert.equal((await checkReceipt(env, pid, { ...bare(words[0]), r: receipts[0].r })).z, false);
  });

  test('shows the badge a surveyor picked, if the Worker signed it for them', async () => {
    const pid = await playerId(token(1));
    const amy = await join(1, 'AMY', { badge: ['seven-seas', await badgeSig(env, pid, 'seven-seas')] });
    await say(amy, { t: 'pos', x: 10, y: 10 });
    const zed = await join(2, 'ZED', { badge: ['seven-seas', await badgeSig(env, pid, 'seven-seas')] });  // Amy's, not Zed's
    await say(zed, { t: 'pos', x: 12, y: 10 });
    clock += 2000;
    await say(amy, { t: 'here' });
    await mock.timers.tick(2000);
    const p = Object.fromEntries(amy.all('presence').at(-1).p.map((q) => [q[1], q]));
    assert.deepEqual(p.AMY.slice(4), [[], 'seven-seas']);
    assert.deepEqual(p.ZED.slice(4), []);
    assert.equal(await checkBadge(env, pid, ['no-such-badge', await badgeSig(env, pid, 'no-such-badge')]), null);
  });
});

// The parts of D1 the badges use (their rate limit), with the leaderboard's migrations.
function fakeD1() {
  const db = new DatabaseSync(':memory:');
  const dir = new URL('../migrations/', import.meta.url);
  for (const file of readdirSync(dir).sort()) db.exec(readFileSync(new URL(file, dir), 'utf8'));
  const statement = (sql, params = []) => ({
    bind: (...values) => statement(sql, values),
    first: async (column) => { const row = db.prepare(sql).get(...params); return row ? (column ? row[column] : row) : null; },
    run: async () => { db.prepare(sql).run(...params); return { success: true }; },
  });
  return { prepare: (sql) => statement(sql) };
}

describe('POST /v1/survey/badges', () => {
  let env;
  const AFTER = TRUSTED_UNTIL + DAY, BEFORE = TRUSTED_UNTIL - DAY;
  beforeEach(() => { env = { DB: fakeD1(), ALLOWED_ORIGINS: ORIGIN, IP_SALT: SALT }; });
  const ask = async (body, now = AFTER, ip = '203.0.113.9') => {
    const res = await routeBadges(new Request('https://survey.test/v1/survey/badges', {
      method: 'POST', headers: { Origin: ORIGIN, 'CF-Connecting-IP': ip }, body: JSON.stringify({ token: token(1), ...body }),
    }), env, now);
    return [res.status, await res.json()];
  };
  // Finds signed for player 1, the sector's times one minute apart from `at`.
  const signed = async (words, at, flags = 'f', n = 1) => {
    const pid = await playerId(token(n));
    return Promise.all(words.map(async (o, i) => ({ ...bare(o), t: 0, r: await signFind(env, pid, o, at + i * 60000, flags) })));
  };

  test('signs the badges signed finds prove, worked out as the game does', async () => {
    const finds = await signed(territoryWords(0, 0).slice(0, 12), Date.UTC(2026, 11, 20, 10));
    const [status, { badges }] = await ask({ finds });
    assert.equal(status, 200);
    const pid = await playerId(token(1));
    assert.ok(badges['first-mark'] && badges['first-light']);
    assert.equal(badges['first-mark'], await badgeSig(env, pid, 'first-mark'));
    assert.equal(badges['field-book'], undefined);  // 12 finds, not 100
    assert.equal(badges.witness, undefined);  // being there for a supernova isn't something a find proves
  });

  test("takes the game's word for what it earned until TRUSTED_UNTIL, and after that only signed finds", async () => {
    const earned = ['great-atlas', 'witness', 'hats-off', 'not-a-badge'];
    assert.deepEqual(Object.keys((await ask({ earned }, BEFORE))[1].badges).sort(), ['great-atlas', 'hats-off', 'witness']);
    assert.deepEqual((await ask({ earned }, AFTER))[1].badges, {});
  });

  test("counts no find signed for someone else, unsigned, or tampered with", async () => {
    const words = territoryWords(0, 0).slice(0, 3);
    const theirs = await signed(words, Date.UTC(2026, 11, 20, 10), 'f', 2);
    const tampered = (await signed(words, Date.UTC(2026, 11, 20, 10), ''))
      .map((f) => ({ ...f, r: f.r.replace(/^([0-9a-z]+)\.\./, '$1.f.') }));
    const unsigned = words.map((o) => ({ ...bare(o), t: Date.now() }));
    assert.deepEqual((await ask({ finds: [...theirs, ...tampered, ...unsigned] }))[1].badges, {});
  });

  test("works out days surveyed from the sector's times, on the surveyor's own dates", async () => {
    // Three finds an evening for a week, at 23:00 in Toronto (04:00 the next day in UTC).
    const words = territoryWords(0, 0), finds = [];
    for (let day = 0; day < 7; day++) finds.push(...await signed(words.slice(day * 3, day * 3 + 3), Date.UTC(2026, 11, 10 + day, 4), ''));
    const ids = async (z) => Object.keys((await ask({ finds, z }, Date.UTC(2026, 11, 17, 12)))[1].badges);
    assert.ok((await ids(300)).includes('seven-days'));
  });

  test('needs a salt to sign with and a real token, and limits how often an address asks', async () => {
    assert.equal((await ask({ token: 'nope' }))[0], 400);
    for (let i = 0; i < 30; i++) assert.equal((await ask({}))[0], 200);
    assert.equal((await ask({}))[0], 429);
    env.IP_SALT = '';
    assert.equal((await ask({}, AFTER, '198.51.100.1'))[0], 503);
    const res = await worker.fetch(new Request('https://survey.test/v1/survey/badges', { method: 'POST', headers: { Origin: ORIGIN }, body: '{}' }), { ...env, IP_SALT: SALT });
    assert.equal(res.status, 400);  // routed, and no token
  });
});
