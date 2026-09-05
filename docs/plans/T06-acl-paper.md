# T06 — ACL Paper

**Status: done.**

## Dependencies

T03 official baselines, T04 intervention conclusions, and T05 analysis/demo evidence.

## Scope

Write the course report with ACL style, documenting the benchmark, methods, evaluation, results, errors, limitations, and reproducibility. Ported to Typst using `@preview/tracl:0.8.1`.

## Progress & Migration to Typst

- **Source Document**: Ported from `references/vigsqa/main.tex` and `references/vigsqa/custom.bib` ("VN-GeoQA: A Reproducible Vietnamese Geospatial Question Answering Benchmark" by Anh Pham-Ky & Tien Dang-Anh, HCMUS), corresponding to the LaTeX PDF `/mnt/c/Users/itsky/Downloads/_HCMUS__NLP_CK_latex.pdf`.
- **Target Files**:
  - `docs/report/main.typ`: Full paper in Typst with ACL template (`@preview/tracl:0.8.1`).
  - `docs/report/references.bib`: 19 fully audited BibTeX entries (replaced the provisional Hayagriva `references.yaml`, which pergamon cannot parse; see the 2026-09-06 rewrite entry).
  - `docs/report/figures/`: SVG diagrams for Figure 1 (`fig1_baselines.svg`) and Figure 3 (`fig3_pipeline.svg`). The notebook §2.4 spatial-reasoning map (`artifacts/figures/spatial_reasoning_example.{svg,webp}`, mixed raster/vector SVG over OSM Mapnik tiles) is available for reuse via `scripts/restore_figures.sh`.
- **Semantic Formatting Invariant**: All ad-hoc LaTeX spacing (`\vspace`, `\resizebox`, `\tabcolsep`, etc.) removed; layout relies on semantic Typst primitives (`table`, `figure`). Wide tables (Table 1 and Table 4) span across both columns via `scope: "parent"`.
- **Visual Comparative Analysis**: Page screenshots captured at 144 PPI for both LaTeX (9 pages) and Typst (10 pages) and analyzed with multimodal vision.

## Verification

- Typst compiles cleanly to `docs/report/main.pdf` with zero missing citations or broken labels.
- Code style validated with `typstyle --check docs/report/main.typ`.

## 2026-09-06 — Notebook/Report taxonomy consistency fix (P0 packaging item)

The notebook's error-analysis cell (§6, cell id `b671d660`) had drifted from
`scripts/error_taxonomy.py`: it flagged `diacritic_loss` on exact
diacritic-stripped string equality and inlined its own gold extraction, while
the canonical script scores stripped-text token F1 against `TEXT_PASS` via
`gold_values`/`text_score`. Same flag name, two criteria — the notebook
reported 1 `diacritic_loss` for Ornith/T2SQL where the sealed taxonomy CSV
(and the report) say 9.

Fix: the cell now imports `strip_diacritics`, `gold_values`, and `text_score`
from the canonical scripts (single source of truth) instead of reimplementing
them; no report numbers were changed. Full Run All revalidated on a fresh
Colab CPU session (session `vigsqa-cell33`, 39 cells, zero cell errors):
`diacritic_loss` 9, `geocode_miss` 219, `sector_right_angle_wrong` 14 —
matching `results/analysis/taxonomy_Ornith-1.5-9B-NVFP4_text2sql_all.csv`
exactly. Executed outputs are saved in the working notebook.

## Pre-submission notebook checklist

- [x] **Cell `b671d660` (§6 taxonomy flags) matches the canonical script** — see
  2026-09-06 entry above; `diacritic_loss` 9 / `geocode_miss` 219 /
  `sector_right_angle_wrong` 14 on a fresh Colab Run All.
- [x] **Cell `02cb282e` (§6 failure examples) shows one representative failure
  per taxonomy stage** (2026-09-06). The old positional `head(6)` selector
  sampled almost only `intersects+count` questions and was rejected for the
  paper. The cell now classifies every sealed Ornith/T2SQL row with the
  canonical `classify`/`parse_ok` from `scripts/error_taxonomy.py` (plus
  `exec_rows`/`rescue_block` for the rescuable stage) and picks, per failure
  stage, the first question whose tid is not already shown. Revalidated on a
  fresh Colab CPU Run All (`vigsqa-cell35`, 39 cells, zero errors): six
  stages — no-rows, parse-failure, rescuable, rows-unusable, sql-error,
  wrong-attempted — six distinct tids; cell `b671d660` numbers unchanged.
  Notebook-cell code ruff-checked (only cross-cell F821/E402 false positives
  remain, inherent to extraction); `ruff check scripts/` green.

## 2026-09-06 — Notebook markdown style pass, local Run All, figure re-pin

- **Markdown style pass over all 21 markdown cells** against the charter
  agreed in the style session (`codex-session-01a07272-…md`): academic
  English, no em dashes, no semicolons, no audit-style phrasing, headings
  locked. Mechanical scan found only cell `b6508937` (§6 representative
  failures, rewritten for the new selector) in violation; rewritten in the
  agreed voice. Also applied the outstanding `diacritic_loss` bullet fix in
  cell `9a33d1f0` that the style session had prescribed but never applied:
  the bullet now describes the canonical token-F1 criterion instead of exact
  stripped-string equality. Verified: 0 em dashes, 0 semicolons, 0 banned
  phrases, heading sequence byte-identical, code cells byte-identical.
- **Local Run All** (Pixi `dev`, `nb execute`, 39 cells, zero cell errors,
  PostgreSQL already bootstrapped): taxonomy 9/219/14 unchanged; §6 failure
  table reproduces the Colab snapshot (six stages, six distinct tids);
  OSM basemap tiles fetched successfully. Executed outputs are saved in
  `ViGSQA.ipynb`.
- **Figure assets re-pinned.** Local runs are not byte-reproducible (OSM
  Mapnik tile responses vary), so the stale local figures and the release
  archive were replaced by this run's output: `scripts/figures.sha256`
  re-pinned (fig1/fig3 unchanged) and `report-figures.tar.gz` re-uploaded
  to the v3.0.0 release with `--clobber`; empty legacy dirs `report/` and
  `references/` removed.
- **Title de-versioned** at the user's direction: the notebook title is
  `# ViGSQA: Vietnamese Geospatial Question Answering` (no `v3.0.0`), so no
  release-version mention remains outside technical filenames/URLs.
- **Colab copy synced via the Colab MCP** (browser session, not the CLI):
  the open notebook shared the local UUID lineage; six cells were replaced
  (title, §6 markdown + taxonomy code, representative-failure markdown +
  selector code, Limitations) and verified back byte-identical to
  `ViGSQA.ipynb`.
- Follow-ups at the user's direction: the **Precomputed model outputs**
  limitation bullet was dropped (the intro cell already states the external
  inference setup), and the §6 representative-failure markdown gained two
  analytical sentences (only the wrong-answer stage yields a prediction;
  the rescuable stage is §5's rescue target). Colab re-synced and verified
  (title, §6 markdown, Limitations).

## 2026-09-06 — Full ACL rewrite of `main.typ` (page-budgeted, evidence-synchronized)

The paper was rewritten end-to-end against the brief's eight work areas.
Final layout: **5 main-content pages**, References start on page 6, appendices
follow (10 PDF pages total). Measured with temporary `#context metadata`
markers at the conclusion/bibliography boundary (removed before release).

### Structure and page budget

- Section order: Abstract, Introduction, Related Work, Dataset (Construction,
  Location Gold, quality-control paragraph), Baselines (Direct, Text2SQL,
  scope; Zero-LLM Rescue subsection), Experimental Setup (Metrics with formal
  definitions, dev/test-split paragraph), Results and Discussion, Error
  Analysis, Limitations, Ethical Considerations, Conclusion. All mandatory
  sections present.
- **Master results table** (`tab:fourruns`): the former four-run table and the
  rescue table were merged into one table with a `+R` intervention column
  (attempted/correct full-benchmark rows + per-family test means; the four
  zero-delta rescue rows were dropped as uninformative). Rendered **in-column
  at 8 pt** (ACL `\footnotesize` practice) instead of a `scope: "parent"`
  band, per the user's consider-first guidance on two-column elements: the
  7-column numeric table fits a 7.7 cm column at 8 pt, removes the page-top
  float (and its slack), and the wide `scope: "parent"` remains only where
  genuinely needed (appendix samples/templates tables).
- Appendix (excluded from the page budget): sample records table + stored
  JSON record + surface phrasings; 28-template inventory with pipeline and
  baselines figures; taxonomy stage-by-family table.
- Compression went 6.95 -> 5.00 content pages through 13 passes of prose
  density rewriting; no metric formula, evidence number, or required section
  was deleted. Fonts/spacing follow tracl defaults (only the 8 pt table text
  via a figure-local `#set text`).

### Metric definitions (from `scripts/run_evaluation.py`)

Normalization (NFKC, casefold, punctuation-to-space, diacritics preserved),
token-multiset P/R/F1, capped relative error with the exact zero-guard cases,
circular direction error, 500 km-capped geodesic error, best-pair reduction
(max-F1/min-error, ties toward earlier candidates), attempted semantics and
worst-case scoring of unattempted questions, and the explicit separation of
official metrics from the analysis-only thresholds (F1 >= 0.5 / E <= 0.1) and
the taxonomy-level `refused` label.

### Bibliography: `references.yaml` replaced by `references.bib`

Pergamon's `add-bib-resource` parses BibTeX only, so the audited bibliography
now lives in `docs/report/references.bib` (19 entries); the Hayagriva
`references.yaml` was removed to keep a single source. Every entry was
verified by three parallel web agents against ACL Anthology / ACM DL /
Springer / Copernicus / PLOS ONE / arXiv / Hugging Face. Key corrections:

- `li2025mapqa`: archival SIGSPATIAL '25 version replaces the preprint —
  title "Benchmarking Geospatial Question Answering with MapQA", 6 authors,
  pp. 1042–1045, DOI 10.1145/3748636.3764174. In-text "concurrent" dropped
  (it is prior work from our 2026 vantage).
- `nguyen2020uitviquad`, `thai2022vicov19qa`: published versions have
  4-author lists (the old lists matched arXiv preprints); pages/publishers/
  DOIs added.
- `le2022vimqa`: author names de-garbled (Nguyen-Khang Le, Dieu-Hien
  Nguyen, Tung Le, Minh Nguyen).
- `punjani2018geoquestions201`: GIR '18, ACM, pp. 1–10, DOI, 14 authors
  (one was dropped before).
- `xu2020geoanqu` added (GeoAnQu's true origin; the Beydokhti et al. 2021
  attribution circulating in GS-QA's reference list is unreliable).
- `qwen35`: author corrected to AxionML (community NVFP4 quantization of
  Qwen/Qwen3.5-9B, not the Qwen team).
- `nominatim`: author corrected to "Nominatim developers" (OSMF only operates
  the public instance).
- `vnreform2025`: Resolution No. 202/2025/QH15, passed 12 June 2025; district
  abolition attributed to the 16 June 2025 instruments, not Resolution 202.
- Unused entries dropped (`zelle1996geoquery`, `li2023bird`, `postgis`,
  `geofabrik`); GS-QA §2 facts quoted in our Related Work were all CONFIRMED
  against arXiv 2605.22811 by the audit agent.

### Claim -> source verification (main quantitative claims)

- 2,214/2,800 = 79.1% Ornith/Direct unattempted, 77 correct; Qwen/Direct
  2,039 unattempted, 79 correct — `results/evaluation/*/per_question.jsonl`.
- Refusals 904/1,100 entity, 572/800 location —
  `results/analysis/taxonomy_Ornith-1.5-9B-NVFP4_direct_all.csv`.
- Full-benchmark attempted/correct 20.9/2.8, 54.2/32.4, 27.2/2.8, 51.5/29.3%
  and all per-family test means in `tab:fourruns` — notebook §4.2 (Colab,
  latest run) cross-checked against sealed per-question artifacts.
- Rescue: 222/2,240 test (entity 165, location 35, direction 3, distance 19
  — verified `results/rescue/rescued_test.jsonl`), zero regressions, entity
  F1 +0.162, distance rel-err −0.078; count/area/length/textual_fact
  unchanged because no question in them produced a rescue candidate.
- Taxonomy flags 9 / 219 (46% of 471 attempted locations) / 14 with
  comparables 139 (Qwen/T2S) and 175 (Ornith/Direct); entity SQL errors
  100 vs 209, no-rows 280, subquery-as-expression 107 of 295, area/length
  unusable 34/43 — taxonomy CSVs + `baselines/cache_vi/.../sql_exec.json`.
- Family sizes corrected to 1,100 entity + 100 textual-fact (was miscounted
  as 1,200); test n in the table caption sums to 2,240.
- Dataset numbers (38,207 POIs, 5,321 address-bearing pool, 13,857/72/7
  coverage, 4,500–4,800 district/city/province, gold-set median 2–6 max 542,
  128 phrasings, 26 sub-categories) — T10 record and generator sources.
- Dev/test stability scoped: location distance 0.670 dev / 0.643 test, but
  direction text F1 0.712 dev / 0.552 test (sampling-sized divergence).

### Validation

- `typst compile` clean (only tracl's benign inconsolata fallback warning);
  `typstyle --check` clean after `typstyle -i` on session-owned code.
- Citation/label audit: every `#cite` key resolves in `references.bib`, no
  unused bib entries, no dangling `@` refs.
- `scan.py --strict` on `main.typ`: 0 hard tells (advisory long-sentence
  notes remain by design in data-dense sentences).
- Content-page boundary confirmed by dual temporary markers after the final
  edits; PNG render of all 10 pages checked structurally (dimensions, ink
  coverage, no blank/overflow pages).
