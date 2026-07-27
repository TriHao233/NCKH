import test from 'node:test';
import assert from 'node:assert/strict';
import {
  BULK_QUESTION_CHANGE_NOTE,
  buildBulkQuestionUpdatePayload,
  filterSubmittableQuestions,
  selectedQuestionsForIds,
  summarizeBulkSettled,
} from './questionBulkActions.js';

test('bulk helpers select questions and keep only submittable statuses', () => {
  const questions = [
    { id: 'q1', review_status: 'DRAFT' },
    { id: 'q2', review_status: 'APPROVED' },
    { id: 'q3', review_status: 'NEEDS_REVISION' },
  ];

  const selected = selectedQuestionsForIds(questions, ['q3', 'q1']);
  const submittable = filterSubmittableQuestions(selected, new Set(['DRAFT', 'NEEDS_REVISION']));

  assert.deepEqual(selected.map((question) => question.id), ['q1', 'q3']);
  assert.deepEqual(submittable.map((question) => question.id), ['q1', 'q3']);
});

test('bulk update payload includes only requested metadata changes', () => {
  const payload = buildBulkQuestionUpdatePayload(
    { id: 'q1', current_version: 4 },
    { bloomLevel: '3', difficulty: 'kho', applyClo: true, cloIds: ['clo1'] },
  );

  assert.deepEqual(payload, {
    expected_version: 4,
    change_note: BULK_QUESTION_CHANGE_NOTE,
    bloom_level: 3,
    difficulty: 'kho',
    clo_ids: ['clo1'],
  });
  assert.equal(buildBulkQuestionUpdatePayload({ current_version: 1 }, {}), null);
});

test('bulk summary counts fulfilled and rejected results', () => {
  const summary = summarizeBulkSettled([
    { status: 'fulfilled', value: {} },
    { status: 'rejected', reason: new Error('Version conflict') },
    { status: 'rejected', reason: new Error('Permission denied') },
  ]);

  assert.deepEqual(summary, {
    success: 1,
    failed: 2,
    firstError: 'Version conflict',
  });
});
