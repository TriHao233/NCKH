# Phân tích tổng quan hệ thống và backlog ưu tiên theo vai trò

Cập nhật: 2026-07-27

## Handoff nhanh cho chat tiếp theo

**Trạng thái mới nhất 2026-07-27:**

- Đã hoàn tất `P1-TEA-02 — Quản lý pipeline tài liệu`.
- Đã audit/chốt `P1-TEA-03 — Hoàn thiện exam lifecycle`.
- Đã audit/chốt `P1-TEA-04 — Server-side question picker cho đề thi`.
- Đã hoàn tất core `P1-TEA-05 — Bộ lọc ngân hàng câu hỏi` với saved filters.
- Đã audit/chốt `P0-01 — Khóa demo login ngoài môi trường demo`.
- Đã audit/chốt `P0-02 — Sửa ownership và authorization cho đề thi`.
- Đã audit/chốt `P0-03 — Thống nhất permission matrix frontend/backend`.
- Đã audit/chốt `P0-04 — Bảo vệ tài khoản Admin cuối cùng`.
- Đã audit/chốt `P0-05 — Xử lý đúng trạng thái Moodle`.
- Đã audit/chốt `P0-06 — Recovery cho job bị treo`.
- Đã audit/chốt `P0-07 — Bộ test tối thiểu cho luồng quan trọng`.
- Đã audit/chốt `P1-TEA-01 — Version history, diff và restore`.
- Đã hoàn thiện/chốt `P1-ADM-01 — Operations Dashboard`.
- Đã audit/chốt `P1-ADM-02 — Job Management`.
- Đã audit/chốt `P1-ADM-03 — Audit Log API và UI`.
- Đã audit/chốt `P1-ADM-04 — Full lifecycle môn/chương/CLO`.
- Đã audit/chốt `P1-ADM-05 — Quản trị model/prompt/policy thật`.
- Đã audit/chốt `P1-ADM-06 — Quản lý Moodle target`.
- Đã audit/chốt `P1-REV-01 — Phân công và claim review`.
- Đã audit/chốt `P1-REV-02 — Bộ lọc nghiệp vụ đầy đủ`.
- Checklist `P1-TEA-02` hiện đã xong 6/6:
  - xem OCR pages;
  - sửa OCR trước khi chunk/index;
  - xem lỗi/job history theo từng bước;
  - retry/cancel OCR job từ Document sidebar và Admin Jobs;
  - retry/cancel chunking;
  - re-index khi embedding model thay đổi.
- Các commit liên quan gần nhất:
  - `82f13ed feat: show document pipeline job history`
  - `0ec5562 feat: retry document pipeline jobs`
  - `5c8db6c feat: show document OCR pages`
  - `914d07c feat: retry chunk pipeline jobs`
  - `864e05d feat: edit document OCR pages`
  - `c5479bf feat: reindex document embeddings`
- Thay đổi local chưa commit trong lượt này:
  - siết validation đề thi để chỉ nhận câu hỏi có `approved_version_id` đúng current version và có subject khớp đề;
  - matrix availability/auto-pick chỉ tính câu hỏi thật sự usable cho đề;
  - thêm test lifecycle cho approved version, subject và availability.
  - thêm saved filters theo user cho `ManagePage`, lưu trong `localStorage`;
  - tách util/test cho saved question filters và mở rộng frontend test script.
  - thêm test demo-login không tự mở lại Firebase/app user demo đã bị khóa.
  - thêm filter repository `approved_current_only` cho exam picker/auto-pick để không hiện câu stale approved version;
  - thêm test ownership đề thi phủ update/status/delete/matrix/pool/variant methods.
  - frontend route guard và menu cùng dùng permission map trung tâm `PROTECTED_ROUTE_ROLES`/`canAccessPath`;
  - thêm test đảm bảo mọi protected route trong `App.jsx` đều được khai báo trong permission map.
  - thêm test guard Moodle: `mock=false` bị chặn khi chưa cấu hình sync thật, và production non-demo không cho ghi mock.
  - thêm test `DRAFT`/`NEEDS_REVISION` -> `PENDING` khi Teacher submit câu hỏi, gồm idempotent khi đã `PENDING`.
  - thêm GitHub Actions workflow `.github/workflows/p0-tests.yml` chạy backend P0 tests, frontend tests và frontend build.
  - bổ sung filter người tạo và khoảng ngày cho Admin Jobs API/UI.
  - thêm test Admin Job list lọc theo thời gian và test retry evaluation qua Admin service có background task/audit.
  - siết Moodle target `allowed_roles` không được rỗng và enforce role khi publish/retry publication.
  - thêm UI checkbox Admin/Reviewer để quản lý ai được publish trên từng Moodle target.
  - thêm `/users/reviewers` và dropdown Reviewer/Admin active cho modal gán reviewer.
  - thêm test reviewer options chỉ trả Reviewer/Admin active cho assignment.
  - thêm filter server-side `waiting_hours_min` và `overdue_only` cho reviewer queue.
  - thêm UI filter “thời gian chờ” và “quá hạn lock” trong `ReviewQueuePage`.
  - audit/chốt Source Viewer: backend trả PDF metadata/OCR pages/source excerpt/chunk hash/stale warnings; UI mở PDF đúng trang, tab OCR và citation metadata.
  - audit/chốt structured review: form rubric/checklist/notes/revision issues đã thay `window.prompt`, autosave draft và backend validate reject/override.
  - thêm test/chốt notification resubmit: Teacher gửi lại câu hỏi từ `NEEDS_REVISION` tạo `QUESTION_RESUBMITTED` cho Reviewer, deep link về `/kiem-duyet?questionId=...`.
  - audit/chốt Reviewer dashboard: workload, lock quá hạn, review 7d/30d, override AI, thời gian xử lý trung bình và thống kê theo môn đã có API/UI/test.
  - hoàn thiện Admin Operations Dashboard với job breakdown OCR/chunk/generation/evaluation, quality color, publication status và model latency/error rate 30 ngày.
  - audit/chốt Admin Audit Log API/UI: filter actor/entity/action/date/search, before/after/changes/metadata và UI read-only.
  - audit/chốt catalog lifecycle môn/chương/CLO: sửa/sắp xếp/activate-deactivate, chặn trùng mã, không hard-delete và hiển thị usage counts.
  - audit/chốt model/prompt/policy admin: health-check model, test prompt, activate/deactivate/rollback version, runtime config và cảnh báo `PROMPT_SOURCE`.
- Đã kiểm tra sau thay đổi cuối:
  - backend `python -m pytest tests/test_schema_v2.py -q`: `95 passed`
  - frontend `npm --prefix frontend test`: `7 passed`
  - frontend `npm --prefix frontend run build`: pass, còn warning bundle >500 kB của Vite.
  - `git diff --check`: không có whitespace error, chỉ còn warning LF sẽ được Git đổi sang CRLF trên Windows.

**Còn lại theo backlog trong file này:**

- Nếu tính `P0 + P1` core backlog: còn `0` epic/mục chưa chốt trong file.
- Nếu tính cả `P2`: còn `17` epic/mục.
- Chi tiết:
  - `P0`: 7 mục (`P0-01` đến `P0-07`); đã chốt toàn bộ, còn 0 mục.
  - `P1`: 17 mục tổng; toàn bộ Teacher/Admin/Reviewer P1 đã audit/chốt, còn 0 mục.
  - `P2`: 17 mục mở rộng/năng suất.
- Ghi chú tiếp theo: P0 và P1 core đã xong; nếu làm tiếp thì chuyển sang P2 mở rộng/năng suất hoặc hardening theo test/QA.

**Lưu ý repo:**

- `docs/` đang bị ignore bởi `.gitignore` (`/docs/`), nên thay đổi trong file này là ghi local để handoff, không tự xuất hiện trong `git status`.
- Worktree hiện có các thay đổi local chưa commit kể trên; untracked cũ vẫn gồm `.codegraph/` và `backend/data/chunk_outputs/6a64be8990e1e8800c33bb24_chunks_20260725_211944.md`.

Tài liệu này tổng hợp trạng thái code hiện tại của QBankCTU, các chức năng đã có,
các khoảng trống cần hoàn thiện cho `Admin`, `Reviewer`, `Teacher`, và thứ tự ưu
tiên triển khai từ P0 đến P3.

Phạm vi đánh giá là source code hiện có trong `frontend/`, `backend/` và các tài
liệu thiết kế trong `docs/`. Đây là đánh giá tĩnh theo code, chưa thay thế kiểm
thử tích hợp trên môi trường triển khai thật.

## 1. Kết luận ngắn

Hệ thống đã có một luồng nghiệp vụ end-to-end tương đối đầy đủ để demo:

```text
Teacher upload PDF
    -> OCR
    -> chunk/index vào ChromaDB
    -> RAG + LLM sinh câu hỏi nháp
    -> Teacher chỉnh sửa và gửi duyệt
    -> AI evaluation
    -> Reviewer duyệt/yêu cầu sửa/từ chối
    -> đưa câu hỏi đã duyệt vào đề thi hoặc export Moodle
```

Mức độ hoàn thiện theo vai trò:

| Vai trò | Đánh giá hiện tại |
|---|---|
| Teacher | Hoàn thiện nhất; đã có luồng tài liệu, sinh câu hỏi, quản lý câu hỏi, tạo đề và lịch công việc |
| Reviewer | Đủ cho demo kiểm duyệt; còn thiếu phân công công việc, kiểm chứng nguồn thuận tiện và cộng tác với Teacher |
| Admin | Có CRUD người dùng và cấu hình nền; chưa có trung tâm vận hành, giám sát, audit và quản trị tích hợp |

Hệ thống hiện phù hợp với mức **prototype/demo có dữ liệu thật**, nhưng chưa nên
claim là production-ready vì còn thiếu bộ test tối thiểu, một số workflow
Reviewer/Admin và Moodle thật nếu phạm vi sản phẩm yêu cầu đồng bộ ngoài hệ thống.

## 2. Kiến trúc và các khối chức năng hiện tại

### 2.1. Frontend

- React 18 + Vite.
- Firebase Authentication.
- Route guard theo ba role: `Admin`, `Teacher`, `Reviewer`.
- Các trang nghiệp vụ chính:
  - `GeneratePage`: upload/tái sử dụng tài liệu, sinh và chỉnh sửa câu hỏi.
  - `ManagePage`: quản lý câu hỏi, tài liệu và lịch sử workflow.
  - `ReviewQueuePage`: AI evaluation và human review.
  - `ExamListPage`, `ExamBuilderPage`: tạo đề, ma trận, mã đề, preview và PDF.
  - `CatalogAdminPage`: môn học, chương, CLO, model, prompt, policy.
  - `UsersAdminPage`: quản lý người dùng.
  - `TaskCalendarPage`, `UserProfile`: lịch và hồ sơ cá nhân.

### 2.2. Backend

- FastAPI tổ chức theo module.
- Firebase Admin xác minh identity.
- MongoDB lưu dữ liệu nghiệp vụ, version và trạng thái workflow.
- ChromaDB + sentence-transformers phục vụ RAG.
- EasyOCR/pdf2image phục vụ tài liệu scan.
- LLM provider hiện hỗ trợ Qwen, DeepSeek/Ollama và Gemini.
- Question workflow có optimistic concurrency qua `expected_version`.
- Có lưu snapshot model, prompt, policy, nguồn và lịch sử review/evaluation.

### 2.3. Luồng trạng thái câu hỏi

```text
DRAFT
  -> PENDING
      -> APPROVED
      -> NEEDS_REVISION -> Teacher sửa -> PENDING
      -> REJECTED
```

Song song với review status, câu hỏi có:

- `evaluation_status`: trạng thái AI evaluation.
- `quality_summary`: điểm tổng, màu chất lượng, model đánh giá.
- `publication_status`: trạng thái publication.
- `question_versions`: lịch sử phiên bản bất biến.

## 3. Ma trận chức năng hiện có

Ký hiệu:

- **Có**: có API và UI sử dụng được.
- **Một phần**: đã có API hoặc dữ liệu, nhưng UI/luồng vận hành chưa hoàn chỉnh.
- **Không**: chưa thấy triển khai trong code hiện tại.

| Nhóm chức năng | Teacher | Reviewer | Admin |
|---|---:|---:|---:|
| Đăng nhập, hồ sơ cá nhân | Có | Có | Có |
| Upload PDF và OCR | Có | Không | Một phần, backend cho phép nhưng frontend không mở |
| Chunk/index và RAG | Có | Không | Một phần |
| Sinh câu hỏi bằng LLM | Có | Không | Một phần |
| Quản lý tài liệu | Có | Không | Một phần |
| CRUD câu hỏi | Có, theo ownership | Chỉ đọc phục vụ review | Một phần, backend cho phép nhưng frontend không mở |
| Xem version câu hỏi | Một phần, backend có API | Một phần | Một phần |
| Gửi câu hỏi sang review | Có | Không | Một phần |
| AI evaluation | Không trực tiếp | Có | Một phần, backend cho phép |
| Approve/Needs revision/Reject | Không | Có | Một phần, backend cho phép |
| Export GIFT/XML | Không qua UI Teacher | Có | Một phần |
| Publish Moodle thật | Không | Không, hiện chỉ mock | Không |
| Tạo đề và mã đề | Có | Không | Một phần, backend cho phép |
| Xuất đề PDF | Có | Không | Một phần |
| Quản lý người dùng | Không | Không | Có |
| Quản lý môn/chương/CLO | Chỉ đọc | Chỉ đọc | Có ở mức thêm/upsert |
| Quản lý model/prompt/policy | Không | Không | Có ở mức cấu hình cơ bản |
| Dashboard vận hành | Không | Không | Không |
| Job monitoring/retry/cancel | Không | Không | Có |
| Audit log UI/API đọc | Không | Không | Không |
| Phân công Reviewer theo môn | Không | Có | Có |

## 4. Chức năng đã có theo vai trò

### 4.1. Teacher

- Đăng ký public với role cố định là `Teacher`.
- Đăng nhập Firebase email/password hoặc Google.
- Upload PDF tối đa 50 MB.
- Chọn môn và chương cho tài liệu.
- Theo dõi OCR, chunk/index và generation job.
- Tái sử dụng tài liệu đã OCR/index.
- Cấu hình nhiều dòng question plan:
  - loại câu hỏi;
  - mức Bloom;
  - số lượng câu.
- Nhập yêu cầu riêng của Teacher để đưa vào RAG/prompt.
- Lưu preset sinh câu hỏi theo tài khoản.
- Xem trước, sửa, lưu, xóa câu hỏi nháp.
- Gửi từng câu hoặc gửi hàng loạt sang hàng đợi kiểm duyệt.
- Quản lý câu hỏi và tài liệu thuộc ownership của mình.
- Tạo câu hỏi thủ công.
- Xem kết quả evaluation, review và publication trên câu hỏi của mình.
- Tạo đề thi, cấu hình ma trận, kiểm tra số câu khả dụng.
- Chọn câu tự động hoặc thủ công.
- Sinh nhiều mã đề và xáo trộn đáp án.
- Preview và xuất PDF đề/đáp án.
- Quản lý lịch công việc và hồ sơ cá nhân.

### 4.2. Reviewer

- Xem hàng đợi câu hỏi toàn hệ thống.
- Lọc theo trạng thái review, loại câu hỏi, Bloom, màu chất lượng và điểm.
- Tìm kiếm theo mã/nội dung.
- Enqueue AI evaluation.
- Xem model, điểm thành phần, evidence và feedback.
- Approve, yêu cầu sửa hoặc từ chối.
- Override kết quả AI khi có lý do.
- Evaluation hàng loạt và approve hàng loạt các câu phù hợp.
- Xem lịch sử evaluation, review và publication.
- Export câu hỏi đã duyệt sang GIFT/XML.
- Ghi nhận Moodle publication ở chế độ mock.

### 4.3. Admin

- Liệt kê, tìm kiếm và lọc người dùng.
- Tạo tài khoản `Admin`, `Teacher`, `Reviewer`.
- Đổi tên hiển thị, role và trạng thái active.
- Khóa/mở khóa tài khoản.
- Tạo/upsert môn học.
- Thêm chương và CLO.
- Lưu model metadata.
- Tạo version prompt và evaluation policy.
- Backend coi Admin là superuser ở nhiều API Teacher/Reviewer.

## 5. Các blocker và rủi ro chính

### 5.1. Demo login có thể tạo lại tài khoản Admin

`backend/modules/auth/login.py` đang hard-code:

- `admin/admin`;
- `reviewer/reviewer`.

Endpoint `/auth/demo-login` không có environment guard và có thể tạo/mở lại user
Firebase tương ứng. Đây là blocker bảo mật P0 nếu backend được đưa ra mạng.

### 5.2. Ownership đề thi chưa được kiểm tra đầy đủ

Danh sách đề của Teacher được lọc theo owner, nhưng các thao tác theo `exam_id`
như get, update, delete, matrix, question pool, variant và export không xác minh
`created_by_user_id` với user hiện tại.

Hệ quả: Teacher có thể đọc hoặc thay đổi đề của Teacher khác nếu biết ID.

### 5.3. Moodle được chốt ở chế độ mock/export

Publication hiện:

- tạo `moodle_question_ref_id` dạng `mock-*`;
- ghi local record vào MongoDB;
- đặt `publication_status=PUBLISHED`;
- không gọi Moodle API/plugin thật.

Frontend cũng luôn gửi `mock: true`. Vì vậy chỉ nên mô tả chức năng hiện tại là
**export và mô phỏng publication**, chưa phải đồng bộ Moodle. Backend đã chặn
`mock=false` khi chưa cấu hình sync thật và chặn mock ở production non-demo.

### 5.4. Phân quyền frontend và backend chưa đồng nhất

Backend cho Admin sử dụng nhiều API của Teacher/Reviewer, nhưng frontend chỉ mở:

- `/danh-muc`;
- `/quan-ly-nguoi-dung`.

Admin không thể dùng UI để giám sát tài liệu, câu hỏi, hàng duyệt hoặc đề thi dù
backend có quyền.

### 5.5. Background job chưa bền vững

OCR, generation, chunking và evaluation dùng FastAPI `BackgroundTasks` cùng
semaphore trong process.

Rủi ro:

- restart server có thể để job ở `QUEUED/PROCESSING`;
- không có worker độc lập;
- không có retry/cancel chuẩn;
- Admin không có màn hình xử lý job lỗi;
- khó scale nhiều instance.

### 5.6. Cấu hình model/prompt chưa hoàn toàn điều khiển runtime

- Model catalog được lưu trong DB nhưng factory vẫn nhận một số provider code
  hard-code.
- `config` của model chưa được áp dụng đầy đủ vào provider runtime.
- `PROMPT_SOURCE` mặc định là `file`; prompt Admin lưu vào DB chỉ có hiệu lực khi
  đổi environment sang `db`.
- UI Admin luôn lưu model/prompt/policy ở trạng thái active, chưa có quy trình
  test, activate, deactivate hoặc rollback rõ ràng.

### 5.7. Kiểm thử chưa đủ cho RBAC và workflow

- Backend chủ yếu có schema test.
- Chưa có test tích hợp đầy đủ cho ownership, role matrix, workflow transition,
  concurrency và Moodle.
- Frontend chưa có test runner, route guard test hoặc component test.

## 6. Quy ước ưu tiên

| Mức | Ý nghĩa |
|---|---|
| **P0** | Blocker bảo mật, sai quyền, sai dữ liệu hoặc chức năng đang được claim nhưng chưa chạy thật |
| **P1** | Cần cho vận hành ổn định và hoàn thiện nghiệp vụ cốt lõi của ba role |
| **P2** | Tăng năng suất, khả năng mở rộng và trải nghiệm người dùng |
| **P3** | Nâng cao, tối ưu dài hạn, phù hợp sau khi hệ thống cốt lõi ổn định |

## 7. Backlog P0 — phải làm trước

### P0-01 — Khóa demo login ngoài môi trường demo

**Vai trò ảnh hưởng:** Admin, Reviewer, toàn hệ thống.

**Phạm vi:**

- Thêm `APP_ENV` hoặc `DEMO_MODE`.
- Không đăng ký route `/auth/demo-login` khi production.
- Không hard-code mật khẩu demo trong source production.
- Ẩn lựa chọn demo trên LoginPage khi `DEMO_MODE=false`.
- Không tự động mở lại Firebase user đã bị khóa.
- Ghi audit khi demo login được sử dụng.

**Tiêu chí hoàn thành:**

- Production trả `404` hoặc không tồn tại route demo.
- Không thể dùng `admin/admin` để lấy custom token production.
- Có test cho demo mode bật/tắt.

**Đã audit/chốt 2026-07-27:** backend chỉ đăng ký `/auth/demo-login` khi `settings.demo_mode`
bật, `DEMO_MODE` mặc định tắt trong `APP_ENV=production`, password demo lấy từ env và mặc định rỗng.
Frontend chỉ dùng alias demo khi `VITE_DEMO_MODE=true`. Demo Firebase user bị disabled sẽ trả 403 và
không bị `update_user` mở lại; app user demo bị `is_active=false` cũng không được tự bật lại vì
`is_active=True` chỉ nằm trong `$setOnInsert`. Đã có audit `auth.demo_login` và test bổ sung cho các
nhánh disabled.

### P0-02 — Sửa ownership và authorization cho đề thi

**Vai trò ảnh hưởng:** Teacher, Admin.

**Phạm vi:**

- Truyền `CurrentUser` vào toàn bộ service method theo `exam_id`.
- Teacher chỉ được truy cập đề có `created_by_user_id` của mình.
- Admin được truy cập toàn bộ theo policy đã thống nhất.
- Áp dụng cho exam, matrix, questions, variants, preview và PDF export.
- Enforce ownership ở backend, không dựa vào frontend.

**Tiêu chí hoàn thành:**

- Teacher A không thể get/update/delete/export đề của Teacher B.
- Admin vẫn truy cập được khi policy cho phép.
- Có test API cho từng endpoint và từng role.

**Đã audit/chốt 2026-07-27:** `ExamService` và `ExamVariantService` đều lấy đề qua
`_get_for_user_or_404`/`_get_exam_for_user_or_404` trước khi xử lý nội dung, matrix, question pool,
auto-pick, manual add/remove, variant, preview và PDF export path. Teacher chỉ truy cập đề có
`created_by_user_id` của mình; Admin là business superuser theo policy hiện tại. Bổ sung test phủ
update/status/delete/matrix/pool/auto/manual/variant methods và test picker không hiện câu stale
approved version.

### P0-03 — Thống nhất permission matrix frontend/backend

**Vai trò ảnh hưởng:** Admin, Reviewer, Teacher.

**Phạm vi:**

- Tạo một permission map dùng nhất quán cho route và menu.
- Quyết định rõ Admin có phải superuser nghiệp vụ hay chỉ quản trị cấu hình.
- Nếu Admin là superuser, mở UI câu hỏi, review, tài liệu và đề thi cho Admin.
- Nếu Admin không phải superuser, thu hẹp dependency backend tương ứng.
- Không giữ logic quyền chết trong component mà route không thể truy cập.

**Tiêu chí hoàn thành:**

- Mỗi route frontend có permission tương ứng với backend.
- Menu và direct URL cho cùng một kết quả.
- Có route guard test cho ba role.

**Đã audit/chốt 2026-07-27:** chọn policy Admin là business superuser, khớp với backend
`require_teacher_or_admin`, `require_reviewer_or_admin`, `require_teacher_reviewer_or_admin` và
`require_admin`. Frontend dùng `PROTECTED_ROUTE_ROLES` trong `frontend/src/auth/permissions.js` làm
nguồn quyền trung tâm; `App.jsx` lấy role guard qua `rolesForPath`, còn `Header.jsx` lọc menu bằng
`canAccessPath`, nên menu và direct URL cùng đi qua một matrix. Test frontend đã phủ Admin/Teacher,
dynamic route `/lam-de-thi/:examId`, landing path và danh sách protected route phải có trong map.

### P0-04 — Bảo vệ tài khoản Admin cuối cùng

**Vai trò ảnh hưởng:** Admin.

**Phạm vi:**

- Không cho Admin tự khóa hoặc tự hạ role nếu đó là Admin active cuối cùng.
- Không cho xóa/deactivate toàn bộ Admin.
- Xác thực lại hoặc yêu cầu thao tác nhạy cảm cho thay đổi role Admin.
- Audit mọi thay đổi role/trạng thái tài khoản.

**Tiêu chí hoàn thành:**

- Hệ thống luôn còn ít nhất một Admin active.
- Mỗi thay đổi quyền có actor, target, before/after và timestamp.

**Đã audit/chốt 2026-07-27:** `UserService._ensure_admin_floor` chặn deactivate hoặc downgrade Admin
active cuối cùng ở cả `update_admin` và `deactivate`. Các thay đổi role/is_active ghi audit
`user.admin_update`/`user.deactivate` với actor, before/after; test hiện có bao phủ không deactivate và
không downgrade Admin cuối cùng.

### P0-05 — Xử lý đúng trạng thái Moodle

**Vai trò ảnh hưởng:** Reviewer, Admin.

Có hai lựa chọn hợp lệ:

1. Giữ bản demo: đổi toàn bộ nhãn thành “Mô phỏng/Export Moodle”, không claim
   “đồng bộ thành công”.
2. Làm tích hợp thật: gọi Moodle/plugin và chỉ đặt `PUBLISHED` khi Moodle xác nhận.

**Phạm vi tối thiểu nếu tích hợp thật:**

- Cấu hình site URL và credential an toàn.
- Mapping site/course/category.
- Idempotency theo question version và target.
- Trạng thái `QUEUED/PROCESSING/PUBLISHED/FAILED`.
- Retry có giới hạn.
- Lưu response/error đã loại bỏ secret.

**Tiêu chí hoàn thành:**

- Không sinh `mock-*` khi chạy production.
- Publication lỗi không làm câu hỏi thành `PUBLISHED`.
- Retry không tạo câu hỏi trùng trên Moodle.

**Đã audit/chốt 2026-07-27:** chọn hướng giữ bản demo rõ ràng. Backend chặn Moodle thật khi chưa cấu hình,
chặn mock ở production non-demo, ghi `publication_mode=MOCK`, `external_sync=false`,
`status_detail=SIMULATED_LOCAL_RECORD` và message nói rõ chỉ ghi local kèm export GIFT/XML. Admin API/UI
hiển thị nhãn “Đã ghi mô phỏng”, ref `mock-*` là local và không phải Moodle ID thật.
Test backend phủ `mock=false` bị từ chối trước khi đụng database và production non-demo không cho ghi mock.

**Ghi chú mở rộng:** nếu cần Moodle thật, triển khai API/plugin thực và chỉ set `external_sync=true`
khi Moodle xác nhận; phần đó không còn là P0 nếu sản phẩm chỉ claim export/mock.

### P0-06 — Recovery cho job bị treo

**Vai trò ảnh hưởng:** Teacher, Reviewer, Admin.

**Phạm vi:**

- Phát hiện job `PROCESSING` quá timeout khi startup hoặc bằng scheduler.
- Chuyển job sang `STALE/FAILED` hoặc enqueue lại an toàn.
- Dùng idempotency/dedupe để tránh chạy trùng.
- Có retry thủ công cho job lỗi.
- Bước đầu có thể giữ BackgroundTasks, nhưng phải có recovery rõ ràng.

**Tiêu chí hoàn thành:**

- Restart backend không để job treo vô thời hạn.
- Retry không tạo trùng document, question hoặc evaluation.

**Đã audit/chốt 2026-07-27:** `main.lifespan` gọi `recover_stale_jobs` sau bootstrap database khi
backend startup. `core/job_recovery.py` đánh dấu generation job active quá timeout thành `failed`,
evaluation job thành `STALE` và đồng bộ `questions.evaluation_status`, document job thành `FAILED` và
cập nhật `documents.pipeline_summary/latest_error`; chunk set/embedding đang xử lý cũng chuyển `FAILED`.
Manual retry/cancel hiện có qua Document sidebar và Admin Jobs. Test
`test_job_recovery_marks_only_stale_active_jobs` xác nhận chỉ stale active jobs bị recover, job fresh
không bị đụng.

### P0-07 — Bộ test tối thiểu cho luồng quan trọng

**Vai trò ảnh hưởng:** toàn hệ thống.

**Test bắt buộc:**

- Auth và demo-mode.
- Role matrix.
- Document/question/exam ownership.
- Question version conflict.
- DRAFT -> PENDING -> review transitions.
- Reviewer override.
- Publication idempotency và trạng thái lỗi.
- Route guard frontend.

**Tiêu chí hoàn thành:**

- Test chạy được bằng một command backend và một command frontend.
- CI chặn merge nếu test P0 thất bại.

**Đã audit/chốt 2026-07-27:** coverage hiện có đã phủ auth/demo-mode, role matrix frontend,
ownership đề thi, version conflict, reviewer override, Moodle idempotency/trạng thái lỗi, route guard
frontend và transition `DRAFT`/`NEEDS_REVISION` -> `PENDING` trước khi Reviewer review. Backend test chạy
bằng `python -m pytest tests/test_schema_v2.py -q`; frontend test chạy bằng `npm --prefix frontend test`.
Thêm GitHub Actions `.github/workflows/p0-tests.yml` để chạy backend P0 tests, frontend tests và frontend
build trên pull request và push vào `main`/`master`.

## 8. Backlog P1 — hoàn thiện nghiệp vụ cốt lõi

### 8.1. Admin

#### P1-ADM-01 — Operations Dashboard

Hiển thị:

- số user active theo role;
- tài liệu theo trạng thái;
- OCR/chunk/generation/evaluation job đang chạy và lỗi;
- câu hỏi theo DRAFT/PENDING/APPROVED/NEEDS_REVISION/REJECTED;
- chất lượng câu hỏi theo màu;
- publication thành công/thất bại;
- latency và error rate theo model.

**Đã hoàn thiện/chốt 2026-07-27:** `AdminOverviewService.overview` đã tổng hợp user active theo role, document status, review status, quality color, Moodle publication summary, attention queue, recent retry jobs/audit, job breakdown theo generation/evaluation/OCR/chunk và model performance 30 ngày từ evaluation jobs/generation runs (`total`, `completed`, `failed`, `active`, `error_rate`, `avg_latency_ms`). `AdminOverviewPage` hiển thị các panel tương ứng và link sang Job/Audit. Test backend đã phủ operational state, job breakdown, quality color, publication failed, model latency/error rate.

#### P1-ADM-02 — Job Management

- Danh sách job toàn hệ thống.
- Lọc theo loại, user, trạng thái và thời gian.
- Xem log/error/snapshot.
- Retry, cancel và re-index.
- Cảnh báo job chạy quá lâu.

**Đã audit/chốt 2026-07-27:** Admin Jobs API/UI đã có danh sách toàn hệ thống cho generation,
evaluation và document jobs; lọc theo loại, trạng thái, người tạo, khoảng ngày, stale-only và search;
hiển thị lỗi/snapshot/progress/thời gian; cảnh báo long-running theo ngưỡng recovery; retry/cancel
generation/evaluation/document jobs qua Admin service và ghi audit. Document retry đi qua
`DocumentService.retry_job`, bao gồm các job tài liệu retryable như OCR/chunk/re-index. Test backend phủ
summary/search/status rollup, user/status/stale/date filters, cancel generation/evaluation sync ngược câu
hỏi, và retry evaluation có background task/audit.

#### P1-ADM-03 — Audit Log API và UI

- API đọc audit log có pagination/filter.
- Filter theo actor, entity, action, thời gian.
- Xem before/after cho thay đổi quyền và workflow.
- Không cho sửa/xóa audit log qua UI.

**Đã audit/chốt 2026-07-27:** `AdminAuditService.list` hỗ trợ pagination, search và filter theo actor, entity type/id, action, `date_from`/`date_to`, đồng thời chuẩn hóa cả schema audit cũ (`actor_user_id`, `entity_type`, `entity_id`) lẫn schema mới (`actor`, `entity`) thành response có actor/entity/before/after/changes/metadata/hash. Router admin audit chỉ expose `GET /admin/audit`; UI `AdminAuditPage` chỉ đọc, lọc và xem chi tiết JSON before/after/changes/metadata, không có thao tác sửa/xóa. Test backend đã phủ actor/entity/action/date/search/pagination và before/after normalization.

#### P1-ADM-04 — Full lifecycle môn/chương/CLO

- Sửa, sắp xếp, activate/deactivate.
- Kiểm tra trùng mã trong cùng phạm vi.
- Không hard-delete dữ liệu đang được question/document/exam sử dụng.
- Hiển thị số lượng tài liệu/câu hỏi liên quan trước khi khóa.

**Đã audit/chốt 2026-07-27:** `CatalogService` hỗ trợ upsert/update subject, add/update chapter và CLO, gồm `sequence_no`, `is_active`, duplicate code checks theo subject/child scope và usage counts từ documents/current questions/exams. Router chỉ expose POST/PATCH cho subject/chapter/CLO, không có hard-delete endpoint; deactivate là cập nhật `is_active=false`. `CatalogAdminPage` có form sửa, toggle active, sequence cho chương và hiển thị usage counts trước khi khóa. Test backend đã phủ usage counts, duplicate subject/chapter/CLO code và update/deactivate chapter/CLO.

#### P1-ADM-05 — Quản trị model/prompt/policy thật

- Health-check model.
- Test prompt bằng dữ liệu mẫu.
- Activate/deactivate rõ ràng.
- Rollback version.
- Hiển thị runtime config thực tế đang dùng.
- Đồng bộ catalog model với `get_llm_service`.
- Hiển thị `PROMPT_SOURCE=file/db` và cảnh báo khi bản DB chưa có hiệu lực.

**Đã audit/chốt 2026-07-27:** `CatalogService` đã có CRUD/activation cho AI model, prompt template và evaluation policy; model health-check gọi factory `get_llm_service`, lưu `last_health_check`; prompt test dựng dữ liệu mẫu và trả `prompt_source`, active DB prompt/prompt body/warnings; prompt/policy lưu version mới và `activate_*` có thể bật/tắt hoặc rollback sang version cũ bằng cách active version đó. `runtime_config` hiển thị generation/evaluation provider, catalog model, factory status, active prompt count, active evaluation policy và warning khi `PROMPT_SOURCE` chưa khớp DB. `CatalogAdminPage` expose runtime panel, health-check, test prompt, activate/deactivate model/prompt/policy và edit version. Test backend đã phủ factory support, activate/deactivate model, rollback prompt/policy version và runtime config.

#### P1-ADM-06 — Quản lý Moodle target

- CRUD Moodle site.
- Kiểm tra kết nối.
- Mapping course/category.
- Phân quyền ai được publish.
- Xem retry/dead-letter publication.

**Đã audit/chốt 2026-07-27:** Admin Moodle API/UI đã có CRUD target, deactivate, kiểm tra kết nối,
mapping course/category mặc định, danh sách publication/dead-letter theo site/status/search và retry
publication lỗi. Target schema lưu `allowed_roles` với tối thiểu một role; Admin UI có checkbox
Admin/Reviewer; `QuestionWorkflowService.publish_to_moodle` enforce role target khi publish hoặc retry
qua Admin. Moodle thật vẫn không được claim là sync production vì `P0-05` đã chốt phạm vi mock/export.

### 8.2. Reviewer

#### P1-REV-01 — Phân công và claim review

- Gán Reviewer theo môn/chuyên môn.
- Reviewer nhận/claim câu hỏi.
- Trạng thái `UNASSIGNED/ASSIGNED/IN_REVIEW`.
- Lock có timeout để tránh hai Reviewer xử lý cùng lúc.
- Admin có thể reassign.

**Đã audit/chốt 2026-07-27:** backend có `assign_review`, `claim_review`, `release_review`,
`_ensure_review_lock` và audit/notification cho assignment; Reviewer chỉ review khi đang giữ lock còn hạn,
Admin có thể assign/unassign/reassign. ReviewQueue đã có filter môn/chương/CLO/Teacher/assignment,
dashboard workload, nút claim/release và modal gán reviewer. Modal nay dùng `/users/reviewers` để chọn
Reviewer/Admin active thay vì nhập raw ID từ danh sách Teacher. Test phủ lock owner, assign/claim/review
workflow, reviewer dashboard và reviewer options cho assignment.

#### P1-REV-02 — Bộ lọc nghiệp vụ đầy đủ

- Môn, chương, CLO.
- Teacher tạo câu hỏi.
- Reviewer được giao.
- Thời gian chờ và deadline.
- Evaluation status và publication status.
- Server-side pagination/filter.

**Đã audit/chốt 2026-07-27:** `QuestionService.list`/`MongoQuestionRepository.list` đã push filter
server-side cho review status, assignment status, assigned reviewer, Teacher tạo câu hỏi, môn/chương/CLO,
loại câu hỏi, Bloom, độ khó, quality color/min score, evaluation status, publication status, search,
pagination, `waiting_hours_min` và `overdue_only`. `ReviewQueuePage` expose các filter tương ứng, gồm
“Của tôi”, thời gian chờ 24h/72h/7 ngày và quá hạn lock. Test repository kiểm tra pipeline nhận đủ
reviewer filters và các filter thời gian/deadline.

#### P1-REV-03 — Source Viewer

- Xem PDF gốc.
- Nhảy đúng trang OCR/citation.
- Highlight source excerpt.
- Hiển thị chunk ID, page range và content hash.
- Báo nguồn không còn thuộc chunk set hiện hành.

**Đã audit/chốt 2026-07-27:** `QuestionService.source_viewer` trả document/PDF metadata, page OCR, excerpt, chunk id/hash, trạng thái chunk set hiện hành và warning stale source; `ReviewQueuePage` gọi `getQuestionSources`/`fetchQuestionSourcePdf`, mở PDF theo page, hiển thị tab trang OCR, highlight excerpt và metadata citation. Test backend đã phủ schema source viewer và stale chunk-set/page warning.

#### P1-REV-04 — Form review có cấu trúc

- Không dùng `window.prompt`.
- Checklist theo rubric.
- Ghi chú tổng.
- Danh sách lỗi cần Teacher sửa.
- Bắt buộc lý do cho reject/override.
- Autosave draft review nếu cần.

**Đã audit/chốt 2026-07-27:** `ReviewQueuePage` mở modal review có checklist rubric, ghi chú tổng, danh sách lỗi cần Teacher sửa, severity, citation/page reference và autosave draft theo question/decision trong `localStorage`; không còn luồng `window.prompt`. Backend `ReviewCreateRequest`/`ReviewOverride` bắt buộc lý do reject/override và yêu cầu revision issue cho `NEEDS_REVISION`; service lưu `review_form`, `revision_issues`, `override` và dashboard đếm override/revision issue. Test backend đã phủ reject reason, revision issue và override reason.

#### P1-REV-05 — Notification và vòng phản hồi

- Thông báo Teacher khi cần sửa/đã duyệt/bị từ chối.
- Thông báo Reviewer khi câu hỏi được gửi lại.
- Deep link tới đúng question/version.
- Lưu read/unread trong ứng dụng.

**Đã audit/chốt 2026-07-27:** `NotificationService` tạo thông báo cho Teacher khi Reviewer quyết định `APPROVED`/`NEEDS_REVISION`/`REJECTED`, tạo thông báo cho Reviewer khi Admin assign và khi Teacher submit lại từ `NEEDS_REVISION`. Các link trỏ về `/quan-ly?questionId=...` hoặc `/kiem-duyet?questionId=...`; `ManagePage`/`ReviewQueuePage` mở deep link theo `questionId`. API `/notifications`, `/notifications/unread-count`, `/notifications/{id}/read`, `/notifications/read-all` và Header bell đã hỗ trợ unread/read. Test đã phủ create/mark-read và resubmit notification.

#### P1-REV-06 — Dashboard công việc Reviewer

- Số câu chưa nhận/được giao/quá hạn.
- Thời gian duyệt trung bình.
- Số override AI.
- Thống kê theo môn và khoảng thời gian.

**Đã audit/chốt 2026-07-27:** `QuestionWorkflowService.review_dashboard` trả workload `pending`/`unassigned`/`assigned`/`in_review`/`lock_expired`/`mine`, performance 7 ngày/30 ngày, approval rate, override AI, số revision issue và thời gian xử lý trung bình từ audit metadata; đồng thời gom thống kê theo môn. `ReviewQueuePage` hiển thị dashboard ngay đầu hàng duyệt và refresh sau thao tác review/bulk. Test backend đã phủ workload, lock quá hạn, override, revision issue, average review hours và subject stats.

### 8.3. Teacher

#### P1-TEA-01 — Version history, diff và restore

- Frontend gọi endpoint versions hiện có.
- So sánh hai version.
- Hiển thị người sửa, thời gian và change note.
- Restore bằng cách tạo version mới, không sửa version cũ.
- Cảnh báo review/evaluation bị invalidated sau khi sửa.

**Đã audit/chốt 2026-07-27:** `ManagePage` đã tải `listQuestionVersions`, hiển thị danh sách version,
so sánh hai version qua diff nội dung/lựa chọn/đáp án/giải thích/Bloom/CLO/nguồn và restore bằng
`updateQuestion` với `expected_version`, dữ liệu version cũ và `change_note`. Backend `create_version`
luôn tạo version mới, reset evaluation/review/publication state phù hợp và có test
`test_question_restore_creates_new_version_and_resets_workflow`.

#### P1-TEA-02 — Quản lý pipeline tài liệu

- [x] Xem OCR pages.
- [x] Sửa OCR trước khi chunk/index.
- [x] Xem lỗi/job history theo từng bước.
- [x] Retry/cancel OCR job từ Document sidebar và Admin Jobs.
- [x] Retry/cancel chunking.
- [x] Re-index khi embedding model thay đổi.

#### P1-TEA-03 — Hoàn thiện exam lifecycle

Thêm trạng thái:

```text
DRAFT -> READY -> FINALIZED -> ARCHIVED
```

Quy tắc:

- Chỉ tạo variant khi đủ `question_count`.
- Không chỉnh matrix/question pool sau `FINALIZED`, trừ khi mở khóa.
- Kiểm tra mọi câu thuộc đúng subject và vẫn là approved version.
- Lưu snapshot khi finalize.
- Enforce server-side, không chỉ dựa vào UI.

**Đã audit/siết 2026-07-27:** backend đã có trạng thái `DRAFT/READY/FINALIZED/ARCHIVED`,
validate đủ `question_count`, khóa sửa nội dung sau `FINALIZED`, chỉ tạo variant sau finalize và lưu
`finalized_snapshot`. Bổ sung kiểm tra bắt buộc `approved_version_id == current_version_id`, subject
không được thiếu và phải khớp subject của đề; matrix availability/auto-pick chỉ tính câu hỏi usable.
Đã thêm test trong `backend/tests/test_schema_v2.py`.

#### P1-TEA-04 — Server-side question picker cho đề thi

- Filter theo `subject_id`, `chapter_id`, Bloom và difficulty ở API.
- Không tải 200 câu toàn hệ thống rồi lọc client.
- Backend từ chối câu sai môn khi thêm thủ công.
- Pagination và giữ selection qua nhiều trang.

**Đã audit/chốt 2026-07-27:** `ExamBuilderPage` gọi `listExamQuestionPool` với pagination,
search, chapter, Bloom và difficulty; backend luôn ràng theo subject của đề, ownership của Teacher
và chỉ lấy câu `APPROVED`. `add_questions_manual` dùng validation server-side để từ chối câu sai môn,
không đúng approved version hoặc vượt `question_count`. Test `test_exam_question_pool_uses_server_side_filters`
đã bao phủ filter/pagination truyền xuống repository.

#### P1-TEA-05 — Bộ lọc ngân hàng câu hỏi

- Môn, chương, CLO, difficulty.
- Evaluation và publication status.
- Version/source document.
- Saved filter nếu cần.

**Đã triển khai 2026-07-27:** API danh sách câu hỏi và `ManagePage` đã lọc server-side theo
môn, chương, CLO, độ khó, trạng thái AI, trạng thái Moodle và tài liệu nguồn.
Đã bổ sung saved filters theo user trong `ManagePage`; preset lưu local, áp dụng lại search + toàn bộ
filter nghiệp vụ, có xoá preset và đặt lại filter. Frontend có test utility cho parse/storage payload.

**Còn lại tùy chọn:** filter sâu theo từng version nếu vận hành thực tế cần lọc các version cũ,
không chỉ current version/source document.

## 9. Backlog P2 — năng suất và mở rộng

### 9.1. Admin

- `P2-ADM-01`: mời user qua email, reset password, import user hàng loạt.
- `P2-ADM-02`: phân quyền chi tiết theo permission thay vì chỉ ba role.
- `P2-ADM-03`: quản lý ownership/chia sẻ/chuyển giao tài liệu.
- `P2-ADM-04`: báo cáo sử dụng model, token, latency và chi phí.
- `P2-ADM-05`: export báo cáo CSV/XLSX.

### 9.2. Reviewer

- `P2-REV-01`: bulk review theo batch với audit từng item.
- `P2-REV-02`: comment thread và mention.
- `P2-REV-03`: secondary review/two-person approval cho câu quan trọng.
- `P2-REV-04`: calibration giữa Reviewer và AI.
- `P2-REV-05`: mẫu nhận xét tái sử dụng.

### 9.3. Teacher

- `P2-TEA-01`: bulk edit, bulk submit và bulk archive.
- `P2-TEA-02`: import/export GIFT, XML, CSV/XLSX.
- `P2-TEA-03`: nhân bản câu hỏi hoặc đề thi.
- `P2-TEA-04`: hỗ trợ DOCX thật; hiện upload backend chỉ nhận PDF.
- `P2-TEA-05`: export đề DOCX bên cạnh PDF.
- `P2-TEA-06`: dashboard độ phủ Bloom/CLO/chương.
- `P2-TEA-07`: chia sẻ ngân hàng câu hỏi trong cùng môn/bộ môn.

### 9.4. Hạ tầng chung

- Chuyển background jobs sang worker queue bền vững.
- Object storage thay cho local filesystem.
- Rate limit và quota theo user.
- Centralized logging, metrics và alerting.
- Backup/restore MongoDB và ChromaDB.
- CI/CD và môi trường dev/staging/production tách biệt.

## 10. Backlog P3 — nâng cao dài hạn

- Semantic duplicate detection trên toàn ngân hàng.
- Phát hiện drift chất lượng theo model/prompt version.
- A/B testing prompt và evaluation policy.
- Multi-tenant theo khoa/bộ môn.
- SSO tổ chức và đồng bộ danh sách môn/lớp.
- Workflow hai cấp Reviewer -> Head Reviewer/Admin.
- Phân tích chất lượng câu hỏi từ kết quả làm bài thực tế.
- Difficulty calibration dựa trên item response.
- Recommendation câu hỏi cho ma trận đề.
- Realtime collaboration khi biên tập câu hỏi.
- Moodle bidirectional sync và reconciliation.

## 11. Thứ tự triển khai đề xuất

### Giai đoạn 1 — Security và correctness

1. `P0-01` đến `P0-07` đã audit/chốt; tiếp tục giữ suite P0 xanh khi sửa quyền/workflow.

### Giai đoạn 2 — Publication và job reliability

1. `P1-ADM-01`, `P1-ADM-02` và `P1-ADM-06` đã audit/chốt trong phạm vi operations dashboard, job reliability và Moodle target mock/export.

### Giai đoạn 3 — Hoàn thiện ba role

1. Reviewer workflow P1 đã audit/chốt toàn bộ; chuyển trọng tâm sang Admin governance.

### Giai đoạn 4 — Vận hành và mở rộng

1. Admin dashboard và audit.
2. Notification.
3. Bulk import/export.
4. DOCX.
5. Worker queue, object storage, monitoring và CI/CD.

## 12. Các epic có thể tạo ngay

| Epic | Các item |
|---|---|
| Security & RBAC | P0 đã chốt toàn bộ (`P0-01` đến `P0-07`) |
| Moodle Integration | `P0-05`, `P1-ADM-06` đã chốt mock/export + target management; Moodle sync thật nằm ở P2 nếu cần |
| Job Reliability | `P1-ADM-01`, `P1-ADM-02` và `P0-06` đã xong |
| Admin Governance | `P1-ADM-03` đến `P1-ADM-05` đã xong |
| Reviewer Workflow V2 | `P1-REV-01` đến `P1-REV-06` đã xong |
| Teacher Question Bank V2 | `P1-TEA-01`, `P1-TEA-02`, core `P1-TEA-05` đã xong |
| Exam Builder V2 | `P1-TEA-03`, `P1-TEA-04` đã xong |
| Productivity & Scale | Toàn bộ P2 |

## 13. Definition of Done chung

Một item không nên được coi là hoàn thành nếu chỉ có UI hoặc chỉ có schema.

Mỗi chức năng cần tối thiểu:

- API/backend enforce permission và validation.
- UI có loading, empty, error và retry state.
- Có audit cho thao tác nhạy cảm.
- Có test success, forbidden và invalid input.
- Không làm mất ownership/version history.
- Có tài liệu environment hoặc migration nếu phát sinh cấu hình/schema.
- Không claim “Moodle sync”, “DOCX support” hoặc “production-ready” khi mới ở
  mức mock/demo.

## 14. File code liên quan để bắt đầu

- RBAC backend: `backend/core/dependencies.py`.
- Route guard frontend: `frontend/src/App.jsx`, `frontend/src/components/Header.jsx`.
- Demo login: `backend/modules/auth/login.py`, `frontend/src/pages/LoginPage.jsx`.
- Exam ownership: `backend/modules/exams/router.py`,
  `backend/modules/exams/service.py`, `backend/modules/exams/repository.py`.
- Review workflow: `backend/modules/questions/workflow_service.py`,
  `frontend/src/pages/ReviewQueuePage.jsx`.
- Moodle: `backend/modules/questions/workflow_router.py`,
  `backend/modules/questions/workflow_service.py`.
- Job execution: `backend/modules/ocr/ocr.py`,
  `backend/modules/generation/generate.py`,
  `backend/modules/questions/workflow_service.py`.
- Admin catalog: `backend/modules/catalog/`,
  `frontend/src/pages/CatalogAdminPage.jsx`.
- Teacher flow: `frontend/src/pages/GeneratePage.jsx`,
  `frontend/src/pages/ManagePage.jsx`.
