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
| Khóa giới hạn đồng thời model AI | PostgreSQL: `llm_slots` với `LLM_SLOT_STORE=postgres` | MongoDB |
| Tài liệu, trang OCR, câu hỏi/phiên bản, duyệt/đánh giá, đề thi, job, Moodle publication, phần lớn audit | Chưa chuyển luồng đọc/ghi; schema và công cụ sao chép PostgreSQL đã có | MongoDB |
| Chunk, chunk set, embedding metadata và vector collection | Giữ MongoDB | MongoDB |
| Lịch sử quyết định promote/rollback/archive/delete lineage | PostgreSQL: `document_lineage_events` khi `DOCUMENT_STORE=postgres` | MongoDB |
| Chỉ mục/vector truy xuất RAG | ChromaDB local hoặc server chung với `CHROMA_MODE=http` | ChromaDB local |
| File gốc, artifact OCR, bản xuất | Chưa có cloud storage adapter | Filesystem local |

ID nghiệp vụ tiếp tục là chuỗi ObjectId 24 ký tự để giữ API và liên kết hiện tại. Bảng PostgreSQL dùng cột có kiểu cho khóa/trạng thái quan trọng; `payload jsonb` giữ các trường cũ chưa được chuẩn hóa. Dữ liệu chương/CLO đọc từ bảng con, không lấy từ mảng nhúng trong `subjects.payload`.

## Thay đổi đã triển khai

- `db/migrations/0001` đến `0004` tạo schema nghiệp vụ và metadata AI; `0005_catalog_casefold.sql` thêm ràng buộc mã học phần, chương, CLO không trùng khi khác chữ hoa/thường hoặc có khoảng trắng đầu/cuối.
- `0006_dictionary_keyword_uniqueness.sql` ngăn từ khóa trùng trong cùng từ điển, kể cả khác chữ hoa/thường hoặc khác trạng thái CORE/LEARNED/PENDING.
- `0007_document_page_location.sql` cho phép trang OCR không có `page_number` (DOCX/text), thêm `unit_number` và `source_location` để giữ đúng thứ tự, vị trí nguồn khi sao chép sang PostgreSQL. Đây là chuẩn bị schema và shadow copy; luồng tài liệu/OCR vẫn ghi MongoDB.
- `0008_document_subjects.sql` thêm bảng quan hệ `document_subjects` có thứ tự, sao chép đủ `subject_ids` của tài liệu và backfill các bản PostgreSQL shadow hiện có. `documents.subject_id` tiếp tục là học phần chính; luồng tài liệu/OCR vẫn ghi MongoDB cho đến khi hoàn thành chuyển worker/RAG.
- `0009_audit_event_shape.sql` bổ sung actor type/role, danh sách thay đổi, hash trước/sau và payload đầy đủ cho audit. Công cụ shadow copy đọc được cả event lồng nhau hiện hành lẫn field phẳng cũ; phần audit của question workflow vẫn ghi MongoDB cho đến khi chuyển cùng transaction câu hỏi/review.
- `modules/documents/postgres_repository.py` đã có repository PostgreSQL cho metadata tài liệu, học phần gắn tài liệu, artifact, job OCR/CHUNK và trang OCR, gồm transaction khi cập nhật nhiều bảng. Repository này chưa được gắn vào API/worker vì đường hoàn tất chunk/index và các module đọc tài liệu vẫn truy cập MongoDB trực tiếp.
- Hủy CHUNK job trong repository PostgreSQL ghi `outbox_events` cùng transaction; worker chuyển sự kiện sang các collection vector MongoDB, có lease và retry. Event lỗi chỉ lưu tên loại exception, không lưu thông tin kết nối/secret.
- Bộ chọn `DOCUMENT_STORE` đã nối API tài liệu, OCR, bước chunk/reindex cơ bản, lineage và các đường đọc nguồn của RAG/sinh câu hỏi tới repository tương ứng. Cờ vẫn mặc định `mongo` và **chưa được phép bật cho toàn ứng dụng**: Admin jobs/dashboard, user calendar và các luồng đọc/ghi tài liệu trực tiếp còn cần chuyển, kiểm thử và đối soát trước cutover.
- `0010_document_lineage_events.sql` lưu lịch sử quyết định lineage trong PostgreSQL. Promote/rollback khi dùng repository PostgreSQL kiểm tra con trỏ hiện hành và ghi tài liệu, lineage event, audit trong một transaction. Shadow copy chuyển cả lịch sử `pipeline_lineage_events` cũ.
- `0011_user_reviewer_permissions.sql` giữ quyền cộng/trừ và phạm vi học phần Reviewer trong PostgreSQL. Bản shadow user đã sao chép trước migration này cần chạy lại bước sao chép/đối soát để điền các field từ MongoDB cũ.
- Archive và xóa vĩnh viễn lineage ở chế độ PostgreSQL ghi quyết định/outbox vào PostgreSQL; worker thao tác Mongo vector và Chroma theo trạng thái có thể retry. OCR pages/job được xóa khỏi PostgreSQL sau khi xóa vector, trừ khi OCR job còn được chunk set khác sử dụng. Lệnh xóa vĩnh viễn vẫn cần bản backup offline do người vận hành xác nhận; chưa có cơ chế kiểm chứng backup tự động.
- Khi `DOCUMENT_STORE=postgres`, thống kê/lịch tài liệu của Teacher, số lượng tài liệu trên dashboard, danh sách và metrics document jobs của Admin đọc PostgreSQL. Câu hỏi và các job generation/evaluation vẫn dùng nguồn hiện tại. `AUDIT_STORE=postgres` cung cấp phân trang/lọc audit PostgreSQL cho Admin, nhưng chưa bật mặc định khi question/review còn ghi audit MongoDB.
- Reviewer lookup, phân công tự động, mention, dashboard và nhắc hạn duyệt đọc user từ nguồn được chọn bởi `USER_STORE`. Bootstrap không tạo/seed collection MongoDB cho các nhóm đã bật PostgreSQL; collection question/review/job còn được giữ đến khi chuyển chính các luồng đó.
- `modules/catalog/postgres_subject_repository.py` xử lý học phần, chương, CLO trong PostgreSQL. Ghi dữ liệu và audit tương ứng cùng transaction; cập nhật chương/CLO khóa học phần và ghép thay đổi với bản mới nhất để tránh ghi đè trường khác.
- Các đường đọc học phần của tài liệu, sinh câu hỏi, thống kê reviewer và trang quản trị dùng nguồn được chọn bởi `CATALOG_STORE`.
- `modules/notifications/postgres_repository.py` xử lý hộp thông báo, phân trang, số chưa đọc và đánh dấu đã đọc. Mọi truy vấn đều giới hạn theo `recipient_user_id`; bản ghi Mongo cũ có `is_read=true` nhưng thiếu `read_at` vẫn được coi là đã đọc.
- `modules/dictionary/postgres_repository.py` lưu từ điển và các từ khóa CORE/LEARNED/PENDING trong PostgreSQL; bước chunking và tác vụ AI học từ khóa chọn cùng một nguồn qua `DICTIONARY_STORE`.
- `modules/admin/postgres_moodle_target_repository.py` lưu Moodle target, trạng thái kích hoạt và lần kiểm tra kết nối trong PostgreSQL. Trang quản trị, thống kê và bước publish mock đọc cùng nguồn được chọn. Chỉ lưu tên biến môi trường token (`token_env_var`), không lưu giá trị token vào database.
- Khi `MOODLE_TARGET_STORE=postgres`, audit cho thao tác lưu/khóa/kiểm tra target được ghi cùng transaction PostgreSQL với target; không gửi bản audit thứ hai sang MongoDB.
- `modules/generation/llm/postgres_slots.py` cấp/duy trì/giải phóng slot bằng khóa hàng PostgreSQL và thời gian từ database; các API/worker dùng chung giới hạn đồng thời, dashboard đọc số slot từ cùng nguồn.
- Repository PostgreSQL cho tài khoản/phiên và cấu hình AI đã có từ giai đoạn trước.
- Khi `USER_STORE=postgres`, thống kê và lịch cá nhân vẫn đọc tài liệu/câu hỏi từ MongoDB vì đây còn là nguồn ghi chính của hai nhóm đó; không dùng các bảng PostgreSQL shadow copy có thể đã cũ.
- Upload file gốc dùng `LocalArtifactStorage`, tính SHA-256 khi ghi và trả URI local tương thích dữ liệu cũ; bước dedup artifact OCR cũng hash theo từng khối thay vì đọc nguyên file vào RAM. Đây là ranh giới lưu file local, chưa có provider object storage/cloud và chưa chuyển URI cũ thành khóa đối tượng.
- ChromaDB có chế độ `CHROMA_MODE=local` (mặc định) hoặc `CHROMA_MODE=http` cho server chung. API/worker dùng cùng `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_SSL`; nếu có `CHROMA_AUTH_TOKEN`, chỉ đưa vào header kết nối, không ghi vào metadata/log. `vector_collections.persist_uri` ghi endpoint không chứa token. Trước khi đổi từ local sang server phải sao chép/rebuild chỉ mục và đối soát ID/hash vector.

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

Đối soát tài liệu so ID, trạng thái, học phần, thứ tự trang, metadata artifact và hash nội dung của document/job/page/artifact. Nó kiểm tra `active_chunk_set_id` ở PostgreSQL trỏ đến chunk set `COMPLETED` đúng tài liệu ở MongoDB; OCR job nguồn, chunk và embedding cũng phải nối đúng ID. Báo cáo chỉ in số lỗi, không in nội dung tài liệu. Đây là kiểm tra metadata giữa hai database; chưa xác minh vector thực tế trong ChromaDB hoặc checksum file trên storage.

Sau khi đối chiếu dữ liệu và chạy kiểm thử tích hợp, bật các cờ cần thử trong cả API và worker:

```dotenv
USER_STORE=postgres
AI_CONFIG_STORE=postgres
CATALOG_STORE=postgres
NOTIFICATION_STORE=postgres
DICTIONARY_STORE=postgres
MOODLE_TARGET_STORE=postgres
LLM_SLOT_STORE=postgres
```

`CATALOG_STORE`, `NOTIFICATION_STORE` và `MOODLE_TARGET_STORE` yêu cầu `USER_STORE=postgres` để khóa ngoại owner/recipient/actor hợp lệ. Có thể bật từng nhóm sau khi dữ liệu nhóm đó đã được sao chép và kiểm tra. `MOODLE_TARGET_STORE` chỉ chuyển cấu hình target; các publication vẫn ghi MongoDB theo luồng câu hỏi. Không bật các cờ trên production khi câu hỏi, tài liệu, job và các luồng liên quan còn dùng MongoDB. Khởi động lại API/worker sau khi đổi cờ; không chuyển cờ trong lúc có ghi đồng thời ở hai nguồn.

Khi chuyển `LLM_SLOT_STORE`, chờ các lời gọi model đang chạy kết thúc trên toàn bộ API/worker rồi mới đổi cờ đồng loạt. Lease cũ ở MongoDB không tự chuyển theo worker; thay đổi cờ trong lúc chạy có thể khiến hai backend cấp slot song song vượt quá giới hạn.

Kiểm thử PostgreSQL yêu cầu `RUN_POSTGRES_INTEGRATION=1`, `POSTGRES_DSN` trỏ đến database kiểm thử đã migrate. Khi không đặt hai biến này, các ca tích hợp PostgreSQL sẽ được bỏ qua.

## Các việc còn lại trước cutover

1. Chuyển documents/OCR, generation/evaluation jobs, questions/versions/reviews, exams, Moodle, audit và các đường đọc thống kê sang PostgreSQL; giữ transaction và idempotency cho từng aggregate.
2. Chỉ để dữ liệu liên quan chunk/vector ở MongoDB, sau đó ngừng bootstrap các collection nghiệp vụ MongoDB. Không xóa collection cũ trước khi rehearsal, đối soát và hết thời gian rollback.
3. Thêm storage adapter local/object storage, triển khai Chroma server và kiểm tra phục hồi chỉ mục từ chunk MongoDB để hỗ trợ cloud.
4. Diễn tập trên bản sao dữ liệu, đóng băng ghi, sao chép delta, đối chiếu nội dung và chạy lại luồng Teacher → Reviewer → Admin trước khi đổi cờ production.

PostgreSQL, MongoDB, ChromaDB, file storage và model provider không có transaction chung. Các luồng đi qua nhiều hệ cần trạng thái, retry, outbox và tác vụ đối soát trước khi cutover.

## Log MongoDB trong Docker

Kiểm tra log thực tế 10 phút cho thấy các dòng INFO lặp chủ yếu đến từ kết nối `mongosh` của healthcheck (25 `client metadata`, 25 `Connection not authenticating`, 15 bắt tay lệnh đầu) và checkpoint WiredTiger mỗi phút (10 dòng). Compose giữ healthcheck nhanh `start_interval=5s` khi khởi động nhưng giãn `interval` sau khi khỏe từ 2 lên 5 phút. Thay đổi này chỉ có hiệu lực khi container được tạo lại; `logging.max-size/max-file` chỉ giới hạn dung lượng lưu log, không giảm số dòng. Vẫn xem các dòng WARN/ERROR khi chẩn đoán sự cố.
