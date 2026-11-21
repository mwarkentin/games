// Real map data for the architecture figures (kit.py's world()), from the
// survey server's own copy of the game's generator, so every letter, word
// and colour in a figure is the one the game draws:
//
//   node docs/architecture/data.mjs chunk <cx> <cy>           a chunk's 12×12 letters and hidden words
//   node docs/architecture/data.mjs area <x> <y> <w> <h>      letters, hidden and bonus words in a patch of cells
//   node docs/architecture/data.mjs territories <rx0> <ry0> <rx1> <ry1>   each territory's theme, hue, words and name
//   node docs/architecture/data.mjs themes                    every theme's name, hue and word count
//   node docs/architecture/data.mjs deal <rx> <ry>            a territory's shuffled deck, and what each chunk placed

import {
  CH, DEAL, DIRS, RC, RG, STRAY_MIN, THEMES, VOCAB, chunk, fdiv, keyOf, letterAt, regionName, regionTheme, territoryTotal,
} from '../../worker/src/letterfield-world.js';

const A = 65;
const letters = (x, y, w, h) => Array.from({ length: h }, (_, r) => Array.from({ length: w }, (_, c) => String.fromCharCode(A + letterAt(x + c, y + r))).join(''));
const theme = (rx, ry) => { const th = regionTheme(rx, ry); return { th, theme: THEMES[th].name, hue: THEMES[th].hue }; };

// Hidden words whose start cell is in the patch, and bonus words (strays) spelled there by chance.
function wordsIn(x0, y0, w, h) {
  const hidden = [], strays = [], placed = new Set();
  for (let cy = fdiv(y0, CH); cy <= fdiv(y0 + h - 1, CH); cy++) {
    for (let cx = fdiv(x0, CH); cx <= fdiv(x0 + w - 1, CH); cx++) {
      for (const p of chunk(cx, cy).words) {
        placed.add(p.key);
        if (p.x >= x0 && p.x < x0 + w && p.y >= y0 && p.y < y0 + h) hidden.push({ w: p.w, x: p.x, y: p.y, d: p.d });
      }
    }
  }
  for (let y = y0; y < y0 + h; y++) {
    for (let x = x0; x < x0 + w; x++) {
      for (let d = 0; d < 8; d++) {
        let s = '';
        for (let i = 0; i < 12; i++) {
          s += String.fromCharCode(A + letterAt(x + DIRS[d][0] * i, y + DIRS[d][1] * i));
          if (s.length >= STRAY_MIN && VOCAB.has(s) && !placed.has(keyOf(s, x, y, d))) strays.push({ w: s, x, y, d });
        }
      }
    }
  }
  return { hidden, strays };
}

const [what, ...rest] = process.argv.slice(2);
const n = rest.map(Number);
let out;
if (what === 'chunk') {
  const [cx, cy] = n, rx = fdiv(cx, RG), ry = fdiv(cy, RG);
  out = { cx, cy, rx, ry, ...theme(rx, ry), name: regionName(rx, ry), letters: letters(cx * CH, cy * CH, CH, CH), words: chunk(cx, cy).words.map(({ w, x, y, d }) => ({ w, x, y, d })) };
} else if (what === 'area') {
  const [x, y, w, h] = n;
  const terr = [];
  for (let ry = fdiv(y, RC); ry <= fdiv(y + h - 1, RC); ry++) for (let rx = fdiv(x, RC); rx <= fdiv(x + w - 1, RC); rx++) terr.push({ rx, ry, ...theme(rx, ry), name: regionName(rx, ry) });
  out = { x, y, w, h, letters: letters(x, y, w, h), ...wordsIn(x, y, w, h), territories: terr };
} else if (what === 'territories') {
  const [rx0, ry0, rx1, ry1] = n;
  out = [];
  for (let ry = ry0; ry <= ry1; ry++) for (let rx = rx0; rx <= rx1; rx++) out.push([rx, ry, regionTheme(rx, ry), THEMES[regionTheme(rx, ry)].hue, territoryTotal(rx, ry), regionName(rx, ry)]);
} else if (what === 'themes') {
  out = THEMES.map((t) => [t.name, t.hue, t.words.length]);
} else if (what === 'deal') {
  // As genChunk deals: each chunk takes the next DEAL cards of the territory's deck, from (row * RG + col) * DEAL.
  const [rx, ry] = n, words = new Set(THEMES[regionTheme(rx, ry)].words);
  const chunks = [];
  for (let r = 0; r < RG; r++) {
    for (let c = 0; c < RG; c++) {
      const cx = rx * RG + c, cy = ry * RG + r, got = chunk(cx, cy).words.map((p) => p.w);
      chunks.push({ cx, cy, placed: got });
    }
  }
  out = { rx, ry, ...theme(rx, ry), name: regionName(rx, ry), deal: DEAL, deckSize: words.size, total: territoryTotal(rx, ry), chunks };
} else {
  console.error('usage: data.mjs chunk|area|territories|themes|deal …');
  process.exit(2);
}
process.stdout.write(JSON.stringify(out));
