import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAULT_REVIEW_COMMENT_TEMPLATES,
  encodeSavedReviewTemplates,
  parseSavedReviewTemplates,
  reviewTemplateStorageKey,
  templatesForDecision,
} from './reviewCommentTemplates.js';

test('review template storage key is scoped to the signed-in user', () => {
  assert.equal(
    reviewTemplateStorageKey({ id: 'reviewer-1', email: 'reviewer@example.com' }),
    'qbankctu:review-comment-templates:reviewer-1',
  );
  assert.equal(
    reviewTemplateStorageKey({ email: 'reviewer@example.com' }),
    'qbankctu:review-comment-templates:reviewer@example.com',
  );
});

test('review templates round-trip and trim unsafe payloads', () => {
  const parsed = parseSavedReviewTemplates(encodeSavedReviewTemplates([
    {
      id: 'needs-fix',
      title: '  Cần sửa  ',
      body: '  Bổ sung giải thích.  ',
      decision: 'NEEDS_REVISION',
      updated_at: '2026-07-27T00:00:00.000Z',
    },
    { id: 'broken', title: '', body: 'Missing title' },
  ]));

  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].title, 'Cần sửa');
  assert.equal(parsed[0].body, 'Bổ sung giải thích.');
  assert.equal(parsed[0].decision, 'NEEDS_REVISION');
});

test('review templates filter by decision while keeping generic templates', () => {
  const items = [
    ...DEFAULT_REVIEW_COMMENT_TEMPLATES,
    { id: 'generic', title: 'Ghi chú chung', body: 'Dùng được mọi quyết định.', decision: 'all' },
  ];
  const approved = templatesForDecision(items, 'APPROVED');

  assert.ok(approved.some((item) => item.id === 'approved-source-aligned'));
  assert.ok(approved.some((item) => item.id === 'generic'));
  assert.ok(!approved.some((item) => item.id === 'needs-answer-fix'));
});
