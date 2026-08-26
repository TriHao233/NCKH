# Mô tả chi tiết các thay đổi triển khai

Ngày cập nhật: 26/08/2026  
Nhánh triển khai: `dev`  
Phạm vi loại trừ: không chỉnh sửa các module OCR và Chunking.

## 1. Mục tiêu triển khai

Đợt thay đổi này xử lý các nhóm vấn đề sau:

1. Đảm bảo transaction MongoDB hoạt động đúng trên replica set.
2. Sửa kiểm thử đang lỗi và mở rộng CI cho nhánh `dev`.
3. Ràng buộc quyền sở hữu đối với generation job.
4. Chuẩn hóa cấu hình LLM và cơ chế chạy background worker.
5. Tách các phần logic lớn, bổ sung lint và integration tests.

Các thay đổi chỉ tập trung vào hạ tầng, generation, evaluation, cấu hình LLM,
CI và frontend helper. Không có file nào trong `backend/modules/ocr` hoặc module
Chunking được chỉnh sửa.

## 2. MongoDB replica set và transaction

### 2.1. Vấn đề trước khi sửa

`mongo_transaction()` tự động chạy không có session khi MongoDB không hỗ trợ
transaction. Hành vi này phù hợp với máy phát triển chạy Mongo standalone,
nhưng có thể làm các thao tác nhiều collection mất tính nguyên tử nếu cấu hình
production bị sai.

Docker Compose trước đó cũng chạy `mongo:latest` dưới dạng standalone, trong khi
MongoDB chỉ hỗ trợ multi-document transaction trên replica set hoặc mongos.

### 2.2. Thay đổi đã thực hiện

- Khóa Docker image ở `mongo:7.0` thay vì sử dụng `mongo:latest`.
- Khởi động Mongo bằng replica set `rs0`.
- Thêm healthcheck để tự gọi `rs.initiate()` trong lần chạy đầu tiên.
- Backend chờ MongoDB healthy trước khi khởi động.
- Docker truyền URI có `replicaSet=rs0` cho backend.
- Production/staging mặc định yêu cầu MongoDB hỗ trợ transaction.
- Nếu môi trường bắt buộc transaction nhưng Mongo đang chạy standalone,
  application sẽ báo lỗi rõ ràng thay vì âm thầm ghi không nguyên tử.
- Development có thể chủ động đặt `REQUIRE_MONGO_TRANSACTIONS=false`.

Các biến môi trường liên quan:

```dotenv
MONGO_URI=mongodb://mongodb:27017/?replicaSet=rs0
REQUIRE_MONGO_TRANSACTIONS=true
```

Trong `backend/.env.example`, `REQUIRE_MONGO_TRANSACTIONS=false` được dùng cho
cấu hình development mẫu. Docker Compose ghi đè thành `true`.

Các file chính:

- `docker-compose.yml`
- `backend/core/database.py`
- `backend/core/config.py`
- `backend/.env.example`

## 3. Background worker sử dụng MongoDB queue

### 3.1. Vấn đề trước khi sửa

Generation và auto-evaluation được đưa vào `FastAPI BackgroundTasks`. Tác vụ
kiểu này gắn với tiến trình web hiện tại, nên không phù hợp cho công việc AI kéo
dài và có thể bị gián đoạn khi backend khởi động lại.

### 3.2. Kiến trúc mới

API chỉ thực hiện hai việc:

1. Kiểm tra request và quyền truy cập.
2. Ghi job với trạng thái queued vào MongoDB rồi trả HTTP 202.

Worker chạy trong application lifespan và polling MongoDB:

```text
API request
    |
    v
MongoDB queued job
    |
    v
Mongo job worker
    |
    +-- generation queue --> claim atomically --> LLM generation
    |
    +-- evaluation queue --> claim atomically --> AI evaluation
```

Generation và evaluation được lấy từ hai queue riêng và có thể xử lý đồng thời.
Khi không có công việc, worker chờ theo thời gian cấu hình thay vì busy-loop.

Các biến cấu hình:

```dotenv
JOB_WORKER_ENABLED=true
JOB_WORKER_POLL_SECONDS=1
JOB_RECOVERY_TIMEOUT_MINUTES=120
```

### 3.3. Chống xử lý trùng generation job

Generation worker claim job bằng `find_one_and_update()` với điều kiện:

```json
{
  "_id": "<job-id>",
  "status": "queued"
}
```

Chỉ worker đầu tiên chuyển thành công từ `queued` sang `processing` mới nhận
được dữ liệu job. Các worker khác không thể chạy lại cùng job.

Evaluation tiếp tục sử dụng cơ chế claim atomically đã có trong workflow
service.

### 3.4. Retry từ trang quản trị

Retry generation/evaluation chỉ tạo lại job ở trạng thái queued. Admin service
không còn gọi trực tiếp processing function thông qua `BackgroundTasks`; Mongo
worker sẽ tự lấy job mới.

Riêng document background task không thay đổi vì nằm ngoài phạm vi của lần triển
khai này.

Các file chính:

- `backend/core/job_worker.py`
- `backend/main.py`
- `backend/modules/generation/generate.py`
- `backend/modules/generation/mongodb.py`
- `backend/modules/questions/workflow_router.py`
- `backend/modules/admin/jobs_service.py`

## 4. Ràng buộc ownership của generation job

### 4.1. Vấn đề trước khi sửa

Status endpoint chỉ tìm generation job theo `_id`. Vì vậy một giáo viên đã đăng
nhập có thể truy vấn job của giáo viên khác nếu biết job ID.

### 4.2. Quy tắc truy cập mới

- Teacher chỉ được truy vấn job có `requested_by_user_id` bằng user ID hiện tại.
- Admin được truy vấn mọi generation job.
- User có permission `questions.manage_all` được truy vấn mọi generation job.
- Job không tồn tại hoặc không thuộc quyền truy cập đều trả HTTP 404.

Trả 404 thay vì 403 giúp tránh tiết lộ rằng một job ID của người dùng khác đang
tồn tại trong hệ thống.

MongoDB query dành cho teacher có dạng:

```json
{
  "_id": "<job-id>",
  "requested_by_user_id": "<current-user-id>"
}
```

Các file chính:

- `backend/modules/generation/generate.py`
- `backend/modules/generation/mongodb.py`
- `backend/tests/test_generation_api.py`

## 5. Chuẩn hóa cấu hình LLM

### 5.1. Ollama provider dùng chung

Qwen và DeepSeek trước đây có hai cách gọi Ollama khác nhau:

- Khác biến môi trường endpoint.
- Khác timeout.
- Qwen hard-code model name.
- Cơ chế log và xử lý lỗi không thống nhất.

Adapter `OllamaProvider` mới gom các phần dùng chung:

- Endpoint Ollama.
- Model name.
- Timeout.
- Temperature.
- `num_predict`.
- JSON response cleanup.
- Kiểm tra response rỗng.
- Chuẩn hóa exception và structured logging.

Qwen và DeepSeek hiện chỉ cung cấp tên model và các override cần thiết.

### 5.2. Cấu hình Ollama

```dotenv
OLLAMA_GENERATE_URL=http://localhost:11434/api/generate
OLLAMA_TIMEOUT_SECONDS=300
OLLAMA_NUM_PREDICT=900
OLLAMA_TEMPERATURE=0
QWEN_MODEL_NAME=qwen2.5:7b
DEEPSEEK_MODEL_NAME=deepseek-r1
```

`OLLAMA_BASE_URL` cũ vẫn được hỗ trợ như một alias để tránh làm hỏng cấu hình
đang sử dụng.

Trong Docker, endpoint mặc định là:

```text
http://host.docker.internal:11434/api/generate
```

`extra_hosts` được cấu hình để backend container có thể kết nối Ollama chạy trên
host.

### 5.3. Gemini

- Chuẩn hóa tên setting thành `gemini_api_key` và `gemini_model_name`.
- Hỗ trợ `GEMINI_MODEL_NAME`; `DEFAULT_MODEL` vẫn là alias biến môi trường cũ.
- Chuyển lời gọi Gemini SDK đồng bộ sang `asyncio.to_thread()` để không block
  event loop của FastAPI.
- Thay `print()` và traceback trực tiếp bằng logger.

Cấu hình:

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL_NAME=gemini-2.0-flash
```

Các file chính:

- `backend/modules/generation/llm/ollama.py`
- `backend/modules/generation/llm/qwen.py`
- `backend/modules/generation/llm/deepseek.py`
- `backend/modules/generation/llm/gemini.py`
- `backend/core/config.py`
- `backend/modules/catalog/service.py`
- `backend/modules/dictionary/dictionary.py`

## 6. Sửa test evaluation prompt

Test `test_evaluation_prompt_includes_difficulty_rule` khởi tạo
`QuestionWorkflowService(database=None)` để kiểm tra riêng prompt builder.
`_policy()` trước đây vẫn cố truy cập collection từ database và gây
`AttributeError`.

`_policy()` hiện trả fallback policy khi service không được cấp database. Khi
chạy thực tế với database, policy active vẫn được đọc từ MongoDB như trước.

File thay đổi:

- `backend/modules/questions/workflow_service.py`

## 7. Tách logic generation request ở frontend

Logic dựng payload trước đây nằm trực tiếp trong `GeneratePage.jsx`. Phần này đã
được chuyển sang `frontend/src/utils/generationRequest.js` và có unit test riêng.

Các cải tiến kèm theo:

- Không hard-code `collection_name: "chunks"`; backend sử dụng cấu hình mặc định.
- Không tự động gán yêu cầu của giáo viên vào `target_heading`.
- `instruction` chỉ giữ đúng vai trò hướng dẫn sinh câu hỏi.
- Chuẩn hóa client telemetry trong một helper có thể kiểm thử độc lập.

Các file chính:

- `frontend/src/utils/generationRequest.js`
- `frontend/src/utils/generationRequest.test.js`
- `frontend/src/pages/GeneratePage.jsx`

## 8. Lint

### 8.1. Backend

Ruff được thêm vào requirements và cấu hình trong `backend/pyproject.toml`.
Giai đoạn đầu áp dụng nhóm correctness rules an toàn:

```toml
select = ["E9", "F63", "F7", "F82"]
```

OCR và RAG được exclude khỏi phạm vi lint để tuân thủ yêu cầu không chỉnh sửa
OCR/Chunking trong đợt này.

Lệnh chạy:

```shell
cd backend
python -m ruff check core modules tests
```

### 8.2. Frontend

Đã bổ sung ESLint, browser/Node globals và React Hooks plugin.

Lệnh chạy:

```shell
cd frontend
npm run lint
```

Lint hiện không có error. Có 10 warning React Hooks trong các màn hình quản trị
đã tồn tại trước phạm vi thay đổi. Các warning được giữ lại để tiếp tục theo dõi,
không tự động thay đổi dependency array vì có thể ảnh hưởng hành vi tải dữ liệu
của UI.

## 9. Integration tests và infrastructure tests

### 9.1. Generation API ownership

`backend/tests/test_generation_api.py` kiểm tra:

1. Teacher truy vấn job của mình với owner filter.
2. Teacher truy vấn job không thuộc quyền nhận HTTP 404.
3. Admin truy vấn job không bị giới hạn theo owner.

### 9.2. Mongo transaction

`backend/tests/test_infrastructure.py` kiểm tra:

1. Transaction bắt buộc sẽ fail-fast khi Mongo là standalone.
2. Development có thể chủ động cho phép ghi không transaction.

### 9.3. Mongo worker

Infrastructure test xác nhận worker phát hiện và gọi processor cho cả generation
queue lẫn evaluation queue.

### 9.4. Frontend generation payload

Test helper xác nhận:

- Instruction được trim.
- Không gửi `collection_name` hard-code.
- Không dùng instruction làm `target_heading`.
- Client telemetry được tính đúng.

## 10. CI cho nhánh dev

Workflow `.github/workflows/p0-tests.yml` hiện chạy khi push lên:

- `main`
- `master`
- `dev`

Backend CI thực hiện:

1. Cài dependencies.
2. Chạy Ruff.
3. Chạy schema/workflow tests.
4. Chạy generation post-processing tests.
5. Chạy generation API integration tests.
6. Chạy infrastructure tests.

Frontend CI thực hiện:

1. `npm ci`.
2. `npm test`.
3. `npm run lint`.
4. `npm run build`.

Script frontend test được đổi từ wildcard phụ thuộc shell sang `node --test`, giúp
chạy ổn định trên Windows và Linux.

## 11. Kết quả xác minh

Kết quả tại thời điểm hoàn tất triển khai:

| Hạng mục | Kết quả |
| --- | --- |
| Backend test suite | 127 passed |
| Frontend test suite | 39 passed |
| Ruff backend | Passed |
| ESLint frontend | 0 errors, 10 warnings |
| Frontend production build | Passed |
| Docker Compose validation | Passed |
| `git diff --check` | Passed |
| Thay đổi trong OCR | Không có |
| Thay đổi trong Chunking | Không có |

Frontend production build còn cảnh báo một số bundle lớn hơn 500 kB. Đây là
hạng mục code-splitting/lazy loading riêng, không làm build thất bại.

`npm audit` hiện báo 7 dependency vulnerabilities, gồm 4 moderate và 3 high.
Không chạy `npm audit fix --force` trong đợt này vì thao tác đó có thể nâng major
version và gây breaking changes.

## 12. Danh sách file mới

- `backend/core/job_worker.py`
- `backend/modules/generation/llm/ollama.py`
- `backend/pyproject.toml`
- `backend/tests/test_generation_api.py`
- `backend/tests/test_infrastructure.py`
- `frontend/eslint.config.js`
- `frontend/src/utils/generationRequest.js`
- `frontend/src/utils/generationRequest.test.js`
- `IMPLEMENTATION_CHANGES.md`

## 13. Lưu ý vận hành

### Docker Compose

Khởi động hệ thống bằng:

```shell
docker compose up --build
```

Mongo healthcheck sẽ tự khởi tạo replica set trong lần chạy đầu. Backend chỉ được
khởi động sau khi Mongo báo healthy.

### Chạy backend ngoài Docker

Nếu dùng Mongo standalone cho development:

```dotenv
APP_ENV=development
REQUIRE_MONGO_TRANSACTIONS=false
```

Không sử dụng cấu hình này cho production.

Nếu chạy Mongo replica set cục bộ:

```dotenv
MONGO_URI=mongodb://localhost:27017/?replicaSet=rs0
REQUIRE_MONGO_TRANSACTIONS=true
```

### Tắt worker trong một web instance

Trong trường hợp triển khai nhiều loại process và chỉ muốn một nhóm instance xử
lý job:

```dotenv
JOB_WORKER_ENABLED=false
```

Ít nhất một backend instance phải có worker được bật để xử lý generation và
evaluation job.

## 14. Trạng thái Git

Các thay đổi đang nằm trong working tree của nhánh `dev`. Tại thời điểm tạo tài
liệu này, thay đổi chưa được commit hoặc push.
