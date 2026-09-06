#!/usr/bin/env bash
# Parse and score every raw-sealed official run with one fixed parser model.
set -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
cd "${ROOT_DIR}"

LLM_CONCURRENCY="${LLM_CONCURRENCY:-1}"
PARSER_MODEL="ornith-ai/Ornith-1.5-9B-NVFP4"
MODELS=(
	"ornith-ai/Ornith-1.5-9B-NVFP4"
	"AxionML/Qwen3.5-9B-NVFP4"
)
BASELINES=(text2sql direct)

usage() {
	echo "Usage: ${0##*/} [--llm-concurrency N] [--help]"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--help)
		usage
		exit 0
		;;
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
		echo "[ERROR] unknown argument: $1" >&2
		usage >&2
		exit 2
		;;
	esac
done

if ! [[ "${LLM_CONCURRENCY}" =~ ^[1-9][0-9]*$ ]]; then
	echo "[ERROR] --llm-concurrency must be a positive integer" >&2
	exit 2
fi

PENDING_MODELS=()
PENDING_BASELINES=()
for MODEL in "${MODELS[@]}"; do
	for BASELINE in "${BASELINES[@]}"; do
		if python scripts/check_run_seal.py "${MODEL}" "${BASELINE}" --evaluation; then
			continue
		fi
		PENDING_MODELS+=("${MODEL}")
		PENDING_BASELINES+=("${BASELINE}")
	done
done

if [[ ${#PENDING_MODELS[@]} -eq 0 ]]; then
	echo "[INFO] All official evaluations are sealed."
	exit 0
fi

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:8000/v1}"
export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-osm_vn}"
export PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-postgres}"

LOG_DIR="${ROOT_DIR}/logs/official"
mkdir -p "${LOG_DIR}"

echo "[INFO] Preflight: PostgreSQL and LLM cache..."
./scripts/bootstrap_postgres.sh

echo "[INFO] Preflight: frozen dataset and raw seals..."
./scripts/restore_dataset.sh
for INDEX in "${!PENDING_MODELS[@]}"; do
	python scripts/check_run_seal.py \
		"${PENDING_MODELS[INDEX]}" "${PENDING_BASELINES[INDEX]}"
done

echo "[INFO] Preflight: fixed parser endpoint ${OPENAI_BASE_URL}..."
curl --fail --silent --show-error --output /dev/null \
	--max-time 5 --retry 180 --retry-all-errors --retry-delay 5 \
	--retry-max-time "${LLM_WAIT_SECONDS:-900}" \
	"${OPENAI_BASE_URL}/models"

SERVED="$(curl --fail --silent --show-error "${OPENAI_BASE_URL}/models")"
if ! grep --fixed-strings --quiet "\"${PARSER_MODEL}\"" <<<"${SERVED}"; then
	echo "[ERROR] ${OPENAI_BASE_URL} does not serve parser ${PARSER_MODEL}" >&2
	echo "[INFO] served ids: ${SERVED}" >&2
	exit 1
fi

for INDEX in "${!PENDING_MODELS[@]}"; do
	MODEL="${PENDING_MODELS[INDEX]}"
	BASELINE="${PENDING_BASELINES[INDEX]}"
	SAFE="${MODEL//[:\/]/_}"
	STAMP="$(date --iso-8601=seconds | tr --delete ':')"
	RUN_LOG="${LOG_DIR}/evaluation_${SAFE}_${BASELINE}_${STAMP}"
	date --iso-8601=seconds >"${RUN_LOG}.start_ts"
	echo "[INFO] ${MODEL} — ${BASELINE} (parser: ${PARSER_MODEL})"
	python -u scripts/run_evaluation.py \
		--model "${MODEL}" \
		--baseline "${BASELINE}" \
		--llm-concurrency "${LLM_CONCURRENCY}" \
		2> >(tee "${RUN_LOG}.err" >&2) | tee "${RUN_LOG}.out"
	python scripts/check_run_seal.py "${MODEL}" "${BASELINE}" --evaluation
	echo "[INFO] ${MODEL} — ${BASELINE}: evaluation sealed."
done

echo "[INFO] All official evaluations complete."
