# T05 — Vietnamese Error Analysis and Demo

**Status: done (2026-09-05).** Error analysis ran on the **dev split first** (`docs/dev_test_split_v3.0.0.json`); the full-benchmark taxonomy below was computed only after the T04 intervention was frozen (commit `5259b7e6`).

## Taxonomy definition (`scripts/error_taxonomy.py`)

Every question of a sealed run is classified by failure stage, then flagged for measurable Vietnamese phenomena. Stages, in decision order:

- `parse-failure` — the run's answer record contains no fenced JSON block.
- `correct` — family-primary metric passes the paper's analysis thresholds (text F1 ≥ 0.5; error ≤ 0.1; `references/main.tex` ~L1819). Analysis-only: sealed scores are untouched.
- `wrong-attempted` — the model produced candidates but missed.
- `refused` (Direct only) — no candidates and no SQL stage exists; probes (T04 pre-registration) showed these are genuine model refusals with correctly-keyed null JSON, not extraction loss.
- Text2SQL empty-candidate questions split by `sql_exec` evidence: `sql-error` (any statement errored), `no-rows` (SQL ran, returned nothing), `rescuable` (typed rows exist and `rescue_block` could emit an answer — the class T04 recovers), `rows-unusable` (rows exist but carry no typed value for the family, e.g. area/length totals computed out-of-database).

Phenomena flags: `diacritic_loss` (prediction matches a gold once diacritics are stripped from both — a Vietnamese-specific miss the scorer legitimately counts wrong), `geocode_miss` (a predicted address Nominatim cannot resolve — component order and postcode formats differ from OSM conventions), `sector_right_angle_wrong` (correct 8-sector compass name but wrong precise azimuth).

CSVs per model/baseline/split land in `results/analysis/taxonomy_*.csv` (regenerable, gitignored); the tables below are the committed record.

## Full-benchmark stage × family (2,800 questions, post-freeze)

Ornith/Text2SQL (the T04 arm):

| family | correct | wrong-attempted | rescuable | no-rows | sql-error | rows-unusable | parse-failure |
|---|---|---|---|---|---|---|---|
| entity | 313 | 198 | 208 | 280 | 100 | 1 | 0 |
| textual_fact | 1 | 35 | 0 | 7 | 28 | 29 | 0 |
| location | 275 | 196 | 48 | 168 | 46 | 65 | 2 |
| direction | 108 | 22 | 4 | 44 | 18 | 4 | 0 |
| count | 85 | 92 | 1 | 0 | 22 | 0 | 0 |
| distance | 66 | 52 | 24 | 44 | 12 | 2 | 0 |
| area | 29 | 11 | 0 | 0 | 26 | 34 | 0 |
| length | 30 | 5 | 0 | 0 | 22 | 43 | 0 |

Qwen/Text2SQL: entity 310 correct / 136 rescuable / 209 sql-error / 215 no-rows; location 255/38/152/140; much higher sql-error across families (39 area, 62 direction vs Ornith's 26/18). Ornith/Direct: refusal dominates — 904/1,100 entity, 572/800 location, 156/200 count refused; only 77/2,800 correct overall.

## Vietnamese-phenomena flags (full set)

| flag | Ornith/T2S | Qwen/T2S | Ornith/Direct |
|---|---|---|---|
| geocode_miss | 219 | 139 | 175 |
| sector_right_angle_wrong | 14 | 12 | 10 |
| diacritic_loss | 9 | 6 | 1 |

Reading: geocoding, not language, is the recurring Vietnamese-side friction — 46% of Ornith/Text2SQL location questions with candidates contain at least one predicted address Nominatim cannot resolve (219/471; Vietnamese address component order `số, ngõ, phố, phường/xã, quận/huyện, tỉnh` and 6-digit postcodes diverge from OSM's expectations). Those questions still score through address-text F1, but their spatial distance error is dominated by whatever Nominatim returns instead. True diacritic-loss misses are rare (≤9 per run) because NFKC normalization already equates composed/decomposed forms; the remaining 9 are genuinely different spellings. Sector-naming is nearly always consistent with the stated azimuth (14 cases of mismatch) — the direction metric's weakness is the azimuth itself, not the compass vocabulary.

## Representative cases

- **sql-error** `intersects+count-003`: "Số lượng tiệm bánh tại Phường Nha Trang là bao nhiêu?" — the dominant sql-error class is subqueries used as expressions returning multiple rows (107 of Ornith's ~250 execution errors benchmark-wide).
- **no-rows** `intersects:area_max+name-001`: "Đâu là công viên có diện tích lớn nhất của Tỉnh Lâm Đồng?" — generated SQL filters away every candidate, then the model correctly reports nothing.
- **wrong-attempted** `intersects+count-001`: "Đếm số cửa hàng điện tử nằm trong Thành phố Hồ Chí Minh." → 0 (gold 51) — the model names the right category but the spatial predicate selects nothing; Qwen answers the identical question correctly, so this is model capability, not dataset ambiguity.
- **rescuable** `intersects+count-025`: "Trong Thành phố Hồ Chí Minh có bao nhiêu chợ?" → ∅ with `count=103` sitting in the executed rows — exactly the class the T04 rescue recovers.

## Fresh Vietnamese demo (`scripts/t05_demo.py`)

Five questions that appear nowhere in the benchmark (anchor names asserted absent from all 5,600 question surfaces), built in the generator's template dialect with gold grounded by executing gold SQL read-only. Both baselines ran live through Ornith (`ornith-ai/Ornith-1.5-9B-NVFP4`) at the documented OpenAI-compatible endpoint, with the step cache redirected to `baselines/cache_vi/t05-demo/` — the sealed `pv-26b1ac0d` namespace was never touched. This was the only new LLM inference in T04/T05.

| demo | family | gold | Text2SQL outcome |
|---|---|---|---|
| demo-001 | entity | Pharmacity | answered "Pharmacity" — exact match |
| demo-002 | location | 7 Phố Đào Duy Anh, Đống Đa, Hà Nội, 10000 | answered a different hotel's address — honest miss |
| demo-003 | count | 0 | answered 0 — exact match |
| demo-004 | distance | 429.29 m | answered 429 (rows carried 429.29 m; rescue echoes it) — correct |
| demo-005 | direction | 3 cafés with azimuths 353.8°/156.6°/149.3° | generated SQL returned 100 rows (missing the ≤3 km filter); the model narrated angles instead of listing them |

Cards with full gold SQL, generated SQL, and answers: `results/demo/demo.md` + `demo_results.json` (gitignored, regenerable via `env OPENAI_BASE_URL=… pixi run python scripts/run_demo.py`). The demo's two misses reproduce the taxonomy's two largest non-rescuable classes on genuinely novel anchors (wrong-but-attempted selection; unfiltered generated SQL), which is the intended qualitative evidence.

**Rename + cached replay (2026-09-05):** for the course-facing surface the demo script was renamed `scripts/t05_demo.py` → `scripts/run_demo.py`, outputs moved `results/t05/demo/` → `results/demo/`, and the isolated cache dir `baselines/cache_vi/t05-demo/` → `baselines/cache_vi/demo/`. On Colab the notebook replays the demo from the **published step records** (`demo-inputs.tar.gz` on the `v3.0.0` release: `direct_answer`/`sql_generate`/`sql_answer`, sha256 `c538c93…c5228b`): `run_demo.py` configures no global LangChain cache, so the step records are the pipeline's own resume layer — a question without a record attempts the (dead) endpoint and fails loudly, and the notebook asserts the three step files carry five non-empty, error-free records each.

This replaced an initial LangChain-cache replay design after a controlled probe proved byte-identical cache hits impossible on Colab: demo-005's answer-stage prompt embeds 100 executed azimuth floats, and PostGIS renders their last digits differently across distro numeric stacks — the divergence persists even with PostgreSQL 18 + PostGIS 3.6.4 from PGDG on Colab (`358.1027283549995` vs `358.1027283550077` on the original Debian-based environment). 14 of the 15 generations do replay as exact cache hits; the 15th changes the prompt bytes and therefore the md5 cache key. Rule recorded (user-set): **step records are the cross-platform replay contract; the LangChain cache stays the original inference evidence; numeric validation is semantic (tolerance), never byte identity; no new lineage/cache machinery.** `sql_exec` is deliberately not shipped, so the model-generated SQL executes live on the replay host and the rescue is recomputed from those live rows. Local validation: `run_demo.py` against a deliberately dead endpoint reproduced all five demos with identical answers and live rescue.

**Cache-asset refresh (2026-09-05):** after all T04/T05 work the LLM-cache dump was re-exported and published as `llm-cache-20260905.sql.gz` on the `v3.0.0` release (8,085,830 bytes, SHA-256 `60d9e0f2…`, 27,674 rows = 16,800 official generations + 10,859 Ornith evaluation parse-step generations + 15 demo generations; restore-verified into a scratch DB at 27,674 rows, download re-hashed byte-identical). It replaces `llm-cache-20260904.sql.gz` (16,800 rows, official generations only).

## Findings recorded for the report

1. Text2SQL's largest addressable failure class was the refusal floor — recovered deterministically by T04 (test: entity +0.162 F1).
2. After the rescue, the dominant remaining failures are sql-error and no-rows — both require better SQL generation, not better answer formatting.
3. Direct prompting refuses on ~82% of Vietnamese geospatial questions; Text2SQL is strictly the right architecture here.
4. Vietnamese-specific text handling (diacritics) is essentially a solved problem under NFKC scoring; geocoding coverage of Vietnamese address formats is not.
