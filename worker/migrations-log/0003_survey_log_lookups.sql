-- Ways into the survey log other than by time, for the log page's views of
-- one surveyor, one territory or one theme (see "Surveyors, territories and
-- themes" under "The log" in SURVEY.md).
--
-- A territory and its theme are worked out from a word's start cell, as the
-- game does, in virtual columns: nothing more is stored per row, only in the
-- indexes. Territories are 48 cells a side, and SQLite's integer division
-- rounds toward zero, so floor(x / 48) for a negative x is (x - 47) / 48. A
-- territory's theme is (rx + 21 ry) mod 116, as regionTheme in
-- src/letterfield-world.js (LAT_B and the number of themes).
ALTER TABLE survey_log ADD COLUMN rx INTEGER
  GENERATED ALWAYS AS ((x - CASE WHEN x < 0 THEN 47 ELSE 0 END) / 48) VIRTUAL;
ALTER TABLE survey_log ADD COLUMN ry INTEGER
  GENERATED ALWAYS AS ((y - CASE WHEN y < 0 THEN 47 ELSE 0 END) / 48) VIRTUAL;
ALTER TABLE survey_log ADD COLUMN th INTEGER
  GENERATED ALWAYS AS (((rx + 21 * ry) % 116 + 116) % 116) VIRTUAL;

-- A surveyor's words (unsigned ones aren't anyone's); every word in a
-- territory; a theme's hidden words (a stray's theme is its word's, not its
-- territory's). Each costs a row written per word that goes in it.
CREATE INDEX survey_log_by_initials ON survey_log (initials, at) WHERE initials <> '';
CREATE INDEX survey_log_by_territory ON survey_log (rx, ry, at);
CREATE INDEX survey_log_by_theme ON survey_log (th, at) WHERE s = 0;
