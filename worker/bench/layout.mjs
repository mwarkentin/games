// Lays out Letterfield's themes on the map. Territory (rx, ry) has theme
// (rx + LAT_B ry) mod NT, so a territory's eight neighbours have the themes
// 1, LAT_B - 1, LAT_B and LAT_B + 1 places away in THEME_DATA, either way.
// With NT = LAT_B², a theme comes round again only LAT_B territories away in
// any direction, as far apart as NT themes can be.
//
// This searches for an order of THEME_DATA in which every two neighbours
// differ in hue by at least 30 degrees, differ in kind (theme-kinds.json: no
// two bird themes side by side) and share no words, and prints THEME_DATA in
// that order, to paste into letterfield.html and src/letterfield-world.js.
// test/survey.test.js checks the hues, the words and the spacing; the kinds
// are this script's alone, so give a new theme one.
//
//   node bench/layout.mjs [seed] [lat_b] > /tmp/themes.txt
import { readFileSync } from 'node:fs';
import { THEMES } from '../src/letterfield-world.js';

const kinds = JSON.parse(readFileSync(new URL('./theme-kinds.json', import.meta.url), 'utf8'));
const NT = THEMES.length, LAT = Number(process.argv[3] ?? Math.floor(Math.sqrt(NT))), MIN_HUE = 30;
for (const t of THEMES) if (!kinds[t.name]) throw new Error(`no kind for ${t.name} in theme-kinds.json`);
const OFFSETS = [1, LAT - 1, LAT, LAT + 1];  // and their negatives: the 8 neighbours
const circ = (a) => { const d = ((a % 360) + 360) % 360; return Math.min(d, 360 - d); };
const sets = THEMES.map((t) => new Set(t.words));
// How badly two themes go side by side: one for each rule they break.
const clash = new Array(NT * NT).fill(0);
for (let a = 0; a < NT; a++) for (let b = 0; b < NT; b++) {
  if (a === b) continue;
  clash[a * NT + b] = (circ(THEMES[a].hue - THEMES[b].hue) < MIN_HUE)
    + (kinds[THEMES[a].name] === kinds[THEMES[b].name])
    + THEMES[a].words.some((w) => sets[b].has(w));
}
let seed = Number(process.argv[2] ?? 1);
const rnd = () => { seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const at = [...Array(NT).keys()];  // at[i] = the theme in place i
for (let i = NT - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [at[i], at[j]] = [at[j], at[i]]; }
const m = (i) => ((i % NT) + NT) % NT;
const local = (i) => { let c = 0; for (const o of OFFSETS) c += clash[at[i] * NT + at[m(i + o)]] + clash[at[i] * NT + at[m(i - o)]]; return c; };
let cost = 0; for (let i = 0; i < NT; i++) cost += local(i); cost /= 2;
// Simulated annealing over swaps. Two neighbours swapped keep their shared
// edge, which counts the same before and after, so the change is exact.
let T = 2;
for (let step = 0; step < 4e6 && cost > 0; step++) {
  const i = Math.floor(rnd() * NT), j = Math.floor(rnd() * NT);
  if (i === j) continue;
  const before = local(i) + local(j);
  [at[i], at[j]] = [at[j], at[i]];
  const delta = local(i) + local(j) - before;
  if (delta <= 0 || rnd() < Math.exp(-delta / T)) cost += delta; else [at[i], at[j]] = [at[j], at[i]];
  T = Math.max(0.05, T * 0.999998);
}
process.stderr.write(`${NT} themes, LAT_B ${LAT}: ${cost} clashes left\n`);
if (cost > 0) process.exit(1);
console.log(at.map((t) => `${THEMES[t].name}|${THEMES[t].hue}|${THEMES[t].words.join(' ')}`).join('\n'));
