export const REVIEW_TEMPLATE_STORAGE_VERSION = 1;

export const DEFAULT_REVIEW_COMMENT_TEMPLATES = Object.freeze([
  {
    id: 'approved-source-aligned',
    title: 'Đạt, bám sát nguồn',
    body: 'Câu hỏi đạt yêu cầu, đáp án và giải thích bám sát tài liệu nguồn.',
    decision: 'APPROVED',
    built_in: true,
  },
  {
    id: 'needs-answer-fix',
    title: 'Cần sửa đáp án',
    body: 'Cần kiểm tra lại đáp án đúng và phần giải thích để khớp với nội dung nguồn.',
    decision: 'NEEDS_REVISION',
    built_in: true,
  },
  {
    id: 'reject-off-source',
    title: 'Từ chối do lệch nguồn',
    body: 'Câu hỏi chưa bám sát tài liệu nguồn hoặc không đủ căn cứ để đưa vào ngân hàng câu hỏi.',
    decision: 'REJECTED',
    built_in: true,
  },
]);

export function reviewTemplateStorageKey(user) {
  const owner = user?.id || user?.uid || user?.email || 'anonymous';
  return `qbankctu:review-comment-templates:${owner}`;
}

export function normalizeReviewTemplate(template) {
  const title = String(template?.title || '').trim();
  const body = String(template?.body || '').trim();
  if (!title || !body) return null;
  return {
    id: String(template?.id || `tpl-${Date.now()}`),
    title: title.slice(0, 80),
    body: body.slice(0, 1000),
    decision: template?.decision || 'all',
    built_in: Boolean(template?.built_in),
    updated_at: template?.updated_at || null,
  };
}

export function parseSavedReviewTemplates(rawValue) {
  if (!rawValue) return [];
  try {
    const payload = JSON.parse(rawValue);
    const items = Array.isArray(payload) ? payload : payload?.items;
    if (!Array.isArray(items)) return [];
    return items.map(normalizeReviewTemplate).filter(Boolean);
  } catch {
    return [];
  }
}

export function encodeSavedReviewTemplates(items) {
  return JSON.stringify({
    version: REVIEW_TEMPLATE_STORAGE_VERSION,
    items: items.map(normalizeReviewTemplate).filter(Boolean),
  });
}

export function templatesForDecision(items, decision) {
  return items.filter((item) => item.decision === 'all' || item.decision === decision);
}
