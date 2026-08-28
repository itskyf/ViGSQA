SELECT 1
FROM public.osm_import_complete
WHERE
    source_file = :'source_file'
    AND source_size = :'source_size'::bigint
    AND source_mtime = :'source_mtime'::bigint
    AND style_sha256 = :'style_sha256'
    AND to_regclass('public.planet_osm_point') IS NOT NULL
    AND to_regclass('public.planet_osm_region') IS NOT NULL
    AND to_regclass('public.planet_osm_park') IS NOT NULL
    AND to_regclass('public.planet_osm_lake') IS NOT NULL
    AND to_regclass('public.planet_osm_road') IS NOT NULL
    AND to_regclass('public.pois') IS NOT NULL
    AND to_regclass('public.regions') IS NOT NULL
    AND to_regclass('public.parks') IS NOT NULL
    AND to_regclass('public.lakes') IS NOT NULL
    AND to_regclass('public.roads') IS NOT NULL
ORDER BY imported_at DESC
LIMIT 1;
