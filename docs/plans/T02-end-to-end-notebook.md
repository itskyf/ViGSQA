# T02 — End-to-End Experiment Workflow

**Status: in_progress (2026-08-28).** Contract repairs applied and the local smoke passed end-to-end; the Colab smoke (exit criterion) remains.

## Goal

Make the whole experiment runnable end-to-end: a course notebook that restores the frozen benchmark, builds the pinned reference database, runs Direct and Text2SQL baselines through a local llama.cpp server, and evaluates — locally by reusing the checkout and on Colab by cloning the repository.

## Invariants

| Aspect | Contract |
| --- | --- |
| Notebook | `main.ipynb` is the executable course notebook; local runs reuse the checkout, Colab clones to `/content/ViGSQA` and `%cd`s there |
| Dataset | frozen `v1.0.0` with stable string ids; restored via `scripts/restore_dataset.sh`; never commit `data/` |
| Reference DB | pinned `vietnam-260825.osm.pbf` via `OSM_URL` for benchmark, smoke, and full; `vietnam-latest` only for demos/future versions |
| LLM server | llama.cpp exposing the OpenAI-compatible `/v1` endpoint (compose service on port 8080; Colab starts its own) |
| Python client | `langchain_openai.ChatOpenAI` only — no custom chat wrappers, no Ollama |
| Model | `ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M`, addressed as `llamacpp:ornith` |
| Smoke | 8 deterministic questions (first of each type file), run **before** the method/prompt freeze; integration evidence only |
| Full | all 800 questions — owned by T03 |
| Baselines | Direct and Text2SQL only (never `--baseline all`; it pulls RAG/shuffled) |
| Contribution | extension point is the `baselines_vi.py` patch layer; T04 adds a third method without rewriting the pipeline |
| Exit criterion | the same smoke path passes on Colab end-to-end |

## Notebook Structure

Numbered sections map one-to-one onto the rubric's required stages: 0 Bootstrap (Colab clone / local checkout) · 1 Environment · 2 Dataset restore + checks · 3 Reference DB (pinned snapshot) · 4 Model + health check · 5 Run config (`RUN_MODE = smoke \| full`) · 6 EDA · 7 Direct baseline · 8 Text2SQL baseline · 9 Evaluation · 10 Comparison · 11 Error analysis · 12 New Vietnamese demo · 13 T04 extension point. The rubric prescribes this structure; it is not left open.

## Decisions

- Smoke runs **before** the method and prompt freeze — its purpose is to catch integration bugs (load → LLM → SQL → DB → parse → metric) while repairs are still cheap. Smoke results are never benchmark evidence and never prompt-tuning input. (Reverses the earlier "only after freeze" decision.)
- Colab validation is in scope for T02, not deferred: local coherence first, then the same smoke on Colab is the exit criterion. (Reverses the earlier deferral.)
- Notebook cells invoke the baselines as a subprocess CLI (`!python baselines/baselines_vi.py --model llamacpp:ornith --baseline <b> --mode $RUN_MODE`): `_vn_evaluate_answers` reads `sys.argv` to locate the `sql_exec` cache, so import-based invocation would silently break location-type scoring.
- The model client is `ChatOpenAI(base_url=f"{LLAMACPP_URL}/v1")`; llama.cpp applies the chat template from the GGUF, so no per-model prompt formatting exists in this repo. The previous custom `_LlamaCppChat`/`_OllamaChat` wrappers are deleted.
- Generated SQL executes under `default_transaction_read_only` plus a statement timeout — sufficient isolation for a course project; no role/permission architecture.
- Known contract mismatches fixed as part of this task (demonstrated by evidence, not tuning): `load_questions()` overwrote frozen string ids with positional ints; Direct inherited English prompts requiring rounded number words and address output while the frozen benchmark scores exact digits and lon/lat; the Text2SQL prompt advertised `cuisine`, `operator`, `wikidata` columns the `pois` view does not expose; DB credentials were hard-coded instead of `PG*`.
- Reference DB and model server are environment setup, not lineage objects: provenance for official experiments is the six-tuple dataset version, OSM snapshot, model + quantization, prompt/method version, metric definition, results artifact.

## Validation

- `load_questions("smoke")` returns 8 records with string ids; `load_questions("full")` returns 800.
- Read-only holds: `SELECT COUNT(*) FROM pois` succeeds, `CREATE TABLE` fails.
- `curl {LLAMACPP_URL}/health` and one `ChatOpenAI(...).invoke("ping")` succeed before any baseline run.
- Local smoke produces 8 cached records per baseline keyed by string ids and 8-row eval CSVs; location rows carry distance values.
- The same smoke path passes on Colab from a fresh clone (exit criterion).

**Local smoke evidence (2026-08-28, integration-only — not benchmark evidence):**
`llamacpp:ornith` on llama.cpp `/v1` (compose, alias `ornith`), pinned DB. Direct: 8/8 answered, text F1 ≈ 0 (expected — no local-POI knowledge). Text2SQL: 8/8, 0 SQL execution errors; text F1 1.0 on `knn+distance`/`knn+name`/`range+count`/`range:direction+name`, parsed `distance_error` 0.0 on `knn+loc`, `relative_error` 5e-4 on `knn+distance`. Notebook executed fully in smoke mode, including the new-question demo (correct KNN SQL + grounded answer).

## Open Questions

- Which llama-server install method to use on Colab (prebuilt CUDA binary vs `pip install llama-cpp-python[server]`): decide by what works on the Colab runtime; record here.

## Next

After T01 publishes `v1.0.0`: apply the baseline contract repairs, rebuild the notebook, run the local smoke, then the Colab smoke.
