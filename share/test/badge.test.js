// Achievement cards (src/badge.js): every badge in the catalog, drawn as the
// game draws it, with its words laid out inside the card.
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { CORE, MARK_DRAW, MARK_TEXT } from '../../worker/src/achievements.js';
import { badgeSvg, parseBadge, wrap } from '../src/badge.js';
import { PALETTES, measure } from '../src/card.js';

// The card's texts: [x, y, font size, words].
const texts = (svg) => [...svg.matchAll(/<text x="([\d.]+)" y="([\d.]+)"[^>]* font-size="(\d+)"[^>]*>([^<]*)<\/text>/g)]
  .map(([, x, y, px, t]) => [Number(x), Number(y), Number(px), t.replaceAll('&amp;', '&')]);

describe('parseBadge', () => {
  test('knows every achievement in the catalog, and nothing else', () => {
    for (const [id, group] of CORE.CATALOG) {
      const a = parseBadge(id);
      assert.equal(a.name, MARK_TEXT[id][1]);
      assert.equal(a.draw, MARK_DRAW[MARK_TEXT[id][0]]);
      assert.ok(a.group && Number.isInteger(a.hue), `${id} is in ${group}`);
    }
    assert.equal(parseBadge('here-be-dragons').secret, true);
    assert.equal(parseBadge('seven-seas').secret, false);
    for (const id of ['', 'no-such-badge', 'SEVEN-SEAS', '__proto__', 'constructor']) assert.equal(parseBadge(id), null);
  });
});

describe('badgeSvg', () => {
  test('draws the badge in its group\'s colour, and names it, its group and what it asks for', () => {
    const svg = badgeSvg(parseBadge('seven-seas'));
    const words = texts(svg).map((t) => t[3]);
    assert.deepEqual(words, ['LETTERFIELD · ACHIEVEMENT', 'SEVEN SEAS', 'Themes', 'Find words from all 7 themes of', 'the sea.',
      'One of 40 achievements', 'games.michaelwarkentin.com']);
    assert.ok(svg.includes(`stroke="hsl(275,${PALETTES.light.markS},${PALETTES.light.markL})"`));
    assert.ok(!svg.includes('class="f"'));  // the drawing's dots are filled in the badge's colour
    assert.ok(badgeSvg(parseBadge('seven-seas'), { dark: true }).includes(PALETTES.dark.paper));
    assert.ok(texts(badgeSvg(parseBadge('mirror-image'))).some((t) => t[3] === 'Words · secret'));
  });

  test('lays every badge\'s words out inside the card, in both themes, clear of the address', () => {
    for (const [id] of CORE.CATALOG) for (const dark of [false, true]) {
      const t = texts(badgeSvg(parseBadge(id), { dark }));
      const host = t.at(-1), name = t.filter((x) => x[2] >= 40);
      assert.equal(host[3], 'games.michaelwarkentin.com');
      assert.ok(name.length >= 1 && name.length <= 2, `${id}: a name on one line or two`);
      for (const [x, , px, words] of name) assert.ok(x + measure(words, 'display', px, 0.03) <= 1136 + 1, `${id}: ${words} fits`);
      const FACE = { 32: ['ui5', 0], 18: ['mono4', 0], 20: ['mono5', 0.14] };
      for (const [x, , px, words] of t.filter((x) => FACE[x[2]])) assert.ok(x + measure(words, FACE[px][0], px, FACE[px][1]) <= 1136 + 1, `${id}: ${words} fits`);
      const above = t.slice(0, -1).at(-1);
      assert.ok(above[1] <= host[1] - 30, `${id}: its last line (${above[3]}) is clear of the address`);
      assert.ok(name[0][1] - name[0][2] * 0.74 >= 100, `${id}: its name is clear of the eyebrow`);
    }
  });
});

describe('wrap', () => {
  test('breaks between words, and cuts what doesn\'t fit with an ellipsis', () => {
    assert.deepEqual(wrap('one two three', 'ui5', 32, 1000, 3), ['one two three']);
    const lines = wrap('a very long sentence that goes on and on and on and on and on and on and on and on and on', 'ui5', 32, 300, 2);
    assert.equal(lines.length, 2);
    assert.ok(lines[1].endsWith('…'));
    for (const line of lines) assert.ok(measure(line, 'ui5', 32) <= 300);
  });
});
