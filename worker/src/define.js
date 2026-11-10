// What a word means, for Letterfield's field notes: a few short senses from
// Wiktionary, or for a name Wiktionary doesn't know, the start of its
// Wikipedia article. The page only asks about words the player has found.
//
//   GET /v1/define/<WORD>/<th>   WORD in capitals, th the index of a theme that has it
//     → 200 {word, senses: [{pos, text}], source, title, url}
//           senses is empty, and source null, when neither site has anything
//     → 400 {error} for a word that isn't in that theme
//     → 429 {error} when one address looks up too many new words
//     → 503 {error} when Wiktionary or Wikipedia can't answer right now
//
// The words are Letterfield's own (letterfield-world.js), so there are only
// so many to look up: about 17,700 words, each fetched once and then kept in
// D1 for good, with Cloudflare's cache in front. Only a lookup D1 doesn't
// have reaches Wikimedia, counted per address (DEFINE_LOOKUPS in
// wrangler.toml). Wikimedia rate-limits shared addresses like Cloudflare's,
// so a refusal (429) is never kept: the Worker backs off for as long as it's
// told and says to try later. A WIKIMEDIA_TOKEN secret, if it's set, is sent
// as a bearer token, which Wikimedia allows more requests.
//
// Both sites' text is CC BY-SA 4.0: each answer names its source and links
// to the page, which the game shows beside it.

import { corsHeaders, hashIp, json } from './leaderboard.js';
import { MAP_VERSION, THEMES } from './letterfield-world.js';

export const DEFINE_PATH = /^\/v1\/define\/([A-Z]{2,15})\/(\d{1,3})$/;
export const UA = 'LetterfieldDefinitions/1.0 (https://games.michaelwarkentin.com/letterfield)';
export const MAX_SENSES = 3;
export const MAX_SENSE_CHARS = 220;
export const EDGE_CACHE_S = 30 * 86400;     // a found definition, in Cloudflare's cache and the browser's
export const NONE_CACHE_S = 86400;          // an empty answer, which a later edit could fill
export const NONE_RETRY_MS = 30 * 86400000; // an empty answer kept in D1 is looked up again after this
const FETCH_MS = 6000;
const THEME_SETS = THEMES.map((t) => new Set(t.words));

const WIKTIONARY = 'https://en.wiktionary.org';
const WIKIPEDIA = 'https://en.wikipedia.org';

// Until when Wikimedia asked this instance to stop (from a 429's Retry-After).
let busyUntil = 0;
export const forgetDefine = () => { busyUntil = 0; };  // for tests

class Busy extends Error {}

// Wiktionary's definitions come as HTML fragments: keep the text.
export function plain(html) {
  return String(html)
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#0?39;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/\s+/g, ' ')
    .replace(/\s+([.,;:)])/g, '$1').replace(/\(\s+/g, '(')
    .trim();
}

const clip = (s) => (s.length > MAX_SENSE_CHARS ? `${s.slice(0, MAX_SENSE_CHARS - 1).replace(/\s+\S*$/, '')}…` : s);

// A sense that only says a name is a name tells the player nothing.
const BARE_NAME = /^(?:an? |the )?(?:[\w-]+ )?(?:(?:male|female|unisex) )?(?:surname|given name|placename|place name)\b[^.]{0,60}\.?$/i;

// Up to MAX_SENSES English senses from Wiktionary's REST reply, at most two
// from any one entry, so a word with a noun and a verb shows both.
export function wiktionarySenses(reply) {
  const entries = (reply && Array.isArray(reply.en) ? reply.en : []).filter((e) => e && Array.isArray(e.definitions));
  const picked = entries.map((e) => e.definitions
    .map((d) => plain(d && d.definition))
    .filter((t) => t.length > 1 && !BARE_NAME.test(t))
    .slice(0, 2)
    .map((text) => ({ pos: String(e.partOfSpeech || '').toLowerCase(), text: clip(text) })));
  const senses = [];
  // One from each entry first, then seconds.
  for (let round = 0; round < 2; round++) {
    for (const list of picked) if (list[round] && senses.length < MAX_SENSES) senses.push(list[round]);
  }
  return senses;
}

async function getJson(fetcher, url, env) {
  if (Date.now() < busyUntil) throw new Busy();
  const headers = { 'User-Agent': UA, Accept: 'application/json' };
  if (env.WIKIMEDIA_TOKEN) headers.Authorization = `Bearer ${env.WIKIMEDIA_TOKEN}`;
  let res;
  try {
    res = await fetcher(url, { headers, signal: AbortSignal.timeout(FETCH_MS) });
  } catch {
    throw new Busy();
  }
  if (res.status === 404) return null;
  if (res.status === 429) {
    const after = Number(res.headers.get('Retry-After'));
    busyUntil = Date.now() + (Number.isFinite(after) && after > 0 ? Math.min(after, 600) : 60) * 1000;
    throw new Busy();
  }
  if (!res.ok) throw new Busy();
  try { return await res.json(); } catch { throw new Busy(); }
}

const titleCase = (w) => w[0] + w.slice(1).toLowerCase();

// Wiktionary first, as written in lower case and then as a name ("Odin").
async function fromWiktionary(word, env, fetcher) {
  for (const form of [word.toLowerCase(), titleCase(word)]) {
    const reply = await getJson(fetcher, `${WIKTIONARY}/api/rest_v1/page/definition/${encodeURIComponent(form)}`, env);
    const senses = wiktionarySenses(reply);
    if (senses.length) return { senses, source: 'wiktionary', title: form, url: `${WIKTIONARY}/wiki/${encodeURIComponent(form)}#English` };
  }
  return null;
}

// Then Wikipedia, searching for the word beside its theme's name ("cronkite
// Broadcast" finds Walter Cronkite). The article's title must contain the
// word, spaces aside, so a search that wanders off is no answer.
async function fromWikipedia(word, theme, env, fetcher) {
  const q = new URLSearchParams({
    action: 'query', format: 'json', formatversion: '2', redirects: '1',
    generator: 'search', gsrsearch: `${word.toLowerCase()} ${theme}`, gsrlimit: '1', gsrnamespace: '0',
    prop: 'extracts|pageprops', ppprop: 'disambiguation', exintro: '1', explaintext: '1', exsentences: '2',
  });
  const reply = await getJson(fetcher, `${WIKIPEDIA}/w/api.php?${q}`, env);
  const page = reply && reply.query && Array.isArray(reply.query.pages) ? reply.query.pages[0] : null;
  if (!page || typeof page.title !== 'string' || (page.pageprops && 'disambiguation' in page.pageprops)) return null;
  if (!page.title.toUpperCase().replace(/[^A-Z]/g, '').includes(word)) return null;
  const text = plain(page.extract || '');
  if (text.length < 2) return null;
  const title = page.title;
  return { senses: [{ pos: '', text: clip(text) }], source: 'wikipedia', title, url: `${WIKIPEDIA}/wiki/${encodeURIComponent(title.replace(/ /g, '_'))}` };
}

// D1 keeps each answer by word and context: '' for Wiktionary's, which is
// the same in every theme, or the theme's name for one found through
// Wikipedia's search with it. An empty answer is kept too, with context
// '?<theme>', and asked again after NONE_RETRY_MS.
async function stored(db, word, theme, now) {
  if (!db) return null;
  const rows = (await db.prepare('SELECT context, body, fetched_at FROM definitions WHERE word = ? AND context IN (?, ?, ?)')
    .bind(word, '', theme, `?${theme}`).all()).results || [];
  const by = Object.fromEntries(rows.map((r) => [r.context, r]));
  for (const c of ['', theme]) if (by[c]) return JSON.parse(by[c].body);
  const none = by[`?${theme}`];
  if (none && now - none.fetched_at < NONE_RETRY_MS) return { senses: [], source: null, title: null, url: null };
  return null;
}

async function store(db, word, context, body, now) {
  if (!db) return;
  try {
    await db.prepare('INSERT OR REPLACE INTO definitions (word, context, body, fetched_at) VALUES (?, ?, ?, ?)')
      .bind(word, context, JSON.stringify(body), now).run();
  } catch (error) {
    console.error(error);
  }
}

// Looks a word up, from D1 if it can. `theme` is the theme's name.
export async function lookUp(env, word, theme, { now = Date.now(), fetcher = fetch, request = null } = {}) {
  const kept = await stored(env.DB, word, theme, now);
  if (kept) return kept;
  if (request && env.DEFINE_LOOKUPS) {
    let ok = true;
    try { ok = (await env.DEFINE_LOOKUPS.limit({ key: `define:${await hashIp(request, env.IP_SALT)}` })).success !== false; } catch { /* let it through */ }
    if (!ok) return 'limited';
  }
  const wikt = await fromWiktionary(word, env, fetcher);
  if (wikt) { await store(env.DB, word, '', wikt, now); return wikt; }
  const wiki = await fromWikipedia(word, theme, env, fetcher);
  if (wiki) { await store(env.DB, word, theme, wiki, now); return wiki; }
  await store(env.DB, word, `?${theme}`, { senses: [] }, now);
  return { senses: [], source: null, title: null, url: null };
}

function edgeCache() {
  try { return globalThis.caches?.default ?? null; } catch { return null; }
}

// Answers /v1/define/..., or returns null for any other path.
export function routeDefine(request, env, options = {}) {
  const url = new URL(request.url);
  const m = url.pathname.match(DEFINE_PATH);
  if (!m && !url.pathname.startsWith('/v1/define')) return null;
  return answer(request, env, url, m, options);
}

async function answer(request, env, url, m, options) {
  const cors = corsHeaders(request, env);
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
  if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405, cors);
  if (!m) return json({ error: 'not found' }, 404, cors);
  const word = m[1], th = Number(m[2]);
  if (!(th < THEMES.length) || !THEME_SETS[th].has(word)) return json({ error: 'not a word in that theme' }, 400, cors);
  const reply = (body, maxAge) => new Response(body, {
    headers: { ...cors, 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': `public, max-age=${maxAge}` },
  });
  const cache = edgeCache();
  const cacheKey = new Request(`https://${url.host}/_cache/define/m${MAP_VERSION}/${word}/${th}`);
  if (cache) {
    try { const hit = await cache.match(cacheKey); if (hit) return reply(await hit.text(), Number(hit.headers.get('X-Max-Age')) || NONE_CACHE_S); } catch { /* a miss */ }
  }
  let found;
  try {
    found = await lookUp(env, word, THEMES[th].name, { ...options, request });
  } catch (error) {
    if (error instanceof Busy) return json({ error: 'try again later' }, 503, { ...cors, 'Retry-After': '60' });
    throw error;
  }
  if (found === 'limited') return json({ error: 'slow down' }, 429, cors);
  const body = JSON.stringify({ word, senses: found.senses, source: found.source ?? null, title: found.title ?? null, url: found.url ?? null });
  const maxAge = found.senses.length ? EDGE_CACHE_S : NONE_CACHE_S;
  if (cache) {
    try { await cache.put(cacheKey, new Response(body, { headers: { 'Cache-Control': `public, max-age=${maxAge}`, 'X-Max-Age': String(maxAge) } })); } catch { /* not cached */ }
  }
  return reply(body, maxAge);
}
