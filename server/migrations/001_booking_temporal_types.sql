-- Back up the database before applying this migration to an existing deployment.
-- Verify that the following query returns zero rows first:
-- SELECT id, date, begin, end FROM bookings
-- WHERE (date IS NOT NULL AND STR_TO_DATE(date, '%Y-%m-%d') IS NULL)
--    OR (begin IS NOT NULL AND STR_TO_DATE(begin, '%H:%i') IS NULL)
--    OR (end IS NOT NULL AND STR_TO_DATE(end, '%H:%i') IS NULL);

ALTER TABLE bookings
  MODIFY COLUMN date DATE NULL,
  MODIFY COLUMN begin TIME NULL,
  MODIFY COLUMN end TIME NULL,
  DROP INDEX idx_date,
  ADD INDEX idx_date_id (date, id);
