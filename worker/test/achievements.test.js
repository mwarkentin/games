// Tests for Letterfield's achievements on the Worker (src/achievements.js):
// the rules shared with the game, receipts for signed finds, the badges they
// prove, and a sector that signs and shows them. Run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

import worker from '../src/index.js';
import { CORE, MARK_DRAW, MARK_GROUPS, MARK_TEXT, TRUSTED_UNTIL, UNIVERSE_EDGE, badgeSig, checkBadge, checkCard, checkReceipt, routeBadges, signCard, signFind } from '../src/achievements.js';
import { chunk } from '../src/letterfield-world.js';
import { AREA, Sector } from '../src/survey.js';
import { playerId } from '../src/survey-social.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const SALT = 'test-salt';
const DAY = 86400000;
const token = (n) => n.toString(16).padStart(32, '0');
// Every hidden word of territory (rx, ry), in chunk order.
const territoryWords = (rx, ry) => {
  const out = [];
  for (let cy = ry * 4; cy < ry * 4 + 4; cy++) for (let cx = rx * 4; cx < rx * 4 + 4; cx++) out.push(...chunk(cx, cy).words);
  return out;
};
const bare = ({ w, x, y, d }) => ({ w, x, y, d });

describe('the achievements core', () => {
  const block = (text) => {
    const start = text.indexOf('// ---- BEGIN ACHIEVEMENTS CORE ----'), end = text.indexOf('// ---- END ACHIEVEMENTS CORE ----');
    assert.ok(start >= 0 && end > start, 'lost its ACHIEVEMENTS CORE markers');
    return text.slice(start, end);
  };

  test('is the same in letterfield.html, word for word', () => {
    const game = readFileSync(new URL('../../letterfield.html', import.meta.url), 'utf8');
    const ours = readFileSync(new URL('../src/achievements.js', import.meta.url), 'utf8');
    assert.equal(block(ours), block(game));
  });

  test("draws and names its badges as letterfield.html does, word for word, every one", () => {
    const art = (text) => {
      const start = text.indexOf('// ---- BEGIN BADGE ART ----'), end = text.indexOf('// ---- END BADGE ART ----');
      assert.ok(start >= 0 && end > start, 'lost its BADGE ART markers');
      return text.slice(start, end);
    };
    const game = readFileSync(new URL('../../letterfield.html', import.meta.url), 'utf8');
    const ours = readFileSync(new URL('../src/achievements.js', import.meta.url), 'utf8');
    assert.equal(art(ours), art(game));
    for (const [id, g] of CORE.CATALOG) {
      assert.ok(MARK_TEXT[id] && MARK_DRAW[MARK_TEXT[id][0]], `${id} has words and a drawing`);
      assert.ok(MARK_GROUPS.some((x) => x.id === g), `${id}'s group`);
    }
  });

  test("names only themes the map has, and puts the universe's edge where the survey's is", () => {
    for (const i of [...CORE.BIRDS, ...CORE.SEAS, ...CORE.SKIES, ...CORE.NATIONS]) assert.ok(i >= 0);
    assert.equal(UNIVERSE_EDGE, AREA * 4);
    assert.equal(CORE.CATALOG.length, 40);
  });

  test('Number of the Beast is a secret earned at 666 finds, not 665, and signed finds can prove it', () => {
    const [, group, flags] = CORE.CATALOG.find(([id]) => id === 'number-of-the-beast');
    assert.equal(group, 'notes');
    assert.ok(flags.includes('h'));
    assert.ok(CORE.PROVABLE.has('number-of-the-beast'));
    const words = [];
    for (let ry = 0; words.length < 666; ry++) for (let rx = 0; rx < 8 && words.length < 666; rx++) words.push(...territoryWords(rx, ry));
    const finds = words.slice(0, 666).map((w, i) => ({ ...w, t: Date.UTC(2026, 10, 1) + i * 60000, th: 0 }));
    const have = (n) => CORE.CHECK.get('number-of-the-beast')(CORE.tally(finds.slice(0, n), [], Date.UTC(2026, 10, 20)).T);
    assert.deepEqual(have(665).slice(0, 2), [665, 666]);
    assert.deepEqual(have(666).slice(0, 2), [666, 666]);
    const { reached } = CORE.tally(finds, [], Date.UTC(2026, 10, 20), ['number-of-the-beast']);
    assert.equal(reached['number-of-the-beast'].at, finds[665].t);
  });

  // A card names badges by their places in the catalog, so a card made today
  // must mean the same once the catalog grows.
  test('only grows at its end, and a card names every badge others may see', () => {
    const FIRST = ['first-mark', 'field-book', 'bound-volume', 'great-atlas', 'first-light', 'trailblazer', 'pathfinder', 'cairn',
      'wanderer', 'gazetteer', 'every-last-word', 'five-sheets', 'lions-share', 'map-key', 'full-legend', 'lexicographer',
      'dawn-chorus', 'seven-seas', 'star-chart', 'passport', 'happy-accident', 'serendipity', 'long-measure', 'compass-rose',
      'mirror-image', 'self-portrait', 'over-the-horizon', 'edge-of-the-universe', 'here-be-dragons', 'witness', 'starfield',
      'last-word', 'seven-days', 'lunar-month', 'thirty-days', 'full-circle', 'fellowship', 'two-places', 'hats-off'];
    assert.deepEqual(CORE.CATALOG.slice(0, FIRST.length).map(([id]) => id), FIRST);
    assert.deepEqual(CORE.CATALOG.slice(FIRST.length).map(([id]) => id), ['number-of-the-beast']);
    const all = new Set(CORE.CATALOG.map(([id]) => id));
    assert.deepEqual(CORE.cardIds(CORE.cardMask(all)), [...all]);
    assert.equal(CORE.PROVABLE.size, 34);  // not Cairn, Witness, Starfield or the company's three
    assert.deepEqual(CORE.cardIds(CORE.cardMask(new Set(['hats-off', 'seven-seas', 'witness']))), ['seven-seas', 'witness', 'hats-off']);
    assert.equal(CORE.cardMask(new Set()), 0);
    assert.ok(Number.isSafeInteger(CORE.cardMask(all)));
  });
});

describe('receipts', () => {
  const env = { IP_SALT: SALT };

  test("prove a find for the player they were made for, and nothing else", async () => {
    const pid = await playerId(token(1)), other = await playerId(token(2));
    const word = bare(chunk(0, 0).words[0]), at = Date.UTC(2026, 11, 1, 9);
    const r = await signFind(env, pid, word, at, 'f');
    assert.deepEqual(await checkReceipt(env, pid, { ...word, r }), { at, f: true, z: false });
    assert.equal(await checkReceipt(env, other, { ...word, r }), null);
    assert.equal(await checkReceipt(env, pid, { ...word, x: word.x + 1, r }), null);
    assert.equal(await checkReceipt(env, pid, { ...word, r: r.replace('.f.', '.fz.') }), null);
    assert.equal(await checkReceipt({ IP_SALT: 'another salt' }, pid, { ...word, r }), null);
    // Without a salt there's no key worth trusting, so nothing is signed or believed.
    assert.equal(await checkReceipt({}, pid, { ...word, r }), null);
  });
});

// The parts of a Durable Object's state a Sector uses, and its sockets.
function fakeState() {
  const db = new DatabaseSync(':memory:');
  const sockets = [];
  return {
    sockets,
    storage: { sql: { exec(query, ...b) { const rows = db.prepare(query).all(...b); return { toArray: () => rows, one: () => rows[0] }; } } },
    acceptWebSocket: (ws) => sockets.push(ws),
    getWebSockets: () => sockets.filter((ws) => ws.open),
  };
}
function fakeSocket() {
  let attachment = null;
  return {
    open: true,
    sent: [],
    send(text) { const frame = JSON.parse(text); this.sent.push(...(Array.isArray(frame) ? frame : [frame])); },
    accept() {},
    close() { this.open = false; },
    serializeAttachment(value) { attachment = structuredClone(value); },
    deserializeAttachment: () => structuredClone(attachment),
    all(type) { return this.sent.filter((m) => m.t === type); },
  };
}

describe('a sector', () => {
  let sector, clock;
  const env = { IP_SALT: SALT };
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout'] });
    sector = new Sector(fakeState(), env);
    clock = Date.UTC(2026, 11, 20, 12);
    sector.now = () => clock;
  });
  afterEach(() => mock.timers.reset());
  const say = (ws, message) => sector.webSocketMessage(ws, JSON.stringify(message));
  async function join(n, initials, more = {}) {
    const ws = fakeSocket();
    sector.join(ws, 0, 0);
    await say(ws, { t: 'me', initials, ...(n ? { token: token(n) } : {}), ...more });
    return ws;
  }
  const claim = async (ws, word) => { clock += 2000; await say(ws, { t: 'claim', ...bare(word) }); };

  test("signs each word a surveyor circles, for them alone: charted first, or someone else's", async () => {
    const amy = await join(1, 'AMY'), zed = await join(2, 'ZED'), old = await join(0, 'OLD');
    const word = chunk(0, 0).words[0];
    await claim(amy, word);
    const [signed] = amy.all('signed');
    assert.equal(signed.k, word.key);
    assert.deepEqual(await checkReceipt(env, await playerId(token(1)), { ...bare(word), r: signed.r }), { at: clock, f: true, z: false });
    assert.deepEqual(zed.all('signed'), []);
    // Zed circles it too: theirs isn't first, but it's still theirs to prove.
    await claim(zed, word);
    assert.deepEqual(await checkReceipt(env, await playerId(token(2)), { ...bare(word), r: zed.all('signed')[0].r }), { at: clock, f: false, z: false });
    // A game that sends no token (an older one) gets no receipt.
    await claim(old, chunk(0, 0).words[1]);
    assert.deepEqual(old.all('signed'), []);
  });

  test('says which word set off a supernova', async () => {
    const amy = await join(1, 'AMY'), pid = await playerId(token(1));
    const words = territoryWords(1, 2);
    for (const o of words) await claim(amy, o);
    const receipts = amy.all('signed');
    assert.equal(receipts.length, words.length);
    const last = await checkReceipt(env, pid, { ...bare(words.at(-1)), r: receipts.at(-1).r });
    assert.deepEqual([last.f, last.z], [true, true]);
    assert.equal((await checkReceipt(env, pid, { ...bare(words[0]), r: receipts[0].r })).z, false);
  });

  test('shows the badge a surveyor picked, if the Worker signed it for them', async () => {
    const pid = await playerId(token(1));
    const amy = await join(1, 'AMY', { badge: ['seven-seas', await badgeSig(env, pid, 'seven-seas')] });
    await say(amy, { t: 'pos', x: 10, y: 10 });
    const zed = await join(2, 'ZED', { badge: ['seven-seas', await badgeSig(env, pid, 'seven-seas')] });  // Amy's, not Zed's
    await say(zed, { t: 'pos', x: 12, y: 10 });
    clock += 2000;
    await say(amy, { t: 'here' });
    await mock.timers.tick(2000);
    const p = Object.fromEntries(amy.all('presence').at(-1).p.map((q) => [q[1], q]));
    assert.deepEqual(p.AMY.slice(4), [[], 'seven-seas']);
    assert.deepEqual(p.ZED.slice(4), []);
    assert.equal(await checkBadge(env, pid, ['no-such-badge', await badgeSig(env, pid, 'no-such-badge')]), null);
    // One no find can prove, like Hats Off, is shown with a signature too.
    assert.equal(await checkBadge(env, pid, ['hats-off', await badgeSig(env, pid, 'hats-off')]), 'hats-off');
  });

  test("shows a surveyor's card without its signature, if the Worker signed it for them", async () => {
    const pid = await playerId(token(1)), mask = CORE.cardMask(new Set(['first-mark', 'seven-seas'])), day = 20400;
    const card = await signCard(env, pid, mask, day);
    const amy = await join(1, 'AMY', { card });
    await say(amy, { t: 'pos', x: 10, y: 10 });
    const zed = await join(2, 'ZED', { card });  // Amy's, not Zed's
    await say(zed, { t: 'pos', x: 12, y: 10 });
    const bea = await join(3, 'BEA', { card: await signCard(env, await playerId(token(3)), mask, day), badge: ['seven-seas', await badgeSig(env, await playerId(token(3)), 'seven-seas')] });
    await say(bea, { t: 'pos', x: 14, y: 10 });
    clock += 2000;
    await say(amy, { t: 'here' });
    await mock.timers.tick(2000);
    const p = Object.fromEntries(amy.all('presence').at(-1).p.map((q) => [q[1], q]));
    const shown = `${mask.toString(36)}.${day.toString(36)}`;
    assert.deepEqual(p.AMY.slice(4), [[], '', shown]);
    assert.deepEqual(p.BEA.slice(4), [[], 'seven-seas', shown]);
    assert.deepEqual(p.ZED.slice(4), []);
    // A new card from the same game takes the old one's place.
    const next = await signCard(env, pid, CORE.cardMask(new Set(['first-mark', 'seven-seas', 'map-key'])), day);
    await say(amy, { t: 'me', initials: 'AMY', token: token(1), card: next });
    clock += 2000;
    await say(amy, { t: 'here' });
    await mock.timers.tick(2000);
    const again = Object.fromEntries(amy.all('presence').at(-1).p.map((q) => [q[1], q]));
    assert.equal(again.AMY[6], next.split('.').slice(0, 2).join('.'));
  });
});

// The parts of D1 the badges use (their rate limit), with the leaderboard's migrations.
function fakeD1() {
  const db = new DatabaseSync(':memory:');
  const dir = new URL('../migrations/', import.meta.url);
  for (const file of readdirSync(dir).sort()) db.exec(readFileSync(new URL(file, dir), 'utf8'));
  const statement = (sql, params = []) => ({
    bind: (...values) => statement(sql, values),
    first: async (column) => { const row = db.prepare(sql).get(...params); return row ? (column ? row[column] : row) : null; },
    run: async () => { db.prepare(sql).run(...params); return { success: true }; },
  });
  return { prepare: (sql) => statement(sql) };
}

describe('POST /v1/survey/badges', () => {
  let env;
  const AFTER = TRUSTED_UNTIL + DAY, BEFORE = TRUSTED_UNTIL - DAY;
  beforeEach(() => { env = { DB: fakeD1(), ALLOWED_ORIGINS: ORIGIN, IP_SALT: SALT }; });
  const ask = async (body, now = AFTER, ip = '203.0.113.9') => {
    const res = await routeBadges(new Request('https://survey.test/v1/survey/badges', {
      method: 'POST', headers: { Origin: ORIGIN, 'CF-Connecting-IP': ip }, body: JSON.stringify({ token: token(1), ...body }),
    }), env, now);
    return [res.status, await res.json()];
  };
  // Finds signed for player 1, the sector's times one minute apart from `at`.
  const signed = async (words, at, flags = 'f', n = 1) => {
    const pid = await playerId(token(n));
    return Promise.all(words.map(async (o, i) => ({ ...bare(o), t: 0, r: await signFind(env, pid, o, at + i * 60000, flags) })));
  };

  test('signs the badges signed finds prove, worked out as the game does', async () => {
    const finds = await signed(territoryWords(0, 0).slice(0, 12), Date.UTC(2026, 11, 20, 10));
    const [status, { badges }] = await ask({ finds });
    assert.equal(status, 200);
    const pid = await playerId(token(1));
    assert.ok(badges['first-mark'] && badges['first-light']);
    assert.equal(badges['first-mark'], await badgeSig(env, pid, 'first-mark'));
    assert.equal(badges['field-book'], undefined);  // 12 finds, not 100
    assert.equal(badges.witness, undefined);  // being there for a supernova isn't something a find proves
  });

  test('signs Number of the Beast for 666 signed finds, not 665', async () => {
    const words = [];
    for (let rx = 0; words.length < 666; rx++) words.push(...territoryWords(rx, 0));
    const finds = await signed(words.slice(0, 666), Date.UTC(2026, 11, 20, 10));
    assert.equal((await ask({ finds: finds.slice(0, 665) }))[1].badges['number-of-the-beast'], undefined);
    const [, { badges }] = await ask({ finds });
    assert.equal(badges['number-of-the-beast'], await badgeSig(env, await playerId(token(1)), 'number-of-the-beast'));
    assert.equal(badges['bound-volume'], undefined);
  });

  test("takes the game's word for what it earned until TRUSTED_UNTIL, and after that only signed finds", async () => {
    // Always, though, for those no find can prove.
    const earned = ['great-atlas', 'witness', 'hats-off', 'not-a-badge'];
    assert.deepEqual(Object.keys((await ask({ earned }, BEFORE))[1].badges).sort(), ['great-atlas', 'hats-off', 'witness']);
    assert.deepEqual(Object.keys((await ask({ earned }, AFTER))[1].badges).sort(), ['hats-off', 'witness']);
  });

  const cardOf = async (card) => (card ? checkCard(env, await playerId(token(1)), card) : null);
  test("signs a card of every badge it stands behind, and the day the surveyor began", async () => {
    const at = Date.UTC(2026, 11, 20, 10), finds = await signed(territoryWords(0, 0).slice(0, 12), at);
    const [, { badges, card }] = await ask({ finds, earned: ['great-atlas'], since: Date.UTC(2026, 9, 4, 8) }, BEFORE);
    const got = await cardOf(card);
    assert.deepEqual(CORE.cardIds(got.mask), CORE.CATALOG.map(([id]) => id).filter((id) => badges[id]));
    assert.ok(CORE.cardIds(got.mask).includes('great-atlas'));
    assert.equal(got.day, Math.floor(Date.UTC(2026, 9, 4) / DAY));  // the game's word, while it's taken
    // Afterwards, the day comes from the earliest signed find.
    assert.equal((await cardOf((await ask({ finds, since: Date.UTC(2026, 9, 4) }))[1].card)).day, Math.floor(at / DAY));
    // Someone else's card means nothing here; with nothing signed, there's no card.
    const theirs = await signCard(env, await playerId(token(2)), CORE.cardMask(new Set(['great-atlas'])), 20000);
    assert.equal((await ask({ card: theirs }))[1].card, undefined);
    assert.equal(await checkCard(env, await playerId(token(1)), theirs), null);
  });

  test('keeps on a card what was signed before, once the game\'s word is no longer taken', async () => {
    const pid = await playerId(token(1));
    const [, before] = await ask({ earned: ['great-atlas', 'passport'], since: Date.UTC(2026, 9, 4) }, BEFORE);
    // Its last card brings back both badges and the day it began; badges it holds count too.
    const [, after] = await ask({ card: before.card, held: { 'seven-seas': await badgeSig(env, pid, 'seven-seas'), 'map-key': 'AAAAAAAAAAAA' } });
    const got = await cardOf(after.card);
    assert.deepEqual(CORE.cardIds(got.mask), ['great-atlas', 'seven-seas', 'passport']);
    assert.equal(got.day, Math.floor(Date.UTC(2026, 9, 4) / DAY));
    assert.deepEqual(Object.keys(after.badges).sort(), ['great-atlas', 'passport', 'seven-seas']);
    // A card can't be changed without its signature going bad.
    const forged = before.card.replace(/^[0-9a-z]+/, (CORE.cardMask(new Set(['great-atlas', 'passport', 'full-legend']))).toString(36));
    assert.equal(await checkCard(env, pid, forged), null);
  });

  test("counts no find signed for someone else, unsigned, or tampered with", async () => {
    const words = territoryWords(0, 0).slice(0, 3);
    const theirs = await signed(words, Date.UTC(2026, 11, 20, 10), 'f', 2);
    const tampered = (await signed(words, Date.UTC(2026, 11, 20, 10), ''))
      .map((f) => ({ ...f, r: f.r.replace(/^([0-9a-z]+)\.\./, '$1.f.') }));
    const unsigned = words.map((o) => ({ ...bare(o), t: Date.now() }));
    assert.deepEqual((await ask({ finds: [...theirs, ...tampered, ...unsigned] }))[1].badges, {});
  });

  test("works out days surveyed from the sector's times, on the surveyor's own dates", async () => {
    // Three finds an evening for a week, at 23:00 in Toronto (04:00 the next day in UTC).
    const words = territoryWords(0, 0), finds = [];
    for (let day = 0; day < 7; day++) finds.push(...await signed(words.slice(day * 3, day * 3 + 3), Date.UTC(2026, 11, 10 + day, 4), ''));
    const ids = async (z) => Object.keys((await ask({ finds, z }, Date.UTC(2026, 11, 17, 12)))[1].badges);
    assert.ok((await ids(300)).includes('seven-days'));
  });

  test('needs a salt to sign with and a real token, and limits how often an address asks', async () => {
    assert.equal((await ask({ token: 'nope' }))[0], 400);
    for (let i = 0; i < 30; i++) assert.equal((await ask({}))[0], 200);
    assert.equal((await ask({}))[0], 429);
    env.IP_SALT = '';
    assert.equal((await ask({}, AFTER, '198.51.100.1'))[0], 503);
    const res = await worker.fetch(new Request('https://survey.test/v1/survey/badges', { method: 'POST', headers: { Origin: ORIGIN }, body: '{}' }), { ...env, IP_SALT: SALT });
    assert.equal(res.status, 400);  // routed, and no token
  });
});
