// Nghiệp vụ kiểm duyệt dùng chung cho Người duyệt và Quản trị viên.
// Tách khỏi JSX để kiểm thử được bằng `node --test`.
//
// Vòng đời câu hỏi:
//   DRAFT (giảng viên) -> submit -> PENDING + AI tự đánh giá
//   PENDING: người duyệt Nhận câu (khóa xử lý có hạn) -> chấm 5 tiêu chí -> quyết định
//     APPROVED  (có thể yêu cầu duyệt lần 2; người duyệt lần 2 phải khác người lần 1)
//     NEEDS_REVISION (bắt buộc có danh sách lỗi) -> giảng viên sửa, gửi lại
//     REJECTED (bắt buộc có lý do)
//   APPROVED -> xuất GIFT/XML hoặc ghi Moodle.

export const REVIEW_STATUS_LABEL = Object.freeze({
  DRAFT: 'Nháp',
  PENDING: 'Chờ duyệt',
  PROCESSED: 'Đã xử lý',
  APPROVED: 'Đã duyệt',
  NEEDS_REVISION: 'Cần sửa',
  REJECTED: 'Từ chối',
});

export const REVIEW_STATUS_TONE = Object.freeze({
  DRAFT: '',
  PENDING: 'info',
  APPROVED: 'success',
  NEEDS_REVISION: 'warn',
  REJECTED: 'danger',
});

export const DECISIONS = Object.freeze([
  { value: 'APPROVED', label: 'Duyệt', tone: 'success' },
  { value: 'NEEDS_REVISION', label: 'Cần sửa', tone: 'warn' },
  { value: 'REJECTED', label: 'Từ chối', tone: 'danger' },
]);

export const EVALUATION_STATUS_LABEL = Object.freeze({
  NOT_STARTED: 'Chưa đánh giá',
  QUEUED: 'AI đang xếp hàng',
  PROCESSING: 'AI đang đánh giá',
  RUNNING: 'AI đang đánh giá',
  PASSED: 'AI đề xuất đạt',
  FAILED: 'AI đề xuất xem lại',
  ERROR: 'AI chưa đánh giá được',
  STALE: 'Cần đánh giá lại',
  INSUFFICIENT_EVIDENCE: 'Thiếu bằng chứng nguồn',
  EVIDENCE_VALIDATION_FAILED: 'Minh chứng AI không hợp lệ',
});

export const EVALUATION_RETRY_STATUSES = Object.freeze([
  'ERROR',
  'FAILED',
  'STALE',
  'INSUFFICIENT_EVIDENCE',
  'EVIDENCE_VALIDATION_FAILED',
]);

export const QUALITY_LABEL = Object.freeze({
  GREEN: 'Đạt tốt',
  YELLOW: 'Cần xem lại',
  RED: 'Rủi ro cao',
});

export const QUALITY_TONE = Object.freeze({
  GREEN: 'success',
  YELLOW: 'warn',
  RED: 'danger',
});

export const PUBLICATION_STATUS_LABEL = Object.freeze({
  NOT_PUBLISHED: 'Chưa đồng bộ Moodle',
  PENDING: 'Đang đồng bộ Moodle',
  PUBLISHED: 'Đã đồng bộ Moodle',
  FAILED: 'Đồng bộ lỗi',
});

export const DECISION_DONE_TEXT = Object.freeze({
  APPROVED: 'Đã duyệt',
  NEEDS_REVISION: 'Đã gửi yêu cầu sửa',
  REJECTED: 'Đã từ chối',
});

export const SECONDARY_STATUS_LABEL = Object.freeze({
  NOT_REQUIRED: 'Không yêu cầu',
  AWAITING_SECONDARY: 'Chờ duyệt lần 2',
  COMPLETED: 'Đã duyệt lần 2',
  CANCELLED: 'Đã huỷ duyệt lần 2',
});

export const ISSUE_SEVERITY = Object.freeze([
  { value: 'LOW', label: 'Nhẹ' },
  { value: 'MEDIUM', label: 'Vừa' },
  { value: 'HIGH', label: 'Nghiêm trọng' },
]);

export const CRITERION_RATINGS = Object.freeze([
  { value: 'PASS', label: 'Đạt' },
  { value: 'REVIEW', label: 'Xem lại' },
  { value: 'FAIL', label: 'Không đạt' },
  { value: 'NO_DATA', label: 'Thiếu dữ liệu' },
]);

export const REVIEW_CRITERIA = Object.freeze([
  {
    key: 'faithfulness',
    label: 'Bám sát nguồn',
    description: 'Câu hỏi, đáp án và giải thích có căn cứ trong tài liệu nguồn.',
  },
  {
    key: 'contextual_relevancy',
    label: 'Phù hợp ngữ cảnh',
    description: 'Tập trung vào nội dung quan trọng của học phần.',
  },
  {
    key: 'answer_relevancy',
    label: 'Đáp án đúng',
    description: 'Đáp án đúng, rõ ràng và phù hợp với dạng câu hỏi.',
  },
  {
    key: 'bloom_alignment',
    label: 'Đúng cấp Bloom',
    description: 'Thao tác tư duy khớp cấp Bloom đã gắn.',
  },
  {
    key: 'clo_alignment',
    label: 'Đúng CLO',
    description: 'Câu hỏi đo được chuẩn đầu ra đã chọn.',
  },
]);

export const QUESTION_TYPE_GUIDANCE = Object.freeze({
  dung_sai: [
    'Mệnh đề hoàn chỉnh, chỉ có thể hoàn toàn Đúng hoặc hoàn toàn Sai.',
    'Dữ kiện bị thay đổi phải truy ra được trong nguồn.',
    'Đáp án chuẩn hoá A = Đúng, B = Sai; giải thích nêu rõ vì sao.',
  ],
  trac_nghiem: ['Chỉ có một đáp án đúng nhất.', 'Phương án nhiễu cùng loại, hợp lý, không làm lộ đáp án.'],
  nhieu_lua_chon: ['Có ít nhất hai đáp án đúng độc lập.', 'Không có lựa chọn bao hàm làm số đáp án đúng bị mơ hồ.'],
  dien_khuyet: ['Có một đáp án xác định.', 'Không hỏi từ nối hoặc chi tiết vụn vặt.'],
  ghep_cot: ['Hai cột cùng loại, quan hệ ghép rõ ràng.', 'Không thể ghép chỉ bằng mẹo hình thức.'],
  sap_xep: ['Nguồn thực sự chứa quy trình hoặc chuỗi phụ thuộc.', 'Chỉ có một thứ tự hợp lý.'],
  tinh_huong: ['Tình huống đủ dữ kiện để ra quyết định.', 'Đáp án đòi hỏi suy luận, không chỉ nhớ định nghĩa.'],
});

const GENERIC_CHECKLIST = Object.freeze([
  { key: 'source_checked', label: 'Đã đối chiếu câu hỏi và đáp án với tài liệu nguồn' },
  { key: 'language_clear', label: 'Diễn đạt rõ ràng, không lỗi chính tả' },
]);

/** Danh sách kiểm tra theo dạng câu hỏi (tối đa 12 mục theo giới hạn của backend). */
export function checklistForType(typeKey) {
  const specific = (QUESTION_TYPE_GUIDANCE[typeKey] || []).map((label, index) => ({
    key: `${typeKey}_${index + 1}`,
    label,
  }));
  return [...specific, ...GENERIC_CHECKLIST].slice(0, 12);
}

/** Các tab của Hộp việc. `query` là tham số lọc gửi lên API danh sách câu hỏi. */
export const INBOX_TABS = Object.freeze([
  { value: 'mine', label: 'Của tôi', query: { reviewStatus: 'PENDING', assignedTo: 'me' } },
  // Câu chưa từng được giao không có trường review_assignment nên API lọc "UNASSIGNED" bỏ sót; lọc phía trình duyệt.
  { value: 'unassigned', label: 'Chưa ai nhận', query: { reviewStatus: 'PENDING' }, clientFilter: 'unassigned' },
  { value: 'resubmitted', label: 'Gửi lại sau sửa', query: { reviewStatus: 'PENDING' }, clientFilter: 'resubmitted' },
  { value: 'overdue', label: 'Quá hạn', query: { reviewStatus: 'PENDING', overdueOnly: true } },
  { value: 'processed', label: 'Đã xử lý', query: { reviewStatus: 'PROCESSED' } },
  { value: 'moodle', label: 'Chờ lên Moodle', query: { reviewStatus: 'APPROVED', publicationStatus: 'NOT_PUBLISHED' } },
  { value: 'all', label: 'Tất cả', query: { reviewStatus: 'PENDING' }, adminOnly: true },
]);

export function isUnassigned(question) {
  return isPending(question) && assignmentOf(question).status === 'UNASSIGNED';
}

export const INBOX_CLIENT_FILTERS = Object.freeze({
  unassigned: (question) => isUnassigned(question),
  resubmitted: (question) => isResubmission(question),
});

export function inboxTabsFor(user) {
  return INBOX_TABS.filter((tab) => !tab.adminOnly || user?.role === 'Admin');
}

/** Câu đã từng có phiếu kiểm duyệt nay quay lại hàng chờ (giảng viên sửa và gửi lại). */
export function isResubmission(question) {
  return question?.review_status === 'PENDING'
    && Boolean(question?.latest_review_id)
    && question?.secondary_review?.status !== 'AWAITING_SECONDARY';
}

export const SORT_OPTIONS = Object.freeze([
  { value: 'priority', label: 'Ưu tiên xử lý' },
  { value: 'oldest', label: 'Gửi lâu nhất' },
  { value: 'newest', label: 'Gửi mới nhất' },
  { value: 'ai_lowest', label: 'Điểm AI thấp trước' },
  { value: 'updated', label: 'Cập nhật gần nhất' },
]);

const OBJECT_ID_PATTERN = /^[a-f\d]{24}$/i;

export function isObjectId(value) {
  return typeof value === 'string' && OBJECT_ID_PATTERN.test(value);
}

export function refId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return String(value.id || value._id || '');
}

export function childId(item) {
  return refId(item);
}

export function formatScore(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '--';
}

export function formatPercent(value) {
  return typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)}%` : '--';
}

export function formatDateTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function formatWaiting(value, now = Date.now()) {
  if (!value) return '';
  const submitted = new Date(value);
  if (Number.isNaN(submitted.getTime())) return '';
  const hours = Math.max(0, (now - submitted.getTime()) / 3600000);
  if (hours < 1) return 'dưới 1 giờ';
  if (hours < 24) return `${Math.floor(hours)} giờ`;
  return `${Math.floor(hours / 24)} ngày`;
}

export function formatRemaining(value, now = Date.now()) {
  if (!value) return '';
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return '';
  const minutes = Math.round((target.getTime() - now) / 60000);
  if (minutes <= 0) return 'đã hết hạn';
  if (minutes < 60) return `còn ${minutes} phút`;
  return `còn ${Math.floor(minutes / 60)} giờ ${minutes % 60} phút`;
}

export function questionTypeKey(question) {
  return String(question?.classification?.assessment_type || question?.question_type || '').toLowerCase();
}

export function bloomText(question) {
  const bloom = question?.classification?.bloom || {};
  if (!bloom.level) return 'Chưa gắn Bloom';
  return `Bloom ${bloom.level}${bloom.name ? ` - ${bloom.name}` : ''}`;
}

export function subjectText(question, subjectsById) {
  const snapshot = question?.subject || question?.review_submission?.subject || {};
  const fromSnapshot = snapshot.name || snapshot.subject_name;
  if (fromSnapshot) return [snapshot.code || snapshot.subject_code, fromSnapshot].filter(Boolean).join(' - ');
  const id = refId(question?.subject_id || question?.classification?.subject);
  const subject = subjectsById?.get?.(id);
  if (subject) return [subject.subject_code, subject.subject_name].filter(Boolean).join(' - ');
  return 'Chưa gắn học phần';
}

export function correctAnswerKeys(question) {
  return String(question?.question_data?.correct_answer || '')
    .split(/[,;|]/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

export function assignmentOf(question) {
  const assignment = question?.review_assignment || {};
  return {
    status: assignment.status || 'UNASSIGNED',
    reviewerUserId: refId(assignment.reviewer_user_id),
    assignedAt: assignment.assigned_at || null,
    claimedAt: assignment.claimed_at || null,
    lockExpiresAt: assignment.lock_expires_at || null,
  };
}

export function isLockExpired(question, now = Date.now()) {
  const { lockExpiresAt } = assignmentOf(question);
  if (!lockExpiresAt) return false;
  const expires = new Date(lockExpiresAt).getTime();
  return Number.isFinite(expires) && expires <= now;
}

export function isAssignedToUser(question, user) {
  const reviewerId = assignmentOf(question).reviewerUserId;
  return Boolean(reviewerId && user?.id && reviewerId === String(user.id));
}

export function isAdmin(user) {
  return user?.role === 'Admin';
}

export function isPending(question) {
  return question?.review_status === 'PENDING';
}

export function isAwaitingSecondary(question) {
  return question?.secondary_review?.status === 'AWAITING_SECONDARY';
}

/** Người duyệt lần 1 không được tự duyệt lần 2 (backend chặn, UI phản ánh trước). */
export function isBlockedFromSecondary(question, user) {
  if (!isAwaitingSecondary(question)) return false;
  const primary = refId(question?.secondary_review?.primary_reviewer_user_id);
  return Boolean(primary && user?.id && primary === String(user.id));
}

export function canClaim(question, user, now = Date.now()) {
  if (!isPending(question)) return false;
  const { status } = assignmentOf(question);
  return status === 'UNASSIGNED'
    || isAssignedToUser(question, user)
    || isLockExpired(question, now)
    || isAdmin(user);
}

export function canRelease(question, user) {
  if (!isPending(question)) return false;
  const { status } = assignmentOf(question);
  if (status === 'UNASSIGNED') return false;
  return isAdmin(user) || isAssignedToUser(question, user);
}

/** Quyền chốt kết quả: Admin luôn được; Người duyệt cần đang giữ khóa còn hạn. */
export function canDecide(question, user, now = Date.now()) {
  if (!isPending(question)) return false;
  if (isAdmin(user)) return true;
  const { status } = assignmentOf(question);
  return status === 'IN_REVIEW' && isAssignedToUser(question, user) && !isLockExpired(question, now);
}

export function isEvaluationBusy(question) {
  return ['QUEUED', 'PROCESSING', 'RUNNING'].includes(question?.evaluation_status);
}

export function canRequestEvaluation(question) {
  return Boolean(question) && isPending(question) && !isEvaluationBusy(question) && question.evaluation_status !== 'PASSED';
}

export function assignmentLabel(question, user, now = Date.now()) {
  const { status } = assignmentOf(question);
  const mine = isAssignedToUser(question, user);
  if (!isPending(question)) return '';
  if (status === 'IN_REVIEW' && isLockExpired(question, now)) return mine ? 'Khoá của tôi đã hết hạn' : 'Khoá đã hết hạn';
  if (status === 'IN_REVIEW') return mine ? 'Tôi đang xử lý' : 'Người khác đang xử lý';
  if (status === 'ASSIGNED') return mine ? 'Được giao cho tôi' : 'Đã giao người khác';
  return 'Chưa có người nhận';
}

export function assignmentTone(question, user, now = Date.now()) {
  const { status } = assignmentOf(question);
  if (status === 'IN_REVIEW' && isLockExpired(question, now)) return 'warn';
  if (isAssignedToUser(question, user)) return 'info';
  if (status === 'UNASSIGNED') return 'outline';
  return '';
}

export function qualityOf(question) {
  const summary = question?.quality_summary || {};
  if (summary.error) return { score: null, color: null };
  return {
    score: typeof summary.overall_score === 'number' ? summary.overall_score : null,
    color: summary.color || null,
  };
}

export function queueWarnings(question) {
  const warnings = [];
  if (!question?.sources || question.sources.length === 0) warnings.push('Thiếu nguồn');
  if (question?.evaluation_status === 'STALE') warnings.push('Nội dung đã đổi sau lần AI chấm');
  if (question?.evaluation_status === 'ERROR') warnings.push('AI lỗi');
  if (isAwaitingSecondary(question)) warnings.push('Cần duyệt lần 2');
  if (isResubmission(question)) warnings.push('Gửi lại sau sửa');
  return warnings;
}

export function defaultDraft(question, decision) {
  return {
    questionId: question.id,
    checklist: checklistForType(questionTypeKey(question)).map((item) => ({ ...item, passed: false })),
    decision,
    overallNote: '',
    overrideReason: '',
    secondaryRequired: false,
    secondaryReason: '',
    criteria: REVIEW_CRITERIA.map((item) => ({
      key: item.key,
      rating: decision === 'APPROVED' ? 'PASS' : 'REVIEW',
      note: '',
      source_chunk_id: '',
      touched: false,
    })),
    issues: [],
  };
}

/** Ghép bản nháp đã lưu (server/local) với khung mặc định, bỏ trường thừa của phiên bản cũ. */
export function restoreDraft(question, decision, saved) {
  const fallback = defaultDraft(question, decision);
  if (!saved || typeof saved !== 'object') return fallback;
  const savedCriteria = Array.isArray(saved.criteria) ? saved.criteria : [];
  const savedChecklist = Array.isArray(saved.checklist) ? saved.checklist : [];
  return {
    ...fallback,
    checklist: fallback.checklist.map((item) => {
      const match = savedChecklist.find((entry) => entry?.key === item.key);
      return match ? { ...item, passed: Boolean(match.passed) } : item;
    }),
    overallNote: typeof saved.overallNote === 'string' ? saved.overallNote : '',
    overrideReason: typeof saved.overrideReason === 'string' ? saved.overrideReason : '',
    secondaryRequired: Boolean(saved.secondaryRequired),
    secondaryReason: typeof saved.secondaryReason === 'string' ? saved.secondaryReason : '',
    criteria: fallback.criteria.map((item) => {
      const match = savedCriteria.find((entry) => entry?.key === item.key);
      if (!match) return item;
      return {
        ...item,
        rating: CRITERION_RATINGS.some((rating) => rating.value === match.rating) ? match.rating : item.rating,
        note: typeof match.note === 'string' ? match.note : '',
        source_chunk_id: typeof match.source_chunk_id === 'string' ? match.source_chunk_id : '',
        touched: Boolean(match.touched),
      };
    }),
    issues: Array.isArray(saved.issues)
      ? saved.issues.map((issue, index) => ({
          id: issue?.id || `issue-${index}`,
          title: String(issue?.title || ''),
          severity: ISSUE_SEVERITY.some((item) => item.value === issue?.severity) ? issue.severity : 'MEDIUM',
          detail: String(issue?.detail || ''),
          source_chunk_id: String(issue?.source_chunk_id || ''),
          page_number: issue?.page_number ? String(issue.page_number) : '',
        }))
      : [],
  };
}

export function compactIssues(issues) {
  return (issues || [])
    .map((issue) => {
      const page = Number(issue.page_number);
      const detail = String(issue.detail || '').trim().slice(0, 1000);
      // Backend bắt buộc tiêu đề; lỗi chỉ có mô tả thì lấy đoạn đầu mô tả làm tiêu đề.
      const title = (String(issue.title || '').trim() || detail.split('\n')[0]).slice(0, 160);
      return {
        title,
        severity: ISSUE_SEVERITY.some((item) => item.value === issue.severity) ? issue.severity : 'MEDIUM',
        detail,
        source_chunk_id: issue.source_chunk_id || null,
        page_number: Number.isInteger(page) && page > 0 ? page : null,
      };
    })
    .filter((issue) => issue.title);
}

/**
 * Tiêu chí người duyệt không tự chấm sẽ lấy theo kết luận: Duyệt thì "Đạt", còn lại "Xem lại".
 * Nhờ vậy phiếu vẫn đủ 5 tiêu chí cho thống kê mà không bắt người duyệt chấm từng mục.
 */
export function effectiveCriteria(draft) {
  return (draft?.criteria || []).map((item) => (
    item.touched ? item : { ...item, rating: draft.decision === 'APPROVED' ? 'PASS' : 'REVIEW' }
  ));
}

export function needsOverride(question, draft) {
  return draft?.decision === 'APPROVED' && question?.evaluation_status !== 'PASSED';
}

/** Trả về thông báo lỗi đầu tiên, hoặc chuỗi rỗng nếu phiếu hợp lệ. */
export function validateDraft(question, draft, user, now = Date.now()) {
  if (!question || !draft) return 'Chưa có phiếu kiểm duyệt.';
  if (!canDecide(question, user, now)) return 'Bạn cần nhận câu hỏi và giữ khoá còn hạn trước khi chốt kết quả.';
  if (isEvaluationBusy(question) && draft.decision === 'APPROVED') return 'AI đang đánh giá câu này. Chờ có kết quả trước khi duyệt.';
  if (draft.decision === 'APPROVED' && isBlockedFromSecondary(question, user)) {
    return 'Bạn đã duyệt lần 1 câu này, cần một người duyệt khác duyệt lần 2.';
  }
  const criteria = effectiveCriteria(draft);
  if (criteria.length !== REVIEW_CRITERIA.length) return 'Cần đánh giá đủ 5 tiêu chí.';
  if (draft.decision === 'APPROVED' && (draft.checklist || []).some((item) => !item.passed)) {
    return 'Đánh dấu đủ các mục trong danh sách kiểm tra trước khi duyệt.';
  }
  if (draft.decision === 'APPROVED' && criteria.some((item) => item.rating === 'FAIL')) {
    return 'Không thể duyệt khi còn tiêu chí "Không đạt". Chọn Cần sửa hoặc xem lại tiêu chí.';
  }
  if (needsOverride(question, draft) && !String(draft.overrideReason || '').trim()) {
    return 'AI chưa đề xuất đạt. Ghi lý do bạn vẫn duyệt câu này.';
  }
  const issues = compactIssues(draft.issues);
  if (draft.decision === 'NEEDS_REVISION' && issues.length === 0) {
    return 'Thêm ít nhất một lỗi để giảng viên biết cần sửa gì.';
  }
  if (draft.decision === 'REJECTED' && !String(draft.overallNote || '').trim() && issues.length === 0) {
    return 'Ghi lý do từ chối.';
  }
  if (draft.secondaryRequired && draft.decision === 'APPROVED' && !String(draft.secondaryReason || draft.overallNote || '').trim()) {
    return 'Ghi lý do cần duyệt lần 2.';
  }
  return '';
}

export function buildReviewPayload(question, draft) {
  const overallNote = String(draft.overallNote || '').trim();
  const payload = {
    expected_version: question.current_version,
    decision: draft.decision,
    note: overallNote,
    review_form: {
      checklist: (draft.checklist || []).map((item) => ({
        key: item.key,
        label: String(item.label || item.key).slice(0, 160),
        passed: Boolean(item.passed),
        note: '',
      })),
      criterion_assessments: effectiveCriteria(draft).map((item) => {
        const meta = REVIEW_CRITERIA.find((criterion) => criterion.key === item.key);
        return {
          key: item.key,
          label: meta?.label || item.key,
          rating: item.rating,
          note: String(item.note || '').trim(),
          source_chunk_id: item.source_chunk_id || null,
          page_number: null,
        };
      }),
      overall_note: overallNote,
      revision_issues: compactIssues(draft.issues),
    },
  };
  if (draft.decision === 'APPROVED' && draft.secondaryRequired && !isAwaitingSecondary(question)) {
    payload.secondary_required = true;
    payload.secondary_reason = String(draft.secondaryReason || overallNote).trim();
  }
  if (needsOverride(question, draft)) {
    const quality = question.quality_summary || {};
    payload.override = {
      applied: true,
      reason: String(draft.overrideReason || '').trim(),
      ...(typeof quality.overall_score === 'number' ? { score: quality.overall_score } : {}),
      ...(['GREEN', 'YELLOW', 'RED'].includes(quality.color) ? { color: quality.color } : {}),
    };
  }
  return payload;
}

/** Quyết định của người duyệt có khác hướng với gợi ý AI không (dùng để nhắc, không chặn). */
export function differsFromAi(question, decision) {
  const status = question?.evaluation_status;
  if (!decision || !['PASSED', 'FAILED'].includes(status)) return false;
  return (decision === 'APPROVED') !== (status === 'PASSED');
}

export function reviewIssuesOf(review) {
  if (Array.isArray(review?.revision_issues)) return review.revision_issues;
  if (Array.isArray(review?.review_form?.revision_issues)) return review.review_form.revision_issues;
  return [];
}

export function pageRangeLabel(pageRange = {}) {
  if (Array.isArray(pageRange?.pages) && pageRange.pages.length > 0) return `Trang ${pageRange.pages.join(', ')}`;
  if (pageRange?.start && pageRange?.end && pageRange.start !== pageRange.end) return `Trang ${pageRange.start}-${pageRange.end}`;
  if (pageRange?.start) return `Trang ${pageRange.start}`;
  return 'Chưa rõ trang';
}

export function firstSourcePage(source) {
  const pageNumber = source?.pages?.[0]?.page_number || source?.page_range?.start;
  return pageNumber ? Number(pageNumber) : 1;
}

export function evaluationModeLabel(mode) {
  if (mode === 'local_llm') return 'Mô hình AI của hệ thống';
  if (mode === 'heuristic_fallback') return 'Đánh giá dự phòng';
  if (mode === 'heuristic') return 'Chấm nhanh theo luật';
  return mode ? 'Hệ thống hỗ trợ' : '--';
}
