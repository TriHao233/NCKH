# Đánh giá tích hợp riêng Docling

Trạng thái: CHƯA MERGE, chưa đổi OCR hiện tại. Code ứng dụng vẫn dùng EasyOCR + PDFium.
Bản hiện tại: dev-teacher / 0e87a62. Nguồn Docling: origin/dev / f1525bf.

## Kết quả mô phỏng

Chạy hai bản PdfParser trong module riêng của một tiến trình kiểm thử. Dùng PDF tạm 3 trang và dữ liệu nhận dạng giả; các dấu hiệu scan/bảng được kiểm soát bằng fixture. Không gọi OCR thật, model, database hoặc API ứng dụng. Đây là kiểm thử routing/contract, không phải benchmark.

| Tình huống giả lập | EasyOCR gửi xử lý | Docling gửi xử lý |
|---|---|---|
| 3 trang có chữ, không bố cục phức tạp | Không trang nào | Không trang nào |
| 3 trang scan | 1, 2, 3 | 1, 2, 3 |
| Chỉ trang 2 là scan | 2 | 2 |
| Có chữ; trang 2 có dấu hiệu bảng | Không trang nào | 2 (bổ sung bố cục) |

Đạt các kiểm tra:
- Giữ 3 đơn vị tài liệu và số trang gốc qua hai parser.
- Wrapper Docling chọn các trang 1, 3, khử trùng lặp và đưa block trang tương đối 2 về trang gốc 3.
- Yêu cầu tiếng Việt truyền preset tesseract và ngôn ngữ vie.
- Giả lập Docling lỗi: trang có text gốc + bảng giữ trạng thái passed_with_warning; trang scan quality_failed.

Những thứ CHƯA kiểm chứng: nhận dạng tiếng Việt, đoạn mã/bảng thật, latency HTTP, số giây/trang, RAM/VRAM, tích hợp đầy đủ RAG và sinh câu hỏi. Không thể suy ra Docling nhanh hơn từ mô phỏng này.

## Phạm vi tích hợp đề xuất

1. Thêm backend/modules/ocr/docling_engine.py và backend/Docling.Dockerfile từ nguồn đã kiểm tra.
2. Chỉ lấy các thay đổi Docling của parser PDF; giữ schema tài liệu và cách dùng số trang/dẫn chứng.
3. Thêm các trường docling_* vào Settings hiện tại, không thay thế nguyên core/config.py.
4. Giữ khóa gpu_operation hiện tại trong pipeline. Không lấy việc bỏ khóa ở dev.
5. Tạo cấu hình Docker bổ sung cho Docling; truyền DOCLING_URL=http://docling:5001, preset tesseract và ngôn ngữ vie cho cả backend và worker. Kiểm tra cache đúng với user của image, healthcheck, GPU và startup readiness.
6. Giữ pypdfium2 vì parser hiện tại còn dùng để xử lý vùng ảnh/PDF. Giữ EasyOCR trong giai đoạn benchmark để đối chiếu, không tự fallback sang EasyOCR khi Docling lỗi.
7. Không lấy prompt, luồng sinh câu hỏi, frontend, tài khoản, phân quyền, PostgreSQL hoặc toàn bộ Docker Compose của dev.

Ảnh hưởng trực tiếp chỉ ở xử lý tài liệu PDF mới. PDF có bố cục sẽ có thể sinh block/chunk khác và tác động đầu vào RAG; không thể bảo đảm đầu ra sinh câu hỏi giống hoàn toàn dù không sửa code sinh câu hỏi. Tài liệu/vector cũ không được tự tái xử lý hay xóa.

## Rủi ro nếu lấy nguyên file từ dev

- core/config.py đổi model mặc định, giảm số token đầu ra và timeout, bỏ các trường đang dùng. Có thể làm lỗi sinh câu hỏi/auth.
- pipeline.py bỏ khóa phối hợp GPU: có nguy cơ tranh VRAM với Ollama/embedding.
- docker-compose.yml có khóa trùng ANONYMIZED_TELEMETRY và deploy, đồng thời đổi cấu hình frontend và image backend/worker ngoài phạm vi OCR.
- requirements.txt bỏ pypdfium2 dù parser hiện tại còn cần; không nên áp dụng nguyên file.
- Số trang Docling xử lý có thể nhiều hơn EasyOCR do bổ sung layout; tốc độ tổng không chỉ phụ thuộc engine OCR.

## Benchmark thực tế trước khi đưa vào sử dụng

Dùng cùng bộ PDF có chữ, scan tiếng Việt, hỗn hợp, mã nguồn và bảng. Giữ cùng phần cứng, không có job LLM chạy đồng thời; ghi rõ EasyOCR GPU và Docling Tesseract CPU (GPU của container có thể dùng cho layout/table). Đo lượt model chưa nạp và lượt đã nạp, ít nhất 3 lượt lặp. So sánh tổng thời gian, trang xử lý, chữ sai/mất, dấu tiếng Việt, dấu ngoặc/toán tử/indent trong mã, cấu trúc bảng và số trang dẫn chứng. Sau đó chạy ingest → chunk → retrieve → generation với dữ liệu thử riêng.

Hiện chưa có container/image Docling trên máy. Chưa build hoặc tải image nặng trong bước mô phỏng này.

## Artifact

- results.json: kết quả mô phỏng.
- simulate.py + sources.json: script và snapshot nguồn để tái lập.
- docling-core-review.patch: diff riêng engine/parser/Dockerfile để đọc; CHƯA áp dụng. Patch này chưa bao gồm cấu hình Settings/Compose nên chưa phải bản tích hợp có thể chạy.

Chỉ triển khai tích hợp sau lệnh merge của người dùng.
