#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

REQUIRED_COMMANDS=(curl osmium osm2pgsql psql)

if [[ -d /content ]]; then
	# Google Colab: install packages and start the local PostgreSQL service.
	echo "[INFO] Updating package lists..."
	apt-get update --quiet=2

	echo "[INFO] Installing required packages (curl, osm2pgsql, osmium-tool, postgresql-postgis)..."
	apt-get install --yes --no-install-recommends --quiet=2 \
		curl \
		osm2pgsql \
		osmium-tool \
		postgresql-postgis

	echo "[INFO] Starting PostgreSQL service..."
	service postgresql start

	# Wait for TCP readiness: later scripts connect over TCP with password
	# auth (PGHOST/PGUSER/PGPASSWORD) instead of the local peer socket.
	for _ in $(seq 1 30); do
		if pg_isready --host=127.0.0.1 --quiet; then
			break
		fi
		sleep 1
	done
	pg_isready --host=127.0.0.1 --quiet
else
	# Local host: dependencies come from pixi (see pixi.toml); the PostgreSQL
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

echo "[INFO] Dependencies installation and service startup complete."
