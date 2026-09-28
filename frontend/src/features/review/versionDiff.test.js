import test from 'node:test';
import assert from 'node:assert/strict';

import { baselineReview, diffVersions, wordDiff } from './versionDiff.js';

function version(overrides = {}) {
  return {
    version: 1,
    content: 'Ngăn xếp hoạt động theo nguyên tắc nào?',
    question_data: {
      options: { A: 'LIFO', B: 'FIFO' },
      correct_answer: 'A',
      explanation: 'Phần tử vào sau ra trước.',
    },
    classification: {
      subject: { id: 's1', code: 'CTDL', name: 'Cấu trúc dữ liệu' },
      chapter: { id: 'c1' },
      assessment_type: 'TRAC_NGHIEM',
      bloom: { level: 2, name: 'Hiểu' },
      difficulty: 'de',
    },
    clos: [{ id: 'clo1', code: 'CLO1' }],
    sources: [{ chunk_id: 'k1', context_excerpt: 'Stack là cấu trúc LIFO', page_number: 3 }],
    ...overrides,
  };
}

test('wordDiff marks only the words that changed', () => {
  const result = wordDiff('Ngăn xếp theo nguyên tắc FIFO', 'Ngăn xếp theo nguyên tắc LIFO');
  assert.deepEqual(result.before.filter((item) => item.type === 'removed').map((item) => item.text), ['FIFO']);
  assert.deepEqual(result.after.filter((item) => item.type === 'added').map((item) => item.text), ['LIFO']);
  assert.equal(result.before.map((item) => item.text).join(''), 'Ngăn xếp theo nguyên tắc FIFO');
});

test('wordDiff falls back to whole blocks for very long text', () => {
  const long = Array.from({ length: 600 }, (_, index) => `w${index}`).join(' ');
  assert.equal(wordDiff(long, `${long} thêm`), null);
});

test('diffVersions reports classification, CLO and source changes', () => {
  const previous = version();
  const current = version({
    version: 2,
    question_data: { ...previous.question_data, correct_answer: 'B' },
    classification: {
      ...previous.classification,
      chapter: { id: 'c2' },
      bloom: { level: 3, name: 'Vận dụng' },
      difficulty: 'kho',
    },
    clos: [{ id: 'clo2', code: 'CLO2' }],
    sources: [{ chunk_id: 'k2', context_excerpt: 'Queue là FIFO', page_number: 5 }],
  });
  const changes = diffVersions(previous, current, { chapterLabel: (id) => ({ c1: 'Chương 1', c2: 'Chương 2' }[id]) });
  const byKey = Object.fromEntries(changes.map((change) => [change.key, change]));

  assert.deepEqual(Object.keys(byKey).sort(), ['answer', 'bloom', 'chapter', 'clos', 'difficulty', 'sources']);
  assert.equal(byKey.answer.before, 'A');
  assert.equal(byKey.bloom.after, 'Bloom 3 - Vận dụng');
  assert.equal(byKey.difficulty.after, 'Khó');
  assert.equal(byKey.chapter.before, 'Chương 1');
  assert.equal(byKey.clos.after, 'CLO2');
  assert.deepEqual(byKey.sources.removed, ['Trang 3: Stack là cấu trúc LIFO']);
  assert.deepEqual(byKey.sources.added, ['Trang 5: Queue là FIFO']);
});

test('diffVersions returns nothing for identical versions', () => {
  assert.deepEqual(diffVersions(version(), version({ version: 2 })), []);
});

test('baselineReview picks the latest reviewed older version of any decision', () => {
  const question = { current_version: 4 };
  const reviews = [
    { question_version: 4, decision: 'NEEDS_REVISION', reviewed_at: '2026-09-03' },
    { question_version: 3, decision: 'APPROVED', reviewed_at: '2026-09-02' },
    { question_version: 1, decision: 'NEEDS_REVISION', reviewed_at: '2026-09-01' },
  ];
  assert.equal(baselineReview(question, reviews).question_version, 3);
  assert.equal(baselineReview({ current_version: 1 }, reviews), null);
});
