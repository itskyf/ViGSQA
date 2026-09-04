# VN-GeoQA — Bộ Dữ Liệu Hỏi Đáp Không Gian Địa Lý Tiếng Việt

Bộ dữ liệu gồm **2.800 câu hỏi tiếng Việt** về không gian địa lý (28 loại câu hỏi × 100), được tổng hợp tự động từ dữ liệu OpenStreetMap Việt Nam, đóng băng tại phiên bản **v3.0.0**.

**Tài liệu tiếng Anh: [README.md](README.md)**

---

## Cấu Trúc Thư Mục

```text
ViGSQA/
├── main.ipynb                          # Notebook end-to-end (local + Colab)
├── compose.yaml                        # PostGIS + vLLM (NVFP4, tùy chọn local)
├── scripts/
│   ├── install_dependencies.sh         # Cài công cụ (Colab: apt; local: pixi)
│   ├── init_database.sh                # Tạo database osm_vn + PostGIS
│   ├── download_osm.sh                 # Tải PBF snapshot OSM đã pin (vietnam-260901)
│   ├── import_osm.sh                   # osm2pgsql flex → view pois
│   └── restore_dataset.sh              # Tải bộ dữ liệu từ GitHub Release (data-v3.0.0)
├── generator/
│   ├── generator_vi.py                 # Sinh câu hỏi tiếng Việt từ DB
│   ├── verify_vi.py                    # Kiểm tra chất lượng câu hỏi
│   ├── templates_vi/                   # Template câu hỏi tiếng Việt (8 loại)
│   └── questions_vi -> ../data/questions_vi   # symlink
└── baselines/
    ├── baselines_vi.py                 # Chạy baseline trên VN-GeoQA
    ├── baseline_prompts/               # Prompt tiếng Việt (direct + text2sql)
    ├── REPORT_VN_GEOQA.md              # (lưu trữ — trước khi freeze)
    └── *_eval.csv                      # Kết quả đánh giá từng model
```

---

## Yêu Cầu Hệ Thống

- Pixi (local) hoặc Google Colab
- Docker/Podman (local) — hoặc PostgreSQL + PostGIS do notebook cài bằng apt trên Colab
- GPU cho vLLM (model NVFP4 ~6 GB + KV cache)

---

## 1. Khởi Động Nhanh

Mở và chạy `main.ipynb` trong môi trường notebook local hoặc Google Colab.

Notebook chạy nhánh bootstrap PostgreSQL/PostGIS rồi đợi hoàn tất trước khi bắt đầu phần coursework. Endpoint LLM là server vLLM tương thích OpenAI chạy bên ngoài, notebook không tự khởi động: trỏ `OPENAI_BASE_URL` (mặc định `http://127.0.0.1:8000/v1`) và `OPENAI_API_KEY` tới nó, hoặc khởi động service local tùy chọn bằng `podman compose up -d vllm`. Cài dependency, khởi động/chờ service, khởi tạo database và import snapshot OSM đã pin là các bước riêng, chạy lại an toàn. Các kiểm tra sau bootstrap và truy vấn notebook dùng psycopg3.

**Lưu ý:** bộ dữ liệu nằm ngoài git (`data/` bị gitignore). Sau khi clone repo, symlink `generator/questions_vi` sẽ treo cho tới khi chạy `scripts/restore_dataset.sh` (script có sha256 kiểm tra, chạy lại vô hại). Muốn sinh lại từ đầu: xem [docs/plans/T01-dataset-quality.md](docs/plans/T01-dataset-quality.md).

---

## 2. Chạy Baseline

Inference chính thức đi qua endpoint vLLM tương thích OpenAI chạy bên ngoài (một model mỗi server), client là `langchain-openai.ChatOpenAI` với profile giải mã đóng băng trong `baselines_vi.build_model_vi` (không dùng Ollama, không tự dựng chat template, thinking bật mặc định).

```bash
# chạy từ thư mục gốc repo
# smoke: 28 câu (1/TID) — chỉ để kiểm tra integration, không phải bằng chứng benchmark
python scripts/run_raw_inference.py --model ornith-ai/Ornith-1.5-9B-NVFP4 --baseline direct --mode smoke --llm-concurrency 4
python scripts/run_raw_inference.py --model ornith-ai/Ornith-1.5-9B-NVFP4 --baseline text2sql --mode smoke --llm-concurrency 4

# full: 2.800 câu — số liệu chính thức thuộc T03
python scripts/run_raw_inference.py --model ornith-ai/Ornith-1.5-9B-NVFP4 --baseline text2sql --mode full --llm-concurrency 4
# Qwen: restart vLLM với VLLM_MODEL=AxionML/Qwen3.5-9B-NVFP4 rồi dùng id đó
```

`scripts/run_official.sh --llm-concurrency 4` chạy và đóng dấu từng raw run.
Sau khi raw seal hợp lệ, đánh giá độc lập bằng:

```bash
python scripts/run_evaluation.py --model ornith-ai/Ornith-1.5-9B-NVFP4 --baseline direct --llm-concurrency 4
python scripts/check_run_seal.py ornith-ai/Ornith-1.5-9B-NVFP4 direct --evaluation
```

Raw artifacts/seal nằm trong `baselines/cache_vi/pv-26b1ac0d/`; parse, geocode,
metric theo câu và evaluation seal nằm trong `results/evaluation/<model>/<baseline>/`.

### Biến Môi Trường

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `OPENAI_BASE_URL` | `http://127.0.0.1:8000/v1` | Địa chỉ endpoint vLLM tương thích OpenAI |
| `OPENAI_API_KEY` | `not-needed` (fallback) | API key/token của endpoint; server local không cần key |
| `PGHOST` / `PGPORT` | `127.0.0.1` / `5432` | Postgres (giống `scripts/*.sh`) |
| `PGDATABASE` | `osm_vn` | Database |
| `PGUSER` / `PGPASSWORD` | `postgres` / `postgres` | Chứng thực local |
| `LLM_CACHE_DBNAME` | `llm_cache` | Tên DB cache LLM (tách biệt DB OSM `osm_vn`) |

Cờ `--llm-concurrency N` (bắt buộc) giới hạn số lời gọi LLM đồng thời phía client; đặt theo throughput của server vLLM. `scripts/run_official.sh` chỉ dò endpoint (curl `${OPENAI_BASE_URL}/models`), không tự khởi động server — muốn đổi model đang phục vụ, restart vLLM với `VLLM_MODEL=<id>`.

SQL do model sinh luôn chạy trong transaction **read-only** kèm statement timeout.

### Cache LLM (PostgreSQL)

LangChain cache (`SQLAlchemyMd5Cache` chuẩn hoá bỏ trường transport như `base_url`/api key) luôn bật cho pipeline, nằm trong DB `llm_cache` — cùng service Postgres nhưng tách biệt hoàn toàn với DB tham chiếu `osm_vn`, nên restore/xoá cache không bao giờ ảnh hưởng dữ liệu OSM. Hai luồng restore độc lập:

- **OSM**: `scripts/bootstrap_postgres.sh` (dump release `osm-vn.sql.gz` của tag `data-v3.0.0`, ghim SHA-256).
- **LLM cache**: `scripts/export_llm_cache.sh` → `scripts/restore_llm_cache.sh <dump>`.

Hợp đồng cache-key: cùng một yêu cầu model (model/quantization/tham số sinh/prompt giữ nguyên) tại endpoint khác nhau → cache hit; đổi model hoặc tham số sinh → miss. File JSON step (`cache_vi/…`) vẫn là artifact ghi-đầy-đủ; chi tiết trong `docs/plans/T09-llm-cache-postgres.md`.

---

## 3. Định Dạng Dữ Liệu

Mỗi file `.jsonl` tương ứng một loại câu hỏi. Mỗi dòng là một JSON object:

```json
{
  "id": "knn+name-001",
  "question": "cơ sở tôn giáo nào gần vị trí Cafe Rex nhất?",
  "question_surfaces": {"full": "…", "stripped": "co so ton giao nao …"},
  "sql": "SELECT poi_name FROM pois …",
  "answers": [{"poi_name": "…", "geo_wkt": "POINT(105.xx 10.xx)"}],
  "answer_type": "name",
  "question_entities": ["Cafe Rex"]
}
```

### Các Loại Câu Hỏi

| Loại | Mô tả | Số câu |
|------|-------|:------:|
| `knn+name` | Tên POI gần nhất | 100 |
| `knn+loc` | Tọa độ POI gần nhất | 100 |
| `knn+distance` | Khoảng cách đến POI gần nhất | 100 |
| `knn:direction+name` | Tên POI gần nhất theo hướng chỉ định | 100 |
| `range+name` | Tên POI trong bán kính | 100 |
| `range+loc` | Tọa độ POI trong bán kính | 100 |
| `range+count` | Số lượng POI trong bán kính | 100 |
| `range:direction+name` | Tên POI trong bán kính theo hướng | 100 |

Câu range lưu **toàn bộ** tập đáp án sắp xếp theo khoảng cách (semantics GS-QA: nhiều đáp án đúng).

---

## 4. Kết Quả Thực Nghiệm

Các báo cáo hiện có ([`baselines/REPORT_VN_GEOQA.md`](baselines/REPORT_VN_GEOQA.md), [docs/results.md](docs/results.md)) là **kết quả trước khi freeze** — không phải bằng chứng benchmark. Kết quả chính thức sẽ được tổng hợp ở T03.
