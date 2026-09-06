-- Fast-path probe for scripts/restore_database.sh: returns 1 when every
-- reference object exists, zero rows otherwise. Only to_regclass is
-- referenced, so a fresh database yields an empty result instead of a parse
-- error (check_import.sql additionally requires snapshot-lineage variables
-- that a fresh environment cannot supply).
SELECT 1
WHERE
    to_regclass('public.planet_osm_point') IS NOT NULL
    AND to_regclass('public.planet_osm_region') IS NOT NULL
    AND to_regclass('public.planet_osm_park') IS NOT NULL
    AND to_regclass('public.planet_osm_lake') IS NOT NULL
    AND to_regclass('public.planet_osm_road') IS NOT NULL
    AND to_regclass('public.pois') IS NOT NULL
    AND to_regclass('public.regions') IS NOT NULL
    AND to_regclass('public.parks') IS NOT NULL
    AND to_regclass('public.lakes') IS NOT NULL
    AND to_regclass('public.roads') IS NOT NULL
    AND to_regclass('public.osm_import_complete') IS NOT NULL;
