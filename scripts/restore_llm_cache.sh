#!/usr/bin/env bash
# Restore the LangChain LLM cache database from a scripts/export_llm_cache.sh
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
	if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
		psql --username="${PGUSER}" --dbname="${LLM_CACHE_DB}" \
			--quiet --set=ON_ERROR_STOP=1
	else
		podman compose exec --no-tty postgres psql \
			--username="${PGUSER}" --dbname="${LLM_CACHE_DB}" \
			--quiet --set=ON_ERROR_STOP=1
	fi
}

./scripts/start_postgres.sh

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
	echo "[INFO] Creating the LLM cache database '${LLM_CACHE_DB}'..."
	if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
		runuser -u postgres -- createdb --owner="${PGUSER}" "${LLM_CACHE_DB}"
	else
		podman compose exec --no-tty postgres createdb \
			--username="${PGUSER}" --owner="${PGUSER}" "${LLM_CACHE_DB}"
	fi
fi

echo "[INFO] Restoring LLM cache from $(basename "${DUMP_FILE}")..."
if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	# The dump is produced by PostgreSQL 18 / psql 18 and restored into 14/3.4
	# on Colab; these filters remove exactly the 18-only lines (identical
	# filters to scripts/restore_database.sh — COPY data can never match: JSON
	# text never starts with a lone backslash, which COPY escaping always
	# doubles) or ON_ERROR_STOP aborts the restore.
	gzip --decompress --stdout "${DUMP_FILE}" | sed \
		--expression '/^SET transaction_timeout = 0;$/d' \
		--expression '/^\\restrict /d' \
		--expression '/^\\unrestrict /d' |
		psql_stream
else
	gzip --decompress --stdout "${DUMP_FILE}" | psql_stream
fi

if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	ROWS="$(psql --username="${PGUSER}" --dbname="${LLM_CACHE_DB}" \
		--tuples-only --no-align --set=ON_ERROR_STOP=1 \
		--file="${SQL_DIR}/count_llm_cache.sql")"
else
	ROWS="$(podman compose exec --no-tty postgres psql \
		--username="${PGUSER}" --dbname="${LLM_CACHE_DB}" \
		--tuples-only --no-align --set=ON_ERROR_STOP=1 \
		<"${SQL_DIR}/count_llm_cache.sql")"
fi
if [[ "${ROWS//[[:space:]]/}" == "0" ]]; then
	echo "[ERROR] restored cache is empty." >&2
	exit 1
fi
echo "[INFO] LLM cache restore complete: ${ROWS//[$'\t\r ']/} cached generations."
