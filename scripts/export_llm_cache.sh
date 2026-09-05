#!/usr/bin/env bash
# Maintainer-only: dump the LangChain LLM cache database (T09). Consumed by
# scripts/restore_llm_cache.sh; local convenience, not a pinned release asset —
# unlike osm-vn.dump this artifact grows with inference and is regenerable.
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"

LLM_CACHE_DB="${LLM_CACHE_DBNAME:-llm_cache}"
DUMP_FILE="${REPO_ROOT}/llm-cache-$(date +%Y%m%d).sql.gz"
PART_FILE="${DUMP_FILE}.part"

: "${PGHOST:?PGHOST is required}" "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}" "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:?PGDATABASE is required}"

if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	echo "[ERROR] export_llm_cache.sh is local-maintainer-only." >&2
	exit 1
fi

./scripts/start_postgres.sh

echo "[INFO] Dumping ${LLM_CACHE_DB}..."
# --clean --if-exists makes restore_llm_cache.sh replace-in-place idempotently.
# pipefail catches pg_dump failing mid-stream even though gzip exits 0.
podman compose exec --no-tty postgres pg_dump \
	--username="${PGUSER}" \
	--dbname="${LLM_CACHE_DB}" \
	--clean \
	--if-exists \
	--no-owner \
	--no-privileges |
	gzip >"${PART_FILE}"
mv --force "${PART_FILE}" "${DUMP_FILE}"

echo "[INFO] Wrote ${DUMP_FILE} ($(stat --format='%s' "${DUMP_FILE}") bytes)"
sha256sum "${DUMP_FILE}"
