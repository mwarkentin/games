// Survey log views as cards: a surveyor's, a theme's, a guild's or a territory's page, or the Supernovas tab, of
// letterfield-log.html, drawn as that page's own share picture
// (shareImage() there) from the log's own answers.
//
//   /v/surveyor/<initials>/<period>/<when>/<from>-<to>   one surveyor's period
//   /v/theme/<th>/<period>/<when>/<from>-<to>            one theme's period
//   /v/guild/<lid>/<period>/<when>/<from>-<to>           one guild's period, by its log id
//   /v/surveyor/<initials>/all, /v/theme/<th>/all, /v/guild/<lid>/all   all time
//   /v/territory/<rx>,<ry>                               a territory, all time
//   /v/novas/<period>/<when>/<from>-<to>, /v/novas/all   the supernovas of a period, or all time
//   /v/d/…  the dark card; ….png the card itself
//
// A period is pinned to where it starts in the sharer's own time zone: <when>
// is its first day there (YYYY-MM-DD, with Thh for an hour), which names it on
// the card and in the link to the page, and <from>-<to> are the UTC hours it
// covers, which the log is asked for. So a card shared on Monday still matches
// its link on Friday, wherever it's opened.

import { THEMES, regionName, regionTheme } from '../../worker/src/letterfield-world.js';
import { GUILD_FIRST, GUILD_SECOND, GUILD_THIRD } from '../../worker/src/survey-guild.js';
import { H, PALETTES, W, fit, measure, text } from './card.js';
import { novaSvg } from './nova.js';

const HOUR = 3_600_000;
export const LOG_BEGAN_HOUR = Date.UTC(2026, 10, 6) / HOUR;  // where all time starts, until the log's span says earlier
const SLICE_MAX_HOURS = 24 * 3660;  // the most the log's view of one covers (SLICE_MAX_HOURS in survey-log.js)
export const VIEW_PATH = /^\/v\/(d\/)?(surveyor|theme|guild)\/([A-Z]{3}|\d{1,3}|[0-9a-f]{10})\/(?:(all)|(hour|day|week|month|year)\/(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}))?\/(\d{1,8})-(\d{1,8}))(\.png)?$/;
const KEYS = { surveyor: /^[A-Z]{3}$/, theme: /^\d{1,3}$/, guild: /^[0-9a-f]{10}$/ };
export const TERRITORY_PATH = /^\/v\/(d\/)?territory\/(-?\d{1,8}),(-?\d{1,8})(\.png)?$/;
// The Supernovas tab has no key: just its period, pinned as the others' are.
export const NOVAS_PATH = /^\/v\/(d\/)?novas\/(?:(all)|(hour|day|week|month|year)\/(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}))?\/(\d{1,8})-(\d{1,8}))(\.png)?$/;

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const pad = (n) => String(n).padStart(2, '0');
const num = (n) => n.toLocaleString('en-US');
const plural = (n, one, many = `${one}s`) => `${num(n)} ${n === 1 ? one : many}`;
// Dates as the card names them, from wall-clock times kept as UTC.
const longDay = (t) => { const d = new Date(t); return `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
const shortDay = (t, year = true) => { const d = new Date(t); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()].slice(0, 3)}${year ? ` ${d.getUTCFullYear()}` : ''}`; };
export const today = (now) => shortDay(now);
// How long a supernova took, first word to last, as the log page says it (took() there).
export function took(ms) {
  const min = Math.max(1, Math.round(ms / 60000));
  if (min < 60) return plural(min, 'minute');
  const h = Math.round(min / 60);
  return h < 48 ? plural(h, 'hour') : plural(Math.round(h / 24), 'day');
}

// A period's first and last-plus-one wall-clock times, kept as UTC.
function wall(period, y, m, d, h) {
  const start = Date.UTC(y, m - 1, d, period === 'hour' ? h : 0);
  const end = period === 'hour' ? start + HOUR
    : period === 'day' ? Date.UTC(y, m - 1, d + 1)
      : period === 'week' ? Date.UTC(y, m - 1, d + 7)
        : period === 'month' ? Date.UTC(y, m, 1)
          : Date.UTC(y + 1, 0, 1);
  return [start, end];
}

// The view an address names, or null for one that doesn't name a real one:
// a date that isn't one, a week that doesn't start on a Monday, or hours that
// can't be that period in any time zone (UTC-12 to UTC+14).
export function parseView(pathname, now = Date.now()) {
  const t = TERRITORY_PATH.exec(pathname);
  if (t) return { kind: 'territory', rx: Number(t[2]), ry: Number(t[3]), dark: !!t[1], png: !!t[4], period: 'all' };
  const n = NOVAS_PATH.exec(pathname);
  if (n) return pinned({ kind: 'novas', dark: !!n[1], png: !!n[10] }, n.slice(2, 10), now);
  const m = VIEW_PATH.exec(pathname);
  if (!m) return null;
  if (!KEYS[m[2]].test(m[3])) return null;
  const view = { kind: m[2], key: m[2] === 'theme' ? Number(m[3]) : m[3] };
  if (view.kind === 'theme' && !(view.key < THEMES.length)) return null;
  Object.assign(view, { dark: !!m[1], png: !!m[12] });
  return pinned(view, m.slice(4, 12), now);
}

// A view's period from its address's parts: all, or the period, its first
// day (and hour) and the UTC hours it covers.
function pinned(view, [all, period, ys, ms, ds, hs, fs, ts], now) {
  if (all) return { ...view, period: 'all' };
  const [y, mo, d] = [Number(ys), Number(ms), Number(ds)], h = hs === undefined ? null : Number(hs);
  if ((period === 'hour') !== (h !== null) || (h !== null && h > 23)) return null;
  const [start, end] = wall(period, y, mo, d, h ?? 0);
  const date = new Date(start);
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d) return null;
  if ((period === 'week' && date.getUTCDay() !== 1) || (period === 'month' && d !== 1) || (period === 'year' && (mo !== 1 || d !== 1))) return null;
  const from = Number(fs), to = Number(ts);
  // Where the period starts, in UTC hours, for any offset from UTC-12 to UTC+14.
  if (from * HOUR < start - 15 * HOUR || from * HOUR > start + 13 * HOUR) return null;
  if (Math.abs((to - from) - (end - start) / HOUR) > 2 || !(from < to) || to - from > SLICE_MAX_HOURS) return null;
  if (from > Math.floor(now / HOUR)) return null;
  return { ...view, period, y, mo, d, h, start, end, from, to };
}

// A guild's name as its three word numbers, as the log's address carries it
// (?name=<a>-<b>-<c>), or null for a name that isn't three of the lists' words.
export function guildNumbers(name) {
  const words = typeof name === 'string' ? name.split(' ') : [];
  if (words.length !== 3) return null;
  const n = [GUILD_FIRST.map((w) => w[0]), GUILD_SECOND, GUILD_THIRD].map((list, i) => list.indexOf(words[i]));
  return n.every((i) => i >= 0) ? n : null;
}

// The view's own page in the log, with its date pinned, as the page's Share
// gives it (urlFor({ pin: true }) in letterfield-log.html). A guild's carries
// its name, when the card knows it, so the page names it before the log answers.
export function pagePath(v, name = null) {
  const q = new URLSearchParams();
  if (v.kind === 'territory') q.set('territory', `${v.rx},${v.ry}`);
  else if (v.kind === 'novas') q.set('supernovas', '');
  else q.set(v.kind, String(v.key));
  const n = v.kind === 'guild' ? guildNumbers(name) : null;
  if (n) q.set('name', n.join('-'));
  if (v.period !== 'all') {
    q.set('period', v.period);
    q.set('day', `${v.y}-${pad(v.mo)}-${pad(v.d)}`);
    if (v.period === 'hour') q.set('hour', String(v.h));
  }
  return `/letterfield-log?${q.toString().replace(/%2C/g, ',').replace(/(^|&)supernovas=(&|$)/, '$1supernovas$2')}`;
}

// The log's paths for the view: the span first, for all time's start.
export function logPaths(v, span, now = Date.now()) {
  if (v.kind === 'territory') return `/v1/survey/log/territory/${v.rx}/${v.ry}`;
  const base = v.kind === 'novas' ? '/v1/survey/log/novas' : `/v1/survey/log/${v.kind}/${v.key}`;
  if (v.period !== 'all') return `${base}/${v.from}/${v.to}`;
  const first = Number.isInteger(span?.first) ? Math.min(span.first, LOG_BEGAN_HOUR) : LOG_BEGAN_HOUR;
  const to = Math.floor(now / HOUR) + 1;
  return `${base}/${Math.max(first, to - SLICE_MAX_HOURS)}/${to}`;
}

// The view's name, and its theme's hue where it has one, known without asking.
// A guild's is only known from the log's answer (summarize).
export function nameOf(v) {
  if (v.kind === 'surveyor') return { name: v.key };
  if (v.kind === 'guild') return { name: 'A guild' };
  if (v.kind === 'novas') return { name: 'Supernovas' };
  if (v.kind === 'theme') return { name: THEMES[v.key].name, hue: THEMES[v.key].hue };
  const th = regionTheme(v.rx, v.ry);
  return { name: regionName(v.rx, v.ry), hue: THEMES[th].hue };
}

// When, as the card says it (dates, never "this week"), and as its line does.
export function whenOf(v, now = Date.now()) {
  if (v.period === 'all') return { shown: `All time, to ${today(now)}`, said: 'so far' };
  const { start, end } = v, d = new Date(start);
  if (v.period === 'hour') {
    const span = `${pad(d.getUTCHours())}:00 – ${pad(new Date(end).getUTCHours())}:00`;
    return { shown: `${span} · ${longDay(start)}`, said: `from ${span} on ${longDay(start)}` };
  }
  if (v.period === 'day') return { shown: longDay(start), said: `on ${longDay(start)}` };
  if (v.period === 'week') return { shown: `${shortDay(start, false)} – ${shortDay(end - HOUR)}`, said: `in the week of ${shortDay(start)}` };
  if (v.period === 'month') return { shown: `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`, said: `in ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}` };
  return { shown: String(d.getUTCFullYear()), said: `in ${d.getUTCFullYear()}` };
}

// What a card shows of the log's answer: three numbers, the latest words, a
// line for the page's description, and a token that changes when they do.
export function summarize(v, a, now = Date.now()) {
  if (v.kind === 'novas') return summarizeNovas(v, a, now);
  const { name, hue } = v.kind === 'guild' && typeof a?.name === 'string' ? { name: a.name, hue: Number.isFinite(a.hue) ? a.hue : undefined } : nameOf(v);
  const when = whenOf(v, now);
  const entries = Array.isArray(a?.entries) ? a.entries.filter((e) => Array.isArray(e) && typeof e[0] === 'string') : [];
  const themes = a?.themes && typeof a.themes === 'object' ? a.themes : {};
  const words = entries.slice(0, 12).map((e) => ({ w: e[0], hue: themes[e[7]]?.[1], stray: !!e[4] }));
  const latest = entries[0]?.[6] ?? 0;
  const top = Array.isArray(a?.topTerritories?.[0]) ? a.topTerritories[0][2] : null;
  let stats, line, count;
  // A territory gone supernova (its nova: [rx, ry, at, w, x, y, d, initials,
  // first, words, surveyors, top, topN, th]) says so, and how it went.
  const nova = v.kind === 'territory' && Array.isArray(a?.nova) && [2, 8, 9, 10, 12].every((i) => Number.isInteger(a.nova[i])) ? a.nova : null;
  if (nova) {
    const [, , at, w, , , , initials, first, words, surveyors, top] = nova;
    count = a.charted;
    stats = [['Went supernova', shortDay(at)], ['First word to last', took(at - first)], ['Most charted by', /^[A-Z]{3}$/.test(top) ? top : '—']];
    line = `${name} went supernova in Letterfield’s shared survey on ${shortDay(at)}: all ${plural(words, 'hidden word')} charted${surveyors ? ` by ${plural(surveyors, 'surveyor')}` : ''} in ${took(at - first)}, the last, ${w}${/^[A-Z]{3}$/.test(initials) ? `, by ${initials}` : ''}.`;
  } else if (v.kind === 'territory') {
    count = a.charted;
    const people = new Set(entries.map((e) => e[5]).filter((i) => /^[A-Z]{3}$/.test(i))).size;
    stats = [['Hidden words charted', `${num(a.charted)} of ${num(a.total)}`], ['Surveyors', num(people)], ['Latest', entries.length ? shortDay(latest) : '—']];
    line = `${name}, in Letterfield’s shared survey: ${num(a.charted)} of its ${plural(a.total, 'hidden word')} charted so far${people ? `, by ${plural(people, 'surveyor')}` : ''}.`;
  } else if (v.kind === 'surveyor') {
    count = a.words;
    stats = [['Words charted first', num(a.words)], ['In the shared world', num(a.world)], ['Top territory', top || '—']];
    line = a.words
      ? `${name} charted ${plural(a.words, 'word')} first in Letterfield’s shared survey ${when.said}${top ? `, most in ${top}` : ''}.`
      : `No words signed ${name} in Letterfield’s shared survey ${when.said}.`;
  } else if (v.kind === 'guild') {
    count = a.words;
    const who = Array.isArray(a?.topSurveyors?.[0]) ? a.topSurveyors[0][0] : null;
    stats = [['Words charted first', num(a.words)], ['Top member', who || '—'], ['Top territory', top || '—']];
    line = a.words
      ? `The ${name} charted ${plural(a.words, 'word')} first in Letterfield’s shared survey ${when.said}${top ? `, most in ${top}` : ''}.`
      : `The ${name} charted no words in Letterfield’s shared survey ${when.said}.`;
  } else {
    count = a.words;
    const who = Array.isArray(a?.topSurveyors?.[0]) ? a.topSurveyors[0][0] : null;
    stats = [['Hidden words charted', num(a.words)], ['Top surveyor', who || '—'], ['Top territory', top || '—']];
    line = `${plural(a.words, 'hidden word')} charted in Letterfield’s ${name} territories ${when.said}.`;
  }
  const novaOf = nova && { at: nova[2], w: String(nova[3]), initials: String(nova[7] ?? ''), first: nova[8], words: nova[9], surveyors: nova[10], top: String(nova[11] ?? ''), topN: nova[12] };
  return { name, hue, nova: !!nova, novaOf, when: when.shown, stats, words, line, token: `${count}.${latest.toString(36)}${nova ? 'n' : ''}` };
}

// The Supernovas tab's card, as the page's own picture shows it (renderNovas()
// in letterfield-log.html): how many, the latest and the quickest, and the
// latest supernovas' last words, each in its territory theme's colour. The
// log's answer is { count, novas: [[rx, ry, at, w, x, y, d, initials, first,
// words, surveyors, top, topN, th], ...] newest first, places, themes }.
function summarizeNovas(v, a, now) {
  const when = whenOf(v, now);
  const novas = (Array.isArray(a?.novas) ? a.novas : []).filter((n) => Array.isArray(n) && typeof n[3] === 'string' && [0, 1, 2, 8, 13].every((i) => Number.isInteger(n[i])));
  const places = a?.places && typeof a.places === 'object' ? a.places : {};
  const themes = a?.themes && typeof a.themes === 'object' ? a.themes : {};
  const place = (n) => (typeof places[`${n[0]},${n[1]}`] === 'string' ? places[`${n[0]},${n[1]}`] : regionName(n[0], n[1]));
  const count = Number.isInteger(a?.count) ? a.count : novas.length;
  const latest = novas[0], quick = novas.reduce((q, n) => (!q || n[2] - n[8] < q[2] - q[8] ? n : q), null);
  const stats = [['Supernovas', num(count)], ['Latest', latest ? place(latest) : '—'], ['Quickest', quick ? took(quick[2] - quick[8]) : '—']];
  const line = count
    ? `${plural(count, 'territory', 'territories')} went supernova in Letterfield’s shared survey ${when.said}, every hidden word charted.${latest ? ` Latest: ${place(latest)}.` : ''}`
    : `No territories went supernova in Letterfield’s shared survey ${when.said}.`;
  const words = novas.slice(0, 12).map((n) => ({ w: n[3], hue: themes[n[13]]?.[1] }));
  return { name: 'Supernovas', hue: undefined, nova: false, novaOf: null, when: when.shown, stats, words, line, token: `${count}.${(latest?.[2] ?? 0).toString(36)}` };
}

// The card, 1200×630: shareImage() in letterfield-log.html, as SVG.
export function viewSvg(v, s, { dark = false, host = 'games.michaelwarkentin.com' } = {}) {
  // A supernova has a card of its own (nova.js).
  if (s.novaOf) return novaSvg(v, s, { dark, host });
  const C = dark ? PALETTES.dark : PALETTES.light;
  const mark = (hue) => `hsl(${hue},${C.markS},${C.markL})`;
  const X = 72, R = W - 72, out = [];
  const dot = (x, y, r, hue, stray) => (stray
    ? `<circle cx="${x}" cy="${y}" r="${r - 1.5}" fill="none" stroke="${mark(hue)}" stroke-width="3" stroke-dasharray="4 3"/>`
    : `<circle cx="${x}" cy="${y}" r="${r}" fill="${mark(hue)}"/>`);
  out.push(`<rect width="${W}" height="${H}" fill="${C.paper}"/><rect width="${W}" height="10" fill="${C.accent}"/>`);
  const kind = { surveyor: 'SURVEYOR', theme: 'THEME', guild: 'GUILD', territory: 'TERRITORY', novas: 'SUPERNOVAS' }[v.kind];
  const head = `LETTERFIELD · SURVEY LOG · ${kind}`;
  out.push(text(head, X, 84, 'mono5', 20, C.muted, 0.14));
  // The site's address on the right, where it fits beside the heading.
  const hostW = measure(host, 'mono4', 18);
  if (X + measure(head, 'mono5', 20, 0.14) + 40 + hostW <= R) out.push(text(host, R - hostW, 84, 'mono4', 18, C.muted));

  // Whose, as large as fits, after its theme's dot.
  const name = s.name.toUpperCase(), lead = s.hue !== undefined ? 68 : 0;
  const px = fit(name, 'display', 170, 64, R - X - lead, 0.04);
  if (lead) out.push(dot(X + 20, Math.round(250 - px * 0.36), 20, s.hue));
  out.push(text(name, X + lead, 250, 'display', px, C.ink, 0.04));
  out.push(text(s.when, X, 306, 'ui5', fit(s.when, 'ui5', 30, 16, R - X), C.muted));
  out.push(`<rect x="${X}" y="346" width="${R - X}" height="2" fill="${C.rule}"/>`);

  const col = (R - X) / s.stats.length;
  s.stats.forEach(([label, value], i) => {
    const x = X + i * col;
    out.push(text(label, x, 390, 'mono4', fit(label, 'mono4', 18, 12, col - 24), C.muted));
    out.push(text(value, x, 458, 'display', fit(value, 'display', 64, 30, col - 24, 0.04), C.ink, 0.04));
  });

  const none = v.kind === 'novas' ? 'NONE IN THIS PERIOD' : 'NOTHING CHARTED IN THIS PERIOD';
  out.push(text(s.words.length ? 'LATEST' : none, X, 520, 'mono5', 18, C.muted, 0.14));
  let x = X;
  for (const { w, hue, stray } of s.words) {
    const width = 26 + measure(w, 'display', 38, 0.07);
    if (x + width > R) break;
    if (Number.isFinite(hue)) out.push(dot(x + 8, 566, 8, hue, stray));
    out.push(text(w, x + 26, 580, 'display', 38, C.ink, 0.07));
    x += width + 30;
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${out.join('')}</svg>`;
}
