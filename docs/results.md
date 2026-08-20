# Baseline Results — VN-GeoQA

## Setup

- **Dataset:** 800 Vietnamese geospatial questions (8 types × 100)
- **Hardware:** 2× NVIDIA RTX 3060 12 GB (24 GB total VRAM)
- **Inference:** Ollama 0.32.14 / llama.cpp Docker, Q4_K_M quantization
- **Nothink:** `<think>\n\n</think>\n\n` prefix on all Qwen3/Qwen3.5 to disable chain-of-thought

---

## Models

| Model | Size | Backend |
|-------|------|---------|
| Gemma-4-26B | 26B | llama.cpp (Docker, CUDA) |
| Qwen3.5-9B | 9B | llama.cpp (Docker, CUDA) |
| Qwen3.5-27B | 27B | Ollama 0.32.14 |

---

## Overall text F1

| Model | direct | text2sql |
|-------|:------:|:--------:|
| Gemma-4-26B | 0.058 | **0.343** |
| Qwen3.5-9B | 0.040 | **0.342** |
| Qwen3.5-27B | 0.059 | — ¹ |

¹ text2sql run interrupted by PostgreSQL outage after sql_generate phase completed.

---

## Per-type text F1 — direct

All models near-zero — no DB access means relying on parametric knowledge of local Vietnamese POIs, which models do not have.

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

---

## Per-type text F1 — text2sql

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

---

## Parsed Metrics — text2sql

### Location types — dist_err (↓ better, 0 = exact, 1 = ≥500 km off)

| Type | Gemma-4-26B | Qwen3.5-9B |
|------|:-----------:|:---------:|
| knn+loc | **0.135** | 0.162 |
| range+loc | 0.161 | **0.155** |

text F1 = 0.000 for both — model outputs natural-language addresses instead of coordinates. SQL execution is partially correct (dist_err shows proximity), but answer-generation step loses structured output.

### Numeric types — rel_err (↓ better, 0 = exact)

| Type | Gemma-4-26B | Qwen3.5-9B |
|------|:-----------:|:---------:|
| knn+distance | **0.361** | 0.414 |
| range+count | 0.350 | **0.240** |

---

## Key Findings

**1. DB access is mandatory.**
Direct tops out at 0.059. Models hallucinate POI names, output Vietnamese words for distances ("hai mươi mét"), refuse to answer count questions. text2sql lifts this to 0.342–0.343 — a 5–8× gain.

**2. Models are complementary.**
- Gemma-4-26B wins on spatial-reasoning types: `knn+distance`, `knn:direction+name`, `range:direction+name`
- Qwen3.5-9B wins on entity-matching types: `knn+name`, `range+name`, `range+count`
- Overall scores tied (0.343 vs 0.342)

**3. Location types unsolved (text F1 = 0.000).**
SQL execution partially correct (dist_err 0.13–0.16), but answer-generation LLM converts coordinates into prose addresses. Fix: extract coordinates directly from SQL result rows, skip LLM answer step for loc types.

**4. Scale doesn't help without DB.**
Qwen3.5-27B direct (0.059) ≈ Qwen3.5-9B direct (0.040). 3× larger model provides no uplift when DB is absent.

---

## Eval CSV Schema

Files in `baselines/`:

```
<model>_<baseline>_text_eval.csv   → id, attempted, P, R, F1, type
<model>_<baseline>_parsed_eval.csv → id, attempted, distance_error, relative_error, type
```
