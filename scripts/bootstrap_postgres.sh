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
# Querying the views exercises PostGIS functions, so a missing extension
# fails the psql call itself; here only the non-empty results need asserting.
if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	COUNTS="$(psql \
		--tuples-only --no-align --set=ON_ERROR_STOP=1 \
		--file="${SQL_DIR}/count_reference_tables.sql")"
else
	COUNTS="$(podman compose exec --no-tty postgres psql \
		--username="${PGUSER}" --dbname="${PGDATABASE}" \
		--tuples-only --no-align --set=ON_ERROR_STOP=1 \
		<"${SQL_DIR}/count_reference_tables.sql")"
fi

EMPTY_TABLES=()
while IFS='|' read -r TABLE_NAME TABLE_COUNT; do
	TABLE_COUNT="${TABLE_COUNT//[[:space:]]/}"
	TABLE_NAME="${TABLE_NAME//[[:space:]]/}"
	echo "[INFO] ${TABLE_NAME}: ${TABLE_COUNT} rows"
	((TABLE_COUNT > 0)) || EMPTY_TABLES+=("${TABLE_NAME}")
done < <(printf '%s\n' "${COUNTS}")

if ((${#EMPTY_TABLES[@]} > 0)); then
	echo "[ERROR] Reference tables absent or empty: ${EMPTY_TABLES[*]}" >&2
	exit 1
fi
echo "[INFO] PostgreSQL branch ready."
