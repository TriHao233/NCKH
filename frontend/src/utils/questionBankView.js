// Nhãn và cách tóm tắt một câu hỏi cho trang Ngân hàng câu hỏi của quản trị viên.

export const REVIEW_STATUS = {
  DRAFT: { label: 'Nháp', tone: 'muted' },
  PENDING: { label: 'Chờ duyệt', tone: 'active' },
  NEEDS_REVISION: { label: 'Cần sửa', tone: 'warning' },
  APPROVED: { label: 'Đã duyệt', tone: 'success' },
  REJECTED: { label: 'Từ chối', tone: 'danger' },
};
export const REVIEW_STATUS_ORDER = ['DRAFT', 'PENDING', 'NEEDS_REVISION', 'APPROVED', 'REJECTED'];

const EVALUATION_STATUS_LABEL = {
  NOT_STARTED: 'Chưa chấm',
  QUEUED: 'Đang chờ chấm',
  PROCESSING: 'Đang chấm',
  RUNNING: 'Đang chấm',
  PASSED: 'Đạt',
  FAILED: 'Không đạt',
  ERROR: 'AI lỗi',
  STALE: 'Cần chấm lại',
  INSUFFICIENT_EVIDENCE: 'Thiếu nguồn để chấm',
  EVIDENCE_VALIDATION_FAILED: 'Minh chứng không hợp lệ',
};

export const QUALITY_COLORS = [
  { value: 'GREEN', label: 'Đạt tốt', tone: 'success' },
  { value: 'YELLOW', label: 'Cần xem lại', tone: 'warning' },
  { value: 'RED', label: 'Rủi ro cao', tone: 'danger' },
];
const QUALITY_BY_VALUE = Object.fromEntries(QUALITY_COLORS.map((item) => [item.value, item]));

export const PUBLICATION_STATUS = {
  NOT_PUBLISHED: { label: 'Chưa đưa lên', tone: 'muted' },
  PUBLISHED: { label: 'Đã đưa lên', tone: 'success' },
  STALE: { label: 'Cần đưa lại', tone: 'warning' },
  FAILED: { label: 'Đưa lên lỗi', tone: 'danger' },
};

const ORIGIN_LABEL = { MANUAL: 'Soạn tay', AI: 'AI sinh', GENERATED: 'AI sinh', AI_GENERATED: 'AI sinh', IMPORTED: 'Nhập từ file' };

export function reviewStatusOf(question) {
  return REVIEW_STATUS[question?.review_status] || { label: question?.review_status || '--', tone: 'muted' };
}

export function publicationStatusOf(question) {
  return PUBLICATION_STATUS[question?.publication_status] || { label: question?.publication_status || '--', tone: 'muted' };
}

// Có điểm thì hiện điểm kèm mức chất lượng, chưa có thì hiện tình trạng chấm.
export function aiSummaryOf(question) {
  const quality = question?.quality_summary || {};
  const score = quality.overall_score;
  if (typeof score === 'number' && !quality.error) {
    const color = QUALITY_BY_VALUE[quality.color];
    return { text: `${score.toFixed(2)} · ${color?.label || 'Chưa phân mức'}`, tone: color?.tone || 'muted' };
  }
  const status = question?.evaluation_status;
  const tone = ['FAILED', 'ERROR', 'EVIDENCE_VALIDATION_FAILED'].includes(status)
    ? 'danger'
    : ['QUEUED', 'PROCESSING', 'RUNNING'].includes(status) ? 'active'
      : ['STALE', 'INSUFFICIENT_EVIDENCE'].includes(status) ? 'warning' : 'muted';
  return { text: EVALUATION_STATUS_LABEL[status] || status || '--', tone };
}

export function originLabel(origin) {
  return ORIGIN_LABEL[origin] || origin || '--';
}

export function questionTypeOf(question) {
  return String(question?.classification?.assessment_type || '').toLowerCase();
}

function userLabel(user) {
  return user?.display_name || user?.email || '';
}

// Người soạn là tác giả đầu tiên của câu hỏi; không tra được tên thì rơi về người gửi duyệt.
export function authorOf(question, userById = new Map()) {
  const ids = question?.author_user_ids || [];
  for (const id of ids) {
    const label = userLabel(userById.get(id));
    if (label) return { id, name: label, email: userById.get(id)?.email || '' };
  }
  const submitter = question?.review_submission?.submitted_by;
  if (submitter && (!ids.length || ids.includes(submitter.id)) && userLabel(submitter)) {
    return { id: submitter.id, name: userLabel(submitter), email: submitter.email || '' };
  }
  return { id: ids[0] || '', name: ids.length ? 'Tài khoản không còn trong hệ thống' : 'Chưa rõ', email: '' };
}

// Bản lưu học phần trong câu hỏi cũ có thể trống tên, khi đó tra theo danh mục học phần.
export function subjectOf(question, subjectById = new Map()) {
  const snapshots = [question?.classification?.subject, question?.subject, question?.review_submission?.subject];
  const named = snapshots.find((item) => item?.name || item?.code);
  if (named) return { code: named.code || '', name: named.name || named.code };
  const id = question?.subject_id || snapshots.find((item) => item?.id)?.id;
  const subject = subjectById.get(id);
  return subject ? { code: subject.subject_code || '', name: subject.subject_name || subject.subject_code } : { code: '', name: '' };
}

export function statusTotal(counts = {}) {
  return Object.values(counts).reduce((sum, value) => sum + (Number(value) || 0), 0);
}
