SET client_min_messages = warning;

CREATE INDEX IF NOT EXISTS planet_osm_point_geography_idx
ON planet_osm_point
USING gist ((ST_TRANSFORM(way, 4326)::geography));

CREATE OR REPLACE VIEW pois AS
SELECT
    osm_id AS id,
    name AS poi_name,
    amenity,
    tourism,
    shop,
    leisure,
    ST_TRANSFORM(way, 4326)::geography AS geometry,
    ST_ASTEXT(ST_TRANSFORM(way, 4326)) AS geo_wkt
FROM planet_osm_point;

ANALYZE planet_osm_point;
