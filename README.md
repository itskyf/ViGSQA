# ViGSQA — Vietnamese Geospatial Question Answering

[Tiếng Việt](README.vi.md)

ViGSQA is a Vietnamese adaptation of [GS-QA](https://arxiv.org/abs/2605.22811), a benchmark for question answering over geospatial data.
The project contributes VN-GeoQA, a dataset of 2,800 Vietnamese questions across all 28 GS-QA question types, together with evaluated baselines, an answer-recovery method, error analysis, and a Vietnamese demo.
The complete coursework can be reproduced on Google Colab CPU by opening the submitted `main.ipynb` and selecting **Run all**.

## Contributions

1. **Vietnamese dataset:** VN-GeoQA adapts the 28 GS-QA templates to Vietnamese and pairs each question with verified SQL and answers from an OpenStreetMap Vietnam database.
2. **Baseline evaluation:** four combinations of Ornith/Qwen and Direct/Text2SQL are compared on a fixed dev/test split using GS-QA's text and geospatial metrics.
3. **Records-to-answer improvement:** when Text2SQL returns useful database rows but fails to express an answer, the proposed rescue step converts those typed rows into an answer without another LLM call.
4. **Error analysis:** failures are analyzed by pipeline stage and by Vietnamese-specific effects such as address geocoding and diacritics.
5. **Vietnamese demo:** five new questions demonstrate database grounding, both baselines, and the rescue step.

## Course reproduction on Colab CPU

[Open `main.ipynb` in Google Colab](https://drive.google.com/file/d/1ae4NWZ9TkNKvpRsNFPpqiAacQHO8Ihr3/view?usp=sharing), select a CPU runtime, and choose **Runtime → Run all**.
The notebook installs the project and PostgreSQL/PostGIS, downloads the `v3.0.0` artifacts, and verifies their checksums.

No GPU, model download, API key, or LLM service is required.
The official LLM outputs were generated beforehand and are restored from the release artifacts and cache.
The notebook itself executes the SQL/PostGIS workflow, dataset exploration, test evaluation, baseline comparison, records-to-answer reconstruction, error analysis, and demo processing.

The notebook covers the course requirements in this order:

1. environment setup and artifact restoration;
2. dataset validation and exploratory analysis;
3. official baseline results and test-set comparison;
4. records-to-answer improvement on the dev/test split;
5. Vietnamese error analysis;
6. demo on new Vietnamese questions.

## Full pipeline on a GPU machine (optional)

The repository also contains the implementation used to create the dataset and run the models.
This path is separate from the Colab coursework reproduction and requires a GPU for vLLM.

The project uses [Pixi](https://pixi.prefix.dev/latest/installation/) as its package manager.
Install the dependencies, enter the environment, and configure PostgreSQL plus Hugging Face access:

```bash
pixi install
pixi shell
export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=osm_vn PGUSER=postgres PGPASSWORD=postgres HF_TOKEN=your_hugging_face_token
```

To regenerate questions in a staging directory and verify them:

```bash
./scripts/bootstrap_postgres.sh
python generator/generator_vi.py --seed 42 --count 100 --output data/rebuild/questions_vi
python generator/verify_vi.py --input data/rebuild/questions_vi --all
```

`generator/generator_vi.py` creates the Vietnamese questions and `generator/verify_vi.py` checks their structure and answer invariants.

`compose.yaml` defines PostgreSQL/PostGIS and the vLLM service.
Set `VLLM_MODEL` to one of the two Hugging Face model IDs, start that model, and run its Direct and Text2SQL baselines:

```bash
VLLM_MODEL=ornith-ai/Ornith-1.5-9B-NVFP4 podman compose up -d postgres vllm
MODELS=ornith-ai/Ornith-1.5-9B-NVFP4 ./scripts/inference.sh --llm-concurrency 4

VLLM_MODEL=AxionML/Qwen3.5-9B-NVFP4 podman compose up -d --force-recreate vllm
MODELS=AxionML/Qwen3.5-9B-NVFP4 ./scripts/inference.sh --llm-concurrency 4
```

vLLM serves one model at a time, while `scripts/inference.sh` coordinates the complete runs through `scripts/run_raw_inference.py`.
After both models finish, serve Ornith again and run the evaluation because Ornith is the fixed parser for all four runs:

```bash
VLLM_MODEL=ornith-ai/Ornith-1.5-9B-NVFP4 podman compose up -d --force-recreate vllm
./scripts/evaluate.sh --llm-concurrency 4
```

`scripts/evaluate.sh` coordinates `scripts/run_evaluation.py` and validates the completed evaluations.

## Dataset and release assets

VN-GeoQA `v3.0.0` contains 2,800 questions: 100 questions for each of the 28 GS-QA types, generated with seed 42.
Its reference data comes from `vietnam-260901.osm.pbf` (SHA-256 `edf2d41d93b25474acc14a34f6c313940ecfea5671835299ddd793c60d08a3e8`) and is provided as a ready-to-restore PostGIS dump.

Download the artifacts from the [ViGSQA v3.0.0 release](https://github.com/itskyf/ViGSQA/releases/tag/v3.0.0):

| Asset | Contents | SHA-256 |
|---|---|---|
| `vn-geoqa.zip` | Dataset JSONL files and manifest | `dfe0ae70260c52837eb2aa38272787fcb55d98ad02ca4fbf0c432084f9055740` |
| `osm-vn.dump` | PostgreSQL custom-format PostGIS database dump | `deb523cd943520f37b67b70b421a9f3d7a22283ee0fb33d856ffd6b9cb2844d0` |
| `evaluation-results.tar.gz` | Per-question results and evaluation seals for the four official runs | `bb10de26aa851dab1e24baf93dbf8d32d21ecad1205aabf32920074efd484b16` |
| `llm-cache-20260905.sql.gz` | PostgreSQL cache containing the official LLM outputs | `60d9e0f213c6bd8282dd00ceb16b3c428187f9b2791840c2e521b15c6c808830` |
| `rescue-inputs.tar.gz` | Inputs used to reconstruct the records-to-answer results | `56841ffaa4a0354a02fac9619254b5bf554d5a291049d075dde4ad9c42cc373f` |
| `demo-inputs.tar.gz` | Model outputs for 5 demo questions and 15 generation steps | `c538c9332410690b76330ea1659ce3960c17ebc20186319d6930c77ba7c5228b` |

The dataset is restored outside Git with `./scripts/restore_dataset.sh` and read through `generator/questions_vi`.
See [docs/data_generation.md](docs/data_generation.md) for its schema, generation process, and validation.

## Models and evaluation

The evaluated pretrained models are [Ornith-1.5-9B-NVFP4](https://huggingface.co/ornith-ai/Ornith-1.5-9B-NVFP4) and [Qwen3.5-9B-NVFP4](https://huggingface.co/AxionML/Qwen3.5-9B-NVFP4).
Each model was evaluated with Direct and Text2SQL prompting, producing four official runs.
ViGSQA does not fine-tune or publish model weights.

Evaluation follows the GS-QA answer families and reports text F1, capped relative error, geocoded location distance, and eight-sector direction scores where applicable.

### Parser difference from GS-QA

GS-QA selected Qwen 3.5 to convert free-text responses into structured JSON for evaluation.
ViGSQA uses Ornith as a single parser for all four runs so that the comparison uses the same parsing setup while retaining the GS-QA metrics.

## Repository guide

| Path | Purpose |
|---|---|
| `main.ipynb` | End-to-end Colab coursework notebook supplied with the submission |
| `generator/generator_vi.py` | Generate Vietnamese questions from PostGIS |
| `generator/verify_vi.py` | Verify generated questions and answers |
| `compose.yaml` | Define the PostgreSQL/PostGIS and vLLM services |
| `scripts/bootstrap_postgres.sh` | Prepare PostGIS and restore the reference database |
| `scripts/restore_dataset.sh` | Restore and verify VN-GeoQA `v3.0.0` |
| `scripts/restore_llm_cache.sh` | Restore the LLM-output cache |
| `scripts/run_raw_inference.py` / `scripts/inference.sh` | Run Direct and Text2SQL inference |
| `scripts/run_evaluation.py` / `scripts/evaluate.sh` | Parse and evaluate model answers |
| `scripts/records_to_answer.py` | Reconstruct the records-to-answer improvement |
| `scripts/error_taxonomy.py` | Generate the error analysis |
| `scripts/run_demo.py` | Process the Vietnamese demo |
| `docs/data_generation.md` | Describe dataset generation and validation |
