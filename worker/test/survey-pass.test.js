// Tests for the survey's Turnstile passes (src/survey-pass.js and the pass
// check in routeSurvey), run with the rest:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"
// Siteverify is always a fake here: nothing calls Cloudflare. The secret is
// Cloudflare's documented always-passes test secret.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { hashAddress } from '../src/leaderboard.js';
import { ACTION, PASS_MS, PASS_PATH, SITEVERIFY, checkPass, handlePass, issuePass, verifyToken } from '../src/survey-pass.js';
import { ADDRESS_HEADER, addressOf, routeSurvey } from '../src/survey.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const SECRET = '1x0000000000000000000000000000000AA';   // Turnstile's test secret: always passes
const TOKEN = 'XXXX.DUMMY.TOKEN.XXXX';                  // what Turnstile's test site keys hand out
const NOW = Date.UTC(2026, 10, 6, 12);
const IP = '203.0.113.7';

// A stand-in for siteverify: answers each call with the next reply (a
// function of the request body, a status, or a thrown error) and records it.
function fakeSiteverify(...replies) {
  const calls = [];
  const fetcher = async (url, init) => {
    const body = JSON.parse(init.body);
    calls.push({ url, body });
    const reply = replies.length > 1 ? replies.shift() : replies[0];
    if (reply instanceof Error) throw reply;
    if (typeof reply === 'number') return new Response('oops', { status: reply });
    return Response.json(typeof reply === 'function' ? reply(body) : reply);
  };
  return { fetcher, calls };
}
const passes = (extra = {}) => ({ success: true, hostname: 'games.michaelwarkentin.com', action: ACTION, 'error-codes': [], ...extra });

describe('passes', () => {
  const address = 'a'.repeat(64);

  test('work for the address they were issued to, until they expire', async () => {
    const { pass, expires } = await issuePass(SECRET, address, NOW);
    assert.equal(expires, NOW + PASS_MS);
    assert.match(pass, /^\d{13}\.[A-Za-z0-9_-]{43}$/);
    assert.equal(await checkPass(SECRET, address, pass, NOW), true);
    assert.equal(await checkPass(SECRET, address, pass, expires - 1), true);
    assert.equal(await checkPass(SECRET, address, pass, expires), false);
  });

  test('are refused from another address, with another secret, or altered', async () => {
    const { pass } = await issuePass(SECRET, address, NOW);
    assert.equal(await checkPass(SECRET, 'b'.repeat(64), pass, NOW), false);
    assert.equal(await checkPass('2x0000000000000000000000000000000AA', address, pass, NOW), false);
    const [expires, sig] = pass.split('.');
    assert.equal(await checkPass(SECRET, address, `${Number(expires) + PASS_MS}.${sig}`, NOW), false);  // a longer life
    assert.equal(await checkPass(SECRET, address, `${expires}.${sig.slice(0, -1)}${sig.at(-1) === 'A' ? 'B' : 'A'}`, NOW), false);
    for (const junk of [null, '', 'nonsense', `${expires}.`, `${expires}.${sig}=`, 42]) assert.equal(await checkPass(SECRET, address, junk, NOW), false);
  });

  test('never last longer than PASS_MS from now, even if signed for later', async () => {
    const { pass } = await issuePass(SECRET, address, NOW + 2 * PASS_MS);
    assert.equal(await checkPass(SECRET, address, pass, NOW), false);
  });
});

describe('verifyToken', () => {
  const env = { TURNSTILE_SECRET: SECRET };

  test('sends the secret, token, address and an idempotency key to siteverify', async () => {
    const fake = fakeSiteverify(passes());
    assert.deepEqual(await verifyToken(env, TOKEN, IP, fake.fetcher), { ok: true });
    assert.equal(fake.calls[0].url, SITEVERIFY);
    const { secret, response, remoteip, idempotency_key: key } = fake.calls[0].body;
    assert.deepEqual([secret, response, remoteip], [SECRET, TOKEN, IP]);
    assert.match(key, /^[0-9a-f-]{36}$/);
  });

  test('passes on what Turnstile refused', async () => {
    const fake = fakeSiteverify({ success: false, 'error-codes': ['timeout-or-duplicate'] });
    assert.deepEqual(await verifyToken(env, TOKEN, IP, fake.fetcher), { ok: false, status: 403, codes: ['timeout-or-duplicate'] });
    assert.equal(fake.calls.length, 1);
  });

  test('checks the action, and the hostname when TURNSTILE_HOSTNAMES is set', async () => {
    assert.deepEqual(await verifyToken(env, TOKEN, IP, fakeSiteverify(passes({ action: 'login' })).fetcher), { ok: false, status: 403, codes: ['wrong-action'] });
    assert.equal((await verifyToken(env, TOKEN, IP, fakeSiteverify(passes({ hostname: 'evil.test' })).fetcher)).ok, true);
    const strict = { ...env, TURNSTILE_HOSTNAMES: 'games.michaelwarkentin.com, localhost' };
    assert.equal((await verifyToken(strict, TOKEN, IP, fakeSiteverify(passes({ hostname: 'evil.test' })).fetcher)).ok, false);
    assert.equal((await verifyToken(strict, TOKEN, IP, fakeSiteverify(passes({ hostname: 'localhost' })).fetcher)).ok, true);
  });

  test('retries once, with the same key, when siteverify fails, then gives up', async () => {
    const flaky = fakeSiteverify(new Error('reset'), passes());
    assert.deepEqual(await verifyToken(env, TOKEN, IP, flaky.fetcher), { ok: true });
    assert.equal(flaky.calls.length, 2);
    assert.equal(flaky.calls[0].body.idempotency_key, flaky.calls[1].body.idempotency_key);

    const busy = fakeSiteverify({ success: false, 'error-codes': ['internal-error'] }, passes());
    assert.deepEqual(await verifyToken(env, TOKEN, IP, busy.fetcher), { ok: true });

    const down = fakeSiteverify(502);
    assert.deepEqual(await verifyToken(env, TOKEN, IP, down.fetcher), { ok: false, status: 503, codes: ['unreachable'] });
    assert.equal(down.calls.length, 2);
  });
});

describe('POST /v1/survey/pass', () => {
  const json = (body, status, headers) => Response.json(body, { status, headers });
  const cors = { 'Access-Control-Allow-Origin': ORIGIN };
  const post = (body) => new Request(`https://survey.test${PASS_PATH}`, { method: 'POST', headers: { 'Content-Type': 'text/plain', 'CF-Connecting-IP': IP }, body });
  const env = { TURNSTILE_SECRET: SECRET };

  test('turns a token into a pass for the player\'s address', async () => {
    const fake = fakeSiteverify(passes());
    const res = await handlePass(post(JSON.stringify({ token: TOKEN })), env, 'aaaa', cors, json, fake.fetcher);
    assert.equal(res.status, 200);
    const { pass, expires } = await res.json();
    assert.ok(expires > Date.now());
    assert.equal(await checkPass(SECRET, 'aaaa', pass), true);
  });

  test('refuses bad requests without asking Turnstile', async () => {
    const fake = fakeSiteverify(passes());
    for (const body of ['', 'nope', '{}', JSON.stringify({ token: 7 }), JSON.stringify({ token: 'x'.repeat(2049) })]) {
      assert.equal((await handlePass(post(body), env, 'aaaa', cors, json, fake.fetcher)).status, 400, body.slice(0, 20));
    }
    assert.equal((await handlePass(post(JSON.stringify({ token: TOKEN })), env, 'aaaa', {}, json, fake.fetcher)).status, 403);
    assert.equal((await handlePass(post(JSON.stringify({ token: TOKEN })), {}, 'aaaa', cors, json, fake.fetcher)).status, 404);
    assert.equal(fake.calls.length, 0);
  });

  test('says why when Turnstile refuses or can\'t be reached', async () => {
    const refused = await handlePass(post(JSON.stringify({ token: TOKEN })), env, 'aaaa', cors, json, fakeSiteverify({ success: false, 'error-codes': ['invalid-input-response'] }).fetcher);
    assert.equal(refused.status, 403);
    assert.deepEqual(await refused.json(), { error: 'not verified', codes: ['invalid-input-response'] });
    const down = await handlePass(post(JSON.stringify({ token: TOKEN })), env, 'aaaa', cors, json, fakeSiteverify(new Error('down')).fetcher);
    assert.equal(down.status, 503);
  });

  test('limits how often one address asks', async () => {
    let n = 0;
    const limited = { ...env, SURVEY_JOINS: { limit: async ({ key }) => { assert.equal(key, 'pass:aaaa'); return { success: ++n <= 1 }; } } };
    const fake = fakeSiteverify(passes());
    assert.equal((await handlePass(post(JSON.stringify({ token: TOKEN })), limited, 'aaaa', cors, json, fake.fetcher)).status, 200);
    assert.equal((await handlePass(post(JSON.stringify({ token: TOKEN })), limited, 'aaaa', cors, json, fake.fetcher)).status, 429);
    assert.equal(fake.calls.length, 1);
  });
});

describe('routeSurvey with Turnstile on', () => {
  const forwarded = [];
  const env = {
    ALLOWED_ORIGINS: ORIGIN,
    TURNSTILE_SECRET: SECRET,
    SECTORS: { idFromName: (name) => ({ name }), get: (id) => ({ fetch: async (request) => { forwarded.push([id.name, request]); return new Response('ok'); } }) },
  };
  const join = (pass, ip = IP) => routeSurvey(new Request(`https://survey.test/v1/survey/0/0${pass ? `?pass=${encodeURIComponent(pass)}` : ''}`, {
    headers: { Origin: ORIGIN, Upgrade: 'websocket', 'CF-Connecting-IP': ip },
  }), env);

  // Stand-ins for the runtime's WebSocketPair and its 101 responses, as in survey.test.js.
  async function refused(promise) {
    let pair;
    globalThis.WebSocketPair = function WebSocketPair() {
      const socket = () => ({ sent: [], accept() { this.accepted = true; }, send(t) { this.sent.push(JSON.parse(t)); }, close(code) { this.code = code; } });
      pair = [socket(), socket()];
      return { 0: pair[0], 1: pair[1] };
    };
    const RealResponse = Response;
    globalThis.Response = class { constructor(body, init) { Object.assign(this, init); } };
    try {
      const res = await promise();
      assert.equal(res.status, 101);
      assert.equal(res.webSocket, pair[0]);
      return pair[1];
    } finally {
      globalThis.Response = RealResponse;
      delete globalThis.WebSocketPair;
    }
  }

  test('lets a join with a good pass through to its sector, without the pass', async () => {
    const address = await hashAddress(addressOf(IP), env.IP_SALT);
    const { pass } = await issuePass(SECRET, address);
    assert.equal(await (await join(pass)).text(), 'ok');
    const [name, request] = forwarded.at(-1);
    assert.equal(name, '0,0');
    assert.equal(new URL(request.url).search, '');
    assert.equal(request.headers.get(ADDRESS_HEADER), address);
    assert.equal(request.headers.get('Upgrade'), 'websocket');
  });

  test('answers a join without a good pass itself, so the game knows to get one', async () => {
    const before = forwarded.length;
    const address = await hashAddress(addressOf(IP), env.IP_SALT);
    const { pass } = await issuePass(SECRET, address);
    for (const attempt of [() => join(null), () => join('junk'), () => join(pass, '198.51.100.9')]) {
      const server = await refused(attempt);
      assert.ok(server.accepted);
      assert.deepEqual(server.sent, [{ t: 'unverified' }]);
      assert.equal(server.code, 4001);
    }
    assert.equal(forwarded.length, before);
  });

  test('takes the pass from any address in the same IPv6 /64', async () => {
    const { pass } = await issuePass(SECRET, await hashAddress(addressOf('2001:db8:aa:bb::1'), env.IP_SALT));
    assert.equal(await (await join(pass, '2001:db8:aa:bb:9:9:9:9')).text(), 'ok');
  });

  test('routes POST /v1/survey/pass, and only POST', async () => {
    const realFetch = globalThis.fetch;
    globalThis.fetch = fakeSiteverify(passes()).fetcher;
    try {
      const res = await routeSurvey(new Request(`https://survey.test${PASS_PATH}`, {
        method: 'POST', headers: { Origin: ORIGIN, 'CF-Connecting-IP': IP, 'Content-Type': 'text/plain' }, body: JSON.stringify({ token: TOKEN }),
      }), env);
      assert.equal(res.status, 200);
      assert.equal(res.headers.get('Access-Control-Allow-Origin'), ORIGIN);
      const { pass } = await res.json();
      assert.equal(await (await join(pass)).text(), 'ok');
    } finally {
      globalThis.fetch = realFetch;
    }
    assert.equal((await routeSurvey(new Request(`https://survey.test${PASS_PATH}`, { headers: { Origin: ORIGIN } }), env)).status, 405);
  });

  test('changes nothing while TURNSTILE_SECRET is unset', async () => {
    const off = { ...env, TURNSTILE_SECRET: undefined };
    const res = await routeSurvey(new Request('https://survey.test/v1/survey/0/0', { headers: { Origin: ORIGIN, Upgrade: 'websocket' } }), off);
    assert.equal(await res.text(), 'ok');
  });
});
