// Link-preview cards for Letterfield finds (see README.md and
// docs/link-previews.md):
//
//   GET /f/<slug>        a small page whose og:image is the card; it sends
//                        people on to the game at that word
//   GET /f/<slug>.png    the card, 1200×630
//   GET /f/d/<slug>…     the same, with a dark card (a dark page's share)
//   GET /v/…             the same for a view of the survey log: a surveyor's,
//                        theme's, guild's or territory's page, or the
//                        Supernovas tab (see view.js)
//
// <slug> is the game's own fragment, f-<word>-<x>-<y>-<d>. Only words really
// on the map are drawn. Everyone, bot or person, gets the same page: link
// unfurlers read its tags and don't run its refresh or script.
//
// The renderer is passed in (index.js uses resvg), so tests can run this in
// Node.

import { edgeCache, hashAddress } from '../../worker/src/leaderboard.js';
import { MAP_VERSION, RC, THEMES, keyOf, regionName } from '../../worker/src/letterfield-world.js';
import { SECTOR, TOTALS_PATH, inArea } from '../../worker/src/survey.js';
import { CARD_WORDS, day, esc, findSvg, parseFind, progress } from './card.js';
import { logPaths, nameOf, pagePath, parseView, summarize, viewSvg } from './view.js';

export const DEFAULT_SITE = 'https://games.michaelwarkentin.com';
export const PATH = /^\/f\/(d\/)?([a-z0-9-]{1,48}?)(\.png)?$/;
export const ASK_MS = 1500;          // how long a card waits for the survey before leaving its lines off
export const TOTALS_MS = 60_000;     // how long one Worker instance keeps the shared map's totals
export const PAGE_MS = 60_000;       // how long the page is kept at the edge
export const STALE_IMAGE_MS = 300_000; // how long a card asked for with an old state is kept
export const LOG_MS = 3000;          // how long a view's card waits for the log before standing in the game's own
export const DEFAULT_LOG = 'https://api.games.michaelwarkentin.com';
const IMAGE_FOREVER = 'public, max-age=31536000, immutable';

const site = (env) => (env.SITE_URL || DEFAULT_SITE).replace(/\/$/, '');

export async function handle(request, env, ctx, render) {
  const url = new URL(request.url);
  if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('method not allowed', { status: 405 });
  if (url.pathname === '/') return Response.redirect(`${site(env)}/letterfield`, 302);
  if (url.pathname.startsWith('/v/')) {
    const v = parseView(url.pathname, Date.now(), url.search);
    if (!v) return new Response('not found', { status: 404 });
    if (v.png) return cached(request.url, ctx, () => viewImage(request, env, render, v));
    // A page is kept by its own address: a guild's name, and nothing else, from the query.
    const q = v.named ? `name=${v.named.join('-')}` : '';
    return cached(url.origin + url.pathname + (q && `?${q}`), ctx, () => viewPage(env, v, url, q));
  }
  const m = PATH.exec(url.pathname);
  if (!m) return new Response('not found', { status: 404 });
  const dark = !!m[1], slug = m[2], e = parseFind(slug);
  if (m[3]) {
    if (!e) return new Response('not on the map', { status: 404 });
    return cached(request.url, ctx, () => image(request, env, ctx, render, e, slug, dark));
  }
  return cached(url.origin + url.pathname, ctx, () => page(env, e, slug, dark, url));
}

// What the edge keeps for this address, or make()'s answer, kept there when
// it's a 200 (never a stand-in's redirect).
async function cached(address, ctx, make) {
  const cache = edgeCache(), key = new Request(address), hit = await cache?.match(key);
  if (hit) return hit;
  const response = await make();
  if (cache && response.status === 200) ctx.waitUntil(cache.put(key, response.clone()));
  return response;
}

// ---------- What the survey knows ----------

// The word's claim, from its sector's live record (the survey log can be 30 s
// behind, and apps fetch a preview the moment Share is tapped): { initials,
// at }, null if nobody has charted it, or undefined if it couldn't be asked.
export async function claimOf(env, e) {
  const answer = await askSector(env, e.x, e.y, `/claim/${encodeURIComponent(keyOf(e.w, e.x, e.y, e.d))}`);
  if (!answer || (answer.status !== 200 && answer.status !== 404)) return undefined;
  const c = await answer.json().catch(() => null);
  // Only the sector's own answer means nobody: a plain 404 is a sector from
  // before it knew this path (the share Worker deployed first), so unknown.
  if (answer.status === 404) return c?.error === 'not charted' ? null : undefined;
  return c && typeof c.initials === 'string' && Number.isFinite(c.at) ? { initials: c.initials, at: c.at } : undefined;
}

// A territory's supernova, from its sector's own record: a supernova is
// shared from the game seconds after it goes off, and the log only has it
// once the sector next copies to it (up to 30 s later), so a card asked for
// then would otherwise be the plain one. The log's array shape, [rx, ry, at,
// w, x, y, d, initials, first, words, surveyors, top, topN, th], or null.
export async function novaOf(env, rx, ry) {
  const answer = await askSector(env, rx * RC, ry * RC, `/nova/${rx}/${ry}`);
  if (answer?.status !== 200) return null;
  const n = (await answer.json().catch(() => null))?.nova;
  const ok = Array.isArray(n) && n.length === 14 && n[0] === rx && n[1] === ry
    && [2, 4, 5, 6, 8, 9, 10, 12, 13].every((i) => Number.isInteger(n[i])) && [3, 7, 11].every((i) => typeof n[i] === 'string');
  return ok ? n : null;
}

// The answer of the sector holding cell (x, y) on one of its internal paths,
// or null. Only sectors in the shared world are asked, so a card never wakes
// (and makes storage for) a sector nobody has played in.
function askSector(env, x, y, path) {
  const sx = Math.floor(x / SECTOR), sy = Math.floor(y / SECTOR);
  if (!env.SECTORS || !inArea(sx, sy)) return null;
  return ask(() => env.SECTORS.get(env.SECTORS.idFromName(`${sx},${sy}`)).fetch(`https://sector${path}`));
}

// The shared map's totals, from the Atlas, kept for a minute per instance.
let totalsKept = null;
export function forgetTotals() { totalsKept = null; }
export async function totalsOf(env, now = Date.now()) {
  if (!env.ATLAS) return null;
  if (totalsKept && now - totalsKept.at < TOTALS_MS) return totalsKept.totals;
  const answer = await ask(() => env.ATLAS.get(env.ATLAS.idFromName('atlas')).fetch(`https://atlas${TOTALS_PATH}`));
  const totals = answer?.status === 200 ? await answer.json().catch(() => null) : null;
  if (totals) totalsKept = { at: now, totals };
  return totals;
}

// call()'s answer, or null if it fails or takes longer than ms.
async function ask(call, ms = ASK_MS) {
  let timer;
  try {
    return await Promise.race([call(), new Promise((resolve) => { timer = setTimeout(resolve, ms, null); })]);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function stateOf(env, e) {
  const [claim, totals] = await Promise.all([claimOf(env, e), totalsOf(env)]);
  return { claim, progressText: progress(totals) };
}

// A short name for what the card says beyond the map, so its image URL
// changes when that does: charted (with whose initials and the day), not yet,
// or unknown, and the progress as the card rounds it.
export function stateToken({ claim, progressText }) {
  const who = claim ? `c${claim.initials}.${Math.floor(claim.at / 86_400_000)}` : claim === null ? 'o' : 'u';
  const pct = progressText ? progressText.split(' ')[0].replace('%', '').toLowerCase() : 'x';
  return `${who}.${pct}.w${CARD_WORDS}`;
}

// ---------- The page ----------

async function page(env, e, slug, dark, url) {
  const self = url.origin + url.pathname;
  // Not a word on today's map (a link from an older map, or mistyped): the
  // game's own card, and the game.
  if (!e) {
    return htmlPage({
      title: 'Letterfield', description: 'A word search the size of a world, charted together.',
      image: `${site(env)}/previews/letterfield.jpg`, alt: 'Letterfield', png: false,
      self, target: `${site(env)}/letterfield`, linkText: 'Open Letterfield in Letterfield',
    });
  }
  const state = await stateOf(env, e);
  const description = `${e.s ? 'A stray' : 'A'} ${THEMES[e.th].name.toLowerCase()} word in ${regionName(e.rx, e.ry)}, on Letterfield's map. `
    + (state.claim ? `Charted first${state.claim.initials ? ` by ${state.claim.initials}` : ''} on ${day(state.claim.at)}.`
      : state.claim === null ? 'Not yet charted.' : 'Find it on the map.');
  return htmlPage({
    title: `${e.w} · Letterfield`, description,
    image: `${url.origin}/f/${dark ? 'd/' : ''}${slug}.png?s=${encodeURIComponent(stateToken(state))}`,
    alt: `${e.w} circled on Letterfield's map`, png: true,
    self, target: `${site(env)}/letterfield#${slug}`, linkText: `Open ${e.w} in Letterfield`,
  });
}

// A page of link-preview tags that sends people on to target. png: whether
// image is a card (a PNG) rather than the game's own preview (a JPEG).
function htmlPage({ title, description, image, alt, png, self, target, linkText }) {
  const tags = [
    ['property', 'og:type', 'website'], ['property', 'og:site_name', 'Games'],
    ['property', 'og:title', title], ['property', 'og:description', description],
    // Itself, never the game: Meta's crawler (and so WhatsApp) re-reads og:url.
    ['property', 'og:url', self],
    ['property', 'og:image', image], ['property', 'og:image:type', png ? 'image/png' : 'image/jpeg'],
    ['property', 'og:image:width', '1200'], ['property', 'og:image:height', '630'],
    ['property', 'og:image:alt', alt],
    ['name', 'twitter:card', 'summary_large_image'],
  ];
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<meta name="viewport" content="width=device-width,initial-scale=1">
${tags.map(([k, n, v]) => `<meta ${k}="${n}" content="${esc(v)}">`).join('\n')}
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0;url=${esc(target)}">
<script>location.replace(${JSON.stringify(target).replace(/</g, '\\u003c')})</script>
</head><body><p><a href="${esc(target)}">${esc(linkText)}</a></p></body></html>`;
  return new Response(html, {
    headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': `public, max-age=${PAGE_MS / 1000}` },
  });
}

// ---------- The card ----------

async function image(request, env, ctx, render, e, slug, dark) {
  const state = await stateOf(env, e);
  const token = stateToken(state), asked = new URL(request.url).searchParams.get('s');
  const current = asked === token;
  // Only charted words in the shared world (a claim only comes from a sector
  // in it) are kept for good: a card for a word nobody has charted changes
  // once someone does, and anything else would let a script fill the bucket.
  const keep = current && !!state.claim && env.CARDS;
  const stored = `m${MAP_VERSION}/${dark ? 'dark' : 'light'}/${slug}/${token}.png`;
  if (keep) {
    const object = await env.CARDS.get(stored).catch(() => null);
    if (object) return card(await object.arrayBuffer(), true);
  }

  // Drawing costs ~50 ms of CPU, so new cards are limited per address; over
  // the limit, the game's own preview stands in.
  if (!(await allowed(request, env))) return standIn(env);
  const png = await render(findSvg(e, { ...state, dark, host: new URL(site(env)).host }));
  if (keep) ctx.waitUntil(env.CARDS.put(stored, png, { httpMetadata: { contentType: 'image/png' } }).catch((error) => console.error({ share: 'store failed', error: String(error) })));
  // Asked for with an old state, or none: the card as it is now, kept briefly.
  return card(png, current);
}

// A card, kept for good when it shows the state it was asked for.
const card = (png, current) => new Response(png, {
  headers: { 'Content-Type': 'image/png', 'Cache-Control': current ? IMAGE_FOREVER : `public, max-age=${STALE_IMAGE_MS / 1000}` },
});
// The game's own preview, standing in for a card that can't be drawn.
const standIn = (env) => new Response(null, { status: 302, headers: { Location: `${site(env)}/previews/letterfield.jpg`, 'Cache-Control': 'no-store' } });

async function allowed(request, env) {
  if (!env.RENDERS) return true;
  const ip = request.headers.get('CF-Connecting-IP');
  if (!ip) return true;
  try {
    return (await env.RENDERS.limit({ key: await hashAddress(ip, env.IP_SALT) })).success !== false;
  } catch {
    return true;
  }
}

// ---------- Views of the survey log ----------

// The log's answer for a view, asked of the leaderboard Worker through its
// service binding (LOG), by the same paths and under the same host as the
// page asks, so the two share its cache. Null if it can't be had in time, as
// on a Worker Preview, which has no binding.
export async function logOf(env, v, now = Date.now()) {
  if (!env.LOG) return null;
  const base = (env.LOG_URL || DEFAULT_LOG).replace(/\/$/, '');
  const get = async (path) => {
    const answer = await ask(() => env.LOG.fetch(new Request(`${base}${path}`)), LOG_MS);
    return answer?.status === 200 ? await answer.json().catch(() => null) : null;
  };
  const span = v.kind !== 'territory' && v.period === 'all' ? await get('/v1/survey/log/span') : null;
  const a = await get(logPaths(v, span, now));
  if (v.kind === 'novas') return a && Array.isArray(a.novas) && Number.isInteger(a.count) ? summarize(v, a, now) : null;
  if (!a || !Array.isArray(a.entries)) return null;
  if (v.kind === 'territory' ? !(Number.isInteger(a.charted) && Number.isInteger(a.total)) : !(Number.isInteger(a.words) && Number.isInteger(a.world))) return null;
  // A guild the log has no name for, and whose address gives none, has no card:
  // the game's own preview stands in.
  if (v.kind === 'guild' && typeof a.name !== 'string' && !v.named) return null;
  // A territory the log doesn't know has gone supernova may have done so in
  // the last half minute: its sector knows. One with nothing charted can't
  // have, so its sector isn't woken.
  if (v.kind === 'territory' && !Array.isArray(a.nova) && a.charted > 0) {
    const nova = await novaOf(env, v.rx, v.ry);
    if (nova) a.nova = nova;
  }
  return summarize(v, a, now);
}

// q: a guild's name from its address, kept on its card's address and its page's.
async function viewPage(env, v, url, q) {
  const self = url.origin + url.pathname + (q && `?${q}`);
  const s = await logOf(env, v);
  const { name } = s ?? nameOf(v);
  const title = `${name} · Letterfield survey log`;
  const description = s ? s.line : 'Every word charted in Letterfield’s shared survey: what, where, by whom and when.';
  const image = s ? `${url.origin}${url.pathname}.png?${q && `${q}&`}s=${encodeURIComponent(s.token)}` : `${site(env)}/previews/letterfield.jpg`;
  const alt = !s ? 'Letterfield' : v.kind === 'novas' ? 'Supernovas in Letterfield\'s survey log' : `${name}'s page of Letterfield's survey log`;
  return htmlPage({ title, description, image, alt, png: !!s, self, target: `${site(env)}${pagePath(v, s?.name)}`, linkText: `Open ${name} in Letterfield's survey log` });
}

async function viewImage(request, env, render, v) {
  const s = await logOf(env, v);
  if (!s || !(await allowed(request, env))) return standIn(env);
  const png = await render(viewSvg(v, s, { dark: v.dark, host: new URL(site(env)).host }));
  // Asked for with the state it shows, it never changes: a new word is a new token.
  return card(png, new URL(request.url).searchParams.get('s') === s.token);
}
