# Baseline Results — VN-GeoQA

> **ARCHIVED — PRE-FREEZE RESULTS.** These numbers predate the v1.0.0 benchmark freeze (superseded candidate dataset) and are **not valid benchmark evidence**. Official results come from fresh runs against the frozen benchmark (T03).

## Setup

- **Dataset:** 800 Vietnamese geospatial questions (8 types × 100)
- **Hardware:** 2× NVIDIA RTX 3060 12 GB (24 GB total VRAM)
- **Inference:** Ollama 0.32.14 / llama.cpp Docker, Q4_K_M quantization
- **Nothink:** `<think>\n\n</think>\n\n` prefix on all Qwen3/Qwen3.5/Qwen3.6 to disable chain-of-thought

---

## Models

| Model | Size | Backend |
|-------|------|---------|
| Gemma-4-26B | 26B | llama.cpp (Docker, CUDA) |
| Qwen3.5-9B | 9B | llama.cpp (Docker, CUDA) |
| Qwen3.5-27B | 27B | Ollama 0.32.14 |
| Qwen3.6-27B | 27.8B | Ollama 0.32.14 |

---

## Overall text F1

| Model | direct | text2sql |
|-------|:------:|:--------:|
| Gemma-4-26B | 0.058 | 0.343 |
| Qwen3.5-9B | 0.040 | 0.342 |
| **Qwen3.5-27B** | **0.059** | **0.386** |
| Qwen3.6-27B | 0.047 | 0.385 |

---

## Per-type text F1 — direct

All models near-zero — no DB access means relying on parametric knowledge of local Vietnamese POIs, which models do not have.

| Type | Gemma-4-26B | Qwen3.5-9B | Qwen3.5-27B | Qwen3.6-27B |
|------|:-----------:|:---------:|:-----------:|:-----------:|
| knn+name | 0.160 | 0.106 | **0.167** | 0.135 |
| knn+loc | 0.000 | 0.000 | 0.000 | 0.000 |
| knn+distance | 0.000 | 0.002 | 0.000 | 0.000 |
| knn:direction+name | **0.157** | 0.102 | 0.164 | 0.127 |
| range+name | 0.065 | 0.060 | **0.074** | 0.043 |
| range+loc | 0.000 | 0.000 | 0.000 | 0.000 |
| range+count | 0.000 | 0.000 | 0.000 | 0.000 |
| range:direction+name | **0.080** | 0.049 | 0.070 | 0.068 |
| **Overall** | 0.058 | 0.040 | 0.059 | 0.047 |

---

## Per-type text F1 — text2sql

| Type | Gemma-4-26B | Qwen3.5-9B | Qwen3.5-27B | Qwen3.6-27B | Winner |
|------|:-----------:|:---------:|:-----------:|:-----------:|:------:|
| knn+name | 0.392 | **0.586** | 0.535 | 0.538 | Qwen3.5-9B |
| knn+loc | 0.000 | 0.000 | 0.000 | 0.000 | tie |
| knn+distance | **0.670** | 0.580 | **0.670** | **0.670** | Gemma/27B/36B |
| knn:direction+name | 0.519 | 0.294 | 0.583 | **0.590** | Qwen3.6-27B |
| range+name | 0.181 | **0.293** | 0.245 | 0.280 | Qwen3.5-9B |
| range+loc | 0.000 | 0.000 | 0.000 | 0.000 | tie |
| range+count | 0.660 | **0.740** | 0.680 | 0.640 | Qwen3.5-9B |
| range:direction+name | 0.322 | 0.241 | **0.374** | 0.358 | Qwen3.5-27B |
| **Overall** | 0.343 | 0.342 | **0.386** | 0.385 | **Qwen3.5-27B** |

---

## Parsed Metrics — text2sql

### Location types — dist_err (↓ better, 0 = exact, 1 = ≥500 km off)

| Type | Gemma-4-26B | Qwen3.5-9B | Qwen3.5-27B | Qwen3.6-27B |
|------|:-----------:|:---------:|:-----------:|:-----------:|
| knn+loc | **0.135** | 0.162 | 0.172 | 0.206 |
| range+loc | 0.161 | **0.155** | 0.224 | 0.230 |

text F1 = 0.000 for all — model outputs natural-language addresses instead of coordinates. SQL execution partially correct (dist_err shows proximity), but answer-generation step loses structured output.

### Numeric types — rel_err (↓ better, 0 = exact)

| Type | Gemma-4-26B | Qwen3.5-9B | Qwen3.5-27B | Qwen3.6-27B |
|------|:-----------:|:---------:|:-----------:|:-----------:|
| knn+distance | 0.361 | 0.414 | **0.276** | 0.292 |
| range+count | 0.350 | **0.240** | 0.287 | 0.327 |

---

## Key Findings

**1. DB access is mandatory.**
Direct tops out at 0.059. Models hallucinate POI names, output Vietnamese words for distances ("hai mươi mét"), refuse to answer count questions. text2sql lifts this to 0.342–0.386 — a 5–8× gain.

**2. Qwen3.5-27B and Qwen3.6-27B essentially tied overall (0.386 vs 0.385).**
Qwen3.6-27B wins on `knn:direction+name` (0.590 vs 0.583) and matches on `knn+distance` (0.670). Qwen3.5-27B edges ahead on `range:direction+name` (0.374 vs 0.358) and `range+count` (0.680 vs 0.640).

**3. Models have complementary strengths.**

- Qwen3.5-27B / Qwen3.6-27B: best overall, direction types, numeric precision
- Qwen3.5-9B: best for name retrieval (`knn+name` 0.586) and counting (`range+count` 0.740)
- Gemma-4-26B: best location accuracy (dist_err 0.135 on knn+loc)

**4. Location types unsolved (text F1 = 0.000 across all models).**
SQL execution partially correct (dist_err 0.135–0.230), but answer-generation LLM converts coordinates into prose addresses. Fix: extract coordinates directly from SQL result rows, skip LLM answer step for loc types.

**5. Scale doesn't help without DB.**
Direct scores cluster tightly (0.040–0.059) regardless of model size or generation. No uplift from scale when DB is absent.

---

## Eval CSV Schema

Files in `baselines/`:

```text
<model>_<baseline>_text_eval.csv   → id, attempted, P, R, F1, type
<model>_<baseline>_parsed_eval.csv → id, attempted, distance_error, relative_error, type
```
