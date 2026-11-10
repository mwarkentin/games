// The card's drawing: which slugs are drawn, what it says, and that it keeps
// to the page's own colours.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, test } from 'node:test';

import { chunk, keyOf } from '../../worker/src/letterfield-world.js';
import { PALETTES, findSvg, fit, measure, parseFind, progress } from '../src/card.js';

const n = (v) => (v < 0 ? `m${-v}` : String(v));
export const slugOf = (p) => `f-${p.w.toLowerCase()}-${n(p.x)}-${n(p.y)}-${p.d}`;
// A hidden word from a chunk near the middle of the map, and one far out west and north.
export const PLACED = chunk(3, 7).words[0];
export const FAR = chunk(-5000, -3000).words[1];

describe('parseFind', () => {
  test('takes a hidden word in the game\'s fragment form', () => {
    const e = parseFind(slugOf(PLACED));
    assert.equal(e.key, keyOf(PLACED.w, PLACED.x, PLACED.y, PLACED.d));
    assert.equal(e.s, 0);
    assert.equal(e.th, PLACED.th);
    const far = parseFind(slugOf(FAR));
    assert.ok(far.x < 0 && far.y < 0 && slugOf(FAR).includes('-m'));
  });

  test('refuses anything that isn\'t really there', () => {
    const { w, x, y, d } = PLACED;
    for (const slug of [
      `f-${w.toLowerCase()}-${x + 1}-${y}-${d}`,       // the letters aren't there
      `f-${w.toLowerCase()}-${x}-${y}-${(d + 4) % 8}`, // backwards
      'f-zzzz-0-0-0',                                  // not a word
      `f-${w.toLowerCase()}-${x}-${y}-9`,              // no such direction
      `f-${w}-${x}-${y}-${d}`,                         // capitals aren't the game's form
      `${w.toLowerCase()}-${x}-${y}-${d}`,
      'f-a-0-0-0',
    ]) assert.equal(parseFind(slug), null, slug);
  });

  test('refuses a stray shorter than the game counts', () => {
    // Every three-letter run of letters on the map that spells a word would
    // otherwise be a card.
    let found = null;
    for (let x = 0; x < 400 && !found; x++) {
      for (const w of ['CAT', 'DOG', 'SUN', 'TEA', 'OAT']) {
        const e = parseFind(`f-${w.toLowerCase()}-${x}-0-0`);
        if (e) found = e;
      }
    }
    assert.equal(found?.s ?? 0, 0);
  });
});

describe('progress', () => {
  const total = 1_119_752;
  test('says how much of the shared map is charted, rounded down', () => {
    assert.equal(progress({ charted: 0, total }), '0.0% of the shared map charted');
    assert.equal(progress({ charted: 500, total }), 'Under 0.1% of the shared map charted');
    assert.equal(progress({ charted: 4480, total }), '0.4% of the shared map charted');
    assert.equal(progress({ charted: 11_197, total }), '0.9% of the shared map charted');
    assert.equal(progress({ charted: 11_198, total }), '1% of the shared map charted');
    assert.equal(progress({ charted: 33_900, total }), '3% of the shared map charted');
    assert.equal(progress({ charted: total - 1, total }), '99% of the shared map charted');
    assert.equal(progress({ charted: total, total }), 'Every word on the shared map charted');
  });

  test('says nothing without totals', () => {
    for (const t of [null, undefined, {}, { charted: 3 }, { charted: -1, total }, { charted: 1, total: 0 }]) assert.equal(progress(t), null);
  });
});

describe('findSvg', () => {
  const e = parseFind(slugOf(PLACED));
  const texts = (svg) => [...svg.matchAll(/<text[^>]*>([^<]*)<\/text>/g)].map((m) => m[1]);

  test('names the word, its theme, its territory and where it is', () => {
    const svg = findSvg(e, {});
    const t = texts(svg);
    assert.ok(t.includes(PLACED.w));
    assert.ok(t.includes('LETTERFIELD'));
    assert.ok(t.some((s) => s.endsWith(' word')));
    assert.ok(t.includes('games.michaelwarkentin.com'));
    assert.match(svg, /^<svg xmlns="http:\/\/www.w3.org\/2000\/svg" width="1200" height="630"/);
  });

  test('says who charted it first, that nobody has, or nothing if it couldn\'t ask', () => {
    const at = Date.UTC(2026, 10, 9, 15);
    assert.ok(texts(findSvg(e, { claim: { initials: 'ZED', at } })).includes('by ZED · 9 Nov 2026'));
    assert.ok(texts(findSvg(e, { claim: { initials: '', at } })).includes('9 Nov 2026'));
    assert.ok(texts(findSvg(e, { claim: null })).includes('NOT YET CHARTED'));
    const unknown = texts(findSvg(e, {}));
    assert.ok(unknown.includes('FIND IT ON THE MAP'));
    assert.ok(!unknown.some((s) => s.includes('CHARTED')));
    assert.ok(texts(findSvg(e, { claim: null, progressText: '3% of the shared map charted' })).includes('3% of the shared map charted'));
  });

  test('escapes what it writes', () => {
    assert.ok(!findSvg(e, { claim: { initials: '<&>', at: 0 } }).includes('<&>'));
  });

  test('keeps every line of the panel inside it', () => {
    // The longest word, territory and theme names have to fit the panel.
    assert.ok(measure('CHARTED FIRST', 'display', 44, 0.05) < 386);
    assert.ok(measure('Every word on the shared map charted', 'mono4', fit('Every word on the shared map charted', 'mono4', 18, 12, 386), 0) <= 386);
    assert.ok(measure('INTERPLANETARY', 'display', fit('INTERPLANETARY', 'display', 120, 40, 386, 0.04), 0.04) <= 386);
  });

  test('draws in either of the page\'s themes', () => {
    assert.ok(findSvg(e, {}).includes(PALETTES.light.paper));
    assert.ok(findSvg(e, { dark: true }).includes(PALETTES.dark.paper));
    assert.ok(!findSvg(e, { dark: true }).includes(PALETTES.light.paper));
  });
});

describe('the palettes', () => {
  // The card's colours are the page's: its custom properties, the rings'
  // fill and the territories' tint.
  const html = readFileSync(new URL('../../letterfield.html', import.meta.url), 'utf8');
  const props = (block) => Object.fromEntries([...block.matchAll(/--([a-z-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
  const light = props(html.match(/:root\{([^}]*--paper[^}]*)\}/)[1]);
  const dark = props(html.match(/:root\[data-theme="dark"\]\{([^}]*)\}/)[1]);

  for (const [name, page] of [['light', light], ['dark', dark]]) {
    test(`${name} matches letterfield.html`, () => {
      const card = PALETTES[name];
      for (const k of ['paper', 'ink', 'muted', 'rule', 'accent']) assert.equal(card[k].toLowerCase(), page[k].toLowerCase(), k);
      assert.equal(card.markS, page['mark-s'] ?? light['mark-s']);
      assert.equal(card.markL, page['mark-l'] ?? light['mark-l']);
    });
  }

  test('the rings\' fill and the tint match the page\'s', () => {
    const fa = html.match(/const fa = C\.dark \? ([.\d]+) : ([.\d]+);/);
    assert.deepEqual([PALETTES.dark.fill, PALETTES.light.fill], [Number(fa[1]), Number(fa[2])]);
    const tint = html.match(/const base = C\.dark \? ([.\d]+) : ([.\d]+)/);
    assert.deepEqual([PALETTES.dark.tint, PALETTES.light.tint], [Number(tint[1]), Number(tint[2])]);
  });
});
