# VN-GeoQA Baseline Evaluation Report

> **ARCHIVED — PRE-FREEZE RESULTS.** These numbers predate the v1.0.0 benchmark freeze (superseded candidate dataset) and are **not valid benchmark evidence**. Official results come from fresh runs against the frozen benchmark (T03).

**Dataset:** VN-GeoQA — 800 Vietnamese geospatial questions, 8 types × 100 questions each  
**Database:** OpenStreetMap Vietnam (PostGIS, `osm_vn`)  
**Date:** 2026-08-20

---

## 1. Setup

### Question Types

| Type | Description |
|------|-------------|
| `knn+name` | Nearest POI name |
| `knn+loc` | Nearest POI location (coordinates) |
| `knn+distance` | Distance to nearest POI |
| `knn:direction+name` | Nearest POI in a given direction, return name |
| `range+name` | POI within radius, return name |
| `range+loc` | POI within radius, return location |
| `range+count` | Count of POIs within radius |
| `range:direction+name` | POI within radius in a given direction, return name |

### Baselines

| Baseline | Description |
|----------|-------------|
| **direct** | Model answers from parametric knowledge only — no DB access |
| **text2sql** | Model generates SQL → executes against PostGIS → model answers from result |

### Models Evaluated

| Model | Size | Backend | Quantization |
|-------|------|---------|-------------|
| Gemma-4-26B | 26B | llama.cpp (Docker) | Q4_K_M |
| Qwen3.5-9B | 9B | llama.cpp (Docker) | Q4_K_M |
| Qwen3.5-27B | 27B | Ollama 0.32.14 | Q4_K_M |

All models run with **nothink prefix** (`<think>\n\n</think>\n\n`) to suppress chain-of-thought.  
Hardware: 2× NVIDIA RTX 3060 12 GB (24 GB total VRAM).

### Evaluation Metrics

| Metric | Applied to | Interpretation |
|--------|-----------|---------------|
| **text_F1** | All types | Token-level F1 vs. ground-truth answer string |
| **dist_err** | loc types | Normalized geodesic error; 0 = exact, 1 = ≥500 km off |
| **rel_err** | distance, count | Relative numeric error; 0 = exact, 1 = fully wrong |

---

## 2. Results

### 2.1 Overall text F1

| Model | direct | text2sql | Gain |
|-------|--------|----------|------|
| Gemma-4-26B | 0.058 | **0.343** | +0.285 |
| Qwen3.5-9B | 0.040 | **0.342** | +0.302 |
| Qwen3.5-27B | 0.059 | — (incomplete) | — |

> Qwen3.5-27B text2sql run was interrupted by a PostgreSQL service outage after sql_generate phase completed. Direct-only results are available.

### 2.2 Per-type text F1 — direct baseline

| Type | Gemma-4-26B | Qwen3.5-9B | Qwen3.5-27B |
|------|:-----------:|:---------:|:-----------:|
| knn+name | 0.160 | 0.106 | **0.167** |
| knn+loc | 0.000 | 0.000 | 0.000 |
| knn+distance | 0.000 | 0.002 | 0.000 |
| knn:direction+name | **0.157** | 0.102 | 0.164 |
| range+name | 0.065 | 0.060 | **0.074** |
| range+loc | 0.000 | 0.000 | 0.000 |
| range+count | 0.000 | 0.000 | 0.000 |
| range:direction+name | **0.080** | 0.049 | 0.070 |
| **Overall** | 0.058 | 0.040 | 0.059 |

### 2.3 Per-type text F1 — text2sql baseline

| Type | Gemma-4-26B | Qwen3.5-9B | Winner |
|------|:-----------:|:---------:|:------:|
| knn+name | 0.392 | **0.586** | Qwen3.5-9B |
| knn+loc | 0.000 | 0.000 | tie |
| knn+distance | **0.670** | 0.580 | Gemma-4-26B |
| knn:direction+name | **0.519** | 0.294 | Gemma-4-26B |
| range+name | 0.181 | **0.293** | Qwen3.5-9B |
| range+loc | 0.000 | 0.000 | tie |
| range+count | 0.660 | **0.740** | Qwen3.5-9B |
| range:direction+name | **0.322** | 0.241 | Gemma-4-26B |
| **Overall** | **0.343** | 0.342 | tie |

### 2.4 Parsed metrics — text2sql

#### Location types (dist_err ↓ better)

| Type | Gemma-4-26B | Qwen3.5-9B |
|------|:-----------:|:---------:|
| knn+loc | **0.135** | 0.162 |
| range+loc | 0.161 | **0.155** |

> Attempted: 0/100 by text F1 (model outputs natural-language addresses, not coordinates), but SQL execution is partially correct as measured by dist_err.

#### Numeric types (rel_err ↓ better)

| Type | Gemma-4-26B | Qwen3.5-9B |
|------|:-----------:|:---------:|
| knn+distance | **0.361** | 0.414 |
| range+count | 0.350 | **0.240** |

---

## 3. Analysis

### 3.1 Direct baseline is near-random for all models

All three models score ≤ 0.059 text F1 on direct. Failure modes:

- **Distance queries** — models output Vietnamese words ("hai mươi mét") instead of numeric values; ground truth is in km
- **Location queries** — models return natural-language addresses instead of coordinates; att = 0/100
- **Count queries** — models say "không có thông tin" (no information) for most range queries
- **Name queries** — models hallucinate POI names; partial overlap only for nationally known landmarks

This confirms that geospatial queries over local Vietnamese OSM data **require database grounding**. Parametric knowledge is insufficient.

### 3.2 text2sql delivers 5–8× improvement

Both Gemma-4-26B and Qwen3.5-9B reach ~0.342–0.343 overall text F1 — a large absolute gain over direct (+0.285 / +0.302). The models generate valid PostGIS SQL in the majority of cases; the bottleneck is answer-generation quality.

### 3.3 Model strengths split by query structure

**Gemma-4-26B** outperforms on spatial-reasoning types:

- `knn+distance` (+0.090): better numeric extraction and formatting from SQL results
- `knn:direction+name` (+0.225): stronger directional SQL clause generation (`ST_Azimuth`, bearing filters)
- `range:direction+name` (+0.081): same pattern

**Qwen3.5-9B** outperforms on entity-matching types:

- `knn+name` (+0.194): better Vietnamese name matching/normalization
- `range+name` (+0.112): same pattern
- `range+count` (+0.080): more reliable `COUNT(*)` SQL generation

Overall scores are nearly identical (0.343 vs 0.342), suggesting the models are complementary rather than one strictly dominating.

### 3.4 Location types remain unsolved (text F1 = 0.000)

`knn+loc` and `range+loc` score 0.000 text F1 across all models and baselines. Root cause:

1. SQL execution returns raw coordinate rows
2. Answer-generation LLM paraphrases them into Vietnamese prose addresses
3. Evaluator cannot parse prose into `{"lat": x, "lon": y}` for comparison

The dist_err metric (0.135–0.162) shows SQL execution is partially correct — the coordinates reach the LLM but are lost in the answer step. A post-processing fix (extract coordinates directly from SQL result without LLM rephrasing) would likely recover these 200 questions.

### 3.5 SQL execution failure accounts for 200 unattempted questions

Both text2sql runs show att = 600/800. The 200 unattempted questions are the `knn+loc` (0/100) and `range+loc` (0/100) types — where SQL may succeed but the answer-generation path cannot produce a parseable coordinate answer, so the evaluator marks them as unattempted.

### 3.6 Qwen3.5-27B (direct only)

27B direct (0.059) is marginally above 9B direct (0.040) but in the same failure class. Larger model size does not compensate for absent database access. text2sql results pending PostgreSQL restoration.

---

## 4. Summary

| Model | Baseline | text_F1 | Strength |
|-------|----------|:-------:|---------|
| Gemma-4-26B | direct | 0.058 | — |
| Gemma-4-26B | **text2sql** | **0.343** | distance, direction queries |
| Qwen3.5-9B | direct | 0.040 | — |
| Qwen3.5-9B | **text2sql** | **0.342** | name, count queries |
| Qwen3.5-27B | direct | 0.059 | — |
| Qwen3.5-27B | text2sql | pending | — |

**Key takeaways:**

1. Database grounding (text2sql) is essential — direct baseline is near-zero for all models
2. Gemma-4-26B and Qwen3.5-9B are tied overall but have complementary strengths by query type
3. Location types (knn+loc, range+loc) need a post-processing fix to extract coordinates before answer generation
4. text2sql gain is larger for Qwen3.5-9B (+0.302) than Gemma-4-26B (+0.285), suggesting Qwen is weaker at direct but a stronger SQL generator

---

## 5. Limitations and Future Work

1. **Qwen3.5-27B text2sql** — rerun after restoring PostgreSQL to complete the three-model comparison
2. **Location answer extraction** — bypass LLM answer step for loc types; extract coordinates directly from SQL result rows
3. **SQL error analysis** — inspect sql_exec failures to determine if schema mismatches or query errors drive the 200 unattempted loc questions
4. **RAG baseline** — retrieve relevant OSM records as prompt context rather than generating SQL; may improve loc types where SQL generation is harder
5. **Vietnamese-tuned models** — all evaluated models are general-purpose; a Vietnamese-instruction-tuned model may improve name matching and fluency
6. **Ensemble** — combining Gemma-4-26B (direction/distance) + Qwen3.5-9B (name/count) predictions could push overall F1 above either individual model
