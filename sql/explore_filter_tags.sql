-- Read-only exploration used to derive generator/filter_labels_vi.json from
-- the pinned snapshot's actual tag values. Kept for reproducibility.
SELECT
    'cuisine' AS tag,
    cuisine AS tag_value,
    COUNT(*) AS n
FROM pois
WHERE cuisine IS NOT NULL
GROUP BY cuisine
UNION ALL
SELECT
    'museum' AS tag,
    museum AS tag_value,
    COUNT(*) AS n
FROM pois
WHERE museum IS NOT NULL
GROUP BY museum
UNION ALL
SELECT
    'takeaway' AS tag,
    takeaway AS tag_value,
    COUNT(*) AS n
FROM pois
WHERE takeaway IS NOT NULL
GROUP BY takeaway
UNION ALL
SELECT
    'outdoor_seating' AS tag,
    outdoor_seating AS tag_value,
    COUNT(*) AS n
FROM pois
WHERE outdoor_seating IS NOT NULL
GROUP BY outdoor_seating
UNION ALL
SELECT
    'delivery' AS tag,
    delivery AS tag_value,
    COUNT(*) AS n
FROM pois
WHERE delivery IS NOT NULL
GROUP BY delivery
UNION ALL
SELECT
    'emergency' AS tag,
    emergency AS tag_value,
    COUNT(*) AS n
FROM pois
WHERE emergency IS NOT NULL
GROUP BY emergency
ORDER BY tag ASC, n DESC;
