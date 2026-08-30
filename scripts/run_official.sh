#!/usr/bin/env bash
# T07 G6: raw, untuned official baseline runs.
# Ornith Text2SQL → Ornith Direct → Qwen Text2SQL → Qwen Direct, matching the
# llama.cpp preset's 4 slots (config/models.ini). Extra script arguments are
# passed through to the pipeline. Never --clear-cache — write-through caching
# makes every rerun resume. Logs and manifests land in logs/official/.
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

export LLAMACPP_URL="${LLAMACPP_URL:-http://localhost:8080}"
export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-osm_vn}"
export PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-postgres}"

LOG_DIR="${ROOT_DIR}/logs/official"
mkdir -p "${LOG_DIR}"

BOOTSTRAP_ARGS=()
if [[ -z "${COLAB_RELEASE_TAG:-}" ]]; then
	echo "[INFO] Preflight: starting the compose stack..."
	podman compose up --detach
	BOOTSTRAP_ARGS=(--wait-only)
fi

echo "[INFO] Preflight: reference database (five-table gate)..."
./scripts/bootstrap_postgres.sh "${BOOTSTRAP_ARGS[@]}"

if [[ -n "${COLAB_RELEASE_TAG:-}" ]]; then
	echo "[INFO] Preflight: llama.cpp..."
	./scripts/bootstrap_llama.sh
else
	echo "[INFO] Waiting for HAProxy at ${LLAMACPP_URL}..."
	if ! curl --fail --silent --show-error --output /dev/null \
		--max-time 2 --retry 180 --retry-all-errors --retry-delay 5 \
		--retry-max-time "${HAPROXY_WAIT_SECONDS:-900}" \
		"${LLAMACPP_URL}/health"; then
		podman compose logs --tail=40 haproxy >&2 || true
		exit 1
	fi
	echo "[INFO] HAProxy is ready."
fi

echo "[INFO] Preflight: frozen dataset..."
./scripts/restore_dataset.sh

MODELS=(
	"llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M"
	"llamacpp:unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL"
)

for MODEL in "${MODELS[@]}"; do
	for BASELINE in text2sql direct; do
		SAFE="${MODEL//[:\/]/_}"
		STAMP="$(date +%Y%m%d-%H%M%S)"
		RUN_LOG="${LOG_DIR}/${SAFE}_${BASELINE}_${STAMP}"
		date --iso-8601=seconds >"${RUN_LOG}.start_ts"
		echo "[INFO] ${MODEL} — ${BASELINE} (logs: ${RUN_LOG}.out/.err)"
		python -m baselines.baselines_vi \
			--model "${MODEL}" \
			--baseline "${BASELINE}" \
			--mode full \
			--llm-concurrency 4 \
			"$@" \
			>"${RUN_LOG}.out" 2>"${RUN_LOG}.err"
		python scripts/run_check.py \
			--model "${MODEL}" \
			--baseline "${BASELINE}" \
			--log "${RUN_LOG}"
		echo "[INFO] ${MODEL} — ${BASELINE}: asserts green, manifest written."
	done
done

echo "[INFO] All four official runs complete."
