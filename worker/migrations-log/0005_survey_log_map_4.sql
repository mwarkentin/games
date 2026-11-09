-- Map 4 (MAP_VERSION in src/letterfield-world.js) lays out 225 themes, so a
-- territory's theme is now (rx + 15 ry) mod 225, as regionTheme in
-- src/letterfield-world.js. This redefines that column (0003) and its index.
-- It also empties the log again, as 0004 did: a pull request's preview
-- charted words on map 3 before map 4 replaced it. On a log 0004 has just
-- emptied, that part does nothing.
DROP INDEX survey_log_by_theme;
ALTER TABLE survey_log DROP COLUMN th;
ALTER TABLE survey_log ADD COLUMN th INTEGER
  GENERATED ALWAYS AS (((rx + 15 * ry) % 225 + 225) % 225) VIRTUAL;
CREATE INDEX survey_log_by_theme ON survey_log (th, at) WHERE s = 0;

DROP TRIGGER survey_log_uncounted;
DELETE FROM survey_log;
DELETE FROM survey_log_hours;
DELETE FROM survey_log_surveyors;
DELETE FROM survey_log_territories;
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
