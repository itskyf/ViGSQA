SET client_min_messages = warning;

-- Import lineage is keyed on content identity (file name + the md5 Geofabrik
-- publishes for the extract), never size/mtime: the marker row ships inside
-- the release dump, where a maintainer-local timestamp would be meaningless.
CREATE TABLE IF NOT EXISTS osm_import_complete (
    source_file text NOT NULL,
    source_md5 text,
    style_sha256 text,
    imported_at timestamptz NOT NULL DEFAULT now()
);
