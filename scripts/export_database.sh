#!/usr/bin/env bash
# Maintainer-only: produce and publish the prebuilt reference-database dump
# consumed by scripts/restore_database.sh. Never run on Colab.
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"

DUMP_VERSION="v2.0.0"
RELEASE_TAG="data-${DUMP_VERSION}"
DUMP_FILE="${REPO_ROOT}/osm-vn-${DUMP_VERSION}.sql.gz"
PART_FILE="${DUMP_FILE}.part"

: "${PGHOST:?PGHOST is required}" "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}" "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:?PGDATABASE is required}"

if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	echo "[ERROR] export_database.sh is local-maintainer-only." >&2
	exit 1
fi

./scripts/start_postgres.sh

echo "[INFO] Dumping schema public of ${PGDATABASE}..."
# Plain-SQL format restores onto older servers (Colab: PostgreSQL 14 +
# PostGIS 3.4). --exclude-extension keeps CREATE/DROP EXTENSION out of the
# artifact; the target creates the postgis extension itself. pipefail catches
# pg_dump failing mid-stream even though gzip exits 0.
# The psql meta-command tokens are randomized per pg_dump run, which would
# make the artifact non-reproducible; they are normalized to a fixed value
# here (restore_database.sh deletes those lines outright).
podman compose exec --no-tty postgres pg_dump \
	--username="${PGUSER}" \
	--dbname="${PGDATABASE}" \
	--schema=public \
	--exclude-extension=postgis \
	--clean \
	--if-exists \
	--no-owner \
	--no-privileges |
	sed --expression 's/^\\restrict .*$/\\restrict VIGSQA/' \
		--expression 's/^\\unrestrict .*$/\\unrestrict VIGSQA/' |
	gzip >"${PART_FILE}"
mv --force "${PART_FILE}" "${DUMP_FILE}"

echo "[INFO] Wrote ${DUMP_FILE} ($(stat --format='%s' "${DUMP_FILE}") bytes)"
sha256sum "${DUMP_FILE}"

# Pin the resulting checksum into restore_database.sh before publishing, so
# URL and SHA-256 always travel together.
PINNED_SHA256="$(sha256sum "${DUMP_FILE}" | awk '{ print $1 }')"
if ! grep --quiet --fixed-strings "${PINNED_SHA256}" "${SCRIPT_DIR}/restore_database.sh"; then
	echo "[ERROR] restore_database.sh does not pin checksum ${PINNED_SHA256}." >&2
	echo "[ERROR] Update DB_ASSET_SHA256 there, then re-run this script to upload." >&2
	exit 1
fi

if command -v gh >/dev/null 2>&1; then
	gh release upload "${RELEASE_TAG}" "${DUMP_FILE}" --clobber
else
	echo "[INFO] gh not found; upload manually:"
	echo "[INFO]   gh release upload ${RELEASE_TAG} ${DUMP_FILE} --clobber"
fi
