SET client_min_messages = warning;

TRUNCATE osm_import_complete;

INSERT INTO osm_import_complete (
    source_file,
    source_size,
    source_mtime,
    style_sha256
)
VALUES (
    :'source_file',
    :'source_size'::bigint,
    :'source_mtime'::bigint,
    :'style_sha256'
);
