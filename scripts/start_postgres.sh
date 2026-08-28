#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

# Colab: service(8) blocks until the postmaster accepts connections.
# Local: --wait blocks on the pg_isready healthcheck in compose.yaml.
if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	service postgresql start
else
	podman compose up --wait postgres
fi
