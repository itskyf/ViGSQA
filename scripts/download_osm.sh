#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"

OSM_URL="https://download.geofabrik.de/asia/vietnam-260825.osm.pbf"
OSM_SHA256="99ab80801df28b49ab4b668359de7172d5e86f2fbf20cea704799dfc117f2d00"
SOURCE_POINTER="${REPO_ROOT}/.osm_vn_source"
OSM_FILENAME="$(basename "${OSM_URL%%\?*}")"
OSM_FILE="${REPO_ROOT}/${OSM_FILENAME}"
PART_FILE="${OSM_FILE}.part"

if [[ -s "${OSM_FILE}" ]] && echo "${OSM_SHA256}  ${OSM_FILE}" | sha256sum --check --quiet; then
	echo "[INFO] OSM snapshot already exists: ${OSM_FILENAME}"
	printf '%s\n' "${OSM_FILENAME}" >"${SOURCE_POINTER}"
	exit 0
fi

echo "[INFO] Downloading pinned OSM snapshot: ${OSM_FILENAME}..."
curl \
	--fail \
	--show-error \
	--location \
	--retry 2 \
	--continue-at - \
	--progress-bar \
	--output "${PART_FILE}" \
	"${OSM_URL}"
if ! echo "${OSM_SHA256}  ${PART_FILE}" | sha256sum --check --quiet; then
	rm --force "${PART_FILE}"
	echo "[ERROR] Downloaded OSM snapshot failed SHA-256 verification." >&2
	exit 1
fi
mv "${PART_FILE}" "${OSM_FILE}"
printf '%s\n' "${OSM_FILENAME}" >"${SOURCE_POINTER}"
echo "[INFO] Download complete and verified: ${OSM_FILENAME}"
