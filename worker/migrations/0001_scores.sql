-- Private groups, joined by sharing their four-character code.
CREATE TABLE groups (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

-- One row per saved game per place it's shown: scope '*' is the public
-- board, any other scope is a group code. Copies of one game share an entry
-- id. Each (game, scope, difficulty, mode) keeps its top 100 (see src/leaderboard.js).
CREATE TABLE scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry TEXT NOT NULL,
  game TEXT NOT NULL,
  scope TEXT NOT NULL,
  difficulty TEXT NOT NULL,
  mode TEXT NOT NULL,
  initials TEXT NOT NULL,
  score INTEGER NOT NULL,
  level INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX scores_by_board ON scores (game, scope, difficulty, mode, score DESC, created_at, id);
CREATE INDEX scores_by_scope ON scores (game, scope, score DESC, created_at, id);

-- Recent writes per hashed IP address, for rate limiting. Rows older than an
-- hour are deleted as new ones arrive.
CREATE TABLE submissions (
  kind TEXT NOT NULL,
  ip_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX submissions_by_ip ON submissions (kind, ip_hash, created_at);
