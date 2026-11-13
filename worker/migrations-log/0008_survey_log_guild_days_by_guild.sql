-- The days a guild has words on, for the timelapse following it (see
-- "Following a guild" under "The timelapse" in SURVEY.md). Its daily counts
-- (0007) are keyed by day first, so without this a guild's days would mean
-- reading every guild's. The index holds no count, so a word only writes to
-- it on a guild's first word of a day.
CREATE INDEX survey_log_guild_days_by_guild ON survey_log_guild_days (guild, day);
