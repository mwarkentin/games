// A found word as an SVG card, 1200×630: findImage() in letterfield.html,
// drawn from the Worker's copy of the map (worker/src/letterfield-world.js)
// in either of the page's themes. resvg turns it into the PNG (index.js).
//
// Text is fitted with the fonts' own advance widths (metrics.json, made by
// scripts/fonts.py), standing in for canvas measureText.

import { SECTOR, checkClaim } from '../../worker/src/survey.js';
import {
  DIRS, RC, THEMES, fdiv, letterAt, regionName, regionTheme, strayTheme, wordEnd,
} from '../../worker/src/letterfield-world.js';
import METRICS from './metrics.json' with { type: 'json' };

export const W = 1200, H = 630;

// The page's two themes: its :root and dark custom properties
// (test/card.test.js checks they still match letterfield.html).
export const PALETTES = {
  light: { paper: '#EBEEE7', ink: '#1B2428', muted: '#59656A', rule: '#C6CFC6', accent: '#2A43C2', markS: '58%', markL: '38%', fill: 0.26, tint: 0.09 },
  dark: { paper: '#0F171A', ink: '#E2E7DE', muted: '#93A19D', rule: '#2B3A3E', accent: '#97A9FF', markS: '68%', markL: '68%', fill: 0.22, tint: 0.075 },
};
const DNAME = ['E', 'SE', 'S', 'SW', 'W', 'NW', 'N', 'NE'];
const DARROW = ['→', '↘', '↓', '↙', '←', '↖', '↑', '↗'];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmtCoord = (x, y) => `${Math.abs(x)}${x < 0 ? 'W' : 'E'} · ${Math.abs(y)}${y < 0 ? 'N' : 'S'}`;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const DATE = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
export const day = (ms) => DATE.format(new Date(ms));

const FONTS = {
  display: ['Big Shoulders Display', 800, 'BigShouldersDisplay-800'],
  mono4: ['Martian Mono', 400, 'MartianMono-400'],
  mono5: ['Martian Mono', 500, 'MartianMono-500'],
  ui5: ['Schibsted Grotesk', 500, 'SchibstedGrotesk-500'],
  ui6: ['Schibsted Grotesk', 600, 'SchibstedGrotesk-600'],
};
export function measure(text, font, px, spacing = 0) {
  const m = METRICS[FONTS[font][2]];
  let w = 0;
  for (const ch of text) w += (m[ch] ?? 0.6) + spacing;
  return w * px;
}
// The largest size up to px, down to min, at which text fits in width.
export function fit(text, font, px, min, width, spacing = 0) {
  for (; px > min; px -= 2) if (measure(text, font, px, spacing) <= width) return px;
  return min;
}
export function text(str, x, y, font, px, fill, spacing = 0) {
  const [family, weight] = FONTS[font];
  return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-family="${family}" font-weight="${weight}" font-size="${px}"`
    + (spacing ? ` letter-spacing="${(spacing * px).toFixed(1)}"` : '') + ` fill="${fill}">${esc(str)}</text>`;
}

// The game's fragment form, f-<word>-<x>-<y>-<d> (m for minus), checked
// against the map as the survey checks a claim. Returns the find, or null.
export function parseFind(slug) {
  const m = /^f-([a-z]{3,12})-(m?\d{1,9})-(m?\d{1,9})-([0-7])$/.exec(slug);
  if (!m) return null;
  const num = (v) => (v[0] === 'm' ? -Number(v.slice(1)) : Number(v));
  const x = num(m[2]), y = num(m[3]);
  const claim = checkClaim({ w: m[1].toUpperCase(), x, y, d: Number(m[4]) }, fdiv(x, SECTOR), fdiv(y, SECTOR));
  if (claim.error) return null;
  const rx = fdiv(x, RC), ry = fdiv(y, RC);
  return { ...claim, rx, ry, th: claim.s ? strayTheme(claim.w, rx, ry) : regionTheme(rx, ry) };
}

// How much of the shared map is charted, as the card says it: one decimal
// under 1%, whole percents rounded down after that, so it never says 100%
// until it's true.
export function progress(totals) {
  if (!totals || !(totals.total > 0) || !(totals.charted >= 0)) return null;
  if (totals.charted >= totals.total) return 'Every word on the shared map charted';
  const pct = (totals.charted / totals.total) * 100;
  const shown = pct >= 1 ? `${Math.min(99, Math.floor(pct))}%` : pct >= 0.1 || totals.charted === 0 ? `${(Math.floor(pct * 10) / 10).toFixed(1)}%` : 'Under 0.1%';
  return `${shown} of the shared map charted`;
}

// claim: undefined when it couldn't be asked, null when nobody has charted
// the word, or { initials, at }. progressText: progress() or null.
export function findSvg(e, { claim, progressText = null, dark = false, host = 'games.michaelwarkentin.com' } = {}) {
  const C = dark ? PALETTES.dark : PALETTES.light;
  const tc = (hue) => ({ stroke: `hsl(${hue},${C.markS},${C.markL})`, fill: `hsla(${hue},75%,55%,${C.fill})`, tint: `hsl(${hue},45%,50%)` });
  const theme = THEMES[e.th], col = tc(theme.hue), [ex, ey] = wordEnd(e);
  const out = [];
  const PANEL = 470, mx = (PANEL + 60 + W) / 2, my = H / 2;
  const spanX = Math.abs(ex - e.x) + 1, spanY = Math.abs(ey - e.y) + 1;
  const cs = clamp(Math.min((W - PANEL - 120) / (spanX + 1), (H - 120) / (spanY + 1)), 30, 72);
  const wx = (e.x + ex) / 2 + 0.5, wy = (e.y + ey) / 2 + 0.5;
  const SX = (x) => (x - wx) * cs + mx, SY = (y) => (y - wy) * cs + my;
  const x0 = Math.floor(wx - (mx - PANEL + 60) / cs), x1 = Math.ceil(wx + (W - mx) / cs);
  const y0 = Math.floor(wy - my / cs) - 1, y1 = Math.ceil(wy + (H - my) / cs);

  out.push(`<rect width="${W}" height="${H}" fill="${C.paper}"/>`);
  // Territory tints and their dashed borders.
  out.push(`<g fill-opacity="${C.tint}">`);
  for (let ty = fdiv(y0, RC); ty <= fdiv(y1, RC); ty++) for (let tx = fdiv(x0, RC); tx <= fdiv(x1, RC); tx++) {
    out.push(`<rect x="${SX(tx * RC).toFixed(1)}" y="${SY(ty * RC).toFixed(1)}" width="${RC * cs}" height="${RC * cs}" fill="${tc(THEMES[regionTheme(tx, ty)].hue).tint}"/>`);
  }
  out.push('</g>');
  let rules = '';
  for (let tx = fdiv(x0, RC) + 1; tx <= fdiv(x1, RC); tx++) rules += `M${SX(tx * RC).toFixed(1)} 0V${H}`;
  for (let ty = fdiv(y0, RC) + 1; ty <= fdiv(y1, RC); ty++) rules += `M0 ${SY(ty * RC).toFixed(1)}H${W}`;
  if (rules) out.push(`<path d="${rules}" stroke="${C.rule}" stroke-width="1.5" stroke-dasharray="6 6" fill="none"/>`);

  // The word's ring: a capsule from its first letter to its last, dashed for a stray.
  const a = Math.atan2(SY(ey) - SY(e.y), SX(ex) - SX(e.x)), r = cs * 0.42;
  const len = Math.hypot(SX(ex) - SX(e.x), SY(ey) - SY(e.y));
  out.push(`<g transform="translate(${SX(e.x + 0.5).toFixed(1)} ${SY(e.y + 0.5).toFixed(1)}) rotate(${((a * 180) / Math.PI).toFixed(2)})">`
    + `<rect x="${-r}" y="${-r}" width="${(len + 2 * r).toFixed(1)}" height="${2 * r}" rx="${r}" fill="${col.fill}" stroke="${col.stroke}" stroke-width="3"`
    + (e.s ? ` stroke-dasharray="${(cs * 0.16).toFixed(1)} ${(cs * 0.1).toFixed(1)}"` : '') + '/></g>');

  // Letters: the word's in full ink, the rest quieter. resvg's
  // dominant-baseline is patchy, so they're centred by hand (caps are ~0.7em).
  const inWord = new Set([...e.w].map((_, i) => `${e.x + DIRS[e.d][0] * i},${e.y + DIRS[e.d][1] * i}`));
  const px = Math.round(cs * 0.42);
  out.push(`<g font-family="Martian Mono" font-weight="500" font-size="${px}" text-anchor="middle" fill="${C.ink}">`);
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
    const quiet = inWord.has(`${x},${y}`) ? '' : ' fill-opacity=".42"';
    out.push(`<text x="${SX(x + 0.5).toFixed(1)}" y="${(SY(y + 0.5) + px * 0.36).toFixed(1)}"${quiet}>${String.fromCharCode(65 + letterAt(x, y))}</text>`);
  }
  out.push('</g>');

  // The panel, fading into the map.
  out.push(`<defs><linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="${C.paper}"/><stop offset="1" stop-color="${C.paper}" stop-opacity="0"/></linearGradient></defs>`);
  out.push(`<rect width="${PANEL}" height="${H}" fill="${C.paper}"/><rect x="${PANEL}" width="90" height="${H}" fill="url(#fade)"/>`);
  out.push(`<rect width="${W}" height="10" fill="${C.accent}"/>`);
  const X = 64, R = PANEL - 20;
  out.push(text('LETTERFIELD', X, 84, 'mono5', 20, C.muted, 0.14));
  out.push(text(e.w, X, 216, 'display', fit(e.w, 'display', 120, 40, R - X, 0.04), C.ink, 0.04));
  out.push(`<circle cx="${X + 9}" cy="262" r="9" fill="${col.stroke}"/>`);
  const kind = `${e.s ? 'A stray ' + theme.name.toLowerCase() : theme.name} word`;
  out.push(text(kind, X + 30, 271, 'ui5', fit(kind, 'ui5', 26, 16, R - X - 30), C.muted));
  const place = regionName(e.rx, e.ry);
  out.push(text(place, X, 330, 'ui6', fit(place, 'ui6', 34, 18, R - X), C.ink));
  // Martian Mono lacks the diagonal arrows, and resvg 2.6 sets a whole <text>
  // in the wrong face when a <tspan> changes font, so the arrow is a text of
  // its own, placed by width (exact: the font is monospaced).
  const coord = `${fmtCoord(e.x, e.y)} · `, ax = X + measure(coord, 'mono4', 18);
  out.push(text(coord, X, 366, 'mono4', 18, C.muted));
  out.push(text(DARROW[e.d], ax, 366, 'ui5', 18, C.muted));
  out.push(text(` ${DNAME[e.d]}`, ax + measure(DARROW[e.d], 'ui5', 18), 366, 'mono4', 18, C.muted));
  out.push(`<rect x="${X}" y="410" width="${R - X}" height="2" fill="${C.rule}"/>`);

  // Whether it's charted, and how far along the shared map is.
  if (claim) {
    out.push(text('CHARTED FIRST', X, 470, 'display', 44, C.accent, 0.05));
    out.push(text(claim.initials ? `by ${claim.initials} · ${day(claim.at)}` : day(claim.at), X, 506, 'mono4', 18, C.muted));
  } else if (claim === null) {
    out.push(text('NOT YET CHARTED', X, 470, 'display', 44, C.ink, 0.05));
    out.push(text('Find it on the map', X, 506, 'mono4', 18, C.muted));
  } else {
    out.push(text('FIND IT ON THE MAP', X, 470, 'display', 44, C.ink, 0.05));
  }
  if (progressText) out.push(text(progressText, X, claim === undefined ? 506 : 538, 'mono4', fit(progressText, 'mono4', 18, 12, R - X), C.muted));
  out.push(text(host, X, 594, 'mono4', 16, C.muted));
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${out.join('')}</svg>`;
}
