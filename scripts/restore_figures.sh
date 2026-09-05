#!/usr/bin/env bash
# Restore the report figure assets from the public GitHub Release archive.
# Figures are regenerable (report diagrams, notebook §2.4 map) but ship in the
# release so the report builds without rerunning the notebook. Git LFS is
# unavailable on this public fork, so the archive is a plain release asset.
# Idempotent: skips the download when the figures are already present; always
# verifies sha256 (scripts/figures.sha256) before exiting.
set -euo pipefail

VERSION="${FIGURES_VERSION:-v3.0.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${FIGURES_URL:-https://github.com/itskyf/ViGSQA/releases/download/${VERSION}/report-figures.tar.gz}"
ARCHIVE="${ROOT}/report-figures.tar.gz"

if [[ ! -f "${ROOT}/docs/report/figures/fig1_baselines.svg" ]]; then
	curl -fL --continue-at - -o "${ARCHIVE}" "${URL}"
	# The archive stores figures under their repo-relative paths.
	tar -xzf "${ARCHIVE}" -C "${ROOT}"
fi

(cd "${ROOT}" && sha256sum --check "${ROOT}/scripts/figures.sha256" --quiet)
echo "Report figures: $(grep -c . "${ROOT}/scripts/figures.sha256") assets verified."
