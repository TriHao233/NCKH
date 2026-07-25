# Database V2 - trạng thái triển khai và gap ưu tiên

Cập nhật: 2026-07-25. File này đi kèm `DATABASE_DESIGN_V2.md` để phục vụ báo cáo ngắn hạn: phần nào đã có trong code hiện tại, phần nào còn thiếu, và phần nào nên sửa tiếp theo mức độ ưu tiên chức năng.

Quy ước đọc:

- **Đã thực hiện**: đã thấy trong backend/frontend hiện tại hoặc đã có bootstrap/schema/API tương ứng.
- **Còn thiếu**: chưa đủ để claim là end-to-end hoàn chỉnh, hoặc mới có schema nhưng chưa có workflow/UI/worker.
- **Nên sửa**: ưu tiên thực dụng cho demo và báo cáo, không phải toàn bộ backlog dài hạn.

## 1. Tài liệu database đã chuẩn hóa

- `DATABASE_DESIGN_V2.md` là file thiết kế database chính theo đúng tên đang được repo theo dõi.
- Nội dung chi tiết trước đây nằm ở `DATABASE_DESIGN_V2_02.md` đã được đưa về `DATABASE_DESIGN_V2.md`.
- `DATABASE_DESIGN_V2_02.md` chỉ nên xem như bản nháp/duplicate cũ, không nên dùng làm nguồn chính khi báo cáo.
- Khi code và tài liệu còn lệch, ưu tiên mô tả theo trạng thái backend hiện tại rồi ghi rõ gap ở file này.

## 2. Đã thực hiện

### 2.1. Database và backend

- Có phân tách dữ liệu đăng nhập tối giản ở `NCKH.User` và dữ liệu nghiệp vụ/RAG ở `rag_database`.
- Bootstrap V2 đã tạo các collection chính: `users`, `subjects`, `documents`, `document_jobs`, `document_pages`, `chunk_sets`, `document_chunks`, `vector_collections`, `chunk_embeddings`, `generation_jobs`, `generation_runs`, `questions`, `question_versions`, `question_evaluations`, `question_reviews`, `audit_logs`, `moodle_publications`, `schema_meta`, `migration_id_map`.
- Role nghiệp vụ đã thống nhất ba loại: `Admin`, `Teacher`, `Reviewer`. User thường là `Teacher`; đăng ký public không được tự chọn role.
- Backend đã có dependency phân quyền cho `Teacher`, `Reviewer`, `Admin`; review/evaluation yêu cầu `Reviewer` hoặc `Admin` ở các endpoint workflow.
- OCR/tài liệu đã có luồng lưu lại nội dung theo trang trong `document_pages`, có thể tái sử dụng thay vì OCR lại từ đầu.
- Auto-learning/dictionary đã chuyển nguồn đọc chính sang `document_pages`.
- Chunking/indexing đã có các lớp dữ liệu `chunk_sets`, `document_chunks`, `vector_collections`, `chunk_embeddings`; ChromaDB đóng vai trò index có thể rebuild.
- Sinh câu hỏi đã hỗ trợ `question_plan`: mỗi dòng chọn dạng câu hỏi, mức Bloom và số lượng; tổng số lượng được tính theo các dòng được thêm.
- Prompt sinh câu hỏi có thêm `instruction` của Teacher để nói rõ muốn câu hỏi về nội dung gì.
- Kết quả sinh được lưu vào `questions` và `question_versions`; câu hỏi có `question_id`, `current_version`, versioning và optimistic concurrency qua `expected_version`.
- Response sinh câu hỏi đã có `summary` theo từng dòng plan để biết sinh thiếu, trùng, invalid hoặc có warning.
- Logic sinh đã có bước lọc/tránh trùng câu hỏi trong cùng một job bằng fingerprint nội dung.
- Backend đã có collection/API nền cho AI evaluation và human review: `question_evaluations`, `question_reviews`, cập nhật trạng thái review và ghi `audit_logs`.
- Đã có endpoint P0 `POST /questions/{id}/evaluations/auto` để tạo AI evaluation tự động bằng heuristic nội bộ, ghi score/evidence vào `question_evaluations` và cập nhật `quality_summary`.
- Đã có endpoint P0 `POST /questions/{id}/moodle-publications` để ghi nhận mock Moodle publication vào `moodle_publications`, chỉ cho câu hỏi đã được reviewer/admin duyệt.
- Firebase Admin đã có cấu hình đọc service account local qua `backend/firebase-service-account.json`; file credential này phải giữ local và không commit.

### 2.2. Frontend phục vụ luồng Teacher

- Trang sinh câu hỏi đã có hai nguồn tài liệu: upload PDF mới hoặc chọn lại tài liệu đã OCR.
- Teacher có thể thêm/xóa nhiều dòng cấu hình câu hỏi; mỗi dòng quyết định loại câu hỏi, Bloom level và số lượng.
- Ô nhập số lượng đã chuyển sang kiểu dễ thao tác hơn cho việc thay số.
- Giao diện chọn loại câu hỏi/Bloom đã được chỉnh để chữ trong ô rõ hơn.
- Sau khi sinh, giao diện có preview câu hỏi nháp, hiển thị mã câu hỏi/version nếu backend đã lưu.
- Teacher có thể sửa nội dung câu hỏi nháp, đáp án, giải thích và lựa chọn theo từng loại câu hỏi trước khi lưu.
- Có thao tác bỏ/xóa câu hỏi nháp khỏi danh sách sau khi sinh.
- Có hiển thị summary khi job sinh bị thiếu câu, trùng câu hoặc có cảnh báo.
- Điều hướng frontend đã có phân quyền cơ bản: `Admin`/`Teacher` vào sinh câu hỏi, `Admin`/`Teacher`/`Reviewer` vào quản lý, `Admin` vào quản trị user.
- Trang quản lý đã có thao tác P0 cho Reviewer/Admin: chạy AI evaluation, duyệt, yêu cầu sửa, từ chối, xem lịch sử evaluation/review/publication và ghi nhận mock Moodle publication.

## 3. Còn thiếu hoặc chưa nên claim hoàn tất

- Reviewer đã có thao tác P0 trên trang quản lý, nhưng chưa có một trang reviewer queue riêng tối ưu cho khối lượng lớn.
- AI evaluator P0 đang là heuristic nội bộ để phục vụ demo; chưa phải model local evaluator thật theo đúng yêu cầu production.
- Trang quản lý câu hỏi hiện chưa có form sửa structured options đầy đủ như preview sau khi sinh; phần sửa ngoài luồng Generate vẫn còn đơn giản hơn.
- `ai_models`, `prompt_templates`, `evaluation_policies` đã có trong thiết kế/bootstrap nhưng generation vẫn chủ yếu dùng config/prompt hiện tại, chưa chuyển hẳn sang catalog trong DB.
- Moodle publication P0 mới ghi nhận mock publication/idempotency trong DB; chưa gọi Moodle API thật hoặc export định dạng Moodle XML/GIFT end-to-end.
- `keywords` chưa thay thế hoàn toàn compatibility collection/dictionary cũ; cần quyết định migrate hẳn hay giữ song song có tài liệu rõ.
- Subject/Chapter/CLO management chưa đầy đủ; nếu báo cáo claim theo chuẩn đầu ra thì cần CRUD/catalog và mapping dữ liệu thật.
- Upload hiện chủ yếu phục vụ PDF; DOC/DOCX chưa phải end-to-end nếu chưa có converter/normalizer.
- Cần seed/mapping tài khoản `Reviewer` thật trước demo, vì code có role nhưng dữ liệu người dùng phải được gán role đúng.
- Cần kiểm tra lại migration/index/validator trên MongoDB thật của nhóm; có thiết kế và bootstrap không đồng nghĩa target DB đã được migrate.
- Phân quyền ownership tài liệu/câu hỏi còn ở mức role-based; nếu nhiều giảng viên dùng chung, cần rõ ai được xem/sửa tài liệu/câu hỏi của ai.
- Cần thêm test end-to-end cho các luồng rủi ro: chọn lại OCR document, sinh nhiều dòng plan, tránh trùng, sửa/lưu version, reviewer approve/reject.

## 4. Ưu tiên sửa tiếp

### P0 - Trước báo cáo/demo gần nhất

1. Restart backend với Firebase service account đúng project và smoke test Google login.
2. Demo chắc luồng Teacher: chọn tài liệu đã OCR -> thêm nhiều dòng plan -> nhập instruction -> sinh câu hỏi -> xem summary -> sửa/lưu/bỏ câu hỏi nháp.
3. Demo luồng Reviewer P0: chọn câu hỏi -> AI đánh giá -> duyệt/yêu cầu sửa/từ chối -> xem lịch sử.
4. Kiểm tra target MongoDB đã có các collection/index chính của V2, đặc biệt `document_pages`, `generation_jobs`, `generation_runs`, `questions`, `question_versions`.
5. Chuẩn bị ít nhất một tài khoản `Reviewer` thật trong DB trước demo.

### P1 - Quan trọng sau demo Teacher

1. Tách Reviewer UI thành queue riêng: lọc theo môn/chương/Bloom/score, xem source/evidence sâu hơn và thao tác hàng loạt.
2. Thay heuristic evaluator bằng local evaluator model thật, lưu raw response và evidence chặt hơn.
3. Đồng bộ form sửa câu hỏi ở Manage với editor structured options đã có ở Generate preview.
4. Chuyển model/prompt/evaluation policy sang đọc từ DB và snapshot vào `generation_runs`/`question_evaluations`.

### P2 - Hoàn thiện dữ liệu và tích hợp

1. Moodle publication worker/API thật và retry bằng `idempotency_key`.
2. Subject/Chapter/CLO catalog và mapping câu hỏi theo chuẩn đầu ra.
3. Migration/backfill dữ liệu legacy, gồm `pages -> document_pages`, user role, dictionary/keyword.
4. Audit đầy đủ cho document/question/evaluation/publication.
5. Script rebuild ChromaDB từ MongoDB để chứng minh vector index có thể tái tạo.

## 5. Gợi ý nói trong báo cáo

- "File `DATABASE_DESIGN_V2.md` là đặc tả chính; file gap đi kèm ghi rõ trạng thái triển khai để tránh claim quá mức."
- "Schema V2 đã chuyển nội dung authoritative về MongoDB, còn ChromaDB là index phục vụ truy hồi và có thể rebuild."
- "Question bank đã có `questions` và `question_versions`, nên việc chỉnh sửa không ghi đè mất lịch sử."
- "Reviewer là role bắt buộc trong thiết kế Human-in-the-loop; bản P0 đã có thao tác duyệt và lịch sử trên trang quản lý."
- "Luồng Teacher là ưu tiên demo trước: tái sử dụng tài liệu OCR, tạo nhiều dòng yêu cầu sinh câu hỏi, chỉnh nháp và lưu version."
- "Moodle publication ở bản P0 là mock publication ghi vào DB; tích hợp Moodle thật là bước tiếp theo."
