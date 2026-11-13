-- One-time codes for linking another device to a player (src/players.js).
-- A code lasts ten minutes; once it's used, carry is emptied and the row stays
-- until it runs out, so the device that made it can hear it was used.
CREATE TABLE links (
  code TEXT PRIMARY KEY,
  token TEXT NOT NULL,
  carry TEXT NOT NULL,
  expires INTEGER NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
) WITHOUT ROWID;
