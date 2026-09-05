# ViGSQA — Vietnamese Geospatial Question Answering

**VN-GeoQA** is a Vietnamese-language geospatial QA benchmark built on OpenStreetMap Vietnam data, adapted from the upstream [GS-QA](https://github.com/MajidSas/GS-QA) benchmark. Everything below reproduces from the frozen `v3.0.0` GitHub Release; reproducing the published results needs **no GPU and no LLM endpoint**.

| | VN-GeoQA |
|--|--|
| Language | Vietnamese |
| Version | **v3.0.0 (frozen)** — MANIFEST inside the dataset asset |
| Questions | 2,800 (100 × 28 canonical question types), stable `{type}-NNN` ids |
| Source | Geofabrik `vietnam-260901.osm.pbf` (sha256 in MANIFEST) → PostGIS `osm_vn` |
| Baselines | Ornith/Qwen × Direct/Text2SQL over an external OpenAI-compatible vLLM endpoint (frozen decoding profile) |
| Evaluation | sealed per-question results and evaluation seals, published on the release |

**Full Vietnamese documentation: [README_VI.md](README_VI.md)**

## Frozen release assets (`v3.0.0`)

Every artifact is sha256-pinned; the notebook and the individual scripts verify each download.

| asset | contents | sha256 |
|---|---|---|
| `vn-geoqa.zip` | the 2,800-question dataset (28 JSONL files + MANIFEST) | `dfe0ae70260c52837eb2aa38272787fcb55d98ad02ca4fbf0c432084f9055740` |
| `osm-vn.sql.gz` | PostGIS reference database dump | `ae06f7c2ae7808235682371e03017a9da6ce6b323ec962cd06f99c0bb2ef53e6` |
| `evaluation-results.tar.gz` | sealed per-question results for all four official runs | `bb10de26aa851dab1e24baf93dbf8d32d21ecad1205aabf32920074efd484b16` |
| `llm-cache-20260905.sql.gz` | the published LLM cache (27,674 cached generations) | `60d9e0f213c6bd8282dd00ceb16b3c428187f9b2791840c2e521b15c6c808830` |
| `rescue-inputs.tar.gz` | sealed inputs of the records→answer rescue reconstruction | `56841ffaa4a0354a02fac9619254b5bf554d5a291049d075dde4ad9c42cc373f` |
| `demo-inputs.tar.gz` | published step records of the five demo generations | `c538c9332410690b76330ea1659ce3960c17ebc20186319d6930c77ba7c5228b` |

## Course notebook (`main.ipynb`)

Open `main.ipynb` in Google Colab on a **fresh CPU runtime** and Run All — no GPU, no LLM endpoint, no API keys. The notebook:

1. clones this repository, installs it with `uv`, and bootstraps PostgreSQL/PostGIS (Colab installs PostgreSQL 18 + PostGIS 3.6 from the PGDG apt repository; locally the pinned `compose.yaml` service is used);
2. restores the PostGIS reference database, the frozen dataset, the sealed evaluation artifacts, and the published LLM cache — each download sha256-verified;
3. profiles the dataset, computes the official baseline tables from the sealed per-question results, and compares runs under the frozen dev/test split;
4. reconstructs the records→answer rescue improvement live and asserts the recomputed tables equal the frozen record (zero LLM calls, zero geocoding requests — both asserted);
5. replays the five novel Vietnamese demo questions: questions, gold SQL, PostGIS execution, rescue, and presentation are rebuilt live, while every model generation replays from its published step record (the pipeline's resume layer) — a **cached replay of the original live inference, not new inference**;
6. presents the Vietnamese error analysis and interpretation.

Cache-only contract: no notebook step contacts an LLM server. `OPENAI_BASE_URL` points at a deliberately unreachable address, so an unexpected cache miss fails loudly instead of silently falling back to live inference.

The notebook lives in Google Drive/Colab and is intentionally not committed to this repository.

## Environment

- **Colab (recommended for the course run):** nothing to pre-install; the notebook installs the repository and the apt packages itself.
- **Local:** [pixi](https://pixi.sh) (`pixi install`) plus the `compose.yaml` PostgreSQL/PostGIS service (`podman compose up -d postgres`). PostGIS is required.

## Dataset

`data/questions_vi/` is deliberately outside version control. Restore it with `./scripts/restore_dataset.sh` (downloads `vn-geoqa.zip` from the release, sha256-verifies, idempotent) or regenerate byte-identically with the pinned seed:

```text
python generator/generator_vi.py --seed 42 --count 100
```

Read the dataset through the `generator/questions_vi` symlink; never commit anything under `data/`. Location questions store `geo_wkt` as the authoritative spatial gold alongside native OSM address components; range questions store the full distance-ordered answer set (GS-QA range semantics).

## Baselines and official evaluation

Four official runs — Ornith (`ornith-ai/Ornith-1.5-9B-NVFP4`) and Qwen (`AxionML/Qwen3.5-9B-NVFP4`) × Direct and Text2SQL — were produced against an external OpenAI-compatible vLLM endpoint under a frozen decoding profile. Raw generations are QID-indexed under a sealed cache namespace; sealed per-question results and evaluation seals are published as `evaluation-results.tar.gz`.

Inference and scoring CLIs (they only probe the endpoint; nothing starts a server):

```text
python scripts/run_raw_inference.py --model <model> --baseline direct|text2sql --mode smoke|full
./scripts/inference.sh      # official full runs
./scripts/evaluate.sh       # sealed evaluation of all runs
```

### LLM cache

All LangChain generations pass through a PostgreSQL cache database (`llm_cache`, created by `scripts/bootstrap_postgres.sh`). The cache key normalizes away the endpoint address, so a restored cache serves identical prompts on any machine. Restore the published cache with:

```text
./scripts/restore_llm_cache.sh llm-cache-20260905.sql.gz
```

## Records→answer rescue

`scripts/records_to_answer.py` implements the frozen `records-to-answer-rescue-v1` intervention: where the sealed Text2SQL run executed correct SQL with typed rows but then refused to answer, the typed value is emitted through the parser's fenced-JSON shape — only where the sealed run sits at the unattempted floor, so per-question scores can only improve or tie. The notebook reconstructs the published dev/test tables from the sealed artifacts and asserts they equal the frozen record (65/560 dev and 222/2,240 test questions improved, zero regressions on both splits).

## Demo

`scripts/run_demo.py` builds five novel Vietnamese questions (anchors asserted absent from all benchmark surfaces), grounds gold via read-only SQL, and answers through both baselines with the rescue applied to empty Text2SQL answers. On Colab the notebook runs it as a cached replay; with a live endpoint available it performs new inference.

## Optional live inference

New inference is **not** needed to reproduce any published result. To run it, serve one model at a time on any OpenAI-compatible vLLM server started with `--reasoning-parser qwen3` and point `OPENAI_BASE_URL`/`OPENAI_API_KEY` at it. The repository also ships an optional compose service (`VLLM_MODEL=… podman compose up -d vllm`, requires a GPU). One model per server.

## Paper deviation note

GS-QA converts free-text model answers into structured JSON with Qwen 3.5 chosen as the parsing model. ViGSQA intentionally fixes one parser (Ornith, under the same frozen decoding profile) for the structured-answer parsing of all four evaluated runs. This keeps the four arms comparable and the parser identity sealed, while preserving the paper's metric semantics (best-match text F1, capped relative error, geocoded location distance, 8-sector direction scoring). It is a Vietnamese evaluation adaptation, not an exact implementation reproduction of the upstream evaluation stack.

## Docs

- [docs/data_generation.md](docs/data_generation.md) — dataset pipeline, templates, output format
- [README_VI.md](README_VI.md) — full Vietnamese documentation
- [baselines/REPORT_VN_GEOQA.md](baselines/REPORT_VN_GEOQA.md), [docs/results.md](docs/results.md) — archived pre-freeze results
