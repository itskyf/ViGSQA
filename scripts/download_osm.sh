#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"

OSM_URL="https://download.geofabrik.de/asia/vietnam-260901.osm.pbf"
# Geofabrik publishes the integrity reference alongside every extract; using
# it avoids duplicating a pinned hash that drifts from upstream's own record.
MD5_URL="${OSM_URL}.md5"
SOURCE_POINTER="${REPO_ROOT}/.osm_vn_source"
OSM_FILENAME="$(basename "${OSM_URL%%\?*}")"
OSM_FILE="${REPO_ROOT}/${OSM_FILENAME}"
MD5_FILE="${OSM_FILE}.md5"
PART_FILE="${OSM_FILE}.part"

expected_md5() {
	curl --fail --show-error --location --retry 2 --silent --output "${MD5_FILE}" "${MD5_URL}"
	awk '{ print $1 }' "${MD5_FILE}"
}

file_md5() {
	md5sum "$1" | awk '{ print $1 }'
}

if [[ -s "${OSM_FILE}" ]] && [[ "$(file_md5 "${OSM_FILE}")" == "$(expected_md5)" ]]; then
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
if [[ "$(file_md5 "${PART_FILE}")" != "$(expected_md5)" ]]; then
	rm --force "${PART_FILE}"
	echo "[ERROR] Downloaded OSM snapshot failed MD5 verification." >&2
	exit 1
fi
mv "${PART_FILE}" "${OSM_FILE}"
printf '%s\n' "${OSM_FILENAME}" >"${SOURCE_POINTER}"
echo "[INFO] Download complete and verified: ${OSM_FILENAME}"
