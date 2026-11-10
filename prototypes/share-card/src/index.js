// Prototype Worker: link-preview cards for Letterfield finds. Throwaway; see
// ../README.md and docs/link-previews.md. Not part of the real Worker.
//
//   GET /f/<f-word-x-y-d>       a tiny page whose og:image is the card, which
//                               sends people on to the game at that word
//   GET /f/<f-word-x-y-d>.png   the card, 1200×630, cached at the edge
//   GET /f/d/<f-word-x-y-d>…    the same, with the card in the dark theme
//                               (the sharer's, which the page puts in the link)
//
// Only words really on the map are drawn; anything else is a 404.

import { initWasm, Resvg } from '@resvg/resvg-wasm';
import wasm from '@resvg/resvg-wasm/index_bg.wasm';
import big from '../fonts/BigShouldersDisplay-800.ttf';
import mono4 from '../fonts/MartianMono-400.ttf';
import mono5 from '../fonts/MartianMono-500.ttf';
import ui5 from '../fonts/SchibstedGrotesk-500.ttf';
import ui6 from '../fonts/SchibstedGrotesk-600.ttf';
import { MAP_VERSION, THEMES, regionName } from '../../../worker/src/letterfield-world.js';
import { findSvg, parseFind } from './card.js';

const SITE = 'https://games.michaelwarkentin.com';
const fontBuffers = [big, mono4, mono5, ui5, ui6].map((b) => new Uint8Array(b));
let ready;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const m = /^\/f\/(d\/)?(f-[a-z0-9-]{1,40}?)(\.png)?$/.exec(url.pathname);
    if (request.method !== 'GET' || !m) return new Response('not found', { status: 404 });
    const e = parseFind(m[2]);
    if (!e) return new Response('not on the map', { status: 404 });
    return m[3] ? image(request, e, m[2], !!m[1], ctx) : page(url, e, m[2]);
  },
};

function page(url, e, slug) {
  const game = `${SITE}/letterfield#${slug}`, theme = THEMES[e.th].name;
  const title = `${e.w} · Letterfield`, description = `A ${theme.toLowerCase()} word in ${regionName(e.rx, e.ry)}, on Letterfield's map.`;
  const tags = [
    ['property', 'og:type', 'website'], ['property', 'og:site_name', 'Games'],
    ['property', 'og:title', title], ['property', 'og:description', description],
    ['property', 'og:url', `${url.origin}${url.pathname}`],
    ['property', 'og:image', `${url.origin}${url.pathname}.png`],
    ['property', 'og:image:width', '1200'], ['property', 'og:image:height', '630'],
    ['property', 'og:image:alt', `${e.w} circled on Letterfield's map`],
    ['name', 'twitter:card', 'summary_large_image'],
  ];
  // Everyone gets the same 200 (unfurlers read the tags; Apple asks for no
  // user-agent tricks); browsers go on by meta refresh, or the script, which
  // keeps the fragment either way.
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>${esc(title)}</title><meta name="description" content="${esc(description)}">
<meta name="viewport" content="width=device-width,initial-scale=1">
${tags.map(([k, n, v]) => `<meta ${k}="${n}" content="${esc(v)}">`).join('\n')}
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0;url=${esc(game)}">
<script>location.replace(${JSON.stringify(game)})</script>
</head><body><p><a href="${esc(game)}">Open ${esc(e.w)} in Letterfield</a></p></body></html>`;
  return new Response(html, {
    headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'public, max-age=86400' },
  });
}

async function image(request, e, slug, dark, ctx) {
  // The card only changes with the map, so the key carries its version.
  const key = new Request(`${new URL(request.url).origin}/_cache/card/m${MAP_VERSION}/${dark ? 'd/' : ''}${slug}.png`);
  const cache = caches.default;
  const hit = await cache.match(key);
  if (hit) return hit;
  ready ??= initWasm(wasm);
  await ready;
  const t = Date.now();
  const png = new Resvg(findSvg(e, null, undefined, dark), {
    fitTo: { mode: 'original' },
    font: { fontBuffers, loadSystemFonts: false, defaultFontFamily: 'Schibsted Grotesk' },
  }).render().asPng();
  const response = new Response(png, {
    headers: {
      'Content-Type': 'image/png',
      'Cache-Control': 'public, max-age=604800, immutable',
      'Server-Timing': `render;dur=${Date.now() - t}`,
    },
  });
  ctx.waitUntil(cache.put(key, response.clone()));
  return response;
}
