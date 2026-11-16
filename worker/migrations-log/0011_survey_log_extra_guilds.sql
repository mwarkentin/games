-- A surveyor can be in up to five guilds at once (see "Guilds" in SURVEY.md),
-- and a word counts for every guild its charter was in when they charted it.
--
-- survey_log.guild keeps the first of them, in the surveyor's own order, as
-- it always has, with its index (0007) and the triggers that count it into
-- survey_log_guild_days. This table holds the others, one row each, and
-- counts them into the same daily counts. A word in one guild, or in none,
-- adds nothing here, and a Worker from before this reads the log as it did.
CREATE TABLE survey_log_extra_guilds (
  guild TEXT NOT NULL,       -- the guild's log id, as survey_log.guild
  at INTEGER NOT NULL,       -- the word's, as in survey_log
  key TEXT NOT NULL,
  PRIMARY KEY (guild, at, key)
) WITHOUT ROWID;

-- Each word's other guilds, for counting a period's guilds over hours and for
-- taking them out with the word.
CREATE INDEX survey_log_extra_guilds_by_word ON survey_log_extra_guilds (at, key);

CREATE TRIGGER survey_log_extra_guild_counted AFTER INSERT ON survey_log_extra_guilds BEGIN
  INSERT INTO survey_log_guild_days (day, guild, n) VALUES (NEW.at / 86400000, NEW.guild, 1)
    ON CONFLICT (day, guild) DO UPDATE SET n = n + 1;
END;

CREATE TRIGGER survey_log_extra_guild_uncounted AFTER DELETE ON survey_log_extra_guilds BEGIN
  UPDATE survey_log_guild_days SET n = n - 1 WHERE day = OLD.at / 86400000 AND guild = OLD.guild;
END;

-- A word that leaves the log takes its other guilds with it.
CREATE TRIGGER survey_log_extra_guilds_gone AFTER DELETE ON survey_log BEGIN
  DELETE FROM survey_log_extra_guilds WHERE at = OLD.at AND key = OLD.key;
END;
