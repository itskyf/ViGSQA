#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

case "$#" in
0) ;;
1)
	if [[ "$1" != "--wait-only" ]]; then
		echo "[ERROR] Unknown argument: $1" >&2
		exit 2
	fi
	;;
*)
	echo "[ERROR] Usage: ${0##*/} [--wait-only]" >&2
	exit 2
	;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
SQL_DIR="${REPO_ROOT}/sql"

: "${PGHOST:?PGHOST is required}" "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}" "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:?PGDATABASE is required}"

echo "[INFO] PostgreSQL branch: checking dependencies..."
./scripts/install_dependencies.sh

echo "[INFO] PostgreSQL branch: starting the service..."
./scripts/start_postgres.sh "$@"

echo "[INFO] PostgreSQL branch: initializing when required..."
./scripts/init_database.sh

# Priority: prebuilt release dump > raw osm2pgsql import. restore_database.sh
# skips a populated database, so repeat bootstraps no-op whichever path ran
# first. DB_RESTORE=0 forces the raw import.
if [[ "${DB_RESTORE:-1}" != "0" ]] && ./scripts/restore_database.sh; then
	echo "[INFO] PostgreSQL branch: reference database restored from the release asset."
else
	echo "[INFO] PostgreSQL branch: building from the pinned OSM snapshot..."
	./scripts/download_osm.sh
	./scripts/import_osm.sh
fi

# The LangChain LLM cache lives in its own logical database so restoring or
# clearing it can never touch the OSM reference data. The cache table itself is
# created by SQLAlchemyMd5Cache on first use — no schema SQL here.
LLM_CACHE_DB="${LLM_CACHE_DBNAME:-llm_cache}"
if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	DB_EXISTS="$(psql --tuples-only --no-align \
		--set=db_name="${LLM_CACHE_DB}" --set=db_user="${PGUSER}" \
		--file="${SQL_DIR}/check_database.sql")"
else
	# Local psql runs inside the container, so the SQL arrives via stdin.
	DB_EXISTS="$(podman compose exec --no-tty postgres psql \
		--username="${PGUSER}" --dbname=postgres \
		--tuples-only --no-align \
		--set=db_name="${LLM_CACHE_DB}" --set=db_user="${PGUSER}" \
		<"${SQL_DIR}/check_database.sql")"
fi
if [[ "${DB_EXISTS%%|*}" != "1" ]]; then
	echo "[INFO] PostgreSQL branch: creating the LLM cache database '${LLM_CACHE_DB}'..."
	if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
		runuser -u postgres -- createdb --owner="${PGUSER}" "${LLM_CACHE_DB}"
	else
		podman compose exec --no-tty postgres createdb \
			--username="${PGUSER}" --owner="${PGUSER}" "${LLM_CACHE_DB}"
	fi
else
	echo "[INFO] PostgreSQL branch: LLM cache database '${LLM_CACHE_DB}' already exists."
fi

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
