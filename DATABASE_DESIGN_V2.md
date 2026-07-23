# Database Design V2

## 1. Phạm vi

MongoDB là nguồn dữ liệu chính cho hồ sơ người dùng, tài liệu, lịch sử xử lý,
chunk, cấu hình embedding, lần sinh câu hỏi và workflow duyệt câu hỏi.
ChromaDB chỉ lưu vector; Firebase chịu trách nhiệm định danh và mật khẩu.

Backend dùng đúng một database lấy từ `DB_NAME` và URI lấy từ `MONGO_URI`.
MongoDB phải chạy dưới dạng replica set để hỗ trợ transaction.

## 2. Quy tắc chung

- Mọi collection nghiệp vụ mới có `schema_version: 2`.
- ID nội bộ và liên kết MongoDB dùng `ObjectId`.
- Thời gian dùng UTC timezone-aware.
- Không xóa vật lý dữ liệu đã được tham chiếu; dùng trạng thái `ARCHIVED` hoặc
  `is_active: false`.
- Chỉ có hai role ứng dụng: `Admin` và `Teacher`.
- Không lưu mật khẩu hoặc Firebase ID token trong MongoDB.
- Nội dung câu hỏi và kết quả OCR/chunk được version hóa, không ghi đè lịch sử.

## 3. Collections

| Collection | Trách nhiệm |
|---|---|
| `users` | Hồ sơ ứng dụng liên kết Firebase UID |
| `subjects` | Học phần, chương và CLO |
| `documents` | Aggregate tài liệu và con trỏ tới phiên xử lý hiện tại |
| `document_jobs` | Lịch sử OCR, chunk và index |
| `document_pages` | Trang OCR bất biến theo OCR job |
| `chunk_sets` | Một lần chunk tài liệu với snapshot cấu hình |
| `document_chunks` | Nội dung chunk authoritative |
| `vector_collections` | Snapshot collection và embedding model |
| `chunk_embeddings` | Trạng thái vector của từng chunk theo collection |
| `keywords` | Từ khóa theo học phần |
| `ai_models` | Registry model AI |
| `prompt_templates` | Prompt version bất biến |
| `evaluation_policies` | Trọng số và ngưỡng đánh giá |
| `generation_runs` | Snapshot request, model, prompt và retrieval |
| `questions` | Aggregate và trạng thái workflow của câu hỏi |
| `question_versions` | Nội dung bất biến của từng phiên bản |
| `question_evaluations` | Lịch sử AI đánh giá từng phiên bản |
| `question_reviews` | Lịch sử con người duyệt từng phiên bản |
| `audit_logs` | Nhật ký hành động quan trọng |
| `moodle_publications` | Lịch sử xuất bản sang Moodle |
| `schema_meta` | Phiên bản schema hiện tại |

## 4. Users và Firebase

```javascript
{
  _id: ObjectId(),
  schema_version: 2,
  firebase_uid: "firebase-uid",
  email: "teacher@ctu.edu.vn",
  display_name: "Nguyễn Văn A",
  role: "Teacher", // Admin | Teacher
  profile: {
    school: "Đại học Cần Thơ",
    address: "",
    avatar: ""
  },
  is_active: true,
  created_at: ISODate(),
  updated_at: ISODate()
}
```

`firebase_uid` và `email` là duy nhất. Tài khoản đăng ký công khai luôn là
`Teacher`. Chỉ Admin được thay đổi role hoặc khóa tài khoản.

## 5. Documents và processing version

```javascript
{
  _id: ObjectId(),
  schema_version: 2,
  subject_id: ObjectId(),
  chapter_id: ObjectId(),
  uploaded_by_user_id: ObjectId(),
  title: "Giáo trình Cấu trúc dữ liệu",
  original_filename: "ctdl.pdf",
  status: "READY",
  current_version: 1,
  page_count: 120,
  artifacts: [{
    _id: ObjectId(),
    type: "ORIGINAL_PDF",
    document_version: 1,
    storage: { provider: "LOCAL", uri: "...", gridfs_file_id: null },
    mime_type: "application/pdf",
    size_bytes: 123456,
    sha256: "...",
    is_current: true,
    created_at: ISODate()
  }],
  current_processing: {
    ocr_job_id: ObjectId(),
    chunk_set_id: ObjectId(),
    vector_collection_id: ObjectId()
  },
  pipeline_summary: {
    ocr_status: "COMPLETED",
    chunk_status: "COMPLETED",
    index_status: "COMPLETED",
    total_chunks: 300
  },
  latest_error: null,
  created_at: ISODate(),
  updated_at: ISODate(),
  archived_at: null
}
```

Mỗi lần OCR/chunk/index tạo một `document_jobs` mới. `document_pages` có unique
index `(ocr_job_id, page_number)`. OCR lại không xóa page cũ.

## 6. Chunk và nhiều embedding

`chunk_sets` lưu `source_ocr_job_id`, `chunk_job_id`, strategy, config và
`config_hash`. `document_chunks` có unique index `(chunk_set_id, chunk_no)`.

Mỗi vector được theo dõi bởi:

```javascript
{
  chunk_id: ObjectId(),
  chunk_set_id: ObjectId(),
  vector_collection_id: ObjectId(),
  external_vector_id: "...",
  chunk_content_hash: "...",
  embedding_content_hash: "...",
  status: "INDEXED", // PENDING | INDEXED | FAILED | STALE
  indexed_at: ISODate(),
  error: null
}
```

Một chunk có thể có nhiều embedding trong nhiều `vector_collections`. MongoDB
lưu nội dung authoritative; ChromaDB có thể được rebuild từ MongoDB.

## 7. Generation run

Mỗi lần gọi LLM tạo một `generation_runs` chứa:

- `document_id`, `document_version`, `chunk_set_id`;
- snapshot request và model;
- rendered prompt cùng hash;
- retrieval results hoặc context hash/excerpt;
- raw model response, parser version, latency và lỗi.

Nhờ đó có thể chứng minh câu hỏi được sinh từ phiên bản tài liệu, prompt và model
nào.

## 8. Questions và question versions

`questions` chỉ giữ trạng thái aggregate:

```javascript
{
  _id: ObjectId(),
  schema_version: 2,
  question_code: "Q-...",
  current_version: 2,
  current_version_id: ObjectId(),
  approved_version_id: ObjectId(),
  lifecycle_status: "ACTIVE",
  evaluation_status: "PASSED",
  review_status: "APPROVED",
  publication_status: "NOT_PUBLISHED",
  quality_summary: {},
  latest_review_id: ObjectId(),
  created_at: ISODate(),
  updated_at: ISODate(),
  archived_at: null
}
```

Nội dung nằm trong `question_versions`:

```javascript
{
  _id: ObjectId(),
  schema_version: 2,
  question_id: ObjectId(),
  version: 2,
  origin: "MANUAL", // AI | MANUAL | IMPORT
  generation_run_id: ObjectId(),
  document_id: ObjectId(),
  created_by_user_id: ObjectId(),
  classification: {
    subject: { id: ObjectId() },
    chapter: { id: ObjectId() },
    assessment_type: "TRAC_NGHIEM",
    bloom: { level: 2, code: "UNDERSTAND", name: "Hiểu" }
  },
  clos: [],
  content: "...",
  question_data: {},
  sources: [{
    source_type: "CHUNK",
    chunk_id: ObjectId(),
    chunk_set_id: ObjectId(),
    chunk_content_hash: "...",
    citation_order: 1,
    is_primary: true,
    scores: {},
    context_excerpt: "..."
  }],
  keywords: [],
  content_hash: "...",
  change_note: "Question edited",
  created_at: ISODate()
}
```

Mỗi lần sửa tạo version mới bằng optimistic locking (`expected_version`) và
transaction. Evaluation/review luôn trỏ chính xác đến `question_version_id`.

## 9. Workflow

Các trạng thái độc lập:

- lifecycle: `ACTIVE | ARCHIVED`;
- evaluation: `NOT_STARTED | PASSED | FAILED`;
- review: `PENDING | APPROVED | REJECTED | NEEDS_REVISION`;
- publication: `NOT_PUBLISHED | PUBLISHED | FAILED | STALE`.

Chỉ approved version được xuất Moodle. Khi nội dung thay đổi sau xuất bản,
`publication_status` chuyển thành `STALE`.

## 10. Transaction và eventual consistency

Transaction bắt buộc cho:

1. insert `question_versions` và đổi con trỏ trong `questions`;
2. insert evaluation và cập nhật quality summary;
3. insert review, cập nhật trạng thái và audit log;
4. hoàn tất chunk set và cập nhật document aggregate.

MongoDB và ChromaDB không có transaction chung. Quy trình index:

1. ghi chunk authoritative vào MongoDB;
2. tạo `chunk_embeddings` ở trạng thái `PENDING`;
3. upsert Chroma bằng `external_vector_id` idempotent;
4. chuyển embedding thành `INDEXED`, hoặc `FAILED` để worker retry.
