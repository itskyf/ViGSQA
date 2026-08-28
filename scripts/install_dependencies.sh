#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

REQUIRED_COMMANDS=(curl osmium osm2pgsql unzip)

if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	packages=(curl osm2pgsql osmium-tool postgresql postgresql-postgis unzip)
	missing=()
	for package in "${packages[@]}"; do
		dpkg-query --show --showformat='${db:Status-Status}' "${package}" 2>/dev/null |
			grep --quiet 'installed' || missing+=("${package}")
	done
	if [[ ${#missing[@]} -gt 0 ]]; then
		echo "[INFO] Installing missing packages: ${missing[*]}"
		apt-get update --quiet=2
		apt-get install --yes --no-install-recommends --quiet=2 "${missing[@]}"
	else
		echo "[INFO] Required system packages are already installed."
	fi
else
	# Local host: dependencies come from Pixi (see pyproject.toml); PostgreSQL
	# server itself runs in the compose.yaml container, never via apt.
	missing=()

	for cmd in "${REQUIRED_COMMANDS[@]}"; do
		command -v "${cmd}" >/dev/null || missing+=("${cmd}")
	done

	if [[ ${#missing[@]} -gt 0 ]]; then
		echo "[ERROR] Missing commands: ${missing[*]}." >&2
		echo "[ERROR] Run this script through 'pixi run' or after 'pixi shell'." >&2
		exit 1
	fi

	echo "[INFO] All required commands are available."
fi

echo "[INFO] Dependency check complete."
