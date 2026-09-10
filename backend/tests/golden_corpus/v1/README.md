# Golden corpus v1

Ground truth trong `truth/pages.json` được biên soạn trước khi render fixture và không lấy từ text layer hay output OCR. `manifest.json` ánh xạ từng case sang profile ngưỡng. `truth/retrieval_cases.json` chứa cả câu có đáp án và câu bắt buộc từ chối do nguồn không hỗ trợ.

Corpus hiện có 12 trang author-before-render. Đây là ground truth độc lập về mặt dữ liệu, nhưng vẫn mang trạng thái `needs_second_reviewer`; không được tuyên bố OCR đạt chuẩn production trước khi một người thứ hai duyệt bản chép và benchmark live đạt ngưỡng.

Chạy `python scripts/build_golden_corpus.py --output <thư-mục-riêng>` để tạo PDF scan, PDF hỗn hợp, DOCX và DOC. Script không ghi vào uploads/OCR artifacts/Chroma. LibreOffice là bắt buộc cho born-digital PDF và DOC; Docling là bắt buộc khi benchmark OCR live.

Không được dùng corpus này để huấn luyện hoặc tinh chỉnh extractor đang được đánh giá. Mọi sửa ground truth phải tăng `corpus_version` và được review thủ công.
