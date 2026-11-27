// Letterfield's shared survey: everyone explores the same endless map, each
// word is credited to whoever circles it first, and players see each other
// wander. src/index.js routes to it and exports Sector and Atlas as Durable
// Objects; tests import this module directly.
//
//   GET /v1/survey/<sx>/<sy>   WebSocket for one sector of the map
//   GET /v1/survey/world       the world map: charted territories, players, where to start,
//                              and today's and yesterday's numbers (see Atlas.stats)
//   POST /v1/survey/pass       a Turnstile token for a pass (survey-pass.js), while TURNSTILE_SECRET
//                              is set; joins need one only once TURNSTILE_REQUIRED is "true"
//   GET /v1/survey/log/...     the survey's log: every word charted, by hour (survey-log.js).
//                              Each sector copies its new claims to D1 from an alarm (flushLog),
//                              with its supernovas: territories whose every hidden word is charted.
//
// The map is split into sectors of 4×4 territories (192×192 cells), and each
// sector is its own Durable Object: one single-threaded room that holds the
// sector's claims in its SQLite storage and every player's socket. A game
// joins the few sectors in view. Sharding by place is what lets this grow to
// thousands of players: no object sees more than the players near it.
//
// The middle of the map, 100×100 territories around the origin, is the world
// everyone charts together: it hides 1,119,752 words. One Atlas object keeps
// the totals and the world map. Sectors in that area report their numbers to
// it every few seconds while busy; players only read its cached world map.
//
// Cost: a Durable Object is billed for every second it holds a pending timer,
// because it can't hibernate, but otherwise only for the time it spends
// running. So a sector sends owed positions and reports with the next message
// that arrives once they're due, rather than on timers. While people are
// moving there's always a next message; the only timers are short ones for
// something that might be the last thing to happen there: a player leaving a
// quiet sector, and claims waiting in a batch (at most BATCH_MS, well inside
// the idle time before a sector can hibernate). See SURVEY.md for the design
// and how far it scales.
//
// Messages are JSON. From the game:
//   {t: 'me', initials, token, quiet, guilds}
//                                   initials to credit claims to ('' for none); the game's
//                                   secret token, whose hash names the player (survey-social.js);
//                                   quiet: no emotes;
//                                   guilds: the codes of their guilds, up to GUILDS_MAX, each checked
//                                   with its guild (survey-guild.js); an older game sends one `guild`
//   {t: 'pos', x, y} / {t: 'pos', away: true}
//                                   where the player is looking, if in this sector
//   {t: 'claim', w, x, y, d}        a word the player just circled
//   ('me' may also carry badge: [id, sig], the badge they show, and card, their
//   card of badges and when they began, each signed by the Worker for their
//   player id; see achievements.js)
//   {t: 'here'}                     still here: an idle game sends it now and then, so the
//                                   sector keeps listing it (see REFRESH_MS)
//   {t: 'emote', to, e, s}          emote e for player `to`, seen in sector s (survey-social.js)
// To the game (a frame may also be a JSON array of these, sent together):
//   {t: 'hello', you, sector, claims}   on joining; claims are [w, x, y, d, s, initials, at]
//   {t: 'claimed', c, by}           a new claim, to everyone; `by` is the claimer's id
//   {t: 'taken', c}                 to a claimer who wasn't first
//   {t: 'signed', k, r}             to a claimer with a player id, after either: the find's
//                                   receipt, which proves later they circled it (achievements.js)
//   {t: 'error', key, error}        to a claimer, for a word that isn't there, 'slow down'
//                                   when the socket or its address claims too fast, or
//                                   'daily limit' once its address has charted DAILY_CLAIMS today
//   {t: 'presence', n, p}           players here ([id, initials, x, y, tags?, badge?, card?]), about once a
//                                   second; the id is the player's (from their token) once they've sent one;
//                                   tags are their guilds' (one as a string, several as a list, an empty
//                                   list for none when more follows); badge is the id of the one they show
//                                   ('' for none when a card follows); card is theirs without its signature
//   {t: 'emote', from, ini, e, r}   an emote for this player from player `from`, in territory r
//   {t: 'emoted', to, e, ok|error}  what became of an emote this player sent
//   {t: 'guild', tag, on}           which members of one of this player's guilds are online, and where
//                                   ([id, initials, rx, ry, idle, flags], flags as the list's),
//                                   from the Atlas, as it changes
//   {t: 'world', charted, total, players, you?}   the whole world's totals, as they change: players
//                                   by id, each once; you: 1 when this sector counted this player in them
//   {t: 'nova', n: [rx, ry, at, w, x, y, d, initials], ago}
//                                   a territory in another sector has gone supernova, `ago` ms before:
//                                   the claim of its last hidden word, which that sector broadcast to
//                                   its own players as an ordinary 'claimed'. A neighbouring sector, with
//                                   a territory within NOVA_REACH, passes it on at once; every other
//                                   sector in the shared world hears it from the Atlas with its next
//                                   report, and passes it on to players who were here when it went off
//   {t: 'unverified'}               from the Worker, while TURNSTILE_REQUIRED is "true", for a join
//                                   without a good pass, which then
//                                   closes with code 4001: the game gets a new pass and retries
//   {t: 'full', world}              no room in the sector (or, with world: true, in the whole
//                                   survey), or the player's address holds or opens too many
//                                   sockets; the socket then closes with code 4000
//   {t: 'edge'}                     from the Worker, for a join to a sector past the universe's edge,
//                                   where there's no survey (the game never asks); the socket then
//                                   closes with code 4002 (EDGE_CLOSE)
//
// Limits per address (see "Bots" in SURVEY.md): the Worker hands each sector
// a salted hash of the player's IP address, never the address itself. A
// socket's messages past FRAME_BURST at once are dropped unread. A
// sector takes at most ADDRESS_SOCKETS sockets from one address (and the
// Atlas counts an address for at most ADDRESS_ONLINE toward MAX_ONLINE), and two
// rate-limiting bindings, set in wrangler.toml, count joins and claims per
// address across every sector. For a daily cap, sectors in the shared world
// add each address's charted words to their reports, and the Atlas answers
// with the addresses past DAILY_CLAIMS today, which every sector then refuses.

import { addressOf, allowedInitials, corsHeaders, hashAddress, initialsOrNone, isInt, underLimit } from './leaderboard.js';

export { addressOf };
import { PASS_PATH, checkPass, handlePass } from './survey-pass.js';
import { CH, DIRS, MAP_VERSION, RC, STRAY_MIN, VOCAB, chunk, fdiv, keyOf, letterAt, regionTheme, territoryTotal } from '../../js/letterfield/world.js';
import { DAY_MS, HOUR_MS, LOG_BATCH, LOG_MS, LOG_RETRY_MAX_MS, writeLog } from './survey-log.js';
import { GUILD_TAG, GUILD_TAGS_MAX, checkGuilds, matesFor, noteMates, passMates } from './survey-guild.js';
import { checkBadge, checkCard, signFind, signing } from './achievements.js';
import { ATLAS_LIST_PATH, EMOTE_PATH, LIST_MS, REFRESH_MS, TERR, atlas, fromAtlas, goodWho, lidsOf, listed, send, sendEmote, snapshot, tagsOf, takeEmote, takeMe } from './survey-social.js';

export const SECTOR = RC * TERR;      // cells per sector side
export const MAX_PLAYERS = 750;       // sockets one sector accepts (bench/load.js: one sector saturates between 750 and 1,000)
export const PRESENCE_MS = 1000;      // how often positions go out
export const BATCH_MS = 200;          // claims go out together at most this often
export const PRESENCE_MAX = 64;       // positions per update; `n` still counts everyone
export const CLAIM_BURST = 5;         // claims a socket can make at once,
export const CLAIM_REFILL_MS = 1500;  // then one per this many milliseconds
export const FRAME_BURST = 20;        // messages of any kind a socket can send at once,
export const FRAME_REFILL_MS = 100;   // then one per this many milliseconds; the game sends a few a second at most
export const AREA = 12;               // the shared world: sectors -12 to 12 each way
export const AREA_WORDS = 1119752;    // hidden words in it (test/survey.test.js recounts them)
export const REPORT_MS = 10000;       // a busy sector reports to the atlas at most this often
export const SAVE_MS = 60000;         // the atlas writes changed numbers to storage at most this often
export const VIEW_MS = 5000;          // the world map is rebuilt, and cached, for this long
export const ONLINE_MS = 2 * 60000;   // players count as online this long after their sector reported them
export const SPAWN_MAX = 300;         // new players join the biggest crowd with fewer players than this
export const SPAWNS_MAX = 4;          // crowds with room the world map offers, for the game to spread newcomers over
export const MAX_ONLINE = 25000;      // players the whole survey takes at once: a ceiling on the bill
export const ADDRESS_ONLINE = 40;     // players one address counts for toward MAX_ONLINE, however many sectors it's in
export const QUIET = 32;              // a sector with fewer sockets than this sets a timer for a player leaving
export const SAVE_POS_MS = 5000;      // a moving player's position is saved to their socket this often
export const ADDRESS_SOCKETS = 40;    // sockets one address can hold in one sector (a classroom shares an address)
export const ADDRESS_HEADER = 'X-Survey-Address';  // the hashed address, from the Worker to the sector
export const UNPASSED_HEADER = 'X-Survey-Unpassed';  // '1' on a join without a good Turnstile pass, from the Worker
export const DAILY_CLAIMS = 300;      // words one address can chart in the shared world each UTC day
export const DAILY_LIST_MAX = 2000;   // addresses past the daily cap that the Atlas hands out, latest first
export const REPORT_BY_MAX = MAX_PLAYERS * 4;  // addresses one report counts words for: more wait for the next
export const RELAY_MS = ONLINE_MS;    // the Atlas keeps the shared world's supernovas this long, for sectors to pass on
export const RELAY_MAX = 64;          // and at most this many
export const NOVA_REPORT_MS = 1000;   // a sector with a supernova to report reports this soon after its last report
export const NOVA_REACH = 3;          // territories: a supernova this close to the middle of a player's view plays for them, as the game's nearView
const HASH = /^[0-9a-f]{64}$/;
const MAX_MESSAGE = 256;
const LIMIT = 1e9;                    // the game's map runs to ±1e9 cells
export const SECTOR_PATH = /^\/v1\/survey\/(-?\d{1,7})\/(-?\d{1,7})$/;
// Internal paths, for Workers that bind these classes (share/): a sector's
// claim on one word (key as keyOf makes it), and the Atlas's totals.
export const CLAIM_PATH = /^\/claim\/([^/]{1,64})$/;
// A territory's supernova, straight from its sector, for share cards made
// in the seconds before the log has it: { nova: [as the log gives it] }.
export const NOVA_PATH = /^\/nova\/(-?\d{1,8})\/(-?\d{1,8})$/;
// A supernova in a neighbouring sector, POSTed by the sector that recorded
// it: { nova: [rx, ry, at, w, x, y, d, initials] }, passed on to players here.
export const NEAR_PATH = '/near';
export const TOTALS_PATH = '/totals';
export const WORLD_PATH = '/v1/survey/world';

const broadcast = (ctx, frame) => { for (const ws of ctx.getWebSockets()) { try { ws.send(frame); } catch { /* closing */ } } };
const row = (r) => [r.w, r.x, r.y, r.d, r.s, r.initials, r.at];
// The daily cap: DAILY_CLAIMS, unless SURVEY_DAILY_CLAIMS (a var in
// wrangler.toml) says otherwise, as Worker Previews' does so tests can chart
// more in a day.
export function dailyClaims(env) {
  const n = Number(env?.SURVEY_DAILY_CLAIMS);
  return Number.isInteger(n) && n >= 1 && n <= 1e6 ? n : DAILY_CLAIMS;
}
export const inArea = (sx, sy) => Math.abs(sx) <= AREA && Math.abs(sy) <= AREA;
// The sector holding cell (x, y) lies past the universe's edge: in the void
// (a ring one sector wide) or the wilds beyond, where the game surveys alone
// and nothing is shared (see "The edge, the void and the wilds" in SURVEY.md).
export const pastEdge = (x, y) => !inArea(fdiv(x, SECTOR), fdiv(y, SECTOR));

// Whether a Durable Object's storage was last used with an older map
// (MAP_VERSION), recording this one if so. Storage from before maps had
// versions was on map 2. A new object records the version with nothing to clear.
export function onOlderMap(sql) {
  sql.exec('CREATE TABLE IF NOT EXISTS map (id INTEGER PRIMARY KEY CHECK (id = 0), version INTEGER NOT NULL)');
  const version = sql.exec('SELECT version FROM map WHERE id = 0').toArray()[0]?.version ?? 2;
  if (version === MAP_VERSION) return false;
  sql.exec('INSERT INTO map (id, version) VALUES (0, ?) ON CONFLICT (id) DO UPDATE SET version = excluded.version', MAP_VERSION);
  return true;
}

// The word a claim names, checked against the map: {key, w, x, y, d, s} with
// s = 1 for a stray (a word the letters spell by chance), or {error}.
export function checkClaim(claim, sx, sy) {
  const { w, x, y, d } = claim ?? {};
  if (typeof w !== 'string' || !VOCAB.has(w)) return { error: 'not a Letterfield word' };
  if (![x, y].every((v) => Number.isInteger(v) && Math.abs(v) < LIMIT) || !Number.isInteger(d) || d < 0 || d > 7) {
    return { error: 'bad position' };
  }
  if (fdiv(x, SECTOR) !== sx || fdiv(y, SECTOR) !== sy) return { error: 'word starts in another sector' };
  const [dx, dy] = DIRS[d];
  for (let i = 0; i < w.length; i++) {
    if (letterAt(x + dx * i, y + dy * i) !== w.charCodeAt(i) - 65) return { error: 'word is not there' };
  }
  const key = keyOf(w, x, y, d);
  // Hidden words sit inside one chunk; strays count from STRAY_MIN letters, as in the game.
  const placed = chunk(fdiv(x, CH), fdiv(y, CH)).words.some((p) => p.key === key);
  if (!placed && w.length < STRAY_MIN) return { error: 'word is not there' };
  return { key, w, x, y, d, s: placed ? 0 : 1 };
}

// The other sectors with a territory within NOVA_REACH of territory (rx, ry),
// counting as the game's nearView does (the larger of the two distances in
// territories), so every player whose view is centred close enough to see a
// supernova is in one of them or in its own sector. Sectors are 4 territories
// wide and the reach is 3, so a territory on a sector's corner has three
// neighbours to tell, one on an edge five, and one of the middle four all eight.
// Sectors past the universe's edge have nobody in them to tell, so they're left out.
export function novaNeighbours(rx, ry) {
  const sx = fdiv(rx, TERR), sy = fdiv(ry, TERR), out = [];
  for (let ny = fdiv(ry - NOVA_REACH, TERR); ny <= fdiv(ry + NOVA_REACH, TERR); ny++) {
    for (let nx = fdiv(rx - NOVA_REACH, TERR); nx <= fdiv(rx + NOVA_REACH, TERR); nx++) if ((nx !== sx || ny !== sy) && inArea(nx, ny)) out.push([nx, ny]);
  }
  return out;
}

// Whether a supernova, as sectors pass it around ([rx, ry, at, w, x, y, d,
// initials]), names a hidden word that's really there, in the territory named.
export function checkNovaWord(n) {
  if (!Array.isArray(n) || n.length !== 8) return false;
  const [rx, ry, at, w, x, y, d, initials] = n;
  if (![rx, ry].every((v) => isInt(v, -LIMIT, LIMIT)) || !isInt(at, 0, 1e14) || !initialsOrNone(initials)) return false;
  const c = checkClaim({ w, x, y, d }, fdiv(x, SECTOR), fdiv(y, SECTOR));
  return !c.error && !c.s && fdiv(x, RC) === rx && fdiv(y, RC) === ry;
}

// Whether a neighbour's supernova, as NEAR_PATH carries it, is one sector
// (sx, sy) should pass on: a hidden word, really there, in a territory whose
// sector would tell this one (novaNeighbours). Only sectors can reach the
// path, but this keeps a bad frame from going out to every player here.
export function checkNova(n, sx, sy) {
  return checkNovaWord(n) && novaNeighbours(n[0], n[1]).some(([nx, ny]) => nx === sx && ny === sy);
}

// Answers the survey's paths, or returns null for any other path: a sector's
// WebSocket goes to its Durable Object, and the world map comes from the
// Atlas through a short cache. CORS doesn't cover WebSockets, so the origin
// is checked here. With TURNSTILE_SECRET set, POST /v1/survey/pass hands out
// passes (see survey-pass.js and TURNSTILE.md). A join without a good pass is
// turned away only when TURNSTILE_REQUIRED is "true"; until then it goes
// ahead, marked so its sector counts it.
export function routeSurvey(request, env) {
  const url = new URL(request.url);
  const m = url.pathname.match(SECTOR_PATH);
  const world = url.pathname === WORLD_PATH;
  const passing = url.pathname === PASS_PATH;
  if (!(m && env.SECTORS) && !(world && env.ATLAS) && !(passing && env.SECTORS)) return null;
  const cors = corsHeaders(request, env);
  const text = (body, status) => new Response(body, { status, headers: { ...cors, 'Content-Type': 'text/plain' } });
  if (passing) {
    if (request.method !== 'POST') return text('method not allowed', 405);
    return addressHash(request, env).then((address) => handlePass(request, env, address, cors));
  }
  if (request.method !== 'GET') return text('method not allowed', 405);
  if (world) return worldMap(env, cors);
  if (!cors['Access-Control-Allow-Origin']) return text('origin not allowed', 403);
  if (request.headers.get('Upgrade') !== 'websocket') return text('expected a WebSocket', 426);
  // Past the universe's edge there's no survey: the game surveys alone out
  // there and never asks, and an older game that does is told so without
  // waking (or making) a sector, or counting the join.
  if (!inArea(Number(m[1]), Number(m[2]))) return pastTheEdge();
  const name = `${Number(m[1])},${Number(m[2])}`;
  return (async () => {
    const address = await addressHash(request, env);
    const unpassed = !!env.TURNSTILE_SECRET && !(await checkPass(env.TURNSTILE_SECRET, address, url.searchParams.get('pass')));
    if (unpassed && turnstileRequired(env)) return unverified();
    // Joins per address are counted here, before the sector is woken (or
    // made): a join the limiter refuses costs no Durable Object at all.
    if (!(await underLimit(env.SURVEY_JOINS, address))) return refused('full', { world: false }, 4000, 'too many joins');
    // The pass stays here: the sector only needs the path, the address and
    // whether the join had a pass. The Worker sets both headers itself, so a
    // player can't choose either.
    url.search = '';
    const headers = new Headers(request.headers);
    headers.set(ADDRESS_HEADER, address);
    headers.delete(UNPASSED_HEADER);
    if (unpassed) headers.set(UNPASSED_HEADER, '1');
    return env.SECTORS.get(env.SECTORS.idFromName(name)).fetch(new Request(url, { headers }));
  })();
}

// Whether joins without a pass are turned away: a var in wrangler.toml, so
// passes can be handed out (and joins without one counted) before anyone is
// refused.
export const turnstileRequired = (env) => env.TURNSTILE_REQUIRED === true || env.TURNSTILE_REQUIRED === 'true';

// A join without a good pass, while passes are required, or past its
// address's limit on joins, is answered by the Worker itself, without waking
// the sector, and in words the game can read: a browser learns nothing from a
// refused WebSocket upgrade.
const unverified = () => refused('unverified', {}, 4001, 'survey pass needed');
export const EDGE_CLOSE = 4002;
const pastTheEdge = () => refused('edge', {}, EDGE_CLOSE, 'past the edge of the universe');

function refused(t, frame, code, reason) {
  const [client, server] = Object.values(new WebSocketPair());
  server.accept();
  send(server, { t, ...frame });
  server.close(code, reason);
  return new Response(null, { status: 101, webSocket: client });
}

// The player's address as the survey counts it, salted and hashed. The
// Worker sets the header the sector reads itself, so a player can't choose
// their own.
const addressHash = (request, env) => hashAddress(addressOf(request.headers.get('CF-Connecting-IP') || 'unknown'), env.IP_SALT);

// Each Worker instance asks the Atlas for the world map at most once per
// VIEW_MS and shares the answer, so players checking the map can't swamp it.
const worldCache = new WeakMap();
async function worldMap(env, cors) {
  return new Response(await fromAtlas(worldCache, env, '/world', VIEW_MS, (r) => r.text()), {
    headers: { ...cors, 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': `public, max-age=${VIEW_MS / 1000}` },
  });
}

// One sector of the map. It uses the WebSocket Hibernation API: between
// messages the object can be evicted from memory while sockets stay open, so
// everything a socket needs is kept in its attachment. Reading and writing
// attachments is the most expensive thing a busy sector does, though, so the
// players are also kept in memory (`people`): positions, which change every
// second or two, are written to the attachment at most every SAVE_POS_MS.
export class Sector {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.sql = ctx.storage.sql;
    this.now = () => Date.now();
    this.batch = [];         // claims waiting to go out together
    this.batchAt = 0;
    this.batchTimer = null;
    this.presenceTimer = null;
    this.presenceAt = 0;     // when positions last went out
    this.presenceDue = false;
    this.reportedAt = 0;     // when the Atlas last heard from this sector
    this.reportDue = false;
    this.reporting = false;
    this.leaveDue = false;   // a forced report (someone left) came while one was out
    this.hot = null;         // [x, y] of the latest claim, for where new players land when nobody's placed
    this.where = null;       // [sx, sy], from the first socket to join or wake it
    this.claimsJson = null;  // every claim as JSON, built on the first join after waking, then kept up to date
    this.counts = null;      // hidden words charted in each of the sector's 16 territories, likewise
    this.hidden = null;      // hidden words each of those territories has, from the map, worked out when first needed
    this.world = null;       // the last totals the Atlas sent back
    this.counted = new Set();  // the ids this sector listed in the report those totals answered: they're in its count
    this.worldSent = new WeakMap();  // socket → the last totals frame it was sent, so a frame only goes again when it changes
    this.people = null;      // socket → its attachment, read from the sockets on first use after waking
    this.guildChecks = new WeakMap();  // socket → codes of its guilds whose check is out (checkGuilds): kept in memory, never in an attachment
    this.frames = new WeakMap();  // socket → {tokens, at}: its allowance of messages, in memory only
    this.shownChecked = new WeakMap();  // socket → the badge and card it last sent, and what checking them found
    // What the next report owes the Atlas, kept in storage too (`owed`, read
    // below) so a sector that hibernates before reporting still sends it.
    this.chartedBy = new Map();  // address → words it charted here since the last report
    this.unpassed = 0;           // joins without a Turnstile pass since the last report (a bot signal)
    this.overDay = -1;       // the UTC day `over` is for
    this.over = new Set();   // addresses past the daily cap today, as the Atlas last said
    this.overAt = 0;         // the Atlas's count of changes to that list then; it only resends the list when this changes
    // Whether the sector knows who is past today's cap: unknown since waking
    // (or since the day turned), asking the Atlas (`asking` is out), or known
    // (`heardDay` is today). Until it's known, a claim from an address waits
    // for an ask, so waking doesn't let a capped address chart again.
    this.heardDay = -1;      // the UTC day the Atlas last answered for, since waking
    this.asking = null;      // the ask that's out, which every claim waiting on it shares
    this.askedAt = 0;        // when the last ask went out; a failed one isn't tried again for REPORT_MS
    // When the log alarm goes off: the time this object set it for, 0 once it
    // has gone off and none is pending, or null until this object has set one
    // since waking (one set before then may still be pending).
    this.logAt = null;
    this.logFails = 0;       // log writes that have failed in a row
    this.logChecked = false; // whether this object has looked for claims the log is missing since waking
    this.lastAt = null;      // the latest claim's time, read on the first claim after waking
    this.novasOwed = [];     // supernovas here the Atlas hasn't heard of yet, to go with the next report
    this.novasSent = new Set();  // 'rx,ry' of other sectors' supernovas already passed on to players here, since waking
    this.novaSeq = null;     // the Atlas's latest supernova this sector has passed on (stored in `relayed`), read on first use
    this.sql.exec(`CREATE TABLE IF NOT EXISTS claims (
      key TEXT PRIMARY KEY, w TEXT NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL, d INTEGER NOT NULL,
      s INTEGER NOT NULL, initials TEXT NOT NULL, at INTEGER NOT NULL) WITHOUT ROWID`);
    // The survey's log (survey-log.js): claims are copied to D1 in the order
    // they were made, and `logged` holds the last one D1 has.
    this.sql.exec('CREATE INDEX IF NOT EXISTS claims_by_time ON claims (at, key)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS logged (id INTEGER PRIMARY KEY CHECK (id = 0), at INTEGER NOT NULL)');
    // Each claim's guilds, as the log knows them: the log ids of the guilds its
    // charter was in, space-separated, or '' for none (and, from when surveyors
    // could keep off the list, for one who did). The guilds' names go to the
    // log with their claims (noteGuild, flushLog).
    try { this.sql.exec('SELECT guild FROM claims LIMIT 0'); } catch { this.sql.exec("ALTER TABLE claims ADD COLUMN guild TEXT NOT NULL DEFAULT ''"); }
    this.sql.exec('CREATE TABLE IF NOT EXISTS guild_names (lid TEXT PRIMARY KEY, a INTEGER NOT NULL, b INTEGER NOT NULL, c INTEGER NOT NULL) WITHOUT ROWID');
    // Supernovas: the sector's territories whose every hidden word is
    // charted, each recorded by the claim that completed it (supernova()),
    // and copied to the log once it has their last word (logged = 1).
    this.sql.exec(`CREATE TABLE IF NOT EXISTS novas (
      rx INTEGER NOT NULL, ry INTEGER NOT NULL, at INTEGER NOT NULL, w TEXT NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL,
      d INTEGER NOT NULL, initials TEXT NOT NULL, first INTEGER NOT NULL, words INTEGER NOT NULL, surveyors INTEGER NOT NULL,
      top TEXT NOT NULL, top_n INTEGER NOT NULL, logged INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (rx, ry)) WITHOUT ROWID`);
    // The shared world's supernovas this sector has passed on, by the
    // Atlas's count, so one woken from hibernation picks up where it left off.
    this.sql.exec('CREATE TABLE IF NOT EXISTS relayed (id INTEGER PRIMARY KEY CHECK (id = 0), seq INTEGER NOT NULL)');
    // What the next report owes the Atlas (owe()): 'a' and an address for the
    // words it charted here, 'u' for joins without a pass, 'n' and a
    // supernova as JSON. Written as each comes in and taken off once the
    // Atlas has it, so the daily cap counts every word, even ones charted
    // just before the sector hibernated.
    this.sql.exec('CREATE TABLE IF NOT EXISTS owed (k TEXT PRIMARY KEY, n INTEGER NOT NULL) WITHOUT ROWID');
    // Claims from an older map name words that aren't there any more.
    if (onOlderMap(this.sql)) {
      this.sql.exec('DELETE FROM claims');
      this.sql.exec('DELETE FROM logged');
      this.sql.exec('DELETE FROM novas');
    }
    for (const { k, n } of this.sql.exec('SELECT k, n FROM owed').toArray()) {
      if (k[0] === 'a') this.chartedBy.set(k.slice(1), n);
      else if (k === 'u') this.unpassed = n;
      else if (k[0] === 'n') this.novasOwed.push(JSON.parse(k.slice(1)));
      this.reportDue = true;
    }
  }

  // Something for the next report: in memory, and in storage until the Atlas has it.
  owe(k, n = 1) {
    this.sql.exec('INSERT INTO owed (k, n) VALUES (?, ?) ON CONFLICT (k) DO UPDATE SET n = n + excluded.n', k, n);
  }

  // The Atlas has had a report: what it carried comes off what's owed.
  paid(by, unpassed, novas) {
    // One row written either way: the row goes once it's all paid, and is
    // only lowered when more came in while the report was out.
    const take = (k, n) => {
      this.sql.exec('DELETE FROM owed WHERE k = ? AND n <= ?', k, n);
      this.sql.exec('UPDATE owed SET n = n - ? WHERE k = ? AND n > ?', n, k, n);
    };
    for (const [address, n] of by) take(`a${address}`, n);
    if (unpassed) take('u', unpassed);
    for (const nova of novas) take(`n${JSON.stringify(nova)}`, 1);
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);
    // Who charted a word, for the share Worker's cards (share/): it binds this
    // class directly, and the public router only ever forwards WebSocket
    // upgrades here, so this path isn't reachable from outside.
    const claim = request.method === 'GET' && pathname.match(CLAIM_PATH);
    if (claim) return this.claimOf(decodeURIComponent(claim[1]));
    const nova = request.method === 'GET' && pathname.match(NOVA_PATH);
    if (nova) return this.outside(Number(nova[1]) * RC, Number(nova[2]) * RC) ? Response.json({ error: 'no supernova' }, { status: 404 }) : this.novaOf(Number(nova[1]), Number(nova[2]));
    // An emote for a player here, from another sector (survey-social.js).
    if (request.method === 'POST' && pathname === EMOTE_PATH) return takeEmote(this, request);
    if (request.method === 'POST' && pathname === NEAR_PATH) return this.near(request);
    const m = pathname.match(SECTOR_PATH);
    if (!m) return new Response('not found', { status: 404 });
    if (request.headers.get('Upgrade') !== 'websocket') return new Response('expected a WebSocket', { status: 426 });
    const [client, server] = Object.values(new WebSocketPair());
    if (this.outside(Number(m[1]) * SECTOR, Number(m[2]) * SECTOR)) {
      server.accept();
      send(server, { t: 'edge' });
      server.close(EDGE_CLOSE, 'past the edge of the universe');
      return new Response(null, { status: 101, webSocket: client });
    }
    const address = request.headers.get(ADDRESS_HEADER) || null;
    // Only a sector that reports owes the Atlas its joins without a pass:
    // one outside the shared world would keep the row forever.
    if (request.headers.get(UNPASSED_HEADER) === '1' && this.env.ATLAS && inArea(Number(m[1]), Number(m[2]))) {
      this.unpassed++; this.owe('u'); this.reportDue = true;
    }
    const full = () => this.ctx.getWebSockets().length >= MAX_PLAYERS || (address && this.fromAddress(address) >= ADDRESS_SOCKETS);
    // (The Worker has counted the join against the address's limit already.)
    if (this.world && this.world.players >= MAX_ONLINE) this.turnAway(server, true);
    else if (full()) this.turnAway(server, false);
    else this.join(server, Number(m[1]), Number(m[2]), address);
    return new Response(null, { status: 101, webSocket: client });
  }

  claimOf(key) {
    const [, x, y] = key.split('~').map(Number);
    if (this.outside(x, y)) return Response.json({ error: 'not charted' }, { status: 404 });
    const row = this.sql.exec('SELECT initials, at FROM claims WHERE key = ?', key).toArray()[0];
    return row ? Response.json({ initials: row.initials, at: row.at }) : Response.json({ error: 'not charted' }, { status: 404 });
  }

  novaOf(rx, ry) {
    const n = this.sql.exec('SELECT * FROM novas WHERE rx = ? AND ry = ?', rx, ry).toArray()[0];
    return n
      ? Response.json({ nova: [n.rx, n.ry, n.at, n.w, n.x, n.y, n.d, n.initials, n.first, n.words, n.surveyors, n.top, n.top_n, regionTheme(n.rx, n.ry)] })
      : Response.json({ error: 'no supernova' }, { status: 404 });
  }

  // Whether cell (x, y), which a request has just named in this sector, lies
  // past the universe's edge. If it does, this sector is out there, where
  // nothing is shared: the router sends nothing here any more, but one woken
  // anyway (an alarm, an older Worker's request) forgets what it held from
  // before the edge, claims, supernovas and all.
  outside(x, y) {
    if (!Number.isInteger(x) || !Number.isInteger(y) || !pastEdge(x, y)) return false;
    this.purge();
    return true;
  }

  purge() {
    for (const table of ['claims', 'logged', 'novas', 'guild_names', 'owed', 'relayed']) this.sql.exec(`DELETE FROM ${table}`);
    this.claimsJson = null; this.counts = null; this.lastAt = null;
    this.novasOwed = []; this.chartedBy = new Map(); this.unpassed = 0; this.reportDue = false;
  }

  // A neighbour's supernova, for the players here. A sector with nobody in
  // it has nobody to tell, and doesn't know where it is either.
  async near(request) {
    let n = null;
    try { n = (await request.json())?.nova; } catch { /* answered below */ }
    if (!this.ctx.getWebSockets().length) return new Response(null, { status: 204 });
    if (!checkNova(n, ...this.coords())) return new Response('bad supernova', { status: 400 });
    if (!this.novasSent.has(`${n[0]},${n[1]}`)) this.tellPlayers(n);
    return new Response(null, { status: 204 });
  }

  // Another sector's supernova, to the players here (those `who` picks, or all).
  tellPlayers(n, who = null) {
    if (this.novasSent.size >= 1000) this.novasSent.clear();
    this.novasSent.add(`${n[0]},${n[1]}`);
    const frame = JSON.stringify({ t: 'nova', n, ago: Math.max(0, this.now() - n[2]) });
    for (const ws of this.ctx.getWebSockets()) {
      const p = this.person(ws);
      if (!who || (p && who(p))) { try { ws.send(frame); } catch { /* closing */ } }
    }
  }

  heardNovaSeq() {
    this.novaSeq ??= this.sql.exec('SELECT seq FROM relayed WHERE id = 0').toArray()[0]?.seq ?? -1;
    return this.novaSeq;
  }

  // The shared world's supernovas, from the Atlas's answer to a report or an
  // ask: each passed on to the players who were here when it went off, unless
  // they've had it already (it's this sector's own, or a neighbour's).
  relay(world) {
    if (!isInt(world?.novaSeq, 0, 1e14)) return;
    const [sx, sy] = this.coords();
    for (const n of Array.isArray(world.novas) ? world.novas : []) {
      if (!Array.isArray(n) || n.length !== 8 || !isInt(n[0], -LIMIT, LIMIT) || !isInt(n[1], -LIMIT, LIMIT) || !isInt(n[2], 0, 1e14)) continue;
      if (this.novasSent.has(`${n[0]},${n[1]}`) || (fdiv(n[0], TERR) === sx && fdiv(n[1], TERR) === sy)) continue;
      this.tellPlayers(n, (p) => !(p.joined > n[2]));
    }
    if (world.novaSeq !== this.heardNovaSeq()) {
      this.novaSeq = world.novaSeq;
      this.sql.exec('INSERT INTO relayed (id, seq) VALUES (0, ?) ON CONFLICT (id) DO UPDATE SET seq = excluded.seq', world.novaSeq);
    }
  }

  // Tells the neighbouring sectors in reach about a supernova here, without
  // holding up the claim's answer: each passes it on to its own players.
  passOn(nova) {
    if (!this.env.SECTORS) return;
    const body = JSON.stringify({ nova });
    const sent = Promise.all(novaNeighbours(nova[0], nova[1]).map(async ([nx, ny]) => {
      try {
        await this.env.SECTORS.get(this.env.SECTORS.idFromName(`${nx},${ny}`)).fetch(`https://sector${NEAR_PATH}`, { method: 'POST', body });
      } catch { /* they'll see the remnant on the world map */ }
    }));
    this.ctx.waitUntil?.(sent);
  }

  fromAddress(address) {
    let n = 0;
    for (const p of this.everyone().values()) if (p.address === address) n++;
    return n;
  }

  // A full sector (or survey) still answers, so the game can say why it isn't joining.
  turnAway(ws, world) {
    ws.accept();
    send(ws, { t: 'full', world });
    ws.close(4000, world ? 'survey is full' : 'sector is full');
  }

  join(ws, sx, sy, address = null) {
    this.ctx.acceptWebSocket(ws);
    this.where ??= [sx, sy];
    const id = crypto.randomUUID().slice(0, 8);
    const me = { id, sx, sy, address, initials: '', x: null, y: null, moved: 0, saved: 0, tokens: CLAIM_BURST, refilled: this.now(), joined: this.now() };
    ws.serializeAttachment(me);
    this.everyone().set(ws, me);
    // When everyone reconnects at once (after a deploy, say), each join just
    // reuses the claims already turned into JSON.
    this.claimsJson ??= JSON.stringify(this.sql.exec('SELECT w, x, y, d, s, initials, at FROM claims ORDER BY at, key').toArray().map(row));
    const hello = JSON.stringify({ t: 'hello', you: id, sector: [sx, sy], claims: [] });
    try { ws.send(hello.replace('"claims":[]', `"claims":${this.claimsJson}`)); } catch { /* closing */ }
    // The totals, unless they're older than anyone counts as online for: a sector
    // left awake but quiet would otherwise hand a newcomer an old count.
    if (this.world && this.now() - this.reportedAt < ONLINE_MS) this.tellWorld([ws]);
    if (!this.logChecked) {
      // The first join after waking: supernovas from before they were
      // recorded are found, and anything the log hasn't got goes soon.
      this.logChecked = true;
      this.findNovas();
      if (this.env.LOG_DB && (this.unlogged(2).some((r) => r.at > this.logMark()) || this.novasUnlogged())) this.logSoon(1000);
    }
  }

  everyone() {
    if (!this.people) {
      this.people = new Map();
      for (const ws of this.ctx.getWebSockets()) { const me = ws.deserializeAttachment(); if (me) this.people.set(ws, me); }
    }
    return this.people;
  }

  person(ws) {
    let me = this.everyone().get(ws);
    if (!me && (me = ws.deserializeAttachment())) this.people.set(ws, me);
    return me;
  }

  coords() {
    if (!this.where) {
      const first = this.ctx.getWebSockets()[0]?.deserializeAttachment();
      if (first) this.where = [first.sx, first.sy];
    }
    return this.where;
  }

  async webSocketMessage(ws, message) {
    if (typeof message !== 'string' || message.length > MAX_MESSAGE) return;
    // Every message costs the sector's one thread some work, whatever it
    // says, so past a few a second a socket's messages are dropped unread.
    // (Claims and emotes have tighter limits of their own, which answer.)
    const now = this.now(), allowance = this.frames.get(ws) ?? { tokens: FRAME_BURST, at: now };
    allowance.tokens = Math.min(FRAME_BURST, allowance.tokens + (now - allowance.at) / FRAME_REFILL_MS);
    allowance.at = now;
    this.frames.set(ws, allowance);
    if (allowance.tokens < 1) return;
    allowance.tokens -= 1;
    let msg;
    try { msg = JSON.parse(message); } catch { return; }
    const me = this.person(ws);
    if (!me || !msg) return;
    if (msg.t === 'me') {
      const initials = allowedInitials(msg.initials) ? msg.initials : '';
      // Who the player is, whether they take emotes, and their guilds: for the surveyor list and guild checks.
      const social = await takeMe(me, msg);
      if (social) this.reportDue = true;
      // The badge they show, if the Worker signed it for them, and their card,
      // the same way: others see it without its signature. Each is checked
      // again only when the game sends something new.
      const sent = JSON.stringify([me.pid ?? null, msg.badge ?? null, msg.card ?? null]), last = this.shownChecked.get(ws);
      let badge = last?.sent === sent ? last.badge : null, card = last?.sent === sent ? last.card : null;
      if (last?.sent !== sent) {
        badge = me.pid ? await checkBadge(this.env, me.pid, msg.badge) : null;
        card = me.pid ? (await checkCard(this.env, me.pid, msg.card))?.shown ?? null : null;
        this.shownChecked.set(ws, { sent, badge, card });
      }
      const shown = badge !== (me.badge ?? null) || card !== (me.card ?? null);
      if (shown) { me.badge = badge; me.card = card; }
      if (initials !== me.initials || social || shown) { me.initials = initials; this.save(ws, me); this.schedulePresence(false); }
    } else if (msg.t === 'pos') {
      const ok = [msg.x, msg.y].every((v) => Number.isFinite(v) && Math.abs(v) < LIMIT);
      const away = msg.away || !ok, had = me.x !== null && me.x !== undefined;
      if (away) { me.x = null; me.y = null; }
      else { me.x = Math.round(msg.x * 10) / 10; me.y = Math.round(msg.y * 10) / 10; }
      me.moved = this.now();
      // Saved at most every SAVE_POS_MS while moving, but at once when it first
      // becomes known: a sector that sleeps before the next save would wake not
      // knowing where someone sitting still is, and leave them off the list and
      // the map until they moved.
      if (away || !had || me.moved - me.saved >= SAVE_POS_MS) this.save(ws, me);
      this.schedulePresence(away);
    } else if (msg.t === 'claim') {
      await this.claim(ws, me, msg);
    } else if (msg.t === 'emote') {
      await sendEmote(this, ws, me, msg);
    }
    // Each guild the game names is checked when it's new, and now and then while they play.
    for (const checked of checkGuilds(this, ws, me)) this.ctx.waitUntil?.(checked);
    this.catchUp();
  }

  async claim(ws, me, msg) {
    const now = this.now();
    const key = typeof msg.w === 'string' ? keyOf(msg.w, msg.x, msg.y, msg.d) : null;
    me.tokens = Math.min(CLAIM_BURST, me.tokens + (now - me.refilled) / CLAIM_REFILL_MS);
    me.refilled = now;
    if (me.tokens < 1) { this.save(ws, me); return send(ws, { t: 'error', key, error: 'slow down' }); }
    me.tokens -= 1;
    this.save(ws, me);
    // Every claim from the address counts, wherever it's made, so more
    // sockets in more sectors don't let a script claim any faster.
    if (!(await underLimit(this.env.SURVEY_CLAIMS, me.address))) return send(ws, { t: 'error', key, error: 'slow down' });
    if (me.address && this.env.ATLAS && inArea(...this.coords()) && this.heardDay !== Math.floor(now / DAY_MS)
      && (this.asking || now - this.askedAt >= REPORT_MS)) await this.ask();
    if (me.address && this.overToday().has(me.address)) return send(ws, { t: 'error', key, error: 'daily limit' });
    const c = checkClaim(msg, me.sx, me.sy);
    if (c.error) return send(ws, { t: 'error', key, error: c.error });
    // The insert runs as one statement with nothing awaited, so even if
    // another claim ran while the limiter answered, the first to get here wins.
    // Its time is always after the sector's last claim, even if this object
    // moved to a machine whose clock is behind, so the log (which copies
    // claims in order of time) can't skip it.
    const at = this.claimTime(now);
    const inserted = this.sql.exec(
      `INSERT INTO claims (key, w, x, y, d, s, initials, at, guild) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (key) DO NOTHING RETURNING key`,
      c.key, c.w, c.x, c.y, c.d, c.s, me.initials, at, lidsOf(me).join(' '),
    ).toArray().length;
    if (!inserted) {
      const first = this.sql.exec('SELECT w, x, y, d, s, initials, at FROM claims WHERE key = ?', c.key).one();
      send(ws, { t: 'taken', c: row(first) });
      return this.receipt(ws, me, c, now, '');
    }
    this.lastAt = at;
    const claimed = JSON.stringify([c.w, c.x, c.y, c.d, c.s, me.initials, at]);
    if (this.claimsJson) this.claimsJson = `${this.claimsJson.slice(0, -1)}${this.claimsJson === '[]' ? '' : ','}${claimed}]`;
    let wentOff = false;
    if (!c.s) {
      // Counted from storage, the new claim included, if not yet since waking.
      const t = this.territory(c.x, c.y);
      if (this.counts) this.counts[t]++;
      else this.chartedCounts();
      if (this.counts[t] === this.hiddenCounts()[t]) {
        const nova = this.supernova(t);
        wentOff = !!nova;
        if (nova) {
          this.passOn(nova);
          // And to the Atlas, for every other sector in the shared world.
          if (this.env.ATLAS && inArea(...this.coords())) { this.novasOwed.push(nova); this.owe(`n${JSON.stringify(nova)}`); }
        }
      }
    }
    this.hot = [c.x, c.y];
    if (me.address && inArea(...this.coords())) { this.chartedBy.set(me.address, (this.chartedBy.get(me.address) ?? 0) + 1); this.owe(`a${me.address}`); }
    this.batch.push(`{"t":"claimed","c":${claimed},"by":${JSON.stringify(me.id)}}`);
    this.sendBatch();
    this.maybeReport();
    this.logSoon();
    await this.receipt(ws, me, c, at, wentOff ? 'fz' : 'f');
  }

  // A find's receipt, for its player alone, once the sector has answered: it
  // proves later that they circled it, and when, for a badge others see
  // (achievements.js). Nothing is kept here.
  async receipt(ws, me, c, at, flags) {
    if (!me.pid || !signing(this.env)) return;
    send(ws, { t: 'signed', k: c.key, r: await signFind(this.env, me.pid, c, at, flags) });
  }

  claimTime(now) {
    this.lastAt ??= this.sql.exec('SELECT MAX(at) AS at FROM claims').one().at ?? 0;
    return Math.max(now, this.lastAt + 1);
  }

  // Claims D1 hasn't got yet, oldest first: those after the last one it has.
  // Older sectors may hold claims made in the same millisecond, so the one
  // at the mark goes again too, and D1 ignores the copy.
  logMark() {
    return this.sql.exec('SELECT at FROM logged WHERE id = 0').toArray()[0]?.at ?? -1;
  }

  unlogged(limit) {
    return this.sql.exec('SELECT key, w, x, y, d, s, initials, at, guild FROM claims WHERE at >= ? ORDER BY at, key LIMIT ?', this.logMark(), limit).toArray();
  }

  // A guild's name, from its own answer to a member's check (checkGuilds), kept
  // for the log: names never change, so each is written here once.
  noteGuild(lid, [a, b, c]) {
    this.sql.exec('INSERT INTO guild_names (lid, a, b, c) VALUES (?, ?, ?, ?) ON CONFLICT (lid) DO NOTHING', lid, a, b, c);
  }

  // Copies new claims to the log within LOG_MS, from an alarm. An alarm,
  // unlike a timer, doesn't stop the sector hibernating, and it wakes the
  // sector if it was evicted. Claims that come in before it goes off ride
  // along with it. A sector just woken doesn't know the alarm it set before,
  // so it sets one no later than LOG_MS after the oldest claim the log hasn't
  // got: otherwise each claim after a wake would put the log off again.
  logSoon(delay = LOG_MS) {
    if (!this.env.LOG_DB) return;
    let at = this.now() + delay;
    if (this.logAt === null) {
      const oldest = this.sql.exec('SELECT MIN(at) AS at FROM claims WHERE at > ?', this.logMark()).one().at;
      if (oldest !== null) at = Math.min(at, Math.max(this.now() + 1000, oldest + LOG_MS));
    }
    // While D1 is failing, a claim doesn't bring the backed-off retry forward.
    if (this.logAt && (this.logAt <= at || this.logFails)) return;
    this.logAt = at;
    this.ctx.storage.setAlarm(at);
  }

  async alarm() {
    this.logAt = 0;
    let more;
    try {
      more = await this.flushLog();
    } catch (error) {
      // D1 didn't take them: they're still here, and go with a later try.
      this.logFails++;
      console.log({ survey: 'log failed', fails: this.logFails, error: String(error?.message ?? error) });
      this.logSoon(Math.min(LOG_RETRY_MAX_MS, LOG_MS * 2 ** this.logFails));
      return;
    }
    this.logFails = 0;
    if (more) this.logSoon(1000);
  }

  // Sends up to LOG_BATCH claims to D1, and moves the mark past them once D1
  // has them, with the supernovas whose last word D1 then has too, so a
  // supernova never reaches the log ahead of the word that set it off.
  // Returns whether more are waiting.
  async flushLog() {
    if (!this.env.LOG_DB) return false;
    const mark = this.logMark();
    let rows = this.unlogged(LOG_BATCH);
    // A sector past the edge keeps nothing, and sends nothing to the log.
    if (rows.length && this.outside(rows[0].x, rows[0].y)) return false;
    // Only the claim at the mark itself, which D1 already has.
    if (rows.length && rows.at(-1).at === mark) rows = [];
    const upTo = rows.length ? rows.at(-1).at : mark;
    const novas = this.sql.exec('SELECT * FROM novas WHERE logged = 0 AND at <= ?', upTo).toArray();
    if (!rows.length && !novas.length) return false;
    // The names of the guilds these claims count for, which D1 keeps once each.
    // A sector only ever sees a few guilds, so all their names are read.
    // Bonus words (s = 1, spelled by chance) stay here and in the game's field
    // notes, but aren't kept in the public log; the mark still moves past them.
    const shown = rows.filter((r) => !r.s);
    const lids = new Set(shown.flatMap((r) => r.guild.split(' ')).filter(Boolean));
    const guilds = lids.size ? this.sql.exec('SELECT lid, a, b, c FROM guild_names').toArray().filter((g) => lids.has(g.lid)) : [];
    await writeLog(this.env.LOG_DB, shown, novas, guilds);
    if (rows.length) this.sql.exec('INSERT INTO logged (id, at) VALUES (0, ?) ON CONFLICT (id) DO UPDATE SET at = excluded.at', upTo);
    for (const n of novas) this.sql.exec('UPDATE novas SET logged = 1 WHERE rx = ? AND ry = ?', n.rx, n.ry);
    return rows.length === LOG_BATCH;
  }

  novasUnlogged() {
    return this.sql.exec('SELECT rx FROM novas WHERE logged = 0 LIMIT 1').toArray().length > 0;
  }

  // Hidden words in each of the sector's territories, from the map: about
  // 3 ms of work, done once per waking.
  hiddenCounts() {
    if (!this.hidden) {
      const [sx, sy] = this.coords();
      this.hidden = Array.from({ length: TERR * TERR }, (_, t) => territoryTotal(sx * TERR + (t % TERR), sy * TERR + Math.floor(t / TERR)));
    }
    return this.hidden;
  }

  // Territory t (row by row, as territory() numbers them) has just had its
  // last hidden word charted: its supernova, recorded once, with the last
  // word, who charted it, when the first was, and who charted most. A
  // territory lies inside one sector and claims here run one at a time, so
  // only one claim can be the last, and the row is written with that claim,
  // before anything is awaited. Returns what neighbours are told
  // ([rx, ry, at, w, x, y, d, initials]), or null if it was already recorded.
  supernova(t) {
    const [sx, sy] = this.coords(), rx = sx * TERR + (t % TERR), ry = sy * TERR + Math.floor(t / TERR);
    const rows = this.sql.exec(
      'SELECT w, x, y, d, initials, at FROM claims WHERE s = 0 AND x >= ? AND x < ? AND y >= ? AND y < ? ORDER BY at, key',
      rx * RC, rx * RC + RC, ry * RC, ry * RC + RC,
    ).toArray();
    if (!rows.length) return null;
    const by = new Map();
    for (const r of rows) if (r.initials) by.set(r.initials, (by.get(r.initials) ?? 0) + 1);
    // Who charted most, as the log ranks surveyors: most words, then initials.
    const [top, topN] = [...by].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))[0] ?? ['', 0];
    const last = rows.at(-1);
    const inserted = this.sql.exec(
      `INSERT INTO novas (rx, ry, at, w, x, y, d, initials, first, words, surveyors, top, top_n)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (rx, ry) DO NOTHING RETURNING rx`,
      rx, ry, last.at, last.w, last.x, last.y, last.d, last.initials, rows[0].at, rows.length, by.size, top, topN,
    ).toArray().length;
    return inserted ? [rx, ry, last.at, last.w, last.x, last.y, last.d, last.initials] : null;
  }

  // Supernovas the sector hasn't recorded: territories completed before
  // supernovas were recorded at all. Looked for once per waking, from the
  // charted counts the sector keeps anyway.
  findNovas() {
    const counts = this.chartedCounts();
    if (!counts.some((n) => n > 0)) return;
    const hidden = this.hiddenCounts(), [sx, sy] = this.coords();
    const known = new Set(this.sql.exec('SELECT rx, ry FROM novas').toArray().map((r) => `${r.rx},${r.ry}`));
    for (let t = 0; t < TERR * TERR; t++) {
      if (counts[t] === hidden[t] && !known.has(`${sx * TERR + (t % TERR)},${sy * TERR + Math.floor(t / TERR)}`)) this.supernova(t);
    }
  }

  async webSocketClose(ws) {
    try { ws.close(1000); } catch { /* already closed */ }
    this.gone(ws);
    this.left();
  }

  async webSocketError(ws) {
    this.gone(ws);
    this.left();
  }

  // A socket closed. A player who was on the surveyor list comes off it with a
  // report straight away, rather than lingering for minutes.
  gone(ws) {
    let me = this.people?.get(ws);
    if (!me) try { me = ws.deserializeAttachment(); } catch { /* nothing kept */ }
    if (me?.pid && me.x !== null && me.x !== undefined) this.reportDue = true;
    this.people?.delete(ws);
  }

  save(ws, me) {
    me.saved = this.now();
    try { ws.serializeAttachment(me); } catch { /* closing */ }
  }

  // Someone left: the sector may go quiet now, so anything owed goes out.
  left() {
    this.sendBatch(true);
    this.schedulePresence(true);
    if (this.reportDue) this.maybeReport(true);
  }

  // Claims, positions or a report that came due since the last message.
  catchUp() {
    this.sendBatch();
    if (this.presenceDue && this.now() - this.presenceAt >= PRESENCE_MS) this.sendPresence();
    // At least every REFRESH_MS while anything comes in, changed or not, so the
    // Atlas keeps counting and listing players who sit still (their game says
    // 'here' every so often).
    if (this.reportDue || this.now() - this.reportedAt >= REFRESH_MS) this.maybeReport();
  }

  // Sending each claim to every socket costs players × claims sends, which
  // grows with the square of the crowd; batching claims for BATCH_MS cuts
  // that to players × 5 a second. The first claim after a lull goes at once.
  // Claims owed to a batch, however busy the sector, have a timer of their
  // own: without one, a sector that went quiet would hibernate with them
  // unsent, and their claimers would never hear they were first. It lasts at
  // most BATCH_MS, well inside the idle time before a sector can hibernate,
  // so it doesn't keep one awake.
  sendBatch(force = false) {
    if (!this.batch.length) return;
    const wait = BATCH_MS - (this.now() - this.batchAt);
    if (wait > 0 && !force) {
      if (!this.batchTimer) {
        this.batchTimer = setTimeout(() => { this.batchTimer = null; this.sendBatch(true); }, wait);
      }
      return;
    }
    clearTimeout(this.batchTimer);
    this.batchTimer = null;
    const frames = this.batch;
    this.batch = [];
    this.batchAt = this.now();
    broadcast(this.ctx, frames.length === 1 ? frames[0] : `[${frames.join(',')}]`);
  }

  here() {
    return [...this.everyone().values()].filter((p) => p.x !== null);
  }

  // Positions go out together, at most once a second, however many players
  // move: that keeps the messages a sector sends proportional to its players,
  // not to its players squared. Changes that aren't due yet go out with a
  // later message; a player leaving might be the last thing that happens in a
  // quiet sector, so that sets a timer instead of leaving a ghost behind.
  schedulePresence(leaving) {
    const wait = PRESENCE_MS - (this.now() - this.presenceAt);
    if (wait <= 0) return this.sendPresence();
    this.presenceDue = true;
    if (leaving && !this.presenceTimer && this.ctx.getWebSockets().length < QUIET) {
      this.presenceTimer = setTimeout(() => { this.presenceTimer = null; if (this.presenceDue) this.sendPresence(); }, wait);
    }
  }

  sendPresence() {
    this.presenceAt = this.now();
    this.presenceDue = false;
    // One caret a player: a player on two linked devices here shows where they last moved.
    const seen = new Set();
    let here = this.here().sort((a, b) => b.moved - a.moved).filter((p) => { const id = p.pid || p.id; return !seen.has(id) && seen.add(id); });
    // With more than fit, each address's latest mover comes first, then each
    // one's next, and so on: sockets from one address, however busy, can't
    // crowd everyone else off the map.
    if (here.length > PRESENCE_MAX) {
      const ranks = new Map(), rank = new Map();
      for (const p of here) { const a = p.address ?? p.id, r = ranks.get(a) ?? 0; ranks.set(a, r + 1); rank.set(p, r); }
      here = here.sort((a, b) => rank.get(a) - rank.get(b));
    }
    // A member's guild tags: one as a string, as an older game reads it, several as a list.
    // Then the badge they show and their card, if they have them.
    const tags = (p) => {
      const t = tagsOf(p), tag = t.length === 1 ? t[0] : t;
      return p.card ? [tag, p.badge || '', p.card] : p.badge ? [tag, p.badge] : t.length ? [tag] : [];
    };
    broadcast(this.ctx, JSON.stringify({ t: 'presence', n: here.length, p: here.slice(0, PRESENCE_MAX).map((p) => [p.pid || p.id, p.initials, p.x, p.y, ...tags(p)]) }));
    this.maybeReport();
  }

  // The middle of the crowd: the median of where players are looking, which
  // a few people wandering off on their own don't pull away from everyone else.
  // Each address counts once, where it last moved, so one address's sockets
  // can't choose the spot.
  crowd() {
    const latest = new Map();
    for (const p of this.here()) { const a = p.address ?? p.id, q = latest.get(a); if (!q || p.moved > q.moved) latest.set(a, p); }
    const here = [...latest.values()];
    if (!here.length) return null;
    const median = (values) => Math.floor(values.sort((a, b) => a - b)[values.length >> 1]);
    return [median(here.map((p) => p.x)), median(here.map((p) => p.y))];
  }

  // The surveyors listed here, for a report, and the guilds of everyone here,
  // for the Atlas to say which of their members are online: none leaves each out.
  listing() {
    const [sx, sy] = this.coords();
    const who = listed(this.everyone().values(), sx, sy, this.now());
    const all = new Set([...this.everyone().values()].flatMap(tagsOf));
    // A guild nobody here is in any more needs no last frame kept for it.
    for (const tag of this.guildSent?.keys() ?? []) if (!all.has(tag)) this.guildSent.delete(tag);
    // Past GUILD_TAGS_MAX, each report asks about the next ones round, so
    // every guild here hears who's online within a few reports.
    let tags = [...all].sort();
    if (tags.length > GUILD_TAGS_MAX) {
      const from = (this.tagsFrom ?? 0) % tags.length;
      tags = [...tags, ...tags].slice(from, from + GUILD_TAGS_MAX);
      this.tagsFrom = from + GUILD_TAGS_MAX;
    }
    return { ...(who.length ? { who } : {}), ...(tags.length ? { tags } : {}) };
  }

  // Whether an emote from here may go to sector (sx, sy): one in the shared
  // world, which the surveyor list covers, or one beside this, in view.
  reaches(sx, sy) {
    const [x, y] = this.coords();
    return inArea(sx, sy) || Math.max(Math.abs(sx - x), Math.abs(sy - y)) <= 1;
  }

  // Addresses past the daily cap; a new UTC day starts with none.
  overToday() {
    const day = Math.floor(this.now() / DAY_MS);
    if (day !== this.overDay) { this.overDay = day; this.over = new Set(); this.overAt = 0; }
    return this.over;
  }

  // Index of the sector's territory that holds cell (x, y), row by row.
  territory(x, y) {
    const [sx, sy] = this.coords();
    return (fdiv(y, RC) - sy * TERR) * TERR + fdiv(x, RC) - sx * TERR;
  }

  chartedCounts() {
    if (!this.counts) {
      this.counts = new Array(TERR * TERR).fill(0);
      for (const { x, y } of this.sql.exec('SELECT x, y FROM claims WHERE s = 0').toArray()) this.counts[this.territory(x, y)]++;
    }
    return this.counts;
  }

  // What the Atlas said in answer to a report or an ask: who is past the cap,
  // the shared world's supernovas (relay) and guild members online (passMates).
  heard(world) {
    this.overToday();  // in case the day turned while the report was out
    if (Array.isArray(world?.over) && world.day === this.overDay) {
      this.over = new Set(world.over.filter((a) => typeof a === 'string' && HASH.test(a)));
      this.overAt = isInt(world.overAt, 0, 1e9) ? world.overAt : 0;
    }
    if (world?.day === this.overDay) this.heardDay = this.overDay;
    this.relay(world);
    passMates(this, world?.guilds);
  }

  // Asks the Atlas who is past today's cap: a report without the words
  // charted since the last one (those go with the next report, as ever). Every
  // claim waiting on it shares the one ask. If the Atlas can't be reached,
  // claims go ahead, as they do when a rate limiter fails.
  ask() {
    this.asking ??= this.askAtlas().finally(() => { this.asking = null; });
    return this.asking;
  }

  async askAtlas() {
    this.askedAt = this.now();
    try {
      // The ids this request lists, read before anything else can go out and change them.
      const sent = this.toAtlas({ by: [] }), listed = this.listedIds;
      const res = await sent;
      if (res.ok) { const world = await res.json(); this.heard(world); this.takeTotals(world, listed); }
    } catch { /* claims go ahead */ }
  }

  // A report to the Atlas: the sector's numbers, with what this one carries (`extra`).
  // Claims still waiting for their batch go out first: the totals that come
  // back count them, and the game adds every claim it hears of to the last
  // totals it had, so it must hear of each claim before totals that count it,
  // or it counts that one twice.
  toAtlas(extra) {
    const [sx, sy] = this.coords();
    this.sendBatch(true);
    this.overToday();
    const listing = this.listing();
    this.listedIds = new Set((listing.who ?? []).map((e) => e[0]));
    this.reportedPlayers = this.headcount();
    return atlas(this.env).fetch('https://atlas/report', {
      method: 'POST',
      body: JSON.stringify({
        sx, sy, players: this.reportedPlayers, perAddress: this.perAddress(), charted: this.chartedCounts(), hot: this.crowd() ?? this.hot,
        day: this.overDay, overAt: this.overAt, novaSeq: this.heardNovaSeq(), ...listing, ...extra,
      }),
    });
  }

  // People here, each once: a surveyor on two linked devices is one, as on the
  // surveyor list, which counts by id.
  headcount() {
    return new Set(this.here().map((p) => p.pid || p.id)).size;
  }

  // The same, by address: [[address, people], ...], for the Atlas to count
  // each address for at most ADDRESS_ONLINE across the survey.
  perAddress() {
    const by = new Map();
    for (const p of this.here()) if (p.address) { if (!by.has(p.address)) by.set(p.address, new Set()); by.get(p.address).add(p.pid || p.id); }
    return [...by].map(([address, ids]) => [address, ids.size]);
  }

  // The world's totals, as the Atlas answered a report, to each socket here
  // whose frame they change (or to `to`). Each says whether the count takes in
  // that socket's surveyor (`you`): this sector listed them in the report, so
  // the game can leave itself out of "others online" exactly, rather than
  // guess it was counted.
  takeTotals(world, ids) {
    if (!isInt(world?.charted, 0, AREA_WORDS) || !isInt(world?.players, 0, 1e9)) return;
    this.world = { charted: world.charted, total: AREA_WORDS, players: world.players };
    this.counted = ids;
    this.tellWorld();
  }

  tellWorld(to = this.ctx.getWebSockets()) {
    for (const ws of to) {
      const pid = this.person(ws)?.pid;
      const frame = JSON.stringify({ t: 'world', ...this.world, ...(pid && this.counted.has(pid) ? { you: 1 } : {}) });
      if (this.worldSent.get(ws) === frame) continue;
      this.worldSent.set(ws, frame);
      try { ws.send(frame); } catch { /* closing */ }
    }
  }

  // Sectors in the shared world tell the Atlas their numbers at most every
  // REPORT_MS, when something changed: with a later message, or when a player
  // leaves (`force`). A report timer would be pending most of the time in a
  // sector with a few people circling words, and bill it for all of it. The
  // Atlas answers with the world's totals, which are passed on to players,
  // and the shared world's latest supernovas. A supernova here goes at once,
  // or NOVA_REPORT_MS after the last report.
  maybeReport(force = false) {
    const where = this.coords();
    if (!this.env.ATLAS || !where || !inArea(...where)) return;
    const since = this.now() - this.reportedAt;
    // A supernova here, or the crowd here just filled past SPAWN_MAX or
    // emptied below it: new players are being sent here, or should be, so
    // the Atlas hears it within a second rather than REPORT_MS. While a burst
    // of newcomers arrives, the spot it hands out is only as fresh as this.
    const owed = since >= NOVA_REPORT_MS && (this.novasOwed.length > 0
      || (this.reportedPlayers !== undefined && (this.reportedPlayers < SPAWN_MAX) !== (this.headcount() < SPAWN_MAX)));
    // One forced while a report is out (someone left, and the sector may now
    // go quiet) goes as soon as that report is answered, or has failed.
    if (this.reporting && force) this.leaveDue = true;
    if (this.reporting || (!force && !owed && since < REPORT_MS)) { this.reportDue = true; return; }
    this.report();
  }

  async report() {
    this.reportedAt = this.now();
    this.reportDue = false;
    this.reporting = true;
    // Words charted by each address since the last report: sent once, or
    // put back to go with the next report if this one fails.
    // At most REPORT_BY_MAX addresses, the most words first, so a report
    // stays one the Atlas takes however many charted here since the last
    // one: the rest go with the next.
    let by = this.chartedBy;
    const unpassed = this.unpassed, novas = this.novasOwed;
    this.chartedBy = new Map();
    if (by.size > REPORT_BY_MAX) {
      const most = [...by].sort((a, b) => b[1] - a[1]);
      by = new Map(most.slice(0, REPORT_BY_MAX));
      this.chartedBy = new Map(most.slice(REPORT_BY_MAX));
      this.reportDue = true;
    }
    this.unpassed = 0;
    this.novasOwed = [];
    let world, listed;
    try {
      const sent = this.toAtlas({ by: [...by], ...(unpassed ? { unpassed } : {}), ...(novas.length ? { novas } : {}) });
      listed = this.listedIds;  // as askAtlas: this request's own, before an ask can change them
      const res = await sent;
      if (!res.ok) throw new Error(`atlas ${res.status}`);
      world = await res.json();
      this.paid(by, unpassed, novas);
    } catch {
      for (const [address, n] of by) this.chartedBy.set(address, (this.chartedBy.get(address) ?? 0) + n);
      this.unpassed += unpassed;
      this.novasOwed.unshift(...novas);
      this.reportDue = true;  // the totals just go out later, with a later message
      world = null;
    }
    this.reporting = false;
    if (world) this.heard(world);
    if (this.leaveDue) { this.leaveDue = false; this.maybeReport(true); }
    else if (world && this.novasOwed.length) this.maybeReport();  // one that came while this report was out
    if (world) this.takeTotals(world, listed);
  }
}

// The whole shared world at a glance: hidden words charted in each of its
// 10,000 territories and players online in each sector. Sectors send it
// absolute numbers, never changes, so a lost or repeated report does no harm
// and a sector that reports again puts right anything the Atlas lost.
export class Atlas {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.sql = ctx.storage.sql;
    this.now = () => Date.now();
    this.rows = null;      // 'sx,sy' → {sx, sy, players, charted: [16 counts], done, hot, who, at}, loaded on first use
    this.dirty = new Set();
    this.held = new Map();  // address → people it has placed in sectors reporting now (hold())
    this.heldOver = 0;      // how many those add up to past ADDRESS_ONLINE each
    // Who those sectors list, kept up to date the same way (count()): each id
    // → how many of their reports list it, and the people they count without
    // an id. Working these out afresh on every report walked everyone online,
    // most of what a report cost (bench/atlas.js).
    this.ids = new Map();
    this.unlisted = 0;
    this.saveTimer = null;
    this.view = null;      // the world map as JSON, rebuilt at most every VIEW_MS
    this.list = null;      // everyone on the surveyor list as JSON, rebuilt at most every LIST_MS
    this.daily = dailyClaims(env);
    // Words each address charted today (UTC), and those past the daily cap in
    // the order they got there (address → its place, `overSeq` when it was
    // put there). Kept in memory only: the Atlas hears from every busy sector
    // every few seconds, so it's rarely evicted, and if it is, the day's
    // counts start again. `overSeq` counts every change to the list, and goes
    // to sectors as `overAt`: they're sent the list again when it changes.
    this.day = -1;
    this.chartedToday = new Map();
    this.overList = new Map();
    this.overSeq = 0;
    // The numbers that would show bots at work, for the UTC day so far and
    // the day before (in the world map), and for the hour so far (in an
    // hourly line in Workers Logs). Bots that claim without saying where
    // they are add words charted but no player-hours, so words per
    // player-hour climbs far past what people manage (about one a minute).
    // Joins without a Turnstile pass (`unpassed`, see TURNSTILE.md) are
    // almost all scripts once the game has a site key.
    this.stats = this.newStats(-1);
    this.yesterday = null;
    this.hour = { at: -1, charted: 0, playerHours: 0 };
    this.sampledAt = 0;
    this.playersNow = 0;   // players online, as the last report's answer counted them
    // The shared world's latest supernovas, as sectors report them, for every
    // sector to pass on with its next report: {seq, n, at}, numbered in order
    // by the Atlas's clock so a sector's count survives the Atlas being
    // evicted. Kept in memory, for RELAY_MS.
    this.novas = [];
    this.novaKeys = new Set();  // 'rx,ry' of every one heard since waking, so a resent report adds none twice
    this.lastNovaSeq = 0;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS sectors (
      sx INTEGER NOT NULL, sy INTEGER NOT NULL, charted TEXT NOT NULL, done INTEGER NOT NULL,
      PRIMARY KEY (sx, sy)) WITHOUT ROWID`);
    // Sectors' counts from an older map; each sector reports afresh once it wakes.
    if (onOlderMap(this.sql)) this.sql.exec('DELETE FROM sectors');
  }

  load() {
    if (!this.rows) {
      this.rows = new Map();
      for (const r of this.sql.exec('SELECT sx, sy, charted, done FROM sectors').toArray()) {
        this.rows.set(`${r.sx},${r.sy}`, { sx: r.sx, sy: r.sy, players: 0, charted: r.charted.split(',').map(Number), done: r.done, hot: null, who: [], at: 0 });
      }
    }
    return this.rows;
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);
    const json = (body, status = 200) => Response.json(body, { status });
    if (request.method === 'POST' && pathname === '/report') {
      let r = null;
      try { r = await request.json(); } catch { /* answered below */ }
      const by = r?.by ?? [];
      const ok = r && Number.isInteger(r.sx) && Number.isInteger(r.sy) && inArea(r.sx, r.sy) && isInt(r.players, 0, MAX_PLAYERS)
        && Array.isArray(r.charted) && r.charted.length === TERR * TERR && r.charted.every((n) => isInt(n, 0, 1000))
        && Array.isArray(by) && by.length <= REPORT_BY_MAX
        && by.every((e) => Array.isArray(e) && typeof e[0] === 'string' && HASH.test(e[0]) && isInt(e[1], 1, TERR * TERR * 1000))
        && (r.unpassed === undefined || isInt(r.unpassed, 0, 1e6)) && goodWho(r.who, r.sx, r.sy, MAX_PLAYERS)
        && (r.perAddress === undefined || (Array.isArray(r.perAddress) && r.perAddress.length <= MAX_PLAYERS
          && r.perAddress.every((e) => Array.isArray(e) && typeof e[0] === 'string' && HASH.test(e[0]) && isInt(e[1], 1, MAX_PLAYERS))))
        && (r.tags === undefined || (Array.isArray(r.tags) && r.tags.length <= GUILD_TAGS_MAX && r.tags.every((t) => typeof t === 'string' && GUILD_TAG.test(t))))
        && (r.novaSeq === undefined || Number.isInteger(r.novaSeq)) && (r.novas === undefined || (Array.isArray(r.novas) && r.novas.length <= TERR * TERR));
      if (!ok) return json({ error: 'bad report' }, 400);
      this.tally();
      this.countCharted(by);
      this.stats.unpassed += r.unpassed ?? 0;  // tally() has rolled the day
      const key = `${r.sx},${r.sy}`, done = r.charted.reduce((a, b) => a + b, 0), old = this.load().get(key);
      const inside = (v, s) => Number.isInteger(v) && fdiv(v, SECTOR) === s;
      const hot = Array.isArray(r.hot) && inside(r.hot[0], r.sx) && inside(r.hot[1], r.sy) ? r.hot.slice(0, 2) : old?.hot ?? null;
      if (old?.held) this.release(old);
      // A crowd that just filled up, or has room again, changes where new
      // players start: the world map is built afresh for the next to ask.
      if (((old?.players ?? 0) < SPAWN_MAX) !== (r.players < SPAWN_MAX)) this.view = null;
      const row = { sx: r.sx, sy: r.sy, players: r.players, perAddress: r.perAddress ?? [], held: true, charted: r.charted, done, hot, who: r.who ?? [], at: this.now() };
      this.rows.set(key, row);
      this.hold(row.perAddress, 1);
      this.count(row, 1);
      noteMates(this, key, r.who, this.now());  // who's online in each guild (survey-guild.js)
      // A sector nobody's in may not report again for days, so its last
      // count is stored straight away, whether it changed now or in a
      // report still waiting for the flush: one only in memory would be
      // lost if the Atlas were evicted (by a deploy, say) before then.
      if (!old || old.done !== done || (r.players === 0 && this.dirty.has(key))) this.save(key, r.players === 0);
      this.takeNovas(r);
      const totals = this.totals();
      this.playersNow = totals.players;  // for tally() at the next report
      // The list of addresses past the cap goes back only when it has
      // changed since this sector last heard it.
      const fresh = r.day === this.day && r.overAt === this.overSeq;
      return json({
        ...totals, day: this.day, overAt: this.overSeq, ...(fresh ? {} : { over: [...this.overList.keys()].slice(-DAILY_LIST_MAX) }),
        ...(r.tags?.length ? { guilds: matesFor(this, r.tags, this.now(), ONLINE_MS) } : {}),
        ...this.novasFor(r.novaSeq),
      });
    }
    if (request.method === 'GET' && pathname === TOTALS_PATH) return json(this.totals());
    // Everyone on the surveyor list, rebuilt at most every LIST_MS (survey-social.js).
    if (request.method === 'GET' && pathname === ATLAS_LIST_PATH) {
      const now = this.now();
      if (!this.list || now - this.list.at >= LIST_MS) this.list = { at: now, body: JSON.stringify(snapshot(this.load().values(), now, ONLINE_MS)) };
      return new Response(this.list.body, { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
    }
    if (request.method === 'GET' && pathname === '/world') {
      const now = this.now();
      if (!this.view || now - this.view.at >= VIEW_MS) this.view = { at: now, body: JSON.stringify(this.worldMap()) };
      return new Response(this.view.body, { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
    }
    return json({ error: 'not found' }, 404);
  }

  // Supernovas a sector reports, each checked against the map and against
  // the sector's own counts in the same report, which must show its
  // territory complete. A bad one is dropped; the report still counts.
  takeNovas(r) {
    for (const n of r.novas ?? []) {
      if (!checkNovaWord(n)) continue;
      const [rx, ry] = n, k = `${rx},${ry}`;
      if (fdiv(rx, TERR) !== r.sx || fdiv(ry, TERR) !== r.sy || this.novaKeys.has(k)) continue;
      if (r.charted[(ry - r.sy * TERR) * TERR + rx - r.sx * TERR] !== territoryTotal(rx, ry)) continue;
      this.lastNovaSeq = Math.max(this.now(), this.lastNovaSeq) + 1;
      this.novas.push({ seq: this.lastNovaSeq, n, at: this.now() });
      this.novaKeys.add(k);
    }
  }

  // What goes back to a sector that has passed on supernovas up to `seq`:
  // those since, and the count to send next time. A sector that has never
  // heard any (-1) starts from now: its players weren't there for the rest.
  novasFor(seq) {
    if (!Number.isInteger(seq)) return {};
    const cut = this.now() - RELAY_MS;
    while (this.novas.length && (this.novas[0].at < cut || this.novas.length > RELAY_MAX)) this.novas.shift();
    if (seq < 0) return { novaSeq: Math.max(this.now(), this.lastNovaSeq) };
    const novas = this.novas.filter((e) => e.seq > seq).map((e) => e.n);
    return { novaSeq: Math.max(seq, this.lastNovaSeq), ...(novas.length ? { novas } : {}) };
  }

  countCharted(by) {
    this.rollDay();
    for (const [address, n] of by) {
      const before = this.chartedToday.get(address) ?? 0;
      this.chartedToday.set(address, before + n);
      this.stats.charted += n;
      this.hour.charted += n;
      if (before < this.daily && before + n >= this.daily) {
        this.overList.set(address, ++this.overSeq);
        console.log({ survey: 'daily cap', capped: this.overList.size });  // never the address, hashed or not
      } else if (before >= this.daily && this.overSeq - this.overList.get(address) >= DAILY_LIST_MAX) {
        // Past the cap, but charting again: it has dropped out of the latest
        // DAILY_LIST_MAX the sectors are handed, so it goes back to the end.
        // (Places only ever move later, so this may move one that hadn't quite
        // dropped out yet, which does no harm.)
        this.overList.delete(address);
        this.overList.set(address, ++this.overSeq);
      }
    }
  }

  newStats(day) {
    return { day, charted: 0, addresses: 0, capped: 0, playerHours: 0, unpassed: 0 };
  }

  // A new UTC day: today's numbers become yesterday's, and the counts per address start again.
  rollDay() {
    const day = Math.floor(this.now() / DAY_MS);
    if (day === this.day) return;
    // Yesterday is the day before this one: if the Atlas heard nothing that
    // day, it was a day of zeros, not the last day it did hear about.
    if (this.day >= 0) this.yesterday = day - this.day === 1 ? this.statsNow() : this.newStats(day - 1);
    this.day = day;
    this.chartedToday = new Map();
    this.overList = new Map();
    this.overSeq = 0;
    this.stats = this.newStats(day);
  }

  statsNow() {
    const s = { ...this.stats, addresses: this.chartedToday.size, capped: this.overList.size };
    s.playerHours = Math.round(s.playerHours * 100) / 100;
    return s;
  }

  // On each report: adds up player-hours since the last one, from the players
  // online as it began (a gap counts for at most ONLINE_MS, after which
  // nobody counted then is online any more), and
  // once an hour writes the hour's numbers to the log.
  tally() {
    const now = this.now();
    this.rollDay();
    if (this.sampledAt) {
      // Players online since the last report, as its answer counted them:
      // counting again here would walk every surveyor online a second time.
      const hours = this.playersNow * Math.min(now - this.sampledAt, ONLINE_MS) / HOUR_MS;
      this.stats.playerHours += hours;
      this.hour.playerHours += hours;
    }
    this.sampledAt = now;
    const hour = Math.floor(now / HOUR_MS);
    if (hour === this.hour.at) return;
    if (this.hour.at >= 0) {
      const { charted, playerHours } = this.hour;
      console.log({
        survey: 'hour', hour: new Date(this.hour.at * HOUR_MS).toISOString(), charted,
        playerHours: Math.round(playerHours * 100) / 100,
        perPlayerHour: playerHours > 0 ? Math.round(charted / playerHours) : null,
        today: this.statsNow(),
      });
    }
    this.hour = { at: hour, charted: 0, playerHours: 0 };
  }

  // Charted counts only change storage once a minute per sector at most:
  // writing every report would cost a row written per busy sector every
  // REPORT_MS, and players online don't need storing at all. A sector's
  // last report as it empties is written at once (`now`), since nothing
  // there will report again to put it right if this one is lost.
  save(key, now = false) {
    if (now) { this.dirty.delete(key); return this.write(key); }
    this.dirty.add(key);
    this.saveTimer ??= setTimeout(() => this.flush(), SAVE_MS);
  }

  flush() {
    this.saveTimer = null;
    for (const key of this.dirty) this.write(key);
    this.dirty.clear();
  }

  write(key) {
    const r = this.rows.get(key);
    this.sql.exec(
      'INSERT INTO sectors (sx, sy, charted, done) VALUES (?, ?, ?, ?) ON CONFLICT (sx, sy) DO UPDATE SET charted = excluded.charted, done = excluded.done',
      r.sx, r.sy, r.charted.join(','), r.done,
    );
  }

  totals() {
    const now = this.now();
    // Players by id, so someone in two sectors' reports (moving between them,
    // or on two devices) counts once, as on the surveyor list; and anyone a
    // sector counts without listing (an older game, with no id), as they are.
    // But no address counts for more than ADDRESS_ONLINE, however many
    // sectors it's in: sockets from a few addresses, spread over the shared
    // world, can't fill the survey (MAX_ONLINE) and lock everyone out.
    // That cap is taken from each sector's own counts, so someone listed in
    // two sectors' reports counts twice toward their address's held people
    // while counting once in ids: near the cap, players online can read low.
    // It only ever errs toward letting people in, so it's left that way.
    // The ids and people come from count(), kept up to date report by report,
    // so this only walks the sectors, not everyone in them.
    let charted = 0;
    for (const r of this.load().values()) {
      charted += r.done;
      if (r.held && now - r.at >= ONLINE_MS) this.release(r);
    }
    return { charted, total: AREA_WORDS, players: Math.max(0, this.ids.size + this.unlisted - this.heldOver) };
  }

  // A sector's last report stops counting: it has reported again, or not for ONLINE_MS.
  release(r) {
    this.hold(r.perAddress, -1);
    this.count(r, -1);
    r.held = false;
  }

  // The ids a sector's report lists, and the people it counts without one,
  // in or out of the players online (sign 1 or -1).
  count(r, sign) {
    for (const e of r.who) {
      const n = (this.ids.get(e[0]) ?? 0) + sign;
      if (n > 0) this.ids.set(e[0], n);
      else this.ids.delete(e[0]);
    }
    this.unlisted += sign * Math.max(0, r.players - r.who.length);
  }

  // People each address has placed in sectors reporting now, kept up to
  // date report by report (a sector's last replaces what it said before),
  // and how many past ADDRESS_ONLINE they add up to: one pass over every
  // address on each report would cost the Atlas more than the rest of it.
  hold(perAddress, sign) {
    for (const [address, n] of perAddress) {
      const before = this.held.get(address) ?? 0, after = before + sign * n;
      this.heldOver += Math.max(0, after - ADDRESS_ONLINE) - Math.max(0, before - ADDRESS_ONLINE);
      if (after > 0) this.held.set(address, after);
      else this.held.delete(address);
    }
  }

  worldMap() {
    const now = this.now(), size = (2 * AREA + 1) * TERR, bytes = new Uint8Array(size * size), sectors = [], live = [];
    for (const r of this.load().values()) {
      for (let i = 0; i < TERR * TERR; i++) {
        const tx = (r.sx + AREA) * TERR + (i % TERR), ty = (r.sy + AREA) * TERR + Math.floor(i / TERR);
        bytes[ty * size + tx] = Math.min(255, r.charted[i]);
      }
      if (r.players && now - r.at < ONLINE_MS) { sectors.push([r.sx, r.sy, r.players]); live.push(r); }
    }
    let territories = '';
    for (const b of bytes) territories += String.fromCharCode(b);
    this.rollDay();
    return {
      ...this.totals(), area: AREA, territories: btoa(territories), sectors, ...this.spawn(live),
      today: this.statsNow(), yesterday: this.yesterday,
    };
  }

  // Where a new player should start, as a cell (`spawn`): in the middle of
  // the biggest crowd that still has room, so the first thing they see is
  // lots of people at work; beside the biggest crowd if every crowd is full;
  // or at the origin (null) while nobody is playing.
  // A crowd's size here counts each address once, where sectors say (an
  // older sector doesn't), so one address's sockets don't make the biggest.
  // And `spawns`, the biggest few crowds with room, each [x, y, size, room]:
  // everyone arriving within a few seconds reads the same world map, and the
  // Atlas hears of them only with their sectors' next reports, so a burst of
  // newcomers all sent to one crowd would fill it far past SPAWN_MAX
  // (bench/spike.js). The game picks among these by how much each could take.
  spawn(live) {
    const centre = (r) => [r.sx * SECTOR + SECTOR / 2, r.sy * SECTOR + SECTOR / 2];
    const size = (r) => (r.perAddress?.length ? r.perAddress.length : r.players);
    const open = live.filter((r) => r.players < SPAWN_MAX).sort((a, b) => size(b) - size(a));
    if (open.length) {
      const spawns = open.slice(0, SPAWNS_MAX).map((r) => [...(r.hot ?? centre(r)), size(r), SPAWN_MAX - r.players]);
      return { spawn: spawns[0].slice(0, 2), spawns };
    }
    if (!live.length) return { spawn: null, spawns: [] };
    const biggest = live.reduce((a, b) => (b.players > a.players ? b : a));
    const [dx, dy] = DIRS[Math.floor(Math.random() * 8)];
    const clamp = (v) => Math.max(-AREA, Math.min(AREA, v));
    const beside = centre({ sx: clamp(biggest.sx + dx), sy: clamp(biggest.sy + dy) });
    return { spawn: beside, spawns: [[...beside, 0, SPAWN_MAX]] };
  }
}
