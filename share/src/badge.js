// An achievement as an SVG card, 1200×630: its badge, drawn as the game
// draws it (the BADGE ART in worker/src/achievements.js, a copy of
// letterfield.html's), its name, its group and what it asks for, in either of
// the page's themes. Nothing on it is about who shared it: it's the badge, as
// anyone who earns it gets it.

import { CORE, MARK_DRAW, MARK_GROUPS, MARK_TEXT } from '../../worker/src/achievements.js';
import { H, PALETTES, W, fit, measure, text } from './card.js';

// The achievement an address names, or null.
export function parseBadge(id) {
  const entry = CORE.CATALOG.find(([i]) => i === id);
  const group = entry && MARK_GROUPS.find((g) => g.id === entry[1]);
  if (!entry || !group || !MARK_TEXT[id] || !MARK_DRAW[MARK_TEXT[id][0]]) return null;
  const [draw, name, desc] = MARK_TEXT[id];
  return { id, name, desc, draw: MARK_DRAW[draw], group: group.name, hue: group.h, secret: entry[2].includes('h') };
}

// str in lines no wider than width at px in font: at most max of them, the
// last cut with … if it all doesn't fit.
export function wrap(str, font, px, width, max) {
  const lines = [];
  let line = '';
  for (const word of str.split(' ')) {
    const next = line ? `${line} ${word}` : word;
    if (line && measure(next, font, px) > width) { lines.push(line); line = word; } else line = next;
  }
  if (line) lines.push(line);
  if (lines.length <= max) return lines;
  const kept = lines.slice(0, max);
  let last = `${kept[max - 1]} ${lines.slice(max).join(' ')}`;
  while (last.length > 1 && measure(`${last}…`, font, px) > width) last = last.slice(0, -1).trimEnd();
  kept[max - 1] = `${last}…`;
  return kept;
}

// The badge's name in the display face: on one line if it fits at 84px or
// more, otherwise on two, both at the size the longer fits, up to 96px, split
// where that's largest and, of those, most even. [lines, px].
function nameLines(name, width) {
  const caps = name.toUpperCase(), spacing = 0.03;
  const one = fit(caps, 'display', 118, 40, width, spacing);
  if (one >= 84 || !caps.includes(' ')) return [[caps], one];
  const words = caps.split(' ');
  let best = null;
  for (let i = 1; i < words.length; i++) {
    const pair = [words.slice(0, i).join(' '), words.slice(i).join(' ')];
    const px = Math.min(...pair.map((l) => fit(l, 'display', 96, 40, width, spacing)));
    const odd = Math.abs(measure(pair[0], 'display', px, spacing) - measure(pair[1], 'display', px, spacing));
    if (!best || px > best[1] || (px === best[1] && odd < best[2])) best = [pair, px, odd];
  }
  return best[1] > one ? [best[0], best[1]] : [[caps], one];
}

export function badgeSvg(a, { dark = false, host = 'games.michaelwarkentin.com' } = {}) {
  const C = dark ? PALETTES.dark : PALETTES.light;
  const ink = `hsl(${a.hue},${C.markS},${C.markL})`;
  const out = [`<rect width="${W}" height="${H}" fill="${C.paper}"/>`, `<rect width="${W}" height="10" fill="${C.accent}"/>`];

  // The badge, earned, as the page's 64px one (ring, bezel and finer strokes), at 330px on a soft halo.
  const size = 330, cx = 300, cy = 330, k = size / 32;
  out.push(`<circle cx="${cx}" cy="${cy}" r="236" fill="hsl(${a.hue},45%,50%)" fill-opacity="${(C.tint * 1.6).toFixed(3)}"/>`);
  out.push(`<circle cx="${cx}" cy="${cy}" r="272" fill="none" stroke="${C.rule}" stroke-width="1.5" stroke-dasharray="6 6"/>`);
  const glyph = a.draw.replace(/class="f"/g, `fill="${ink}" stroke="none"`);
  out.push(`<g transform="translate(${cx - size / 2} ${cy - size / 2}) scale(${k.toFixed(4)})" fill="none" stroke-linecap="round" stroke-linejoin="round">`
    + `<circle cx="16" cy="16" r="15.3" stroke="${ink}" stroke-width="1" stroke-dasharray=".6 3.38" stroke-opacity=".75"/>`
    + `<circle cx="16" cy="16" r="13.6" fill="hsla(${a.hue},${C.markS},${C.markL},.16)" stroke="${ink}" stroke-width="1.3"/>`
    + `<g stroke="${ink}" stroke-width="1.5">${glyph}</g></g>`);

  // What it is, between the eyebrow and the address, centred there: the name
  // (its caps' top is about 0.74em above its baseline), the group, what it
  // asks for, and a rule over how many there are, if there's room for it.
  const X = 640, R = W - 64, width = R - X, TOP = 116, BOTTOM = 548;
  out.push(text('LETTERFIELD · ACHIEVEMENT', X, 84, 'mono5', 20, C.muted, 0.14));
  const [names, px] = nameLines(a.name, width), desc = wrap(a.desc, 'ui5', 32, width, 3);
  const nameH = px * 0.74 + (names.length - 1) * px * 0.94, descH = 24 + (desc.length - 1) * 42;
  let h = nameH + 64 + 54 + descH;
  const count = h + 76 <= BOTTOM - TOP;
  if (count) h += 76;
  let y = TOP + Math.max(0, (BOTTOM - TOP - h) / 2) + px * 0.74;
  for (const line of names) { out.push(text(line, X, y, 'display', px, C.ink, 0.03)); y += px * 0.94; }
  y += 64 - px * 0.94;
  out.push(`<circle cx="${X + 9}" cy="${y - 9}" r="9" fill="${ink}"/>`);
  const kind = a.secret ? `${a.group} · secret` : a.group;
  out.push(text(kind, X + 30, y, 'ui5', fit(kind, 'ui5', 26, 16, width - 30), C.muted));
  y += 54;
  for (const line of desc) { out.push(text(line, X, y, 'ui5', 32, C.ink)); y += 42; }
  if (count) {
    out.push(`<rect x="${X}" y="${y - 10}" width="${width}" height="2" fill="${C.rule}"/>`);
    out.push(text(`One of ${CORE.CATALOG.length} achievements`, X, y + 34, 'mono4', 18, C.muted));
  }
  out.push(text(host, X, 594, 'mono4', 16, C.muted));
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${out.join('')}</svg>`;
}
