# T07 — 28-Template Benchmark v2.0.0 + Raw Baseline Runs

**Status: in_progress (started 2026-08-29).**

## Goal

Extend the Vietnamese benchmark from 8 to all 28 canonical GS-QA template types (2,800 questions), freeze it as `v2.0.0`, and obtain reliable, resumable raw Direct + Text2SQL inference artifacts for the two 9B GGUF models. Raw artifacts only — no prompt tuning, no method work, no RAG/fine-tuning/extra models/UI in this task.

## Critical Path

**Reference DB → T7/T8 compatibility probe → 5×28 generator smoke → generate 2,800 → automated QC (2,800/2,800) → human QC (template review + 5 instantiated/TID) → freeze/publish v2.0.0 → prompt freeze → 28-question CLI smoke (Direct+Text2SQL) → overnight raw inference.**

## Invariants

| Aspect | Contract |
| --- | --- |
| Scope | All 28 GS-QA TIDs × 100 questions = 2,800; upstream spatial semantics preserved (range `ST_DWithin`, KNN `<->`, 8-sector azimuth direction, towards ±22.5°, intersects, count/distance/angle/area/length, T7/T8 multi-source) |
| v1.0.0 | Never modified; `v2.0.0` is a new freeze with its own MANIFEST/checksums/release asset |
| Snapshot | Pinned `vietnam-260825.osm.pbf`; no OSMX; osm2pgsql flex pipeline only |
| Reference DB | Five views: enriched `pois`, `regions`, `parks`, `lakes`, `roads`; one GiST geometry index each; bootstrap fails if any table is absent/empty (pre-inference gate) |
| Regions | Named `boundary=administrative` relations only (deliberate VN adaptation: postal-code boundaries absent in VN OSM; admin_level 4/6/8); display names from `region_name`, no Wikipedia requirement for regions/parks/lakes/roads (VN coverage too thin; native name columns used instead) |
| Direction | Upstream azimuth-sector semantics (`degrees(ST_Azimuth)`, 45° sectors), replacing v1's lat/lon quadrant tests |
| IDs | `{type}-NNN` per file (28 files, upstream type strings incl. `knn+name+multi_source1/2` for T7/T8) + `tid` field `T01`–`T28`; `tid_to_type` in MANIFEST |
| Caches | Namespaced `cache_vi/ds-{dataset_version}/pv-{prompt_version}/{model}/{step}.json` — v1 results can never be reused for v2; write-through after every question; terminal failures cached as explicit `{id, error}` records; never `--clear-cache` |
| Prompts | One pre-run schema/answer-type compatibility rewrite, frozen before the smoke gate; never changed based on smoke accuracy or full-run results (that is tuning) |
| Authoritative artifacts | Before T03's evaluator cleanup: question IDs, raw model answers, generated SQL, raw SQL execution output/errors, parser output, explicit inference errors, run manifest/counts. W5/W7 eval CSVs are provisional (non-crashing, structurally complete) and are not official scores |
| Notebook | `main.ipynb` gitignored (authoritative copy in Drive/Colab); off the critical path — fixed/cleaned during inference; final executed copy in the submission ZIP |
| Runs | Sequential: Ornith Text2SQL → Ornith Direct → Qwen Text2SQL → Qwen Direct; temperature 0; resumable; no `parallel > 1` optimization |

## Gates

- **G1** — five reference tables non-empty after bootstrap; representative spatial queries succeed (planner choice is not a correctness gate).
- **T7/T8 probe** — one example of each end-to-end before bulk generation: wikidata POI → viwiki (enwiki fallback) → infobox attribute/descriptor frozen into the question record → downstream loader/parser consumes the records.
- **G2** — `--count 5` for all 28 types passes `verify_vi.py` (count warn expected).
- **G3 (mandatory)** — 2,800/2,800 automated verification; 100/type; all answer types present (`name, loc, count, distance, angle, area, length` + multi_source). Byte-identical regeneration attempted once, desirable, not a gate.
- **G4** — human QC in two parts: (1) all Vietnamese phrase-template files reviewed for naturalness/semantic fidelity; (2) ~5 instantiated question+SQL+gold per TID (140 total) checking that substitutions and SQL results actually answer the question. Not a replication of GS-QA's manual-QC protocol.
- **G5** — 28-question CLI smoke (one per TID) for Text2SQL then Direct; both CSVs cover 28 ids; on pass, launch overnight inference immediately.
- **G6** — all four runs assert-green (2,800 unique ids, 100/tid, cache ids == question ids, explicit failures, SQL+exec preserved) with minimal run manifests.

## Scope Freeze

Once G2 passes, no new OSM fields, template families, model backends, evaluation features, or infrastructure unless required to fix a demonstrated correctness/execution blocker for T1–T28.

## Blocking vs Deferred

- **Blocks inference**: reference DB, generator + probe + smoke, 2,800 generation + automated QC, human QC, freeze/publish, prompt rewrite + freeze, 28-question CLI smoke.
- **During inference (non-blocking)**: notebook v2 cleanup, final evaluator semantics, results aggregation, error-analysis tooling.
- **After (owned by T03/T04/T05)**: rigorous evaluator semantics, official baseline aggregation/comparison, error analysis, evidence-driven method selection, Vietnamese-specific robustness analysis, final demo on new Vietnamese questions with the frozen final method.

## Decisions

- Regions = admin-boundary relations; parks/lakes/roads names from native name columns (documented VN adaptations of upstream's postal-code/wikipedia sourcing).
- Non-spatial filter family = T2/T6/T14/T18 via `generator/filter_labels_vi.json` derived from measured VN tag values; no row-count floor — only enough valid, diverse candidates without one predicate dominating.
- T7/T8 external values live inside the frozen question records; a plain QID-keyed fetch cache may exist for generation efficiency only.
- Distance answers in metres under a `distance` key (upstream convention; `_vn_get_osm_value` prefers it).
- Cache namespacing implemented by rebinding in `baselines_vi.py` where possible; the single shared `pipeline.py` edit is terminal-failure caching (clearly safer there).
- Region/park/lake/road anchors referenced by id (`(SELECT geometry FROM <table> WHERE id = N)`), never inlined multipolygon WKT.
- Templates target 5–8 natural Vietnamese phrasings per type.
- `--flat-nodes` only if the first import actually requires it.

## Validation

- **G1 (done, 2026-08-29)**: bootstrap green. Row counts — pois 38,223; regions 8,535 (admin_level 4: 35, 6: 3,327, 8: 30, 9: 5,139); parks 1,492; lakes 7,973 (waterway river 2,872 / stream 1,679 / canal 991; water reservoir 496 / lake 398 / river 386 / pond 231); roads 175,318. Representative queries pass: pois×regions `ST_Intersects` 38,131 rows, `SUM(ST_Area(parks))` ≈ 2.4e10 m², `MAX(ST_Length(roads))` = 75,960 m; `addr_city` present on 4,788 POIs.
- **T7/T8 compatibility probe (done, 2026-08-29)**: both types generate end-to-end. T7 example: "trường đại học gần TPBank nhất được thành lập vào năm nào?" → plain-KNN gold returns the wikidata target (Trường Đại học Mở TP.HCM) with frozen `multi_source_attribute: established`, `multi_source_answer: "1990"`; `pipeline.load_questions` + the `%OTHER_ATT%` parser hook consume it (`'"established": string'`). T8 descriptors render clean Vietnamese ("bảo tàng được thành lập vào 1 tháng 1 năm 2017", "sân vận động có sức chứa 15.000"). Bugs fixed during the probe: (1) `wikidata_sitelink` HTTP errors crashed the run instead of counting as failed draws — now transient misses stay uncached; (2) Wikimedia 429 bursts — 429s back off (5/10/15 s) and inter-request sleep raised to 2 s (pool is ~50 QIDs, so the whole external phase is ≈100 requests); (3) `clean_value` leaked raw wikitext such as `{{Start date and age|1988|09|13|df=yes}}` — date templates now reduce to their year, other templates strip.
- **G2 (done, 2026-08-29)**: `--count 5` × 28 types → 140/140 pass `verify_vi.py` (exit 0; only expected 5≠100 count warnings). Three generator bugs found and fixed by the smoke: (1) origin-CTE column named `geometry` made every unqualified reference ambiguous — all 8 direction/towards types returned 0 questions with the error invisible behind silent `except psycopg.Error`; the CTE now aliases to `geom` and the two handlers print the error; (2) `intersects+count` parsed its kind as `""` (`removeprefix` + `lstrip(":")` left the `+`), so every attempt fell into the total-measure branch with an empty alias → SQL error → 0 questions; separator strip is now `lstrip(":+")`; (3) the towards reference POI was not excluded from its own answers ("…nằm về hướng AMA" could return AMA itself) — `id <> towards_id` is now emitted and the verifier's anchor checks cover it. Also fixed a verifier bug (uppercased haystack vs mixed-case needle for `ST_Intersects`).
- **G3 (done, 2026-08-29)**: 2,800 generated with `--seed 42 --count 100`; `verify_vi.py --all` → **2,800/2,800** (exit 0, zero warnings). All 7 answer types present (name 1200, loc 800, angle 200, count 200, distance 200, area 100, length 100); 28 tids × exactly 100. First run had one `angle: 360.0` (359.96 rounded up) — root-fixed with `% 360` normalization. The regen check then caught a SECOND bug: the E501 line rewrap had dropped two parens from the towards angle-CTE f-string, killing all four towards types in regeneration (2,400/2,800) while the original in-memory run was unaffected. After the fix, a fresh pinned-seed run is byte-identical to the first except the one normalized angle record; the regen bytes (containing the fix) are the frozen dataset.
- **W4 freeze prep (done, 2026-08-29)**: `docs/qc_spot_check_v2.0.0.tsv` (5/tid × 28 = 140 rows: question, SQL, gold, annotation column); `MANIFEST.json` (correct command string, per-file counts, `dataset_sha256`, `tid_to_type`, semantics + adaptations blocks, validation with human QC pending); `scripts/v2.0.0.sha256` (28 files, `sha256sum --check` green); `generator/questions_vi` symlink switched to `../data/v2.0.0/questions_vi` — `baselines_vi` namespace now resolves to `cache_vi/ds-v2.0.0/pv-085560f5`, so v1 caches are unreachable.

## Session notes

- `mbr_limited` sampler from upstream is deliberately omitted: VI picks [1] categories directly (with retries) instead of drawing an MBR-bounded candidate set first. Semantics of the emitted SQL are unchanged.
- Wikidata pool inside the POI node allowlist measured at 51 POIs (12 place_of_worship, 12 attraction, 7 university, 5 hotel, …). T7 draws anchors near a wikidata target so the plain-KNN gold returns it; T8 uses the pool as anchors. The lua allowlist was NOT widened (upstream selector semantics); probe + G2 validate this empirically — widen only on a demonstrated blocker.
- T7 [1]-category distribution is skewed toward universities (the infobox-bearing wikidata targets are university-dominated: 97/100 `established` on universities/colleges, 3 `capacity`). A distribution property of the snapshot, not a correctness issue; anchors remain diverse (97 distinct).
- W5 code landed during W3 generation: cache/eval namespacing in `baselines_vi.py` (`ds-{MANIFEST version}/pv-{sha256-8 of the five vi prompts}`, results to `results/ds-{version}/`), terminal-failure caching with a 10-failure systemic abort in `pipeline.py` (`invoke_or_capture`), prompt rewrite for the five-table schema (azimuth sectors, towards corridor, region subqueries, area/length patterns), VN sector patch for angle evaluation, and area/length digit matching in the text eval. Prompts freeze at G5.

## Next

W3 in progress: full `--count 100` generation into `data/v2.0.0/questions_vi`, then G3 (`verify_vi.py --all`, 2,800/2,800 mandatory). **Scope freeze is now in effect** (G2 passed).
