#!/usr/bin/env bash
# Setup script: PostgreSQL + PostGIS + Vietnam OSM data
# Run once before using generator_vi.py
set -e

echo "=== 1. Install PostgreSQL + PostGIS ==="
sudo apt-get update -qq
sudo apt-get install -y postgresql postgresql-contrib postgis osm2pgsql wget

echo "=== 2. Start PostgreSQL ==="
sudo systemctl start postgresql
sudo systemctl enable postgresql

echo "=== 3. Create database ==="
sudo -u postgres psql -c "CREATE DATABASE osm_vn;" 2>/dev/null || echo "DB already exists"
sudo -u postgres psql -d osm_vn -c "CREATE EXTENSION IF NOT EXISTS postgis;"
sudo -u postgres psql -d osm_vn -c "CREATE EXTENSION IF NOT EXISTS hstore;"

echo "=== 4. Download Vietnam OSM data (Geofabrik) ==="
mkdir -p /tmp/osm_data
cd /tmp/osm_data
if [ ! -f vietnam-latest.osm.pbf ]; then
    wget -c https://download.geofabrik.de/asia/vietnam-latest.osm.pbf
else
    echo "OSM file already downloaded"
fi

echo "=== 5. Load into PostGIS (osm2pgsql) ==="
# --hstore: store all OSM tags in hstore column (needed for amenity, tourism, etc.)
# --slim: lower memory usage
# Uses same schema as GS-QA: pois, roads, parks, lakes, regions tables
sudo -u postgres osm2pgsql \
    --database osm_vn \
    --create \
    --slim \
    --hstore \
    --number-processes 4 \
    /tmp/osm_data/vietnam-latest.osm.pbf

echo "=== 6. Create GS-QA compatible views ==="
sudo -u postgres psql -d osm_vn << 'SQL'
-- POIs view (points with amenity/tourism/shop/leisure tags)
CREATE OR REPLACE VIEW pois AS
SELECT
    osm_id AS id,
    way::geography AS geometry,
    name AS poi_name,
    osm_id,
    tags->'amenity' AS amenity,
    tags->'tourism' AS tourism,
    tags->'shop' AS shop,
    tags->'leisure' AS leisure,
    tags->'cuisine' AS cuisine,
    tags->'opening_hours' AS opening_hours,
    tags->'operator' AS operator,
    tags->'addr:city' AS addr_city,
    tags->'addr:street' AS addr_street,
    tags->'addr:housenumber' AS addr_housenumber,
    tags->'wikidata' AS wikidata,
    tags->'wikipedia' AS wikipedia
FROM planet_osm_point
WHERE (
    tags ? 'amenity' OR tags ? 'tourism' OR
    tags ? 'shop' OR tags ? 'leisure'
) AND name IS NOT NULL;

-- Roads view
CREATE OR REPLACE VIEW roads AS
SELECT
    osm_id,
    way::geography AS geometry,
    name AS road_name,
    tags->'highway' AS highway,
    tags->'wikidata' AS wikidata,
    tags->'wikipedia' AS wikipedia
FROM planet_osm_line
WHERE tags ? 'highway' AND name IS NOT NULL;

-- Parks view
CREATE OR REPLACE VIEW parks AS
SELECT
    osm_id,
    way::geography AS geometry,
    name AS park_name,
    tags->'leisure' AS leisure,
    tags->'wikidata' AS wikidata,
    tags->'wikipedia' AS wikipedia
FROM planet_osm_polygon
WHERE tags->'leisure' IN ('park','garden','nature_reserve') AND name IS NOT NULL;

-- Lakes/waterways view
CREATE OR REPLACE VIEW lakes AS
SELECT
    osm_id,
    way::geography AS geometry,
    name AS lake_name,
    tags->'waterway' AS waterway,
    tags->'water' AS water,
    tags->'wikidata' AS wikidata,
    tags->'wikipedia' AS wikipedia
FROM planet_osm_polygon
WHERE (tags ? 'waterway' OR tags->'natural' = 'water') AND name IS NOT NULL;
SQL

echo "=== 7. Install Python dependencies ==="
pip install -r requirements.txt

echo ""
echo "=== Setup complete! ==="
echo "Test: python generator_vi.py"
echo "Verify: python verify_vi.py --input questions_vi/ --spot-check 0.05"
