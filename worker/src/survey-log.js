// Letterfield's survey log: every word charted in the shared survey, with
// where, by whom (their initials) and when, for letterfield-log.html. See "The
// log" in SURVEY.md.
//
//   GET /v1/survey/log/day/<day>     words charted in each UTC hour of a day (days since 1970):
//                                    {day, hours: [24 counts], total}
//   GET /v1/survey/log/hour/<hour>   the words charted in one UTC hour (hours since 1970), oldest
//       [?after=<at>~<key>]          first, LOG_PAGE at a time: {hour, entries, places, themes, next}
//   GET /v1/survey/log/month/<month> words charted in each UTC hour of a UTC month (months since
//                                    January 1970), hours with none left out:
//                                    {month, hours: [[hour, words, world], ...]}, where world is
//                                    how many were hidden words in the shared world
//   GET /v1/survey/log/span          the first and latest UTC hours with words in them, or nulls:
//                                    {first, last}, where all time starts
//   GET /v1/survey/log/top/<from>/<to>   the most charted over UTC days from..to-1 (days since
//                                    1970): {from, to, surveyors: [[initials, words], ...],
//                                    territories: [[rx, ry, name, th, words], ...],
//                                    themes: [[th, name, hue, words], ...], hidden}
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
// ignored. The table is ordered by time (migrations-log/0001_survey_log.sql, in LOG_DB), so
// reading an hour reads only that hour's rows.
//
// The longer views read counts, not the log: triggers in D1 keep words per
// hour, per day per set of initials and per day per territory as rows go in
// (migrations-log/0002_survey_log_counts.sql). So a month reads at most 744
// rows, whatever happened in it.
//
// Hours, days and months that are over don't change, so once one ended
// SETTLED_MS ago its answer is cached for a day: in browsers, in each Worker
// instance, and in Cloudflare's cache when the Worker is on a custom domain
// (the Cache API does nothing on workers.dev). One still running is cached
// for a few seconds, or a few minutes for top lists over more than a couple
// of days, which change slowly and read more.

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
export const LOG_MONTH_PATH = /^\/v1\/survey\/log\/month\/(\d{1,5})$/;
export const LOG_TOP_PATH = /^\/v1\/survey\/log\/top\/(\d{1,6})\/(\d{1,6})$/;
export const LOG_SPAN_PATH = '/v1/survey/log/span';
export const SPAN_CACHE_S = 300;        // seconds the span is cached for: its latest hour can lag this much
export const TOP_N = 10;                // surveyors and territories in a top list
export const TOP_MAX_DAYS = 3660;       // the longest range a top list covers
export const TOP_SLOW_CACHE_S = 600;    // seconds a running top list over more than 2 days is cached for
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
export const HOURS_SQL = `SELECT hour, n, world FROM survey_log_hours
  WHERE hour >= ? AND hour < ? AND n > 0 ORDER BY hour`;
export const FIRST_SQL = 'SELECT hour FROM survey_log_hours WHERE n > 0 ORDER BY hour LIMIT 1';
export const LAST_SQL = 'SELECT hour FROM survey_log_hours WHERE n > 0 ORDER BY hour DESC LIMIT 1';
export const SURVEYORS_SQL = `SELECT initials, SUM(n) AS n FROM survey_log_surveyors
  WHERE day >= ? AND day < ? GROUP BY initials HAVING SUM(n) > 0 ORDER BY SUM(n) DESC, initials LIMIT ${TOP_N}`;
export const TERRITORIES_SQL = `SELECT rx, ry, SUM(n) AS n FROM survey_log_territories
  WHERE day >= ? AND day < ? GROUP BY rx, ry HAVING SUM(n) > 0`;

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
  const hours = new Array(24).fill(0);
  for (const r of (await db.prepare(HOURS_SQL).bind(day * 24, day * 24 + 24).all()).results) hours[r.hour - day * 24] = r.n;
  return { day, hours, total: hours.reduce((a, b) => a + b, 0) };
}

// A UTC month's first and last-plus-one hour.
export const monthHours = (month) => [Date.UTC(1970, month, 1) / HOUR_MS, Date.UTC(1970, month + 1, 1) / HOUR_MS];

// Words charted in each hour of a UTC month, leaving out hours with none.
export async function readMonth(db, month) {
  const [from, to] = monthHours(month);
  const rows = (await db.prepare(HOURS_SQL).bind(from, to).all()).results;
  return { month, hours: rows.map((r) => [r.hour, r.n, r.world]) };
}

// The first and latest hours with words in them. The log began on
// November 6, 2026, but sectors send words from before then the first time
// they wake, so all time starts wherever the words do.
export async function readSpan(db) {
  const [first, last] = await Promise.all([db.prepare(FIRST_SQL).first('hour'), db.prepare(LAST_SQL).first('hour')]);
  return { first: first ?? null, last: last ?? null };
}

// The most charted over a run of UTC days: surveyors by their initials,
// territories by hidden words charted in them, and every theme those
// territories have. Initials aren't unique, so a "surveyor" is everyone who
// typed the same three letters.
export async function readTop(db, from, to) {
  const [surveyors, territories] = await Promise.all([
    db.prepare(SURVEYORS_SQL).bind(from, to).all(),
    db.prepare(TERRITORIES_SQL).bind(from, to).all(),
  ]);
  const byTheme = new Map();
  let hidden = 0;
  for (const r of territories.results) {
    const th = regionTheme(r.rx, r.ry);
    byTheme.set(th, (byTheme.get(th) ?? 0) + r.n);
    hidden += r.n;
  }
  const top = territories.results.sort((a, b) => b.n - a.n || a.ry - b.ry || a.rx - b.rx).slice(0, TOP_N);
  return {
    from, to, hidden,
    surveyors: surveyors.results.map((r) => [r.initials, r.n]),
    territories: top.map((r) => [r.rx, r.ry, regionName(r.rx, r.ry), regionTheme(r.rx, r.ry), r.n]),
    themes: [...byTheme].sort((a, b) => b[1] - a[1] || a[0] - b[0]).map(([th, n]) => [th, THEMES[th].name, THEMES[th].hue, n]),
  };
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
  const month = url.pathname.match(LOG_MONTH_PATH), top = url.pathname.match(LOG_TOP_PATH), span = url.pathname === LOG_SPAN_PATH;
  if (!(day || hour || month || top || span) || !env.LOG_DB) return null;
  const cors = corsHeaders(request, env);
  if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405, cors);
  let ends, read, key, live = LIVE_CACHE_S;
  if (span) return answer('span', SPAN_CACHE_S, () => readSpan(env.LOG_DB), cors, now);
  if (month) {
    const m = Number(month[1]), [from, to] = monthHours(m);
    if (from > fdiv(now, HOUR_MS)) return json({ error: 'that month has not started' }, 400, cors);
    ends = to * HOUR_MS;
    read = () => readMonth(env.LOG_DB, m);
    key = `month/${m}`;
  } else if (top) {
    const from = Number(top[1]), to = Number(top[2]);
    if (!(from < to) || to - from > TOP_MAX_DAYS) return json({ error: 'bad range of days' }, 400, cors);
    if (from > fdiv(now, DAY_MS)) return json({ error: 'that day has not started' }, 400, cors);
    ends = to * DAY_MS;
    read = () => readTop(env.LOG_DB, from, to);
    key = `top/${from}/${to}`;
    if (to - from > 2) live = TOP_SLOW_CACHE_S;
  } else if (day) {
    const d = Number(day[1]);
    if (d > fdiv(now, DAY_MS)) return json({ error: 'that day has not started' }, 400, cors);
    ends = (d + 1) * DAY_MS;
    read = () => readDay(env.LOG_DB, d);
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
    read = () => readHour(env.LOG_DB, h, cursor);
    key = `hour/${h}${cursor ? `?after=${after}` : ''}`;
  }
  const settled = now >= ends + SETTLED_MS;
  return answer(key, settled ? 86400 : live, read, cors, now);
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
