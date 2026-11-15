-- 0009 ran ahead of the deploy that stopped sectors sending bonus words
-- (the deploy applies migrations first), so a sector still on the old code
-- could copy a few more in that minute. This takes those out the same way;
-- the delete triggers take each out of the counts. It does nothing where
-- there are none.
DELETE FROM survey_log WHERE s = 1;
