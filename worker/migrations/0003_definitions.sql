-- What Letterfield's words mean, fetched once each from Wiktionary or
-- Wikipedia (see src/define.js). context is '' for a Wiktionary answer, the
-- same in every theme; a theme's name for one found through Wikipedia's
-- search with it; or '?' and the theme's name for an empty answer, which is
-- asked again a month later. body is the answer as JSON.
CREATE TABLE definitions (
  word TEXT NOT NULL,
  context TEXT NOT NULL,
  body TEXT NOT NULL,
  fetched_at INTEGER NOT NULL,
  PRIMARY KEY (word, context)
);
