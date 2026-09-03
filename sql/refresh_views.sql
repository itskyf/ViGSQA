SET client_min_messages = warning;

-- One GiST geography index per reference table to support spatial queries;
-- planner choice is not a correctness gate.
CREATE INDEX IF NOT EXISTS planet_osm_point_geography_idx
ON planet_osm_point
USING gist ((ST_TRANSFORM(way, 4326)::geography));

CREATE INDEX IF NOT EXISTS planet_osm_region_geography_idx
ON planet_osm_region
USING gist ((way::geography));

CREATE INDEX IF NOT EXISTS planet_osm_park_geography_idx
ON planet_osm_park
USING gist ((way::geography));

CREATE INDEX IF NOT EXISTS planet_osm_lake_geography_idx
ON planet_osm_lake
USING gist ((way::geography));

CREATE INDEX IF NOT EXISTS planet_osm_road_geography_idx
ON planet_osm_road
USING gist ((way::geography));

CREATE OR REPLACE VIEW pois AS
SELECT
    osm_id AS id,
    name AS poi_name,
    amenity,
    tourism,
    shop,
    leisure,
    cuisine,
    museum,
    takeaway,
    outdoor_seating,
    delivery,
    emergency,
    wikidata,
    wikipedia,
    addr_housenumber,
    addr_street,
    addr_place,
    addr_suburb,
    addr_district,
    addr_city,
    addr_province,
    addr_postcode,
    ST_TRANSFORM(way, 4326)::geography AS geometry,
    ST_ASTEXT(ST_TRANSFORM(way, 4326)) AS geo_wkt
FROM planet_osm_point;

-- Regions are admin-boundary relations only, so osm_id is already unique.
CREATE OR REPLACE VIEW regions AS
SELECT
    osm_id AS id,
    name AS region_name,
    admin_level,
    way::geography AS geometry,
    ST_ASTEXT(way) AS geo_wkt
FROM planet_osm_region;

-- Parks/lakes mix ways and relations: offset relation ids into a separate
-- numeric namespace so view ids stay unique per table (stable per snapshot).
CREATE OR REPLACE VIEW parks AS
SELECT
    park_name,
    leisure,
    way::geography AS geometry,
    (CASE osm_type WHEN 'R' THEN 1000000000000 ELSE 0 END + osm_id) AS id,
    ST_ASTEXT(way) AS geo_wkt
FROM planet_osm_park;

CREATE OR REPLACE VIEW lakes AS
SELECT
    lake_name,
    waterway,
    water,
    way::geography AS geometry,
    (CASE osm_type WHEN 'R' THEN 1000000000000 ELSE 0 END + osm_id) AS id,
    ST_ASTEXT(way) AS geo_wkt
FROM planet_osm_lake;

CREATE OR REPLACE VIEW roads AS
SELECT
    osm_id AS id,
    road_name,
    highway,
    way::geography AS geometry,
    ST_ASTEXT(way) AS geo_wkt
FROM planet_osm_road;

ANALYZE planet_osm_point;
ANALYZE planet_osm_region;
ANALYZE planet_osm_park;
ANALYZE planet_osm_lake;
ANALYZE planet_osm_road;
