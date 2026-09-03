#!/usr/bin/env bash
# Focused check for the run_official.sh tee logging contract: stdout and
# stderr stay separate, both land in their provenance files, and a python
# failure still fails the pipeline (pipefail propagates the exit status).
set -o errexit -o nounset -o pipefail

TMP_DIR="$(mktemp --directory)"
trap 'rm -rf "${TMP_DIR}"' EXIT
LOG="${TMP_DIR}/run"

python -u -c "print('stdout line'); import sys; sys.stderr.write('tqdm-ish stderr\n')" \
	2> >(tee "${LOG}.err" >&2) | tee "${LOG}.out" >/dev/null
# The process substitution flushes asynchronously; give it a beat.
sleep 1
grep -q '^stdout line$' "${LOG}.out"
grep -q 'tqdm-ish stderr' "${LOG}.err"

set +o errexit
python -u -c "import sys; sys.exit('boom')" \
	2> >(tee "${LOG}2.err" >&2) | tee "${LOG}2.out" >/dev/null
STATUS=$?
set -o errexit
sleep 1
[[ ${STATUS} -ne 0 ]] || {
	echo "[ERROR] python failure did not propagate through the tee pipeline" >&2
	exit 1
}
[[ -s "${LOG}2.err" ]] || {
	echo "[ERROR] ${LOG}2.err is empty after a failing run" >&2
	exit 1
}

echo "[INFO] tee logging contract holds: separate .out/.err, live passthrough, exit codes propagate."
