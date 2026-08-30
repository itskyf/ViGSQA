#!/usr/bin/env bash
# Restore the LangChain LLM cache database (T09) from a scripts/export_llm_cache.sh
# dump. Restore means replace: the dump's --clean section drops existing objects,
# so re-running over the current database is safe and idempotent. Unlike
# restore_database.sh there is no skip-if-populated — the cache must be verified
# after restore (row count asserted at the end).
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
SQL_DIR="${REPO_ROOT}/sql"

LLM_CACHE_DB="${LLM_CACHE_DBNAME:-llm_cache}"
DUMP_FILE="${1:?usage: ${0##*/} <llm-cache-YYYYMMDD.sql.gz>}"

: "${PGHOST:?PGHOST is required}" "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}" "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:?PGDATABASE is required}"

if [[ ! -s "${DUMP_FILE}" ]]; then
	echo "[ERROR] dump not found or empty: ${DUMP_FILE}" >&2
	exit 1
fi

psql_stream() {
	podman compose exec --no-tty postgres psql \
		--username="${PGUSER}" --dbname="${LLM_CACHE_DB}" \
		--quiet --set=ON_ERROR_STOP=1
}

./scripts/start_postgres.sh

# Local psql runs inside the container, so the SQL arrives via stdin.
DB_EXISTS="$(podman compose exec --no-tty postgres psql \
	--username="${PGUSER}" --dbname=postgres \
	--tuples-only --no-align \
	--set=db_name="${LLM_CACHE_DB}" --set=db_user="${PGUSER}" \
	<"${SQL_DIR}/check_database.sql")"
if [[ "${DB_EXISTS%%|*}" != "1" ]]; then
	echo "[INFO] Creating the LLM cache database '${LLM_CACHE_DB}'..."
	podman compose exec --no-tty postgres createdb \
		--username="${PGUSER}" --owner="${PGUSER}" "${LLM_CACHE_DB}"
fi

echo "[INFO] Restoring LLM cache from $(basename "${DUMP_FILE}")..."
gzip --decompress --stdout "${DUMP_FILE}" | psql_stream

ROWS="$(podman compose exec --no-tty postgres psql \
	--username="${PGUSER}" --dbname="${LLM_CACHE_DB}" \
	--tuples-only --no-align --set=ON_ERROR_STOP=1 \
	<"${SQL_DIR}/count_llm_cache.sql")"
if [[ "${ROWS//[[:space:]]/}" == "0" ]]; then
	echo "[ERROR] restored cache is empty." >&2
	exit 1
fi
echo "[INFO] LLM cache restore complete: ${ROWS//[$'\t\r ']/} cached generations."
