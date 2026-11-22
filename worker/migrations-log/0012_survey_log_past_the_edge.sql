-- The universe ends at its edge: sectors -12 to 12 each way (AREA in
-- src/survey.js), x and y from -2304 up to 2496, territories -48 to 51. Past
-- it lie the void, a ring one sector wide with nothing to find, and the
-- wilds, where the game surveys alone and keeps every find in the surveyor's
-- own field notes (see "The edge, the void and the wilds" in SURVEY.md).
-- Nothing past the edge is shared, so the words logged out there before, and
-- their supernovas, leave the log. The delete triggers (0002's, 0007's and
-- 0011's) take each word out of the hours', surveyors', territories' and
-- guilds' counts, with its other guilds. Sectors out there send nothing now:
-- the Worker routes nothing to them, and one woken anyway forgets its claims.
DELETE FROM survey_log WHERE x < -2304 OR x >= 2496 OR y < -2304 OR y >= 2496;
DELETE FROM survey_log_novas WHERE rx < -48 OR rx >= 52 OR ry < -48 OR ry >= 52;
