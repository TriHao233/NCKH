# Moodle Question Bank connector runbook

## Boundary

Connector này publish **Question Bank**, không tự tạo Moodle Quiz và không phải SSO. `MOCK` chỉ là
simulation cục bộ. Chỉ record `PUBLISHED`, `external_sync=true`, `status_detail=REMOTE_VERIFIED`
mới là publication Moodle thật.

## Moodle-side adapter contract

Service account cần web service REST và đúng course/category scope. Plugin/adapter phải cung cấp:

- `local_nckh_upsert_question`: nhận `courseid`, `categoryid`, `idempotencykey`, `payloadjson`;
  upsert theo idempotency key và trả `questionid`.
- `local_nckh_get_question`: nhận `questionid`, trả `questionid`, `versionid`, `contenthash` để verify.
- `local_nckh_find_question`: nhận `idempotencykey`, trả remote identity để reconcile sau timeout.
- `qtype_ordering` nếu target nhận dạng `sap_xep`; sáu dạng còn lại dùng qtype lõi Moodle.

Không cấp capability tạo Quiz, sửa course hoặc quản trị user nếu không nằm trong phạm vi nghiệm thu.

## Application setup

1. Tạo target `REST_API` tại `/quan-ly-moodle`; nhập Moodle version/build, URL, course mặc định,
   category, course allowlist và capability thực tế.
2. Chỉ lưu tên biến môi trường token, ví dụ `MOODLE_CTU_TOKEN`; inject secret khi deploy.
3. Chạy **Kiểm tra kết nối**. Không publish nếu target inactive, token thiếu, role/course ngoài allowlist
   hoặc qtype capability không đủ.
4. Gửi publication từ version đã duyệt. Request tạo outbox `QUEUED`; worker chuyển `PUBLISHING`.
5. Thành công cần remote ID và verify version/content hash. Timeout hoặc mất response thành `UNKNOWN`;
   dùng **Đối soát**, không retry mù. `FAILED` xác nhận an toàn mới được retry bằng cùng idempotency key.

## Identity and membership sync

Gửi từng trang tới `POST /api/v1/admin/moodle/identity-sync` với `site_key`, `sync_id`, `checkpoint`,
`next_checkpoint`. Identity key luôn là `(site_key, external_user_id)`; email chỉ là metadata.
Link mới tới internal user phải dùng link token một lần đã băm SHA-256, còn hạn và đúng cả ba identity.
Membership Moodle được upsert idempotent theo site/course/user/subject. Trang cuối (`is_last_page=true`)
revoke membership Moodle không xuất hiện trong cùng `sync_id`; không xóa lịch sử tác giả/reviewer.

## Upgrade and incident checks

- Trước nâng Moodle/plugin: export fixture đủ bảy dạng, import vào test category, chấm thử và verify-read.
- Sau nâng: kiểm tra capability matrix, idempotent upsert hai lần, timeout/reconcile và revocation sync.
- Token nghi lộ: rotate secret tại platform, không sửa record DB; khóa target trong lúc điều tra.
- `UNKNOWN`: reconcile trước. Chỉ chuyển retry khi remote lookup xác nhận không có question.
