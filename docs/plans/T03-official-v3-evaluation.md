# T03 — Official v3 Evaluation and Baselines

**Status: in_progress (2026-09-04).** Raw inference is being separated from evaluation without changing its cache namespace or active artifacts. Official evaluation remains open until the required per-baseline artifacts and seals exist.

## Goal

Measure the four frozen v3 Direct/Text2SQL runs with a standalone, reproducible GS-QA evaluator while raw inference remains independently resumable and sealable.

## Contracts

- Raw inference uses `pv-26b1ac0d`, derived only from its three prompts, with frozen decoding and unchanged PostgreSQL cache rows. Its seal covers only `direct_answer`, or `sql_generate` + `sql_exec` + `sql_answer`; parser prompts belong only to evaluation.
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
- Offline validation is green: Python compilation, Ruff, Bash syntax, logging contract, help/import checks (no NLTK/evaluator/geocoder import on raw path), evaluator contract checks, diff whitespace, and byte-identical raw migration. Official evaluation artifacts, raw immutability across evaluation, and byte-identical sealed evaluation rerun remain pending.
- Qwen resume subsequently completed both raw baselines at 2,800 questions and produced valid raw seals. The raw namespace was reduced from the legacy five-prompt hash `pv-8394cd22` to the three-prompt hash `pv-26b1ac0d`; an ad-hoc verified copy preserved the complete source namespace and PostgreSQL cache.
- Ornith subsequently completed both raw baselines, leaving all four runs sealed under `pv-26b1ac0d`. At the user's explicit request, Qwen `range+loc-026` received one post-seal retry after its original three empty completions; the identical request then returned a valid, normally terminated answer. A first operator invocation omitted `OPENAI_BASE_URL`, causing ten 401 records before the systemic-failure guard stopped it; the affected raw files were restored byte-identically from preserved backups before the targeted retry. The resealed Qwen artifact differs only at that QID and now has zero explicit `sql_answer` failures.
- The PostgreSQL cache contains 16,800 non-empty, normally terminated generations (8,400/model; two semantic model keys). `llm-cache-20260904.sql.gz` was gzip-checked, restored into an isolated temporary database at exactly 16,800 rows, and replaced on the `data-v3.0.0` GitHub Release (5,397,172 bytes; SHA-256 `4726eaad9859475d9fc0af7430cbb5c7d528238af1353e5a46386b9c224fac2c`).

## Next

Run and verify the four separate evaluations. Keep T03 open until all required official outputs exist.
