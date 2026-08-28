#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
SQL_DIR="${REPO_ROOT}/sql"

echo "[INFO] PostgreSQL branch: checking dependencies..."
./scripts/install_dependencies.sh

echo "[INFO] PostgreSQL branch: starting the service..."
./scripts/start_postgres.sh

echo "[INFO] PostgreSQL branch: initializing when required..."
./scripts/init_database.sh

echo "[INFO] PostgreSQL branch: preparing the pinned OSM snapshot..."
./scripts/download_osm.sh
./scripts/import_osm.sh

echo "[INFO] PostgreSQL branch: validating the import..."
# Querying the pois view exercises PostGIS functions, so a missing extension
# fails the psql call itself; here only the non-empty result needs asserting.
if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	POI_COUNT="$(psql \
		--tuples-only --no-align --set=ON_ERROR_STOP=1 \
		--file="${SQL_DIR}/count_pois.sql")"
else
	POI_COUNT="$(podman compose exec --no-tty postgres psql \
		--username="${PGUSER}" --dbname="${PGDATABASE}" \
		--tuples-only --no-align --set=ON_ERROR_STOP=1 \
		<"${SQL_DIR}/count_pois.sql")"
fi
((POI_COUNT > 0))
echo "[INFO] PostgreSQL branch ready: ${POI_COUNT} POIs."
