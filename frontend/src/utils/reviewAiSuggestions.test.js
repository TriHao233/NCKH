import assert from 'node:assert/strict';
import test from 'node:test';

import { evaluationInsights, mergeAiSuggestionsIntoDraft } from './reviewAiSuggestions.js';

const components = [
  { key: 'faithfulness', label: 'Bám sát nguồn' },
  { key: 'answer_relevancy', label: 'Đáp án phù hợp' },
  { key: 'bloom_alignment', label: 'Đúng Bloom' },
];

test('evaluation insights identify weak and suspiciously uniform scores', () => {
  const weak = evaluationInsights({
    scores: { faithfulness: 0.8, answer_relevancy: 0.4, bloom_alignment: 0.7 },
    policy: { thresholds: { pass_min: 0.65 } },
  }, components);
  const uniform = evaluationInsights({
    scores: { faithfulness: 0.8, answer_relevancy: 0.8, bloom_alignment: 0.8 },
  }, components);

  assert.deepEqual(weak.weakCriteria.map((item) => item.key), ['answer_relevancy']);
  assert.equal(weak.uniformScores, false);
  assert.equal(uniform.uniformScores, true);
});

test('AI suggestions populate a revision draft without saving a decision', () => {
  const draft = {
    overallNote: '',
    criteria: components.map((item) => ({ ...item, rating: 'REVIEW', note: '' })),
    issues: [],
  };
  const merged = mergeAiSuggestionsIntoDraft(draft, {
    scores: { faithfulness: 0.82, answer_relevancy: 0.42, bloom_alignment: 0.62 },
    feedback: {
      action: 'NEEDS_REVISION',
      severity: 'HIGH',
      summary: 'Cần sửa đáp án.',
      missing: ['Đáp án chưa được nguồn hỗ trợ.'],
    },
    evidence: { risks: ['Có thể chấm sai người học.'] },
  }, 123);

  assert.match(merged.overallNote, /NEEDS_REVISION.*Cần sửa đáp án/);
  assert.deepEqual(merged.criteria.map((item) => item.rating), ['PASS', 'FAIL', 'REVIEW']);
  assert.equal(merged.issues.length, 2);
  assert.equal(merged.issues[0].severity, 'HIGH');
  assert.equal(draft.issues.length, 0);
});
