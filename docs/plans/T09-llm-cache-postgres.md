# T09 — LLM Cache (PostgreSQL/LangChain) + Bounded Concurrency

**Status: in_progress (started 2026-08-30). Implementation and validation complete; close after user review.**

## Goal

Replace the file-based LLM request cache (JSON step files) with a PostgreSQL-backed LangChain cache in a dedicated `llm_cache` database, and make client-side LLM calls run under one bounded concurrency limit (`--llm-concurrency`, default 1) — without changing prompts, dataset, model/server semantics, downstream artifacts, or rerunning the official pipeline. The paused W7 run's 1,564 `sql_generate` records are migrated into the new cache so the later official resume keeps that inference progress.

## Cache-key contract (user-approved acceptance rule)

> Same semantic model request, different transport endpoint → reuse cache.
> Different model or generation semantics → separate cache.

Changing model / quantization / generation parameters / prompt → miss. Changing only `base_url` (same model served elsewhere) → hit. API key / transport-only configuration must not affect cache identity.

**Eviction extension (2026-08-31, T07/G6)**: `TransportNormalizedMd5Cache.evict(prompt, llm_string)` deletes the rows for exactly one request key (normalized like lookup/update), so an invalid Text2SQL generation can be removed without touching any other row. Version-pinned internal dependency: it delegates to the locked `SQLAlchemyMd5Cache._delete_previous` (langchain-community 0.4.2; deletes by `prompt_md5` + `llm` + `prompt`) — a locked-version upgrade must re-verify this method and the probes. The runtime retry loop (`pipeline.invoke_validated_or_capture`) evicts before every retry: an invalid completion may never survive as the canonical cache entry, and a retry may never replay a poisoned row. `update` is untouched — valid rows replay byte-identically, and non-validating steps (Direct, upstream) keep exactly the previous write behavior, empty completions included.

**Deserialization allowlist (2026-08-31)**: `lookup` is overridden to deserialize rows with an explicit `allowed_objects="core"` — the allowlist langchain falls back to when none is passed, stated explicitly because `SQLAlchemyMd5Cache.lookup` calls `loads()` with none and langchain then warns on every hit (thousands of lines per official run in `logs/official/*.err`). Same rows, same set of revivable classes; `lookup` now pins `SQLAlchemyMd5Cache._search_rows` alongside `_delete_previous`. Because `loads` is called from project code instead of from `langchain_community.cache`, langchain emits one `LangChainBetaWarning` per process at the first hit — accepted, like the sunset warning on import.

## Decisions

- **51 empty-content records are pruned, not migrated** (user decision): the live `sql_generate.json` held 1,564 records of which 51 had `content: ""` with no `error` key — successful invokes that returned empty completions (0 error records). They would fail the G6 ```` ```sql ````-presence check regardless; they regenerate during the future official resume. G5 precedent applied: targeted prune, never `--clear-cache`. Pristine 1,564-record backup: `logs/official/pre_t09_sql_generate_1564.json` (sha256 `be106a35…`).
- **Postgres LangChain cache is the sole skip layer for LLM steps** (user decision): JSON step files remain write-through artifacts (T07 invariant; G6 asserts read them). Initially gated behind `LLM_CACHE=1`; the 2026-08-30 cleanup pass removed the env gate, so the cache is always on when the pipeline runs (`setup_llm_cache()` from the CLI entrypoint and the notebook's in-process import alike). Corollary: `{id, error}` records stay in JSON as artifacts but no longer suppress retries on resume (LangChain never caches failures).
- **Run seals are experiment completion state, not a cache backend.** PostgreSQL `llm_cache` remains the request-level resume/repair cache and is deliberately excluded from seal validity. Publishing its completed dump on the `v2.0.0` Release remains deferred until the user explicitly confirms Qwen has finished; do not upload or replace that asset beforehand.
- **Normalization layer, not key pinning** (user decision after the base_url finding): native llm_strings embed `openai_api_base`; `TransportNormalizedMd5Cache(SQLAlchemyMd5Cache)` in `baselines_vi.py` strips exactly `openai_api_base` + `openai_api_key` from the payload's `kwargs` before lookup/update. Storage/table/serializer inherited unchanged; parse failure passes the key through unchanged (failure mode = endpoint-coupled keys, i.e. redundant inference — never a false hit). Model name, quantization tag, temperature, max_tokens stay keyed. Defined at module level with top-level imports (an earlier lazy-factory version used `noqa` suppressions — removed per user feedback).
- **Concurrency = explicit parameter threading, flag is required** (user decision, revised three times: first an env-var design, then flag-only with default 1, finally no default at all — `--llm-concurrency` must always be provided and `scripts/run_official.sh` passes `4` to match the server preset): the value flows `main() → run_direct/run_text2sql/run_shuffled → step_* → run_llm_step → invoke_or_capture_many → _llm_pool(max_workers)` like every other CLI setting (`--mode`, `--embeddings`). No mutable module global (AGENTS.md), no env var, no `noqa`. `run_rag` (at the 8-arg lint ceiling) keeps its signature and gets the sequential default. A shared `run_llm_step` driver replaces the three identical LLM loop bodies (`step_execute_sql` untouched — sql_exec keeps JSON-skip). No asyncio/Ray/queues.
- **`restart: always` on both compose services**; one postgres service, two logical databases (`osm_vn`, `llm_cache`); two independent restore workflows.
- `SQLAlchemyMd5Cache` imported from `langchain_community.cache` — `langchain_classic.cache` (1.0.8) is only a deprecation shim. `sqlalchemy` is now a direct dependency (engine construction).
- **Cleanup pass (2026-08-30, user review)**: version tokens removed from tool names and local paths (`run_official_v2.sh` → `run_official.sh`, `run_check_v2.py` → `run_check.py`, `logs/official/`, `cache_vi/pv-*`, `results/`, `data/questions_vi/`); release assets renamed in place on `v2.0.0` (`vn-geoqa.zip`, `osm-vn.sql.gz`) so download URLs carry the version and nothing else does; v1 remnants deleted (`scripts/v1.0.0.sha256`, `docs/qc_spot_check_v1.0.0.tsv`, `data/v1.0.0/`, old `main.ipynb`); bootstrap/restore scripts moved their SQL into `sql/` files or `createdb` (no `--command` SQL-in-shell); `--llm-concurrency` became a required flag with the runner passing 4 (notebook included); validation re-run green after the rewrite.

## Validation (all green, 2026-08-30)

- **Probe (blocker gate, `--probe`, P1–P4, in-memory SQLite, no infra)**: P1 native llm_strings differ across `base_url` (the incompatibility being fixed); P2 normalized keys equal across `base_url` AND `api_key`; P3 cross-endpoint hit with byte-identical content; P4 model-name and temperature changes both miss. Every prune/migrate/validate/concurrency stage re-runs the probe first.
- **Prune**: 1,564 → 1,513; the 51 dropped ids are recorded in the prune output (mostly `knn+name+multi_source*`); backup asserted present first.
- **Migrate**: `full_md5_llm_cache` rows = 1,513, distinct prompts = 1,513; re-run idempotent (still 1,513).
- **Validate (offline replay, `_generate` monkeypatched to raise)**: 1,513/1,513 byte-identical hits at the original `LLAMACPP_URL`; 1,513/1,513 byte-identical hits at a dead `base_url` (`http://127.0.0.1:9`); model-name control misses. Zero model calls by construction — a miss raises loudly instead of silently re-running inference.
- **Concurrency (`--concurrency`)**: N=4 → 64/64 byte-identical hits, observed concurrency exactly 4; N=1 → 64/64 hits, observed exactly 1; 16 concurrent idempotent re-updates left the table at 1,513 rows / 1,513 distinct prompts.
- **Restore round trip**: `export_llm_cache.sh` (271 KB dump + sha256) → `DROP DATABASE` → bootstrap's guard recreates → `restore_llm_cache.sh` → re-validate green (1,513/1,513 byte-identical on both URLs). Restore proven both ways: over an existing DB (replace) and cold (creates the DB itself).
- **Infrastructure**: `podman compose down --volumes` → clean stack; OSM restore green with exact T07-G1 counts (pois 38,223 / regions 8,535 / parks 1,492 / lakes 7,973 / roads 175,318); bootstrap idempotent; `restart: always` on both services confirmed via `podman inspect` + `podman compose config`.
- **Compose startup cleanup**: the local official runner starts the complete compose stack once (Postgres, llama.cpp, and HAProxy) without `--wait`, passes `--wait-only` to the PostgreSQL bootstrap, then waits on HAProxy's `/v1/models` endpoint. HAProxy already depends on a healthy llama.cpp service, so no second llama.cpp poll runs locally; Colab retains its direct llama.cpp bootstrap and health wait.
- **Three-service health contract (2026-08-31)**: Compose now gives HAProxy
  its own `CMD` healthcheck against `/v1/models`, which proves that at least one
  pooled backend can answer; `/health` remains frontend liveness only. HAProxy
  still checks every local/remote pool member at its `/health` endpoint, with
  the SSH remote optional. PostgreSQL uses bounded `pg_isready`, llama.cpp uses
  bounded `curl` against its direct `/health`, and the Colab PostgreSQL path now
  explicitly waits with the same connection parameters after `service start`.
  The official runner retains its bounded `/v1/models` probe because it checks
  the effective, overrideable `LLAMACPP_URL`, not merely one container's state.
- **No-regression**: with the cache not configured (in-process import without `setup_llm_cache()`), `get_llm_cache() is None` → JSON-skip fallback active (asserted).

## Session notes

- **HAProxy runtime validation (2026-08-30)**: the first live probe found the
  container restarting because `config/haproxy.cfg` lacked its final newline;
  HAProxy 3.4 rejected the file as truncated. Adding the newline made the
  image's config check pass. The proxied `/health` then alternated between 200
  and a backend's 503, so HAProxy now owns that path via `monitor-uri`; repeated
  probes test proxy readiness directly while compose owns llama.cpp readiness.
- **Progress accounting fix (2026-08-30)**: the shared LLM driver previously
  advanced tqdm once per concurrency batch while declaring a question-count
  total, so `214/2800` at concurrency 4 represented about 856 completed
  questions. It now updates by the actual batch length, including a short final
  batch; cache behavior and artifacts are unchanged.
- **Runtime cache audit (2026-08-31)**: the live PostgreSQL cache held 8,233
  unique rows, with zero empty contents, HTTP 503 responses, or server-error
  responses. Its sole `finish_reason=length` row contains a complete fenced SQL
  block and remains valid under the frozen stage policy. Transport and terminal
  validation failures remain only in JSON artifacts and therefore retry on
  resume; no PostgreSQL rows were cleared. Separately, the ID-only `sql_exec`
  JSON cache could outlive a changed generation, so T07 now binds those records
  to their exact extracted SQL blocks.
- **Locked-version verification (before any code)**: langchain-core 1.6.1 / langchain-openai 1.6.0 / langchain-community 0.4.2 / sqlalchemy 2.0.52 / psycopg 3.3.4. Verified live: `.invoke()` consults `self.cache` (or the global) before `_generate`; the cache key = (`dumps(messages)` with ids stripped, `model._get_llm_string()`); the llm_string is `json.dumps(lc-constructor serialization, sort_keys=True) + "---" + str(stop)` with the model kwargs NESTED under a `"kwargs"` key — the first `_normalize_llm_string` draft assumed flat kwargs and P2 caught it immediately (probe did its job). `openai_api_key` serializes as a secret *reference* (`{"id": ["OPENAI_API_KEY"], "type": "secret"}`), so the api-key value never reaches the key even before normalization; stripping it keeps the invariant explicit. langchain-community emits a sunset `DeprecationWarning` on import — accepted, it is the locked set.
- **Bugs found by validation**: (1) the flat-kwargs normalizer assumption (above); (2) `restore_llm_cache.sh`'s `psql_admin()` helper dropped its arguments (missing `"$@"`), silently no-op'ing the create-DB guard — caught by observing "Creating" print on an existing DB; fixed and both branches re-proven.
- **Cache-hit warning fix (2026-08-31)**: every `lookup` printed `LangChainPendingDeprecationWarning` because `SQLAlchemyMd5Cache.lookup` calls `loads()` without `allowed_objects`. `TransportNormalizedMd5Cache.lookup` now deserializes with `"core"` — the implicit default, so what a row may revive is unchanged (verified over all 8,164 live rows: each holds exactly a `ChatGeneration` and its `AIMessage`, nothing else). A strict class allowlist (`ChatGeneration`, `AIMessage`) was possible on that evidence but rejected: it would change behavior for any unexpected class instead of only silencing a warning; deserialization quietness is validated against the cache engine. Not re-run: `migrate_sql_generate_cache.py --validate` is stale independent of this change — its `_assert_row_counts` expects one row per `sql_generate.json` record (2,723) while the live table now holds 8,164 rows from the resumed runs.
- **User coding-standards feedback applied**: no `noqa` suppressions (root-cause fixes instead — the lazy-import factory became top-level imports and a module-level class; the mutable `LLM_CONCURRENCY` global and the env-var variant became explicit parameter threading); no inline heredoc/`python -c` scripts for repo work. Full validation chain re-run green after the refactor (validate 1,513/1,513 both URLs; concurrency N=4 observed 4, N=1 observed 1, writes intact; no-regression assert).
- **Driver parity check (offline, stub model, 5 cases)**: fresh sequential run freezes errors; JSON-skip resume makes zero calls and returns identical results; partial resume calls only uncached ids and retries past error records; N=4 through the pool produces byte-identical outcomes; identical replays no longer rewrite the JSON (the `cache.get(id) != record` guard — added after the driver landed, it removes ~1 GB of rewrite I/O on the 1,513-record PG replay while leaving the file's content unchanged).
- The 51 empty ids are NOT silently dropped from history: the prune prints them, and the pristine 1,564-record JSON stays in `logs/official/`.
- An accidental `ruff check baselines/` auto-fixed lint inside `baselines/sql_runtime.ipynb` — reverted, it is upstream-derived and untouched by this task.
- The Drive-side cache folder must follow the local restructure: `cache_vi/ds-v2.0.0/pv-b383e117` → `cache_vi/pv-b383e117` (the notebook symlinks `baselines/cache_vi` to the Drive `cache_vi`).

## Next

Resume T07 in a follow-up session: `scripts/run_official.sh --llm-concurrency 4`. Expected: `sql_generate` replays the 1,513 migrated ids as PG hits with zero model calls, re-invokes the 51 pruned ids plus the remaining 1,287, then the other three baselines continue → G6 per run → notebook Run All per T07.
