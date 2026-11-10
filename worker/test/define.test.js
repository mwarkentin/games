// Tests for Letterfield's definitions (src/define.js), run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"
// Wiktionary and Wikipedia are a fake fetch answering with replies shaped
// like theirs (trimmed from real ones; their text is CC BY-SA 4.0), and D1 is
// node:sqlite loaded with the real migrations, as in leaderboard.test.js.

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { beforeEach, describe, test } from 'node:test';

import worker from '../src/index.js';
import {
  EDGE_CACHE_S, MAX_SENSES, MAX_SENSE_CHARS, NONE_CACHE_S, NONE_RETRY_MS, UA, forgetDefine, lookUp, plain, routeDefine, wiktionarySenses,
} from '../src/define.js';
import { THEMES } from '../src/letterfield-world.js';

const MIGRATIONS = new URL('../migrations/', import.meta.url);
const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 10, 10, 12);
const th = (name) => THEMES.findIndex((t) => t.name === name);

function fakeD1() {
  const db = new DatabaseSync(':memory:');
  for (const file of readdirSync(MIGRATIONS).sort()) db.exec(readFileSync(new URL(file, MIGRATIONS), 'utf8'));
  const statement = (sql, params = []) => ({
    bind: (...values) => statement(sql, values),
    all: async () => ({ results: db.prepare(sql).all(...params) }),
    run: async () => { db.prepare(sql).run(...params); return { success: true }; },
  });
  return { prepare: (sql) => statement(sql), raw: db, rows: () => db.prepare('SELECT word, context, fetched_at FROM definitions ORDER BY word, context').all().map((r) => ({ ...r })) };
}

const BASIL = {
  en: [
    { partOfSpeech: 'Noun', language: 'English', definitions: [
      { definition: '' },
      { definition: 'A <a rel="mw:WikiLink" href="/wiki/plant" title="plant">plant</a> (<span class="biota"><a rel="mw:WikiLink" href="/wiki/Ocimum_basilicum#Translingual"><i>Ocimum basilicum</i></a></span>).' },
      { definition: 'The <a rel="mw:WikiLink" href="/wiki/leaves">leaves</a> of this plant used as a <a href="/wiki/herb">herb</a>.' },
      { definition: 'Any other species in the genus <i>Ocimum</i>.' },
    ] },
    { partOfSpeech: 'Noun', language: 'English', definitions: [{ definition: "The angle to which a joiner's tool is ground away." }] },
    { partOfSpeech: 'Verb', language: 'English', definitions: [{ definition: '<span class="usage-label-sense"></span> To grind the edge of a tool to an <a href="/wiki/acute">acute</a> angle.' }] },
  ],
  fr: [{ partOfSpeech: 'Noun', language: 'French', definitions: [{ definition: 'basil' }] }],
};
const MONET = {
  en: [{ partOfSpeech: 'Proper noun', language: 'English', definitions: [
    { definition: '<a rel="mw:WikiLink/Interwiki" href="https://en.wikipedia.org/wiki/Claude%20Monet" class="extiw">Claude Monet</a>, French <a rel="mw:WikiLink" href="/wiki/painter">painter</a>.' },
    { definition: '<span>A </span><a href="x">rural municipality</a><span> (the </span><a href="y">Rural Municipality of Monet No. 257</a><span>) in western </span><a href="z">Saskatchewan</a><span>, Canada.</span>' },
  ] }],
};
const ONLY_A_SURNAME = { en: [{ partOfSpeech: 'Proper noun', language: 'English', definitions: [{ definition: 'A <a href="/wiki/surname">surname</a> from German.' }] }] };
const CRONKITE_SEARCH = { query: { pages: [{ pageid: 1, ns: 0, title: 'Walter Cronkite', extract: 'Walter Leland Cronkite Jr. (November 4, 1916 – July 17, 2009) was an American broadcast journalist who served as anchorman for the CBS Evening News for 19 years.' }] } };

// A fake fetch over a table of URL → reply (an object is JSON; a number is a
// bare status), logging every URL asked and the headers sent.
function fakeFetch(table) {
  const asked = [];
  const fetcher = async (url, init) => {
    asked.push({ url, headers: init.headers });
    for (const [match, reply] of Object.entries(table)) {
      if (!url.includes(match)) continue;
      if (typeof reply === 'number') return new Response('', { status: reply, headers: reply === 429 ? { 'Retry-After': '30' } : {} });
      return new Response(JSON.stringify(reply), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response('', { status: 404 });
  };
  return { fetcher, asked };
}

let env;
beforeEach(() => {
  forgetDefine();
  env = { DB: fakeD1(), ALLOWED_ORIGINS: ORIGIN, IP_SALT: 'salt' };
});

const get = (path, { origin = ORIGIN, method = 'GET' } = {}) =>
  new Request(`https://api.test${path}`, { method, headers: { Origin: origin, 'CF-Connecting-IP': '203.0.113.9' } });

describe('reading Wiktionary', () => {
  test('keeps the text of its HTML', () => {
    assert.equal(plain('A <a href="/wiki/plant">plant</a> (<i>Ocimum basilicum</i> ).'), 'A plant (Ocimum basilicum).');
    assert.equal(plain('Tom &amp; Jerry&#39;s &lt;b&gt;'), "Tom & Jerry's <b>");
  });

  test('takes English senses, one from each entry before seconds, and skips empty ones', () => {
    const senses = wiktionarySenses(BASIL);
    assert.equal(senses.length, MAX_SENSES);
    assert.deepEqual(senses, [
      { pos: 'noun', text: 'A plant (Ocimum basilicum).' },
      { pos: 'noun', text: "The angle to which a joiner's tool is ground away." },
      { pos: 'verb', text: 'To grind the edge of a tool to an acute angle.' },
    ]);
  });

  test('drops a sense that only says the word is a surname', () => {
    assert.deepEqual(wiktionarySenses(ONLY_A_SURNAME), []);
    assert.equal(wiktionarySenses(MONET)[0].text, 'Claude Monet, French painter.');
  });

  test('clips a long sense at a word', () => {
    const long = { en: [{ partOfSpeech: 'Noun', definitions: [{ definition: 'word '.repeat(100) }] }] };
    const [s] = wiktionarySenses(long);
    assert.ok(s.text.length <= MAX_SENSE_CHARS);
    assert.ok(s.text.endsWith('word…'));
  });
});

describe('looking a word up', () => {
  test('asks Wiktionary in lower case, names itself, and keeps the answer in D1 for every theme', async () => {
    const { fetcher, asked } = fakeFetch({ 'definition/basil': BASIL });
    const found = await lookUp(env, 'BASIL', 'Spice Rack', { now: NOW, fetcher });
    assert.equal(found.source, 'wiktionary');
    assert.equal(found.url, 'https://en.wiktionary.org/wiki/basil#English');
    assert.equal(asked.length, 1);
    assert.equal(asked[0].headers['User-Agent'], UA);
    assert.equal(asked[0].headers.Authorization, undefined);
    assert.deepEqual(env.DB.rows(), [{ word: 'BASIL', context: '', fetched_at: NOW }]);
    // In another theme, and later: from D1, with nothing fetched.
    const again = await lookUp(env, 'BASIL', 'Herb Garden', { now: NOW + 1, fetcher });
    assert.deepEqual(again, found);
    assert.equal(asked.length, 1);
  });

  test('tries the word as a name when the lower case has no English entry', async () => {
    const { fetcher, asked } = fakeFetch({ 'definition/monet': { fi: [] }, 'definition/Monet': MONET });
    const found = await lookUp(env, 'MONET', 'Old Masters', { now: NOW, fetcher });
    assert.equal(found.title, 'Monet');
    assert.equal(found.senses[0].text, 'Claude Monet, French painter.');
    assert.equal(asked.length, 2);
  });

  test("falls back to Wikipedia's search with the theme, kept for that theme only", async () => {
    const { fetcher, asked } = fakeFetch({ 'w/api.php': CRONKITE_SEARCH });
    const found = await lookUp(env, 'CRONKITE', 'Broadcast', { now: NOW, fetcher });
    assert.equal(found.source, 'wikipedia');
    assert.equal(found.url, 'https://en.wikipedia.org/wiki/Walter_Cronkite');
    assert.match(found.senses[0].text, /^Walter Leland Cronkite Jr\./);
    const search = new URL(asked[2].url).searchParams;
    assert.equal(search.get('gsrsearch'), 'cronkite Broadcast');
    assert.deepEqual(env.DB.rows().map((r) => r.context), ['Broadcast']);
  });

  test('turns down a Wikipedia article whose title lacks the word, or a disambiguation page', async () => {
    const off = { query: { pages: [{ title: 'Television news', extract: 'News on television.' }] } };
    assert.deepEqual((await lookUp(env, 'CRONKITE', 'Broadcast', { now: NOW, fetcher: fakeFetch({ 'w/api.php': off }).fetcher })).senses, []);
    forgetDefine(); env.DB = fakeD1();
    const dab = { query: { pages: [{ title: 'Cronkite (disambiguation)', pageprops: { disambiguation: '' }, extract: 'Cronkite may refer to' }] } };
    assert.deepEqual((await lookUp(env, 'CRONKITE', 'Broadcast', { now: NOW, fetcher: fakeFetch({ 'w/api.php': dab }).fetcher })).senses, []);
  });

  test('keeps an empty answer for a month, then asks again', async () => {
    const { fetcher, asked } = fakeFetch({});
    const none = await lookUp(env, 'NEWYEAR', 'Festivals', { now: NOW, fetcher });
    assert.deepEqual(none.senses, []);
    assert.equal(asked.length, 3);  // two Wiktionary forms and a search
    await lookUp(env, 'NEWYEAR', 'Festivals', { now: NOW + NONE_RETRY_MS - 1, fetcher });
    assert.equal(asked.length, 3);
    await lookUp(env, 'NEWYEAR', 'Festivals', { now: NOW + NONE_RETRY_MS, fetcher });
    assert.equal(asked.length, 6);
  });

  test('sends a Wikimedia token when there is one', async () => {
    const { fetcher, asked } = fakeFetch({ 'definition/basil': BASIL });
    await lookUp({ ...env, WIKIMEDIA_TOKEN: 'tok' }, 'BASIL', 'Spice Rack', { now: NOW, fetcher });
    assert.equal(asked[0].headers.Authorization, 'Bearer tok');
  });
});

describe('GET /v1/define', () => {
  test('answers a found word with its senses and source, cached for a month', async () => {
    const { fetcher } = fakeFetch({ 'definition/basil': BASIL });
    const res = await routeDefine(get(`/v1/define/BASIL/${th('Spice Rack')}`), env, { fetcher, now: NOW });
    assert.equal(res.status, 200);
    assert.equal(res.headers.get('Access-Control-Allow-Origin'), ORIGIN);
    assert.equal(res.headers.get('Cache-Control'), `public, max-age=${EDGE_CACHE_S}`);
    const body = await res.json();
    assert.equal(body.word, 'BASIL');
    assert.equal(body.source, 'wiktionary');
    assert.equal(body.senses.length, 3);
  });

  test('answers a word with no definition with empty senses, cached for a day', async () => {
    const res = await routeDefine(get(`/v1/define/NEWYEAR/${th('Festivals')}`), env, { fetcher: fakeFetch({}).fetcher, now: NOW });
    assert.equal(res.status, 200);
    assert.equal(res.headers.get('Cache-Control'), `public, max-age=${NONE_CACHE_S}`);
    assert.deepEqual(await res.json(), { word: 'NEWYEAR', senses: [], source: null, title: null, url: null });
  });

  test('refuses a word that is not in the theme, or a theme that does not exist, without fetching', async () => {
    const { fetcher, asked } = fakeFetch({});
    for (const path of [`/v1/define/BASIL/${th('Broadcast')}`, '/v1/define/BASIL/999', '/v1/define/ZZZZZQ/0']) {
      const res = await routeDefine(get(path), env, { fetcher, now: NOW });
      assert.equal(res.status, 400, path);
    }
    assert.equal((await routeDefine(get('/v1/define/basil/0'), env, { fetcher })).status, 404);
    assert.equal(asked.length, 0);
  });

  test('says to try later when Wikimedia turns it away, keeps nothing, and backs off', async () => {
    const busy = fakeFetch({ 'definition/basil': 429 });
    const res = await routeDefine(get(`/v1/define/BASIL/${th('Spice Rack')}`), env, { fetcher: busy.fetcher, now: NOW });
    assert.equal(res.status, 503);
    assert.deepEqual(env.DB.rows(), []);
    // While backing off, it doesn't ask again.
    const second = await routeDefine(get(`/v1/define/BASIL/${th('Spice Rack')}`), env, { fetcher: busy.fetcher, now: NOW });
    assert.equal(second.status, 503);
    assert.equal(busy.asked.length, 1);
  });

  test('a network failure is a try-later too', async () => {
    const fetcher = async () => { throw new TypeError('network'); };
    const res = await routeDefine(get(`/v1/define/BASIL/${th('Spice Rack')}`), env, { fetcher, now: NOW });
    assert.equal(res.status, 503);
  });

  test('counts only new words against the per-address limit', async () => {
    const keys = [];
    env.DEFINE_LOOKUPS = { limit: async ({ key }) => { keys.push(key); return { success: keys.length <= 1 }; } };
    const { fetcher } = fakeFetch({ 'definition/basil': BASIL, 'definition/thirsty': BASIL });
    assert.equal((await routeDefine(get(`/v1/define/BASIL/${th('Spice Rack')}`), env, { fetcher, now: NOW })).status, 200);
    assert.equal((await routeDefine(get(`/v1/define/BASIL/${th('Herb Garden')}`), env, { fetcher, now: NOW })).status, 200);
    assert.equal(keys.length, 1);  // the second came from D1
    assert.match(keys[0], /^define:[0-9a-f]{64}$/);
    assert.equal((await routeDefine(get(`/v1/define/THIRSTY/${th('Desert')}`), env, { fetcher, now: NOW })).status, 429);
  });

  test('takes only GET, and leaves other paths alone', async () => {
    assert.equal((await routeDefine(get(`/v1/define/BASIL/${th('Spice Rack')}`, { method: 'POST' }), env)).status, 405);
    assert.equal(routeDefine(get('/v1/scores'), env), null);
  });

  test('is reached through the Worker', async () => {
    const res = await worker.fetch(get(`/v1/define/BASIL/999`), env);
    assert.equal(res.status, 400);
  });
});
