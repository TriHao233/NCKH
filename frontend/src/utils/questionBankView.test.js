import test from 'node:test';
import assert from 'node:assert/strict';
import { aiSummaryOf, authorOf, reviewStatusOf, statusTotal, subjectOf } from './questionBankView.js';

test('ai summary shows the score when there is one and the grading state otherwise', () => {
  assert.deepEqual(
    aiSummaryOf({ evaluation_status: 'PASSED', quality_summary: { overall_score: 0.7925, color: 'GREEN' } }),
    { text: '0.79 · Đạt tốt', tone: 'success' },
  );
  assert.deepEqual(aiSummaryOf({ evaluation_status: 'NOT_STARTED', quality_summary: {} }), { text: 'Chưa chấm', tone: 'muted' });
  assert.deepEqual(
    aiSummaryOf({ evaluation_status: 'ERROR', quality_summary: { overall_score: 0.5, error: { message: 'x' } } }),
    { text: 'AI lỗi', tone: 'danger' },
  );
  assert.equal(aiSummaryOf({ evaluation_status: 'QUEUED' }).tone, 'active');
});

test('author comes from the user list, then the submitter, then a clear fallback', () => {
  const users = new Map([['u1', { display_name: 'Cô Lan', email: 'lan@ctu.edu.vn' }]]);
  assert.deepEqual(authorOf({ author_user_ids: ['u1'] }, users), { id: 'u1', name: 'Cô Lan', email: 'lan@ctu.edu.vn' });
  const submitted = { author_user_ids: ['u2'], review_submission: { submitted_by: { id: 'u2', display_name: 'Thầy Hào' } } };
  assert.equal(authorOf(submitted, users).name, 'Thầy Hào');
  assert.equal(authorOf({ author_user_ids: ['gone'] }, users).name, 'Tài khoản không còn trong hệ thống');
  assert.equal(authorOf({}, users).name, 'Chưa rõ');
});

test('a submitter who is not an author is not shown as the author', () => {
  const question = { author_user_ids: ['u9'], review_submission: { submitted_by: { id: 'admin', display_name: 'Admin Demo' } } };
  assert.equal(authorOf(question).name, 'Tài khoản không còn trong hệ thống');
});

test('review status falls back to the raw value and counts add up', () => {
  assert.equal(reviewStatusOf({ review_status: 'APPROVED' }).label, 'Đã duyệt');
  assert.equal(reviewStatusOf({ review_status: 'ODD' }).label, 'ODD');
  assert.equal(statusTotal({ APPROVED: 4, DRAFT: 1, PENDING: 1 }), 6);
});

test('subject falls back to the catalog when the stored snapshot has no name', () => {
  const catalog = new Map([['s1', { subject_code: 'CTDL', subject_name: 'Cấu trúc dữ liệu' }]]);
  const stale = { subject_id: 's1', subject: { id: 's1', code: '', name: '' }, classification: { subject: { id: 's1' } } };
  assert.deepEqual(subjectOf(stale, catalog), { code: 'CTDL', name: 'Cấu trúc dữ liệu' });
  assert.deepEqual(subjectOf({ classification: { subject: { id: 's1', code: 'X', name: 'Môn X' } } }, catalog), { code: 'X', name: 'Môn X' });
  assert.deepEqual(subjectOf({ subject_id: 'missing' }, catalog), { code: '', name: '' });
});
