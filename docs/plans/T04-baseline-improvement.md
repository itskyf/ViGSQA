# T04 — Improve Frozen Baseline Failures

**Status: done (2026-09-05).** Evaluation protocol: the benchmark is split 20/TID dev + 80/TID test (`docs/dev_test_split_v3.0.0.json`, T04-owned). Method selection inspects **dev evidence only**; the intervention is frozen (committed) before any test aggregate is computed. Sealed T03 artifacts are read-only inputs; all intervention outputs live outside `results/evaluation/` and `cache_vi/pv-26b1ac0d/`.

## Dev/test protocol

- `scripts/make_dev_test_split.py` → `docs/dev_test_split_v3.0.0.json` (committed sidecar; the 28 frozen JSONLs are untouched). Deterministic: per TID, QIDs ranked by ascending `sha256("vigsqa-devtest-v1::<qid>")`, first 20 of 100 are dev → 560 dev / 2,240 test. `--check` re-derives byte-identically. No train split (nothing is trained).
- Baseline dev/test metrics come from the sealed T03 `per_question.jsonl` files filtered by the split (`scripts/report_split_metrics.py`) — no inference is rerun. Means include unattempted questions at their worst-case values (paper §5.1 semantics).
- Stratification audit: 28 TIDs × exactly 100 confirmed (28×100 = 2,800; `wc -l` + MANIFEST counts). T07's internal attribute skew is within one stratum; TID is the only stratification variable. Dev/test baseline aggregates track each other closely (e.g. Ornith-Text2SQL location distance error 0.670 dev / 0.643 test), confirming the stratification is stable.

## Metric semantics check (paper §5.1 vs upstream vs current evaluator)

Compared `references/main.tex` §5.1 (~L1301-1382), upstream-derived `baselines/evaluate.py`, and `scripts/run_evaluation.py` before touching anything: the current evaluator preserves the paper's intended semantics — token P/R/F1, address-text plus geodesic distance normalized by 500 km with cap 1.0, 8-sector/circular |Δ|/180 direction error, capped relative error for numerics, metric-specific attempted/unattempted with worst-case inclusion in means, and best applicable match across the full distance-ordered gold set (T03 contract). Deviations from upstream code are deliberate Vietnamese adaptations already documented in the T03 record (NFKC normalization so composed/decomposed diacritics compare equal, punctuation via Unicode category, digits kept as digits, Vietnamese sector names and unit words, decimal comma, multiset token overlap, gold-side geometry instead of geocoded gold). **No scoring code was changed for T04**; the intervention arm is scored by importing `evaluate`/`candidates`/`finite_number`/`load_geocodes` verbatim from `run_evaluation.py`. Paper error-binning thresholds (text F1 ≥ 0.5, error ≤ 0.1, `main.tex` ~L1819) are used only for analysis, never scoring.

## Pre-registration disclosure

Intervention *feasibility* was scouted before the freeze on **full-set** aggregates over sealed artifacts (the T03 results are already-published evidence): Ornith/Direct empty candidates are genuine model refusals (2,211/2,214 have parse JSON blocks with correct keys and null values — no extraction headroom); Ornith/Text2SQL empty-candidate root causes split ~543 sql-ok-empty-rows / ~435 rows-but-null-answer / ~220 sql-exec errors; ~286 of the 435 are deterministically recoverable from execution rows. This scouting fixed the *shape* of the candidate intervention; the recorded go/no-go decision below uses **dev counts only**, and no per-question test result was inspected before the freeze commit.

## Intervention (frozen as `records-to-answer-rescue-v1`)

One change, zero new LLM inference, implemented in `scripts/t04_rescue.py` (arm: Ornith/Text2SQL, the endpoint-served model):

- **Trigger (fallback-only):** the sealed run has empty `candidates` for the question — i.e. the score already sits at the unattempted floor (F1 0 / error 1.0). Questions the model answered are never touched, so per-question scores can only improve or tie; this is asserted per question after every evaluation.
- **Action:** if `sql_exec` rows carry usable typed values, emit them through the parser's fenced-JSON shape: entity → first non-empty of `poi_name/park_name/lake_name/road_name` per row (the published gold key set — schema knowledge, not gold answers); location → `address` column or canonical string rebuilt from `addr_*` components in the MANIFEST-documented order (mirrors `generator_vi.canonical_address`); count/distance/direction/area/length → the family column. Typing and unit filtering then happen inside the sealed `candidates()`/`finite_number()` paths. Textual facts are never rescued (out-of-schema by verifier design).
- **Scoring:** merged parse records → imported `evaluate()`; geocoding warm-started from the sealed `geocodes.json` (identical address strings keep sealed coordinates), only genuinely new rescued addresses hit Nominatim at 1 req/s with terminal rejections persisted.
- Outputs under `results/t04/rescue/` only: `intervention.json` (freeze manifest: rule, input SHA-256s, dev gate counts), `per_question_{split}.jsonl`, `rescued_{split}.jsonl`, `geocodes_{split}.json`, `summary_{split}.json`.

## Gate (dev only) — decision evidence

| family | answered | rescuable | sql-error | no-rows | rows-unusable |
|---|---|---|---|---|---|
| area | 7 | 0 | 4 | 0 | 9 |
| count | 38 | 1 | 1 | 0 | 0 |
| direction | 30 | 1 | 3 | 6 | 0 |
| distance | 29 | 5 | 1 | 5 | 0 |
| entity | 99 | 43 | 25 | 53 | 0 |
| length | 6 | 0 | 3 | 0 | 11 |
| location | 82 | 15 | 15 | 39 | 9 |
| textual_fact | 8 | 0 | 4 | 0 | 8 |

Dev rescuable: **65/560 (11.6%)** — far above the pre-agreed ≥5% empty-candidate / ≥2pp headroom threshold for a Tier-0 (zero-LLM) intervention. The alternative (one Ornith prompt-variant step) is not needed and stays unused.

## Dev evaluation (before freeze)

| family | metric | baseline | rescue | delta |
|---|---|---|---|---|
| area | relative_error | 0.682 | 0.682 | +0.000 ≈ |
| count | relative_error | 0.550 | 0.550 | +0.000 ≈ |
| direction | text_f1 | 0.713 | 0.738 | +0.025 ↑ |
| direction | angle_error | 0.284 | 0.259 | −0.025 ↑ |
| distance | relative_error | 0.530 | 0.479 | −0.050 ↑ |
| entity | text_f1 | 0.263 | 0.423 | +0.160 ↑ |
| length | relative_error | 0.700 | 0.700 | +0.000 ≈ |
| location | text_f1 | 0.340 | 0.416 | +0.076 ↑ |
| location | distance_error | 0.670 | 0.583 | −0.087 ↑ |
| textual_fact | text_f1 | 0.050 | 0.050 | +0.000 ≈ |

65 rescued; per-question regression assert passed (0 regressions, as guaranteed by the fallback-only trigger). 328 new addresses geocoded (rescued location questions contribute one address per returned row; ~22/question).

## Freeze

Commit `5259b7e6` ("t04: freeze records-to-answer-rescue-v1 ...") contains the rescue script, the split artifact, and the record up to the dev table above. The test evaluation ran after that commit; no per-question test evidence was inspected before it.

## Test evaluation (after freeze)

222/2,240 questions rescued (9.9%); per-question regression assert passed (0 regressions).

| family | metric | baseline | rescue | delta |
|---|---|---|---|---|
| area | relative_error | 0.711 | 0.711 | +0.000 ≈ |
| count | relative_error | 0.570 | 0.570 | +0.000 ≈ |
| direction | text_f1 | 0.552 | 0.571 | +0.019 ↑ |
| direction | angle_error | 0.433 | 0.414 | −0.019 ↑ |
| distance | relative_error | 0.645 | 0.568 | −0.078 ↑ |
| entity | text_f1 | 0.278 | 0.440 | +0.162 ↑ |
| length | relative_error | 0.675 | 0.675 | +0.000 ≈ |
| location | text_f1 | 0.387 | 0.436 | +0.049 ↑ |
| location | distance_error | 0.643 | 0.589 | −0.055 ↑ |
| textual_fact | text_f1 | 0.000 | 0.000 | +0.000 ≈ |

630 new addresses geocoded for rescued location questions. Every family that improved on dev improved on test, with deltas of the same sign and similar magnitude (entity +0.162 test vs +0.160 dev; distance −0.078 vs −0.050) — the improvement is not a dev-split artifact.

## Limitations

- The rescue only recovers the refusal floor; it cannot fix wrong-but-attempted answers (the larger remaining class — see the T05 taxonomy) or sql-error/no-rows failures (their SQL yields nothing to rescue).
- area/length/textual_fact are untouched by construction: their failing SQL returns no typed aggregate (area/length golds come from external measurements; textual facts are out-of-schema for the verifier).
- Location rescue emits the row's address string, which may differ from gold formatting even when it names the same place — text F1 gains understate the true spatial recovery (distance error improves separately).
- The intervention arm is evaluated as a merge over sealed parse records; it is not a rerun of the pipeline, so latency/cost claims about the full system do not apply (the rescue itself is deterministic and free).
