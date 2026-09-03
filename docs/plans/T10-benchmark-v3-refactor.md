# T10 — v3.0.0 Benchmark Refactor

**Status:** `in_progress` (activated 2026-09-03)

## Goal

Freeze a corrected v3.0.0 benchmark contract and prepare the runtime so the four official baseline runs (Ornith/Qwen × Direct/Text2SQL) can be launched manually by the user. Fix Location at the source (native OSM addresses), restore T7/T8 out-of-schema semantics, move to the `vietnam-260901.osm.pbf` snapshot, and isolate v3 from v1/v2 artifacts. **No official inference and no T03 evaluation work inside this task.**

## Contract

- Version `v3.0.0`, seed 42, 28 canonical TIDs × 100 = 2,800, snapshot `vietnam-260901.osm.pbf` (Geofabrik md5 sidecar; never `vietnam-latest`).
- Location gold (T13–T20): `geo_wkt` + native address components + one deterministic canonical address string (derived only from frozen components); address-bearing candidate predicate; question surfaces request location/address, never coordinates alone; geometry remains the authoritative spatial reference.
- T7/T8 external attributes verifiably absent from the reference schema.
- Preservation: v1/v2 releases, raw JSONs, logs, seals, QC records stay on disk as historical evidence; old seals can never satisfy v3; PG `llm_cache` never cleared.
- Unchanged: parser-model policy, 3-attempt structural retry + cache-eviction policy, `--llm-concurrency`, PostgreSQL semantic cache, compose/bootstrap architecture, models.

## Decisions

- **Loc mechanism: prompt-visible address-bearing predicate** (chosen at planning; confirmed/adjusted at the G1′ coverage audit). All T13–T20 gold SQL filters candidates to address-bearing POIs, and the Text2SQL prompt states the predicate precisely — same pattern as prompt-visible anchor exclusion and the wrap-safe towards formula. Fallback if the audit shows pool collapse: rejection sampling on the draw. knn+loc gold = nearest address-bearing candidate; range+loc gold = full distance-ordered address-bearing set.
- **`capacity` removed from the reference schema** (Lua `poi_extra_tags`, `pois` view, Text2SQL prompt) and kept as a T7/T8 external attribute. Evidence: no filter label uses it (`generator/filter_labels_vi.json` covers cuisine/museum/takeaway/outdoor_seating/delivery/emergency), so removal breaks no template while making every T7/T8 attribute genuinely out-of-schema. Upstream GS-QA shares this quirk (`poi_schema.json` exposes `capacity` while `generator.py` uses "Capacity" as a multi-source attribute); v3 does not copy it.
- **Prompts are edited only after user QC approval**, immediately before freeze: a repo with v3 prompts + v2 dataset is self-consistent to the seal machinery, and an accidental official run in that window would seal a hybrid. No official-runner invocations between prompt edit and dataset freeze.
- **Generation goes to a staging directory, swapped at freeze** (documented flow in `docs/data_generation.md`): in-place regeneration would leave the v2 `MANIFEST.json` describing v3 files.
- **v2 dump pins and export version bump land in one commit** (`restore_database.sh` + `export_database.sh` are two halves of the `data-v3.0.0` release tag).

## Evidence log

### 2026-09-03 — P0 baseline state

- All four v2 seals validate (`scripts/check_run_seal.py`, 2026-09-03): Ornith text2sql/direct, Qwen text2sql/direct under `pv-b383e117` — T07's exit condition was already met; PLAN now records T07 `done` (superseded as v3 evidence).
- Pending v2 tooling committed (`daa93ed1`): T09 record note (seals exclude the PG cache), `check_qwen_runtime.py` 28-TID uncached non-thinking preflight, `run_qwen_official.sh` local-route Qwen runner, deletion of `docs/context/00b_missing.md`.

## Validation

(to be filled by phase: G1′ DB rebuild + audits, G2′ smoke, G3′ full regen + byte-identical, G4′ human QC, prompt freeze, G5′ runner checks + seal negative test, G6′ publish + restore verification)

## Open questions / next

- G1′ address coverage audit decides: exact address-bearing criterion, exposed address column set, loc anchor strategy, canonical address composition details.
- Interim loc evaluation (`_vn_evaluate_answers` lon/lat fallbacks) will not match address-text predictions after the prompt change — documented degradation; T03 owns the evaluator (requirements recorded in PLAN/T03 row).
- Untracked `main.ipynb` still pins `pv-b383e117` — follow-up for T03/T05 when the notebook is next executed.
