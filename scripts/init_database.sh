#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
SQL_DIR="${REPO_ROOT}/sql"

: "${PGHOST:?PGHOST is required}" "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}" "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:?PGDATABASE is required}"

if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	echo "[INFO] Initializing the Colab PostgreSQL database."
else
	echo "[INFO] Local database initialization is owned by compose."
	exit 0
fi

echo "[INFO] Checking database '${PGDATABASE}'..."
admin_query() {
	runuser -u postgres -- psql \
		--host=/var/run/postgresql \
		--username=postgres \
		--dbname=postgres \
		--tuples-only \
		--no-align \
		"$@"
}

EXISTS="$(
	admin_query \
		--set=db_name="${PGDATABASE}" \
		--set=db_user="${PGUSER}" \
		--file="${SQL_DIR}/check_database.sql"
)"
IFS='|' read -r DB_EXISTS ROLE_EXISTS <<<"${EXISTS}"

if [[ "${ROLE_EXISTS}" != "1" ]]; then
	echo "[INFO] Creating database role '${PGUSER}'..."
	runuser -u postgres -- createuser --host=/var/run/postgresql \
		--username=postgres --login "${PGUSER}"
fi

if [[ "${DB_EXISTS}" != "1" ]]; then
	echo "[INFO] Creating database '${PGDATABASE}'..."
	runuser -u postgres -- createdb \
		--host=/var/run/postgresql --username=postgres \
		--owner="${PGUSER}" "${PGDATABASE}"
else
	echo "[INFO] Database '${PGDATABASE}' already exists."
fi

echo "[INFO] Configuring database credentials and PostGIS extension..."
runuser -u postgres -- psql \
	--host=/var/run/postgresql \
	--username=postgres \
	--dbname="${PGDATABASE}" \
	--quiet \
	--set=ON_ERROR_STOP=1 \
	--set=db_user="${PGUSER}" \
	--set=db_password="${PGPASSWORD}" \
	--file="${SQL_DIR}/init_database.sql"
echo "[INFO] Database '${PGDATABASE}' initialization complete."
