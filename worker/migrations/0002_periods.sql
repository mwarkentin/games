-- Scores are no longer trimmed to a top 100, so every view needs an index
-- that finds its rows directly: by one filter alone, and by date for views of
-- a recent period. The Worker names the index for each query (INDEXED BY).
CREATE INDEX scores_by_difficulty ON scores (game, scope, difficulty, score DESC, created_at, id);
CREATE INDEX scores_by_mode ON scores (game, scope, mode, score DESC, created_at, id);
CREATE INDEX scores_by_time ON scores (game, scope, created_at);
