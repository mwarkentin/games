// Tests for War rooms (src/war.js), run with:
//   node --disable-warning=ExperimentalWarning --test "worker/test/*.test.js"
// The rules run as they are. Rooms run against stand-ins for a Durable
// Object's state and its WebSockets; HTTP routes against a stand-in D1 and a
// namespace of those rooms.

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { beforeEach, describe, test } from 'node:test';

import {
  EXPIRE_MS, MAX_SOCKETS, WAR, WarRoom, cleanDeck, cleanName, handleWar, warDeal, warDueAt, warNewGame, warRank, warResolve,
  warFlop, warSlam, warStandings, warUpCard,
} from '../src/war.js';

const ORIGIN = 'https://games.michaelwarkentin.com';
const NOW = Date.UTC(2026, 10, 3, 12);

// A seeded random number generator (mulberry32), so games repeat exactly.
function seeded(seed) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// A card of the given rank (0 is a two, 12 an ace) from the given deck and suit.
const card = (rank, suit = 0, deck = 0) => deck * WAR.DECK + suit * 13 + rank;
// One of a deck's two jokers.
const joker = (which = 0, deck = 0) => deck * WAR.DECK + 52 + which;

// A game with chosen piles, top card first, in its first battle.
function rigged(piles, { bots, limit = 60 } = {}) {
  const { game } = warNewGame(piles.map((_, i) => bots?.[i] ?? false), 'standard', seeded(1), NOW);
  game.piles = piles.map((p) => p.slice());
  game.limit = limit;
  game.fighters = piles.map((_, i) => i).filter((i) => piles[i].length);
  game.slams = {};
  return game;
}

describe('the rules', () => {
  test('there is a deck for every two players, jokers included, dealt evenly', () => {
    const sizes = (n) => warDeal(n, seeded(n)).map((p) => p.length);
    assert.equal(WAR.DECK, 54);
    assert.deepEqual(sizes(2), [27, 27]);
    assert.deepEqual(sizes(3), [36, 36, 36]);
    assert.deepEqual(new Set(sizes(50)), new Set([27]));
    const all = warDeal(50, seeded(9)).flat().sort((a, b) => a - b);
    assert.deepEqual(all, Array.from({ length: 54 * 25 }, (_, i) => i));
    assert.equal(all.filter((c) => warRank(c) === 13).length, 50, 'two jokers in each of the 25 decks');
  });

  test('cards rank two to ace in every suit and deck, and jokers above them all', () => {
    for (const deck of [0, 1, 24]) {
      for (let suit = 0; suit < 4; suit++) {
        for (let rank = 0; rank < 13; rank++) assert.equal(warRank(card(rank, suit, deck)), rank);
      }
      assert.equal(warRank(joker(0, deck)), 13);
      assert.equal(warRank(joker(1, deck)), 13);
    }
  });

  test('a joker beats an ace, and two jokers make a war', () => {
    const beaten = rigged([[card(12), card(2)], [joker(), card(3)]]);
    assert.equal(warResolve(beaten, NOW, seeded(2)).winner, 1);
    const war = rigged([[joker(0), card(2), card(3), card(4), card(5)], [joker(1, 1), card(6), card(7), card(8), card(9)]]);
    const flip = warResolve(war, NOW, seeded(2));
    assert.equal(flip.winner, null);
    assert.deepEqual(flip.next.fighters, [0, 1]);
    assert.equal(warResolve(war, NOW, seeded(2)).winner, 1, 'the war is won by the higher card, a jack over a six');
  });

  test('the highest card takes every card played', () => {
    const game = rigged([[card(5), card(2)], [card(9), card(3)], [card(7), card(4)]]);
    const flip = warResolve(game, NOW, seeded(2));
    assert.equal(flip.winner, 1);
    assert.deepEqual(flip.tied, [1]);
    assert.deepEqual(flip.counts, [1, 4, 1]);
    assert.deepEqual(game.piles[1].slice(0, 1), [card(3)]);
    assert.deepEqual(game.piles[1].slice(1).sort((a, b) => a - b), [card(5), card(7), card(9)].sort((a, b) => a - b));
    assert.equal(flip.next.battle, 2);
    assert.deepEqual(flip.next.fighters, [0, 1, 2]);
  });

  test('a tie is a war: three cards face down, the fourth decides', () => {
    const game = rigged([
      [card(10), card(2), card(3), card(4), card(12)],
      [card(10, 1), card(5), card(6), card(7), card(11)],
      [card(3), card(9)],
    ]);
    const tie = warResolve(game, NOW, seeded(3));
    assert.equal(tie.winner, null);
    assert.deepEqual(tie.tied, [0, 1]);
    assert.equal(tie.next.stage, 1);
    assert.deepEqual(tie.next.fighters, [0, 1]);
    assert.equal(tie.next.opensIn, WAR.WAR_REVEAL_MS);
    assert.equal(game.wars, 1);

    const war = warResolve(game, NOW, seeded(3));
    assert.deepEqual(war.plays.map(([seat, down, up]) => [seat, down, up]), [[0, 3, card(12)], [1, 3, card(11)]]);
    assert.equal(war.winner, 0);
    assert.deepEqual(war.counts, [11, 0, 1]);
    assert.deepEqual(war.out, [1]);
    assert.equal(game.out[1], 1);
  });

  test('a player short of cards lays down what they have', () => {
    const game = rigged([[card(8), card(2), card(1)], [card(8, 1), card(3), card(4), card(5), card(6)]]);
    warResolve(game, NOW, seeded(4));
    const war = warResolve(game, NOW, seeded(4));
    assert.deepEqual(war.plays.map(([seat, down]) => [seat, down]), [[0, 1], [1, 3]]);
    assert.equal(war.winner, 1);
    assert.ok(war.over, 'player 0 is out of cards, so the game is over');
    assert.deepEqual(war.over.winners, [1]);
  });

  test('a tie with no cards left to fight with goes to whoever has some', () => {
    const game = rigged([[card(6)], [card(6, 1), card(2)], [card(1), card(4)]]);
    const flip = warResolve(game, NOW, seeded(5));
    assert.deepEqual(flip.tied, [0, 1]);
    assert.equal(flip.winner, 1);
    assert.equal(flip.gods, false);
    assert.deepEqual(flip.out, [0]);
  });

  test('when nobody in a war has cards left, the war gods pick', () => {
    const game = rigged([[card(6)], [card(6, 1)]]);
    const flip = warResolve(game, NOW, seeded(6));
    assert.equal(flip.gods, true);
    assert.ok([0, 1].includes(flip.winner));
    assert.deepEqual(flip.over.winners, [flip.winner]);
  });

  test('at the battle limit, the most cards wins, and a tie for most is shared', () => {
    const game = rigged([[card(2), card(3), card(4)], [card(5), card(6)], [card(1), card(7), card(8)]], { limit: 1 });
    const flip = warResolve(game, NOW, seeded(7));
    assert.equal(flip.winner, 1);
    assert.deepEqual(flip.counts, [2, 4, 2]);
    assert.deepEqual(flip.over.winners, [1]);
    assert.deepEqual(flip.over.order, [1, 0, 2]);
    assert.equal(flip.next, undefined);

    const even = rigged([[card(9), card(3)], [card(2), card(4), card(5), card(6)]], { limit: 1 });
    assert.deepEqual(warResolve(even, NOW, seeded(8)).over.winners, [0, 1]);
  });

  test('players out of cards rank by how long they lasted', () => {
    const game = rigged([[], [], [card(3)]]);
    game.out = [4, 7, 0];
    assert.deepEqual(warStandings(game).order, [2, 1, 0]);
  });

  test('slams change nothing', () => {
    const play = (power) => {
      const random = seeded(42);
      let { game } = warNewGame([false, true, true, false], 'quick', random, NOW);
      const log = [];
      while (!game.over) {
        for (const seat of game.fighters) warSlam(game, seat, power(seat), 3);
        const flip = warResolve(game, NOW, random);
        log.push([flip.winner, flip.counts]);
      }
      return { log, over: game.over };
    };
    const gentle = play(() => 0);
    const mighty = play(() => WAR.MAX_POWER);
    const random = play((seat) => (seat * 37) % 201);
    assert.deepEqual(mighty, gentle);
    assert.deepEqual(random, gentle);
  });

  test('a slam counts once, only from someone fighting, and is kept in range', () => {
    const game = rigged([[card(2)], [card(3)], []]);
    assert.deepEqual(warSlam(game, 0, 999, 4), { t: 'slam', seat: 0, power: WAR.MAX_POWER, style: 4, up: card(2) });
    assert.equal(warSlam(game, 0, 50, 1), null);
    assert.equal(warSlam(game, 2, 50, 1), null);
    assert.deepEqual(warSlam(game, 1, 'lots', 99), { t: 'slam', seat: 1, power: 0, style: 0, up: card(3) });
  });

  test("a slam turns over the card the flip shows, in a battle and in a war", () => {
    const game = rigged([
      [card(9), card(1), card(2), card(3), card(12)],
      [card(9, 1), card(5), card(6)],
      [card(4), card(7)],
    ]);
    const ups = game.fighters.map((seat) => warSlam(game, seat, 50, 0).up);
    assert.deepEqual(ups, [card(9), card(9, 1), card(4)]);
    const tie = warResolve(game, NOW, seeded(1));
    assert.deepEqual(tie.plays.map((p) => p[2]), ups);

    // In the war, the card that counts comes after those laid face down:
    // three for seat 0, and the one seat 1 can spare from its two.
    assert.deepEqual([warUpCard(game, 0), warUpCard(game, 1)], [card(12), card(6)]);
    const war = [warSlam(game, 0, 80, 1).up, warSlam(game, 1, 80, 1).up];
    const flip = warResolve(game, NOW, seeded(1));
    assert.deepEqual(flip.plays.map((p) => [p[1], p[2]]), [[3, war[0]], [1, war[1]]]);
  });

  test("the bots' cards come with their slams, and match the flip", () => {
    const random = seeded(77);
    let { game, stage } = warNewGame([false, true, true, true], 'standard', random, NOW);
    for (let i = 0; i < 40 && !game.over; i++) {
      const bots = Object.fromEntries(stage.bots.map(([seat, , , , up]) => [seat, up]));
      for (const seat of game.fighters) warSlam(game, seat, 10, 0);
      const flip = warResolve(game, NOW, random);
      for (const [seat, , up] of flip.plays) if (seat in bots) assert.equal(bots[seat], up);
      stage = flip.next;
    }
  });

  test('cards nobody slammed flop over by themselves', () => {
    const game = rigged([[card(2)], [card(3)]]);
    warSlam(game, 0, 120, 2);
    const flip = warResolve(game, NOW, seeded(1));
    assert.deepEqual(flip.plays, [[0, 0, card(2), 120, 2, 0], [1, 0, card(3), 0, 0, 1]]);
  });

  test('a war gives people longer to slam, and the bots longer to show off', () => {
    const game = rigged([[card(9), card(1), card(2), card(3), card(4)], [card(9, 1), card(5), card(6), card(7), card(8)]], { bots: [false, true] });
    const war = warResolve(game, NOW, seeded(1)).next;
    assert.equal(war.closesIn - war.opensIn, WAR.WAR_STAGE_MS);
    assert.equal(warDueAt(game, new Set()), game.opensAt + WAR.WAR_BOT_MS);
    assert.ok(war.bots[0][3] > 0 && war.bots[0][3] < WAR.WAR_BOT_MS);
  });

  test('bots slam as a stage opens, and a stage waits only for people online', () => {
    const { game, stage } = warNewGame([false, true, true, false], 'standard', seeded(11), NOW);
    assert.deepEqual(stage.bots.map(([seat]) => seat), [1, 2]);
    for (const [, power, style, delay] of stage.bots) {
      assert.ok(power >= 0 && power <= WAR.MAX_POWER && style >= 0 && style < WAR.STYLES);
      assert.ok(delay > 0 && delay < WAR.BOT_MS);
    }
    assert.equal(warDueAt(game, new Set([0, 3])), game.closesAt);
    assert.equal(warDueAt(game, new Set([0])), game.closesAt);
    assert.equal(warDueAt(game, new Set()), game.opensAt + WAR.BOT_MS);
    warSlam(game, 0, 10, 0);
    assert.equal(warDueAt(game, new Set([0])), game.opensAt + WAR.BOT_MS);
    assert.equal(warDueAt(game, new Set([0, 3])), game.closesAt);
  });

  test('a slow game has no clock: a stage waits for everyone online, and the bots still play', () => {
    const { game, stage } = warNewGame([false, true, false], 'standard', seeded(12), NOW, 1, true);
    assert.equal(stage.closesIn, null);
    assert.equal(game.closesAt, Infinity);
    assert.equal(warDueAt(game, new Set([0, 2])), Infinity, 'waits for both people, however long');
    assert.deepEqual(Object.keys(game.slams), ['1'], 'the bot slams as the stage opens');
    warSlam(game, 0, 10, 0);
    assert.equal(warDueAt(game, new Set([0, 2])), Infinity);
    assert.equal(warDueAt(game, new Set([0])), game.opensAt + WAR.BOT_MS, 'not for someone who has left');
    warSlam(game, 2, 10, 0);
    assert.equal(warDueAt(game, new Set([0, 2])), game.opensAt + WAR.BOT_MS);
    const flip = warResolve(game, NOW, seeded(12));
    assert.deepEqual(flip.plays.map((p) => p[5]), [0, 0, 0], 'nobody flopped');
    assert.equal((flip.next || {}).closesIn ?? null, null, 'the next stage has no clock either');
  });

  test("a slow game's card flipped for someone counts as a flop, once", () => {
    const game = rigged([[card(2)], [card(3)]]);
    game.slow = true;
    assert.deepEqual(warFlop(game, 1), { t: 'slam', seat: 1, power: 0, style: 0, up: card(3), flopped: true });
    assert.equal(warFlop(game, 1), null);
    assert.equal(warSlam(game, 1, 50, 0), null, 'too late to slam it yourself');
    const flip = warResolve(game, NOW, seeded(1));
    assert.deepEqual(flip.plays[1].slice(2), [card(3), 0, 0, 1]);
    assert.deepEqual(game.naps, [1, 1]);
  });

  test('every game ends, however many play', () => {
    for (const players of [2, 7, 50]) {
      const random = seeded(players);
      const bots = Array.from({ length: players }, () => true);
      let { game } = warNewGame(bots, 'total', random, NOW);
      let last;
      while (!game.over) last = warResolve(game, NOW, random);
      assert.ok(last.over.battles <= WAR.LENGTHS.total);
      assert.equal(last.counts.reduce((a, b) => a + b), WAR.DECK * Math.ceil(players / 2));
    }
  });
});

test('war.html runs the same core as the Worker', () => {
  const core = (text) => {
    const match = text.match(/\/\/ ---- BEGIN WAR CORE ----\n([\s\S]*?)\/\/ ---- END WAR CORE ----/);
    assert.ok(match, 'core markers are missing');
    return match[1];
  };
  const page = readFileSync(new URL('../../war.html', import.meta.url), 'utf8');
  const worker = readFileSync(new URL('../src/war.js', import.meta.url), 'utf8');
  assert.equal(core(page), core(worker), 'the War core in war.html and worker/src/war.js must match word for word');
});

test('names are tidied and checked', () => {
  assert.equal(cleanName('  Dana   B  '), 'Dana B');
  assert.equal(cleanName('Zoë!'), 'Zoë!');
  assert.equal(cleanName('<script>'), null);
  assert.equal(cleanName('x'.repeat(17)), null);
  assert.equal(cleanName(''), null);
});

// ---- Rooms ----

class FakeSocket {
  constructor() {
    this.readyState = 1;
    this.sent = [];
    this.attachment = null;
  }
  send(text) {
    if (this.readyState !== 1) throw new Error('closed');
    this.sent.push(JSON.parse(text));
  }
  close() { this.readyState = 3; }
  serializeAttachment(value) { this.attachment = structuredClone(value); }
  deserializeAttachment() { return structuredClone(this.attachment); }
  last(t) { return this.sent.filter((m) => m.t === t).at(-1); }
  all(t) { return this.sent.filter((m) => m.t === t); }
}

function fakeState() {
  const data = new Map();
  const sockets = [];
  const state = {
    alarm: null,
    writes: 0,
    storage: {
      get: async (key) => structuredClone(data.get(key)),
      put: async (key, value) => { state.writes++; data.set(key, structuredClone(value)); },
      deleteAll: async () => data.clear(),
      setAlarm: async (at) => { state.alarm = at; },
    },
    data,
    acceptWebSocket: (ws) => sockets.push(ws),
    getWebSockets: () => sockets.filter((ws) => ws.readyState !== 3),
  };
  return state;
}

function newRoom(state = fakeState()) {
  const room = new WarRoom(state, {});
  room.clock = NOW;
  room.now = () => room.clock;
  room.random = seeded(1234);
  return room;
}

const token = (name) => `token-${name}-0123456789`;

async function join(room, name, avatar = 1, deck = undefined) {
  const ws = new FakeSocket();
  room.connect(ws);
  await room.webSocketMessage(ws, JSON.stringify({ t: 'hello', name, avatar, token: token(name), deck }));
  return ws;
}

const say = (room, ws, message) => room.webSocketMessage(ws, JSON.stringify(message));

async function openRoom() {
  const room = newRoom();
  assert.equal(await room.create('K7QP'), true);
  return room;
}

// Moves the room's clock to its alarm and fires it.
async function fireAlarm(room) {
  room.clock = Math.max(room.clock, room.state.alarm);
  await room.alarm();
}

describe('rooms', () => {
  let room;
  beforeEach(async () => { room = await openRoom(); });

  test('a code in use is not given out again until the room has been idle a while', async () => {
    assert.equal(await room.create('K7QP'), false);
    room.clock += EXPIRE_MS;
    assert.equal(await room.create('K7QP'), true);
  });

  test('players join the lobby, and the first one is host', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob', 5);
    const state = bob.last('state');
    assert.equal(state.phase, 'lobby');
    assert.equal(state.you, 1);
    assert.equal(state.host, 0);
    assert.deepEqual(state.players.map((p) => [p.name, p.avatar, p.online]), [['Dana', 1, true], ['Bob', 5, true]]);
    assert.equal(dana.last('state').players.length, 2, 'everyone hears about newcomers');
    assert.ok(!JSON.stringify(state).includes('token-'), 'tokens stay private');
    assert.deepEqual(room.info(), { code: 'K7QP', phase: 'lobby', players: 2, full: false });
  });

  test('a bad name is refused', async () => {
    const ws = new FakeSocket();
    room.connect(ws);
    await say(room, ws, { t: 'hello', name: '<b>', avatar: 0, token: token('x') });
    assert.match(ws.last('error').error, /name/);
    assert.equal(room.room.players.length, 0);
  });

  test('only the host sets the length, adds bots and starts', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, bob, { t: 'length', length: 'quick' });
    await say(room, bob, { t: 'bots', n: 3 });
    await say(room, bob, { t: 'start' });
    assert.equal(room.room.length, 'standard');
    assert.equal(room.room.players.length, 2);
    assert.equal(room.room.phase, 'lobby');

    await say(room, dana, { t: 'length', length: 'quick' });
    await say(room, dana, { t: 'bots', n: 3 });
    const state = bob.last('state');
    assert.equal(state.length, 'quick');
    assert.deepEqual(state.players.map((p) => p.bot), [false, false, true, true, true]);
    assert.equal(new Set(state.players.map((p) => p.name)).size, 5, 'bots get names of their own');
    await say(room, dana, { t: 'bots', n: 1 });
    assert.equal(room.room.players.length, 3);
  });

  test('the host leaving hands the room to the next player', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'leave' });
    const state = bob.last('state');
    assert.equal(state.host, 0);
    assert.equal(state.you, 0);
    assert.deepEqual(state.players.map((p) => p.name), ['Bob']);
  });

  test('a lone player needs company to start', async () => {
    const dana = await join(room, 'Dana');
    await say(room, dana, { t: 'start' });
    assert.match(dana.last('error').error, /two players/);
    assert.equal(room.room.phase, 'lobby');
  });

  test('a room holds 50 players, and people take the place of bots', async () => {
    const host = await join(room, 'Host');
    await say(room, host, { t: 'bots', n: 99 });
    assert.equal(room.room.players.length, WAR.MAX_PLAYERS);
    await join(room, 'Late');
    assert.equal(room.room.players.length, WAR.MAX_PLAYERS);
    assert.deepEqual(room.room.players.filter((p) => !p.bot).map((p) => p.name), ['Host', 'Late']);
  });

  test('a game is dealt, slammed and played out', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'bots', n: 2 });
    await say(room, dana, { t: 'start' });
    assert.equal(room.room.phase, 'playing');
    const state = bob.last('state');
    assert.equal(state.game.battle, 1);
    assert.deepEqual(state.game.counts, [27, 27, 27, 27]);
    const stage = bob.last('stage');
    assert.deepEqual(stage.fighters, [0, 1, 2, 3]);
    assert.deepEqual(stage.bots.map(([seat]) => seat), [2, 3]);
    assert.equal(room.state.alarm, room.room.game.closesAt, 'waits for Dana and Bob');

    await say(room, dana, { t: 'charge', tier: 4 });
    assert.deepEqual(bob.last('charge'), { t: 'charge', seat: 0, tier: 4 });
    const top = room.room.game.piles[0][0];
    await say(room, dana, { t: 'slam', power: 150, style: 2 });
    assert.deepEqual(bob.last('slam'), { t: 'slam', seat: 0, power: 150, style: 2, up: top });
    assert.deepEqual(dana.last('slam'), bob.last('slam'), 'your own slam comes back with your card');
    await say(room, dana, { t: 'slam', power: 10, style: 2 });
    assert.equal(bob.all('slam').length, 1, 'one slam per stage');
    assert.equal(bob.all('flip').length, 0);

    await say(room, bob, { t: 'slam', power: 3, style: 0 });
    assert.equal(room.state.alarm, room.room.game.opensAt + WAR.BOT_MS, 'everyone slammed, so it plays out once the bots have');
    await fireAlarm(room);
    const flip = bob.last('flip');
    assert.equal(flip.battle, 1);
    assert.deepEqual(flip.plays.map((p) => [p[0], p[3], p[5]]), [[0, 150, 0], [1, 3, 0], [2, flip.plays[2][3], 0], [3, flip.plays[3][3], 0]]);
    assert.deepEqual(dana.last('flip'), flip);
    assert.equal(flip.plays[0][2], top, 'the card Dana slammed face up is the one the flip shows');
    assert.deepEqual(stage.bots.map((b) => b[4]), [flip.plays[2][2], flip.plays[3][2]]);
    assert.equal(flip.counts.reduce((a, b) => a + b), WAR.DECK * 2);
    assert.ok(flip.next);
  });

  test('in a war, each face-down card is slammed on its own, and everyone hears about it', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'start' });
    await say(room, dana, { t: 'card', n: 0, power: 50 });
    assert.equal(bob.all('card').length, 0, 'no face-down cards in a plain battle');

    // Rig a tie, so the next stage is a war between Dana and Bob.
    const game = room.room.game;
    game.piles = [[card(9), card(1), card(2), card(3), card(4)], [card(9, 1), card(5), card(6), card(7), card(8)]];
    await say(room, dana, { t: 'slam', power: 10, style: 0 });
    await say(room, bob, { t: 'slam', power: 10, style: 0 });
    await fireAlarm(room);
    const war = bob.last('flip').next;
    assert.equal(war.stage, 1);
    assert.equal(war.closesIn - war.opensIn, WAR.WAR_STAGE_MS);

    await say(room, dana, { t: 'card', n: 0, power: 999 });
    await say(room, dana, { t: 'card', n: 1, power: 'lots' });
    await say(room, dana, { t: 'card', n: 5, power: 50 });
    assert.deepEqual(bob.all('card'), [{ t: 'card', seat: 0, n: 0, power: WAR.MAX_POWER }, { t: 'card', seat: 0, n: 1, power: 0 }]);
    await say(room, dana, { t: 'slam', power: 120, style: 1 });
    await say(room, dana, { t: 'card', n: 2, power: 50 });
    assert.equal(bob.all('card').length, 2, 'nothing more once the last card is slammed');
  });

  test("a player who doesn't slam in time flops", async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'start' });
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    room.clock += 1000;
    await room.alarm();
    assert.equal(bob.all('flip').length, 0, 'not yet');
    await fireAlarm(room);
    const flip = bob.last('flip');
    assert.deepEqual(flip.plays.map((p) => [p[0], p[3], p[5]]), [[0, 80, 0], [1, 0, 1]]);
  });

  test('someone leaving mid-game is not waited for, and everyone leaving pauses it', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'start' });
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    bob.close();
    await room.webSocketClose(bob);
    assert.deepEqual(dana.last('online').online, [0]);
    await fireAlarm(room);
    assert.equal(dana.all('flip').length, 1);

    dana.close();
    await room.webSocketClose(dana);
    assert.ok(room.room.pausedAt);
    const left = room.room.game.opensAt;
    room.clock += 60_000;
    assert.equal(room.state.alarm, room.room.touchedAt + EXPIRE_MS, 'nothing happens until someone is back');

    const back = await join(room, 'Dana');
    assert.equal(back.last('state').you, 0);
    const { game } = back.last('state');
    assert.deepEqual(Object.keys(game.ups), Object.keys(game.slams), 'rejoining shows the cards already slammed');
    for (const seat of Object.keys(game.ups)) assert.equal(game.ups[seat], room.room.game.piles[seat][0]);
    assert.equal(room.room.game.opensAt, left + 60_000, 'the stage picks up where it was');
    assert.equal(room.state.alarm, room.room.game.closesAt);
  });

  test("everyone sees each player's deck, and can change theirs mid-game", async () => {
    const dana = await join(room, 'Dana', 1, 'neon');
    const bob = await join(room, 'Bob', 2, 'NOT a deck');
    await say(room, dana, { t: 'bots', n: 1 });
    assert.deepEqual(bob.last('state').players.map((p) => p.deck), ['neon', null, null], "bots and bad decks get none");
    assert.equal(cleanDeck('candy'), 'candy');
    assert.equal(cleanDeck('x'.repeat(17)), null);
    assert.equal(cleanDeck(7), null);

    await say(room, dana, { t: 'start' });
    await say(room, dana, { t: 'deck', deck: 'candy' });
    assert.deepEqual(bob.last('deck'), { t: 'deck', seat: 0, deck: 'candy' });
    assert.equal(room.room.players[0].deck, 'candy');
    await say(room, dana, { t: 'deck', deck: 'space' });
    assert.equal(bob.all('deck').length, 1, 'at most one change a second');
    room.clock += 1000;
    await say(room, dana, { t: 'deck', deck: 'space' });
    await say(room, bob, { t: 'deck', deck: '../../etc' });
    assert.deepEqual(bob.all('deck').map((m) => m.deck), ['candy', 'space']);

    // Rejoining mid-game brings your deck along.
    room.clock += 1000;
    const bob2 = await join(room, 'Bob', 2, 'royal');
    assert.equal(bob2.last('state').players[1].deck, 'royal');
  });

  test('newcomers watch a game in progress and are dealt into the next', async () => {
    const dana = await join(room, 'Dana');
    await say(room, dana, { t: 'bots', n: 1 });
    await say(room, dana, { t: 'start' });
    const eve = await join(room, 'Eve', 1, 'spooky');
    const watching = eve.last('state');
    assert.equal(watching.you, null);
    assert.equal(watching.phase, 'playing');
    assert.equal(dana.last('online').watchers, 1);
    await say(room, eve, { t: 'slam', power: 100, style: 0 });
    assert.equal(dana.all('slam').length, 0, "spectators can't slam");
    await say(room, eve, { t: 'deck', deck: 'candy' });
    assert.equal(dana.all('deck').length, 0, "a spectator's deck is kept for the next game");

    room.room.game.limit = 1;
    await say(room, dana, { t: 'slam', power: 1, style: 0 });
    await fireAlarm(room);
    while (room.room.phase === 'playing') await fireAlarm(room);
    assert.equal(room.room.phase, 'over');
    assert.ok(eve.last('flip').over);

    await say(room, dana, { t: 'start' });
    const next = eve.last('state');
    assert.equal(next.phase, 'playing');
    assert.deepEqual(next.players.map((p) => p.name), ['Dana', 'Eve', room.room.players[2].name]);
    assert.equal(next.you, 1);
    assert.equal(next.players[1].deck, 'candy');
  });

  test('a spectator can start the next game when no player is left', async () => {
    const dana = await join(room, 'Dana');
    await say(room, dana, { t: 'bots', n: 1 });
    await say(room, dana, { t: 'start' });
    const eve = await join(room, 'Eve');
    dana.close();
    await room.webSocketClose(dana);
    room.room.game.limit = 1;
    while (room.room.phase === 'playing') await fireAlarm(room);
    assert.equal(eve.last('flip').over !== undefined, true);
    await say(room, eve, { t: 'start' });
    assert.equal(room.room.phase, 'playing');
    assert.equal(eve.last('state').you, 0);
  });

  test('a room woken from hibernation carries on from storage', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'start' });
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    const woken = newRoom(room.state);
    woken.clock = room.state.alarm;
    await woken.alarm();
    const flip = bob.last('flip');
    assert.equal(flip.battle, 1);
    assert.deepEqual(flip.plays.map((p) => p[5]), [1, 1], 'the slams in memory were forgotten, so both flopped');
  });

  test('cheers are passed on, but not too often', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'cheer', e: 2 });
    await say(room, dana, { t: 'cheer', e: 3 });
    await say(room, dana, { t: 'cheer', e: 99 });
    assert.deepEqual(bob.all('cheer'), [{ t: 'cheer', seat: 0, e: 2 }]);
    room.clock += 500;
    await say(room, dana, { t: 'cheer', e: 3 });
    assert.equal(bob.all('cheer').length, 2);
  });

  test('cleaning up is passed on to everyone, from players only, and not too often', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'tidy' });
    assert.equal(bob.all('tidy').length, 0, 'nothing to clean up in the lobby');
    await say(room, dana, { t: 'start' });
    const eve = await join(room, 'Eve');
    await say(room, bob, { t: 'tidy' });
    await say(room, bob, { t: 'tidy' });
    await say(room, eve, { t: 'tidy' });
    assert.deepEqual(dana.all('tidy'), [{ t: 'tidy', seat: 1 }]);
    assert.deepEqual(eve.all('tidy'), [{ t: 'tidy', seat: 1 }], 'spectators see it, but have no heap to clean up');
    room.clock += 1000;
    await say(room, bob, { t: 'tidy' });
    assert.equal(dana.all('tidy').length, 2);
  });

  test('the host picks a slow game in the lobby, and everyone hears', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    assert.equal(bob.last('state').slow, false);
    await say(room, bob, { t: 'slow', slow: true });
    assert.equal(room.room.slow, false, 'only the host');
    await say(room, dana, { t: 'slow', slow: 'yes' });
    assert.equal(room.room.slow, false);
    await say(room, dana, { t: 'slow', slow: true });
    assert.equal(bob.last('state').slow, true);
    await say(room, dana, { t: 'start' });
    assert.equal(bob.last('stage').closesIn, null);
    assert.equal(bob.last('state').game.closesIn, null);
    assert.equal(bob.last('state').game.slow, true);
    await say(room, dana, { t: 'slow', slow: false });
    assert.equal(room.room.slow, true, 'not mid-game');
  });

  // A slow room with Dana, Bob and a bot, dealt and waiting for the first stage.
  async function slowRoom() {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'slow', slow: true });
    await say(room, dana, { t: 'bots', n: 1 });
    await say(room, dana, { t: 'start' });
    return { dana, bob };
  }

  test('a slow room waits for everyone online, however long', async () => {
    const { dana, bob } = await slowRoom();
    assert.equal(room.state.alarm, room.room.touchedAt + EXPIRE_MS, 'no stage deadline, only the idle check');
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    room.clock += 5 * 60 * 60 * 1000;
    await fireAlarm(room);
    assert.equal(bob.all('flip').length, 0, 'five hours later, still waiting for Bob');
    assert.ok(room.state.alarm > room.clock, 'and the alarm looks again later, rather than spinning');
    await say(room, bob, { t: 'slam', power: 20, style: 0 });
    await fireAlarm(room);
    const flip = bob.last('flip');
    assert.deepEqual(flip.plays.map((p) => p[5]), [0, 0, 0], 'nobody flopped, and the bot played');
    assert.equal(flip.next.closesIn, null);
  });

  test("a slow room doesn't wait for someone who has left", async () => {
    const { dana, bob } = await slowRoom();
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    bob.close();
    await room.webSocketClose(bob);
    await fireAlarm(room);
    assert.deepEqual(dana.last('flip').plays.map((p) => p[5]), [0, 1, 0]);

    // Back at the table, Bob is waited for again.
    room.clock += 1000;
    const back = await join(room, 'Bob');
    room.clock = room.room.game.opensAt;
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    await fireAlarm(room);
    assert.equal(dana.all('flip').length, 1);
    await say(room, back, { t: 'slam', power: 80, style: 0 });
    await fireAlarm(room);
    assert.equal(dana.all('flip').length, 2);
  });

  test('in a slow room, anyone can nudge the players it waits for, once they have had a moment', async () => {
    const { dana, bob } = await slowRoom();
    const eve = await join(room, 'Eve');
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    await say(room, dana, { t: 'nudge' });
    assert.equal(bob.all('nudge').length, 0, 'too soon');
    room.clock = room.room.game.opensAt + WAR.NUDGE_MS;
    await say(room, dana, { t: 'nudge' });
    assert.deepEqual(bob.last('nudge'), { t: 'nudge', seats: [1], by: 0 });
    await say(room, dana, { t: 'nudge' });
    assert.equal(bob.all('nudge').length, 1, 'not too often');
    await say(room, eve, { t: 'nudge' });
    assert.deepEqual(bob.last('nudge'), { t: 'nudge', seats: [1], by: null }, 'spectators can nudge too');
    room.clock += 3000;
    await say(room, bob, { t: 'nudge' });
    assert.equal(bob.all('nudge').length, 2, "nobody else to nudge: Bob can't nudge himself");
  });

  test('in a slow room, after a long wait, the host can flip their cards over for them', async () => {
    const { dana, bob } = await slowRoom();
    // An ace for Dana, so the first battle is no war and everyone fights the next.
    room.room.game.piles = [[card(12), card(9), card(9, 1)], [card(2), card(3), card(4)], [card(5), card(6), card(7)]];
    const flopped = () => bob.all('slam').filter((m) => m.flopped);
    await say(room, bob, { t: 'slam', power: 80, style: 0 });
    room.clock = room.room.game.opensAt + WAR.FLOP_MS;
    await say(room, bob, { t: 'flop' });
    assert.equal(flopped().length, 0, 'only the host');
    await say(room, dana, { t: 'flop' });
    assert.equal(flopped().length, 0, "nobody to flip but Dana herself, and she doesn't");
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    await fireAlarm(room);
    assert.equal(bob.last('flip').winner, 0);

    const next = room.room.game;
    room.clock = next.opensAt + 1000;
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    await say(room, dana, { t: 'flop' });
    assert.equal(flopped().length, 0, 'too soon');
    room.clock = next.opensAt + WAR.FLOP_MS;
    await say(room, dana, { t: 'flop' });
    assert.deepEqual(flopped(), [{ t: 'slam', seat: 1, power: 0, style: 0, up: card(3), flopped: true }]);
    await fireAlarm(room);
    const flip = bob.last('flip');
    assert.deepEqual(flip.plays[1].slice(2), [card(3), 0, 0, 1], "Bob's card flopped over");
    assert.equal(flip.battle, 2);
  });

  test("a slow room keeps its slams through hibernation, and still expires when idle", async () => {
    const { dana, bob } = await slowRoom();
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    const woken = newRoom(room.state);
    woken.clock = room.clock;
    await woken.webSocketMessage(bob, JSON.stringify({ t: 'slam', power: 5, style: 0 }));
    woken.clock = room.state.alarm;
    await woken.alarm();
    assert.deepEqual(bob.last('flip').plays.map((p) => p[5]), [0, 0, 0], "Dana's slam was saved");

    dana.close();
    await woken.webSocketClose(dana);
    bob.close();
    await woken.webSocketClose(bob);
    woken.clock += EXPIRE_MS;
    await woken.alarm();
    assert.equal(woken.room, null);
  });

  test('a timed room has no nudges or flipping for others: its clock does that', async () => {
    const dana = await join(room, 'Dana');
    const bob = await join(room, 'Bob');
    await say(room, dana, { t: 'start' });
    await say(room, dana, { t: 'slam', power: 80, style: 0 });
    room.clock = room.room.game.opensAt + WAR.FLOP_MS - 1;
    await say(room, dana, { t: 'nudge' });
    await say(room, dana, { t: 'flop' });
    assert.equal(bob.all('nudge').length, 0);
    assert.equal(bob.all('slam').length, 1);
  });

  test('junk messages are ignored', async () => {
    const dana = await join(room, 'Dana');
    await room.webSocketMessage(dana, 'not json');
    await room.webSocketMessage(dana, 'x'.repeat(5000));
    await room.webSocketMessage(dana, new ArrayBuffer(8));
    await say(room, dana, { t: 'nope' });
    assert.equal(dana.all('error').length, 0);
  });

  test('an idle room is deleted', async () => {
    await join(room, 'Dana');
    room.state.getWebSockets()[0].close();
    room.clock += EXPIRE_MS;
    await room.alarm();
    assert.equal(room.state.data.size, 0);
    assert.equal(room.room, null);
  });

  test('a stage played out costs one storage write, not one per slam', async () => {
    const dana = await join(room, 'Dana');
    await say(room, dana, { t: 'bots', n: 20 });
    await say(room, dana, { t: 'start' });
    const before = room.state.writes;
    await say(room, dana, { t: 'slam', power: 1, style: 0 });
    await fireAlarm(room);
    assert.equal(room.state.writes - before, 1);
  });
});

// ---- HTTP routes ----

function fakeD1() {
  const db = new DatabaseSync(':memory:');
  const migrations = new URL('../migrations/', import.meta.url);
  for (const file of readdirSync(migrations).sort()) db.exec(readFileSync(new URL(file, migrations), 'utf8'));
  const statement = (sql, params = []) => ({
    bind: (...values) => statement(sql, values),
    first: async (column) => {
      const row = db.prepare(sql).get(...params);
      return row ? (column ? row[column] : row) : null;
    },
    run: async () => { db.prepare(sql).run(...params); return { success: true }; },
  });
  return { prepare: (sql) => statement(sql) };
}

function fakeNamespace() {
  const rooms = new Map();
  return {
    rooms,
    forwarded: [],
    idFromName: (name) => name,
    get(id) {
      if (!rooms.has(id)) rooms.set(id, newRoom());
      const room = rooms.get(id);
      return {
        fetch: async (input, init) => {
          const request = input instanceof Request ? input : new Request(input, init);
          if (request.headers.get('Upgrade') === 'websocket') {
            this.forwarded.push(id);
            return new Response('upgraded');
          }
          return room.fetch(request);
        },
      };
    },
  };
}

describe('routes', () => {
  let env;
  beforeEach(() => {
    env = { DB: fakeD1(), WAR_ROOMS: fakeNamespace(), ALLOWED_ORIGINS: ORIGIN, IP_SALT: 'salt' };
  });

  const call = (method, path, { origin = ORIGIN, headers = {} } = {}) => handleWar(
    new Request(`https://leaderboard.test${path}`, {
      method, headers: { ...(origin ? { Origin: origin } : {}), 'CF-Connecting-IP': '203.0.113.9', ...headers },
    }),
    env,
    NOW,
  );

  test('a new room gets a code that can be looked up', async () => {
    const response = await call('POST', '/v1/war/rooms');
    assert.equal(response.status, 201);
    assert.equal(response.headers.get('Access-Control-Allow-Origin'), ORIGIN);
    const { code } = await response.json();
    assert.match(code, /^[A-HJKMNP-Z2-9]{4}$/);
    const info = await call('GET', `/v1/war/rooms/${code}`);
    assert.equal(info.status, 200);
    assert.deepEqual(await info.json(), { code, phase: 'lobby', players: 0, full: false });
  });

  test('unknown and malformed codes are not found', async () => {
    assert.equal((await call('GET', '/v1/war/rooms/ZZZZ')).status, 404);
    assert.equal((await call('GET', '/v1/war/rooms/zz')).status, 404);
    assert.equal(env.WAR_ROOMS.rooms.size, 1, 'a malformed code never reaches a room');
  });

  test('only the games may start or join rooms', async () => {
    assert.equal((await call('POST', '/v1/war/rooms', { origin: 'https://evil.example' })).status, 403);
    const ws = { headers: { Upgrade: 'websocket' } };
    assert.equal((await call('GET', '/v1/war/rooms/K7QP', { ...ws, origin: 'https://evil.example' })).status, 403);
    assert.equal((await call('GET', '/v1/war/rooms/K7QP', ws)).status, 200);
    assert.deepEqual(env.WAR_ROOMS.forwarded, ['K7QP']);
  });

  test('one address can only start so many rooms', async () => {
    for (let i = 0; i < 20; i++) assert.equal((await call('POST', '/v1/war/rooms')).status, 201);
    assert.equal((await call('POST', '/v1/war/rooms')).status, 429);
  });

  test('rooms turn away connections past the socket limit', async () => {
    const room = await openRoom();
    for (let i = 0; i < MAX_SOCKETS; i++) room.connect(new FakeSocket());
    const response = await room.fetch(new Request('https://war-room/v1/war/rooms/K7QP', { headers: { Upgrade: 'websocket' } }));
    assert.equal(response.status, 429);
  });
});

test('a player whose card flops over twice in a row is not waited for until they slam', () => {
  // No ties, so no wars: each battle is one stage.
  const game = rigged([[card(12), card(11), card(10), card(9)], [card(2), card(3), card(4), card(5)]]);
  const online = new Set([0, 1]);
  const play = () => assert.equal(warResolve(game, NOW, seeded(3)).winner, 0);
  warSlam(game, 0, 50, 0);
  play();
  assert.equal(warDueAt(game, online), game.closesAt, 'one flop: still waited for');
  warSlam(game, 0, 50, 0);
  play();
  assert.deepEqual(game.naps, [0, 2]);
  warSlam(game, 0, 50, 0);
  assert.equal(warDueAt(game, online), game.opensAt + WAR.BOT_MS, 'two flops: dozed off');
  warSlam(game, 1, 50, 0);
  assert.equal(game.naps[1], 0, 'slamming wakes you up');
});
