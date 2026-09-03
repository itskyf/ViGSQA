# ViGSQA Project Plan

## Project Goal

Build and evaluate a reproducible Vietnamese adaptation of GS-QA that satisfies the course requirements and supports defensible experimental conclusions. The authoritative requirements and initial audit are in `docs/context/00a_context.md` and `docs/context/00b_missing.md`.

## Target Scientific Contribution

ViGSQA extends GS-QA to Vietnamese OSM data and investigates whether database grounding plus output-type-aware handling can address failures of direct LLM answering and vanilla Text2SQL. The exact improvement is selected from frozen-baseline error evidence; typed deterministic rendering is the current primary hypothesis, not a committed method. Vietnamese-specific robustness and error analysis form a second contribution axis.

## Naming rule

`v2.0.0` appears only as release lineage: the `data-v2.0.0` release tag (download URLs), `scripts/v2.0.0.sha256`, and the dataset MANIFEST's `version` field. Asset filenames (`vn-geoqa.zip`, `osm-vn.sql.gz`), tools, and local paths carry no version.

## Tasks

| ID | Goal | Status | Current state |
| --- | --- | --- | --- |
| T01 | Establish a trustworthy Vietnamese benchmark | `done` | Frozen benchmark published (`data-v2.0.0` release, seed 42, 800/800 then 2,800/2,800 verified); restored by `scripts/restore_dataset.sh`. |
| T02 | Make the whole experiment runnable end-to-end | `done` | All coursework cells implemented and proven end-to-end on a fresh Colab VM; `main.ipynb` is the executable notebook (Drive/Colab holds the authoritative copy). |
| T03 | Measure correctly and establish official baselines | `planned` | Validate metric semantics per answer type (best-match against full gold candidate sets), then aggregate and report the official comparison over the raw artifacts (see T07). Raw caches are authoritative pre-evaluation evidence; interim eval CSVs are provisional. |
| T04 | Improve what the frozen baselines fail at | `planned` | Select the intervention from full-baseline error evidence; the typed deterministic renderer stays a hypothesis until then. Plugs into the `baselines_vi.py` patch layer without a pipeline rewrite. |
| T05 | Analyze Vietnamese-specific behavior and errors | `planned` | Full/stripped diacritic surfaces exist; robustness, error taxonomy, and the final demonstration on new Vietnamese questions remain. |
| T06 | Tell the story as an ACL paper | `planned` | Course requires the official ACL style files; the current Typst placeholder is replaced in T06. |
| T07 | Complete the benchmark and capture raw baseline runs | `in_progress` | Ornith Direct and Text2SQL are G6-valid and sealed. Qwen inference/resume remains in progress and is not sealed. T07 finishes only after all four official pairs pass G6 and their seals verify. Record: `docs/plans/T07-benchmark-v2-raw-runs.md`. |
| T08 | Fast database bootstrap via prebuilt release dump | `done` | `bootstrap_postgres.sh` restores `osm-vn.sql.gz` (release `data-v2.0.0`, SHA-256 pinned) before falling back to the osm2pgsql import; verified on PostgreSQL 18 and 14/PostGIS 3.5 with exact reference counts. |
| T09 | PostgreSQL LangChain LLM cache + bounded LLM concurrency | `in_progress` | PostgreSQL remains request-level resume/repair state and is excluded from run seals. Release publication of the completed cache dump is deferred until explicit confirmation that Qwen has finished. Record: `docs/plans/T09-llm-cache-postgres.md`. |

## Cross-Task Discoveries

- Official experiments use the frozen benchmark and the matching pinned OSM snapshot (`https://download.geofabrik.de/asia/vietnam-260825.osm.pbf`), verified against the Geofabrik md5 sidecar in `download_osm.sh`.
- The dataset lives outside version control; restore with `scripts/restore_dataset.sh` (release asset) or byte-identical regeneration with the pinned seed. Read through the `generator/questions_vi` symlink; never commit `data/` or `main.ipynb`.
- All pre-freeze result artifacts (`baselines/*_eval.csv`, `baselines/REPORT_VN_GEOQA.md`, `docs/results.md`) are archived and describe a superseded dataset; never use them as benchmark evidence.
- Range-type gold answers are full distance-ordered sets (up to ~1254 candidates): score predictions by best applicable match against the complete gold set. T03 owns metric semantics.
- T09's cache-key contract governs every cache interaction: same semantic model request at a different transport endpoint → cache reuse; different model/quantization/generation parameters/prompt → separate cache. JSON step caches remain write-through raw artifacts and PostgreSQL `llm_cache` is the LLM-step skip layer. Exhausted structural-validation failures remain stable explicit raw artifacts; transport/configuration failures remain distinguishable and retryable on resume. Structurally valid but incorrect outputs are never retried.
- Official completion is a valid G6 seal bound to model/baseline, frozen dataset and prompt identities, repository-pinned OSM/database provenance, and raw artifact hashes. Git commit is provenance-only; an all-sealed official run exits before infrastructure startup.

## Active Next Action

T07: **finish Qwen → G6 each Qwen baseline → seal each → verify all four seals → mark T07 done → activate T03.** Do not Run All `main.ipynb` against the canonical sealed cache before T03; defer notebook cleanup and final execution until official evaluation can consume the sealed raw artifacts safely.

## Session Prompt

> Continue `<TASK_ID>` from `docs/PLAN.md`. Follow `AGENTS.md`, validate changes, and update the plan and task notes with evidence. If the task is unclear, conflicts with the repository, or reveals suspicious results, pause and ask me to review that task, stating the evidence and decisions needed.
