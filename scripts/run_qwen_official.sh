#!/usr/bin/env bash
# Qwen-only T07 preflight, full raw runs, and G6 validation.
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

export LLAMACPP_URL="http://127.0.0.1:8000"
export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-osm_vn}"
export PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-postgres}"

QWEN_MODEL="llamacpp:unsloth/Qwen3.5-9B-GGUF:Q4_K_XL"
QWEN_RUN_DIR="${QWEN_RUN_DIR:-${ROOT_DIR}/logs/official/qwen35-9b-nonthinking-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "${QWEN_RUN_DIR}"

echo "[INFO] Restoring the frozen dataset and recreating local llama.cpp..."
./scripts/restore_dataset.sh
podman compose up --detach --force-recreate --wait llamacpp

echo "[INFO] Running the uncached 28-TID Qwen preflight..."
python scripts/check_qwen_runtime.py "${LLAMACPP_URL}/v1/models"

echo "[INFO] Preparing PostgreSQL/PostGIS and the LLM cache database..."
./scripts/bootstrap_postgres.sh

run_baseline() {
	local baseline="$1"
	local log_prefix="${QWEN_RUN_DIR}/${baseline}"

	date --iso-8601=seconds >"${log_prefix}.start_ts"
	echo "[INFO] Running Qwen ${baseline} (logs: ${log_prefix}.out/.err)..."
	python -m baselines.baselines_vi \
		--model "${QWEN_MODEL}" \
		--baseline "${baseline}" \
		--mode full \
		--llm-concurrency 4 \
		>"${log_prefix}.out" 2>"${log_prefix}.err"

	echo "[INFO] Running G6 for Qwen ${baseline}..."
	python scripts/run_check.py \
		--model "${QWEN_MODEL}" \
		--baseline "${baseline}" \
		--log "${log_prefix}"
}

run_baseline text2sql
run_baseline direct

echo "[INFO] Qwen Text2SQL, Direct, and both G6 checks completed."
echo "[INFO] Run namespace: ${QWEN_RUN_DIR}"
