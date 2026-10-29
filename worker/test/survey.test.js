// Tests for Letterfield's shared survey (src/survey.js), run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"
// The Sector Durable Object gets a stand-in for its state: SQLite storage
// backed by node:sqlite and fake WebSockets that record what they're sent.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';
import vm from 'node:vm';

import worker from '../src/index.js';
import { CH, DIRS, VOCAB, chunk, genChunk, keyOf, letterAt, wordEnd } from '../src/letterfield-world.js';
import {
  CLAIM_BURST, CLAIM_REFILL_MS, MAX_PLAYERS, PRESENCE_MAX, PRESENCE_MS, SECTOR, Sector, checkClaim, routeSurvey,
} from '../src/survey.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 9, 29, 12);

// Runs the world code from letterfield.html itself, from its world constants
// up to its formatting helpers, so the copy in src/ can be compared with it.
function gameWorld() {
  const html = readFileSync(new URL('../../letterfield.html', import.meta.url), 'utf8');
  const start = html.indexOf('/* ---------- World constants ---------- */');
  const end = html.indexOf('/* ---------- Formatting ---------- */');
  assert.ok(start > 0 && end > start, 'letterfield.html lost its section markers');
  const context = vm.createContext({ matchMedia: () => ({ matches: false }) });
  return vm.runInContext(`${html.slice(start, end)}; ({ genChunk, letterAt, SECTOR })`, context);
}

// A hidden word in the given chunk, as the game would send it.
function placed(cx, cy, n = 0) {
  const { w, x, y, d } = chunk(cx, cy).words[n];
  return { w, x, y, d };
}

// A word the letters spell by chance, found by reading the map near the origin.
function findStray() {
  for (let y = 0; y < 96; y++) {
    for (let x = 0; x < 96; x++) {
      for (let d = 0; d < 8; d++) {
        let s = '';
        for (let i = 0; i < 12; i++) {
          s += String.fromCharCode(65 + letterAt(x + DIRS[d][0] * i, y + DIRS[d][1] * i));
          if (s.length >= 4 && VOCAB.has(s) && !chunk(Math.floor(x / CH), Math.floor(y / CH)).words.some((p) => p.key === keyOf(s, x, y, d))) {
            return { w: s, x, y, d };
          }
        }
      }
    }
  }
  return null;
}

describe('the world copy', () => {
  test('matches the game, letter for letter and word for word', () => {
    const game = gameWorld();
    for (let cy = -6; cy <= 6; cy++) {
      for (let cx = -6; cx <= 6; cx++) {
        const ours = genChunk(cx, cy), theirs = game.genChunk(cx, cy);
        assert.deepEqual([...ours.g], [...theirs.g], `letters differ in chunk ${cx},${cy}`);
        assert.deepEqual(ours.words, JSON.parse(JSON.stringify(theirs.words)), `words differ in chunk ${cx},${cy}`);
      }
    }
    for (const [x, y] of [[1e6, -3e5], [-987654, 123457], [40000, 40000]]) assert.equal(letterAt(x, y), game.letterAt(x, y));
  });

  test('splits the map into the same sectors as the game', () => {
    assert.equal(gameWorld().SECTOR, SECTOR);
  });
});

describe('checkClaim', () => {
  test('accepts a hidden word in its own sector', () => {
    const word = placed(0, 0);
    assert.deepEqual(checkClaim(word, 0, 0), { key: keyOf(word.w, word.x, word.y, word.d), ...word, s: 0 });
    const far = placed(-40, 25, 1);
    assert.equal(checkClaim(far, Math.floor(far.x / SECTOR), Math.floor(far.y / SECTOR)).s, 0);
  });

  test('accepts a stray word of four letters or more', () => {
    const stray = findStray();
    assert.ok(stray, 'no stray word near the origin');
    assert.equal(checkClaim(stray, 0, 0).s, 1);
  });

  test('rejects words that are not on the map', () => {
    const word = placed(0, 0);
    assert.deepEqual(checkClaim({ ...word, x: word.x + 1 }, 0, 0), { error: 'word is not there' });
    assert.deepEqual(checkClaim({ ...word, d: (word.d + 4) % 8 }, 0, 0), { error: 'word is not there' });
    assert.deepEqual(checkClaim({ ...word, w: 'ZZZZ' }, 0, 0), { error: 'not a Letterfield word' });
    assert.deepEqual(checkClaim({ ...word, x: 1.5 }, 0, 0), { error: 'bad position' });
    assert.deepEqual(checkClaim({ ...word, d: 8 }, 0, 0), { error: 'bad position' });
    assert.deepEqual(checkClaim(null, 0, 0), { error: 'not a Letterfield word' });
    assert.deepEqual(checkClaim(word, 1, 0), { error: 'word starts in another sector' });
  });

  test('rejects three-letter strays, as the game does', () => {
    // Three letters in a row that spell a word but aren't a hidden word.
    let checked = 0;
    for (let y = 0; y < 24; y++) {
      for (let x = 0; x < 96; x++) {
        for (let d = 0; d < 8; d++) {
          const [dx, dy] = DIRS[d];
          const w = [0, 1, 2].map((i) => String.fromCharCode(65 + letterAt(x + dx * i, y + dy * i))).join('');
          if (!VOCAB.has(w) || chunk(Math.floor(x / CH), Math.floor(y / CH)).words.some((p) => p.key === keyOf(w, x, y, d))) continue;
          assert.deepEqual(checkClaim({ w, x, y, d }, 0, 0), { error: 'word is not there' });
          checked++;
        }
      }
    }
    assert.ok(checked > 0, 'no three-letter strays near the origin');
  });
});

// The parts of a Durable Object's state the Sector uses.
function fakeState() {
  const db = new DatabaseSync(':memory:');
  const sockets = [];
  return {
    sockets,
    storage: {
      sql: {
        exec(query, ...bindings) {
          const rows = db.prepare(query).all(...bindings);
          return { toArray: () => rows, one: () => { assert.equal(rows.length, 1); return rows[0]; } };
        },
      },
    },
    acceptWebSocket: (ws) => sockets.push(ws),
    getWebSockets: () => sockets.filter((ws) => ws.open),
  };
}

function fakeSocket() {
  let attachment = null;
  return {
    open: true,
    sent: [],
    send(text) { if (!this.open) throw new Error('closed'); this.sent.push(JSON.parse(text)); },
    close() { this.open = false; },
    serializeAttachment(value) { attachment = structuredClone(value); },
    deserializeAttachment: () => structuredClone(attachment),
    last(type) { return this.sent.filter((m) => m.t === type).at(-1); },
  };
}

describe('Sector', () => {
  let state, sector, clock;
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout'] });
    state = fakeState();
    sector = new Sector(state, {});
    clock = NOW;
    sector.now = () => clock;
  });
  afterEach(() => mock.timers.reset());

  function join(sx = 0, sy = 0) {
    const ws = fakeSocket();
    sector.join(ws, sx, sy);
    return ws;
  }
  const say = (ws, message) => sector.webSocketMessage(ws, JSON.stringify(message));
  const claim = (ws, word) => say(ws, { t: 'claim', ...word });

  test('greets a new player with the claims so far', async () => {
    const first = join();
    assert.deepEqual(first.sent[0], { t: 'hello', you: first.deserializeAttachment().id, sector: [0, 0], claims: [] });
    await say(first, { t: 'me', initials: 'ZED' });
    const word = placed(0, 0);
    await claim(first, word);
    const second = join();
    assert.deepEqual(second.sent[0].claims, [[word.w, word.x, word.y, word.d, 0, 'ZED', NOW]]);

    // The snapshot kept in memory matches storage, including after the object
    // is evicted and starts again with only its storage.
    const next = placed(0, 0, 1);
    await claim(second, next);
    const kept = join().sent[0].claims;
    sector = new Sector(state, {});
    assert.deepEqual(join().sent[0].claims, kept);
    assert.equal(kept.length, 2);
  });

  test('credits a word to the first player to claim it', async () => {
    const [a, b] = [join(), join()];
    await say(a, { t: 'me', initials: 'AAA' });
    await say(b, { t: 'me', initials: 'BBB' });
    const word = placed(0, 0, 2);
    await claim(a, word);
    const claimed = { t: 'claimed', c: [word.w, word.x, word.y, word.d, 0, 'AAA', NOW], by: a.deserializeAttachment().id };
    assert.deepEqual(a.last('claimed'), claimed);
    assert.deepEqual(b.last('claimed'), claimed);

    clock += 5000;
    await claim(b, word);
    assert.deepEqual(b.last('taken'), { t: 'taken', c: [word.w, word.x, word.y, word.d, 0, 'AAA', NOW] });
    assert.equal(a.last('taken'), undefined);
    assert.equal(b.sent.filter((m) => m.t === 'claimed').length, 1);
  });

  test('refuses claims that are not on the map or not in this sector', async () => {
    const ws = join();
    const word = placed(0, 0);
    await claim(ws, { ...word, x: word.x + 1 });
    assert.deepEqual(ws.last('error'), { t: 'error', key: keyOf(word.w, word.x + 1, word.y, word.d), error: 'word is not there' });
    const elsewhere = join(1, 0);
    await claim(elsewhere, word);
    assert.equal(elsewhere.last('error').error, 'word starts in another sector');
    assert.equal(ws.last('claimed'), undefined);
  });

  test('ignores initials it would not show and messages it cannot read', async () => {
    const ws = join();
    for (const initials of ['ab', 'ABCD', 'abc', 'KKK', 7]) {
      await say(ws, { t: 'me', initials });
      assert.equal(ws.deserializeAttachment().initials, '');
    }
    await sector.webSocketMessage(ws, 'not json');
    await sector.webSocketMessage(ws, JSON.stringify({ t: 'pos', x: 1, y: 2, pad: 'x'.repeat(300) }));
    await sector.webSocketMessage(ws, new ArrayBuffer(8));
    assert.equal(ws.deserializeAttachment().x, null);
    assert.equal(ws.sent.length, 1); // just the hello
  });

  test('limits how fast one socket can claim', async () => {
    const ws = join();
    const words = [...chunk(0, 0).words, ...chunk(1, 0).words];
    for (const w of words.slice(0, CLAIM_BURST + 1)) await claim(ws, w);
    assert.equal(ws.sent.filter((m) => m.t === 'claimed').length, CLAIM_BURST);
    assert.equal(ws.last('error').error, 'slow down');
    clock += CLAIM_REFILL_MS;
    await claim(ws, words[CLAIM_BURST + 1]);
    assert.equal(ws.sent.filter((m) => m.t === 'claimed').length, CLAIM_BURST + 1);
  });

  test('sends positions together, at most once a second', async () => {
    const [a, b, watcher] = [join(), join(), join()];
    await say(a, { t: 'me', initials: 'AAA' });
    await say(a, { t: 'pos', x: 6.04, y: 7 });
    clock += 10;
    await say(b, { t: 'pos', x: 20, y: 30 });
    assert.equal(watcher.last('presence'), undefined);
    mock.timers.tick(PRESENCE_MS);
    const ids = [a, b].map((ws) => ws.deserializeAttachment().id);
    const expected = { t: 'presence', n: 2, p: [[ids[1], '', 20, 30], [ids[0], 'AAA', 6, 7]] };
    for (const ws of [a, b, watcher]) assert.deepEqual(ws.last('presence'), expected);

    // A player who looks into another sector, or leaves, drops off.
    await say(b, { t: 'pos', away: true });
    a.close();
    await sector.webSocketClose(a);
    mock.timers.tick(PRESENCE_MS);
    assert.deepEqual(watcher.last('presence'), { t: 'presence', n: 0, p: [] });
  });

  test('caps the positions in one update but counts everyone', async () => {
    const players = Array.from({ length: PRESENCE_MAX + 6 }, () => join());
    for (const [i, ws] of players.entries()) { clock += 1; await say(ws, { t: 'pos', x: i, y: 0 }); }
    mock.timers.tick(PRESENCE_MS);
    const frame = players[0].last('presence');
    assert.equal(frame.n, PRESENCE_MAX + 6);
    assert.equal(frame.p.length, PRESENCE_MAX);
    assert.equal(frame.p[0][2], PRESENCE_MAX + 5); // most recently moved first
  });

  test('turns players away once the sector is full', async () => {
    state.getWebSockets = () => ({ length: MAX_PLAYERS });
    const response = await sector.fetch(new Request('https://survey.test/v1/survey/0/0', { headers: { Upgrade: 'websocket' } }));
    assert.equal(response.status, 503);
  });
});

describe('routeSurvey', () => {
  const forwarded = [];
  const env = {
    ALLOWED_ORIGINS: ORIGIN,
    SECTORS: {
      idFromName: (name) => ({ name }),
      get: (id) => ({ fetch: async (request) => { forwarded.push([id.name, request.url]); return new Response('ok'); } }),
    },
  };
  const open = (path, { origin = ORIGIN, upgrade = 'websocket', method = 'GET' } = {}) => {
    const headers = {};
    if (origin) headers.Origin = origin;
    if (upgrade) headers.Upgrade = upgrade;
    return routeSurvey(new Request(`https://survey.test${path}`, { method, headers }), env);
  };

  test('sends each sector to its own Durable Object', async () => {
    assert.equal(await (await open('/v1/survey/0/0')).text(), 'ok');
    await open('/v1/survey/-3/12');
    await open('/v1/survey/-0/007');
    assert.deepEqual(forwarded.map(([name]) => name), ['0,0', '-3,12', '0,7']);
  });

  test('turns away other origins and plain requests', async () => {
    assert.equal((await open('/v1/survey/0/0', { origin: 'https://evil.test' })).status, 403);
    assert.equal((await open('/v1/survey/0/0', { origin: null })).status, 403);
    assert.equal((await open('/v1/survey/0/0', { upgrade: null })).status, 426);
    assert.equal((await open('/v1/survey/0/0', { method: 'POST' })).status, 405);
  });

  test('is what the Worker does with survey paths, failures included', async () => {
    const broken = { ...env, SECTORS: { idFromName: () => ({}), get: () => ({ fetch: async () => { throw new Error('evicted'); } }) } };
    const request = () => new Request('https://survey.test/v1/survey/2/3', { headers: { Origin: ORIGIN, Upgrade: 'websocket' } });
    assert.equal(await (await worker.fetch(request(), env)).text(), 'ok');
    const errors = mock.method(console, 'error', () => {});
    const failed = await worker.fetch(request(), broken);
    assert.equal(failed.status, 500);
    assert.deepEqual(await failed.json(), { error: 'server error' });
    assert.equal(errors.mock.callCount(), 1);
    errors.mock.restore();
    const scores = await worker.fetch(new Request('https://survey.test/v1/scores?game=nope'), env);
    assert.equal(scores.status, 400); // the leaderboard's own answer
  });

  test('leaves every other path to the leaderboard', () => {
    for (const path of ['/v1/scores', '/v1/survey', '/v1/survey/0', '/v1/survey/a/b', '/v1/survey/12345678/0']) {
      assert.equal(open(path), null);
    }
    assert.equal(routeSurvey(new Request('https://survey.test/v1/survey/0/0'), {}), null);
  });
});

test('a word never crosses a sector edge', () => {
  // Hidden words stay inside their chunk, and chunks tile sectors exactly.
  assert.equal(SECTOR % CH, 0);
  for (const w of chunk(15, 15).words) {
    const [ex, ey] = wordEnd(w);
    assert.equal(Math.floor(ex / SECTOR), Math.floor(w.x / SECTOR));
    assert.equal(Math.floor(ey / SECTOR), Math.floor(w.y / SECTOR));
  }
});
