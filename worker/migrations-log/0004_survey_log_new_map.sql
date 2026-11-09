-- The map was redrawn (map 3: about 150 words a theme, MAP_VERSION in
-- src/letterfield-world.js), so every word logged so far names a place that
-- holds other letters now. The survey starts over, and so does its log:
-- sectors forget their claims when they next wake (survey.js), and this
-- empties the log and its counts.
--
-- The delete trigger would update three counts for every row, so it's set
-- aside while the rows go, then put back as it was in 0002, and the counts
-- are emptied outright.
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
