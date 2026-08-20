# VN-GeoQA — Bộ Dữ Liệu Hỏi Đáp Không Gian Địa Lý Tiếng Việt

Bộ dữ liệu gồm **800 câu hỏi tiếng Việt** về không gian địa lý (KNN và range query), được tổng hợp tự động từ dữ liệu OpenStreetMap Việt Nam.

---

## Cấu Trúc Thư Mục

```
GS-QA/
├── setup_vn.sh                        # Cài đặt PostgreSQL/PostGIS + nạp dữ liệu OSM
├── generator/
│   ├── generator_vi.py                # Sinh câu hỏi tiếng Việt từ DB
│   ├── verify_vi.py                   # Kiểm tra chất lượng câu hỏi sinh ra
│   ├── templates_vi/                  # Template câu hỏi tiếng Việt (8 loại)
│   └── questions_vi/                  # Bộ dữ liệu 800 câu (*.jsonl, 100/loại)
└── baselines/
    ├── baselines_vi.py                # Chạy baseline trên VN-GeoQA
    ├── baseline_prompts/              # Prompt tiếng Việt cho text2sql
    ├── REPORT_VN_GEOQA.md             # Báo cáo kết quả thực nghiệm
    └── *_eval.csv                     # Kết quả đánh giá từng model
```

---

## Yêu Cầu Hệ Thống

- Python ≥ 3.10
- PostgreSQL ≥ 14 + PostGIS ≥ 3.3
- osm2pgsql
- (tùy chọn) Ollama ≥ 0.32 hoặc llama.cpp để chạy model local

---

## 1. Cài Đặt Python

```bash
pip install -r baselines/requirements.txt
```

---

## 2. Cài Đặt Cơ Sở Dữ Liệu

Script `setup_vn.sh` tự động:
1. Cài PostgreSQL + PostGIS + osm2pgsql
2. Tạo database `osm_vn`
3. Tải dữ liệu OSM Việt Nam từ Geofabrik (~100 MB)
4. Nạp vào PostGIS và tạo các view `pois`, `roads`, `parks`, `lakes`

```bash
bash setup_vn.sh
```

Kiểm tra kết nối sau khi cài xong:
```bash
psql -U postgres -d osm_vn -c "SELECT COUNT(*) FROM pois;"
```

---

## 3. Sinh Câu Hỏi

> Bộ dữ liệu 800 câu đã có sẵn trong `generator/questions_vi/` — bước này chỉ cần thiết nếu muốn sinh lại từ đầu.

```bash
cd generator
python generator_vi.py --output questions_vi/ --count 100
```

Kiểm tra chất lượng:
```bash
python verify_vi.py --input questions_vi/ --spot-check 0.05
```

### Định Dạng Dữ Liệu

Mỗi file `.jsonl` tương ứng một loại câu hỏi. Mỗi dòng là một JSON object:

```json
{
  "question": "Bể bơi gần [POI] nhất là gì?",
  "type": "knn+name",
  "sql": "SELECT poi_name FROM pois ORDER BY geometry <-> (SELECT geometry FROM pois WHERE poi_name ILIKE '%[POI]%') LIMIT 1",
  "answers": [{"poi_name": "[TÊN KẾT QUẢ]", "geo_wkt": "POINT(105.xx 21.xx)"}],
  "answer_type": "name",
  "question_entities": ["[POI]"]
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

---

## 4. Chạy Baseline

### Cài Đặt Model

**Tùy chọn A — Ollama (khuyến nghị):**
```bash
# Cài Ollama >= 0.32
curl -fsSL https://ollama.com/install.sh | bash
ollama pull qwen2.5:7b    # hoặc model khác
ollama serve
```

**Tùy chọn B — llama.cpp server:**
```bash
docker run -p 8080:8080 --gpus all ghcr.io/ggml-org/llama.cpp:server-cuda \
  -m /path/to/model.gguf --port 8080 -ngl 40
```

### Chạy Baseline

```bash
cd baselines

# Baseline direct (model trả lời từ kiến thức sẵn có, không truy vấn DB)
python baselines_vi.py --model ollama:qwen2.5:7b --baseline direct

# Baseline text2sql (model sinh SQL → thực thi → model trả lời từ kết quả)
python baselines_vi.py --model ollama:qwen2.5:7b --baseline text2sql

# Chạy cả hai
python baselines_vi.py --model ollama:qwen2.5:7b --baseline all
```

Thay `ollama:qwen2.5:7b` bằng tên model đang chạy. Dùng `llamacpp:<tag>` cho llama.cpp server.

Kết quả được lưu tại:
- `baselines/<model>_<baseline>_text_eval.csv`
- `baselines/<model>_<baseline>_parsed_eval.csv`

### Biến Môi Trường

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `OLLAMA_URL` | `http://localhost:11434` | Địa chỉ Ollama server |
| `LLAMACPP_URL` | `http://localhost:8080` | Địa chỉ llama.cpp server |
| `OLLAMA_NOTHINK` | `1` | Tắt chain-of-thought (Qwen3/Qwen3.5) |
| `LLAMACPP_NOTHINK` | `1` | Tắt chain-of-thought |

---

## 5. Kết Quả Thực Nghiệm

Xem báo cáo đầy đủ: [`baselines/REPORT_VN_GEOQA.md`](baselines/REPORT_VN_GEOQA.md)

### Tóm Tắt (text F1, 800 câu)

| Model | Baseline | text F1 |
|-------|----------|:-------:|
| Gemma-4-26B | direct | 0.058 |
| Gemma-4-26B | **text2sql** | **0.343** |
| Qwen3.5-9B | direct | 0.040 |
| Qwen3.5-9B | **text2sql** | **0.342** |
| Qwen3.5-27B | direct | 0.059 |

Baseline text2sql cải thiện **5–8× so với direct** — model không có kiến thức về POI địa phương Việt Nam, cần truy vấn cơ sở dữ liệu để trả lời chính xác.
