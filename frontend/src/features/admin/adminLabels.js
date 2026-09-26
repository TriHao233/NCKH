// Nhãn hiển thị dùng chung cho các trang Quản trị (Tổng quan, Hàng đợi, Nhật ký).

export const AUDIT_ACTION_LABEL = Object.freeze({
  'auth.demo_login': 'Đăng nhập tài khoản demo',
  'user.admin_update': 'Cập nhật tài khoản',
  'user.deactivate': 'Khoá tài khoản',
  'user.invite': 'Mời tài khoản',
  'user.password_reset': 'Tạo link đặt lại mật khẩu',
  'question.submit_review': 'Gửi câu hỏi đi duyệt',
  'question.sharing_update': 'Đổi chia sẻ câu hỏi',
  'document.sharing_update': 'Đổi chia sẻ tài liệu',
  QUESTION_EVALUATED: 'AI chấm câu hỏi',
  QUESTION_APPROVED: 'Duyệt câu hỏi',
  QUESTION_NEEDS_REVISION: 'Yêu cầu sửa câu hỏi',
  QUESTION_REJECTED: 'Từ chối câu hỏi',
  QUESTION_SECONDARY_REVIEW_REQUESTED: 'Yêu cầu duyệt lần 2',
  QUESTION_SECONDARY_REVIEW_SET: 'Đặt yêu cầu duyệt lần 2',
  QUESTION_REVIEW_CLAIMED: 'Nhận câu kiểm duyệt',
  QUESTION_REVIEW_RELEASED: 'Trả câu kiểm duyệt',
  QUESTION_REVIEW_ASSIGNED: 'Giao câu cho người duyệt',
  QUESTION_REVIEW_UNASSIGNED: 'Bỏ giao câu kiểm duyệt',
  QUESTION_COMMENT_ADDED: 'Thêm trao đổi',
  QUESTION_COMMENT_UPDATED: 'Sửa trao đổi',
  QUESTION_COMMENT_DELETED: 'Xoá trao đổi',
  'admin.job_retry': 'Chạy lại tác vụ',
  'admin.job_cancel': 'Huỷ tác vụ',
  'admin.moodle_target_save': 'Lưu cấu hình Moodle',
  'admin.moodle_target_deactivate': 'Tắt cấu hình Moodle',
  'admin.moodle_target_check': 'Kiểm tra kết nối Moodle',
  'admin.moodle_publication_retry': 'Ghi lại câu hỏi lên Moodle',
});

export const AUDIT_ENTITY_LABEL = Object.freeze({
  user: 'Tài khoản',
  QUESTION: 'Câu hỏi',
  question: 'Câu hỏi',
  document: 'Tài liệu',
  generation: 'Tác vụ sinh câu hỏi',
  evaluation: 'Tác vụ đánh giá',
  moodle_target: 'Cấu hình Moodle',
  moodle_publication: 'Lượt ghi Moodle',
  subject: 'Học phần',
});

export const JOB_KIND_LABEL = Object.freeze({
  generation: 'Sinh câu hỏi',
  evaluation: 'AI đánh giá',
  document: 'Xử lý tài liệu',
});

export const JOB_TYPE_LABEL = Object.freeze({
  OCR: 'Nhận dạng văn bản (OCR)',
  EXTRACT_TEXT: 'Trích xuất văn bản',
  CHUNK_AND_EMBED: 'Cắt đoạn và nhúng',
  generation: 'Sinh câu hỏi',
  Generation: 'Sinh câu hỏi',
  evaluation: 'AI đánh giá câu hỏi',
  Evaluation: 'AI đánh giá câu hỏi',
});

export const JOB_STATUS_LABEL = Object.freeze({
  queued: 'Đang chờ',
  processing: 'Đang chạy',
  failed: 'Thất bại',
  completed: 'Hoàn tất',
  error: 'Lỗi',
  stale: 'Cần chạy lại',
  cancelled: 'Đã huỷ',
  BLOCKED: 'Thiếu bằng chứng',
});

export function jobStatusLabel(status) {
  const key = String(status || '');
  return JOB_STATUS_LABEL[key] || JOB_STATUS_LABEL[key.toLowerCase()] || key || 'Chưa rõ';
}

export function jobStatusTone(status) {
  const normalized = String(status || '').toLowerCase();
  if (['failed', 'error', 'cancelled'].includes(normalized)) return 'danger';
  if (['stale', 'blocked'].includes(normalized)) return 'warn';
  if (['queued', 'processing'].includes(normalized)) return 'info';
  if (normalized === 'completed') return 'success';
  return '';
}

export function auditActionLabel(action) {
  return AUDIT_ACTION_LABEL[action] || String(action || 'Không rõ').replace(/[._]/g, ' ').toLowerCase();
}

export function auditEntityLabel(type) {
  return AUDIT_ENTITY_LABEL[type] || type || 'Đối tượng';
}

export function compactId(value) {
  if (!value) return '--';
  const text = String(value);
  return text.length <= 12 ? text : `${text.slice(0, 6)}…${text.slice(-4)}`;
}

export function formatNumber(value) {
  return new Intl.NumberFormat('vi-VN').format(value || 0);
}

export function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return '';
  if (seconds < 60) return `${seconds} giây`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} phút`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ`;
  return `${Math.floor(seconds / 86400)} ngày`;
}
