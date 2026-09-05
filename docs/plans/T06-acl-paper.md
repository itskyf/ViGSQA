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
  - `docs/report/figures/`: SVG diagrams for Figure 1 (`fig1_baselines.svg`) and Figure 3 (`fig3_pipeline.svg`).
- **Semantic Formatting Invariant**: All ad-hoc LaTeX spacing (`\vspace`, `\resizebox`, `\tabcolsep`, etc.) removed; layout relies on semantic Typst primitives (`table`, `figure`). Wide tables (Table 1 and Table 4) span across both columns via `scope: "parent"`.
- **Visual Comparative Analysis**: Page screenshots captured at 144 PPI for both LaTeX (9 pages) and Typst (10 pages) and analyzed with multimodal vision.

## Verification

- Typst compiles cleanly to `docs/report/main.pdf` with zero missing citations or broken labels.
- Code style validated with `typstyle --check docs/report/main.typ`.
