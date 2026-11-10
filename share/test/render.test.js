// Real cards, through the same resvg wasm and fonts the Worker uses. Needs
// `npm ci` in share/ first.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { describe, test } from 'node:test';

import { Resvg, initWasm } from '@resvg/resvg-wasm';
import { findSvg, parseFind } from '../src/card.js';
import { parseView, summarize, viewSvg } from '../src/view.js';
import { renderer } from '../src/render.js';
import { FAR, PLACED, slugOf } from './card.test.js';

const wasm = readFileSync(createRequire(import.meta.url).resolve('@resvg/resvg-wasm/index_bg.wasm'));
const fonts = ['BigShouldersDisplay-800', 'MartianMono-400', 'MartianMono-500', 'SchibstedGrotesk-500', 'SchibstedGrotesk-600']
  .map((name) => readFileSync(new URL(`../fonts/${name}.ttf`, import.meta.url)));
const render = renderer(() => initWasm(wasm), Resvg, fonts);

// A PNG's size, from its IHDR chunk.
const size = (png) => { const v = new DataView(png.buffer, png.byteOffset); return [v.getUint32(16), v.getUint32(20)]; };

describe('rendering', () => {
  const cases = [
    ['charted, light', PLACED, { claim: { initials: 'ZED', at: Date.UTC(2026, 10, 9) }, progressText: '0.4% of the shared map charted' }],
    ['not yet charted, dark', PLACED, { claim: null, progressText: '3% of the shared map charted', dark: true }],
    ['far out, nothing known', FAR, {}],
  ];
  for (const [name, word, state] of cases) {
    test(`draws a 1200×630 PNG small enough for WhatsApp: ${name}`, async () => {
      const png = await render(findSvg(parseFind(slugOf(word)), state));
      assert.deepEqual([...png.slice(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
      assert.deepEqual(size(png), [1200, 630]);
      assert.ok(png.length < 300_000, `${png.length} bytes`);
    });
  }

  test('draws a card in well under the CPU a request can have', async () => {
    const e = parseFind(slugOf(PLACED));
    await render(findSvg(e, {}));  // the wasm starts on the first
    const start = performance.now();
    for (let i = 0; i < 5; i++) await render(findSvg(e, { dark: i % 2 === 1 }));
    const each = (performance.now() - start) / 5;
    assert.ok(each < 250, `${each.toFixed(0)} ms a card`);
  });
});

describe('rendering a view of the survey log', () => {
  const NOW = Date.UTC(2026, 10, 10, 15, 30), from = Date.UTC(2026, 10, 1, 4) / 3_600_000;
  const entry = (w, th, s = 0) => [w, 5, 7, 0, s, 'MLW', NOW, th];
  const slice = {
    words: 5, world: 5, topTerritories: [[0, 0, 'Hafnium Basin', 1, 3]],
    entries: [entry('BOHRIUM', 1), entry('BERYLLIUM', 1), entry('OSMIUM', 1, 1), entry('FIREWORKS', 2), entry('RAMEN', 3)],
    themes: { 1: ['Periodic Table', 236], 2: ['Festivals', 95], 3: ['Pasta', 356] },
  };
  for (const [name, path] of [['a surveyor\'s month, light', `/v/surveyor/MLW/month/2026-11-01/${from}-${from + 721}.png`], ['a theme, dark', '/v/d/theme/11/all.png']]) {
    test(`draws a 1200×630 PNG: ${name}`, async () => {
      const v = parseView(path, NOW);
      const png = await render(viewSvg(v, summarize(v, { ...slice, topSurveyors: [['MLW', 5]] }, NOW), { dark: v.dark }));
      assert.deepEqual(size(png), [1200, 630]);
      assert.ok(png.length < 300_000, `${png.length} bytes`);
      if (process.env.SHARE_CARD_OUT) (await import('node:fs')).writeFileSync(`${process.env.SHARE_CARD_OUT}/view-${v.kind}-${v.dark ? 'dark' : 'light'}.png`, png);
    });
  }
});
