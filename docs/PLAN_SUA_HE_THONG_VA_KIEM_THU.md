# Plan sửa hệ thống và kiểm thử QBankCTU

## 1. Căn cứ lập kế hoạch

Kế hoạch này được xây dựng từ:

- `docs/Tai_lieu_dac_ta_QBankCTU.docx`.
- `docs/Tai_lieu_kich_ban_kiem_thu_QBankCTU.docx`.
- Đối chiếu với frontend/backend hiện tại.
- Baseline test và production build tại thời điểm lập kế hoạch.

Mục tiêu là kiểm tra và sửa luồng nghiệp vụ, đầu vào, đầu ra, phân quyền, tính toàn vẹn dữ liệu và UI/UX. Trọng tâm ưu tiên là Reviewer và Admin.

## 2. Phạm vi

### 2.1. Trong phạm vi

- Xác thực, phiên đăng nhập và RBAC.
- Quản lý người dùng, hồ sơ và lịch cá nhân.
- Catalog: môn học, chương, CLO, model AI, prompt và evaluation policy.
- Tài liệu, OCR, page, chunk, index và RAG.
- Sinh và quản lý câu hỏi.
- AI evaluation và Human Review.
- Moodle GIFT/XML và Moodle publication mock.
- Admin dashboard, job, audit và notification.
- Transaction, concurrency, idempotency, recovery và bảo mật.
- UI/UX của các luồng trên.

### 2.2. Ngoài phạm vi

Không kiểm tra hoặc sửa tính năng tạo đề thi:

- `EXM-01..EXM-07`.
- `SMK-08`.
- Phần tạo đề thi trong `NFR-06`.

Sau khi loại trừ phần đề thi, còn 68 test case chi tiết cần được truy vết và thực thi.

## 3. Baseline hiện tại

Kết quả chạy tại thời điểm lập kế hoạch:

- Backend: `100 passed`.
- Frontend: `35 passed`.
- Frontend production build: thành công.
- Bundle JavaScript chính khoảng 783 KB, Vite cảnh báo chunk lớn hơn 500 KB.

Các giới hạn của baseline:

- Frontend chủ yếu mới test permission/helper/util.
- Chưa có component test cho các trang nghiệp vụ.
- Chưa có UI E2E tự động.
- Backend chủ yếu dùng schema/service test với fake collection.
- Chưa đủ bằng chứng cho route authorization, transaction thật, worker cancellation race và toàn bộ 68 test case.

## 4. Nguyên tắc triển khai

Thứ tự ưu tiên:

1. Sửa lỗi quyền, state transition, concurrency và tính toàn vẹn dữ liệu.
2. Bổ sung API integration test để khóa hành vi đúng.
3. Sửa và tinh giản Reviewer workflow.
4. Sửa các luồng Admin.
5. Regression tài liệu, generation và question bank.
6. UI E2E và kiểm thử phi chức năng.

Không refactor lớn giao diện trước khi các rule nghiệp vụ P0 được khóa bằng test.

## 5. P0 — Security và nghiệp vụ bắt buộc sửa trước

### P0-01 — Chỉ cho review câu hỏi PENDING

Hiện trạng:

- `QuestionWorkflowService.review()` kiểm tra version, evaluation và lock nhưng chưa chặn rõ `review_status` khác `PENDING`.
- Admin được bỏ qua review lock nên có nguy cơ gọi API review trực tiếp trên DRAFT, APPROVED hoặc REJECTED.

Đầu vào cần test:

- Câu hỏi `DRAFT`, `PENDING`, `APPROVED`, `REJECTED`, `NEEDS_REVISION`.
- Admin và Reviewer.
- `expected_version` đúng và sai.

Đầu ra đúng:

- Chỉ `PENDING` được tạo review decision.
- Các trạng thái còn lại trả 400 hoặc 409 phù hợp.
- Không tạo `question_reviews`, audit hoặc notification khi request bị từ chối.

Việc sửa:

- Thêm state transition guard trong `backend/modules/questions/workflow_service.py`.
- Thêm `review_status=PENDING` vào atomic update filter.
- Bổ sung test success, invalid state và concurrent review.

### P0-02 — Không cho Reviewer tự tạo kết quả AI PASSED

Hiện trạng:

- Endpoint `POST /questions/{question_id}/evaluations` nhận trực tiếp năm điểm từ Reviewer/Admin.
- Payload điểm cao có thể làm câu hỏi chuyển sang `evaluation_status=PASSED` mà không chạy model.

Đầu vào cần test:

- Reviewer gửi năm điểm bằng 1.
- Reviewer khai báo `evaluator_model_code` tùy ý.
- Evaluation không có `evaluation_job_id`.

Đầu ra đúng:

- Người dùng không thể tạo kết quả mang nghĩa AI evaluation chính thức từ điểm tự nhập.

Việc sửa đề xuất:

- Chỉ cho worker/internal service gọi evaluation persistence; hoặc
- Nếu giữ manual evaluation, lưu `evaluation_type=MANUAL` và không dùng kết quả này để thỏa điều kiện approve không override.
- Audit phải phân biệt `AI`, `HEURISTIC` và `MANUAL`.

### P0-03 — Bảo vệ generation job status

Hiện trạng:

- `GET /generate/status/{job_id}` chưa yêu cầu current user.
- Người biết job ID có thể xem trạng thái hoặc kết quả generation.

Đầu vào cần test:

- Không token.
- Teacher A xem job của Teacher B.
- Reviewer xem generation job.
- Admin xem job.

Đầu ra đúng:

- Không token trả 401.
- Teacher khác trả 403/404.
- Owner và Admin truy cập được.

Việc sửa:

- Thêm dependency auth.
- Lưu và kiểm tra `requested_by_user_id`.
- Bổ sung API auth matrix test.

### P0-04 — Cancel job phải thực sự dừng side effect

Hiện trạng:

- Generation worker có thể đổi job đã bị cancel về `processing` rồi `completed`.
- Evaluation worker có thể ghi `question_evaluations` và cập nhật câu hỏi sau khi Admin đã cancel job.
- OCR đã có một số cancellation check nhưng cần regression toàn bộ.

Đầu vào cần test:

- Cancel khi `QUEUED`.
- Cancel khi `PROCESSING`.
- Cancel ngay trước final database write.
- Worker hoàn thành model call sau khi job đã bị cancel.

Đầu ra đúng:

- Trạng thái cancel là terminal.
- Không tạo thêm câu hỏi, evaluation, chunk hoặc publication sau cancel.
- Question/document aggregate không bị cập nhật thành PASSED/READY/COMPLETED từ job đã cancel.

Việc sửa:

- Worker phải claim job bằng compare-and-set từ `QUEUED` sang `PROCESSING`.
- Kiểm tra cancellation trước và sau external/model call.
- Final write chỉ thành công nếu job vẫn còn `PROCESSING`.
- Thêm race test cho generation, evaluation, OCR và chunk.

### P0-05 — Validation evaluation policy

Hiện trạng:

- Evaluation policy nhận `weights` và `thresholds` dưới dạng dictionary chung.
- Có thể lưu thiếu tiêu chí, tổng weight sai hoặc threshold không hợp lệ.
- Có thể tồn tại nhiều policy name cùng active, trong khi runtime chỉ lấy một record active.

Đầu vào cần test:

- Thiếu một trong năm weight.
- Có key không hỗ trợ.
- Weight âm hoặc lớn hơn 1.
- Tổng weight khác 1.
- Threshold ngoài khoảng 0–1.
- `yellow_min > green_min`.
- Kích hoạt hai policy khác tên.

Đầu ra đúng:

- API trả 400/422 cho cấu hình sai.
- Policy đang active không bị tắt nếu policy mới lưu thất bại.
- Chỉ có một evaluation policy active toàn hệ thống.

Việc sửa:

- Pydantic validator cho đúng năm tiêu chí.
- Validate range, tổng weight và thứ tự threshold.
- Activate policy trong transaction hoặc atomic workflow.

### P0-06 — Xử lý phiên hết hạn tập trung

Hiện trạng:

- `AuthContext` xử lý 401/403 khi đồng bộ phiên đăng nhập.
- Các API request phát sinh sau đó chỉ throw `ApiError`, chưa có global logout/redirect.

Đầu vào cần test:

- Token hết hạn khi đang ở Reviewer/Admin page.
- Backend trả 401.
- Backend trả 403 do tài khoản vừa bị khóa.

Đầu ra đúng:

- 401: refresh token một lần; nếu vẫn lỗi thì sign out, xóa cache và về `/dang-nhap`.
- Giữ return URL để đăng nhập lại quay về route hợp lệ.
- 403 do inactive: sign out và hiển thị thông báo tài khoản bị khóa.

Việc sửa:

- Thêm auth error handler tập trung trong `frontend/src/services/apiClient.js`.
- Không để từng page tự xử lý 401 bằng `alert`.

### P0-07 — Đồng bộ Firebase và MongoDB khi quản lý user

Hiện trạng:

- Update/disable Firebase được gọi trước MongoDB.
- Nếu MongoDB update lỗi, Firebase và application user có thể lệch trạng thái.

Đầu vào cần test:

- Firebase thành công, MongoDB lỗi.
- Firebase lỗi, MongoDB chưa thay đổi.
- Khóa/mở tài khoản.
- Đổi role của Admin cuối cùng.

Đầu ra đúng:

- Hai nguồn dữ liệu nhất quán hoặc có compensation rollback.
- Không vô hiệu hóa Admin active cuối cùng.
- Session bị thu hồi khi tài khoản bị khóa.

Việc sửa:

- Thêm compensation cho identity update.
- Ghi audit chỉ sau khi workflow hoàn tất.
- Trả lỗi rõ ràng nếu rollback không thành công.

### P0-08 — Concurrency cho phân công Reviewer

Đầu vào cần test:

- Hai Admin assign cùng một câu hỏi.
- Admin reassign trong lúc Reviewer giữ lock.
- Reviewer claim ngay lúc Admin assign.

Đầu ra đúng:

- Chỉ một mutation thắng.
- Request cũ trả 409.
- Không âm thầm ghi đè active lock.

Việc sửa:

- Thêm `expected_version` hoặc `assignment_revision`.
- Atomic filter phải kiểm tra assignment trước đó.
- Admin muốn override active lock phải xác nhận và ghi lý do.

## 6. Reviewer workflow

### 6.1. Vấn đề UI/UX

`frontend/src/pages/ReviewQueuePage.jsx` hiện khoảng 1.826 dòng và chứa:

- Dashboard.
- Nhiều bộ lọc nghiệp vụ.
- Queue và pagination.
- Claim/release/assign.
- Source PDF/OCR.
- Evaluation history.
- Review history.
- Review form.
- Publication history và Moodle action.

Luồng có nhiều bước và quá nhiều thông tin hiển thị đồng thời.

### 6.2. Luồng Reviewer đề xuất

Trang mặc định chỉ có ba tab:

1. `Cần tôi xử lý`.
2. `Chưa có người nhận`.
3. `Đã xử lý`.

Các filter môn, chương, CLO, Bloom, score, color, publication và creator đưa vào panel `Bộ lọc nâng cao`.

Thay hai bước `Claim` rồi mở form bằng CTA `Bắt đầu duyệt`:

1. Claim nguyên tử.
2. Nếu thành công, mở workspace review.
3. Nếu conflict, hiển thị Reviewer đang giữ và thời gian hết lock.

Workspace review gồm:

- Vùng nội dung câu hỏi và đáp án.
- Vùng nguồn PDF/OCR/evidence.
- Vùng AI score, rubric và quyết định.

Thanh hành động sticky:

- `Duyệt`.
- `Yêu cầu sửa`.
- `Từ chối`.

AI evaluation:

- Tự enqueue khi Teacher submit.
- Reviewer chỉ thấy `Thử lại đánh giá` khi job lỗi.
- Không bắt Reviewer quản lý job trong happy path.

Admin mode:

- CTA chính là `Phân công`.
- `Duyệt thay Reviewer` là thao tác phụ và bắt buộc ghi lý do.
- Không cho Admin claim đè lock đang còn hiệu lực mà không xác nhận.

### 6.3. Test Reviewer

Chạy đủ:

- `REV-01..REV-11`.

Bổ sung:

- Admin review câu không PENDING.
- Reviewer gửi evaluation scores trực tiếp.
- Concurrent claim/assign/review.
- Lock hết hạn ngay trước submit.
- Source chunk/PDF bị stale hoặc mất.
- Teacher gửi lại sau `NEEDS_REVISION`.
- Notification và deep link.
- Refresh trang khi đang nhập form review.
- Draft review được phục hồi đúng user/question/decision.

## 7. Admin workflow

### 7.1. Quản lý người dùng

Vấn đề:

- UI tải tối đa 100 user rồi lọc role ở frontend.
- Tổng số và role count không đúng khi có hơn 100 user.
- Icon thùng rác thực chất là khóa tài khoản.
- Validation chủ yếu dùng browser alert.

Việc sửa:

- Chuyển role/search/pagination xuống server.
- Hiển thị đúng `total`, page count và active/inactive count.
- Đổi wording thành `Khóa tài khoản`.
- Confirmation nêu rõ ảnh hưởng đến login, job và review assignment.
- Inline validation cho email, password, display name và role.

Test:

- `USR-01..USR-03`.
- Email trùng.
- Mật khẩu yếu.
- Role không hợp lệ.
- Khóa/mở.
- Last active Admin.
- Firebase/Mongo compensation.

### 7.2. Catalog, model, prompt và policy

Việc sửa UX:

- Tách `Bản nháp` và `Đang áp dụng`.
- Model phải health-check thành công trước activate.
- Prompt phải test-build trước activate.
- Policy hiển thị tổng weight theo thời gian thực.
- Khi deactivate môn/chương/CLO đang được sử dụng, hiển thị usage count và ảnh hưởng.

Test:

- `CAT-01..CAT-04`.
- Duplicate code.
- Subject/chapter mismatch.
- Model provider/config lỗi.
- Prompt thiếu placeholder bắt buộc.
- Policy weight/threshold sai.
- Activate/rollback version.

### 7.3. Admin Jobs

Preset mặc định:

- `Đang chạy`.
- `Lỗi có thể retry`.
- `Treo quá ngưỡng`.

Việc sửa:

- Chỉ hiện Retry/Cancel khi backend trả `can_retry`/`can_cancel`.
- Modal cancel hiển thị loại job, owner, đối tượng và side effect.
- Chuyển filter/count/pagination xuống MongoDB.
- Không gom tối đa 500 record mỗi loại rồi phân trang trong memory.
- Mở được audit liên quan qua correlation ID.

Test:

- `JOB-01..JOB-03`.
- Retry job không retryable.
- Cancel job terminal.
- Concurrent cancel/complete.
- Filter date/user/status/search.
- Pagination và summary với dữ liệu lớn.

### 7.4. Audit

Việc sửa:

- Chọn actor từ dropdown thay vì nhập raw ObjectId.
- Hiển thị bản tóm tắt thay đổi trước JSON chi tiết.
- Link từ audit tới question, user, job hoặc publication tương ứng.
- Giữ màn hình read-only.

Test:

- `AUD-01`.
- Filter actor/entity/action/date/search.
- Audit legacy và nested schema.
- Không hiển thị secret/token trong metadata.

### 7.5. Moodle

Việc sửa:

- Mọi UI phải ghi rõ `Mô phỏng Moodle`.
- Không dùng wording khiến Admin hiểu rằng đã đồng bộ Moodle thật.
- Ẩn hoặc disable `mock=false` cho đến khi có Moodle REST, secret management và integration test.

Test:

- `LMS-01..LMS-06`.
- Approved version hiện hành.
- Non-approved bị chặn.
- Target active/inactive.
- Allowed roles.
- Idempotency.
- Retry publication khi version đã thay đổi.

### 7.6. Dashboard

Dashboard chỉ nên:

- Hiển thị KPI chính.
- Hiển thị mục cần chú ý.
- Điều hướng đến trang xử lý.

Không đưa form cấu hình hoặc thao tác nguy hiểm trực tiếp lên dashboard.

Test:

- `ADM-01`.
- Loading, empty, partial data và API error.
- Link attention giữ đúng filter đích.

## 8. Tài liệu, generation và question bank

### 8.1. Test bắt buộc

- `DOC-01..DOC-08`.
- `GEN-01..GEN-08`.
- `QUE-01..QUE-09`.

### 8.2. Phạm vi PDF/DOCX

Tài liệu đặc tả xem PDF text/PDF scan là đầu vào chính và chưa claim DOCX hoàn chỉnh, trong khi code/UI hiện đã nhận DOCX.

Cần chọn một phương án:

1. Đưa DOCX vào đặc tả và bổ sung test end-to-end; hoặc
2. Gắn nhãn `Thử nghiệm`, không tính vào tiêu chí nghiệm thu.

Đề xuất trước mắt:

- PDF là phạm vi nghiệm thu.
- DOCX là experimental cho đến khi có test upload, extract paragraph/table, retry, chunk, source viewer và generation.

### 8.3. Tinh giản Manage Page

`frontend/src/pages/ManagePage.jsx` hiện khoảng 3.053 dòng và chứa nhiều nhóm tác vụ.

Đề xuất chia thành ba tab:

1. `Tài liệu`.
2. `Ngân hàng câu hỏi`.
3. `Cần sửa theo Reviewer`.

Các chức năng sau chuyển vào menu `Công cụ`:

- Import/export.
- Coverage.
- Bulk metadata.
- Saved filters nâng cao.

Bulk action chỉ xuất hiện khi có lựa chọn.

Thay browser `alert/confirm` bằng:

- Inline validation.
- Toast cho kết quả ngắn.
- Modal xác nhận có mô tả ảnh hưởng.
- Batch result hiển thị từng item thành công/thất bại.

## 9. Hạ tầng kiểm thử

### 9.1. Unit/schema

Chạy mỗi commit:

- State transition.
- Pydantic validation.
- Permission helper.
- Evaluation policy.
- Export formatter.
- Parser và question data shape.

### 9.2. API integration

Sử dụng FastAPI TestClient và dependency override cho:

- Admin.
- Teacher A.
- Teacher B.
- Reviewer A.
- Reviewer B.
- Inactive user.
- Missing/invalid token.

Test phải kiểm tra:

- Status code.
- Response schema.
- Database side effect.
- Audit.
- Notification.
- Ownership.
- Version conflict.

Transaction/concurrency test cần MongoDB test replica set.

### 9.3. Frontend component test

Bổ sung test cho:

- Loading.
- Empty.
- API error.
- 401/403/409.
- Form validation.
- Reviewer claim/review.
- Admin user/catalog/job actions.
- Moodle mock wording.

### 9.4. UI E2E

Sử dụng Playwright với dữ liệu seed cố định:

1. Auth và route guard.
2. Upload hoặc chọn lại document READY.
3. Generate.
4. Lưu câu hỏi.
5. Sửa để tăng version.
6. Submit review.
7. Reviewer claim.
8. Xem source/evaluation.
9. Approve, needs revision hoặc reject.
10. Export GIFT/XML.
11. Admin xem dashboard/job/audit.

Không đưa tạo đề thi vào chuỗi E2E này.

### 9.5. AI/OCR smoke

Tách khỏi regression deterministic:

- Một PDF text nhỏ.
- Một PDF scan nhỏ.
- Một câu Đúng/Sai hoặc Trắc nghiệm.

Chỉ assert:

- Schema.
- Source.
- Status.
- Khả năng truy vết.

Không assert từng chữ do model sinh.

## 10. Dữ liệu test chuẩn

### Người dùng

- `admin.test`.
- `teacher.a`.
- `teacher.b`.
- `reviewer.a`.
- `reviewer.b`.
- Một Teacher inactive.
- Một Reviewer inactive.
- Một Admin active cuối cùng.

### Tài liệu

- PDF text hợp lệ.
- PDF scan hợp lệ.
- File sai định dạng.
- File quá dung lượng.
- Document READY.
- Document FAILED.
- Document PROCESSING.
- Document của Teacher khác.

### Câu hỏi

- DRAFT + NOT_STARTED.
- PENDING + QUEUED.
- PENDING + PASSED/GREEN.
- PENDING + FAILED/RED.
- PENDING đang được Reviewer A giữ lock.
- PENDING có lock hết hạn.
- NEEDS_REVISION.
- REJECTED.
- APPROVED đúng current version.
- APPROVED nhưng current version đã thay đổi.

### Admin

- Job QUEUED.
- Job PROCESSING.
- Job FAILED/ERROR.
- Job STALE.
- Job CANCELLED.
- Moodle target active.
- Moodle target inactive.
- Target giới hạn allowed roles.
- Policy hợp lệ và các policy fixture không hợp lệ.

## 11. Ma trận kiểm thử đầu vào/đầu ra

Mỗi test case phải ghi tối thiểu:

| Trường | Nội dung |
|---|---|
| Test ID | ID trong tài liệu |
| Priority | P0/P1/P2 |
| Role | Admin/Teacher/Reviewer/Public |
| Preconditions | Dữ liệu và trạng thái ban đầu |
| Input | Payload, file hoặc thao tác UI |
| Expected API | Status code và response |
| Expected DB | Record được tạo/sửa/không đổi |
| Expected audit | Action, actor, entity, metadata |
| Expected notification | Người nhận, type, deep link |
| Expected UI | Loading/success/error/redirect |
| Cleanup | Dữ liệu cần xóa/reset |
| Result | Pass/Fail/Blocked/Not run |

Không đánh dấu Pass nếu chỉ đúng UI nhưng DB, audit hoặc notification sai.

## 12. Thứ tự triển khai

### Sprint 1 — P0 correctness

- P0-01 đến P0-08.
- API auth matrix.
- Worker cancellation race test.
- Policy validation.
- Reviewer state transition tests.

### Sprint 2 — Reviewer

- Tinh giản Review Queue.
- `REV-01..REV-11`.
- Source viewer.
- Notification/deep link.
- Teacher → Reviewer → export E2E.

### Sprint 3 — Admin

- User pagination và identity consistency.
- Catalog/model/prompt/policy.
- Admin Jobs.
- Audit.
- Moodle mock.
- Admin component/E2E tests.

### Sprint 4 — Regression và NFR

- DOC/GEN/QUE.
- Transaction và concurrency.
- Secret redaction.
- Recovery.
- Bundle code splitting.
- Báo cáo test cuối.

Ước lượng một người: 10–15 ngày làm việc, không gồm Moodle REST thật và benchmark AI dài hạn.

## 13. Definition of Done

Một hạng mục chỉ hoàn thành khi:

- Backend enforce đúng, không chỉ disable nút trên frontend.
- Có test success.
- Có test invalid input.
- Có test forbidden/ownership.
- Có test version conflict hoặc concurrency nếu có mutation.
- Kiểm tra database side effect.
- Có audit cho thao tác quan trọng.
- Có notification nếu nghiệp vụ yêu cầu.
- UI có loading, empty, error và retry.
- Không dùng browser alert/confirm cho happy path chính.
- Test case được cập nhật `Pass/Fail/Blocked/Not run`.
- Frontend test, backend test và production build đều pass.

## 14. Sửa tài liệu kiểm thử

Ma trận truy vết trong tài liệu kiểm thử đang có một số điểm không khớp:

- Ghi `REV-01..REV-09`, nhưng phần chi tiết có `REV-01..REV-11`.
- Ghi `LMS-01..LMS-05`, nhưng phần chi tiết có `LMS-01..LMS-06`.
- Nhóm `USR/CAT` chưa được ánh xạ đầy đủ trong ma trận luồng.
- `NFR-06` đang gộp phần tạo đề thi; cần tách thành:
  - Teacher → Reviewer → export.
  - Tạo đề thi, nằm ngoài phạm vi kế hoạch này.

Cần sửa ma trận trước khi dùng làm báo cáo coverage chính thức.

## 15. Trạng thái thực hiện

Cập nhật ngày 30/07/2026.

### 15.1. Correctness và bảo mật — đã hoàn thành

- [x] Chỉ cho phép tạo review decision khi câu hỏi đang `PENDING`; điều kiện trạng thái được kiểm tra cả trước và trong atomic update.
- [x] Gỡ API cho phép client gửi trực tiếp điểm AI evaluation.
- [x] Giới hạn API xem generation job cho đúng chủ job hoặc Admin.
- [x] Dùng compare-and-set cho các transition của generation job; job đã hủy/lỗi không thể bị worker ghi đè thành `processing` hoặc `completed`.
- [x] Thêm cooperative cancellation trước/sau LLM và trước từng lần lưu câu hỏi.
- [x] Thêm finalization claim cho evaluation job; Admin cancel và worker ghi kết quả không thể cùng thành công.
- [x] Phân biệt evaluation job `CANCELLED` với `STALE`.
- [x] Validate evaluation policy: đúng bộ 5 tiêu chí, mỗi giá trị trong `0..1`, tổng weights bằng `1`, đủ ngưỡng và thỏa `yellow_min <= green_min <= pass_min`.
- [x] Chỉ cho phép một evaluation policy active trên toàn hệ thống; có transaction, unique partial index và bootstrap repair dữ liệu cũ.
- [x] Đổi UI nhập policy từ JSON textarea sang các ô số có nhãn, hiển thị tổng trọng số và cảnh báo thứ tự ngưỡng.
- [x] API frontend refresh token đúng một lần khi gặp 401; hết phiên mới đăng xuất và hiển thị lý do ở trang đăng nhập.
- [x] 403 do thiếu quyền không làm mất phiên; direct URL hiển thị trang 403 rõ ràng. Chỉ 403 do tài khoản bị khóa mới kết thúc phiên.
- [x] Thêm compensation cho cập nhật/vô hiệu hóa Firebase identity nếu MongoDB update thất bại.
- [x] Dùng assignment revision và compare-and-set cho claim/assign/release/review; Admin phải xác nhận và ghi lý do khi ghi đè active lock.
- [x] Chặn Admin duyệt thay Reviewer mà không có ghi chú.
- [x] Giữ `CANCELLED` là trạng thái terminal cho generation/evaluation và chặn side effect ghi muộn.

### 15.2. Reviewer — đã hoàn thành phần sửa chính

- [x] Ba tab chính: `Cần tôi xử lý`, `Chưa có người nhận`, `Đã xử lý`.
- [x] Bộ lọc chi tiết được đưa vào `Bộ lọc nâng cao`.
- [x] CTA `Bắt đầu duyệt` claim nguyên tử, sau đó tự mở workspace và chuyển sang hàng của Reviewer.
- [x] Reviewer chỉ thấy retry AI khi evaluation ở `ERROR/FAILED/STALE`.
- [x] Gỡ duyệt hàng loạt và enqueue AI hàng loạt khỏi happy path.
- [x] Admin dùng CTA `Phân công`; `Duyệt thay Reviewer` là thao tác phụ và bắt buộc lý do.
- [x] Source PDF/OCR/evidence, evaluation, review và publication được tải độc lập; lỗi một phần không xóa các phần đã tải thành công.
- [x] Deep link `questionId` được validate; notification vẫn điều hướng kể cả khi đánh dấu đã đọc lỗi.
- [x] Sửa bộ lọc `UNASSIGNED` để nhận cả dữ liệu cũ chưa có trường `review_assignment.status`.
- [x] Kiểm thử trực tiếp bằng tài khoản Reviewer demo: mở hàng chưa phân công, chọn câu, xem source/evidence, claim, kiểm tra lock/action, release và xác nhận dữ liệu được hoàn tác.

### 15.3. Admin — đã hoàn thành phần sửa chính

- [x] User Admin dùng server-side search/role/status/pagination; số lượng không còn bị giới hạn bởi 100 record đầu.
- [x] Đổi wording xóa thành khóa/mở tài khoản; confirmation nêu ảnh hưởng và validation hiển thị inline.
- [x] Model phải health-check thành công với đúng config hiện hành trước khi activate.
- [x] Prompt phải lưu draft và test-build đúng content hash trước khi activate.
- [x] Deactivate môn/chương/CLO hiển thị usage count và yêu cầu xác nhận ảnh hưởng.
- [x] Job list/filter/pagination/summary xử lý toàn bộ dữ liệu; Retry/Cancel theo `can_retry/can_cancel`.
- [x] Audit loại secret/token khỏi metadata trả về.
- [x] Moodle Admin dùng wording `Mô phỏng Moodle` và publication có server-side pagination.
- [x] Attention link của Dashboard giữ đúng filter đích cho review, job retryable, job quá ngưỡng và tài liệu lỗi.
- [x] Cho Admin truy cập `/quan-ly`; trước sửa, attention link tài liệu lỗi trả 403 dù backend đã cho phép Admin.
- [x] Tách `Quản lý nội dung` thành ba tab: ngân hàng câu hỏi, tài liệu nguồn và cần sửa theo Reviewer.
- [x] Tài liệu có filter trạng thái và phân trang; link `/quan-ly?tab=documents&status=FAILED` mở đúng `FAILED`.
- [x] Gỡ thao tác duyệt trùng lặp khỏi Question Bank của Admin; Admin xử lý tại Review Queue.

### 15.4. Teacher, tài liệu và Question Bank — đã sửa UX chính

- [x] Coverage và import/export được thu gọn vào khu vực công cụ.
- [x] Bulk action chỉ xuất hiện sau khi có ít nhất một câu được chọn.
- [x] Lịch sử evaluation/review/publication/version tải độc lập.
- [x] PDF được ghi rõ là phạm vi nghiệm thu; DOCX được gắn nhãn `Thử nghiệm`.
- [x] Tab `Cần sửa theo Reviewer` mở sẵn filter `NEEDS_REVISION`.

### 15.5. Kết quả regression hiện tại

- Backend sau khi rebase lên `origin/full-dev`: `124 passed`.
- Frontend sau khi rebase lên `origin/full-dev`: `40 passed`.
- Frontend production build: thành công.
- Browser smoke trên local với tài khoản Admin/Reviewer demo:
  - Admin attention filter review/job/tài liệu: pass.
  - Admin access `/quan-ly`: pass sau khi sửa route permission.
  - Reviewer default queue, unassigned queue, source/evidence, claim/release: pass.
  - Dữ liệu claim dùng để smoke test đã được release về trạng thái ban đầu.
- `git diff --check`: không có lỗi whitespace.
- Cảnh báo còn lại: bundle JavaScript chính khoảng 830 KB, lớn hơn ngưỡng cảnh báo 500 KB của Vite.

### 15.6. Phần chưa hoàn thành

- [ ] Gắn trạng thái Pass/Fail/Blocked/Not run cho từng test case trong ma trận 68 test ngoài phạm vi tạo đề thi.
- [ ] Component test cho các page Reviewer/Admin; hiện frontend vẫn chủ yếu là helper/util test.
- [ ] Playwright E2E tự động với seed cố định cho Teacher → Reviewer → export; browser smoke hiện mới chạy thủ công có kiểm soát.
- [ ] API auth matrix đầy đủ với FastAPI TestClient cho missing/invalid/inactive token và mọi role.
- [ ] Transaction/concurrency trên MongoDB replica set thật; test hiện tại chủ yếu dùng fake collection/service.
- [ ] Chạy trọn ma trận `DOC/GEN/QUE`, AI/OCR smoke với PDF text và PDF scan chuẩn.
- [ ] Code splitting để xử lý cảnh báo bundle lớn.
