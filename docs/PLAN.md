# ViGSQA Project Plan

## Project Goal

Build and evaluate a reproducible Vietnamese adaptation of GS-QA (`docs/context/00a_context.md`) that satisfies the course requirements — a runnable notebook, baseline comparison, evaluation, error analysis, and a Vietnamese demo — and supports defensible experimental conclusions.

## v3.0.0 Reproducibility Contract

- Dataset `v3.0.0`: 28 canonical GS-QA TIDs × 100 = 2,800 questions, seed 42, generated from the pinned Geofabrik snapshot `vietnam-260901.osm.pbf` (md5 verified against the Geofabrik sidecar in `download_osm.sh`; never `vietnam-latest`).
- Location gold (T13–T20): frozen geometry (`geo_wkt`) **and** native OSM address components **and** one deterministic canonical address string built only from those components; candidates are restricted to address-bearing POIs by a criterion fixed by the coverage audit; geometry stays the authoritative spatial reference.
- T7/T8 external facts (frozen viwiki/enwiki infobox values) are genuinely out-of-schema: no T7/T8 answer attribute is exposed as a reference-DB column (verifier-enforced).
- Official baselines: Ornith/Qwen × Direct/Text2SQL over an external OpenAI-compatible vLLM endpoint (`ornith-ai/Ornith-1.5-9B-NVFP4`, `AxionML/Qwen3.5-9B-NVFP4`), frozen decoding profile (T11: temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence_penalty 1.5, repetition_penalty 1.0, max_completion_tokens 32768, seed 42, thinking on), frozen prompts, bounded concurrency, raw QID-indexed JSON artifacts under `cache_vi/pv-<prompt_sha256>/`, G6 artifact-integrity seal binding dataset + prompt + OSM/DB provenance.
- v1/v2 artifacts (releases, raw JSONs, logs, seals, QC records) are historical evidence only; old seals can never satisfy v3; the PostgreSQL semantic LLM cache was purged once at T11 (v2 rows and file caches deleted — the llama.cpp/temperature-0 era ended), after which the T09 cache-key contract again guarantees natural misses across profile changes.

## Why v1/v2 were superseded

- **v1 (8 template families, `data-v1.0.0`)** — first frozen benchmark; subsumed by v2's all-28-TID expansion.
- **v2 (28 TIDs, `data-v2.0.0`)** — spatial semantics validated and all four raw runs sealed, but Location gold was coordinates-only (importer kept `addr:city` alone), which cannot reproduce GS-QA's address-text Location evaluation; additionally the `capacity` column leaked a T7/T8 external fact into the Text2SQL schema. v3 rebuilds the benchmark on `vietnam-260901.osm.pbf` with native address columns. v2 raw inference is superseded before official evaluation and preserved only as historical evidence.

## Naming rule

`v3.0.0` appears only as release lineage: the `data-v3.0.0` release tag (download URLs), `scripts/v3.0.0.sha256`, and the dataset MANIFEST `version` field. Asset filenames (`vn-geoqa.zip`, `osm-vn.sql.gz`), tools, and local paths carry no version. `scripts/v2.0.0.sha256` is retained so v2 stays restorable.

## Tasks

| ID | Goal | Status | Current state |
| --- | --- | --- | --- |
| T01 | Establish a trustworthy Vietnamese benchmark | `done` | Satisfied **at v3**: T10 re-validated the frozen benchmark (2,800/2,800 automated verification, byte-identical regeneration, human QC approval). The v1/v2 freezes remain Git/history evidence. |
| T02 | Make the whole experiment runnable end-to-end | `planned` | **Reopened for v3.** The v2 proof (fresh Colab VM) is tooling evidence only. v3 re-proof pending: T11 bumped the notebook's v3 pins and vLLM endpoint plumbing; the end-to-end re-run (bootstrap → dataset → baseline on v3 assets) rides with T03/T05 once the four v3 raw runs exist. |
| T03 | Measure correctly and establish official baselines | `in_progress` | Raw/evaluation entrypoints and separate seals implemented; Qwen Text2SQL was cleanly paused at 2,052/2,800 `sql_answer` records with all raw hashes preserved. Offline contracts pass. Live resume/seal and the four official evaluation artifact sets remain. Record: `docs/plans/T03-official-v3-evaluation.md`. |
| T04 | Improve what the frozen baselines fail at | `planned` | Starts from T03 sealed per-question evidence; no intervention is selected in advance. Record: `docs/plans/T04-baseline-improvement.md`. |
| T05 | Analyze Vietnamese-specific behavior and errors | `planned` | Depends on official T03 evidence (and retained T04 results); covers robustness, error taxonomy, and the Vietnamese demo. Record: `docs/plans/T05-vietnamese-error-analysis.md`. |
| T06 | Tell the story as an ACL paper | `planned` | Depends on T03–T05 evidence; ACL report claims and tables remain artifact-traceable. Record: `docs/plans/T06-acl-paper.md`. |
| T07 | Complete the v2 benchmark and capture raw baseline runs | `done` | v2-scoped by goal: all four v2 runs G6-valid and sealed (2026-09-03), then superseded as evidence by v3 before evaluation. The v3 equivalent (four fresh raw runs) is launched manually by the user — its capture is tracked under T03. Record: `docs/plans/T07-benchmark-v2-raw-runs.md`. |
| T08 | Fast database bootstrap via prebuilt release dump | `done` | Version-agnostic capability, re-verified **at v3** inside T10: clean-DB restore from the published `data-v3.0.0` dump matched all G1′ counts (five tables + import marker). |
| T09 | PostgreSQL LangChain LLM cache + bounded LLM concurrency | `done` | Architecture preserved unchanged in v3; the prompt-version namespace (`pv-8394cd22`) isolates v3 keys from the v2 rows. First v3 exercise happens with the official runs. Record: `docs/plans/T09-llm-cache-postgres.md`. |
| T10 | v3.0.0 benchmark refactor | `done` | v3 frozen and published (`data-v3.0.0`: dataset + DB dump, both restores verified from the release); all gates G1′–G6′ passed including byte-identical regeneration, human QC approval, prompt freeze `pv-8394cd22`, v2-seal negative test; no official inference launched. Record: `docs/plans/T10-benchmark-v3-refactor.md`. |
| T11 | Official inference on an external vLLM endpoint | `done` | All llama.cpp code/config/docs removed from the official path; `baselines_vi.build_model_vi` serves both NVFP4 models through standard OpenAI env vars with one frozen decoding profile; `run_official.sh` probes the endpoint per model (curl `/v1/models` gate), compose keeps an optional `vllm` service (`--reasoning-parser qwen3`); step records gained diagnostic `gen` metadata; all LLM caches purged. Record: `docs/plans/T11-vllm-official-inference.md`. |

## Cross-Task Contracts

- Official experiments consume only published frozen assets (`data-v3.0.0` release) — never a mutable local DB/dataset — and the pinned snapshot verified by `download_osm.sh`.
- The dataset lives outside version control; restore with `scripts/restore_dataset.sh` or byte-identical regeneration (seed 42, frozen `wikipedia_cache_vi.json`). Read through the `generator/questions_vi` symlink; never commit `data/` or `main.ipynb`.
- T09's cache-key contract governs every cache interaction: same semantic model request at a different transport endpoint → cache reuse; different model/quantization/generation parameters/prompt → separate cache. JSON step caches are write-through raw artifacts; PostgreSQL `llm_cache` is the LLM-step skip layer. Exhausted structural-validation failures stay explicit; transport/configuration failures stay retryable; structurally valid but incorrect outputs are never retried.
- Official completion is a valid G6 seal bound to model/baseline, frozen dataset and prompt identities, repository-pinned OSM/DB provenance, and raw artifact hashes. Git commit is provenance-only.
- Range-type gold answers are full distance-ordered sets: score predictions by best applicable match against the complete gold set (T03).

## Validation Gates (T10)

G1′ DB rebuild (five tables non-empty, representative spatial ops, address coverage audit, T7/T8 overlap audit) → G2′ smoke 5×28 → G3′ full seed-42 generation, 2,800/2,800 automated verification, byte-identical regeneration → G4′ human QC (~5/TID) with user approval → prompt freeze (new `pv-*` hash; no official-runner invocations between prompt edit and dataset freeze) → G5′ runner static checks + v2-seal negative test → G6′ publish `data-v3.0.0` and verify dataset/DB restore. No official inference is launched inside T10.

## Active Next Action

**Resume Qwen Text2SQL through `scripts/run_official.sh --llm-concurrency 4`.** The raw-only path should reuse 2,800 `sql_generate`, 2,800 `sql_exec`, and 2,052 `sql_answer` records, fill only the missing answers, and seal without JSON parsing. Evaluate each raw-sealed run separately with `scripts/run_evaluation.py`; keep T03 open until all official evaluation artifacts/seals exist.

## Session Prompt

> Continue `<TASK_ID>` from `docs/PLAN.md`. Follow `AGENTS.md`, validate changes, and update the plan and task notes with evidence. If the task is unclear, conflicts with the repository, or reveals suspicious results, pause and ask me to review that task, stating the evidence and decisions needed.
