#!/usr/bin/env bash
# Restore the reference database from the prebuilt GitHub Release dump.
# Priority over the raw osm2pgsql import; fails loudly so the caller can fall
# back. Safe to re-run: skips an already-populated database, and the dump's
# --clean section drops its own partial objects first.
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
SQL_DIR="${REPO_ROOT}/sql"

# Pinned like scripts/download_osm.sh: URL and checksum are a verification
# pair, so neither is env-overridable.
DB_ASSET_URL="https://github.com/itskyf/ViGSQA/releases/download/data-v3.0.0/osm-vn.sql.gz"
DB_ASSET_SHA256="ae06f7c2ae7808235682371e03017a9da6ce6b323ec962cd06f99c0bb2ef53e6"
DB_ASSET_FILE="${REPO_ROOT}/osm-vn.sql.gz"
PART_FILE="${DB_ASSET_FILE}.part"

: "${PGHOST:?PGHOST is required}" "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}" "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:?PGDATABASE is required}"

psql_query() {
	if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
		psql --tuples-only --no-align --set=ON_ERROR_STOP=1
	else
		podman compose exec --no-tty postgres psql \
			--username="${PGUSER}" --dbname="${PGDATABASE}" \
			--tuples-only --no-align --set=ON_ERROR_STOP=1
	fi
}

psql_stream() {
	if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
		psql --quiet --set=ON_ERROR_STOP=1
	else
		podman compose exec --no-tty postgres psql \
			--username="${PGUSER}" --dbname="${PGDATABASE}" \
			--quiet --set=ON_ERROR_STOP=1
	fi
}

POPULATED="$(psql_query <"${SQL_DIR}/check_database_populated.sql")"
if [[ "${POPULATED}" == "1" ]]; then
	echo "[INFO] Reference database already populated; skipping restore."
	exit 0
fi

if [[ -s "${DB_ASSET_FILE}" ]] &&
	echo "${DB_ASSET_SHA256}  ${DB_ASSET_FILE}" | sha256sum --check --quiet; then
	echo "[INFO] DB dump already cached: $(basename "${DB_ASSET_FILE}")"
else
	echo "[INFO] Downloading pinned DB dump..."
	curl \
		--fail \
		--show-error \
		--location \
		--retry 2 \
		--continue-at - \
		--progress-bar \
		--output "${PART_FILE}" \
		"${DB_ASSET_URL}"
	if ! echo "${DB_ASSET_SHA256}  ${PART_FILE}" | sha256sum --check --quiet; then
		rm --force "${PART_FILE}"
		echo "[ERROR] Downloaded DB dump failed SHA-256 verification." >&2
		exit 1
	fi
	mv "${PART_FILE}" "${DB_ASSET_FILE}"
fi

echo "[INFO] Restoring reference database..."
# The dump is produced by PostgreSQL 18 / psql 18 and restored into 14/3.4 on
# Colab; these filters remove exactly the incompatible lines (COPY data can
# never match: hex EWKB and tab-separated text never start with a lone
# backslash, which COPY escaping always doubles) and the --clean artifacts
# that would drop the schema hosting the postgis extension.
gzip --decompress --stdout "${DB_ASSET_FILE}" |
	sed \
		--expression '/^SET transaction_timeout = 0;$/d' \
		--expression '/^\\restrict /d' \
		--expression '/^\\unrestrict /d' \
		--expression '/^DROP SCHEMA IF EXISTS public;$/d' \
		--expression '/^CREATE SCHEMA public;$/d' |
	psql_stream

echo "[INFO] Reference database restore complete."
