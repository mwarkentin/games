// How much work the Atlas does per report, and so how many reports a second
// its one thread can take, measured in Node with the stand-ins the tests use.
// Every sector in the shared world reports to this one object (see "How it
// works" in SURVEY.md), so it's the survey's one part that doesn't grow by
// adding objects. Run with:
//   node --disable-warning=ExperimentalWarning worker/bench/atlas.js [online] [sectors]
// e.g. 5000 players spread over 60 busy sectors. Like bench/sector.js this
// is only our code: in the Workers runtime each request costs the runtime's
// own work too (receiving it, parsing its 10–30 KB of JSON is counted here),
// so treat the reports a second as a ceiling, not a target.

import { DatabaseSync } from 'node:sqlite';
import { performance } from 'node:perf_hooks';

import { Atlas, MAX_PLAYERS, REPORT_MS } from '../src/survey.js';
import { TERR } from '../src/survey-social.js';

const [online = '5000', busy = '60'] = process.argv.slice(2);
const ONLINE = Number(online), SECTORS = Math.min(625, Number(busy));

function fakeState() {
  const db = new DatabaseSync(':memory:');
  return { storage: { sql: { exec: (q, ...b) => { const rows = db.prepare(q).all(...b); return { toArray: () => rows, one: () => rows[0] }; } } } };
}

const atlas = new Atlas(fakeState(), {});
// Sectors spiral out from the origin, the busiest in the middle, as a crowd that spawns together would.
const spots = [];
for (let r = 0; spots.length < SECTORS; r++) {
  for (let sy = -r; sy <= r; sy++) for (let sx = -r; sx <= r; sx++) if (Math.max(Math.abs(sx), Math.abs(sy)) === r && spots.length < SECTORS) spots.push([sx, sy]);
}
const hex = (n, len) => n.toString(16).padStart(len, '0').slice(-len);
let pid = 0;
// Each player has an address of their own, apart from a few shared ones (an office, a campus).
const reports = spots.map(([sx, sy], i) => {
  const players = Math.min(MAX_PLAYERS, Math.round(ONLINE / SECTORS));
  const who = Array.from({ length: players }, () => {
    pid++;
    const guild = pid % 5 === 0 ? [[hex(pid % 400, 8)]] : [];
    return [hex(pid, 12), 'ABC', sx * TERR + (pid % TERR), sy * TERR + ((pid >> 2) % TERR), pid % 90, 0, ...guild];
  });
  const perAddress = who.map((e, j) => [hex(j < 20 ? i : 1e6 + pid - j, 64), 1]);
  const tags = [...new Set(who.flatMap((e) => e[6] ?? []))].slice(0, 100);
  const by = who.slice(0, Math.ceil(players / 20)).map((e, j) => [hex(1e6 + j * 7 + i, 64), 1]);
  return { sx, sy, players, perAddress, charted: new Array(TERR * TERR).fill(3), hot: [sx * 192 + 96, sy * 192 + 96], who, tags, by, day: -1, overAt: 0, novaSeq: 0 };
});
const bodies = reports.map((r) => JSON.stringify(r));
const post = async (i) => {
  const res = await atlas.fetch(new Request('https://atlas/report', { method: 'POST', body: bodies[i % bodies.length] }));
  if (!res.ok) throw new Error(`report refused: ${await res.text()}`);
  await res.text();
};

for (let i = 0; i < bodies.length; i++) await post(i);  // every sector once, so the world is full
const runs = Math.max(400, bodies.length * 4);
let t0 = performance.now();
for (let i = 0; i < runs; i++) await post(i);
const report = (performance.now() - t0) / runs;
t0 = performance.now();
for (let i = 0; i < 200; i++) atlas.totals();
const totals = (performance.now() - t0) / 200;
t0 = performance.now();
for (let i = 0; i < 20; i++) { atlas.view = null; await atlas.fetch(new Request('https://atlas/world')); }
const world = (performance.now() - t0) / 20;
t0 = performance.now();
for (let i = 0; i < 20; i++) { atlas.list = null; await atlas.fetch(new Request('https://atlas/surveyors')); }
const list = (performance.now() - t0) / 20;

const avgBytes = bodies.reduce((a, b) => a + b.length, 0) / bodies.length;
// Reports a second: each busy sector at most every REPORT_MS, plus one when a listed player leaves (forced).
const steady = SECTORS / (REPORT_MS / 1000);
console.log(`${ONLINE} online over ${SECTORS} sectors (${Math.round(ONLINE / SECTORS)} a sector), reports of ${(avgBytes / 1024).toFixed(1)} KB`);
console.log(`  one report:       ${report.toFixed(3)} ms (totals() alone ${totals.toFixed(3)} ms)`);
console.log(`  world map built:  ${world.toFixed(2)} ms, at most every 5 s`);
console.log(`  list snapshot:    ${list.toFixed(2)} ms, at most every 10 s`);
console.log(`  reports a second at 100% of one thread: ~${Math.floor(1000 / report)}; steady state here is ~${steady.toFixed(0)} a second plus forced ones`);
process.exit(0);  // the Atlas's save timer would keep Node waiting a minute
