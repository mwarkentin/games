// A territory gone supernova, as its own card: the moment the game plays
// when the last hidden word comes in (supernova() in letterfield.html),
// stopped just after the burst. A white-hot core in the territory theme's
// hue, the shockwave rolling out with its fainter echoes behind it, sparks
// and the territory's own letters flung outward, and a field of stars, with
// the name and how it went on the dark side of the sky.
//
// It's always night: a star going off is a thing seen in the dark. The light
// card's sky is a deep blue dusk and the dark card's a black one, so each
// still sits with its theme. Everything random is seeded by the territory,
// so a territory's card is always the same picture.

import { RC, THEMES, letterAt, regionTheme } from '../../worker/src/letterfield-world.js';
import { H, W, fit, measure, text } from './card.js';

// A small seeded generator (mulberry32), from the territory's coordinates.
function seeded(rx, ry) {
  let a = (Math.imul(rx | 0, 0x9e3779b1) ^ Math.imul(ry | 0, 0x85ebca77) ^ 0x5bd1e995) >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const f1 = (n) => n.toFixed(1);
// The sky behind it all, by the page's theme.
const SKIES = {
  light: { top: '#0D1838', bottom: '#060B1E', edge: '#03050F', ink: '#F4F6FF', muted: '#A9B4D6', rule: 'rgba(214,224,255,0.22)' },
  dark: { top: '#060A14', bottom: '#020308', edge: '#000000', ink: '#EEF1F6', muted: '#97A2B8', rule: 'rgba(214,224,255,0.18)' },
};

// s: summarize()'s answer for a territory with a supernova, whose novaOf has
// { at, w, initials, first, words, surveyors, top, topN, th }; v: the view.
export function novaSvg(v, s, { dark = false, host = 'games.michaelwarkentin.com' } = {}) {
  const K = dark ? SKIES.dark : SKIES.light, n = s.novaOf, hue = s.hue ?? 200;
  const glow = (l, a = 1, sat = 95) => `hsla(${hue},${sat}%,${l}%,${a})`;
  const r = seeded(v.rx, v.ry);
  const CX = 868, CY = 300, R = 360;  // the burst, and the shockwave's front
  const out = [];
  out.push('<defs>'
    + `<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${K.top}"/><stop offset="1" stop-color="${K.bottom}"/></linearGradient>`
    + `<radialGradient id="core" cx="${CX}" cy="${CY}" r="84" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#FFFFFF"/><stop offset="0.24" stop-color="#FFFFFF" stop-opacity="0.95"/><stop offset="0.5" stop-color="${glow(86, 0.7, 100)}"/><stop offset="0.78" stop-color="${glow(72, 0.28)}"/><stop offset="1" stop-color="${glow(66, 0)}"/></radialGradient>`
    // Behind the words, the sky darkens, so they read whatever is going on.
    // Diffraction spikes: a star's cross of light.
    + `<linearGradient id="spikeH" x1="0" x2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/><stop offset="0.5" stop-color="#FFFFFF" stop-opacity="0.9"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>`
    + `<linearGradient id="spikeV" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/><stop offset="0.5" stop-color="#FFFFFF" stop-opacity="0.85"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>`
    + '<filter id="haze" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>'
    + '</defs>');
  out.push(`<rect width="${W}" height="${H}" fill="url(#sky)"/>`);

  // Stars, near and far: a few tinted by the burst.
  let stars = '';
  for (let i = 0; i < 130; i++) {
    const x = r() * W, y = r() * H, big = r() < 0.08, rad = big ? 1.4 + r() * 1.2 : 0.5 + r() * 0.9;
    const tint = r() < 0.25 ? glow(85, 1, 70) : '#FFFFFF';
    stars += `<circle cx="${f1(x)}" cy="${f1(y)}" r="${rad.toFixed(2)}" fill="${tint}" fill-opacity="${(0.25 + r() * 0.65).toFixed(2)}"/>`;
  }
  out.push(stars);

  // The glow of it, as shells of light thinning outward: flat steps rather
  // than one smooth gradient, which would make a PNG too big for WhatsApp.
  let shells = '';
  for (let i = 0; i < 8; i++) {
    const rr = R * 1.45 * (1 - i / 8);
    shells += `<circle cx="${CX}" cy="${CY}" r="${f1(rr)}" fill="${glow(50 + i, 0.055 + i * 0.004, 90)}"/>`;
  }
  out.push(shells);
  // Behind the wave the sky is lit; ahead of it, still dark (as in novaOver).
  out.push(`<circle cx="${CX}" cy="${CY}" r="${R}" fill="${glow(60, 0.07)}"/>`);

  // The shockwave: a bright front with fainter echoes behind it (novaOver's
  // rings at 1, .74 and .52), each a band of the hue in widening strokes
  // under a white-hot edge.
  for (const [f, a] of [[0.52, 0.35], [0.74, 0.6], [1, 1]]) {
    const rr = R * f;
    for (const [w, o] of f === 1 ? [[44, 0.11], [14, 0.26]] : []) {
      out.push(`<circle cx="${CX}" cy="${CY}" r="${f1(rr - w * 0.2)}" fill="none" stroke="${glow(62)}" stroke-opacity="${(o * a).toFixed(3)}" stroke-width="${w}"/>`);
    }
    out.push(`<circle cx="${CX}" cy="${CY}" r="${f1(rr)}" fill="none" stroke="${glow(f === 1 ? 92 : 80, 1, 100)}" stroke-opacity="${(0.95 * a).toFixed(2)}" stroke-width="${f1(1.2 + 2.6 * a)}"/>`);
  }

  // The territory's own letters, flung outward by the blast: bigger, fainter
  // and more turned the further they've gone.
  const gx = v.rx * RC, gy = v.ry * RC;
  let letters = '';
  for (let i = 0; i < 40; i++) {
    // Most ride the shockwave's front, shoved along by it; the rest trail behind.
    const front = r() < 0.6, ang = r() * Math.PI * 2;
    const d = front ? R * (0.86 + r() * 0.26) : 70 + Math.pow(r(), 0.8) * R * 0.8;
    const x = CX + Math.cos(ang) * d, y = CY + Math.sin(ang) * d * 0.96;
    if (x < 560 || x > W + 20 || y < -20 || y > H + 20) continue;
    const ch = String.fromCharCode(65 + letterAt(gx + Math.floor(r() * RC), gy + Math.floor(r() * RC)));
    const px = Math.round(16 + (d / R) * 24), rot = (r() - 0.5) * 80 * (d / R);
    const op = front ? 0.5 + r() * 0.35 : 0.18 + r() * 0.25;
    letters += `<text transform="translate(${f1(x)} ${f1(y)}) rotate(${rot.toFixed(1)})" font-size="${px}" fill-opacity="${op.toFixed(2)}">${ch}</text>`;
  }
  out.push(`<g font-family="Martian Mono" font-weight="500" text-anchor="middle" fill="${glow(88, 1, 60)}">${letters}</g>`);

  // Sparks: streaks flung out from the core, tapering to their tails, a third
  // of them white-hot.
  let sparks = '';
  for (let i = 0; i < 96; i++) {
    const ang = r() * Math.PI * 2, c = Math.cos(ang), sn = Math.sin(ang), streak = r() < 0.35;
    // Streaks: long and thin, the fastest debris, already past the front.
    const head = streak ? R * (0.9 + r() * 0.75) : 60 + Math.pow(r(), 0.7) * (R + 120);
    const len = streak ? 110 + r() * 160 : 14 + r() * 80 * (head / R), tail = Math.max(24, head - len);
    const w = streak ? 0.7 + r() * 1.3 : 0.9 + r() * 2.4, white = r() < (streak ? 0.55 : 0.3);
    const hx = CX + c * head, hy = CY + sn * head, tx = CX + c * tail, ty = CY + sn * tail;
    // None reach into the words, where the sky is darkened anyway.
    if (Math.min(hx, tx) < 560) continue;
    const px = -sn * w, py = c * w;
    sparks += `<path d="M${f1(tx)} ${f1(ty)}L${f1(hx + px)} ${f1(hy + py)}L${f1(hx - px)} ${f1(hy - py)}Z" fill="${white ? '#FFFFFF' : glow(66)}" fill-opacity="${(0.35 + r() * 0.6).toFixed(2)}"/>`;
  }
  out.push(sparks);

  // The core, white-hot, with its cross of light.
  // The core: a soft, white-hot middle inside steps of the hue's light (a
  // gradient as wide would cost the PNG tens of kilobytes).
  for (const [rad, l, a] of [[124, 60, 0.12], [98, 66, 0.16]]) {
    out.push(`<circle cx="${CX}" cy="${CY}" r="${rad}" fill="${glow(l, a, 100)}"/>`);
  }
  out.push(`<circle cx="${CX}" cy="${CY}" r="84" fill="url(#core)"/>`);
  out.push(`<circle cx="${CX}" cy="${CY}" r="34" fill="#FFFFFF" filter="url(#haze)"/>`);
  out.push(`<rect x="${CX - 330}" y="${CY - 2.5}" width="660" height="5" fill="url(#spikeH)"/>`);
  out.push(`<rect x="${CX - 2}" y="${CY - 230}" width="4" height="460" fill="url(#spikeV)"/>`);
  out.push(`<rect x="${CX - 120}" y="${CY - 1}" width="240" height="2" fill="#FFFFFF" fill-opacity="0.9"/>`);

  // The words, on the darker side of the sky.
  // In flat steps rather than a gradient: across the sky's own gradient,
  // a smooth one would make every pixel different, and the PNG too big.
  let scrim = '';
  for (let i = 0; i < 12; i++) scrim += `<rect x="${i * 64}" width="64" height="${H}" fill="${K.edge}" fill-opacity="${(0.8 * (1 - i / 12) ** 1.4).toFixed(3)}"/>`;
  out.push(scrim);
  out.push(`<rect width="${W}" height="6" fill="${glow(62, 0.95)}"/>`);
  const X = 72, COL = 640;
  // Which theme went up, by name as well as by colour.
  const head = `LETTERFIELD · SUPERNOVA · ${THEMES[regionTheme(v.rx, v.ry)].name.toUpperCase()}`;
  out.push(text(head, X, 84, 'mono5', fit(head, 'mono5', 20, 13, COL + 60, 0.16), glow(80, 1, 85), 0.16));
  const name = s.name.toUpperCase(), px = fit(name, 'display', 150, 60, COL, 0.03);
  out.push(text(name, X, 228, 'display', px, K.ink, 0.03));
  const sub = `Every one of its ${n.words.toLocaleString('en-US')} hidden words charted`;
  out.push(text(sub, X, 280, 'ui5', fit(sub, 'ui5', 28, 16, COL), K.muted));
  out.push(`<rect x="${X}" y="318" width="${COL - 40}" height="2" fill="${K.rule}"/>`);
  const col = (COL - 40) / 3;
  // One size for every label: the largest at which each fits its column.
  const lpx = Math.min(...s.stats.map(([label]) => fit(label.toUpperCase(), 'mono4', 15, 11, col - 30, 0.06)));
  s.stats.forEach(([label, value], i) => {
    const x = X + i * col;
    out.push(text(label.toUpperCase(), x, 360, 'mono4', lpx, K.muted, 0.06));
    out.push(text(value, x, 414, 'display', fit(value, 'display', 52, 26, col - 20, 0.03), K.ink, 0.03));
  });
  out.push(text('THE LAST WORD', X, 478, 'mono5', 16, glow(80, 1, 85), 0.16));
  const word = n.w, wpx = fit(word, 'display', 78, 40, COL - 140, 0.06);
  out.push(text(word, X, 552, 'display', wpx, '#FFFFFF', 0.06));
  if (/^[A-Z]{3}$/.test(n.initials)) {
    const by = `BY ${n.initials}`, bx = X + measure(word, 'display', wpx, 0.06) + 22;
    out.push(text(by, bx, 552, 'mono5', 22, K.muted, 0.1));
  }
  out.push(text(host, X, 600, 'mono4', 15, K.muted));
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${out.join('')}</svg>`;
}
