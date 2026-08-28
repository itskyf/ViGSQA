#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${ROOT_DIR}/config/models.ini"

: "${LLAMACPP_URL:?LLAMACPP_URL must be set}"
LLAMA_APP_DIR="${HOME}/.llama-app"
LOCK_FILE="${LLAMA_APP_DIR}/server.lock"
LOG_FILE="${LLAMA_APP_DIR}/server.log"

WAIT_SECONDS="${LLAMA_WAIT_SECONDS:-900}"

health_code() {
	curl --silent --output /dev/null --write-out '%{http_code}' \
		--max-time 2 "${LLAMACPP_URL}/health" || true
}

mkdir -p "${LLAMA_APP_DIR}"

exec {lock_fd}>"${LOCK_FILE}"
flock "${lock_fd}"

code="$(health_code)"
if [[ "${code}" == 200 || "${code}" == 503 ]]; then
	echo "[INFO] Reusing llama.cpp server (${code})."
elif [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	LLAMA_BIN="${LLAMA_APP_DIR}/llama"
	if [[ ! -x "${LLAMA_BIN}" ]]; then
		echo "[INFO] Installing llama.cpp for Colab..."
		curl --fail --location --silent --show-error https://llama.app/install.sh | sh
	else
		echo "[INFO] llama.cpp is already installed."
	fi

	echo "[INFO] Starting llama.cpp (log: ${LOG_FILE})..."
	nohup "${LLAMA_BIN}" serve \
		--models-preset "${CONFIG_FILE}" \
		--models-max 1 \
		--log-file "${LOG_FILE}" \
		>/dev/null 2>&1 &
else
	echo "[INFO] Starting the compose llama.cpp service..."
	podman compose up --detach llama-cpp
fi

flock -u "${lock_fd}"
exec {lock_fd}>&-

echo "[INFO] Waiting for llama.cpp at ${LLAMACPP_URL}..."
deadline=$((SECONDS + WAIT_SECONDS))
until [[ "$(health_code)" == 200 ]]; do
	if ((SECONDS >= deadline)); then
		echo "[ERROR] llama.cpp was not ready after ${WAIT_SECONDS}s." >&2
		if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
			tail --lines=40 "${LOG_FILE}" 2>/dev/null || true
		else
			podman compose logs --tail=40 llama-cpp >&2 || true
		fi
		exit 1
	fi
	sleep 5
	if ((SECONDS % 30 < 5)); then
		echo "[INFO] llama.cpp is still loading..."
	fi
done

echo "[INFO] llama.cpp is ready."
