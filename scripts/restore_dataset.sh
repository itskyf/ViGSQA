#!/usr/bin/env bash
# Restore the frozen VN-GeoQA benchmark from the public GitHub Release asset.
# Idempotent: skips the download when the files are already present; always
# verifies sha256 (scripts/<version>.sha256) before exiting.
set -euo pipefail

VERSION="${DATASET_VERSION:-v2.0.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${ROOT}/data/${VERSION}/questions_vi"
URL="${DATASET_URL:-https://github.com/itskyf/ViGSQA/releases/download/data-${VERSION}/vn-geoqa-${VERSION}.zip}"
ARCHIVE="${ROOT}/data/${VERSION}.zip"

if [[ ! -f "${DATA_DIR}/MANIFEST.json" ]]; then
	mkdir -p "${ROOT}/data"
	curl -fL --continue-at - -o "${ARCHIVE}" "${URL}"
	# The archive contains questions_vi/ at its root.
	unzip -oq "${ARCHIVE}" -d "${ROOT}/data/${VERSION}"
fi

(cd "${DATA_DIR}" && sha256sum --check "${ROOT}/scripts/${VERSION}.sha256" --quiet)
echo "VN-GeoQA ${VERSION}: $(find "${DATA_DIR}" -maxdepth 1 -name '*.jsonl' | wc -l) files, $(cat "${DATA_DIR}"/*.jsonl | wc -l) questions verified."
