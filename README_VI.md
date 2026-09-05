# VN-GeoQA — Bộ Dữ Liệu Hỏi Đáp Không Gian Địa Lý Tiếng Việt

Bộ dữ liệu gồm **2.800 câu hỏi tiếng Việt** về không gian địa lý (28 loại câu hỏi × 100), được tổng hợp tự động từ dữ liệu OpenStreetMap Việt Nam, đóng băng tại phiên bản **v3.0.0**. ViGSQA là bản thích ứng tiếng Việt của benchmark [GS-QA](https://github.com/MajidSas/GS-QA). Mọi kết quả đã công bố đều tái lập được từ GitHub Release `v3.0.0` — **không cần GPU, không cần endpoint LLM**.

**Tài liệu tiếng Anh: [README.md](README.md)**

---

## Asset Đóng Băng (`v3.0.0`)

Mọi asset được ghim SHA-256; notebook và từng script tự kiểm tra mỗi lượt tải.

| Asset | Nội dung | SHA-256 |
|---|---|---|
| `vn-geoqa.zip` | Bộ dữ liệu 2.800 câu hỏi (28 file JSONL + MANIFEST) | `dfe0ae70…5740` |
| `osm-vn.dump` | Dump database tham chiếu PostGIS (định dạng custom của pg_dump, restore song song) | `deb523cd…84d0` |
| `evaluation-results.tar.gz` | Kết quả theo từng câu (sealed) của cả bốn run chính thức | `bb10de26…84b16` |
| `llm-cache-20260905.sql.gz` | Cache LLM đã công bố (27.674 generation) | `60d9e0f2…8830` |
| `rescue-inputs.tar.gz` | Input sealed cho việc tái dựng records→answer rescue | `56841ffa…373f` |
| `demo-inputs.tar.gz` | Step record đã công bố của năm generation demo | `c538c93…c5228b` |

---

## Notebook Mon Học (`main.ipynb`)

Mở `main.ipynb` trong Google Colab trên **runtime CPU mới** và Run All — không GPU, không endpoint LLM, không API key. Notebook:

1. clone repository này, cài bằng `uv`, và bootstrap PostgreSQL/PostGIS (Colab cài PostgreSQL 18 + PostGIS 3.6 từ apt repository PGDG; local dùng service `compose.yaml`);
2. restore database tham chiếu PostGIS, bộ dữ liệu đóng băng, artifact đánh giá sealed, và cache LLM đã công bố — mỗi lượt tải đều kiểm tra SHA-256;
3. phân tích bộ dữ liệu, tính bảng baseline chính thức từ kết quả sealed theo từng câu, so sánh các run dưới split dev/test đóng băng;
4. tái dựng live cải tiến records→answer rescue và assert bảng tính lại bằng đúng kết quả đã đóng băng (0 lời gọi LLM, 0 yêu cầu geocoding — đều được assert);
5. replay năm câu hỏi demo tiếng Việt mới: câu hỏi, gold SQL, thực thi PostGIS, rescue và trình bày được dựng lại live, còn mọi generation của model replay từ step record đã công bố (resume layer của pipeline) — **cached replay của lần inference trực tiếp gốc, không phải inference mới**;
6. trình bày phân tích lỗi tiếng Việt và diễn giải.

Hợp đồng cache-only: không bước nào của notebook gọi tới server LLM. `OPENAI_BASE_URL` trỏ vào một địa chỉ cố tình không thể truy cập, nên cache miss bất ngờ sẽ fail thẳng thay vì âm thầm fallback sang inference trực tiếp.

Notebook nằm trong Google Drive/Colab và cố tình không được commit vào repository này.

---

## Môi Trường

- **Colab (khuyến nghị cho lần chạy môn học):** không cần cài trước gì; notebook tự cài repository và các gói apt.
- **Local:** [pixi](https://pixi.sh) (`pixi install`) + service PostgreSQL/PostGIS trong `compose.yaml` (`podman compose up -d postgres`). Bắt buộc có PostGIS.

---

## Bộ Dữ Liệu

`data/questions_vi/` cố tình nằm ngoài version control. Restore bằng `./scripts/restore_dataset.sh` (tải `vn-geoqa.zip` từ release, kiểm tra SHA-256, chạy lại vô hại) hoặc sinh lại byte-identical với seed đã pin:

```text
python generator/generator_vi.py --seed 42 --count 100
```

Đọc bộ dữ liệu qua symlink `generator/questions_vi`; không bao giờ commit gì dưới `data/`. Câu location lưu `geo_wkt` làm gold không gian chính thống kèm thành phần địa chỉ OSM gốc; câu range lưu **toàn bộ** tập đáp án sắp xếp theo khoảng cách (semantics GS-QA: nhiều đáp án đúng).

### Định Dạng Dữ Liệu

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

---

## Baseline và Đánh Giá Chính Thức

Bốn run chính thức — Ornith (`ornith-ai/Ornith-1.5-9B-NVFP4`) và Qwen (`AxionML/Qwen3.5-9B-NVFP4`) × Direct và Text2SQL — được chạy qua endpoint vLLM tương thích OpenAI bên ngoài với profile giải mã đóng băng. Generation thô được đánh chỉ mục theo QID trong namespace cache sealed; kết quả theo từng câu và evaluation seal được công bố trong `evaluation-results.tar.gz`.

CLI inference và chấm điểm (chỉ dò endpoint; không tự khởi động server):

```bash
# smoke: 28 câu (1/mỗi loại) — chỉ kiểm tra integration, không phải bằng chứng benchmark
python scripts/run_raw_inference.py --model ornith-ai/Ornith-1.5-9B-NVFP4 --baseline direct --mode smoke --llm-concurrency 4
python scripts/run_raw_inference.py --model ornith-ai/Ornith-1.5-9B-NVFP4 --baseline text2sql --mode smoke --llm-concurrency 4

# full: 2.800 câu
python scripts/run_raw_inference.py --model ornith-ai/Ornith-1.5-9B-NVFP4 --baseline text2sql --mode full --llm-concurrency 4
# Qwen: restart vLLM với VLLM_MODEL=AxionML/Qwen3.5-9B-NVFP4 rồi dùng id đó

./scripts/inference.sh --llm-concurrency 4    # các run chính thức, seal từng raw run
./scripts/evaluate.sh --llm-concurrency 4     # đánh giá sealed của cả bốn run
```

Ornith là parser cố định cho cả bốn run; model đang được đánh giá không bao giờ tự chọn parser. `evaluate.sh` tiếp tục từ evaluation JSON nếu bị gián đoạn và thoát ngay sau khi đủ bốn evaluation seal. SQL do model sinh luôn chạy trong transaction **read-only** kèm statement timeout.

### Biến Môi Trường

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `OPENAI_BASE_URL` | `http://127.0.0.1:8000/v1` | Địa chỉ endpoint vLLM tương thích OpenAI |
| `OPENAI_API_KEY` | `not-needed` (fallback) | API key/token của endpoint; server local không cần key |
| `PGHOST` / `PGPORT` | `127.0.0.1` / `5432` | Postgres (giống `scripts/*.sh`) |
| `PGDATABASE` | `osm_vn` | Database |
| `PGUSER` / `PGPASSWORD` | `postgres` / `postgres` | Chứng thực local |
| `LLM_CACHE_DBNAME` | `llm_cache` | Tên DB cache LLM (tách biệt DB OSM `osm_vn`) |

### Cache LLM (PostgreSQL)

LangChain cache (chuẩn hoá cache-key bỏ trường transport như `base_url`/api key) luôn bật cho pipeline, nằm trong DB `llm_cache` — cùng service Postgres nhưng tách biệt hoàn toàn với DB tham chiếu `osm_vn`. Vì cache-key không phụ thuộc endpoint, cache đã restore phục vụ cùng prompt trên bất kỳ máy nào:

```text
./scripts/restore_llm_cache.sh llm-cache-20260905.sql.gz
```

Hợp đồng cache-key: cùng model/quantization/tham số sinh/prompt tại endpoint khác nhau → cache hit; đổi model hoặc tham số sinh → miss.

---

## Records→Answer Rescue

`scripts/records_to_answer.py` hiện thực intervention đóng băng `records-to-answer-rescue-v1`: tại những câu mà run Text2SQL sealed đã thực thi SQL đúng với các hàng có kiểu nhưng từ chối trả lời, giá trị có kiểu được phát ra đúng fenced-JSON shape của parser — chỉ khi run sealed đang ở sàn unattempted, nên điểm theo câu chỉ có thể tăng hoặc giữ nguyên. Notebook tái dựng bảng dev/test đã công bố từ artifact sealed và assert bằng đúng kết quả đóng băng (65/560 câu dev và 222/2.240 câu test được cải thiện, 0 regression trên cả hai split).

---

## Demo

`scripts/run_demo.py` dựng năm câu hỏi tiếng Việt mới (anchor được assert không xuất hiện trong mọi bề mặt benchmark), gold qua SQL read-only, và trả lời qua cả hai baseline có áp rescue cho câu trả lời Text2SQL rỗng. Trên Colab notebook chạy nó như cached replay; khi có endpoint sống nó thực hiện inference mới.

---

## Inference Trực Tiếp (Tùy Chọn)

Inference mới **không** cần thiết để tái lập bất kỳ kết quả đã công bố nào. Muốn chạy: phục vụ từng model một trên server vLLM tương thích OpenAI khởi động với `--reasoning-parser qwen3` và trỏ `OPENAI_BASE_URL`/`OPENAI_API_KEY` tới nó. Repository cũng kèm compose service tùy chọn (`VLLM_MODEL=… podman compose up -d vllm`, cần GPU). Một model mỗi server.

---

## Lệch So Với Paper

GS-QA dùng Qwen 3.5 làm model parsing khi chuyển câu trả lời văn bản tự do thành JSON có cấu trúc. ViGSQA chủ động cố định **một** parser (Ornith, cùng profile giải mã đóng băng) cho bước parsing của cả bốn run. Cách này giữ bốn arm so sánh được và identity của parser nằm trong evaluation seal, trong khi bảo toàn semantics metric của paper (best-match text F1, relative error có chặn, location distance qua geocoding, chấm hướng theo 8 cung). Đây là thích ứng cho đánh giá tiếng Việt, không phải tái hiện chính xác toàn bộ evaluation stack upstream.

---

## Cấu Trúc Thư Mục

```text
ViGSQA/
├── main.ipynb                          # Notebook end-to-end (Colab + local), không commit
├── compose.yaml                        # PostGIS + vLLM (NVFP4, tùy chọn local)
├── scripts/
│   ├── bootstrap_postgres.sh           # Orchestrator: cài → start → init → restore → validate
│   ├── restore_dataset.sh              # Tải bộ dữ liệu từ GitHub Release (v3.0.0)
│   ├── restore_database.sh             # Tải dump PostGIS từ release (ghim SHA-256)
│   ├── restore_llm_cache.sh            # Restore DB cache LLM từ dump
│   ├── run_raw_inference.py            # Inference raw (smoke/full) qua endpoint ngoài
│   ├── inference.sh / evaluate.sh      # Run chính thức / đánh giá sealed
│   ├── records_to_answer.py            # Workflow records-to-answer-rescue-v1
│   ├── run_demo.py                     # Năm câu demo tiếng Việt mới
│   └── error_taxonomy.py               # Phân loại lỗi tiếng Việt
├── generator/
│   ├── generator_vi.py                 # Sinh câu hỏi tiếng Việt từ DB
│   ├── verify_vi.py                    # Kiểm tra chất lượng câu hỏi
│   ├── templates_vi/                   # Template câu hỏi tiếng Việt
│   └── questions_vi -> ../data/questions_vi   # symlink
└── baselines/
    ├── baselines_vi.py                 # Model client + cache LLM PostgreSQL
    ├── baseline_prompts/               # Prompt tiếng Việt (direct + text2sql)
    └── REPORT_VN_GEOQA.md              # (lưu trữ — trước khi freeze)
```

---

## Kết Quả Thực Nghiệm

Kết quả chính thức được công bố trong `evaluation-results.tar.gz` trên release `v3.0.0` và trình bày trong notebook (§3–§8). Các báo cáo cũ ([`baselines/REPORT_VN_GEOQA.md`](baselines/REPORT_VN_GEOQA.md), [docs/results.md](docs/results.md)) là kết quả trước khi freeze — không phải bằng chứng benchmark.
