# Database V2 - trạng thái triển khai và gap ưu tiên

Cập nhật: 2026-07-26. File này đi kèm `DATABASE_DESIGN_V2.md` để phục vụ báo cáo ngắn hạn: phần nào đã có trong code hiện tại, phần nào còn thiếu, và phần nào nên sửa tiếp theo mức độ ưu tiên chức năng.

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
- Bootstrap V2 đã tạo các collection chính: `users`, `subjects`, `documents`, `document_jobs`, `document_pages`, `chunk_sets`, `document_chunks`, `vector_collections`, `chunk_embeddings`, `generation_jobs`, `generation_runs`, `questions`, `question_versions`, `question_evaluations`, `question_reviews`, `audit_logs`, `moodle_publications`, `schema_meta`, `migration_id_map`; `users.generation_presets` lưu tối đa 12 preset sinh câu hỏi theo tài khoản.
- Role nghiệp vụ đã thống nhất ba loại: `Admin`, `Teacher`, `Reviewer`. User thường là `Teacher`; đăng ký public không được tự chọn role.
- Backend đã có dependency phân quyền cho `Teacher`, `Reviewer`, `Admin`; review/evaluation yêu cầu `Reviewer` hoặc `Admin` ở các endpoint workflow.
- Backend đã siết ownership bước đầu theo giảng viên: Teacher chỉ list/xem/sửa/xóa tài liệu và câu hỏi thuộc mình; generate/chunk/OCR status cũng kiểm tra quyền dùng tài liệu; Reviewer/Admin vẫn giữ luồng kiểm duyệt/quản trị theo role.
- Upload tài liệu đã có endpoint nghiệp vụ chính `POST /api/v1/documents/upload`: nhận PDF, tạo `documents`, lưu artifact gốc, tạo `document_jobs` loại `OCR` và enqueue OCR nền. Endpoint cũ `POST /api/v1/ocr/upload` vẫn giữ làm compatibility route.
- OCR/tài liệu đã có luồng lưu lại nội dung theo trang trong `document_pages`, có thể tái sử dụng thay vì OCR lại từ đầu.
- Auto-learning/dictionary đã chuyển nguồn đọc chính sang `document_pages`.
- Chunking/indexing đã có các lớp dữ liệu `chunk_sets`, `document_chunks`, `vector_collections`, `chunk_embeddings`; ChromaDB đóng vai trò index có thể rebuild.
- Sinh câu hỏi đã hỗ trợ `question_plan`: mỗi dòng chọn dạng câu hỏi, mức Bloom và số lượng; tổng số lượng được tính theo các dòng được thêm.
- Prompt sinh câu hỏi có thêm `instruction` của Teacher để nói rõ muốn câu hỏi về nội dung gì; frontend hiện gửi cùng nội dung này vào cả `instruction` và `target_heading` để vừa đưa vào prompt LLM vừa hỗ trợ RAG truy xuất đúng trọng tâm hơn.
- RAG `target_heading` đã chuyển thành ưu tiên mềm: nếu nội dung giảng viên nhập không khớp heading/mục lục, backend fallback về kết quả vector query thay vì làm job sinh câu hỏi thất bại.
- Kết quả sinh được lưu vào `questions` và `question_versions`; câu hỏi có `question_id`, `current_version`, versioning và optimistic concurrency qua `expected_version`.
- Câu hỏi sinh từ AI hiện mặc định ở trạng thái `DRAFT`; MongoDB validator đã cho phép `DRAFT`, và Teacher/Admin có endpoint `POST /questions/{id}/submit-review` để chuyển `DRAFT`/`NEEDS_REVISION` sang `PENDING`.
- Response sinh câu hỏi đã có `summary` theo từng dòng plan để biết sinh thiếu, trùng, invalid hoặc có warning.
- Logic sinh đã có bước lọc/tránh trùng câu hỏi trong cùng một job bằng fingerprint nội dung.
- Prompt output format đã ghi rõ shape options theo từng loại câu hỏi; backend có retry 1 lần khi LLM trả thiếu/sai format hoặc bị lọc trùng, giúp MCQ 4 đáp án ổn định hơn cho demo.
- Backend đã có collection/API nền cho AI evaluation và human review: `evaluation_jobs`, `question_evaluations`, `question_reviews`, cập nhật trạng thái review và ghi `audit_logs`.
- Đã có endpoint `POST /questions/{id}/evaluations/auto` để đưa câu hỏi vào hàng đợi AI evaluation. Khi Teacher gửi duyệt, backend cũng enqueue job nền bằng model cấu hình qua `EVALUATION_MODEL_PROVIDER` (mặc định `deepseek-r1`); job lưu `QUEUED/PROCESSING/COMPLETED/ERROR/STALE`, prompt/policy/source snapshot, attempt, lỗi và thời gian chạy.
- Prompt evaluator đã tách thành `backend/prompts/evaluation/question_quality.txt`, có rubric 5 thành phần (`faithfulness`, `contextual_relevancy`, `answer_relevancy`, `bloom_alignment`, `clo_alignment`), truyền kèm options, tối đa 3 source chunk đã rút gọn, Bloom/CLO và evaluation policy weights để local AI evaluator chấm rõ hơn.
- Đã có endpoint P0 `POST /questions/{id}/moodle-publications` để ghi nhận mock Moodle publication vào `moodle_publications`, chỉ cho câu hỏi đã được reviewer/admin duyệt; publication hiện lưu kèm payload export Moodle dạng GIFT/XML để có artifact đầu ra phục vụ demo.
- Bootstrap đã seed catalog `ai_models` cho `qwen`/`deepseek`/`deepseek-r1` và seed `prompt_templates` từ file prompt. `PromptBuilder` hiện dùng `PROMPT_SOURCE=file` theo mặc định; chỉ ưu tiên đọc prompt active từ DB khi cấu hình `PROMPT_SOURCE=db`.
- `generation_runs.model` và `question_evaluations.evaluator_model` đã snapshot từ `ai_models` khi catalog có dữ liệu.
- Backend đã có catalog API cho `subjects`, chapter, CLO, `ai_models`, `prompt_templates`, `evaluation_policies`; Admin có thể thêm dữ liệu nền thay vì sửa trực tiếp trong DB.
- Câu hỏi đã hỗ trợ gắn `clo_ids` khi tạo/sửa; backend validate CLO thuộc đúng subject và lưu snapshot CLO vào `question_versions.clos`.
- Auto evaluation đã ghi thêm `audit_logs` action `QUESTION_EVALUATED` để truy vết lần AI chấm.
- Đã có script `backend/scripts/rebuild_chromadb.py` để rebuild/upsert ChromaDB từ `document_chunks` + `chunk_embeddings` trong MongoDB, có `--dry-run` và `--reset-collection`.
- Đã sửa và chạy được smoke E2E backend `backend/scripts/run_e2e_ocr_questions.py`: OCR -> `document_pages` -> chunk/index -> RAG -> Qwen -> lưu câu hỏi V2 ở trạng thái `DRAFT` kèm source chunk snapshot.
- Đã có script `backend/scripts/database/set_user_role.py` để gán role `Admin`/`Teacher`/`Reviewer` cho user đã được Firebase login sync vào `rag_database.users`.
- Đã có tài khoản demo riêng qua endpoint custom token `/auth/demo-login`: `admin/admin` cho role `Admin` và `reviewer/reviewer` cho role `Reviewer`; script `backend/scripts/database/seed_demo_users.py` có thể seed lại Firebase user + MongoDB role.
- Đã có script `backend/scripts/database/seed_demo_review_flow.py` để tạo/refresh dữ liệu kiểm duyệt demo: document/chunk nguồn, CLO demo và câu hỏi `Q-DEMO-REVIEW-001` ở trạng thái `PENDING`/`NOT_STARTED` để Reviewer chạy AI evaluation rồi duyệt/yêu cầu sửa/từ chối.
- Đã có script `backend/scripts/database/backfill_ownership.py` để lấp owner cho dữ liệu V2 cũ thiếu `documents.uploaded_by_user_id`, `questions.created_by_user_id`, `question_versions.created_by_user_id`; DB demo hiện tại đã chạy apply với fallback owner `vpqcuong@gmail.com` và dry-run còn 0 bản ghi thiếu owner.
- Firebase Admin đã có cấu hình đọc service account local qua `backend/firebase-service-account.json`; file credential này phải giữ local và không commit.

### 2.2. Frontend phục vụ luồng Teacher

- Trang sinh câu hỏi đã có hai nguồn tài liệu: upload PDF mới hoặc chọn lại tài liệu đã OCR.
- Generate page hiện gọi `POST /api/v1/documents/upload` khi upload PDF mới; sau đó poll OCR status, gọi chunk/index rồi mới enqueue generation.
- Picker tài liệu đã OCR đã ẩn các tài liệu/pipeline `FAILED`, `CANCELLED`, `ARCHIVED` để tránh chọn nhầm tài liệu lỗi.
- Teacher có thể thêm/xóa nhiều dòng cấu hình câu hỏi; mỗi dòng quyết định loại câu hỏi, Bloom level và số lượng.
- Generate page chỉ còn một ô `Yêu cầu sinh câu hỏi`; nội dung được gửi vào cả `instruction` và `target_heading`.
- Generate page có lưu/xóa preset cấu hình sinh câu hỏi theo tài khoản qua API `/users/me/generation-presets`; localStorage chỉ còn là cache/fallback và có migrate mẫu cũ lên server khi server chưa có preset.
- Generate page hiển thị thời gian upload, OCR, chunk/index, sinh câu hỏi và tổng thời gian của lần chạy hiện tại; nếu chọn tài liệu đã OCR/index sẵn thì hiển thị trạng thái tái sử dụng. Frontend gửi `client_telemetry` khi enqueue generation và backend persist `generation_jobs.metrics` gồm timing client/server cho lần sinh.
- Ô nhập số lượng đã chuyển sang kiểu dễ thao tác hơn cho việc thay số.
- Giao diện chọn loại câu hỏi/Bloom đã được chỉnh để chữ trong ô rõ hơn.
- Sau khi sinh, giao diện có preview câu hỏi nháp, hiển thị mã câu hỏi/version nếu backend đã lưu.
- Teacher có thể sửa nội dung câu hỏi nháp, đáp án, giải thích và lựa chọn theo từng loại câu hỏi trước khi lưu.
- Có thao tác bỏ/xóa câu hỏi nháp khỏi danh sách sau khi sinh.
- Có thao tác gửi từng câu hỏi hoặc gửi hàng loạt câu hỏi nháp sang hàng đợi kiểm duyệt.
- Có hiển thị summary khi job sinh bị thiếu câu, trùng câu hoặc có cảnh báo.
- Manage page đã có lọc theo trạng thái review, tài liệu, Bloom/search và có nút gửi câu hỏi `DRAFT`/`NEEDS_REVISION` sang kiểm duyệt.
- Điều hướng frontend đã tách role rõ cho demo: `Teacher` vào `/sinh-cau-hoi` và `/quan-ly`; `Reviewer` vào `/kiem-duyet`; `Admin` vào `/danh-muc` và `/quan-ly-nguoi-dung`. Khi chưa đăng nhập, header chỉ hiển thị nhóm công khai; sau đăng nhập mới hiện các nhóm quyền theo role, và route guard vẫn chuyển sang `/dang-nhap` nếu truy cập trực tiếp route cần quyền.
- Route `/ho-so` đã được bảo vệ bằng role `Admin`/`Teacher`/`Reviewer`.
- Login page đã redirect theo đúng role fallback: `Teacher` về `/sinh-cau-hoi`, `Reviewer` về `/kiem-duyet`, `Admin` về `/danh-muc` nếu route vừa bấm không thuộc quyền.
- Đã có trang riêng `/kiem-duyet` cho Reviewer ở UI demo: lọc theo trạng thái, dạng câu hỏi, Bloom, màu/score; xem evidence/source sâu hơn; chạy AI evaluation, duyệt, yêu cầu sửa, từ chối, xem lịch sử evaluation/review/publication và ghi nhận mock Moodle publication.
- Form sửa câu hỏi ở Manage đã dùng cùng logic structured option editor với Generate preview.
- Admin đã có trang `/danh-muc` để quản trị subject/chapter/CLO, model local, prompt template và evaluation policy ở mức demo.
- Manage và Reviewer queue đã hiển thị CLO; modal sửa câu hỏi cho phép chọn lại CLO theo subject hiện hành.

## 3. Còn thiếu hoặc chưa nên claim hoàn tất

- Reviewer queue đã có ở mức P1 và đã dùng filter/phân trang server-side; thao tác hàng loạt vẫn enqueue tuần tự trên trang hiện tại, chưa có audit chi tiết cho từng batch.
- AI evaluator đã gọi local LLM provider cấu hình qua `EVALUATION_MODEL_PROVIDER` qua `evaluation_jobs`; nếu model timeout/parser lỗi thì câu hỏi chuyển `ERROR` để Reviewer retry hoặc duyệt thủ công có lý do, không ghi heuristic dưới tên model local. Vẫn cần benchmark/hardening parser với nhiều câu hỏi thật trước production.
- MCQ generation đã được hardening format/retry ở mức demo; vẫn cần benchmark chất lượng câu hỏi MCQ với nhiều PDF thật/model thật trước production.
- `ai_models`, `prompt_templates`, `evaluation_policies` đã có UI quản trị demo; chưa có workflow promote version chặt chẽ, review/approve version prompt/model hoặc rollback version.
- Preset cấu hình sinh câu hỏi đã lưu server-side trong `users.generation_presets`; còn thiếu E2E UI thật để chứng minh đồng bộ giữa nhiều trình duyệt/tài khoản demo.
- Thời gian xử lý đã được persist bước đầu trong `generation_jobs.metrics` cho từng job sinh câu hỏi; chưa có dashboard/aggregation telemetry nhiều lần chạy hoặc collection phân tích riêng.
- Moodle publication P0 ghi nhận mock publication/idempotency trong DB và lưu payload export GIFT/XML; chưa gọi Moodle API thật.
- `keywords` chưa thay thế hoàn toàn compatibility collection/dictionary cũ; cần quyết định migrate hẳn hay giữ song song có tài liệu rõ.
- Subject/Chapter/CLO đã có catalog và mapping câu hỏi ở mức demo; còn thiếu import/backfill dữ liệu thật, sửa/xóa mềm CLO, và rule bắt buộc CLO theo từng học phần.
- Upload hiện chủ yếu phục vụ PDF; DOC/DOCX chưa phải end-to-end nếu chưa có converter/normalizer.
- Endpoint upload đã nhận sẵn `subject_id`/`chapter_id` dạng form field, nhưng Generate page chưa có UI chọn học phần/chương lúc upload; tài liệu upload từ Generate page hiện vẫn rơi về subject mặc định nếu không truyền metadata.
- Tài khoản demo `Admin`/`Reviewer` đã có thể seed bằng `python scripts/database/seed_demo_users.py`; dữ liệu hàng đợi Reviewer demo có thể refresh bằng `python scripts/database/seed_demo_review_flow.py`. Nếu muốn gán role cho tài khoản Google thật thì vẫn dùng `python scripts/database/set_user_role.py --email <email> --role Reviewer` sau khi user đã đăng nhập Firebase ít nhất một lần.
- Cần kiểm tra lại migration/index/validator trên MongoDB thật của nhóm; môi trường hiện tại đã pass `scripts/database/verify_v2.py`, nhưng DB deploy/demo khác vẫn phải chạy lại.
- Ownership theo giảng viên đã có P0 cho tài liệu/câu hỏi và DB demo đã backfill owner; phần còn thiếu cho production là policy chia sẻ/chuyển owner nếu nhiều giảng viên dùng chung học liệu.
- Cần thêm E2E UI/API có auth thật cho các luồng rủi ro: chọn lại OCR document, sinh nhiều dòng plan, tránh trùng, sửa/lưu version, reviewer approve/reject. Hiện đã có backend smoke E2E cho OCR/chunk/RAG/generate/persist.
- Cần smoke test lại luồng guest chỉ thấy menu công khai -> truy cập trực tiếp route cần quyền -> đăng nhập Google -> quay lại đúng route; đã browser-test redirect guest `Sinh Câu Hỏi` -> `/dang-nhap` trước khi đổi header, nhưng chưa test lại với tài khoản Google thật trong phiên người dùng.

## 4. Ưu tiên sửa tiếp

### P0 - Trước báo cáo/demo gần nhất

1. Restart backend với Firebase service account đúng project và smoke test Google login.
2. Smoke test điều hướng public/protected: guest chỉ thấy menu công khai, truy cập trực tiếp route cần quyền thì về login; sau đăng nhập, `Teacher` quay lại route Teacher nếu có quyền, `Reviewer` về `/kiem-duyet`, `Admin` về `/danh-muc`.
3. Demo chắc luồng Teacher: chọn tài liệu đã OCR -> thêm nhiều dòng plan -> nhập instruction -> sinh câu hỏi -> xem summary/thời gian xử lý -> sửa/lưu/bỏ câu hỏi nháp -> gửi kiểm duyệt.
4. Refresh dữ liệu hàng đợi demo bằng `python scripts/database/seed_demo_review_flow.py` nếu cần câu hỏi chắc chắn đang `PENDING`/`NOT_STARTED`.
5. Demo luồng Reviewer P0: chọn câu hỏi -> AI đánh giá bằng model cấu hình -> duyệt/yêu cầu sửa/từ chối -> xem lịch sử.
6. Chạy lại `python scripts/database/verify_v2.py` trên đúng MongoDB dùng demo để kiểm tra collection/index/validator chính của V2.
7. Chuẩn bị tài khoản kiểm duyệt: dùng demo `reviewer/reviewer` hoặc gán role cho tài khoản thật bằng Admin UI/`scripts/database/set_user_role.py`.
8. Chạy `python scripts/run_e2e_ocr_questions.py` nếu cần bằng chứng backend smoke OCR/chunk/RAG/generate/persist trước buổi demo; có thể test MCQ bằng `E2E_QUESTION_TYPE=trac_nghiem E2E_NUM_QUESTIONS=1`.
9. Với câu hỏi đã `APPROVED`, dùng Reviewer queue hoặc endpoint `/questions/{id}/moodle-export?format=gift|xml` để lấy artifact export Moodle phục vụ báo cáo/demo.

### P1 - Đã xử lý ở mức demo/mid-term

1. Tách Reviewer UI thành queue riêng: lọc server-side theo trạng thái/dạng/Bloom/score/màu, phân trang theo DB, xem source/evidence sâu hơn và có batch action giới hạn.
2. Nâng auto evaluator sang local LLM provider cấu hình bằng `EVALUATION_MODEL_PROVIDER` (mặc định `deepseek-r1`, có thể dùng `ollama:<model>`), chạy qua `evaluation_jobs`, lưu raw response/evidence/prompt snapshot và trạng thái lỗi rõ ràng khi model local lỗi.
3. Đồng bộ form sửa câu hỏi ở Manage với editor structured options đã có ở Generate preview.
4. Seed/đọc catalog `ai_models`, `prompt_templates`, snapshot model vào generation/evaluation records.

### P2 - Đã xử lý ở mức demo, chưa gồm Moodle thật

1. Backend catalog APIs cho subject/chapter/CLO, AI models, prompt templates và evaluation policies.
2. Admin UI `/danh-muc` để thêm/sửa dữ liệu nền ở mức demo.
3. Mapping CLO vào `question_versions.clos`; Manage edit modal chọn lại CLO theo subject, Reviewer queue hiển thị CLO khi duyệt.
4. Audit cho auto evaluation qua `audit_logs.action = QUESTION_EVALUATED`.
5. Script `backend/scripts/rebuild_chromadb.py` rebuild/upsert ChromaDB từ MongoDB, phục vụ chứng minh VectorDB là index có thể tái tạo.

### P2 - Còn lại sau demo này

1. Moodle publication worker/API thật và retry bằng `idempotency_key`; tạm hoãn vì chưa có Moodle thật.
2. Workflow promote/rollback version prompt, model và evaluation policy thay vì chỉ lưu version mới qua form Admin.
3. Migration/backfill dữ liệu legacy khi nhập DB khác, gồm `pages -> document_pages`, user role, owner tài liệu/câu hỏi, dictionary/keyword và mapping CLO thật.
4. Thêm UI chọn học phần/chương khi upload tài liệu mới trên Generate/Manage page, rồi truyền `subject_id`/`chapter_id` vào `/documents/upload`.
5. Audit đầy đủ cho document/question/publication và audit riêng cho batch reviewer actions.
6. Soft delete/deactivate UI cho subject/chapter/CLO và rule bắt buộc CLO theo từng học phần.

## 5. Gợi ý nói trong báo cáo

- "File `DATABASE_DESIGN_V2.md` là đặc tả chính; file gap đi kèm ghi rõ trạng thái triển khai để tránh claim quá mức."
- "Schema V2 đã chuyển nội dung authoritative về MongoDB, còn ChromaDB là index phục vụ truy hồi và có thể rebuild."
- "Question bank đã có `questions` và `question_versions`, nên việc chỉnh sửa không ghi đè mất lịch sử."
- "Reviewer là role bắt buộc trong thiết kế Human-in-the-loop; bản P1 đã có queue kiểm duyệt riêng, xem evidence và thao tác duyệt."
- "Luồng Teacher là ưu tiên demo trước: tái sử dụng tài liệu OCR, tạo nhiều dòng yêu cầu sinh câu hỏi, chỉnh nháp, lưu version và gửi câu hỏi sang kiểm duyệt."
- "Trang public chỉ hiển thị các mục công khai; các module theo quyền chỉ xuất hiện sau đăng nhập và vẫn được kiểm soát thêm bằng route guard/backend role."
- "Moodle publication ở bản P0 là mock publication ghi vào DB kèm export GIFT/XML; tích hợp Moodle API thật là bước tiếp theo."
- "AI evaluator ở bản P1 ưu tiên local LLM qua Ollama, chạy nền qua `evaluation_jobs`; nếu lỗi thì lưu `ERROR` để Reviewer retry hoặc duyệt thủ công có lý do, production cần benchmark evaluator riêng."

## 6. Handoff nhanh cho chat tiếp theo

- Branch hiện tại: `nckh/v2-demo-hardening`.
- Các thay đổi hiện vẫn chưa stage/commit.
- Frontend build gần nhất: `npm run build` pass, còn warning Vite về chunk JS lớn hơn 500KB.
- Browser-test cũ trước khi đổi header: guest vào `/trang-chu` thấy đủ 9 mục menu, không đè nút login; bấm `Sinh Câu Hỏi` thì chuyển sang `/dang-nhap`. Header hiện đã đổi sang chỉ hiện nhóm công khai khi chưa đăng nhập, cần smoke test lại nếu muốn chốt UI mới.
- Backend smoke/test đã chạy trước đó: `tests/test_schema_v2.py`, `scripts/database/verify_v2.py`, `scripts/database/bootstrap_v2.py`, và `scripts/run_e2e_ocr_questions.py` đều pass trên môi trường local lúc test.
- Việc nên làm ngay khi sang chat mới: smoke test Google login thật trên browser người dùng, sau đó chạy end-to-end Teacher -> Reviewer trên đúng DB demo.
- Không nên claim production: Moodle thật, telemetry dashboard/aggregation, E2E UI/auth tự động, benchmark chất lượng câu hỏi, sharing/chuyển owner nhiều giảng viên, DOC/DOCX end-to-end.
