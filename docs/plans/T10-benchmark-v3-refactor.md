# T10 — v3.0.0 Benchmark Refactor

**Status:** `done` (activated 2026-09-03, closed 2026-09-03)

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

### 2026-09-03 — G1′: snapshot + DB rebuild + audits

- `vietnam-260901.osm.pbf` downloaded and Geofabrik-md5-verified (`c03f4b2db0fce6b85af7071ce6bfc13b`, 327,637,117 B, sha256 `edf2d41d93b25474acc14a34f6c313940ecfea5671835299ddd793c60d08a3e8`); `.osm_vn_source` repointed; old 260825 pbf kept on disk.
- Rebuild via `DB_RESTORE=0 bootstrap_postgres.sh --wait-only` (import path, not the v2 dump). Marker: `vietnam-260901.osm.pbf` + Lua style sha `5360305f…`; `pois` view = 24 columns with all 8 `addr_*` and no `capacity`.
- Five-table gate: pois 38,207 / regions 8,567 / parks 1,493 / lakes 7,987 / roads 175,883 (v2: 38,223 / 8,535 / 1,492 / 7,973 / 175,318 — snapshot drift only, no v2 count treated as expectation).
- Representative spatial ops: `SUM(ST_Area(parks))` ≈ 2.434e10 m², `MAX(ST_Length(roads))` = 75,961 m, KNN `<->` ordering works.
- **Address coverage audit** (all-POI per-component, non-null): total 38,207; housenumber 10,229 / **street 13,857** / place 72 / suburb 7 / district 4,803 / city 4,795 / province 4,489 / postcode 1,470.
  - Criterion candidates: street-only 13,857; **street-or-place + ≥1 broader locator 5,321**; housenumber+street+broad 4,020; city-only 4,795.
  - **Decision: criterion = `(addr_street OR addr_place) AND (addr_city OR addr_district OR addr_suburb OR addr_province)`** — 5,321 POIs (13.9%), the least restrictive criterion that stays unambiguously geocodable (street-only without any broader locator is ambiguous nationwide; Vietnamese centrally governed cities repeat city=province so the broad locator set is an OR).
  - Per-subcategory address-bearing pools: all 26 subcategories non-empty — restaurant 1,375, cafe 1,048, convenience 646, hotel 541, bank 288, supermarket 243 … university 11, gallery 9, sports_centre 9, stadium 4, swimming_pool 2. KNN questions are valid nationwide; small-radius range questions for thin categories rely on the existing redraw loop.
  - Geography: Hà Nội 1,464 / Bắc Ninh 643 / HCMC ~552 (three OSM spellings) / Cần Thơ 126 / Đà Nẵng 113 / Đà Lạt 71 / Hội An 67+41 / Nha Trang 50 / Huế 40 — North/Central/South spread. Native component spellings are frozen verbatim (no synthesis/normalization of OSM values).
  - All 8 address columns stay exposed in view+prompt+`ADDR_COLUMNS` (suburb=7 rows is harmless; one consistent set beats special-casing).
  - Loc mechanism confirmed: prompt-visible predicate + address-bearing anchors (drawn `TABLESAMPLE SYSTEM(10)`); smoke acceptance validates.
- **T7/T8 overlap audit**: live `information_schema` check — attribute registry (established, built, architect, founder, director, opened, capacity, designed) ∩ pois columns = **0**. `wikidata`/`wikipedia` (53 POIs) are anchor identifiers, not answer facts; they stay. Verifier guard `pois_view_columns()` (parses `refresh_views.sql`, fail-closed) holds permanently.

## Validation

### 2026-09-03 — G2′ smoke + G3′ full generation

- G2′ smoke (`--count 5`, all 28 TIDs): 140/140 verifier pass; loc acceptance 3–15 it/s (no exhaustion). Address-bearing anchors (`TABLESAMPLE SYSTEM(10)`) work without special-casing.
- G3′ full run (`--seed 42 --count 100 --output data/v3-stage/questions_vi`): **2,800/2,800 verifier pass**; 28 files × exactly 100; answer-type distribution identical to v2 (name 1200, **loc 800**, angle 200, count 200, distance 200, area 100, length 100); `wikipedia_cache_vi.json` unchanged (sha256 `09b74191…`).
- Loc gold quality: knn types exactly 1 address-bearing answer; range types keep full distance-ordered sets (median 2–6, max 542); zero empty addresses; 65–89% of knn gold carries housenumbers. Canonical addresses read naturally (e.g. "5B Nguyễn Thiện Thuật, Phường Hoàn Kiếm, Hà Nội, Thành phố Hà Nội", "23 Đường Vạn Phúc, Hà Đông, Hà Nội"); mixed orthography in components ("Bắc Ninh" vs "Bac Ninh") is native OSM data frozen verbatim.
- Human QC TSV: `docs/qc_spot_check_v3.0.0.tsv` (5 per TID, seed 42) → user review.
- **Byte-identical regeneration: second seed-42 run (`data/v3-stage/regen2`) `diff -r` clean across all 28 files (2,800 questions).**

### 2026-09-03 — G4′ + prompt freeze

- User approved the QC gate after the spot-check TSV was made answer-type-aware (v2 column always showed `poi_name`, hiding loc addresses, T7 facts and numeric gold; same seeded 140-row sample regenerated).
- **Prompt freeze `pv-8394cd22`** (aggregate sha256 `8394cd22f8e227778968be0169351e7b7d42fca238fced28693c55649da4091f`, supersedes `pv-b383e117`). Per-file sha256: `direct_answer_vi` `8a1fc088…2a98a`, `direct_json_parse_vi` = `text2sql_json_parse_vi` `7de156f0…874b2`, `text2sql_generate_vi` `8962be4a…df6cd`, `text2sql_answer_vi` `811d781c…d3873`.
- Semantic changes only (G4′-approved, no accuracy tuning): Text2SQL schema exposes the 8 `addr_*` columns and drops `capacity`; Location pattern selects address columns and states the address-bearing candidate predicate verbatim (replacing the `ST_X/ST_Y` lon/lat idiom); Direct/Text2SQL answer rule 5 asks for the full address instead of coordinate decimals; both JSON parse prompts restore upstream's "The location must be provided as a complete address" while keeping `lon`/`lat` as optional keys.
- Upstream parity audit (paper §5 + `references/main.tex`, upstream prompts): upstream's `direct_json_parse.txt` is address-primary — restored verbatim. Upstream's "numbers as words rounded to nearest ten" quirk stays replaced by exact digits (T02 decision: the benchmark scores exact digits); upstream exposes `capacity` as both column and multi-source attribute — v3 deliberately does not.
- Interim evaluation degradation (documented, not fixed — T03 owns the evaluator): after the prompt change, predictions for the 800 loc questions are address text, which `_vn_evaluate_answers`' lon/lat fallbacks do not consume; interim eval CSVs must not be quoted as v3 Location evidence. T03 requirements recorded in PLAN.

## Open questions / next

- Interim loc evaluation (`_vn_evaluate_answers` lon/lat fallbacks) will not match address-text predictions after the prompt change — documented degradation; T03 owns the evaluator (requirements recorded in PLAN/T03 row).
- Untracked `main.ipynb` still pins `pv-b383e117` — follow-up for T03/T05 when the notebook is next executed.
- Next: G2′ smoke (5 × 28) watching loc acceptance; then full seed-42 regen into staging.

### 2026-09-03 — G5′ runner prep + G6′ freeze/publish (task closed)

- Tee live logging landed in both runners (`python -u … 2> >(tee .err >&2) | tee .out`); `scripts/check_run_logging.sh` verifies exit propagation + both files non-empty (failing python → non-zero script exit; succeeding → `.out`/`.err` both populated).
- **Seal negative test passed**: all four `check_run_seal.py` pairs report `incomplete` (exit 1) under `pv-8394cd22` — v2 seals live under `pv-b383e117` and can never satisfy v3 identity.
- Freeze swap executed: v2 dataset archived at `data/questions_vi_v2_archive` (release `data-v2.0.0` also restorable), staged v3 moved to `data/questions_vi`; `dataset_sha256 = d7a0c45c…17ff1`; `scripts/v3.0.0.sha256` (28 files); MANIFEST v3.0.0 written.
- Release **`data-v3.0.0` published**: `vn-geoqa.zip` (2,388,528 B) + `osm-vn.sql.gz` (122,288,436 B, sha `ae06f7c2…ef53e6`); export/upload pin ordering enforced by the existing guard; pins committed as one commit (`90ca689d`) with `restore_dataset.sh` default → v3.0.0.
- **Restore verification from the published release**: `restore_dataset.sh` into a moved-aside `data/questions_vi` → "28 files, 2800 questions verified", `diff -r` byte-identical to the frozen copy. DB: tables dropped via `prepare_import.sql`, `bootstrap_postgres.sh` (dump path) → five-table counts match G1′ exactly (38,207 / 8,567 / 1,493 / 7,987 / 175,883); restored `pois` view = 24 columns (8 `addr_*`, no `capacity`), address-bearing pool = 5,321.
- Docs refreshed: README.md / README_VI.md (v3.0.0, `vietnam-260901`, release tag, full-mode = 2,800), `docs/data_generation.md` (v3 view columns, address semantics, staging-dir flow, answer-key table re-verified against the frozen jsonl).
- **T10 closed**: no official inference launched (no new `logs/official/` artifacts), no T03/evaluator code touched. Next action: user review → user manually launches the four v3 official baseline runs.
