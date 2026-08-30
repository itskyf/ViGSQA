#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

case "$#" in
0) WAIT_ONLY=0 ;;
1)
	if [[ "$1" != "--wait-only" ]]; then
		echo "[ERROR] Unknown argument: $1" >&2
		exit 2
	fi
	WAIT_ONLY=1
	;;
*)
	echo "[ERROR] Usage: ${0##*/} [--wait-only]" >&2
	exit 2
	;;
esac

# Colab: service(8) blocks until the postmaster accepts connections.
if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	if ((WAIT_ONLY)); then
		until pg_isready --quiet; do
			sleep 2
		done
	else
		service postgresql start
	fi
else
	if ((! WAIT_ONLY)); then
		podman compose up --detach postgres
	fi
	POSTGRES_CONTAINER="$(podman compose ps --quiet postgres)"
	podman wait --condition healthy --interval 2s "${POSTGRES_CONTAINER}" >/dev/null
fi
