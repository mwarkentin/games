// War rooms: multiplayer games of War for war.html. Each room is a Durable
// Object holding the game, with every player connected over a WebSocket.
// src/index.js exports the WarRoom class and sends /v1/war/ requests here;
// tests import this module directly.
//
//   POST /v1/war/rooms           start a room, returns its four-character code
//   GET  /v1/war/rooms/<code>    look a room up, or, as a WebSocket, join it
//
// The room deals, waits for slams and plays every battle; the pages only show
// what it tells them. Solo games run the same rules in the page: both import
// them from js/war/core.js.

import {
  WAR, warBotNames, warDeal, warDueAt, warFlop, warGather, warHeld, warNewGame, warShort, warOpenStage, warRank, warResolve,
  warShuffle, warSlam, warStandings, warUpCard, warWaitingFor,
} from '../../js/war/core.js';
import { nameIsKind } from '../../js/war/names.js';
import { CODE, CODE_ALPHABET, HttpError, corsHeaders, hashIp, json, rateLimit } from './leaderboard.js';

export {
  WAR, warBotNames, warDeal, warDueAt, warFlop, warGather, warHeld, warNewGame, warShort, warOpenStage, warRank, warResolve,
  warShuffle, warSlam, warStandings, warUpCard, warWaitingFor,
};

const HOUR = 60 * 60 * 1000;
export const EXPIRE_MS = 6 * HOUR;  // a room nobody has used for this long is deleted
export const MAX_SOCKETS = 60;       // players and spectators
const MAX_MESSAGE = 1024;
const CHEERS = 6;
const CHEER_GAP_MS = 400;
const DECK_GAP_MS = 1000;
const TIDY_GAP_MS = 1000;
const NUDGE_GAP_MS = 3000;
// Messages that save the room and send everyone its state (hello, and the
// host's settings): a few at once, then this many a second, per socket.
const PACE_BURST = 5;
const PACE_PER_S = 5;
const NAME = /^[\p{L}\p{N}][\p{L}\p{N} '&.,!?-]{0,15}$/u;
const TOKEN = /^[A-Za-z0-9-]{16,64}$/;
// The deck a player's cards are drawn in, one of war.html's DECKS. Rooms only
// check that it looks like one, so a new deck needs no change here; pages draw
// a deck they don't know as the classic one.
const DECK = /^[a-z0-9]{1,16}$/;
const CLOSING = 2;

// The states a room can be in, and the moves it may make from each (see
// "State machines" in AGENTS.md). The stored room keeps the shape it always
// had, so rooms saved before this still load: `phase` is 'lobby', 'playing'
// or 'over', and a game playing with nobody connected is paused, marked by
// `pausedAt`. WarRoom.roomState() reads which state that is, and
// WarRoom.go() makes every move.
//
//   absent   no room: never made, or deleted once nobody had used it for EXPIRE_MS
//   lobby    players gather, and the host picks the length and the bots
//   playing  a game is on, with someone connected
//   paused   a game is on and nobody is connected: it waits for someone to come back
//   over     the game has ended, and the host can deal the next one
export const ROOM_MOVES = {
  absent: ['lobby'],
  lobby: ['playing', 'absent'],
  playing: ['paused', 'over', 'absent'],
  paused: ['playing', 'absent'],
  over: ['playing', 'absent'],
};

// The messages a room takes in each state. 'open' is playing once the stage
// has opened: a slam (or a charge, or a face-down card) that arrives before
// then was meant for the stage just played out, and mustn't count toward the
// next one. What else a message needs (the host, a seat, a card still to
// slam) is checked where it's handled.
const ANY = ['lobby', 'playing', 'paused', 'over'];
export const ROOM_MESSAGES = {
  hello: ANY,
  leave: ANY,
  cheer: ANY,
  deck: ANY,
  length: ['lobby'],
  bots: ['lobby'],
  slow: ['lobby'],
  shuffle: ['lobby'],
  start: ['lobby', 'over'],
  charge: ['open'],
  card: ['open'],
  slam: ['open'],
  gather: ['playing', 'paused'],
  nudge: ['playing', 'paused'],
  flop: ['playing', 'paused'],
  tidy: ['playing', 'paused', 'over'],
};

const roomStub = (env, code) => env.WAR_ROOMS.get(env.WAR_ROOMS.idFromName(code));

function newCode() {
  return [...crypto.getRandomValues(new Uint8Array(4))].map((b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');
}

export function cleanName(value) {
  const name = typeof value === 'string' ? value.trim().replace(/\s+/g, ' ') : '';
  return NAME.test(name) ? name : null;
}

export function cleanDeck(value) {
  return typeof value === 'string' && DECK.test(value) ? value : null;
}

// One room. Its state is a single storage value, saved when something
// changes for good (a player joins, a stage is played out). In a timed game,
// slams in the current stage aren't saved one by one: each is kept on the
// socket that made it too, since sockets' attachments survive hibernation,
// and a woken room takes back the ones it can (see recallSlams). A slow game
// has no clock to flop a forgotten card, so it saves every slam. The alarm
// closes each stage and, once a room is idle, deletes it. While nobody is
// connected, a game in progress waits for someone to come back.
//
// A slow game waits for everyone connected, so one sleepy player can't stall
// it for good: players who've left aren't waited for, everyone sees who is,
// anyone can nudge them after WAR.NUDGE_MS, and after WAR.FLOP_MS the host
// can flip their cards over for them.
export class WarRoom {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.room = undefined;
    this.alarmAt = null;
    this.gone = new WeakSet();
    this.cheered = new WeakMap();
    this.decked = new WeakMap();
    this.tidied = new WeakMap();
    this.nudged = new WeakMap();
    this.paces = new WeakMap();
    this.now = () => Date.now();
    this.random = Math.random;
  }

  async load() {
    if (this.room === undefined) {
      this.room = (await this.state.storage.get('room')) ?? null;
      // A game saved before winnings were kept apart has them all in its decks.
      const game = this.room?.game;
      if (game && !game.loot) {
        game.loot = game.piles.map(() => []);
        game.potBy = game.pot.map(() => -1);
      }
      this.recallSlams();
    }
    return this.room;
  }

  // Which of ROOM_MOVES' states the room is in, read from what's stored.
  roomState() {
    const room = this.room;
    if (!room) return 'absent';
    if (room.phase === 'playing') return room.pausedAt ? 'paused' : 'playing';
    return room.phase;
  }

  is(...states) {
    return states.includes(this.roomState());
  }

  // Makes one of the moves in ROOM_MOVES, and nothing else: every change of
  // state goes through here. Any other move is a bug, refused with an error in
  // the log. The caller saves.
  //   go('lobby', code)            a new room
  //   go('playing', players, game) a new game, from the lobby or after one
  //   go('playing')                someone is back: the paused stage picks up where it was
  //   go('paused'), go('over'), go('absent')
  go(to, ...args) {
    const from = this.roomState();
    if (!ROOM_MOVES[from]?.includes(to)) {
      console.error({ war: 'no such move', from, to });
      return false;
    }
    const now = this.now();
    if (to === 'absent') {
      this.room = null;
    } else if (to === 'lobby') {
      this.room = {
        code: args[0], createdAt: now, touchedAt: now, phase: 'lobby', length: 'standard', slow: false, shuffle: false,
        players: [], game: null, pausedAt: 0,
      };
    } else if (to === 'paused') {
      this.room.pausedAt = now;
    } else if (to === 'over') {
      this.room.phase = 'over';
    } else if (from === 'paused') {
      const paused = now - this.room.pausedAt;
      if (this.room.game) { this.room.game.opensAt += paused; this.room.game.closesAt += paused; }
      this.room.pausedAt = 0;
    } else {
      const [players, game] = args;
      Object.assign(this.room, { players, game, phase: 'playing' });
    }
    return true;
  }

  // Whether the room takes a message of this type in the state it's in (ROOM_MESSAGES).
  takes(type) {
    const states = typeof type === 'string' && Object.hasOwn(ROOM_MESSAGES, type) ? ROOM_MESSAGES[type] : [];
    const state = this.roomState();
    return states.includes(state) || (state === 'playing' && states.includes('open') && this.now() >= this.room.game.opensAt);
  }

  // When the alarm should go off: the stage's deadline while a game is
  // playing; otherwise the idle check, EXPIRE_MS after the room was last used.
  // A slow game's stage has no deadline while it waits for someone, and
  // neither has a room between games: then it's the idle check, never in the
  // past, so with people still connected it looks again in an hour.
  deadline() {
    const due = this.is('playing') ? warDueAt(this.room.game, this.onlineSeats()) : Infinity;
    return Number.isFinite(due) ? due : Math.max(this.room.touchedAt + EXPIRE_MS, this.now() + HOUR);
  }

  // A slam is kept on the socket that made it, as well as in the game, so a
  // room woken from hibernation still has it: the game is saved once a stage,
  // not once a slam, but attachments survive. The stage is named by when it
  // opened, which no other stage, in this game or another, shares (a pause
  // moves it, but nobody is connected through one).
  keepSlam(ws, slam) {
    ws.serializeAttachment({ ...ws.deserializeAttachment(), slam: [this.room.game.opensAt, slam.power, slam.style] });
  }

  recallSlams() {
    const game = this.room?.game;
    if (!game || game.over) return;
    for (const ws of this.state.getWebSockets()) {
      const a = ws.deserializeAttachment();
      if (!a?.token || !Array.isArray(a.slam) || a.slam[0] !== game.opensAt) continue;
      const seat = this.room.players.findIndex((p) => p.token === a.token);
      // A slam from a deck that couldn't cover the stage picked up its
      // winnings first, shuffled maybe, which the saved game doesn't have:
      // that one can't be taken back exactly, so it flops when time runs out.
      if (seat >= 0 && game.fighters.includes(seat) && !game.slams[seat] && !warShort(game, seat)) {
        game.slams[seat] = [a.slam[1], a.slam[2], 0];
        game.naps[seat] = 0;
      }
    }
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

  // Claims this room for a new code, unless someone is using it: it was used
  // in the last EXPIRE_MS, or someone is still connected to it.
  async create(code) {
    const room = await this.load();
    if (room && (this.now() - room.touchedAt < EXPIRE_MS || this.sockets().length)) return false;
    if (room) this.go('absent');
    this.go('lobby', code);
    await this.save();
    return true;
  }

  // The stored phase, as pages have always read it: a paused game is 'playing'.
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
      t: 'state', code: room.code, phase: room.phase, length: room.length, slow: Boolean(room.slow),
      shuffle: Boolean(room.shuffle), you: this.seatOf(ws),
      host: this.hostSeat(), watchers: this.sockets().filter((s) => this.seatOf(s) === null).length,
      players: room.players.map((p, seat) => ({
        name: p.name, avatar: p.avatar, deck: p.deck ?? null, bot: p.bot, online: p.bot || online.has(seat),
      })),
      game: game && {
        battle: game.battle, limit: game.limit, stage: game.stage, fighters: game.fighters,
        counts: game.piles.map((_, seat) => warHeld(game, seat)), decks: game.piles.map((pile) => pile.length),
        loot: game.loot, shuffle: Boolean(game.shuffle), out: game.out, pot: game.pot.length,
        slams: Object.fromEntries(Object.entries(game.slams).map(([seat, [power, style]]) => [seat, [power, style]])),
        // The cards those slams turned face up.
        ups: game.over ? {} : Object.fromEntries(Object.keys(game.slams).map((seat) => [seat, warUpCard(game, Number(seat))])),
        opensIn: Math.max(0, game.opensAt - now), closesIn: game.slow ? null : Math.max(0, game.closesAt - now),
        naps: game.naps, slow: Boolean(game.slow), wars: game.wars, over: game.over,
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

  // Whether ws may send another message that saves the room (PACE_BURST).
  paced(ws) {
    const now = this.now(), [left, at] = this.paces.get(ws) ?? [PACE_BURST, now];
    const have = Math.min(PACE_BURST, left + ((now - at) * PACE_PER_S) / 1000);
    if (have < 1) return false;
    this.paces.set(ws, [have - 1, now]);
    return true;
  }

  async webSocketMessage(ws, data) {
    if (typeof data !== 'string' || data.length > MAX_MESSAGE) return;
    let message;
    try { message = JSON.parse(data); } catch { return; }
    if (!message || typeof message !== 'object') return;
    const room = await this.load();
    if (!room) { try { ws.close(4004, 'unknown room'); } catch { /* already closed */ } return; }
    if (!this.takes(message.t)) return;
    const seat = this.seatOf(ws);
    const host = this.isHost(ws);
    switch (message.t) {
      case 'hello': return this.paced(ws) ? this.hello(ws, message) : undefined;
      case 'leave': return this.leave(ws);
      case 'length':
        if (!host || !Object.hasOwn(WAR.LENGTHS, message.length) || !this.paced(ws)) return;
        room.length = message.length;
        await this.save();
        return this.sendStates();
      case 'slow':
        if (!host || typeof message.slow !== 'boolean' || !this.paced(ws)) return;
        room.slow = message.slow;
        await this.save();
        return this.sendStates();
      case 'shuffle':
        if (!host || typeof message.shuffle !== 'boolean' || !this.paced(ws)) return;
        room.shuffle = message.shuffle;
        await this.save();
        return this.sendStates();
      case 'gather':
        // A player puts their winnings under their deck. It changes no card
        // to come, so it can happen any time, even mid-stage.
        if (room.phase !== 'playing' || seat === null || !warGather(room.game, seat, this.random)) return;
        this.broadcast({ t: 'gather', seat });
        return this.save();
      case 'bots':
        if (!host || !Number.isInteger(message.n) || !this.paced(ws)) return;
        return this.setBots(message.n);
      case 'start':
        if (!host) return;
        return this.start();
      case 'charge':
        if (seat === null || !Number.isInteger(message.tier)) return;
        if (!room.game.fighters.includes(seat) || room.game.slams[seat]) return;
        return this.broadcast({ t: 'charge', seat, tier: Math.max(0, Math.min(WAR.TIERS - 1, message.tier)) });
      case 'card':
        // In a war, each card laid face down is slammed on its own, for show;
        // the last card is the slam that counts.
        if (seat === null || !room.game.stage || !Number.isInteger(message.n)) return;
        if (message.n < 0 || message.n > 2 || !room.game.fighters.includes(seat) || room.game.slams[seat]) return;
        return this.broadcast({
          t: 'card', seat, n: message.n,
          power: Math.max(0, Math.min(WAR.MAX_POWER, Math.round(Number(message.power)) || 0)),
        });
      case 'slam': {
        if (seat === null) return;
        const slam = warSlam(room.game, seat, message.power, message.style, this.random);
        if (!slam) return;
        this.keepSlam(ws, slam);
        this.broadcast(slam);
        if (room.game.slow) await this.save();
        return this.tick();
      }
      case 'nudge': {
        // In a slow game, anyone can give the players the table is waiting
        // for a nudge: their deck shakes and makes a noise, on their screen.
        const now = this.now();
        if (room.phase !== 'playing' || !room.game.slow || now < room.game.opensAt + WAR.NUDGE_MS) return;
        if (now - (this.nudged.get(ws) || 0) < NUDGE_GAP_MS) return;
        const seats = warWaitingFor(room.game, this.onlineSeats()).filter((s) => s !== seat);
        if (!seats.length) return;
        this.nudged.set(ws, now);
        return this.broadcast({ t: 'nudge', seats, by: seat });
      }
      case 'flop': {
        // After a long wait, the host flips over the cards of everyone the
        // table is still waiting for, as if they'd flopped.
        if (room.phase !== 'playing' || !host || !room.game.slow || this.now() < room.game.opensAt + WAR.FLOP_MS) return;
        const seats = warWaitingFor(room.game, this.onlineSeats()).filter((s) => s !== seat);
        if (!seats.length) return;
        for (const s of seats) this.broadcast(warFlop(room.game, s, this.random));
        await this.save();
        return this.tick();
      }
      case 'cheer': {
        const now = this.now();
        if (!Number.isInteger(message.e) || message.e < 0 || message.e >= CHEERS) return;
        if (now - (this.cheered.get(ws) || 0) < CHEER_GAP_MS) return;
        this.cheered.set(ws, now);
        return this.broadcast({ t: 'cheer', seat, e: message.e });
      }
      case 'deck': {
        const now = this.now();
        if (now - (this.decked.get(ws) || 0) < DECK_GAP_MS) return;
        this.decked.set(ws, now);
        return this.setDeck(ws, seat, cleanDeck(message.deck));
      }
      case 'tidy': {
        // A player cleaned up the cards they've won, for show: everyone sees
        // that player's heap squared into a neat stack.
        const now = this.now();
        if (seat === null || now - (this.tidied.get(ws) || 0) < TIDY_GAP_MS) return;
        this.tidied.set(ws, now);
        return this.broadcast({ t: 'tidy', seat });
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
    const deck = cleanDeck(message.deck);
    if (!name) return this.send(ws, { t: 'error', error: 'Pick a name of up to 16 letters or numbers.' });
    if (!nameIsKind(name)) return this.send(ws, { t: 'error', error: 'Pick a different name, please.' });
    if (typeof message.token !== 'string' || !TOKEN.test(message.token)) return this.send(ws, { t: 'error', error: 'Bad token.' });
    // One socket is one person: it can't take a second seat with another token.
    const was = ws.deserializeAttachment()?.token;
    if (was && was !== message.token) return this.send(ws, { t: 'error', error: 'Bad token.' });
    let player = room.players.find((p) => p.token === message.token);
    if (player && this.is('lobby', 'over')) Object.assign(player, { name, avatar });
    if (player) player.deck = deck;  // only for show, so it can change mid-game
    if (!player && this.is('lobby')) {
      // People take the place of bots once the room is full.
      const bot = room.players.findLastIndex((p) => p.bot);
      if (room.players.length >= WAR.MAX_PLAYERS && bot >= 0) room.players.splice(bot, 1);
      if (room.players.length < WAR.MAX_PLAYERS) {
        player = { name, avatar, deck, bot: false, token: message.token };
        room.players.push(player);
      }
    }
    // Spectators carry their name, for the next game.
    ws.serializeAttachment(player ? { token: message.token } : { token: message.token, name, avatar, deck });
    // Back at a slow table, you're waited for again, even if your cards
    // flopped over while you were gone.
    const seat = player ? room.players.indexOf(player) : -1;
    if (seat >= 0 && this.is('playing', 'paused') && room.game.slow) room.game.naps[seat] = 0;
    if (this.is('paused')) this.go('playing');
    await this.save();
    if (this.is('playing')) {
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
    if (seat !== null && this.is('lobby')) {
      room.players.splice(seat, 1);
      await this.save();
    }
    try { ws.close(1000, 'left'); } catch { /* already closed */ }
    return this.closed(ws);
  }

  // A player picked another deck: everyone sees their cards in it from now
  // on. A spectator's is kept for the next game.
  async setDeck(ws, seat, deck) {
    if (!deck) return;
    if (seat === null) {
      const a = ws.deserializeAttachment();
      if (a?.name) ws.serializeAttachment({ ...a, deck });
      return;
    }
    const player = this.room.players[seat];
    if (player.deck === deck) return;
    player.deck = deck;
    await this.save();
    this.broadcast({ t: 'deck', seat, deck });
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
        humans.push({ name: a.name, avatar: a.avatar, deck: a.deck ?? null, bot: false, token: a.token });
        ws.serializeAttachment({ token: a.token });
      }
    }
    const players = [...humans, ...room.players.filter((p) => p.bot)].slice(0, WAR.MAX_PLAYERS);
    if (players.length < 2) {
      return this.broadcast({ t: 'error', error: 'You need at least two players. Add some bots!' });
    }
    const { game, stage } = warNewGame(players.map((p) => p.bot), room.length, this.random, now, {
      slow: room.slow, shuffle: room.shuffle,
    });
    this.go('playing', players, game);
    await this.save();
    this.sendStates();
    this.broadcast(stage);
  }

  // Plays the stage out if it's due, then sets the alarm for whatever's next.
  async tick() {
    const now = this.now();
    if (this.is('playing') && now >= this.deadline()) {
      const flip = warResolve(this.room.game, now, this.random);
      if (flip.over) this.go('over');
      this.broadcast(flip);
      return this.save();
    }
    return this.schedule();
  }

  // The alarm goes off when the stage is due, or else (in the lobby, after a
  // game, while paused, or while a slow stage waits for someone) when the room
  // has been idle long enough to delete. If people are still connected then,
  // it looks again in an hour.
  async schedule() {
    const at = this.deadline();
    if (at === this.alarmAt) return;
    this.alarmAt = at;
    await this.state.storage.setAlarm(at);
  }

  async alarm() {
    this.alarmAt = null;
    const room = await this.load();
    if (!room) return;
    const here = this.sockets().length > 0;
    if (this.now() >= room.touchedAt + EXPIRE_MS) {
      // Nobody has used the room for EXPIRE_MS: it's deleted, unless someone
      // is still connected, which counts as using it. (Setting the alarm for
      // that same moment again would set off a new alarm straight away, for
      // as long as they stayed.)
      if (!here) {
        await this.state.storage.deleteAll();
        this.go('absent');
        return;
      }
      if (!this.is('playing')) return this.save();
    }
    if (!here && this.is('playing')) {
      this.go('paused');
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
    if (this.is('lobby', 'over')) return this.sendStates();
    if (!this.sockets().length) {
      // A pause starts once: a page that connects to a paused room and
      // leaves again without joining mustn't shorten the stage it left.
      if (this.is('playing')) this.go('paused');
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
