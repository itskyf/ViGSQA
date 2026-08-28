# ViGSQA Project Plan

## Project Goal

Build and evaluate a reproducible Vietnamese adaptation of GS-QA that satisfies the course requirements and supports defensible experimental conclusions. The authoritative requirements and initial audit are in `docs/context/00a_context.md` and `docs/context/00b_missing.md`.

## Target Scientific Contribution

ViGSQA extends GS-QA to Vietnamese OSM data and investigates whether database grounding plus output-type-aware handling can address failures of direct LLM answering and vanilla Text2SQL. The exact improvement is selected from frozen-baseline error evidence; typed deterministic rendering is the current primary hypothesis, not a committed method. Vietnamese-specific robustness and error analysis form a second contribution axis.

## Tasks

| ID | Goal | Status | Current state |
| --- | --- | --- | --- |
| T01 | Establish a trustworthy Vietnamese benchmark | `done` | `v1.0.0` frozen (2026-08-28) from the pinned `vietnam-260825` snapshot, seed 42, 800/800 verified, jsonl byte-identical to the prior freeze so its 80/80 human QC carries over. Published as the `data-v1.0.0` GitHub Release asset; restored by `scripts/restore_dataset.sh`. |
| T02 | Make the whole experiment runnable end-to-end | `in_progress` | Local smoke passed end-to-end (2026-08-28): both baselines, 8 questions, string ids, read-only SQL, notebook executed fully in smoke mode (integration evidence only). Remaining: the same smoke on Colab from a fresh clone (exit criterion). |
| T03 | Measure correctly and establish official baselines | `planned` | Validate metric semantics per answer type (best-match against full gold candidate sets), then run and report the official full 800-question comparison on the frozen benchmark. |
| T04 | Improve what the frozen baselines fail at | `planned` | Select the intervention from full-baseline error evidence; the typed deterministic renderer stays a hypothesis until that evidence supports it. Plugs into the `baselines_vi.py` patch layer without a pipeline rewrite. |
| T05 | Analyze Vietnamese-specific behavior and errors | `planned` | Full/stripped diacritic surfaces exist; robustness, error taxonomy, and new-data demonstration remain. |
| T06 | Tell the story as an ACL paper | `planned` | Course requires the official ACL style files; the current `report/main.typ` Typst placeholder is replaced in T06. |

## Cross-Task Discoveries

- Official experiments use the frozen benchmark and the matching pinned snapshot (`OSM_URL=https://download.geofabrik.de/asia/vietnam-260825.osm.pbf`); `download_osm.sh`'s `vietnam-latest` default is for producing future versions and demos, never for evaluation.
- All pre-freeze result artifacts (`baselines/*_eval.csv`, `baselines/REPORT_VN_GEOQA.md`, `docs/results.md`) are archived, describe a superseded candidate dataset, and must not be used as benchmark evidence.
- The dataset lives outside version control; restore it with `scripts/restore_dataset.sh` (public Release asset) or byte-identical regeneration with the pinned seed. Read through the `generator/questions_vi` symlink; never commit `data/`.
- Range-type gold answers are full distance-ordered sets (up to ~1254 candidates): score predictions by best applicable match against the complete gold set; never require exhaustive enumeration. T03 owns metric semantics.

## Active Next Action

Run the T02 exit criterion: the same 8-question smoke on Google Colab from a fresh clone (`main.ipynb`, `RUN_MODE=smoke`). Then T03 validates metric semantics and runs the official full-800 comparison.

## Session Prompt

> Continue `<TASK_ID>` from `docs/PLAN.md`. Follow `AGENTS.md`, validate changes, and update the plan and task notes with evidence. If the task is unclear, conflicts with the repository, or reveals suspicious results, pause and ask me to review that task, stating the evidence and decisions needed.
