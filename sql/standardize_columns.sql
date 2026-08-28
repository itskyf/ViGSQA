SET client_min_messages = warning;

ALTER TABLE planet_osm_point RENAME COLUMN node_id TO osm_id;
