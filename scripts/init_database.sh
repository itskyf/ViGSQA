#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
SQL_DIR="${REPO_ROOT}/sql"

# libpq connection variables: shared with the compose container (compose.yaml)
# and the Colab-local server started by install_dependencies.sh.
: "${PGHOST:=127.0.0.1}" "${PGPORT:=5432}" "${PGUSER:=postgres}" "${PGPASSWORD:=postgres}" "${PGDATABASE:=osm_vn}"
export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE

echo "[INFO] Checking database '${PGDATABASE}'..."
DB_EXISTS="$(
	psql \
		--dbname=postgres \
		--tuples-only \
		--no-align \
		--command="SELECT 1 FROM pg_database WHERE datname = '${PGDATABASE}';"
)"

if [[ "${DB_EXISTS}" != "1" ]]; then
	echo "[INFO] Creating database '${PGDATABASE}'..."
	createdb
else
	echo "[INFO] Database '${PGDATABASE}' already exists."
fi

echo "[INFO] Configuring PostGIS extension and database credentials..."
psql \
	--quiet \
	--set=ON_ERROR_STOP=1 \
	--file="${SQL_DIR}/init_database.sql"

echo "[INFO] Database '${PGDATABASE}' initialization complete."
