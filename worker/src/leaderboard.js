// Leaderboard API logic: routing, validation and SQL for the D1 database.
// src/index.js wraps it as the Worker; tests import it directly.
//
//   GET  /v1/scores?game=&scope=&difficulty=&mode=   top 10 for one view
//   POST /v1/scores                                  save a finished game
//   POST /v1/groups                                  create a private group
//   GET  /v1/groups/<code>                           look up a group to join
//
// A scope is '*' for the public board or a group's four-character code;
// difficulty and mode can be 'all'. POST bodies are JSON sent as text/plain,
// which keeps the request "simple" so browsers skip the CORS preflight. Only
// origins in ALLOWED_ORIGINS get a response the browser will read, and only
// they may write.

const TOP = 10;            // scores returned per view
const KEEP = 100;          // scores stored per scope, difficulty and mode
const MAX_GROUPS = 5;      // groups one score can be saved to
const MAX_BODY_BYTES = 2048;
const HOUR = 60 * 60 * 1000;
const LIMITS = {
  score: { max: 10, windowMs: 10 * 60 * 1000 },  // saves per IP address
  group: { max: 5, windowMs: HOUR },             // new groups per IP address
};

const PUBLIC = '*';
// No 0/O or 1/I/L, so a code read aloud or off a screen can't be mistyped.
const CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
const CODE = /^[A-HJKMNP-Z2-9]{4}$/;
const GROUP_NAME = /^[\p{L}\p{N}][\p{L}\p{N} '&.,!-]{0,23}$/u;
const INITIALS = /^[A-Z]{3}$/;
const BLOCKED_INITIALS = new Set([
  'ASS', 'CUM', 'DIC', 'DIK', 'FAG', 'FCK', 'FUC', 'FUK', 'KKK', 'NIG', 'SEX', 'SHT', 'TIT', 'WTF', 'XXX',
]);

const isInt = (value, min, max) => Number.isInteger(value) && value >= min && value <= max;

// Each game lists the values of its two filters, difficulty and mode, and a
// plausibility check for a finished game. A determined cheater can still fake
// consistent numbers; the checks stop casual tampering such as editing only
// the score.
export const GAMES = {
  'funnels-and-buckets': {
    difficulties: ['starter', 'classic', 'challenge'],
    modes: ['normal', 'easy'],
    check({ mode, score, level, popped, seconds }) {
      if (!isInt(popped, 1, 100000)) return 'popped must be a positive whole number';
      if (!isInt(seconds, 1, 6 * 60 * 60)) return 'seconds must be between 1 and 21600';
      // The most a pop scores is 20 points (divide), tripled while the sponge is out.
      if (score > popped * 60) return 'score is too high for the bubbles popped';
      if (popped > seconds * 3 + 5) return 'too many bubbles popped for the time played';
      const perLevel = mode === 'easy' ? 30 : 10;
      if (level !== 1 + Math.floor(popped / perLevel)) return 'level does not match bubbles popped';
      return null;
    },
  },
  'doodle-chomp': {
    difficulties: ['starter', 'explorer', 'expert'],
    modes: ['multiples', 'factors', 'primes', 'equals', 'compare', 'mix', 'kinder'],
    check({ difficulty, mode, score, level, chomps, seconds }) {
      if (!isInt(chomps, 1, 100000)) return 'chomps must be a positive whole number';
      if (!isInt(seconds, 1, 6 * 60 * 60)) return 'seconds must be between 1 and 21600';
      if (mode === 'kinder' && difficulty !== 'starter') return 'kindergarten games are filed as starter';
      // A page starts with at least 10 numbers to chomp (7 on kindergarten's
      // smaller page), and a level ends once they're all chomped. Ink blots can
      // drip more onto a page, so there's no upper limit.
      const cleared = level - 1;
      if (chomps < cleared * (mode === 'kinder' ? 7 : 10)) return 'too few chomps to reach this level';
      // A chomp on level n scores 5 × (2 + difficulty) + 2 × (n - 1). Clearing
      // level n adds 25 × n, plus 50 for a page with no wrong chomps.
      const base = 5 * (2 + this.difficulties.indexOf(difficulty));
      const bonuses = (25 * level * cleared) / 2;
      const least = chomps * base + bonuses;
      const most = chomps * (base + 2 * cleared) + bonuses + 50 * cleared;
      if (score < least || score > most) return 'score does not match chomps and level';
      if (chomps > seconds * 4 + 5) return 'too many chomps for the time played';
      return null;
    },
  },
  // A shift is ranked by aircraft handled, then, for a clean shift, by the
  // time left over: score = handled × 10000 + seconds to spare, and level
  // carries the number handled. The mode is the slowest radar sweep used.
  'air-traffic-controller': {
    difficulties: ['trainee', 'easy', 'average', 'hard', 'expert'],
    modes: ['calm', 'steady', 'rush'],
    shifts: { trainee: [30, 8], easy: [70, 26], average: [50, 26], hard: [35, 26], expert: [25, 26] },  // minutes, aircraft
    check({ difficulty, score, level: handled, sweeps }) {
      const [minutes, aircraft] = this.shifts[difficulty];
      // Each radar sweep is 15 seconds of game time.
      if (!isInt(sweeps, 1, minutes * 4)) return 'sweeps must fit in the shift';
      if (handled > aircraft) return 'more aircraft handled than the shift has';
      const clean = handled === aircraft;
      // Aircraft check in throughout the shift's first (minutes - 15) minutes,
      // so a clean shift can't end in under half that.
      if (clean && sweeps < (minutes - 15) * 2) return 'shift finished too quickly';
      if (score !== handled * 10000 + (clean ? (minutes * 4 - sweeps) * 15 : 0)) {
        return 'score does not match aircraft handled and time';
      }
      return null;
    },
  },
};

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function corsHeaders(request, env) {
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

export function json(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...headers },
  });
}

async function readBody(request) {
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) throw new HttpError(413, 'body too large');
  try {
    return JSON.parse(text);
  } catch {
    throw new HttpError(400, 'body must be JSON');
  }
}

async function hashIp(request, salt) {
  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${salt || ''}:${ip}`));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function rateLimit(db, kind, ipHash, now) {
  const { max, windowMs } = LIMITS[kind];
  await db.prepare('DELETE FROM submissions WHERE created_at < ?').bind(now - HOUR).run();
  const recent = await db
    .prepare('SELECT COUNT(*) AS n FROM submissions WHERE kind = ? AND ip_hash = ? AND created_at >= ?')
    .bind(kind, ipHash, now - windowMs)
    .first('n');
  if (recent >= max) throw new HttpError(429, 'too many requests, try again in a few minutes');
  await db.prepare('INSERT INTO submissions (kind, ip_hash, created_at) VALUES (?, ?, ?)').bind(kind, ipHash, now).run();
}

// Returns an error message for a bad score, or null when it's valid.
export function validate(entry) {
  if (!entry || typeof entry !== 'object') return 'body must be a JSON object';
  const game = GAMES[entry.game];
  if (!game) return 'unknown game';
  if (!game.difficulties.includes(entry.difficulty)) return 'unknown difficulty';
  if (!game.modes.includes(entry.mode)) return 'unknown mode';
  if (typeof entry.initials !== 'string' || !INITIALS.test(entry.initials)) return 'initials must be three letters A-Z';
  if (BLOCKED_INITIALS.has(entry.initials)) return 'pick different initials';
  if (!isInt(entry.score, 1, 10000000)) return 'score must be a positive whole number';
  if (!isInt(entry.level, 1, 10000)) return 'level must be a positive whole number';
  const groups = entry.groups ?? [];
  if (!Array.isArray(groups) || groups.length > MAX_GROUPS || !groups.every((c) => typeof c === 'string' && CODE.test(c))) {
    return `groups must be up to ${MAX_GROUPS} group codes`;
  }
  if (entry.public === false && !groups.length) return 'save to the public board or at least one group';
  return game.check(entry);
}

async function groupExists(db, code) {
  return (await db.prepare('SELECT 1 AS ok FROM groups WHERE code = ?').bind(code).first('ok')) === 1;
}

// The top 10 for one scope, optionally narrowed to one difficulty and mode.
async function readView(db, url) {
  const p = url.searchParams;
  const game = GAMES[p.get('game')];
  const scope = p.get('scope') || PUBLIC;
  const difficulty = p.get('difficulty') || 'all';
  const mode = p.get('mode') || 'all';
  if (!game) throw new HttpError(400, 'unknown game');
  if (difficulty !== 'all' && !game.difficulties.includes(difficulty)) throw new HttpError(400, 'unknown difficulty');
  if (mode !== 'all' && !game.modes.includes(mode)) throw new HttpError(400, 'unknown mode');
  if (scope !== PUBLIC && !(CODE.test(scope) && (await groupExists(db, scope)))) throw new HttpError(404, 'unknown group');

  const where = ['game = ?', 'scope = ?'];
  const params = [p.get('game'), scope];
  if (difficulty !== 'all') { where.push('difficulty = ?'); params.push(difficulty); }
  if (mode !== 'all') { where.push('mode = ?'); params.push(mode); }
  const { results } = await db
    .prepare(
      `SELECT entry, initials, score, level, difficulty, mode, created_at FROM scores
       WHERE ${where.join(' AND ')}
       ORDER BY score DESC, created_at ASC, id ASC LIMIT ?`,
    )
    .bind(...params, TOP)
    .all();
  return {
    game: p.get('game'), scope, difficulty, mode,
    scores: results.map((row, i) => ({
      rank: i + 1, entry: row.entry, initials: row.initials, score: row.score, level: row.level,
      difficulty: row.difficulty, mode: row.mode, at: row.created_at,
    })),
  };
}

async function saveScore(request, env, now) {
  const entry = await readBody(request);
  const problem = validate(entry);
  if (problem) throw new HttpError(400, problem);
  const db = env.DB;
  const groups = [...new Set(entry.groups ?? [])];
  for (const code of groups) {
    if (!(await groupExists(db, code))) throw new HttpError(400, `unknown group ${code}`);
  }
  await rateLimit(db, 'score', await hashIp(request, env.IP_SALT), now);

  const { game, difficulty, mode, initials, score, level } = entry;
  const id = crypto.randomUUID();
  const scopes = [...(entry.public === false ? [] : [PUBLIC]), ...groups];
  const ranks = {};
  for (const scope of scopes) {
    await db
      .prepare(
        `INSERT INTO scores (entry, game, scope, difficulty, mode, initials, score, level, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(id, game, scope, difficulty, mode, initials, score, level, now)
      .run();
    // Rank within the game's own difficulty and mode. Ties go to whoever got
    // there first, so a new score ranks below equal ones.
    const above = await db
      .prepare(
        `SELECT COUNT(*) AS n FROM scores WHERE game = ? AND scope = ? AND difficulty = ? AND mode = ?
         AND (score > ? OR (score = ? AND created_at < ?))`,
      )
      .bind(game, scope, difficulty, mode, score, score, now)
      .first('n');
    ranks[scope] = above + 1;
    await db
      .prepare(
        `DELETE FROM scores WHERE game = ? AND scope = ? AND difficulty = ? AND mode = ? AND id NOT IN (
           SELECT id FROM scores WHERE game = ? AND scope = ? AND difficulty = ? AND mode = ?
           ORDER BY score DESC, created_at ASC, id ASC LIMIT ?)`,
      )
      .bind(game, scope, difficulty, mode, game, scope, difficulty, mode, KEEP)
      .run();
  }
  return { entry: id, ranks };
}

async function createGroup(request, env, now) {
  const body = await readBody(request);
  const name = typeof body?.name === 'string' ? body.name.trim().replace(/\s+/g, ' ') : '';
  if (!GROUP_NAME.test(name)) throw new HttpError(400, 'name must be 1-24 letters, numbers or spaces');
  const db = env.DB;
  await rateLimit(db, 'group', await hashIp(request, env.IP_SALT), now);
  for (let attempt = 0; attempt < 8; attempt++) {
    const bytes = crypto.getRandomValues(new Uint8Array(4));
    const code = [...bytes].map((b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
    const created = await db
      .prepare('INSERT INTO groups (code, name, created_at) VALUES (?, ?, ?) ON CONFLICT (code) DO NOTHING RETURNING code')
      .bind(code, name, now)
      .first('code');
    if (created) return { code, name };
  }
  throw new HttpError(503, 'could not pick a free group code, try again');
}

async function readGroup(db, code) {
  const row = CODE.test(code)
    ? await db.prepare('SELECT code, name FROM groups WHERE code = ?').bind(code).first()
    : null;
  if (!row) throw new HttpError(404, 'unknown group');
  return { code: row.code, name: row.name };
}

export async function handle(request, env, now = Date.now()) {
  const url = new URL(request.url);
  const cors = corsHeaders(request, env);
  const allowedOrigin = Boolean(cors['Access-Control-Allow-Origin']);
  const { method } = request;
  const groupPath = url.pathname.match(/^\/v1\/groups\/([^/]+)$/);
  try {
    if (method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (url.pathname === '/v1/scores' && method === 'GET') return json(await readView(env.DB, url), 200, cors);
    if (groupPath && method === 'GET') return json(await readGroup(env.DB, groupPath[1]), 200, cors);
    if ((url.pathname === '/v1/scores' || url.pathname === '/v1/groups') && method === 'POST') {
      if (!allowedOrigin) throw new HttpError(403, 'origin not allowed');
      const result = url.pathname === '/v1/scores' ? await saveScore(request, env, now) : await createGroup(request, env, now);
      return json(result, 201, cors);
    }
    return json({ error: 'not found' }, 404, cors);
  } catch (error) {
    if (error instanceof HttpError) return json({ error: error.message }, error.status, cors);
    throw error;
  }
}
