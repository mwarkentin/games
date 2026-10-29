// Leaderboard API for games.michaelwarkentin.com, a Cloudflare Worker backed
// by a D1 (SQLite) database. See worker/README.md for setup.
//
//   GET  /v1/scores?game=<game>&board=<board>  top 10 for one board
//   POST /v1/scores                            save a score, returns its rank
//
// POST bodies are JSON sent as text/plain, which keeps the request "simple"
// so browsers skip the CORS preflight. Only origins in ALLOWED_ORIGINS get a
// response the browser will read, and only they may save scores.

const TOP = 10;            // scores returned per board
const KEEP = 100;          // scores stored per board; lower ones are deleted
const RATE_WINDOW_MS = 10 * 60 * 1000;
const RATE_LIMIT = 10;     // saves per IP address per window
const MAX_BODY_BYTES = 2048;

const INITIALS = /^[A-Z]{3}$/;
const BLOCKED_INITIALS = new Set([
  'ASS', 'CUM', 'DIC', 'DIK', 'FAG', 'FCK', 'FUC', 'FUK', 'KKK', 'NIG', 'SEX', 'SHT', 'TIT', 'WTF', 'XXX',
]);

const isInt = (value, min, max) => Number.isInteger(value) && value >= min && value <= max;

// Each game lists its boards and a plausibility check for a finished game.
// A determined cheater can still fake consistent numbers; these checks stop
// casual tampering such as editing only the score.
export const GAMES = {
  'funnels-and-buckets': {
    boards: ['starter', 'classic', 'challenge', 'starter-easy', 'classic-easy', 'challenge-easy'],
    check({ board, score, level, popped, seconds }) {
      if (!isInt(popped, 1, 100000)) return 'popped must be a positive whole number';
      if (!isInt(seconds, 1, 6 * 60 * 60)) return 'seconds must be between 1 and 21600';
      // The most a pop scores is 20 points (divide), tripled while the sponge is out.
      if (score > popped * 60) return 'score is too high for the bubbles popped';
      if (popped > seconds * 3 + 5) return 'too many bubbles popped for the time played';
      const perLevel = board.endsWith('-easy') ? 30 : 10;
      if (level !== 1 + Math.floor(popped / perLevel)) return 'level does not match bubbles popped';
      return null;
    },
  },
};

function corsHeaders(request, env) {
  const origin = request.headers.get('Origin');
  const allowed = (env.ALLOWED_ORIGINS || '').split(',').map((o) => o.trim()).filter(Boolean);
  const headers = { Vary: 'Origin' };
  if (origin && allowed.includes(origin)) {
    headers['Access-Control-Allow-Origin'] = origin;
    headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS';
    headers['Access-Control-Allow-Headers'] = 'Content-Type';
    headers['Access-Control-Max-Age'] = '86400';
  }
  return headers;
}

function json(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...headers },
  });
}

async function topScores(db, game, board) {
  const { results } = await db
    .prepare(
      `SELECT id, initials, score, level, created_at FROM scores
       WHERE game = ? AND board = ?
       ORDER BY score DESC, created_at ASC, id ASC LIMIT ?`,
    )
    .bind(game, board, TOP)
    .all();
  return results.map((row, i) => ({
    rank: i + 1, id: row.id, initials: row.initials, score: row.score, level: row.level, at: row.created_at,
  }));
}

async function hashIp(ip, salt) {
  const data = new TextEncoder().encode(`${salt || ''}:${ip}`);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

// Returns an error message for a bad submission, or null when it's valid.
export function validate(entry) {
  if (!entry || typeof entry !== 'object') return 'body must be a JSON object';
  const game = GAMES[entry.game];
  if (!game) return 'unknown game';
  if (!game.boards.includes(entry.board)) return 'unknown board';
  if (typeof entry.initials !== 'string' || !INITIALS.test(entry.initials)) return 'initials must be three letters A-Z';
  if (BLOCKED_INITIALS.has(entry.initials)) return 'pick different initials';
  if (!isInt(entry.score, 1, 10000000)) return 'score must be a positive whole number';
  if (!isInt(entry.level, 1, 10000)) return 'level must be a positive whole number';
  return game.check(entry);
}

async function readScores(url, db, cors) {
  const game = url.searchParams.get('game');
  const board = url.searchParams.get('board');
  if (!GAMES[game] || !GAMES[game].boards.includes(board)) return json({ error: 'unknown game or board' }, 400, cors);
  return json({ game, board, scores: await topScores(db, game, board) }, 200, cors);
}

async function saveScore(request, env, cors, now) {
  if (!cors['Access-Control-Allow-Origin']) return json({ error: 'origin not allowed' }, 403, cors);
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return json({ error: 'body too large' }, 413, cors);
  let entry;
  try {
    entry = JSON.parse(text);
  } catch {
    return json({ error: 'body must be JSON' }, 400, cors);
  }
  const problem = validate(entry);
  if (problem) return json({ error: problem }, 400, cors);

  const db = env.DB;
  const ipHash = await hashIp(request.headers.get('CF-Connecting-IP') || 'unknown', env.IP_SALT);
  await db.prepare('DELETE FROM submissions WHERE created_at < ?').bind(now - 6 * RATE_WINDOW_MS).run();
  const recent = await db
    .prepare('SELECT COUNT(*) AS n FROM submissions WHERE ip_hash = ? AND created_at >= ?')
    .bind(ipHash, now - RATE_WINDOW_MS)
    .first('n');
  if (recent >= RATE_LIMIT) return json({ error: 'too many scores saved, try again in a few minutes' }, 429, cors);
  await db.prepare('INSERT INTO submissions (ip_hash, created_at) VALUES (?, ?)').bind(ipHash, now).run();

  const { game, board, initials, score, level } = entry;
  const id = await db
    .prepare('INSERT INTO scores (game, board, initials, score, level, created_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING id')
    .bind(game, board, initials, score, level, now)
    .first('id');
  // Ties go to whoever got there first, so a new score ranks below equal ones.
  const above = await db
    .prepare('SELECT COUNT(*) AS n FROM scores WHERE game = ? AND board = ? AND (score > ? OR (score = ? AND id < ?))')
    .bind(game, board, score, score, id)
    .first('n');
  await db
    .prepare(
      `DELETE FROM scores WHERE game = ? AND board = ? AND id NOT IN (
         SELECT id FROM scores WHERE game = ? AND board = ?
         ORDER BY score DESC, created_at ASC, id ASC LIMIT ?)`,
    )
    .bind(game, board, game, board, KEEP)
    .run();
  return json({ id, rank: above + 1, scores: await topScores(db, game, board) }, 201, cors);
}

export async function handle(request, env, now = Date.now()) {
  const url = new URL(request.url);
  const cors = corsHeaders(request, env);
  if (url.pathname !== '/v1/scores') return json({ error: 'not found' }, 404, cors);
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
  if (request.method === 'GET') return readScores(url, env.DB, cors);
  if (request.method === 'POST') return saveScore(request, env, cors, now);
  return json({ error: 'method not allowed' }, 405, { ...cors, Allow: 'GET, POST, OPTIONS' });
}

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (error) {
      console.error(error);
      return json({ error: 'server error' }, 500, corsHeaders(request, env));
    }
  },
};
