// Letterfield's world, copied from letterfield.html so the survey can check
// that a circled word is really on the map. The game generates every letter
// from a fixed seed, so this copy must stay identical to the game's: the test
// in test/survey.test.js runs both and compares them.

export const SEED = 0x1E77E2;
export const CH = 12;          // cells per chunk side
export const RG = 4;           // chunks per territory side
export const RC = CH * RG;     // cells per territory side (48)
export const DIRS = [[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1],[0,-1],[1,-1]];
const DWEIGHT = [3,2,3,1,1,1,1,2], DW_TOTAL = 14;

// Theme names and words, in the game's order (a theme's index is its id).
export const THEMES = [
  ['Kitchen', 'BASIL BRAISE BROTH BUTTER CLOVE CUMIN DOUGH FENNEL GARLIC GINGER KNEAD LADLE LEMON MINCE NUTMEG OREGANO PAPRIKA PEPPER POACH RISOTTO SAFFRON SAGE SAUTE SIMMER SKILLET SORREL THYME TOAST WHISK ZEST'],
  ['Orchard', 'APPLE APRICOT BANANA BERRY CHERRY CITRON CURRANT DAMSON DATE FIG GRAPE GUAVA KIWI KUMQUAT LIME LOQUAT LYCHEE MANGO MEDLAR MELON NECTARINE OLIVE PAPAYA PEACH PEAR PERSIMMON PLUM POMELO QUINCE RAISIN'],
  ['Mountains', 'ALPINE BASALT BOULDER BUTTE CAIRN CANYON CAVERN CLIFF CRAG FJORD FLINT GEYSER GLACIER GORGE GRANITE LAVA MAGMA MESA MORAINE PEAK QUARTZ RIDGE SCREE SHALE SLATE SUMMIT TALUS TUNDRA VALLEY VOLCANO'],
  ['Garden', 'ASTER AZALEA BLOOM BULB CLOVER CROCUS DAHLIA DAISY HOSTA IRIS LILAC LILY LOTUS LUPINE MARIGOLD ORCHID PANSY PEONY PETAL POLLEN POPPY PRIMROSE ROSE SEED SNOWDROP STEM TULIP VIOLET YARROW ZINNIA'],
  ['Forest', 'ACORN ALDER ASPEN BADGER BARK BIRCH BRACKEN BRAMBLE CANOPY CEDAR FERN FOX FUNGUS HAZEL HOLLOW HOLLY LARCH LICHEN MAPLE MOSS OWL PINE ROOT SAPLING SPRUCE THICKET TIMBER TRILLIUM WILLOW WOODLAND'],
  ['Animals', 'ALPACA BEAVER BISON CAMEL CHEETAH COYOTE FERRET GECKO GIRAFFE HYENA IBEX IGUANA JACKAL KOALA LEMUR LYNX MARMOT MOOSE OCELOT OTTER PANDA PUMA QUOKKA RACCOON SLOTH TAPIR WALRUS WOMBAT YAK ZEBRA'],
  ['Sea', 'ANCHOR ANEMONE BARNACLE BRINE CORAL COVE CURRENT DRIFT FATHOM GULL HARBOR KELP KRILL LAGOON LIMPET MANTA NARWHAL ORCA OYSTER PEARL PLANKTON REEF SEAWEED SHOAL SQUID SURF SWELL TIDE URCHIN WHALE'],
  ['Weather', 'BLIZZARD BREEZE CIRRUS CLOUD CUMULUS CYCLONE DELUGE DEW DRIZZLE FOG FROST GALE GUST HAIL HAZE LIGHTNING MIST MONSOON NIMBUS RAIN RAINBOW SLEET SNOW SQUALL STORM SUNSHINE THUNDER TORNADO TYPHOON ZEPHYR'],
  ['Library', 'ALMANAC ATLAS BINDING CHAPTER CODEX DRAFT EPILOGUE ESSAY FABLE FOLIO GLOSSARY INDEX INK JOURNAL LEDGER MARGIN MYTH NOVEL PAGE POEM PREFACE PROSE QUILL SAGA SCROLL SONNET SPINE STANZA TOME VERSE'],
  ['Space', 'APOGEE ASTEROID AURORA COMET CORONA COSMOS CRATER ECLIPSE GALAXY GRAVITY JUPITER LUNAR MARS METEOR NEBULA NOVA ORBIT PARSEC PHOTON PLANET PULSAR QUASAR ROCKET ROVER SATURN SOLAR STAR VENUS VOID ZENITH'],
  ['Workshop', 'ANVIL AUGER AWL BOLT BRACE CHISEL CLAMP DRILL FILE GIMLET HAMMER HINGE LATHE LEVEL MALLET NAIL PLANE PLIERS RASP RIVET SANDER SAW SCREW SOLDER SPANNER TONGS TROWEL VISE WASHER WRENCH'],
  ['Music', 'ALTO ARIA BANJO BASS BUGLE CANTATA CELLO CHORD CHORUS CLEF CODA FIDDLE FUGUE GUITAR HARP LUTE LYRE MELODY OBOE OCTAVE OPERA PIANO RHYTHM SONATA TEMPO TENOR TRILL TUBA VIOLA WALTZ'],
].map(([name, words]) => ({ name, words: words.split(' ') }));
const NT = THEMES.length;
export const VOCAB = new Map();
THEMES.forEach((t, i) => t.words.forEach(w => { if (!VOCAB.has(w)) VOCAB.set(w, i); }));

function h3(a, b, c) {
  let h = Math.imul(a | 0, 0x27d4eb2d) ^ Math.imul(b | 0, 0x165667b1) ^ (c | 0);
  h ^= h >>> 15; h = Math.imul(h, 0x85ebca6b);
  h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16; return h >>> 0;
}
function rng(seed) {
  let a = seed | 0;
  return () => {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export const fdiv = (a, b) => Math.floor(a / b);
const RSEED = SEED ^ 0x5bd1e995;
export const regionTheme = (rx, ry) => h3(rx, ry, RSEED) % NT;
export const keyOf = (w, x, y, d) => `${w}~${x}~${y}~${d}`;

export function genChunk(cx, cy) {
  const r = rng(h3(cx, cy, SEED));
  const th = regionTheme(fdiv(cx, RG), fdiv(cy, RG));
  const g = new Uint8Array(CH * CH).fill(255);
  const pool = THEMES[th].words.slice();
  for (let i = pool.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); const t = pool[i]; pool[i] = pool[j]; pool[j] = t; }
  const target = 6 + Math.floor(r() * 3);
  const words = [];
  for (const w of pool) {
    if (words.length >= target) break;
    const L = w.length;
    for (let attempt = 0; attempt < 40; attempt++) {
      let pick = r() * DW_TOTAL, d = 0;
      while (pick >= DWEIGHT[d]) { pick -= DWEIGHT[d]; d++; }
      const dx = DIRS[d][0], dy = DIRS[d][1];
      const x0 = dx < 0 ? L - 1 : 0, x1 = dx > 0 ? CH - L : CH - 1;
      const y0 = dy < 0 ? L - 1 : 0, y1 = dy > 0 ? CH - L : CH - 1;
      const sx = x0 + Math.floor(r() * (x1 - x0 + 1)), sy = y0 + Math.floor(r() * (y1 - y0 + 1));
      let ok = true, overlap = 0;
      for (let i = 0; i < L; i++) {
        const c = g[(sy + dy * i) * CH + sx + dx * i], v = w.charCodeAt(i) - 65;
        if (c !== 255) { if (c !== v) { ok = false; break; } overlap++; }
      }
      if (!ok || overlap === L) continue;
      for (let i = 0; i < L; i++) g[(sy + dy * i) * CH + sx + dx * i] = w.charCodeAt(i) - 65;
      const x = cx * CH + sx, y = cy * CH + sy;
      words.push({ w, x, y, d, th, key: keyOf(w, x, y, d) });
      break;
    }
  }
  let src = 'AEIOUNRSTL';
  for (const o of words) src += o.w;
  for (let i = 0; i < g.length; i++) if (g[i] === 255) g[i] = src.charCodeAt(Math.floor(r() * src.length)) - 65;
  return { g, words };
}
const chunks = new Map();
export function chunk(cx, cy) {
  const k = cx + ',' + cy;
  let c = chunks.get(k);
  if (!c) {
    c = genChunk(cx, cy);
    chunks.set(k, c);
    if (chunks.size > 4000) { let n = 0; for (const key of chunks.keys()) { chunks.delete(key); if (++n >= 800) break; } }
  }
  return c;
}
export function letterAt(x, y) {
  const cx = fdiv(x, CH), cy = fdiv(y, CH);
  return chunk(cx, cy).g[(y - cy * CH) * CH + (x - cx * CH)];
}
export const wordEnd = (e) => [e.x + DIRS[e.d][0] * (e.w.length - 1), e.y + DIRS[e.d][1] * (e.w.length - 1)];
