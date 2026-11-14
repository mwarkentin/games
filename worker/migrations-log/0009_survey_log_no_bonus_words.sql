-- Bonus words (s = 1, words the letters spell by chance) aren't kept in the
-- public log any more: sectors stop sending them (flushLog in src/survey.js),
-- and this takes out the ones already here. The delete triggers
-- (survey_log_uncounted, survey_log_guild_uncounted) take each out of the
-- hours', surveyors' and guilds' counts as it goes. Their sectors and the
-- game's field notes keep them.
DELETE FROM survey_log WHERE s = 1;
