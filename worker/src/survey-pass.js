// Survey passes: proof that a player passed a Turnstile check, so the survey
// can turn away bots spread over many addresses (see TURNSTILE.md). Without
// the TURNSTILE_SECRET secret, there are no passes and every join goes ahead
// as before. With it, passes are handed out and checked, but a join without
// one is only counted (routeSurvey in survey.js) until TURNSTILE_REQUIRED is
// "true" in wrangler.toml.
//
//   POST /v1/survey/pass   {"token": "<Turnstile token>"}
//     → 200 {"pass", "expires"}
//     → 400 {"error"} for a missing or malformed token
//     → 403 {"error", "codes"} when Turnstile says no, or for another origin
//     → 429 when one address asks too often
//     → 503 when Turnstile can't be reached
//
// A Turnstile token can be checked once and lasts 300 s, but a player joins
// up to four sector sockets at once and opens about ten an hour as they roam,
// and every socket reconnects after a deploy. So the Worker checks the token
// once with siteverify and hands back a pass: an expiry and an HMAC of it and
// the player's hashed address. Sector joins carry it as ?pass=, and the
// Worker checks it without storing anything or asking anyone. A pass works
// only from the address it was issued to, so one solved challenge can't be
// shared across a pool of proxies; a player whose address changes is asked
// again, invisibly for almost everyone.

export const SITEVERIFY = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';
export const PASS_PATH = '/v1/survey/pass';
export const PASS_MS = 60 * 60 * 1000;   // a pass lasts an hour
export const ACTION = 'survey';          // the widget's action, checked on the reply
const VERIFY_TIMEOUT_MS = 5000;
const MAX_TOKEN = 2048;                  // Turnstile's longest token

const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

// The pass key comes from the Turnstile secret, with its own label, so there's
// one secret to manage and rotating it ends every pass.
const keys = new Map();
function passKey(secret) {
  let key = keys.get(secret);
  if (!key) {
    const enc = new TextEncoder();
    key = crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
      .then((k) => crypto.subtle.sign('HMAC', k, enc.encode('letterfield survey pass v1')))
      .then((raw) => crypto.subtle.importKey('raw', raw, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']));
    keys.set(secret, key);
  }
  return key;
}

const signed = (address, expires) => new TextEncoder().encode(`${address}.${expires}`);

export async function issuePass(secret, address, now = Date.now()) {
  const expires = now + PASS_MS;
  const sig = await crypto.subtle.sign('HMAC', await passKey(secret), signed(address, expires));
  return { pass: `${expires}.${b64url(sig)}`, expires };
}

// Whether a pass is one this Worker issued to this address and hasn't expired.
export async function checkPass(secret, address, pass, now = Date.now()) {
  const m = typeof pass === 'string' && pass.match(/^(\d{13})\.([A-Za-z0-9_-]{43})$/);
  if (!m) return false;
  const expires = Number(m[1]);
  if (expires <= now || expires > now + PASS_MS) return false;
  const sig = Uint8Array.from(atob(m[2].replace(/-/g, '+').replace(/_/g, '/') + '='), (c) => c.charCodeAt(0));
  return crypto.subtle.verify('HMAC', await passKey(secret), sig, signed(address, expires));
}

// Asks Turnstile about a token: {ok: true} or {ok: false, status, codes}.
// One retry, with the same idempotency key, if Turnstile fails or is slow.
export async function verifyToken(env, token, ip, fetcher = fetch) {
  const body = { secret: env.TURNSTILE_SECRET, response: token, idempotency_key: crypto.randomUUID() };
  if (ip) body.remoteip = ip;
  let reply = null;
  for (let attempt = 0; attempt < 2 && !reply; attempt++) {
    try {
      const res = await fetcher(SITEVERIFY, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(VERIFY_TIMEOUT_MS),
      });
      if (res.ok) reply = await res.json();
    } catch { /* retried once, then 503 */ }
    if (reply && (reply['error-codes'] ?? []).includes('internal-error')) reply = null;
  }
  if (!reply) return { ok: false, status: 503, codes: ['unreachable'] };
  if (reply.success !== true) return { ok: false, status: 403, codes: reply['error-codes'] ?? [] };
  // The widget's action, and the page it ran on when the hostnames are set.
  if (reply.action && reply.action !== ACTION) return { ok: false, status: 403, codes: ['wrong-action'] };
  const hosts = (env.TURNSTILE_HOSTNAMES || '').split(',').map((h) => h.trim()).filter(Boolean);
  if (hosts.length && !hosts.includes(reply.hostname)) return { ok: false, status: 403, codes: ['wrong-hostname'] };
  return { ok: true };
}

// POST /v1/survey/pass. `address` is the player's hashed address, `json` the
// leaderboard's JSON responder, `cors` the request's CORS headers.
export async function handlePass(request, env, address, cors, json, fetcher = fetch) {
  if (!cors['Access-Control-Allow-Origin']) return json({ error: 'origin not allowed' }, 403, cors);
  if (!env.TURNSTILE_SECRET) return json({ error: 'passes are off' }, 404, cors);
  let token = null;
  try { ({ token } = JSON.parse(await request.text())); } catch { /* below */ }
  if (typeof token !== 'string' || !token || token.length > MAX_TOKEN) return json({ error: 'expected {"token"}' }, 400, cors);
  // Siteverify costs nothing, but each ask is a Worker request: one address
  // gets as many as it may open sockets.
  if (env.SURVEY_JOINS) {
    try { if ((await env.SURVEY_JOINS.limit({ key: `pass:${address}` })).success === false) return json({ error: 'slow down' }, 429, cors); } catch { /* let it through */ }
  }
  const verdict = await verifyToken(env, token, request.headers.get('CF-Connecting-IP'), fetcher);
  if (!verdict.ok) return json({ error: verdict.status === 503 ? 'turnstile unreachable' : 'not verified', codes: verdict.codes }, verdict.status, cors);
  return json(await issuePass(env.TURNSTILE_SECRET, address), 200, cors);
}
