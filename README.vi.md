# ViGSQA — Hỏi đáp không gian địa lý tiếng Việt

[English](README.md)

ViGSQA là bản chuyển thể tiếng Việt của [GS-QA](https://arxiv.org/abs/2605.22811), một benchmark hỏi đáp trên dữ liệu không gian địa lý.
Dự án xây dựng VN-GeoQA, bộ dữ liệu gồm 2.800 câu hỏi tiếng Việt thuộc đầy đủ 28 loại câu hỏi của GS-QA, cùng với các baseline đã đánh giá, một phương pháp phục hồi câu trả lời, phân tích lỗi và demo tiếng Việt.
Toàn bộ nội dung đồ án có thể được tái lập trên Google Colab CPU bằng cách mở `main.ipynb` trong bài nộp và chọn **Run all**.

## Đóng góp

1. **Bộ dữ liệu tiếng Việt:** VN-GeoQA chuyển thể 28 template của GS-QA sang tiếng Việt và ghép mỗi câu hỏi với SQL cùng đáp án đã được kiểm chứng trên cơ sở dữ liệu OpenStreetMap Việt Nam.
2. **Đánh giá baseline:** bốn tổ hợp Ornith/Qwen và Direct/Text2SQL được so sánh trên split dev/test cố định bằng các metric văn bản và không gian địa lý của GS-QA.
3. **Cải tiến records-to-answer:** khi Text2SQL trả về các hàng dữ liệu hữu ích nhưng không diễn đạt được câu trả lời, bước rescue chuyển các hàng có kiểu đó thành đáp án mà không cần thêm lời gọi LLM.
4. **Phân tích lỗi:** lỗi được phân tích theo giai đoạn của pipeline và theo các yếu tố đặc thù tiếng Việt như geocode địa chỉ và dấu thanh.
5. **Demo tiếng Việt:** năm câu hỏi mới minh họa việc truy vấn cơ sở dữ liệu, hai baseline và bước rescue.

## Tái lập đồ án trên Colab CPU

[Mở `main.ipynb` bằng Google Colab](https://drive.google.com/file/d/1ae4NWZ9TkNKvpRsNFPpqiAacQHO8Ihr3/view?usp=sharing), chọn runtime CPU, rồi chọn **Runtime → Run all**.
Notebook cài đặt dự án và PostgreSQL/PostGIS, tải các artifact `v3.0.0` và kiểm tra checksum.

Không cần GPU, tải model, API key hay dịch vụ LLM.
Các kết quả chính thức của LLM đã được tạo từ trước và được khôi phục từ các tệp cùng cache của release.
Notebook trực tiếp chạy quy trình SQL/PostGIS, khám phá dữ liệu, đánh giá tập test, so sánh baseline, tái dựng records-to-answer, phân tích lỗi và xử lý demo.

Notebook đáp ứng các yêu cầu môn học theo thứ tự sau:

1. cài đặt môi trường và khôi phục artifact;
2. kiểm tra và khám phá bộ dữ liệu;
3. trình bày kết quả baseline chính thức và so sánh trên tập test;
4. đánh giá cải tiến records-to-answer trên split dev/test;
5. phân tích lỗi tiếng Việt;
6. demo trên các câu hỏi tiếng Việt mới.

## Chạy lại toàn bộ pipeline trên máy có GPU (tùy chọn)

Repository cũng chứa mã nguồn đã được dùng để tạo bộ dữ liệu và chạy các model.
Đây là quy trình riêng với phần tái lập đồ án trên Colab và cần GPU để chạy vLLM.

Dự án dùng [Pixi](https://pixi.prefix.dev/latest/installation/) làm trình quản lý gói.
Cài đặt các dependency, vào môi trường của dự án và cấu hình PostgreSQL cùng quyền truy cập Hugging Face:

```bash
pixi install
pixi shell
export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=osm_vn PGUSER=postgres PGPASSWORD=postgres HF_TOKEN=your_hugging_face_token
```

Để sinh lại câu hỏi trong một thư mục staging và kiểm tra kết quả:

```bash
./scripts/bootstrap_postgres.sh
python generator/generator_vi.py --seed 42 --count 100 --output data/rebuild/questions_vi
python generator/verify_vi.py --input data/rebuild/questions_vi --all
```

`generator/generator_vi.py` tạo các câu hỏi tiếng Việt và `generator/verify_vi.py` kiểm tra cấu trúc cùng các ràng buộc của đáp án.

`compose.yaml` định nghĩa các dịch vụ PostgreSQL/PostGIS và vLLM.
Đặt `VLLM_MODEL` thành ID của một trong hai model trên Hugging Face, khởi động model đó rồi chạy hai baseline Direct và Text2SQL:

```bash
VLLM_MODEL=ornith-ai/Ornith-1.5-9B-NVFP4 podman compose up -d postgres vllm
MODELS=ornith-ai/Ornith-1.5-9B-NVFP4 ./scripts/inference.sh --llm-concurrency 4

VLLM_MODEL=AxionML/Qwen3.5-9B-NVFP4 podman compose up -d --force-recreate vllm
MODELS=AxionML/Qwen3.5-9B-NVFP4 ./scripts/inference.sh --llm-concurrency 4
```

vLLM chỉ phục vụ một model tại mỗi thời điểm, còn `scripts/inference.sh` điều phối các lần chạy hoàn chỉnh thông qua `scripts/run_raw_inference.py`.
Sau khi cả hai model hoàn tất, phục vụ lại Ornith rồi chạy đánh giá vì Ornith là parser cố định cho cả bốn lần chạy:

```bash
VLLM_MODEL=ornith-ai/Ornith-1.5-9B-NVFP4 podman compose up -d --force-recreate vllm
./scripts/evaluate.sh --llm-concurrency 4
```

`scripts/evaluate.sh` điều phối `scripts/run_evaluation.py` và kiểm tra các kết quả đánh giá đã hoàn tất.

## Bộ dữ liệu và asset của release

VN-GeoQA `v3.0.0` gồm 2.800 câu hỏi: 100 câu cho mỗi loại trong 28 loại của GS-QA, được sinh với seed 42.
Dữ liệu tham chiếu bắt nguồn từ `vietnam-260901.osm.pbf` (SHA-256 `edf2d41d93b25474acc14a34f6c313940ecfea5671835299ddd793c60d08a3e8`) và được cung cấp dưới dạng dump PostGIS có thể khôi phục trực tiếp.

Tải các artifact từ [release ViGSQA v3.0.0](https://github.com/itskyf/ViGSQA/releases/tag/v3.0.0):

| Asset | Nội dung | SHA-256 |
|---|---|---|
| `vn-geoqa.zip` | Các file JSONL của bộ dữ liệu và manifest | `dfe0ae70260c52837eb2aa38272787fcb55d98ad02ca4fbf0c432084f9055740` |
| `osm-vn.dump` | Dump cơ sở dữ liệu PostGIS ở định dạng custom của PostgreSQL | `deb523cd943520f37b67b70b421a9f3d7a22283ee0fb33d856ffd6b9cb2844d0` |
| `evaluation-results.tar.gz` | Kết quả theo từng câu và evaluation seal của bốn run chính thức | `bb10de26aa851dab1e24baf93dbf8d32d21ecad1205aabf32920074efd484b16` |
| `llm-cache-20260905.sql.gz` | Cache PostgreSQL chứa kết quả chính thức của LLM | `60d9e0f213c6bd8282dd00ceb16b3c428187f9b2791840c2e521b15c6c808830` |
| `rescue-inputs.tar.gz` | Input dùng để tái dựng kết quả records-to-answer | `56841ffaa4a0354a02fac9619254b5bf554d5a291049d075dde4ad9c42cc373f` |
| `demo-inputs.tar.gz` | Kết quả mô hình cho 5 câu hỏi demo qua 15 bước sinh | `c538c9332410690b76330ea1659ce3960c17ebc20186319d6930c77ba7c5228b` |

Bộ dữ liệu được khôi phục ngoài Git bằng `./scripts/restore_dataset.sh` và được đọc qua `generator/questions_vi`.
Xem [docs/data_generation.md](docs/data_generation.md) để biết schema, quy trình sinh và cách kiểm chứng dữ liệu.

## Model và đánh giá

Hai model pretrained được đánh giá là [Ornith-1.5-9B-NVFP4](https://huggingface.co/ornith-ai/Ornith-1.5-9B-NVFP4) và [Qwen3.5-9B-NVFP4](https://huggingface.co/AxionML/Qwen3.5-9B-NVFP4).
Mỗi model được đánh giá với Direct và Text2SQL, tạo thành bốn run chính thức.
ViGSQA không fine-tune hoặc công bố trọng số model.

Phần đánh giá tuân theo các nhóm đáp án của GS-QA và báo cáo text F1, relative error có chặn, khoảng cách vị trí qua geocode và điểm hướng theo tám cung khi phù hợp.

### Khác biệt về parser so với GS-QA

GS-QA chọn Qwen 3.5 để chuyển câu trả lời dạng văn bản tự do thành JSON có cấu trúc phục vụ đánh giá.
ViGSQA dùng Ornith làm parser chung cho cả bốn run để phép so sánh sử dụng cùng một cách parsing trong khi vẫn giữ các metric của GS-QA.

## Hướng dẫn cấu trúc repository

| Đường dẫn | Mục đích |
|---|---|
| `main.ipynb` | Notebook Colab end-to-end được cung cấp cùng bài nộp |
| `generator/generator_vi.py` | Sinh câu hỏi tiếng Việt từ PostGIS |
| `generator/verify_vi.py` | Kiểm tra câu hỏi và đáp án đã sinh |
| `compose.yaml` | Định nghĩa các dịch vụ PostgreSQL/PostGIS và vLLM |
| `scripts/bootstrap_postgres.sh` | Chuẩn bị PostGIS và khôi phục cơ sở dữ liệu tham chiếu |
| `scripts/restore_dataset.sh` | Khôi phục và kiểm tra VN-GeoQA `v3.0.0` |
| `scripts/restore_llm_cache.sh` | Khôi phục cache kết quả LLM |
| `scripts/run_raw_inference.py` / `scripts/inference.sh` | Chạy inference Direct và Text2SQL |
| `scripts/run_evaluation.py` / `scripts/evaluate.sh` | Parse và đánh giá câu trả lời của model |
| `scripts/records_to_answer.py` | Tái dựng cải tiến records-to-answer |
| `scripts/error_taxonomy.py` | Sinh kết quả phân tích lỗi |
| `scripts/run_demo.py` | Xử lý demo tiếng Việt |
| `docs/data_generation.md` | Mô tả quy trình sinh và kiểm chứng dữ liệu |
