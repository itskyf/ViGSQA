# T03 — Official v3 Evaluation and Baselines

**Status: in_progress (2026-09-04).** Raw inference is being separated from evaluation without changing its cache namespace or active artifacts. Official evaluation remains open until the required per-baseline artifacts and seals exist.

## Goal

Measure the four frozen v3 Direct/Text2SQL runs with a standalone, reproducible GS-QA evaluator while raw inference remains independently resumable and sealable.

## Contracts

- Raw inference keeps `pv-8394cd22`, all five prompt inputs, frozen decoding, existing cache files, and PostgreSQL cache rows. Its seal covers only `direct_answer`, or `sql_generate` + `sql_exec` + `sql_answer`.
- Evaluation requires a valid raw seal, reads only the corresponding raw answer file, and writes only under `results/evaluation/<model>/<baseline>/`.
- The same selected model parses answers with the frozen baseline-specific parser prompt. Parse artifacts never enter `cache_vi`.
- One explicit T01–T28 family mapping is checked against the frozen manifest: entity/name (T01–T06, T08–T12), textual fact (T07), Location (T13–T20), direction/angle (T21–T22), count (T23–T24), distance (T25–T26), area (T27), length (T28).
- Text normalization is Unicode NFKC + casefold + Unicode punctuation separation + whitespace collapse, preserving Vietnamese diacritics and numbers; token precision/recall/F1 uses no NLTK or stopwords.
- Location scoring extracts non-empty parsed addresses, text-scores them, geocodes only those addresses with Nominatim, and compares them to authoritative gold `geo_wkt` with `min(distance_m / 500000, 1)`. No SQL, database, POI, or coordinate-extraction fallback is permitted.
- Direction uses eight Vietnamese sectors and circular angular error / 180. Numeric families accept finite values, normalize supported metric units, require integral counts, and cap relative error at one.
- Every applicable prediction/gold pairing is considered, including complete range answer sets; deterministic best-match indices are recorded. Attempted status is metric-specific.
- Ordered Nominatim results, including confirmed nulls, are persisted; transient failures abort without an evaluation seal. QID-sorted metrics and a seal bind the raw seal, evaluator/parser identities, parser prompt, and all evaluation artifact hashes.

## Validation and Evidence

- Static: Bash syntax, Python compile/import, Ruff, repository checks, and both entrypoint `--help` paths.
- Focused checks: Vietnamese composed/decomposed normalization, punctuation and digits; angle wrap-around; metric units; non-first range gold selection; Location address geocoded against gold WKT; strict TID validation.
- Operational: resume Qwen Text2SQL through raw inference, prove completed cache reuse and missing `sql_answer` completion, then seal without JSON parse. Hash raw files before/after evaluation, validate both seals, and prove frozen parse/geocode reruns produce byte-identical per-question output.

## Progress (2026-09-04)

- At the user's direction, interrupted the legacy Qwen Text2SQL process cleanly during `sql_answer`: `sql_generate` and `sql_exec` remain 2,800/2,800; `sql_answer` remains valid at 2,052/2,800. Before/after SHA-256 values are identical (`179d08f8…`, `db8ff557…`, `5671e23c…` respectively), so no cache conversion was needed.
- Added the raw-only entrypoint and changed the official runner/raw seal to the three-stage contract. The old Vietnamese evaluator patch and every SQL/DB/coordinate/POI Location fallback were deleted from the inference configuration path.
- Added the standalone evaluator, explicit T01–T28 mapping validation, deterministic text/typed/spatial best-match scoring, persistent Nominatim results, QID-sorted metrics, and a separate evaluation seal/check path.
- Offline validation is green: Python compilation, Ruff, Bash syntax, logging contract, help/import checks (no NLTK/evaluator/geocoder import on raw path), evaluator contract checks, diff whitespace, and byte-identical interrupted raw artifacts. Live resume, raw sealing, official evaluation artifacts, raw immutability across evaluation, and byte-identical sealed evaluation rerun remain pending.

## Next

Resume Qwen Text2SQL with `scripts/run_official.sh --llm-concurrency 4`; it should reuse the 2,800 SQL generations/executions and 2,052 answers, fill the remaining 748 answers, and raw-seal without parsing. Then run and verify the separate evaluation. Keep T03 open until all required official outputs exist.
