SELECT 1
FROM public.osm_import_complete
WHERE
    source_file = :'source_file'
    AND source_size = :'source_size'::bigint
    AND source_mtime = :'source_mtime'::bigint
    AND style_sha256 = :'style_sha256'
    AND to_regclass('public.planet_osm_point') IS NOT NULL
    AND to_regclass('public.pois') IS NOT NULL
ORDER BY imported_at DESC
LIMIT 1;
