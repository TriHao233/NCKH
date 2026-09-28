# Runbook cutover: MongoDB nghiệp vụ → PostgreSQL (kịch bản B)

Áp dụng cho nhánh `db-refactor` từ commit `28c6aec` trở đi. Runbook chuyển **toàn bộ dữ liệu nghiệp vụ** sang PostgreSQL trong một lần dừng ghi ngắn. MongoDB tiếp tục giữ chunk/vector; ChromaDB và file không đổi trong lần cutover này.

> Chạy toàn bộ runbook ít nhất một lần trên bản sao dữ liệu (mục 2) trước khi làm trên môi trường thật. Mọi ô `____` phải được điền từ lần diễn tập.

## 1. Nguyên tắc

- **Một nguồn ghi tại mọi thời điểm.** Trước cutover, MongoDB là nguồn ghi. Sau khi mở ghi lại, PostgreSQL là nguồn ghi. Không có dual-write.
- **Đổi tất cả cờ cùng lúc.** Không bật dần từng cờ trên môi trường thật: nhiều luồng đọc chéo giữa các nhóm (câu hỏi ↔ đề thi ↔ thông báo ↔ job), bật lệch sẽ đọc thiếu dữ liệu.
- **Chép vào database PostgreSQL mới, rỗng.** `db.copy_business_data --resume` chỉ upsert nên không xóa được bản ghi đã bị xóa ở Mongo (draft, đề thi, mã đề…); `db.verify_business_data` sẽ báo dư. Chép sạch trong lúc dừng ghi là cách duy nhất đã được kiểm chứng.
- **Không xóa gì ở MongoDB** trong runbook này. Dọn collection nghiệp vụ Mongo là việc riêng sau rollback window (mục 10).
- **Điểm không quay lại:** thời điểm mở ghi cho người dùng trên PostgreSQL (bước 7.4). Trước điểm này rollback chỉ là đổi cờ; sau điểm này không có công cụ chép ngược.

## 2. Diễn tập (bắt buộc)

1. Dựng môi trường tách biệt (máy khác hoặc compose project khác) từ bản backup Mongo mới nhất và cùng commit sẽ deploy.
2. Chạy nguyên mục 5 → 7 trên môi trường đó, bấm giờ từng bước vào bảng ở Phụ lục C.
3. Chạy smoke test đầy đủ (mục 8) với tài khoản thật của từng vai trò.
4. Diễn tập rollback (mục 9.1) một lần: đổi cờ về `mongo`, khởi động lại, xác nhận ứng dụng chạy như trước.
5. Diễn tập khôi phục: restore bản `pg_dump` vào database trống và chạy lại `db.verify_business_data`.

Ngưỡng chấp nhận (điền sau diễn tập):

| Chỉ số | Kết quả diễn tập | Ngưỡng cho môi trường thật |
|---|---|---|
| Thời gian chép (`copy_business_data --apply`) | ____ phút | ____ phút |
| Tổng thời gian dừng ghi (5.2 → 7.4) | ____ phút | ____ phút |
| `verify_business_data` | lỗi: ____ | 0 bảng lỗi |
| Smoke test | đạt ____/____ | 100% |

## 3. Điều kiện trước khi lên lịch

- [ ] Diễn tập (mục 2) đạt tất cả ngưỡng.
- [ ] Môi trường thật đang chạy **toàn bộ cờ `*_STORE=mongo`** (mặc định). Nếu có nhóm nào đã ghi vào PostgreSQL trên môi trường thật, **dừng lại**: dữ liệu nhóm đó chỉ có ở PostgreSQL và cách chép sạch trong runbook này sẽ làm mất nó; cần kế hoạch riêng cho nhóm đó.
- [ ] Commit deploy chứa migration mới nhất (hiện tới `0017`) và đã chạy xong test: `RUN_POSTGRES_INTEGRATION=1` cho `tests/test_postgres_*.py`, cùng `tests/test_schema_v2.py`.
- [ ] MongoDB chạy replica set (`REQUIRE_MONGO_TRANSACTIONS=true` như compose).
- [ ] Ổ đĩa đủ cho: backup Mongo, `pg_dump`, bản sao `backend/data`.
- [ ] Đã thông báo lịch dừng hệ thống cho Teacher/Reviewer/Admin, kèm thời lượng dự kiến lấy từ diễn tập.
- [ ] Có người phụ trách quyết định go/no-go và người thực hiện, cùng kênh liên lạc trong suốt cửa sổ.

## 4. Chuẩn bị trước ngày cutover (T-1)

1. Build image của commit sẽ deploy nhưng **chưa** khởi động lại dịch vụ:

   ```bash
   docker compose build backend worker
   ```

2. Chuẩn bị file cấu hình đích `backend/.env.postgres` = `backend/.env` hiện tại + các cờ ở Phụ lục A. Chưa thay `backend/.env`.
3. Ghi lại số lượng nguồn để so sánh (không ghi gì):

   ```bash
   docker compose run --rm backend python -m db.copy_business_data > cutover/source-counts-T-1.txt
   ```

## 5. Dừng ghi và sao lưu (T0)

1. **Rút cạn hàng đợi.** Thông báo người dùng ngừng thao tác. Chờ tới khi trang Admin → Jobs không còn job `queued/processing` (generation, evaluation, OCR/chunk/index), hoặc chấp nhận hủy chúng. Job còn chạy lúc dừng sẽ được chép ở trạng thái dở dang: generation bị hủy ngay khi worker mới khởi động; evaluation/OCR đang `PROCESSING` sẽ được worker nhận lại khi lease hết hạn, và chỉ bị đánh `STALE/FAILED` nếu đã quá `JOB_RECOVERY_TIMEOUT_MINUTES` (mặc định 120 phút). Rút cạn hàng đợi để tránh cả hai trường hợp.
2. **Dừng ghi** bằng cách dừng API và worker (ứng dụng không có chế độ bảo trì riêng):

   ```bash
   docker compose stop backend worker
   ```

   Ghi giờ dừng: ____

3. **Backup MongoDB** (toàn bộ, gồm cả collection vector):

   ```bash
   docker compose exec -T mongodb mongodump --archive --gzip > cutover/mongo-before-cutover.archive.gz
   ```

4. **Backup file** (upload, artifact, avatar, Chroma local):

   ```bash
   tar -czf cutover/backend-data-before-cutover.tgz backend/data
   ```

5. Kiểm tra hai file backup có kích thước hợp lý và đọc được (`gzip -t`).

## 6. Chép sang PostgreSQL mới và đối soát

Đặt tên database đích, ví dụ `nckh_cutover_20261010`. Các lệnh dưới dùng biến:

```bash
export CUTOVER_DB=nckh_cutover_20261010
export CUTOVER_DSN=postgresql://nckh:<mật-khẩu>@postgres:5432/$CUTOVER_DB
```

1. Tạo database trống:

   ```bash
   docker compose exec -T postgres psql -U nckh -d postgres -c "CREATE DATABASE $CUTOVER_DB"
   ```

2. Áp migration và kiểm tra không còn migration treo:

   ```bash
   docker compose run --rm -e POSTGRES_DSN=$CUTOVER_DSN backend python -m db.migrate --apply
   docker compose run --rm -e POSTGRES_DSN=$CUTOVER_DSN backend python -m db.migrate --check
   ```

3. Chép dữ liệu nghiệp vụ (từ chối chạy nếu database đích đã có dữ liệu, đúng như mong muốn):

   ```bash
   docker compose run --rm -e POSTGRES_DSN=$CUTOVER_DSN backend \
     python -m db.copy_business_data --apply | tee cutover/copy-output.txt
   ```

   Ghi thời gian: ____ phút.

4. Đối soát ID, số lượng, trường quan trọng và nội dung JSON đã theo dõi:

   ```bash
   docker compose run --rm -e POSTGRES_DSN=$CUTOVER_DSN backend \
     python -m db.verify_business_data | tee cutover/verify-output.txt
   ```

   **Phải kết thúc bằng** `Business IDs and critical fields match`. Bất kỳ dòng nào có `missing`, `extra`, `critical_mismatch` hoặc `content_mismatch` khác 0 → **no-go**, chuyển mục 9.1.

5. Kiểm tra bổ sung bằng SQL (Phụ lục B): không có câu hỏi thiếu version hiện hành, không có đề đã chốt thiếu snapshot, không có job đang chạy.
6. Backup database vừa chép (điểm khôi phục nếu phải làm lại):

   ```bash
   docker compose exec -T postgres pg_dump -U nckh -Fc $CUTOVER_DB > cutover/postgres-after-copy.dump
   ```

## 7. Đổi nguồn và khởi động

1. Trỏ ứng dụng sang database mới: đặt `POSTGRES_DB=$CUTOVER_DB` trong file `.env` cạnh `docker-compose.yml` (compose dùng biến này để dựng `POSTGRES_DSN` cho `backend` và `worker`).
2. Thay cấu hình ứng dụng:

   ```bash
   cp backend/.env backend/.env.mongo-before-cutover
   cp backend/.env.postgres backend/.env
   ```

3. Khởi động bằng image mới:

   ```bash
   docker compose up -d backend worker
   docker compose logs --since 5m backend worker
   ```

   Khi khởi động, backend và worker tự kiểm tra migration (`db.migrate --check`) và dừng nếu còn thiếu. Log không được có lỗi kết nối PostgreSQL, lỗi migration hay `RuntimeError ... requires ...STORE=postgres` (thiếu cờ phụ thuộc, xem Phụ lục A). `/health` chỉ báo tiến trình còn sống, **không** chứng minh PostgreSQL hoạt động; smoke test (mục 8) mới là bằng chứng.

4. **Chạy smoke test (mục 8) trong khi người dùng chưa được mở lại.** Nếu đạt → go: thông báo mở lại hệ thống, ghi giờ: ____. **Đây là điểm không quay lại.** Nếu không đạt → mục 9.1.

## 8. Smoke test

Dùng tài khoản thật của từng vai trò, trên trình duyệt, theo thứ tự. Đánh dấu và ghi chú lỗi.

**Đăng nhập và quyền**
- [ ] Admin, Teacher, Reviewer đăng nhập được; tài khoản bị khóa bị từ chối.
- [ ] Hồ sơ, avatar cũ hiển thị; đổi avatar được.

**Teacher**
- [ ] Danh sách tài liệu, môn/chương/CLO hiển thị đúng như trước cutover.
- [ ] Upload một PDF nhỏ → OCR hoàn tất → xem/sửa trang OCR → chunk/index hoàn tất.
- [ ] Sinh câu hỏi từ tài liệu vừa index; tiến độ job cập nhật; kết quả hiện ra.
- [ ] Lưu một câu hỏi, sửa (tạo version mới), gửi duyệt → evaluation job chạy xong.
- [ ] Xem nguồn câu hỏi và tải PDF nguồn của một câu hỏi cũ.
- [ ] Mở một đề thi cũ đã chốt: nội dung và mã đề giữ nguyên, xuất PDF/DOCX được.
- [ ] Tạo đề mới → thêm câu đã duyệt → chốt → tạo mã đề → xem trước.

**Reviewer**
- [ ] Hàng đợi hiện đúng số câu chờ duyệt; lọc và sắp xếp hoạt động.
- [ ] Claim → comment có mention → duyệt APPROVED. Teacher nhận được thông báo.
- [ ] Dashboard Reviewer hiển thị số liệu 30 ngày.

**Admin**
- [ ] Overview: số user, câu hỏi, tài liệu khớp với `cutover/source-counts-T-1.txt` (± thay đổi trong ngày).
- [ ] Trang Jobs, Audit, cấu hình AI (model/prompt/policy), Moodle target và publication hiển thị dữ liệu cũ.
- [ ] Publish Moodle mock một câu đã duyệt; retry được một publication lỗi (nếu có).
- [ ] Phân công tự động một câu chờ duyệt.

## 9. Rollback

### 9.1 Trước khi mở lại cho người dùng (an toàn)

MongoDB chưa bị ghi gì kể từ bước 5.2, nên rollback chỉ là trả cấu hình:

```bash
docker compose stop backend worker
cp backend/.env.mongo-before-cutover backend/.env
# bỏ POSTGRES_DB=$CUTOVER_DB khỏi .env cạnh docker-compose.yml
docker compose up -d backend worker
```

Kiểm tra nhanh đăng nhập và một trang danh sách, rồi mở lại hệ thống. Giữ lại database `$CUTOVER_DB` và toàn bộ file trong `cutover/` để phân tích.

### 9.2 Sau khi đã mở lại (không có đường tắt)

Sau bước 7.4, mọi thay đổi mới chỉ nằm ở PostgreSQL. Không có công cụ chép ngược sang MongoDB.

- **Mặc định: sửa tiến (forward-fix)** trên PostgreSQL. Lỗi dữ liệu cụ thể sửa bằng SQL có review, lưu script trong `cutover/`.
- **Chỉ khi lỗi nghiêm trọng không sửa tiến được:** quay lại MongoDB theo mục 9.1 và **chấp nhận mất** mọi thay đổi tạo sau giờ mở lại. Trước khi làm, xuất danh sách bản ghi mới từ PostgreSQL (`created_at`/`updated_at` sau giờ mở lại) để nhập lại thủ công. Quyết định này thuộc người phụ trách go/no-go.

## 10. Sau cutover

**Trong 24–72 giờ đầu**
- Theo dõi log `backend`/`worker`: lỗi 5xx, `VERSION_CONFLICT` bất thường, job `failed`/dead-letter trong Admin → Jobs.
- Giữ nguyên MongoDB, backup và database đích; không chạy lệnh dọn dẹp.
- Backup PostgreSQL hằng ngày (`pg_dump -Fc`), kiểm tra restore được ít nhất một lần.

**Các bước tiếp theo, mỗi bước là một thay đổi riêng có lịch riêng**
1. **Chuyển file sang object storage.** Làm được khi hệ thống đang chạy vì từng artifact được đổi riêng, có điều kiện:

   ```bash
   docker compose run --rm backend python -m db.migrate_artifact_storage --manifest data/storage-manifest.jsonl
   docker compose run --rm backend python -m db.migrate_artifact_storage --apply --verify-content --manifest data/storage-manifest.jsonl
   ```

   Chỉ đặt `STORAGE_PROVIDER=s3` sau khi lần `--apply` không còn lỗi. File local chưa bị xóa.
2. **Chroma server** (`CHROMA_MODE=http`) khi chạy nhiều instance: dựng server, rồi `python scripts/rebuild_chromadb.py --dry-run`, sau đó chạy thật.
3. **Dọn MongoDB (sau rollback window ____ ngày):** backup lần cuối, rồi xóa các collection nghiệp vụ. Chỉ giữ `chunk_sets`, `document_chunks`, `vector_collections`, `chunk_embeddings`, `pipeline_lineage_events`. Khi mọi cờ ở Phụ lục A là `postgres`, bootstrap không tạo lại collection hay index nghiệp vụ nào nữa (bảng `POSTGRES_OWNERS` trong `backend/core/bootstrap.py`), nên các collection đã xóa sẽ không xuất hiện lại.

## Phụ lục A. Cờ cấu hình đích

Đặt trong `backend/.env.postgres`:

```dotenv
USER_STORE=postgres
CATALOG_STORE=postgres
AI_CONFIG_STORE=postgres
DICTIONARY_STORE=postgres
NOTIFICATION_STORE=postgres
MOODLE_TARGET_STORE=postgres
LLM_SLOT_STORE=postgres
DOCUMENT_STORE=postgres
AUDIT_STORE=postgres
REVIEW_POLICY_STORE=postgres
QUESTION_STORE=postgres
GENERATION_STORE=postgres
EXAM_STORE=postgres
# Giữ nguyên trong lần cutover này (đổi ở mục 10):
STORAGE_PROVIDER=local
CHROMA_MODE=local
```

Phụ thuộc được kiểm tra khi repository được dùng tới; thiếu cờ nào thì ứng dụng báo lỗi ghi rõ cờ đó:

| Cờ | Cần thêm |
|---|---|
| `DOCUMENT_STORE` | `USER_STORE`, `CATALOG_STORE` |
| `QUESTION_STORE` | `USER_STORE`, `CATALOG_STORE` |
| `GENERATION_STORE` | `USER_STORE`, `DOCUMENT_STORE` |
| `EXAM_STORE` | `QUESTION_STORE`, `CATALOG_STORE` |
| `NOTIFICATION_STORE` | `USER_STORE` |
| `CATALOG_STORE`, `REVIEW_POLICY_STORE`, `MOODLE_TARGET_STORE` | `USER_STORE` |
| Moodle target thật cho publication | `MOODLE_TARGET_STORE` |
| Thông báo cùng transaction | `QUESTION_STORE` + `NOTIFICATION_STORE` |

## Phụ lục B. Truy vấn kiểm tra sau khi chép

Chạy với `psql -d $CUTOVER_DB`. Mỗi truy vấn phải trả về `0`.

```sql
-- Câu hỏi active thiếu version hiện hành
SELECT count(*) FROM questions q
LEFT JOIN question_versions v ON v.id = q.current_version_id
WHERE q.lifecycle_status = 'ACTIVE' AND v.id IS NULL;

-- Câu hỏi APPROVED nhưng version đã duyệt không còn tồn tại
SELECT count(*) FROM questions q
LEFT JOIN question_versions v ON v.id = q.approved_version_id
WHERE q.review_status = 'APPROVED' AND v.id IS NULL;

-- Đề đã chốt nhưng thiếu snapshot
SELECT count(*) FROM exams
WHERE upper(status) = 'FINALIZED' AND payload->'finalized_snapshot' IS NULL;

-- Job còn đang chạy (hàng đợi chưa được rút cạn ở bước 5.1)
SELECT (SELECT count(*) FROM generation_jobs WHERE status IN ('queued','processing'))
     + (SELECT count(*) FROM evaluation_jobs WHERE status IN ('QUEUED','PROCESSING'))
     + (SELECT count(*) FROM document_jobs WHERE status IN ('QUEUED','PROCESSING'));

-- Artifact tài liệu trỏ tới file không có đường dẫn
SELECT count(*) FROM document_artifacts WHERE storage_key = '';
```

## Phụ lục C. Nhật ký thời gian

| Bước | Bắt đầu | Kết thúc | Người làm | Ghi chú |
|---|---|---|---|---|
| 5.1 Rút cạn hàng đợi | | | | |
| 5.2 Dừng ghi | | | | |
| 5.3–5.5 Backup | | | | |
| 6.1–6.2 Tạo DB, migration | | | | |
| 6.3 Chép dữ liệu | | | | |
| 6.4–6.6 Đối soát, backup | | | | |
| 7.1–7.3 Đổi cờ, khởi động | | | | |
| 8 Smoke test | | | | |
| 7.4 Mở lại (go) / 9.1 Rollback | | | | |
