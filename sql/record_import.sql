SET client_min_messages = warning;

TRUNCATE osm_import_complete;

INSERT INTO osm_import_complete (
    source_file,
    source_md5,
    style_sha256
)
VALUES (
    :'source_file',
    :'source_md5',
    :'style_sha256'
);
