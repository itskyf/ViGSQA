# ViGSQA Project Plan

## Project Goal

Build and evaluate a reproducible Vietnamese adaptation of GS-QA that satisfies the course requirements and supports defensible experimental conclusions. The authoritative requirements and initial audit are in `docs/context/00a_context.md` and `docs/context/00b_missing.md`.

## Target Scientific Contribution

ViGSQA extends GS-QA to Vietnamese OSM data and investigates whether database grounding plus output-type-aware handling can address failures of direct LLM answering and vanilla Text2SQL. The exact improvement is selected from frozen-baseline error evidence; typed deterministic rendering is the current primary hypothesis, not a committed method. Vietnamese-specific robustness and error analysis form a second contribution axis.

## Tasks

| ID | Goal | Status | Current state |
| --- | --- | --- | --- |
| T01 | Establish a trustworthy Vietnamese benchmark | `done` | `v1.0.0` frozen (2026-08-28) from the pinned `vietnam-260825` snapshot, seed 42, 800/800 verified, jsonl byte-identical to the prior freeze so its 80/80 human QC carries over. Published as the `data-v1.0.0` GitHub Release asset; restored by `scripts/restore_dataset.sh`. |
| T02 | Make the whole experiment runnable end-to-end | `done` | All coursework cells implemented (health gates, dataset restore + EDA, smoke baselines, masked comparison, error taxonomy, grounded 5-question demo, extension point). Full local run passes; the exit criterion passed on 2026-08-29 — a fresh Colab VM cloned `main` and ran all cells end-to-end with zero errors, tables matching local greedy-decoding output. llama.cpp now serves on repo-wide port 8000; Colab bootstrap uses non-editable `uv pip install --python sys.executable .`, kernel-stop on bootstrap failure, `punkt_tab` download, and `NLTK_ALLOW_PROXIED_URLOPEN=1` (details in the task record). 2026-08-29 presentation pass: §4 cells numbered `####` with minijinja-rendered example/demo cards; fixed a `gold_summary` display bug that hid `knn+distance` gold distances (data unaffected). Packaging pass: `baselines/` is a top-level package of the distribution (upstream `baselines.py` renamed `pipeline.py`); the Vietnamese CLI is now `python -m baselines.baselines_vi` from the repo root and the notebook imports the patched pipeline without `sys.path` hacks. |
| T03 | Measure correctly and establish official baselines | `planned` | Validate metric semantics per answer type (best-match against full gold candidate sets), then run and report the official full 800-question comparison on the frozen benchmark. |
| T04 | Improve what the frozen baselines fail at | `planned` | Select the intervention from full-baseline error evidence; the typed deterministic renderer stays a hypothesis until that evidence supports it. Plugs into the `baselines_vi.py` patch layer without a pipeline rewrite. |
| T05 | Analyze Vietnamese-specific behavior and errors | `planned` | Full/stripped diacritic surfaces exist; robustness, error taxonomy, and new-data demonstration remain. |
| T06 | Tell the story as an ACL paper | `planned` | Course requires the official ACL style files; the current `report/main.typ` Typst placeholder is replaced in T06. |

## Cross-Task Discoveries

- Official experiments use the frozen benchmark and the matching pinned snapshot (`https://download.geofabrik.de/asia/vietnam-260825.osm.pbf`), which is hardcoded directly in `download_osm.sh` along with its SHA-256 checksum.
- All pre-freeze result artifacts (`baselines/*_eval.csv`, `baselines/REPORT_VN_GEOQA.md`, `docs/results.md`) are archived, describe a superseded candidate dataset, and must not be used as benchmark evidence.
- The dataset lives outside version control; restore it with `scripts/restore_dataset.sh` (public Release asset) or byte-identical regeneration with the pinned seed. Read through the `generator/questions_vi` symlink; never commit `data/`.
- Range-type gold answers are full distance-ordered sets (up to ~1254 candidates): score predictions by best applicable match against the complete gold set; never require exhaustive enumeration. T03 owns metric semantics.
- The T02 smoke produced identical evaluation tables locally and on a fresh Colab VM (greedy decoding, same GGUF), and every environment quirk Colab exposed (port 8000, non-editable uv install, punkt_tab + proxied-urlopen) is now encoded in the bootstrap cell — T03's full run can treat local and Colab executions as equivalent.

## Active Next Action

Start T03: validate metric semantics per answer type, then run the official full 800-question comparison on the frozen benchmark with `RUN_MODE = "full"`.

## Session Prompt

> Continue `<TASK_ID>` from `docs/PLAN.md`. Follow `AGENTS.md`, validate changes, and update the plan and task notes with evidence. If the task is unclear, conflicts with the repository, or reveals suspicious results, pause and ask me to review that task, stating the evidence and decisions needed.
