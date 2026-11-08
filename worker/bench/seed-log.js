// Made-up history for a test copy of the survey log, to try the log page's
// weeks, months and years without waiting for real players. It prints SQL for
// `wrangler d1 execute`, for your local database or the Worker Previews' one,
// never production's:
//
//   node worker/bench/seed-log.js [days] > /tmp/seed.sql
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

import { chunk, keyOf } from '../src/letterfield-world.js';

const DAYS = Number(process.argv[2] || 45);
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

for (let t = Math.floor(start / HOUR) * HOUR; t < now - HOUR; t += HOUR) {
  const hour = new Date(t).getUTCHours(), day = (t - start) / 86400000;
  const rate = (0.4 + day / 10) * (hour >= 22 || hour <= 3 ? 2.2 : hour >= 8 && hour <= 12 ? 0.4 : 1);
  const n = Math.floor(rate * (0.5 + random()));
  for (let i = 0; i < n; i++) chart(Math.floor(t + random() * HOUR));
}
for (let i = 0; i < 45; i++) chart(Math.floor(now - HOUR + random() * (HOUR - 60000)));

for (let i = 0; i < rows.length; i += PER_STATEMENT) {
  console.log(`INSERT OR IGNORE INTO survey_log (at, key, w, x, y, d, s, initials) VALUES\n${rows.slice(i, i + PER_STATEMENT).join(',\n')};`);
}
console.error(`${rows.length} words over ${DAYS} days`);
