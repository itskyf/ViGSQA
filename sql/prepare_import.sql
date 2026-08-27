SET client_min_messages = warning;

DROP VIEW IF EXISTS pois;
DROP VIEW IF EXISTS roads;
DROP VIEW IF EXISTS parks;
DROP VIEW IF EXISTS lakes;

DROP TABLE IF EXISTS planet_osm_point;
DROP TABLE IF EXISTS planet_osm_roads;
DROP TABLE IF EXISTS planet_osm_line;
DROP TABLE IF EXISTS planet_osm_polygon;

DROP TABLE IF EXISTS planet_osm_nodes;
DROP TABLE IF EXISTS planet_osm_ways;
DROP TABLE IF EXISTS planet_osm_rels;
