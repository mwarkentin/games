// War rooms: multiplayer games of War for war.html. Each room is a Durable
// Object holding the game, with every player connected over a WebSocket.
// src/index.js exports the WarRoom class and sends /v1/war/ requests here;
// tests import this module directly.
//
//   POST /v1/war/rooms           start a room, returns its four-character code
//   GET  /v1/war/rooms/<code>    look a room up, or, as a WebSocket, join it
//
// The room deals, waits for slams and plays every battle; the pages only show
// what it tells them. Solo games run the same rules in the page (see the core
// below).

import { CODE, CODE_ALPHABET, HttpError, corsHeaders, hashIp, json, rateLimit } from './leaderboard.js';

// ---- BEGIN WAR CORE ----
// The rules of War and the pacing of a game, shared word for word by war.html
// (solo games against bots) and worker/src/war.js (rooms played over the
// network). worker/test/war.test.js checks that the two copies match, so
// change both. A slam's power and style are passed along for show, but the
// rules never read them: slamming changes nothing.
const WAR = {
  MAX_PLAYERS: 50,
  LENGTHS: { quick: 20, standard: 60, long: 150, total: 5000 },  // battles at most
  MAX_POWER: 200,
  STYLES: 11,          // power-ups, 0 for bare hands
  AVATARS: 24,
  TIERS: 9,            // slam tiers, from boop to cosmic
  DECK: 54,            // cards in a deck: the usual 52 and two jokers
  STAGE_MS: 8000,      // to slam before your card flops over by itself
  WAR_STAGE_MS: 20000, // the same in a war, where you slam every card you lay down
  NAPS: 2,             // flops in a row before a stage stops waiting for you
  BOT_MS: 1300,        // the shortest a stage lasts, while the bots slam
  WAR_BOT_MS: 2600,    // the same in a war, while the bots slam all their cards
  REVEAL_MS: 2400,     // to watch the cards turn over before the next battle
  WAR_REVEAL_MS: 3000, // the same before a war
};

const WAR_BOT_FIRST = [
  'Sir', 'Lady', 'Captain', 'Doctor', 'Baron', 'Auntie', 'Professor', 'Lil', 'Big', 'Sleepy',
  'Grumpy', 'Sneaky', 'Lucky', 'Soggy', 'Turbo', 'Dizzy', 'Cosmic', 'Wobbly', 'Mighty', 'Tiny',
];
const WAR_BOT_LAST = [
  'Shuffles', 'Pancake', 'Noodle', 'Walrus', 'Biscuit', 'Pickle', 'Waffle', 'Badger', 'Muffin', 'Goose',
  'Nugget', 'Meatball', 'Toast', 'Pebble', 'Beans', 'Squid', 'Crumpet', 'Tater', 'Wombat', 'Jellybean',
];

// Cards are numbers, WAR.DECK to a deck. In each deck, card % WAR.DECK is
// suit * 13 + rank for the usual 52 cards (rank 0 is a two, 12 an ace), and 52
// and 53 are the jokers, which beat every other card: their rank is 13. Two
// jokers tie, like any two cards of the same rank. There's a deck for every two
// players, so everyone starts with about 27 cards however many play.
function warRank(card) {
  const face = card % WAR.DECK;
  return face < 52 ? face % 13 : 13;
}

function warShuffle(cards, random) {
  for (let i = cards.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [cards[i], cards[j]] = [cards[j], cards[i]];
  }
  return cards;
}

function warDeal(count, random) {
  const decks = Math.max(1, Math.ceil(count / 2));
  const cards = warShuffle(Array.from({ length: WAR.DECK * decks }, (_, i) => i), random);
  const piles = Array.from({ length: count }, () => []);
  cards.forEach((card, i) => piles[i % count].push(card));
  return piles;
}

function warBotNames(count, random, taken) {
  const used = new Set(taken || []);
  const names = [];
  while (names.length < count) {
    const name = WAR_BOT_FIRST[Math.floor(random() * WAR_BOT_FIRST.length)] + ' '
      + WAR_BOT_LAST[Math.floor(random() * WAR_BOT_LAST.length)];
    if (!used.has(name)) { used.add(name); names.push(name); }
  }
  return names;
}

// Some bots place their cards gently, most slam, a few lose control entirely.
function warBotPower(random) {
  const r = random();
  if (r < 0.25) return Math.floor(random() * 40);
  if (r < 0.8) return 40 + Math.floor(random() * 90);
  return 150 + Math.floor(random() * 51);
}

// A new game for seats 0..n-1, where bots[seat] is true for a bot. Returns
// the game and the message opening its first battle.
function warNewGame(bots, length, random, now, pace) {
  const game = {
    limit: WAR.LENGTHS[length] || WAR.LENGTHS.standard,
    piles: warDeal(bots.length, random),
    bots: bots.slice(),
    out: bots.map(() => 0),  // the battle each player ran out of cards in
    naps: bots.map(() => 0), // stages in a row each player's card flopped over by itself
    battle: 0, stage: 0, fighters: [], slams: {}, pot: [],
    opensAt: 0, closesAt: 0, pace: pace || 1,
    wars: 0, biggest: 0, deepest: 0, over: null,
  };
  return { game, stage: warOpenStage(game, now, random, null, 0) };
}

// How long the bots take to slam: a moment in a battle, longer in a war,
// where they slam every card they lay down.
function warBotMs(game) {
  return Math.round((game.stage ? WAR.WAR_BOT_MS : WAR.BOT_MS) * game.pace);
}

// Opens the next stage: a new battle for everyone still holding cards, or,
// when fighters is given, a war between them. Bots slam straight away; the
// pages show their slams one by one while the stage opens.
function warOpenStage(game, now, random, fighters, delay) {
  if (fighters) {
    game.stage++;
    game.fighters = fighters;
  } else {
    game.battle++;
    game.stage = 0;
    game.fighters = game.piles.map((_, seat) => seat).filter((seat) => game.piles[seat].length);
    game.pot = [];
  }
  game.slams = {};
  game.opensAt = now + Math.round(delay * game.pace);
  game.closesAt = game.opensAt + (game.stage ? WAR.WAR_STAGE_MS : WAR.STAGE_MS);
  const bots = [];
  for (const seat of game.fighters) {
    if (!game.bots[seat]) continue;
    const power = warBotPower(random);
    const style = Math.floor(random() * WAR.STYLES);
    game.slams[seat] = [power, style, 0];
    bots.push([seat, power, style, Math.round(100 * game.pace + random() * (warBotMs(game) - 300 * game.pace))]);
  }
  return {
    t: 'stage', battle: game.battle, stage: game.stage, limit: game.limit, fighters: game.fighters.slice(),
    opensIn: game.opensAt - now, closesIn: game.closesAt - now, bots,
  };
}

// Players (not bots) in this stage who are online and haven't slammed yet,
// unless they've dozed off: then nobody waits for them until they slam again.
function warWaitingFor(game, online) {
  return game.fighters.filter((seat) => !game.bots[seat] && online.has(seat) && !game.slams[seat]
    && game.naps[seat] < WAR.NAPS);
}

// When to play the stage out: once everyone online has slammed and the bots
// have had their moment, or when time runs out.
function warDueAt(game, online) {
  return warWaitingFor(game, online).length ? game.closesAt : game.opensAt + warBotMs(game);
}

// Records a slam. Returns the message to pass on, or null when it doesn't
// count: the game is over, the seat isn't fighting, or it already slammed.
function warSlam(game, seat, power, style) {
  if (game.over || !game.fighters.includes(seat) || game.slams[seat]) return null;
  power = Math.max(0, Math.min(WAR.MAX_POWER, Math.round(Number(power)) || 0));
  style = Number.isInteger(style) && style >= 0 && style < WAR.STYLES ? style : 0;
  game.slams[seat] = [power, style, 0];
  game.naps[seat] = 0;
  return { t: 'slam', seat, power, style };
}

// Plays the stage out. Every fighter turns over their top card (in a war,
// after laying up to three face down, keeping one to turn over) and the
// highest rank takes the pot. A tie is a war between the tied players who
// still have cards: if only one does, they win; if none do, the war gods pick.
// Anyone who hasn't slammed flops their card over anyway. Returns the message
// describing it all, with the next stage or the end of the game.
function warResolve(game, now, random) {
  const plays = [];
  let best = -1;
  for (const seat of game.fighters) {
    const pile = game.piles[seat];
    const slam = game.slams[seat] || [0, 0, 1];
    if (slam[2]) game.naps[seat]++;
    const down = game.stage ? Math.min(3, pile.length - 1) : 0;
    game.pot.push(...pile.splice(0, down));
    const up = pile.shift();
    game.pot.push(up);
    best = Math.max(best, warRank(up));
    plays.push([seat, down, up, ...slam]);
  }
  const tied = plays.filter((play) => warRank(play[2]) === best).map((play) => play[0]);
  const able = tied.filter((seat) => game.piles[seat].length);
  let winner = tied.length === 1 ? tied[0] : able.length === 1 ? able[0] : null;
  const gods = tied.length > 1 && !able.length;
  if (gods) winner = tied[Math.floor(random() * tied.length)];
  const message = { t: 'flip', battle: game.battle, stage: game.stage, plays, tied, winner, gods, pot: game.pot.length };
  if (winner === null) {
    if (!game.stage) game.wars++;
    game.biggest = Math.max(game.biggest, able.length);
    game.deepest = Math.max(game.deepest, game.stage + 1);
    message.counts = game.piles.map((pile) => pile.length);
    message.next = warOpenStage(game, now, random, able, WAR.WAR_REVEAL_MS);
    return message;
  }
  game.piles[winner].push(...warShuffle(game.pot, random));
  game.pot = [];
  message.counts = game.piles.map((pile) => pile.length);
  message.out = [];
  message.counts.forEach((count, seat) => {
    if (!count && !game.out[seat]) { game.out[seat] = game.battle; message.out.push(seat); }
  });
  if (message.counts.filter(Boolean).length <= 1 || game.battle >= game.limit) {
    game.fighters = [];
    game.over = warStandings(game);
    message.over = game.over;
  } else {
    message.next = warOpenStage(game, now, random, null, WAR.REVEAL_MS);
  }
  return message;
}

// Most cards first, then whoever lasted longest. Everyone tied for the most
// cards wins.
function warStandings(game) {
  const counts = game.piles.map((pile) => pile.length);
  const lasted = (seat) => game.out[seat] || Infinity;
  const order = counts.map((_, seat) => seat).sort((a, b) => counts[b] - counts[a] || lasted(b) - lasted(a) || a - b);
  const most = counts[order[0]];
  return {
    winners: order.filter((seat) => counts[seat] === most), order, counts, out: game.out.slice(),
    battles: game.battle, wars: game.wars, biggest: game.biggest, deepest: game.deepest,
  };
}
// ---- END WAR CORE ----

export {
  WAR, warBotNames, warDeal, warDueAt, warNewGame, warOpenStage, warRank, warResolve, warShuffle, warSlam,
  warStandings, warWaitingFor,
};

const HOUR = 60 * 60 * 1000;
export const EXPIRE_MS = 6 * HOUR;  // a room nobody has used for this long is deleted
export const MAX_SOCKETS = 60;       // players and spectators
const MAX_MESSAGE = 1024;
const CHEERS = 6;
const CHEER_GAP_MS = 400;
const NAME = /^[\p{L}\p{N}][\p{L}\p{N} '&.,!?-]{0,15}$/u;
const TOKEN = /^[A-Za-z0-9-]{16,64}$/;
const CLOSING = 2;

const roomStub = (env, code) => env.WAR_ROOMS.get(env.WAR_ROOMS.idFromName(code));

function newCode() {
  return [...crypto.getRandomValues(new Uint8Array(4))].map((b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
}

export function cleanName(value) {
  const name = typeof value === 'string' ? value.trim().replace(/\s+/g, ' ') : '';
  return NAME.test(name) ? name : null;
}

// One room. Its state is a single storage value, saved when something
// changes for good (a player joins, a stage is played out); slams in the
// current stage live only in memory, so a room woken from hibernation
// forgets them and those cards flop over when time runs out. The alarm
// closes each stage and, once a room is idle, deletes it. While nobody is
// connected, a game in progress waits for someone to come back.
export class WarRoom {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.room = undefined;
    this.alarmAt = null;
    this.gone = new WeakSet();
    this.cheered = new WeakMap();
    this.now = () => Date.now();
    this.random = Math.random;
  }

  async load() {
    if (this.room === undefined) this.room = (await this.state.storage.get('room')) ?? null;
    return this.room;
  }

  async save() {
    this.room.touchedAt = this.now();
    await this.state.storage.put('room', this.room);
    await this.schedule();
  }

  async fetch(request) {
    const room = await this.load();
    const url = new URL(request.url);
    if (request.headers.get('Upgrade') === 'websocket') {
      if (!room) return new Response('unknown room', { status: 404 });
      if (this.sockets().length >= MAX_SOCKETS) return new Response('room is full', { status: 429 });
      const [client, server] = Object.values(new WebSocketPair());
      this.connect(server);
      return new Response(null, { status: 101, webSocket: client });
    }
    if (url.pathname === '/create' && request.method === 'POST') {
      return new Response(null, { status: (await this.create(await request.text())) ? 201 : 409 });
    }
    if (url.pathname === '/info') return room ? Response.json(this.info()) : new Response(null, { status: 404 });
    return new Response(null, { status: 404 });
  }

  // Claims this room for a new code, unless someone is using it.
  async create(code) {
    const room = await this.load();
    const now = this.now();
    if (room && now - room.touchedAt < EXPIRE_MS) return false;
    this.room = { code, createdAt: now, touchedAt: now, phase: 'lobby', length: 'standard', players: [], game: null, pausedAt: 0 };
    await this.save();
    return true;
  }

  info() {
    const { code, phase, players } = this.room;
    return { code, phase, players: players.length, full: players.filter((p) => !p.bot).length >= WAR.MAX_PLAYERS };
  }

  connect(ws) {
    this.state.acceptWebSocket(ws);
    ws.serializeAttachment({ token: null });
  }

  // Connected sockets. One whose close is being handled can still be listed.
  sockets() {
    return this.state.getWebSockets().filter((ws) => !this.gone.has(ws) && !(ws.readyState >= CLOSING));
  }

  tokenOf(ws) {
    return ws.deserializeAttachment()?.token ?? null;
  }

  seatOf(ws) {
    const token = this.tokenOf(ws);
    const seat = token ? this.room.players.findIndex((p) => p.token === token) : -1;
    return seat < 0 ? null : seat;
  }

  onlineSeats() {
    return new Set(this.sockets().map((ws) => this.seatOf(ws)).filter((seat) => seat !== null));
  }

  // The first player still here runs the room: picks the length, adds bots,
  // starts. With no players here, any spectator can.
  hostSeat() {
    const online = this.onlineSeats();
    const seat = this.room.players.findIndex((p, i) => !p.bot && online.has(i));
    return seat < 0 ? null : seat;
  }

  isHost(ws) {
    const host = this.hostSeat();
    return host === null ? Boolean(this.tokenOf(ws)) : this.seatOf(ws) === host;
  }

  send(ws, message) {
    try { ws.send(JSON.stringify(message)); } catch { /* it's going away */ }
  }

  broadcast(message) {
    const text = JSON.stringify(message);
    for (const ws of this.sockets()) {
      try { ws.send(text); } catch { /* it's going away */ }
    }
  }

  snapshot(ws, now) {
    const room = this.room;
    const online = this.onlineSeats();
    const game = room.game;
    return {
      t: 'state', code: room.code, phase: room.phase, length: room.length, you: this.seatOf(ws),
      host: this.hostSeat(), watchers: this.sockets().filter((s) => this.seatOf(s) === null).length,
      players: room.players.map((p, seat) => ({ name: p.name, avatar: p.avatar, bot: p.bot, online: p.bot || online.has(seat) })),
      game: game && {
        battle: game.battle, limit: game.limit, stage: game.stage, fighters: game.fighters,
        counts: game.piles.map((pile) => pile.length), out: game.out, pot: game.pot.length,
        slams: Object.fromEntries(Object.entries(game.slams).map(([seat, [power, style]]) => [seat, [power, style]])),
        opensIn: Math.max(0, game.opensAt - now), closesIn: Math.max(0, game.closesAt - now),
        wars: game.wars, over: game.over,
      },
    };
  }

  sendStates() {
    const now = this.now();
    for (const ws of this.sockets()) this.send(ws, this.snapshot(ws, now));
  }

  onlineMessage() {
    const online = this.onlineSeats();
    return {
      t: 'online', host: this.hostSeat(), online: [...online].sort((a, b) => a - b),
      watchers: this.sockets().filter((ws) => this.seatOf(ws) === null).length,
    };
  }

  async webSocketMessage(ws, data) {
    if (typeof data !== 'string' || data.length > MAX_MESSAGE) return;
    let message;
    try { message = JSON.parse(data); } catch { return; }
    if (!message || typeof message !== 'object') return;
    const room = await this.load();
    if (!room) { try { ws.close(4004, 'unknown room'); } catch { /* already closed */ } return; }
    const seat = this.seatOf(ws);
    const host = this.isHost(ws);
    const setup = room.phase !== 'playing';
    switch (message.t) {
      case 'hello': return this.hello(ws, message);
      case 'leave': return this.leave(ws);
      case 'length':
        if (!host || !setup || !Object.hasOwn(WAR.LENGTHS, message.length)) return;
        room.length = message.length;
        await this.save();
        return this.sendStates();
      case 'bots':
        if (!host || !setup || !Number.isInteger(message.n)) return;
        return this.setBots(message.n);
      case 'start':
        if (!host || !setup) return;
        return this.start();
      case 'charge':
        if (room.phase !== 'playing' || seat === null || !Number.isInteger(message.tier)) return;
        if (!room.game.fighters.includes(seat) || room.game.slams[seat]) return;
        return this.broadcast({ t: 'charge', seat, tier: Math.max(0, Math.min(WAR.TIERS - 1, message.tier)) });
      case 'card':
        // In a war, each card laid face down is slammed on its own, for show;
        // the last card is the slam that counts.
        if (room.phase !== 'playing' || seat === null || !room.game.stage || !Number.isInteger(message.n)) return;
        if (message.n < 0 || message.n > 2 || !room.game.fighters.includes(seat) || room.game.slams[seat]) return;
        return this.broadcast({
          t: 'card', seat, n: message.n,
          power: Math.max(0, Math.min(WAR.MAX_POWER, Math.round(Number(message.power)) || 0)),
        });
      case 'slam': {
        if (room.phase !== 'playing' || seat === null) return;
        const slam = warSlam(room.game, seat, message.power, message.style);
        if (!slam) return;
        this.broadcast(slam);
        return this.tick();
      }
      case 'cheer': {
        const now = this.now();
        if (!Number.isInteger(message.e) || message.e < 0 || message.e >= CHEERS) return;
        if (now - (this.cheered.get(ws) || 0) < CHEER_GAP_MS) return;
        this.cheered.set(ws, now);
        return this.broadcast({ t: 'cheer', seat, e: message.e });
      }
      default:
    }
  }

  // Joins the room, or rejoins it with the same token. Once a game has
  // started, newcomers watch, and are dealt in when the next one starts.
  async hello(ws, message) {
    const room = this.room;
    const name = cleanName(message.name);
    const avatar = Number.isInteger(message.avatar) && message.avatar >= 0 && message.avatar < WAR.AVATARS ? message.avatar : 0;
    if (!name) return this.send(ws, { t: 'error', error: 'Pick a name of up to 16 letters or numbers.' });
    if (typeof message.token !== 'string' || !TOKEN.test(message.token)) return this.send(ws, { t: 'error', error: 'Bad token.' });
    let player = room.players.find((p) => p.token === message.token);
    if (player && room.phase !== 'playing') Object.assign(player, { name, avatar });
    if (!player && room.phase === 'lobby') {
      // People take the place of bots once the room is full.
      const bot = room.players.findLastIndex((p) => p.bot);
      if (room.players.length >= WAR.MAX_PLAYERS && bot >= 0) room.players.splice(bot, 1);
      if (room.players.length < WAR.MAX_PLAYERS) {
        player = { name, avatar, bot: false, token: message.token };
        room.players.push(player);
      }
    }
    // Spectators carry their name, for the next game.
    ws.serializeAttachment(player ? { token: message.token } : { token: message.token, name, avatar });
    if (room.pausedAt) {
      const paused = this.now() - room.pausedAt;
      if (room.game) { room.game.opensAt += paused; room.game.closesAt += paused; }
      room.pausedAt = 0;
    }
    await this.save();
    if (room.phase === 'playing') {
      this.send(ws, this.snapshot(ws, this.now()));
      this.broadcast(this.onlineMessage());
      return this.tick();
    }
    return this.sendStates();
  }

  async leave(ws) {
    const room = this.room;
    const seat = this.seatOf(ws);
    ws.serializeAttachment({ token: null });
    if (seat !== null && room.phase === 'lobby') {
      room.players.splice(seat, 1);
      await this.save();
    }
    try { ws.close(1000, 'left'); } catch { /* already closed */ }
    return this.closed(ws);
  }

  async setBots(n) {
    const room = this.room;
    const humans = room.players.filter((p) => !p.bot);
    const bots = room.players.filter((p) => p.bot);
    const want = Math.max(0, Math.min(WAR.MAX_PLAYERS - humans.length, n));
    if (want < bots.length) bots.length = want;
    const names = warBotNames(want - bots.length, this.random, room.players.map((p) => p.name));
    for (const name of names) bots.push({ name, avatar: Math.floor(this.random() * WAR.AVATARS), bot: true, token: null });
    room.players = [...humans, ...bots];
    await this.save();
    this.sendStates();
  }

  // Deals a new game to everyone here, spectators included, and the bots.
  async start() {
    const room = this.room;
    const now = this.now();
    const sockets = this.sockets();
    const here = new Set(sockets.map((ws) => this.tokenOf(ws)).filter(Boolean));
    const humans = room.players.filter((p) => !p.bot && here.has(p.token));
    for (const ws of sockets) {
      const a = ws.deserializeAttachment();
      if (a?.token && a.name && !humans.some((p) => p.token === a.token)) {
        humans.push({ name: a.name, avatar: a.avatar, bot: false, token: a.token });
        ws.serializeAttachment({ token: a.token });
      }
    }
    const players = [...humans, ...room.players.filter((p) => p.bot)].slice(0, WAR.MAX_PLAYERS);
    if (players.length < 2) {
      return this.broadcast({ t: 'error', error: 'You need at least two players. Add some bots!' });
    }
    room.players = players;
    const { game, stage } = warNewGame(players.map((p) => p.bot), room.length, this.random, now);
    room.game = game;
    room.phase = 'playing';
    await this.save();
    this.sendStates();
    this.broadcast(stage);
  }

  // Plays the stage out if it's due, then sets the alarm for whatever's next.
  async tick() {
    const room = this.room;
    const now = this.now();
    if (room.phase === 'playing' && !room.pausedAt && now >= warDueAt(room.game, this.onlineSeats())) {
      const flip = warResolve(room.game, now, this.random);
      if (flip.over) room.phase = 'over';
      this.broadcast(flip);
      return this.save();
    }
    return this.schedule();
  }

  async schedule() {
    const room = this.room;
    const at = room.phase === 'playing' && !room.pausedAt
      ? warDueAt(room.game, this.onlineSeats())
      : room.touchedAt + EXPIRE_MS;
    if (at === this.alarmAt) return;
    this.alarmAt = at;
    await this.state.storage.setAlarm(at);
  }

  async alarm() {
    this.alarmAt = null;
    const room = await this.load();
    if (!room) return;
    if (!this.sockets().length && this.now() >= room.touchedAt + EXPIRE_MS) {
      await this.state.storage.deleteAll();
      this.room = null;
      return;
    }
    if (room.phase === 'playing' && !room.pausedAt && !this.sockets().length) {
      room.pausedAt = this.now();
      return this.save();
    }
    return this.tick();
  }

  async webSocketClose(ws) {
    try { ws.close(1000, 'bye'); } catch { /* already closed */ }
    return this.closed(ws);
  }

  async webSocketError(ws) {
    return this.closed(ws);
  }

  // Someone's connection ended. A game in progress carries on without them
  // (their cards flop over on their own) unless nobody is left to watch.
  async closed(ws) {
    if (this.gone.has(ws)) return;
    this.gone.add(ws);
    const room = await this.load();
    if (!room) return;
    if (room.phase !== 'playing') return this.sendStates();
    if (!this.sockets().length) {
      room.pausedAt = this.now();
      return this.save();
    }
    this.broadcast(this.onlineMessage());
    return this.tick();
  }
}

// Routes /v1/war/ requests, from src/index.js.
export async function handleWar(request, env, now = Date.now()) {
  const url = new URL(request.url);
  const cors = corsHeaders(request, env);
  const allowedOrigin = Boolean(cors['Access-Control-Allow-Origin']);
  const roomPath = url.pathname.match(/^\/v1\/war\/rooms\/([^/]+)$/);
  try {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (url.pathname === '/v1/war/rooms' && request.method === 'POST') {
      if (!allowedOrigin) throw new HttpError(403, 'origin not allowed');
      await rateLimit(env.DB, 'room', await hashIp(request, env.IP_SALT), now);
      for (let attempt = 0; attempt < 8; attempt++) {
        const code = newCode();
        const created = await roomStub(env, code).fetch('https://war-room/create', { method: 'POST', body: code });
        if (created.status === 201) return json({ code }, 201, cors);
      }
      throw new HttpError(503, 'could not pick a free room code, try again');
    }
    if (roomPath && request.method === 'GET') {
      const code = roomPath[1];
      if (!CODE.test(code)) throw new HttpError(404, 'unknown room');
      if (request.headers.get('Upgrade') === 'websocket') {
        if (!allowedOrigin) throw new HttpError(403, 'origin not allowed');
        return roomStub(env, code).fetch(request);
      }
      const info = await roomStub(env, code).fetch('https://war-room/info');
      if (info.status !== 200) throw new HttpError(404, 'unknown room');
      return json(await info.json(), 200, cors);
    }
    return json({ error: 'not found' }, 404, cors);
  } catch (error) {
    if (error instanceof HttpError) return json({ error: error.message }, error.status, cors);
    throw error;
  }
}
