-- Supernovas: territories whose every hidden word has been charted, for the
-- log page's list of them, its day and hour views and a territory's own view
-- (see "Supernovas" under "The log" in SURVEY.md).
--
-- A territory lies inside one sector, so its sector, which counts its hidden
-- words as claims come in, sees the claim that completes it and records the
-- supernova once (survey.js, Sector.supernova). The row is copied here in the
-- same batch as the claims, never before its last word, keyed by territory,
-- so a resent row is ignored. at is the last hidden word's time, first the
-- first's; w, x, y, d and initials are the last word and who charted it;
-- words is how many hidden words the territory has, surveyors how many sets
-- of initials charted them, and top and top_n who charted most and how many.
--
-- A new map empties this along with the rest of the log. Taking a word out of
-- the log for moderation doesn't change its supernova: delete or edit the
-- territory's row here too.
CREATE TABLE survey_log_novas (
  rx INTEGER NOT NULL,
  ry INTEGER NOT NULL,
  at INTEGER NOT NULL,
  w TEXT NOT NULL,
  x INTEGER NOT NULL,
  y INTEGER NOT NULL,
  d INTEGER NOT NULL,
  initials TEXT NOT NULL,
  first INTEGER NOT NULL,
  words INTEGER NOT NULL,
  surveyors INTEGER NOT NULL,
  top TEXT NOT NULL,
  top_n INTEGER NOT NULL,
  PRIMARY KEY (rx, ry)
) WITHOUT ROWID;

-- The list, newest first, over a range of time.
CREATE INDEX survey_log_novas_by_time ON survey_log_novas (at, rx, ry);
