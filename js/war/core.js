// The rules of War and the pacing of a game, for war.html (solo games
// against bots) and worker/src/war.js (rooms played over the network): one
// file, so the two always play by the same rules. A slam's power and style are
// passed along for show, but the rules never read them: slamming changes
// nothing.
//
// No DOM: node:test imports it as it is (worker/test/war.test.js).

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
  NUDGE_MS: 5000,      // in a slow game, how long a stage waits before you can nudge someone
  FLOP_MS: 30000,      // and before the host can flip their card over for them
  BOT_MS: 1300,        // the shortest a stage lasts, while the bots slam
  WAR_BOT_MS: 2600,    // the same in a war, while the bots slam all their cards
  REVEAL_MS: 2400,     // to watch the cards turn over before the next battle
  WAR_REVEAL_MS: 3000, // the same before a war
  JOKER_REVEAL_MS: 4500, // and before a war on jokers, which the pages put on a show for
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
// the game and the message opening its first battle. Options: pace speeds
// it up (below 1) or slows it down; a slow game has no clock, so each stage
// waits until everyone has played, like a game at a real table, and nobody's
// card flops over by itself; and shuffle shuffles each player's winnings as
// they go back under their deck, instead of keeping them as they were won.
//
// Each player has a deck, face down, played from the top (piles), and the
// cards they've won, face up beside it (loot), the latest last. Winnings go
// back under the deck when the player picks them up (warGather): players do
// that themselves, bots when their deck can't cover a stage. Either way the
// cards come round in the same order, so picking up early changes nothing.
function warNewGame(bots, length, random, now, options = {}) {
  const game = {
    limit: WAR.LENGTHS[length] || WAR.LENGTHS.standard,
    piles: warDeal(bots.length, random),
    loot: bots.map(() => []),
    bots: bots.slice(),
    out: bots.map(() => 0),  // the battle each player ran out of cards in
    naps: bots.map(() => 0), // stages in a row each player's card flopped over by itself
    battle: 0, stage: 0, fighters: [], slams: {}, pot: [], potBy: [],
    opensAt: 0, closesAt: 0, pace: options.pace || 1, slow: Boolean(options.slow), shuffle: Boolean(options.shuffle),
    wars: 0, biggest: 0, deepest: 0, over: null,
  };
  return { game, stage: warOpenStage(game, now, random, null, 0) };
}

// The cards a player holds: their deck and their winnings.
function warHeld(game, seat) {
  return game.piles[seat].length + game.loot[seat].length;
}

// Puts a player's winnings under their deck as they lie, the oldest first,
// or shuffled in a game that shuffles them. Only the bottom of the deck
// changes, so the card a stage turns up stays the same. Returns how many
// cards went under.
function warGather(game, seat, random) {
  const loot = game.loot[seat];
  if (!loot.length) return 0;
  game.piles[seat].push(...(game.shuffle ? warShuffle(loot, random) : loot));
  game.loot[seat] = [];
  return loot.length;
}

// Whether a player has to pick up their winnings before they can play this
// stage: their deck can't cover it (a card in a battle, four in a war) and
// they have winnings to pick up.
function warShort(game, seat) {
  return game.loot[seat].length > 0 && game.piles[seat].length < (game.stage ? 4 : 1);
}

// How long the bots take to slam: a moment in a battle, longer in a war,
// where they slam every card they lay down.
function warBotMs(game) {
  return Math.round((game.stage ? WAR.WAR_BOT_MS : WAR.BOT_MS) * game.pace);
}

// The card a fighter will turn over this stage: their top card, or in a war
// the one after the (up to three) they lay face down. A stage's cards are
// fixed once it opens, since piles only change when it's played out, so a
// slam can show its card face up at once. War has no decisions, so seeing
// cards early gives nobody an edge.
function warUpCard(game, seat) {
  const pile = game.piles[seat];
  return pile[game.stage ? Math.min(3, pile.length - 1) : 0];
}

// Opens the next stage: a new battle for everyone still holding cards, or,
// when fighters is given, a war between them. A bot whose deck can't cover
// the stage picks up its winnings first; gathered says which. Players pick up
// their own, before they slam. Bots slam straight away; the pages show their
// slams one by one while the stage opens, each bot's card face up as it lands.
function warOpenStage(game, now, random, fighters, delay) {
  if (fighters) {
    game.stage++;
    game.fighters = fighters;
  } else {
    game.battle++;
    game.stage = 0;
    game.fighters = game.piles.map((_, seat) => seat).filter((seat) => warHeld(game, seat));
    game.pot = [];
    game.potBy = [];
  }
  const gathered = game.fighters.filter((seat) => game.bots[seat] && warShort(game, seat) && warGather(game, seat, random));
  game.slams = {};
  game.opensAt = now + Math.round(delay * game.pace);
  game.closesAt = game.slow ? Infinity : game.opensAt + (game.stage ? WAR.WAR_STAGE_MS : WAR.STAGE_MS);
  const bots = [];
  for (const seat of game.fighters) {
    if (!game.bots[seat]) continue;
    const power = warBotPower(random);
    const style = Math.floor(random() * WAR.STYLES);
    game.slams[seat] = [power, style, 0];
    const delay = Math.round(100 * game.pace + random() * (warBotMs(game) - 300 * game.pace));
    bots.push([seat, power, style, delay, warUpCard(game, seat)]);
  }
  return {
    t: 'stage', battle: game.battle, stage: game.stage, limit: game.limit, fighters: game.fighters.slice(),
    opensIn: game.opensAt - now, closesIn: game.slow ? null : game.closesAt - now, bots, gathered,
  };
}

// Players (not bots) in this stage who are online and haven't slammed yet,
// unless they've dozed off: then nobody waits for them until they slam again.
function warWaitingFor(game, online) {
  return game.fighters.filter((seat) => !game.bots[seat] && online.has(seat) && !game.slams[seat]
    && game.naps[seat] < WAR.NAPS);
}

// When to play the stage out: once everyone online has slammed and the bots
// have had their moment, or when time runs out. In a slow game time never
// runs out: Infinity, until everyone online has played.
function warDueAt(game, online) {
  return warWaitingFor(game, online).length ? game.closesAt : game.opensAt + warBotMs(game);
}

// Records a slam. Returns the message to pass on, with the card it turns
// over, or null when it doesn't count: the game is over, the seat isn't
// fighting, or it already slammed. The pages have the player pick up their
// winnings first when they must; a slam that comes without picks them up
// (gathered: true).
function warSlam(game, seat, power, style, random = Math.random) {
  if (game.over || !game.fighters.includes(seat) || game.slams[seat]) return null;
  power = Math.max(0, Math.min(WAR.MAX_POWER, Math.round(Number(power)) || 0));
  style = Number.isInteger(style) && style >= 0 && style < WAR.STYLES ? style : 0;
  const gathered = warShort(game, seat) && warGather(game, seat, random) > 0;
  game.slams[seat] = [power, style, 0];
  game.naps[seat] = 0;
  const slam = { t: 'slam', seat, power, style, up: warUpCard(game, seat) };
  if (gathered) slam.gathered = true;
  return slam;
}

// In a slow game, someone the table has waited a long time for gets their
// card flipped over for them, as if it had flopped. Returns the slam to pass
// on, or null when it doesn't count.
function warFlop(game, seat, random = Math.random) {
  if (game.over || !game.fighters.includes(seat) || game.slams[seat]) return null;
  const gathered = warShort(game, seat) && warGather(game, seat, random) > 0;
  game.slams[seat] = [0, 0, 1];
  const slam = { t: 'slam', seat, power: 0, style: 0, up: warUpCard(game, seat), flopped: true };
  if (gathered) slam.gathered = true;
  return slam;
}

// Plays the stage out. Every fighter turns over their top card (in a war,
// after laying up to three face down, keeping one to turn over) and the
// highest rank takes the pot. A tie is a war between the tied players who
// still have cards: if only one does, they win; if none do, the war gods pick.
// Anyone who hasn't slammed flops their card over anyway. Returns the message
// describing it all, with the next stage or the end of the game. In a war,
// downs has the cards each fighter laid face down, so whoever wins the pot
// can see every card in it. The pot goes onto the winner's winnings as it
// lies: everyone else's cards in the order they were played, then the
// winner's own on top. counts is every card each player holds, decks the
// ones in their deck. A card that flops over from a deck that couldn't
// cover the stage picks up its player's winnings first; gathered says whose.
function warResolve(game, now, random) {
  const plays = [];
  const downs = {};
  const gathered = game.fighters.filter((seat) => warShort(game, seat) && warGather(game, seat, random));
  let best = -1;
  for (const seat of game.fighters) {
    const pile = game.piles[seat];
    const slam = game.slams[seat] || [0, 0, 1];
    if (slam[2]) game.naps[seat]++;
    const down = game.stage ? Math.min(3, pile.length - 1) : 0;
    const laid = pile.splice(0, down);
    if (down) downs[seat] = laid;
    const up = pile.shift();
    for (const card of [...laid, up]) { game.pot.push(card); game.potBy.push(seat); }
    best = Math.max(best, warRank(up));
    plays.push([seat, down, up, ...slam]);
  }
  const tied = plays.filter((play) => warRank(play[2]) === best).map((play) => play[0]);
  const able = tied.filter((seat) => warHeld(game, seat));
  let winner = tied.length === 1 ? tied[0] : able.length === 1 ? able[0] : null;
  const gods = tied.length > 1 && !able.length;
  if (gods) winner = tied[Math.floor(random() * tied.length)];
  const message = {
    t: 'flip', battle: game.battle, stage: game.stage, plays, tied, winner, gods, pot: game.pot.length, gathered,
  };
  if (game.stage) message.downs = downs;
  if (winner === null) {
    if (!game.stage) game.wars++;
    game.biggest = Math.max(game.biggest, able.length);
    game.deepest = Math.max(game.deepest, game.stage + 1);
    message.counts = game.piles.map((_, seat) => warHeld(game, seat));
    message.decks = game.piles.map((pile) => pile.length);
    // A war on jokers (rank 13) waits longer to open, for its show.
    message.next = warOpenStage(game, now, random, able, best === 13 ? WAR.JOKER_REVEAL_MS : WAR.WAR_REVEAL_MS);
    return message;
  }
  const theirs = game.pot.filter((_, i) => game.potBy[i] !== winner);
  const own = game.pot.filter((_, i) => game.potBy[i] === winner);
  game.loot[winner].push(...theirs, ...own);
  game.pot = [];
  game.potBy = [];
  message.counts = game.piles.map((_, seat) => warHeld(game, seat));
  message.decks = game.piles.map((pile) => pile.length);
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
  const counts = game.piles.map((_, seat) => warHeld(game, seat));
  const lasted = (seat) => game.out[seat] || Infinity;
  const order = counts.map((_, seat) => seat).sort((a, b) => counts[b] - counts[a] || lasted(b) - lasted(a) || a - b);
  const most = counts[order[0]];
  return {
    winners: order.filter((seat) => counts[seat] === most), order, counts, out: game.out.slice(),
    battles: game.battle, wars: game.wars, biggest: game.biggest, deepest: game.deepest,
  };
}

export {
  WAR, WAR_BOT_FIRST, WAR_BOT_LAST, warBotMs, warBotNames, warBotPower, warDeal, warDueAt, warFlop, warGather,
  warHeld, warNewGame, warOpenStage, warRank, warResolve, warShort, warShuffle, warSlam, warStandings, warUpCard, warWaitingFor,
};
