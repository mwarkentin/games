// How much work our own code does per message in one survey sector, measured
// in Node with the same stand-ins the tests use. Run with:
//   node --disable-warning=ExperimentalWarning worker/bench/sector.js
// This is only our code. In the Workers runtime, receiving and sending each
// WebSocket message costs far more than this: bench/load.js against wrangler
// dev saturates a sector at 750 to 1,000 players, where this estimate says it
// would be nearly idle. Use it to catch slow code, and load.js for capacity.

import { DatabaseSync } from 'node:sqlite';
import { performance } from 'node:perf_hooks';

import { chunk } from '../src/letterfield-world.js';
import { SECTOR, Sector, checkClaim } from '../src/survey.js';

const PLAYERS = 1000;

function fakeState() {
  const db = new DatabaseSync(':memory:');
  const sockets = [];
  return {
    storage: { sql: { exec: (q, ...b) => { const rows = db.prepare(q).all(...b); return { toArray: () => rows, one: () => rows[0] }; } } },
    acceptWebSocket: (ws) => sockets.push(ws),
    getWebSockets: () => sockets,
  };
}
function fakeSocket() {
  let attachment = null;
  return {
    bytes: 0,
    send(text) { this.bytes += text.length; },
    serializeAttachment(v) { attachment = structuredClone(v); },
    deserializeAttachment: () => structuredClone(attachment),
  };
}
function time(label, runs, fn) {
  fn(0);
  const t0 = performance.now();
  for (let i = 1; i <= runs; i++) fn(i);
  const each = (performance.now() - t0) / runs;
  console.log(`${label.padEnd(52)} ${each < 1 ? `${(each * 1000).toFixed(1)} µs` : `${each.toFixed(2)} ms`}`);
  return each;
}

// Every hidden word in sector 0,0: about 16 territories × 16 chunks × 7 words.
const words = [];
for (let cy = 0; cy < SECTOR / 12; cy++) for (let cx = 0; cx < SECTOR / 12; cx++) words.push(...chunk(cx, cy).words);
console.log(`sector 0,0 hides ${words.length} words; ${PLAYERS} players connected\n`);

time('checkClaim, chunk already generated', 20000, (i) => checkClaim(words[i % words.length], 0, 0));
let far = 0;
time('checkClaim, chunk generated for it', 2000, () => {
  far += 1;
  const w = chunk(far * 40, 9000).words[0];
  checkClaim(w, Math.floor(w.x / SECTOR), Math.floor(w.y / SECTOR));
});

const state = fakeState();
const sector = new Sector(state, {});
sector.schedulePresence = () => {};
const sockets = Array.from({ length: PLAYERS }, () => fakeSocket());
for (const ws of sockets) sector.join(ws, 0, 0);
let n = 0;
for (const ws of sockets) await sector.webSocketMessage(ws, JSON.stringify({ t: 'pos', x: (n++ % 190) + 0.5, y: n % 190 }));

let claimed = 0;
const claimMs = time(`claim, sent to ${PLAYERS} sockets without batching`, Math.min(2000, words.length - 1), (i) => {
  const ws = sockets[i % PLAYERS];
  const me = ws.deserializeAttachment();
  me.tokens = 5;
  ws.serializeAttachment(me);
  const { w, x, y, d } = words[i];
  sector.claim(ws, me, { t: 'claim', w, x, y, d });
  sector.sendBatch(true);
  claimed++;
});
const posMs = time('position update', 20000, (i) => {
  sector.webSocketMessage(sockets[i % PLAYERS], `{"t":"pos","x":${i % 190},"y":${(i * 7) % 190}}`);
});
const frameMs = time(`presence frame to ${PLAYERS} sockets`, 200, () => sector.sendPresence());
const joinMs = time(`join, with ${claimed} claims in the snapshot`, 200, () => {
  const ws = fakeSocket();
  sector.join(ws, 0, 0);
  state.getWebSockets().pop();
});
time('join, first after waking from hibernation', 50, () => {
  sector.claimsJson = null;
  const ws = fakeSocket();
  sector.join(ws, 0, 0);
  state.getWebSockets().pop();
});
const before = sockets[0].bytes;
sector.sendPresence();
const frameBytes = sockets[0].bytes - before;
const snapshot = fakeSocket();
sector.join(snapshot, 0, 0);
console.log(`\nA presence frame is ${(frameBytes / 1024).toFixed(1)} KB; a join's snapshot is ${(snapshot.bytes / 1024).toFixed(0)} KB.`);

const busy = PLAYERS * (0.5 * posMs + claimMs / 30) + frameMs;
console.log(`
If each of ${PLAYERS} players sends a position every 2 s and claims a word every
30 s, and the sector sends one presence frame a second, the sector is busy for
about ${busy.toFixed(0)} ms of every second in our code, sending ${(PLAYERS * frameBytes / 1024 / 1024).toFixed(1)} MB of positions
(${(PLAYERS * 0.5 + PLAYERS / 30).toFixed(0)} incoming messages a second). The runtime's own work per message is the real limit.`);
