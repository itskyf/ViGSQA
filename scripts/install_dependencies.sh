#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

REQUIRED_COMMANDS=(curl osmium osm2pgsql unzip)

if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	# PostgreSQL 18 + PostGIS 3.6 come from PGDG — the versions the release
	# dumps were produced with, so restores need no version-skew handling.
	# apt.postgresql.org.sh is interactive (waits for Enter); the piped
	# newline accepts its prompt, and re-running it over an existing
	# repository is harmless.
	base_packages=(curl osm2pgsql osmium-tool postgresql-common unzip)
	pgdg_packages=(postgresql-18 postgresql-18-postgis-3)

	installed() {
		dpkg-query --show --showformat='${db:Status-Status}' "${1}" 2>/dev/null |
			grep --quiet 'installed'
	}

	missing=()
	for package in "${base_packages[@]}"; do
		installed "${package}" || missing+=("${package}")
	done
	if [[ ${#missing[@]} -gt 0 ]]; then
		echo "[INFO] Installing missing packages: ${missing[*]}"
		apt-get update --quiet=2
		apt-get install --yes --no-install-recommends --quiet=2 "${missing[@]}"
	else
		echo "[INFO] Required system packages are already installed."
	fi

	if ! installed postgresql-18 || ! installed postgresql-18-postgis-3; then
		echo "[INFO] Adding the PGDG apt repository and installing: ${pgdg_packages[*]}"
		printf '\n' | /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh
		apt-get update --quiet=2
		apt-get install --yes --no-install-recommends --quiet=2 "${pgdg_packages[@]}"
	else
		echo "[INFO] PostgreSQL 18 is already installed."
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
