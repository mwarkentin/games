// The Worker's routes, with the survey, R2, the edge cache and the rate
// limiter faked, and a renderer that only counts.
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

import { keyOf, regionName, regionTheme } from '../../worker/src/letterfield-world.js';
import { ASK_MS, PAGE_MS, claimOf, forgetTotals, handle, novaOf, stateToken, totalsOf } from '../src/app.js';
import { FAR, PLACED, slugOf } from './card.test.js';

const SHARE = 'https://share.test';
const SITE = 'https://games.test';
const AT = Date.UTC(2026, 10, 9, 15);
const SLUG = slugOf(PLACED);
const KEY = keyOf(PLACED.w, PLACED.x, PLACED.y, PLACED.d);

function fakeEnv({ claims = new Map(), totals = { charted: 4480, total: 1_119_752, players: 3 }, limited = false } = {}) {
  const asked = { sectors: [], atlas: 0, limits: [] };
  const stored = new Map();
  const env = {
    SITE_URL: SITE,
    IP_SALT: 'salt',
    SECTORS: {
      idFromName: (name) => name,
      get: (name) => ({
        fetch: async (url) => {
          asked.sectors.push([name, url]);
          const key = decodeURIComponent(new URL(url).pathname.slice('/claim/'.length));
          const c = claims.get(key);
          return c ? Response.json(c) : Response.json({ error: 'not charted' }, { status: 404 });
        },
      }),
    },
    ATLAS: {
      idFromName: (name) => name,
      get: () => ({ fetch: async () => { asked.atlas++; return Response.json(totals); } }),
    },
    CARDS: {
      get: async (key) => (stored.has(key) ? { arrayBuffer: async () => stored.get(key) } : null),
      put: async (key, value) => { stored.set(key, value); },
    },
    RENDERS: { limit: async ({ key }) => { asked.limits.push(key); return { success: !limited }; } },
  };
  return { env, asked, stored };
}

function fakeCache() {
  const kept = new Map();
  return { kept, default: { match: async (r) => kept.get(r.url)?.clone(), put: async (r, response) => { kept.set(r.url, response); } } };
}

let renders, waits;
const render = async (svg) => { renders.push(svg); return new Uint8Array([137, 80, 78, 71, renders.length]); };
const ctx = { waitUntil: (p) => waits.push(p) };
async function get(path, env, headers = {}) {
  const response = await handle(new Request(`${SHARE}${path}`, { headers: { 'CF-Connecting-IP': '203.0.113.9', ...headers } }), env, ctx, render);
  await Promise.all(waits);
  return response;
}
const meta = (html, name) => html.match(new RegExp(`<meta (?:property|name)="${name}" content="([^"]*)"`))?.[1]?.replaceAll('&amp;', '&');

beforeEach(() => { renders = []; waits = []; forgetTotals(); delete globalThis.caches; });
afterEach(() => { delete globalThis.caches; mock.timers.reset(); });

describe('the page', () => {
  test('carries the card for a word, and sends people on to the game at it', async () => {
    const { env } = fakeEnv({ claims: new Map([[KEY, { initials: 'ZED', at: AT }]]) });
    const response = await get(`/f/${SLUG}`, env);
    assert.equal(response.status, 200);
    assert.match(response.headers.get('Content-Type'), /^text\/html/);
    const html = await response.text();
    assert.equal(meta(html, 'og:title'), `${PLACED.w} · Letterfield`);
    assert.match(meta(html, 'og:description'), /Charted first by ZED on 9 Nov 2026\.$/);
    // og:url is the share address itself, never the game.
    assert.equal(meta(html, 'og:url'), `${SHARE}/f/${SLUG}`);
    assert.equal(meta(html, 'og:image'), `${SHARE}/f/${SLUG}.png?s=cZED.20766.0.4`);
    assert.equal(meta(html, 'og:image:width'), '1200');
    assert.equal(meta(html, 'twitter:card'), 'summary_large_image');
    const target = `${SITE}/letterfield#${SLUG}`;
    assert.ok(html.includes(`<meta http-equiv="refresh" content="0;url=${target}">`));
    assert.ok(html.includes(`location.replace(${JSON.stringify(target)})`));
    assert.ok(html.includes('<meta name="robots" content="noindex">'));
    assert.equal(renders.length, 0);
  });

  test('a dark share points at the dark card, and still sends people to the same game', async () => {
    const { env } = fakeEnv();
    const html = await (await get(`/f/d/${SLUG}`, env)).text();
    assert.equal(meta(html, 'og:image'), `${SHARE}/f/d/${SLUG}.png?s=o.0.4`);
    assert.equal(meta(html, 'og:url'), `${SHARE}/f/d/${SLUG}`);
    assert.ok(html.includes(`location.replace(${JSON.stringify(`${SITE}/letterfield#${SLUG}`)})`));
  });

  test('a word not on the map still gets a page: the game\'s own card, and the game', async () => {
    const { env } = fakeEnv();
    const response = await get('/f/f-zzzz-1-2-3', env);
    assert.equal(response.status, 200);
    const html = await response.text();
    assert.equal(meta(html, 'og:image'), `${SITE}/previews/letterfield.jpg`);
    assert.ok(html.includes(`location.replace(${JSON.stringify(`${SITE}/letterfield`)})`));
  });

  test('is kept at the edge for a minute', async () => {
    const cache = fakeCache();
    globalThis.caches = cache;
    const { env, asked } = fakeEnv();
    await get(`/f/${SLUG}`, env);
    await get(`/f/${SLUG}?utm=x`, env);
    assert.equal(asked.sectors.length, 1);
    assert.equal(cache.kept.get(`${SHARE}/f/${SLUG}`).headers.get('Cache-Control'), `public, max-age=${PAGE_MS / 1000}`);
  });

  test('answers nothing else', async () => {
    const { env } = fakeEnv();
    assert.equal((await get('/f/', env)).status, 404);
    assert.equal((await get('/x/f-coral-1-2-3', env)).status, 404);
    assert.equal((await get('/f/x/' + SLUG, env)).status, 404);
    assert.equal((await handle(new Request(`${SHARE}/f/${SLUG}`, { method: 'POST' }), env, ctx, render)).status, 405);
    const home = await get('/', env);
    assert.equal(home.status, 302);
    assert.equal(home.headers.get('Location'), `${SITE}/letterfield`);
  });
});

describe('the card', () => {
  test('is drawn for a word on the map, and refused for anything else', async () => {
    const { env } = fakeEnv();
    const response = await get(`/f/${SLUG}.png`, env);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('Content-Type'), 'image/png');
    assert.equal(renders.length, 1);
    assert.ok(renders[0].includes(PLACED.w));
    assert.ok(renders[0].includes('NOT YET CHARTED'));
    assert.ok(renders[0].includes('0.4% of the shared map charted'));
    assert.ok(renders[0].includes('>games.test<'));
    assert.equal((await get('/f/f-zzzz-1-2-3.png', env)).status, 404);
    assert.equal(renders.length, 1);
  });

  test('a charted word\'s card is drawn once and kept in R2; others are only kept at the edge', async () => {
    const { env, stored } = fakeEnv({ claims: new Map([[KEY, { initials: 'ZED', at: AT }]]) });
    const path = `/f/${SLUG}.png?s=cZED.20766.0.4`;
    const first = await get(path, env);
    assert.equal(first.headers.get('Cache-Control'), 'public, max-age=31536000, immutable');
    assert.deepEqual([...stored.keys()], [`m4/light/${SLUG}/cZED.20766.0.4.png`]);
    await get(path, env);  // another data centre: no edge copy, but R2 has it
    assert.equal(renders.length, 1);

    const open = fakeEnv();
    await get(`/f/${SLUG}.png?s=o.0.4`, open.env);
    assert.equal(open.stored.size, 0);
  });

  test('asked for with an old or made-up state, it draws the card as it is now, kept briefly and never stored', async () => {
    const { env, stored } = fakeEnv({ claims: new Map([[KEY, { initials: 'ZED', at: AT }]]) });
    const response = await get(`/f/${SLUG}.png?s=cEVE.1.50`, env);
    assert.equal(response.headers.get('Cache-Control'), 'public, max-age=300');
    assert.ok(renders[0].includes('by ZED · 9 Nov 2026'));
    assert.ok(!renders[0].includes('EVE'));
    assert.equal(stored.size, 0);
  });

  test('is drawn dark for a dark share', async () => {
    const { env } = fakeEnv();
    await get(`/f/d/${SLUG}.png`, env);
    assert.ok(renders[0].includes('#0F171A'));
  });

  test('cards already drawn are never limited; new ones are, per hashed address', async () => {
    const cache = fakeCache();
    globalThis.caches = cache;
    const { env, asked } = fakeEnv({ limited: true });
    const over = await get(`/f/${SLUG}.png?s=o.0.4`, env);
    assert.equal(over.status, 302);
    assert.equal(over.headers.get('Location'), `${SITE}/previews/letterfield.jpg`);
    assert.equal(renders.length, 0);
    assert.equal(asked.limits.length, 1);
    assert.match(asked.limits[0], /^[0-9a-f]{64}$/);
    assert.ok(!asked.limits[0].includes('203.0.113.9'));

    const free = fakeEnv();
    await get(`/f/${SLUG}.png?s=o.0.4`, free.env);  // drawn, and kept at the edge
    assert.equal(renders.length, 1);
    const again = await get(`/f/${SLUG}.png?s=o.0.4`, env);  // the limited address, from the edge
    assert.equal(again.status, 200);
    assert.equal(renders.length, 1);
  });
});

describe('asking the survey', () => {
  test('asks the word\'s own sector by its key', async () => {
    const { env, asked } = fakeEnv();
    assert.equal(await claimOf(env, { ...PLACED }), null);
    const sx = Math.floor(PLACED.x / 192), sy = Math.floor(PLACED.y / 192);
    assert.deepEqual(asked.sectors, [[`${sx},${sy}`, `https://sector/claim/${encodeURIComponent(KEY)}`]]);
  });

  test('never asks a sector outside the shared world, so a card can\'t make one', async () => {
    const { env, asked } = fakeEnv();
    assert.equal(await claimOf(env, { ...FAR }), undefined);
    assert.equal(asked.sectors.length, 0);
    await get(`/f/${slugOf(FAR)}.png`, env);
    assert.equal(asked.sectors.length, 0);
    assert.ok(renders[0].includes('FIND IT ON THE MAP'));
  });

  test('keeps the totals for a minute', async () => {
    const { env, asked } = fakeEnv();
    await totalsOf(env, 1000);
    await totalsOf(env, 1000 + 59_000);
    assert.equal(asked.atlas, 1);
    await totalsOf(env, 1000 + 61_000);
    assert.equal(asked.atlas, 2);
  });

  test('leaves the lines off when the survey doesn\'t answer in time, or fails', async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    const hanging = { idFromName: (n) => n, get: () => ({ fetch: () => new Promise(() => {}) }) };
    const pending = claimOf({ SECTORS: hanging }, { ...PLACED });
    mock.timers.tick(ASK_MS);
    assert.equal(await pending, undefined);
    mock.timers.reset();

    const older = { idFromName: (n) => n, get: () => ({ fetch: async () => new Response('not found', { status: 404 }) }) };
    assert.equal(await claimOf({ SECTORS: older }, { ...PLACED }), undefined);

    const broken = { idFromName: (n) => n, get: () => ({ fetch: async () => { throw new Error('down'); } }) };
    assert.equal(await claimOf({ SECTORS: broken }, { ...PLACED }), undefined);
    assert.equal(await totalsOf({ ATLAS: broken }), null);
    const { env } = fakeEnv();
    await get(`/f/${SLUG}.png`, { ...env, SECTORS: broken, ATLAS: broken });
    assert.ok(renders[0].includes('FIND IT ON THE MAP'));
    assert.ok(!renders[0].includes('shared map charted'));
  });

  test('works with no survey bindings at all, as a Worker Preview does', async () => {
    const { env } = fakeEnv();
    const { SECTORS, ATLAS, ...preview } = env;
    const html = await (await get(`/f/${SLUG}`, preview)).text();
    assert.match(meta(html, 'og:image'), /\?s=u\.x$/);
    await get(`/f/${SLUG}.png?s=u.x`, preview);
    assert.equal(renders.length, 1);
  });

  test('names the state the card shows', () => {
    assert.equal(stateToken({ claim: { initials: 'ZED', at: AT }, progressText: '3% of the shared map charted' }), 'cZED.20766.3');
    assert.equal(stateToken({ claim: { initials: '', at: AT }, progressText: null }), 'c.20766.x');
    assert.equal(stateToken({ claim: null, progressText: 'Every word on the shared map charted' }), 'o.every');
    assert.equal(stateToken({ claim: undefined, progressText: 'Under 0.1% of the shared map charted' }), 'u.under');
  });
});

// ---------- A supernova the log hasn't got yet ----------

describe('a territory gone supernova moments ago', () => {
  const NOW = Date.UTC(2026, 10, 11, 1, 47), at = NOW - 20_000;
  const NOVA = [0, 1, at, 'MULTITOOL', 15, 71, 0, 'LMW', at - 21 * 3_600_000, 116, 1, 'LMW', 116, regionTheme(0, 1)];
  // The log, a few words behind and with no supernova yet; the sector, with it.
  function sectorEnv({ charted = 112, nova = NOVA, status = 200 } = {}) {
    const asked = [];
    const env = {
      SITE_URL: SITE,
      LOG: { fetch: async () => Response.json({ rx: 0, ry: 1, charted, total: 116, nova: null, entries: [['TENT', 5, 50, 0, 0, 'LMW', at - 60_000, 15]], themes: {} }) },
      SECTORS: {
        idFromName: (name) => name,
        get: (name) => ({
          fetch: async (url) => {
            asked.push([name, new URL(url).pathname]);
            return status === 200 && nova ? Response.json({ nova }) : Response.json({ error: 'no supernova' }, { status: 404 });
          },
        }),
      },
    };
    return { env, asked };
  }
  let realNow;
  beforeEach(() => { renders = []; waits = []; delete globalThis.caches; realNow = Date.now; Date.now = () => NOW; });
  afterEach(() => { Date.now = realNow; });

  test('asks its sector, and shows the supernova card straight away', async () => {
    const { env, asked } = sectorEnv();
    const html = await (await get('/v/territory/0,1', env)).text();
    assert.deepEqual(asked, [['0,0', '/nova/0/1']]);
    assert.match(meta(html, 'og:description'), /^Sodden Wold went supernova in Letterfield’s shared survey on 11 Nov 2026: all 116 hidden words charted by 1 surveyor in 21 hours, the last, MULTITOOL, by LMW\.$/);
    assert.match(meta(html, 'og:image'), /\/v\/territory\/0,1\.png\?s=112\.[a-z0-9]+n$/);
    await get('/v/territory/0,1.png', env);
    assert.ok(renders[0].includes('>LETTERFIELD · SUPERNOVA · ') && renders[0].includes('>MULTITOOL<'));
  });

  test('keeps the log\'s card when the sector has none, can\'t say, or nothing is charted there', async () => {
    for (const [state, wantAsked] of [[{ nova: null }, 1], [{ status: 500 }, 1], [{ charted: 0 }, 0]]) {
      renders = [];
      const { env, asked } = sectorEnv(state);
      await get('/v/territory/0,1.png', env);
      assert.equal(asked.length, wantAsked, JSON.stringify(state));
      assert.ok(renders[0].includes('SURVEY LOG · TERRITORY'), JSON.stringify(state));
    }
  });

  test('checks what the sector says, and never asks one outside the shared world', async () => {
    const { env, asked } = sectorEnv({ nova: [...NOVA.slice(0, 13)] });
    assert.equal(await novaOf(env, 0, 1), null);  // the wrong shape
    assert.equal(await novaOf(sectorEnv({ nova: [1, ...NOVA.slice(1)] }).env, 0, 1), null);  // another territory's
    assert.deepEqual(await novaOf(sectorEnv().env, 0, 1), NOVA);
    assert.equal(await novaOf(env, 400, 1), null);
    assert.equal(await novaOf({}, 0, 1), null);
    assert.equal(asked.filter(([, path]) => path === '/nova/400/1').length, 0);
    assert.equal(regionName(0, 1), 'Sodden Wold');
  });
});
