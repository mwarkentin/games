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
import { CH, DEAL, DIRS, HOLDERS, MAP_VERSION, RG, STRAY_MIN, THEMES, THEME_DATA, VOCAB, chunk, genChunk, keyOf, letterAt, regionName, regionTheme, strayTheme, wordEnd } from '../src/letterfield-world.js';
import {
  ADDRESS_HEADER, ADDRESS_SOCKETS, AREA, AREA_WORDS, Atlas, BATCH_MS, DAILY_CLAIMS, dailyClaims, DAILY_LIST_MAX, CLAIM_BURST, CLAIM_REFILL_MS, MAX_ONLINE, MAX_PLAYERS, ONLINE_MS, PRESENCE_MAX, PRESENCE_MS,
  QUIET, REPORT_MS, UNPASSED_HEADER, SAVE_MS, SAVE_POS_MS, SECTOR, SPAWN_MAX, Sector, VIEW_MS, addressOf, checkClaim, routeSurvey,
} from '../src/survey.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 9, 29, 12);
const DAY = 86400000;
const TODAY = Math.floor(NOW / DAY);  // the UTC day, as the daily cap counts it
const hashed = (n) => n.toString(16).padStart(64, '0');  // a stand-in for a hashed address

// Runs the world code from letterfield.html itself, from its world constants
// up to its formatting helpers, so the copy in src/ can be compared with it.
function gameWorld() {
  const html = readFileSync(new URL('../../letterfield.html', import.meta.url), 'utf8');
  const start = html.indexOf('/* ---------- World constants ---------- */');
  const end = html.indexOf('/* ---------- Formatting ---------- */');
  assert.ok(start > 0 && end > start, 'letterfield.html lost its section markers');
  const context = vm.createContext({ matchMedia: () => ({ matches: false }) });
  return vm.runInContext(`${html.slice(start, end)}; ({ genChunk, letterAt, regionName, regionTheme, strayTheme, SECTOR, SURVEY_AREA, THEME_DATA, THEMES })`, context);
}

// A hidden word in the given chunk, as the game would send it.
function placed(cx, cy, n = 0) {
  const { w, x, y, d } = chunk(cx, cy).words[n];
  return { w, x, y, d };
}

// A word the letters spell by chance, found by reading the map near the origin,
// of `min` to `max` letters.
function findStray(min = STRAY_MIN, max = 12) {
  for (let y = 0; y < 96; y++) {
    for (let x = 0; x < 96; x++) {
      for (let d = 0; d < 8; d++) {
        let s = '';
        for (let i = 0; i < max; i++) {
          s += String.fromCharCode(65 + letterAt(x + DIRS[d][0] * i, y + DIRS[d][1] * i));
          if (s.length >= min && VOCAB.has(s) && !chunk(Math.floor(x / CH), Math.floor(y / CH)).words.some((p) => p.key === keyOf(s, x, y, d))) {
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

  test('has the same themes as the game, and lays them out the same way', () => {
    const game = gameWorld();
    assert.equal(THEME_DATA, game.THEME_DATA);
    // A stray takes its territory's theme when that theme has the word, as in the game.
    for (const [i, t] of THEMES.entries()) {
      for (const w of t.words.slice(0, 3)) for (const [rx, ry] of [[i, 0], [3, -7]]) assert.equal(strayTheme(w, rx, ry), game.strayTheme(w, rx, ry));
    }
    // One chunk in a territory of every theme.
    for (let t = 0; t < THEMES.length; t++) {
      const cx = t * RG + (t % RG), cy = -(t % 3);
      assert.equal(regionTheme(Math.floor(cx / RG), Math.floor(cy / RG)), game.regionTheme(Math.floor(cx / RG), Math.floor(cy / RG)));
      assert.deepEqual(genChunk(cx, cy).words, JSON.parse(JSON.stringify(game.genChunk(cx, cy).words)), `words differ in chunk ${cx},${cy}`);
    }
  });

  test('gives a stray in several themes its territory\'s theme where that has the word', () => {
    const [w] = [...HOLDERS].find(([, n]) => n > 1);
    const [a, b] = THEMES.flatMap((t, i) => (t.words.includes(w) ? [i] : []));
    const other = THEMES.findIndex((t) => !t.words.includes(w));
    // Theme t is the one at (t, 0): regionTheme is (rx + LAT_B ry) mod NT.
    for (const t of [a, b, other]) assert.equal(regionTheme(t, 0), t);
    assert.equal(strayTheme(w, a, 0), a);
    assert.equal(strayTheme(w, b, 0), b);
    // Anywhere else, the first theme that has it.
    assert.equal(VOCAB.get(w), a);
    assert.equal(strayTheme(w, other, 0), a);
    const game = gameWorld();
    for (const t of [a, b, other]) assert.equal(game.strayTheme(w, t, 0), strayTheme(w, t, 0));
  });

  test('names territories as the game does, for the survey\'s log', () => {
    const game = gameWorld();
    for (let ry = -AREA * 4; ry < (AREA + 1) * 4; ry += 3) {
      for (let rx = -AREA * 4; rx < (AREA + 1) * 4; rx++) assert.equal(regionName(rx, ry), game.regionName(rx, ry), `${rx},${ry}`);
    }
    for (const [rx, ry] of [[1e5, -3e4], [-98765, 4321]]) assert.equal(regionName(rx, ry), game.regionName(rx, ry));
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

  test('accepts a stray word of STRAY_MIN letters or more, and no shorter', () => {
    const stray = findStray();
    assert.ok(stray, 'no stray word near the origin');
    assert.equal(checkClaim(stray, 0, 0).s, 1);
    const short = findStray(3, STRAY_MIN - 1);
    assert.ok(short, 'no short stray near the origin');
    assert.deepEqual(checkClaim(short, 0, 0), { error: 'word is not there' });
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

  test('tells the share Worker who charted a word, and nothing for one nobody has', async () => {
    const ws = join();
    await say(ws, { t: 'me', initials: 'ZED' });
    const word = placed(0, 0);
    const ask = (w) => sector.fetch(new Request(`https://sector/claim/${encodeURIComponent(keyOf(w.w, w.x, w.y, w.d))}`));
    assert.equal((await ask(word)).status, 404);
    await claim(ws, word);
    const answer = await ask(word);
    assert.equal(answer.status, 200);
    assert.deepEqual(await answer.json(), { initials: 'ZED', at: NOW });
    // It's only for GETs, and a socket's path still needs an upgrade.
    assert.equal((await sector.fetch(new Request(`https://sector/claim/x`, { method: 'POST' }))).status, 404);
    assert.equal((await sector.fetch(new Request('https://sector/v1/survey/0/0'))).status, 426);
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

  test('claims owed to a batch go out even if the sector goes quiet, however busy it was', async () => {
    const players = Array.from({ length: QUIET }, () => join());
    const [a, b] = players;
    const ws0 = chunk(0, 0).words;
    await claim(a, ws0[0]);  // the first goes at once
    clock += 50;
    await claim(b, ws0[1]);  // owed to the next batch
    // Then nothing comes in to carry it. Its own short timer does, before the
    // sector could hibernate and forget it.
    clock += BATCH_MS;
    mock.timers.tick(BATCH_MS);
    for (const ws of players) assert.equal(ws.sent.filter((m) => m.t === 'claimed').length, 2);
    assert.equal(b.last('claimed').by, b.deserializeAttachment().id, 'so its claimer hears it was first');
  });

  test('a busy sector sets no timers for positions, so it can hibernate between messages', async () => {
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

  // A stand-in for a rate-limiting binding: `max` calls per address, then no.
  function fakeLimiter(max) {
    const counts = new Map();
    return {
      counts,
      limit: async ({ key }) => { counts.set(key, (counts.get(key) ?? 0) + 1); return { success: counts.get(key) <= max }; },
    };
  }

  // Opens a socket the way the Worker does, from a hashed address; returns the server's end.
  async function openFrom(address) {
    let pair;
    globalThis.WebSocketPair = function WebSocketPair() { pair = [fakeSocket(), fakeSocket()]; return { 0: pair[0], 1: pair[1] }; };
    const RealResponse = Response;
    globalThis.Response = class { constructor(body, init) { Object.assign(this, init); } };
    try {
      await sector.fetch(new Request('https://survey.test/v1/survey/0/0', { headers: { Upgrade: 'websocket', [ADDRESS_HEADER]: address } }));
    } finally {
      globalThis.Response = RealResponse;
      delete globalThis.WebSocketPair;
    }
    return pair[1];
  }

  test('takes only so many sockets from one address', async () => {
    const mine = [];
    for (let i = 0; i < ADDRESS_SOCKETS; i++) mine.push(await openFrom('aaaa'));
    assert.ok(mine.every((ws) => ws.sent[0].t === 'hello'));
    const extra = await openFrom('aaaa');
    assert.deepEqual(extra.sent, [{ t: 'full', world: false }]);
    assert.equal(extra.code, 4000);
    assert.equal((await openFrom('bbbb')).sent[0].t, 'hello');  // someone else still gets in

    // When one leaves, the address has room again, including after the sector wakes.
    mine[0].open = false;
    await sector.webSocketClose(mine[0]);
    sector = new Sector(state, {});
    sector.now = () => clock;
    assert.equal((await openFrom('aaaa')).sent[0].t, 'hello');
    assert.equal((await openFrom('aaaa')).sent[0].t, 'full');
  });

  test('turns an address away when it opens sockets too fast, and lets everyone in if the limiter fails', async () => {
    const joins = fakeLimiter(2);
    sector = new Sector(state, { SURVEY_JOINS: joins });
    assert.equal((await openFrom('aaaa')).sent[0].t, 'hello');
    assert.equal((await openFrom('aaaa')).sent[0].t, 'hello');
    assert.deepEqual((await openFrom('aaaa')).sent, [{ t: 'full', world: false }]);
    assert.equal((await openFrom('bbbb')).sent[0].t, 'hello');
    assert.deepEqual([...joins.counts], [['aaaa', 3], ['bbbb', 1]]);

    sector = new Sector(state, { SURVEY_JOINS: { limit: async () => { throw new Error('limiter down'); } } });
    assert.equal((await openFrom('aaaa')).sent[0].t, 'hello');
  });

  test('counts sockets again once the limiter answers, so joins arriving together still stop at the cap', async () => {
    // A limiter that says yes after a moment, as a call out of the object does:
    // other joins come in while it answers.
    sector = new Sector(state, { SURVEY_JOINS: { limit: () => new Promise((resolve) => setImmediate(() => resolve({ success: true }))) } });
    const servers = [];
    globalThis.WebSocketPair = function WebSocketPair() { const pair = [fakeSocket(), fakeSocket()]; servers.push(pair[1]); return { 0: pair[0], 1: pair[1] }; };
    const RealResponse = Response;
    globalThis.Response = class { constructor(body, init) { Object.assign(this, init); } };
    try {
      await Promise.all(Array.from({ length: ADDRESS_SOCKETS + 10 }, () => sector.fetch(
        new Request('https://survey.test/v1/survey/0/0', { headers: { Upgrade: 'websocket', [ADDRESS_HEADER]: 'aaaa' } }),
      )));
    } finally {
      globalThis.Response = RealResponse;
      delete globalThis.WebSocketPair;
    }
    assert.equal(servers.filter((ws) => ws.sent[0]?.t === 'hello').length, ADDRESS_SOCKETS);
    assert.equal(servers.filter((ws) => ws.sent[0]?.t === 'full').length, 10);
  });

  test('limits how fast one address can claim, across every sector', async () => {
    const claims = fakeLimiter(3);
    const env = { SURVEY_CLAIMS: claims };
    sector = new Sector(state, env);
    sector.now = () => clock;
    const here = await openFrom('aaaa');
    const otherState = fakeState();
    const there = new Sector(otherState, env);
    there.now = () => clock;
    const far = fakeSocket();
    there.join(far, 1, 0, 'aaaa');
    const neighbour = await openFrom('bbbb');

    // Each socket is well inside its own limit; together they pass the address's.
    const words = chunk(0, 0).words, farWords = chunk(Math.floor(SECTOR / CH), 0).words;
    await claim(here, words[0]);
    await claim(here, words[1]);
    await there.webSocketMessage(far, JSON.stringify({ t: 'claim', ...farWords[0] }));
    await there.webSocketMessage(far, JSON.stringify({ t: 'claim', ...farWords[1] }));
    await claim(here, words[2]);
    mock.timers.tick(BATCH_MS);
    assert.equal(here.sent.filter((m) => m.t === 'claimed').length, 2);
    assert.equal(far.sent.filter((m) => m.t === 'claimed').length, 1);
    assert.deepEqual(far.last('error'), { t: 'error', key: keyOf(farWords[1].w, farWords[1].x, farWords[1].y, farWords[1].d), error: 'slow down' });
    assert.equal(here.last('error').error, 'slow down');
    // The word is still there for whoever claims it next.
    await claim(neighbour, words[2]);
    mock.timers.tick(BATCH_MS);
    assert.equal(neighbour.last('claimed').c[0], words[2].w);
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
    assert.deepEqual(reports, [{ sx: 2, sy: -3, players: 0, charted: countsFor(1), hot: [words[0].x, words[0].y], by: [], day: TODAY, overAt: 0 }]);
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
    assert.deepEqual(reports[1], { sx: 2, sy: -3, players: 1, charted: countsFor(2), hot: [401, -500], by: [], day: TODAY, overAt: 0 });  // where the player is
    assert.deepEqual(b.last('world'), { t: 'world', charted: 1002, total: AREA_WORDS, players: 40 });
    // Later joiners get the totals straight away.
    assert.deepEqual(join(2, -3).sent[1], { t: 'world', charted: 1002, total: AREA_WORDS, players: 40 });
  });

  test('reports the middle of the crowd, not the stragglers', async () => {
    const reports = [];
    reportingSector(reports);
    const crowd = [[400, -540], [402, -541], [405, -538], [401, -539], [560, -400]];  // four together, one far off
    let last;
    for (const [x, y] of crowd) { last = join(2, -3); clock += 1; await say(last, { t: 'pos', x, y }); }
    await settle();  // the first report, sent with the first move
    clock += REPORT_MS;
    await say(last, { t: 'pos', x: 560.5, y: -400 });
    await settle();
    assert.deepEqual(reports.at(-1).hot, [402, -539]);
  });

  test('reports its last change when its players leave', async () => {
    const reports = [];
    reportingSector(reports);
    const players = Array.from({ length: QUIET }, () => join(2, -3));  // busy: no timer to report with
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

  test('counts words charted per address in its reports, and keeps them if a report fails', async () => {
    const reports = [];
    let fail = true;
    sector = new Sector(state, {
      ATLAS: {
        idFromName: (name) => name,
        get: () => ({
          fetch: async (url, init) => {
            if (fail) throw new Error('atlas evicted');
            reports.push(JSON.parse(init.body));
            return Response.json({ charted: 1, total: AREA_WORDS, players: 1, day: TODAY, overAt: 0 });
          },
        }),
      },
    });
    sector.now = () => clock;
    const [a, b] = [fakeSocket(), fakeSocket()];
    sector.join(a, 2, -3, hashed(1));
    sector.join(b, 2, -3, hashed(2));
    await claim(a, words[0]);
    await settle();
    assert.equal(reports.length, 0);  // that report failed
    fail = false;
    clock += REPORT_MS;
    await claim(a, words[1]);
    await claim(b, words[2]);
    await claim(b, words[2]);  // taken: charted only once
    await settle();
    assert.deepEqual(reports.at(-1).by, [[hashed(1), 2]]);  // the failed report's word, and the new one
    clock += REPORT_MS;
    await say(a, { t: 'pos', x: 400, y: -500 });
    await settle();
    assert.deepEqual(reports.at(-1).by, [[hashed(2), 1]]);
  });

  test('counts joins without a Turnstile pass in its reports, and keeps the count if a report fails', async () => {
    const reports = [];
    let fail = true;
    sector = new Sector(state, {
      ATLAS: {
        idFromName: (name) => name,
        get: () => ({
          fetch: async (url, init) => {
            if (fail) throw new Error('atlas evicted');
            reports.push(JSON.parse(init.body));
            return Response.json({ charted: 1, total: AREA_WORDS, players: 1, day: TODAY, overAt: 0 });
          },
        }),
      },
    });
    sector.now = () => clock;
    // Opens a socket as the Worker forwards it, with or without the Worker's mark.
    async function open(unpassed) {
      let pair;
      globalThis.WebSocketPair = function WebSocketPair() { pair = [fakeSocket(), fakeSocket()]; return { 0: pair[0], 1: pair[1] }; };
      const RealResponse = Response;
      globalThis.Response = class { constructor(body, init) { Object.assign(this, init); } };
      try {
        const headers = { Upgrade: 'websocket', [ADDRESS_HEADER]: hashed(unpassed ? 1 : 2), ...(unpassed ? { [UNPASSED_HEADER]: '1' } : {}) };
        await sector.fetch(new Request('https://survey.test/v1/survey/2/-3', { headers }));
      } finally {
        globalThis.Response = RealResponse;
        delete globalThis.WebSocketPair;
      }
      return pair[1];
    }
    const bot = await open(true);
    await open(true);
    const player = await open(false);
    assert.equal(bot.sent[0].t, 'hello');  // counted, not refused
    await say(player, { t: 'pos', x: 400, y: -500 });
    await settle();
    assert.equal(reports.length, 0);  // that report failed
    fail = false;
    clock += REPORT_MS;
    await say(player, { t: 'pos', x: 410, y: -500 });
    await settle();
    assert.equal(reports.at(-1).unpassed, 2);
    // Nothing new: the report leaves it out.
    await claim(player, words[0]);
    clock += REPORT_MS;
    await say(player, { t: 'pos', x: 420, y: -500 });
    await settle();
    assert.equal(reports.length, 2);
    assert.equal('unpassed' in reports.at(-1), false);
  });

  test('refuses claims from addresses past the daily cap, once the Atlas says so', async () => {
    const atlasObject = new Atlas(fakeState(), {});
    atlasObject.now = () => clock;
    const env = { ATLAS: { idFromName: (name) => name, get: () => ({ fetch: (url, init) => atlasObject.fetch(new Request(url, init)) }) } };
    const busy = hashed(1), other = hashed(2);
    atlasObject.countCharted([[busy, DAILY_CLAIMS - 1]]);

    // Sector 2,-3 credits the address's last word for today, reports it, and hears it's over.
    sector = new Sector(state, env);
    sector.now = () => clock;
    const [mine, theirs] = [fakeSocket(), fakeSocket()];
    sector.join(mine, 2, -3, busy);
    sector.join(theirs, 2, -3, other);
    await claim(mine, words[0]);
    await settle();
    assert.equal(mine.sent.filter((m) => m.t === 'claimed').length, 1);
    await claim(mine, words[1]);
    assert.deepEqual(mine.last('error'), { t: 'error', key: keyOf(words[1].w, words[1].x, words[1].y, words[1].d), error: 'daily limit' });
    await claim(theirs, words[1]);
    mock.timers.tick(BATCH_MS);
    assert.equal(theirs.last('claimed').c[0], words[1].w);  // everyone else carries on

    // Sector 0,0 learns the list with its own next report, so the address gets no further there.
    const elsewhere = new Sector(fakeState(), env);
    elsewhere.now = () => clock;
    const [mineThere, theirsThere] = [fakeSocket(), fakeSocket()];
    elsewhere.join(mineThere, 0, 0, busy);
    elsewhere.join(theirsThere, 0, 0, other);
    await elsewhere.webSocketMessage(theirsThere, JSON.stringify({ t: 'claim', ...placed(0, 0) }));
    await settle();
    await elsewhere.webSocketMessage(mineThere, JSON.stringify({ t: 'claim', ...placed(0, 0, 1) }));
    assert.equal(mineThere.last('error').error, 'daily limit');

    // A new day, a new count.
    clock += DAY;
    await claim(mine, words[2]);
    mock.timers.tick(BATCH_MS);
    assert.equal(mine.last('claimed').c[0], words[2].w);
  });

  test('takes a daily cap of its own from SURVEY_DAILY_CLAIMS, as Worker Previews do', () => {
    assert.equal(dailyClaims({}), DAILY_CLAIMS);
    assert.equal(dailyClaims({ SURVEY_DAILY_CLAIMS: '1000' }), 1000);
    for (const bad of ['', 'lots', '0', '-5', '2.5', '1e9']) assert.equal(dailyClaims({ SURVEY_DAILY_CLAIMS: bad }), DAILY_CLAIMS, bad);
    const atlasObject = new Atlas(fakeState(), { SURVEY_DAILY_CLAIMS: '1000' });
    atlasObject.now = () => clock;
    atlasObject.countCharted([[hashed(1), DAILY_CLAIMS]]);
    assert.equal(atlasObject.overList.length, 0);
    atlasObject.countCharted([[hashed(1), 1000 - DAILY_CLAIMS]]);
    assert.deepEqual(atlasObject.overList, [hashed(1)]);
  });

  // An Atlas that already counts hashed(1) past today's cap. `held` keeps its
  // answers back until `answer()`.
  function cappedAtlas({ held = null } = {}) {
    const atlasObject = new Atlas(fakeState(), {});
    atlasObject.now = () => clock;
    atlasObject.countCharted([[hashed(1), DAILY_CLAIMS]]);
    return { ATLAS: { idFromName: (name) => name, get: () => ({ fetch: async (url, init) => { await held; return atlasObject.fetch(new Request(url, init)); } }) } };
  }

  test("refuses an address past the cap even straight after waking, when it hasn't heard from the Atlas yet", async () => {
    const env = cappedAtlas();
    sector = new Sector(state, env);
    sector.now = () => clock;
    const mine = fakeSocket();
    sector.join(mine, 2, -3, hashed(1));
    await claim(mine, words[0]);
    assert.equal(mine.last('error')?.error, 'daily limit', 'not even its first claim here');
    // The sector hibernates, with the socket still open. Woken, it asks again.
    clock += 30000;
    sector = new Sector(state, env);
    sector.now = () => clock;
    await claim(mine, words[1]);
    mock.timers.tick(BATCH_MS);
    assert.equal(mine.sent.filter((m) => m.t === 'claimed').length, 0);
    assert.equal(mine.sent.filter((m) => m.error === 'daily limit').length, 2);
  });

  test('claims sent together while the sector asks the Atlas all wait for its answer', async () => {
    let answer;
    const env = cappedAtlas({ held: new Promise((resolve) => { answer = resolve; }) });
    sector = new Sector(state, env);
    sector.now = () => clock;
    const ws = fakeSocket();
    sector.join(ws, 2, -3, hashed(1));
    const sent = Promise.all(words.slice(0, CLAIM_BURST).map((w) => claim(ws, w)));
    await settle();
    answer();
    await sent;
    mock.timers.tick(BATCH_MS);
    assert.equal(ws.sent.filter((m) => m.t === 'claimed').length, 0);
    assert.equal(ws.sent.filter((m) => m.error === 'daily limit').length, CLAIM_BURST);
  });

  test("charts as before when the Atlas can't be reached to ask", async () => {
    sector = new Sector(state, { ATLAS: { idFromName: (name) => name, get: () => ({ fetch: async () => { throw new Error('atlas down'); } }) } });
    sector.now = () => clock;
    const ws = fakeSocket();
    sector.join(ws, 2, -3, hashed(1));
    await claim(ws, words[0]);
    assert.equal(ws.last('claimed').c[0], words[0].w);
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
  let state, atlasObject, clock, logged;
  beforeEach(() => {
    logged = mock.method(console, 'log', () => {});
    mock.timers.enable({ apis: ['setTimeout'] });
    state = fakeState();
    atlasObject = new Atlas(state, {});
    clock = NOW;
    atlasObject.now = () => clock;
  });
  afterEach(() => { mock.timers.reset(); logged.mock.restore(); });

  const counts = (...n) => [...n, ...Array(16 - n.length).fill(0)];
  const logs = (kind) => logged.mock.calls.map((c) => c.arguments[0]).filter((l) => l?.survey === kind);
  // A report, and the Atlas's answer: by default only the world's totals.
  async function report(body, { all = false } = {}) {
    const response = await atlasObject.fetch(new Request('https://atlas/report', { method: 'POST', body: JSON.stringify(body) }));
    const answer = await response.json();
    if (all || response.status !== 200) return [response.status, answer];
    const { charted, total, players } = answer;
    return [response.status, { charted, total, players }];
  }
  async function worldMap() {
    return (await atlasObject.fetch(new Request('https://atlas/world'))).json();
  }

  test('gives the share Worker the world\'s totals', async () => {
    await report({ sx: 0, sy: 0, players: 3, charted: counts(5, 2) });
    const answer = await atlasObject.fetch(new Request('https://atlas/totals'));
    assert.deepEqual(await answer.json(), { charted: 7, total: AREA_WORDS, players: 3 });
  });

  test('adds up joins without a pass for the UTC day, and keeps yesterday\'s', async () => {
    await report({ sx: 0, sy: 0, players: 3, charted: counts(5), unpassed: 3 });
    await report({ sx: 1, sy: 0, players: 1, charted: counts(1), unpassed: 2 });
    await report({ sx: 1, sy: 0, players: 1, charted: counts(1) });  // older sectors send none
    let map = await worldMap();
    assert.equal(map.today.day, TODAY);
    assert.equal(map.today.unpassed, 5);
    clock += DAY;
    await report({ sx: 0, sy: 0, players: 3, charted: counts(5), unpassed: 1 });
    map = await worldMap();
    assert.deepEqual([map.today.day, map.today.unpassed], [TODAY + 1, 1]);
    assert.deepEqual([map.yesterday.day, map.yesterday.unpassed], [TODAY, 5]);
    for (const unpassed of [-1, 1.5, '2', 1e7]) assert.equal((await report({ sx: 0, sy: 0, players: 0, charted: counts(), unpassed }))[0], 400);
  });

  test('adds up what sectors report', async () => {
    assert.deepEqual(await report({ sx: 0, sy: 0, players: 3, charted: counts(5, 2) }), [200, { charted: 7, total: AREA_WORDS, players: 3 }]);
    assert.deepEqual((await report({ sx: -1, sy: 4, players: 2, charted: counts(1) }))[1], { charted: 8, total: AREA_WORDS, players: 5 });
    // Reports are absolute, so a repeat changes nothing.
    assert.deepEqual((await report({ sx: -1, sy: 4, players: 2, charted: counts(1) }))[1], { charted: 8, total: AREA_WORDS, players: 5 });
    assert.deepEqual((await report({ sx: 0, sy: 0, players: 0, charted: counts(6, 2) }))[1], { charted: 9, total: AREA_WORDS, players: 2 });
  });

  test('counts what each address charts today, and lists those past the daily cap', async () => {
    const base = { players: 1, charted: counts(), day: TODAY, overAt: 0 };
    const [, first] = await report({ ...base, sx: 0, sy: 0, by: [[hashed(1), DAILY_CLAIMS - 100]] }, { all: true });
    assert.deepEqual([first.day, first.overAt, first.over], [TODAY, 0, undefined]);  // nothing new for this sector
    // Counts add up across sectors.
    const [, second] = await report({ ...base, sx: 1, sy: 0, by: [[hashed(1), 100], [hashed(2), 5]] }, { all: true });
    assert.deepEqual([second.overAt, second.over], [1, [hashed(1)]]);
    assert.equal((await report({ ...base, sx: 1, sy: 0, overAt: 1 }, { all: true }))[1].over, undefined);  // already heard
    assert.deepEqual((await report({ ...base, sx: 2, sy: 0 }, { all: true }))[1].over, [hashed(1)]);  // hasn't yet
    // Going further past the cap doesn't list an address twice.
    assert.equal((await report({ ...base, sx: 0, sy: 0, by: [[hashed(1), 3]] }, { all: true }))[1].overAt, 1);

    clock += DAY;
    const [, tomorrow] = await report({ ...base, sx: 0, sy: 0, day: TODAY, overAt: 1, by: [[hashed(2), 1]] }, { all: true });
    assert.deepEqual([tomorrow.day, tomorrow.overAt, tomorrow.over], [TODAY + 1, 0, []]);
  });

  test('hands out only the latest addresses past the cap', async () => {
    const many = Array.from({ length: DAILY_LIST_MAX + 5 }, (_, i) => [hashed(i + 1), DAILY_CLAIMS]);
    atlasObject.countCharted(many);
    const [, answer] = await report({ sx: 0, sy: 0, players: 0, charted: counts() }, { all: true });
    assert.equal(answer.overAt, DAILY_LIST_MAX + 5);
    assert.deepEqual(answer.over, many.slice(5).map(([a]) => a));
  });

  test('keeps the day\'s numbers for the world map, and yesterday\'s', async () => {
    const base = { charted: counts(), day: TODAY, overAt: 0 };
    await report({ ...base, sx: 0, sy: 0, players: 3, by: [[hashed(1), 40], [hashed(2), 2]] });
    clock += 60000;  // 3 players for a minute
    await report({ ...base, sx: 1, sy: 0, players: 1, by: [[hashed(1), DAILY_CLAIMS - 40]] });
    clock += 30 * 60000;  // both sectors went quiet, so their players stopped counting as online
    await report({ ...base, sx: 1, sy: 0, players: 0 });
    let map = await worldMap();
    assert.deepEqual(map.today, { day: TODAY, charted: DAILY_CLAIMS + 2, addresses: 2, capped: 1, playerHours: 0.05, unpassed: 0 });
    assert.equal(map.yesterday, null);

    clock += DAY;
    await report({ ...base, sx: 0, sy: 0, players: 0 });
    clock += VIEW_MS;
    map = await worldMap();
    assert.equal(map.yesterday.charted, DAILY_CLAIMS + 2);
    assert.equal(map.yesterday.capped, 1);
    assert.deepEqual({ ...map.today, playerHours: 0 }, { day: TODAY + 1, charted: 0, addresses: 0, capped: 0, playerHours: 0, unpassed: 0 });

    // A day with nothing to hear about is a day of zeros, not a repeat of the last busy one.
    clock += 2 * DAY;
    await report({ ...base, sx: 0, sy: 0, players: 0 });
    clock += VIEW_MS;
    assert.deepEqual((await worldMap()).yesterday, { day: TODAY + 2, charted: 0, addresses: 0, capped: 0, playerHours: 0, unpassed: 0 });
  });

  test('logs each hour\'s numbers, and each address reaching the cap, never the address', async () => {
    clock = Math.floor(NOW / 3600000) * 3600000;  // on the hour
    const base = { charted: counts(), day: TODAY, overAt: 0 };
    await report({ ...base, sx: 0, sy: 0, players: 2, by: [[hashed(7), DAILY_CLAIMS]] });
    assert.deepEqual(logs('daily cap'), [{ survey: 'daily cap', capped: 1 }]);
    assert.ok(!JSON.stringify(logged.mock.calls.map((c) => c.arguments)).includes(hashed(7)));
    clock += 60000;
    await report({ ...base, sx: 0, sy: 0, players: 2, by: [[hashed(8), 10]] });
    assert.equal(logs('hour').length, 0);
    clock += 3600000;
    await report({ ...base, sx: 0, sy: 0, players: 2 });
    const [hour] = logs('hour');
    assert.equal(hour.hour, new Date(clock - 3600000 - 60000).toISOString());
    // 310 words in 2 players' minute: a rate no person reaches.
    assert.deepEqual({ ...hour, today: undefined }, {
      survey: 'hour', hour: hour.hour, charted: DAILY_CLAIMS + 10, playerHours: 0.03, perPlayerHour: 9300, today: undefined,
    });
    assert.equal(hour.today.capped, 1);
  });

  test('stops counting players whose sector has gone quiet', async () => {
    await report({ sx: 0, sy: 0, players: 3, charted: counts(1) });
    clock += ONLINE_MS;
    assert.deepEqual((await report({ sx: 1, sy: 0, players: 1, charted: counts() }))[1], { charted: 1, total: AREA_WORDS, players: 1 });
  });

  test('refuses words charted by addresses it cannot read', async () => {
    const base = { sx: 0, sy: 0, players: 0, charted: counts() };
    for (const by of ['nope', [['not a hash', 1]], [[hashed(1), 0]], [[hashed(1), 1.5]], [[hashed(0xabc).toUpperCase(), 1]]]) {
      assert.equal((await report({ ...base, by }))[0], 400, JSON.stringify(by));
    }
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

  test('starts new players in the middle of the biggest crowd with room', async () => {
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

describe('the map', () => {
  test('has well-formed themes: enough words to deal a territory, A to Z, 3 to 10 letters, at least half their own', () => {
    const holders = new Map();
    for (const t of THEMES) {
      assert.ok(t.words.length >= RG * RG * DEAL, `${t.name} has ${t.words.length} words`);
      assert.ok(Number.isInteger(t.hue) && t.hue >= 0 && t.hue < 360, `${t.name} hue`);
      assert.equal(new Set(t.words).size, t.words.length, `${t.name} has a word twice`);
      for (const w of t.words) {
        assert.match(w, /^[A-Z]{3,10}$/, `${t.name}: ${w}`);
        holders.set(w, [...(holders.get(w) ?? []), t.name]);
      }
    }
    // A word can be in up to three themes where it belongs in each, but at least
    // half of every theme is its own.
    for (const [w, names] of holders) assert.ok(names.length <= 3, `${w} is in ${names.join(', ')}`);
    for (const t of THEMES) {
      const shared = t.words.filter((w) => holders.get(w).length > 1).length;
      assert.ok(shared <= t.words.length / 2, `${t.name} shares ${shared} of its ${t.words.length} words`);
    }
    assert.equal(new Set(THEMES.map((t) => t.name)).size, THEMES.length);
  });

  // NT themes can keep a theme at most floor(sqrt(NT)) territories from its next
  // appearance (each needs that square to itself), and the layout does.
  const SPACING = Math.floor(Math.sqrt(THEMES.length));
  test(`never repeats a theme within ${SPACING - 1} territories, and neighbours differ in colour and share no words`, () => {
    const circ = (a) => Math.min(((a % 360) + 360) % 360, 360 - (((a % 360) + 360) % 360));
    const sets = THEMES.map((t) => new Set(t.words));
    const share = (a, b) => THEMES[a].words.some((w) => sets[b].has(w));
    for (let ry = -20; ry < 20; ry++) {
      for (let rx = -20; rx < 20; rx++) {
        const t = regionTheme(rx, ry);
        for (let dy = 1 - SPACING; dy < SPACING; dy++) {
          for (let dx = 1 - SPACING; dx < SPACING; dx++) {
            if (!dx && !dy) continue;
            const u = regionTheme(rx + dx, ry + dy);
            assert.notEqual(u, t, `${rx},${ry} and ${rx + dx},${ry + dy}`);
            if (Math.abs(dx) <= 1 && Math.abs(dy) <= 1) {
              assert.ok(circ(THEMES[t].hue - THEMES[u].hue) >= 30, `hues at ${rx},${ry}`);
              assert.ok(!share(t, u), `${THEMES[t].name} and ${THEMES[u].name} share a word, side by side at ${rx},${ry}`);
            }
          }
        }
      }
    }
  });

  test('never repeats a word within a territory of the shared world', () => {
    for (let ry = -AREA * RG; ry < (AREA + 1) * RG; ry++) {
      for (let rx = -AREA * RG; rx < (AREA + 1) * RG; rx++) {
        const seen = new Set();
        for (let cy = ry * RG; cy < ry * RG + RG; cy++) {
          for (let cx = rx * RG; cx < rx * RG + RG; cx++) {
            for (const { w } of chunk(cx, cy).words) {
              assert.ok(!seen.has(w), `${w} twice in territory ${rx},${ry}`);
              seen.add(w);
            }
          }
        }
      }
    }
  });

  test('names every territory in the shared world, with repeats at least 60 apart', () => {
    const { regionName } = gameWorld();
    const where = new Map();
    for (let ry = -AREA * 4; ry < (AREA + 1) * 4; ry++) {
      for (let rx = -AREA * 4; rx < (AREA + 1) * 4; rx++) {
        const name = regionName(rx, ry);
        assert.match(name, /^[A-Z][a-z]{3,9} [A-Z][a-z]+$/);
        for (const [x, y] of where.get(name) ?? []) assert.ok(Math.max(Math.abs(x - rx), Math.abs(y - ry)) >= 60, `${name} at ${x},${y} and ${rx},${ry}`);
        where.set(name, [...(where.get(name) ?? []), [rx, ry]]);
      }
    }
    assert.ok(where.size > 0.99 * (2 * AREA + 1) ** 2 * 16);
  });
});

describe('a new map', () => {
  const count = (sql, table) => sql.exec(`SELECT COUNT(*) AS n FROM ${table}`).one().n;

  test('clears a sector\'s claims and log mark from an older map, once', () => {
    const state = fakeState(), sql = state.storage.sql;
    // A sector from map 2, before maps had versions: a claim, logged.
    new Sector(state, {});
    sql.exec('DROP TABLE map');
    sql.exec("INSERT INTO claims (key, w, x, y, d, s, initials, at) VALUES ('ACORN~1~2~0', 'ACORN', 1, 2, 0, 0, 'ZED', 5)");
    sql.exec('INSERT INTO logged VALUES (0, 5)');
    new Sector(state, {});
    assert.equal(count(sql, 'claims'), 0);
    assert.equal(count(sql, 'logged'), 0);
    assert.equal(sql.exec('SELECT version FROM map').one().version, MAP_VERSION);
    // Claims on this map stay when it wakes again.
    sql.exec("INSERT INTO claims (key, w, x, y, d, s, initials, at) VALUES ('BARK~1~2~0', 'BARK', 1, 2, 0, 0, 'ZED', 6)");
    new Sector(state, {});
    assert.equal(count(sql, 'claims'), 1);
  });

  test('clears the Atlas\'s counts from an older map', () => {
    const state = fakeState(), sql = state.storage.sql;
    new Atlas(state, {});
    sql.exec("INSERT INTO sectors VALUES (0, 0, '1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0', 1)");
    sql.exec('UPDATE map SET version = ?', MAP_VERSION - 1);
    const atlasObject = new Atlas(state, {});
    assert.equal(count(sql, 'sectors'), 0);
    assert.equal(atlasObject.totals().charted, 0);
    sql.exec("INSERT INTO sectors VALUES (0, 0, '1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0', 1)");
    assert.equal(new Atlas(state, {}).totals().charted, 1);
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
      get: (id) => ({ fetch: async (request) => { forwarded.push([id.name, request.url, request.headers]); return new Response('ok'); } }),
    },
  };
  const open = (path, { origin = ORIGIN, upgrade = 'websocket', method = 'GET', headers = {} } = {}) => {
    if (origin) headers.Origin = origin;
    if (upgrade) headers.Upgrade = upgrade;
    return routeSurvey(new Request(`https://survey.test${path}`, { method, headers }), env);
  };

  test('never forwards the internal claim path, which only the share Worker uses', async () => {
    forwarded.length = 0;
    assert.equal(await open('/claim/CORAL~0~0~0'), null);
    assert.equal(await open('/v1/survey/claim/CORAL'), null);
    assert.equal(forwarded.length, 0);
  });

  test('sends each sector to its own Durable Object', async () => {
    assert.equal(await (await open('/v1/survey/0/0')).text(), 'ok');
    await open('/v1/survey/-3/12');
    await open('/v1/survey/-0/007');
    assert.deepEqual(forwarded.map(([name]) => name), ['0,0', '-3,12', '0,7']);
  });

  test('tells the sector who is connecting by a salted hash of their address, never the address', async () => {
    const addressFor = async (ip, extra = {}) => {
      await open('/v1/survey/0/0', { headers: { 'CF-Connecting-IP': ip, ...extra } });
      return forwarded.at(-1)[2].get(ADDRESS_HEADER);
    };
    const a = await addressFor('203.0.113.7');
    assert.match(a, /^[0-9a-f]{64}$/);
    assert.equal(await addressFor('203.0.113.7', { [ADDRESS_HEADER]: 'chosen-by-me' }), a);
    assert.notEqual(await addressFor('203.0.113.8'), a);
    // Everything in one IPv6 /64 is one address.
    const v6 = await addressFor('2001:db8:aa:bb:1:2:3:4');
    assert.equal(await addressFor('2001:db8:aa:bb::9'), v6);
    assert.notEqual(await addressFor('2001:db8:aa:bc::9'), v6);
    env.IP_SALT = 'pepper';
    try { assert.notEqual(await addressFor('203.0.113.7'), a); } finally { delete env.IP_SALT; }
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

test('addressOf keeps IPv4 addresses whole and IPv6 ones to their /64', () => {
  assert.equal(addressOf('198.51.100.20'), '198.51.100.20');
  assert.equal(addressOf('2001:DB8:0:1:aaaa:bbbb:cccc:dddd'), '2001:db8:0:1::/64');
  assert.equal(addressOf('2001:db8::1'), '2001:db8:0:0::/64');
  assert.equal(addressOf('::1'), '0:0:0:0::/64');
  assert.equal(addressOf('2001:db8:0:1::'), '2001:db8:0:1::/64');
  assert.equal(addressOf('nonsense:zz'), 'nonsense:zz');
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
