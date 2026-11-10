// Link-preview cards for Letterfield finds (see README.md and
// docs/link-previews.md):
//
//   GET /f/<slug>        a small page whose og:image is the card; it sends
//                        people on to the game at that word
//   GET /f/<slug>.png    the card, 1200×630
//   GET /f/d/<slug>…     the same, with a dark card (a dark page's share)
//
// <slug> is the game's own fragment, f-<word>-<x>-<y>-<d>. Only words really
// on the map are drawn. Everyone, bot or person, gets the same page: link
// unfurlers read its tags and don't run its refresh or script.
//
// The renderer is passed in (index.js uses resvg), so tests can run this in
// Node.

import { hashAddress } from '../../worker/src/leaderboard.js';
import { MAP_VERSION, THEMES, keyOf, regionName } from '../../worker/src/letterfield-world.js';
import { AREA, SECTOR, CLAIM_PATH, TOTALS_PATH } from '../../worker/src/survey.js';
import { day, findSvg, parseFind, progress } from './card.js';

export const DEFAULT_SITE = 'https://games.michaelwarkentin.com';
export const PATH = /^\/f\/(d\/)?([a-z0-9-]{1,48}?)(\.png)?$/;
export const ASK_MS = 1500;          // how long a card waits for the survey before leaving its lines off
export const TOTALS_MS = 60_000;     // how long one Worker instance keeps the shared map's totals
export const PAGE_MS = 60_000;       // how long the page is kept at the edge
export const STALE_IMAGE_MS = 300_000; // how long a card asked for with an old state is kept
const IMAGE_FOREVER = 'public, max-age=31536000, immutable';

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const site = (env) => (env.SITE_URL || DEFAULT_SITE).replace(/\/$/, '');

export async function handle(request, env, ctx, render) {
  const url = new URL(request.url);
  if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('method not allowed', { status: 405 });
  if (url.pathname === '/') return Response.redirect(`${site(env)}/letterfield`, 302);
  const m = PATH.exec(url.pathname);
  if (!m) return new Response('not found', { status: 404 });
  const dark = !!m[1], slug = m[2], e = parseFind(slug);
  if (m[3]) {
    if (!e) return new Response('not on the map', { status: 404 });
    return image(request, env, ctx, render, e, slug, dark);
  }
  return page(request, env, ctx, e, slug, dark);
}

// ---------- What the survey knows ----------

// The word's claim, from its sector's live record (the survey log can be 30 s
// behind, and apps fetch a preview the moment Share is tapped): { initials,
// at }, null if nobody has charted it, or undefined if it couldn't be asked.
// Only sectors in the shared world are asked, so a card never wakes (and
// makes storage for) a sector nobody has played in.
export async function claimOf(env, e) {
  const sx = Math.floor(e.x / SECTOR), sy = Math.floor(e.y / SECTOR);
  if (!env.SECTORS || Math.abs(sx) > AREA || Math.abs(sy) > AREA) return undefined;
  const path = `/claim/${encodeURIComponent(keyOf(e.w, e.x, e.y, e.d))}`;
  if (!CLAIM_PATH.test(path)) return undefined;
  const answer = await ask(() => env.SECTORS.get(env.SECTORS.idFromName(`${sx},${sy}`)).fetch(`https://sector${path}`));
  if (!answer || (answer.status !== 200 && answer.status !== 404)) return undefined;
  const c = await answer.json().catch(() => null);
  // Only the sector's own answer means nobody: a plain 404 is a sector from
  // before it knew this path (the share Worker deployed first), so unknown.
  if (answer.status === 404) return c?.error === 'not charted' ? null : undefined;
  return c && typeof c.initials === 'string' && Number.isFinite(c.at) ? { initials: c.initials, at: c.at } : undefined;
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

async function ask(call) {
  let timer;
  try {
    return await Promise.race([call(), new Promise((resolve) => { timer = setTimeout(resolve, ASK_MS, null); })]);
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
  return `${who}.${pct}`;
}

// ---------- The page ----------

async function page(request, env, ctx, e, slug, dark) {
  const cache = await edgeCache();
  const key = new Request(new URL(request.url).origin + new URL(request.url).pathname);
  const hit = await cache?.match(key);
  if (hit) return hit;
  const origin = new URL(request.url).origin, self = `${origin}${new URL(request.url).pathname}`;
  let title, description, image, alt, target;
  if (e) {
    const state = await stateOf(env, e);
    const theme = THEMES[e.th].name.toLowerCase();
    title = `${e.w} · Letterfield`;
    description = `${e.s ? 'A stray' : 'A'} ${theme} word in ${regionName(e.rx, e.ry)}, on Letterfield's map. `
      + (state.claim ? `Charted first${state.claim.initials ? ` by ${state.claim.initials}` : ''} on ${day(state.claim.at)}.`
        : state.claim === null ? 'Not yet charted.' : 'Find it on the map.');
    image = `${origin}/f/${dark ? 'd/' : ''}${slug}.png?s=${encodeURIComponent(stateToken(state))}`;
    alt = `${e.w} circled on Letterfield's map`;
    target = `${site(env)}/letterfield#${slug}`;
  } else {
    // Not a word on today's map (a link from an older map, or mistyped): the
    // game's own card, and the game.
    title = 'Letterfield';
    description = 'A word search the size of a world, charted together.';
    image = `${site(env)}/previews/letterfield.jpg`;
    alt = 'Letterfield';
    target = `${site(env)}/letterfield`;
  }
  const tags = [
    ['property', 'og:type', 'website'], ['property', 'og:site_name', 'Games'],
    ['property', 'og:title', title], ['property', 'og:description', description],
    // Itself, never the game: Meta's crawler (and so WhatsApp) re-reads og:url.
    ['property', 'og:url', self],
    ['property', 'og:image', image], ['property', 'og:image:type', e ? 'image/png' : 'image/jpeg'],
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
</head><body><p><a href="${esc(target)}">Open ${esc(e ? e.w : 'Letterfield')} in Letterfield</a></p></body></html>`;
  const response = new Response(html, {
    status: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': `public, max-age=${PAGE_MS / 1000}` },
  });
  if (cache) ctx.waitUntil(cache.put(key, response.clone()));
  return response;
}

// ---------- The card ----------

async function image(request, env, ctx, render, e, slug, dark) {
  const cache = await edgeCache();
  const key = new Request(request.url);
  const hit = await cache?.match(key);
  if (hit) return hit;

  const state = await stateOf(env, e);
  const token = stateToken(state), asked = new URL(request.url).searchParams.get('s');
  const current = asked === token;
  // Only charted words in the shared world are kept for good: a card for a
  // word nobody has charted changes once someone does, and anything else
  // would let a script fill the bucket.
  const sx = Math.floor(e.x / SECTOR), sy = Math.floor(e.y / SECTOR);
  const keep = current && !!state.claim && Math.abs(sx) <= AREA && Math.abs(sy) <= AREA && env.CARDS;
  const stored = `m${MAP_VERSION}/${dark ? 'dark' : 'light'}/${slug}/${token}.png`;
  if (keep) {
    const object = await env.CARDS.get(stored).catch(() => null);
    if (object) return answer(await object.arrayBuffer(), IMAGE_FOREVER, cache, key, ctx);
  }

  // Drawing costs ~50 ms of CPU, so new cards are limited per address; over
  // the limit, the game's own preview stands in.
  if (!(await allowed(request, env))) {
    return new Response(null, { status: 302, headers: { Location: `${site(env)}/previews/letterfield.jpg`, 'Cache-Control': 'no-store' } });
  }
  const png = await render(findSvg(e, { ...state, dark, host: new URL(site(env)).host }));
  if (keep) ctx.waitUntil(env.CARDS.put(stored, png, { httpMetadata: { contentType: 'image/png' } }).catch((error) => console.error({ share: 'store failed', error: String(error) })));
  // Asked for with an old state, or none: the card as it is now, kept briefly.
  return answer(png, current ? IMAGE_FOREVER : `public, max-age=${STALE_IMAGE_MS / 1000}`, cache, key, ctx);
}

function answer(png, cacheControl, cache, key, ctx) {
  const response = new Response(png, { headers: { 'Content-Type': 'image/png', 'Cache-Control': cacheControl } });
  if (cache) ctx.waitUntil(cache.put(key, response.clone()));
  return response;
}

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

async function edgeCache() {
  try { return globalThis.caches?.default ?? null; } catch { return null; }
}
