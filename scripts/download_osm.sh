#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"

LATEST_URL="${OSM_URL:-https://download.geofabrik.de/asia/vietnam-latest.osm.pbf}"
SOURCE_POINTER="${REPO_ROOT}/.osm_vn_source"

rm --force "${SOURCE_POINTER}"

echo "[INFO] Resolving latest OSM extract URL: ${LATEST_URL}..."
HEADER_FILE="$(mktemp)"
trap 'rm --force "${HEADER_FILE}"' EXIT

EFFECTIVE_URL="$(
	curl \
		--fail \
		--silent \
		--show-error \
		--location \
		--head \
		--dump-header "${HEADER_FILE}" \
		--output /dev/null \
		--write-out '%{url_effective}' \
		"${LATEST_URL}"
)"

HEADER_NAME="$(
	tr --delete '\r' <"${HEADER_FILE}" |
		sed \
			--quiet \
			--regexp-extended \
			's/^[Cc]ontent-[Dd]isposition:.*filename="?([^";]+)"?.*$/\1/p' |
		tail --lines=1
)"

if [[ -n "${HEADER_NAME}" ]]; then
	OSM_FILENAME="${HEADER_NAME}"
else
	OSM_FILENAME="$(basename "${EFFECTIVE_URL%%\?*}")"
fi

OSM_FILE="${REPO_ROOT}/${OSM_FILENAME}"
PART_FILE="${OSM_FILE}.part"

if [[ ! -s "${OSM_FILE}" ]]; then
	echo "[INFO] Downloading ${OSM_FILENAME}..."
	curl \
		--fail \
		--show-error \
		--location \
		--retry 2 \
		--continue-at - \
		--progress-bar \
		--output "${PART_FILE}" \
		"${EFFECTIVE_URL}"

	mv "${PART_FILE}" "${OSM_FILE}"
	echo "[INFO] Download completed: ${OSM_FILENAME}"
else
	echo "[INFO] OSM file already exists: ${OSM_FILENAME}"
fi

printf '%s\n' "${OSM_FILENAME}" >"${SOURCE_POINTER}"
echo "[INFO] Active OSM source configured: ${OSM_FILENAME}"
