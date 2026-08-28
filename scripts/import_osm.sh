#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
SQL_DIR="${REPO_ROOT}/sql"

SOURCE_POINTER="${REPO_ROOT}/.osm_vn_source"
FILE_INFO_CACHE="${REPO_ROOT}/.osm_vn_fileinfo"
STYLE_FILE="${SCRIPT_DIR}/osm_poi.lua"

: "${PGHOST:?PGHOST is required}" "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}" "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:?PGDATABASE is required}"

psql_file() {
	if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
		psql --quiet --set=ON_ERROR_STOP=1 --file="$1"
	else
		podman compose exec --no-tty postgres psql \
			--username="${PGUSER}" --dbname="${PGDATABASE}" \
			--quiet --set=ON_ERROR_STOP=1 <"$1"
	fi
}

psql_query() {
	if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
		psql --tuples-only --no-align --set=ON_ERROR_STOP=1 "$@"
	else
		podman compose exec --no-tty postgres psql \
			--username="${PGUSER}" --dbname="${PGDATABASE}" \
			--tuples-only --no-align --set=ON_ERROR_STOP=1 "$@"
	fi
}

if [[ ! -s "${SOURCE_POINTER}" ]]; then
	echo "[ERROR] Missing ${SOURCE_POINTER}. Run download_osm.sh first." >&2
	exit 1
fi

OSM_FILENAME="$(<"${SOURCE_POINTER}")"
if [[ "${OSM_FILENAME}" = /* ]]; then
	OSM_FILE="${OSM_FILENAME}"
else
	OSM_FILE="${REPO_ROOT}/${OSM_FILENAME}"
fi

if [[ ! -s "${OSM_FILE}" ]]; then
	echo "[ERROR] Missing or empty OSM file: ${OSM_FILE}" >&2
	exit 1
fi

SOURCE_SIZE="$(stat --format='%s' "${OSM_FILE}")"
SOURCE_MTIME="$(stat --format='%Y' "${OSM_FILE}")"
STYLE_SHA256="$(sha256sum "${STYLE_FILE}" | awk '{ print $1 }')"

psql_file "${SQL_DIR}/init_marker.sql"

IMPORT_MATCH="$(
	psql_query \
		--set=source_file="${OSM_FILENAME}" \
		--set=source_size="${SOURCE_SIZE}" \
		--set=source_mtime="${SOURCE_MTIME}" \
		--set=style_sha256="${STYLE_SHA256}" \
		<"${SQL_DIR}/check_import.sql"
)"

refresh_views() {
	echo "[INFO] Refreshing views and spatial index..."
	psql_file "${SQL_DIR}/refresh_views.sql"
}

if [[ "${IMPORT_MATCH}" == "1" ]]; then
	echo "[INFO] Already imported: ${OSM_FILENAME}"
	exit 0
fi

CACHED_FILE=""
CACHED_SIZE=""
CACHED_MTIME=""
TOTAL_NODES=""
TOTAL_WAYS=""
TOTAL_RELATIONS=""
CACHE_VALID=false

if [[ -s "${FILE_INFO_CACHE}" ]]; then
	IFS=$'\t' read -r \
		CACHED_FILE \
		CACHED_SIZE \
		CACHED_MTIME \
		TOTAL_NODES \
		TOTAL_WAYS \
		TOTAL_RELATIONS \
		<"${FILE_INFO_CACHE}" || true

	if [[ "${CACHED_FILE}" == "${OSM_FILE}" &&
		"${CACHED_SIZE}" == "${SOURCE_SIZE}" &&
		"${CACHED_MTIME}" == "${SOURCE_MTIME}" &&
		"${TOTAL_NODES}" =~ ^[0-9]+$ &&
		"${TOTAL_WAYS}" =~ ^[0-9]+$ &&
		"${TOTAL_RELATIONS}" =~ ^[0-9]+$ ]]; then
		CACHE_VALID=true
	fi
fi

if [[ "${CACHE_VALID}" != true ]]; then
	echo "[INFO] Scanning OSM file with osmium..."

	FILE_INFO="$(
		osmium fileinfo \
			--extended \
			--no-crc \
			--progress \
			"${OSM_FILE}"
	)"

	TOTAL_NODES="$(
		sed \
			--quiet \
			--regexp-extended \
			's/^[[:space:]]*Number of nodes:[[:space:]]*([0-9]+).*$/\1/p' \
			<<<"${FILE_INFO}"
	)"

	TOTAL_WAYS="$(
		sed \
			--quiet \
			--regexp-extended \
			's/^[[:space:]]*Number of ways:[[:space:]]*([0-9]+).*$/\1/p' \
			<<<"${FILE_INFO}"
	)"

	TOTAL_RELATIONS="$(
		sed \
			--quiet \
			--regexp-extended \
			's/^[[:space:]]*Number of relations:[[:space:]]*([0-9]+).*$/\1/p' \
			<<<"${FILE_INFO}"
	)"

	if [[ ! "${TOTAL_NODES}" =~ ^[0-9]+$ ||
		! "${TOTAL_WAYS}" =~ ^[0-9]+$ ||
		! "${TOTAL_RELATIONS}" =~ ^[0-9]+$ ]]; then
		echo "[ERROR] Failed to read OSM object counts." >&2
		exit 1
	fi

	CACHE_TMP="$(mktemp "${FILE_INFO_CACHE}.XXXXXX")"

	printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
		"${OSM_FILE}" \
		"${SOURCE_SIZE}" \
		"${SOURCE_MTIME}" \
		"${TOTAL_NODES}" \
		"${TOTAL_WAYS}" \
		"${TOTAL_RELATIONS}" \
		>"${CACHE_TMP}"

	mv --force "${CACHE_TMP}" "${FILE_INFO_CACHE}"
fi

awk \
	-v nodes="${TOTAL_NODES}" \
	-v ways="${TOTAL_WAYS}" \
	-v relations="${TOTAL_RELATIONS}" \
	'BEGIN {
        printf "[INFO] OSM input summary: Node(%.1fk) Way(%.1fk) Relation(%.1fk)\n",
            nodes / 1000,
            ways / 1000,
            relations / 1000
    }'

echo "[INFO] Preparing database tables..."
psql_file "${SQL_DIR}/prepare_import.sql"

echo "[INFO] Importing reference tables with osm2pgsql..."
osm2pgsql \
	--create \
	--output=flex \
	--style="${STYLE_FILE}" \
	--number-processes="$(nproc)" \
	--log-level=info \
	--log-progress=true \
	"${OSM_FILE}"

echo "[INFO] Standardizing POI table column names..."
psql_file "${SQL_DIR}/standardize_columns.sql"

refresh_views

echo "[INFO] Recording import completion..."
psql_query \
	--set=source_file="${OSM_FILENAME}" \
	--set=source_size="${SOURCE_SIZE}" \
	--set=source_mtime="${SOURCE_MTIME}" \
	--set=style_sha256="${STYLE_SHA256}" \
	<"${SQL_DIR}/record_import.sql" >/dev/null

echo "[INFO] Import complete: ${OSM_FILENAME}"
