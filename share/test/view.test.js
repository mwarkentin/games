// Cards of the survey log's views: which addresses name a view, what the card
// says, and the routes, with the log faked behind its service binding.
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { THEMES, regionName, regionTheme } from '../../worker/src/letterfield-world.js';
import { DEFAULT_LOG, LOG_MS, handle } from '../src/app.js';
import { LOG_BEGAN_HOUR, logPaths, pagePath, parseView, summarize, viewSvg, whenOf } from '../src/view.js';

const HOUR = 3_600_000;
const NOW = Date.UTC(2026, 10, 10, 15, 30);  // Tuesday, November 10, 2026, 3:30 PM UTC
// Monday, November 9, in Toronto (UTC-5): its week's UTC hours.
const WEEK_FROM = Date.UTC(2026, 10, 9, 5) / HOUR;
const WEEK = `week/2026-11-09/${WEEK_FROM}-${WEEK_FROM + 168}`;
const SHARE = 'https://share.test';
const SITE = 'https://games.test';

const entry = (w, at, initials = 'ZED', th = 11, s = 0) => [w, 5, 7, 0, s, initials, at, th];
const SLICE = {
  words: 3, world: 2,
  topTerritories: [[0, 0, 'Acorn Hollow', 11, 2], [1, 0, 'Monet Reach', 0, 1]],
  topThemes: [[11, 'Forest', 40, 2]],
  entries: [entry('BIRCH', NOW - HOUR), entry('MONET', NOW - 2 * HOUR, 'ZED', 0, 1), entry('ACORN', NOW - 30 * HOUR)],
  themes: { 11: ['Forest', 40], 0: ['Old Masters', 56] }, places: {}, next: null,
};

describe('parseView', () => {
  test('takes a surveyor\'s or theme\'s period, all time, and a territory', () => {
    const v = parseView(`/v/surveyor/ZED/${WEEK}`, NOW);
    assert.equal(v.kind, 'surveyor'); assert.equal(v.key, 'ZED'); assert.equal(v.period, 'week');
    assert.deepEqual([v.from, v.to, v.dark, v.png], [WEEK_FROM, WEEK_FROM + 168, false, false]);
    assert.equal(parseView(`/v/d/theme/11/${WEEK}.png`, NOW).dark, true);
    assert.equal(parseView(`/v/d/theme/11/${WEEK}.png`, NOW).png, true);
    assert.equal(parseView('/v/surveyor/ZED/all', NOW).period, 'all');
    assert.deepEqual(parseView('/v/territory/-3,12.png', NOW), { kind: 'territory', rx: -3, ry: 12, dark: false, png: true, period: 'all' });
    const hour = parseView(`/v/surveyor/ZED/hour/2026-11-10T09/${Date.UTC(2026, 10, 10, 14) / HOUR}-${Date.UTC(2026, 10, 10, 15) / HOUR}`, NOW);
    assert.equal(hour.h, 9);
    // A day in a time zone half an hour off UTC covers the hour either side.
    const kolkata = Date.UTC(2026, 10, 9, 18, 30) / HOUR;  // midnight, November 10, in UTC+5:30
    assert.ok(parseView(`/v/surveyor/ZED/day/2026-11-10/${Math.floor(kolkata)}-${Math.ceil(kolkata + 24)}`, NOW));
  });

  test('refuses an address that can\'t be a real view', () => {
    for (const path of [
      `/v/surveyor/zed/${WEEK}`,                                        // initials are capitals
      `/v/theme/${THEMES.length}/${WEEK}`,                              // no such theme
      `/v/surveyor/ZED/week/2026-11-10/${WEEK_FROM + 24}-${WEEK_FROM + 192}`,  // weeks start on a Monday
      `/v/surveyor/ZED/day/2026-02-30/${WEEK_FROM}-${WEEK_FROM + 24}`,  // no such day
      `/v/surveyor/ZED/week/2026-11-09/${WEEK_FROM + 30}-${WEEK_FROM + 198}`,  // no time zone starts it then
      `/v/surveyor/ZED/week/2026-11-09/${WEEK_FROM}-${WEEK_FROM + 24}`, // a day's hours, not a week's
      `/v/surveyor/ZED/hour/2026-11-10/${WEEK_FROM}-${WEEK_FROM + 1}`,  // an hour needs its hour
      `/v/surveyor/ZED/day/2026-11-20/${Date.UTC(2026, 10, 20, 5) / HOUR}-${Date.UTC(2026, 10, 21, 5) / HOUR}`,  // not started
      '/v/territory/1,2,3', '/v/surveyor/ZED', '/v/ZED/all',
    ]) assert.equal(parseView(path, NOW), null, path);
  });
});

describe('what a card says', () => {
  test('links to the view\'s own page in the log, its date pinned', () => {
    assert.equal(pagePath(parseView(`/v/surveyor/ZED/${WEEK}`, NOW)), '/letterfield-log?surveyor=ZED&period=week&day=2026-11-09');
    assert.equal(pagePath(parseView('/v/theme/11/all', NOW)), '/letterfield-log?theme=11');
    assert.equal(pagePath(parseView('/v/territory/-3,12', NOW)), '/letterfield-log?territory=-3,12');
    const hour = parseView(`/v/surveyor/ZED/hour/2026-11-10T09/${Date.UTC(2026, 10, 10, 14) / HOUR}-${Date.UTC(2026, 10, 10, 15) / HOUR}`, NOW);
    assert.equal(pagePath(hour), '/letterfield-log?surveyor=ZED&period=hour&day=2026-11-10&hour=9');
  });

  test('names the period by its dates, never "this week"', () => {
    assert.deepEqual(whenOf(parseView(`/v/surveyor/ZED/${WEEK}`, NOW), NOW), { shown: '9 Nov – 15 Nov 2026', said: 'in the week of 9 Nov 2026' });
    const day = Date.UTC(2026, 10, 10, 5) / HOUR;
    assert.equal(whenOf(parseView(`/v/surveyor/ZED/day/2026-11-10/${day}-${day + 24}`, NOW), NOW).shown, 'Tuesday 10 November 2026');
    const month = Date.UTC(2026, 10, 1, 4) / HOUR;
    assert.equal(whenOf(parseView(`/v/surveyor/ZED/month/2026-11-01/${month}-${month + 721}`, NOW), NOW).shown, 'November 2026');
    assert.equal(whenOf(parseView('/v/surveyor/ZED/all', NOW), NOW).shown, 'All time, to 10 Nov 2026');
  });

  test('asks the log for the view\'s own hours, and all time from where the log starts', () => {
    assert.equal(logPaths(parseView(`/v/surveyor/ZED/${WEEK}`, NOW), null, NOW), `/v1/survey/log/surveyor/ZED/${WEEK_FROM}/${WEEK_FROM + 168}`);
    assert.equal(logPaths(parseView('/v/theme/11/all', NOW), { first: LOG_BEGAN_HOUR - 30 }, NOW), `/v1/survey/log/theme/11/${LOG_BEGAN_HOUR - 30}/${Math.floor(NOW / HOUR) + 1}`);
    assert.equal(logPaths(parseView('/v/territory/-3,12', NOW), null, NOW), '/v1/survey/log/territory/-3/12');
  });

  test('a surveyor\'s numbers, latest words and line, as the page shares them', () => {
    const s = summarize(parseView(`/v/surveyor/ZED/${WEEK}`, NOW), SLICE, NOW);
    assert.deepEqual(s.stats, [['Words charted first', '3'], ['In the shared world', '2'], ['Top territory', 'Acorn Hollow']]);
    assert.deepEqual(s.words.map((w) => [w.w, w.hue, w.stray]), [['BIRCH', 40, false], ['MONET', 56, true], ['ACORN', 40, false]]);
    assert.equal(s.line, 'ZED charted 3 words first in Letterfield’s shared survey in the week of 9 Nov 2026, most in Acorn Hollow.');
    assert.equal(s.token, `3.${(NOW - HOUR).toString(36)}`);
    const none = summarize(parseView(`/v/surveyor/ZED/${WEEK}`, NOW), { ...SLICE, words: 0, world: 0, entries: [], topTerritories: [] }, NOW);
    assert.equal(none.line, 'No words signed ZED in Letterfield’s shared survey in the week of 9 Nov 2026.');
  });

  test('a theme\'s and a territory\'s', () => {
    const theme = summarize(parseView('/v/theme/11/all', NOW), { ...SLICE, topSurveyors: [['ZED', 3]] }, NOW);
    assert.equal(theme.name, THEMES[11].name);
    assert.equal(theme.hue, THEMES[11].hue);
    assert.deepEqual(theme.stats[1], ['Top surveyor', 'ZED']);
    assert.match(theme.line, /^3 hidden words charted in Letterfield’s .+ territories so far\.$/);
    const territory = summarize(parseView('/v/territory/0,0', NOW), { charted: 2, total: 112, entries: [entry('BIRCH', NOW), entry('ACORN', NOW - HOUR, 'ABC')], themes: {} }, NOW);
    assert.equal(territory.name, regionName(0, 0));
    assert.equal(territory.hue, THEMES[regionTheme(0, 0)].hue);
    assert.deepEqual(territory.stats, [['Hidden words charted', '2 of 112'], ['Surveyors', '2'], ['Latest', '10 Nov 2026']]);
    assert.equal(territory.line, `${regionName(0, 0)}, in Letterfield’s shared survey: 2 of its 112 hidden words charted so far, by 2 surveyors.`);
  });

  test('draws the card, its address only where it fits beside the heading', () => {
    const v = parseView(`/v/surveyor/ZED/${WEEK}`, NOW), s = summarize(v, SLICE, NOW);
    const svg = viewSvg(v, s);
    assert.ok(svg.startsWith('<svg') && svg.includes('>ZED<') && svg.includes('>BIRCH<') && svg.includes('games.michaelwarkentin.com'));
    assert.ok(!viewSvg(v, s, { host: 'pr-51-games-preview.mwarkentin.workers.dev' }).includes('workers.dev'));
    assert.ok(viewSvg(v, s, { dark: true }).includes('#0F171A'));
  });
});

// ---------- The routes ----------

function fakeLog(answers) {
  const asked = [];
  return {
    asked,
    LOG: {
      fetch: async (request) => {
        const url = new URL(request.url);
        asked.push(url.href);
        const body = answers[url.pathname];
        if (body === 'hang') return new Promise(() => {});
        return body ? Response.json(body) : Response.json({ error: 'no' }, { status: 400 });
      },
    },
  };
}
let renders, waits;
const render = async (svg) => { renders.push(svg); return new Uint8Array([137, 80, 78, 71]); };
const ctx = { waitUntil: (p) => waits.push(p) };
async function get(path, env) {
  const response = await handle(new Request(`${SHARE}${path}`, { headers: { 'CF-Connecting-IP': '203.0.113.9' } }), env, ctx, render);
  await Promise.all(waits);
  return response;
}
const meta = (html, name) => html.match(new RegExp(`<meta (?:property|name)="${name}" content="([^"]*)"`))?.[1]?.replaceAll('&amp;', '&');

describe('a view\'s page and card', () => {
  let realNow;
  beforeEach(() => { renders = []; waits = []; delete globalThis.caches; realNow = Date.now; Date.now = () => NOW; });
  afterEach(() => { Date.now = realNow; });

  test('the page carries the card and sends people on to the view\'s own page', async () => {
    const log = fakeLog({ [`/v1/survey/log/surveyor/ZED/${WEEK_FROM}/${WEEK_FROM + 168}`]: SLICE });
    const response = await get(`/v/surveyor/ZED/${WEEK}`, { SITE_URL: SITE, ...log });
    const html = await response.text();
    // Asked under the API's own host, so it shares the log page's cache.
    assert.equal(log.asked[0], `${DEFAULT_LOG}/v1/survey/log/surveyor/ZED/${WEEK_FROM}/${WEEK_FROM + 168}`);
    assert.equal(meta(html, 'og:title'), 'ZED · Letterfield survey log');
    assert.equal(meta(html, 'og:description'), 'ZED charted 3 words first in Letterfield’s shared survey in the week of 9 Nov 2026, most in Acorn Hollow.');
    assert.equal(meta(html, 'og:url'), `${SHARE}/v/surveyor/ZED/${WEEK}`);
    assert.equal(meta(html, 'og:image'), `${SHARE}/v/surveyor/ZED/${WEEK}.png?s=3.${(NOW - HOUR).toString(36)}`);
    const target = `${SITE}/letterfield-log?surveyor=ZED&period=week&day=2026-11-09`;
    assert.ok(html.includes(`<meta http-equiv="refresh" content="0;url=${target.replaceAll('&', '&amp;')}">`));
    assert.ok(html.includes(`location.replace(${JSON.stringify(target)})`));
  });

  test('all time asks where the log starts first; a dark share points at the dark card', async () => {
    const to = Math.floor(NOW / HOUR) + 1;
    const log = fakeLog({ '/v1/survey/log/span': { first: LOG_BEGAN_HOUR, last: to - 1 }, [`/v1/survey/log/theme/11/${LOG_BEGAN_HOUR}/${to}`]: { ...SLICE, topSurveyors: [['ZED', 3]] } });
    const html = await (await get('/v/d/theme/11/all', { SITE_URL: SITE, ...log })).text();
    assert.match(meta(html, 'og:image'), new RegExp(`^${SHARE}/v/d/theme/11/all\\.png\\?s=`));
    assert.ok(html.includes(`content="0;url=${SITE}/letterfield-log?theme=11"`));
  });

  test('the card is drawn from the log, kept for good when asked for with the state it shows', async () => {
    const log = fakeLog({ '/v1/survey/log/territory/0/0': { charted: 2, total: 112, entries: [entry('BIRCH', NOW)], themes: { 11: ['Forest', 40] } } });
    const token = `2.${NOW.toString(36)}`;
    const current = await get(`/v/territory/0,0.png?s=${token}`, { SITE_URL: SITE, ...log });
    assert.equal(current.headers.get('Content-Type'), 'image/png');
    assert.match(current.headers.get('Cache-Control'), /max-age=31536000/);
    assert.ok(renders[0].includes('>BIRCH<'));
    const stale = await get('/v/territory/0,0.png?s=old', { SITE_URL: SITE, ...log });
    assert.equal(stale.headers.get('Cache-Control'), 'public, max-age=300');
  });

  test('without the log, as on a Worker Preview or when it doesn\'t answer, the game\'s own preview stands in', async () => {
    const html = await (await get(`/v/surveyor/ZED/${WEEK}`, { SITE_URL: SITE })).text();
    assert.equal(meta(html, 'og:image'), `${SITE}/previews/letterfield.jpg`);
    assert.equal(meta(html, 'og:title'), 'ZED · Letterfield survey log');
    assert.ok(html.includes(`content="0;url=${SITE}/letterfield-log?surveyor=ZED&amp;period=week&amp;day=2026-11-09"`));
    const image = await get(`/v/surveyor/ZED/${WEEK}.png`, { SITE_URL: SITE });
    assert.equal(image.status, 302);
    assert.equal(image.headers.get('Location'), `${SITE}/previews/letterfield.jpg`);
    assert.equal(renders.length, 0);
  });

  test('a log that hangs is given up on', { timeout: LOG_MS + 2000 }, async () => {
    const log = fakeLog({ [`/v1/survey/log/surveyor/ZED/${WEEK_FROM}/${WEEK_FROM + 168}`]: 'hang' });
    const html = await (await get(`/v/surveyor/ZED/${WEEK}`, { SITE_URL: SITE, ...log })).text();
    assert.equal(meta(html, 'og:image'), `${SITE}/previews/letterfield.jpg`);
  });

  test('an address that isn\'t a view is not found', async () => {
    assert.equal((await get('/v/surveyor/ZED/week/2026-11-10/1-2', { SITE_URL: SITE })).status, 404);
    assert.equal((await get('/v/nobody', { SITE_URL: SITE })).status, 404);
  });
});
