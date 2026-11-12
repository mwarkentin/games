// Players across devices. The games name a player by a random token kept in
// localStorage (`games.player`; see "Who a player is" in SURVEY.md), which
// lives on one device. A link carries it to another: the first device asks
// for a one-time code, shows it (as a code, a link and a QR code), and the
// other device redeems it for the token and a few settings, and is then the
// same player. See "One player, several devices" in SURVEY.md.
//
//   POST /v1/link                   {token, carry} → 201 {code, expires}
//   POST /v1/link/<code>/status     {token} → {state}: waiting, used or gone (gone to anyone who didn't make it)
//   POST /v1/link/<code>            {} → {token, carry}, once; then 404
//
// carry: {initials, guild: {code, name, tag} | null, muted: [ids], listed, emotes}
//
// A code is eight characters from the groups' alphabet (850 billion codes),
// good for LINK_MS and for one use. Making codes and trying them are each
// limited per address, so guessing one is hopeless. The token only ever
// travels in a request's body, never in an address.

import { CODE_ALPHABET, HttpError, INITIALS, corsHeaders, hashIp, json, rateLimit } from './leaderboard.js';
import { goodName } from './survey-guild.js';
import { GUILD_CODE, GUILD_TAG, PID, TOKEN } from './survey-social.js';

export const LINK_MS = 10 * 60000;        // a code lasts this long
export const LINK_CODE = /^[A-HJKMNP-Z2-9]{8}$/;
const MUTED_MAX = 200;
const MAX_BODY = 8192;
const LINK_PATH = /^\/v1\/link(?:\/([^/]{1,16})(\/status)?)?$/;

// The settings a link carries, checked and in a fixed shape, or null.
export function cleanCarry(c) {
  if (!c || typeof c !== 'object') return null;
  const { initials = '', guild = null, muted = [], listed = true, emotes = true } = c;
  if (!(initials === '' || (typeof initials === 'string' && INITIALS.test(initials)))) return null;
  if (guild !== null && !(guild && typeof guild.code === 'string' && GUILD_CODE.test(guild.code) && goodName(guild.name) && typeof guild.tag === 'string' && GUILD_TAG.test(guild.tag))) return null;
  if (!Array.isArray(muted) || muted.length > MUTED_MAX || !muted.every((p) => typeof p === 'string' && PID.test(p))) return null;
  if (typeof listed !== 'boolean' || typeof emotes !== 'boolean') return null;
  return { initials, guild: guild && { code: guild.code, name: guild.name, tag: guild.tag }, muted, listed, emotes };
}

async function readBody(request) {
  const text = await request.text();
  if (text.length > MAX_BODY) throw new HttpError(413, 'body too large');
  if (!text) return {};
  try { return JSON.parse(text); } catch { throw new HttpError(400, 'body must be JSON'); }
}

// The link paths, or null for any other.
export function routeLinks(request, env, now = Date.now()) {
  const url = new URL(request.url);
  const m = url.pathname.match(LINK_PATH);
  if (!m || !env.DB) return null;
  const cors = corsHeaders(request, env);
  return (async () => {
    try {
      if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
      if (request.method !== 'POST') throw new HttpError(405, 'method not allowed');
      if (!cors['Access-Control-Allow-Origin']) throw new HttpError(403, 'origin not allowed');
      const body = await readBody(request);
      const db = env.DB, address = await hashIp(request, env.IP_SALT);
      if (!m[1]) {
        if (typeof body?.token !== 'string' || !TOKEN.test(body.token)) throw new HttpError(400, 'token must be 32 hex digits');
        const carry = cleanCarry(body.carry ?? {});
        if (!carry) throw new HttpError(400, 'carry is not something a link takes');
        await rateLimit(db, 'link', address, now);
        await db.prepare('DELETE FROM links WHERE expires < ?').bind(now).run();
        for (let attempt = 0; attempt < 8; attempt++) {
          const code = [...crypto.getRandomValues(new Uint8Array(8))].map((b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
          const made = await db.prepare('INSERT INTO links (code, token, carry, expires) VALUES (?, ?, ?, ?) ON CONFLICT (code) DO NOTHING RETURNING code')
            .bind(code, body.token, JSON.stringify(carry), now + LINK_MS).first('code');
          if (made) return json({ code, expires: now + LINK_MS }, 201, cors);
        }
        throw new HttpError(503, 'could not pick a free code, try again');
      }
      const code = m[1].toUpperCase();
      if (m[2]) {
        // Only whoever made the code, who knows the token, hears what became of it.
        const row = LINK_CODE.test(code) && typeof body?.token === 'string'
          ? await db.prepare('SELECT token, expires, used FROM links WHERE code = ?').bind(code).first() : null;
        const state = !row || row.token !== body.token || row.expires < now ? 'gone' : row.used ? 'used' : 'waiting';
        return json({ state }, 200, cors);
      }
      // Every try counts, right or wrong, so codes can't be guessed.
      await rateLimit(db, 'linkTry', address, now);
      // One statement claims it, so two tries at once can't both have it; then what it carried goes.
      const row = LINK_CODE.test(code)
        ? await db.prepare('UPDATE links SET used = 1 WHERE code = ? AND used = 0 AND expires >= ? RETURNING token, carry').bind(code, now).first()
        : null;
      if (!row) throw new HttpError(404, 'no such code, or it has run out');
      await db.prepare("UPDATE links SET carry = '' WHERE code = ?").bind(code).run();
      return json({ token: row.token, carry: JSON.parse(row.carry) }, 200, cors);
    } catch (error) {
      if (error instanceof HttpError) return json({ error: error.message }, error.status, cors);
      throw error;
    }
  })();
}
