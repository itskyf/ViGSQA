#!/usr/bin/env bash
# T07 G6: raw, untuned official baseline runs.
# Ornith Text2SQL → Ornith Direct → Qwen Text2SQL → Qwen Direct.
# Extra script arguments are passed through to the pipeline. Never --clear-cache —
# write-through caching makes every rerun resume. Logs and manifests land in logs/official/.
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

LLM_CONCURRENCY="${LLM_CONCURRENCY:-1}"
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
	case "$1" in
	--llm-concurrency)
		if [[ $# -lt 2 ]]; then
			echo "[ERROR] --llm-concurrency requires an argument" >&2
			exit 2
		fi
		LLM_CONCURRENCY="$2"
		shift 2
		;;
	--llm-concurrency=*)
		LLM_CONCURRENCY="${1#*=}"
		shift
		;;
	*)
		EXTRA_ARGS+=("$1")
		shift
		;;
	esac
done

MODELS=(
	"llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M"
	"llamacpp:unsloth/Qwen3.5-9B-GGUF:Q4_K_XL"
)
PENDING_MODELS=()
PENDING_BASELINES=()

for MODEL in "${MODELS[@]}"; do
	for BASELINE in text2sql direct; do
		if python scripts/check_run_seal.py "${MODEL}" "${BASELINE}"; then
			continue
		fi
		PENDING_MODELS+=("${MODEL}")
		PENDING_BASELINES+=("${BASELINE}")
	done
done

if [[ "${#PENDING_MODELS[@]}" -eq 0 ]]; then
	echo "[INFO] All four official runs are sealed."
	exit 0
fi

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
	# Probe /v1/models, not /health: monitor-uri answers /health on the
	# frontend itself, so it stays 200 even with every backend down.
	echo "[INFO] Waiting for a servable backend at ${LLAMACPP_URL}..."
	if ! curl --fail --silent --show-error --output /dev/null \
		--max-time 2 --retry 180 --retry-all-errors --retry-delay 5 \
		--retry-max-time "${HAPROXY_WAIT_SECONDS:-900}" \
		"${LLAMACPP_URL}/v1/models"; then
		podman compose logs --tail=40 haproxy >&2 || true
		exit 1
	fi
	echo "[INFO] Backend pool is ready."
fi

echo "[INFO] Preflight: frozen dataset..."
./scripts/restore_dataset.sh

QWEN_MODEL="llamacpp:unsloth/Qwen3.5-9B-GGUF:Q4_K_XL"
if [[ " ${PENDING_MODELS[*]} " == *" ${QWEN_MODEL} "* ]]; then
	echo "[INFO] Preflight: Qwen runtime identity..."
	python scripts/check_qwen_runtime.py "${LLAMACPP_URL}/v1/models"
fi

for INDEX in "${!PENDING_MODELS[@]}"; do
	MODEL="${PENDING_MODELS[INDEX]}"
	BASELINE="${PENDING_BASELINES[INDEX]}"
	if [[ "${MODEL}" == "llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M" && "${BASELINE}" == direct ]]; then
		python scripts/backup_direct_repair.py --model "${MODEL}"
	fi
	SAFE="${MODEL//[:\/]/_}"
	STAMP="$(date +%Y%m%d-%H%M%S)"
	RUN_LOG="${LOG_DIR}/${SAFE}_${BASELINE}_${STAMP}"
	date --iso-8601=seconds >"${RUN_LOG}.start_ts"
	echo "[INFO] ${MODEL} — ${BASELINE} (logs: ${RUN_LOG}.out/.err)"
	# tee keeps the .out/.err provenance files while showing progress live
	# (tqdm writes stderr). The process substitution sits outside the
	# pipeline, so pipefail still propagates the python exit status.
	python -u -m baselines.baselines_vi \
		--model "${MODEL}" \
		--baseline "${BASELINE}" \
		--mode full \
		--llm-concurrency "${LLM_CONCURRENCY}" \
		"${EXTRA_ARGS[@]}" \
		2> >(tee "${RUN_LOG}.err" >&2) | tee "${RUN_LOG}.out"
	python scripts/run_check.py \
		--model "${MODEL}" \
		--baseline "${BASELINE}" \
		--log "${RUN_LOG}"
	echo "[INFO] ${MODEL} — ${BASELINE}: G6 green and sealed."
done

echo "[INFO] All four official runs complete."
