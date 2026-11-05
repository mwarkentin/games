// Load test for the survey: opens many player sockets on one sector of a
// running Worker (wrangler dev, or a deployed one) and plays like people do.
// Each player sends its position every 2 s and circles a hidden word every
// ~30 s; the script reports how long claims take to come back and how
// regularly positions arrive. Run with:
//   node worker/bench/load.js http://127.0.0.1:8787 [players] [seconds] [origin]
// The origin must be in the Worker's ALLOWED_ORIGINS.

import { performance } from 'node:perf_hooks';

import { chunk } from '../src/letterfield-world.js';
import { SECTOR } from '../src/survey.js';

const [base = 'http://127.0.0.1:8787', players = '200', seconds = '30', origin = 'http://localhost:8000'] = process.argv.slice(2);
const N = Number(players), RUN_MS = Number(seconds) * 1000;
const url = `${base.replace(/^http/, 'ws')}/v1/survey/0/0`;

const words = [];
for (let cy = 0; cy < SECTOR / 12; cy++) for (let cx = 0; cx < SECTOR / 12; cx++) words.push(...chunk(cx, cy).words);

const stats = { connected: 0, failed: 0, full: 0, claimMs: [], gaps: [], received: 0, bytes: 0, first: 0, taken: 0, errors: 0 };
const pct = (list, p) => { const s = [...list].sort((a, b) => a - b); return s.length ? s[Math.min(s.length - 1, Math.floor(p * s.length))] : NaN; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function player(i) {
  return new Promise((resolve) => {
    const ws = new WebSocket(url, { headers: { Origin: origin } });
    const pending = new Map();
    let x = 6 + Math.random() * 180, y = 6 + Math.random() * 180, lastPresence = 0, timers = [];
    ws.onopen = () => {
      stats.connected++;
      ws.send(JSON.stringify({ t: 'me', initials: 'LDT' }));
      const move = () => {
        x = Math.max(1, Math.min(190, x + (Math.random() - .5) * 6));
        y = Math.max(1, Math.min(190, y + (Math.random() - .5) * 6));
        ws.send(JSON.stringify({ t: 'pos', x, y }));
        timers.push(setTimeout(move, 1800 + Math.random() * 400));
      };
      const claim = () => {
        const { w, x: wx, y: wy, d } = words[Math.floor(Math.random() * words.length)];
        pending.set(`${w}~${wx}~${wy}~${d}`, performance.now());
        ws.send(JSON.stringify({ t: 'claim', w, x: wx, y: wy, d }));
        timers.push(setTimeout(claim, 20000 + Math.random() * 20000));
      };
      timers.push(setTimeout(move, Math.random() * 2000), setTimeout(claim, Math.random() * 10000));
    };
    ws.onmessage = (ev) => {
      stats.received++;
      stats.bytes += ev.data.length;
      const frame = JSON.parse(ev.data);
      for (const m of Array.isArray(frame) ? frame : [frame]) handle(m);
    };
    const handle = (m) => {
      const settle = (c) => {
        const key = `${c[0]}~${c[1]}~${c[2]}~${c[3]}`, t0 = pending.get(key);
        if (t0 !== undefined) { stats.claimMs.push(performance.now() - t0); pending.delete(key); return true; }
        return false;
      };
      if (m.t === 'claimed' && settle(m.c)) stats.first++;
      else if (m.t === 'taken' && settle(m.c)) stats.taken++;
      else if (m.t === 'error') stats.errors++;
      else if (m.t === 'full') stats.full++;
      else if (m.t === 'presence') {
        const now = performance.now();
        if (lastPresence) stats.gaps.push(now - lastPresence);
        lastPresence = now;
      }
    };
    ws.onerror = () => {};
    ws.onclose = () => { if (!ws.everOpened) stats.failed++; timers.forEach(clearTimeout); resolve(); };
    ws.addEventListener('open', () => { ws.everOpened = true; });
    setTimeout(() => ws.close(), RUN_MS + i % 1000);
    setTimeout(() => { timers.forEach(clearTimeout); resolve(); }, RUN_MS + 5000);  // don't wait on a lost close
  });
}

const t0 = performance.now();
const progress = process.env.PROGRESS && setInterval(() => console.error(`  … ${((performance.now() - t0) / 1000).toFixed(0)} s: ${stats.connected} connected, ${stats.received} messages`), 5000);
const all = [];
const RAMP = Number(process.env.RAMP || 500);  // new connections a second
for (let i = 0; i < N; i++) { all.push(player(i)); if (i % 10 === 9) await sleep(10000 / RAMP); }
await Promise.all(all);
clearInterval(progress);
const secs = (performance.now() - t0) / 1000;
console.log(`${N} players on one sector for ${seconds} s (${url})`);
console.log(`  connected ${stats.connected}, failed ${stats.failed}, turned away ${stats.full}`);
console.log(`  claims answered: ${stats.claimMs.length} (${stats.first} first, ${stats.taken} taken, ${stats.errors} refused)`);
console.log(`  claim round trip: p50 ${pct(stats.claimMs, .5).toFixed(1)} ms, p95 ${pct(stats.claimMs, .95).toFixed(1)} ms, p99 ${pct(stats.claimMs, .99).toFixed(1)} ms`);
console.log(`  gap between position updates: p50 ${pct(stats.gaps, .5).toFixed(0)} ms, p95 ${pct(stats.gaps, .95).toFixed(0)} ms`);
console.log(`  received ${stats.received} messages, ${(stats.bytes / 1024 / 1024).toFixed(1)} MB (${(stats.bytes / secs / 1024).toFixed(0)} KB/s)`);
process.exit(0);  // sockets the server never closed would keep Node alive
