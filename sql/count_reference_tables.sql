-- Health check: every reference table must be present and non-empty before
-- benchmark generation or inference runs.
SELECT
    'pois' AS table_name,
    COUNT(*) AS row_count
FROM pois
UNION ALL
SELECT
    'regions' AS table_name,
    COUNT(*) AS row_count
FROM regions
UNION ALL
SELECT
    'parks' AS table_name,
    COUNT(*) AS row_count
FROM parks
UNION ALL
SELECT
    'lakes' AS table_name,
    COUNT(*) AS row_count
FROM lakes
UNION ALL
SELECT
    'roads' AS table_name,
    COUNT(*) AS row_count
FROM roads
ORDER BY table_name;
