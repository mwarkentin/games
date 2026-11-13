-- Recovery codes (src/players.js): a code a player saves to be the same player
-- again on any device. Neither the code nor the token is kept: a code's
-- SHA-512 gives the row's id (its first half) and the key (its second) that
-- the token is sealed with, so only someone holding the code can open it.
CREATE TABLE recovery (
  id TEXT PRIMARY KEY,
  pid TEXT NOT NULL,
  box TEXT NOT NULL,
  made INTEGER NOT NULL
) WITHOUT ROWID;
CREATE INDEX recovery_pid ON recovery (pid);
