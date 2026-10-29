-- One row per saved score. Each board keeps only its top 100 (see src/index.js).
CREATE TABLE scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game TEXT NOT NULL,
  board TEXT NOT NULL,
  initials TEXT NOT NULL,
  score INTEGER NOT NULL,
  level INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX scores_by_board ON scores (game, board, score DESC, created_at, id);

-- Recent submissions per hashed IP address, for rate limiting. Rows older than
-- an hour are deleted as new ones arrive.
CREATE TABLE submissions (
  ip_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX submissions_by_ip ON submissions (ip_hash, created_at);
