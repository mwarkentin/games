// A crowd arriving at once, as a link on a busy news site would bring: new
// players keep arriving, each asks the world map where to start, as the game
// does (spawnSomewhere), joins that sector and plays like bench/load.js's.
// Unlike load.js it spreads over as many sectors as the spawn rule sends
// people to, so it shows where a burst of newcomers lands, how the Atlas's
// world map keeps up, and, with STORM, every socket dropping at once (as a
// deploy of the Worker does) and coming back with the game's own backoff.
// Run against wrangler dev (or a Worker Preview, never production):
//   node worker/bench/spike.js http://127.0.0.1:8787 [players] [arrivals a second] [seconds] [origin]
// Environment:
//   SHARED=0.2 ADDRESSES=5  a fifth of players behind five shared addresses (an office, a campus, CGNAT)
//   STORM=30                drop every socket 30 s in, and reconnect each after the game's backoff
//   STORM_MIN=1 STORM_MAX=6 that backoff's range, in seconds (the game's first try after a drop: 1–6 s)
//   OLD_SPAWN=1             start everyone at the world map's one `spawn`, as games did before `spawns`
//   PLACE="0,0 1,0 0,1"     start players round these sectors instead, ignoring the world map's spawn:
//                           on the edge every player here is one address, which a sector takes 40 of
//   CLAIM_S=30              seconds between a player's claims, on average (20–40 s by default)
//   WATCH=5                 read the world map every 5 s through the run, for the Atlas's view as load rises
// Each player claims an address of its own with CF-Connecting-IP, which only
// wrangler dev believes; on Cloudflare's edge every player here is one address.

import { performance } from 'node:perf_hooks';

import { CH, chunk } from '../../js/letterfield/world.js';
import { SECTOR } from '../src/survey.js';

const [base = 'http://127.0.0.1:8787', players = '600', rate = '20', seconds = '60', origin = 'http://localhost:8000'] = process.argv.slice(2);
const N = Number(players), RATE = Number(rate), RUN_MS = Number(seconds) * 1000;
const SHARED = Number(process.env.SHARED || 0), ADDRESSES = Number(process.env.ADDRESSES || 5);
const STORM = Number(process.env.STORM || 0) * 1000;
const PLACE = (process.env.PLACE || '').split(/\s+/).filter(Boolean).map((k) => k.split(',').map(Number));
const CLAIM_MS = Number(process.env.CLAIM_S || 30) * 1000, WATCH = Number(process.env.WATCH || 0) * 1000;
const STORM_MIN = Number(process.env.STORM_MIN ?? 1) * 1000, STORM_MAX = Number(process.env.STORM_MAX ?? 6) * 1000;
const ws = base.replace(/^http/, 'ws');
const LOCAL = /^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(base);
const pct = (list, p) => { const s = [...list].sort((a, b) => a - b); return s.length ? s[Math.min(s.length - 1, Math.floor(p * s.length))] : NaN; };
const ms = (list) => `p50 ${pct(list, .5).toFixed(0)} / p95 ${pct(list, .95).toFixed(0)} / p99 ${pct(list, .99).toFixed(0)} ms`;
const sleep = (t) => new Promise((r) => setTimeout(r, t));
const hex = (n) => Array.from(crypto.getRandomValues(new Uint8Array(n)), (b) => b.toString(16).padStart(2, '0')).join('');

const t0 = performance.now();
const stats = { world: [], worldFailed: 0, hello: [], helloStorm: [], claim: [], first: 0, taken: 0, refused: {}, full: 0, fullWorld: 0, failed: 0, dropped: 0, back: 0 };
const landed = new Map();   // 'sx,sy' → players who started there
const fullBy = new Map();   // 'sx,sy' → times turned away as full
const words = new Map();    // 'sx,sy' → that sector's hidden words, worked out when someone first lands there
const wordsIn = (sx, sy) => {
  const k = `${sx},${sy}`;
  if (!words.has(k)) {
    const out = [], n = SECTOR / CH;
    for (let cy = 0; cy < n; cy++) for (let cx = 0; cx < n; cx++) out.push(...chunk(sx * n + cx, sy * n + cy).words);
    words.set(k, out);
  }
  return words.get(k);
};

let placed = 0;
async function startAt() {
  if (PLACE.length) { const [sx, sy] = PLACE[placed++ % PLACE.length]; return [sx * SECTOR + 96, sy * SECTOR + 96]; }
  const t = performance.now();
  try {
    const res = await fetch(`${base}/v1/survey/world`, { headers: { Origin: origin } });
    const m = await res.json();
    stats.world.push(performance.now() - t);
    // As the game picks (pickSpawn): among the crowds offered, by size or room, whichever is less.
    const offers = Array.isArray(m.spawns) && !process.env.OLD_SPAWN ? m.spawns : [];
    if (offers.length) {
      const weight = ([, , size, room]) => Math.max(1, Math.min(size, room));
      let r = Math.random() * offers.reduce((a, o) => a + weight(o), 0);
      for (const o of offers) if ((r -= weight(o)) < 0) return o;
      return offers[0];
    }
    return Array.isArray(m.spawn) ? m.spawn : [96, 96];
  } catch { stats.worldFailed++; return [96, 96]; }
}

function player(i) {
  const shared = Math.random() < SHARED;
  const ip = shared ? `192.0.2.${i % ADDRESSES}` : `10.${(i >> 16) & 255}.${(i >> 8) & 255}.${i & 255}`;
  const token = hex(16);
  let sock = null, timers = [], stopped = false;
  return (async () => {
    const [x0, y0] = await startAt();
    const x = x0 + (Math.random() - .5) * 8, y = y0 + (Math.random() - .5) * 8;
    const sx = Math.floor(x / SECTOR), sy = Math.floor(y / SECTOR), key = `${sx},${sy}`;
    landed.set(key, (landed.get(key) ?? 0) + 1);
    const pool = wordsIn(sx, sy), pending = new Map();
    let px = x, py = y, tries = 0;
    const open = (storm = false) => new Promise((resolve) => {
      const opened = performance.now();
      // Only wrangler dev takes an address from the client; Cloudflare's edge sets it, and refuses one sent.
      const s = new WebSocket(`${ws}/v1/survey/${sx}/${sy}`, { headers: { Origin: origin, ...(LOCAL ? { 'CF-Connecting-IP': ip } : {}) } });
      sock = s;
      s.onopen = () => {
        s.send(JSON.stringify({ t: 'me', initials: 'HNX', token }));
        const move = () => {
          px = Math.max(sx * SECTOR + 1, Math.min(sx * SECTOR + SECTOR - 2, px + (Math.random() - .5) * 4));
          py = Math.max(sy * SECTOR + 1, Math.min(sy * SECTOR + SECTOR - 2, py + (Math.random() - .5) * 4));
          try { s.send(JSON.stringify({ t: 'pos', x: px, y: py })); } catch { /* closed */ }
          timers.push(setTimeout(move, 1800 + Math.random() * 400));
        };
        const claim = () => {
          const { w, x: wx, y: wy, d } = pool[Math.floor(Math.random() * pool.length)];
          pending.set(`${w}~${wx}~${wy}~${d}`, performance.now());
          try { s.send(JSON.stringify({ t: 'claim', w, x: wx, y: wy, d })); } catch { /* closed */ }
          timers.push(setTimeout(claim, CLAIM_MS * (2 / 3 + Math.random() * 2 / 3)));
        };
        timers.push(setTimeout(move, Math.random() * 2000), setTimeout(claim, 5000 + Math.random() * 15000));
      };
      s.onmessage = (ev) => {
        const frame = JSON.parse(ev.data);
        for (const m of Array.isArray(frame) ? frame : [frame]) {
          const settle = (c) => {
            const k = `${c[0]}~${c[1]}~${c[2]}~${c[3]}`, at = pending.get(k);
            if (at === undefined) return false;
            stats.claim.push(performance.now() - at); pending.delete(k); return true;
          };
          if (m.t === 'hello') { (storm ? stats.helloStorm : stats.hello).push(performance.now() - opened); tries = 0; }
          else if (m.t === 'claimed' && settle(m.c)) stats.first++;
          else if (m.t === 'taken' && settle(m.c)) stats.taken++;
          else if (m.t === 'error') stats.refused[m.error] = (stats.refused[m.error] ?? 0) + 1;
          else if (m.t === 'full') { if (m.world) stats.fullWorld++; else stats.full++; fullBy.set(key, (fullBy.get(key) ?? 0) + 1); }
        }
      };
      s.onerror = () => {};
      s.onclose = () => {
        timers.forEach(clearTimeout); timers = [];
        if (stopped || sock !== s) return resolve();
        // Turned away or dropped: back off as the game does (a full sector waits a minute).
        tries++;
        const wait = fullBy.has(key) && tries === 1 ? 60000 : Math.min(30000, 1000 * 2 ** (tries - 1)) * (.5 + Math.random());
        timers.push(setTimeout(() => { if (!stopped) open().then(resolve); }, wait));
      };
    });
    open();
    if (STORM) {
      const until = STORM - (performance.now() - t0);
      if (until > 0) {
        await sleep(until);
        if (sock && sock.readyState === 1) {
          const old = sock;
          sock = null; old.onclose = () => {}; old.close(); timers.forEach(clearTimeout); timers = [];
          stats.dropped++;
          await sleep(STORM_MIN + Math.random() * (STORM_MAX - STORM_MIN));
          if (!stopped) { stats.back++; open(true); }
        }
      }
    }
    await sleep(Math.max(0, RUN_MS - (performance.now() - t0)));
    stopped = true; timers.forEach(clearTimeout);
    try { sock?.close(); } catch { /* closed */ }
  })();
}

const watched = [];
const watcher = WATCH && setInterval(async () => {
  const t = performance.now();
  try {
    const m = await (await fetch(`${base}/v1/survey/world`, { headers: { Origin: origin } })).json();
    watched.push(`${((t - t0) / 1000).toFixed(0)}s ${m.players}p/${m.sectors.length}s ${(performance.now() - t).toFixed(0)}ms`);
  } catch { watched.push(`${((t - t0) / 1000).toFixed(0)}s failed`); }
}, WATCH);
const all = [];
for (let i = 0; i < N; i++) {
  all.push(player(i));
  await sleep(1000 / RATE);
}
await Promise.all(all);
clearInterval(watcher);
await sleep(500);
let after = null;
try { after = await (await fetch(`${base}/v1/survey/world`, { headers: { Origin: origin } })).json(); } catch { /* left out */ }

console.log(`${N} players arriving at ${RATE} a second, for ${seconds} s${SHARED ? `, ${Math.round(SHARED * 100)}% behind ${ADDRESSES} shared addresses` : ''} (${base})`);
console.log(`  world map: ${ms(stats.world)}${stats.worldFailed ? `, ${stats.worldFailed} failed` : ''}`);
console.log(`  joined (upgrade to hello): ${stats.hello.length}, ${ms(stats.hello)}`);
console.log(`  turned away full: ${stats.full} sector, ${stats.fullWorld} survey`);
console.log(`  claims answered: ${stats.claim.length} (${stats.first} first, ${stats.taken} taken), ${ms(stats.claim)}; refused ${JSON.stringify(stats.refused)}`);
const where = [...landed].sort((a, b) => b[1] - a[1]);
console.log(`  started in ${where.length} sectors: ${where.slice(0, 8).map(([k, n]) => `${k}: ${n}${fullBy.get(k) ? ` (${fullBy.get(k)} full)` : ''}`).join(', ')}`);
if (STORM) console.log(`  storm at ${STORM / 1000} s: ${stats.dropped} dropped, ${stats.back} back over ${STORM_MIN / 1000}–${STORM_MAX / 1000} s, rejoined ${stats.helloStorm.length}, ${ms(stats.helloStorm)}`);
if (watched.length) console.log(`  world map through the run (time, players online/sectors live, latency): ${watched.join(', ')}`);
if (after) console.log(`  the Atlas after: ${after.players} online, ${after.sectors.length} sectors live, ${after.today?.charted ?? '?'} charted today`);
process.exit(0);
