-- Letterfield's survey log, in its own database (LOG_DB in wrangler.toml):
-- one row per word charted, copied from the sector
-- that took the claim (see "The log" in SURVEY.md). The table is ordered by
-- time, so reading an hour reads only that hour's rows and needs no other
-- index. A sector resends rows it isn't sure arrived, and the same (at, key)
-- is never a second row.
CREATE TABLE survey_log (
  at INTEGER NOT NULL,       -- when the sector took the claim, ms since 1970
  key TEXT NOT NULL,         -- word~x~y~d, as the game and the sector name it
  w TEXT NOT NULL,
  x INTEGER NOT NULL,
  y INTEGER NOT NULL,
  d INTEGER NOT NULL,
  s INTEGER NOT NULL,        -- 1 for a stray word
  initials TEXT NOT NULL,    -- '' when the charter gave none
  PRIMARY KEY (at, key)
) WITHOUT ROWID;
