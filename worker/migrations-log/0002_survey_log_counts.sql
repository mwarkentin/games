-- Counts of the survey log, for its week, month, year and all-time views
-- (see "Counts" under "The log" in SURVEY.md). Reading a month of the log
-- itself could mean a million rows, so these keep running totals instead:
--
--   survey_log_hours        words charted in each UTC hour (hours since
--                           1970), and how many were hidden words in the
--                           shared world (sectors -12 to 12, as AREA in
--                           src/survey.js), which count toward its total;
--   survey_log_surveyors    hidden and stray words per UTC day (days since
--                           1970) per set of initials, for top surveyors;
--   survey_log_territories  hidden words per UTC day per territory, for top
--                           territories and themes.
--
-- Triggers keep them in step with survey_log in the same transaction as
-- each insert or delete. INSERT OR IGNORE skips a row it already has
-- without firing them, so a sector resending a batch counts nothing twice.

CREATE TABLE survey_log_hours (
  hour INTEGER PRIMARY KEY,
  n INTEGER NOT NULL,
  world INTEGER NOT NULL
) WITHOUT ROWID;

CREATE TABLE survey_log_surveyors (
  day INTEGER NOT NULL,
  initials TEXT NOT NULL,
  n INTEGER NOT NULL,
  PRIMARY KEY (day, initials)
) WITHOUT ROWID;

CREATE TABLE survey_log_territories (
  day INTEGER NOT NULL,
  rx INTEGER NOT NULL,       -- territories are 48 cells a side, rx = floor(x / 48)
  ry INTEGER NOT NULL,
  n INTEGER NOT NULL,
  PRIMARY KEY (day, rx, ry)
) WITHOUT ROWID;

-- SQLite's integer division rounds toward zero, so floor(x / 48) for a
-- negative x is (x - 47) / 48. The shared world is x and y from -2304 up to
-- 2496 (sectors of 192 cells, -12 to 12).
CREATE TRIGGER survey_log_counted AFTER INSERT ON survey_log BEGIN
  INSERT INTO survey_log_hours (hour, n, world)
    VALUES (NEW.at / 3600000, 1,
      NEW.s = 0 AND NEW.x >= -2304 AND NEW.x < 2496 AND NEW.y >= -2304 AND NEW.y < 2496)
    ON CONFLICT (hour) DO UPDATE SET n = n + 1, world = world + excluded.world;
  INSERT INTO survey_log_surveyors (day, initials, n)
    SELECT NEW.at / 86400000, NEW.initials, 1 WHERE NEW.initials <> ''
    ON CONFLICT (day, initials) DO UPDATE SET n = n + 1;
  INSERT INTO survey_log_territories (day, rx, ry, n)
    SELECT NEW.at / 86400000,
      (NEW.x - CASE WHEN NEW.x < 0 THEN 47 ELSE 0 END) / 48,
      (NEW.y - CASE WHEN NEW.y < 0 THEN 47 ELSE 0 END) / 48, 1
    WHERE NEW.s = 0
    ON CONFLICT (day, rx, ry) DO UPDATE SET n = n + 1;
END;

-- Removing a row (moderation, say) takes it out of the counts too.
CREATE TRIGGER survey_log_uncounted AFTER DELETE ON survey_log BEGIN
  UPDATE survey_log_hours SET n = n - 1,
    world = world - (OLD.s = 0 AND OLD.x >= -2304 AND OLD.x < 2496 AND OLD.y >= -2304 AND OLD.y < 2496)
    WHERE hour = OLD.at / 3600000;
  UPDATE survey_log_surveyors SET n = n - 1
    WHERE OLD.initials <> '' AND day = OLD.at / 86400000 AND initials = OLD.initials;
  UPDATE survey_log_territories SET n = n - 1
    WHERE OLD.s = 0 AND day = OLD.at / 86400000
      AND rx = (OLD.x - CASE WHEN OLD.x < 0 THEN 47 ELSE 0 END) / 48
      AND ry = (OLD.y - CASE WHEN OLD.y < 0 THEN 47 ELSE 0 END) / 48;
END;

-- Words logged before these tables existed. The triggers come first and
-- these set absolute numbers, so a word logged while this runs is counted
-- once either way. ("WHERE true" keeps SQLite from reading ON CONFLICT as
-- part of the SELECT.)
INSERT INTO survey_log_hours (hour, n, world)
  SELECT at / 3600000, COUNT(*),
    SUM(s = 0 AND x >= -2304 AND x < 2496 AND y >= -2304 AND y < 2496)
  FROM survey_log WHERE true GROUP BY at / 3600000
  ON CONFLICT (hour) DO UPDATE SET n = excluded.n, world = excluded.world;
INSERT INTO survey_log_surveyors (day, initials, n)
  SELECT at / 86400000, initials, COUNT(*) FROM survey_log WHERE initials <> ''
  GROUP BY at / 86400000, initials
  ON CONFLICT (day, initials) DO UPDATE SET n = excluded.n;
INSERT INTO survey_log_territories (day, rx, ry, n)
  SELECT at / 86400000, (x - CASE WHEN x < 0 THEN 47 ELSE 0 END) / 48,
    (y - CASE WHEN y < 0 THEN 47 ELSE 0 END) / 48, COUNT(*)
  FROM survey_log WHERE s = 0 GROUP BY 1, 2, 3
  ON CONFLICT (day, rx, ry) DO UPDATE SET n = excluded.n;
