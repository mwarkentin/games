-- Guilds in the survey log: each word's guild, for a guild's own page in the
-- log and the top guilds of a period (see "Guilds" under "The log" in
-- SURVEY.md).
--
-- guild is the log id of the guild its charter was in when they charted it
-- (a random id of its own, never the tag their caret wears or the code that
-- invites), and '' for anyone in no guild or off the surveyor list. A sector
-- knows it at claim time from its check with the guild (survey-guild.js).
-- Words logged before this have none.
ALTER TABLE survey_log ADD COLUMN guild TEXT NOT NULL DEFAULT '';

-- A guild's words, through their own index; words in no guild cost nothing.
CREATE INDEX survey_log_by_guild ON survey_log (guild, at) WHERE guild <> '';

-- Words per UTC day per guild, for top guilds, kept by triggers as rows go in
-- and out, as 0002's counts are.
CREATE TABLE survey_log_guild_days (
  day INTEGER NOT NULL,
  guild TEXT NOT NULL,
  n INTEGER NOT NULL,
  PRIMARY KEY (day, guild)
) WITHOUT ROWID;

CREATE TRIGGER survey_log_guild_counted AFTER INSERT ON survey_log WHEN NEW.guild <> '' BEGIN
  INSERT INTO survey_log_guild_days (day, guild, n) VALUES (NEW.at / 86400000, NEW.guild, 1)
    ON CONFLICT (day, guild) DO UPDATE SET n = n + 1;
END;

CREATE TRIGGER survey_log_guild_uncounted AFTER DELETE ON survey_log WHEN OLD.guild <> '' BEGIN
  UPDATE survey_log_guild_days SET n = n - 1 WHERE day = OLD.at / 86400000 AND guild = OLD.guild;
END;

-- Each guild's name, three words from the game's lists (GUILD_FIRST,
-- GUILD_SECOND and GUILD_THIRD in src/survey-guild.js), sent once by the
-- sectors with its first claims. Names never change, and a guild that ends
-- keeps its name here, with its words.
CREATE TABLE survey_log_guilds (
  guild TEXT PRIMARY KEY,
  a INTEGER NOT NULL,
  b INTEGER NOT NULL,
  c INTEGER NOT NULL
) WITHOUT ROWID;
