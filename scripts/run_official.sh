#!/usr/bin/env bash
# T07 G6: raw, untuned official baseline runs (T11: external vLLM endpoint).
# Ornith Text2SQL → Ornith Direct → Qwen Text2SQL → Qwen Direct — but vLLM
# serves one model at a time: restart it with VLLM_MODEL and re-run for the
# other, or pass MODELS="<id>" for a single-model pass. The endpoint itself is
# external; this script only probes it.
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

# The official v3 models. Override MODELS when the endpoint serves only one.
read -ra MODELS <<<"${MODELS:-ornith-ai/Ornith-1.5-9B-NVFP4 AxionML/Qwen3.5-9B-NVFP4}"
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
	echo "[INFO] All pending official runs are sealed."
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

echo "[INFO] Preflight: reference database (five-table gate)..."
./scripts/bootstrap_postgres.sh

echo "[INFO] Preflight: frozen dataset..."
./scripts/restore_dataset.sh

# /models stays refused while the server cold-loads the model, so probe it
# like a health check; the served-id check below then fails fast, because no
# retry can fix an endpoint serving a different model.
echo "[INFO] Preflight: external vLLM endpoint ${OPENAI_BASE_URL}..."
curl --fail --silent --show-error --output /dev/null \
	--max-time 5 --retry 180 --retry-all-errors --retry-delay 5 \
	--retry-max-time "${LLM_WAIT_SECONDS:-900}" \
	"${OPENAI_BASE_URL}/models"

SERVED="$(curl --fail --silent "${OPENAI_BASE_URL}/models")"
MISSING=()
for MODEL in "${PENDING_MODELS[@]}"; do
	if ! grep --fixed-strings --quiet "\"${MODEL}\"" <<<"${SERVED}"; then
		MISSING+=("${MODEL}")
	fi
done
if [[ "${#MISSING[@]}" -gt 0 ]]; then
	echo "[ERROR] ${OPENAI_BASE_URL} does not serve: ${MISSING[*]}" >&2
	echo "[INFO] served ids: ${SERVED}" >&2
	exit 1
fi

for INDEX in "${!PENDING_MODELS[@]}"; do
	MODEL="${PENDING_MODELS[INDEX]}"
	BASELINE="${PENDING_BASELINES[INDEX]}"
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

echo "[INFO] All pending official runs complete."
