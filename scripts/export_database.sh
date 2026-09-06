#!/usr/bin/env bash
# Maintainer-only: produce and publish the prebuilt reference-database dump
# consumed by scripts/restore_database.sh. Never run on Colab.
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"

DUMP_VERSION="v3.0.0"
RELEASE_TAG="${DUMP_VERSION}"
DUMP_FILE="${REPO_ROOT}/osm-vn.dump"
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
# Custom format so restore_database.sh can restore in parallel with pg_restore
# --jobs; both restore environments are PostgreSQL 18 (the compose image and
# Colab's PGDG packages), so the old cross-version plain-SQL shape is no
# longer needed. --exclude-extension keeps the postgis extension out of the
# archive (the target creates it itself); --clean --if-exists keeps re-running
# an interrupted restore self-healing. The archive is binary, but streaming it
# through `podman compose exec --no-tty` stdout is byte-safe (same path the
# previous gzip pipeline used).
podman compose exec --no-tty postgres pg_dump \
	--username="${PGUSER}" \
	--dbname="${PGDATABASE}" \
	--format=custom \
	--schema=public \
	--exclude-extension=postgis \
	--clean \
	--if-exists \
	--no-owner \
	--no-privileges >"${PART_FILE}"
mv --force "${PART_FILE}" "${DUMP_FILE}"

echo "[INFO] Wrote ${DUMP_FILE} ($(stat --format='%s' "${DUMP_FILE}") bytes)"
sha256sum "${DUMP_FILE}"

# Pin the resulting checksum into restore_database.sh before publishing, so
# URL and SHA-256 always travel together. Custom archives embed their
# creation timestamp, so every export differs and the pin cannot be confirmed
# by re-running (that would loop on a fresh checksum) — it is written
# automatically and reviewed via the git diff of this run.
PINNED_SHA256="$(sha256sum "${DUMP_FILE}" | awk '{ print $1 }')"
sed --in-place \
	"s/^DB_ASSET_SHA256=\"[0-9a-f]*\"$/DB_ASSET_SHA256=\"${PINNED_SHA256}\"/" \
	"${SCRIPT_DIR}/restore_database.sh"
if ! grep --quiet --fixed-strings "${PINNED_SHA256}" "${SCRIPT_DIR}/restore_database.sh"; then
	echo "[ERROR] Failed to pin checksum ${PINNED_SHA256} into restore_database.sh." >&2
	exit 1
fi

if command -v gh >/dev/null 2>&1; then
	gh release upload "${RELEASE_TAG}" "${DUMP_FILE}" --clobber
else
	echo "[INFO] gh not found; upload manually:"
	echo "[INFO]   gh release upload ${RELEASE_TAG} ${DUMP_FILE} --clobber"
fi
