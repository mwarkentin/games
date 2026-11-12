// Tests for Letterfield's surveyor list and emotes (src/survey-social.js),
// through the Sector and Atlas that use it. Run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"

import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

import worker from '../src/index.js';
import { corsHeaders, json } from '../src/leaderboard.js';
import { AREA, AREA_WORDS, Atlas, MAX_PLAYERS, ONLINE_MS, REPORT_MS, SECTOR, Sector, routeSurvey } from '../src/survey.js';
import {
  EMOTE_BURST, EMOTE_REFILL_MS, EMOTES, FLAG_QUIET, INBOX_MAX, LIST_MS, LIST_PAGE, LIST_PAGES, PAIR_MAX, PAIR_MS, REFRESH_MS,
  nearest, playerId, routeSurveyors,
} from '../src/survey-social.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 10, 12, 12);
const token = (n) => n.toString(16).padStart(32, '0');  // a stand-in for a game's random token
const settle = () => new Promise((resolve) => setImmediate(resolve));

function fakeState() {
  const db = new DatabaseSync(':memory:');
  const sockets = [];
  return {
    sockets,
    storage: { sql: { exec(query, ...bindings) { const rows = db.prepare(query).all(...bindings); return { toArray: () => rows, one: () => rows[0] }; } } },
    acceptWebSocket: (ws) => sockets.push(ws),
    getWebSockets: () => sockets.filter((ws) => ws.open),
  };
}

function fakeSocket() {
  let attachment = null;
  return {
    open: true,
    sent: [],
    send(text) { if (!this.open) throw new Error('closed'); const f = JSON.parse(text); this.sent.push(...(Array.isArray(f) ? f : [f])); },
    accept() {},
    close(code) { this.open = false; this.code = code; },
    serializeAttachment(value) { attachment = structuredClone(value); },
    deserializeAttachment: () => structuredClone(attachment),
    all(type) { return this.sent.filter((m) => m.t === type); },
    last(type) { return this.all(type).at(-1); },
  };
}

// A world of sectors that can reach each other and an Atlas, as the runtime's bindings would.
function world({ limiters = {} } = {}) {
  const env = { ...limiters };
  const sectors = new Map(), clock = { now: NOW };
  const atlas = new Atlas(fakeState(), env);
  atlas.now = () => clock.now;
  env.ATLAS = { idFromName: (name) => name, get: () => ({ fetch: (url, init) => atlas.fetch(new Request(url, init)) }) };
  env.SECTORS = {
    idFromName: (name) => name,
    get: (name) => ({ fetch: (url, init) => sectorAt(name).fetch(new Request(url, init)) }),
  };
  function sectorAt(name) {
    if (!sectors.has(name)) {
      const s = new Sector(fakeState(), env);
      s.now = () => clock.now;
      sectors.set(name, s);
    }
    return sectors.get(name);
  }
  // A player joining sector (sx, sy), signed and with a token unless told otherwise.
  async function player(sx, sy, { initials = 'ABC', id = 1, hide = false, quiet = false, x, y, address = null } = {}) {
    const sector = sectorAt(`${sx},${sy}`), ws = fakeSocket();
    sector.join(ws, sx, sy, address);
    const p = { ws, sector, say: (m) => sector.webSocketMessage(ws, JSON.stringify(m)) };
    await p.say({ t: 'me', initials, ...(id === null ? {} : { token: token(id) }), hide, quiet });
    if (x !== undefined) await p.say({ t: 'pos', x, y });
    p.pid = id === null ? null : await playerId(token(id));
    return p;
  }
  // Time passes and a message comes in, to carry whatever the sector owes.
  async function tick(p, ms = 1000) {
    clock.now += ms;
    await p.say({ t: 'here' });
    await settle();
  }
  return { env, clock, atlas, sectorAt, player, tick };
}

describe('who a player is', () => {
  test('a player is named by the hash of their token, the same in every sector and every visit', async () => {
    const w = world();
    const a = await w.player(0, 0, { id: 7, x: 10, y: 10 });
    const watcher = await w.player(0, 0, { id: 8 });
    await w.tick(watcher);
    assert.match(a.pid, /^[0-9a-f]{12}$/);
    assert.deepEqual(watcher.ws.last('presence').p, [[a.pid, 'ABC', 10, 10]]);
    // Another socket with the same token, elsewhere or later, is the same player.
    const again = await w.player(1, 0, { id: 7, x: SECTOR + 10, y: 10 });
    await w.tick(again);
    assert.equal(again.ws.last('presence').p[0][0], a.pid);
    assert.notEqual((await w.player(0, 0, { id: 9 })).pid, a.pid);
  });

  test("a player can't pick their id, or change it once given", async () => {
    const w = world();
    const victim = await w.player(0, 0, { id: 1 });
    const watcher = await w.player(0, 0, { id: 2 });
    const sock = await w.player(0, 0, { id: null });
    await sock.say({ t: 'me', initials: 'EVL', pid: victim.pid, id: victim.pid, token: victim.pid });
    await sock.say({ t: 'pos', x: 5, y: 5 });
    await w.tick(watcher);
    const shown = watcher.ws.last('presence').p.map((p) => p[0]);
    assert.ok(!shown.includes(victim.pid));
    assert.equal(shown[0], sock.ws.deserializeAttachment().id);  // just its socket's id, as before
    await sock.say({ t: 'me', initials: 'EVL', token: token(3) });
    await sock.say({ t: 'me', initials: 'EVL', token: token(4) });
    assert.equal(sock.sector.everyone().get(sock.ws).pid, await playerId(token(3)));
  });
});

describe('the surveyor list', () => {
  let w, reports;
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout'] });
    w = world();
    reports = [];
    const fetch = w.env.ATLAS.get().fetch;
    w.env.ATLAS.get = () => ({ fetch: (url, init) => { if (url.endsWith('/report')) reports.push(JSON.parse(init.body)); return fetch(url, init); } });
  });
  afterEach(() => mock.timers.reset());

  test('a sector reports who is listed: by territory, never the cell, and only those who are', async () => {
    const at = (rx, ry) => ({ x: rx * 48 + 17.4, y: ry * 48 + 30 });
    const one = await w.player(0, 0, { id: 1, initials: 'ONE', ...at(1, 2) });
    w.clock.now += 3000;
    const two = await w.player(0, 0, { id: 2, initials: 'TWO', quiet: true, ...at(3, 3) });
    await w.player(0, 0, { id: 3, initials: 'HID', hide: true, ...at(0, 0) });   // hidden from the list
    await w.player(0, 0, { id: null, initials: 'OLD', ...at(0, 1) });            // an older game, with no token
    await w.player(0, 0, { id: 4, initials: 'AWY' });                            // joined, but looking elsewhere
    await w.player(0, 0, { id: 5, initials: 'OUT', x: SECTOR + 5, y: 5 });       // says it's somewhere it isn't
    w.clock.now += REPORT_MS;
    const last = await w.player(0, 0, { id: 6, initials: 'NEW', ...at(2, 0) });
    await w.tick(last, REPORT_MS);
    const pid = (n) => playerId(token(n));
    assert.deepEqual(reports.at(-1).who, [
      [await pid(6), 'NEW', 2, 0, 10, 0],
      [await pid(2), 'TWO', 3, 3, 20, FLAG_QUIET],
      [await pid(1), 'ONE', 1, 2, 23, 0],
    ]);
    assert.equal(reports.at(-1).players, 6);  // everyone placed still counts
    // Nobody listed: no list in the report at all.
    for (const [p, i] of [[one, 1], [two, 2], [last, 6]]) await p.say({ t: 'me', initials: 'ANY', token: token(i), hide: true });
    await w.tick(last, REPORT_MS);
    assert.equal('who' in reports.at(-1), false);
  });

  test('a player in two tabs is listed once, where they last moved', async () => {
    const a = await w.player(0, 0, { id: 1, x: 5, y: 5 });
    w.clock.now += 1000;
    await w.player(0, 0, { id: 1, x: 100, y: 100 });
    await w.tick(a, REPORT_MS);
    assert.deepEqual(reports.at(-1).who.map((e) => e.slice(0, 4)), [[a.pid, 'ABC', 2, 2]]);
  });

  test('a sector reports at least every REFRESH_MS while its players are still there, moving or not', async () => {
    const p = await w.player(0, 0, { id: 1, x: 5, y: 5 });
    await w.tick(p, REPORT_MS);  // what was owed goes
    const before = reports.length;
    w.clock.now += REFRESH_MS - 1;
    await p.say({ t: 'here' });
    await settle();
    assert.equal(reports.length, before);
    w.clock.now += 1;
    await p.say({ t: 'here' });
    await settle();
    assert.equal(reports.length, before + 1);
    assert.equal(reports.at(-1).who[0][4], (REPORT_MS + REFRESH_MS) / 1000);  // idle all along
  });

  test('a listed player leaving comes off the list with a report straight away', async () => {
    const players = await Promise.all(Array.from({ length: 3 }, (_, i) => w.player(0, 0, { id: i + 1, x: 5 + i, y: 5 })));
    await w.tick(players[1], REPORT_MS);
    // Just after positions went out, when nothing else would send a report.
    w.clock.now += 10;
    const before = reports.length;
    players[0].ws.close();
    await players[0].sector.webSocketClose(players[0].ws);
    await settle();
    assert.equal(reports.length, before + 1);
    assert.deepEqual(reports.at(-1).who.map((e) => e[0]).sort(), [players[1].pid, players[2].pid].sort());
    // One who wasn't listed leaves without a report of its own.
    const quiet = await w.player(0, 0, { id: 9, hide: true, x: 9, y: 9 });
    await w.tick(quiet, REPORT_MS);
    w.clock.now += 10;
    const then = reports.length;
    quiet.ws.close();
    await quiet.sector.webSocketClose(quiet.ws);
    await settle();
    assert.equal(reports.length, then);
  });
});

describe('the Atlas list', () => {
  let atlas, clock;
  beforeEach(() => { atlas = new Atlas(fakeState(), {}); clock = NOW; atlas.now = () => clock; });
  const counts = () => Array(16).fill(0);
  const report = (sx, sy, who) => atlas.fetch(new Request('https://atlas/report', { method: 'POST', body: JSON.stringify({ sx, sy, players: who.length, charted: counts(), who }) }));
  const list = async () => (await atlas.fetch(new Request('https://atlas/surveyors'))).json();
  const pid = (n) => n.toString(16).padStart(12, '0');

  test('lists everyone sectors reported, once each, from the latest report, idle counted to now', async () => {
    assert.equal((await report(0, 0, [[pid(1), 'ONE', 1, 1, 5, 0], [pid(2), 'TWO', 2, 3, 0, 0]])).status, 200);
    clock += 4000;
    assert.equal((await report(1, 0, [[pid(2), 'TWO', 4, 0, 0, 0]])).status, 200);  // TWO crossed into sector 1,0
    clock += 1000;
    const snap = await list();
    assert.equal(snap.n, 2);
    assert.deepEqual(snap.sectors, [[0, 0, [[pid(1), 'ONE', 1, 1, 10, 0]]], [1, 0, [[pid(2), 'TWO', 4, 0, 1, 0]]]]);
  });

  test('forgets sectors that stop reporting, and rebuilds the list at most every LIST_MS', async () => {
    await report(0, 0, [[pid(1), 'ONE', 1, 1, 0, 0]]);
    assert.equal((await list()).n, 1);
    await report(2, 2, [[pid(2), 'TWO', 8, 8, 0, 0]]);
    assert.equal((await list()).n, 1);
    clock += LIST_MS;
    assert.equal((await list()).n, 2);
    clock += ONLINE_MS;
    await report(2, 2, [[pid(2), 'TWO', 8, 8, 0, 0]]);
    clock += LIST_MS;
    assert.deepEqual((await list()).sectors.map((s) => s.slice(0, 2)), [[2, 2]]);
    // A report without a list empties its sector's.
    await report(2, 2, []);
    clock += LIST_MS;
    assert.equal((await list()).n, 0);
  });

  test('refuses lists it cannot use', async () => {
    const bad = [
      [['nothex', 'ONE', 1, 1, 0, 0]],
      [[pid(1), 'one', 1, 1, 0, 0]],
      [[pid(1), 'ONE', 4, 1, 0, 0]],      // a territory of another sector
      [[pid(1), 'ONE', 1, 1, -1, 0]],
      [[pid(1), 'ONE', 1, 1, 0]],
      'everyone',
      Array.from({ length: MAX_PLAYERS + 1 }, (_, i) => [pid(i), 'ONE', 1, 1, 0, 0]),
    ];
    for (const who of bad) assert.equal((await report(0, 0, who)).status, 400, JSON.stringify(who).slice(0, 60));
  });
});

describe('a page of the list', () => {
  const pid = (n) => n.toString(16).padStart(12, '0');
  // Players spread over the shared world, as the Atlas would hand them out.
  function spread(n, seed = 1) {
    let s = seed;
    const rand = () => ((s = (s * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
    const bySector = new Map();
    for (let i = 0; i < n; i++) {
      const rx = Math.floor(rand() * 100) - 50, ry = Math.floor(rand() * 100) - 50, key = `${Math.floor(rx / 4)},${Math.floor(ry / 4)}`;
      if (!bySector.has(key)) bySector.set(key, [Math.floor(rx / 4), Math.floor(ry / 4), []]);
      bySector.get(key)[2].push([pid(i), 'ABC', rx, ry, Math.floor(rand() * 100), 0]);
    }
    return { n, sectors: [...bySector.values()] };
  }

  test('comes nearest first, and pages through everyone exactly once', () => {
    const snap = spread(500), all = snap.sectors.flatMap((s) => s[2]);
    const d = (e, rx, ry) => Math.max(Math.abs(e[2] - rx), Math.abs(e[3] - ry));
    const first = nearest(snap, 3, -7, 0);
    assert.equal(first.who.length, LIST_PAGE);
    assert.equal(first.n, 500);
    assert.equal(first.more, true);
    // Nobody left out is nearer than the last one on the page.
    const edge = d(first.who.at(-1), 3, -7);
    const shown = new Set(first.who.map((e) => e[0]));
    assert.ok(all.every((e) => shown.has(e[0]) || d(e, 3, -7) >= edge));
    for (let i = 1; i < first.who.length; i++) assert.ok(d(first.who[i - 1], 3, -7) <= d(first.who[i], 3, -7));
    const seen = [];
    for (let page = 0; ; page++) {
      const p = nearest(snap, 3, -7, page);
      seen.push(...p.who.map((e) => e[0]));
      if (!p.more) break;
    }
    assert.equal(seen.length, 500);
    assert.equal(new Set(seen).size, 500);
  });

  test('leaves out whoever is asking', () => {
    const snap = { n: 2, sectors: [[0, 0, [[pid(1), 'ME', 1, 1, 0, 0], [pid(2), 'YOU', 2, 2, 0, 0]]]] };
    assert.deepEqual(nearest(snap, 1, 1, 0, pid(1)), { n: 1, page: 0, size: LIST_PAGE, more: false, who: [[pid(2), 'YOU', 2, 2, 0, 0]] });
  });
});

describe('GET /v1/survey/surveyors', () => {
  const pid = (n) => n.toString(16).padStart(12, '0');
  let asked, env;
  beforeEach(() => {
    asked = 0;
    env = {
      ALLOWED_ORIGINS: ORIGIN,
      ATLAS: {
        idFromName: () => 'atlas',
        get: () => ({ fetch: async () => { asked++; return Response.json({ n: 2, sectors: [[0, 0, [[pid(1), 'ONE', 0, 0, 0, 0]]], [3, 3, [[pid(2), 'TWO', 12, 12, 0, 0]]]] }); } }),
      },
    };
  });
  const get = (query, init = {}) => routeSurveyors(new Request(`https://survey.test/v1/survey/surveyors${query}`, { headers: { Origin: ORIGIN }, ...init }), env, corsHeaders, json);

  test("answers nearest first from the Atlas's snapshot, cached for a few seconds", async () => {
    const res = await get('?r=13,13');
    assert.equal(res.status, 200);
    assert.equal(res.headers.get('Access-Control-Allow-Origin'), ORIGIN);
    assert.equal(res.headers.get('Cache-Control'), `public, max-age=${LIST_MS / 1000}`);
    assert.deepEqual((await res.json()).who.map((e) => e[1]), ['TWO', 'ONE']);
    assert.deepEqual((await (await get('?r=0,0&page=0')).json()).who.map((e) => e[1]), ['ONE', 'TWO']);
    assert.equal(asked, 1);
  });

  test('refuses questions it cannot answer, and leaves other paths alone', async () => {
    for (const q of ['', '?r=1', '?r=a,b', `?r=0,0&page=${LIST_PAGES}`, '?r=0,0&page=-1', '?r=0,0&me=nope']) assert.equal((await get(q)).status, 400, q);
    assert.equal((await get('?r=0,0', { method: 'POST' })).status, 405);
    assert.equal(routeSurveyors(new Request('https://survey.test/v1/survey/world'), env, corsHeaders, json), null);
    assert.equal(routeSurveyors(new Request('https://survey.test/v1/survey/surveyors?r=0,0'), {}, corsHeaders, json), null);
  });

  test('is what the Worker does with the path', async () => {
    const res = await worker.fetch(new Request('https://survey.test/v1/survey/surveyors?r=0,0', { headers: { Origin: ORIGIN } }), env);
    assert.equal(res.status, 200);
    assert.equal((await res.json()).n, 2);
  });
});

describe('emotes', () => {
  let w;
  beforeEach(() => { w = world(); });
  const emote = (from, to, e = 'wave', s = null) => from.say({ t: 'emote', to: to.pid, e, s: s ?? [Math.floor(to.ws.deserializeAttachment().sx), to.ws.deserializeAttachment().sy] });

  test('reach a player in the same sector, from whoever sent them, with where they are', async () => {
    const a = await w.player(0, 0, { id: 1, initials: 'AAA', x: 60, y: 100 });
    const b = await w.player(0, 0, { id: 2, initials: 'BBB', x: 5, y: 5 });
    await emote(a, b);
    assert.deepEqual(b.ws.last('emote'), { t: 'emote', from: a.pid, ini: 'AAA', e: 'wave', r: [1, 2] });
    assert.deepEqual(a.ws.last('emoted'), { t: 'emoted', to: b.pid, e: 'wave', ok: true });
    assert.equal(a.ws.last('emote'), undefined);
  });

  test('reach a player in another sector, through that sector', async () => {
    const a = await w.player(0, 0, { id: 1, initials: 'AAA', x: 10, y: 10 });
    const b = await w.player(5, -3, { id: 2, initials: 'BBB', x: 5 * SECTOR + 1, y: -3 * SECTOR + 1 });
    await emote(a, b, 'thanks', [5, -3]);
    assert.deepEqual(b.ws.last('emote'), { t: 'emote', from: a.pid, ini: 'AAA', e: 'thanks', r: [0, 0] });
    assert.equal(a.ws.last('emoted').ok, true);
    // Sent to the wrong sector, it finds nobody.
    await emote(a, b, 'wave', [4, -3]);
    assert.deepEqual(a.ws.last('emoted'), { t: 'emoted', to: b.pid, e: 'wave', error: 'gone' });
  });

  test("can't be sent as anyone else, or by anyone unsigned", async () => {
    const a = await w.player(0, 0, { id: 1, initials: 'AAA' });
    const b = await w.player(0, 0, { id: 2, initials: 'BBB' });
    const c = await w.player(0, 0, { id: 3, initials: 'CCC' });
    await a.say({ t: 'emote', to: b.pid, e: 'wave', s: [0, 0], from: c.pid, ini: 'CCC' });
    assert.equal(b.ws.last('emote').from, a.pid);
    assert.equal(b.ws.last('emote').ini, 'AAA');
    const unsigned = await w.player(0, 0, { id: 4, initials: '' });
    const noToken = await w.player(0, 0, { id: null, initials: 'NOT' });
    for (const p of [unsigned, noToken]) { await emote(p, b); assert.equal(p.ws.last('emoted').error, 'sign first'); }
    // The internal path isn't reachable from outside: the Worker only forwards sockets.
    assert.equal(routeSurvey(new Request('https://survey.test/emote', { method: 'POST', headers: { Origin: ORIGIN } }), w.env), null);
  });

  test('are only the fixed few, to someone else', async () => {
    const a = await w.player(0, 0, { id: 1 });
    const b = await w.player(0, 0, { id: 2 });
    for (const bad of [{ e: 'kiss' }, { e: 'hello there' }, { to: 'nobody' }, { to: a.pid }, { s: [0] }, { s: 'here' }]) {
      await a.say({ t: 'emote', to: b.pid, e: 'wave', s: [0, 0], ...bad });
      assert.equal(a.ws.last('emoted').error, 'bad emote', JSON.stringify(bad));
    }
    assert.equal(b.ws.all('emote').length, 0);
    assert.equal(EMOTES.length, 7);
  });

  test('are limited per socket', async () => {
    const a = await w.player(0, 0, { id: 1 });
    const others = await Promise.all([2, 3, 4, 5].map((id) => w.player(0, 0, { id })));
    for (const b of others) await emote(a, b);
    assert.deepEqual(a.ws.all('emoted').map((m) => m.error ?? 'ok'), [...Array(EMOTE_BURST).fill('ok'), 'slow down']);
    w.clock.now += EMOTE_REFILL_MS;
    await emote(a, others[3]);
    assert.equal(a.ws.last('emoted').ok, true);
  });

  test('are limited per address, across every sector', async () => {
    let n = 0;
    w = world({ limiters: { SURVEY_EMOTES: { limit: async () => ({ success: ++n <= 2 }) } } });
    const a = await w.player(0, 0, { id: 1, address: 'aaaa' });
    const there = await w.player(1, 0, { id: 1, address: 'aaaa' });
    const b = await w.player(0, 0, { id: 2 }), c = await w.player(1, 0, { id: 3 });
    await emote(a, b);
    await emote(there, c);
    await emote(a, c, 'wave', [1, 0]);
    assert.deepEqual([...a.ws.all('emoted'), ...there.ws.all('emoted')].map((m) => m.error ?? 'ok'), ['ok', 'slow down', 'ok']);
  });

  test('from one sender to one player are capped wherever they come from, and nobody can be flooded', async () => {
    const b = await w.player(0, 0, { id: 2, x: 5, y: 5 });
    // One sender with sockets in three sectors.
    const a = await Promise.all([[0, 0], [1, 0], [0, 1]].map(([sx, sy]) => w.player(sx, sy, { id: 1 })));
    for (let i = 0; i < PAIR_MAX + 1; i++) await emote(a[i % 3], b, 'wave', [0, 0]);
    assert.equal(b.ws.all('emote').length, PAIR_MAX);
    assert.equal(a[PAIR_MAX % 3].ws.last('emoted').error, 'slow down');
    w.clock.now += PAIR_MS;
    // Many senders at once: the first INBOX_MAX get through.
    const crowd = await Promise.all(Array.from({ length: INBOX_MAX + 2 }, (_, i) => w.player(0, 0, { id: 100 + i })));
    for (const p of crowd) await emote(p, b);
    assert.equal(b.ws.all('emote').length, PAIR_MAX + INBOX_MAX);
    assert.deepEqual(crowd.slice(INBOX_MAX).map((p) => p.ws.last('emoted').error), ['busy', 'busy']);
  });

  test("don't reach anyone who turned them off, or a hidden player from afar", async () => {
    const quiet = await w.player(0, 0, { id: 2, quiet: true });
    const hidden = await w.player(0, 0, { id: 3, hide: true });
    const near = await w.player(0, 0, { id: 1 });
    const far = await w.player(3, 3, { id: 4 });
    await emote(near, quiet);
    assert.equal(near.ws.last('emoted').error, 'off');
    await emote(near, hidden);
    assert.equal(near.ws.last('emoted').ok, true);
    await emote(far, hidden, 'wave', [0, 0]);
    assert.equal(far.ws.last('emoted').error, 'gone');
    assert.equal(hidden.ws.all('emote').length, 1);
    assert.equal(quiet.ws.all('emote').length, 0);
  });

  test('only go to sectors a list or a caret could show', async () => {
    const out = AREA + 5;
    const a = await w.player(out, 0, { id: 1, x: out * SECTOR + 3, y: 3 });
    const b = await w.player(out + 3, 0, { id: 2 });
    await emote(a, b, 'wave', [out + 3, 0]);
    assert.equal(a.ws.last('emoted').error, 'gone');
    assert.equal(w.sectorAt(`${out + 3},0`).everyone().size, 1);
    const c = await w.player(out + 1, 0, { id: 3 });
    await emote(a, c, 'wave', [out + 1, 0]);  // beside it, in view
    assert.equal(c.ws.last('emote').from, a.pid);
  });

  test('a sector passing one on is told of a bad one, and nothing goes out', async () => {
    const b = await w.player(0, 0, { id: 2 });
    const sector = w.sectorAt('0,0');
    const post = (body) => sector.fetch(new Request('https://sector/emote', { method: 'POST', body: typeof body === 'string' ? body : JSON.stringify(body) }));
    for (const body of ['nope', { from: 'x', to: b.pid, e: 'wave', ini: 'AAA', r: null }, { from: '0'.repeat(12), to: b.pid, e: 'kiss', ini: 'AAA', r: null }]) {
      assert.equal((await post(body)).status, 400);
    }
    const res = await post({ from: '0'.repeat(12), to: b.pid, e: 'wave', ini: 'AAA', r: [0, 0] });
    assert.deepEqual(await res.json(), { error: null });
    assert.equal(b.ws.all('emote').length, 1);
  });
});

test('the Atlas still totals a sector that lists its surveyors', async () => {
  const atlas = new Atlas(fakeState(), {});
  atlas.now = () => NOW;
  const res = await atlas.fetch(new Request('https://atlas/report', {
    method: 'POST', body: JSON.stringify({ sx: 0, sy: 0, players: 1, charted: Array(16).fill(0), who: [['0'.repeat(12), 'ABC', 0, 0, 0, 0]] }),
  }));
  assert.deepEqual(await res.json(), { charted: 0, total: AREA_WORDS, players: 1, day: Math.floor(NOW / 86400000), overAt: 0, over: [] });
});
