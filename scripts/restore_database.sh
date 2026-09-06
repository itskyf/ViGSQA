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
DB_ASSET_URL="https://github.com/itskyf/ViGSQA/releases/download/v3.0.0/osm-vn.dump"
DB_ASSET_SHA256="deb523cd943520f37b67b70b421a9f3d7a22283ee0fb33d856ffd6b9cb2844d0"
DB_ASSET_FILE="${REPO_ROOT}/osm-vn.dump"
PART_FILE="${DB_ASSET_FILE}.part"
TOC_FILE="${DB_ASSET_FILE}.toc"

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
# The archive is a pg_dump custom format, restored in parallel. Dropping the
# TOC's 'SCHEMA - public' entries (the custom-format analogue of the previous
# plain-SQL schema filters) keeps the restore from dropping/recreating the
# schema that hosts the postgis extension init_database.sql creates before
# this runs; every other --clean entry stays, so an interrupted restore
# remains self-healing. --jobs: 2-vCPU Colab plus headroom — pg_restore caps
# concurrency by dependency order, so extra jobs are harmless.
# The local branch restores inside the container with the image's own
# pg_restore; binary stdin keeps the podman compose service-name idiom.
if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	pg_restore --list "${DB_ASSET_FILE}" |
		grep --invert-match --fixed-strings ' SCHEMA - public ' >"${TOC_FILE}"
	pg_restore \
		--dbname="${PGDATABASE}" \
		--use-list="${TOC_FILE}" \
		--jobs=4 \
		--exit-on-error \
		"${DB_ASSET_FILE}"
else
	podman compose exec --no-tty postgres sh -c 'cat > /tmp/osm-vn.dump' \
		<"${DB_ASSET_FILE}"
	podman compose exec --no-tty postgres sh -c \
		"pg_restore --list /tmp/osm-vn.dump |
			grep --invert-match --fixed-strings ' SCHEMA - public ' >/tmp/osm-vn.dump.toc"
	podman compose exec --no-tty postgres pg_restore \
		--username="${PGUSER}" \
		--dbname="${PGDATABASE}" \
		--use-list=/tmp/osm-vn.dump.toc \
		--jobs=4 \
		--exit-on-error \
		/tmp/osm-vn.dump
	podman compose exec --no-tty postgres rm --force \
		/tmp/osm-vn.dump /tmp/osm-vn.dump.toc
fi

echo "[INFO] Reference database restore complete."
