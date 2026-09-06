# QBankCTU — Rà soát lại 8 giai đoạn A–H

Ngày kiểm tra: **06/09/2026** (Asia/Saigon). Mã nguồn: commit **46a89565d2deb80fabd268d67b6e9df3bfe74df2**, workspace `D:/NCKH`.

Tài liệu đối chiếu: [PROJECT_COMPLETION_MASTER_PLAN.md](D:/NCKH/docs/PROJECT_COMPLETION_MASTER_PLAN.md), đặc biệt mục 14 và acceptance gates G1–G10. Đã đối chiếu **đủ 42 đầu việc thuộc 8 giai đoạn**, đọc các đường xử lý chính, chạy lại kiểm thử hiện có và thực hiện các phép thử bổ sung bằng dữ liệu tổng hợp.

Phạm vi bàn giao lần này là **báo cáo kiểm tra**, chưa sửa logic sản phẩm. Master plan được giữ nguyên. Các trạng thái và số liệu cũ trong master plan là lịch sử triển khai, không thay thế kết quả rà soát này.

## 1. Kết luận

**Chưa thể xác nhận code đã hoàn tất cả 8 giai đoạn.** Các module chính và phần lớn hạ tầng kỹ thuật đã có, nhưng vẫn tồn tại lỗi thực thi trong các điều kiện nghiệm thu quan trọng. Không chỉ còn thiếu corpus, Moodle của trường hoặc chữ ký UAT.

- Bộ kiểm thử hiện có đạt **225 backend tests**, **9 Mongo integration tests**, **47 frontend tests**, lint hai phía, build frontend và **3 browser tests về quyền truy cập trang**.
- Kiểm tra bổ sung vẫn tái hiện được: duyệt khi biểu mẫu rỗng/có tiêu chí FAIL; ghi đè revision OCR đã hoàn tất; xuất sai thứ tự đáp án; publish phiên bản cũ khi câu hiện tại đã về DRAFT; cấp membership cho identity Moodle inactive; chấp nhận trang cuối sync không có chuỗi checkpoint trước đó.
- Cấu hình production hợp nhất vẫn publish MongoDB ra cổng host 27017. Plugin Moodle mà adapter gọi chưa có implementation trong repository. Backend Dockerfile chưa cài Chromium cho chức năng xuất PDF.
- Giai đoạn A có thể giữ trạng thái **baseline kỹ thuật**, nhưng B cần mở lại phần invariant; C–H cần sửa các thiếu sót kỹ thuật bên dưới rồi mới tiếp tục nghiệm thu thực tế.

Không đưa ra phần trăm hoàn thành: số lượng test hoặc file không đo được tính đúng của toàn bộ quy trình.

## 2. Phương pháp và kết quả kiểm chứng

### 2.1. Môi trường và giới hạn

- Dùng CodeGraph trước để tìm symbol/luồng; đọc trực tiếp những phần công cụ không trả về, tài liệu và cấu hình.
- Backend chạy **source đang có trong workspace**, mount chỉ đọc vào container kiểm tra. Python trong image có sẵn là **3.10.21**, khác bản baseline 3.10.14. Image gốc: `nckh-backend:latest`, ID `sha256:032159e5a83fc5eb52f89fe97f84120f16c958652b2f7b16d456afffd7d99c7b`.
- Image cũ thiếu PyMuPDF; đã bổ sung **PyMuPDF 1.28.2 chỉ trong container kiểm tra tạm**, không thay requirements/code/image sản phẩm. pytest 9.1.1, Ruff 0.16.5.
- MongoDB dùng image `mongo:7.0`, replica set riêng `auditrs`, network/container riêng, không publish cổng host và không dùng database đang vận hành.
- Frontend chạy Node **24.12.0**, npm **11.14.1** trên máy hiện tại. Node này nằm ngoài engines `>=20.19.0 <21` của dự án. Kết quả đạt không thay thế kiểm tra fresh install trên Node 20.19.0.
- Các phép thử lỗi Moodle dùng adapter giả và dữ liệu tổng hợp; **không gửi câu hỏi tới Moodle thật**. Không chạy suy luận Ollama/OCR scan trên corpus CTDL, không benchmark GPU, không UAT và không kiểm thị giác các trang PDF/DOCX thật.
- Kết quả local không chứng minh workflow GitHub Actions trên remote đã chạy đạt.

### 2.2. Các lệnh đã thực thi

| Kiểm tra | Lệnh chính | Kết quả mới |
|---|---|---|
| Baseline | `py scripts/verify_baseline.py` | PASS; giới hạn: kiểm manifest/file hiện có, không xác nhận corpus nghiệm thu |
| Backend | `python -m pytest tests -q -rs -p no:cacheprovider` | **225 passed, 9 skipped**, thêm 14 subtests passed; 6,84 giây |
| Mongo profile | `RUN_MONGO_INTEGRATION=1 python -m pytest tests/test_mongo_integration.py -q -rs -p no:cacheprovider` | **9 passed**, 1,40 giây; không skip |
| Backend lint | `python -m ruff check core modules workers tests --no-cache` | PASS theo cấu hình hiện tại; Ruff exclude OCR/RAG và chỉ bật một nhóm rule correctness |
| Frontend unit | `npm test` | **47 passed**, không failed/skipped |
| Frontend lint | `npm run lint` | PASS |
| Frontend build | `npm run build` | PASS |
| Browser | `npm run test:e2e` | **3 passed**, 6,1 giây; chỉ role-access |
| Cấu hình deployment | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config --format json` | Hợp nhất được; phát hiện cổng MongoDB chưa bị gỡ |
| Kiểm tra bổ sung | Hai script kiểm tra trong thư mục audit tạm | Tái hiện các trường hợp sai ở mục 4 |

**Giải thích các lượt thử trước:** lượt đầu có 5 failures: 4 do image thiếu `fitz`, 1 do test hard-code tên DB `NCKH` trong khi môi trường dùng `NCKH_audit_auth`. Sau bổ sung PyMuPDF còn 1 failure do tên DB. Lượt cuối dùng tên `NCKH`/`rag_database` **trên Mongo cô lập** và đạt 225 tests. Không tính các lỗi setup này thành lỗi sản phẩm; không xóa hoặc bỏ qua test để lấy kết quả đạt. 9 tests skipped ở suite chính được chạy thành công trong profile riêng.

Log cục bộ: [thư mục audit](D:/NCKH/tmp/audit-20260906), gồm `backend-tests-final.log`, `mongo-tests.log`, `backend-results.xml`, `mongo-results.xml`, `frontend-tests.log`, `frontend-lint.log`, `frontend-build.log`, `frontend-e2e.log`, `compose-ports.json` và kết quả các phép thử. Đây là artifacts tạm, không phải hồ sơ đã commit.

### 2.3. Mức bao phủ của các test theo giai đoạn

| Nhóm chuyên biệt | Số test đạt | Giới hạn đáng chú ý |
|---|---:|---|
| Stage B | 5 | Có scope/self-review/bulk export/local-only/bearer; chưa chặn biểu mẫu APPROVED sai |
| Document pipeline C | 9 | Có extraction-first, ký hiệu code, PDF hỏng/mã hóa, claim lease; chưa thử stale writer ghi page set đã hoàn tất |
| Stage D | 8 | Có fusion, hard heading, prompt manifest, role/config digest; benchmark mới thử hàm recall bằng fixture |
| Stage E | 11 | Có typed/evidence/fingerprint/checkpoint; compiler success dùng mock |
| Stage F | 4 | Có Bloom cao, allocation, mapping và HTML sinh viên; chưa kiểm thứ tự đáp án ở bảng đáp án |
| Stage G | 10 | Gồm 7 serializer cases + capability, secret, timeout; chưa có Moodle thật và chưa bao phủ identity sync/outbox đầy đủ |
| Stage H | 3 | Có alert, holdout aggregate, readiness; không thay crash/restore/load/UAT thật |

Các test trên là thành phần của suite 225, không cộng thêm lần nữa. Những test còn lại nằm trong schema/workflow/generation/infrastructure và các nhóm hiện hữu khác.

## 3. Đối chiếu đủ 42 đầu việc

Quy ước: **Có** = thấy implementation và kiểm tra hiện có hỗ trợ; **Một phần** = còn thiếu phần thuộc acceptance; **Cần sửa** = đã xác định lỗi/điều kiện chưa được cưỡng chế; **Chờ nghiệm thu** = cần dữ liệu hoặc hoạt động thực tế chưa thực hiện. “Có” không có nghĩa mọi tình huống cạnh tranh hoặc môi trường đã được chứng minh đúng.

### A — Baseline và hợp đồng

**Đánh giá: giữ baseline kỹ thuật; chưa hoàn tất bằng chứng ngoại vi.**

| ID | Đối chiếu code/tài liệu | Kết quả |
|---|---|---|
| A01 | Có inventory, requirement trace, phạm vi sản phẩm, README và baseline contract. Trace còn dẫn `F01–F05`, `G01–G06`, `H01–H06` trong khi backlog hiện chỉ có F04/G05/H04. | Có; cần đồng bộ tài liệu |
| A02 | Có `.python-version`, `.nvmrc`, requirements, env examples, runtime manifest, CI. Lần kiểm tra này chưa dùng đúng runtime baseline/fresh install; digest model thực vẫn thiếu. | Một phần |
| A03 | Dataset manifest có rubric và split policy; entry PDF hiện ghi `acceptance_corpus=false`, `required_in_repository=false`. Assets CTDL có license, official CLO, query/evidence labels vẫn nằm trong `required_external_assets`. | Baseline có; chờ dữ liệu nghiệm thu |
| A04 | Có Moodle integration contract và runbook. Version/build/course/category/service account/round-trip fixture thực chưa chốt; hợp đồng spike vẫn yêu cầu những thứ này. | Baseline có; spike thực chưa nghiệm thu |

Căn cứ: [baseline contract](D:/NCKH/docs/BASELINE_CONTRACT.md), [dataset manifest](D:/NCKH/docs/baseline_dataset_manifest.json), [runtime manifest](D:/NCKH/docs/runtime_manifest.json), [Moodle contract](D:/NCKH/docs/MOODLE_INTEGRATION_CONTRACT.md).

**Điều kiện đóng:** sửa trace ID, chạy fresh install đúng runtime và lưu kết quả; chốt assets/nhãn/model runtime/Moodle facts trước các gate phụ thuộc. Baseline verifier PASS không có nghĩa đã có 1 corpus CTDL đạt chuẩn: file không bắt buộc có thể vắng mà script vẫn báo verified.

### B — Quyền, export và invariant

**Đánh giá: cần mở lại B04/B05/B07; không giữ tuyên bố Gate B hoàn tất toàn bộ.**

| ID | Đối chiếu code/tài liệu | Kết quả |
|---|---|---|
| B01 | Có `subject_memberships`, `active_subject_ids`, `has_subject_access`, backfill và kiểm deny-by-default. Migration rehearsal cũ chưa chạy lại trong phiên này. | Có |
| B02 | Scope resolver đã nối vào các service tài liệu/câu hỏi/đề và route capabilities; test hiện có đạt. Quyền đồng bộ từ Moodle còn lỗi ở G02. | Có nền tảng; cần regression liên thông G02 |
| B03 | Bulk GIFT/XML qua backend; cùng `_moodle_export_error`, có expected version và lỗi từng item, không tạo file khi batch chứa câu không hợp lệ. | Có; test mixed batch đạt |
| B04 | Có chống self-review, quyền override, lock và CAS. Nhưng backend vẫn APPROVED biểu mẫu rỗng hoặc chứa tiêu chí FAIL; xem R01. | **Cần sửa** |
| B05 | LOCAL_ONLY chặn cloud runtime/host ngoài allowlist. Chưa kiểm model đã cài/được allowlist; `model_digest` là hash cấu hình; xem R10. | **Một phần** |
| B06 | Session repository bỏ raw bearer mới; có migration xóa token, env reference cho Moodle secret và kiểm metadata evaluator. | Có; regression đạt |
| B07 | UI dùng capability và backend export; tuy nhiên UI/backend khác điều kiện approve. Browser tests chưa kiểm batch/version race trên giao diện. | **Cần sửa và bổ sung acceptance** |

Căn cứ: [access policy](D:/NCKH/backend/core/access_policy.py:19), [review service](D:/NCKH/backend/modules/questions/workflow_service.py:2336), [bulk export](D:/NCKH/backend/modules/questions/workflow_service.py:2963), [model policy](D:/NCKH/backend/modules/generation/llm/model_registry.py:68), [Stage B tests](D:/NCKH/backend/tests/test_stage_b_contracts.py).

**Điều kiện đóng:** server cưỡng chế đủ bộ tiêu chí duyệt, unique criterion keys, không APPROVED khi FAIL; kiểm model release đã chốt; bổ sung negative tests và kiểm UI/backend trên cùng dữ liệu.

### C — Nguồn PDF và durable document pipeline

**Đánh giá: có pipeline mới, còn lỗi bất biến ở page persistence; chưa chỉ là chờ corpus.**

| ID | Đối chiếu code/tài liệu | Kết quả |
|---|---|---|
| C01 | Cleaning giữ raw metadata, ký hiệu và indentation trong regression. Không còn có thể kết luận lỗi strip code cũ vẫn nguyên trạng. | Có; cần corpus thật |
| C02 | Extraction-first theo trang, OCR fallback, lỗi corrupt/encrypted và page limit có implementation/tests. Scan/mixed corpus thực chưa chạy. | Có; chờ nghiệm thu |
| C03 | Có processing revisions, correction provenance và page-set manifest. `save_pages` vẫn xóa/ghi lại revision COMPLETED, không kiểm fencing token; R02. | **Cần sửa** |
| C04 | OCR/CHUNK/INDEX đã vào Mongo worker, có lease/heartbeat/checkpoint/cancel. OCR checkpoint hiện ghi tiến độ; retry vẫn gọi lại pipeline toàn PDF, chưa resume từ kết quả từng trang đã lưu. Ghi pages chưa được fencing bảo vệ đầy đủ. | **Một phần/Cần sửa** |
| C05 | Có candidate activation, coverage validation, index manifest và switch/rollback; Mongo tests đạt. Tính toàn vẹn nguồn phía trước còn bị R02 tác động. Chưa crash drill toàn chuỗi Mongo/file/Chroma. | Có; cần nghiệm thu recovery |
| C06 | Manage UI hiển thị revision, raw/cleaned source, visual flags và correction. Chưa UAT đối chiếu PDF scan/code/lưu đồ thực. | Có; chờ nghiệm thu |

Căn cứ: [extraction engine](D:/NCKH/backend/modules/ocr/easyocr_engine.py:233), [OCR worker path](D:/NCKH/backend/modules/ocr/ocr.py:62), [document worker](D:/NCKH/backend/modules/documents/worker.py:30), [save_pages](D:/NCKH/backend/modules/documents/repository.py:871), [Mongo integration](D:/NCKH/backend/tests/test_mongo_integration.py:230).

**Điều kiện đóng:** ngăn stale/completed writer trước mọi side effect, bảo vệ commit page set; lưu/resume output checkpoint đúng yêu cầu hoặc công bố rõ retry toàn tác vụ; chạy kill/restart ở từng checkpoint và T01–T03 trên corpus đã chốt.

### D — Retrieval, prompt và model release

**Đánh giá: đã có phần lớn đường xử lý, còn thiếu enforcement ngân sách và provenance model thực.**

| ID | Đối chiếu code/tài liệu | Kết quả |
|---|---|---|
| D01 | Chunks có token estimate, protected block, parent/source span và metadata. Retrieval vẫn nhận chunk đầu lớn hơn context budget; R11. | **Một phần** |
| D02 | Dense/lexical độc lập và fusion có trace; heading không khớp không fallback âm thầm. Lexical lấy prefix theo chunk_no rồi mới rank, có thể bỏ evidence cuối tài liệu khi vượt candidate limit. | Có; cần sửa/đo coverage |
| D03 | Có benchmark dense/lexical/hybrid, fixture hash/recall/latency và index switch/rollback. Chưa có báo cáo so embedding trên corpus độc lập, size/quality comparison để chọn model. | Harness có; chờ benchmark |
| D04 | Có template/release/rendered hashes, DB prompt fail rõ và preview. Chỉ dẫn chính/repair đã Việt hóa so với ghi chú cũ ở mục 19 master plan. | Có |
| D05 | Có ba logical roles, structured output và resource profile. Digest chưa là digest weights thật; GPU OCR vẫn semaphore trong process, chưa chứng minh scheduler chung OCR/LLM. | **Một phần** |
| D06 | UI tách mục/chương nhập dưới dạng target heading, topic, CLO và instruction/code mode; có thông báo thiếu evidence. Chưa browser test toàn luồng và corpus chapter mapping. | Có; chờ nghiệm thu |

Căn cứ: [retrieval](D:/NCKH/backend/modules/rag/search.py:262), [lexical candidates](D:/NCKH/backend/modules/rag/search.py:137), [model snapshot](D:/NCKH/backend/modules/generation/llm/model_registry.py:20), [embedding manifest](D:/NCKH/backend/modules/rag/mongodb.py:23), [benchmark script](D:/NCKH/backend/scripts/benchmark_retrieval.py), [prompt builder](D:/NCKH/backend/modules/generation/prompt_builder.py:51).

**Điều kiện đóng:** xử lý oversize có chủ đích, truy xuất lexical không giới hạn mù phần đầu, lưu digest model thực, đo recall@5/latency theo query slice. Chưa có căn cứ tuyên bố đạt G4 ≥ 0,85.

### E — Chất lượng câu hỏi, evaluator và HITL

**Đánh giá: evaluator có tiến bộ rõ, nhưng typed validation và backend review chưa kín.**

| ID | Đối chiếu code/tài liệu | Kết quả |
|---|---|---|
| E01 | Bảy dạng có typed contract chung AI/manual/import. Ba ví dụ invalid cũ được cải thiện, nhưng matching vẫn chấp nhận một vế trái có hai đáp án và bỏ qua rác cuối input; R09. | **Cần sửa** |
| E02 | Evidence quote/offset/hash được đối chiếu chunk; source viewer dùng OCR job snapshot; evaluator không còn cố định ba nguồn đầu. Test exact span và nguồn thứ 5 đạt. Derived/code evidence thực chưa được nghiệm thu. | Có; chờ nghiệm thu |
| E03 | Có hard failures, NO_DATA/score coverage, server aggregate và fingerprint policy/input/model. Chưa rubric chuyên gia đã ký, chưa hiệu chuẩn false GREEN; model fingerprint chịu giới hạn R10. | Có nền tảng; chờ hiệu chuẩn |
| E04 | Có C/C++ syntax-only subprocess với timeout/prlimit và toolchain snapshot. Không chạy thuật toán để chứng minh đáp án tracing/complexity đúng. Các code fence từ stem/options/explanation bị ghép chung, chưa phân biệt code cố ý sai trong bài tìm lỗi. | **Một phần so với acceptance T14** |
| E05 | Có checkpoint theo generation plan, partial result, dedupe và re-evaluation fingerprint. Test resume bỏ qua plan đã xong đạt. Chưa kill worker thật giữa persist question/checkpoint. | Có; cần crash acceptance |
| E06 | UI có evidence spans, rubric, hard failure/NO_DATA/override. Backend chấp nhận form mà UI cấm; R01. Chưa independent reviewer study/inter-rater agreement. | **Cần sửa và nghiệm thu** |

Căn cứ: [typed contract](D:/NCKH/backend/modules/questions/contracts.py:130), [Stage E tests](D:/NCKH/backend/tests/test_stage_e_contracts.py), [code sandbox](D:/NCKH/backend/modules/questions/code_sandbox.py:44), [evaluator guardrails](D:/NCKH/backend/modules/questions/workflow_service.py:892), [review UI](D:/NCKH/frontend/src/pages/ReviewQueuePage.jsx:1172).

**Điều kiện đóng:** sửa matching/review validation; xác định loại code question được hỗ trợ và bằng chứng đáp án tương ứng; hiệu chuẩn trên holdout với reviewer độc lập. Syntax PASS không phải đáp án đúng hoặc chất lượng câu hỏi PASS.

### F — Bộ đề dùng được

**Đánh giá: blueprint/variant đã có; đầu ra đáp án vẫn sai với dạng sắp xếp và môi trường PDF chưa đầy đủ.**

| ID | Đối chiếu code/tài liệu | Kết quả |
|---|---|---|
| F01 | Blueprint V2 có Bloom set/CLO/type/marks; mapping vận dụng cao giữ {4,5,6}; regression đạt. | Có |
| F02 | Eligible pool chia sẻ cho manual/auto, allocation ô khan hiếm, backtracking có giới hạn, coverage validation trước READY/FINALIZED. | Có; cần tải/overlap corpus thực |
| F03 | Có CAS trên exam, immutable snapshot/checksum, seed/permutation và typed shuffle. Chưa kiểm cạnh tranh đồng thời sửa question/finalize/variant bằng DB thật; test mapping hiện chưa chứng minh mọi mã đề có đáp án đúng đến file xuất. | Có; cần concurrency/E2E acceptance |
| F04 | Có preview, PDF/DOCX và tách đề/đáp án. Hàm chung xuất đáp án phá thứ tự SAP_XEP; Dockerfile thiếu Chromium; rendering rich content còn đơn giản, chưa QA code/formula/image/table. | **Cần sửa** |

Căn cứ: [allocation/coverage](D:/NCKH/backend/modules/exams/service.py:221), [finalization CAS](D:/NCKH/backend/modules/exams/repository.py:104), [variant shuffler](D:/NCKH/backend/modules/exams/service.py:687), [export context](D:/NCKH/backend/modules/exams/pdf_service.py:31), [backend Dockerfile](D:/NCKH/backend/Dockerfile).

**Điều kiện đóng:** giữ nguyên thứ tự đáp án theo qtype trong preview/PDF/DOCX; cài/kiểm renderer trong backend image; QA từng trang thật và đối chiếu answer key sau shuffle của đủ bốn mã đề.

### G — Moodle identity và publication thật

**Đánh giá: có backend connector; chưa đủ implementation đầu cuối và còn lỗi identity/outbox.**

| ID | Đối chiếu code/tài liệu | Kết quả |
|---|---|---|
| G01 | Có backend serializers và qtype capability matrix. Tests kiểm XML text/qtype, chưa import/chấm round-trip trên Moodle. Ordering phụ thuộc plugin. | Có phía ứng dụng; chờ round-trip |
| G02 | Có external-ID key, link token, sync page replay và revocation. Không chặn identity inactive; chưa xác minh thứ tự/đủ trang trước revoke toàn site; R06. | **Cần sửa** |
| G03 | Python adapter gọi ba hàm `local_nckh_*`, nhưng không có implementation PHP/plugin tương ứng trong `moodle/` của repository. Runbook mới mô tả contract phải cung cấp. | **Một phần; thiếu phía Moodle** |
| G04 | Có outbox, claim, lease, UNKNOWN/reconcile. Worker không kiểm lại approved-current trước remote write; HTML/JSON lỗi có thể bị ghi FAILED thay UNKNOWN; R05/R07. | **Cần sửa** |
| G05 | Admin UI có target config, health, worker/retry/reconcile; runbook có. Chưa chứng minh target/course đúng quyền bằng Moodle thật; trạng thái UI phụ thuộc các lỗi G02/G04. | Có UI; chờ sửa và nghiệm thu |

Căn cứ: [adapter](D:/NCKH/backend/modules/moodle/adapter.py:14), [identity sync](D:/NCKH/backend/modules/moodle/identity_service.py:67), [publication worker](D:/NCKH/backend/modules/moodle/publication_worker.py:62), [connector runbook](D:/NCKH/docs/MOODLE_CONNECTOR_RUNBOOK.md), [Stage G tests](D:/NCKH/backend/tests/test_stage_g_contracts.py).

**Điều kiện đóng:** có remote implementation được version-control hoặc dependency phát hành rõ; sửa sync/outbox; kiểm idempotency, timeout, verify-read, qtype grading và revocation trên target thật. SSO và tạo Moodle Quiz vẫn là phạm vi riêng, không tính ngầm là thiếu sót G01–G05.

### H — Nghiệm thu, vận hành và báo cáo

**Đánh giá: có harness/checklist, còn thiếu cả kiểm thử kỹ thuật lẫn kết quả nghiệm thu.**

| ID | Đối chiếu code/tài liệu | Kết quả |
|---|---|---|
| H01 | CI có suite chính, Mongo profile, Moodle contract, FE lint/build và browser. Browser chỉ inject role vào localStorage rồi kiểm redirect/heading; không chạy upload→generate→review→exam→Moodle. | **Một phần** |
| H02 | Có readiness/alerts, production compose, bounded load smoke, Mongo dump/restore script. Compose vẫn mở Mongo; dump/restore chưa bao gồm artifact storage và Chroma rebuild verification; chưa đo RTO/RPO/crash/load. | **Cần sửa và thực thi drill** |
| H03 | Có aggregate report giữ denominator/exclusion/reviewer count. Chưa báo false GREEN/confidence interval/inter-rater agreement; `split` chỉ là nhãn tham số, không kiểm tính đồng nhất split của input; thiếu corpus và nghiên cứu thật. | **Harness một phần; chưa nghiệm thu** |
| H04 | Có guide/runbook/UAT scripts. Chưa có biên bản người ngoài nhóm dev, bộ demo đã duyệt có license, video và QA thị giác toàn bộ đầu ra. | Chờ nghiệm thu |

Căn cứ: [CI](D:/NCKH/.github/workflows/p0-tests.yml), [role-access E2E](D:/NCKH/frontend/e2e/role-access.spec.js:3), [production compose](D:/NCKH/docker-compose.prod.yml), [restore drill](D:/NCKH/scripts/mongo_backup_restore_drill.py), [holdout report](D:/NCKH/scripts/holdout_report.py:11), [operations runbook](D:/NCKH/docs/OPERATIONS_ACCEPTANCE_RUNBOOK.md).

**Điều kiện đóng:** full workflow E2E trên services thật, release profiles không skip, cấu hình production đã kiểm sau merge, restore cả Mongo+artifacts rồi rebuild/search/source verification; nghiên cứu và UAT có bằng chứng lưu trữ.

## 4. Phát hiện cần xử lý, theo ưu tiên

P0: sai quyền/quyết định duyệt, sai nguồn/đáp án hoặc phá invariant phát hành. P1: thiếu chức năng bắt buộc, recovery hoặc khả năng tái hiện. Mỗi phép thử dưới đây chỉ chứng minh hành vi được mô tả; không được hiểu là đã tấn công hệ thống đang chạy hoặc publish Moodle thật.

### R01 — P0 — Server vẫn duyệt form rỗng hoặc có tiêu chí FAIL

- **Vị trí:** [ReviewCreateRequest](D:/NCKH/backend/modules/questions/workflow_schemas.py:106), [review](D:/NCKH/backend/modules/questions/workflow_service.py:2336), đối chiếu [UI validation](D:/NCKH/frontend/src/pages/ReviewQueuePage.jsx:1182).
- **Đã tái hiện qua service + Mongo cô lập:** câu PENDING/evaluation PASSED, reviewer khác tác giả, lock còn hạn. Gửi APPROVED với `review_form={}` → lưu APPROVED, 0 tiêu chí. Gửi một tiêu chí `faithfulness=FAIL` → cũng lưu APPROVED.
- **Nguyên nhân:** schema chỉ bắt lý do REJECTED/issue NEEDS_REVISION; service không kiểm đủ/unique năm tiêu chí và không chặn FAIL như UI.
- **Cần sửa:** đưa quy tắc vào backend, kiểm bộ keys/ratings và evidence references theo version. Regression API/service cho thiếu, trùng, FAIL, NO_DATA theo policy đã chốt. Tác động B04/B07/E06, G1/G7.

### R02 — P0 — Page persistence không bảo vệ revision đã hoàn tất khỏi writer cũ

- **Vị trí:** [save_pages](D:/NCKH/backend/modules/documents/repository.py:871), [caller](D:/NCKH/backend/modules/ocr/ocr.py:114).
- **Đã tái hiện:** tạo job/revision COMPLETED có page `verified old`; gọi `save_pages` cùng job với nội dung mới → page cũ bị thay bằng `late stale overwrite`.
- **Nguyên nhân:** chỉ kiểm job thuộc document và loại OCR; `delete_many` theo revision không kiểm state/worker/fencing. Caller kiểm checkpoint sau khi đã ghi pages. Writer mất lease giữa checkpoint cuối và save có thể ghi trước khi phát hiện lease lost.
- **Cần sửa:** fencing/CAS và commit bất biến bao phủ pages, manifest, artifact activation; không chỉ bảo vệ cập nhật status. Test hai worker và revision đã được chunks/questions tham chiếu. Tác động C03/C04/C05, G2/G10.

### R03 — P0 — Bảng đáp án làm sai câu sắp xếp

- **Vị trí:** [_build_context](D:/NCKH/backend/modules/exams/pdf_service.py:43).
- **Đã tái hiện:** SAP_XEP có `correct_answer="B,A,D,C"` → `answer_rows[0].answer="A, B, C, D"`.
- **Nguyên nhân:** chuyển đáp án thành `set`, sau đó `sorted` để render. Thứ tự bị mất dù variant shuffler đã giữ mapping đúng.
- **Cần sửa:** render theo qtype; ordering giữ sequence, matching giữ pairs, choice/multi-answer mới xử lý như tập phù hợp. Kiểm cả PDF/DOCX vì dùng chung context. Tác động F03/F04, G8.

### R04 — P0 — Production override chưa đóng cổng MongoDB

- **Vị trí:** [base compose](D:/NCKH/docker-compose.yml), [production override](D:/NCKH/docker-compose.prod.yml).
- **Đã thực thi:** `docker compose ... config --format json` vẫn có Mongo `target=27017`, `published=27017`, không giới hạn `host_ip`. Frontend cũng giữ port 80 của base và thêm 127.0.0.1:8080.
- **Nguyên nhân:** `ports: []` không gỡ published ports của base trong cấu hình hợp nhất hiện tại. Base Mongo không bật authentication.
- **Cần sửa:** cấu hình production độc lập hoặc reset/override ports đúng với Compose runtime; kiểm JSON hợp nhất trong CI. Chưa kết luận host thực sự truy cập được từ Internet vì còn phụ thuộc firewall/network; sai lệch giữa cấu hình và runbook đã được xác nhận. Tác động H02 và tuyên bố an toàn deployment.

### R05 — P0 — Publication worker có thể gửi phiên bản không còn được duyệt hiện hành

- **Vị trí:** [_process](D:/NCKH/backend/modules/moodle/publication_worker.py:62).
- **Đã tái hiện:** publication tham chiếu v1, question hiện tại v2/DRAFT và `approved_version_id=None`; adapter giả vẫn được gọi và publication ghi PUBLISHED.
- **Nguyên nhân:** eligibility được kiểm lúc enqueue, worker chỉ kiểm question/version tồn tại. Điều kiện APPROVED ở cập nhật aggregate sau remote call không ngăn remote write đã xảy ra.
- **Cần sửa:** tái kiểm version/state/scope trước side effect và chốt policy khi quyền/approval đổi lúc đang publish. Test enqueue→edit/revoke→worker. Tác động B03/G04, invariant approved-current.

### R06 — P1 — Moodle sync chưa xử lý khóa identity và tính đầy đủ của phiên sync

- **Vị trí:** [membership upsert và revoke](D:/NCKH/backend/modules/moodle/identity_service.py:82).
- **Đã tái hiện 1:** identity đã lưu `is_active=false`, membership đầu vào active → lưu membership ACTIVE.
- **Đã tái hiện 2:** gửi `is_last_page=true`, checkpoint `page-99` của sync mới chưa có trang trước → nhận thành công và revoke membership không mang sync_id mới.
- **Nguyên nhân:** upsert chỉ nhìn `item.is_active`; trang cuối không có gate kiểm chuỗi checkpoint/trạng thái run đầy đủ và revoke theo toàn site.
- **Cần sửa:** account inactive phải ảnh hưởng quyền; sync run có sequence/completion/ownership và chỉ revoke sau snapshot đầy đủ, đúng phạm vi. Thử missing page, concurrent sync, replay và lỗi link. Tác động G02, T22/T28.

### R07 — P1 — Response Moodle không phải JSON có thể bị coi nhầm là thất bại an toàn để retry

- **Vị trí:** [_call](D:/NCKH/backend/modules/moodle/adapter.py:29), [exception handling worker](D:/NCKH/backend/modules/moodle/publication_worker.py:110).
- **Đã tái hiện:** response HTTP 502 chứa HTML khiến `_call` ném `JSONDecodeError`, không phải `MoodleRemoteUncertain`.
- **Nguyên nhân:** gọi `response.json()` trước khi kiểm HTTP 5xx. Worker bắt exception chung và gắn FAILED/CONFIRMED_FAILURE; đường này chưa chứng minh remote write không xảy ra.
- **Cần sửa:** phân loại HTTP/body/transport ambiguity trước; giữ UNKNOWN nếu mất xác nhận sau write, lưu remote ID khi có, reconcile trước retry. Regression HTML 502, JSON malformed và verify-read lỗi sau upsert. Tác động G04/T20.

### R08 — P1 — Thiếu implementation phía Moodle của các hàm adapter yêu cầu

- **Vị trí:** [adapter function names](D:/NCKH/backend/modules/moodle/adapter.py:15), [runbook](D:/NCKH/docs/MOODLE_CONNECTOR_RUNBOOK.md).
- **Bằng chứng repository:** `git ls-files moodle .moodle-dev` không có file tracked; liệt kê file trong `moodle/` không có implementation. Adapter gọi `local_nckh_upsert_question`, `local_nckh_get_question`, `local_nckh_find_question`.
- **Cần sửa:** cung cấp plugin/adapter remote thực và quy trình cài/nâng cấp/capability/idempotency, hoặc khai báo rõ artifact bên ngoài có version và contract tests. Đây là phần implementation chưa có trong repo, không thể chỉ ghi “chờ credential của trường”. Tác động G03.

### R09 — P1 — Matching validator vẫn nhận đáp án mâu thuẫn hoặc có rác

- **Vị trí:** [MatchingData.validate_matching](D:/NCKH/backend/modules/questions/contracts.py:130).
- **Đã tái hiện:** `1-A,1-B,2-B,3-C` được nhận nguyên trạng; cùng vế 1 có hai đáp án. `1-A,2-B,3-C,garbage` được nhận và lặng lẽ bỏ phần rác.
- **Nguyên nhân:** `findall` chỉ trích substring, kiểm tập vế trái mà không kiểm mỗi vế đúng một lần hoặc toàn bộ chuỗi hợp grammar.
- **Cần sửa:** parse toàn input, kiểm cardinality/duplicate-left; chốt rule reuse vế phải theo contract. Thử qua CRUD, import và AI postprocessing. Tác động E01/G01.

### R10 — P1 — Model digest là hash cấu hình; local policy chưa có gate model đã cài

- **Vị trí:** [_finalize_snapshot](D:/NCKH/backend/modules/generation/llm/model_registry.py:20), [enforce_inference_policy](D:/NCKH/backend/modules/generation/llm/model_registry.py:68), [embedding_model_manifest](D:/NCKH/backend/modules/rag/mongodb.py:23).
- **Đã tái hiện:** snapshot Ollama localhost với tag `never-installed-audit-model:latest` vẫn qua policy. Đây là kiểm hàm policy, không phải khẳng định inference với model đó thành công.
- **Bằng chứng code:** digest được tính từ tên/parameters/role/config, không truy vấn digest weights/quantization thực; embedding tương tự.
- **Cần sửa:** tách config hash và artifact digest, ghi runtime/model revision/quantization thực và xác minh release đã cài/được phép. Cùng mutable tag có weights khác không được mang cùng provenance. Tác động A02/B05/D03/D05/E05/H03.

### R11 — P1 — Context budget có thể bị vượt; lexical branch còn giới hạn phần đầu

- **Vị trí:** [selection budget](D:/NCKH/backend/modules/rag/search.py:363), [lexical prefix](D:/NCKH/backend/modules/rag/search.py:137).
- **Đã tái hiện budget:** budget 128, một candidate token_count 200 → chọn candidate, trace báo `context_tokens=200`. Guard chỉ chạy khi đã có `selected_chunks`.
- **Bằng chứng code lexical:** sort `chunk_no`, limit trước khi rank theo query. Evidence ngoài prefix không có cơ hội cạnh tranh trong nhánh lexical.
- **Cần sửa:** xử lý chunk oversize bằng parent/window strategy hoặc lỗi rõ có trace; chốt token budget toàn prompt/output. Thay prefix cap bằng retrieval phù hợp hoặc đo và công bố coverage giới hạn. Tác động D01/D02/G4.

### R12 — P1 — Backend deployment chưa chuẩn bị Chromium cho xuất PDF

- **Vị trí:** [render_exam_pdf](D:/NCKH/backend/modules/exams/pdf_service.py:91), [Dockerfile](D:/NCKH/backend/Dockerfile).
- **Bằng chứng:** renderer gọi `playwright.chromium.launch()`; Dockerfile cài Python package nhưng không cài browser/runtime dependencies bằng bước tương ứng. Kiểm tra executable path trong image backend đang có trả `False`.
- **Cần sửa:** cài browser và dependencies trong backend image, chạy smoke tạo PDF bằng chính image vừa build. Chromium dùng cho frontend E2E ở job/máy khác không cung cấp runtime cho backend. Tác động F04/H02.

## 5. Trạng thái acceptance gates sau rà soát

| Gate | Kết luận hiện tại | Bằng chứng còn thiếu hoặc blocker |
|---|---|---|
| G1 — Quyền/workflow | **Chưa đạt đầy đủ** | R01; regression quyền liên quan sync R06 |
| G2 — Provenance | **Chưa đạt** | R02; crash/source history cần bảo toàn end-to-end |
| G3 — Local inference | **Một phần** | Có runtime/endpoint enforcement; thiếu model gate/digest thật và inference trong môi trường chặn cloud |
| G4 — Retrieval | **Chưa nghiệm thu** | R10/R11; benchmark evidence recall@5 trên tập query độc lập |
| G5 — Generation | **Chưa nghiệm thu** | R09; chưa đo tỷ lệ schema hợp lệ/đáp án code trên corpus sau repair |
| G6 — Evaluation | **Chưa nghiệm thu** | Thiếu false GREEN trên holdout, denominator/CI và chuyên gia xác nhận |
| G7 — Human review | **Chưa đạt đầy đủ** | R01; thiếu independent reviewer calibration/UAT |
| G8 — Exams | **Chưa đạt** | R03/R12; thiếu QA thị giác và answer mapping đến file của đủ mã đề |
| G9 — Moodle | **Chưa đạt** | R05–R08; plugin, identity/remote round-trip/grade thật |
| G10 — Recovery | **Chưa nghiệm thu** | R02/R04/R07; chưa crash/load/restore cả Mongo+artifacts+vector trên môi trường tương đương production |

## 6. Cập nhật so với các nhận xét cũ trong master plan

Không sao chép nguyên trạng những phát hiện từ baseline `790bc91`: code đã thay đổi đáng kể.

- Export chính thức hàng loạt đã chuyển qua backend, scope membership và self-review guard đã có.
- PDF đã extraction-first; raw/layout metadata và processing revision đã có, nhưng persistence chưa bất biến hoàn toàn theo R02.
- Retrieval đã có hai nhánh độc lập, hard heading và trace; còn R11 và thiếu benchmark thực.
- Prompt builder và repair instructions đã chuyển sang tiếng Việt; nhận xét “vẫn chủ yếu English” ở mục 19 không còn mô tả đúng các đoạn này.
- Typed validator đã chặn các ví dụ MCQ answer Z, multi-answer chỉ A,A và matching thiếu mapping/target invalid theo contract mới; vẫn còn trường hợp mới R09.
- Evaluator đã có verified spans, token-budgeted source selection, NO_DATA/hard checks; không còn chỉ lấy ba đoạn đầu như baseline.
- Blueprint đã giữ Bloom 5–6. Sai thứ tự đáp án ở R03 là lỗi đầu ra riêng, không phải mất Bloom.
- Moodle đã có backend remote adapter/outbox/identity endpoints, nhưng phần remote implementation và tính đúng của outbox/sync còn thiếu.

Các góp ý còn cần nghiệm thu riêng: highlight keyword đúng evidence, ngữ nghĩa lưu đồ/cây/đồ thị, biên ngày/timezone, tên người gửi/môn với dữ liệu legacy, độ rõ câu Đúng/Sai, thống kê dễ hiểu và rubric độ khó do giảng viên chốt. Không có bằng chứng mới để đánh dấu những mục UX/chất lượng này hoàn tất.

## 7. Thứ tự xử lý và điều kiện kiểm lại

1. **Đóng lỗi P0 trước:** R01 review server, R02 immutable/fencing, R03 đáp án, R04 Compose, R05 publish stale version. Mỗi lỗi có regression tái hiện thất bại trước sửa, đạt sau sửa.
2. **Hoàn thiện contract và recovery:** R06/R07 sync/outbox, R09 matching, R10 model release, R11 retrieval budget/coverage, R12 PDF image. Kiểm xuyên frontend→API→worker→persistence trên các đường liên quan.
3. **Bổ sung implementation Moodle:** R08; kiểm capability, input validation, version/hash mapping, idempotency và test đủ qtypes tại site thử nghiệm.
4. **Chạy đúng môi trường baseline:** fresh install Python 3.10.14/Node 20.19.0 hoặc cập nhật baseline có chủ đích; chạy CI mới với Mongo profile bắt buộc và workflow E2E thực.
5. **Nghiệm thu C–H bằng artifacts thực:** corpus CTDL/license/CLO/split freeze; benchmark retrieval/generation/evaluation; code-answer validation; independent human review; PDF/DOCX QA; Moodle round-trip; crash/load/backup restore và UAT/video.

**Bằng chứng cần bàn giao khi đóng gate:** commit/runtime/model artifact digests, command/log, input/checksum, expected/actual, denominator và slices cho số đo, file xuất/ảnh QA, remote IDs + verify-read nếu có, người thực hiện và xác nhận chuyên môn. Không dùng harness, checklist hoặc test mock làm bằng chứng đã chạy nghiệm thu thật.

**Trạng thái cuối của lần rà soát này:** đủ 8 giai đoạn đã được đối chiếu; chưa có cơ sở đóng toàn bộ dự án. Khuyến nghị dùng tài liệu này làm danh sách sửa và kiểm lại, đồng thời cập nhật trạng thái master plan ở lần triển khai tiếp theo.

## 8. Kết quả triển khai sau rà soát — 06/09/2026

Đợt triển khai tiếp theo đã xử lý các blocker code/config R01–R12 và thêm regression tương ứng:

- R01: backend chỉ cho APPROVED khi có đúng, đủ và duy nhất năm tiêu chí; còn `FAIL` thì từ chối.
- R02: page set chỉ được ghi bởi OCR job/revision chưa hoàn tất; worker phải khớp lease/fencing token và toàn bộ manifest/pages/document update nằm trong transaction.
- R03: đáp án `SAP_XEP` và `GHEP_COT` giữ sequence khi dùng chung context PDF/DOCX.
- R04: production Compose dùng reset/override semantics; cấu hình hợp nhất không còn publish MongoDB và frontend chỉ bind `127.0.0.1:8080`.
- R05: worker tái kiểm lifecycle, approved-current version, tài khoản/role và subject scope ngay trước remote side effect.
- R06: sync bắt buộc `page_number` liên tục, checkpoint nối chuỗi, một run hoạt động trên mỗi site; identity inactive không thể tạo membership ACTIVE và chỉ revoke snapshot khi trang cuối không lỗi.
- R07: HTTP 5xx, response 2xx không phải JSON và mất xác nhận được phân loại `UNKNOWN`/reconcile thay vì confirmed failure để retry mù.
- R08: thêm Moodle plugin versioned `moodle/local/nckh` release 1.0.0, ba web-service, capability tối thiểu và bảng mapping idempotency/provenance.
- R09: matching parser kiểm toàn chuỗi và từ chối duplicate-left/rác cuối.
- R10: tách `config_digest`, `artifact_digest`, quantization và release/model digest; production bắt buộc digest cho LLM và embedding model.
- R11: chunk đầu vượt budget không còn được nhận; lexical candidate limit chỉ áp dụng sau khi rank toàn chunk set của tài liệu.
- R12: backend image cài Chromium cùng system dependencies; smoke test đã tạo PDF hợp lệ trong image sạch.

Kết quả kiểm lại source sau sửa:

| Kiểm tra | Kết quả |
|---|---:|
| Backend suite | **238 passed, 9 skipped**, thêm 14 subtests passed |
| Mongo replica-set profile | **9 passed**, không skip |
| Backend Ruff | PASS |
| Frontend unit | **47 passed** |
| Frontend ESLint/build | PASS/PASS |
| Browser role-access | **3 passed** |
| Moodle plugin PHP syntax | PASS cho toàn bộ file PHP |
| Backend image/PDF smoke | Build PASS; PDF 37.574 bytes, header `%PDF` |
| Production Compose merged config | MongoDB `ports=[]`; frontend chỉ `127.0.0.1:8080` |

Các gate phụ thuộc hệ thống/dữ liệu thật vẫn chưa được tự động đóng: corpus CTDL và benchmark độc lập; kill/restart/load/backup-restore đầy đủ; QA thị giác PDF/DOCX nhiều dạng; Moodle install/import/grade/verify-read trên site thử nghiệm; nghiên cứu reviewer/UAT/video. Plugin Moodle mới đã qua kiểm tra cú pháp và contract repository, chưa thay thế round-trip trên Moodle mục tiêu.

## 9. Nghiệm thu bổ sung ngoài Moodle — 06/09/2026

Đã dựng môi trường cô lập dùng backend image đã sửa, MongoDB 7 replica set và artifact storage riêng. Kết quả chi tiết nằm trong [Non Moodle Acceptance Report](D:/NCKH/artifacts/acceptance/non-moodle-2026-09-06/NON_MOODLE_ACCEPTANCE_REPORT.md).

| Nhóm | Kết quả |
|---|---:|
| Readiness production-like | PASS; Mongo transaction/storage/LOCAL_ONLY đều sẵn sàng |
| Load `/health/ready` | PASS; 100×10 và 2.000×50 đều 0 lỗi; p95 lần lượt 34,17 ms và 217,33 ms |
| Kill/restart OCR worker thật | PASS; kill khi PROCESSING, retry/fencing lên 2, hoàn tất 300 trang không trùng |
| Backup/restore | PASS; hai DB khớp count+canonical hash, 11 artifact khớp SHA-256; RTO drill 4,422 s, RPO 0 s khi dừng ghi |
| Chroma rebuild sau restore | PASS; re-index sang collection mới và hybrid recall@5 giữ 1,0 trên 5 query fixture |
| Benchmark retrieval fixture | Một phần; lexical/hybrid recall@5 = 1,0 nhưng dense = 0,2; đây là PDF thuyết minh đề tài, không phải corpus CTDL được cấp phép |
| Xuất đề/đáp án | PASS cấu trúc 16 file, 4 mã đề, đủ 7 qtype; 24 trang render không clipping/overlap |
| Rich content PDF/DOCX | FAIL; code còn backtick, bảng pipe còn text thô, chưa có đường render ảnh/công thức chuyên biệt |
| Regression kỹ thuật ngoài Moodle | PASS; backend 37 tests + 7 subtests, frontend 47 tests, browser reviewer role 1 test |
| UAT giảng viên/reviewer bên ngoài | Chưa chạy; repository không thể tự tạo người nghiệm thu/chữ ký |

Kết luận tại thời điểm kết thúc mục 9: recovery/load/restore và layout cơ bản đã có bằng chứng thực thi, nhưng rich-content export và việc dọn diagnostic stale vẫn còn mở; hai phát hiện kỹ thuật này đã được xử lý và kiểm chứng tại mục 10. Corpus/quality/UAT vẫn chưa thể đóng vì `baseline_dataset_manifest.json` xác nhận còn thiếu licensed text/scan/mixed CTDL PDF, official CLO revision và expert-labelled queries/questions.

## 10. Đóng các hạng mục kỹ thuật còn lại ngoài Moodle — 06/09/2026

Đã xử lý và kiểm lại ba hạng mục kỹ thuật phát hiện ở lần nghiệm thu bổ sung:

- Export PDF/DOCX có parser an toàn dùng chung cho inline/fenced code, bảng Markdown, công thức và ảnh data-URI. PDF dùng MathML; DOCX dùng OMML; HTML thô bị escape và URL ảnh remote/file bị từ chối để tránh SSRF/đọc file cục bộ.
- OCR job phục hồi thành công sẽ xóa `error` cũ ở cả job và `documents.latest_error`. Drill follow-up trên 300 trang hoàn tất với `run_attempt=2`, `fencing_token=2`, trang liên tục/không trùng và `error=null`.
- Embedding mặc định chuyển sang `bkai-foundation-models/vietnamese-bi-encoder`, có revision và SHA-256 artifact được pin trong `.env.example`; loader thực sự truyền revision cho SentenceTransformer. Trên cùng fixture 5 query, dense recall@5 tăng từ 0,2 lên 0,6, hybrid/lexical giữ 1,0. Đây vẫn chỉ là bằng chứng kỹ thuật trên PDF thuyết minh, không thay thế corpus CTDL có nhãn chuyên gia.

Kết quả kiểm cuối:

| Kiểm tra | Kết quả |
|---|---:|
| Backend suite | **240 passed, 9 skipped**, thêm 14 subtests passed |
| Mongo replica-set profile | **9 passed** |
| Frontend unit / ESLint / build | **47 passed / PASS / PASS** |
| Browser role-access | **3 passed** |
| Export structure | **16/16 file PASS**, 4 mã đề × đề/đáp án × PDF/DOCX |
| Visual QA cuối | **24/24 trang đã inspect**, code/bảng/công thức/ảnh đều được exercise |
| Dense / lexical / hybrid recall@5 fixture | **0,6 / 1,0 / 1,0** |
| Worker stale recovery follow-up | **PASS**, 300 trang, `error=null` |

Bằng chứng: [Non Moodle Acceptance Report](D:/NCKH/artifacts/acceptance/non-moodle-2026-09-06/NON_MOODLE_ACCEPTANCE_REPORT.md), `logs/retrieval-vietnamese-benchmark.json`, `logs/worker-stale-recovery-followup.json`, `logs/visual-export-qa.json` và `exports/export-manifest.json`. PDF/DOCX cùng ảnh render QA được tái tạo bằng script nghiệm thu và chủ động loại khỏi source control; manifest/log giữ bằng chứng kiểm chứng máy đọc được.

Ngoài Moodle, các hạng mục còn mở đều cần đầu vào bên ngoài repository: corpus CTDL được cấp phép + CLO chính thức + nhãn chuyên gia để chạy benchmark chất lượng; UAT có giảng viên/reviewer được chỉ định và ký xác nhận; workload authenticated trên môi trường identity mục tiêu. Không đánh dấu các mục này PASS bằng fixture tổng hợp.
