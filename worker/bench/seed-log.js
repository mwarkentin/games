// Made-up history for a test copy of the survey log, to try the log page's
// weeks, months and years without waiting for real players. It prints SQL for
// `wrangler d1 execute`, for your local database or the Worker Previews' one,
// never production's:
//
//   node worker/bench/seed-log.js [days] [explore] > /tmp/seed.sql
//   cd worker
//   npx wrangler@4.151.0 d1 execute games-survey-log --local --file /tmp/seed.sql
//   npx wrangler@4.151.0 d1 execute games-survey-log-previews --remote \
//     --config wrangler.previews-migrations.toml --file /tmp/seed.sql
//
// Words are real ones at their real places, so each links to the map, spread
// over the last `days` days (45 by default), busier lately and in the
// evenings (UTC), with a busy last hour for the minute-by-minute view.
// Running it again adds another set, since the times move with the clock.
// The database's triggers keep the log's counts as the rows go in.
//
// With `explore`, for the timelapse, surveyors instead push out from the
// origin a territory at a time, a few dozen words a sitting, and finish the
// territories they keep coming back to, each with its supernova as a sector
// records it.

import { RG, chunk, keyOf } from '../src/letterfield-world.js';

const DAYS = Number(process.argv[2] || 45), EXPLORE = process.argv[3] === 'explore';
const HOUR = 3600000, now = Date.now(), start = now - DAYS * 86400000;
const INITIALS = ['ZED', 'AMY', 'KIT', '', 'BOB', 'SIS', 'ZED', 'AMY', 'JOE', 'ZED', 'LIV', 'PAT', 'KIT', 'ROO'];
const PER_STATEMENT = 150;  // D1 takes up to 100 KB of SQL in a statement

let seed = 20261108;
const random = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const rows = [], seen = new Set();

function chart(at) {
  for (let tries = 0; tries < 5; tries++) {
    const cx = Math.floor(random() * 40) - 20, cy = Math.floor(random() * 40) - 20, words = chunk(cx, cy).words;
    const { w, x, y, d } = words[Math.floor(random() * words.length)], key = keyOf(w, x, y, d);
    if (seen.has(key)) continue;
    seen.add(key);
    const initials = INITIALS[Math.floor(random() * INITIALS.length)];
    rows.push(`(${at}, '${key}', '${w}', ${x}, ${y}, ${d}, 0, '${initials}')`);
    return;
  }
}

// A territory's hidden words, in the order surveyors happen on them.
function hidden(rx, ry) {
  const words = [];
  for (let cy = ry * RG; cy < ry * RG + RG; cy++) for (let cx = rx * RG; cx < rx * RG + RG; cx++) words.push(...chunk(cx, cy).words);
  for (let i = words.length - 1; i > 0; i--) { const j = Math.floor(random() * (i + 1)); [words[i], words[j]] = [words[j], words[i]]; }
  return words;
}
const novas = [];
function explore() {
  const places = new Map(), RADIUS = 6;
  const place = (rx, ry) => {
    const k = `${rx},${ry}`;
    if (!places.has(k)) places.set(k, { rx, ry, left: hidden(rx, ry), done: 0, first: 0, by: new Map() });
    return places.get(k);
  };
  for (let t = Math.floor(start / HOUR) * HOUR; t < now - HOUR; t += HOUR) {
    const f = (t - start) / (now - start), hour = new Date(t).getUTCHours();
    const sittings = Math.floor((0.6 + 2.2 * f) * (hour >= 22 || hour <= 3 ? 2 : hour >= 8 && hour <= 12 ? 0.2 : 1) * random() * 2);
    for (let i = 0; i < sittings; i++) {
      // Nearer the origin more often, and further out as the days go by.
      const r = (0.6 + RADIUS * f) * random() ** 1.6, a = random() * Math.PI * 2;
      const p = place(Math.round(r * Math.cos(a)), Math.round(r * Math.sin(a)));
      const initials = INITIALS[Math.floor(random() * INITIALS.length)], k = 6 + Math.floor(random() * 30);
      let at = Math.floor(t + random() * HOUR * 0.8);
      for (let j = 0; j < k && p.left.length; j++) {
        const { w, x, y, d } = p.left.pop();
        at += 20000 + Math.floor(random() * 90000);
        rows.push(`(${at}, '${keyOf(w, x, y, d)}', '${w}', ${x}, ${y}, ${d}, 0, '${initials}')`);
        p.first ||= at; p.done++;
        if (initials) p.by.set(initials, (p.by.get(initials) || 0) + 1);
        if (!p.left.length) {
          const [top, topN] = [...p.by].sort((m, n) => n[1] - m[1])[0] ?? ['', 0];
          novas.push(`(${p.rx}, ${p.ry}, ${at}, '${w}', ${x}, ${y}, ${d}, '${initials}', ${p.first}, ${p.done}, ${p.by.size}, '${top}', ${topN})`);
        }
      }
    }
  }
}

if (EXPLORE) explore();
else for (let t = Math.floor(start / HOUR) * HOUR; t < now - HOUR; t += HOUR) {
  const hour = new Date(t).getUTCHours(), day = (t - start) / 86400000;
  const rate = (0.4 + day / 10) * (hour >= 22 || hour <= 3 ? 2.2 : hour >= 8 && hour <= 12 ? 0.4 : 1);
  const n = Math.floor(rate * (0.5 + random()));
  for (let i = 0; i < n; i++) chart(Math.floor(t + random() * HOUR));
}
if (!EXPLORE) for (let i = 0; i < 45; i++) chart(Math.floor(now - HOUR + random() * (HOUR - 60000)));

for (let i = 0; i < rows.length; i += PER_STATEMENT) {
  console.log(`INSERT OR IGNORE INTO survey_log (at, key, w, x, y, d, s, initials) VALUES\n${rows.slice(i, i + PER_STATEMENT).join(',\n')};`);
}
for (let i = 0; i < novas.length; i += PER_STATEMENT) {
  console.log(`INSERT OR IGNORE INTO survey_log_novas (rx, ry, at, w, x, y, d, initials, first, words, surveyors, top, top_n) VALUES\n${novas.slice(i, i + PER_STATEMENT).join(',\n')};`);
}
console.error(`${rows.length} words and ${novas.length} supernovas over ${DAYS} days`);
