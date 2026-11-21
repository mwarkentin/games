// Names other people see: players in a War room, and leaderboard groups.
// war.html checks a name this way before it asks for a room, and the Worker
// (worker/src/war.js for rooms, worker/src/leaderboard.js for groups) has the
// last word, with this same file.
//
// No DOM: node:test imports it as it is (worker/test/war.test.js).

// Accents come off, digits that look like letters count as those letters, and
// any letter may repeat ("fuuuck"). Words that turn up inside ordinary names
// (ass in Cassandra, shit in Yamashita, porn in Pornchai) count only as a word
// of their own, or spelled out with spaces; the rest count anywhere in a name.
const NAME_ANYWHERE = [
  'fuck', 'fck', 'bullshit', 'shithead', 'shitty', 'dipshit', 'cunt', 'nigger', 'nigga', 'faggot', 'bitch',
  'whore', 'slut', 'bastard', 'asshole', 'jackass', 'dumbass', 'jizz', 'retard', 'pussy', 'penis', 'vagina',
  'dildo', 'wanker', 'twat', 'blowjob', 'handjob', 'cumshot', 'pornhub', 'hitler',
  'putain', 'salope', 'connard', 'connasse', 'encule', 'batard', 'niquer', 'merde', 'mierda', 'pendejo',
];
const NAME_ALONE = [
  'ass', 'asses', 'arse', 'butthole', 'dick', 'dik', 'cock', 'cum', 'sex', 'sexy', 'tit', 'tits', 'titty',
  'titties', 'boob', 'boobs', 'nipple', 'anal', 'anus', 'nude', 'naked', 'horny', 'sperm', 'semen', 'orgasm',
  'rape', 'rapist', 'porn', 'porno', 'wank', 'shit', 'shits', 'fuk', 'damn', 'hell', 'crap', 'piss', 'fag',
  'fags', 'hoe', 'hoes', 'thot', 'milf', 'wtf', 'stfu', 'gtfo', 'xxx', 'kkk', 'nazi', 'kike', 'chink', 'spic',
  'coon', 'negro', 'dyke', 'homo', 'tranny', 'pute', 'nique', 'puta', 'puto',
];
const NAME_LOOKALIKES = { 0: 'o', 3: 'e', 4: 'a', 5: 's', 7: 't', 8: 'b', 9: 'g', '!': 'i' };
const nameWord = (word, alone) => new RegExp(`${alone ? '^' : ''}${[...word].map((c) => `${c}+`).join('')}${alone ? '$' : ''}`);
const NAME_ANYWHERE_RES = NAME_ANYWHERE.map((word) => nameWord(word, false));
const NAME_ALONE_RES = NAME_ALONE.map((word) => nameWord(word, true));

// Whether a name is fit to show everyone. A 1 is read as both an i and an l.
function nameIsKind(name) {
  const plain = String(name).normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
  return ['i', 'l'].every((one) => {
    const letters = plain.replace(/[0-9!]/g, (c) => (c === '1' ? one : NAME_LOOKALIKES[c] ?? c));
    const words = letters.split(/[^a-z]+/).filter(Boolean);
    const squashed = words.join('');
    if (NAME_ANYWHERE_RES.some((re) => re.test(squashed))) return false;
    return ![...words, squashed].some((word) => NAME_ALONE_RES.some((re) => re.test(word)));
  });
}

export { nameIsKind };
