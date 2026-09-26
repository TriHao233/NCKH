import test from 'node:test';
import assert from 'node:assert/strict';

import {
  isUnassigned,
  checklistForType,
  differsFromAi,
  isResubmission,
  buildReviewPayload,
  canClaim,
  canDecide,
  canRelease,
  canRequestEvaluation,
  childId,
  compactIssues,
  defaultDraft,
  isBlockedFromSecondary,
  restoreDraft,
  validateDraft,
} from './reviewModel.js';

const NOW = Date.parse('2026-09-26T10:00:00Z');
const reviewer = { id: 'r1', role: 'Reviewer' };
const otherReviewer = { id: 'r2', role: 'Reviewer' };
const admin = { id: 'a1', role: 'Admin' };

function checkAll(draft) {
  return { ...draft, checklist: draft.checklist.map((item) => ({ ...item, passed: true })) };
}

function question(overrides = {}) {
  return {
    id: 'q1',
    current_version: 3,
    review_status: 'PENDING',
    evaluation_status: 'PASSED',
    quality_summary: { overall_score: 0.81, color: 'GREEN' },
    review_assignment: {
      status: 'IN_REVIEW',
      reviewer_user_id: 'r1',
      lock_expires_at: '2026-09-26T10:20:00Z',
    },
    secondary_review: {},
    ...overrides,
  };
}

test('childId accepts plain ids and objects', () => {
  assert.equal(childId('abc'), 'abc');
  assert.equal(childId({ id: 'x' }), 'x');
  assert.equal(childId({ _id: 'y' }), 'y');
  assert.equal(childId(null), '');
});

test('reviewer must hold a live lock to decide; admin always can', () => {
  assert.equal(canDecide(question(), reviewer, NOW), true);
  assert.equal(canDecide(question(), otherReviewer, NOW), false);
  const expired = question({ review_assignment: { status: 'IN_REVIEW', reviewer_user_id: 'r1', lock_expires_at: '2026-09-26T09:00:00Z' } });
  assert.equal(canDecide(expired, reviewer, NOW), false);
  assert.equal(canDecide(expired, admin, NOW), true);
  assert.equal(canDecide(question({ review_status: 'APPROVED' }), admin, NOW), false);
});

test('claim and release rules follow assignment state', () => {
  const unassigned = question({ review_assignment: { status: 'UNASSIGNED' } });
  assert.equal(canClaim(unassigned, otherReviewer, NOW), true);
  assert.equal(canClaim(question(), otherReviewer, NOW), false);
  const expired = question({ review_assignment: { status: 'IN_REVIEW', reviewer_user_id: 'r1', lock_expires_at: '2026-09-26T09:00:00Z' } });
  assert.equal(canClaim(expired, otherReviewer, NOW), true);
  assert.equal(canRelease(unassigned, reviewer), false);
  assert.equal(canRelease(question(), reviewer), true);
  assert.equal(canRelease(question(), otherReviewer), false);
  assert.equal(canRelease(question(), admin), true);
});

test('AI evaluation can only be requested for pending, idle, non-passed questions', () => {
  assert.equal(canRequestEvaluation(question()), false);
  assert.equal(canRequestEvaluation(question({ evaluation_status: 'FAILED' })), true);
  assert.equal(canRequestEvaluation(question({ evaluation_status: 'PROCESSING' })), false);
  assert.equal(canRequestEvaluation(question({ evaluation_status: 'FAILED', review_status: 'APPROVED' })), false);
});

test('validation enforces decision specific requirements', () => {
  const q = question();
  const unchecked = defaultDraft(q, 'APPROVED');
  assert.match(validateDraft(q, unchecked, reviewer, NOW), /danh sách kiểm tra/);
  const approve = checkAll(unchecked);
  assert.equal(validateDraft(q, approve, reviewer, NOW), '');

  const failing = { ...approve, criteria: approve.criteria.map((item, index) => (index === 0 ? { ...item, rating: 'FAIL', touched: true } : item)) };
  assert.match(validateDraft(q, failing, reviewer, NOW), /Không đạt/);

  const aiFailed = question({ evaluation_status: 'FAILED' });
  assert.match(validateDraft(aiFailed, checkAll(defaultDraft(aiFailed, 'APPROVED')), reviewer, NOW), /lý do/);
  assert.equal(validateDraft(aiFailed, { ...checkAll(defaultDraft(aiFailed, 'APPROVED')), overrideReason: 'Đã đối chiếu nguồn' }, reviewer, NOW), '');

  assert.match(validateDraft(q, defaultDraft(q, 'NEEDS_REVISION'), reviewer, NOW), /lỗi/);
  assert.equal(
    validateDraft(q, { ...defaultDraft(q, 'NEEDS_REVISION'), issues: [{ title: 'Sai đáp án', detail: '' }] }, reviewer, NOW),
    '',
  );
  assert.match(validateDraft(q, defaultDraft(q, 'REJECTED'), reviewer, NOW), /từ chối/);
  assert.match(validateDraft(q, approve, otherReviewer, NOW), /nhận câu hỏi/);
});

test('primary reviewer cannot approve the secondary round', () => {
  const q = question({
    secondary_review: { status: 'AWAITING_SECONDARY', primary_reviewer_user_id: 'r1' },
  });
  assert.equal(isBlockedFromSecondary(q, reviewer), true);
  assert.match(validateDraft(q, checkAll(defaultDraft(q, 'APPROVED')), reviewer, NOW), /lần 2/);
  assert.equal(validateDraft(q, defaultDraft(q, 'NEEDS_REVISION'), reviewer, NOW).includes('lần 2'), false);
});

test('payload carries override, secondary request and compacted issues', () => {
  const q = question({ evaluation_status: 'FAILED', quality_summary: { overall_score: 0.52, color: 'YELLOW' } });
  const draft = {
    ...defaultDraft(q, 'APPROVED'),
    overallNote: '  Ổn  ',
    overrideReason: 'Đã đối chiếu',
    secondaryRequired: true,
    secondaryReason: 'Chủ đề mới',
    issues: [{ title: '', detail: '' }, { title: 'Chính tả', detail: 'Dòng 2', page_number: '4' }],
  };
  const payload = buildReviewPayload(q, draft);
  assert.equal(payload.expected_version, 3);
  assert.equal(payload.note, 'Ổn');
  assert.deepEqual(payload.override, { applied: true, reason: 'Đã đối chiếu', score: 0.52, color: 'YELLOW' });
  assert.equal(payload.secondary_required, true);
  assert.equal(payload.review_form.criterion_assessments.length, 5);
  assert.equal(payload.review_form.revision_issues.length, 1);
  assert.equal(payload.review_form.revision_issues[0].page_number, 4);
  assert.equal(payload.review_form.checklist.length, draft.checklist.length);
  assert.ok(payload.review_form.checklist.every((item) => item.label && typeof item.passed === 'boolean'));
});

test('secondary approval does not re-request another secondary round', () => {
  const q = question({ secondary_review: { status: 'AWAITING_SECONDARY', primary_reviewer_user_id: 'r9' } });
  const payload = buildReviewPayload(q, { ...defaultDraft(q, 'APPROVED'), secondaryRequired: true, secondaryReason: 'x' });
  assert.equal(payload.secondary_required, undefined);
});

test('restoreDraft sanitises legacy drafts', () => {
  const q = question();
  const restored = restoreDraft(q, 'NEEDS_REVISION', {
    overallNote: 'Ghi chú',
    checklist: [{ key: 'legacy', passed: true }],
    criteria: [{ key: 'faithfulness', rating: 'FAIL', note: 'Lệch' }, { key: 'unknown', rating: 'PASS' }],
    issues: [{ title: 'A', severity: 'BOGUS', page_number: 2 }],
  });
  assert.equal(restored.overallNote, 'Ghi chú');
  assert.ok(restored.checklist.every((item) => item.key !== 'legacy'));
  assert.equal(restored.criteria.length, 5);
  assert.equal(restored.criteria[0].rating, 'FAIL');
  assert.equal(restored.criteria[0].touched, false);
  assert.equal(restored.criteria[1].rating, 'REVIEW');
  assert.equal(restored.issues[0].severity, 'MEDIUM');
  assert.equal(restored.issues[0].page_number, '2');
});

test('compactIssues drops empty rows and invalid pages', () => {
  assert.deepEqual(compactIssues([{ title: ' ', detail: '' }, { title: 'X', page_number: 'abc' }]), [
    { title: 'X', severity: 'MEDIUM', detail: '', source_chunk_id: null, page_number: null },
  ]);
});

test('compactIssues derives a title from the detail when missing', () => {
  const [issue] = compactIssues([{ title: '', detail: 'Phương án C trùng ý với B\nChi tiết thêm' }]);
  assert.equal(issue.title, 'Phương án C trùng ý với B');
  assert.equal(issue.detail, 'Phương án C trùng ý với B\nChi tiết thêm');
});

test('checklist follows question type and stays within backend limit', () => {
  const items = checklistForType('trac_nghiem');
  assert.ok(items.length >= 3 && items.length <= 12);
  assert.ok(items.some((item) => item.key.startsWith('trac_nghiem_')));
  assert.equal(checklistForType('unknown').length, 2);
});

test('resubmission and AI disagreement helpers', () => {
  assert.equal(isResubmission(question({ latest_review_id: 'r' })), true);
  assert.equal(isResubmission(question({ latest_review_id: 'r', secondary_review: { status: 'AWAITING_SECONDARY' } })), false);
  assert.equal(isResubmission(question()), false);
  assert.equal(differsFromAi(question({ evaluation_status: 'FAILED' }), 'APPROVED'), true);
  assert.equal(differsFromAi(question({ evaluation_status: 'PASSED' }), 'APPROVED'), false);
  assert.equal(differsFromAi(question({ evaluation_status: 'PASSED' }), 'REJECTED'), true);
  assert.equal(differsFromAi(question({ evaluation_status: 'ERROR' }), 'REJECTED'), false);
});

test('untouched criteria follow the decision in the payload', () => {
  const q = question();
  const draft = defaultDraft(q, 'NEEDS_REVISION');
  const approved = buildReviewPayload(q, { ...draft, decision: 'APPROVED' });
  assert.ok(approved.review_form.criterion_assessments.every((item) => item.rating === 'PASS'));
  const touched = { ...draft, decision: 'APPROVED', criteria: draft.criteria.map((item, index) => (index === 1 ? { ...item, rating: 'REVIEW', touched: true } : item)) };
  const payload = buildReviewPayload(q, touched);
  assert.equal(payload.review_form.criterion_assessments[1].rating, 'REVIEW');
  assert.equal(payload.review_form.criterion_assessments[0].rating, 'PASS');
});

test('unassigned includes questions that never had an assignment record', () => {
  assert.equal(isUnassigned(question({ review_assignment: undefined })), true);
  assert.equal(isUnassigned(question({ review_assignment: { status: 'UNASSIGNED' } })), true);
  assert.equal(isUnassigned(question()), false);
  assert.equal(isUnassigned(question({ review_status: 'APPROVED', review_assignment: undefined })), false);
});
