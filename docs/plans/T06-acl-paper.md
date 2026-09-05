# T06 — ACL Paper

**Status: in_progress.**

## Dependencies

T03 official baselines, T04 intervention conclusions, and T05 analysis/demo evidence.

## Scope

Write the course report with ACL style, documenting the benchmark, methods, evaluation, results, errors, limitations, and reproducibility. Ported to Typst using `@preview/tracl:0.8.1`.

## Progress & Migration to Typst

- **Source Document**: Ported from `references/vigsqa/main.tex` and `references/vigsqa/custom.bib` ("VN-GeoQA: A Reproducible Vietnamese Geospatial Question Answering Benchmark" by Anh Pham-Ky & Tien Dang-Anh, HCMUS), corresponding to the LaTeX PDF `/mnt/c/Users/itsky/Downloads/_HCMUS__NLP_CK_latex.pdf`.
- **Target Files**:
  - `docs/report/main.typ`: Full paper in Typst with ACL template (`@preview/tracl:0.8.1`).
  - `docs/report/references.yaml`: 22 bibliographic entries in Hayagriva YAML format.
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
