# Yêu cầu của đồ án cuối kì

Đề tài nhóm chọn là paper [GS-QA: A Benchmark for Geospatial Question Answering](https://arxiv.org/pdf/2605.22811), codebase gốc là <https://github.com/MajidSas/GS-QA>.

## Yêu cầu đề tài (Đề tài mang tính lý thuyết)

Cài đặt được paper chỉ 40%, có báo cáo dạng paper 40%, còn 20% cho tiếng Việt. Cụ thể:

### 1. Ngữ liệu và khả năng xử lý tiếng Việt (2,0 điểm)

Hệ thống phải được xây dựng và đánh giá trên dữ liệu tiếng Việt. Học viên chủ động tìm kiếm bộ ngữ liệu công khai phù hợp hoặc xây dựng dữ liệu bằng các phương pháp như dịch máy, sinh dữ liệu tổng hợp, gán nhãn thủ công hoặc bán tự động.

### 2. Cài đặt, thực nghiệm và chương trình minh họa (4,0 điểm)

Học viên phải cung cấp ít nhất một Jupyter Notebook hoàn chỉnh, có thể chạy trên Google Colab hoặc Kaggle Notebook.

Notebook cần được tổ chức tối thiểu thành các phần:

* Cài đặt thư viện và cấu hình môi trường.
* Tải hoặc đọc bộ dữ liệu.
* Khám phá và tiền xử lý dữ liệu.
* Cài đặt hoặc huấn luyện mô hình.
* Đánh giá trên tập kiểm thử.
* So sánh với mô hình cơ sở.
* Phân tích lỗi.
* Demo trên dữ liệu tiếng Việt mới.

Notebook không được phụ thuộc vào các đường dẫn cục bộ trên máy cá nhân. Trường hợp cần mô hình hoặc dữ liệu dung lượng lớn, học viên phải cung cấp đường dẫn tải và hướng dẫn sử dụng.

### 3. Báo cáo khoa học dạng ACL Short Paper (4,0 điểm)

Học viên viết báo cáo ngắn từ 4–5 trang, không tính phần tài liệu tham khảo và phụ lục, bằng tiếng Việt hoặc tiếng Anh.
Báo cáo phải sử dụng bộ định dạng chính thức của ACL (<https://github.com/acl-org/acl-style-files>). Cấu trúc báo cáo đề nghị:

* Abstract
* Introduction
* Related Work
* Dataset
* Method
* Experimental Setup
* Results and Discussion
* Error Analysis
* Limitations and Ethical Considerations
* Conclusion
* References

### 4. Sản phẩm cần nộp

Học viên nộp đầy đủ các sản phẩm sau, nén lại thành tập tin `.zip` (đặt tên theo MSHV của tất cả thành viên nhóm):

* File báo cáo PDF theo định dạng ACL.
* Mã nguồn hoặc đường dẫn kho mã nguồn.
* Jupyter Notebook có thể chạy trên Google Colab hoặc Kaggle.
* File `README.md` mô tả cách chạy chương trình.
* Thông tin hoặc đường dẫn tải bộ dữ liệu (nếu có).
* Mô hình đã huấn luyện hoặc đường dẫn tải mô hình.

## Q&A từ giảng viên

### 1. Cách viết và cấu trúc báo cáo

* **Nội dung trọng tâm:** Không cần trình bày chi tiết toàn bộ các phần lý thuyết như paper gốc. Tóm tắt ngắn gọn và tập trung chủ yếu vào phần nhóm tự triển khai (dữ liệu tiếng Việt, cài đặt thực nghiệm, cải tiến, phân tích lỗi).
* **Định hướng triển khai:** Bài báo chỉ mang tính chất tham khảo ý tưởng (không bắt buộc chỉ dùng 1 bài). Nên tập trung khai thác các điểm hạn chế (limitation) của paper hoặc tự đề xuất giải pháp, hướng tiếp cận mới theo góc nhìn của nhóm.

### 2. Yêu cầu thành phần bài nộp

* **Hình thức nộp code:** Bắt buộc phải nộp cả hai thành phần:
  * Mã nguồn (Source code) hoặc đường dẫn kho mã nguồn (Repository).
  * File Jupyter Notebook có khả năng thực thi được trên Google Colab hoặc Kaggle.

### 3. Quy định về tái hiện thực nghiệm (Reproduce)

* **Phạm vi Dataset:** Chỉ cần chọn và chạy thực nghiệm trên 1 dataset trong số các dataset của bài báo, không bắt buộc phải chạy trên toàn bộ.
* **Mức độ phụ thuộc paper:** Paper gốc là tài liệu tham khảo ý tưởng, nhóm không bắt buộc phải làm hoàn toàn rập khuôn theo toàn bộ thiết lập thực nghiệm của tác giả.
