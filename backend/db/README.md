# Refactor cơ sở dữ liệu: PostgreSQL nghiệp vụ, MongoDB vector

Tài liệu này ghi **trạng thái mã nguồn hiện tại** của quá trình chuyển đổi. Các cờ lưu trữ mặc định vẫn là `mongo`; chưa có cutover toàn ứng dụng.

## Phân chia dữ liệu

| Nhóm | Nguồn dữ liệu khi bật cờ PostgreSQL | Mặc định hiện tại |
|---|---|---|
| Tài khoản, quyền, hồ sơ, phiên demo | PostgreSQL: `users`, `user_sessions` với `USER_STORE=postgres` | MongoDB |
| Model AI, phiên bản model, prompt, policy đánh giá | PostgreSQL: `ai_models`, `ai_model_versions`, `prompt_templates`, `evaluation_policies` với `AI_CONFIG_STORE=postgres` | MongoDB |
| Học phần, chương, CLO | PostgreSQL: `subjects`, `subject_chapters`, `learning_outcomes` với `CATALOG_STORE=postgres` | MongoDB |
| Từ điển từ khóa dùng khi chunking | PostgreSQL: `legacy_dictionaries`, `keywords` với `DICTIONARY_STORE=postgres` | MongoDB |
| Thông báo và trạng thái đã đọc | PostgreSQL: `notifications` với `NOTIFICATION_STORE=postgres` | MongoDB |
| Cấu hình Moodle target | PostgreSQL: `moodle_targets` với `MOODLE_TARGET_STORE=postgres` | MongoDB |
| Tài liệu, trang OCR, câu hỏi/phiên bản, duyệt/đánh giá, đề thi, job, Moodle publication, phần lớn audit | Chưa chuyển luồng đọc/ghi; schema và công cụ sao chép PostgreSQL đã có | MongoDB |
| Chunk, chunk set, embedding metadata, vector collection và lineage của index | Giữ MongoDB | MongoDB |
| Chỉ mục/vector truy xuất RAG | ChromaDB | ChromaDB local |
| File gốc, artifact OCR, bản xuất | Chưa có cloud storage adapter | Filesystem local |

ID nghiệp vụ tiếp tục là chuỗi ObjectId 24 ký tự để giữ API và liên kết hiện tại. Bảng PostgreSQL dùng cột có kiểu cho khóa/trạng thái quan trọng; `payload jsonb` giữ các trường cũ chưa được chuẩn hóa. Dữ liệu chương/CLO đọc từ bảng con, không lấy từ mảng nhúng trong `subjects.payload`.

## Thay đổi đã triển khai

- `db/migrations/0001` đến `0004` tạo schema nghiệp vụ và metadata AI; `0005_catalog_casefold.sql` thêm ràng buộc mã học phần, chương, CLO không trùng khi khác chữ hoa/thường hoặc có khoảng trắng đầu/cuối.
- `0006_dictionary_keyword_uniqueness.sql` ngăn từ khóa trùng trong cùng từ điển, kể cả khác chữ hoa/thường hoặc khác trạng thái CORE/LEARNED/PENDING.
- `0007_document_page_location.sql` cho phép trang OCR không có `page_number` (DOCX/text), thêm `unit_number` và `source_location` để giữ đúng thứ tự, vị trí nguồn khi sao chép sang PostgreSQL. Đây là chuẩn bị schema và shadow copy; luồng tài liệu/OCR vẫn ghi MongoDB.
- `modules/catalog/postgres_subject_repository.py` xử lý học phần, chương, CLO trong PostgreSQL. Ghi dữ liệu và audit tương ứng cùng transaction; cập nhật chương/CLO khóa học phần và ghép thay đổi với bản mới nhất để tránh ghi đè trường khác.
- Các đường đọc học phần của tài liệu, sinh câu hỏi, thống kê reviewer và trang quản trị dùng nguồn được chọn bởi `CATALOG_STORE`.
- `modules/notifications/postgres_repository.py` xử lý hộp thông báo, phân trang, số chưa đọc và đánh dấu đã đọc. Mọi truy vấn đều giới hạn theo `recipient_user_id`; bản ghi Mongo cũ có `is_read=true` nhưng thiếu `read_at` vẫn được coi là đã đọc.
- `modules/dictionary/postgres_repository.py` lưu từ điển và các từ khóa CORE/LEARNED/PENDING trong PostgreSQL; bước chunking và tác vụ AI học từ khóa chọn cùng một nguồn qua `DICTIONARY_STORE`.
- `modules/admin/postgres_moodle_target_repository.py` lưu Moodle target, trạng thái kích hoạt và lần kiểm tra kết nối trong PostgreSQL. Trang quản trị, thống kê và bước publish mock đọc cùng nguồn được chọn. Chỉ lưu tên biến môi trường token (`token_env_var`), không lưu giá trị token vào database.
- Repository PostgreSQL cho tài khoản/phiên và cấu hình AI đã có từ giai đoạn trước.
- Khi `USER_STORE=postgres`, thống kê và lịch cá nhân vẫn đọc tài liệu/câu hỏi từ MongoDB vì đây còn là nguồn ghi chính của hai nhóm đó; không dùng các bảng PostgreSQL shadow copy có thể đã cũ.

## Cấu hình và chạy thử

Ví dụ chạy từ thư mục `backend` trên **database kiểm thử**:

```powershell
python -m db.migrate --apply
python -m db.migrate --check
python -m db.copy_business_data
python -m db.copy_business_data --apply
python -m db.verify_business_data
```

`POSTGRES_DSN` và `MONGO_URI` phải trỏ đúng môi trường kiểm thử. `copy_business_data` mặc định chỉ đếm và không ghi; `--apply` sao chép một chiều từ MongoDB. Chạy `verify_business_data` **trước khi cho phép ghi mới vào PostgreSQL**: sau khi đổi nguồn chuẩn, việc so toàn bộ PostgreSQL với MongoDB cũ sẽ báo chênh lệch đúng với thực tế. `--resume` chỉ dùng cho shadow copy chưa có ghi mới vì upsert có thể ghi đè dữ liệu PostgreSQL.

Sau khi đối chiếu dữ liệu và chạy kiểm thử tích hợp, bật các cờ cần thử trong cả API và worker:

```dotenv
USER_STORE=postgres
AI_CONFIG_STORE=postgres
CATALOG_STORE=postgres
NOTIFICATION_STORE=postgres
DICTIONARY_STORE=postgres
MOODLE_TARGET_STORE=postgres
```

`CATALOG_STORE` và `NOTIFICATION_STORE` yêu cầu `USER_STORE=postgres` để khóa ngoại owner/recipient hợp lệ. Có thể bật từng nhóm sau khi dữ liệu nhóm đó đã được sao chép và kiểm tra. `MOODLE_TARGET_STORE` chỉ chuyển cấu hình target; các publication vẫn ghi MongoDB theo luồng câu hỏi. Không bật các cờ trên production khi câu hỏi, tài liệu, job và các luồng liên quan còn dùng MongoDB. Khởi động lại API/worker sau khi đổi cờ; không chuyển cờ trong lúc có ghi đồng thời ở hai nguồn.

Kiểm thử PostgreSQL yêu cầu `RUN_POSTGRES_INTEGRATION=1`, `POSTGRES_DSN` trỏ đến database kiểm thử đã migrate. Khi không đặt hai biến này, các ca tích hợp PostgreSQL sẽ được bỏ qua.

## Các việc còn lại trước cutover

1. Chuyển documents/OCR, generation/evaluation jobs, questions/versions/reviews, exams, Moodle, audit và các đường đọc thống kê sang PostgreSQL; giữ transaction và idempotency cho từng aggregate.
2. Chỉ để dữ liệu liên quan chunk/vector ở MongoDB, sau đó ngừng bootstrap các collection nghiệp vụ MongoDB. Không xóa collection cũ trước khi rehearsal, đối soát và hết thời gian rollback.
3. Thêm storage adapter local/object storage, triển khai Chroma server và kiểm tra phục hồi chỉ mục từ chunk MongoDB để hỗ trợ cloud.
4. Diễn tập trên bản sao dữ liệu, đóng băng ghi, sao chép delta, đối chiếu nội dung và chạy lại luồng Teacher → Reviewer → Admin trước khi đổi cờ production.

PostgreSQL, MongoDB, ChromaDB, file storage và model provider không có transaction chung. Các luồng đi qua nhiều hệ cần trạng thái, retry, outbox và tác vụ đối soát trước khi cutover.
