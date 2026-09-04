# T11 — Official Inference on an External vLLM Endpoint

**Status: done (2026-09-04).** Every llama.cpp-specific script, config, prefix, URL, and doc is removed from the official inference path; `inference.sh` (renamed from `run_official.sh` during T03) and `main.ipynb` target an external OpenAI-compatible vLLM endpoint through standard OpenAI env vars with one frozen decoding profile; all existing LLM caches are purged.

## Goal

Serve both official models (`ornith-ai/Ornith-1.5-9B-NVFP4`, `AxionML/Qwen3.5-9B-NVFP4`) from an already-running external vLLM instead of the llama.cpp router stack (compose `llamacpp` + haproxy + `config/models.ini` + Colab installer), with a frozen, documented decoding profile and no reusable results from the llama.cpp/temperature-0 era.

## Invariants

| Aspect | Contract |
| --- | --- |
| Endpoint | external, already running; addressed only via standard env vars — `OPENAI_BASE_URL` (default `http://127.0.0.1:8000/v1`; `OPENAI_API_BASE` also honored by langchain-openai) and `OPENAI_API_KEY` (factory falls back to `not-needed` for keyless local vLLM; never a real credential) |
| Client | `baselines_vi.build_model_vi` (installed as `pipeline.build_model`/`build_parser_model`); the notebook imports the same factory, so CLI and notebook share the identical profile |
| Profile (frozen, both models) | thinking on via default chat behavior (no `chat_template_kwargs`), `temperature=1.0`, `top_p=0.95`, `top_k=20`, `min_p=0.0`, `presence_penalty=1.5`, `repetition_penalty=1.0`, `max_completion_tokens=32768`, `seed=42`; vLLM-only samplers ride in `extra_body`; never deprecated `max_tokens`; no tool-calling config |
| Serving (repo-maintained only) | `compose.yaml` `vllm` service, one model per server, `--reasoning-parser qwen3 --language-model-only --max-model-len auto`, model selectable via `VLLM_MODEL` (default `AxionML/Qwen3.5-9B-NVFP4`); no other serving flags; no `--served-model-name` (served id = HF repo id) |
| Reasoning | `--reasoning-parser qwen3` keeps `<think>` text out of `content`; evaluation and stage validation read `content` only; step records persist only diagnostic `gen` metadata (`finish_reason`, `completion_tokens`, `reasoning_tokens` when the API reports them) — never chain-of-thought text |
| Runner | `inference.sh` probes the endpoint (curl `--retry` against `${OPENAI_BASE_URL}/models` for cold loads, then a served-id `grep --fixed-strings` gate that fails fast listing missing ids); one model per invocation via `MODELS="<id>"`; the runner never starts the LLM server, only postgres + dataset restore |
| Cache | T09 architecture unchanged and no profile-hash machinery added — `extra_body` and all standard kwargs already enter the cache key through `_get_llm_string()`; every pre-T11 cache was deleted instead (see Decisions) |

## Decisions

- **Per-model invocation, not server rotation** (user choice): vLLM serves one model, so the official workflow is "restart vLLM with `VLLM_MODEL=<id>`, run `MODELS=\"<id>\" ./scripts/inference.sh`" per model. `scripts/run_qwen_official.sh` is deleted (its single-model pass is the `MODELS` override). The runner still iterates all pending pairs but fails fast before any inference if the endpoint does not serve a pending model.
- **Factory always routes to the endpoint** — no `llamacpp:`-style prefix and no official-model allowlist: every `--model` passed to `baselines_vi` is treated as a served model id, and a wrong id fails loudly as an HTTP 404 from the server. Upstream `pipeline.build_model` (Ollama/Anthropic) remains untouched for the English legacy path, but `baselines_vi` no longer falls through to it.
- **`api_key` fallback lives in the factory** (`os.environ.get("OPENAI_API_KEY") or "not-needed"`): one place covers keyless local vLLM for CLI and notebook; a real endpoint overrides via env. Verified: `ChatOpenAI` construction raises without any key, so the fallback is required, not cosmetic.
- **Profile keys the cache for free**: verified in the pinned env that `max_completion_tokens` is emitted on the wire (not `max_tokens`) and `extra_body` is a first-class `ChatOpenAI` field present in both the request payload and `_get_llm_string()`. No inference-profile hash was added.
- **`--reasoning-parser qwen3` only in the repo-maintained compose command**, per the external-endpoint assumption: any other vLLM deployment must pass it itself (README states this requirement); the repo adds no other serving flags.
- **Cache purge (user-approved full purge)**: `rm -rf baselines/cache_vi/pv-b383e117 baselines/cache_vi/pv-8394cd22` and `TRUNCATE full_md5_llm_cache` (27,983 rows → 0). Consequence accepted: v2 seals and raw v2 step artifacts are gone, so `check_run_seal.py` can no longer validate the v2 llama.cpp runs; the `llm-cache-*.sql.gz` exports are kept as frozen backups (their keys are unreachable: model name, temperature, max-completion, and `extra_body` all changed). Eval CSVs and `logs/official/` remain the v2 historical record.
- **Deleted with the era**: `scripts/bootstrap_llama.sh`, `scripts/check_qwen_runtime.py`, `scripts/run_qwen_official.sh`, `config/models.ini`, `config/haproxy.cfg` (and the empty `config/` dir), `scripts/backup_direct_repair.py` (v2 repair machinery whose inputs the purge destroyed — re-introduce if a v3 run ever needs pre-repair backups), and the `haproxy` compose service plus the orphaned running container. `scripts/migrate_sql_generate_cache.py` stays: offline T09 maintenance tooling whose llamacpp ids are historical cache keys, not the inference path.
- **`gen` record schema addition**: step JSON records may now carry `gen` (diagnostics only; `run_check.py` ignores unknown keys). Known behavior: with `seed=42`, stage-validation retries resend identical requests and may reproduce identical invalid outputs (same as the temperature-0 era); they exhaust into the terminal `invalid_*` label as designed.
- **Notebook pins bumped to v3 in this pass** (user choice): title, dataset-manifest assert, and smoke-section pins now say `v3.0.0` / `pv-8394cd22`; the model client is `build_model_vi(MODEL)`. The rest of T02's v3 refresh (e.g. the ad-hoc Colab Drive bridge cells still referencing the `vigsqa-v2-smoke` session) remains T02 scope.

## Validation

- Static (2026-09-04): Ruff clean on all touched Python; `bash -n` + ShellCheck clean on the official inference runner (now `scripts/inference.sh`); `podman compose config -q` OK; `scripts/check_run_logging.sh` passes (tee/pipefail contract unchanged); grep gate — remaining llama.cpp/haproxy mentions are only frozen history (`docs/results.md`, `baselines/REPORT_VN_GEOQA.md`, T02/T07/T09 records, `migrate_sql_generate_cache.py`) plus this record's own description of the removal.
- Offline payload assert (2026-09-04, no server): `build_model_vi(...)._get_request_payload(...)` emits `max_completion_tokens=32768` with **no** `max_tokens`, `temperature=1.0`, `top_p=0.95`, `seed=42`, `presence_penalty=1.5`, and `extra_body={"top_k": 20, "min_p": 0.0, "repetition_penalty": 1.0}` as its own payload key (the openai SDK merges it into the wire JSON at send time); no `tools`, no `chat_template_kwargs`. `pipeline.build_model is build_model_vi` after patching; the profile also appears in `_get_llm_string()`, so it is part of the cache key.
- Preflight behavior (2026-09-04): the curl gate's served-id check (`grep --fixed-strings '"<id>"'` over `/v1/models`) detects a missing id and a present id correctly against a stubbed response; the refused-endpoint curl retry path fails within its `--retry-max-time` (verified with a shrunk budget); `check_served_models.py` was later folded into this curl gate per review — no standalone checker script remains.
- Seal gate: `check_run_seal.py ornith-ai/Ornith-1.5-9B-NVFP4 direct` exits 1 "incomplete" against the purged caches — both per-model pairs correctly become pending for the runner.
- Cache purge (2026-09-04): `full_md5_llm_cache` 27,983 rows → 0; `baselines/cache_vi/` empty; `llm-cache-*.sql.gz` exports untouched.

*(Pending — requires the endpoint up: model ping, the served-id gate against a live server loading a different id, `--mode smoke` direct+text2sql with `gen` metadata (`finish_reason`, `reasoning_tokens`) and CoT-free `content`. Run: `podman compose up --detach vllm`, then `MODELS="AxionML/Qwen3.5-9B-NVFP4" ./scripts/inference.sh --llm-concurrency 4` or the notebook smoke.)*

## Next

User launches the four v3 official runs per model (see `docs/PLAN.md` Active Next Action); T03 then starts from those sealed artifacts. Append the live-endpoint evidence above when the first smoke/official run happens.
