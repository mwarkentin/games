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
  AREA, AREA_WORDS, Atlas, BATCH_MS, CLAIM_BURST, CLAIM_REFILL_MS, MAX_ONLINE, MAX_PLAYERS, ONLINE_MS, PRESENCE_MAX, PRESENCE_MS,
  QUIET, REPORT_MS, SAVE_MS, SAVE_POS_MS, SECTOR, SPAWN_MAX, Sector, VIEW_MS, checkClaim, routeSurvey,
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
  return vm.runInContext(`${html.slice(start, end)}; ({ genChunk, letterAt, SECTOR, SURVEY_AREA })`, context);
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

  test('splits the map into the same sectors and shared world as the game', () => {
    const game = gameWorld();
    assert.equal(game.SECTOR, SECTOR);
    assert.equal(game.SURVEY_AREA, AREA);
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
    saves: 0,
    send(text) {
      if (!this.open) throw new Error('closed');
      const frame = JSON.parse(text);
      this.sent.push(...(Array.isArray(frame) ? frame : [frame]));  // a batch, as the game reads it
      this.frames = (this.frames ?? 0) + 1;
    },
    accept() {},
    close(code) { this.open = false; this.code = code; },
    serializeAttachment(value) { this.saves++; attachment = structuredClone(value); },
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
    mock.timers.tick(BATCH_MS);
    assert.equal(ws.sent.filter((m) => m.t === 'claimed').length, CLAIM_BURST);
    assert.equal(ws.last('error').error, 'slow down');
    clock += CLAIM_REFILL_MS;
    await claim(ws, words[CLAIM_BURST + 1]);
    assert.equal(ws.sent.filter((m) => m.t === 'claimed').length, CLAIM_BURST + 1);
  });

  test('sends claims made close together in one frame', async () => {
    const [a, b, watcher] = [join(), join(), join()];
    const words = chunk(0, 0).words;
    await claim(a, words[0]);  // the first goes at once
    assert.equal(watcher.frames, 2);
    clock += 50;
    await claim(b, words[1]);
    await claim(a, words[2]);
    assert.equal(watcher.frames, 2);
    clock += BATCH_MS;
    mock.timers.tick(BATCH_MS);
    assert.equal(watcher.frames, 3);
    assert.deepEqual(watcher.sent.filter((m) => m.t === 'claimed').map((m) => m.c[0]), [words[0].w, words[1].w, words[2].w]);
  });

  test('sends positions together, at most once a second', async () => {
    const [a, b, watcher] = [join(), join(), join()];
    await say(a, { t: 'pos', x: 6.04, y: 7 });
    const ids = [a, b].map((ws) => ws.deserializeAttachment().id);
    // The first change goes out at once.
    assert.deepEqual(watcher.last('presence'), { t: 'presence', n: 1, p: [[ids[0], '', 6, 7]] });
    clock += 10;
    await say(a, { t: 'me', initials: 'AAA' });
    await say(b, { t: 'pos', x: 20, y: 30 });
    assert.equal(watcher.sent.filter((m) => m.t === 'presence').length, 1);
    assert.equal(sector.presenceTimer, null);
    // The rest go with the first message once a second has passed.
    clock += PRESENCE_MS;
    await say(b, { t: 'pos', x: 20.5, y: 30 });
    const expected = { t: 'presence', n: 2, p: [[ids[1], '', 20.5, 30], [ids[0], 'AAA', 6, 7]] };
    for (const ws of [a, b, watcher]) assert.deepEqual(ws.last('presence'), expected);

    // A player who looks into another sector, or leaves, drops off, even if
    // nothing else happens: in a quiet sector that's worth a timer.
    clock += 10;
    await say(b, { t: 'pos', away: true });
    a.close();
    await sector.webSocketClose(a);
    clock += PRESENCE_MS;
    mock.timers.tick(PRESENCE_MS);
    assert.deepEqual(watcher.last('presence'), { t: 'presence', n: 0, p: [] });
  });

  test('saves positions to the socket now and then, and finds them after waking', async () => {
    const [ws, watcher] = [join(), join()];
    const saves = ws.saves;
    for (let i = 0; i < 10; i++) { clock += 1000; await say(ws, { t: 'pos', x: i, y: 1 }); }
    assert.equal(ws.saves - saves, 10000 / SAVE_POS_MS);
    assert.equal(ws.deserializeAttachment().x, 5);  // the last one saved
    // A woken sector knows roughly where everyone was.
    sector = new Sector(state, {});
    sector.now = () => clock;
    clock += PRESENCE_MS;
    sector.sendPresence();
    assert.deepEqual(watcher.last('presence').p.map((p) => p.slice(2)), [[5, 1]]);
    // Looking away is saved straight away.
    await say(ws, { t: 'pos', away: true });
    assert.equal(ws.deserializeAttachment().x, null);
  });

  test('a busy sector sets no timers, so it can hibernate between messages', async () => {
    const players = Array.from({ length: QUIET }, () => join());
    for (const [i, ws] of players.entries()) { clock += 1; await say(ws, { t: 'pos', x: i, y: 0 }); }
    assert.equal(sector.presenceTimer, null);
    const frames = () => players[0].sent.filter((m) => m.t === 'presence');
    assert.equal(frames().length, 1);  // the first move, at once; the rest are owed
    // Owed positions go out with the first message after they come due.
    clock += PRESENCE_MS;
    await say(players[5], { t: 'me', initials: 'FIV' });
    assert.equal(frames().length, 2);
    assert.equal(frames()[1].n, QUIET);
  });

  test('caps the positions in one update but counts everyone', async () => {
    const players = Array.from({ length: PRESENCE_MAX + 6 }, () => join());
    for (const [i, ws] of players.entries()) { clock += 1; await say(ws, { t: 'pos', x: i, y: 0 }); }
    clock += PRESENCE_MS;
    await say(players[0], { t: 'me', initials: 'CAP' });
    const frame = players[0].last('presence');
    assert.equal(frame.n, PRESENCE_MAX + 6);
    assert.equal(frame.p.length, PRESENCE_MAX);
    assert.equal(frame.p[0][2], PRESENCE_MAX + 5); // most recently moved first
  });

  test('tells players a full sector, or a full survey, has no room', async () => {
    // Stand-ins for the runtime's WebSocketPair and its 101 responses.
    let pair;
    globalThis.WebSocketPair = function WebSocketPair() { pair = [fakeSocket(), fakeSocket()]; return { 0: pair[0], 1: pair[1] }; };
    const RealResponse = Response;
    globalThis.Response = class { constructor(body, init) { Object.assign(this, init); } };
    const open = () => sector.fetch(new Request('https://survey.test/v1/survey/0/0', { headers: { Upgrade: 'websocket' } }));
    try {
      const sockets = state.getWebSockets;
      state.getWebSockets = () => ({ length: MAX_PLAYERS });
      const response = await open();
      assert.equal(response.status, 101);
      assert.equal(response.webSocket, pair[0]);
      assert.deepEqual(pair[1].sent, [{ t: 'full', world: false }]);
      assert.equal(pair[1].code, 4000);

      state.getWebSockets = sockets;
      sector.world = { charted: 0, total: AREA_WORDS, players: MAX_ONLINE };
      await open();
      assert.deepEqual(pair[1].sent, [{ t: 'full', world: true }]);
      assert.equal(state.sockets.length, 0);
    } finally {
      globalThis.Response = RealResponse;
      delete globalThis.WebSocketPair;
    }
  });

  function reportingSector(reports) {
    const env = {
      ATLAS: {
        idFromName: (name) => name,
        get: () => ({
          fetch: async (url, init) => {
            reports.push(JSON.parse(init.body));
            return Response.json({ charted: 1000 + reports.length, total: AREA_WORDS, players: 40 });
          },
        }),
      },
    };
    sector = new Sector(state, env);
    sector.now = () => clock;
  }
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  // Two territories of sector 2,-3, and the charted counts for its first n words.
  const words = [...chunk(32, -48).words, ...chunk(36, -44).words];
  const countsFor = (n) => {
    const counts = Array(16).fill(0);
    for (const w of words.slice(0, n)) counts[(Math.floor(w.y / 48) + 12) * 4 + Math.floor(w.x / 48) - 8]++;
    return counts;
  };

  test('reports its numbers to the Atlas and passes the totals on', async () => {
    const reports = [];
    reportingSector(reports);
    const [a, b] = [join(2, -3), join(2, -3)];
    await claim(a, words[0]);
    await settle();
    assert.deepEqual(reports, [{ sx: 2, sy: -3, players: 0, charted: countsFor(1), hot: [words[0].x, words[0].y] }]);
    assert.deepEqual(b.last('world'), { t: 'world', charted: 1001, total: AREA_WORDS, players: 40 });

    // Changes within REPORT_MS wait for the first message after it.
    await claim(a, words[1]);
    await say(b, { t: 'pos', x: 400, y: -500 });
    assert.equal(reports.length, 1);
    mock.timers.tick(REPORT_MS);
    assert.equal(reports.length, 1);  // no timer
    clock += REPORT_MS;
    await say(b, { t: 'pos', x: 401, y: -500 });
    await settle();
    assert.deepEqual(reports[1], { sx: 2, sy: -3, players: 1, charted: countsFor(2), hot: [words[1].x, words[1].y] });
    assert.deepEqual(b.last('world'), { t: 'world', charted: 1002, total: AREA_WORDS, players: 40 });
    // Later joiners get the totals straight away.
    assert.deepEqual(join(2, -3).sent[1], { t: 'world', charted: 1002, total: AREA_WORDS, players: 40 });
  });

  test('reports its last change when its players leave', async () => {
    const reports = [];
    reportingSector(reports);
    const players = Array.from({ length: QUIET }, () => join(2, -3));  // busy: no timers
    await claim(players[0], words[0]);
    await settle();
    await claim(players[0], words[1]);
    assert.equal(reports.length, 1);
    players[0].close();
    await sector.webSocketClose(players[0]);
    await settle();
    assert.equal(reports.length, 2);
    assert.deepEqual(reports[1].charted, countsFor(2));
  });

  test('keeps sectors outside the shared world to themselves', async () => {
    const env = { ATLAS: { idFromName: () => 'atlas', get: () => assert.fail('reported') } };
    sector = new Sector(state, env);
    const ws = join(AREA + 1, 0);
    await say(ws, { t: 'pos', x: (AREA + 1) * SECTOR + 5, y: 5 });
    await claim(ws, chunk((AREA + 1) * 16, 0).words[0]);
    clock += REPORT_MS;
    await say(ws, { t: 'pos', x: (AREA + 1) * SECTOR + 9, y: 5 });
    assert.equal(sector.reportDue, false);
  });
});

describe('Atlas', () => {
  let state, atlasObject, clock;
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout'] });
    state = fakeState();
    atlasObject = new Atlas(state, {});
    clock = NOW;
    atlasObject.now = () => clock;
  });
  afterEach(() => mock.timers.reset());

  const counts = (...n) => [...n, ...Array(16 - n.length).fill(0)];
  async function report(body) {
    const response = await atlasObject.fetch(new Request('https://atlas/report', { method: 'POST', body: JSON.stringify(body) }));
    return [response.status, await response.json()];
  }
  async function worldMap() {
    return (await atlasObject.fetch(new Request('https://atlas/world'))).json();
  }

  test('adds up what sectors report', async () => {
    assert.deepEqual(await report({ sx: 0, sy: 0, players: 3, charted: counts(5, 2) }), [200, { charted: 7, total: AREA_WORDS, players: 3 }]);
    assert.deepEqual((await report({ sx: -1, sy: 4, players: 2, charted: counts(1) }))[1], { charted: 8, total: AREA_WORDS, players: 5 });
    // Reports are absolute, so a repeat changes nothing.
    assert.deepEqual((await report({ sx: -1, sy: 4, players: 2, charted: counts(1) }))[1], { charted: 8, total: AREA_WORDS, players: 5 });
    assert.deepEqual((await report({ sx: 0, sy: 0, players: 0, charted: counts(6, 2) }))[1], { charted: 9, total: AREA_WORDS, players: 2 });
  });

  test('stops counting players whose sector has gone quiet', async () => {
    await report({ sx: 0, sy: 0, players: 3, charted: counts(1) });
    clock += ONLINE_MS;
    assert.deepEqual((await report({ sx: 1, sy: 0, players: 1, charted: counts() }))[1], { charted: 1, total: AREA_WORDS, players: 1 });
  });

  test('refuses reports it cannot use', async () => {
    for (const bad of [
      { sx: AREA + 1, sy: 0, players: 1, charted: counts() },
      { sx: 0, sy: 0, players: -1, charted: counts() },
      { sx: 0, sy: 0, players: 1, charted: [1, 2] },
      { sx: 0, sy: 0, players: 1, charted: counts(1.5) },
      { sx: '0', sy: 0, players: 1, charted: counts() },
    ]) assert.equal((await report(bad))[0], 400);
    const response = await atlasObject.fetch(new Request('https://atlas/report', { method: 'POST', body: 'nope' }));
    assert.equal(response.status, 400);
  });

  test('writes charted counts to storage once a minute, and reloads them', async () => {
    const rows = () => state.storage.sql.exec('SELECT sx, sy, charted, done FROM sectors').toArray().map((r) => ({ ...r }));
    await report({ sx: 0, sy: 0, players: 3, charted: counts(5) });
    await report({ sx: 0, sy: 0, players: 3, charted: counts(6) });
    await report({ sx: 2, sy: 2, players: 1, charted: counts(0, 1) });
    assert.deepEqual(rows(), []);
    mock.timers.tick(SAVE_MS);
    assert.deepEqual(rows(), [
      { sx: 0, sy: 0, charted: counts(6).join(','), done: 6 },
      { sx: 2, sy: 2, charted: counts(0, 1).join(','), done: 1 },
    ]);
    // After eviction the charted counts come back; players wait for new reports.
    atlasObject = new Atlas(state, {});
    atlasObject.now = () => clock;
    assert.deepEqual((await worldMap()).charted, 7);
    assert.deepEqual((await worldMap()).players, 0);
  });

  test('draws the world map, one byte per territory', async () => {
    await report({ sx: -AREA, sy: -AREA, players: 2, charted: counts(9) });
    await report({ sx: 1, sy: 0, players: SPAWN_MAX, charted: counts(0, 0, 0, 0, 0, 7) });
    const map = await worldMap();
    const size = (2 * AREA + 1) * 4, bytes = Buffer.from(map.territories, 'base64');
    assert.equal(bytes.length, size * size);
    assert.equal(bytes[0], 9);                                         // top-left territory of the world
    assert.equal(bytes[(AREA * 4 + 1) * size + (AREA + 1) * 4 + 1], 7); // second row, second column of sector 1,0
    assert.equal(bytes.reduce((a, b) => a + b, 0), 16);
    assert.deepEqual(map.sectors, [[-AREA, -AREA, 2], [1, 0, SPAWN_MAX]]);
    assert.deepEqual(map.spawn, [-AREA * SECTOR + SECTOR / 2, -AREA * SECTOR + SECTOR / 2]);  // the middle of the crowd with room
    assert.deepEqual([map.charted, map.total, map.players, map.area], [16, AREA_WORDS, 2 + SPAWN_MAX, AREA]);
  });

  test('starts new players in the biggest crowd with room, where the latest word was charted', async () => {
    assert.equal((await worldMap()).spawn, null);  // nobody playing: the origin
    await report({ sx: 3, sy: 3, players: 12, charted: counts(), hot: [3 * SECTOR + 7, 3 * SECTOR + 9] });
    await report({ sx: -2, sy: 5, players: 80, charted: counts(), hot: [-2 * SECTOR + 50, 5 * SECTOR + 60] });
    await report({ sx: 0, sy: 0, players: 30, charted: counts(), hot: [SECTOR * 4, 0] });  // a hot spot outside it is ignored
    clock += VIEW_MS;
    assert.deepEqual((await worldMap()).spawn, [-2 * SECTOR + 50, 5 * SECTOR + 60]);
    // A report without a hot spot keeps the last one.
    await report({ sx: -2, sy: 5, players: 81, charted: counts() });
    clock += VIEW_MS;
    assert.deepEqual((await worldMap()).spawn, [-2 * SECTOR + 50, 5 * SECTOR + 60]);
  });

  test('starts new players beside the biggest crowd when every crowd is full', async () => {
    await report({ sx: 3, sy: 3, players: SPAWN_MAX, charted: counts() });
    await report({ sx: -6, sy: 1, players: SPAWN_MAX + 50, charted: counts() });
    const [x, y] = (await worldMap()).spawn, sx = Math.floor(x / SECTOR), sy = Math.floor(y / SECTOR);
    assert.equal(Math.max(Math.abs(sx + 6), Math.abs(sy - 1)), 1, `${sx},${sy} is not next to -6,1`);
  });

  test('rebuilds the world map at most every few seconds', async () => {
    await report({ sx: 0, sy: 0, players: 1, charted: counts(1) });
    assert.equal((await worldMap()).charted, 1);
    await report({ sx: 0, sy: 0, players: 1, charted: counts(2) });
    assert.equal((await worldMap()).charted, 1);
    clock += VIEW_MS;
    assert.equal((await worldMap()).charted, 2);
  });
});

test('the shared world hides AREA_WORDS words', () => {
  let total = 0;
  for (let cy = -AREA * 16; cy < (AREA + 1) * 16; cy++) for (let cx = -AREA * 16; cx < (AREA + 1) * 16; cx++) total += genChunk(cx, cy).words.length;
  assert.equal(total, AREA_WORDS);
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

  test('serves the world map from the Atlas through a short cache', async () => {
    let asked = 0;
    const atlasEnv = {
      ALLOWED_ORIGINS: ORIGIN,
      ATLAS: { idFromName: () => 'atlas', get: () => ({ fetch: async () => { asked++; return new Response(`{"charted":${asked}}`); } }) },
    };
    const get = () => routeSurvey(new Request('https://survey.test/v1/survey/world', { headers: { Origin: ORIGIN } }), atlasEnv);
    const first = await get();
    assert.deepEqual(await first.json(), { charted: 1 });
    assert.equal(first.headers.get('Access-Control-Allow-Origin'), ORIGIN);
    assert.equal(first.headers.get('Cache-Control'), `public, max-age=${VIEW_MS / 1000}`);
    assert.deepEqual(await (await get()).json(), { charted: 1 });
    assert.equal(asked, 1);
    assert.equal((await routeSurvey(new Request('https://survey.test/v1/survey/world', { method: 'POST' }), atlasEnv)).status, 405);
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
