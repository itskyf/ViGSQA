# Kết luận

**Chưa đầy đủ.** Repo `itskyf/ViGSQA` hiện đã có một nền tảng khá tốt cho **II.1 – dữ liệu tiếng Việt** và đã có code + kết quả thử nghiệm Direct/Text2SQL, nhưng **chưa đạt trạng thái bài nộp cuối kỳ** vì ba khoảng trống lớn:

1. **Dataset chưa được quality-control đủ chặt trước khi coi 800 câu là benchmark chính thức.**
2. **Notebook theo rubric gần như chưa có** — notebook của bạn hiện mới làm OSM → PostGIS, và trong `main` mình cũng không tìm thấy `.ipynb` được commit.
3. **Report chưa đạt yêu cầu ACL Short Paper**; Markdown report hiện tại còn stale so với `docs/results.md`.

Quan trọng hơn, **không cần reproduce toàn bộ 28 template/2,800 câu của GS-QA**. Với Q&A của thầy, 8 loại câu/800 câu của VN-GeoQA là một scope hoàn toàn hợp lý nếu nhóm chứng minh được: dữ liệu đúng, pipeline chạy được, baseline hợp lý, có cải tiến/phân tích, và notebook reproducible.

Paper gốc xây reference DB từ OSM trong PostGIS, dùng SQL để tạo ground truth xác định; 28 template chỉ là tập kết hợp được lựa chọn từ các spatial predicate/output type, chứ bản chất contribution nằm ở **grounded generation + evaluation**. ([arXiv][1])

---

## 1. Audit theo đúng rubric

| Yêu cầu                              | Repo hiện tại                                                                                   | Đánh giá                           | Cần làm thêm                                                                                              |
| ------------------------------------ | ----------------------------------------------------------------------------------------------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **II.1 Ngữ liệu & tiếng Việt – 2đ**  | Có `questions_vi`, 8 type × 100 = 800 câu, OSM Việt Nam, câu hỏi tiếng Việt, SQL + ground truth | 🟡 **Gần đạt nhưng chưa nên chốt** | QC dữ liệu, sửa lỗi generator, thống kê, split, manual validation, provenance                             |
| **II.2 Notebook & thực nghiệm – 4đ** | Có code Direct/Text2SQL và bảng kết quả, nhưng notebook của bạn mới import OSM→PostGIS          | 🔴 **Chưa đạt**                    | Notebook end-to-end: EDA → generate/load QA → model → evaluation → comparison → error analysis → demo     |
| **II.3 ACL Short Paper – 4đ**        | Có `REPORT_VN_GEOQA.md`, `docs/results.md`                                                      | 🔴 **Chưa đạt**                    | Viết 4–5 trang bằng ACL official LaTeX, cập nhật kết quả mới, methodology, experiments, error/limitations |
| **II.4 Sản phẩm nộp**                | Source + data có; README có nền tảng                                                            | 🟡 **Chưa đủ package**             | `.ipynb`, ACL PDF, final README, raw experimental outputs, model links/config                             |

---

## 2. II.1 — Dữ liệu tiếng Việt: giữ 800 câu, nhưng phải “freeze” lại benchmark

### Những gì repo đã làm đúng

`docs/results.md` hiện ghi rõ **800 câu tiếng Việt, 8 loại × 100**, trên PostGIS OSM Việt Nam. Các file `generator/questions_vi/*.jsonl` thực sự chứa câu Việt Nam, tọa độ Việt Nam, câu hỏi, SQL, answer type và ground truth.

Đây là hướng rất phù hợp GS-QA vì paper cũng xây câu hỏi sao cho SQL trên reference database xác định đáp án ground truth một cách deterministic. ([arXiv][1])

Bạn **không cần dịch 2,800 câu tiếng Anh của GS-QA** nữa. Dataset Việt Nam tự sinh từ OSM Việt Nam có giá trị hơn về mặt đồ án.

### Nhưng hiện có lỗi chất lượng phải sửa trước khi chạy final experiment

Ví dụ mình đọc trực tiếp thấy câu:

> “Gợi ý quán ăn nhanh nào cách Pizza!! trong khoảng 2 km.”

SQL `range+name` lại trả chính `"Pizza!!"` làm đáp án vì anchor không bị loại khỏi candidate set.

Đây là lỗi benchmark thực sự: model có thể “đúng” theo SQL nhưng câu hỏi không còn đúng ý nghĩa người dùng.

Ngoài ra có những case cần sanity check như khoảng cách nearest rất lớn và OSM tag có thể không khớp trực giác con người. Ví dụ dataset có câu nearest convenience store cách anchor hơn 80 km. Paper gốc cũng nhận ra OSM crowdsourced có dữ liệu thiếu/sai và vì vậy lọc các record nổi bật rồi **manual review khoảng 10% câu mỗi template**. ([arXiv][1])

#### Việc cần làm trước khi coi `questions_vi` là dataset cuối

| Task                      | Cần làm                                                                    | Done khi                                         |
| ------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------ |
| **Self-anchor filtering** | Với range/KNN, thêm `id <> anchor_id` khi anchor có thể cùng category      | Anchor không bao giờ là answer của chính câu hỏi |
| **Determinism**           | Các query có `LIMIT` nên có `ORDER BY` rõ ràng                             | Chạy lại DB cho cùng answer                      |
| **Sanity distance**       | Loại/regenerate nearest quá xa nếu tạo câu phi tự nhiên                    | Có rule được ghi trong report                    |
| **OSM semantic sanity**   | Kiểm tra tag/category và tên POI bất thường                                | Invalid examples được loại                       |
| **Unique IDs**            | Mỗi QA có top-level ID ổn định; sample mình đọc chưa thấy ID ở JSON        | Có dạng `vi_knn_distance_0001`                   |
| **Snapshot/version**      | Ghi URL Geofabrik + ngày snapshot OSM                                      | Dataset reproduce được                           |
| **Seed**                  | Fixed random seed cho generator/select                                     | Sinh lại cùng subset                             |
| **Manual QC**             | Review ít nhất **80/800 = 10%**, tốt nhất 10/type                          | Có bảng validity                                 |
| **Dataset statistics**    | Type, answer type, POI category, distance distribution, question length... | Có bảng/figure trong notebook                    |
| **Freeze dataset**        | Sau QC tạo `v1.0`                                                          | Experiment không tiếp tục thay dataset           |

#### Manual QC nên đánh giá 4 tiêu chí

Mỗi câu được đánh `0/1` cho:

* tiếng Việt có tự nhiên không;
* câu hỏi có rõ nghĩa/không ambiguous không;
* entity/category có hợp lý không;
* SQL ground truth có thực sự trả lời đúng câu hỏi không.

Nếu nhóm có 2 thành viên, rất nên cho cả hai cùng review khoảng 30–50 câu giao nhau và báo **agreement**. Đây là một chi tiết nhỏ nhưng làm phần “20% tiếng Việt” thuyết phục hơn rất nhiều.

---

## 3. Split dataset như thế nào?

Vì GS-QA là benchmark evaluation chứ không phải bài fine-tuning, bạn **không bắt buộc train model**. Paper cũng nói generator có thể tạo training data nhưng bản thân nghiên cứu tập trung vào evaluation. ([arXiv][1])

Tuy nhiên bạn sẽ chỉnh prompt/Text2SQL, nên không nên chỉnh trên toàn bộ 800 rồi lại đánh giá chính 800 đó.

Mình khuyên:

| Split |        Số câu | Mục đích                                    |
| ----- | ------------: | ------------------------------------------- |
| Dev   | 160 = 20/type | sửa prompt, debug SQL/parser                |
| Test  | 640 = 80/type | **chỉ chạy final sau khi method đã freeze** |

Stratified theo 8 question types, fixed seed.

Nếu muốn giữ đúng 800 làm test benchmark, có thể generate thêm một dev set riêng. Cách đó thậm chí đẹp hơn.

---

## 4. II.2 — Notebook là gap lớn nhất

Theo rubric, notebook không chỉ là “có code chạy được”.

Notebook hiện tại của bạn:

> OSM `.pbf` → PostgreSQL/PostGIS

mới hoàn thành phần **setup + load reference data**.

Bạn còn thiếu gần như toàn bộ nửa sau của assignment.

### Notebook final mình khuyên tổ chức thành pipeline này

#### Part A — Environment & reference database

##### 1. Environment setup

Cần thể hiện:

* phiên bản Python;
* PostgreSQL/PostGIS;
* dependencies pinned;
* GPU info;
* model/backend;
* random seed;
* secrets lấy từ environment/Colab Secrets, không hard-code;
* không có path từ máy cá nhân.

##### 2. Download/import OSM

Giữ notebook hiện tại của bạn.

Output tối thiểu:

* snapshot/source URL;
* file size;
* số node/way hoặc số record import;
* PostGIS version;
* bbox Việt Nam;
* số POI có tên.

##### 3. Validate reference DB

Chạy vài query:

* count records;
* geometry validity;
* category distribution;
* sample nearest-neighbor;
* sample range query.

Mục tiêu là chứng minh **database dùng để tạo ground truth thật sự hoạt động**, không chỉ “import successful”.

---

#### Part B — Vietnamese dataset

##### 4. Generate hoặc load VN-GeoQA

Notebook nên có lựa chọn:

```text
USE_PREGENERATED_DATASET = True
```

để giảng viên không phải generate 800 câu mỗi lần.

Nhưng cũng có cell cho thấy cách generate từ DB.

Hiển thị schema:

```text
id
question
question_surfaces.full
question_surfaces.stripped
type
answer_type
sql
answers
question_entities
```

##### 5. EDA + quality checks

Đây là phần notebook hiện đang thiếu nhưng rubric ghi rõ “Khám phá và tiền xử lý dữ liệu”.

Ít nhất cần có:

* number of QA;
* distribution 8 types;
* example 1–2 câu/type;
* answer-type distribution;
* question length;
* POI category distribution;
* duplicated questions/entities;
* empty answers;
* absurd distance/outlier;
* anchor-in-answer check;
* manual QC results.

Không cần biến EDA thành một data-science project; 3–5 bảng/figure có ý nghĩa là đủ.

---

## 5. Model/pipeline nào nên chạy?

Đây là phần mình nghĩ nên **đơn giản hóa so với repo hiện tại**.

`docs/results.md` đang có 4 model lớn:

* Gemma-4-26B
* Qwen3.5-9B
* Qwen3.5-27B
* Qwen3.6-27B

và được chạy trên **2 × RTX 3060 12 GB**.

Những kết quả này rất tốt để đưa vào extended experiments, nhưng **không nên bắt notebook Colab phụ thuộc vào 26–27B model**.

Rubric cần một notebook runnable; không yêu cầu toàn bộ bảng paper phải reproduce trên free Colab.

### Thiết kế thực nghiệm mình khuyên chốt

#### System A — Direct LLM

Cùng một model nhận câu tiếng Việt và trả lời trực tiếp.

Đây là baseline tối thiểu.

Dùng **một model 7–9B chạy 4-bit** trong notebook, ví dụ một Qwen instruct model mà stack của bạn hỗ trợ ổn định.

Không cần notebook chạy cả bốn model 26–27B.

#### System B — Text2SQL

```text
Vietnamese question
       ↓
LLM generates PostGIS SQL
       ↓
SQL validator
       ↓
PostGIS
       ↓
SQL result
       ↓
LLM formats answer
```

Đây là baseline quan trọng nhất vì nó bám sát GS-QA. Paper cũng so sánh ba hướng chính: Bare LLM, Text2SQL và dense RAG. ([arXiv][1])

Kết quả hiện tại của repo đã cho tín hiệu rất rõ:

* Direct khoảng `0.040–0.059` F1;
* Text2SQL khoảng `0.342–0.386`.

---

## 6. Nên có một “cải tiến của nhóm”: đừng chạy RAG ngay

Mình **không khuyên ưu tiên thêm vanilla dense RAG**.

Paper gốc đã phát hiện Text2SQL cải thiện đáng kể nhiều template, trong khi dense-retrieval RAG thường kém vì embedding không thể hiện thông tin vị trí tốt; tác giả cũng chỉ ra cần retrieval method có ý thức geospatial tốt hơn. ([arXiv][1])

Trong khi repo của bạn đã có một limitation rất rõ:

> `knn+loc` và `range+loc`: text F1 = **0.000** dù SQL có thông tin vị trí tương đối đúng.

Đây là cơ hội làm contribution vừa hợp lý vừa ít công.

### System C — Text2SQL + Typed/Deterministic Answer Renderer

Thay vì:

```text
SQL result → LLM → final answer
```

hãy làm:

```text
SQL result
   ↓
answer_type
   ├─ name     → normalized entity names
   ├─ location → lat/lon trực tiếp
   ├─ distance → numeric formatter + unit
   └─ count    → integer
```

Tức là LLM vẫn làm **Text2SQL**, nhưng dữ liệu đã có cấu trúc thì không cho LLM “viết lại” rồi làm mất cấu trúc.

#### Đây là experiment rất đẹp cho đồ án

| System                               | Direct |  DB | Deterministic output |
| ------------------------------------ | :----: | :-: | :------------------: |
| Direct                               |    ✓   |  ✗  |           ✗          |
| Text2SQL                             |    ✓   |  ✓  |           ✗          |
| **Text2SQL + Typed Renderer (ours)** |    ✓   |  ✓  |           ✓          |

Research question của report có thể là:

> **Database grounding và type-aware answer rendering cải thiện GeoQA tiếng Việt đến mức nào?**

Câu chuyện nghiên cứu rõ hơn hẳn việc chỉ “chạy thêm 4 model”.

---

## 7. Thêm một experiment tiếng Việt rất rẻ nhưng giá trị

Dataset đã chứa:

```text
question_surfaces.full
question_surfaces.stripped
```

Ví dụ câu có dấu và phiên bản bỏ dấu.

Hãy tận dụng nó.

### Vietnamese robustness ablation

Chọn **một model** và so:

| Input           | Ví dụ                           |
| --------------- | ------------------------------- |
| Full Vietnamese | `Cách Sân vận động ... bao xa?` |
| No-diacritics   | `Cach San van dong ... bao xa?` |

Chạy Direct hoặc Text2SQL trên cả hai.

Bạn sẽ có một experiment thực sự liên quan NLP tiếng Việt:

> Dấu tiếng Việt ảnh hưởng đến entity recognition/Text2SQL GeoQA như thế nào?

Không cần dịch sang English, không cần model mới, không cần training.

Nếu thời gian ít, đây là experiment phụ mình ưu tiên hơn việc thêm model thứ 5.

---

## 8. Evaluation hiện tại cần chỉnh

Đây là một điểm cần đặc biệt chú ý khi viết paper.

Paper GS-QA nhấn mạnh rằng không thể đánh giá mọi spatial output chỉ bằng string matching. Entity, location, direction và numeric output có bản chất khác nhau. ([arXiv][1])

Do đó **không nên dùng `overall text F1` làm kết luận duy nhất**.

Với **8 loại hiện tại** của ViGSQA, nên dùng:

| Type hiện tại          | Primary metric                                 |
| ---------------------- | ---------------------------------------------- |
| `knn+name`             | normalized Exact Match + token F1              |
| `range+name`           | **set Precision/Recall/F1** nếu nhiều answer   |
| `knn:direction+name`   | name EM/F1                                     |
| `range:direction+name` | set/name F1                                    |
| `knn+loc`              | geodesic distance error                        |
| `range+loc`            | geodesic distance error / nearest valid answer |
| `knn+distance`         | relative numeric error                         |
| `range+count`          | exact count accuracy + relative error          |

Lưu ý: hai `direction+name` của bạn **trả entity name**, không trả angle, nên không cần bê nguyên Angle Error từ paper.

Ngoài final-answer metric, Text2SQL nên báo thêm:

* `% valid SQL`;
* `% executable SQL`;
* `% correct execution result`;
* `% timeout`;
* SQL error taxonomy.

Paper cũng làm SQL error analysis và chỉ ra **valid SQL không có nghĩa là correct SQL**. ([arXiv][1])

---

## 9. Error Analysis notebook cần làm gì?

Không được dừng ở kiểu:

> “Model hallucinate vì không biết địa điểm Việt Nam.”

Hãy tự động + thủ công chia lỗi thành taxonomy:

| Error                      | Ví dụ cần tìm                         |
| -------------------------- | ------------------------------------- |
| **Entity resolution**      | sai POI do tên Việt/Anh/mixed name    |
| **Diacritics**             | tên có dấu ↔ bỏ dấu                   |
| **Wrong category**         | cafe/restaurant/marketplace           |
| **Wrong spatial operator** | KNN thành range, sai `ST_DWithin`     |
| **Direction reasoning**    | bearing/filter sai                    |
| **Unit error**             | m ↔ km                                |
| **Numeric extraction**     | SQL đúng nhưng final answer sai       |
| **Location formatting**    | coordinates bị LLM chuyển thành prose |
| **SQL schema error**       | column/function/table không tồn tại   |
| **OSM ground-truth issue** | tag sai, POI thiếu, stale data        |

Bảng tốt nhất trong report sẽ là:

```text
Error category | Direct | Text2SQL | Ours
```

Như vậy bạn chứng minh được **cải tiến giải quyết lỗi nào**, thay vì chỉ báo một con số F1 tăng.

---

## 10. Demo tiếng Việt mới

Rubric yêu cầu rõ ràng:

> Demo trên dữ liệu tiếng Việt mới.

Notebook cuối nên có **5 câu không thuộc test set**, ví dụ:

```text
“Quán cà phê gần Đại học ... nhất là gì?”
“Có bao nhiêu bệnh viện trong bán kính 5 km từ ...?”
“... cách ... bao nhiêu km?”
```

Với mỗi câu, show:

```text
Question
→ generated SQL
→ SQL execution result
→ detected answer_type
→ final Vietnamese answer
```

Nếu làm một widget/map nhỏ thì đẹp, nhưng **không cần thiết để đạt rubric**.

---

## 11. II.3 — Report hiện tại chưa thể nộp

Có hai file khác nhau:

* `docs/results.md`: kết quả mới, **4 model**, Qwen3.5-27B và Qwen3.6-27B đã có Text2SQL.

* `baselines/REPORT_VN_GEOQA.md`: vẫn ghi Qwen3.5-27B Text2SQL **pending**, chỉ tổng hợp ba model.

Vì vậy trước hết phải chọn **một source of truth** cho results.

Ngoài ra mình không thấy ACL `.tex`/ACL style trong repo hiện tại. Markdown report không thay thế yêu cầu:

> 4–5 pages, official ACL format.

Đừng dùng style của paper GS-QA gốc: bản paper hiện tại là manuscript ACM, còn thầy yêu cầu **ACL**.

---

## 12. Report ACL 4–5 trang nên kể câu chuyện gì?

Không nên dành 2 trang kể lại GS-QA.

### Abstract

Khoảng 120–170 từ:

* vấn đề GeoQA;
* limitation: benchmark gốc không tập trung tiếng Việt;
* VN-GeoQA: bao nhiêu câu, bao nhiêu type, OSM Vietnam;
* Direct vs Text2SQL vs proposed renderer;
* 1–2 kết quả chính;
* conclusion.

Không ghi số final cho đến khi notebook final đã rerun.

---

### 1. Introduction

Khoảng 0.5 trang.

Chỉ cần:

**Problem:** LLM biết ngôn ngữ nhưng khó tính toán spatial relation trên local OSM.

**Gap:** GS-QA đánh giá geospatial QA nhưng không nghiên cứu tiếng Việt/Vietnam-specific entities.

**Contributions:** nên chốt ba contribution:

1. xây **VN-GeoQA**, benchmark 800 câu tiếng Việt grounded trên OSM Việt Nam;
2. reproduce Direct + Text2SQL trên benchmark tiếng Việt;
3. đề xuất **type-aware structured answer pipeline**, kèm phân tích robustness tiếng Việt/error.

Đây là contribution rõ hơn “chúng tôi dịch paper sang tiếng Việt”.

---

### 2. Related Work

Chỉ khoảng 0.4–0.5 trang.

Ba nhóm là đủ:

* Geospatial QA / GS-QA;
* LLM + Text2SQL / tool-assisted QA;
* Vietnamese QA / multilingual LLM.

Paper gốc cũng đặt Text2SQL là related direction quan trọng cho geospatial database. ([arXiv][1])

Không cần liệt kê 15 paper mỗi paper làm gì.

---

### 3. Dataset

Đây phải là phần mạnh.

Ghi:

* OSM/Geofabrik source + snapshot date;
* Vietnam region;
* OSM → PostGIS;
* DB schema;
* 8 query types;
* generation templates;
* SQL ground truth;
* 800 QA;
* dev/test split;
* sample;
* manual QC protocol;
* percentage valid;
* Vietnamese normalization/full-vs-stripped;
* licensing/provenance.

Cần nói rõ **data được synthetic/template-generated**, không giả vờ là human-authored corpus.

---

### 4. Method

Có sơ đồ 3 system:

```text
Direct
Text2SQL
Text2SQL + Typed Renderer
```

Chỉ giải thích điều nhóm thực sự chạy.

Không cần trình bày lại toàn bộ architecture paper gốc.

---

### 5. Experimental Setup

Phải đủ để người khác tái chạy:

* exact model ID;
* model revision/checkpoint nếu có;
* GGUF filename/quantization nếu local;
* inference backend + version;
* prompt;
* temperature;
* max tokens;
* seed;
* hardware;
* PostgreSQL/PostGIS version;
* dev/test sizes;
* metrics;
* timeout;
* số record SQL trả tối đa.

Hiện `docs/results.md` chỉ ghi shorthand model + backend/quantization; final report nên ghi **canonical model source/checkpoint**.

---

### 6. Results and Discussion

Main table đừng chỉ để:

```text
overall text F1
```

Tốt hơn:

| Method | Name F1 ↑ | Loc Error ↓ | Dist RelErr ↓ | Count Acc ↑ | Valid SQL ↑ |
| ------ | --------: | ----------: | ------------: | ----------: | ----------: |

Sau đó bảng nhỏ per-type hoặc appendix.

Main discussion trả lời ba câu:

1. grounding bằng PostGIS giúp bao nhiêu?
2. typed renderer sửa được bao nhiêu lỗi location/numeric?
3. tiếng Việt có dấu vs bỏ dấu khác nhau thế nào?

Paper gốc cũng thấy Text2SQL nhìn chung mạnh hơn các baseline khác nhưng còn nhiều lỗi spatial SQL. ([arXiv][1])

---

### 7. Error Analysis

Không chỉ đưa 3 ví dụ.

Có:

* taxonomy;
* số lỗi từng nhóm;
* 2–3 representative examples;
* lỗi được proposed method sửa;
* lỗi còn lại.

Đây là chỗ rất dễ lấy điểm vì đúng lời thầy: **tập trung vào phần nhóm tự triển khai**.

---

### 8. Limitations and Ethical Considerations

Nên ghi cụ thể:

* chỉ 8/28 dạng GS-QA;
* template-generated Vietnamese chưa đa dạng như human queries;
* OSM coverage không đồng đều;
* OSM có tag sai/stale;
* benchmark hiện chỉ một quốc gia/ngôn ngữ;
* POI names có thể mixed Vietnamese/English;
* model quantization ảnh hưởng kết quả;
* QA này không nên được xem như hệ thống navigation safety-critical;
* OSM attribution/license;
* API/model version có thể thay đổi.

Paper gốc cũng thừa nhận benchmark/evaluation còn cần spatial-aware evaluation tốt hơn và retrieval hiện tại chưa xử lý location tốt. ([arXiv][1])

---

## 13. II.4 — Package cuối cùng cần trông như thế này

Một cấu trúc repo hợp lý:

```text
ViGSQA/
├── README.md
├── notebooks/
│   └── ViGSQA_End_to_End.ipynb
├── data/
│   ├── vigsqa_v1.jsonl
│   ├── dev.jsonl
│   └── test.jsonl
├── generator/
├── baselines/
├── evaluation/
├── results/
│   ├── predictions/
│   ├── text2sql/
│   ├── metrics.csv
│   └── error_analysis.csv
├── report/
│   ├── main.tex
│   ├── references.bib
│   ├── acl.sty ...
│   └── ViGSQA.pdf
└── docs/
    └── results.md
```

Mình cũng **không tìm thấy raw `_text_eval.csv`, `_parsed_eval.csv` hoặc `sql_exec.json` trong repo search hiện tại**. Nếu chúng đang `.gitignore`, final release nên ít nhất publish các prediction/evaluation artifacts cần thiết để người chấm có thể audit bảng kết quả mà không phải chạy lại 4 model lớn.

Nếu không fine-tune model thì mục “mô hình đã huấn luyện hoặc link model” không phải vấn đề: README ghi rõ **no fine-tuning**, rồi cung cấp exact model IDs/download links và quantization used.

---

## 14. Roadmap nên làm theo thứ tự này

| Phase                            | Goal                    | Việc cụ thể                                                   | Exit criterion                        |
| -------------------------------- | ----------------------- | ------------------------------------------------------------- | ------------------------------------- |
| **P0. Fix benchmark**            | Có dataset đáng tin     | Fix self-anchor, deterministic SQL, outlier checks, IDs, seed | Generator không còn known bugs        |
| **P1. Validate Vietnamese data** | Hoàn thành II.1         | Manual QC ≥80 câu, stats, freeze v1, dev/test                 | Có dataset card + QC table            |
| **P2. Finish notebook baseline** | Đạt tối thiểu II.2      | OSM→DB → EDA → Direct → Text2SQL → metrics                    | Một Colab chạy end-to-end             |
| **P3. Add group contribution**   | Bài không chỉ reproduce | Text2SQL + Typed Renderer                                     | Có controlled comparison với Text2SQL |
| **P4. Vietnamese experiment**    | Làm rõ 20% tiếng Việt   | full vs stripped diacritics                                   | Có một bảng robustness                |
| **P5. Error analysis**           | Giải thích kết quả      | SQL error + QA error taxonomy                                 | Có counts + examples                  |
| **P6. New-data demo**            | Đúng rubric             | 5 câu Việt mới                                                | Notebook show full pipeline           |
| **P7. ACL report**               | Hoàn thành II.3         | Viết 4–5 trang theo story trên                                | PDF ACL compile sạch                  |
| **P8. Submission cleanup**       | II.4                    | README, model links, raw outputs, notebook clean-run          | Clone repo → notebook chạy được       |

---

## 15. Scope mình khuyên chốt để tránh làm quá nhiều

Nếu mục tiêu là **đủ mạnh nhưng hoàn thành được**, đừng chạy thêm hàng loạt model.

**Final experiment matrix nên chỉ là:**

| Experiment                      | Model                           | Dataset          |
| ------------------------------- | ------------------------------- | ---------------- |
| Direct                          | 1 model 7–9B                    | test 640         |
| Text2SQL                        | **cùng model**                  | test 640         |
| **Text2SQL + Typed Renderer**   | **cùng model**                  | test 640         |
| Diacritics ablation             | cùng model                      | subset/full test |
| Existing large-model comparison | 4 model trong `docs/results.md` | supplementary    |

Ưu điểm là thay đổi duy nhất giữa ba system chính là **method**, nên có thể kết luận được nguyên nhân cải thiện. Nếu thay model liên tục thì rất khó biết điểm tăng do model hay do pipeline.

Các run Gemma/Qwen 26–27B hiện có vẫn rất hữu ích để làm **secondary evidence**, không cần ép Colab reproduce chúng.

---

### Definition of Done

Nếu phải rút toàn bộ kế hoạch thành một câu:

> **Freeze một VN-GeoQA 800 câu đã QC → làm một notebook Colab end-to-end với Direct, Text2SQL và Text2SQL+structured output → đánh giá bằng metric theo answer type → làm Vietnamese diacritics/error analysis → viết ACL paper dựa hoàn toàn trên các run reproducible đó.**

Nếu hoàn thành chuỗi này, bạn không chỉ đáp ứng từng bullet trong rubric mà còn có một câu chuyện nghiên cứu khá sạch: **Vietnamese adaptation + database grounding + một cải tiến cụ thể giải quyết limitation quan sát được từ chính experiment của nhóm**, thay vì chỉ port code GS-QA và chạy lại vài LLM.

[1]: https://arxiv.org/pdf/2605.22811 "https://arxiv.org/pdf/2605.22811"
