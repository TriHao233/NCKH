import test from 'node:test';
import assert from 'node:assert/strict';

import {
  QUESTION_FILTER_DEFAULTS,
  encodeSavedQuestionFilters,
  parseSavedQuestionFilters,
  questionFilterStorageKey,
} from './questionFilterPresets.js';

test('question filter storage key is scoped to the signed-in user', () => {
  assert.equal(
    questionFilterStorageKey({ id: 'teacher-1', email: 'teacher@example.com' }),
    'qbankctu:question-filters:teacher-1',
  );
  assert.equal(
    questionFilterStorageKey({ email: 'teacher@example.com' }),
    'qbankctu:question-filters:teacher@example.com',
  );
});

test('saved question filters round-trip through storage payload', () => {
  const items = [
    {
      id: 'approved-hard',
      name: 'Approved hard questions',
      filters: {
        ...QUESTION_FILTER_DEFAULTS,
        statusFilter: 'APPROVED',
        difficultyFilter: 'kho',
        searchInput: 'queue',
      },
      updated_at: '2026-07-27T00:00:00.000Z',
    },
  ];

  assert.deepEqual(parseSavedQuestionFilters(encodeSavedQuestionFilters(items)), items);
});

test('saved question filter parser ignores bad payloads and backfills defaults', () => {
  assert.deepEqual(parseSavedQuestionFilters('not-json'), []);

  const parsed = parseSavedQuestionFilters(JSON.stringify({
    items: [
      { id: 'legacy', name: 'Legacy filter', filters: { statusFilter: 'PENDING' } },
      { id: '', name: 'Broken', filters: {} },
    ],
  }));

  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].filters.statusFilter, 'PENDING');
  assert.equal(parsed[0].filters.publicationFilter, 'all-publications');
  assert.equal(parsed[0].filters.createdFromFilter, '');
  assert.equal(parsed[0].filters.createdToFilter, '');
});
