// Renders a few finds to PNG in Node with the same wasm the Worker uses, and
// times each step. node scripts/bench.js [out-dir]
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs';
import { initWasm, Resvg } from '@resvg/resvg-wasm';
import { chunk } from '../../../worker/src/letterfield-world.js';
import { findSvg, parseFind } from '../src/card.js';

const here = new URL('..', import.meta.url).pathname, out = process.argv[2] ?? `${here}out`;
mkdirSync(out, { recursive: true });
let t = performance.now();
await initWasm(readFileSync(`${here}node_modules/@resvg/resvg-wasm/index_bg.wasm`));
console.log(`wasm init ${(performance.now() - t).toFixed(0)} ms`);
const fontBuffers = readdirSync(`${here}fonts`).filter((f) => f.endsWith('.ttf')).map((f) => readFileSync(`${here}fonts/${f}`));

// Some real words from the map: the first few hidden words of a few chunks,
// plus one with negative coordinates.
const slugs = [];
for (const [cx, cy] of [[0, 0], [3, 7], [-5, -2], [40, -31]]) {
  const p = chunk(cx, cy).words[0];
  const n = (v) => (v < 0 ? 'm' + -v : v);
  slugs.push(`f-${p.w.toLowerCase()}-${n(p.x)}-${n(p.y)}-${p.d}`);
}
slugs.push('f-zzzz-0-0-0'); // not on the map
for (const [i, slug] of slugs.entries()) {
  t = performance.now();
  const e = parseFind(slug);
  if (!e) { console.log(`${slug}: refused (not on the map)`); continue; }
  const svg = findSvg(e, i % 2 ? { initials: 'ZED', n: 1234 + i, total: 1119752 } : null);
  const tSvg = performance.now() - t;
  t = performance.now();
  const png = new Resvg(svg, { fitTo: { mode: 'original' }, font: { fontBuffers, loadSystemFonts: false, defaultFontFamily: 'Schibsted Grotesk' } }).render().asPng();
  const tPng = performance.now() - t;
  writeFileSync(`${out}/${slug}.png`, png);
  console.log(`${slug}: svg ${(svg.length / 1024).toFixed(0)} KB in ${tSvg.toFixed(1)} ms, png ${(png.length / 1024).toFixed(0)} KB in ${tPng.toFixed(0)} ms`);
}
