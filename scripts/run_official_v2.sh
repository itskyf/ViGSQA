#!/usr/bin/env bash
# T07 G6: raw, untuned v2.0.0 baseline runs.
# Sequential order (one llama.cpp slot): Ornith Text2SQL → Ornith Direct →
# Qwen Text2SQL → Qwen Direct. Never --clear-cache — write-through caching
# makes every rerun resume. Logs and manifests land in logs/v2.0.0/.
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

export LLAMACPP_URL="${LLAMACPP_URL:-http://localhost:8000}"
export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-osm_vn}"
export PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-postgres}"
PYTHON="${PYTHON:-pixi run python}"

LOG_DIR="${ROOT_DIR}/logs/v2.0.0"
mkdir -p "${LOG_DIR}"

echo "[INFO] Preflight: reference database (five-table gate)..."
./scripts/bootstrap_postgres.sh

echo "[INFO] Preflight: llama.cpp..."
./scripts/bootstrap_llama.sh

echo "[INFO] Preflight: frozen v2.0.0 dataset..."
./scripts/restore_dataset.sh

MODELS=(
	"llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M"
	"llamacpp:unsloth/Qwen3.5-9B-MTP-GGUF:UD-Q4_K_XL"
)

for MODEL in "${MODELS[@]}"; do
	for BASELINE in text2sql direct; do
		SAFE="${MODEL//[:\/]/_}"
		STAMP="$(date +%Y%m%d-%H%M%S)"
		RUN_LOG="${LOG_DIR}/${SAFE}_${BASELINE}_${STAMP}"
		date --iso-8601=seconds >"${RUN_LOG}.start_ts"
		echo "[INFO] ${MODEL} — ${BASELINE} (logs: ${RUN_LOG}.out/.err)"
		${PYTHON} -m baselines.baselines_vi \
			--model "${MODEL}" \
			--baseline "${BASELINE}" \
			--mode full \
			>"${RUN_LOG}.out" 2>"${RUN_LOG}.err"
		${PYTHON} scripts/run_check_v2.py \
			--model "${MODEL}" \
			--baseline "${BASELINE}" \
			--log "${RUN_LOG}"
		echo "[INFO] ${MODEL} — ${BASELINE}: asserts green, manifest written."
	done
done

echo "[INFO] All four v2.0.0 runs complete."
