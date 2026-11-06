// Letterfield's survey log: every word charted in the shared survey, with
// where, by whom (their initials) and when, for letterfield-log.html. See "The
// log" in SURVEY.md.
//
//   GET /v1/survey/log/day/<day>     words charted in each UTC hour of a day (days since 1970):
//                                    {day, hours: [24 counts], total}
//   GET /v1/survey/log/hour/<hour>   the words charted in one UTC hour (hours since 1970), oldest
//       [?after=<at>~<key>]          first, LOG_PAGE at a time: {hour, entries, places, themes, next}
//
// Entries are [w, x, y, d, s, initials, at, th]: the claim as the game gets
// it from a sector, plus its theme. `places` names each territory ('rx,ry'),
// and `themes` gives each theme used as [name, hue], so the page needs none of
// the map's data. `next`, when there is more, is the `after` for the next page.
//
// How claims get here: each Sector keeps its own claims as before, and copies
// new ones to D1 at most every LOG_MS, from an alarm (survey.js, flushLog). It
// remembers the last claim D1 accepted, so a failed write is only tried again
// later, and a sector that charted words before the log existed sends those
// the first time it wakes. Rows are keyed by (at, key), so a resent row is
// ignored. The table is ordered by time (migrations/0003_survey_log.sql), so
// reading an hour reads only that hour's rows.
//
// Hours and days that are over don't change, so once one ended SETTLED_MS ago
// its answer is cached for a day: in browsers, in each Worker instance, and in
// Cloudflare's cache when the Worker is on a custom domain (the Cache API does
// nothing on workers.dev). The hour or day still running is cached for a few
// seconds.

import { corsHeaders, json } from './leaderboard.js';
import { RC, THEMES, VOCAB, fdiv, regionName, regionTheme } from './letterfield-world.js';

export const LOG_MS = 30000;            // a sector copies new claims to D1 at most this often
export const LOG_BATCH = 240;           // claims copied at once; more go a second later
export const LOG_ROWS_PER_INSERT = 12;  // D1 takes 100 bound values per statement, and a row has 8
export const LOG_RETRY_MAX_MS = 600000; // a sector whose writes fail tries again at most this far apart
export const LOG_PAGE = 500;            // entries per page of an hour
export const SETTLED_MS = 3600000;      // an hour or day that ended this long ago is cached for a day
export const LIVE_CACHE_S = 15;         // seconds the hour or day still running is cached for
export const MEMO_MAX = 300;            // answers each Worker instance keeps
export const HOUR_MS = 3600000;
export const DAY_MS = 86400000;
export const LOG_DAY_PATH = /^\/v1\/survey\/log\/day\/(\d{1,6})$/;
export const LOG_HOUR_PATH = /^\/v1\/survey\/log\/hour\/(\d{1,8})$/;
const CURSOR = /^(\d{1,15})~([A-Z]{3,12}~-?\d{1,10}~-?\d{1,10}~[0-7])$/;

// Copies claims, as a sector stores them, to D1 in one batch, which D1 runs
// as one transaction: all of them or none.
export async function writeLog(db, rows) {
  const statements = [];
  for (let i = 0; i < rows.length; i += LOG_ROWS_PER_INSERT) {
    const part = rows.slice(i, i + LOG_ROWS_PER_INSERT);
    statements.push(
      db.prepare(`INSERT OR IGNORE INTO survey_log (at, key, w, x, y, d, s, initials) VALUES ${part.map(() => '(?, ?, ?, ?, ?, ?, ?, ?)').join(', ')}`)
        .bind(...part.flatMap((r) => [r.at, r.key, r.w, r.x, r.y, r.d, r.s, r.initials])),
    );
  }
  if (statements.length) await db.batch(statements);
}

export const HOUR_SQL = `SELECT at, key, w, x, y, d, s, initials FROM survey_log
  WHERE at >= ? AND at < ? ORDER BY at, key LIMIT ?`;
export const HOUR_AFTER_SQL = `SELECT at, key, w, x, y, d, s, initials FROM survey_log
  WHERE at >= ? AND at < ? AND (at, key) > (?, ?) ORDER BY at, key LIMIT ?`;
export const DAY_SQL = `SELECT at / ${HOUR_MS} AS h, COUNT(*) AS n FROM survey_log
  WHERE at >= ? AND at < ? GROUP BY h`;

// One hour's entries, a page at a time, with the names the page shows.
export async function readHour(db, hour, after = null) {
  const from = hour * HOUR_MS, to = from + HOUR_MS;
  const statement = after
    ? db.prepare(HOUR_AFTER_SQL).bind(from, to, after.at, after.key, LOG_PAGE + 1)
    : db.prepare(HOUR_SQL).bind(from, to, LOG_PAGE + 1);
  const rows = (await statement.all()).results;
  const more = rows.length > LOG_PAGE;
  if (more) rows.length = LOG_PAGE;
  const places = {}, themes = {};
  const entries = rows.map((r) => {
    const rx = fdiv(r.x, RC), ry = fdiv(r.y, RC), place = `${rx},${ry}`;
    const th = r.s ? VOCAB.get(r.w) : regionTheme(rx, ry);
    places[place] ??= regionName(rx, ry);
    themes[th] ??= [THEMES[th].name, THEMES[th].hue];
    return [r.w, r.x, r.y, r.d, r.s, r.initials, r.at, th];
  });
  const last = rows.at(-1);
  return { hour, entries, places, themes, next: more ? `${last.at}~${last.key}` : null };
}

// How many words were charted in each hour of a UTC day.
export async function readDay(db, day) {
  const from = day * DAY_MS;
  const hours = new Array(24).fill(0);
  for (const { h, n } of (await db.prepare(DAY_SQL).bind(from, from + DAY_MS).all()).results) hours[h - day * 24] = n;
  return { day, hours, total: hours.reduce((a, b) => a + b, 0) };
}

// Answers kept by this Worker instance: url → {body, until, maxAge}.
const memo = new Map();
export const forgetLog = () => memo.clear();  // for tests

// Cloudflare's cache, which only holds anything on a custom domain.
function edgeCache() {
  try { return globalThis.caches?.default ?? null; } catch { return null; }
}

// Answers the log's paths, or returns null for any other path.
export function routeLog(request, env, now = Date.now()) {
  const url = new URL(request.url);
  const day = url.pathname.match(LOG_DAY_PATH), hour = url.pathname.match(LOG_HOUR_PATH);
  if (!(day || hour) || !env.DB) return null;
  const cors = corsHeaders(request, env);
  if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405, cors);
  let ends, read, key;
  if (day) {
    const d = Number(day[1]);
    if (d > fdiv(now, DAY_MS)) return json({ error: 'that day has not started' }, 400, cors);
    ends = (d + 1) * DAY_MS;
    read = () => readDay(env.DB, d);
    key = `day/${d}`;
  } else {
    const h = Number(hour[1]);
    if (h > fdiv(now, HOUR_MS)) return json({ error: 'that hour has not started' }, 400, cors);
    const after = url.searchParams.get('after');
    let cursor = null;
    if (after !== null) {
      const m = after.match(CURSOR);
      if (!m) return json({ error: 'bad cursor' }, 400, cors);
      cursor = { at: Number(m[1]), key: m[2] };
    }
    ends = (h + 1) * HOUR_MS;
    read = () => readHour(env.DB, h, cursor);
    key = `hour/${h}${cursor ? `?after=${after}` : ''}`;
  }
  const settled = now >= ends + SETTLED_MS;
  return answer(key, settled ? 86400 : LIVE_CACHE_S, read, cors, now);
}

async function answer(key, maxAge, read, cors, now) {
  const reply = (body) => new Response(body, {
    headers: { ...cors, 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': `public, max-age=${maxAge}` },
  });
  const kept = memo.get(key);
  if (kept && kept.until > now) return reply(kept.body);
  memo.delete(key);
  const cache = edgeCache(), cacheKey = new Request(`https://survey-log.cache/${key}`);
  let body = null;
  if (cache) {
    try { const hit = await cache.match(cacheKey); if (hit) body = await hit.text(); } catch { /* treated as a miss */ }
  }
  if (body === null) {
    body = JSON.stringify(await read());
    // Stored without CORS headers, which differ by origin; each answer adds its own.
    if (cache) {
      try { await cache.put(cacheKey, new Response(body, { headers: { 'Cache-Control': `public, max-age=${maxAge}` } })); } catch { /* not cached */ }
    }
  }
  memo.set(key, { body, until: now + maxAge * 1000 });
  while (memo.size > MEMO_MAX) memo.delete(memo.keys().next().value);
  return reply(body);
}
