# T02 — End-to-End Experiment Workflow

**Status: in_progress (2026-08-28).** The idempotent two-branch bootstrap and prior local smoke passed. The coursework outline is restored; downstream executable cells and the fresh-Colab smoke remain.

## Goal

Make the whole experiment runnable end-to-end: a course notebook that restores the frozen benchmark, builds the pinned reference database, runs Direct and Text2SQL baselines through a local llama.cpp server, and evaluates — locally by reusing the checkout and on Colab by cloning the repository.

## Invariants

| Aspect | Contract |
| --- | --- |
| Notebook | `main.ipynb` is the executable course notebook; local runs reuse the checkout, Colab clones to `/content/ViGSQA` and `%cd`s there |
| Dataset | frozen `v1.0.0` with stable string ids; restored via `scripts/restore_dataset.sh`; never commit `data/` |
| Reference DB | pinned `vietnam-260825.osm.pbf` hardcoded in `scripts/download_osm.sh` with SHA-256 verification |
| LLM server | llama.cpp router mode using `config/models.ini` preset on port 8080 (compose service; Colab starts its own) |
| Python client | `langchain_openai.ChatOpenAI` only — no custom chat wrappers, no Ollama |
| Model | `llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M` (preset with context 8192, no-mmproj) |
| Smoke | 8 deterministic questions (first of each type file), run **before** the method/prompt freeze; integration evidence only |
| Full | all 800 questions — owned by T03 |
| Baselines | Direct and Text2SQL only (never `--baseline all`; it pulls RAG/shuffled) |
| Contribution | extension point is the `baselines_vi.py` patch layer; T04 adds a third method without rewriting the pipeline |
| Exit criterion | the same smoke path passes on Colab end-to-end |

## Bootstrap Structure

`main.ipynb` launches two independent external workflows and waits for both before any exploration or experiment:

- llama.cpp: local runs reuse the `compose.yaml` service; Colab installs llama.cpp with the official installer only when missing, then starts `llama serve --models-preset config/models.ini --models-max 1`. A healthy or loading endpoint is reused, so reruns do not install or spawn duplicates.
- PostgreSQL/OSM: local runs reuse the compose database and its defaults; Colab installs the required PostgreSQL/PostGIS tools with apt, starts PostgreSQL, and performs the minimal initialization. The pinned OSM download and marker-based import are separate idempotent steps.

One notebook code cell performs runtime setup, launches two `subprocess.Popen` processes, and waits at a barrier with branch logs kept visible. After startup, psycopg3 performs bounded readiness and PostGIS/POI validation. Dependency installation never starts services or imports data.

After the barrier, H2/H3 markdown outlines the required coursework sections: dataset restore/checks, run config (`RUN_MODE = smoke \| full`), EDA, Direct, Text2SQL, evaluation, comparison, error analysis, new Vietnamese demo, and the T04 extension point. Their executable cells remain to be implemented.

## Decisions

- Smoke runs **before** the method and prompt freeze — its purpose is to catch integration bugs (load → LLM → SQL → DB → parse → metric) while repairs are still cheap. Smoke results are never benchmark evidence and never prompt-tuning input. (Reverses the earlier "only after freeze" decision.)
- Colab validation is in scope for T02, not deferred: local coherence first, then the same smoke on Colab is the exit criterion. (Reverses the earlier deferral.)
- Notebook cells invoke the baselines as a subprocess CLI (`!python baselines/baselines_vi.py --model llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M --baseline <b> --mode $RUN_MODE`): `_vn_evaluate_answers` reads `sys.argv` to locate the `sql_exec` cache, so import-based invocation would silently break location-type scoring.
- The model client is `ChatOpenAI(base_url=f"{LLAMACPP_URL}/v1")`; llama.cpp applies the chat template from the GGUF, so no per-model prompt formatting exists in this repo. The previous custom `_LlamaCppChat`/`_OllamaChat` wrappers are deleted.
- Generated SQL executes under `default_transaction_read_only` plus a statement timeout — sufficient isolation for a course project; no role/permission architecture.
- Known contract mismatches fixed as part of this task (demonstrated by evidence, not tuning): `load_questions()` overwrote frozen string ids with positional ints; Direct inherited English prompts requiring rounded number words and address output while the frozen benchmark scores exact digits and lon/lat; the Text2SQL prompt advertised `cuisine`, `operator`, `wikidata` columns the `pois` view does not expose; DB credentials were hard-coded instead of `PG*`.
- Reference DB and model server are environment setup, not lineage objects: provenance for official experiments is the six-tuple dataset version, OSM snapshot, model + quantization, prompt/method version, metric definition, results artifact.
- Bootstrap concurrency stays shell/process based: two `Popen` calls plus a wait barrier, not a Python concurrency abstraction. Local services belong to compose; only Colab installs llama.cpp or apt-managed PostgreSQL.
- Shell scripts consistently test a non-empty `COLAB_RELEASE_TAG` for the Colab branch; reusable psycopg readiness/PostGIS/POI checks live in `scripts/check_postgres.py` instead of inline Python heredocs.

## Validation

- `load_questions("smoke")` returns 8 records with string ids; `load_questions("full")` returns 800.
- Read-only holds: `SELECT COUNT(*) FROM pois` succeeds, `CREATE TABLE` fails.
- `curl {LLAMACPP_URL}/health` and one `ChatOpenAI(...).invoke("ping")` succeed before any baseline run.
- Local smoke produces 8 cached records per baseline keyed by string ids and 8-row eval CSVs; location rows carry distance values.
- The same smoke path passes on Colab from a fresh clone (exit criterion).

**Local bootstrap evidence (2026-08-28):** a fresh compose database imported
the pinned snapshot into 38,223 POIs while llama.cpp became healthy. The
immediate rerun reused both containers and the existing PBF/import marker; the
complete bootstrap-only notebook then executed through its readiness barrier.

**Local smoke evidence (2026-08-28, integration-only — not benchmark evidence):**
`llamacpp:ornith` on llama.cpp `/v1` (compose, alias `ornith`), pinned DB. Direct: 8/8 answered, text F1 ≈ 0 (expected — no local-POI knowledge). Text2SQL: 8/8, 0 SQL execution errors; text F1 1.0 on `knn+distance`/`knn+name`/`range+count`/`range:direction+name`, parsed `distance_error` 0.0 on `knn+loc`, `relative_error` 5e-4 on `knn+distance`. Notebook executed fully in smoke mode, including the new-question demo (correct KNN SQL + grounded answer).

**Post-refactor smoke evidence (2026-08-28):** `generator_vi.py` and `baselines_vi.py` moved to psycopg3 (baselines_vi also dropped its `_` import aliases), and `save_eval` now flattens `/` in model tags so the verbatim README_VI command (full `org/repo:quant` tag, no server alias) writes its CSVs — both smokes pass end-to-end with those commands.

**Bootstrap repair evidence (2026-08-28):** all initialization and existence-check SQL lives in linted files under `sql/`; shell code only passes variables and invokes `psql --file`. `sqlfluff lint sql/`, Ruff, ShellCheck, and Bash syntax checks pass. The consolidated one-cell notebook passed two consecutive local executions; both reused the healthy llama.cpp server, existing OSM snapshot, and completed 38,223-POI import.

## Next

Implement the downstream coursework cells behind the barrier, then run the full smoke path from a fresh Colab clone.
