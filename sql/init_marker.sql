SET client_min_messages = warning;

CREATE TABLE IF NOT EXISTS osm_import_complete (
    source_file text NOT NULL,
    source_size bigint,
    source_mtime bigint,
    style_sha256 text,
    imported_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE osm_import_complete
ADD COLUMN IF NOT EXISTS source_size bigint;

ALTER TABLE osm_import_complete
ADD COLUMN IF NOT EXISTS source_mtime bigint;

ALTER TABLE osm_import_complete
ADD COLUMN IF NOT EXISTS style_sha256 text;
